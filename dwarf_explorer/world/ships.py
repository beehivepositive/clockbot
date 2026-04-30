from __future__ import annotations

from dwarf_explorer.config import SHIP_WALKABLE
from dwarf_explorer.world.generator import TileData

# Default background tile for out-of-room areas
_BG = "deep_water"

# Player spawn on the helm deck (at the wheel)
HELM_SPAWN: tuple[int, int] = (4, 1)


def _generate_helm() -> dict[tuple[int, int], str]:
    """
    Helm deck — 9 wide × 18 tall, y=0 at stern (top), y=17 = bow tip.

    Template (each cell = 1 tile):
      y 0:  . . . . . . . . .   stern deck
      y 1:  . . . . H . . . .   helm wheel
      y 2:  . . . . . . . . .   open deck
      y 3:  # . . # # # . . #   upper cabin walls
      y 4:  # . . # D # . . #   door → captain's quarters
      y 5:  . . . . . . . . .
      y 6:  . . . . . . . . .   main open deck
      y 7:  . . . . . . . . .
      y 8:  . . . . . . . . .
      y 9:  . . . . . . . . .
      y10:  # . . # D # . . #   door → lower deck
      y11:  # . . # # # . . #   lower cabin walls
      y12:  . . . . . . . . .   forward deck
      y13:  (void gap)
      y14:    . . . . . . .     7-wide bow taper
      y15:      . . . . .       5-wide
      y16:        . . .         3-wide
      y17:          .           bow tip
    """
    tiles: dict[tuple[int, int], str] = {}

    # Stern + open deck (y 0–2)
    for y in range(3):
        for x in range(9):
            tiles[(x, y)] = "ship_deck"
    tiles[(4, 1)] = "ship_helm"

    # Upper cabin (y 3–4)
    for x in (0, 3, 4, 5, 8):
        tiles[(x, 3)] = "ship_wall"
    for x in (1, 2, 6, 7):
        tiles[(x, 3)] = "ship_deck"

    for x in (0, 3, 5, 8):
        tiles[(x, 4)] = "ship_wall"
    for x in (1, 2, 6, 7):
        tiles[(x, 4)] = "ship_deck"
    tiles[(4, 4)] = "ship_door"        # → captain's quarters

    # Main open deck (y 5–9)
    for y in range(5, 10):
        for x in range(9):
            tiles[(x, y)] = "ship_deck"

    # Lower cabin (y 10–11)
    for x in (0, 3, 5, 8):
        tiles[(x, 10)] = "ship_wall"
    for x in (1, 2, 6, 7):
        tiles[(x, 10)] = "ship_deck"
    tiles[(4, 10)] = "ship_door"       # → lower deck

    for x in (0, 3, 4, 5, 8):
        tiles[(x, 11)] = "ship_wall"
    for x in (1, 2, 6, 7):
        tiles[(x, 11)] = "ship_deck"

    # Forward deck (y 12)
    for x in range(9):
        tiles[(x, 12)] = "ship_deck"

    # y 13: void gap — no tiles placed; renders as _BG (deep_water)

    # Bow taper (y 14–17)
    for x in range(1, 8):             # 7-wide
        tiles[(x, 14)] = "ship_deck"
    for x in range(2, 7):             # 5-wide
        tiles[(x, 15)] = "ship_deck"
    for x in range(3, 6):             # 3-wide
        tiles[(x, 16)] = "ship_deck"
    tiles[(4, 17)] = "ship_deck"      # bow tip

    return tiles


