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


def _is_bridge_endpoint(
    bx: int, by: int, seed: int, river_tile_set: set[tuple[int, int]]
) -> bool:
    """Return True if this bridge tile has at least one non-water, non-river neighbour.

    Such tiles sit on the bank edge of a bridge — starting a path worm from
    them ensures the worm can immediately step onto dry land.
    """
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nx, ny = bx + dx, by + dy
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            if (nx, ny) not in river_tile_set:
                if get_biome(nx, ny, seed) not in _WATER_BIOMES:
                    return True
    return False


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


# ── Perlin-worm pathfinder ────────────────────────────────────────────────────

def _norm2(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy)
    return (dx / m, dy / m) if m > 1e-9 else (1.0, 0.0)


def _rotate2(dx: float, dy: float, angle: float) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return (c * dx - s * dy, s * dx + c * dy)


def _path_worm(
    start: tuple[int, int],
    target: tuple[int, int],
    seed: int,
    worm_seed: int,
    avoid_tiles: set[tuple[int, int]],
    stop_tiles: set[tuple[int, int]],
    passable_tiles: set[tuple[int, int]],
    max_steps: int = 700,
) -> list[tuple[int, int]]:
    """Perlin-worm road from start toward target.

    Moves in float space so paths meander organically (not Manhattan staircases).
    Strictly avoids water biomes and avoid_tiles (rivers).  Bridge tiles in
    passable_tiles bypass the water-biome check.  Stops early when adjacent to
    stop_tiles (existing path network).  If a step would land on a blocked tile,
    tries rotating the direction in 45° increments; terminates cleanly if all
    directions are impassable rather than looping forever.
    """
    x, y = float(start[0]), float(start[1])
    tx, ty = float(target[0]), float(target[1])
    dx, dy = _norm2(tx - x, ty - y)

    freq = 0.045
    path: list[tuple[int, int]] = []

    def _passable(nx: int, ny: int) -> bool:
        if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
            return False
        if (nx, ny) in avoid_tiles:
            return False
        if get_biome(nx, ny, seed) in _WATER_BIOMES and (nx, ny) not in passable_tiles:
            return False
        return True

    for step in range(max_steps):
        ix, iy = int(round(x)), int(round(y))

        # Add tile to path (dedup consecutive duplicates)
        if not path or (ix, iy) != path[-1]:
            if not _passable(ix, iy):
                break
            path.append((ix, iy))

        # Reached the target tile
        if (ix, iy) == (int(round(tx)), int(round(ty))):
            break

        # Reached existing path network (min length guard avoids self-connect)
        if len(path) > 10 and (ix, iy) in stop_tiles:
            break

        # Adjacent to existing path — append that tile and stop (natural Y-junction)
        if len(path) > 10:
            for adx, ady in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nb = (ix + adx, iy + ady)
                if nb in stop_tiles:
                    path.append(nb)
                    return path

        # --- Steer: Perlin noise rotation + pull toward target ---
        n = fbm(x * freq, y * freq, worm_seed, octaves=3)
        rot = math.radians((n - 0.5) * 160.0)   # ±80° wiggle — organic curves
        ndx, ndy = _norm2(*_rotate2(dx, dy, rot))
        tdx, tdy = _norm2(tx - x, ty - y)
        # 35% noise, 65% pull toward target — meanders but always converges
        dx, dy = _norm2(ndx * 0.35 + tdx * 0.65, ndy * 0.35 + tdy * 0.65)

        # Validate next step; rotate if blocked
        nx_int = int(round(x + dx))
        ny_int = int(round(y + dy))
        if not _passable(nx_int, ny_int):
            found = False
            for angle_deg in (45, -45, 90, -90, 135, -135, 180):
                rdx, rdy = _norm2(*_rotate2(tdx, tdy, math.radians(angle_deg)))
                rnx, rny = int(round(x + rdx)), int(round(y + rdy))
                if _passable(rnx, rny):
                    dx, dy = rdx, rdy
                    found = True
                    break
            if not found:
                break   # fully blocked — stop cleanly

        x = max(0.0, min(WORLD_SIZE - 1.0, x + dx))
        y = max(0.0, min(WORLD_SIZE - 1.0, y + dy))

    return path


# ── Structure generation ───────────────────────────────────────────────────────

def _group_caves(
    cave_positions: list[tuple[int, int]],
    rng: random.Random,
    max_group_size: int = 3,
    max_link_dist: float = 45.0,
) -> list[list[tuple[int, int]]]:
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


