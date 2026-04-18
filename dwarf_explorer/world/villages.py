from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import (
    VILLAGE_MIN_SIZE, VILLAGE_MAX_SIZE,
    VIEWPORT_SIZE, VIEWPORT_CENTER,
    INTERIOR_VIEWPORT_SIZE, INTERIOR_VIEWPORT_CENTER,
)
from dwarf_explorer.world.generator import TileData

_VILLAGE_SEED_OFFSET  = 7000
_BUILDING_SEED_OFFSET = 8000


# ── Village interior generation ───────────────────────────────────────────────

def _generate_village_interior(
    village_id: int, seed: int, world_x: int, world_y: int,
) -> tuple[int, int, list[tuple[int, int, str]], tuple[int, int],
           list[tuple[int, int, str]]]:
    """Generate village interior with single-tile buildings.

    Returns (width, height, tiles, entry_pos, buildings).
    buildings: list of (vil_x, vil_y, building_type)
    """
    rng = random.Random(seed + _VILLAGE_SEED_OFFSET + village_id + world_x * 997 + world_y * 1009)

    W = rng.randint(VILLAGE_MIN_SIZE, VILLAGE_MAX_SIZE)
    H = rng.randint(VILLAGE_MIN_SIZE, VILLAGE_MAX_SIZE)

    grid: list[list[str]] = [["vil_grass"] * W for _ in range(H)]

    cx, cy = W // 2, H // 2

    # ── Main roads ────────────────────────────────────────────────────────────
    for x in range(1, W - 1):
        grid[cy][x] = "vil_path"
    for y in range(1, H - 1):
        grid[y][cx] = "vil_path"

    # ── Well ──────────────────────────────────────────────────────────────────
    grid[cy][cx] = "vil_well"

    occupied: set[tuple[int, int]] = set()
    # roads, border, well
    for x in range(W): occupied.add((x, cy)); occupied.add((x, 0)); occupied.add((x, H - 1))
    for y in range(H): occupied.add((cx, y)); occupied.add((0, y)); occupied.add((W - 1, y))
    occupied.add((cx, cy))

    buildings: list[tuple[int, int, str]] = []

    # ── Required special buildings (church, bank, shop) ────────────────────
    required = ["vil_church", "vil_bank", "vil_shop"]
    rng.shuffle(required)
    for btype in required:
        for _ in range(200):
            bx = rng.randint(2, W - 3)
            by = rng.randint(2, H - 3)
            if (bx, by) in occupied:
                continue
            # Require a path tile adjacent to building for access
            adj = [(bx+1,by),(bx-1,by),(bx,by+1),(bx,by-1)]
            if not any(0 <= ax < W and 0 <= ay < H and grid[ay][ax] == "vil_path" for ax, ay in adj):
                continue
            grid[by][bx] = btype
            occupied.add((bx, by))
            buildings.append((bx, by, btype))
            # Ensure connecting path to road
            _connect_to_road(grid, bx, by, cx, cy, W, H, occupied)
            break

    # ── Houses (3-5 single tiles) ────────────────────────────────────────────
    house_count = rng.randint(3, 5)
    for _ in range(300):
        if sum(1 for _, _, t in buildings if t == "vil_house") >= house_count:
            break
        bx = rng.randint(2, W - 3)
        by = rng.randint(2, H - 3)
        if (bx, by) in occupied:
            continue
        adj = [(bx+1,by),(bx-1,by),(bx,by+1),(bx,by-1)]
        if not any(0 <= ax < W and 0 <= ay < H and grid[ay][ax] in ("vil_path","vil_grass") for ax, ay in adj):
            continue
        grid[by][bx] = "vil_house"
        occupied.add((bx, by))
        buildings.append((bx, by, "vil_house"))
        _connect_to_road(grid, bx, by, cx, cy, W, H, occupied)

    # ── Garden patches ────────────────────────────────────────────────────────
    for _ in range(rng.randint(2, 4)):
        for _ in range(60):
            gw = rng.randint(2, 3)
            gh = rng.randint(2, 3)
            gx = rng.randint(2, W - gw - 2)
            gy = rng.randint(2, H - gh - 2)
            g_set = {(gx + dx, gy + dy) for dy in range(gh) for dx in range(gw)}
            if not (g_set & occupied):
                for (gxi, gyi) in g_set:
                    grid[gyi][gxi] = "vil_garden"
                occupied.update(g_set)
                break

    # ── Trees at corners ─────────────────────────────────────────────────────
    for tx, ty in [(1, 1), (W-2, 1), (1, H-2), (W-2, H-2)]:
        if (tx, ty) not in occupied:
            grid[ty][tx] = "vil_tree"
            occupied.add((tx, ty))

    # ── Entry (bottom-centre path tile) ──────────────────────────────────────
    entry_x, entry_y = cx, H - 2
    grid[entry_y][entry_x] = "vil_path"

    tiles = [(x, y, grid[y][x]) for y in range(H) for x in range(W)]
    return W, H, tiles, (entry_x, entry_y), buildings


