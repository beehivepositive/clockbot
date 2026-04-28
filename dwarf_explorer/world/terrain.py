from __future__ import annotations

import random as _rng_module

from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import WORLD_SIZE

_MOISTURE_OFFSET = 1000

# ── Coastline boundary ─────────────────────────────────────────────────────────
# One per world-seed: a random-walk per-column (or per-row) boundary that
# determines where land ends and ocean begins.

_coast_cache: dict[int, tuple[int, list[int]]] = {}


def _compute_coast_boundary(seed: int) -> tuple[int, list[int]]:
    """Generate a meandering coastline as a random walk for one edge.

    Returns (edge, boundary):
      edge 0 = south (ocean at y >= coast[x])
      edge 1 = north (ocean at y <= coast[x])
      edge 2 = west  (ocean at x <= coast[y])
      edge 3 = east  (ocean at x >= coast[y])

    boundary is a list of WORLD_SIZE integers, one per column (or row).
    The walk meanders ±~30 tiles around a base value (≈80 or 20 % of
    WORLD_SIZE), with gentle mean-reversion so it never drifts off entirely.
    The map edge is always at least 2 tiles of open ocean (boundary stays
    ≤ WORLD_SIZE-2 for S/E, ≥ 1 for N/W).
    """
    rng = _rng_module.Random(seed ^ 0xC0A57A1E)
    edge = rng.randint(0, 3)

    if edge == 0:   # south — ocean is at high y
        base = int(WORLD_SIZE * 0.80)
        lo   = int(WORLD_SIZE * 0.66)
        hi   = WORLD_SIZE - 2
    elif edge == 1: # north — ocean is at low y
        base = int(WORLD_SIZE * 0.20)
        lo   = 1
        hi   = int(WORLD_SIZE * 0.34)
    elif edge == 2: # west — ocean is at low x
        base = int(WORLD_SIZE * 0.20)
        lo   = 1
        hi   = int(WORLD_SIZE * 0.34)
    else:           # east — ocean is at high x
        base = int(WORLD_SIZE * 0.80)
        lo   = int(WORLD_SIZE * 0.66)
        hi   = WORLD_SIZE - 2

    val = float(base)
    boundary: list[int] = []
    for _ in range(WORLD_SIZE):
        # Mean-reverting random walk — drift pulls back toward base
        drift = (base - val) * 0.04
        val  += rng.gauss(drift, 2.5)
        val   = max(lo, min(hi, val))
        boundary.append(int(val))

    return edge, boundary


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
