"""Dwarven Hall interior generator.

An ancient underground dwarven hall accessed by bombing a cracked mountain
wall (cracked_mountain_wall structure → dwarven_entrance structure).

Reuses the villages / village_tiles / village_entrances DB tables with
village_type = "dwarven_hall" on the player record while inside.
"""
from __future__ import annotations

import asyncio

from dwarf_explorer.config import DWARVEN_HALL_W, DWARVEN_HALL_H

# ---------------------------------------------------------------------------
# Layout encoding
# ---------------------------------------------------------------------------
# W=18, H=14.  Each character maps to a tile type via _CHAR_MAP.
# Entry/exit tile is 'E' at position (9, 12) — second row from bottom, centre.
#
#        0         1
#        012345678901234567
# y= 0:  WWWWWWWWWWWWWWWWWW
# y= 1:  WFFPFFFFFFFFFFPFFW   pillars at x=3, x=14
# y= 2:  WFFFFGFFFFFGFFFFFW   forges at x=5, x=11
# y= 3:  WFFFFFFFFFFFFFFFFW
# y= 4:  WFPFFFFFAFFFFFFPFW   altar at x=8; pillars at x=2, x=15
# y= 5:  WFFFFFFFFFFFFFFFFW
# y= 6:  WFFFFFFFLFFFFFFFFW   gate at x=8 (sealed passage to deeper hall)
# y= 7:  WFFFFFFFFFFFFFFFFW
# y= 8:  WFPFFFFFBFFFFFFPFW   bell at x=8; pillars at x=2, x=15
# y= 9:  WFFFFCFFFFFFCFFFFW   chests at x=5, x=12
# y=10:  WFFFFFFFFFFFFFFFFW
# y=11:  WFFFFFFFFFFFFFFFFW
# y=12:  WFFFFFFFFEFFFFFFFW   exit at x=9 (player spawns here on entry)
# y=13:  WWWWWWWWWWWWWWWWWW

_HALL_ROWS: tuple[str, ...] = (
    "WWWWWWWWWWWWWWWWWW",  # y= 0
    "WFFPFFFFFFFFFFPFFW",  # y= 1
    "WFFFFGFFFFFGFFFFFW",  # y= 2
    "WFFFFFFFFFFFFFFFFW",  # y= 3
    "WFPFFFFFAFFFFFFPFW",  # y= 4
    "WFFFFFFFFFFFFFFFFW",  # y= 5
    "WFFFFFFFLFFFFFFFFW",  # y= 6
    "WFFFFFFFFFFFFFFFFW",  # y= 7
    "WFPFFFFFBFFFFFFPFW",  # y= 8
    "WFFFFCFFFFFFCFFFFW",  # y= 9
    "WFFFFFFFFFFFFFFFFW",  # y=10
    "WFFFFFFFFFFFFFFFFW",  # y=11
    "WFFFFFFFFEFFFFFFFW",  # y=12
    "WWWWWWWWWWWWWWWWWW",  # y=13
)

_CHAR_MAP: dict[str, str] = {
    "W": "dw_wall",
    "F": "dw_floor",
    "P": "dw_pillar",
    "G": "dw_forge",
    "A": "dw_altar",
    "L": "dw_gate",
    "C": "dw_chest",
    "B": "dw_bell_tower",
    "E": "dw_exit",
}

# Entry is the exit tile position (player spawns here when entering)
_ENTRY_X = 9
_ENTRY_Y = 12


# ---------------------------------------------------------------------------
# Interior generator
# ---------------------------------------------------------------------------

def _generate_dwarven_hall_interior() -> tuple[int, int, list[tuple[int, int, str]], tuple[int, int]]:
    """Return (W, H, tiles, entry_pos) for a new dwarven hall interior."""
    assert len(_HALL_ROWS) == DWARVEN_HALL_H, "HALL_ROWS height mismatch"
    assert all(len(r) == DWARVEN_HALL_W for r in _HALL_ROWS), "HALL_ROWS width mismatch"

    tiles: list[tuple[int, int, str]] = []
    for y, row in enumerate(_HALL_ROWS):
        for x, ch in enumerate(row):
            tile_type = _CHAR_MAP.get(ch, "dw_wall")
            tiles.append((x, y, tile_type))

    return DWARVEN_HALL_W, DWARVEN_HALL_H, tiles, (_ENTRY_X, _ENTRY_Y)


# ---------------------------------------------------------------------------
# DB accessor (async — mirrors get_or_create_ruins)
# ---------------------------------------------------------------------------

async def get_or_create_dwarven_hall(
    world_x: int, world_y: int, db,
) -> tuple[int, int, int]:
    """Return (hall_village_id, entry_local_x, entry_local_y).

    The hall is stored using the villages / village_tiles / village_entrances
    tables (same as villages and ruins) so we get the viewport loader for free.
    village_type = 'dwarven_hall' tags the player row while inside.
    """
    row = await db.fetch_one(
        "SELECT village_id, entry_x, entry_y FROM village_entrances "
        "WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        return row["village_id"], row["entry_x"], row["entry_y"]

    cursor = await db.execute("INSERT INTO villages (width, height) VALUES (1, 1)")
    hall_id = cursor.lastrowid

    W, H, tiles, entry = await asyncio.to_thread(_generate_dwarven_hall_interior)

    await db.execute(
        "UPDATE villages SET width = ?, height = ? WHERE village_id = ?",
        (W, H, hall_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO village_tiles (village_id, local_x, local_y, tile_type) "
        "VALUES (?, ?, ?, ?)",
        [(hall_id, lx, ly, tt) for lx, ly, tt in tiles],
    )
    await db.execute(
        "INSERT OR IGNORE INTO village_entrances "
        "(village_id, entry_x, entry_y, world_x, world_y) "
        "VALUES (?, ?, ?, ?, ?)",
        (hall_id, entry[0], entry[1], world_x, world_y),
    )
    return hall_id, entry[0], entry[1]
