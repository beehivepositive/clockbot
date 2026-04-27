from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import WORLD_SIZE

# Elevation seed offset for moisture layer
_MOISTURE_OFFSET = 1000

# South-edge ocean / beach thresholds
_BEACH_START_Y   = int(WORLD_SIZE * 0.84)   # sand beach transition begins (~376)
_SHALLOW_OCEAN_Y = int(WORLD_SIZE * 0.88)   # shallow water starts (~394)
_DEEP_OCEAN_Y    = int(WORLD_SIZE * 0.93)   # deep water starts (~416)

# How far (in tiles) the ocean boundary waves per column
_OCEAN_WAVE_AMP  = 8


def _ocean_wave(x: int, seed: int) -> int:
    """Per-column y-offset for the ocean boundary.

    Uses low-frequency (0.04 scale) fBm noise so the boundary curves
    smoothly over tens of tiles rather than jittering tile-by-tile.
    Returns an integer in [-_OCEAN_WAVE_AMP, +_OCEAN_WAVE_AMP].
    """
    # fbm(x*0.04, 0, …) varies slowly with x, giving ≈ 20-tile wavelength
    return int((fbm(x * 0.04, 0, seed + 9877) - 0.5) * 2.0 * _OCEAN_WAVE_AMP)


def get_biome(x: int, y: int, seed: int) -> str:
    """Return the terrain biome string for a world coordinate."""
    # Per-column wave offset so the coastline is organic rather than a
    # perfectly straight horizontal line.
    wave = _ocean_wave(x, seed)

    if y >= _DEEP_OCEAN_Y + wave:
        return "deep_water"
    if y >= _SHALLOW_OCEAN_Y + wave:
        return "shallow_water"
    # Coastal beach — sand forced in the transition zone regardless of noise
    if y >= _BEACH_START_Y + wave:
        return "sand"

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