def _connect_to_road(
    grid: list[list[str]], bx: int, by: int,
    cx: int, cy: int, W: int, H: int,
    occupied: set[tuple[int, int]],
) -> None:
    """Draw a short path from building tile toward the nearest road axis."""
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
        if t not in ("vil_house", "vil_church", "vil_bank", "vil_shop", "vil_well", "vil_tree"):
            grid[npy][npx] = "vil_path"
        px, py = npx, npy


# ── Building interior generation ─────────────────────────────────────────────

def _house_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    # Walls + floor
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    # Door bottom centre
    tiles[(W//2, H-1)] = "b_door"
    # Bed corner
    bx = 1 if rng.random() < 0.5 else W - 2
    tiles[(bx, 1)] = "b_bed"
    # Stove opposite corner
    sx = W - 2 if bx == 1 else 1
    tiles[(sx, 1)] = "b_stove"
    # Table + chairs middle
    tx, ty = W//2, H//2
    tiles[(tx, ty)] = "b_table"
    for cdx, cdy in [(0,-1),(0,1),(-1,0),(1,0)]:
        ccx, ccy = tx+cdx, ty+cdy
        if 1 <= ccx < W-1 and 1 <= ccy < H-1 and tiles[(ccx,ccy)] == "b_floor":
            tiles[(ccx, ccy)] = "b_chair"
    # Bookshelf
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
    # Altar at far end
    tiles[(W//2, 1)] = "b_altar"
    for dx in [-1, 0, 1]:
        cx = W//2 + dx
        if 0 < cx < W-1:
            tiles[(cx, 2)] = "b_candle"
    # Pews in rows
    for row in range(3, H-2, 2):
        for col in range(2, W-2):
            if tiles[(col, row)] == "b_floor":
                tiles[(col, row)] = "b_pew"
    # Priest NPC near altar
    tiles[(W//2, 3)] = "b_priest"
    return tiles


def _bank_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"
    # Counter along back wall (row 2) — full width minus corners
    for x in range(2, W-2):
        tiles[(x, 2)] = "b_counter"
    # NPC stands in front of the counter (row 3) — accessible to the player
    tiles[(W//2, 3)] = "b_bank_npc"
    # Safes behind the counter against the back wall
    tiles[(1, 1)] = "b_safe"
    tiles[(W-2, 1)] = "b_safe"
    return tiles


def _shop_interior(rng: random.Random, W: int, H: int) -> dict[tuple[int,int], str]:
    tiles: dict[tuple[int,int], str] = {}
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "b_wall" if (x == 0 or x == W-1 or y == 0 or y == H-1) else "b_floor"
    tiles[(W//2, H-1)] = "b_door"
    # Counter along back
    for x in range(2, W-2):
        tiles[(x, 1)] = "b_shop_counter"
    # NPC behind counter
    tiles[(W//2, 1)] = "b_shop_npc"
    # Shelves along sides
    for y in range(2, H-2):
        if tiles[(1, y)] == "b_floor":
            tiles[(1, y)] = "b_shelf"
        if tiles[(W-2, y)] == "b_floor":
            tiles[(W-2, y)] = "b_shelf"
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
    else:  # house
        W, H = rng.randint(7, 11), rng.randint(6, 9)
        tiles_dict = _house_interior(rng, W, H)

    entry_pos = (W // 2, H - 2)
    tile_list = [(x, y, tt) for (x, y), tt in tiles_dict.items()]
    return W, H, tile_list, entry_pos


# ── DB helpers ────────────────────────────────────────────────────────────────

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
        canonical = {"vil_house": "house", "vil_church": "church",
                     "vil_bank": "bank", "vil_shop": "shop"}.get(btype, "house")
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
    half = INTERIOR_VIEWPORT_CENTER
    x_min, y_min = center_x - half, center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM house_tiles "
        "WHERE house_id = ? AND local_x >= ? AND local_x <= ? AND local_y >= ? AND local_y <= ?",
        (house_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}
    grid = []
    for local_y in range(INTERIOR_VIEWPORT_SIZE):
        row_tiles = []
        for local_x in range(INTERIOR_VIEWPORT_SIZE):
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
