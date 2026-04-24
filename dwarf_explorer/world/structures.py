from __future__ import annotations

import asyncio
import heapq
import math
import random

from dwarf_explorer.world.terrain import get_biome
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


# ── A* pathfinder ─────────────────────────────────────────────────────────────

def _tile_move_cost(
    x: int, y: int,
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> float:
    """Base movement cost for A* — water is near-impassable, mountains expensive."""
    if (x, y) in bridge_all:
        return 1.0
    if _is_water(x, y, seed, river_tiles):
        return 9999.0
    biome = get_biome(x, y, seed)
    if biome in ("mountain", "snow"):
        return 30.0
    if biome == "hills":
        return 5.0
    return 1.0


def _astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> list[tuple[int, int]] | None:
    """8-directional A* from start to goal, treating water as near-impassable.

    Returns the tile path, or None if no path was found.
    """
    if start == goal:
        return [start]

    open_heap: list[tuple[float, float, int, int]] = []
    heapq.heappush(open_heap, (0.0, 0.0, start[0], start[1]))
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    g_score: dict[tuple[int, int], float] = {start: 0.0}
    max_iters = 60_000

    for _ in range(max_iters):
        if not open_heap:
            break
        _, g, cx, cy = heapq.heappop(open_heap)

        if (cx, cy) == goal:
            path: list[tuple[int, int]] = []
            node: tuple[int, int] | None = goal
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        if g > g_score.get((cx, cy), float("inf")):
            continue

        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = cx + ddx, cy + ddy
                if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
                    continue
                step_cost = _tile_move_cost(nx, ny, seed, river_tiles, bridge_all)
                move_dist = math.sqrt(2.0) if (ddx != 0 and ddy != 0) else 1.0
                new_g = g + step_cost * move_dist
                if new_g < g_score.get((nx, ny), float("inf")):
                    g_score[(nx, ny)] = new_g
                    came_from[(nx, ny)] = (cx, cy)
                    h = math.hypot(goal[0] - nx, goal[1] - ny)
                    heapq.heappush(open_heap, (new_g + h, new_g, nx, ny))

    return None  # no path found


def _snap_to_dry(
    x: int, y: int,
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
    radius: int = 8,
) -> tuple[int, int]:
    """Return nearest non-water tile to (x, y), or (x, y) itself if already dry."""
    if not _is_water(x, y, seed, river_tiles) or (x, y) in bridge_all:
        return (x, y)
    for r in range(1, radius + 1):
        for ddx in range(-r, r + 1):
            for ddy in ((-r, r) if abs(ddx) < r else range(-r, r + 1)):
                nx, ny = x + ddx, y + ddy
                if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
                    if not _is_water(nx, ny, seed, river_tiles):
                        return (nx, ny)
    return (x, y)


def _perpendicular_waypoint(
    a: tuple[int, int],
    b: tuple[int, int],
    rng: random.Random,
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
    offset_range: tuple[int, int] = (8, 18),
) -> tuple[int, int]:
    """Return a dry waypoint offset perpendicularly from the midpoint of a→b."""
    mx = (a[0] + b[0]) // 2
    my = (a[1] + b[1]) // 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    # Perpendicular: rotate 90°
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length
    offset = rng.randint(*offset_range) * rng.choice((-1, 1))
    wx = int(round(mx + px * offset))
    wy = int(round(my + py * offset))
    wx = max(2, min(WORLD_SIZE - 3, wx))
    wy = max(2, min(WORLD_SIZE - 3, wy))
    return _snap_to_dry(wx, wy, seed, river_tiles, bridge_all)


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

def _is_water(x: int, y: int, seed: int, river_tiles: set[tuple[int, int]]) -> bool:
    """True if tile is water — either a river override OR a water biome tile."""
    return (x, y) in river_tiles or get_biome(x, y, seed) in _WATER_BIOMES


def _widen_path(
    centerline: list[tuple[int, int]],
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Return extra tiles one step to the right of the path centerline direction."""
    extra: set[tuple[int, int]] = set()
    n = len(centerline)
    if n < 2:
        return extra
    for i in range(n):
        if i == 0:
            dx = centerline[1][0] - centerline[0][0]
            dy = centerline[1][1] - centerline[0][1]
        elif i == n - 1:
            dx = centerline[-1][0] - centerline[-2][0]
            dy = centerline[-1][1] - centerline[-2][1]
        else:
            dx = centerline[i + 1][0] - centerline[i - 1][0]
            dy = centerline[i + 1][1] - centerline[i - 1][1]
        if dx == 0 and dy == 0:
            continue
        # Clockwise perpendicular: (dx, dy) → sign(dy, -dx)
        pdx = (1 if dy > 0 else -1) if dy != 0 else 0
        pdy = (-1 if dx > 0 else 1) if dx != 0 else 0
        px, py = centerline[i]
        nx, ny = px + pdx, py + pdy
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            if (nx, ny) not in bridge_all and not _is_water(nx, ny, seed, river_tiles):
                extra.add((nx, ny))
    return extra


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
    1. Build an MST (Prim's) over all nodes — guarantees full connectivity,
       each pair connected at most once, no redundant parallel routes.
    2. Add a small number of bonus short-range cross-connections for loops.
    3. Each edge is rendered via A* with 1–3 large perpendicular waypoints
       for natural meander.
    4. Each path is widened by one tile (2-tile-wide roads).
    """
    rng = random.Random(seed + _PATH_SEED_OFFSET)
    path_tiles: set[tuple[int, int]] = set(existing_path_tiles)
    overrides: list[tuple[int, int, str]] = []

    all_nodes = village_positions + bridge_endpoints
    if len(all_nodes) < 2:
        return overrides

    # ── 1. MST (Prim's) — guaranteed full connectivity ────────────────────────
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    in_tree: set[tuple[int, int]] = {all_nodes[0]}
    remaining: set[tuple[int, int]] = set(all_nodes[1:])
    while remaining:
        best_d, best_a, best_b = float("inf"), None, None
        for a in in_tree:
            for b in remaining:
                d = math.hypot(b[0] - a[0], b[1] - a[1])
                if d < best_d:
                    best_d, best_a, best_b = d, a, b
        edges.append((best_a, best_b))  # type: ignore[arg-type]
        in_tree.add(best_b)             # type: ignore[arg-type]
        remaining.discard(best_b)       # type: ignore[arg-type]

    # ── 2. Bonus cross-connections (nearby non-MST pairs, creates loops) ──────
    used_pairs: set[frozenset] = {frozenset(e) for e in edges}
    bonus_budget = max(2, len(all_nodes) // 3)
    candidates = sorted(
        [
            (math.hypot(b[0] - a[0], b[1] - a[1]), a, b)
            for i, a in enumerate(all_nodes)
            for b in all_nodes[i + 1:]
            if frozenset([a, b]) not in used_pairs
        ],
        key=lambda x: x[0],
    )
    bonus_added = 0
    for dist_ab, a, b in candidates:
        if bonus_added >= bonus_budget:
            break
        if dist_ab > 65:
            break
        if rng.random() < 0.55:
            edges.append((a, b))
            used_pairs.add(frozenset([a, b]))
            bonus_added += 1

    # ── 3. Render each edge with meandering A* + path widening ────────────────
    def connect(a: tuple[int, int], b: tuple[int, int]) -> None:
        dist = math.hypot(b[0] - a[0], b[1] - a[1])

        # Waypoints: larger offsets = more meander
        waypoints: list[tuple[int, int]] = []
        if dist > 15:
            lo = max(10, int(dist * 0.28))
            hi = max(lo + 6, int(dist * 0.50))
            wp1 = _perpendicular_waypoint(a, b, rng, seed, river_tiles, bridge_all,
                                          offset_range=(lo, hi))
            waypoints.append(wp1)
        if dist > 45:
            lo2 = max(8, int(dist * 0.18))
            hi2 = max(lo2 + 4, int(dist * 0.35))
            wp2 = _perpendicular_waypoint(waypoints[-1], b, rng, seed, river_tiles, bridge_all,
                                          offset_range=(lo2, hi2))
            waypoints.append(wp2)
        if dist > 90:
            lo3 = max(6, int(dist * 0.10))
            hi3 = max(lo3 + 4, int(dist * 0.22))
            wp3 = _perpendicular_waypoint(waypoints[-1], b, rng, seed, river_tiles, bridge_all,
                                          offset_range=(lo3, hi3))
            waypoints.append(wp3)

        stops = [a] + waypoints + [b]
        centerline: list[tuple[int, int]] = []
        for i in range(len(stops) - 1):
            seg = _astar(stops[i], stops[i + 1], seed, river_tiles, bridge_all)
            if seg is None:
                return  # skip this edge silently
            centerline.extend(seg if not centerline else seg[1:])

        # Write centerline + widened tiles
        extra = _widen_path(centerline, seed, river_tiles, bridge_all)
        for px, py in centerline:
            if not _is_water(px, py, seed, river_tiles) and (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))
        for px, py in extra:
            if (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))

    for a, b in edges:
        connect(a, b)

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
