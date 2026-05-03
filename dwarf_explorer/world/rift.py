"""Temporal Rift pocket dimension — layout generation and DB persistence.

Layout (21 × 26 tiles):
  y=0          : rift_entrance at (10,0), rest rift_wall
  y=1..10      : 3-wide corridor, x∈[9,10,11] = rift_floor
  y=11         : widened arch, x∈[7..13] = rift_floor (transition to boss room)
  y=12..24     : boss room, x∈[2..18] = rift_floor
  y=25         : all rift_wall (south wall)

Chronolite deposits (minable after boss defeated):
  8 positions scattered in the boss room perimeter.

Boss (temporal_echo) spawns at (10, 19) on first entry.
Boss trigger zone: any rift_floor tile with local_y >= 12.
"""
from __future__ import annotations

RIFT_W = 21
RIFT_H = 26

RIFT_ENTRANCE_X = 10  # local_x of rift_entrance tile
RIFT_ENTRANCE_Y = 0

RIFT_SPAWN_X = 10     # where player appears when entering the rift
RIFT_SPAWN_Y = 1      # first corridor tile

RIFT_BOSS_Y   = 12    # y >= this triggers the boss on first entry
RIFT_BOSS_SPAWN_X = 10
RIFT_BOSS_SPAWN_Y = 19

_DEPOSIT_POSITIONS: list[tuple[int, int]] = [
    (4, 13), (8, 13), (12, 13), (16, 13),
    (3, 19), (17, 19),
    (4, 24), (16, 24),
]


def _build_tile_map() -> dict[tuple[int, int], str]:
    """Return a dict (lx, ly) → tile_type for the entire rift."""
    tiles: dict[tuple[int, int], str] = {}

    # Fill everything with rift_wall
    for y in range(RIFT_H):
        for x in range(RIFT_W):
            tiles[(x, y)] = "rift_wall"

    # Entrance portal at top of corridor
    tiles[(RIFT_ENTRANCE_X, RIFT_ENTRANCE_Y)] = "rift_entrance"

    # Corridor: 3 wide, y=1..10
    for y in range(1, 11):
        for x in (9, 10, 11):
            tiles[(x, y)] = "rift_floor"

    # Widened arch at y=11 (corridor→boss room transition)
    for x in range(7, 14):
        tiles[(x, 11)] = "rift_floor"

    # Boss room: x=2..18, y=12..24
    for y in range(12, 25):
        for x in range(2, 19):
            tiles[(x, y)] = "rift_floor"

    # Chronolite deposits (overwrite floor tiles in boss room)
    for dx, dy in _DEPOSIT_POSITIONS:
        if (dx, dy) in tiles and tiles[(dx, dy)] == "rift_floor":
            tiles[(dx, dy)] = "rift_deposit"

    return tiles


async def create_rift(world_x: int, world_y: int, db) -> tuple[int, int, int]:
    """Generate and persist a rift linked to (world_x, world_y).

    Returns (cave_id, entrance_local_x, entrance_local_y).
    Idempotent: if a rift already exists for this world tile, returns it.
    """
    # Check for existing rift entrance at this world position
    existing = await db.fetch_one(
        "SELECT cave_id, local_x, local_y FROM cave_entrances WHERE world_x=? AND world_y=?",
        (world_x, world_y),
    )
    if existing:
        return existing["cave_id"], existing["local_x"], existing["local_y"]

    # Create caves row for the rift
    cur = await db.execute(
        "INSERT INTO caves (width, height, cave_level, cave_type, boss_defeated)"
        " VALUES (?, ?, 0, 'rift', 0)",
        (RIFT_W, RIFT_H),
    )
    # Fetch the new cave_id
    cave_row = await db.fetch_one("SELECT last_insert_rowid() AS id")
    cave_id = cave_row["id"]

    # Insert all tiles
    tile_map = _build_tile_map()
    tile_rows = [(cave_id, x, y, t) for (x, y), t in tile_map.items()]
    await db.executemany(
        "INSERT OR IGNORE INTO cave_tiles (cave_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        tile_rows,
    )

    # Create entrance record linking world position → rift entrance tile
    await db.execute(
        "INSERT OR IGNORE INTO cave_entrances (cave_id, local_x, local_y, world_x, world_y)"
        " VALUES (?, ?, ?, ?, ?)",
        (cave_id, RIFT_ENTRANCE_X, RIFT_ENTRANCE_Y, world_x, world_y),
    )

    return cave_id, RIFT_ENTRANCE_X, RIFT_ENTRANCE_Y


async def get_rift_for_sundial(world_x: int, world_y: int, db) -> tuple[int, int, int] | None:
    """Return (cave_id, entrance_x, entrance_y) if a rift exists at (world_x, world_y)."""
    row = await db.fetch_one(
        "SELECT ce.cave_id, ce.local_x, ce.local_y"
        " FROM cave_entrances ce"
        " JOIN caves c ON c.cave_id = ce.cave_id"
        " WHERE ce.world_x=? AND ce.world_y=? AND c.cave_type='rift'",
        (world_x, world_y),
    )
    if row:
        return row["cave_id"], row["local_x"], row["local_y"]
    return None
