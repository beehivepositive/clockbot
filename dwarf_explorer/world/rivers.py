from __future__ import annotations

import asyncio
import math
import random

from dwarf_explorer.config import WORLD_SIZE
from dwarf_explorer.world.noise import fbm
from dwarf_explorer.world.terrain import get_biome

_WATER_BIOMES = {"deep_water", "shallow_water"}


def _is_water(x: int, y: int, seed: int) -> bool:
    return get_biome(x, y, seed) in _WATER_BIOMES


def _generate_rivers_sync(seed: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Generate river and bridge tile positions.

    Returns (river_tiles, bridge_tiles) as lists of (x, y).
    River tiles that land on existing water biome are skipped — the river
    connects naturally to lakes/ponds instead of overriding them.
    """
    rng = random.Random(seed ^ 0xDEAD_BEEF)

    river_tiles: set[tuple[int, int]] = set()
    bridge_tiles: set[tuple[int, int]] = set()

    # ------------------------------------------------------------------
    # Main river: guaranteed to cross the entire map west -> east
    # Width: 3 tiles baseline (center ± 1), 5 tiles every 20 columns
    # ------------------------------------------------------------------
    main_river_by_col: dict[int, set[int]] = {}  # col -> set of y values

    start_y = rng.randint(40, WORLD_SIZE - 40)
    y = float(start_y)

    for x in range(WORLD_SIZE):
        cy = int(round(y))
        cy = max(8, min(WORLD_SIZE - 8, cy))

        # Baseline width: ±1 either side (3 tiles wide)
        half_w = 2 if (x % 20 == 0) else 1  # widen to 5 tiles every 20 cols
        for dy in range(-half_w, half_w + 1):
            ry = cy + dy
            if 4 <= ry < WORLD_SIZE - 4:
                if not _is_water(x, ry, seed):
                    river_tiles.add((x, ry))
                main_river_by_col.setdefault(x, set()).add(ry)

        # Drift: smooth noise-driven meander
        noise_val = fbm(x * 0.02, cy * 0.02, seed, octaves=3)
        y += (noise_val - 0.5) * 2.0
        y = max(8.0, min(WORLD_SIZE - 8.0, y))

    # ------------------------------------------------------------------
    # Tributaries (2-4): flow from top/bottom edge toward the main river
    # Curved using noise-driven horizontal offset (S-curve shape)
    # ------------------------------------------------------------------
    num_tributaries = rng.randint(2, 4)
    trib_start_cols = rng.sample(range(30, WORLD_SIZE - 30), num_tributaries)

    trib_tile_sets: list[set[tuple[int, int]]] = []

    for trib_idx, trib_col in enumerate(trib_start_cols):
        if trib_col not in main_river_by_col:
            continue

        # Target: the topmost row of the main river at this column
        target_y = min(main_river_by_col[trib_col])

        # Start from top or bottom edge
        if rng.random() < 0.5:
            ty = rng.randint(0, 10)
            direction = 1   # flows down toward river
        else:
            ty = rng.randint(WORLD_SIZE - 10, WORLD_SIZE - 1)
            direction = -1  # flows up toward river

        tx = float(trib_col)
        trib_tiles: set[tuple[int, int]] = set()

        total_dist = abs(ty - target_y)
        step = 0

        while step < WORLD_SIZE:
            iy = max(0, min(WORLD_SIZE - 1, ty))
            ix = max(0, min(WORLD_SIZE - 1, int(round(tx))))

            if not _is_water(ix, iy, seed):
                trib_tiles.add((ix, iy))

            # Stop when we reach the main river band
            if iy in main_river_by_col.get(ix, set()) or abs(iy - target_y) <= 2:
                break

            # Smooth S-curve horizontal drift via noise
            progress = step / max(total_dist, 1)
            noise_val = fbm(progress * 4.0, trib_idx * 10.0, seed ^ 0xCAFE, octaves=2)
            # Sine envelope so it curves out and back in
            envelope = math.sin(progress * math.pi)
            horiz_speed = (noise_val - 0.5) * 3.0 * envelope
            tx += horiz_speed

            # Clamp x to map bounds
            tx = max(1.0, min(WORLD_SIZE - 2.0, tx))

            ty += direction
            step += 1

        river_tiles |= trib_tiles
        trib_tile_sets.append(trib_tiles)

    # ------------------------------------------------------------------
    # Bridges
    # Main river: every 30-40 columns, span the full river width
    # Each tributary: one bridge at the midpoint of its path
    # ------------------------------------------------------------------

    # Main river bridges
    bridge_interval = rng.randint(30, 40)
    x = bridge_interval
    while x < WORLD_SIZE - bridge_interval:
        if x in main_river_by_col:
            ys = sorted(main_river_by_col[x])
            for ry in ys:
                bridge_tiles.add((x, ry))
                # Path approach tiles above and below the bridge
                approach_above = ry - 1
                approach_below = ry + 1
                if approach_above >= 0 and approach_above not in main_river_by_col.get(x, set()):
                    bridge_tiles.add((x, approach_above))
                if approach_below < WORLD_SIZE and approach_below not in main_river_by_col.get(x, set()):
                    bridge_tiles.add((x, approach_below))
        x += rng.randint(30, 40)

    # Tributary bridges: one per tributary at the midpoint
    for trib_tiles in trib_tile_sets:
        if not trib_tiles:
            continue
        trib_list = sorted(trib_tiles, key=lambda t: t[1])  # sort by y
        mid = trib_list[len(trib_list) // 2]
        mx, my = mid
        # Collect all river tiles in this column that belong to the tributary
        col_tiles = [t for t in trib_tiles if t[0] == mx]
        if not col_tiles:
            col_tiles = [mid]
        for tx_b, ty_b in col_tiles:
            bridge_tiles.add((tx_b, ty_b))
        # Approach tiles
        min_y = min(t[1] for t in col_tiles)
        max_y = max(t[1] for t in col_tiles)
        if min_y - 1 >= 0:
            bridge_tiles.add((mx, min_y - 1))
        if max_y + 1 < WORLD_SIZE:
            bridge_tiles.add((mx, max_y + 1))

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
