from __future__ import annotations

from dwarf_explorer.world.generator import TileData

HOUSE_WIDTH = 7
HOUSE_HEIGHT = 7
HOUSE_SPAWN_X = 3   # center x of the interior
HOUSE_SPAWN_Y = 5   # one tile above the door (door is at y=6)


def _default_tiles() -> list[tuple[int, int, str]]:
    """Generate default 7×7 house interior tiles."""
    tiles = []
    for y in range(HOUSE_HEIGHT):
        for x in range(HOUSE_WIDTH):
            if y == 0 or x == 0 or x == HOUSE_WIDTH - 1:
                tile_type = "b_wall"
            elif y == HOUSE_HEIGHT - 1:
                # Bottom wall: door at center, walls elsewhere
                tile_type = "b_door" if x == HOUSE_WIDTH // 2 else "b_wall"
            else:
                tile_type = "b_floor_wood"
            tiles.append((x, y, tile_type))
    return tiles


async def create_player_house(
    db,
    owner_id: int,
    loc_x: int,
    loc_y: int,
    is_cave: bool,
    loc_cave_id: int | None,
) -> int:
    """Create a new player house record and populate its default tiles. Returns house_id."""
    cursor = await db.execute(
        "INSERT INTO player_houses (owner_id, is_cave, loc_cave_id, loc_x, loc_y)"
        " VALUES (?, ?, ?, ?, ?)",
        (owner_id, int(is_cave), loc_cave_id, loc_x, loc_y),
    )
    house_id = cursor.lastrowid
    await db.executemany(
        "INSERT OR IGNORE INTO player_house_tiles (house_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(house_id, lx, ly, tt) for lx, ly, tt in _default_tiles()],
    )
    return house_id


async def get_player_house_at(
    db,
    loc_x: int,
    loc_y: int,
    is_cave: bool,
    loc_cave_id: int | None,
) -> int | None:
    """Return house_id if a player house exists at this world/cave location, else None."""
    if is_cave:
        row = await db.fetch_one(
            "SELECT house_id FROM player_houses"
            " WHERE loc_x=? AND loc_y=? AND is_cave=1 AND loc_cave_id=?",
            (loc_x, loc_y, loc_cave_id),
        )
    else:
        row = await db.fetch_one(
            "SELECT house_id FROM player_houses"
            " WHERE loc_x=? AND loc_y=? AND is_cave=0",
            (loc_x, loc_y),
        )
    return row["house_id"] if row else None


async def get_player_house_owner(db, house_id: int) -> int | None:
    """Return owner_id for a player house, or None if not found."""
    row = await db.fetch_one(
        "SELECT owner_id FROM player_houses WHERE house_id=?", (house_id,)
    )
    return row["owner_id"] if row else None


async def delete_player_house(db, house_id: int) -> tuple[int, int, bool, int | None]:
    """Delete a player house and all its tiles.

    Returns (loc_x, loc_y, is_cave, loc_cave_id) so the caller can clean up
    the overworld/cave tile that was pointing at it.
    """
    row = await db.fetch_one(
        "SELECT loc_x, loc_y, is_cave, loc_cave_id FROM player_houses WHERE house_id=?",
        (house_id,),
    )
    if not row:
        return 0, 0, False, None
    loc_x = row["loc_x"]
    loc_y = row["loc_y"]
    is_cave = bool(row["is_cave"])
    loc_cave_id = row["loc_cave_id"]
    await db.execute("DELETE FROM player_house_tiles WHERE house_id=?", (house_id,))
    await db.execute("DELETE FROM player_houses WHERE house_id=?", (house_id,))
    return loc_x, loc_y, is_cave, loc_cave_id


async def load_player_house_viewport(
    house_id: int, center_x: int, center_y: int, db
) -> list[list[TileData]]:
    """Load a 9×9 viewport centred on (center_x, center_y) inside a player house."""
    from dwarf_explorer.config import VIEWPORT_SIZE, VIEWPORT_CENTER
    half = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM player_house_tiles"
        " WHERE house_id=? AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (house_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}
    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row_data: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row_data.append(TileData(terrain=tile_map.get((cx, cy), "void"),
                                     world_x=cx, world_y=cy))
        grid.append(row_data)
    return grid


async def load_player_house_single_tile(
    house_id: int, local_x: int, local_y: int, db
) -> TileData:
    """Load a single tile from a player house by local coordinates."""
    row = await db.fetch_one(
        "SELECT tile_type FROM player_house_tiles"
        " WHERE house_id=? AND local_x=? AND local_y=?",
        (house_id, local_x, local_y),
    )
    return TileData(terrain=row["tile_type"] if row else "void",
                    world_x=local_x, world_y=local_y)


async def set_player_house_tile(
    house_id: int, local_x: int, local_y: int, tile_type: str, db
) -> None:
    """Set (insert or replace) a tile in a player house."""
    await db.execute(
        "INSERT OR REPLACE INTO player_house_tiles"
        " (house_id, local_x, local_y, tile_type) VALUES (?, ?, ?, ?)",
        (house_id, local_x, local_y, tile_type),
    )
