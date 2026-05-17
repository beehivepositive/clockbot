from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import (
    VILLAGE_MIN_SIZE, VILLAGE_MAX_SIZE,
    VIEWPORT_SIZE, VIEWPORT_CENTER,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.world.terrain import get_coast_boundary

_VILLAGE_SEED_OFFSET  = 7000
_BUILDING_SEED_OFFSET = 8000

# Building tile types that paths must not overwrite
_PROTECTED_TILES = {
    "vil_well", "vil_house", "vil_church", "vil_bank", "vil_shop",
    "vil_blacksmith", "vil_tavern", "vil_hospital", "vil_lumber_mill", "vil_farmhouse",
    "vil_puzzle_board",
    "vil_tree", "vil_fence", "vil_fence_gate",
    "vil_cow", "vil_pig", "vil_chicken", "vil_goat", "vil_sheep",
    "vil_pen_grass",
    "vil_farmland",
    "vil_seeds_wheat", "vil_seeds_carrot", "vil_seeds_potato",
    "vil_crop_wheat", "vil_crop_carrot", "vil_crop_potato",
}


# ── Path helpers ──────────────────────────────────────────────────────────────

def _draw_path(
    grid: list[list[str]],
    sx: int, sy: int, ex: int, ey: int,
    W: int, H: int, rng: random.Random,
    meander_chance: float = 0.25,
) -> None:
    """Draw a meandering path from (sx,sy) toward (ex,ey).

    The path walks primarily toward the target but occasionally steps
    perpendicular, creating an organic winding road feel.
    """
    px, py = sx, sy
    for _ in range(W + H + 10):
        if px == ex and py == ey:
            break
        dx, dy = ex - px, ey - py
        if dx == 0 and dy == 0:
            break

        # Primary direction
        if abs(dx) >= abs(dy):
            step = (1 if dx > 0 else -1, 0)
        else:
            step = (0, 1 if dy > 0 else -1)

        # Random meander — take a perpendicular step
        if rng.random() < meander_chance and (abs(dx) + abs(dy)) > 3:
            if abs(dx) >= abs(dy):
                step = (0, rng.choice([-1, 1]))
            else:
                step = (rng.choice([-1, 1]), 0)

        nx, ny = px + step[0], py + step[1]
        if 1 <= nx < W - 1 and 1 <= ny < H - 1:
            if grid[ny][nx] not in _PROTECTED_TILES:
                grid[ny][nx] = "vil_path"
            px, py = nx, ny
        else:
            # Fall back to primary direction
            pdx = 1 if dx > 0 else -1 if dx < 0 else 0
            pdy = 1 if dy > 0 else -1 if dy < 0 else 0
            nx2, ny2 = px + pdx, py + pdy
            if 1 <= nx2 < W - 1 and 1 <= ny2 < H - 1:
                if grid[ny2][nx2] not in _PROTECTED_TILES:
                    grid[ny2][nx2] = "vil_path"
                px, py = nx2, ny2
            else:
                break


def _connect_to_road(
    grid: list[list[str]], bx: int, by: int,
    cx: int, cy: int, W: int, H: int,
    occupied: set[tuple[int, int]],
) -> None:
    """Walk a short spur from a building tile toward the nearest path."""
    px, py = bx, by
    for _ in range(max(W, H)):
        if grid[py][px] == "vil_path":
            break
        if abs(px - cx) >= abs(py - cy):
            step = 1 if cx > px else -1
            npx, npy = px + step, py
        else:
            step = 1 if cy > py else -1
            npx, npy = px, py + step
        if not (1 <= npx < W - 1 and 1 <= npy < H - 1):
            break
        t = grid[npy][npx]
        if t not in _PROTECTED_TILES:
            grid[npy][npx] = "vil_path"
        px, py = npx, npy


# ── Village interior generation ───────────────────────────────────────────────

def _extend_to_edge(
    grid: list[list[str]], px: int, py: int,
    W: int, H: int, direction: str,
) -> tuple[int, int]:
    """Punch a straight path segment from (px,py) to the map border in `direction`.

    direction: "N" | "S" | "E" | "W"
    Returns the border tile reached.
    """
    dx, dy = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}[direction]
    x, y = px, py
    while True:
        nx, ny = x + dx, y + dy
        if nx < 0 or nx >= W or ny < 0 or ny >= H:
            break
        if grid[ny][nx] not in _PROTECTED_TILES:
            grid[ny][nx] = "vil_path"
        x, y = nx, ny
    return x, y


