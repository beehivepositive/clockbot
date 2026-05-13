"""Sky temple system — interior generation, gear puzzle, portal management."""
from __future__ import annotations

from dwarf_explorer.world.generator import TileData
from dwarf_explorer.config import VIEWPORT_SIZE, VIEWPORT_CENTER

TEMPLE_SIZE = 11
TEMPLE_ENTRY_X = 5
TEMPLE_ENTRY_Y = 8   # player spawns one tile inside the entrance

# Gear slots in each outer temple.
# Large gears are 2×2 tiles anchored at (slot_x, slot_y).
# CW/CCW alternates by slot index (even = CW, odd = CCW) so adjacent gears mesh.
OUTER_GEAR_SLOTS: list[tuple[int, int, str]] = [
    (2, 2, "small_gear"),   # index 0 — CW,  top-left corner
    (7, 2, "large_gear"),   # index 1 — CCW, top-right  (covers 7-8, 2-3)
    (2, 7, "large_gear"),   # index 2 — CW,  bottom-left (covers 2-3, 7-8)
    (8, 8, "small_gear"),   # index 3 — CCW, bottom-right corner
]

# Is this gear slot clockwise? (derived from index parity at module load)
GEAR_SLOT_IS_CW: dict[tuple[int, int], bool] = {
    (ax, ay): (idx % 2 == 0)
    for idx, (ax, ay, _) in enumerate(OUTER_GEAR_SLOTS)
}

# All gear-slot tile-type names (used by game_view to detect interact targets)
GEAR_SLOT_TERRAIN: frozenset[str] = frozenset({
    "gear_slot_s_empty", "gear_slot_l_empty",
    "gear_slot_s_cw", "gear_slot_s_ccw",
    "gear_slot_l_cw_tl",  "gear_slot_l_cw_tr",  "gear_slot_l_cw_bl",  "gear_slot_l_cw_br",
    "gear_slot_l_ccw_tl", "gear_slot_l_ccw_tr", "gear_slot_l_ccw_bl", "gear_slot_l_ccw_br",
})

OUTER_ALTAR_POS    = (5, 5)
OUTER_ENTRANCE_POS = (5, 9)

MAIN_PORTAL_POS       = (5, 5)
MAIN_RUNE_POSITIONS   = [(5, 4), (4, 5), (6, 5), (5, 6)]
MAIN_PILLAR_POSITIONS = [(2, 2), (8, 2), (2, 8), (8, 8)]
MAIN_ENTRANCE_POS     = (5, 9)

# Quadrant offsets for a 2×2 large gear: (dx, dy) → quadrant name
_LARGE_GEAR_QUADS = {(0, 0): "tl", (1, 0): "tr", (0, 1): "bl", (1, 1): "br"}


def _large_gear_tiles(ax: int, ay: int) -> list[tuple[int, int, str]]:
    """Return [(x, y, quad), ...] for all 4 tiles of a large gear anchored at (ax, ay)."""
    return [(ax + dx, ay + dy, q) for (dx, dy), q in _LARGE_GEAR_QUADS.items()]


def find_gear_slot_anchor(local_x: int, local_y: int) -> tuple[int, int] | None:
    """Return the anchor (slot_x, slot_y) if (local_x, local_y) is any part of a gear slot.

    Handles single-tile small gears and 2×2 large gears.
    Returns None if the position is not a gear slot.
    """
    for ax, ay, gear_type in OUTER_GEAR_SLOTS:
        if gear_type == "large_gear":
            if (local_x, local_y) in {(ax, ay), (ax + 1, ay), (ax, ay + 1), (ax + 1, ay + 1)}:
                return (ax, ay)
        else:
            if (local_x, local_y) == (ax, ay):
                return (ax, ay)
    return None


GEAR_MACHINE_POS = (5, 1)   # centre of north interior row — the interactable machine panel

def _make_outer_temple_tiles() -> list[tuple[int, int, str]]:
    """Generate the static tile layout for an outer (puzzle) temple."""
    tiles: dict[tuple[int, int], str] = {}
    for y in range(TEMPLE_SIZE):
        for x in range(TEMPLE_SIZE):
            if x == 0 or x == TEMPLE_SIZE - 1 or y == 0 or y == TEMPLE_SIZE - 1:
                tiles[(x, y)] = "temple_wall"
            else:
                tiles[(x, y)] = "temple_floor"

    # Entrance (south wall opening)
    ex, ey = OUTER_ENTRANCE_POS
    tiles[(ex, ey)] = "temple_entrance"

    # Gear machine panel on the north interior wall (walkable — opens machine UI)
    mx, my = GEAR_MACHINE_POS
    tiles[(mx, my)] = "gear_machine"

    # Altar centre
    ax, ay = OUTER_ALTAR_POS
    tiles[(ax, ay)] = "temple_altar"

    # Rune stones flanking the altar
    tiles[(ax - 2, ay)] = "temple_rune"
    tiles[(ax + 2, ay)] = "temple_rune"

    return [(x, y, t) for (x, y), t in tiles.items()]


