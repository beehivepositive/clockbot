"""Sunken ship interior generator.

Each shipwreck is deterministically generated from (world_x, world_y, seed).
The interior is a 7×7 grid. Layout:
  - Outer ring: sw_wall (impassable)
  - Interior floor: sw_floor (flooded deck)
  - Entry tile: sw_entrance at (SHIPWRECK_ENTRY_X, SHIPWRECK_ENTRY_Y)
  - 2–4 treasure chests: sw_chest scattered around interior
  - Occasional debris: sw_debris (walkable flavour tile)
"""
from __future__ import annotations

import random

from dwarf_explorer.config import (
    SHIPWRECK_SIZE,
    SHIPWRECK_ENTRY_X,
    SHIPWRECK_ENTRY_Y,
)
from dwarf_explorer.world.generator import TileData

_SW_SEED_OFFSET = 77777


def _make_tile(terrain: str) -> TileData:
    """Create a TileData for a shipwreck interior tile.
    Walkability is determined by WALKABLE_TILES via the TileData.walkable property.
    sw_floor/sw_chest/sw_entrance/sw_debris are in WALKABLE_TILES; sw_wall is not.
    """
    return TileData(terrain=terrain)


def generate_shipwreck_interior(wx: int, wy: int, world_seed: int) -> list[list[TileData]]:
    """Return a SHIPWRECK_SIZE × SHIPWRECK_SIZE grid for the sunken ship interior."""
    size = SHIPWRECK_SIZE
    rng = random.Random(hash((wx, wy, world_seed, _SW_SEED_OFFSET)) & 0xFFFFFFFF)

    # Fill everything with floor
    grid: list[list[TileData]] = [[_make_tile("sw_floor") for _ in range(size)] for _ in range(size)]

    # Outer ring → wall
    for r in range(size):
        for c in range(size):
            if r == 0 or r == size - 1 or c == 0 or c == size - 1:
                grid[r][c] = _make_tile("sw_wall")

    # Place entrance/exit hatch at bottom-centre of interior
    grid[SHIPWRECK_ENTRY_Y][SHIPWRECK_ENTRY_X] = _make_tile("sw_entrance")

    # Place 2–4 debris tiles (avoid entry and walls)
    interior_cells = [
        (r, c)
        for r in range(1, size - 1)
        for c in range(1, size - 1)
        if not (r == SHIPWRECK_ENTRY_Y and c == SHIPWRECK_ENTRY_X)
    ]
    rng.shuffle(interior_cells)
    debris_count = rng.randint(2, 4)
    for r, c in interior_cells[:debris_count]:
        grid[r][c] = _make_tile("sw_debris")

    # Place 2–4 treasure chests (avoid entry, walls, and already-placed debris)
    occupied = {(SHIPWRECK_ENTRY_Y, SHIPWRECK_ENTRY_X)}
    occupied.update(interior_cells[:debris_count])
    chest_candidates = [
        (r, c)
        for r in range(1, size - 1)
        for c in range(1, size - 1)
        if (r, c) not in occupied
    ]
    rng.shuffle(chest_candidates)
    chest_count = rng.randint(2, 4)
    chest_positions: set[tuple[int, int]] = set()
    for r, c in chest_candidates[:chest_count]:
        grid[r][c] = _make_tile("sw_chest")
        chest_positions.add((r, c))

    return grid


def load_shipwreck_viewport(wx: int, wy: int, sx: int, sy: int, world_seed: int) -> list[list[TileData]]:
    """Return a 7×7 viewport centred on (sx, sy) inside the shipwreck.

    Since the interior is already 7×7 the viewport IS the full grid — but we
    respect the position argument by returning the full grid regardless (the
    player marker is placed by the renderer at grid centre).

    Out-of-bounds positions (shouldn't happen in a 7×7) fall back to sw_wall.
    """
    grid = generate_shipwreck_interior(wx, wy, world_seed)
    size = SHIPWRECK_SIZE
    half = size // 2

    result: list[list[TileData]] = []
    for row_y in range(size):
        row: list[TileData] = []
        for col_x in range(size):
            # Map viewport cell (col_x, row_y) → world cell
            world_r = sy - half + row_y
            world_c = sx - half + col_x
            if 0 <= world_r < size and 0 <= world_c < size:
                row.append(grid[world_r][world_c])
            else:
                row.append(_make_tile("sw_wall"))
        result.append(row)
    return result


def get_tile_at(wx: int, wy: int, sx: int, sy: int, world_seed: int) -> TileData:
    """Return the tile at shipwreck local position (sx, sy)."""
    size = SHIPWRECK_SIZE
    if not (0 <= sx < size and 0 <= sy < size):
        return _make_tile("sw_wall")
    grid = generate_shipwreck_interior(wx, wy, world_seed)
    return grid[sy][sx]
