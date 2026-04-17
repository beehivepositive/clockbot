from __future__ import annotations

import asyncio
import random

from dwarf_explorer.config import (
    CAVE_MIN_SIZE, CAVE_MAX_SIZE, CAVE_WALK_STEPS,
    CAVE_WALKABLE, VIEWPORT_SIZE, VIEWPORT_CENTER, WORLD_SIZE,
    WALKABLE_TILES,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.world.terrain import get_biome

_CAVE_SEED_OFFSET = 9000


def _drunkard_walk(
    rng: random.Random,
    carved: set[tuple[int, int]],
    start_x: int, start_y: int,
    steps: int, width: int, height: int,
    room_freq: int = 8,
) -> None:
    """Carve a drunkard's walk starting at (start_x, start_y) for `steps` steps."""
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


def _carve_chamber(
    carved: set[tuple[int, int]],
    cx: int, cy: int, size: int, width: int, height: int,
) -> None:
    """Carve a square chamber of given size centered roughly at (cx, cy)."""
    half = size // 2
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            nx, ny = cx + dx, cy + dy
            if 1 <= nx < width - 1 and 1 <= ny < height - 1:
                carved.add((nx, ny))


def _generate_cave_interior(
    cave_id: int, seed: int, world_x: int, world_y: int,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Generate a large cave interior using drunkard's walk + branching corridors.

    Returns (width, height, tiles, entrance_positions).
    tiles is list of (local_x, local_y, tile_type).
    entrance_positions is list of (local_x, local_y) for each entrance.
    """
    rng = random.Random(seed + _CAVE_SEED_OFFSET + cave_id + world_x * 1000 + world_y)

    width = rng.randint(CAVE_MIN_SIZE, CAVE_MAX_SIZE)
    height = rng.randint(CAVE_MIN_SIZE, CAVE_MAX_SIZE)

    carved: set[tuple[int, int]] = set()

    # --- Primary entrance on a random edge ---
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

    # Step one tile inward and carve an opening chamber
    if edge == "top":
        ix, iy = ex, 1
    elif edge == "bottom":
        ix, iy = ex, height - 2
    elif edge == "left":
        ix, iy = 1, ey
    else:
        ix, iy = width - 2, ey
    carved.add((ix, iy))
    _carve_chamber(carved, ix, iy, 3, width, height)

    # --- Primary drunkard's walk ---
    _drunkard_walk(rng, carved, ix, iy, CAVE_WALK_STEPS, width, height, room_freq=8)

    # --- 2-3 branching corridors from carved room positions ---
    carved_list = list(carved)
    num_branches = rng.randint(2, 3)
    for _ in range(num_branches):
        if len(carved_list) < 10:
            break
        branch_start = rng.choice(carved_list)
        branch_steps = rng.randint(CAVE_WALK_STEPS // 4, CAVE_WALK_STEPS // 2)
        _drunkard_walk(rng, carved, branch_start[0], branch_start[1],
                       branch_steps, width, height, room_freq=10)
        carved_list = list(carved)

    # Carve a large chamber at the midpoint of the cave
    if carved_list:
        mid = carved_list[len(carved_list) // 2]
        _carve_chamber(carved, mid[0], mid[1], 5, width, height)

    # --- Secondary entrance (70% chance) ---
    if rng.random() < 0.7 and len(carved) > 20:
        best_dist = 0
        best_pos = None
        for pos in carved:
            d = abs(pos[0] - ex) + abs(pos[1] - ey)
            if d > best_dist:
                best_dist = d
                best_pos = pos

        if best_pos and best_dist > 10:
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

    # --- Build tile list ---
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
    row = await db.fetch_one(
        "SELECT cave_id, local_x, local_y FROM cave_entrances WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        return row["cave_id"], row["local_x"], row["local_y"]

    cursor = await db.execute(
        "INSERT INTO caves (width, height) VALUES (1, 1)"
    )
    cave_id = cursor.lastrowid

    # Look for adjacent cave tiles that have no entrance yet (for natural multi-entrance linking)
    extra_entrances_world: list[tuple[int, int]] = []
    for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
        nx, ny = world_x + ddx, world_y + ddy
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            tile_row = await db.fetch_one(
                "SELECT tile_type FROM tile_overrides WHERE world_x = ? AND world_y = ?",
                (nx, ny),
            )
            if tile_row and tile_row["tile_type"] == "cave":
                existing = await db.fetch_one(
                    "SELECT cave_id FROM cave_entrances WHERE world_x = ? AND world_y = ?",
                    (nx, ny),
                )
                if not existing:
                    extra_entrances_world.append((nx, ny))

    width, height, tiles, entrance_positions = await asyncio.to_thread(
        _generate_cave_interior, cave_id, seed, world_x, world_y
    )

    await db.execute(
        "UPDATE caves SET width = ?, height = ? WHERE cave_id = ?",
        (width, height, cave_id),
    )

    await db.executemany(
        "INSERT OR IGNORE INTO cave_tiles (cave_id, local_x, local_y, tile_type) VALUES (?, ?, ?, ?)",
        [(cave_id, lx, ly, tt) for lx, ly, tt in tiles],
    )

    # Link primary entrance
    primary_ex, primary_ey = entrance_positions[0]
    await db.execute(
        "INSERT OR IGNORE INTO cave_entrances (cave_id, local_x, local_y, world_x, world_y) "
        "VALUES (?, ?, ?, ?, ?)",
        (cave_id, primary_ex, primary_ey, world_x, world_y),
    )

    # Link secondary entrance if one was generated
    if len(entrance_positions) > 1:
        sec_ex, sec_ey = entrance_positions[1]

        # Prefer an existing adjacent cave tile
        if extra_entrances_world:
            sec_wx, sec_wy = extra_entrances_world[0]
        else:
            # Synthesize a new surface exit: find a walkable tile near the primary entrance
            sec_wx, sec_wy = await _find_surface_exit(seed, world_x, world_y, db)

        if sec_wx is not None:
            # Ensure the surface tile exists as a cave override so the player can see it
            await db.execute(
                "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'cave')",
                (sec_wx, sec_wy),
            )
            await db.execute(
                "INSERT OR IGNORE INTO cave_entrances (cave_id, local_x, local_y, world_x, world_y) "
                "VALUES (?, ?, ?, ?, ?)",
                (cave_id, sec_ex, sec_ey, sec_wx, sec_wy),
            )

    return cave_id, primary_ex, primary_ey


async def _find_surface_exit(
    seed: int, world_x: int, world_y: int, db
) -> tuple[int | None, int | None]:
    """Find a nearby walkable wilderness tile to use as a synthesized cave exit.

    Searches in a spiral outward from the primary entrance (2-8 tiles away),
    avoiding existing tile_overrides.
    """
    for radius in range(2, 9):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue  # Only check the ring at this radius
                nx, ny = world_x + dx, world_y + dy
                if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
                    continue
                # Not already an override
                existing = await db.fetch_one(
                    "SELECT tile_type FROM tile_overrides WHERE world_x = ? AND world_y = ?",
                    (nx, ny),
                )
                if existing:
                    continue
                # Walkable base biome
                biome = get_biome(nx, ny, seed)
                if biome in WALKABLE_TILES:
                    return nx, ny
    return None, None


async def load_cave_viewport(
    cave_id: int, center_x: int, center_y: int, db
) -> list[list[TileData]]:
    """Load a 9x9 viewport within a cave, centered on (center_x, center_y).

    Out-of-bounds or non-existent tiles render as stone_wall.
    """
    half = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

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
