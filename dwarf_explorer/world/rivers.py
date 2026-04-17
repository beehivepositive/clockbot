from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import WORLD_SIZE
from dwarf_explorer.world.noise import fbm
from dwarf_explorer.world.terrain import get_biome

_WATER_BIOMES = {"deep_water", "shallow_water"}
_MIN_TRIB_SPACING = 45   # minimum x-distance between main tributary join points


def _is_water(x: int, y: int, seed: int) -> bool:
    return get_biome(x, y, seed) in _WATER_BIOMES


def _place_lake(lake_tiles: set, cx: int, cy: int, radius: int) -> None:
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= r2:
                tx, ty = cx + dx, cy + dy
                if 0 <= tx < WORLD_SIZE and 0 <= ty < WORLD_SIZE:
                    lake_tiles.add((tx, ty))


def _gen_upstream_path(
    start_x: int,
    start_y: int,
    primary_dir: int,       # -1 = north (y decreasing), +1 = south (y increasing)
    length: int,
    rng: random.Random,
    seed: int,
    idx: int,
    west_strength: float = 1.0,   # how strongly to drift westward
    meander_strength: float = 2.5, # amplitude of meander noise
) -> list[tuple[int, int]]:
    """Walk upstream from a join point.

    Flows away from the river in primary_dir, gradually curving westward.
    The first ~20% is mostly perpendicular (N/S) with little westward drift;
    after that westward drift grows, producing a curved drainage shape:

        |        ← mostly perpendicular at start
        |
         \\       ← starts curving west
          ←←←←   ← mostly westward near source

    Meanders are achieved by carrying momentum (smooth S-curves, not random jitter).
    """
    path: list[tuple[int, int]] = []
    x, y = float(start_x), float(start_y)
    momentum = 0.0   # x-momentum for smooth meanders

    for step in range(int(length * 2)):
        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))

        if not (0 <= ix < WORLD_SIZE and 0 <= iy < WORLD_SIZE):
            break
        if len(path) >= length:
            break

        # Deduplicate adjacent steps
        if not path or (ix, iy) != path[-1]:
            path.append((ix, iy))

        # Progress 0→1 over the walk
        progress = step / max(length, 1)

        # Westward drift: starts near 0, grows quadratically after 20% progress
        west_progress = max(0.0, (progress - 0.20) / 0.80)
        west_drift = west_progress ** 2 * west_strength * 0.9

        # Smooth meander via momentum (avoids jittery back-and-forth)
        noise_val = fbm(step * 0.06, idx * 23.7 + 5.1, seed ^ 0xBEEF, octaves=3)
        momentum = momentum * 0.65 + (noise_val - 0.5) * meander_strength
        # Cap momentum to prevent runaway drift
        momentum = max(-3.0, min(3.0, momentum))

        x += -west_drift + momentum   # westward drift + smooth meander
        y += primary_dir              # step in primary direction
        x = max(1.0, min(WORLD_SIZE - 2.0, x))

    return path


def _gen_branch_path(
    start_x: int,
    start_y: int,
    dir_x: int,   # primary horizontal direction (-1=west, 1=east)
    dir_y: int,   # primary vertical component (usually small)
    length: int,
    rng: random.Random,
    seed: int,
    idx: int,
) -> list[tuple[int, int]]:
    """Generate a sub-branch path, flowing mostly in dir_x direction."""
    path: list[tuple[int, int]] = []
    x, y = float(start_x), float(start_y)
    momentum = 0.0

    for step in range(length):
        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))
        if not (0 <= ix < WORLD_SIZE and 0 <= iy < WORLD_SIZE):
            break
        if not path or (ix, iy) != path[-1]:
            path.append((ix, iy))

        noise_val = fbm(step * 0.09, idx * 31.4 + 2.7, seed ^ 0xDEAD, octaves=2)
        momentum = momentum * 0.6 + (noise_val - 0.5) * 2.0
        momentum = max(-2.0, min(2.0, momentum))

        x += float(dir_x)
        y += float(dir_y) + momentum * (1.0 if dir_x != 0 else 0.0)
        if dir_x == 0:
            x += momentum
        x = max(0.0, min(WORLD_SIZE - 1.0, x))
        y = max(0.0, min(WORLD_SIZE - 1.0, y))

    return path


