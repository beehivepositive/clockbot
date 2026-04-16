import hashlib

from dwarf_explorer.config import NOISE_OCTAVES, NOISE_LACUNARITY, NOISE_GAIN, NOISE_BASE_SCALE


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def hash_coord(x: int, y: int, seed: int) -> float:
    """Deterministic hash of a 2D coordinate to a float in [0, 1]."""
    h = hashlib.sha256(f"{seed}:{x}:{y}".encode()).digest()
    value = int.from_bytes(h[:4], "big")
    return value / 0xFFFFFFFF


def value_noise_2d(x: float, y: float, seed: int, scale: float) -> float:
    """Bilinear-interpolated value noise at (x/scale, y/scale)."""
    sx = x / scale
    sy = y / scale

    x0 = int(sx) if sx >= 0 else int(sx) - 1
    y0 = int(sy) if sy >= 0 else int(sy) - 1
    x1 = x0 + 1
    y1 = y0 + 1

    tx = _smoothstep(sx - x0)
    ty = _smoothstep(sy - y0)

    c00 = hash_coord(x0, y0, seed)
    c10 = hash_coord(x1, y0, seed)
    c01 = hash_coord(x0, y1, seed)
    c11 = hash_coord(x1, y1, seed)

    top = c00 + (c10 - c00) * tx
    bottom = c01 + (c11 - c01) * tx
    return top + (bottom - top) * ty


def fbm(x: float, y: float, seed: int,
        octaves: int = NOISE_OCTAVES,
        lacunarity: float = NOISE_LACUNARITY,
        gain: float = NOISE_GAIN,
        base_scale: float = NOISE_BASE_SCALE) -> float:
    """Fractional Brownian Motion — sum of multiple noise octaves."""
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_amp = 0.0

    for _ in range(octaves):
        total += value_noise_2d(x * frequency, y * frequency, seed, base_scale) * amplitude
        max_amp += amplitude
        amplitude *= gain
        frequency *= lacunarity

    return total / max_amp  # Normalize to [0, 1]