def _generate_quarters() -> dict[tuple[int, int], str]:
    """
    Captain's quarters — 9 wide × 9 tall.

      y 0:  # # # # D # # # #   door → back to helm (open deck side)
      y 1:  #  .  .  .  .  .  .  .  #
      y 2:  #  .  BED .  .  .  C  .  #   bed (l) + personal chest (r)
      y 3:  #  .  .  .  .  .  .  .  #
      y 4:  #  .  .  T  .  .  .  .  #   table (decorative)
      y 5:  #  .  .  .  .  .  .  .  #
      y 6:  #  .  .  .  .  .  .  .  #
      y 7:  #  .  .  .  .  .  .  .  #
      y 8:  # # # # # # # # #         back wall
    """
    tiles: dict[tuple[int, int], str] = {}

    # Outer walls
    for x in range(9):
        tiles[(x, 0)] = "ship_wall"
        tiles[(x, 8)] = "ship_wall"
    for y in range(1, 8):
        tiles[(0, y)] = "ship_wall"
        tiles[(8, y)] = "ship_wall"

    # Interior deck
    for y in range(1, 8):
        for x in range(1, 8):
            tiles[(x, y)] = "ship_deck"

    # Door, furnishings
    tiles[(4, 0)] = "ship_door"            # back to helm
    tiles[(2, 2)] = "ship_bed"             # bed
    tiles[(6, 2)] = "ship_chest_personal"  # personal chest
    tiles[(3, 4)] = "ship_table"           # map table (impassable)

    return tiles


def _generate_lower_deck() -> dict[tuple[int, int], str]:
    """
    Lower deck — 9 wide × 9 tall.

      y 0:  # # # # D # # # #   door → back to helm (main deck side)
      y 1:  C  .  .  .  .  .  .  .  C   cannon ports (impassable)
      y 2:  #  .  .  .  .  .  .  .  #
      y 3:  #  .  .  .  .  .  .  .  #
      y 4:  #  .  .  .  CG .  .  .  #   cargo chest
      y 5:  #  .  .  .  .  .  .  .  #
      y 6:  #  .  .  .  .  .  .  .  #
      y 7:  C  .  .  .  .  .  .  .  C   cannon ports
      y 8:  # # # # # # # # #         back wall
    """
    tiles: dict[tuple[int, int], str] = {}

    # Outer walls + cannon ports
    for x in range(9):
        tiles[(x, 0)] = "ship_wall"
        tiles[(x, 8)] = "ship_wall"
    for y in range(1, 8):
        tiles[(0, y)] = "ship_wall"
        tiles[(8, y)] = "ship_wall"

    # Interior deck
    for y in range(1, 8):
        for x in range(1, 8):
            tiles[(x, y)] = "ship_deck"

    # Door + contents
    tiles[(4, 0)]  = "ship_door"          # back to helm
    tiles[(0, 1)]  = "ship_cannon"        # cannon ports (impassable)
    tiles[(8, 1)]  = "ship_cannon"
    tiles[(0, 7)]  = "ship_cannon"
    tiles[(8, 7)]  = "ship_cannon"
    tiles[(4, 4)]  = "ship_chest_cargo"   # cargo chest
    tiles[(9, 3)]  = "ship_stairs"        # repair station marker (out of bounds, won't render)

    return tiles


# Room sizes: (width, height)
_ROOM_SIZES: dict[str, tuple[int, int]] = {
    "helm":        (9, 18),
    "quarters":    (9, 9),
    "lower_deck":  (9, 9),
}

# Cached tilemaps
_ROOM_TILES: dict[str, dict[tuple[int, int], str]] = {
    "helm":        _generate_helm(),
    "quarters":    _generate_quarters(),
    "lower_deck":  _generate_lower_deck(),
}

# Door connections: (room, x, y) → (new_room, new_x, new_y)
_DOOR_TARGETS: dict[tuple[str, int, int], tuple[str, int, int]] = {
    ("helm",        4, 4):  ("quarters",   4, 1),   # stern door → quarters
    ("quarters",    4, 0):  ("helm",       4, 5),   # quarters exit → main deck
    ("helm",        4, 10): ("lower_deck", 4, 1),   # bow door → lower deck
    ("lower_deck",  4, 0):  ("helm",       4, 9),   # lower deck exit → main deck
}


def get_room_size(room: str) -> tuple[int, int]:
    """Return (width, height) for the given room."""
    return _ROOM_SIZES.get(room, (9, 18))


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