def _gen_offshoot_path(
    start_x: int,
    start_y: int,
    dir_x: int,   # primary direction away from parent
    dir_y: int,
    length: int,
    rng: random.Random,
    seed: int,
    idx: int,
) -> list[tuple[int, int]]:
    """Generate a short, strongly meandering offshoot that ends in a pond."""
    path: list[tuple[int, int]] = []
    x, y = float(start_x), float(start_y)

    for step in range(length):
        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))
        if not (0 <= ix < WORLD_SIZE and 0 <= iy < WORLD_SIZE):
            break
        if not path or (ix, iy) != path[-1]:
            path.append((ix, iy))

        # High-amplitude random wander so offshoot is visually distinct
        wx = float(dir_x) + (rng.random() - 0.5) * 3.0
        wy = float(dir_y) + (rng.random() - 0.5) * 3.0
        x += wx
        y += wy
        x = max(0.0, min(WORLD_SIZE - 1.0, x))
        y = max(0.0, min(WORLD_SIZE - 1.0, y))

    return path


def _widen(river_tiles: set, path: list[tuple[int, int]], half_w: int, seed: int) -> None:
    """Add tiles ±half_w in the x direction to widen a primarily N-S path."""
    for px, py in path:
        for dx in range(-half_w, half_w + 1):
            nx = px + dx
            if 0 <= nx < WORLD_SIZE and not _is_water(nx, py, seed):
                river_tiles.add((nx, py))


