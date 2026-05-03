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
    """Two-octave spatially-coherent noise for path meander.

    Coarse layer (8-tile grid, 60%) gives large-scale bends.
    Fine layer (3-tile grid, 40%) adds small wiggles within each bend.
    Returns a value in [0, 1].
    """
    def _h(n: int) -> float:
        n = (n ^ (n >> 16)) * 0x45D9F3B
        n = (n ^ (n >> 16)) * 0x45D9F3B
        n ^= (n >> 16)
        return (n & 0xFFFFF) / 0xFFFFF

    # Coarse layer — 8-tile grid
    x8, y8 = x >> 3, y >> 3
    fx8 = (x & 7) / 8.0
    fy8 = (y & 7) / 8.0
    s = seed & 0xFFFFFFFF
    coarse = (
        _h(x8 * 1664525    + y8 * 1013904223 + s) * (1 - fx8) * (1 - fy8)
      + _h((x8+1)*1664525  + y8 * 1013904223 + s) *      fx8  * (1 - fy8)
      + _h(x8 * 1664525    + (y8+1)*1013904223+s) * (1 - fx8) *      fy8
      + _h((x8+1)*1664525  + (y8+1)*1013904223+s) *      fx8  *      fy8
    )

    # Fine layer — 3-tile grid (independent seed offset)
    s2 = (seed ^ 0xBEEF1234) & 0xFFFFFFFF
    x3, y3 = x // 3, y // 3
    fx3 = (x % 3) / 3.0
    fy3 = (y % 3) / 3.0
    fine = (
        _h(x3 * 2246822519   + y3 * 3266489917 + s2) * (1 - fx3) * (1 - fy3)
      + _h((x3+1)*2246822519 + y3 * 3266489917 + s2) *      fx3  * (1 - fy3)
      + _h(x3 * 2246822519   + (y3+1)*3266489917+s2) * (1 - fx3) *      fy3
      + _h((x3+1)*2246822519 + (y3+1)*3266489917+s2) *      fx3  *      fy3
    )

    return coarse * 0.6 + fine * 0.4


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
    if biome == "sand":
        return 20.0   # paths avoid beach (still passable but very costly)
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
) -> tuple[list[list[float]], set[tuple[int, int]]]:
    """Build a WORLD_SIZE×WORLD_SIZE cost grid for A* plus the narrow_river set.

    Rivers are now *crossable* at moderate cost so paths can ford/bridge them:
      - narrow_river (hw=0 sub-tributaries, 0 cardinal river neighbours): 6.0
      - wide river (has cardinal river neighbours): 25.0
    Ocean / shallow_water remain impassable (9999).

    narrow_river tiles are returned so the caller can upgrade DB river→ford/bridge.
    Indexed as grid[y][x].
    """
    # Detect narrow (isolated) river tiles — no cardinal river neighbours
    narrow_river: set[tuple[int, int]] = set()
    for rx, ry in river_tiles:
        if sum(
            1 for ddx, ddy in ((0, 1), (0, -1), (1, 0), (-1, 0))
            if (rx + ddx, ry + ddy) in river_tiles
        ) == 0:
            narrow_river.add((rx, ry))

    grid: list[list[float]] = []
    for y in range(WORLD_SIZE):
        row: list[float] = []
        for x in range(WORLD_SIZE):
            if (x, y) in narrow_river:
                row.append(6.0)    # fordable sub-tributary
            elif (x, y) in river_tiles:
                row.append(80.0)   # crossable but expensive — skimming the bank is never worth it
            else:
                biome = get_biome(x, y, seed)
                if biome in _WATER_BIOMES:
                    row.append(9_999.0)
                elif biome == "sand":
                    row.append(9_998.0)   # paths avoid beach/sand entirely
                elif biome in ("mountain", "snow"):
                    row.append(30.0)
                elif biome == "hills":
                    row.append(3.0)
                else:
                    row.append(0.5 + _meander_noise(x, y, seed ^ _PATH_SEED_OFFSET) * 2.0)
        grid.append(row)
    return grid, narrow_river


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

    # --- Villages (7-10): plains/grass, single tile, minimum 40 tiles apart ---
    village_count = rng.randint(7, 10)
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

    # --- Harbors: 2-3 villages adjacent to the ocean coastline, spaced apart ---
    _ocean_biomes    = {'deep_water', 'shallow_water'}
    _bad_biomes      = {'mountain', 'snow', 'deep_water', 'shallow_water'}
    ocean_edge, coast_boundary = get_coast_boundary(seed)
    _HARBOR_TARGET   = rng.randint(3, 5)
    _HARBOR_MIN_SEP  = 60   # 5 harbors × 60 = 300 tiles — fits comfortably on 448-tile coast
    harbor_positions: list[tuple[int, int]] = []

    def _coast_index(hx: int, hy: int) -> int:
        """Return the coast-parallel index (x for N/S edges, y for E/W edges)."""
        return hx if ocean_edge in (0, 1) else hy

    for _ in range(2400):
        if len(harbor_positions) >= _HARBOR_TARGET:
            break
        if ocean_edge in (0, 1):  # south / north — vary x, compute y from boundary
            hx = rng.randint(8, WORLD_SIZE - 9)
            c  = coast_boundary[hx]
            hy = (c - 1) if ocean_edge == 0 else (c + 1)
        else:                     # west / east — vary y, compute x from boundary
            hy = rng.randint(8, WORLD_SIZE - 9)
            c  = coast_boundary[hy]
            hx = (c + 1) if ocean_edge == 2 else (c - 1)
        hx = max(2, min(WORLD_SIZE - 3, hx))
        hy = max(2, min(WORLD_SIZE - 3, hy))
        if get_biome(hx, hy, seed) in _bad_biomes:
            continue
        # Confirm at least one adjacent tile is ocean
        adj_ocean = any(
            get_biome(hx + ddx, hy + ddy, seed) in _ocean_biomes
            for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if 0 <= hx + ddx < WORLD_SIZE and 0 <= hy + ddy < WORLD_SIZE
        )
        if not adj_ocean:
            continue
        # Enforce minimum spacing along the coastline
        ci = _coast_index(hx, hy)
        if any(abs(ci - _coast_index(px, py)) < _HARBOR_MIN_SEP
               for px, py in harbor_positions):
            continue
        overrides.append((hx, hy, 'harbor'))
        harbor_positions.append((hx, hy))

    if not harbor_positions:
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
                break

    # --- Sundial (1 per world): plains/grass, far from spawn and villages ---
    sundial_placed = False
    for _ in range(1500):
        if sundial_placed:
            break
        x = rng.randint(10, WORLD_SIZE - 11)
        y = rng.randint(10, WORLD_SIZE - 11)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) not in ('plains', 'grass'):
            continue
        if any(abs(x - vx) + abs(y - vy) < 30 for vx, vy in village_centers):
            continue
        overrides.append((x, y, 'sundial'))
        sundial_placed = True

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
) -> list[tuple[int, int]]:
    """Return corner tiles for diagonal steps to eliminate checkerboard gaps.

    Skips adding a corner tile if it is a river tile AND both step tiles are
    dry land — that combination means the path is skirting the river bank,
    not crossing it, and the corner would become a spurious bridge fragment.
    """
    fillers: list[tuple[int, int]] = []
    for i in range(len(path) - 1):
        x, y = path[i]
        nx, ny = path[i + 1]
        dx, dy = nx - x, ny - y
        if dx != 0 and dy != 0:
            step_dry = (x, y) not in river_tiles and (nx, ny) not in river_tiles
            for fx, fy in ((x + dx, y), (x, y + dy)):
                if 0 <= fx < WORLD_SIZE and 0 <= fy < WORLD_SIZE:
                    # Dry-to-dry diagonal that clips a river corner → skip;
                    # genuine crossings (at least one step tile is river) keep their corners.
                    if step_dry and (fx, fy) in river_tiles:
                        continue
                    fillers.append((fx, fy))
    return fillers


