from __future__ import annotations

import asyncio
import heapq
import math
import random

from dwarf_explorer.world.terrain import get_biome, get_coast_boundary
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

def _meander_noise(x: int, y: int, seed: int) -> float:
    """Fast spatially-coherent noise for path meander (no fbm overhead).

    Bilinearly interpolates hashed values sampled every 8 tiles, giving
    smooth 8-tile-scale cost variation without any expensive floating-point
    noise functions.  Returns a value in [0, 1].
    """
    def _h(n: int) -> float:
        n = (n ^ (n >> 16)) * 0x45D9F3B
        n = (n ^ (n >> 16)) * 0x45D9F3B
        n ^= (n >> 16)
        return (n & 0xFFFFF) / 0xFFFFF

    x8, y8 = x >> 3, y >> 3
    fx = (x & 7) / 8.0
    fy = (y & 7) / 8.0
    s = seed & 0xFFFFFFFF
    h00 = _h(x8 * 1664525   + y8 * 1013904223 + s)
    h10 = _h((x8+1)*1664525  + y8 * 1013904223 + s)
    h01 = _h(x8 * 1664525   + (y8+1)*1013904223 + s)
    h11 = _h((x8+1)*1664525  + (y8+1)*1013904223 + s)
    return (h00*(1-fx)*(1-fy) + h10*fx*(1-fy) +
            h01*(1-fx)*fy    + h11*fx*fy)


