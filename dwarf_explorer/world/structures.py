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

def _reconstruct(came_from: dict, end: tuple[int, int]) -> list[tuple[int, int]]:
    path: list[tuple[int, int]] = []
    pos = end
    while pos in came_from:
        path.append(pos)
        pos = came_from[pos]
    path.reverse()
    return path


def _astar_path(
    start: tuple[int, int],
    end: tuple[int, int],
    seed: int,
    avoid_tiles: set[tuple[int, int]],
    stop_tiles: set[tuple[int, int]],
    max_nodes: int = 80_000,
) -> list[tuple[int, int]]:
    """A* from start to end, stopping early at any stop_tile.

    Avoids tiles in avoid_tiles (rivers) and water biomes.
    Returns [] if the target is unreachable (e.g. blocked by water with no
    bridge crossing available).  This replaces the old Perlin worm so paths
    are guaranteed to be water-free and never loop.
    """
    sx, sy = start
    ex, ey = end

    open_heap: list[tuple[int, int, int]] = []
    heapq.heappush(open_heap, (0, sx, sy))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {(sx, sy): 0}
    visited: set[tuple[int, int]] = set()

    while open_heap:
        _, cx, cy = heapq.heappop(open_heap)

        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))

        # Reached existing path network (outside start's own zone)
        if (cx, cy) in stop_tiles:
            return _reconstruct(came_from, (cx, cy))

        # Reached the explicit target
        if (cx, cy) == (ex, ey):
            return _reconstruct(came_from, (cx, cy))

        if len(visited) > max_nodes:
            break   # give up — target unreachable within budget

        current_g = g_score.get((cx, cy), 0)

        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
                continue
            if (nx, ny) in avoid_tiles:
                continue
            if get_biome(nx, ny, seed) in _WATER_BIOMES:
                continue
            if (nx, ny) in visited:
                continue

            ng = current_g + 1
            if ng < g_score.get((nx, ny), 10 ** 9):
                g_score[(nx, ny)] = ng
                h = abs(nx - ex) + abs(ny - ey)
                heapq.heappush(open_heap, (ng + h, nx, ny))
                came_from[(nx, ny)] = (cx, cy)

    return []   # unreachable


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

def _generate_village_paths_sync(
    seed: int,
    village_positions: list[tuple[int, int]],
    bridge_positions: list[tuple[int, int]],
    existing_path_tiles: set[tuple[int, int]],
    river_tiles: set[tuple[int, int]],
) -> list[tuple[int, int, str]]:
    """Connect villages and bridges into a road network using A* pathfinding.

    A* guarantees water-free paths and clean termination.
    Connections are deduplicated so (A→B) prevents a redundant (B→A) run.
    """
    path_tiles: set[tuple[int, int]] = set(existing_path_tiles)
    overrides:  list[tuple[int, int, str]] = []
    avoid_tiles: set[tuple[int, int]] = set(river_tiles)

    all_targets = list(village_positions) + list(bridge_positions)

    # Track connected pairs to avoid duplicate roads
    connected_pairs: set[frozenset] = set()

    def _connect(start: tuple[int, int], end: tuple[int, int]) -> None:
        pair = frozenset([start, end])
        if pair in connected_pairs:
            return
        connected_pairs.add(pair)

        # Exclude start's own 7×7 zone so path can't immediately stop at own ring
        own_zone = {(start[0] + dx, start[1] + dy)
                    for dx in range(-3, 4) for dy in range(-3, 4)}
        stop = path_tiles - own_zone

        path = _astar_path(start, end, seed, avoid_tiles, stop)
        if not path:
            return   # unreachable — skip silently

        for px, py in path:
            if (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, 'path'))

    # --- Villages: connect to 1-2 nearest targets ---
    for vx, vy in village_positions:
        candidates = sorted(
            (math.hypot(tx - vx, ty - vy), (tx, ty))
            for (tx, ty) in all_targets
            if (tx, ty) != (vx, vy)
        )
        if not candidates:
            continue
        targets = [candidates[0][1]]
        if len(candidates) > 1 and candidates[1][0] < candidates[0][0] * 2.0:
            targets.append(candidates[1][1])

        for target in targets:
            _connect((vx, vy), target)

    # --- Bridges: connect each bridge to its nearest target ---
    for bx, by in bridge_positions:
        candidates = sorted(
            (math.hypot(tx - bx, ty - by), (tx, ty))
            for (tx, ty) in all_targets
            if (tx, ty) != (bx, by)
        )
        if not candidates:
            continue
        dist, nearest = candidates[0]
        if dist > 120:
            continue

        # Skip if bridge is already adjacent to an existing path tile
        if any((bx + dx, by + dy) in path_tiles
               for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))):
            continue

        _connect((bx, by), nearest)

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
    bridge_positions = [(r["world_x"], r["world_y"]) for r in bridge_rows]

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
