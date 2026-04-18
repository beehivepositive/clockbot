from __future__ import annotations

import asyncio
import math
import random

from dwarf_explorer.config import WORLD_SIZE
from dwarf_explorer.world.noise import fbm


# ── Perlin Worm core ──────────────────────────────────────────────────────────

def _worm_noise_angle(wx: float, wy: float, seed: int) -> float:
    """Sample fBm at world position → rotation angle in radians (-π/2..+π/2).

    Sampling at world position (not step index) gives geographic coherence:
    worms crossing the same region curve the same way.
    freq=0.5 → ~8 direction reversals over the 224-tile map.
    """
    n = fbm(wx * 0.5, wy * 0.5, seed, octaves=3)  # 0..1
    return math.radians((n - 0.5) * 180.0)         # -90°..+90°


def _rotate2(dx: float, dy: float, angle: float) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return (c * dx - s * dy, s * dx + c * dy)


def _norm2(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy)
    return (dx / m, dy / m) if m > 1e-9 else (1.0, 0.0)


def _worm_path(
    start: tuple[float, float],
    start_angle: float,
    length: int,
    seed: int,
    convergence: tuple[float, float] | None = None,
    conv_weight: float = 0.5,
) -> list[tuple[int, int]]:
    """
    Perlin Worm: each step, sample fBm at world position → rotate direction
    by that angle → (optionally) blend toward convergence target → step forward.

    conv_weight 0.5 means half noise-driven, half aimed at target.
    """
    x, y = float(start[0]), float(start[1])
    dx, dy = _norm2(math.cos(start_angle), math.sin(start_angle))
    path: list[tuple[int, int]] = []

    for _ in range(length * 4):
        if len(path) >= length:
            break

        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))
        if not path or (ix, iy) != path[-1]:
            path.append((ix, iy))

        # Rotate direction by noise-derived angle at this world position
        rot = _worm_noise_angle(x, y, seed)
        dx, dy = _norm2(*_rotate2(dx, dy, rot))

        if convergence is not None:
            tx, ty = convergence[0] - x, convergence[1] - y
            dist = math.hypot(tx, ty)
            if dist < 1.5:
                break
            tdx, tdy = _norm2(tx, ty)
            w = conv_weight
            dx, dy = _norm2(dx * (1 - w) + tdx * w, dy * (1 - w) + tdy * w)

        x = max(0.0, min(WORLD_SIZE - 1.0, x + dx))
        y = max(0.0, min(WORLD_SIZE - 1.0, y + dy))

    return path


# ── Main trunk (noise-sampled Y, guaranteed W→E crossing) ────────────────────

def _trunk_path(start_y: float, seed: int) -> list[tuple[int, int]]:
    """Main river trunk: visits every x-column W→E with noise-driven Y meanders.

    Samples fBm at each column to offset Y smoothly around the starting position.
    Guaranteed to cross the full map width with no gaps.
    """
    path: list[tuple[int, int]] = []
    for x in range(WORLD_SIZE):
        # Coarse noise: big sweeping bends (~40-tile amplitude)
        coarse = fbm(x * 0.5, 0.0, seed, octaves=2)
        # Fine noise: small wiggles
        fine   = fbm(x * 1.8, 0.0, seed ^ 0xABCD, octaves=2)
        offset = (coarse - 0.5) * 80.0 + (fine - 0.5) * 15.0
        y = int(round(max(15.0, min(WORLD_SIZE - 15.0, start_y + offset))))
        if not path or (x, y) != path[-1]:
            path.append((x, y))
    return path


# ── Rendering ─────────────────────────────────────────────────────────────────

def _paint(path: list[tuple[int, int]], hw: int, tiles: set[tuple[int, int]]) -> None:
    """Chebyshev-distance brush along path — no gaps regardless of angle."""
    for px, py in path:
        for dy in range(-hw, hw + 1):
            for dx in range(-hw, hw + 1):
                nx, ny = px + dx, py + dy
                if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
                    tiles.add((nx, ny))


# ── Lakes ─────────────────────────────────────────────────────────────────────

def _place_lake(tiles: set[tuple[int, int]], cx: int, cy: int, r: int) -> None:
    r2 = r * r
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r2:
                tx, ty = cx + dx, cy + dy
                if 0 <= tx < WORLD_SIZE and 0 <= ty < WORLD_SIZE:
                    tiles.add((tx, ty))


