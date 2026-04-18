from __future__ import annotations

import asyncio
import math
import random

from dwarf_explorer.config import (
    CAVE_MIN_SIZE, CAVE_MAX_SIZE, CAVE_WALK_STEPS,
    CAVE_WALKABLE, INTERIOR_VIEWPORT_SIZE, INTERIOR_VIEWPORT_CENTER, WORLD_SIZE,
    WALKABLE_TILES, CHEST_LOOT,
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
    """Carve an L-shaped corridor from (sx,sy) to (tx,ty) for guaranteed connectivity."""
    x, y = sx, sy
    while x != tx:
        x += 1 if x < tx else -1
        if 1 <= x < width - 1 and 1 <= y < height - 1:
            carved.add((x, y))
    while y != ty:
        y += 1 if y < ty else -1
        if 1 <= x < width - 1 and 1 <= y < height - 1:
            carved.add((x, y))


def _inward_step(ex: int, ey: int, edge: str, width: int, height: int) -> tuple[int, int]:
    """Return the interior tile one step inward from an edge entrance."""
    if edge == "top":    return ex, 1
    if edge == "bottom": return ex, height - 2
    if edge == "left":   return 1, ey
    return width - 2, ey   # right


def _generate_cave_interior(
    cave_id: int, seed: int, world_x: int, world_y: int,
    num_entrances: int = 1,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Generate a cave interior with `num_entrances` entrance holes.

    Entrance holes are spread across different edges and linked via corridors
    so all reach the same main body.  Returns (width, height, tiles, entrances).
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

    # --- Build tile list ---
    tiles: list[tuple[int, int, str]] = []
    for y in range(height):
        for x in range(width):
            if (x, y) in entrance_set:
                tiles.append((x, y, "cave_entrance"))
            elif (x, y) in chest_positions:
                tiles.append((x, y, "cave_chest"))
            elif (x, y) in carved:
                tiles.append((x, y, "stone_floor"))
            else:
                tiles.append((x, y, "stone_wall"))

    return width, height, tiles, entrances


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
    cursor = await db.execute("INSERT INTO caves (width, height) VALUES (1, 1)")
    cave_id = cursor.lastrowid

    width, height, tiles, entrance_positions = await asyncio.to_thread(
        _generate_cave_interior,
        cave_id, seed, world_positions[0][0], world_positions[0][1], n,
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


async def open_chest(cave_id: int, local_x: int, local_y: int, db) -> dict:
    rng = random.Random(cave_id * 9999 + local_x * 100 + local_y)
    weights = [t[0] for t in CHEST_LOOT]
    tier = rng.choices(CHEST_LOOT, weights=weights, k=1)[0]
    _, gold_min, gold_max, xp_min, xp_max, item = tier
    gold = rng.randint(gold_min, gold_max)
    xp   = rng.randint(xp_min, xp_max)
    await db.execute(
        "UPDATE cave_tiles SET tile_type = 'stone_floor'"
        " WHERE cave_id = ? AND local_x = ? AND local_y = ?",
        (cave_id, local_x, local_y),
    )
    return {"gold": gold, "xp": xp, "item": item}


async def load_cave_viewport(
    cave_id: int, center_x: int, center_y: int, db
) -> list[list[TileData]]:
    half  = INTERIOR_VIEWPORT_CENTER
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
    for local_y in range(INTERIOR_VIEWPORT_SIZE):
        row: list[TileData] = []
        for local_x in range(INTERIOR_VIEWPORT_SIZE):
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
