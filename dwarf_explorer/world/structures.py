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


# ── Perlin worm (meander) ─────────────────────────────────────────────────────

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
    passable_tiles: set[tuple[int, int]],
    max_steps: int = 400,
) -> list[tuple[int, int]]:
    """Perlin-worm road from start to target, avoiding water.

    Shorter budget than before because it's used between sparse waypoints
    that are already guaranteed to be on dry land. Bridge tiles in
    passable_tiles bypass the water-biome check.
    """
    x, y = float(start[0]), float(start[1])
    tx, ty = float(target[0]), float(target[1])
    dx, dy = _norm2(tx - x, ty - y)
    freq = 0.045
    path: list[tuple[int, int]] = []

    def _ok(nx: int, ny: int) -> bool:
        if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
            return False
        if (nx, ny) in avoid_tiles:
            return False
        if get_biome(nx, ny, seed) in _WATER_BIOMES and (nx, ny) not in passable_tiles:
            return False
        return True

    for _ in range(max_steps):
        ix, iy = int(round(x)), int(round(y))
        if not path or (ix, iy) != path[-1]:
            if not _ok(ix, iy):
                break
            path.append((ix, iy))

        if (ix, iy) == (int(round(tx)), int(round(ty))):
            break

        # Noise rotation + pull toward target
        n = fbm(x * freq, y * freq, worm_seed, octaves=3)
        rot = math.radians((n - 0.5) * 120.0)   # ±60° wiggle
        ndx, ndy = _norm2(*_rotate2(dx, dy, rot))
        tdx, tdy = _norm2(tx - x, ty - y)
        dx, dy = _norm2(ndx * 0.4 + tdx * 0.6, ndy * 0.4 + tdy * 0.6)

        # If next step is blocked, try rotated fallbacks
        nx_int = int(round(x + dx))
        ny_int = int(round(y + dy))
        if not _ok(nx_int, ny_int):
            for angle_deg in (45, -45, 90, -90, 135, -135, 180):
                rdx, rdy = _norm2(*_rotate2(tdx, tdy, math.radians(angle_deg)))
                if _ok(int(round(x + rdx)), int(round(y + rdy))):
                    dx, dy = rdx, rdy
                    break
            else:
                break

        x = max(0.0, min(WORLD_SIZE - 1.0, x + dx))
        y = max(0.0, min(WORLD_SIZE - 1.0, y + dy))

    return path


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


def _astar_sparse_waypoints(
    start: tuple[int, int],
    end: tuple[int, int],
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
    step: int = 14,
) -> list[tuple[int, int]]:
    """Run A* then subsample to sparse waypoints every `step` tiles.

    Returns a short list of dry-land waypoints. The Perlin worm is then
    used to meander organically between each consecutive pair.
    """
    full = _astar(start, end, seed, river_tiles, bridge_all)
    if len(full) <= step * 2:
        return full  # short path — just return as-is
    pts = [full[0]]
    for i in range(step, len(full) - 1, step):
        pts.append(full[i])
    pts.append(full[-1])
    return pts


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


