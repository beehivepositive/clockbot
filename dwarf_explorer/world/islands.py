"""Small island interior generation for high-seas exploration.

Islands are procedurally generated 11×11 grids stored in the DB.
Terrain types used:
  island_void   — ocean surrounding the island (impassable)
  island_sand   — beach ring
  island_grass  — interior clearing
  island_forest — dense interior
  island_chest  — treasure chest (loot once per island)
  island_dock   — dock tile to return to the boat
"""
from __future__ import annotations

import asyncio
import math
import random as _rng_module


ISLAND_SIZE = 11   # square grid
ISLAND_WALKABLE = {"island_sand", "island_grass", "island_forest",
                   "island_chest", "island_dock"}


def _generate_island_tiles(
    island_id: int, ocean_x: int, ocean_y: int,
) -> list[tuple[int, int, str]]:
    """Return list of (local_x, local_y, tile_type) for an 11×11 island."""
    rng = _rng_module.Random(island_id ^ (ocean_x * 1_234_567) ^ (ocean_y * 7_654_321))
    W = H = ISLAND_SIZE
    cx, cy = W // 2, H // 2

    grid: list[list[str]] = [["island_void"] * W for _ in range(H)]

    # Irregular island shape: ellipse radius with per-direction noise
    radii = [2.5 + rng.uniform(-0.6, 0.6) for _ in range(8)]

    def _radius_at(angle_idx: float) -> float:
        lo = radii[int(angle_idx) % 8]
        hi = radii[(int(angle_idx) + 1) % 8]
        t = angle_idx - int(angle_idx)
        return lo + (hi - lo) * t

    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            if dist < 0.01:
                grid[y][x] = "island_grass"
                continue
            angle = math.atan2(dy, dx)
            sector = (angle / (2 * math.pi)) * 8
            r = _radius_at(sector)
            if dist < r - 1.2:
                grid[y][x] = "island_forest"
            elif dist < r:
                grid[y][x] = "island_grass"
            elif dist < r + 1.2:
                grid[y][x] = "island_sand"
            # else remains island_void

    # Place chest in interior (forest or grass)
    candidates = [
        (x, y) for y in range(1, H-1) for x in range(1, W-1)
        if grid[y][x] in ("island_forest", "island_grass") and (x, y) != (cx, cy)
    ]
    if candidates:
        chest_x, chest_y = rng.choice(candidates)
        grid[chest_y][chest_x] = "island_chest"

    # Place dock on the south beach edge
    dock_x = cx
    for y in range(H - 1, -1, -1):
        if grid[y][dock_x] == "island_sand":
            grid[y][dock_x] = "island_dock"
            break
    else:
        # Fallback: bottom edge
        if grid[H - 2][dock_x] != "island_void":
            grid[H - 2][dock_x] = "island_dock"
        else:
            grid[H - 3][dock_x] = "island_dock"

    return [(x, y, grid[y][x]) for y in range(H) for x in range(W)]


def _find_dock_pos(tiles: list[tuple[int, int, str]]) -> tuple[int, int]:
    for lx, ly, tt in tiles:
        if tt == "island_dock":
            return lx, ly
    return ISLAND_SIZE // 2, ISLAND_SIZE // 2


async def get_or_create_island_data(
    db, ocean_x: int, ocean_y: int, seed: int,
) -> tuple[int, list[tuple[int, int, str]], tuple[int, int]]:
    """Return (island_id, tiles, (dock_x, dock_y)). Creates DB record if needed."""
    from dwarf_explorer.database.repositories import (
        get_or_create_island, store_island_tiles, get_island_tiles,
    )
    island_id = await get_or_create_island(db, ocean_x, ocean_y)
    existing = await get_island_tiles(db, island_id)
    if existing:
        tiles = existing
    else:
        tiles = await asyncio.to_thread(
            _generate_island_tiles, island_id, ocean_x, ocean_y
        )
        await store_island_tiles(db, island_id, tiles)
    dock_pos = _find_dock_pos(tiles)
    return island_id, tiles, dock_pos


def load_island_viewport(
    tiles: list[tuple[int, int, str]],
    player_x: int,
    player_y: int,
    size: int = 9,
) -> list[list]:
    """Return a size×size list of TileData rows centred on (player_x, player_y)."""
    from dwarf_explorer.world.generator import TileData

    tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
    half = size // 2
    rows: list[list] = []
    for dy in range(-half, half + 1):
        row: list = []
        for dx in range(-half, half + 1):
            nx, ny = player_x + dx, player_y + dy
            terrain = tile_map.get((nx, ny), "island_void")
            row.append(TileData(terrain=terrain, world_x=nx, world_y=ny))
        rows.append(row)
    return rows
