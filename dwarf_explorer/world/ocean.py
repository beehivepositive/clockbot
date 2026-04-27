"""Ocean biome generation and viewport loading.

The ocean is a separate 200×200 grid (OCEAN_SIZE × OCEAN_SIZE) accessible
from a harbor structure on the south coast of the overworld.

Coordinate convention:
  (0, 0) = north-west corner, nearest to the overworld shore
  oy increases southward (deeper into the ocean)
  ox increases eastward

Terrain types used:
  deep_water   — open ocean (most common)
  shallow_water — near islands / shoals
  sand         — island beaches
  grass        — island interiors
  forest       — island forest interiors
  shipwreck    — rare structure on deep_water (stored as structure field)
"""
from __future__ import annotations

from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import OCEAN_SIZE

_OCEAN_ELEV_OFFSET = 5000
_OCEAN_MOIST_OFFSET = 6000


def get_ocean_tile(ox: int, oy: int, seed: int) -> str:
    """Return terrain tile for ocean coordinates.

    Uses fBm elevation noise biased by depth so that islands become
    less frequent further from shore and the far reaches are mostly
    deep open ocean.
    """
    e = fbm(ox, oy, seed + _OCEAN_ELEV_OFFSET)
    # depth_bias: 0 at shore (oy=0), 0.45 at far edge (oy=OCEAN_SIZE-1)
    depth_bias = (oy / OCEAN_SIZE) * 0.45
    adjusted_e = e - depth_bias

    if adjusted_e > 0.50:
        # High ground → island
        m = fbm(ox, oy, seed + _OCEAN_MOIST_OFFSET)
        if m > 0.5:
            return "forest"
        return "grass"
    elif adjusted_e > 0.35:
        return "sand"      # island beach / shoal
    elif adjusted_e > -0.05:
        return "shallow_water"
    else:
        return "deep_water"


def get_ocean_structure(ox: int, oy: int, seed: int) -> str | None:
    """Return structure type for this ocean tile, or None.

    Shipwrecks appear rarely (≈1 in 2500 deep-water tiles).
    """
    import random as _rng
    rnd = _rng.Random(seed ^ (ox * 73_856_093) ^ (oy * 19_349_663))
    if rnd.random() < 0.0004:
        if get_ocean_tile(ox, oy, seed) == "deep_water":
            return "shipwreck"
    return None


def load_ocean_viewport(ox: int, oy: int, seed: int, size: int = 9) -> list[list]:
    """Return a size×size list of TileData rows centred on (ox, oy).

    Out-of-bounds tiles show as impassable deep water.
    """
    from dwarf_explorer.world.generator import TileData
    half = size // 2
    rows: list[list] = []
    for dy in range(-half, half + 1):
        row: list = []
        for dx in range(-half, half + 1):
            nx, ny = ox + dx, oy + dy
            if 0 <= nx < OCEAN_SIZE and 0 <= ny < OCEAN_SIZE:
                terrain = get_ocean_tile(nx, ny, seed)
                structure = get_ocean_structure(nx, ny, seed)
                row.append(TileData(terrain=terrain, structure=structure,
                                    world_x=nx, world_y=ny))
            else:
                # Edge of ocean map — treat as void / impassable deep water
                row.append(TileData(terrain="deep_water", world_x=nx, world_y=ny))
        rows.append(row)
    return rows


def load_ocean_single_tile(ox: int, oy: int, seed: int):
    """Return TileData for a single ocean coordinate."""
    from dwarf_explorer.world.generator import TileData
    if 0 <= ox < OCEAN_SIZE and 0 <= oy < OCEAN_SIZE:
        terrain = get_ocean_tile(ox, oy, seed)
        structure = get_ocean_structure(ox, oy, seed)
        return TileData(terrain=terrain, structure=structure, world_x=ox, world_y=oy)
    return TileData(terrain="deep_water", world_x=ox, world_y=oy)
