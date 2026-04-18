from __future__ import annotations

import asyncio
import math
import random

from dwarf_explorer.world.terrain import get_biome
from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import WORLD_SIZE, WALKABLE_TILES

_STRUCTURE_SEED_OFFSET = 2000
_PATH_SEED_OFFSET      = 3000
_SPAWN_BUFFER = 12

_WATER_BIOMES = {"deep_water", "shallow_water"}


def _near_spawn(x: int, y: int) -> bool:
    cx, cy = WORLD_SIZE // 2, WORLD_SIZE // 2
    return abs(x - cx) < _SPAWN_BUFFER and abs(y - cy) < _SPAWN_BUFFER


def _is_adjacent_to(x: int, y: int, seed: int, biome: str) -> bool:
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            if get_biome(nx, ny, seed) == biome:
                return True
    return False


def _norm2(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy)
    return (dx / m, dy / m) if m > 1e-9 else (1.0, 0.0)


def _rotate2(dx: float, dy: float, angle: float) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return (c * dx - s * dy, s * dx + c * dy)


def _is_blocked(x: float, y: float, seed: int, avoid_tiles: set[tuple[int, int]]) -> bool:
    """Return True if this position is water or a river tile."""
    ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
    iy = max(0, min(WORLD_SIZE - 1, int(round(y))))
    if (ix, iy) in avoid_tiles:
        return True
    return get_biome(ix, iy, seed) in _WATER_BIOMES


def _path_worm(
    start: tuple[int, int],
    end: tuple[int, int],
    seed: int,
    stop_tiles: set[tuple[int, int]],
    avoid_tiles: set[tuple[int, int]],
    max_steps: int = 700,
) -> list[tuple[int, int]]:
    """Perlin-worm path from start toward end that navigates around water.

    Uses persistent worm direction with ±80° fBm rotation and 40% convergence.
    Diagonal steps are widened to prevent gaps.
    Avoids water biomes and river tiles.
    """
    x, y = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    freq = 0.15
    path: list[tuple[int, int]] = []
    dx, dy = _norm2(ex - x, ey - y)

    for _ in range(max_steps):
        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))

        # Only add tile to path if it's not on water/river
        if not _is_blocked(x, y, seed, avoid_tiles):
            if not path or (ix, iy) != path[-1]:
                # Widen diagonals: fill corner tile to prevent gaps
                if path:
                    lx, ly = path[-1]
                    step_dx, step_dy = ix - lx, iy - ly
                    if abs(step_dx) == 1 and abs(step_dy) == 1:
                        path.append((lx + step_dx, ly))
                path.append((ix, iy))

        if len(path) > 5:
            for nx, ny in [(ix+1,iy),(ix-1,iy),(ix,iy+1),(ix,iy-1)]:
                if (nx, ny) in stop_tiles:
                    path.append((nx, ny))
                    return path
            if (ix, iy) in stop_tiles:
                return path

        # Worm direction: persistent momentum + Perlin rotation + convergence pull
        n = fbm(x * freq, y * freq, seed, octaves=3)
        rot = math.radians((n - 0.5) * 160.0)   # ±80°
        ndx, ndy = _norm2(*_rotate2(dx, dy, rot))
        tdx, tdy = _norm2(ex - x, ey - y)
        dx, dy = _norm2(0.40 * tdx + 0.60 * ndx, 0.40 * tdy + 0.60 * ndy)

        # Look ahead 5 steps to start steering before hitting water
        look_blocked = False
        for la in range(1, 6):
            lx = max(0.0, min(WORLD_SIZE - 1.0, x + dx * la))
            ly = max(0.0, min(WORLD_SIZE - 1.0, y + dy * la))
            if _is_blocked(lx, ly, seed, avoid_tiles):
                look_blocked = True
                break

        new_x = max(0.0, min(WORLD_SIZE - 1.0, x + dx))
        new_y = max(0.0, min(WORLD_SIZE - 1.0, y + dy))

        if look_blocked or _is_blocked(new_x, new_y, seed, avoid_tiles):
            deflected = False
            for try_deg in [45, -45, 90, -90, 135, -135, 180]:
                rdx, rdy = _norm2(*_rotate2(dx, dy, math.radians(try_deg)))
                tx = max(0.0, min(WORLD_SIZE - 1.0, x + rdx))
                ty = max(0.0, min(WORLD_SIZE - 1.0, y + rdy))
                if not _is_blocked(tx, ty, seed, avoid_tiles):
                    # Also check this deflection direction doesn't head into water soon
                    near_water = any(
                        _is_blocked(max(0.0,min(WORLD_SIZE-1.0,x+rdx*k)),
                                    max(0.0,min(WORLD_SIZE-1.0,y+rdy*k)),
                                    seed, avoid_tiles)
                        for k in range(2, 4)
                    )
                    if not near_water:
                        dx, dy = rdx, rdy
                        new_x, new_y = tx, ty
                        deflected = True
                        break
            if not deflected:
                # Last resort: try all 8 cardinal/diagonal directions
                for rdx, rdy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
                    rdx_f, rdy_f = _norm2(float(rdx), float(rdy))
                    tx = max(0.0, min(WORLD_SIZE-1.0, x + rdx_f))
                    ty = max(0.0, min(WORLD_SIZE-1.0, y + rdy_f))
                    if not _is_blocked(tx, ty, seed, avoid_tiles):
                        dx, dy = rdx_f, rdy_f
                        new_x, new_y = tx, ty
                        deflected = True
                        break

        x, y = new_x, new_y

    return path