def _line_has_water(
    a: tuple[int, int],
    b: tuple[int, int],
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> bool:
    """True if the straight line from a to b crosses any water tile (bridge tiles exempt)."""
    for x, y in _line_samples(a, b):
        if (x, y) not in bridge_all and _is_water(x, y, seed, river_tiles):
            return True
    return False


def _away_from_water_dir(
    x: int, y: int,
    seed: int,
    river_tiles: set[tuple[int, int]],
    scan_radius: int = 20,
) -> tuple[float, float]:
    """Unit vector pointing away from the nearest water tile."""
    for r in range(1, scan_radius + 1):
        for ddx in range(-r, r + 1):
            for ddy in ((-r, r) if abs(ddx) < r else range(-r, r + 1)):
                nx, ny = x + ddx, y + ddy
                if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
                    if _is_water(nx, ny, seed, river_tiles):
                        # Direction toward water → negate for away
                        return _norm2(-float(ddx), -float(ddy))
    return (1.0, 0.0)  # no water nearby


def _find_escape_point(
    start: tuple[int, int],
    seed: int,
    river_tiles: set[tuple[int, int]],
    escape_dist: int = 25,
) -> tuple[int, int] | None:
    """Walk away from nearest water ~escape_dist tiles and return the endpoint."""
    esc_dx, esc_dy = _away_from_water_dir(start[0], start[1], seed, river_tiles)
    x, y = float(start[0]), float(start[1])

    for _ in range(escape_dist * 4):
        nx = int(round(x + esc_dx))
        ny = int(round(y + esc_dy))
        nx = max(0, min(WORLD_SIZE - 1, nx))
        ny = max(0, min(WORLD_SIZE - 1, ny))

        if _is_water(nx, ny, seed, river_tiles):
            # Deflect 45° and try again
            esc_dx, esc_dy = _norm2(*_rotate2(esc_dx, esc_dy, math.radians(45)))
            continue

        x, y = float(nx), float(ny)
        if math.hypot(x - start[0], y - start[1]) >= escape_dist:
            return (int(x), int(y))

    pt = (int(round(x)), int(round(y)))
    return pt if pt != start else None


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
    Phase 1 — For each node, look at every other node sorted by distance.
      If the straight line to that node contains NO water tile (bridge tiles OK),
      deploy a Perlin worm to connect. Stop after 2 successful connections.

    Phase 2 — Any node still unconnected escapes away from the nearest water
      ~25 tiles, creates a virtual escape node there, and that node repeats
      Phase 1. Repeat up to 3 times until connected or exhausted.
    """
    path_tiles: set[tuple[int, int]] = set(existing_path_tiles)
    overrides: list[tuple[int, int, str]] = []
    connected_pairs: set[frozenset] = set()
    node_conn_count: dict[tuple[int, int], int] = {}

    def _worm_connect(a: tuple[int, int], b: tuple[int, int]) -> bool:
        """Worm from a to b. Returns True if worm reached within 10 tiles of b."""
        pair = frozenset([a, b])
        if pair in connected_pairs:
            return True
        connected_pairs.add(pair)

        worm_seed = (seed ^ (a[0] * 31 + a[1] * 97 + b[0] * 7 + b[1] * 13)) & 0xFFFFFFFF
        dist = math.hypot(b[0] - a[0], b[1] - a[1])
        seg = _path_worm(a, b, seed, worm_seed, river_tiles, bridge_all,
                         max_steps=int(dist * 5) + 150)

        if not seg:
            return False
        end_dist = math.hypot(seg[-1][0] - b[0], seg[-1][1] - b[1])
        if end_dist > 10:
            # Worm failed to reach — discard tiles to avoid path overfill
            return False

        for px, py in seg:
            if (px, py) not in path_tiles and not _is_water(px, py, seed, river_tiles):
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))
        node_conn_count[a] = node_conn_count.get(a, 0) + 1
        node_conn_count[b] = node_conn_count.get(b, 0) + 1
        return True

    def _try_connect_from(node: tuple[int, int], candidates: list[tuple[int, int]]) -> int:
        """Try to connect node to up to 2 candidates with clear lines. Returns count made."""
        made = 0
        for other in candidates:
            if other == node:
                continue
            if _line_has_water(node, other, seed, river_tiles, bridge_all):
                continue
            if _worm_connect(node, other):
                made += 1
                if made >= 2:
                    break
        return made

    all_nodes = village_positions + bridge_endpoints
    if len(all_nodes) < 2:
        return overrides

    # Phase 1: connect nodes that have a clear (no-water) line of sight
    for node in all_nodes:
        candidates = sorted(
            [n for n in all_nodes if n != node],
            key=lambda n: math.hypot(n[0] - node[0], n[1] - node[1]),
        )
        _try_connect_from(node, candidates)

    # Phase 2: isolated nodes escape away from water and retry
    for node in all_nodes:
        if node_conn_count.get(node, 0) > 0:
            continue

        current = node
        for _attempt in range(3):
            esc = _find_escape_point(current, seed, river_tiles, escape_dist=25)
            if esc is None:
                break

            # Worm from the original node to the escape point
            _worm_connect(node, esc)

            # From escape point, look for any node with a clear line
            all_candidates = sorted(
                all_nodes,
                key=lambda n: math.hypot(n[0] - esc[0], n[1] - esc[1]),
            )
            made = _try_connect_from(esc, all_candidates)
            if made > 0:
                break

            current = esc  # push further away next iteration

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
