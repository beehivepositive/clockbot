from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import (
    VILLAGE_MIN_SIZE, VILLAGE_MAX_SIZE,
    VILLAGE_WALKABLE, VIEWPORT_SIZE, VIEWPORT_CENTER,
)
from dwarf_explorer.world.generator import TileData

_VILLAGE_SEED_OFFSET = 7000
_HOUSE_SEED_OFFSET   = 8000


# ── Village interior generation ───────────────────────────────────────────────

def _generate_village_interior(
    village_id: int, seed: int, world_x: int, world_y: int,
) -> tuple[int, int, list[tuple[int, int, str]], tuple[int, int], list[tuple[int, int, int, int, int, int]]]:
    """Generate a village interior.

    Returns (width, height, tiles, entry_pos, houses).
    tiles  : list of (local_x, local_y, tile_type)
    entry  : (local_x, local_y) — where the player spawns on entering
    houses : list of (hx, hy, hw, hh, door_x, door_y)
    """
    rng = random.Random(seed + _VILLAGE_SEED_OFFSET + village_id + world_x * 997 + world_y * 1009)

    W = rng.randint(VILLAGE_MIN_SIZE, VILLAGE_MAX_SIZE)
    H = rng.randint(VILLAGE_MIN_SIZE, VILLAGE_MAX_SIZE)

    # 2-D grid, default grass
    grid: list[list[str]] = [["vil_grass"] * W for _ in range(H)]

    cx, cy = W // 2, H // 2

    # ── Main roads (cross through centre) ────────────────────────────────────
    for x in range(W):
        grid[cy][x] = "vil_path"
    for y in range(H):
        grid[y][cx] = "vil_path"

    # ── Well at centre ────────────────────────────────────────────────────────
    grid[cy][cx] = "vil_well"

    # ── Track occupied positions ──────────────────────────────────────────────
    occupied: set[tuple[int, int]] = set()
    # roads
    for x in range(W):
        occupied.add((x, cy))
    for y in range(H):
        occupied.add((cx, y))
    # border margin (keep 1 tile clear so player can walk to edge / exit)
    for x in range(W):
        occupied.add((x, 0))
        occupied.add((x, H - 1))
    for y in range(H):
        occupied.add((0, y))
        occupied.add((W - 1, y))

    # ── Houses ────────────────────────────────────────────────────────────────
    house_count = rng.randint(3, 5)
    houses: list[tuple[int, int, int, int, int, int]] = []

    for _ in range(300):
        if len(houses) >= house_count:
            break

        hw = rng.randint(5, 8)
        hh = rng.randint(4, 6)
        hx = rng.randint(2, W - hw - 2)
        hy = rng.randint(2, H - hh - 2)

        # Buffer footprint (house + 1-tile clearance on all sides)
        footprint: set[tuple[int, int]] = set()
        for dy in range(-1, hh + 2):
            for dx in range(-1, hw + 2):
                footprint.add((hx + dx, hy + dy))

        if footprint & occupied:
            continue

        # Draw house walls
        for dy in range(hh):
            for dx in range(hw):
                grid[hy + dy][hx + dx] = "vil_wall"

        # Door placement: face toward nearest road axis
        dist_h = abs((hy + hh // 2) - cy)
        dist_v = abs((hx + hw // 2) - cx)
        if dist_h <= dist_v:
            door_x = hx + hw // 2
            door_y = hy if hy > cy else hy + hh - 1
        else:
            door_y = hy + hh // 2
            door_x = hx if hx > cx else hx + hw - 1

        grid[door_y][door_x] = "vil_door"

        # Path from door toward nearest road tile
        px, py = door_x, door_y
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
            if t not in ("vil_wall", "vil_well"):
                grid[npy][npx] = "vil_path"
                px, py = npx, npy

        occupied.update(footprint)
        houses.append((hx, hy, hw, hh, door_x, door_y))

    # ── Garden patches ────────────────────────────────────────────────────────
    for _ in range(rng.randint(2, 3)):
        for _ in range(60):
            gw = rng.randint(2, 4)
            gh = rng.randint(2, 3)
            gx = rng.randint(2, W - gw - 2)
            gy = rng.randint(2, H - gh - 2)
            g_set = {(gx + dx, gy + dy) for dy in range(gh) for dx in range(gw)}
            if not (g_set & occupied):
                for (gxi, gyi) in g_set:
                    grid[gyi][gxi] = "vil_garden"
                occupied.update(g_set)
                break

    # ── Entry position (bottom centre, on path) ───────────────────────────────
    entry_x = cx
    entry_y = H - 2
    if grid[entry_y][entry_x] not in ("vil_wall",):
        grid[entry_y][entry_x] = "vil_path"

    # Flatten grid to tile list
    tiles = [(x, y, grid[y][x]) for y in range(H) for x in range(W)]
    return W, H, tiles, (entry_x, entry_y), houses


# ── House interior generation ─────────────────────────────────────────────────

def _generate_house_interior(
    house_id: int, seed: int, village_id: int, door_vx: int, door_vy: int,
) -> tuple[int, int, list[tuple[int, int, str]], tuple[int, int]]:
    """Generate a house interior.

    Returns (width, height, tiles, entry_pos).
    entry_pos : where the player spawns inside the house (just inside the door).
    """
    rng = random.Random(seed + _HOUSE_SEED_OFFSET + house_id + village_id * 97 + door_vx * 13 + door_vy)

    W = rng.randint(7, 11)
    H = rng.randint(6, 9)

    tiles: dict[tuple[int, int], str] = {}

    # Floor
    for y in range(H):
        for x in range(W):
            tiles[(x, y)] = "house_floor"

    # Walls
    for x in range(W):
        tiles[(x, 0)]     = "house_wall"
        tiles[(x, H - 1)] = "house_wall"
    for y in range(H):
        tiles[(0, y)]     = "house_wall"
        tiles[(W - 1, y)] = "house_wall"

    # Door at bottom centre (walking onto it exits to village)
    dx = W // 2
    tiles[(dx, H - 1)] = "house_door"

    # Bed in upper corner
    if rng.random() < 0.5:
        bx, by = 1, 1
    else:
        bx, by = W - 2, 1
    tiles[(bx, by)] = "house_bed"

    # Stove in opposite upper corner
    sx = W - 2 if bx == 1 else 1
    tiles[(sx, 1)] = "house_stove"

    # Table near centre
    tx, ty = W // 2, H // 2
    tiles[(tx, ty)] = "house_table"

    # Chairs around table (skip if occupied)
    for cdx, cdy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        ccx, ccy = tx + cdx, ty + cdy
        if 1 <= ccx < W - 1 and 1 <= ccy < H - 1 and tiles[(ccx, ccy)] == "house_floor":
            tiles[(ccx, ccy)] = "house_chair"

    entry_pos = (dx, H - 2)   # one tile inside the door

    tile_list = [(x, y, tt) for (x, y), tt in tiles.items()]
    return W, H, tile_list, entry_pos


# ── DB helpers ────────────────────────────────────────────────────────────────

async def get_or_create_village(
    seed: int, world_x: int, world_y: int, db,
) -> tuple[int, int, int]:
    """Return (village_id, entry_local_x, entry_local_y) for a village at (world_x, world_y).

    Creates the village interior (and all house interiors) on first access.
    """
    # Direct lookup
    row = await db.fetch_one(
        "SELECT village_id, entry_x, entry_y FROM village_entrances "
        "WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        return row["village_id"], row["entry_x"], row["entry_y"]

    # Check adjacent tiles — all 9 tiles in a cluster share the same village
    for ddx in range(-1, 2):
        for ddy in range(-1, 2):
            if ddx == 0 and ddy == 0:
                continue
            adj = await db.fetch_one(
                "SELECT village_id, entry_x, entry_y FROM village_entrances "
                "WHERE world_x = ? AND world_y = ?",
                (world_x + ddx, world_y + ddy),
            )
            if adj:
                await db.execute(
                    "INSERT OR IGNORE INTO village_entrances "
                    "(village_id, entry_x, entry_y, world_x, world_y) VALUES (?, ?, ?, ?, ?)",
                    (adj["village_id"], adj["entry_x"], adj["entry_y"], world_x, world_y),
                )
                return adj["village_id"], adj["entry_x"], adj["entry_y"]

    # Generate new village
    cursor = await db.execute("INSERT INTO villages (width, height) VALUES (1, 1)")
    village_id = cursor.lastrowid

    W, H, tiles, entry, houses = await asyncio.to_thread(
        _generate_village_interior, village_id, seed, world_x, world_y
    )
    await db.execute(
        "UPDATE villages SET width = ?, height = ? WHERE village_id = ?",
        (W, H, village_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO village_tiles (village_id, local_x, local_y, tile_type) "
        "VALUES (?, ?, ?, ?)",
        [(village_id, lx, ly, tt) for lx, ly, tt in tiles],
    )
    await db.execute(
        "INSERT OR IGNORE INTO village_entrances (village_id, entry_x, entry_y, world_x, world_y) "
        "VALUES (?, ?, ?, ?, ?)",
        (village_id, entry[0], entry[1], world_x, world_y),
    )

    # Generate house interiors for each house in the village
    for hx, hy, hw, hh, door_x, door_y in houses:
        hcursor = await db.execute(
            "INSERT INTO houses (village_id, width, height) VALUES (?, 1, 1)", (village_id,)
        )
        house_id = hcursor.lastrowid
        hW, hH, htiles, hentry = await asyncio.to_thread(
            _generate_house_interior, house_id, seed, village_id, door_x, door_y
        )
        await db.execute(
            "UPDATE houses SET width = ?, height = ? WHERE house_id = ?",
            (hW, hH, house_id),
        )
        await db.executemany(
            "INSERT OR IGNORE INTO house_tiles (house_id, local_x, local_y, tile_type) "
            "VALUES (?, ?, ?, ?)",
            [(house_id, lx, ly, tt) for lx, ly, tt in htiles],
        )
        await db.execute(
            "INSERT OR IGNORE INTO house_entrances "
            "(house_id, entry_x, entry_y, village_id, village_x, village_y) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (house_id, hentry[0], hentry[1], village_id, door_x, door_y),
        )

    return village_id, entry[0], entry[1]


async def get_or_create_house(
    village_id: int, village_x: int, village_y: int, db,
) -> tuple[int, int, int] | None:
    """Return (house_id, entry_x, entry_y) for a house whose vil_door is at (village_x, village_y).

    Returns None if no house is registered at that position.
    """
    row = await db.fetch_one(
        "SELECT house_id, entry_x, entry_y FROM house_entrances "
        "WHERE village_id = ? AND village_x = ? AND village_y = ?",
        (village_id, village_x, village_y),
    )
    if row:
        return row["house_id"], row["entry_x"], row["entry_y"]
    return None


async def load_village_viewport(
    village_id: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    """9×9 viewport within a village, centred on (center_x, center_y)."""
    half = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM village_tiles "
        "WHERE village_id = ? AND local_x >= ? AND local_x <= ? AND local_y >= ? AND local_y <= ?",
        (village_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map: dict[tuple[int, int], str] = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row_tiles: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            tile_type = tile_map.get((cx, cy), "void")
            row_tiles.append(TileData(terrain=tile_type, world_x=cx, world_y=cy))
        grid.append(row_tiles)

    return grid


async def load_village_single_tile(
    village_id: int, local_x: int, local_y: int, db,
) -> TileData:
    """Single tile lookup inside a village."""
    row = await db.fetch_one(
        "SELECT tile_type FROM village_tiles "
        "WHERE village_id = ? AND local_x = ? AND local_y = ?",
        (village_id, local_x, local_y),
    )
    tile_type = row["tile_type"] if row else "void"
    return TileData(terrain=tile_type, world_x=local_x, world_y=local_y)


async def load_house_viewport(
    house_id: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    """9×9 viewport within a house, centred on (center_x, center_y)."""
    half = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM house_tiles "
        "WHERE house_id = ? AND local_x >= ? AND local_x <= ? AND local_y >= ? AND local_y <= ?",
        (house_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map: dict[tuple[int, int], str] = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row_tiles: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            tile_type = tile_map.get((cx, cy), "void")
            row_tiles.append(TileData(terrain=tile_type, world_x=cx, world_y=cy))
        grid.append(row_tiles)

    return grid


async def load_house_single_tile(
    house_id: int, local_x: int, local_y: int, db,
) -> TileData:
    """Single tile lookup inside a house."""
    row = await db.fetch_one(
        "SELECT tile_type FROM house_tiles "
        "WHERE house_id = ? AND local_x = ? AND local_y = ?",
        (house_id, local_x, local_y),
    )
    tile_type = row["tile_type"] if row else "void"
    return TileData(terrain=tile_type, world_x=local_x, world_y=local_y)