def _generate_village_interior(
    village_id: int, seed: int, world_x: int, world_y: int,
    river_side: str | None = None,
) -> tuple[int, int, list[tuple[int, int, str]], tuple[int, int],
           list[tuple[int, int, str]]]:
    """Generate a 32×32 village with a triangular, meandering road network.

    Four cardinal spokes radiate from the central well with slight random
    offsets.  Two or three optional diagonal spokes and multiple cross-
    connectors between adjacent tip-pairs create triangular cells.  The south
    spoke is always extended straight to the bottom border (entry point).
    1-3 other spokes may also exit their respective edges for extra road exits.

    Returns (width, height, tiles, entry_pos, buildings).
    """
    rng = random.Random(seed + _VILLAGE_SEED_OFFSET + village_id + world_x * 997 + world_y * 1009)

    W = H = 32

    grid: list[list[str]] = [["vil_grass"] * W for _ in range(H)]

    cx, cy = W // 2, H // 2  # centre (16, 16)

    # ── Well at centre ────────────────────────────────────────────────────────
    grid[cy][cx] = "vil_well"

    # ── Pre-place farm cluster BEFORE paths so roads route around it ──────────
    # Farmland is directly adjacent to the farmhouse; pen is on the opposite side.
    # All tiles are in _PROTECTED_TILES, so _draw_path won't overwrite them.
    from dwarf_explorer.config import FARM_ANIMALS
    PEN_W, PEN_H = 7, 5
    _land_w = rng.randint(4, 6)
    _land_h = rng.randint(3, 5)
    _farm_pre: set[tuple[int, int]] = set()
    _farm_cluster_placed = False
    _farm_fx, _farm_fy = 0, 0  # farmhouse position (set when placed)

    # Each pair: (pen_direction, land_direction) as (dx, dy)
    _orient_pairs = [
        ((0, 1), (0, -1)),   # pen south, land north
        ((0, -1), (0, 1)),   # pen north, land south
        ((1, 0), (-1, 0)),   # pen east,  land west
        ((-1, 0), (1, 0)),   # pen west,  land east
    ]

    for _attempt in range(600):
        _fx = rng.randint(5, W - 6)
        _fy = rng.randint(5, H - 6)
        if abs(_fx - cx) <= 3 and abs(_fy - cy) <= 3:
            continue

        rng.shuffle(_orient_pairs)
        for (pdx, pdy), (ldx, ldy) in _orient_pairs:
            # Pen top-left — directly adjacent to farmhouse
            if   pdy ==  1: _px0, _py0 = _fx - PEN_W // 2,  _fy + 1
            elif pdy == -1: _px0, _py0 = _fx - PEN_W // 2,  _fy - PEN_H
            elif pdx ==  1: _px0, _py0 = _fx + 1,            _fy - PEN_H // 2
            else:           _px0, _py0 = _fx - PEN_W,        _fy - PEN_H // 2

            # Farmland top-left — directly adjacent to farmhouse (opposite side)
            if   ldy == -1: _lx0, _ly0 = _fx - _land_w // 2, _fy - _land_h
            elif ldy ==  1: _lx0, _ly0 = _fx - _land_w // 2, _fy + 1
            elif ldx ==  1: _lx0, _ly0 = _fx + 1,             _fy - _land_h // 2
            else:           _lx0, _ly0 = _fx - _land_w,       _fy - _land_h // 2

            _land = {(_lx0+dx, _ly0+dy) for dx in range(_land_w) for dy in range(_land_h)}
            _pen  = {(_px0+dx, _py0+dy) for dx in range(PEN_W)   for dy in range(PEN_H)}
            _all  = {(_fx, _fy)} | _land | _pen

            if not all(2 <= x <= W - 3 and 2 <= y <= H - 3 for x, y in _all):
                continue
            if (cx, cy) in _all:
                continue
            if _land & _pen:
                continue

            # Place farmhouse
            grid[_fy][_fx] = "vil_farmhouse"

            # Place farmland
            for _lx, _ly in _land:
                grid[_ly][_lx] = "vil_farmland"

            # Place pen fence perimeter
            _pen_corners = {
                (_px0, _py0), (_px0 + PEN_W - 1, _py0),
                (_px0, _py0 + PEN_H - 1), (_px0 + PEN_W - 1, _py0 + PEN_H - 1),
            }
            _perim: list[tuple[int, int]] = []
            for _dx in range(PEN_W):
                for _dy in range(PEN_H):
                    _gpx, _gpy = _px0 + _dx, _py0 + _dy
                    if _dx == 0 or _dx == PEN_W - 1 or _dy == 0 or _dy == PEN_H - 1:
                        grid[_gpy][_gpx] = "vil_fence"
                        _perim.append((_gpx, _gpy))

            # Gate: non-corner, not directly adjacent to farmhouse
            _gate_cands = [
                (_gx, _gy) for _gx, _gy in _perim
                if (_gx, _gy) not in _pen_corners
                and abs(_gx - _fx) + abs(_gy - _fy) > 1
            ]
            if _gate_cands:
                _gx, _gy = rng.choice(_gate_cands)
                grid[_gy][_gx] = "vil_fence_gate"

            # Animals inside pen — one consistent species per village
            _village_animal = FARM_ANIMALS[rng.randint(0, len(FARM_ANIMALS) - 1)]
            _pen_interior = [
                (_px0 + _dx, _py0 + _dy)
                for _dx in range(1, PEN_W - 1)
                for _dy in range(1, PEN_H - 1)
            ]
            rng.shuffle(_pen_interior)
            _animal_count = rng.randint(3, 6)
            for _apos in _pen_interior[:_animal_count]:
                grid[_apos[1]][_apos[0]] = _village_animal
            # Fill remaining interior tiles so paths can't cut through the pen
            for _apos in _pen_interior[_animal_count:]:
                grid[_apos[1]][_apos[0]] = "vil_pen_grass"

            _farm_pre.update(_all)
            _farm_cluster_placed = True
            _farm_fx, _farm_fy = _fx, _fy
            break

        if _farm_cluster_placed:
            break

    # ── Cardinal spoke inner endpoints ────────────────────────────────────────
    # Each spoke wanders from the well toward a point near (but not at) its
    # respective edge, then is optionally extended straight to the border.
    off = lambda lo, hi: rng.randint(lo, hi)  # noqa: E731
    n_inner = (cx + off(-5, 5), 4)
    e_inner = (W - 5, cy + off(-5, 5))
    s_inner = (cx + off(-5, 5), H - 5)
    w_inner = (4, cy + off(-5, 5))

    # Draw the four cardinal spokes (meandering)
    for tx, ty in (n_inner, e_inner, s_inner, w_inner):
        _draw_path(grid, cx, cy, tx, ty, W, H, rng, meander_chance=0.20)

    # ── Diagonal / intermediate spokes ───────────────────────────────────────
    diagonals = []
    if rng.random() < 0.70:
        t = (W - 6, 4 + off(0, 3))        # NE
        _draw_path(grid, cx, cy, t[0], t[1], W, H, rng, 0.20)
        diagonals.append(t)
    if rng.random() < 0.50:
        t = (4 + off(0, 3), H - 6)        # SW
        _draw_path(grid, cx, cy, t[0], t[1], W, H, rng, 0.20)
        diagonals.append(t)
    if rng.random() < 0.40:
        t = (4 + off(0, 3), 4 + off(0, 3))  # NW
        _draw_path(grid, cx, cy, t[0], t[1], W, H, rng, 0.20)
        diagonals.append(t)
    if rng.random() < 0.40:
        t = (W - 6, H - 6)                # SE
        _draw_path(grid, cx, cy, t[0], t[1], W, H, rng, 0.20)
        diagonals.append(t)

    # ── Cross-connectors between adjacent spoke tips (creates triangular loops)
    candidates = [
        (n_inner, e_inner, 0.80),
        (s_inner, w_inner, 0.80),
        (n_inner, w_inner, 0.60),
        (e_inner, s_inner, 0.60),
        (n_inner, s_inner, 0.40),   # north-south direct connector
        (e_inner, w_inner, 0.40),   # east-west direct connector
    ]
    for (ax, ay), (bx2, by2), prob in candidates:
        if rng.random() < prob:
            _draw_path(grid, ax, ay, bx2, by2, W, H, rng, meander_chance=0.30)

    # ── Extend spokes to the map border ──────────────────────────────────────
    # South spoke ALWAYS exits the bottom edge (this becomes the player entry).
    sx, sy = _extend_to_edge(grid, s_inner[0], s_inner[1], W, H, "S")
    # Other spokes randomly exit their edge
    if rng.random() < 0.60:
        _extend_to_edge(grid, n_inner[0], n_inner[1], W, H, "N")
    if rng.random() < 0.50:
        _extend_to_edge(grid, e_inner[0], e_inner[1], W, H, "E")
    if rng.random() < 0.50:
        _extend_to_edge(grid, w_inner[0], w_inner[1], W, H, "W")

    # ── Occupied tracking ─────────────────────────────────────────────────────
    occupied: set[tuple[int, int]] = set()
    # Borders (but NOT the edge tiles we just paved — they count as path)
    for x in range(W):
        if grid[0][x] != "vil_path":
            occupied.add((x, 0))
        if grid[H - 1][x] != "vil_path":
            occupied.add((x, H - 1))
    for y in range(H):
        if grid[y][0] != "vil_path":
            occupied.add((0, y))
        if grid[y][W - 1] != "vil_path":
            occupied.add((W - 1, y))
    occupied.add((cx, cy))  # well
    for y in range(H):
        for x in range(W):
            if grid[y][x] in ("vil_path", "vil_well"):
                occupied.add((x, y))
    # Merge pre-placed farm cluster so other buildings won't overwrite it
    occupied.update(_farm_pre)

    buildings: list[tuple[int, int, str]] = []

    # ── Register pre-placed farmhouse and connect it to the road network ──────
    if _farm_cluster_placed:
        buildings.append((_farm_fx, _farm_fy, "vil_farmhouse"))
        _connect_to_road(grid, _farm_fx, _farm_fy, cx, cy, W, H, occupied)

    # ── Required special buildings ────────────────────────────────────────────
    required = ["vil_church", "vil_bank", "vil_shop", "vil_blacksmith",
                "vil_tavern", "vil_hospital", "vil_puzzle_board"]
    if not _farm_cluster_placed:
        required.append("vil_farmhouse")
    rng.shuffle(required)
    for btype in required:
        for _ in range(400):
            bx = rng.randint(2, W - 3)
            by = rng.randint(2, H - 3)
            if (bx, by) in occupied:
                continue
            adj = [(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)]
            if not any(0 <= ax < W and 0 <= ay < H and grid[ay][ax] == "vil_path"
                       for ax, ay in adj):
                continue
            grid[by][bx] = btype
            occupied.add((bx, by))
            buildings.append((bx, by, btype))
            _connect_to_road(grid, bx, by, cx, cy, W, H, occupied)
            break

    # ── Houses (5-9) ──────────────────────────────────────────────────────────
    house_count = rng.randint(5, 9)
    for _ in range(600):
        if sum(1 for _, _, t in buildings if t == "vil_house") >= house_count:
            break
        bx = rng.randint(2, W - 3)
        by = rng.randint(2, H - 3)
        if (bx, by) in occupied:
            continue
        adj = [(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)]
        if not any(0 <= ax < W and 0 <= ay < H and grid[ay][ax] in ("vil_path", "vil_grass")
                   for ax, ay in adj):
            continue
        grid[by][bx] = "vil_house"
        occupied.add((bx, by))
        buildings.append((bx, by, "vil_house"))
        _connect_to_road(grid, bx, by, cx, cy, W, H, occupied)

    # ── Garden patches ────────────────────────────────────────────────────────
    for _ in range(rng.randint(4, 7)):
        for _ in range(80):
            gw = rng.randint(2, 4)
            gh = rng.randint(2, 4)
            gx = rng.randint(2, W - gw - 2)
            gy = rng.randint(2, H - gh - 2)
            g_set = {(gx + dx, gy + dy) for dy in range(gh) for dx in range(gw)}
            if not (g_set & occupied):
                for (gxi, gyi) in g_set:
                    grid[gyi][gxi] = "vil_garden"
                occupied.update(g_set)
                break

    # ── Corner trees ─────────────────────────────────────────────────────────
    for tx, ty in [(1, 1), (W - 2, 1), (1, H - 2), (W - 2, H - 2)]:
        if (tx, ty) not in occupied:
            grid[ty][tx] = "vil_tree"
            occupied.add((tx, ty))

    # ── Outside NPCs: villagers + guards ─────────────────────────────────────
    # Villagers wander near path/grass tiles
    villager_count = rng.randint(4, 8)
    placed_v = 0
    for _ in range(600):
        if placed_v >= villager_count:
            break
        vx = rng.randint(2, W - 3)
        vy = rng.randint(2, H - 3)
        if (vx, vy) in occupied:
            continue
        if grid[vy][vx] not in ("vil_path", "vil_grass"):
            continue
        grid[vy][vx] = "vil_villager"
        occupied.add((vx, vy))
        placed_v += 1

    # Guards near the village entry path
    guard_count = rng.randint(1, 3)
    placed_g = 0
    # Try to place guards within 4 tiles of the south-spoke entry
    for _ in range(400):
        if placed_g >= guard_count:
            break
        gx = rng.randint(max(2, sx - 4), min(W - 3, sx + 4))
        gy = rng.randint(max(2, sy - 8), min(H - 3, sy + 2))
        if (gx, gy) in occupied:
            continue
        if grid[gy][gx] not in ("vil_path", "vil_grass"):
            continue
        grid[gy][gx] = "vil_guard"
        occupied.add((gx, gy))
        placed_g += 1

    # ── River-side water edge (river villages only) ──────────────────────────
    if river_side:
        # Each column/row gets a random water depth 1-4, seeded for smooth meander
        def _water_depth(idx: int, base_seed: int) -> int:
            h = (base_seed ^ (idx * 2654435761)) & 0xFFFFFFFF
            h = ((h >> 16) ^ h) & 0xFFFFFFFF
            return 1 + (h % 4)   # 1-4

        ws = rng.randint(0, 0xFFFFFF)
        if river_side == "S":
            for x in range(W):
                depth = _water_depth(x, ws)
                for d in range(depth):
                    gy = H - 1 - d
                    if 0 <= gy < H:
                        grid[gy][x] = "vil_water"
                        occupied.add((x, gy))
        elif river_side == "N":
            for x in range(W):
                depth = _water_depth(x, ws)
                for d in range(depth):
                    gy = d
                    if 0 <= gy < H:
                        grid[gy][x] = "vil_water"
                        occupied.add((x, gy))
        elif river_side == "E":
            for y in range(H):
                depth = _water_depth(y, ws)
                for d in range(depth):
                    gx = W - 1 - d
                    if 0 <= gx < W:
                        grid[y][gx] = "vil_water"
                        occupied.add((gx, y))
        elif river_side == "W":
            for y in range(H):
                depth = _water_depth(y, ws)
                for d in range(depth):
                    gx = d
                    if 0 <= gx < W:
                        grid[y][gx] = "vil_water"
                        occupied.add((gx, y))

        # ── Lumber mill: must be directly adjacent to a water tile ───────────
        lumber_placed = False
        for _ in range(500):
            # Pick a random position anywhere in the village interior
            lx = rng.randint(2, W - 3)
            ly = rng.randint(2, H - 3)
            if (lx, ly) in occupied:
                continue
            if grid[ly][lx] in _PROTECTED_TILES:
                continue
            # Must have at least one adjacent water tile
            adj_water = any(
                0 <= lx+ddx < W and 0 <= ly+ddy < H
                and grid[ly+ddy][lx+ddx] == "vil_water"
                for ddx, ddy in [(0,1),(0,-1),(1,0),(-1,0)]
            )
            if not adj_water:
                continue
            grid[ly][lx] = "vil_lumber_mill"
            occupied.add((lx, ly))
            buildings.append((lx, ly, "vil_lumber_mill"))
            _connect_to_road(grid, lx, ly, cx, cy, W, H, occupied)
            lumber_placed = True
            break

        # ── Entry relocation when river blocks the default south exit ────────
        if river_side == "S":
            # South edge is water — relocate entry to north border
            nx_e, ny_e = _extend_to_edge(grid, n_inner[0], n_inner[1], W, H, "N")
            sx, sy = nx_e, ny_e
        elif river_side == "N":
            # North edge is water — use south spoke (already set)
            pass
        elif river_side == "E":
            nx_e, ny_e = _extend_to_edge(grid, w_inner[0], w_inner[1], W, H, "W")
            sx, sy = nx_e, ny_e
        elif river_side == "W":
            nx_e, ny_e = _extend_to_edge(grid, e_inner[0], e_inner[1], W, H, "E")
            sx, sy = nx_e, ny_e

    # (Farm cluster was pre-placed before paths — see top of function)

    # ── Entry at the bottom border (south spoke exit) ─────────────────────────
    # Player enters the village at this border tile.
    # The tile above it (sy-1) should already be path from the spoke.
    entry_x, entry_y = sx, sy

    tiles = [(x, y, grid[y][x]) for y in range(H) for x in range(W)]
    return W, H, tiles, (entry_x, entry_y), buildings