# ── Bridges ───────────────────────────────────────────────────────────────────

def _place_bridge_at(
    path: list[tuple[int, int]],
    idx: int,
    river_tiles: set[tuple[int, int]],
    bridge_tiles: set[tuple[int, int]],
) -> None:
    """Replace river tiles in a 5×5 area with a bridge and add cardinal approach tiles."""
    if idx < 0 or idx >= len(path):
        return
    px, py = path[idx]

    for dy in range(-2, 3):
        for dx in range(-2, 3):
            nx, ny = px + dx, py + dy
            if (nx, ny) in river_tiles:
                bridge_tiles.add((nx, ny))
                river_tiles.discard((nx, ny))

    for ddx, ddy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        for dist in range(1, 5):
            ax, ay = px + ddx * dist, py + ddy * dist
            if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
                if (ax, ay) not in river_tiles and (ax, ay) not in bridge_tiles:
                    bridge_tiles.add((ax, ay))
                    break


def _add_bridges(
    paths_orders: list[tuple[list[tuple[int, int]], int]],
    river_tiles: set[tuple[int, int]],
    bridge_tiles: set[tuple[int, int]],
    rng: random.Random,
) -> None:
    """Bridges only on order≥3 streams (trunk + major tribs).
    Trunk: every 35-50 tiles. Major tribs: one bridge at midpoint.
    """
    for path, order in paths_orders:
        if order < 3:
            continue
        if order >= 4:
            # Trunk: evenly spaced bridges
            interval = rng.randint(35, 50)
            idx = interval
            while idx < len(path) - 5:
                _place_bridge_at(path, idx, river_tiles, bridge_tiles)
                idx += rng.randint(35, 50)
        else:
            # Major tributaries: one bridge at midpoint
            if len(path) >= 10:
                _place_bridge_at(path, len(path) // 2, river_tiles, bridge_tiles)


# ── World generation ──────────────────────────────────────────────────────────

def _generate_rivers_sync(
    seed: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    """
    Hybrid Perlin Worm drainage network.

    Trunk:           noise-sampled Y per column → guaranteed W→E, visible bends.
    Major tribs:     Perlin Worms from N/S edges converging onto trunk junctions.
    Sub-tribs:       Perlin Worms from off-path positions converging onto trib junctions.
    Bridges:         on trunk + major tribs only (3-tile-wide streams), ~30-45 tiles apart.
    Source lakes:    at worm start points (60% chance, if within map bounds).
    """
    rng = random.Random(seed ^ 0xDEAD_BEEF)
    dir_seed = (seed ^ 0xF00D_CAFE) & 0xFFFFFFFF

    river_tiles: set[tuple[int, int]] = set()
    bridge_tiles: set[tuple[int, int]] = set()
    lake_tiles: set[tuple[int, int]] = set()
    paths_orders: list[tuple[list[tuple[int, int]], int]] = []

    # ── 1. Main trunk ─────────────────────────────────────────────────────────
    start_y = float(rng.randint(55, WORLD_SIZE - 55))
    trunk = _trunk_path(start_y, seed)

    _paint(trunk, hw=1, tiles=river_tiles)  # 3-tile base width
    # Extra width in the middle half: 5 tiles
    mid_s = len(trunk) // 4
    mid_e = 3 * len(trunk) // 4
    _paint(trunk[mid_s:mid_e], hw=2, tiles=river_tiles)
    paths_orders.append((trunk, 4))

    # ── 2. Major tributaries (Perlin Worms from N/S edges → trunk) ───────────
    num_major = rng.randint(5, 7)
    spacing = max(1, len(trunk) // (num_major + 1))
    major_tribs: list[list[tuple[int, int]]] = []
    side = rng.choice([-1, 1])  # -1=north, +1=south; alternates

    for i in range(num_major):
        j_idx = spacing * (i + 1) + rng.randint(-spacing // 3, spacing // 3)
        j_idx = max(5, min(len(trunk) - 5, j_idx))
        jx, jy = trunk[j_idx]

        sx = float(max(2, min(WORLD_SIZE - 2, jx + rng.randint(-30, 30))))
        if side < 0:
            sy = float(rng.randint(2, 15))
            start_ang = math.pi * 0.5    # heading south toward trunk
        else:
            sy = float(rng.randint(WORLD_SIZE - 15, WORLD_SIZE - 2))
            start_ang = -math.pi * 0.5   # heading north toward trunk

        trib_seed = (dir_seed + 0x1000 + i) & 0xFFFFFFFF
        trib = _worm_path(
            start=(sx, sy),
            start_angle=start_ang,
            length=100,
            seed=trib_seed,
            convergence=(float(jx), float(jy)),
            conv_weight=0.50,
        )
        if len(trib) >= 8:
            _paint(trib, hw=1, tiles=river_tiles)
            paths_orders.append((trib, 3))
            major_tribs.append(trib)

            ox, oy = trib[0]
            at_edge = ox <= 4 or ox >= WORLD_SIZE - 4 or oy <= 4 or oy >= WORLD_SIZE - 4
            if not at_edge and rng.random() < 0.55:
                _place_lake(lake_tiles, ox, oy, rng.randint(2, 4))

        side *= -1

    # ── 3. Sub-tributaries (Perlin Worms from sides → trib junctions) ─────────
    for t_i, trib in enumerate(major_tribs):
        num_sub = rng.randint(2, 4)
        sub_spacing = max(1, len(trib) // (num_sub + 1))
        sub_side = rng.choice([-1, 1])

        for s_i in range(num_sub):
            j_idx = sub_spacing * (s_i + 1) + rng.randint(-sub_spacing // 3, sub_spacing // 3)
            j_idx = max(2, min(len(trib) - 2, j_idx))
            jx, jy = trib[j_idx]

            # Perpendicular to parent trib at junction
            i0 = max(0, j_idx - 2)
            i1 = min(len(trib) - 1, j_idx + 2)
            parent_ang = math.atan2(trib[i1][1] - trib[i0][1],
                                    trib[i1][0] - trib[i0][0])
            perp_ang = parent_ang + sub_side * rng.uniform(
                math.radians(70), math.radians(110))

            dist_out = rng.randint(20, 45)
            sx = max(2.0, min(WORLD_SIZE - 2.0, jx + math.cos(perp_ang) * dist_out))
            sy = max(2.0, min(WORLD_SIZE - 2.0, jy + math.sin(perp_ang) * dist_out))
            back_ang = math.atan2(jy - sy, jx - sx)

            sub_seed = (dir_seed + 0x2000 + t_i * 20 + s_i) & 0xFFFFFFFF
            sub = _worm_path(
                start=(sx, sy),
                start_angle=back_ang,
                length=55,
                seed=sub_seed,
                convergence=(float(jx), float(jy)),
                conv_weight=0.55,
            )
            if len(sub) >= 5:
                _paint(sub, hw=0, tiles=river_tiles)
                paths_orders.append((sub, 2))

                ox, oy = sub[0]
                at_edge = ox <= 4 or ox >= WORLD_SIZE - 4 or oy <= 4 or oy >= WORLD_SIZE - 4
                if not at_edge and rng.random() < 0.60:
                    _place_lake(lake_tiles, int(ox), int(oy), rng.randint(2, 3))

            sub_side *= -1

    # ── 4. Bridges (trunk + major tribs only) ────────────────────────────────
    _add_bridges(paths_orders, river_tiles, bridge_tiles, rng)

    lake_tiles -= river_tiles
    lake_tiles -= bridge_tiles

    return list(river_tiles), list(bridge_tiles), list(lake_tiles)


async def generate_rivers(seed: int, db) -> None:
    """Generate rivers, bridges, and lakes; write to tile_overrides."""
    river_tiles, bridge_tiles, lake_tiles = await asyncio.to_thread(
        _generate_rivers_sync, seed
    )
    if river_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type)"
            " VALUES (?, ?, 'river')",
            [(x, y) for x, y in river_tiles],
        )
    if bridge_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type)"
            " VALUES (?, ?, 'bridge')",
            [(x, y) for x, y in bridge_tiles],
        )
    if lake_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type)"
            " VALUES (?, ?, 'shallow_water')",
            [(x, y) for x, y in lake_tiles],
        )
