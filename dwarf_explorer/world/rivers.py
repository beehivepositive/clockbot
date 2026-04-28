from __future__ import annotations

import asyncio
import math
import random

from dwarf_explorer.config import WORLD_SIZE
from dwarf_explorer.world.noise import fbm
from dwarf_explorer.world.terrain import get_biome, get_coast_boundary

_WATER_BIOMES = {"deep_water", "shallow_water"}
_HIGH_COST_BIOMES = {"mountain", "snow"}
# Biomes rivers should avoid entering (ocean/beach zone)
_COAST_BIOMES = _WATER_BIOMES | {"sand"}
# All biomes to steer away from when tracing a path
_AVOID_BIOMES = _HIGH_COST_BIOMES | _COAST_BIOMES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm2(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy)
    return (dx / m, dy / m) if m > 1e-9 else (1.0, 0.0)


def _rotate2(dx: float, dy: float, angle: float) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return (c * dx - s * dy, s * dx + c * dy)


# ── Gradient (path of least resistance) ──────────────────────────────────────
# Sampling points are clamped to the map so edge tiles get valid gradients.

def _gradient_dir(
    x: float, y: float,
    seed: int, freq: float, octaves: int,
    delta: float = 8.0,
) -> tuple[float, float]:
    """Unit vector toward steepest terrain descent.

    Uses clamped sample points so the gradient is valid even at map edges.
    freq / octaves control resolution:
      low freq + few octaves  → large-scale valleys  (trunk)
      high freq + more octaves → fine gullies         (sub-tribs)
    """
    xl = max(0.0, x - delta); xr = min(WORLD_SIZE - 1.0, x + delta)
    yl = max(0.0, y - delta); yr = min(WORLD_SIZE - 1.0, y + delta)
    ex = (fbm(xr * freq, y  * freq, seed, octaves=octaves) -
          fbm(xl * freq, y  * freq, seed, octaves=octaves))
    ey = (fbm(x  * freq, yr * freq, seed, octaves=octaves) -
          fbm(x  * freq, yl * freq, seed, octaves=octaves))
    if abs(ex) + abs(ey) < 1e-9:
        return (1.0, 0.0)
    return _norm2(-ex, -ey)   # negate → toward lower elevation


# ── Trunk: noise-curve along primary axis ────────────────────────────────────

