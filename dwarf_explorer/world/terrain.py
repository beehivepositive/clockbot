from __future__ import annotations

import math as _math
import random as _rng_module

from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import WORLD_SIZE

_MOISTURE_OFFSET = 1000

# ── Coastline boundary ─────────────────────────────────────────────────────────
# One per world-seed: a random-walk per-column (or per-row) boundary that
# determines where land ends and ocean begins.

_coast_cache: dict[int, tuple[int, list[int]]] = {}


def _compute_coast_boundary(seed: int) -> tuple[int, list[int]]:
    """Generate a meandering coastline with large macro-scale curves.

    Returns (edge, boundary):
      edge 0 = south (ocean at y >= coast[x])
      edge 1 = north (ocean at y <= coast[x])
      edge 2 = west  (ocean at x <= coast[y])
      edge 3 = east  (ocean at x >= coast[y])

    The ocean occupies ~11-22 tiles at the world edge (narrow strip).
    Two random sine waves create large macro bends; fBm adds fine roughness.
    """
    rng = _rng_module.Random(seed ^ 0xC0A57A1E)
    edge = rng.randint(0, 3)

    # Place the coastline close to the world edge — ocean is ~14 tiles wide
    # at the base position (3 sand + 4 shallow + 7 deep).
    # Wider lo/hi range lets the combined noise swing freely without rail-clamping.
    if edge == 0:   # south — ocean at high y
        base = WORLD_SIZE - 11
        lo   = WORLD_SIZE - 26
        hi   = WORLD_SIZE - 6
    elif edge == 1: # north — ocean at low y
        base = 10
        lo   = 5
        hi   = 24
    elif edge == 2: # west — ocean at low x
        base = 10
        lo   = 5
        hi   = 24
    else:           # east — ocean at high x
        base = WORLD_SIZE - 11
        lo   = WORLD_SIZE - 26
        hi   = WORLD_SIZE - 6

    # Macro bend: two sine waves with randomised period / phase / amplitude.
    # Primary: long meander (200-350 tile period) → ~1-2 full bends across map
    p1  = rng.uniform(200.0, 350.0)
    ph1 = rng.uniform(0.0, 2.0 * _math.pi)
    a1  = rng.uniform(7.0, 11.0)     # ±7-11 tile amplitude
    # Secondary: medium undulation (80-160 tile period) for added complexity
    p2  = rng.uniform(80.0, 160.0)
    ph2 = rng.uniform(0.0, 2.0 * _math.pi)
    a2  = rng.uniform(2.5, 5.0)

    boundary: list[int] = []
    for i in range(WORLD_SIZE):
        macro  = a1 * _math.sin(2.0 * _math.pi * i / p1 + ph1)
        medium = a2 * _math.sin(2.0 * _math.pi * i / p2 + ph2)
        # Meso roughness (25-50 tile scale, ±3 tiles) — fractal bumps
        meso   = (fbm(i * 0.3, 0.0, seed ^ 0xF1D37A, octaves=3) - 0.5) * 6.0
        # Micro jaggedness (2-8 tile scale, ±1.5 tiles) — tile-level irregularity
        micro  = (fbm(i * 2.0, 0.0, seed ^ 0xA3B2C1D4, octaves=3) - 0.5) * 3.0
        offset = macro + medium + meso + micro
        val    = int(round(max(float(lo), min(float(hi), float(base) + offset))))
        boundary.append(val)

    # Weighted 3-point smoother — centre counts double, so 2-tile features
    # survive while lone 1-tile spikes are softened.
    smoothed = list(boundary)
    for i in range(1, len(boundary) - 1):
        smoothed[i] = (boundary[i - 1] + 2 * boundary[i] + boundary[i + 1]) // 4

    return edge, smoothed


def get_coast_boundary(seed: int) -> tuple[int, list[int]]:
    """Return (edge, per-column boundary list) for this world seed. Cached."""
    if seed not in _coast_cache:
        _coast_cache[seed] = _compute_coast_boundary(seed)
    return _coast_cache[seed]


# ── Biome lookup ───────────────────────────────────────────────────────────────

def get_biome(x: int, y: int, seed: int) -> str:
    """Return the terrain biome string for a world coordinate."""
    edge, boundary = get_coast_boundary(seed)

    # ── Ocean / beach zone ───────────────────────────────────────────────────
    if edge == 0:   # south ocean
        c = boundary[x] if 0 <= x < WORLD_SIZE else int(WORLD_SIZE * 0.80)
        if y >= c + 4:  return "deep_water"
        if y >= c:      return "shallow_water"
        if y >= c - 3:  return "sand"

    elif edge == 1: # north ocean
        c = boundary[x] if 0 <= x < WORLD_SIZE else int(WORLD_SIZE * 0.20)
        if y <= c - 4:  return "deep_water"
        if y <= c:      return "shallow_water"
        if y <= c + 3:  return "sand"

    elif edge == 2: # west ocean
        c = boundary[y] if 0 <= y < WORLD_SIZE else int(WORLD_SIZE * 0.20)
        if x <= c - 4:  return "deep_water"
        if x <= c:      return "shallow_water"
        if x <= c + 3:  return "sand"

    else:           # east ocean
        c = boundary[y] if 0 <= y < WORLD_SIZE else int(WORLD_SIZE * 0.80)
        if x >= c + 4:  return "deep_water"
        if x >= c:      return "shallow_water"
        if x >= c - 3:  return "sand"

    # ── Normal Whittaker-style land biomes ───────────────────────────────────
    e = fbm(x, y, seed)
    m = fbm(x, y, seed + _MOISTURE_OFFSET)

    if e > 0.72:
        return "snow" if m > 0.55 else "mountain"
    elif e > 0.58:
        if m > 0.55:  return "dense_forest"
        if m > 0.30:  return "forest"
        return "hills"
    elif e > 0.42:
        if m > 0.55:  return "forest"
        if m > 0.30:  return "grass"
        return "plains"
    elif e > 0.28:
        if m > 0.55:  return "grass"
        if m > 0.30:  return "plains"
        return "sand"
    else:
        if m > 0.55:  return "deep_water"
        if m > 0.30:  return "shallow_water"
        return "sand"
