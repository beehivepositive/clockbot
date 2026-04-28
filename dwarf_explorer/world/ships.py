from __future__ import annotations

from dwarf_explorer.config import SHIP_WALKABLE
from dwarf_explorer.world.generator import TileData

# Default background tile for out-of-room areas
_BG = "deep_water"

# Spawn position on the helm deck
HELM_SPAWN: tuple[int, int] = (11, 6)


def _generate_helm() -> dict[tuple[int, int], str]:
    """Build helm room tilemap (23 wide × 19 tall). Returns {(x,y): tile_type}."""
    tiles: dict[tuple[int, int], str] = {}

    # Deck tiles: rows 4–14, cols 5–17
    for y in range(4, 15):
        for x in range(5, 18):
            tiles[(x, y)] = "ship_deck"

    # Special tiles
    tiles[(11, 5)] = "ship_helm"      # steering wheel
    tiles[(11, 9)] = "ship_mast"      # impassable mast
    tiles[(5, 8)]  = "ship_cannon"    # cannon port (impassable)
    tiles[(17, 8)] = "ship_cannon"    # cannon port (impassable)
    tiles[(11, 14)] = "ship_door"     # door south to captain's quarters

    return tiles


def _generate_quarters() -> dict[tuple[int, int], str]:
    """Build captain's quarters room tilemap (23 wide × 13 tall)."""
    tiles: dict[tuple[int, int], str] = {}

    # Ship wall border: rows 4–8, cols 6–16
    for y in range(4, 9):
        for x in range(6, 17):
            tiles[(x, y)] = "ship_wall"

    # Interior deck: rows 5–7, cols 7–15
    for y in range(5, 8):
        for x in range(7, 16):
            tiles[(x, y)] = "ship_deck"

    # Doors and furnishings
    tiles[(11, 4)] = "ship_door"           # door north (back to helm)
    tiles[(8, 6)]  = "ship_chest_personal" # personal chest
    tiles[(11, 6)] = "ship_table"          # decorative table (impassable)
    tiles[(11, 8)] = "ship_door"           # door south (to lower deck)

    return tiles


def _generate_lower_deck() -> dict[tuple[int, int], str]:
    """Build lower deck room tilemap (23 wide × 17 tall)."""
    tiles: dict[tuple[int, int], str] = {}

    # Ship wall border: rows 4–12, cols 4–18
    for y in range(4, 13):
        for x in range(4, 19):
            tiles[(x, y)] = "ship_wall"

    # Interior deck: rows 5–11, cols 5–17
    for y in range(5, 12):
        for x in range(5, 18):
            tiles[(x, y)] = "ship_deck"

    # Door north (back to quarters)
    tiles[(11, 4)] = "ship_door"

    # Beds (impassable)
    tiles[(6, 7)]  = "ship_bed"
    tiles[(6, 9)]  = "ship_bed"
    tiles[(16, 7)] = "ship_bed"
    tiles[(16, 9)] = "ship_bed"

    # Cannons (impassable)
    tiles[(5, 6)]  = "ship_cannon"
    tiles[(5, 8)]  = "ship_cannon"
    tiles[(17, 6)] = "ship_cannon"
    tiles[(17, 8)] = "ship_cannon"

    # Cargo chest
    tiles[(11, 11)] = "ship_chest_cargo"

    # Stairs near north door (walkable)
    tiles[(9, 4)]  = "ship_stairs"
    tiles[(13, 4)] = "ship_stairs"

    return tiles


# Room sizes: (width, height)
_ROOM_SIZES: dict[str, tuple[int, int]] = {
    "helm":        (23, 19),
    "quarters":    (23, 13),
    "lower_deck":  (23, 17),
}

# Cached tilemaps
_ROOM_TILES: dict[str, dict[tuple[int, int], str]] = {
    "helm":        _generate_helm(),
    "quarters":    _generate_quarters(),
    "lower_deck":  _generate_lower_deck(),
}

# Door connections: (room, x, y) → (new_room, new_x, new_y)
_DOOR_TARGETS: dict[tuple[str, int, int], tuple[str, int, int]] = {
    ("helm",        11, 14): ("quarters",   11, 5),
    ("quarters",    11,  4): ("helm",       11, 13),
    ("quarters",    11,  8): ("lower_deck", 11, 5),
    ("lower_deck",  11,  4): ("quarters",   11, 7),
}


def get_room_size(room: str) -> tuple[int, int]:
    """Return (width, height) for the given room."""
    return _ROOM_SIZES.get(room, (23, 19))


def get_room_tile(room: str, x: int, y: int) -> str:
    """Return tile type string at (x, y) in the given room."""
    tiles = _ROOM_TILES.get(room, {})
    width, height = get_room_size(room)
    if x < 0 or x >= width or y < 0 or y >= height:
        return _BG
    return tiles.get((x, y), _BG)


def load_ship_viewport(room: str, ship_x: int, ship_y: int) -> list[list[TileData]]:
    """Return 9×9 viewport (list of lists of TileData) centered on (ship_x, ship_y)."""
    grid: list[list[TileData]] = []
    half = 4  # 9//2
    for row_offset in range(-half, half + 1):
        row: list[TileData] = []
        for col_offset in range(-half, half + 1):
            tx = ship_x + col_offset
            ty = ship_y + row_offset
            tile_type = get_room_tile(room, tx, ty)
            row.append(TileData(terrain=tile_type))
        grid.append(row)
    return grid


def get_door_target(room: str, x: int, y: int) -> tuple[str, int, int] | None:
    """If (x, y) in room is a door tile, return (new_room, new_x, new_y). Else None."""
    tile = get_room_tile(room, x, y)
    if tile != "ship_door":
        return None
    return _DOOR_TARGETS.get((room, x, y), None)
