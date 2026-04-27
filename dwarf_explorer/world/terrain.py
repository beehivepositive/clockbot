from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import WORLD_SIZE

# Elevation seed offset for moisture layer
_MOISTURE_OFFSET = 1000

# South-edge ocean thresholds (computed once at import time)
_SHALLOW_OCEAN_Y = int(WORLD_SIZE * 0.88)   # shallow water starts here
_DEEP_OCEAN_Y    = int(WORLD_SIZE * 0.93)   # deep water starts here


def get_biome(x: int, y: int, seed: int) -> str:
    """Return the terrain biome string for a world coordinate."""
    # South-edge ocean always overrides noise-based biome
    if y >= _DEEP_OCEAN_Y:
        return "deep_water"
    if y >= _SHALLOW_OCEAN_Y:
        return "shallow_water"

    e = fbm(x, y, seed)
    m = fbm(x, y, seed + _MOISTURE_OFFSET)

    # Whittaker-style biome lookup: elevation rows × moisture columns
    if e > 0.72:
        if m > 0.55:
            return "snow"
        return "mountain"
    elif e > 0.58:
        if m > 0.55:
            return "dense_forest"
        elif m > 0.30:
            return "forest"
        return "hills"
    elif e > 0.42:
        if m > 0.55:
            return "forest"
        elif m > 0.30:
            return "grass"
        return "plains"
    elif e > 0.28:
        if m > 0.55:
            return "grass"
        elif m > 0.30:
            return "plains"
        return "sand"
    else:
        if m > 0.55:
            return "deep_water"
        elif m > 0.30:
            return "shallow_water"
        return "sand"