def _generate_structures_sync(
    seed: int,
) -> tuple[list[tuple[int, int, str]], list[list[tuple[int, int]]]]:
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


# ── Path generation ────────────────────────────────────────────────────────────

def _line_samples(
    start: tuple[int, int],
    end: tuple[int, int],
    oversample: int = 3,
) -> list[tuple[int, int]]:
    """Return integer tile positions along the straight line from start to end."""
    sx, sy = start
    ex, ey = end
    dist = math.hypot(ex - sx, ey - sy)
    steps = max(int(dist * oversample), 1)
    seen: set[tuple[int, int]] = set()
    pts: list[tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        ix = int(round(sx + t * (ex - sx)))
        iy = int(round(sy + t * (ey - sy)))
        if (ix, iy) not in seen:
            seen.add((ix, iy))
            pts.append((ix, iy))
    return pts


def _build_mst(positions: list[tuple[int, int]]) -> list[tuple[tuple[int,int], tuple[int,int]]]:
    """Greedy minimum spanning tree (nearest-neighbour Prim's) of positions."""
    if len(positions) < 2:
        return []
    connected = {positions[0]}
    remaining = set(positions[1:])
    edges: list[tuple[tuple[int,int], tuple[int,int]]] = []
    while remaining:
        best_dist = float("inf")
        best_edge = None
        for c in connected:
            for r in remaining:
                d = math.hypot(r[0] - c[0], r[1] - c[1])
                if d < best_dist:
                    best_dist = d
                    best_edge = (c, r)
        if best_edge is None:
            break
        edges.append(best_edge)
        connected.add(best_edge[1])
        remaining.discard(best_edge[1])
    return edges


def _is_water(x: int, y: int, seed: int, river_tiles: set[tuple[int, int]]) -> bool:
    """True if tile is water — either a river override OR a water biome tile."""
    return (x, y) in river_tiles or get_biome(x, y, seed) in _WATER_BIOMES


def _crossing_center(
    samples: list[tuple[int, int]],
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> tuple[float, float] | None:
    """Return center of water-crossing tiles (river overrides OR biome water, not bridges)."""
    crossings = [(x, y) for x, y in samples
                 if (x, y) not in bridge_all and _is_water(x, y, seed, river_tiles)]
    if not crossings:
        return None
    return (sum(x for x, y in crossings) / len(crossings),
            sum(y for x, y in crossings) / len(crossings))


def _generate_village_paths_sync(
    seed: int,
    village_positions: list[tuple[int, int]],
    bridge_endpoints: list[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
    existing_path_tiles: set[tuple[int, int]],
    river_tiles: set[tuple[int, int]],
) -> list[tuple[int, int, str]]:
    """Connect villages and bridge endpoints into a road network.

    Algorithm:
    1. Build MST connecting villages via nearest-neighbour Prim's.
    2. For each MST edge: if the straight line crosses a river, find the nearest
       bridge endpoint to the crossing and route through it as a waypoint.
    3. Generate each sub-segment as a straight line with Perlin perpendicular meander.
    4. After villages are connected, connect each isolated bridge endpoint to the
       nearest existing path node.
    """
    path_tiles: set[tuple[int, int]] = set(existing_path_tiles)
    overrides: list[tuple[int, int, str]] = []
    connected_pairs: set[frozenset] = set()

    def _add_segment(start: tuple[int, int], end: tuple[int, int]) -> None:
        pair = frozenset([start, end])
        if pair in connected_pairs:
            return
        connected_pairs.add(pair)
        worm_seed = (seed ^ (start[0] * 31 + start[1] * 97 +
                             end[0] * 7 + end[1] * 13)) & 0xFFFFFFFF

        # Exclude our own start zone so the worm doesn't Y-junction on itself
        own_zone = {(start[0] + ddx, start[1] + ddy)
                    for ddx in range(-4, 5) for ddy in range(-4, 5)}
        stop = path_tiles - own_zone

        dist = math.hypot(end[0] - start[0], end[1] - start[1])
        seg = _path_worm(start, end, seed, worm_seed,
                         river_tiles, stop, bridge_all,
                         max_steps=int(dist * 3) + 50)
        for px, py in seg:
            if (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))

    def _route(a: tuple[int, int], b: tuple[int, int]) -> None:
        """Route from a to b, detouring through a bridge pair if crossing water."""
        samples = _line_samples(a, b)
        center = _crossing_center(samples, seed, river_tiles, bridge_all)
        if center is not None and len(bridge_endpoints) >= 2:
            cx, cy = center
            # Sort all endpoints by distance to the crossing centre
            sorted_eps = sorted(bridge_endpoints,
                                key=lambda ep: math.hypot(ep[0] - cx, ep[1] - cy))
            # Take the closest endpoint on each side of the crossing:
            # ep_a is closest to A, ep_b is closest to B among the two nearest
            ep1, ep2 = sorted_eps[0], sorted_eps[1]
            # Assign: ep_a faces A, ep_b faces B
            if (math.hypot(ep1[0]-a[0], ep1[1]-a[1]) <=
                    math.hypot(ep2[0]-a[0], ep2[1]-a[1])):
                ep_a, ep_b = ep1, ep2
            else:
                ep_a, ep_b = ep2, ep1

            direct_dist = math.hypot(b[0] - a[0], b[1] - a[1])
            detour_dist = (math.hypot(ep_a[0]-a[0], ep_a[1]-a[1]) +
                           math.hypot(ep_b[0]-ep_a[0], ep_b[1]-ep_a[1]) +
                           math.hypot(b[0]-ep_b[0], b[1]-ep_b[1]))
            if detour_dist < direct_dist * 3.0:
                _add_segment(a, ep_a)
                _add_segment(ep_a, ep_b)
                _add_segment(ep_b, b)
                return
        _add_segment(a, b)

    # Step 1: MST of villages
    mst_edges = _build_mst(village_positions)
    for a, b in mst_edges:
        _route(a, b)

    # Step 2: Connect paired bridge endpoints across the same crossing
    # Group endpoints by proximity (within 12 tiles = same bridge span)
    paired: set[int] = set()
    for i, ep_i in enumerate(bridge_endpoints):
        if i in paired:
            continue
        for j, ep_j in enumerate(bridge_endpoints):
            if j <= i or j in paired:
                continue
            if math.hypot(ep_j[0]-ep_i[0], ep_j[1]-ep_i[1]) <= 12:
                _add_segment(ep_i, ep_j)
                paired.add(i)
                paired.add(j)
                break

    # Step 3: Connect any bridge endpoint still isolated from the path network
    for bx, by in bridge_endpoints:
        nearby = any(
            abs(bx - px) + abs(by - py) <= 4
            for px, py in path_tiles
        )
        if nearby:
            continue
        candidates = sorted(
            village_positions + list(bridge_endpoints),
            key=lambda t: math.hypot(t[0] - bx, t[1] - by)
        )
        for target in candidates[:2]:
            if target != (bx, by):
                _add_segment((bx, by), target)

    return overrides


async def place_structures(seed: int, db) -> None:
    from dwarf_explorer.world.caves import create_cave_system

    # 1. Base structures
    overrides, cave_groups = await asyncio.to_thread(_generate_structures_sync, seed)
    if overrides:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
            overrides,
        )

    # 2. Pre-generate cave systems
    for group in cave_groups:
        await create_cave_system(seed, group, db)

    # 3. Village positions
    village_positions = [(x, y) for x, y, t in overrides if t == 'village']

    # 4. Bridge positions
    bridge_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'bridge'"
    )
    bridge_all_list = [(r["world_x"], r["world_y"]) for r in bridge_rows]
    bridge_all_set = set(bridge_all_list)

    # 5. Existing path tiles
    path_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'path'"
    )
    existing_paths = {(r["world_x"], r["world_y"]) for r in path_rows}

    # 6. River tiles to avoid
    river_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'river'"
    )
    river_tiles = {(r["world_x"], r["world_y"]) for r in river_rows}

    # Filter bridges to only bank-edge tiles (adjacent to dry land)
    bridge_endpoints = [
        (bx, by) for bx, by in bridge_all_list
        if _is_bridge_endpoint(bx, by, seed, river_tiles | bridge_all_set)
    ]

    # 7. Generate inter-village/bridge paths
    if village_positions or bridge_endpoints:
        path_overrides = await asyncio.to_thread(
            _generate_village_paths_sync,
            seed, village_positions, bridge_endpoints, bridge_all_set, existing_paths, river_tiles,
        )
        if path_overrides:
            await db.executemany(
                "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
                path_overrides,
            )