def _group_caves(
    cave_positions: list[tuple[int, int]],
    rng: random.Random,
    max_group_size: int = 3,
    max_link_dist: float = 45.0,
) -> list[list[tuple[int, int]]]:
    """Group nearby cave tiles into shared cave systems.

    Tiles within max_link_dist of each other (and not yet grouped) are joined
    into one system of up to max_group_size entrances.
    """
    remaining = list(range(len(cave_positions)))
    rng.shuffle(remaining)
    used: set[int] = set()
    groups: list[list[tuple[int, int]]] = []

    for i in remaining:
        if i in used:
            continue
        pos = cave_positions[i]
        group = [pos]
        used.add(i)

        for j in remaining:
            if j in used or len(group) >= max_group_size:
                continue
            other = cave_positions[j]
            if math.hypot(other[0] - pos[0], other[1] - pos[1]) <= max_link_dist:
                group.append(other)
                used.add(j)

        groups.append(group)

    return groups


def _generate_structures_sync(seed: int) -> tuple[list[tuple[int, int, str]], list[list[tuple[int, int]]]]:
    """Synchronously compute all structure placements (excludes village paths).

    Returns list of (x, y, tile_type).
    Villages are placed as a SINGLE tile each.
    """
    rng = random.Random(seed + _STRUCTURE_SEED_OFFSET)
    overrides: list[tuple[int, int, str]] = []
    village_centers: list[tuple[int, int]] = []

    # --- Villages (4-6): plains/grass, single tile, minimum 40 tiles apart ---
    village_count = rng.randint(4, 6)
    found = 0
    for _ in range(800):
        if found >= village_count:
            break
        x = rng.randint(5, WORLD_SIZE - 6)
        y = rng.randint(5, WORLD_SIZE - 6)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) not in ('plains', 'grass'):
            continue
        if any(abs(x - vx) + abs(y - vy) < 40 for vx, vy in village_centers):
            continue
        village_centers.append((x, y))
        overrides.append((x, y, 'village'))
        # Surround the village tile with a 1-tile ring of path
        for ry in range(y - 1, y + 2):
            for rx in range(x - 1, x + 2):
                if (rx, ry) != (x, y) and 0 <= rx < WORLD_SIZE and 0 <= ry < WORLD_SIZE:
                    overrides.append((rx, ry, 'path'))
        found += 1

    # --- Shrines (6-10): on hills tiles ---
    shrine_count = rng.randint(6, 10)
    found = 0
    for _ in range(600):
        if found >= shrine_count:
            break
        x = rng.randint(1, WORLD_SIZE - 2)
        y = rng.randint(1, WORLD_SIZE - 2)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) == 'hills':
            overrides.append((x, y, 'shrine'))
            found += 1

    # --- Caves (10-16 tiles): walkable tile adjacent to mountain ---
    # Higher count because nearby tiles will be grouped into shared cave systems
    cave_count = rng.randint(10, 16)
    found = 0
    cave_positions: list[tuple[int, int]] = []
    for _ in range(2000):
        if found >= cave_count:
            break
        x = rng.randint(1, WORLD_SIZE - 2)
        y = rng.randint(1, WORLD_SIZE - 2)
        if _near_spawn(x, y):
            continue
        biome = get_biome(x, y, seed)
        if biome in WALKABLE_TILES and _is_adjacent_to(x, y, seed, 'mountain'):
            overrides.append((x, y, 'cave'))
            cave_positions.append((x, y))
            found += 1

    # --- Ruins (3-5): single tile on walkable terrain ---
    ruins_count = rng.randint(3, 5)
    found = 0
    for _ in range(500):
        if found >= ruins_count:
            break
        x = rng.randint(1, WORLD_SIZE - 2)
        y = rng.randint(1, WORLD_SIZE - 2)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) in WALKABLE_TILES:
            overrides.append((x, y, 'ruins'))
            found += 1

    cave_groups = _group_caves(cave_positions, rng)
    return overrides, cave_groups