def _widen_path(
    centerline: list[tuple[int, int]],
    seed: int,
    river_tiles: set[tuple[int, int]],
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Return (extra_tile, beyond_tile) pairs for 2-tile-wide path widening.

    beyond_tile is one additional step in the same perpendicular direction —
    callers use it to skip widening when that tile is already a road centerline,
    which prevents two adjacent paths from merging into a 4-tile-wide strip.
    River tiles are skipped — widening never extends into water.
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
            if not _is_water(nx, ny, seed, river_tiles):
                result.append(((nx, ny), (bx, by)))
    return result


def _generate_village_paths_sync(
    seed: int,
    nodes: list[tuple[int, int]],
    river_tiles: set[tuple[int, int]],
) -> list[tuple[int, int, str]]:
    """Connect villages and harbors into a road network.

    Bridges are NOT pre-existing — rivers are crossable at moderate cost so
    A* finds the narrowest crossing point naturally.  After this function,
    the caller upgrades path-overlapping river tiles to 'bridge' (wide rivers)
    or 'path' (narrow tributary fords) via SQL UPDATE.

    Algorithm:
    1. MST (Prim's) over all nodes — full connectivity, each pair once.
    2. Bonus short-range cross-connections for loops.
    3. A* centerlines with natural meander from fBm cost noise.
    4. Widen paths to 2 tiles wide (skipping river tiles).
    """
    if len(nodes) < 2:
        return []

    rng = random.Random(seed + _PATH_SEED_OFFSET)
    path_tiles: set[tuple[int, int]] = set()
    overrides: list[tuple[int, int, str]] = []

    # Pre-build cost grid once — rivers crossable at moderate cost
    cost_grid, narrow_river = _precompute_costs(seed, river_tiles)

    def _river_cross_weight(a: tuple[int, int], b: tuple[int, int]) -> float:
        """Euclidean distance, ×8 if the straight line crosses many river tiles.

        Keeps the MST preferring same-bank connections; only crosses rivers
        when no dry-land route exists.
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
            d *= 8.0
        return d

    # ── 1. MST (Prim's) ───────────────────────────────────────────────────────
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    in_tree: set[tuple[int, int]] = {nodes[0]}
    remaining: set[tuple[int, int]] = set(nodes[1:])
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

    # ── 2. Bonus cross-connections (creates loops) ────────────────────────────
    used_pairs: set[frozenset] = {frozenset(e) for e in edges}
    bonus_budget = max(2, len(nodes) // 4)
    candidates = sorted(
        [
            (_river_cross_weight(a, b), a, b)
            for i, a in enumerate(nodes)
            for b in nodes[i + 1:]
            if frozenset([a, b]) not in used_pairs
        ],
        key=lambda x: x[0],
    )
    bonus_added = 0
    for dist_ab, a, b in candidates:
        if bonus_added >= bonus_budget:
            break
        if dist_ab > 55:
            break
        if rng.random() < 0.45:
            edges.append((a, b))
            used_pairs.add(frozenset([a, b]))
            bonus_added += 1

    # ── 3. Centerlines via A* ─────────────────────────────────────────────────
    def compute_centerline(
        a: tuple[int, int], b: tuple[int, int]
    ) -> list[tuple[int, int]] | None:
        dist = max(1.0, math.hypot(b[0] - a[0], b[1] - a[1]))
        seg = _astar(a, b, cost_grid)
        if seg is None:
            return None
        # Reject extreme detours (river crossings are expected and don't add detour penalty)
        if len(seg) > 5.0 * dist:
            return None
        return seg

    all_centerlines: list[list[tuple[int, int]]] = []
    for a, b in edges:
        cl = compute_centerline(a, b)
        if cl:
            all_centerlines.append(cl)

    # Union of centerline tiles for the 4-wide guard
    all_cl_tiles: set[tuple[int, int]] = set()
    for cl in all_centerlines:
        all_cl_tiles.update(cl)

    # Pass 1 — centerline tiles + diagonal gap fillers
    for cl in all_centerlines:
        for px, py in cl:
            if (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))
        for px, py in _fill_diagonal_gaps(cl, seed, river_tiles):
            if (px, py) not in path_tiles:
                path_tiles.add((px, py))
                overrides.append((px, py, "path"))

    # Pass 2 — widen to 2-tile-wide roads (skips river tiles)
    for cl in all_centerlines:
        for (nx, ny), (bx, by) in _widen_path(cl, seed, river_tiles):
            if (bx, by) in all_cl_tiles:
                continue  # 4-wide guard: skip if beyond is another centerline
            if (nx, ny) not in path_tiles:
                path_tiles.add((nx, ny))
                overrides.append((nx, ny, "path"))

    return overrides


async def place_structures(seed: int, db) -> None:
    from dwarf_explorer.world.caves import create_cave_system

    # 1. Base structures (villages, shrines, caves, ruins, harbors)
    overrides, cave_groups = await asyncio.to_thread(_generate_structures_sync, seed)
    if overrides:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
            overrides,
        )

    # 2. Cave systems
    for group in cave_groups:
        await create_cave_system(seed, group, db)

    # 3. Nodes: villages + harbors
    village_positions = [(x, y) for x, y, t in overrides if t == 'village']
    harbor_positions  = [(x, y) for x, y, t in overrides if t == 'harbor']
    nodes = village_positions + harbor_positions

    # 4. River tiles (bridges don't exist yet — they emerge from path crossings)
    river_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'river'"
    )
    river_tiles = {(r["world_x"], r["world_y"]) for r in river_rows}

    # 5. Narrow river set for crossing classification
    narrow_river = {
        (rx, ry) for rx, ry in river_tiles
        if sum(
            1 for ddx, ddy in ((0, 1), (0, -1), (1, 0), (-1, 0))
            if (rx + ddx, ry + ddy) in river_tiles
        ) == 0
    }

    # 6. Generate paths — A* crosses rivers at moderate cost
    if nodes:
        path_overrides = await asyncio.to_thread(
            _generate_village_paths_sync, seed, nodes, river_tiles,
        )
        if path_overrides:
            await db.executemany(
                "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
                path_overrides,
            )
            # 7. Upgrade river tiles where paths cross them:
            #    wide river crossings  → bridge
            #    narrow tributary fords → path
            wide_cross   = [(x, y) for x, y, _ in path_overrides
                            if (x, y) in river_tiles and (x, y) not in narrow_river]
            narrow_cross = [(x, y) for x, y, _ in path_overrides
                            if (x, y) in narrow_river]
            if wide_cross:
                await db.executemany(
                    "UPDATE tile_overrides SET tile_type='bridge'"
                    " WHERE world_x=? AND world_y=? AND tile_type='river'",
                    wide_cross,
                )
            if narrow_cross:
                await db.executemany(
                    "UPDATE tile_overrides SET tile_type='path'"
                    " WHERE world_x=? AND world_y=? AND tile_type='river'",
                    narrow_cross,
                )