def _generate_rivers_sync(
    seed: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    """
    River generation algorithm (from river outward):

    1. Main river: W→E, gentle meanders, 3-5 tiles wide.
    2. Main tributaries: branch FROM the river, walk upstream (N or S) with
       westward drift and smooth meanders. 3 tiles wide. Minimum spacing enforced;
       if a candidate join point is too close to an existing tributary, the new
       tributary branches from the existing one instead (flows into the other).
    3. Sub-branches: 1-2 tiles wide, branch from tributary mid-sections.
    4. Offshoots: 1 tile wide, strongly meandering channels that end in ponds.
       Go in a direction perpendicular to their parent so they look distinct.
    5. Source lakes at path endpoints if within map bounds.
    6. Main river bridges (N-S crossing), tributary bridges (E-W crossing).
    7. Existing water biome tiles are skipped (rivers connect naturally to lakes).

    Returns (river_tiles, bridge_tiles, lake_tiles).
    """
    rng = random.Random(seed ^ 0xDEAD_BEEF)

    river_tiles: set[tuple[int, int]] = set()
    bridge_tiles: set[tuple[int, int]] = set()
    lake_tiles: set[tuple[int, int]] = set()

    # -----------------------------------------------------------------------
    # MAIN RIVER — west → east, gentle meanders
    # -----------------------------------------------------------------------
    main_center: list[int] = []   # center y for each x column
    main_river_ys: dict[int, set[int]] = {}  # all river y values per column

    fy = float(rng.randint(40, WORLD_SIZE - 40))
    m_momentum = 0.0

    for x in range(WORLD_SIZE):
        cy = max(8, min(WORLD_SIZE - 8, int(round(fy))))
        main_center.append(cy)

        # Width: 3 baseline, 5 every 20 columns
        half_w = 2 if (x % 20 == 0) else 1
        for dy in range(-half_w, half_w + 1):
            ry = cy + dy
            if 4 <= ry < WORLD_SIZE - 4:
                if not _is_water(x, ry, seed):
                    river_tiles.add((x, ry))
                main_river_ys.setdefault(x, set()).add(ry)

        # Gentle meander via momentum (main river meanders less than tributaries)
        noise_val = fbm(x * 0.015, fy * 0.015, seed, octaves=2)
        m_momentum = m_momentum * 0.80 + (noise_val - 0.5) * 0.8
        m_momentum = max(-1.5, min(1.5, m_momentum))
        fy += m_momentum
        fy = max(8.0, min(WORLD_SIZE - 8.0, fy))

    # -----------------------------------------------------------------------
    # MAIN TRIBUTARIES — start at river, walk upstream with westward drift
    # -----------------------------------------------------------------------
    # Pick candidate join points; enforce _MIN_TRIB_SPACING between them.
    # If a candidate is too close to an existing trib, branch from that trib.
    num_tribs = rng.randint(3, 5)
    candidate_xs = sorted(rng.sample(range(20, WORLD_SIZE - 20), min(20, WORLD_SIZE - 40)))

    placed_tribs: list[tuple[int, list[tuple[int, int]]]] = []  # (join_x, path)
    trib_paths_for_bridges: list[list[tuple[int, int]]] = []

    for t_idx, join_x in enumerate(candidate_xs):
        if len(placed_tribs) >= num_tribs:
            break

        join_y = main_center[join_x]

        # Check proximity to existing tribs on the main river
        too_close = False
        close_trib_path: list[tuple[int, int]] | None = None
        for ex_join_x, ex_path in placed_tribs:
            if abs(join_x - ex_join_x) < _MIN_TRIB_SPACING:
                too_close = True
                close_trib_path = ex_path
                break

        if too_close and close_trib_path:
            # Branch from the close tributary instead (flows into the other)
            if len(close_trib_path) >= 6:
                start_idx = rng.randint(len(close_trib_path) // 4,
                                        3 * len(close_trib_path) // 4)
                bsx, bsy = close_trib_path[start_idx]
                # Branch direction: perpendicular to the trib (E or W)
                dir_x = rng.choice([-1, 1])
                br_len = rng.randint(15, 35)
                br_path = _gen_branch_path(bsx, bsy, dir_x, 0, br_len, rng, seed, t_idx + 100)
                _widen(river_tiles, br_path, 0, seed)   # sub-branches: width 1
                if br_path:
                    end = br_path[-1]
                    if 5 < end[0] < WORLD_SIZE - 5 and 5 < end[1] < WORLD_SIZE - 5:
                        _place_lake(lake_tiles, end[0], end[1], rng.randint(2, 3))
            continue

        # New main tributary
        # Direction: go toward the nearer map edge
        go_north = join_y > WORLD_SIZE // 2
        direction = -1 if go_north else 1   # -1 = north, +1 = south

        if go_north:
            max_dist = join_y - 5
        else:
            max_dist = WORLD_SIZE - join_y - 5

        length = rng.randint(max(25, int(max_dist * 0.45)), int(max_dist * 0.90))

        trib_path = _gen_upstream_path(
            join_x, join_y, direction, length, rng, seed, t_idx,
            west_strength=1.2, meander_strength=2.8,
        )

        if not trib_path:
            continue

        # Widen tributary: 3 tiles (±1 in x since it flows mostly N/S)
        _widen(river_tiles, trib_path, 1, seed)

        placed_tribs.append((join_x, trib_path))
        trib_paths_for_bridges.append(trib_path)

        # Source lake or map edge (no lake if end is at/near map boundary)
        end_x, end_y = trib_path[-1]
        at_edge = end_x <= 4 or end_x >= WORLD_SIZE - 4 or \
                  end_y <= 4 or end_y >= WORLD_SIZE - 4
        if not at_edge:
            _place_lake(lake_tiles, end_x, end_y, rng.randint(3, 5))

        # -------------------------------------------------------------------
        # SUB-BRANCHES from this tributary
        # -------------------------------------------------------------------
        num_branches = rng.randint(1, 3)
        branch_anchors: list[tuple[int, int]] = []
        mid_path = trib_path[len(trib_path) // 4: 3 * len(trib_path) // 4]

        for _ in range(num_branches * 4):
            if len(branch_anchors) >= num_branches or not mid_path:
                break
            candidate = rng.choice(mid_path)
            if not branch_anchors or all(
                abs(candidate[0] - bx) + abs(candidate[1] - by) > 12
                for bx, by in branch_anchors
            ):
                branch_anchors.append(candidate)

        for b_idx, (bx, by) in enumerate(branch_anchors):
            # Branches go E or W (perpendicular to N-S trib), with slight N/S drift
            dir_x = rng.choice([-1, -1, 1])  # slight west preference
            dir_y = rng.choice([-1, 0, 0, 0, 1])
            br_len = rng.randint(12, 30)
            br_path = _gen_branch_path(bx, by, dir_x, dir_y, br_len, rng, seed, t_idx * 10 + b_idx)

            if not br_path:
                continue

            _widen(river_tiles, br_path, 0, seed)  # width 1

            # Source lake at branch end (if in bounds)
            br_end = br_path[-1]
            at_edge = br_end[0] <= 4 or br_end[0] >= WORLD_SIZE - 4 or \
                      br_end[1] <= 4 or br_end[1] >= WORLD_SIZE - 4
            if not at_edge and rng.random() < 0.55:
                _place_lake(lake_tiles, br_end[0], br_end[1], rng.randint(2, 3))

            # OFFSHOOTS from this branch: go N or S (perpendicular to E/W branch)
            if br_path and rng.random() < 0.45:
                off_anchor = rng.choice(br_path)
                off_dir_y = rng.choice([-1, 1])
                off_len = rng.randint(6, 14)
                off_path = _gen_offshoot_path(
                    off_anchor[0], off_anchor[1], 0, off_dir_y,
                    off_len, rng, seed, t_idx * 100 + b_idx,
                )
                for pt in off_path:
                    if not _is_water(pt[0], pt[1], seed):
                        river_tiles.add(pt)
                if off_path:
                    off_end = off_path[-1]
                    at_edge = off_end[0] <= 4 or off_end[0] >= WORLD_SIZE - 4 or \
                              off_end[1] <= 4 or off_end[1] >= WORLD_SIZE - 4
                    if not at_edge:
                        _place_lake(lake_tiles, off_end[0], off_end[1], rng.randint(2, 3))

        # -------------------------------------------------------------------
        # OFFSHOOTS from main tributary: go E or W (perpendicular to N-S trib)
        # -------------------------------------------------------------------
        num_offshoots = rng.randint(1, 3)
        for o_idx in range(num_offshoots):
            if not trib_path:
                break
            anchor_idx = rng.randint(len(trib_path) // 5, 4 * len(trib_path) // 5)
            ox, oy = trib_path[anchor_idx]
            off_dir_x = rng.choice([-1, 1])
            off_len = rng.randint(8, 18)
            off_path = _gen_offshoot_path(
                ox, oy, off_dir_x, 0, off_len, rng, seed, t_idx * 1000 + o_idx,
            )
            for pt in off_path:
                if not _is_water(pt[0], pt[1], seed):
                    river_tiles.add(pt)
            if off_path:
                off_end = off_path[-1]
                at_edge = off_end[0] <= 4 or off_end[0] >= WORLD_SIZE - 4 or \
                          off_end[1] <= 4 or off_end[1] >= WORLD_SIZE - 4
                if not at_edge:
                    _place_lake(lake_tiles, off_end[0], off_end[1], rng.randint(2, 3))

    # -----------------------------------------------------------------------
    # MAIN RIVER BRIDGES — N-S crossing of E-W river
    # -----------------------------------------------------------------------
    bridge_interval = rng.randint(28, 40)
    bx = bridge_interval
    while bx < WORLD_SIZE - bridge_interval:
        if bx in main_river_ys:
            ys = sorted(main_river_ys[bx])
            for ry in ys:
                bridge_tiles.add((bx, ry))
            min_y, max_y = min(ys), max(ys)
            if min_y - 1 >= 0 and (bx, min_y - 1) not in river_tiles:
                bridge_tiles.add((bx, min_y - 1))
            if max_y + 1 < WORLD_SIZE and (bx, max_y + 1) not in river_tiles:
                bridge_tiles.add((bx, max_y + 1))
        bx += rng.randint(28, 40)

    # -----------------------------------------------------------------------
    # TRIBUTARY BRIDGES — E-W crossing of N-S tributary (3 tiles wide in x)
    # -----------------------------------------------------------------------
    for t_path in trib_paths_for_bridges:
        if not t_path:
            continue
        mid = t_path[len(t_path) // 2]
        mx, my = mid

        # Bridge spans the full width (±1 in x) at this row
        for dx in range(-1, 2):
            bridge_tiles.add((mx + dx, my))
        # E-W approach tiles just outside the tributary width
        if mx - 2 >= 0 and (mx - 2, my) not in river_tiles:
            bridge_tiles.add((mx - 2, my))
        if mx + 2 < WORLD_SIZE and (mx + 2, my) not in river_tiles:
            bridge_tiles.add((mx + 2, my))

    # Bridges replace river tiles; lakes are independent
    river_tiles -= bridge_tiles
    lake_tiles -= river_tiles
    lake_tiles -= bridge_tiles

    return list(river_tiles), list(bridge_tiles), list(lake_tiles)


async def generate_rivers(seed: int, db) -> None:
    """Generate rivers, bridges, and lakes; store in tile_overrides."""
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