def _tile_move_cost(
    x: int, y: int,
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> float:
    """Base movement cost for A* — water near-impassable, mountains expensive.

    Normal terrain gets a fast bilinear-hash perturbation (0.5–2.5) so A*
    naturally meanders through cost valleys without needing waypoints.
    """
    if (x, y) in bridge_all:
        return 1.0
    if _is_water(x, y, seed, river_tiles):
        return 9999.0
    biome = get_biome(x, y, seed)
    if biome in ("mountain", "snow"):
        return 30.0
    if biome == "hills":
        return 3.0
    return 0.5 + _meander_noise(x, y, seed ^ _PATH_SEED_OFFSET) * 2.0


def _turn_penalty(ldx: int, ldy: int, ndx: int, ndy: int) -> float:
    """Extra cost for direction changes.  Penalises turns sharper than ~80°."""
    if ldx == 0 and ldy == 0:
        return 0.0
    dot = (ldx * ndx + ldy * ndy) / (math.hypot(ldx, ldy) * math.hypot(ndx, ndy))
    # dot ≈ 1: straight  |  dot ≈ 0.17: 80° change  |  dot = 0: 90°  |  dot = -1: U-turn
    if dot >= 0.17:     # ≤ 80° change — free
        return 0.0
    elif dot >= -0.17:  # 80–100°
        return 12.0
    elif dot >= -0.5:   # 100–120°
        return 40.0
    else:               # > 120° — near-reversal
        return 100.0


def _precompute_costs(
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> list[list[float]]:
    """Build a WORLD_SIZE×WORLD_SIZE cost grid for A*.

    Calling get_biome once per tile upfront (instead of on every A* step)
    gives a large speedup when the same world is path-searched many times.
    Indexed as grid[y][x].
    """
    grid: list[list[float]] = []
    for y in range(WORLD_SIZE):
        row: list[float] = []
        for x in range(WORLD_SIZE):
            if (x, y) in bridge_all:
                row.append(1.0)
            elif (x, y) in river_tiles:
                row.append(9_999.0)
            else:
                biome = get_biome(x, y, seed)
                if biome in _WATER_BIOMES:
                    row.append(9_999.0)
                elif biome in ("mountain", "snow"):
                    row.append(30.0)
                elif biome == "hills":
                    row.append(3.0)
                else:
                    row.append(0.5 + _meander_noise(x, y, seed ^ _PATH_SEED_OFFSET) * 2.0)
        grid.append(row)
    return grid


def _astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    cost_grid: list[list[float]],
) -> list[tuple[int, int]] | None:
    """Simple (x,y) A* using a pre-built cost grid.

    Replacing direction-aware state (x,y,dx,dy) with plain (x,y) shrinks the
    state space by 8× and removes turn-penalty overhead. Natural path meander
    comes from the spatially-varying cost values in cost_grid.
    """
    if start == goal:
        return [start]

    INF = float("inf")
    # heap: (f, g, node)
    open_heap: list[tuple[float, float, tuple[int, int]]] = [
        (0.0, 0.0, start)
    ]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    g_score: dict[tuple[int, int], float] = {start: 0.0}

    while open_heap:
        _, g, cur = heapq.heappop(open_heap)
        if g > g_score.get(cur, INF):
            continue  # stale entry
        if cur == goal:
            path: list[tuple[int, int]] = []
            s: tuple[int, int] | None = cur
            while s is not None:
                path.append(s)
                s = came_from[s]
            path.reverse()
            return path
        cx, cy = cur
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = cx + ddx, cy + ddy
                if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
                    continue
                step = cost_grid[ny][nx]
                move_dist = 1.4142135 if (ddx and ddy) else 1.0
                new_g = g + step * move_dist
                nb = (nx, ny)
                if new_g < g_score.get(nb, INF):
                    g_score[nb] = new_g
                    came_from[nb] = cur
                    h = math.hypot(goal[0] - nx, goal[1] - ny)
                    heapq.heappush(open_heap, (new_g + h, new_g, nb))

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

    # --- Shrines: fixed count regardless of world size ---
    # Formula intentionally does NOT scale with area — too many shrines if
    # world size doubles.  12–18 is the right feel for any size world.
    shrine_count = rng.randint(12, 18)
    found = 0
    for _ in range(shrine_count * 80):
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

    # --- Ruins: fixed count similar to shrines ---
    ruins_count = rng.randint(10, 16)
    found = 0
    for _ in range(ruins_count * 100):
        if found >= ruins_count:
            break
        x = rng.randint(1, WORLD_SIZE - 2)
        y = rng.randint(1, WORLD_SIZE - 2)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) in WALKABLE_TILES:
            overrides.append((x, y, 'ruins'))
            found += 1

    # --- Harbor: 1 village adjacent to the ocean coastline ---
    _ocean_biomes = {'deep_water', 'shallow_water'}
    _bad_biomes   = {'mountain', 'snow', 'deep_water', 'shallow_water'}
    ocean_edge, coast_boundary = get_coast_boundary(seed)
    harbor_placed = False
    for _ in range(1200):
        if ocean_edge in (0, 1):  # south / north — vary x, compute y from boundary
            hx = rng.randint(8, WORLD_SIZE - 9)
            c  = coast_boundary[hx]
            offset = rng.randint(1, 4)
            hy = (c - offset) if ocean_edge == 0 else (c + offset)
        else:                     # west / east — vary y, compute x from boundary
            hy = rng.randint(8, WORLD_SIZE - 9)
            c  = coast_boundary[hy]
            offset = rng.randint(1, 4)
            hx = (c + offset) if ocean_edge == 2 else (c - offset)
        hx = max(2, min(WORLD_SIZE - 3, hx))
        hy = max(2, min(WORLD_SIZE - 3, hy))
        if get_biome(hx, hy, seed) not in _bad_biomes:
            # Confirm at least one adjacent tile is ocean
            adj_ocean = any(
                get_biome(hx + ddx, hy + ddy, seed) in _ocean_biomes
                for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0),
                                 (0, 2), (0, -2), (2, 0), (-2, 0),
                                 (0, 3), (0, -3), (3, 0), (-3, 0)]
                if 0 <= hx + ddx < WORLD_SIZE and 0 <= hy + ddy < WORLD_SIZE
            )
            if adj_ocean:
                overrides.append((hx, hy, 'harbor'))
                harbor_placed = True
                break
    if not harbor_placed:
        # Fallback: scan along the coast boundary for first walkable tile
        for col in range(WORLD_SIZE):
            if ocean_edge in (0, 1):
                hx, hy = col, coast_boundary[col] + (-1 if ocean_edge == 0 else 1)
            else:
                hy, hx = col, coast_boundary[col] + (1 if ocean_edge == 2 else -1)
            hx = max(2, min(WORLD_SIZE - 3, hx))
            hy = max(2, min(WORLD_SIZE - 3, hy))
            if get_biome(hx, hy, seed) not in _bad_biomes:
                overrides.append((hx, hy, 'harbor'))
                harbor_placed = True
                break

    cave_groups = _group_caves(cave_positions, rng)
    return overrides, cave_groups


# ── Path generation ────────────────────────────────────────────────────────────

def _is_water(x: int, y: int, seed: int, river_tiles: set[tuple[int, int]]) -> bool:
    """True if tile is water — either a river override OR a water biome tile."""
    return (x, y) in river_tiles or get_biome(x, y, seed) in _WATER_BIOMES


