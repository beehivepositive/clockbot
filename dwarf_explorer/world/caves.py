from __future__ import annotations

import asyncio
import math
import random

from dwarf_explorer.config import (
    CAVE_MIN_SIZE, CAVE_MAX_SIZE, CAVE_WALK_STEPS,
    CAVE_WALKABLE, CAVE_CHEST_TYPES, VIEWPORT_SIZE, VIEWPORT_CENTER, WORLD_SIZE,
    WALKABLE_TILES, CHEST_LOOT, CAVE_ORE_RATES, CAVE_GOLD_ORE_RATES,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.world.terrain import get_biome
from dwarf_explorer.world.noise import fbm

_CAVE_SEED_OFFSET = 9000


def _norm2(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy)
    return (dx / m, dy / m) if m > 1e-9 else (1.0, 0.0)


def _rotate2(dx: float, dy: float, angle: float) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return (c * dx - s * dy, s * dx + c * dy)


def _drunkard_walk(
    rng: random.Random,
    carved: set[tuple[int, int]],
    start_x: int, start_y: int,
    steps: int, width: int, height: int,
    room_freq: int = 8,
) -> None:
    cx, cy = start_x, start_y
    for i in range(steps):
        dx, dy = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
        nx, ny = cx + dx, cy + dy
        if 1 <= nx < width - 1 and 1 <= ny < height - 1:
            cx, cy = nx, ny
            carved.add((cx, cy))
            if i % room_freq == 0:
                room_w = rng.randint(2, 4)
                room_h = rng.randint(2, 4)
                for ry in range(room_h):
                    for rx in range(room_w):
                        rrx, rry = cx + rx, cy + ry
                        if 1 <= rrx < width - 1 and 1 <= rry < height - 1:
                            carved.add((rrx, rry))


def _perlin_worm_cave(
    rng: random.Random,
    carved: set[tuple[int, int]],
    start_x: int, start_y: int,
    worm_seed: int,
    width: int, height: int,
    steps: int,
) -> None:
    """Perlin-worm corridor — carves a 3-wide winding tunnel with occasional wide chambers."""
    x, y = float(start_x), float(start_y)
    freq = 0.07
    angle = rng.uniform(0, 2 * math.pi)
    dx, dy = math.cos(angle), math.sin(angle)

    for step in range(steps):
        ix = max(1, min(width - 2, int(round(x))))
        iy = max(1, min(height - 2, int(round(y))))
        half = 1 if step % 5 != 0 else 2   # wider chamber every 5th step
        for ddy in range(-half, half + 1):
            for ddx in range(-half, half + 1):
                nx, ny = ix + ddx, iy + ddy
                if 1 <= nx < width - 1 and 1 <= ny < height - 1:
                    carved.add((nx, ny))

        n = fbm(x * freq, y * freq, worm_seed, octaves=3)
        rot = math.radians((n - 0.5) * 160.0)
        dx, dy = _norm2(*_rotate2(dx, dy, rot))
        x = max(1.0, min(width - 2.0, x + dx))
        y = max(1.0, min(height - 2.0, y + dy))


def _carve_chamber(
    carved: set[tuple[int, int]],
    cx: int, cy: int, size: int, width: int, height: int,
) -> None:
    half = size // 2
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            nx, ny = cx + dx, cy + dy
            if 1 <= nx < width - 1 and 1 <= ny < height - 1:
                carved.add((nx, ny))


def _corridor_to_point(
    carved: set[tuple[int, int]],
    sx: int, sy: int, tx: int, ty: int,
    width: int, height: int,
) -> None:
    """Carve a 3-wide L-shaped corridor from (sx,sy) to (tx,ty) for guaranteed connectivity."""
    x, y = sx, sy
    while x != tx:
        x += 1 if x < tx else -1
        for off in (-1, 0, 1):
            nx2, ny2 = x, y + off
            if 1 <= nx2 < width - 1 and 1 <= ny2 < height - 1:
                carved.add((nx2, ny2))
    while y != ty:
        y += 1 if y < ty else -1
        for off in (-1, 0, 1):
            nx2, ny2 = x + off, y
            if 1 <= nx2 < width - 1 and 1 <= ny2 < height - 1:
                carved.add((nx2, ny2))


def _inward_step(ex: int, ey: int, edge: str, width: int, height: int) -> tuple[int, int]:
    """Return the interior tile one step inward from an edge entrance."""
    if edge == "top":    return ex, 1
    if edge == "bottom": return ex, height - 2
    if edge == "left":   return 1, ey
    return width - 2, ey   # right


def _generate_cave_interior(
    cave_id: int, seed: int, world_x: int, world_y: int,
    num_entrances: int = 1,
    cave_level: int = 1,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]], list[tuple[int, int]]]:
    """Generate a cave interior with `num_entrances` entrance holes.

    Entrance holes are spread across different edges and linked via corridors
    so all reach the same main body.  Returns (width, height, tiles, entrances, stairdown_positions).
    """
    rng = random.Random(seed + _CAVE_SEED_OFFSET + cave_id + world_x * 1000 + world_y)
    worm_seed = (seed ^ (cave_id * 0x9E37 + world_x * 31 + world_y * 97)) & 0xFFFFFFFF

    # Multi-entrance caves are proportionally larger
    extra = (num_entrances - 1) * 15
    width  = rng.randint(CAVE_MIN_SIZE + extra, CAVE_MAX_SIZE + extra)
    height = rng.randint(CAVE_MIN_SIZE + extra, CAVE_MAX_SIZE + extra)

    carved: set[tuple[int, int]] = set()

    # --- Place entrances on different edges, well spread apart ---
    edges = ["top", "bottom", "left", "right"]
    rng.shuffle(edges)
    min_spread = max(width, height) // max(num_entrances, 1)

    entrances: list[tuple[int, int]] = []
    inward: list[tuple[int, int]] = []

    for i in range(num_entrances):
        edge = edges[i % len(edges)]
        best = None
        for _ in range(30):
            if edge == "top":
                pos = (rng.randint(2, width - 3), 0)
            elif edge == "bottom":
                pos = (rng.randint(2, width - 3), height - 1)
            elif edge == "left":
                pos = (0, rng.randint(2, height - 3))
            else:
                pos = (width - 1, rng.randint(2, height - 3))

            if not entrances or min(
                abs(pos[0] - px) + abs(pos[1] - py) for px, py in entrances
            ) >= min_spread:
                best = pos
                break
        if best is None:
            best = pos   # fallback

        ex, ey = best
        entrances.append((ex, ey))
        carved.add((ex, ey))
        ix, iy = _inward_step(ex, ey, edge, width, height)
        carved.add((ix, iy))
        inward.append((ix, iy))

    # --- Primary carve from first entrance ---
    ix0, iy0 = inward[0]
    _carve_chamber(carved, ix0, iy0, 4, width, height)
    _perlin_worm_cave(rng, carved, ix0, iy0, worm_seed, width, height, CAVE_WALK_STEPS)
    _drunkard_walk(rng, carved, ix0, iy0, CAVE_WALK_STEPS // 2, width, height)

    # --- Secondary entrance corridors: L-shaped path to cave centre ---
    cx, cy = width // 2, height // 2
    for ix, iy in inward[1:]:
        _carve_chamber(carved, ix, iy, 3, width, height)
        _corridor_to_point(carved, ix, iy, cx, cy, width, height)

    # --- Branching corridors ---
    carved_list = list(carved)
    for b in range(rng.randint(2, 4)):
        if not carved_list:
            break
        bs = rng.choice(carved_list)
        bseed = (worm_seed + b * 0x1337) & 0xFFFFFFFF
        if b % 2 == 0:
            _perlin_worm_cave(rng, carved, bs[0], bs[1], bseed,
                              width, height, CAVE_WALK_STEPS // 3)
        else:
            _drunkard_walk(rng, carved, bs[0], bs[1],
                           CAVE_WALK_STEPS // 3, width, height)
        carved_list = list(carved)

    # Large central chamber
    if carved_list:
        mid = carved_list[len(carved_list) // 2]
        _carve_chamber(carved, mid[0], mid[1], 6, width, height)

    # --- Chests ---
    entrance_set = set(entrances)
    floor_tiles = [
        p for p in carved
        if p not in entrance_set
        and all(abs(p[0] - ex) + abs(p[1] - ey) > 8 for ex, ey in entrances)
    ]
    num_chests = rng.randint(2, min(6, max(2, len(floor_tiles) // 20)))
    chest_positions: set[tuple[int, int]] = set()
    if floor_tiles:
        rng.shuffle(floor_tiles)
        for pos in floor_tiles:
            if len(chest_positions) >= num_chests:
                break
            if all(abs(pos[0] - cx2) + abs(pos[1] - cy2) > 6
                   for cx2, cy2 in chest_positions):
                chest_positions.add(pos)

    # --- Cave rocks, iron ore deposits, and gold ore deposits (mineable) ---
    rock_positions: set[tuple[int, int]] = set()
    ore_positions: set[tuple[int, int]] = set()
    gold_ore_positions: set[tuple[int, int]] = set()
    rock_candidates = [
        p for p in carved
        if p not in entrance_set
        and p not in chest_positions
        and all(abs(p[0] - ex) + abs(p[1] - ey) > 4 for ex, ey in entrances)
    ]
    rng.shuffle(rock_candidates)
    rock_count = len(rock_candidates) // 8  # ~12% of floor tiles
    ore_rate = CAVE_ORE_RATES.get(cave_level, 0.0)
    gold_ore_rate = CAVE_GOLD_ORE_RATES.get(cave_level, 0.0)
    for pos in rock_candidates[:rock_count]:
        r = rng.random()
        if r < ore_rate:
            ore_positions.add(pos)
        elif r < ore_rate + gold_ore_rate:
            gold_ore_positions.add(pos)
        else:
            rock_positions.add(pos)

    # --- All chests are small (cave_chest) ---
    chest_types: dict[tuple[int, int], str] = {}
    for pos in chest_positions:
        chest_types[pos] = "cave_chest"

    # --- Stairdown entrances (if not at max depth) ---
    stairdown_positions: set[tuple[int, int]] = set()
    if cave_level < 3 and floor_tiles:
        num_stairs = rng.randint(1, 2)
        far_tiles = [p for p in floor_tiles
                     if p not in chest_positions
                     and all(abs(p[0] - ex2) + abs(p[1] - ey2) > 10 for ex2, ey2 in entrances)
                     and all(abs(p[0] - cx2) + abs(p[1] - cy2) > 8 for cx2, cy2 in chest_positions)]
        rng.shuffle(far_tiles)
        for pos in far_tiles:
            if len(stairdown_positions) >= num_stairs:
                break
            if all(abs(pos[0] - sx) + abs(pos[1] - sy) > 10 for sx, sy in stairdown_positions):
                stairdown_positions.add(pos)

    # --- Stairup (for non-level-1 caves) ---
    stairup_position: tuple[int, int] | None = None
    if cave_level > 1:
        # Place stairup near the center of the cave floor
        cx_center, cy_center = width // 2, height // 2
        center_tiles = sorted(
            [p for p in carved if p not in entrance_set and p not in chest_positions
             and p not in stairdown_positions],
            key=lambda p: abs(p[0] - cx_center) + abs(p[1] - cy_center),
        )
        if center_tiles:
            stairup_position = center_tiles[0]

    # --- Build tile list (enemies no longer placed as tiles — random encounters instead) ---
    tiles: list[tuple[int, int, str]] = []
    for y in range(height):
        for x in range(width):
            if (x, y) in entrance_set:
                tiles.append((x, y, "cave_entrance"))
            elif (x, y) == stairup_position:
                tiles.append((x, y, "cave_stairup"))
            elif (x, y) in stairdown_positions:
                tiles.append((x, y, "cave_stairdown"))
            elif (x, y) in chest_positions:
                tiles.append((x, y, chest_types[(x, y)]))
            elif (x, y) in ore_positions:
                tiles.append((x, y, "iron_ore_deposit"))
            elif (x, y) in gold_ore_positions:
                tiles.append((x, y, "gold_ore_deposit"))
            elif (x, y) in rock_positions:
                tiles.append((x, y, "cave_rock"))
            elif (x, y) in carved:
                tiles.append((x, y, "stone_floor"))
            else:
                tiles.append((x, y, "stone_wall"))

    return width, height, tiles, entrances, list(stairdown_positions)


async def _create_child_cave(
    seed: int, parent_cave_id: int,
    parent_local_x: int, parent_local_y: int,
    level: int, db,
) -> None:
    """Create a child (deeper) cave linked to a stairdown in the parent cave."""
    cursor = await db.execute(
        "INSERT INTO caves (width, height, cave_level, parent_cave_id) VALUES (1, 1, ?, ?)",
        (level, parent_cave_id),
    )
    child_cave_id = cursor.lastrowid

    width, height, tiles, _entrances, child_stairdowns = await asyncio.to_thread(
        _generate_cave_interior,
        child_cave_id, seed, parent_cave_id * 100 + parent_local_x,
        parent_local_y, 1, level,
    )

    await db.execute(
        "UPDATE caves SET width = ?, height = ? WHERE cave_id = ?",
        (width, height, child_cave_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO cave_tiles (cave_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(child_cave_id, lx, ly, tt) for lx, ly, tt in tiles],
    )

    # Find stairup position in the child cave
    stairup_row = await db.fetch_one(
        "SELECT local_x, local_y FROM cave_tiles WHERE cave_id = ? AND tile_type = 'cave_stairup'",
        (child_cave_id,),
    )
    if stairup_row:
        child_stairup_x = stairup_row["local_x"]
        child_stairup_y = stairup_row["local_y"]
    else:
        # Fallback: center of cave
        child_stairup_x = width // 2
        child_stairup_y = height // 2

    # Link stairdown in parent → stairup in child
    await db.execute(
        "INSERT OR IGNORE INTO cave_deep_entrances"
        " (parent_cave_id, parent_local_x, parent_local_y,"
        "  child_cave_id, child_local_x, child_local_y)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (parent_cave_id, parent_local_x, parent_local_y,
         child_cave_id, child_stairup_x, child_stairup_y),
    )

    # Recursively create deeper caves
    if level < 3:
        await create_deep_caves(seed, child_cave_id, level, child_stairdowns, db)


async def create_deep_caves(
    seed: int, cave_id: int, cave_level: int,
    stairdown_positions: list[tuple[int, int]], db,
) -> None:
    """Create child caves for each stairdown position."""
    for sx, sy in stairdown_positions:
        await _create_child_cave(seed, cave_id, sx, sy, cave_level + 1, db)


def _generate_lava_cave_interior(
    cave_id: int, seed: int, island_id: int, local_x: int, local_y: int,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Generate a lava cave interior for a volcano island.

    Returns (width, height, tiles, entrances).
    Lava caves use lava_wall as boundaries, lava_floor as walkable floor,
    with lava_pool rivers and lava_bridge crossings.
    Full sight (no torch needed) — cave_type set to 'lava' in DB.
    """
    rng = random.Random(seed + _CAVE_SEED_OFFSET + cave_id + island_id * 31 + local_x * 1000 + local_y)
    worm_seed = (seed ^ (cave_id * 0xBEEF + island_id * 31 + local_x * 97 + local_y)) & 0xFFFFFFFF

    # Lava caves are generous-sized
    width  = rng.randint(40, 70)
    height = rng.randint(40, 60)

    carved: set[tuple[int, int]] = set()

    # Single entrance at top center (island surface)
    ex, ey = width // 2, 0
    entrances = [(ex, ey)]
    carved.add((ex, ey))
    ix, iy = ex, 1
    carved.add((ix, iy))

    # Primary cave carve
    _carve_chamber(carved, ix, iy, 5, width, height)
    _perlin_worm_cave(rng, carved, ix, iy, worm_seed, width, height, CAVE_WALK_STEPS)
    _drunkard_walk(rng, carved, ix, iy, CAVE_WALK_STEPS // 2, width, height)

    # Branching corridors
    carved_list = list(carved)
    for b in range(rng.randint(3, 5)):
        if not carved_list:
            break
        bs = rng.choice(carved_list)
        bseed = (worm_seed + b * 0xCAFE) & 0xFFFFFFFF
        if b % 2 == 0:
            _perlin_worm_cave(rng, carved, bs[0], bs[1], bseed,
                              width, height, CAVE_WALK_STEPS // 3)
        else:
            _drunkard_walk(rng, carved, bs[0], bs[1],
                           CAVE_WALK_STEPS // 3, width, height)
        carved_list = list(carved)

    # Large central chamber
    mid = carved_list[len(carved_list) // 2]
    _carve_chamber(carved, mid[0], mid[1], 8, width, height)

    # --- Lava rivers: 2–4 horizontal or diagonal bands of lava_pool ---
    entrance_set = set(entrances)
    lava_cells: set[tuple[int, int]] = set()
    num_rivers = rng.randint(2, 4)
    for ri in range(num_rivers):
        # Choose a y-band and carve a wavy horizontal river
        river_y = rng.randint(height // 5, height - height // 5)
        rx = 1
        cur_y = river_y
        while rx < width - 1:
            if (rx, cur_y) in carved and (rx, cur_y) not in entrance_set:
                lava_cells.add((rx, cur_y))
            cur_y = max(1, min(height - 2, cur_y + rng.randint(-1, 1)))
            rx += 1

    # Place lava_bridge every 8–15 tiles along each river to allow crossing
    for (rx2, ry2) in list(lava_cells):
        # Remove from carved so river is impassable by default
        carved.discard((rx2, ry2))

    # Add bridges: for each river scan, place bridges at intervals
    bridges: set[tuple[int, int]] = set()
    sorted_lava = sorted(lava_cells, key=lambda p: p[0])
    if sorted_lava:
        bridge_interval = rng.randint(8, 15)
        for i, (rx2, ry2) in enumerate(sorted_lava):
            if i % bridge_interval == 0 and (rx2, ry2) in lava_cells:
                bridges.add((rx2, ry2))

    # Chests scattered in the cave
    floor_tiles = [
        p for p in carved
        if p not in entrance_set
        and all(abs(p[0] - ex2) + abs(p[1] - ey2) > 6 for ex2, ey2 in entrances)
    ]
    num_chests = rng.randint(2, 5)
    chest_positions: set[tuple[int, int]] = set()
    if floor_tiles:
        rng.shuffle(floor_tiles)
        for pos in floor_tiles:
            if len(chest_positions) >= num_chests:
                break
            if all(abs(pos[0] - cx2) + abs(pos[1] - cy2) > 6
                   for cx2, cy2 in chest_positions):
                chest_positions.add(pos)

    # Ore deposits in lava caves (richer than normal)
    ore_positions: set[tuple[int, int]] = set()
    ore_candidates = [p for p in carved if p not in entrance_set and p not in chest_positions]
    rng.shuffle(ore_candidates)
    for pos in ore_candidates[:len(ore_candidates) // 6]:
        r2 = rng.random()
        if r2 < 0.2:
            ore_positions.add(pos)

    # Build tile list
    tiles: list[tuple[int, int, str]] = []
    for y in range(height):
        for x in range(width):
            if (x, y) in entrance_set:
                tiles.append((x, y, "cave_entrance"))
            elif (x, y) in bridges:
                tiles.append((x, y, "lava_bridge"))
            elif (x, y) in lava_cells:
                tiles.append((x, y, "lava_pool"))
            elif (x, y) in chest_positions:
                tiles.append((x, y, "cave_chest"))
            elif (x, y) in ore_positions:
                tiles.append((x, y, "gold_ore_deposit"))
            elif (x, y) in carved:
                tiles.append((x, y, "lava_floor"))
            else:
                tiles.append((x, y, "lava_wall"))

    return width, height, tiles, entrances


async def create_island_lava_cave(
    seed: int, island_id: int, local_x: int, local_y: int, db,
) -> int:
    """Create a lava cave linked to a vol_cave tile on a volcano island.

    Returns the new cave_id.
    """
    from dwarf_explorer.database.repositories import register_island_cave

    # Check if already exists
    row = await db.fetch_one(
        "SELECT cave_id FROM island_cave_entrances"
        " WHERE island_id=? AND local_x=? AND local_y=?",
        (island_id, local_x, local_y),
    )
    if row:
        return row["cave_id"]

    # Insert cave row
    cursor = await db.execute(
        "INSERT INTO caves (width, height, cave_level, cave_type) VALUES (1, 1, 1, 'lava')"
    )
    cave_id = cursor.lastrowid

    width, height, tiles, entrances = await asyncio.to_thread(
        _generate_lava_cave_interior,
        cave_id, seed, island_id, local_x, local_y,
    )

    await db.execute(
        "UPDATE caves SET width=?, height=? WHERE cave_id=?",
        (width, height, cave_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO cave_tiles (cave_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(cave_id, lx, ly, tt) for lx, ly, tt in tiles],
    )

    # Register link
    await register_island_cave(db, island_id, local_x, local_y, cave_id)

    return cave_id


async def create_cave_system(
    seed: int, world_positions: list[tuple[int, int]], db
) -> None:
    """Pre-generate one cave interior shared by all world_positions.

    Each world tile gets its own unique cave_entrance hole.
    Skips silently if any position is already linked (idempotent).
    """
    for wx, wy in world_positions:
        existing = await db.fetch_one(
            "SELECT cave_id FROM cave_entrances WHERE world_x = ? AND world_y = ?",
            (wx, wy),
        )
        if existing:
            return   # already created (e.g. re-init)

    n = len(world_positions)
    cursor = await db.execute(
        "INSERT INTO caves (width, height, cave_level) VALUES (1, 1, 1)"
    )
    cave_id = cursor.lastrowid

    width, height, tiles, entrance_positions, stairdown_positions = await asyncio.to_thread(
        _generate_cave_interior,
        cave_id, seed, world_positions[0][0], world_positions[0][1], n, 1,
    )

    await db.execute(
        "UPDATE caves SET width = ?, height = ? WHERE cave_id = ?",
        (width, height, cave_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO cave_tiles (cave_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(cave_id, lx, ly, tt) for lx, ly, tt in tiles],
    )
    # Link each overworld tile to its own local entrance hole
    for (ex, ey), (wx, wy) in zip(entrance_positions, world_positions):
        await db.execute(
            "INSERT OR IGNORE INTO cave_entrances"
            " (cave_id, local_x, local_y, world_x, world_y) VALUES (?, ?, ?, ?, ?)",
            (cave_id, ex, ey, wx, wy),
        )

    # Deep caves are generated lazily on first descent (not during world init)


async def get_or_create_cave(
    seed: int, world_x: int, world_y: int, db
) -> tuple[int, int, int]:
    """Return (cave_id, entrance_local_x, entrance_local_y) for a given overworld tile.

    Caves are normally pre-generated by create_cave_system during world init.
    Falls back to creating a standalone single-entrance cave if not found.
    """
    row = await db.fetch_one(
        "SELECT cave_id, local_x, local_y FROM cave_entrances"
        " WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        return row["cave_id"], row["local_x"], row["local_y"]

    # Fallback: standalone single-entrance cave
    await create_cave_system(seed, [(world_x, world_y)], db)
    row = await db.fetch_one(
        "SELECT cave_id, local_x, local_y FROM cave_entrances"
        " WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    return row["cave_id"], row["local_x"], row["local_y"]


async def populate_chest_loot(chest_id: int, chest_type: str, db, lava_mode: bool = False) -> None:
    """Populate a freshly-created chest with random loot.

    lava_mode=True: use sea-themed bonus loot in addition to standard loot
    (cannonballs, seaweed, extra gold — for lava cave chests on volcano islands).
    """
    from dwarf_explorer.database.repositories import add_to_chest
    rng = random.Random(chest_id * 7331)
    weights = [t[0] for t in CHEST_LOOT]

    # All chests are small (1 loot tier)
    tier = rng.choices(CHEST_LOOT, weights=weights, k=1)[0]
    _, gold_min, gold_max, _xp_min, _xp_max, item = tier
    gold = rng.randint(gold_min, gold_max)
    if gold > 0:
        await add_to_chest(db, chest_id, "gold_coin", gold)
    if item:
        await add_to_chest(db, chest_id, item, 1)

    # Lava cave sea-themed bonus loot
    if lava_mode:
        sea_roll = rng.random()
        if sea_roll < 0.40:
            await add_to_chest(db, chest_id, "cannonball", rng.randint(1, 4))
        elif sea_roll < 0.65:
            await add_to_chest(db, chest_id, "seaweed", rng.randint(2, 6))
        elif sea_roll < 0.80:
            await add_to_chest(db, chest_id, "iron_ingot", rng.randint(2, 5))
        elif sea_roll < 0.90:
            await add_to_chest(db, chest_id, "gem", rng.randint(1, 2))
        # Extra gold for the pirate vibe
        await add_to_chest(db, chest_id, "gold_coin", rng.randint(20, 60))


async def _restore_regenerated_rocks(cave_id: int, db) -> None:
    """Restore cave_rock tiles broken 48+ hours ago, skipping spots with player houses."""
    rows = await db.fetch_all(
        "SELECT local_x, local_y FROM cave_rock_breaks"
        " WHERE cave_id = ? AND broken_at <= datetime('now', '-48 hours')",
        (cave_id,),
    )
    if not rows:
        return
    for row in rows:
        lx, ly = row["local_x"], row["local_y"]
        # Don't restore if a player-built house is standing here
        ph = await db.fetch_one(
            "SELECT house_id FROM player_houses"
            " WHERE is_cave=1 AND loc_cave_id=? AND loc_x=? AND loc_y=?",
            (cave_id, lx, ly),
        )
        if not ph:
            await db.execute(
                "UPDATE cave_tiles SET tile_type='cave_rock'"
                " WHERE cave_id=? AND local_x=? AND local_y=?",
                (cave_id, lx, ly),
            )
        await db.execute(
            "DELETE FROM cave_rock_breaks WHERE cave_id=? AND local_x=? AND local_y=?",
            (cave_id, lx, ly),
        )


async def load_cave_viewport(
    cave_id: int, center_x: int, center_y: int, db
) -> list[list[TileData]]:
    await _restore_regenerated_rocks(cave_id, db)
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half
    rows  = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM cave_tiles"
        " WHERE cave_id = ? AND local_x >= ? AND local_x <= ?"
        "   AND local_y >= ? AND local_y <= ?",
        (cave_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}
    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row.append(TileData(terrain=tile_map.get((cx, cy), "stone_wall"),
                                world_x=cx, world_y=cy))
        grid.append(row)
    return grid


async def load_cave_single_tile(cave_id: int, local_x: int, local_y: int, db) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM cave_tiles"
        " WHERE cave_id = ? AND local_x = ? AND local_y = ?",
        (cave_id, local_x, local_y),
    )
    return TileData(terrain=row["tile_type"] if row else "void",
                    world_x=local_x, world_y=local_y)
