"""Hermit's Hut interior — 2-floor irregular building with hermit NPC."""
from __future__ import annotations

from dwarf_explorer.config import VIEWPORT_CENTER
from dwarf_explorer.world.generator import TileData

# ── Hut dimensions ────────────────────────────────────────────────────────────
HUT_W = 9
HUT_H = 9
HUT_NUM_FLOORS = 2

# Floor 1 — player spawn when entering from the forest
HUT_ENTRY_X = 4
HUT_ENTRY_Y = 6    # one step in from the door tile

# Floor 1 door tile (stepping onto it exits to forest)
HUT_DOOR_X = 4
HUT_DOOR_Y = 7

# Floor 1 stair-up position
HUT_F1_STAIR_X = 2
HUT_F1_STAIR_Y = 4

# Floor 2 stair-down position
HUT_F2_STAIR_X = 6
HUT_F2_STAIR_Y = 4

# Landing positions when changing floors
HUT_F2_ENTRY_X = 5    # appear here on floor 2 after going up
HUT_F2_ENTRY_Y = 4
HUT_F1_RETURN_X = 3   # appear here on floor 1 after going down
HUT_F1_RETURN_Y = 4

# Hermit NPC tile on floor 1
HUT_HERMIT_X = 2
HUT_HERMIT_Y = 2

# ── Tile shorthand aliases ────────────────────────────────────────────────────
_W  = "b_wall"
_F  = "b_floor_wood"
_Bk = "b_bookshelf"
_Hm = "hermit_npc"
_Sv = "b_stove"          # decorative; NOT walkable
_Tb = "b_table"
_Ch = "b_chair"
_Su = "hut_stair_up"
_Vn = "b_vines"
_Cn = "b_candle"
_D  = "b_door"           # exit door tile
_Bd = "b_bed"
_Sd = "hut_stair_down"

# ── Floor layouts (9×9, row-major y=0..8, col x=0..8) ────────────────────────

# Floor 1: irregular upper-left nook created by wall bump at x=1 rows y=1..2
#   The hermit lives in this alcove; bookshelf wall above, stove at desk,
#   heavy vines creeping toward the door, candle near bottom-right.
_FLOOR1: list[list[str]] = [
    # y=0  top wall
    [_W, _W, _W, _W, _W, _W, _W, _W, _W],
    # y=1  wall bump at x=1 creates nook; bookshelves at x=4,6
    [_W, _W, _F, _F, _Bk, _F, _Bk, _F, _W],
    # y=2  hermit alcove; stove at x=4 (wall bump continues at x=1)
    [_W, _W, _Hm, _F, _Sv, _F, _F, _F, _W],
    # y=3  main room — table and chair in middle
    [_W, _F, _F, _Tb, _F, _Ch, _F, _F, _W],
    # y=4  stair up at x=2
    [_W, _F, _Su, _F, _F, _F, _F, _F, _W],
    # y=5  vines creeping in from west and east sides
    [_W, _F, _Vn, _F, _F, _F, _Vn, _F, _W],
    # y=6  vine cluster near south; candle at x=7 — player spawns here (x=4,y=6)
    [_W, _F, _F, _Vn, _F, _F, _F, _Cn, _W],
    # y=7  door at x=4 (exit)
    [_W, _F, _F, _F, _D, _F, _F, _F, _W],
    # y=8  bottom wall
    [_W, _W, _W, _W, _W, _W, _W, _W, _W],
]

# Floor 2: cramped upper room with heavy vine infestation
#   Room spans roughly x=2..6, y=2..6; rest is solid wall.
#   Stair down at x=6,y=4; bed at x=3,y=3; dense vines & candle.
_FLOOR2: list[list[str]] = [
    # y=0  solid
    [_W, _W, _W, _W, _W, _W, _W, _W, _W],
    # y=1  solid
    [_W, _W, _W, _W, _W, _W, _W, _W, _W],
    # y=2  top of room — bookshelves wall x=3..5
    [_W, _W, _W, _Bk, _Bk, _Bk, _W, _W, _W],
    # y=3  bed at x=3; vines claiming the corners
    [_W, _W, _Vn, _Bd, _F, _F, _Vn, _W, _W],
    # y=4  stair down at x=6; room at x=2..5  (player lands at x=5,y=4 after going up)
    [_W, _W, _F, _F, _F, _F, _Sd, _W, _W],
    # y=5  candle centre; vines flanking
    [_W, _W, _F, _Vn, _Cn, _Vn, _F, _W, _W],
    # y=6  narrower — vines closing in
    [_W, _W, _W, _Vn, _F, _Vn, _W, _W, _W],
    # y=7  solid
    [_W, _W, _W, _W, _W, _W, _W, _W, _W],
    # y=8  solid
    [_W, _W, _W, _W, _W, _W, _W, _W, _W],
]


def _get_floor_grid(floor_num: int) -> list[list[str]]:
    return _FLOOR1 if floor_num == 1 else _FLOOR2


def generate_hut_tiles(floor_num: int) -> list[tuple[int, int, str]]:
    """Return list of (local_x, local_y, tile_type) for the given floor."""
    grid = _get_floor_grid(floor_num)
    return [
        (x, y, tile)
        for y, row in enumerate(grid)
        for x, tile in enumerate(row)
    ]


async def ensure_hermit_hut_built(forest_id: int, db) -> None:
    """Lazily generate hermit hut tiles for both floors if not yet stored."""
    expected = HUT_W * HUT_H * HUT_NUM_FLOORS  # 162
    row = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM hermit_hut_tiles WHERE forest_id=?",
        (forest_id,),
    )
    if row and row["cnt"] >= expected:
        return
    all_tiles: list[tuple] = [
        (forest_id, floor_num, x, y, t)
        for floor_num in range(1, HUT_NUM_FLOORS + 1)
        for x, y, t in generate_hut_tiles(floor_num)
    ]
    await db.executemany(
        "INSERT OR IGNORE INTO hermit_hut_tiles"
        "(forest_id, floor_num, local_x, local_y, tile_type) VALUES (?,?,?,?,?)",
        all_tiles,
    )


async def load_hut_viewport(
    forest_id: int, floor_num: int, center_x: int, center_y: int, db
) -> list[list[TileData]]:
    """Load a 7×7 viewport of a hut floor centred on (center_x, center_y)."""
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM hermit_hut_tiles"
        " WHERE forest_id=? AND floor_num=?"
        " AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (forest_id, floor_num,
         x_min, center_x + half,
         y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}
    grid = []
    for gy in range(y_min, center_y + half + 1):
        grid_row = []
        for gx in range(x_min, center_x + half + 1):
            t = tile_map.get((gx, gy), "b_wall")
            grid_row.append(TileData(terrain=t, world_x=gx, world_y=gy))
        grid.append(grid_row)
    return grid


async def load_hut_single_tile(
    forest_id: int, floor_num: int, local_x: int, local_y: int, db
) -> TileData:
    """Fetch a single tile from the hermit hut."""
    row = await db.fetch_one(
        "SELECT tile_type FROM hermit_hut_tiles"
        " WHERE forest_id=? AND floor_num=? AND local_x=? AND local_y=?",
        (forest_id, floor_num, local_x, local_y),
    )
    return TileData(
        terrain=row["tile_type"] if row else "b_wall",
        world_x=local_x,
        world_y=local_y,
    )