def _fill_diagonal_gaps(
    path: list[tuple[int, int]],
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Return corner tiles for diagonal steps to eliminate checkerboard gaps.

    Always adds both corners even if they're water — small tributary crossings
    should become path.
    """
    fillers: list[tuple[int, int]] = []
    for i in range(len(path) - 1):
        x, y = path[i]
        nx, ny = path[i + 1]
        dx, dy = nx - x, ny - y
        if dx != 0 and dy != 0:
            for fx, fy in ((x + dx, y), (x, y + dy)):
                if 0 <= fx < WORLD_SIZE and 0 <= fy < WORLD_SIZE:
                    if (fx, fy) not in bridge_all:
                        fillers.append((fx, fy))
    return fillers


def _widen_path(
    centerline: list[tuple[int, int]],
    seed: int,
    river_tiles: set[tuple[int, int]],
    bridge_all: set[tuple[int, int]],
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Return (extra_tile, beyond_tile) pairs for 2-tile-wide path widening.

    beyond_tile is one additional step in the same perpendicular direction —
    callers use it to skip widening when that tile is already a road centerline,
    which prevents two adjacent paths from merging into a 4-tile-wide strip.
    """
    result: list[tuple[tuple[int, int], tuple[int, int]]] = []
    n = len(centerline)
    if n < 2:
        return result
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
        # Clockwise perpendicular: (dx, dy) → (sign(dy), -sign(dx))
        pdx = (1 if dy > 0 else -1) if dy != 0 else 0
        pdy = (-1 if dx > 0 else 1) if dx != 0 else 0
        px, py = centerline[i]
        nx, ny = px + pdx, py + pdy
        bx, by = nx + pdx, ny + pdy  # one step further — for 4-wide guard
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            if (nx, ny) not in bridge_all and not _is_water(nx, ny, seed, river_tiles):
                result.append(((nx, ny), (bx, by)))
    return result


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

    # Pre-build cost grid once — avoids calling get_biome on every A* step
    cost_grid = _precompute_costs(seed, river_tiles, bridge_all)

    def _river_cross_weight(a: tuple[int, int], b: tuple[int, int]) -> float:
        """Euclidean distance, multiplied if the straight line samples many river tiles.

        Causes the MST to prefer paths that don't need to cross wide rivers —
        bridge endpoints on the same bank as a village will be preferred instead.
        """
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(d / 4))
        river_hits = 0
        for t in range(steps + 1):
            frac = t / steps
            x = int(round(a[0] + (b[0] - a[0]) * frac))
            y = int(round(a[1] + (b[1] - a[1]) * frac))
            if (x, y) in river_tiles:
                river_hits += 1
        if river_hits >= 3:
            d *= 8.0  # strongly discourage river-crossing MST edges
        return d

    # ── 1. MST (Prim's) — guaranteed full connectivity ────────────────────────
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    in_tree: set[tuple[int, int]] = {all_nodes[0]}
    remaining: set[tuple[int, int]] = set(all_nodes[1:])
    while remaining:
        best_d, best_a, best_b = float("inf"), None, None
        for a in in_tree:
            for b in remaining:
                d = _river_cross_weight(a, b)
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
            (_river_cross_weight(a, b), a, b)
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

    # ── 3. Compute all centerlines first (two-pass avoids 4-wide merging) ────
    # No explicit waypoints — fbm noise in _tile_move_cost produces natural meander,
    # and the turn-penalty A* keeps bends gradual.  Paths longer than 3× the
    # straight-line distance (river detours) or crossing too many river tiles are
    # rejected so isolated dead-ends don't form.
    def compute_centerline(
        a: tuple[int, int], b: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        dist = max(1.0, math.hypot(b[0] - a[0], b[1] - a[1]))
        seg = _astar(a, b, cost_grid)
        if seg is None:
            return None
        # Reject if the path is a huge river-avoidance detour
        if len(seg) > 3.5 * dist:
            return None
        # Reject if it crosses more than 2 river tiles (small tribs ok; big rivers not)
        if sum(1 for px, py in seg if (px, py) in river_tiles) > 2:
            return None
        return seg

    all_centerlines: list[list[tuple[int, int]]] = []
    for a, b in edges:
        cl = compute_centerline(a, b)
        if cl:
            all_centerlines.append(cl)

    # Build the union of all raw centerline tiles for the 4-wide guard
    all_cl_tiles: set[tuple[int, int]] = set()
    for cl in all_centerlines:
        all_cl_tiles.update(cl)

    # Pass 1 — write centerline tiles + diagonal gap fillers
    for cl in all_centerlines:
        for px, py in cl:
            if (px, py) not in bridge_all and (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))
        for px, py in _fill_diagonal_gaps(cl, seed, river_tiles, bridge_all):
            if (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))

    # Pass 2 — widen each centerline, skipping tiles whose beyond is a centerline
    for cl in all_centerlines:
        for (nx, ny), (bx, by) in _widen_path(cl, seed, river_tiles, bridge_all):
            if (bx, by) in all_cl_tiles:
                continue  # would merge two adjacent paths into 4-wide strip
            if (nx, ny) not in path_tiles:
                path_tiles.add((nx, ny))
                overrides.append((nx, ny, "path"))

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
    # Deduplicate: 2-wide bridges produce ~2 endpoints per bank; collapse to 1 per cluster
    _deduped_eps: list[tuple[int, int]] = []
    for ep in bridge_endpoints:
        if not any(abs(ep[0] - k[0]) + abs(ep[1] - k[1]) < 4 for k in _deduped_eps):
            _deduped_eps.append(ep)
    bridge_endpoints = _deduped_eps

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