def _generate_harbor_village_interior(
    village_id: int, seed: int, world_x: int, world_y: int, ocean_edge: int = 0,
) -> tuple[int, int, list[tuple[int, int, str]], tuple[int, int],
           tuple[int, int], list[tuple[int, int, str]]]:
    """Harbor village: same size/layout as regular village, with a water+dock zone at one edge.

    ocean_edge: 0=south water, 1=north water, 2=west water, 3=east water
    Returns (width, height, tiles, entry_pos, dock_pos, buildings).
    """
    W = H = 32
    cx, cy = W // 2, H // 2   # centre = (16, 16)
    WATER_DEPTH = 3            # rows/cols of ocean at the coast edge

    rng = random.Random(seed + _VILLAGE_SEED_OFFSET + village_id + world_x * 997 + world_y * 1009 + 42)

    grid: list[list[str]] = [["vil_grass"] * W for _ in range(H)]

    # ── Pre-fill water zone based on ocean_edge ────────────────────────────────
    if ocean_edge == 0:    # south water
        for yr in range(H - WATER_DEPTH, H):
            for xr in range(W): grid[yr][xr] = "vil_water"
        dock_x, dock_y = cx, H - WATER_DEPTH
        _shore_inner_dir = "S"
        entry_dir = "N"
    elif ocean_edge == 1:  # north water
        for yr in range(WATER_DEPTH):
            for xr in range(W): grid[yr][xr] = "vil_water"
        dock_x, dock_y = cx, WATER_DEPTH - 1
        _shore_inner_dir = "N"
        entry_dir = "S"
    elif ocean_edge == 2:  # west water
        for yr in range(H):
            for xr in range(WATER_DEPTH): grid[yr][xr] = "vil_water"
        dock_x, dock_y = WATER_DEPTH - 1, cy
        _shore_inner_dir = "W"
        entry_dir = "E"
    else:                  # east water
        for yr in range(H):
            for xr in range(W - WATER_DEPTH, W): grid[yr][xr] = "vil_water"
        dock_x, dock_y = W - WATER_DEPTH, cy
        _shore_inner_dir = "E"
        entry_dir = "W"

    grid[dock_y][dock_x] = "vil_dock"
    grid[cy][cx] = "vil_well"

    # ── Meandering spoke roads (same style as regular village) ────────────────
    off = lambda lo, hi: rng.randint(lo, hi)  # noqa: E731
    n_inner = (cx + off(-5, 5), 4)
    e_inner = (W - 5, cy + off(-5, 5))
    s_inner = (cx + off(-5, 5), H - 5)
    w_inner = (4, cy + off(-5, 5))

    # Clamp inner spokes away from water zone
    if ocean_edge == 0:
        s_inner = (s_inner[0], H - WATER_DEPTH - 3)
    elif ocean_edge == 1:
        n_inner = (n_inner[0], WATER_DEPTH + 3)
    elif ocean_edge == 2:
        w_inner = (WATER_DEPTH + 3, w_inner[1])
    else:
        e_inner = (W - WATER_DEPTH - 3, e_inner[1])

    for tx, ty in (n_inner, e_inner, s_inner, w_inner):
        _draw_path(grid, cx, cy, tx, ty, W, H, rng, meander_chance=0.25)

    # Diagonal spokes for extra variety
    if rng.random() < 0.65:
        _draw_path(grid, cx, cy, W - 6, 4 + off(0, 3), W, H, rng, 0.20)
    if rng.random() < 0.50:
        _draw_path(grid, cx, cy, 4 + off(0, 3), H - 6, W, H, rng, 0.20)
    if rng.random() < 0.40:
        _draw_path(grid, cx, cy, 4 + off(0, 3), 4 + off(0, 3), W, H, rng, 0.20)

    # Cross-connectors between adjacent spokes
    cross_candidates = [
        (n_inner, e_inner, 0.70),
        (s_inner, w_inner, 0.70),
        (n_inner, w_inner, 0.55),
        (e_inner, s_inner, 0.55),
        (n_inner, s_inner, 0.35),
        (e_inner, w_inner, 0.35),
    ]
    for (ax, ay), (bx2, by2), prob in cross_candidates:
        if rng.random() < prob:
            _draw_path(grid, ax, ay, bx2, by2, W, H, rng, meander_chance=0.30)

    # ── Road spur from well toward dock ───────────────────────────────────────
    _draw_path(grid, cx, cy, dock_x, dock_y, W, H, rng, meander_chance=0.15)
    grid[dock_y][dock_x] = "vil_dock"   # restore dock tile after path drawing

    # ── Extend spokes to border on non-water edges ────────────────────────────
    # Entry is on the edge opposite the water.  One more edge exit is chosen randomly.
    if entry_dir == "N":
        ex_x, ex_y = _extend_to_edge(grid, n_inner[0], n_inner[1], W, H, "N")
        if rng.random() < 0.55: _extend_to_edge(grid, e_inner[0], e_inner[1], W, H, "E")
        if rng.random() < 0.55: _extend_to_edge(grid, w_inner[0], w_inner[1], W, H, "W")
    elif entry_dir == "S":
        ex_x, ex_y = _extend_to_edge(grid, s_inner[0], s_inner[1], W, H, "S")
        if rng.random() < 0.55: _extend_to_edge(grid, e_inner[0], e_inner[1], W, H, "E")
        if rng.random() < 0.55: _extend_to_edge(grid, w_inner[0], w_inner[1], W, H, "W")
    elif entry_dir == "E":
        ex_x, ex_y = _extend_to_edge(grid, e_inner[0], e_inner[1], W, H, "E")
        if rng.random() < 0.55: _extend_to_edge(grid, n_inner[0], n_inner[1], W, H, "N")
        if rng.random() < 0.55: _extend_to_edge(grid, s_inner[0], s_inner[1], W, H, "S")
    else:
        ex_x, ex_y = _extend_to_edge(grid, w_inner[0], w_inner[1], W, H, "W")
        if rng.random() < 0.55: _extend_to_edge(grid, n_inner[0], n_inner[1], W, H, "N")
        if rng.random() < 0.55: _extend_to_edge(grid, s_inner[0], s_inner[1], W, H, "S")

    entry_x, entry_y = ex_x, ex_y

    # ── Occupied tracking ─────────────────────────────────────────────────────
    occupied: set[tuple[int, int]] = set()
    for yr in range(H):
        for xr in range(W):
            if grid[yr][xr] in ("vil_water", "vil_dock", "vil_path", "vil_well"):
                occupied.add((xr, yr))
    for x in range(W): occupied.add((x, 0)); occupied.add((x, H - 1))
    for y in range(H): occupied.add((0, y)); occupied.add((W - 1, y))
    occupied.add((cx, cy))

    buildings: list[tuple[int, int, str]] = []

    # ── Required buildings (same list as regular village) ─────────────────────
    required = ["vil_church", "vil_bank", "vil_shop", "vil_blacksmith",
                "vil_tavern", "vil_hospital", "vil_puzzle_board"]
    rng.shuffle(required)
    for btype in required:
        for _ in range(400):
            bx = rng.randint(2, W - 3)
            by = rng.randint(2, H - 3)
            if (bx, by) in occupied:
                continue
            if grid[by][bx] == "vil_water":
                continue
            adj = [(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)]
            if not any(0 <= ax < W and 0 <= ay < H and grid[ay][ax] == "vil_path"
                       for ax, ay in adj):
                continue
            grid[by][bx] = btype
            occupied.add((bx, by))
            buildings.append((bx, by, btype))
            _connect_to_road(grid, bx, by, cx, cy, W, H, occupied)
            break

    # ── Houses (5-9, same as regular village) ─────────────────────────────────
    house_count = rng.randint(5, 9)
    for _ in range(600):
        if sum(1 for _, _, t in buildings if t == "vil_house") >= house_count:
            break
        bx = rng.randint(2, W - 3)
        by = rng.randint(2, H - 3)
        if (bx, by) in occupied:
            continue
        if grid[by][bx] == "vil_water":
            continue
        adj = [(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)]
        if not any(0 <= ax < W and 0 <= ay < H
                   and grid[ay][ax] in ("vil_path", "vil_grass")
                   for ax, ay in adj):
            continue
        grid[by][bx] = "vil_house"
        occupied.add((bx, by))
        buildings.append((bx, by, "vil_house"))
        _connect_to_road(grid, bx, by, cx, cy, W, H, occupied)

    # ── NPCs ─────────────────────────────────────────────────────────────────
    villager_count = rng.randint(4, 8)
    placed_v = 0
    for _ in range(600):
        if placed_v >= villager_count:
            break
        vx, vy = rng.randint(2, W - 3), rng.randint(2, H - 3)
        if (vx, vy) in occupied:
            continue
        if grid[vy][vx] not in ("vil_path", "vil_grass"):
            continue
        grid[vy][vx] = "vil_villager"
        occupied.add((vx, vy))
        placed_v += 1

    # ── Corner trees ──────────────────────────────────────────────────────────
    for tx, ty in [(1, 1), (W - 2, 1), (1, H - 2), (W - 2, H - 2)]:
        if (tx, ty) not in occupied and grid[ty][tx] != "vil_water":
            grid[ty][tx] = "vil_tree"
            occupied.add((tx, ty))

    tiles = [(x, y, grid[y][x]) for y in range(H) for x in range(W)]
    return W, H, tiles, (entry_x, entry_y), (dock_x, dock_y), buildings