def _trunk_path(
    seed: int,
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Main trunk that enters from a random edge and exits at the opposite edge.

    Walks along the primary axis (W-E or N-S) visiting every column/row, with
    the cross-axis offset driven by two fBm layers (coarse bends + fine wiggles).
    Uses the terrain heightmap's fBm so bends follow large-scale valley shapes.
    """
    # Pick axis perpendicular to the ocean edge so rivers flow INTO the ocean,
    # not parallel along it.
    # edge 0=south, 1=north → ocean is horizontal → rivers flow N-S (axis=1)
    # edge 2=west,  3=east  → ocean is vertical   → rivers flow E-W (axis=0)
    ocean_edge, _ = get_coast_boundary(seed)
    axis = 1 if ocean_edge in (0, 1) else 0
    start_cross = float(rng.randint(40, WORLD_SIZE - 40))

    path: list[tuple[int, int]] = []
    for primary in range(WORLD_SIZE):
        # Coarse terrain sample gives big bends (~40-tile amplitude)
        coarse = fbm(primary * 0.5, start_cross * 0.05, seed, octaves=2)
        # Fine sample gives small wiggles
        fine   = fbm(primary * 1.5, start_cross * 0.05, seed ^ 0xABCD, octaves=2)
        cross_offset = (coarse - 0.5) * 80.0 + (fine - 0.5) * 14.0
        cross = int(round(max(15.0, min(WORLD_SIZE - 15.0, start_cross + cross_offset))))

        if axis == 0:
            tile = (primary, cross)
        else:
            tile = (cross, primary)

        if not path or tile != path[-1]:
            path.append(tile)

    return path


# ── Tributary worm (gradient-biased Perlin worm) ──────────────────────────────

def _trib_path(
    start: tuple[float, float],
    convergence: tuple[float, float],
    max_steps: int,
    seed: int,
    freq: float,
    octaves: int,
    noise_weight: float,
    conv_weight: float,
    stop_tiles: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Tributary path using gradient descent + convergence + Perlin-worm noise.

    Direction at each step:
      gradient (terrain descent) * grad_w
      + toward convergence target  * conv_weight
      + worm noise rotation        * noise_weight

    Stops when adjacent to any stop_tile, appending that tile so the
    tributary is guaranteed to physically connect to the parent stream.
    """
    x, y = float(start[0]), float(start[1])
    # Initial direction: toward convergence target
    dx, dy = _norm2(convergence[0] - x, convergence[1] - y)
    path: list[tuple[int, int]] = []

    for _ in range(max_steps):
        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))

        if not path or (ix, iy) != path[-1]:
            path.append((ix, iy))

        # Check connection to parent
        if len(path) > 2:
            if (ix, iy) in stop_tiles:
                break
            for nx, ny in [(ix+1,iy),(ix-1,iy),(ix,iy+1),(ix,iy-1)]:
                if (nx, ny) in stop_tiles:
                    path.append((nx, ny))
                    return path

        # --- Build composite direction ---
        # 1. Terrain gradient (path of least resistance)
        gdx, gdy = _gradient_dir(x, y, seed, freq, octaves)
        grad_w = 1.0 - noise_weight - conv_weight

        # 2. Convergence toward target
        tdx, tdy = _norm2(convergence[0] - x, convergence[1] - y)

        # 3. Perlin worm noise (rotates current direction)
        n = fbm(x * freq, y * freq, seed ^ 0xBEEF, octaves=3)
        rot = math.radians((n - 0.5) * 160.0)   # ±80° max
        ndx, ndy = _norm2(*_rotate2(dx, dy, rot))

        dx, dy = _norm2(
            gdx * grad_w + tdx * conv_weight + ndx * noise_weight,
            gdy * grad_w + tdy * conv_weight + ndy * noise_weight,
        )

        # Avoidance: steer away from mountains, ocean, and beach (sand) zones.
        # Try progressively larger rotations before accepting the step.
        nx_cand = int(round(x + dx))
        ny_cand = int(round(y + dy))
        if (0 <= nx_cand < WORLD_SIZE and 0 <= ny_cand < WORLD_SIZE and
                get_biome(nx_cand, ny_cand, seed) in _AVOID_BIOMES):
            for angle_deg in (30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180):
                c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
                rdx, rdy = _norm2(c * dx - s * dy, s * dx + c * dy)
                rnx = int(round(x + rdx))
                rny = int(round(y + rdy))
                if (0 <= rnx < WORLD_SIZE and 0 <= rny < WORLD_SIZE and
                        get_biome(rnx, rny, seed) not in _AVOID_BIOMES):
                    dx, dy = rdx, rdy
                    break
            # If no clear alternative, keep original direction rather than getting stuck

        x = max(0.0, min(WORLD_SIZE - 1.0, x + dx))
        y = max(0.0, min(WORLD_SIZE - 1.0, y + dy))

    return path


# ── Rendering ─────────────────────────────────────────────────────────────────

def _paint(path: list[tuple[int, int]], hw: int, tiles: set[tuple[int, int]]) -> None:
    for px, py in path:
        for dy in range(-hw, hw + 1):
            for dx in range(-hw, hw + 1):
                nx, ny = px + dx, py + dy
                if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
                    tiles.add((nx, ny))


# ── Bridges ───────────────────────────────────────────────────────────────────

def _local_flow_dir(
    path: list[tuple[int, int]], idx: int,
) -> tuple[float, float]:
    """Unit vector of river flow direction at path[idx]."""
    n = len(path)
    if n < 2:
        return (1.0, 0.0)
    if idx == 0:
        dx, dy = path[1][0] - path[0][0], path[1][1] - path[0][1]
    elif idx >= n - 1:
        dx, dy = path[-1][0] - path[-2][0], path[-1][1] - path[-2][1]
    else:
        dx, dy = path[idx + 1][0] - path[idx - 1][0], path[idx + 1][1] - path[idx - 1][1]
    return _norm2(float(dx), float(dy))


