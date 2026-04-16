from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import (
    CAVE_MIN_SIZE, CAVE_MAX_SIZE, CAVE_WALK_STEPS,
    CAVE_WALKABLE, VIEWPORT_SIZE, VIEWPORT_CENTER, WORLD_SIZE,
)
from dwarf_explorer.world.generator import TileData

_CAVE_SEED_OFFSET = 9000


def _generate_cave_interior(
    cave_id: int, seed: int, world_x: int, world_y: int,
    extra_entrances: list[tuple[int, int]] | None = None,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Generate a cave interior layout using drunkard's walk + rooms.

    Returns (width, height, tiles, entrance_positions).
    tiles is list of (local_x, local_y, tile_type).
    entrance_positions is list of (local_x, local_y) for each entrance.
    """
    rng = random.Random(seed + _CAVE_SEED_OFFSET + cave_id + world_x * 1000 + world_y)

    width = rng.randint(CAVE_MIN_SIZE, CAVE_MAX_SIZE)
    height = rng.randint(CAVE_MIN_SIZE, CAVE_MAX_SIZE)

    # Start with all walls
    carved: set[tuple[int, int]] = set()

    # Place primary entrance on a random edge
    edge = rng.choice(["top", "bottom", "left", "right"])
    if edge == "top":
        ex, ey = rng.randint(2, width - 3), 0
    elif edge == "bottom":
        ex, ey = rng.randint(2, width - 3), height - 1
    elif edge == "left":
        ex, ey = 0, rng.randint(2, height - 3)
    else:
        ex, ey = width - 1, rng.randint(2, height - 3)

    entrances: list[tuple[int, int]] = [(ex, ey)]
    carved.add((ex, ey))

    # Drunkard's walk from entrance
    cx, cy = ex, ey
    # Move one step inward first
    if edge == "top":
        cy = 1
    elif edge == "bottom":
        cy = height - 2
    elif edge == "left":
        cx = 1
    else:
        cx = width - 2
    carved.add((cx, cy))

    steps = rng.randint(CAVE_WALK_STEPS - 10, CAVE_WALK_STEPS + 10)
    for i in range(steps):
        dx, dy = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
        nx, ny = cx + dx, cy + dy
        # Stay within interior bounds (1 to size-2)
        if 1 <= nx < width - 1 and 1 <= ny < height - 1:
            cx, cy = nx, ny
            carved.add((cx, cy))

            # Every 12 steps, carve a small room
            if i % 12 == 0:
                room_size = rng.choice([2, 3])
                for ry in range(room_size):
                    for rx in range(room_size):
                        rrx, rry = cx + rx, cy + ry
                        if 1 <= rrx < width - 1 and 1 <= rry < height - 1:
                            carved.add((rrx, rry))

    # 50% chance: add a second entrance/exit at a distant position
    if rng.random() < 0.5 and len(carved) > 10:
        # Pick the carved tile furthest from the primary entrance
        best_dist = 0
        best_pos = None
        for pos in carved:
            d = abs(pos[0] - ex) + abs(pos[1] - ey)
            if d > best_dist:
                best_dist = d
                best_pos = pos

        if best_pos and best_dist > 6:
            # Place exit on nearest edge from that position
            bx, by = best_pos
            candidates = []
            if by <= 2:
                candidates.append((bx, 0))
            if by >= height - 3:
                candidates.append((bx, height - 1))
            if bx <= 2:
                candidates.append((0, by))
            if bx >= width - 3:
                candidates.append((width - 1, by))

            if not candidates:
                # Pick closest edge
                dists = [
                    (by, (bx, 0)),
                    (height - 1 - by, (bx, height - 1)),
                    (bx, (0, by)),
                    (width - 1 - bx, (width - 1, by)),
                ]
                dists.sort()
                candidates = [dists[0][1]]

            exit_pos = rng.choice(candidates)
            entrances.append(exit_pos)
            carved.add(exit_pos)
            # Carve path from best_pos to exit
            px, py = best_pos
            tx, ty = exit_pos
            while px != tx or py != ty:
                if px < tx:
                    px += 1
                elif px > tx:
                    px -= 1
                if py < ty:
                    py += 1
                elif py > ty:
                    py -= 1
                carved.add((px, py))

    # Build tile list
    tiles: list[tuple[int, int, str]] = []
    entrance_set = set(entrances)
    for y in range(height):
        for x in range(width):
            if (x, y) in entrance_set:
                tiles.append((x, y, "cave_entrance"))
            elif (x, y) in carved:
                tiles.append((x, y, "stone_floor"))
            else:
                tiles.append((x, y, "stone_wall"))

    return width, height, tiles, entrances


async def get_or_create_cave(
    seed: int, world_x: int, world_y: int, db
) -> tuple[int, int, int]:
    """Get or create a cave at the given wilderness position.

    Returns (cave_id, entrance_local_x, entrance_local_y).
    """
    # Check if cave already exists for this position
    row = await db.fetch_one(
        "SELECT cave_id, local_x, local_y FROM cave_entrances WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        return row["cave_id"], row["local_x"], row["local_y"]

    # Generate new cave — use a temporary cave_id from insert
    # We need the cave_id for seeding, so insert first then generate
    cursor = await db.execute(
        "INSERT INTO caves (width, height) VALUES (1, 1)"
    )
    cave_id = cursor.lastrowid

    # Find other cave tile_overrides adjacent to this position that don't have caves yet
    # (for multi-entrance caves connecting to nearby wilderness cave tiles)
    extra_entrances_world: list[tuple[int, int]] = []
    for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
        nx, ny = world_x + ddx, world_y + ddy
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            tile_row = await db.fetch_one(
                "SELECT tile_type FROM tile_overrides WHERE world_x = ? AND world_y = ?",
                (nx, ny),
            )
            if tile_row and tile_row["tile_type"] == "cave":
                # Check if this tile already belongs to a cave
                existing = await db.fetch_one(
                    "SELECT cave_id FROM cave_entrances WHERE world_x = ? AND world_y = ?",
                    (nx, ny),
                )
                if not existing:
                    extra_entrances_world.append((nx, ny))

    width, height, tiles, entrance_positions = await asyncio.to_thread(
        _generate_cave_interior, cave_id, seed, world_x, world_y
    )

    # Update cave dimensions
    await db.execute(
        "UPDATE caves SET width = ?, height = ? WHERE cave_id = ?",
        (width, height, cave_id),
    )

    # Store tiles
    await db.executemany(
        "INSERT OR IGNORE INTO cave_tiles (cave_id, local_x, local_y, tile_type) VALUES (?, ?, ?, ?)",
        [(cave_id, lx, ly, tt) for lx, ly, tt in tiles],
    )

    # Link primary entrance to wilderness position
    primary_ex, primary_ey = entrance_positions[0]
    await db.execute(
        "INSERT OR IGNORE INTO cave_entrances (cave_id, local_x, local_y, world_x, world_y) "
        "VALUES (?, ?, ?, ?, ?)",
        (cave_id, primary_ex, primary_ey, world_x, world_y),
    )

    # Link secondary entrance if it exists and there's a nearby cave tile
    if len(entrance_positions) > 1 and extra_entrances_world:
        sec_ex, sec_ey = entrance_positions[1]
        sec_wx, sec_wy = extra_entrances_world[0]
        await db.execute(
            "INSERT OR IGNORE INTO cave_entrances (cave_id, local_x, local_y, world_x, world_y) "
            "VALUES (?, ?, ?, ?, ?)",
            (cave_id, sec_ex, sec_ey, sec_wx, sec_wy),
        )

    return cave_id, primary_ex, primary_ey


async def load_cave_viewport(
    cave_id: int, center_x: int, center_y: int, db
) -> list[list[TileData]]:
    """Load a 9x9 viewport within a cave, centered on (center_x, center_y).

    Out-of-bounds or non-existent tiles render as stone_wall.
    """
    half = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    # Fetch all cave tiles in the viewport range
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM cave_tiles "
        "WHERE cave_id = ? AND local_x >= ? AND local_x <= ? AND local_y >= ? AND local_y <= ?",
        (cave_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map: dict[tuple[int, int], str] = {}
    for r in rows:
        tile_map[(r["local_x"], r["local_y"])] = r["tile_type"]

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            tile_type = tile_map.get((cx, cy), "stone_wall")
            row.append(TileData(terrain=tile_type, world_x=cx, world_y=cy))
        grid.append(row)

    return grid


async def load_cave_single_tile(cave_id: int, local_x: int, local_y: int, db) -> TileData:
    """Load a single cave tile for walkability checks."""
    row = await db.fetch_one(
        "SELECT tile_type FROM cave_tiles WHERE cave_id = ? AND local_x = ? AND local_y = ?",
        (cave_id, local_x, local_y),
    )
    tile_type = row["tile_type"] if row else "void"
    return TileData(terrain=tile_type, world_x=local_x, world_y=local_y)