# ── Building interior generation ─────────────────────────────────────────────

def _house_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"

    # Bed — one side, stove — opposite side
    bed_left = rng.random() < 0.5
    bx = 1 if bed_left else W - 2
    tiles[(bx, 1)] = "b_bed"
    sx = W - 2 if bed_left else 1
    tiles[(sx, 1)] = "b_stove"

    # Chest next to bed (30% chance on the other adjacent wall tile)
    cx2 = bx + 1 if bed_left else bx - 1
    if 1 <= cx2 < W - 1 and rng.random() < 0.30:
        tiles[(cx2, 1)] = "b_chest"

    # Table in middle with chairs around it
    tx, ty = W // 2, H // 2
    tiles[(tx, ty)] = "b_table"
    door_x = W // 2
    for cdx, cdy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        ccx, ccy = tx + cdx, ty + cdy
        if ccy == H - 2:          # don't block path to door
            continue
        if 1 <= ccx < W-1 and 1 <= ccy < H-1 and tiles[(ccx, ccy)] == "b_floor":
            tiles[(ccx, ccy)] = "b_chair"

    # Bookshelf on back wall (first free slot)
    for x in range(1, W - 1):
        if tiles[(x, 1)] == "b_floor":
            tiles[(x, 1)] = "b_bookshelf"
            break

    # Resident NPC — placed on a free floor tile near the centre
    placed_resident = False
    for cdx, cdy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1)]:
        rx, ry = tx + cdx, ty + cdy
        if 1 <= rx < W-1 and 1 <= ry < H-1 and tiles.get((rx, ry)) == "b_floor":
            tiles[(rx, ry)] = "b_resident"
            placed_resident = True
            break
    # Fallback — any free floor tile in lower half
    if not placed_resident:
        for fy in range(H // 2, H - 1):
            for fx in range(1, W - 1):
                if tiles.get((fx, fy)) == "b_floor":
                    tiles[(fx, fy)] = "b_resident"
                    placed_resident = True
                    break
            if placed_resident:
                break

    # Pet cat — 50% chance, placed on a floor tile near the door
    if rng.random() < 0.50:
        for fx in range(1, W - 1):
            if tiles.get((fx, H - 2)) == "b_floor":
                tiles[(fx, H - 2)] = "b_pet"
                break

    return tiles


def _church_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"
    tiles[(W//2, 1)] = "b_altar"
    for dx in [-1, 0, 1]:
        cx = W//2 + dx
        if 0 < cx < W-1:
            tiles[(cx, 2)] = "b_candle"
    for row in range(3, H-2, 2):
        for col in range(2, W-2):
            if tiles[(col, row)] == "b_floor":
                tiles[(col, row)] = "b_pew"
    tiles[(W//2, 3)] = "b_priest"
    return tiles


def _bank_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"
    for x in range(2, W-2):
        tiles[(x, 2)] = "b_counter"
    tiles[(W//2, 3)] = "b_bank_npc"
    tiles[(1, 1)] = "b_safe"
    tiles[(W-2, 1)] = "b_safe"
    return tiles


def _shop_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"
    for x in range(2, W-2):
        tiles[(x, 1)] = "b_shop_counter"
    tiles[(W//2, 1)] = "b_shop_npc"
    for y in range(2, H-2):
        if tiles[(1, y)] == "b_floor":
            tiles[(1, y)] = "b_shelf"
        if tiles[(W-2, y)] == "b_floor":
            tiles[(W-2, y)] = "b_shelf"
    return tiles


def _blacksmith_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"
    tiles[(W//2, 1)] = "b_forge"
    tiles[(W//2, H//2)] = "b_anvil"
    tiles[(W//2 - 1, H//2)] = "b_blacksmith_npc"
    return tiles


def _place_table_cluster(
    tiles: dict, rng: random.Random,
    tx: int, ty: int, W: int, H: int,
    with_npc: bool = False,
) -> None:
    """Place a table with surrounding chairs and optionally a quest NPC nearby."""
    if tiles.get((tx, ty)) != "b_floor":
        return
    tiles[(tx, ty)] = "b_table"
    for cdx, cdy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        cx2, cy2 = tx + cdx, ty + cdy
        if 1 <= cx2 < W - 1 and 1 <= cy2 < H - 1 and tiles.get((cx2, cy2)) == "b_floor":
            tiles[(cx2, cy2)] = "b_chair"
    if with_npc:
        # Place quest NPC on a floor tile 2 steps away from the table
        dirs = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        rng.shuffle(dirs)
        for cdx, cdy in dirs:
            nx2, ny2 = tx + cdx * 2, ty + cdy
            if 1 <= nx2 < W - 1 and 1 <= ny2 < H - 1 and tiles.get((nx2, ny2)) == "b_floor":
                tiles[(nx2, ny2)] = "b_tavern_npc"
                break


def _tavern_interior(rng: random.Random, W: int, H: int, is_harbor: bool = False) -> dict[tuple[int,int], str]:
    """Tavern with bar, 3-4 table clusters, and 4-6 quest NPCs (patrons)."""
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W - 1 or y == 0 or y == H - 1) else "b_floor"
    tiles[(W // 2, H - 1)] = "b_door"

    # ── Bar counter along back wall ───────────────────────────────────────────
    for x in range(2, W - 2):
        tiles[(x, 2)] = "b_bar_counter"
    tiles[(1, 1)] = "b_barrel"
    tiles[(W - 2, 1)] = "b_barrel"
    # Barkeep in the centre of row 3
    tiles[(W // 2, 3)] = "b_barkeep"

    # ── Table clusters spread across the floor ────────────────────────────────
    # Positions chosen to spread evenly across the space below the bar
    floor_top = 4          # first usable row below bar/barkeep
    floor_bot = H - 2      # last usable row above door wall

    cluster_positions = [
        (W // 4,       (floor_top + floor_bot) // 2,       True),   # left-centre, NPC
        ((3 * W) // 4, (floor_top + floor_bot) // 2,       True),   # right-centre, NPC
        (W // 2,       floor_top + 1,                       True),   # centre-top, NPC
        (W // 4,       floor_bot - 2,                       True),   # left-bottom, NPC
        ((3 * W) // 4, floor_bot - 2,                       False),  # right-bottom, chairs only
    ]
    for tx, ty, with_npc in cluster_positions:
        _place_table_cluster(tiles, rng, tx, ty, W, H, with_npc=with_npc)

    # ── Lone patrons (1-3 extra b_tavern_npc on spare floor tiles) ───────────
    extra_npcs = rng.randint(1, 3)
    placed = 0
    attempts = 0
    while placed < extra_npcs and attempts < 200:
        attempts += 1
        ex = rng.randint(2, W - 3)
        ey = rng.randint(floor_top, floor_bot - 1)
        if tiles.get((ex, ey)) == "b_floor":
            tiles[(ex, ey)] = "b_tavern_npc"
            placed += 1

    # ── Harbour-specific: one crew recruit NPC near the bar ──────────────────
    if is_harbor:
        for _try in range(100):
            rx = rng.randint(2, W - 3)
            ry = rng.randint(floor_top, floor_bot - 1)
            if tiles.get((rx, ry)) == "b_floor":
                tiles[(rx, ry)] = "b_crew_npc"
                break

    return tiles


def _hospital_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    """Hospital with a healer NPC, patient beds, and medicine shelf."""
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    # Door at bottom centre
    tiles[(W//2, H-1)] = "b_door"

    # ── Healer NPC near centre ─────────────────────────────────────────────────
    # Table at row 2 centre (desk), healer stands at row 3
    tiles[(W//2, 2)] = "b_table"
    tiles[(W//2 - 1, 2)] = "b_chair"
    tiles[(W//2, 3)] = "b_healer"

    # ── Medicine shelf along back wall ────────────────────────────────────────
    for x in range(2, W-2):
        tiles[(x, 1)] = "b_medicine_shelf"

    # ── Patient beds along sides ──────────────────────────────────────────────
    bed_rows = list(range(4, H-2, 2))
    for by_r in bed_rows:
        if tiles.get((1, by_r)) == "b_floor":
            tiles[(1, by_r)] = "b_bed"
        if tiles.get((W-2, by_r)) == "b_floor":
            tiles[(W-2, by_r)] = "b_bed"

    # Candle beside each bed
    for by_r in bed_rows:
        if by_r + 1 < H - 1:
            if tiles.get((1, by_r + 1)) == "b_floor":
                tiles[(1, by_r + 1)] = "b_candle"
            if tiles.get((W-2, by_r + 1)) == "b_floor":
                tiles[(W-2, by_r + 1)] = "b_candle"

    return tiles


def _lumber_mill_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    """Lumber mill: 2-wide river on the left, large gear in the water, small CCW
    gear at column 2, and a VERTICAL conveyor column running top-to-bottom.

    Conveyor column layout (x = conv_x, y = 1..H-2):
      top   → b_log_input   (player inserts logs from adjacent floor tile)
      mid   → b_saw         (aligned with small gear row)
      bot   → b_plank_output (player picks up planks from adjacent floor tile)
      rest  → b_conveyor segments

    None of the conveyor tiles are walkable — player stands adjacent on b_floor.
    """
    tiles: dict[tuple[int,int], str] = {}

    # Base layer: walls everywhere, then carve out floor
    for y in range(H):
        for x in range(W):
            if x == 0 or x == W - 1 or y == 0 or y == H - 1:
                tiles[(x, y)] = "b_wall"
            else:
                tiles[(x, y)] = "b_floor"

    # Door at centre-bottom
    tiles[(W // 2, H - 1)] = "b_door"

    # ── Water: columns 0 and 1 are the river ─────────────────────────────────
    for y in range(H):
        tiles[(0, y)] = "b_water"
        tiles[(1, y)] = "b_water"

    # ── Large gear (2×2) centred vertically in the water columns ─────────────
    gear_top_y = H // 2 - 1
    gear_bot_y = H // 2
    tiles[(0, gear_top_y)] = "b_gear_tl"
    tiles[(1, gear_top_y)] = "b_gear_tr"
    tiles[(0, gear_bot_y)] = "b_gear_bl"
    tiles[(1, gear_bot_y)] = "b_gear_br"

    # ── Small CCW gear at column 2, level with large gear bottom ─────────────
    small_gear_y = gear_bot_y
    tiles[(2, small_gear_y)] = "b_gear_small"

    # ── Vertical conveyor column ──────────────────────────────────────────────
    # Saw column is immediately right of the small gear (conv_x = gear_col + 1)
    # so the saw tile is directly adjacent to the small CCW gear.
    # Player walks in columns 4, 5, 6, 7 to the right of the conveyor.
    conv_x   = 3          # fixed column — adjacent to small gear at x=2
    top_y    = 1          # first interior row
    bot_y    = H - 2      # last interior row
    saw_y    = small_gear_y   # saw aligns with the small gear for visual continuity

    for cy in range(top_y, bot_y + 1):
        if cy == top_y:
            tiles[(conv_x, cy)] = "b_log_input"
        elif cy == saw_y:
            tiles[(conv_x, cy)] = "b_saw"
        elif cy == bot_y:
            tiles[(conv_x, cy)] = "b_plank_output"
        else:
            tiles[(conv_x, cy)] = "b_conveyor"

    # ── Lumber NPC stands to the right of the saw ────────────────────────────
    npc_x = min(conv_x + 1, W - 2)
    tiles[(npc_x, saw_y)] = "b_lumber_npc"

    # ── Candle near top-right interior corner ─────────────────────────────────
    candle_x = min(conv_x + 2, W - 2)
    if tiles.get((candle_x, top_y)) == "b_floor":
        tiles[(candle_x, top_y)] = "b_candle"

    return tiles


def _farmhouse_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    """Farmhouse: farmer NPC, table, chairs, seed shelves."""
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"

    # Seed shelves on back wall
    for dx in [-1, 0, 1]:
        sx = W//2 + dx
        if 0 < sx < W-1:
            tiles[(sx, 1)] = "b_shelf"

    # Table and chairs in the middle
    tiles[(W//2, H//2)] = "b_table"
    tiles[(W//2-1, H//2)] = "b_chair"
    if W//2+1 < W-1:
        tiles[(W//2+1, H//2)] = "b_chair"

    # Farmer NPC below the table
    farmer_y = min(H//2 + 1, H-2)
    tiles[(W//2, farmer_y)] = "b_farmer_npc"

    # Stove in upper-left corner
    tiles[(1, 1)] = "b_stove"

    return tiles


def _generate_building_interior(
    house_id: int, seed: int, village_id: int,
    building_type: str, door_vx: int, door_vy: int,
    is_harbor: bool = False,
) -> tuple[int, int, list[tuple[int, int, str]], tuple[int, int]]:
    rng = random.Random(seed + _BUILDING_SEED_OFFSET + house_id + village_id * 97 + door_vx * 13 + door_vy)

    if building_type in ("vil_church", "church"):
        W, H = rng.randint(9, 13), rng.randint(9, 13)
        tiles_dict = _church_interior(rng, W, H)
    elif building_type in ("vil_bank", "bank"):
        W, H = rng.randint(9, 13), rng.randint(7, 9)
        tiles_dict = _bank_interior(rng, W, H)
    elif building_type in ("vil_shop", "shop"):
        W, H = rng.randint(8, 11), rng.randint(7, 9)
        tiles_dict = _shop_interior(rng, W, H)
    elif building_type in ("vil_blacksmith", "blacksmith"):
        W, H = rng.randint(7, 9), rng.randint(6, 8)
        tiles_dict = _blacksmith_interior(rng, W, H)
    elif building_type in ("vil_tavern", "tavern"):
        W, H = rng.randint(11, 13), rng.randint(10, 12)
        tiles_dict = _tavern_interior(rng, W, H, is_harbor=is_harbor)
    elif building_type in ("vil_hospital", "hospital"):
        W, H = rng.randint(9, 11), rng.randint(9, 11)
        tiles_dict = _hospital_interior(rng, W, H)
    elif building_type in ("vil_lumber_mill", "lumber_mill"):
        W, H = rng.randint(9, 11), rng.randint(8, 10)
        tiles_dict = _lumber_mill_interior(rng, W, H)
    elif building_type in ("vil_farmhouse", "farmhouse"):
        W, H = rng.randint(7, 10), rng.randint(6, 8)
        tiles_dict = _farmhouse_interior(rng, W, H)
    else:  # house
        W, H = rng.randint(7, 11), rng.randint(6, 9)
        tiles_dict = _house_interior(rng, W, H)

    entry_pos = (W // 2, H - 2)
    tile_list = [(x, y, tt) for (x, y), tt in tiles_dict.items()]
    return W, H, tile_list, entry_pos


# ── DB helpers ────────────────────────────────────────────────────────────────

_CANONICAL_BUILDING_TYPE = {
    "vil_house":        "house",
    "vil_church":       "church",
    "vil_bank":         "bank",
    "vil_shop":         "shop",
    "vil_blacksmith":   "blacksmith",
    "vil_tavern":       "tavern",
    "vil_hospital":     "hospital",
    "vil_lumber_mill":  "lumber_mill",
    "vil_farmhouse":    "farmhouse",
}


async def get_or_create_village(
    seed: int, world_x: int, world_y: int, db,
) -> tuple[int, int, int]:
    """Return (village_id, entry_local_x, entry_local_y)."""
    row = await db.fetch_one(
        "SELECT village_id, entry_x, entry_y FROM village_entrances "
        "WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        return row["village_id"], row["entry_x"], row["entry_y"]

    cursor = await db.execute("INSERT INTO villages (width, height) VALUES (1, 1)")
    village_id = cursor.lastrowid

    # Detect if this village is adjacent to a river
    river_side = None
    for ddx, ddy, side in [(0,-1,"N"),(0,1,"S"),(1,0,"E"),(-1,0,"W")]:
        adj_river = await db.fetch_one(
            "SELECT 1 FROM tile_overrides WHERE world_x=? AND world_y=? AND tile_type='river'",
            (world_x+ddx, world_y+ddy),
        )
        if adj_river:
            river_side = side
            break

    W, H, tiles, entry, buildings = await asyncio.to_thread(
        _generate_village_interior, village_id, seed, world_x, world_y, river_side
    )
    await db.execute(
        "UPDATE villages SET width = ?, height = ? WHERE village_id = ?",
        (W, H, village_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO village_tiles (village_id, local_x, local_y, tile_type) VALUES (?, ?, ?, ?)",
        [(village_id, lx, ly, tt) for lx, ly, tt in tiles],
    )
    await db.execute(
        "INSERT OR IGNORE INTO village_entrances (village_id, entry_x, entry_y, world_x, world_y) "
        "VALUES (?, ?, ?, ?, ?)",
        (village_id, entry[0], entry[1], world_x, world_y),
    )

    # Generate interiors for each building
    for bx, by, btype in buildings:
        canonical = _CANONICAL_BUILDING_TYPE.get(btype, "house")
        hcursor = await db.execute(
            "INSERT INTO houses (village_id, building_type, width, height) VALUES (?, ?, 1, 1)",
            (village_id, canonical),
        )
        house_id = hcursor.lastrowid
        hW, hH, htiles, hentry = await asyncio.to_thread(
            _generate_building_interior, house_id, seed, village_id, btype, bx, by
        )
        await db.execute(
            "UPDATE houses SET width = ?, height = ? WHERE house_id = ?",
            (hW, hH, house_id),
        )
        await db.executemany(
            "INSERT OR IGNORE INTO house_tiles (house_id, local_x, local_y, tile_type) VALUES (?, ?, ?, ?)",
            [(house_id, lx, ly, tt) for lx, ly, tt in htiles],
        )
        await db.execute(
            "INSERT OR IGNORE INTO house_entrances "
            "(house_id, entry_x, entry_y, village_id, village_x, village_y) VALUES (?, ?, ?, ?, ?, ?)",
            (house_id, hentry[0], hentry[1], village_id, bx, by),
        )

    return village_id, entry[0], entry[1]


async def get_or_create_harbor_village(
    seed: int, world_x: int, world_y: int, db,
) -> tuple[int, int, int, int, int]:
    """Return (village_id, entry_local_x, entry_local_y, dock_x, dock_y)."""
    row = await db.fetch_one(
        "SELECT village_id, entry_x, entry_y FROM village_entrances "
        "WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        _edge, _ = get_coast_boundary(seed)
        _W, _H, _cx = 16, 16, 8
        _dock = {0: (_cx, _H - 2), 1: (_cx, 1), 2: (1, _H // 2), 3: (_W - 2, _H // 2)}
        dk_x, dk_y = _dock.get(_edge, (_cx, _H - 2))
        return row["village_id"], row["entry_x"], row["entry_y"], dk_x, dk_y

    cursor = await db.execute("INSERT INTO villages (width, height) VALUES (1, 1)")
    village_id = cursor.lastrowid

    from dwarf_explorer.world.terrain import get_coast_boundary as _gcb
    ocean_edge, _ = _gcb(seed)
    W, H, tiles, entry, dock, buildings = await asyncio.to_thread(
        _generate_harbor_village_interior, village_id, seed, world_x, world_y, ocean_edge
    )
    await db.execute(
        "UPDATE villages SET width = ?, height = ? WHERE village_id = ?",
        (W, H, village_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO village_tiles (village_id, local_x, local_y, tile_type) VALUES (?, ?, ?, ?)",
        [(village_id, lx, ly, tt) for lx, ly, tt in tiles],
    )
    await db.execute(
        "INSERT OR IGNORE INTO village_entrances (village_id, entry_x, entry_y, world_x, world_y) "
        "VALUES (?, ?, ?, ?, ?)",
        (village_id, entry[0], entry[1], world_x, world_y),
    )

    for bx, by, btype in buildings:
        canonical = _CANONICAL_BUILDING_TYPE.get(btype, "house")
        hcursor = await db.execute(
            "INSERT INTO houses (village_id, building_type, width, height) VALUES (?, ?, 1, 1)",
            (village_id, canonical),
        )
        house_id = hcursor.lastrowid
        # Harbor villages: pass is_harbor=True for taverns so they get a crew NPC
        _is_harbor_bldg = btype in ("vil_tavern", "tavern")
        hW, hH, htiles, hentry = await asyncio.to_thread(
            _generate_building_interior, house_id, seed, village_id, btype, bx, by, _is_harbor_bldg
        )
        await db.execute(
            "UPDATE houses SET width = ?, height = ? WHERE house_id = ?",
            (hW, hH, house_id),
        )
        await db.executemany(
            "INSERT OR IGNORE INTO house_tiles (house_id, local_x, local_y, tile_type) VALUES (?, ?, ?, ?)",
            [(house_id, lx, ly, tt) for lx, ly, tt in htiles],
        )
        await db.execute(
            "INSERT OR IGNORE INTO house_entrances "
            "(house_id, entry_x, entry_y, village_id, village_x, village_y) VALUES (?, ?, ?, ?, ?, ?)",
            (house_id, hentry[0], hentry[1], village_id, bx, by),
        )

    return village_id, entry[0], entry[1], dock[0], dock[1]


async def get_building_at(
    village_id: int, village_x: int, village_y: int, db,
) -> tuple[int, str, int, int] | None:
    """Return (house_id, building_type, entry_x, entry_y) for a building at (vx,vy)."""
    row = await db.fetch_one(
        "SELECT he.house_id, h.building_type, he.entry_x, he.entry_y "
        "FROM house_entrances he JOIN houses h ON h.house_id = he.house_id "
        "WHERE he.village_id = ? AND he.village_x = ? AND he.village_y = ?",
        (village_id, village_x, village_y),
    )
    if row:
        return row["house_id"], row["building_type"], row["entry_x"], row["entry_y"]
    return None


# ── Recruitable NPC helpers ────────────────────────────────────────────────────

def get_recruitable_npc_positions(
    village_id: int, world_x: int, world_y: int, seed: int
) -> list[tuple[int, int]]:
    """Return 3-5 fixed positions of potentially recruitable NPCs for this village.

    Seeded by village parameters so the positions are stable across sessions.
    """
    rng = random.Random(seed + village_id * 137 + world_x * 997 + world_y * 1009 + 999)
    count = rng.randint(3, 5)
    positions: list[tuple[int, int]] = []
    for _ in range(count * 20):
        if len(positions) >= count:
            break
        x = rng.randint(4, 27)
        y = rng.randint(4, 27)
        if (x, y) not in positions:
            positions.append((x, y))
    return positions[:count]


def is_npc_recruitable_for_player(
    user_id: int, village_id: int, npc_x: int, npc_y: int
) -> bool:
    """60% chance an NPC is recruitable for a given player (deterministic per combination)."""
    import hashlib
    h = hashlib.md5(f"{user_id}:{village_id}:{npc_x}:{npc_y}".encode()).digest()
    return (h[0] % 10) < 6


async def get_replacement_npc_position(
    village_id: int, world_x: int, world_y: int, seed: int,
    user_id: int, recruited_x: int, recruited_y: int, db,
) -> tuple[int, int] | None:
    """Find a grass/path tile in the village interior to place a replacement NPC.

    Returns (x, y) of a suitable tile, or None if no open tile found.
    The position is deterministic per (user_id, village_id, recruited_x, recruited_y).
    """
    import hashlib
    # Seed a deterministic RNG for this replacement
    h_int = int(hashlib.md5(
        f"rep:{user_id}:{village_id}:{recruited_x}:{recruited_y}".encode()
    ).hexdigest(), 16)
    rng = random.Random(h_int)

    # Fetch all current tiles in the village so we can find a free grass/path spot
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM village_tiles WHERE village_id = ?",
        (village_id,),
    )
    open_tiles = [
        (r["local_x"], r["local_y"])
        for r in rows
        if r["tile_type"] in ("vil_grass", "vil_path")
        and 4 <= r["local_x"] <= 27 and 4 <= r["local_y"] <= 27
    ]
    if not open_tiles:
        return None
    # Shuffle deterministically and pick the first one not at the recruited position
    rng.shuffle(open_tiles)
    for pos in open_tiles:
        if pos != (recruited_x, recruited_y):
            return pos
    return None


async def load_village_viewport(
    village_id: int, center_x: int, center_y: int, db,
    user_id: int | None = None,
) -> list[list[TileData]]:
    half = VIEWPORT_CENTER
    x_min, y_min = center_x - half, center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM village_tiles "
        "WHERE village_id = ? AND local_x >= ? AND local_x <= ? AND local_y >= ? AND local_y <= ?",
        (village_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    # Apply per-player tile overrides if a user_id was provided
    if user_id is not None:
        from dwarf_explorer.database.repositories import get_player_village_overrides
        overrides = await get_player_village_overrides(db, user_id, village_id)
        tile_map.update(overrides)

    grid = []
    for local_y in range(VIEWPORT_SIZE):
        row_tiles = []
        for local_x in range(VIEWPORT_SIZE):
            cx, cy = x_min + local_x, y_min + local_y
            row_tiles.append(TileData(terrain=tile_map.get((cx, cy), "void"), world_x=cx, world_y=cy))
        grid.append(row_tiles)
    return grid


async def load_village_single_tile(
    village_id: int, local_x: int, local_y: int, db,
) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM village_tiles WHERE village_id = ? AND local_x = ? AND local_y = ?",
        (village_id, local_x, local_y),
    )
    return TileData(terrain=row["tile_type"] if row else "void", world_x=local_x, world_y=local_y)


async def load_building_viewport(
    house_id: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    half = VIEWPORT_CENTER
    x_min, y_min = center_x - half, center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM house_tiles "
        "WHERE house_id = ? AND local_x >= ? AND local_x <= ? AND local_y >= ? AND local_y <= ?",
        (house_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}
    grid = []
    for local_y in range(VIEWPORT_SIZE):
        row_tiles = []
        for local_x in range(VIEWPORT_SIZE):
            cx, cy = x_min + local_x, y_min + local_y
            row_tiles.append(TileData(terrain=tile_map.get((cx, cy), "void"), world_x=cx, world_y=cy))
        grid.append(row_tiles)
    return grid


async def load_building_single_tile(
    house_id: int, local_x: int, local_y: int, db,
) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM house_tiles WHERE house_id = ? AND local_x = ? AND local_y = ?",
        (house_id, local_x, local_y),
    )
    return TileData(terrain=row["tile_type"] if row else "void", world_x=local_x, world_y=local_y)