def _make_main_temple_tiles() -> list[tuple[int, int, str]]:
    """Generate the static tile layout for the main (portal) temple."""
    tiles: dict[tuple[int, int], str] = {}
    for y in range(TEMPLE_SIZE):
        for x in range(TEMPLE_SIZE):
            if x == 0 or x == TEMPLE_SIZE - 1 or y == 0 or y == TEMPLE_SIZE - 1:
                tiles[(x, y)] = "temple_wall"
            else:
                tiles[(x, y)] = "temple_floor"
    ex, ey = MAIN_ENTRANCE_POS
    tiles[(ex, ey)] = "temple_entrance"
    # Portal (locked by default — unlocked dynamically)
    px, py = MAIN_PORTAL_POS
    tiles[(px, py)] = "temple_portal_locked"
    # Rune stones
    for rx, ry in MAIN_RUNE_POSITIONS:
        tiles[(rx, ry)] = "temple_rune"
    # Pillars
    for ppx, ppy in MAIN_PILLAR_POSITIONS:
        tiles[(ppx, ppy)] = "temple_pillar"
    return [(x, y, t) for (x, y), t in tiles.items()]


_OLD_GEAR_SLOT_TILES = frozenset({
    "gear_slot_s_empty", "gear_slot_l_empty",
    "gear_slot_s_cw", "gear_slot_s_ccw",
    "gear_slot_l_cw_tl",  "gear_slot_l_cw_tr",  "gear_slot_l_cw_bl",  "gear_slot_l_cw_br",
    "gear_slot_l_ccw_tl", "gear_slot_l_ccw_tr", "gear_slot_l_ccw_bl", "gear_slot_l_ccw_br",
})


async def get_or_create_outer_temple(db, world_x: int, world_y: int) -> int:
    """Return temple_id for the outer temple at (world_x, world_y), creating it if needed.

    Also migrates legacy temples that still have floor gear-slot tiles by replacing
    them with the new gear_machine panel layout.
    """
    row = await db.fetch_one(
        "SELECT id FROM sky_temples WHERE world_x=? AND world_y=? AND temple_type='outer'",
        (world_x, world_y),
    )
    if row:
        temple_id = row["id"]
        # Migrate old layout: remove any legacy gear-slot floor tiles and add the machine panel
        legacy = await db.fetch_all(
            "SELECT local_x, local_y FROM temple_tiles WHERE temple_id=? AND tile_type IN ({})".format(
                ",".join("?" * len(_OLD_GEAR_SLOT_TILES))
            ),
            (temple_id, *_OLD_GEAR_SLOT_TILES),
        )
        if legacy:
            # Delete old gear-slot tiles
            await db.execute(
                "DELETE FROM temple_tiles WHERE temple_id=? AND tile_type IN ({})".format(
                    ",".join("?" * len(_OLD_GEAR_SLOT_TILES))
                ),
                (temple_id, *_OLD_GEAR_SLOT_TILES),
            )
            # Place gear_machine tile (upsert)
            mx, my = GEAR_MACHINE_POS
            await db.execute(
                "INSERT OR REPLACE INTO temple_tiles (temple_id, local_x, local_y, tile_type) VALUES (?,?,?,'gear_machine')",
                (temple_id, mx, my),
            )
        return temple_id

    cur = await db.execute(
        "INSERT INTO sky_temples (world_x, world_y, temple_type) VALUES (?, ?, 'outer')",
        (world_x, world_y),
    )
    temple_id = cur.lastrowid
    tile_list = _make_outer_temple_tiles()
    await db.executemany(
        "INSERT OR IGNORE INTO temple_tiles (temple_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        [(temple_id, x, y, t) for x, y, t in tile_list],
    )
    # One gear_slot row per anchor position (small or large)
    await db.executemany(
        "INSERT OR IGNORE INTO temple_gear_slots (temple_id, slot_x, slot_y, required_gear) VALUES (?,?,?,?)",
        [(temple_id, sx, sy, req) for sx, sy, req in OUTER_GEAR_SLOTS],
    )
    return temple_id


async def get_or_create_main_temple(db, world_x: int, world_y: int, world_seed: int) -> tuple[int, int, int]:
    """Return (temple_id, entry_x, entry_y) for the main temple, creating if needed."""
    row = await db.fetch_one(
        "SELECT id, sky_id FROM sky_temples WHERE world_x=? AND world_y=? AND temple_type='main'",
        (world_x, world_y),
    )
    if row:
        return row["id"], TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y
    cur = await db.execute(
        "INSERT INTO sky_temples (world_x, world_y, temple_type) VALUES (?, ?, 'main')",
        (world_x, world_y),
    )
    temple_id = cur.lastrowid
    tile_list = _make_main_temple_tiles()
    await db.executemany(
        "INSERT OR IGNORE INTO temple_tiles (temple_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        [(temple_id, x, y, t) for x, y, t in tile_list],
    )
    return temple_id, TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y