def _place_bridge_at(
    path: list[tuple[int, int]],
    idx: int,
    river_tiles: set[tuple[int, int]],
    bridge_tiles: set[tuple[int, int]],
) -> None:
    """Place a bridge spanning perpendicularly across a single contiguous river section.

    Uses the true perpendicular direction (can be diagonal), but walks outward from
    the spine tile and stops at the FIRST gap — so two parallel river sections are
    never joined by a single bridge.  Bridge is longer than it is wide because it
    spans the full river width (typically 3-5 tiles) as a single-tile-wide line.
    Both bank ends must be non-river and in-bounds or the bridge is skipped.
    """
    if idx < 0 or idx >= len(path):
        return
    px, py = path[idx]

    fdx, fdy = _local_flow_dir(path, idx)
    # Perpendicular direction (true float, not axis-snapped)
    pdx, pdy = -fdy, fdx

    # Walk outward in + direction until we leave the contiguous river block
    t_hi = 0
    for t in range(1, 20):
        nx = int(round(px + pdx * t))
        ny = int(round(py + pdy * t))
        if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
            break
        if (nx, ny) in river_tiles:
            t_hi = t
        else:
            break   # first gap — stop here, do not scan further

    # Walk outward in – direction until we leave the contiguous river block
    t_lo = 0
    for t in range(1, 20):
        nx = int(round(px - pdx * t))
        ny = int(round(py - pdy * t))
        if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
            break
        if (nx, ny) in river_tiles:
            t_lo = t
        else:
            break

    # Bank tiles are one step beyond the river edge on each side
    bx_hi = int(round(px + pdx * (t_hi + 1)))
    by_hi = int(round(py + pdy * (t_hi + 1)))
    bx_lo = int(round(px - pdx * (t_lo + 1)))
    by_lo = int(round(py - pdy * (t_lo + 1)))

    # Skip if either bank is out of bounds or still river (no dry land to connect)
    if not (0 <= bx_hi < WORLD_SIZE and 0 <= by_hi < WORLD_SIZE):
        return
    if not (0 <= bx_lo < WORLD_SIZE and 0 <= by_lo < WORLD_SIZE):
        return
    if (bx_hi, by_hi) in river_tiles or (bx_lo, by_lo) in river_tiles:
        return

    # Collect bridge tile positions bank-to-bank (inclusive)
    bridge_line: list[tuple[int, int]] = []
    for t in range(-(t_lo + 1), t_hi + 2):
        nx = int(round(px + pdx * t))
        ny = int(round(py + pdy * t))
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            bridge_line.append((nx, ny))

    # Add staircase connectors for diagonal steps so 4-dir movement can cross
    connectors: list[tuple[int, int]] = []
    for i in range(1, len(bridge_line)):
        ax, ay = bridge_line[i - 1]
        bx, by = bridge_line[i]
        if abs(bx - ax) == 1 and abs(by - ay) == 1:
            # Diagonal step — fill both corner tiles to guarantee walkability
            if 0 <= ax < WORLD_SIZE and 0 <= by < WORLD_SIZE:
                connectors.append((ax, by))
            if 0 <= bx < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
                connectors.append((bx, ay))

    # First lane
    for nx, ny in bridge_line + connectors:
        river_tiles.discard((nx, ny))
        bridge_tiles.add((nx, ny))

    # Second parallel lane (1 step in the flow direction) for 2-wide bridges
    fdx_i = round(fdx)
    fdy_i = round(fdy)
    for nx, ny in bridge_line + connectors:
        lx, ly = nx + fdx_i, ny + fdy_i
        if 0 <= lx < WORLD_SIZE and 0 <= ly < WORLD_SIZE:
            river_tiles.discard((lx, ly))
            bridge_tiles.add((lx, ly))


