from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import WORLD_SIZE
from dwarf_explorer.world.noise import fbm


def _generate_rivers_sync(seed: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Generate river and bridge tile positions.

    Returns (river_tiles, bridge_tiles) as lists of (x, y).
    """
    rng = random.Random(seed ^ 0xDEAD_BEEF)

    river_tiles: set[tuple[int, int]] = set()
    bridge_tiles: set[tuple[int, int]] = set()

    # ------------------------------------------------------------------
    # Main river: guaranteed to cross the entire map west -> east
    # ------------------------------------------------------------------
    main_river_by_col: dict[int, set[int]] = {}  # col -> set of y values

    start_y = rng.randint(30, WORLD_SIZE - 30)
    y = start_y

    for x in range(WORLD_SIZE):
        y = max(10, min(WORLD_SIZE - 10, y))

        river_tiles.add((x, y))
        main_river_by_col.setdefault(x, set()).add(y)

        # Widen every 15 columns (3 tiles wide)
        if x % 15 == 0:
            for dy in (-1, 1):
                ny = y + dy
                if 5 <= ny < WORLD_SIZE - 5:
                    river_tiles.add((x, ny))
                    main_river_by_col.setdefault(x, set()).add(ny)

        # Drift: biased random walk influenced by noise
        noise_val = fbm(x * 0.03, y * 0.03, seed, octaves=2)
        drift_bias = int((noise_val - 0.5) * 3)
        move = rng.choices([-1, 0, 0, 1], k=1)[0] + drift_bias
        y += max(-1, min(1, move))

    # ------------------------------------------------------------------
    # Tributaries (2-4): flow from top/bottom edge toward the main river
    # ------------------------------------------------------------------
    num_tributaries = rng.randint(2, 4)
    tributary_cols = rng.sample(range(20, WORLD_SIZE - 20), num_tributaries)

    for trib_x in tributary_cols:
        if trib_x not in main_river_by_col:
            continue
        target_y = min(main_river_by_col[trib_x])

        if rng.random() < 0.5:
            ty = rng.randint(0, 15)
            direction = 1
        else:
            ty = rng.randint(WORLD_SIZE - 15, WORLD_SIZE - 1)
            direction = -1

        tx = trib_x
        steps = 0

        while steps < WORLD_SIZE:
            ty = max(0, min(WORLD_SIZE - 1, ty))
            river_tiles.add((tx, ty))

            if abs(ty - target_y) <= 1:
                break

            vert = direction
            horiz = rng.choice([-1, 0, 0, 0, 1])
            nx, ny = tx + horiz, ty + vert

            if not (0 <= nx < WORLD_SIZE):
                nx = tx
            tx, ty = nx, ny
            steps += 1

    # ------------------------------------------------------------------
    # Bridges on main river: every 30-40 columns
    # ------------------------------------------------------------------
    bridge_interval = rng.randint(30, 40)
    x = bridge_interval
    while x < WORLD_SIZE - bridge_interval:
        if x in main_river_by_col:
            ys = sorted(main_river_by_col[x])
            for ry in ys:
                bridge_tiles.add((x, ry))
                # Path approach tiles immediately above and below
                if ry - 1 >= 0 and (x, ry - 1) not in river_tiles:
                    bridge_tiles.add((x, ry - 1))
                if ry + 1 < WORLD_SIZE and (x, ry + 1) not in river_tiles:
                    bridge_tiles.add((x, ry + 1))
        x += rng.randint(30, 40)

    # Bridge tiles replace river tiles at crossings
    river_tiles -= bridge_tiles

    return list(river_tiles), list(bridge_tiles)


async def generate_rivers(seed: int, db) -> None:
    """Generate rivers and bridges and store them in tile_overrides."""
    river_tiles, bridge_tiles = await asyncio.to_thread(_generate_rivers_sync, seed)

    if river_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'river')",
            [(x, y) for x, y in river_tiles],
        )

    if bridge_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'bridge')",
            [(x, y) for x, y in bridge_tiles],
        )
