from __future__ import annotations

import asyncio
import heapq
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


# ── A* pathfinder + Perlin meander ───────────────────────────────────────────

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
) -> list[tuple[int, int]]:
    """8-directional A* from start to goal, treating water as near-impassable.

    Returns a tile path guaranteed to not cross water (unless no dry route
    exists at all, in which case falls back to a straight line).
    """
    if start == goal:
        return [start]

    open_heap: list[tuple[float, float, int, int]] = []
    heapq.heappush(open_heap, (0.0, 0.0, start[0], start[1]))
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    g_score: dict[tuple[int, int], float] = {start: 0.0}
    max_iters = WORLD_SIZE * WORLD_SIZE

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
            continue  # stale heap entry

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

    # A* exhausted without reaching goal — fall back to straight line
    return _line_samples(start, goal)


def _smooth_path(
    path: list[tuple[int, int]],
    seed: int,
    river_tiles: set[tuple[int, int]],
    amplitude: float = 2.5,
    freq: float = 0.07,
) -> list[tuple[int, int]]:
    """Apply perpendicular Perlin noise meander to an A* backbone path.

    Each tile is displaced perpendicularly to the local path direction.
    Displaced tiles that land on water fall back to the original tile.
    """
    if len(path) < 3:
        return list(path)

    result: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    n = len(path)

    for i, (px, py) in enumerate(path):
        # Local path direction
        if i == 0:
            ldx, ldy = float(path[1][0] - px), float(path[1][1] - py)
        elif i == n - 1:
            ldx, ldy = float(px - path[-2][0]), float(py - path[-2][1])
        else:
            ldx, ldy = float(path[i+1][0] - path[i-1][0]), float(path[i+1][1] - path[i-1][1])

        m = math.hypot(ldx, ldy)
        if m < 1e-9:
            perp_x, perp_y = 0.0, 0.0
        else:
            perp_x, perp_y = -ldy / m, ldx / m  # 90° CCW rotation

        # Parabolic taper: 0 at endpoints, 1 at midpoint
        t = i / (n - 1)
        taper = 4.0 * t * (1.0 - t)

        noise_val = fbm(px * freq, py * freq, seed ^ 0xCAFE, octaves=2)
        offset = (noise_val - 0.5) * 2.0 * amplitude * taper

        mx = int(round(px + offset * perp_x))
        my = int(round(py + offset * perp_y))

        # Fall back to unperturbed tile if displaced position is water or OOB
        if not (0 <= mx < WORLD_SIZE and 0 <= my < WORLD_SIZE) or \
                _is_water(mx, my, seed, river_tiles):
            mx, my = px, py

        if (mx, my) not in seen:
            seen.add((mx, my))
            result.append((mx, my))

    return result


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
    2. For each MST edge, run A* (water = near-impassable) to find a dry route.
    3. Apply Perlin perpendicular meander to smooth the A* backbone.
    4. Connect isolated bridge endpoints to nearest path node.
    """
    path_tiles: set[tuple[int, int]] = set(existing_path_tiles)
    overrides: list[tuple[int, int, str]] = []
    connected_pairs: set[frozenset] = set()

    def _add_path(start: tuple[int, int], end: tuple[int, int]) -> None:
        pair = frozenset([start, end])
        if pair in connected_pairs:
            return
        connected_pairs.add(pair)

        backbone = _astar(start, end, seed, river_tiles, bridge_all)
        seg = _smooth_path(backbone, seed, river_tiles)
        for px, py in seg:
            if (px, py) not in path_tiles and \
                    not _is_water(px, py, seed, river_tiles):
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))

    # K-nearest-neighbor graph over ALL nodes (villages + bridge endpoints).
    # Each node connects to its 2 nearest other nodes via A*.
    # This guarantees every node has at least 2 connections and the network
    # is densely connected without relying on MST + separate bridge steps.
    all_nodes = village_positions + bridge_endpoints
    if len(all_nodes) < 2:
        return overrides

    for node in all_nodes:
        nearest = sorted(
            [n for n in all_nodes if n != node],
            key=lambda n: math.hypot(n[0] - node[0], n[1] - node[1]),
        )
        for target in nearest[:2]:
            _add_path(node, target)

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
