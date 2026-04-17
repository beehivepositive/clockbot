from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import WORLD_SIZE
from dwarf_explorer.world.noise import fbm
from dwarf_explorer.world.terrain import get_biome

_WATER_BIOMES = {"deep_water", "shallow_water"}


def _is_water(x: int, y: int, seed: int) -> bool:
    return get_biome(x, y, seed) in _WATER_BIOMES


def _place_lake(lake_tiles: set[tuple[int, int]], cx: int, cy: int, radius: int) -> None:
    """Carve a roughly circular lake of shallow_water tiles."""
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= r2:
                x, y = cx + dx, cy + dy
                if 0 <= x < WORLD_SIZE and 0 <= y < WORLD_SIZE:
                    lake_tiles.add((x, y))


def _generate_rivers_sync(
    seed: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    """Generate river, bridge, and lake tile positions.

    Main river flows west→east.
    Tributaries flow from north/south and curve eastward (in the direction of
    flow) as they approach the main river, creating natural confluences.
    Source lakes are placed at each tributary's origin.
    Side-pool lakes branch off tributaries as offshoots.

    Returns (river_tiles, bridge_tiles, lake_tiles).
    River/bridge tiles skip positions where the base biome is already water.
    """
    rng = random.Random(seed ^ 0xDEAD_BEEF)

    river_tiles: set[tuple[int, int]] = set()
    bridge_tiles: set[tuple[int, int]] = set()
    lake_tiles: set[tuple[int, int]] = set()

    # ------------------------------------------------------------------
    # Main river: west → east across the full map
    # Width: 3 tiles baseline (±1), widened to 5 (±2) every 20 columns
    # ------------------------------------------------------------------
    main_river_by_col: dict[int, set[int]] = {}

    start_y = rng.randint(40, WORLD_SIZE - 40)
    fy = float(start_y)

    for x in range(WORLD_SIZE):
        cy = max(8, min(WORLD_SIZE - 8, int(round(fy))))

        half_w = 2 if (x % 20 == 0) else 1
        for dy in range(-half_w, half_w + 1):
            ry = cy + dy
            if 4 <= ry < WORLD_SIZE - 4:
                if not _is_water(x, ry, seed):
                    river_tiles.add((x, ry))
                main_river_by_col.setdefault(x, set()).add(ry)

        # Smooth noise-driven meander
        noise_val = fbm(x * 0.02, cy * 0.02, seed, octaves=3)
        fy += (noise_val - 0.5) * 2.0
        fy = max(8.0, min(WORLD_SIZE - 8.0, fy))

    # ------------------------------------------------------------------
    # Tributaries (2-4): flow from top/bottom edge toward the main river.
    #
    # Flow shape: mostly vertical at first, then curving eastward (+x) in
    # the final stretch so they join the main river like a natural confluence.
    #
    #   |           ← flows south at first
    #   |
    #    \          ← starts bending east
    #     \
    #      ------→  ← merges into main river heading east
    #
    # Source lake placed at each tributary's starting point.
    # Side-pool lakes branched off as offshoots (not inline).
    # ------------------------------------------------------------------
    num_tributaries = rng.randint(2, 4)
    # Spread tributaries across the western 3/4 of the map so the curves
    # have room to develop before the east edge
    trib_start_cols = sorted(rng.sample(range(20, int(WORLD_SIZE * 0.75)), num_tributaries))

    trib_tile_sets: list[set[tuple[int, int]]] = []

    for trib_idx, trib_col in enumerate(trib_start_cols):
        if trib_col not in main_river_by_col:
            continue

        main_ys = sorted(main_river_by_col[trib_col])

        # Choose from-top or from-bottom
        from_top = rng.random() < 0.5
        if from_top:
            lake_cy = rng.randint(5, 18)
            target_y = min(main_ys) - 1
            direction = 1          # flows southward (increasing y)
        else:
            lake_cy = rng.randint(WORLD_SIZE - 18, WORLD_SIZE - 5)
            target_y = max(main_ys) + 1
            direction = -1         # flows northward (decreasing y)

        # --- Source lake at tributary origin ---
        lake_radius = rng.randint(3, 5)
        _place_lake(lake_tiles, trib_col, lake_cy, lake_radius)

        # Tributary starts at the lake edge facing the main river
        fx = float(trib_col)
        fy_t = float(lake_cy + direction * (lake_radius + 1))

        trib_tiles: set[tuple[int, int]] = set()
        total_dist = max(abs(fy_t - target_y), 1)
        step = 0

        while step < WORLD_SIZE * 2:
            iy = max(0, min(WORLD_SIZE - 1, int(round(fy_t))))
            ix = max(0, min(WORLD_SIZE - 1, int(round(fx))))

            # Stop when we reach the main river band
            if iy in main_river_by_col.get(ix, set()) or abs(iy - target_y) <= 2:
                break

            # Skip tiles that are already water (natural connection)
            if not _is_water(ix, iy, seed) and (ix, iy) not in lake_tiles:
                trib_tiles.add((ix, iy))

            progress = step / total_dist  # 0.0 → 1.0+

            # Noise gives gentle natural variation
            noise_val = fbm(progress * 5.0, trib_idx * 20.0 + 7.3, seed ^ 0xCAFE, octaves=2)
            base_curve = (noise_val - 0.5) * 1.2

            # Eastward pull: begins at progress=0.35, grows quadratically,
            # peaks at ~2.5 tiles/step to create a pronounced eastward curve
            east_factor = max(0.0, (progress - 0.35) / 0.65)
            eastward_pull = east_factor * east_factor * 2.5

            fx += base_curve + eastward_pull
            fx = max(1.0, min(WORLD_SIZE - 2.0, fx))
            fy_t += direction
            step += 1

        # --- Side-pool offshoots (2-4 per tributary, off to the side) ---
        trib_list = sorted(trib_tiles, key=lambda t: t[1])
        if trib_list:
            num_pools = rng.randint(2, 4)
            quarter = max(1, len(trib_list) // 4)
            mid_section = trib_list[quarter: 3 * quarter]
            for _ in range(num_pools):
                if not mid_section:
                    break
                anchor = rng.choice(mid_section)
                side = rng.choice([-1, 1])
                pool_cx = anchor[0] + side * rng.randint(2, 4)
                pool_cy = anchor[1]
                if 0 <= pool_cx < WORLD_SIZE:
                    _place_lake(lake_tiles, pool_cx, pool_cy, rng.randint(2, 3))

        river_tiles |= trib_tiles
        trib_tile_sets.append(trib_tiles)

    # ------------------------------------------------------------------
    # Main river bridges: N-S crossing of the E-W flowing river
    # Bridge spans the full river width; approach tiles north & south
    # ------------------------------------------------------------------
    bridge_interval = rng.randint(30, 40)
    x = bridge_interval
    while x < WORLD_SIZE - bridge_interval:
        if x in main_river_by_col:
            ys = sorted(main_river_by_col[x])
            for ry in ys:
                bridge_tiles.add((x, ry))
            min_y, max_y = min(ys), max(ys)
            # Approach tiles above and below (N-S crossing)
            if min_y - 1 >= 0 and (x, min_y - 1) not in river_tiles:
                bridge_tiles.add((x, min_y - 1))
            if max_y + 1 < WORLD_SIZE and (x, max_y + 1) not in river_tiles:
                bridge_tiles.add((x, max_y + 1))
        x += rng.randint(30, 40)

    # ------------------------------------------------------------------
    # Tributary bridges: E-W crossing of the N-S flowing tributary
    # Single bridge tile at midpoint; approach tiles east & west
    # ------------------------------------------------------------------
    for trib_tiles in trib_tile_sets:
        if not trib_tiles:
            continue
        trib_list = sorted(trib_tiles, key=lambda t: t[1])
        mid = trib_list[len(trib_list) // 2]
        mx, my = mid

        bridge_tiles.add((mx, my))
        # E-W approach tiles (perpendicular to the N-S tributary flow)
        if mx - 1 >= 0 and (mx - 1, my) not in river_tiles:
            bridge_tiles.add((mx - 1, my))
        if mx + 1 < WORLD_SIZE and (mx + 1, my) not in river_tiles:
            bridge_tiles.add((mx + 1, my))

    # Bridges replace river tiles at crossings; lakes are independent
    river_tiles -= bridge_tiles
    lake_tiles -= river_tiles
    lake_tiles -= bridge_tiles

    return list(river_tiles), list(bridge_tiles), list(lake_tiles)


async def generate_rivers(seed: int, db) -> None:
    """Generate rivers, bridges, and source/side lakes; store in tile_overrides."""
    river_tiles, bridge_tiles, lake_tiles = await asyncio.to_thread(
        _generate_rivers_sync, seed
    )

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
    if lake_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'shallow_water')",
            [(x, y) for x, y in lake_tiles],
        )
