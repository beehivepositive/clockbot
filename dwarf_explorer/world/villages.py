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
    "vil_blacksmith", "vil_tavern", "vil_hospital", "vil_tree",
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

    buildings: list[tuple[int, int, str]] = []

    # ── Required special buildings ────────────────────────────────────────────
    required = ["vil_church", "vil_bank", "vil_shop", "vil_blacksmith",
                "vil_tavern", "vil_hospital"]
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

    # ── Houses (4-8) ──────────────────────────────────────────────────────────
    house_count = rng.randint(4, 8)
    for _ in range(500):
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
    """Harbor village: water+dock at bottom edge, buildings+well above, entry at top.

    Returns (width, height, tiles, entry_pos, dock_pos, buildings).
    """
    W, H = 16, 16
    cx = W // 2   # centre column  = 8
    cy = 7        # horizontal road row

    rng = random.Random(seed + _VILLAGE_SEED_OFFSET + village_id + world_x * 997 + world_y * 1009 + 42)

    grid: list[list[str]] = [["vil_grass"] * W for _ in range(H)]

    # ── Water zone, dock, roads, well, and entry — oriented by ocean_edge ─────
    cy = H // 2  # recalculate based on edge

    if ocean_edge == 0:   # south — water at bottom
        water_rows = range(H - 2, H)
        dock_x, dock_y = cx, H - 2
        shore_inner = H - 3
        road_range = range(1, shore_inner + 1)
        entry_x, entry_y = cx, 1
        for yr in water_rows:
            for xr in range(W): grid[yr][xr] = "vil_water"
        for yr in road_range: grid[yr][cx] = "vil_path"
        for xr in range(1, W - 1): grid[cy][xr] = "vil_path"
    elif ocean_edge == 1: # north — water at top
        water_rows = range(0, 2)
        dock_x, dock_y = cx, 1
        shore_inner = 2
        road_range = range(shore_inner, H - 1)
        entry_x, entry_y = cx, H - 2
        for yr in water_rows:
            for xr in range(W): grid[yr][xr] = "vil_water"
        for yr in road_range: grid[yr][cx] = "vil_path"
        for xr in range(1, W - 1): grid[cy][xr] = "vil_path"
    elif ocean_edge == 2: # west — water at left
        for yr in range(H):
            grid[yr][0] = "vil_water"
            grid[yr][1] = "vil_water"
        dock_x, dock_y = 1, H // 2
        shore_inner = 2
        for xr in range(shore_inner, W - 1): grid[H // 2][xr] = "vil_path"
        for yr in range(1, H - 1): grid[yr][cx] = "vil_path"
        entry_x, entry_y = W - 2, H // 2
    else:                 # east — water at right
        for yr in range(H):
            grid[yr][W - 1] = "vil_water"
            grid[yr][W - 2] = "vil_water"
        dock_x, dock_y = W - 2, H // 2
        shore_inner = W - 3
        for xr in range(1, shore_inner + 1): grid[H // 2][xr] = "vil_path"
        for yr in range(1, H - 1): grid[yr][cx] = "vil_path"
        entry_x, entry_y = 1, H // 2

    grid[dock_y][dock_x] = "vil_dock"
    grid[cy][cx] = "vil_well"
    grid[entry_y][entry_x] = "vil_path"

    # ── Occupied tracking ─────────────────────────────────────────────────────
    occupied: set[tuple[int, int]] = set()
    for yr in range(H):
        for xr in range(W):
            if grid[yr][xr] == "vil_water":
                occupied.add((xr, yr))
    for x in range(W): occupied.add((x, 0)); occupied.add((x, H - 1))
    for y in range(H): occupied.add((0, y)); occupied.add((W - 1, y))
    for x in range(W): occupied.add((x, cy))
    for y in range(H): occupied.add((cx, y))
    occupied.add((cx, cy))

    buildings: list[tuple[int, int, str]] = []

    # ── Required buildings ────────────────────────────────────────────────────
    required = ["vil_church", "vil_bank", "vil_shop", "vil_blacksmith", "vil_tavern", "vil_hospital"]
    rng.shuffle(required)
    for btype in required:
        for _ in range(200):
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

    # ── Houses ────────────────────────────────────────────────────────────────
    house_count = rng.randint(2, 3)
    for _ in range(200):
        if sum(1 for _, _, t in buildings if t == "vil_house") >= house_count:
            break
        bx = rng.randint(2, W - 3)
        by = rng.randint(2, H - 3)
        if (bx, by) in occupied:
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

    # ── Trees at upper corners ─────────────────────────────────────────────────
    for tx, ty in [(1, 1), (W - 2, 1)]:
        if (tx, ty) not in occupied:
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
    bx = 1 if rng.random() < 0.5 else W - 2
    tiles[(bx, 1)] = "b_bed"
    sx = W - 2 if bx == 1 else 1
    tiles[(sx, 1)] = "b_stove"
    tx, ty = W//2, H//2
    tiles[(tx, ty)] = "b_table"
    door_x, door_y = W//2, H-1
    for cdx, cdy in [(0,-1),(0,1),(-1,0),(1,0)]:
        ccx, ccy = tx+cdx, ty+cdy
        if (ccx, ccy) == (door_x, door_y - 1):
            continue
        if 1 <= ccx < W-1 and 1 <= ccy < H-1 and tiles[(ccx,ccy)] == "b_floor":
            tiles[(ccx, ccy)] = "b_chair"
    for x in range(1, W-1):
        if tiles[(x, 1)] == "b_floor":
            tiles[(x, 1)] = "b_bookshelf"
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


def _tavern_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    """Tavern with a bar along the back wall, tables/chairs, and quest NPCs."""
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    # Door at bottom centre
    tiles[(W//2, H-1)] = "b_door"

    # ── Bar counter along the back wall ───────────────────────────────────────
    # Row 2: bar counter tiles (barrier); row 1: barrels behind bar
    for x in range(2, W-2):
        tiles[(x, 2)] = "b_bar_counter"
    # Barrels in back corners
    tiles[(1, 1)] = "b_barrel"
    tiles[(W-2, 1)] = "b_barrel"
    # Barkeep NPC stands at row 3 (in front of bar, facing patrons)
    tiles[(W//2, 3)] = "b_barkeep"

    # ── Table clusters (2 groups) ─────────────────────────────────────────────
    # Group 1: left side of room
    t1x, t1y = W//4, H//2
    if tiles.get((t1x, t1y)) == "b_floor":
        tiles[(t1x, t1y)] = "b_table"
        for cdx, cdy in [(0,-1),(0,1),(-1,0),(1,0)]:
            cx2, cy2 = t1x+cdx, t1y+cdy
            if 1 <= cx2 < W-1 and 1 <= cy2 < H-1 and tiles[(cx2,cy2)] == "b_floor":
                tiles[(cx2, cy2)] = "b_chair"
        # Quest NPC 1 adjacent to this table
        for cdx, cdy in [(1,0),(0,1),(-1,0),(0,-1)]:
            nx2, ny2 = t1x+cdx*2, t1y+cdy
            if 1 <= nx2 < W-1 and 1 <= ny2 < H-1 and tiles[(nx2,ny2)] == "b_floor":
                tiles[(nx2, ny2)] = "b_tavern_npc"
                break

    # Group 2: right side of room
    t2x, t2y = (3*W)//4, H//2 + 1
    if tiles.get((t2x, t2y)) == "b_floor":
        tiles[(t2x, t2y)] = "b_table"
        for cdx, cdy in [(0,-1),(0,1),(-1,0),(1,0)]:
            cx2, cy2 = t2x+cdx, t2y+cdy
            if 1 <= cx2 < W-1 and 1 <= cy2 < H-1 and tiles[(cx2,cy2)] == "b_floor":
                tiles[(cx2, cy2)] = "b_chair"
        # Quest NPC 2 adjacent to this table
        for cdx, cdy in [(1,0),(0,1),(-1,0),(0,-1)]:
            nx2, ny2 = t2x+cdx*2, t2y+cdy
            if 1 <= nx2 < W-1 and 1 <= ny2 < H-1 and tiles[(nx2,ny2)] == "b_floor":
                tiles[(nx2, ny2)] = "b_tavern_npc"
                break

    # Extra table near back
    if H > 9:
        t3x, t3y = W//2, H - 4
        if tiles.get((t3x, t3y)) == "b_floor":
            tiles[(t3x, t3y)] = "b_table"
            for cdx, cdy in [(-1,0),(1,0)]:
                cx2, cy2 = t3x+cdx, t3y
                if 1 <= cx2 < W-1 and tiles[(cx2,cy2)] == "b_floor":
                    tiles[(cx2, cy2)] = "b_chair"

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


def _generate_building_interior(
    house_id: int, seed: int, village_id: int,
    building_type: str, door_vx: int, door_vy: int,
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
        tiles_dict = _tavern_interior(rng, W, H)
    elif building_type in ("vil_hospital", "hospital"):
        W, H = rng.randint(9, 11), rng.randint(9, 11)
        tiles_dict = _hospital_interior(rng, W, H)
    else:  # house
        W, H = rng.randint(7, 11), rng.randint(6, 9)
        tiles_dict = _house_interior(rng, W, H)

    entry_pos = (W // 2, H - 2)
    tile_list = [(x, y, tt) for (x, y), tt in tiles_dict.items()]
    return W, H, tile_list, entry_pos


# ── DB helpers ────────────────────────────────────────────────────────────────

_CANONICAL_BUILDING_TYPE = {
    "vil_house":       "house",
    "vil_church":      "church",
    "vil_bank":        "bank",
    "vil_shop":        "shop",
    "vil_blacksmith":  "blacksmith",
    "vil_tavern":      "tavern",
    "vil_hospital":    "hospital",
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

    W, H, tiles, entry, buildings = await asyncio.to_thread(
        _generate_village_interior, village_id, seed, world_x, world_y
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


async def load_village_viewport(
    village_id: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    half = VIEWPORT_CENTER
    x_min, y_min = center_x - half, center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM village_tiles "
        "WHERE village_id = ? AND local_x >= ? AND local_x <= ? AND local_y >= ? AND local_y <= ?",
        (village_id, x_min, center_x + half, y_min, center_y + half),
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