def _generate_village_paths_sync(
    seed: int,
    village_positions: list[tuple[int, int]],
    bridge_positions: list[tuple[int, int]],
    existing_path_tiles: set[tuple[int, int]],
    river_tiles: set[tuple[int, int]],
) -> list[tuple[int, int, str]]:
    """Generate Perlin-worm paths connecting villages and bridges into a network.

    Each village connects to its 2 nearest targets (other villages or bridges).
    Each bridge connects to its nearest target to ensure bridge-to-bridge links.
    Paths navigate around water/river tiles.
    Returns list of (x, y, 'path') overrides.
    """
    rng = random.Random(seed + _PATH_SEED_OFFSET)
    path_tiles: set[tuple[int, int]] = set(existing_path_tiles)
    overrides: list[tuple[int, int, str]] = []

    all_targets = list(village_positions) + list(bridge_positions)
    # Water/river tiles to avoid
    avoid_tiles: set[tuple[int, int]] = set(river_tiles)

    def _connect(
        start: tuple[int, int], end: tuple[int, int], pseed: int,
        stop_override: set[tuple[int, int]] | None = None,
    ) -> None:
        worm = _path_worm(
            start=start,
            end=end,
            seed=pseed,
            stop_tiles=stop_override if stop_override is not None else path_tiles,
            avoid_tiles=avoid_tiles,
            max_steps=700,
        )
        for px, py in worm:
            if (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, 'path'))

    # --- Villages: connect to 2 nearest targets ---
    for i, (vx, vy) in enumerate(village_positions):
        candidates = [(math.hypot(tx - vx, ty - vy), (tx, ty))
                      for (tx, ty) in all_targets
                      if (tx, ty) != (vx, vy)]
        if not candidates:
            continue
        candidates.sort()

        targets_to_connect = [candidates[0][1]]
        if len(candidates) > 1 and candidates[1][0] < candidates[0][0] * 2.0:
            targets_to_connect.append(candidates[1][1])

        # Exclude this village's own 5×5 zone so the worm can't loop back to its ring
        own_zone = {(vx + dx, vy + dy) for dx in range(-3, 4) for dy in range(-3, 4)}
        stop_for_village = path_tiles - own_zone

        path_seed = (seed + _PATH_SEED_OFFSET + i * 7) & 0xFFFFFFFF
        for target in targets_to_connect:
            _connect((vx, vy), target, path_seed, stop_override=stop_for_village)
            path_seed = (path_seed + 1337) & 0xFFFFFFFF

    # --- Bridges: connect each bridge to its nearest target ---
    for j, (bx, by) in enumerate(bridge_positions):
        candidates = [(math.hypot(tx - bx, ty - by), (tx, ty))
                      for (tx, ty) in all_targets
                      if (tx, ty) != (bx, by)]
        if not candidates:
            continue
        candidates.sort()
        nearest_dist, nearest = candidates[0]
        if nearest_dist > 120:   # skip very distant bridges
            continue

        # Only connect if bridge isn't already adjacent to existing path
        already_connected = any(
            (bx + ddx, by + ddy) in path_tiles
            for ddx, ddy in [(0,1),(0,-1),(1,0),(-1,0)]
        )
        if already_connected:
            continue

        # Exclude own position so the worm leaves the bridge before it can stop
        own_zone = {(bx + dx, by + dy) for dx in range(-3, 4) for dy in range(-3, 4)}
        stop_for_bridge = path_tiles - own_zone

        bridge_seed = (seed + _PATH_SEED_OFFSET + 5000 + j * 13) & 0xFFFFFFFF
        _connect((bx, by), nearest, bridge_seed, stop_override=stop_for_bridge)

    return overrides


async def place_structures(seed: int, db) -> None:
    """Generate all structures and store as tile_overrides.

    Order: base structures → bridges (already done) → inter-village paths.
    """
    from dwarf_explorer.world.caves import create_cave_system

    # 1. Base structures
    overrides, cave_groups = await asyncio.to_thread(_generate_structures_sync, seed)
    if overrides:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
            overrides,
        )

    # 2. Pre-generate cave systems (grouped overworld tiles → shared interior)
    for group in cave_groups:
        await create_cave_system(seed, group, db)

    # 3. Collect village positions from what we just placed
    village_positions = [(x, y) for x, y, t in overrides if t == 'village']

    # 4. Fetch bridge positions from DB (placed before structures)
    bridge_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'bridge'"
    )
    bridge_positions = [(r["world_x"], r["world_y"]) for r in bridge_rows]

    # 5. Existing path tiles (so worms stop at them)
    path_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'path'"
    )
    existing_paths = {(r["world_x"], r["world_y"]) for r in path_rows}

    # 6. River tiles (to avoid during path generation)
    river_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'river'"
    )
    river_tiles = {(r["world_x"], r["world_y"]) for r in river_rows}

    # 7. Generate inter-village/bridge paths
    if village_positions or bridge_positions:
        path_overrides = await asyncio.to_thread(
            _generate_village_paths_sync,
            seed, village_positions, bridge_positions, existing_paths, river_tiles,
        )
        if path_overrides:
            await db.executemany(
                "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
                path_overrides,
            )