def _overlay_gear_slots(
    tile_map: dict[tuple[int, int], str],
    slot_rows: list,
) -> None:
    """Overlay dynamic gear-slot states onto tile_map in-place."""
    for sr in slot_rows:
        ax, ay = sr["slot_x"], sr["slot_y"]
        req    = sr["required_gear"]
        filled = bool(sr["is_filled"])
        is_cw  = GEAR_SLOT_IS_CW.get((ax, ay), True)
        dir_s  = "cw" if is_cw else "ccw"

        if req == "small_gear":
            tile_map[(ax, ay)] = f"gear_slot_s_{dir_s}" if filled else "gear_slot_s_empty"
        else:  # large_gear — 2×2 block
            for gx, gy, quad in _large_gear_tiles(ax, ay):
                tile_map[(gx, gy)] = f"gear_slot_l_{dir_s}_{quad}" if filled else "gear_slot_l_empty"


async def load_temple_viewport(
    temple_id: int, center_x: int, center_y: int, db, is_main: bool = False
) -> list[list[TileData]]:
    """Load a 9×9 viewport centred at (center_x, center_y) inside the temple."""
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM temple_tiles"
        " WHERE temple_id=? AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (temple_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    if is_main:
        # Main temple: overlay portal open/locked based on puzzle completion
        all_solved = await are_all_outer_temples_solved(db)
        px, py = MAIN_PORTAL_POS
        tile_map[(px, py)] = "temple_portal_open" if all_solved else "temple_portal_locked"

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row_tiles: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row_tiles.append(TileData(
                terrain=tile_map.get((cx, cy), "temple_wall"),
                world_x=cx, world_y=cy,
            ))
        grid.append(row_tiles)
    return grid


async def load_temple_single_tile(
    temple_id: int, local_x: int, local_y: int, db, is_main: bool = False
) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM temple_tiles WHERE temple_id=? AND local_x=? AND local_y=?",
        (temple_id, local_x, local_y),
    )
    tile_type = row["tile_type"] if row else "temple_wall"

    if is_main and tile_type in ("temple_portal_locked", "temple_portal_open"):
        all_solved = await are_all_outer_temples_solved(db)
        tile_type = "temple_portal_open" if all_solved else "temple_portal_locked"

    return TileData(terrain=tile_type, world_x=local_x, world_y=local_y)


async def fill_gear_slot(db, temple_id: int, slot_x: int, slot_y: int, user_id: int) -> str | None:
    """Fill a gear slot (by anchor position).

    Returns the required_gear type on success, None if slot not found or already filled.
    """
    row = await db.fetch_one(
        "SELECT required_gear, is_filled FROM temple_gear_slots"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (temple_id, slot_x, slot_y),
    )
    if not row or row["is_filled"]:
        return None
    await db.execute(
        "UPDATE temple_gear_slots SET is_filled=1, filled_by=?"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (user_id, temple_id, slot_x, slot_y),
    )
    return row["required_gear"]


async def remove_gear_slot(db, temple_id: int, slot_x: int, slot_y: int) -> str | None:
    """Remove a gear from a filled slot (by anchor position).

    Returns gear type removed, or None if not filled.
    """
    row = await db.fetch_one(
        "SELECT required_gear, is_filled FROM temple_gear_slots"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (temple_id, slot_x, slot_y),
    )
    if not row or not row["is_filled"]:
        return None
    await db.execute(
        "UPDATE temple_gear_slots SET is_filled=0, filled_by=NULL"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (temple_id, slot_x, slot_y),
    )
    return row["required_gear"]


async def is_outer_temple_solved(db, temple_id: int) -> bool:
    """Return True if all gear slots in this outer temple are filled."""
    row = await db.fetch_one(
        "SELECT COUNT(*) AS total, SUM(is_filled) AS filled FROM temple_gear_slots WHERE temple_id=?",
        (temple_id,),
    )
    if not row or not row["total"]:
        return False
    return row["total"] == row["filled"]


async def are_all_outer_temples_solved(db) -> bool:
    """Return True if every outer temple has its puzzle completed."""
    temples = await db.fetch_all(
        "SELECT id FROM sky_temples WHERE temple_type='outer'"
    )
    if not temples:
        return False
    for t in temples:
        if not await is_outer_temple_solved(db, t["id"]):
            return False
    return True


async def get_main_temple_sky_id(db, temple_id: int, world_seed: int) -> int:
    """Get or create the sky biome linked to the main temple."""
    row = await db.fetch_one("SELECT sky_id FROM sky_temples WHERE id=?", (temple_id,))
    if row and row["sky_id"]:
        return row["sky_id"]
    # Create new sky biome
    cur = await db.execute("INSERT INTO sky_biomes (width, height) VALUES (1, 1)")
    sky_id = cur.lastrowid
    await db.execute("UPDATE sky_temples SET sky_id=? WHERE id=?", (sky_id, temple_id))
    from dwarf_explorer.world.sky import create_sky_biome
    await create_sky_biome(sky_id, world_seed, db)
    return sky_id