def _add_bridges(
    paths_orders: list[tuple[list[tuple[int, int]], int]],
    river_tiles: set[tuple[int, int]],
    bridge_tiles: set[tuple[int, int]],
    rng: random.Random,
) -> None:
    for path, order in paths_orders:
        if order < 3:
            continue
        if order >= 4:   # trunk: evenly spaced
            interval = rng.randint(35, 50)
            idx = interval
            while idx < len(path) - 5:
                _place_bridge_at(path, idx, river_tiles, bridge_tiles)
                idx += rng.randint(35, 50)
        elif len(path) >= 10:   # major trib: one at midpoint
            _place_bridge_at(path, len(path) // 2, river_tiles, bridge_tiles)


# ── World generation ──────────────────────────────────────────────────────────

def _generate_landings_sync(
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_tiles: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Generate river landing tiles on walkable land adjacent to river/bridge tiles.

    Landings are spaced at least 12 tiles apart and placed only on non-water,
    non-mountain biome land tiles.  Returns a list of (world_x, world_y) positions.
    """
    water = river_tiles | bridge_tiles
    _HIGH = {"mountain", "snow", "deep_water", "shallow_water"}
    candidates: list[tuple[int, int]] = []

    # Cardinal neighbours only — diagonal access from land is confusing
    for wx, wy in sorted(water):
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            lx, ly = wx + dx, wy + dy
            if not (0 <= lx < WORLD_SIZE and 0 <= ly < WORLD_SIZE):
                continue
            if (lx, ly) in water:
                continue
            biome = get_biome(lx, ly, seed)
            if biome in _HIGH:
                continue
            candidates.append((lx, ly))

    # Deduplicate candidates
    candidates = list(dict.fromkeys(candidates))

    # Greedy spacing filter: keep a landing only if it's ≥35 tiles from any kept landing.
    # Hard cap of 15 landings total. Use a coarse grid to avoid O(n²) comparisons.
    _MIN_DIST = 35
    _CELL = _MIN_DIST // 2  # 17
    occupied: dict[tuple[int, int], tuple[int, int]] = {}  # cell → kept pos
    kept: list[tuple[int, int]] = []

    for cx, cy in candidates:
        cell_x, cell_y = cx // _CELL, cy // _CELL
        too_close = False
        # Check the 5×5 neighbourhood of cells
        for dcx in range(-2, 3):
            for dcy in range(-2, 3):
                nb = occupied.get((cell_x + dcx, cell_y + dcy))
                if nb and abs(cx - nb[0]) + abs(cy - nb[1]) < _MIN_DIST:
                    too_close = True
                    break
            if too_close:
                break
        if not too_close:
            occupied[(cell_x, cell_y)] = (cx, cy)
            kept.append((cx, cy))
            if len(kept) >= 15:
                break

    return kept


def _generate_rivers_sync(
    seed: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    rng = random.Random(seed ^ 0xDEAD_BEEF)

    river_tiles: set[tuple[int, int]] = set()
    bridge_tiles: set[tuple[int, int]] = set()
    paths_orders: list[tuple[list[tuple[int, int]], int]] = []

    # Determine which world-edge map to the ocean so we can exclude it from
    # tributary starts.  Coast edge indices → trib-edge codes:
    #   coast 0=south → trib edge 1 (south world edge, y≈WORLD_SIZE)
    #   coast 1=north → trib edge 0 (north world edge, y≈0)
    #   coast 2=west  → trib edge 2 (west world edge,  x≈0)
    #   coast 3=east  → trib edge 3 (east world edge,  x≈WORLD_SIZE)
    ocean_edge, _ = get_coast_boundary(seed)
    _skip_trib_edge = {0: 1, 1: 0, 2: 2, 3: 3}[ocean_edge]

    # ── 1. Main trunk ─────────────────────────────────────────────────────────
    trunk = _trunk_path(seed, rng)
    _paint(trunk, hw=1, tiles=river_tiles)
    _paint(trunk[len(trunk)//4: 3*len(trunk)//4], hw=2, tiles=river_tiles)
    paths_orders.append((trunk, 4))
    trunk_set = set(trunk)

    # ── 2. Major tributaries ──────────────────────────────────────────────────
    # Each starts from a random position and converges to the nearest trunk tile.
    # Start positions are validated to be on land (not ocean/beach/sand zone).
    num_major = rng.randint(5, 8)
    all_river = set(river_tiles)

    for i in range(num_major):
        sx: float | None = None
        sy: float | None = None

        edge_start = rng.random() < 0.6   # 60% start from map edge
        if edge_start:
            m = 10
            for _ in range(20):
                edge = rng.randint(0, 3)
                if edge == _skip_trib_edge:
                    continue   # never start from the ocean-facing world edge
                if edge == 0:   csx, csy = float(rng.randint(m, WORLD_SIZE-m)), 2.0
                elif edge == 1: csx, csy = float(rng.randint(m, WORLD_SIZE-m)), float(WORLD_SIZE-3)
                elif edge == 2: csx, csy = 2.0, float(rng.randint(m, WORLD_SIZE-m))
                else:           csx, csy = float(WORLD_SIZE-3), float(rng.randint(m, WORLD_SIZE-m))
                if get_biome(int(csx), int(csy), seed) not in _COAST_BIOMES:
                    sx, sy = csx, csy
                    break

        # Fallback (or non-edge start): pick interior land tile
        if sx is None:
            for _ in range(20):
                csx = float(rng.randint(10, WORLD_SIZE - 10))
                csy = float(rng.randint(10, WORLD_SIZE - 10))
                if get_biome(int(csx), int(csy), seed) not in _COAST_BIOMES:
                    sx, sy = csx, csy
                    break

        if sx is None:
            continue   # couldn't find a valid land start

        # Convergence: nearest trunk tile to the start point
        conv = min(trunk, key=lambda t: math.hypot(t[0]-sx, t[1]-sy))  # type: ignore[arg-type]

        trib_seed = (seed ^ (0x1000 + i)) & 0xFFFFFFFF
        trib = _trib_path(
            start=(sx, sy),
            convergence=(float(conv[0]), float(conv[1])),
            max_steps=180,
            seed=trib_seed,
            freq=0.6,
            octaves=3,
            noise_weight=0.20,
            conv_weight=0.45,
            stop_tiles=all_river,
        )
        if len(trib) >= 8:
            _paint(trib, hw=1, tiles=river_tiles)
            paths_orders.append((trib, 3))
            all_river.update(river_tiles)

    all_river = set(river_tiles)

    # ── 3. Sub-tributaries ────────────────────────────────────────────────────
    # Use finer-grained terrain (more octaves) for the gradient.
    for i in range(rng.randint(10, 16)):
        sx2: float | None = None
        sy2: float | None = None
        for _ in range(20):
            csx = float(rng.randint(5, WORLD_SIZE - 5))
            csy = float(rng.randint(5, WORLD_SIZE - 5))
            if get_biome(int(csx), int(csy), seed) not in _COAST_BIOMES:
                sx2, sy2 = csx, csy
                break
        if sx2 is None:
            continue

        # Nearest river tile as convergence target
        sample = rng.sample(list(all_river), min(200, len(all_river)))
        conv_t = min(sample, key=lambda t: math.hypot(t[0]-sx2, t[1]-sy2))  # type: ignore[arg-type]

        sub_seed = (seed ^ (0x2000 + i)) & 0xFFFFFFFF
        sub = _trib_path(
            start=(sx2, sy2),
            convergence=(float(conv_t[0]), float(conv_t[1])),
            max_steps=120,
            seed=sub_seed,
            freq=0.9,
            octaves=4,
            noise_weight=0.25,
            conv_weight=0.40,
            stop_tiles=all_river,
        )
        if len(sub) >= 6:
            _paint(sub, hw=0, tiles=river_tiles)
            paths_orders.append((sub, 2))

    # ── 4. Bridges ────────────────────────────────────────────────────────────
    _add_bridges(paths_orders, river_tiles, bridge_tiles, rng)

    # ── 5. Strip river/bridge tiles from ocean, shallow-water, and sand zones ─
    # Rivers stop at the land/sand boundary — they do not enter the beach.
    # Bridge tiles are exempt (a bridge over a natural water body is valid).
    _river_filter = _WATER_BIOMES | {"sand"}
    river_tiles = {(x, y) for x, y in river_tiles
                   if get_biome(x, y, seed) not in _river_filter}

    bridge_tiles = {(x, y) for x, y in bridge_tiles
                    if get_biome(x, y, seed) not in _WATER_BIOMES}

    # ── 6. Generate river landings ────────────────────────────────────────────
    landing_tiles = _generate_landings_sync(seed, river_tiles, bridge_tiles)

    return list(river_tiles), list(bridge_tiles), landing_tiles


async def generate_rivers(seed: int, db) -> None:
    """Generate rivers, bridges, and landings; write to tile_overrides."""
    river_tiles, bridge_tiles, landing_tiles = await asyncio.to_thread(
        _generate_rivers_sync, seed
    )
    if river_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type)"
            " VALUES (?, ?, 'river')",
            [(x, y) for x, y in river_tiles],
        )
    if bridge_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type)"
            " VALUES (?, ?, 'bridge')",
            [(x, y) for x, y in bridge_tiles],
        )
    if landing_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type)"
            " VALUES (?, ?, 'river_landing')",
            [(x, y) for x, y in landing_tiles],
        )
