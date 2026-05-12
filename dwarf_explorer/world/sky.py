"""Sky biome generator.

Sky biomes are position-based interior zones stored in the `sky_biomes` DB table.
Players navigate them with (sky_x, sky_y) the same way they navigate caves.
The layout is generated procedurally from a seed derived from the sky_id.

Layout concepts
---------------
- The sky consists of cloud islands floating in void (sky_void).
- Each island is a roughly circular cluster of sky_cloud tiles.
- Islands are connected by narrow (1-tile-wide) sky_bridge paths.
- The entry island (centred at sky_entrance) is where the player starts.
- Some larger islands hold sky_temple or sky_altar structures.
- sky_chest tiles are scattered on cloud islands as reward spots.
- Enemies (wind_wisp on clouds, storm_hawk on bridges) spawn via random
  encounter — they are NOT placed as tiles.
"""
from __future__ import annotations

import math
import random
from typing import NamedTuple

from dwarf_explorer.config import SKY_WALKABLE, VIEWPORT_SIZE, VIEWPORT_CENTER
from dwarf_explorer.world.generator import TileData

_SKY_SEED_OFFSET = 77777

# Grid size for a sky biome (same as cave approach — large scrollable space)
SKY_WIDTH  = 80
SKY_HEIGHT = 80

# Entry island spawn position
SKY_ENTRY_X = SKY_WIDTH  // 2
SKY_ENTRY_Y = SKY_HEIGHT // 2


def _dist(ax: int, ay: int, bx: int, by: int) -> float:
    return math.hypot(ax - bx, ay - by)


def _place_cloud_island(
    tiles: dict[tuple[int, int], str],
    cx: int, cy: int, radius: int,
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Carve a roughly circular cloud island centred at (cx, cy).
    Returns list of all cloud positions placed.
    """
    placed: list[tuple[int, int]] = []
    for dy in range(-radius - 1, radius + 2):
        for dx in range(-radius - 1, radius + 2):
            nx, ny = cx + dx, cy + dy
            if not (0 < nx < SKY_WIDTH - 1 and 0 < ny < SKY_HEIGHT - 1):
                continue
            # Jittered circular test
            jitter = rng.uniform(0.7, 1.2)
            if math.hypot(dx, dy) <= radius * jitter:
                tiles[(nx, ny)] = "sky_cloud"
                placed.append((nx, ny))
    return placed


def _bridge_to(
    tiles: dict[tuple[int, int], str],
    sx: int, sy: int, tx: int, ty: int,
) -> None:
    """Draw a 1-tile-wide L-shaped sky_bridge from (sx,sy) to (tx,ty)."""
    x, y = sx, sy
    while x != tx:
        x += 1 if x < tx else -1
        if (x, y) not in tiles or tiles[(x, y)] == "sky_void":
            tiles[(x, y)] = "sky_bridge"
    while y != ty:
        y += 1 if y < ty else -1
        if (x, y) not in tiles or tiles[(x, y)] == "sky_void":
            tiles[(x, y)] = "sky_bridge"


def generate_sky_biome(sky_id: int, world_seed: int) -> tuple[int, int, list[tuple[int, int, str]]]:
    """Generate a sky biome interior.

    Returns (width, height, tiles) where tiles is a list of (x, y, tile_type).
    """
    rng = random.Random(world_seed + _SKY_SEED_OFFSET + sky_id * 31337)

    tiles: dict[tuple[int, int], str] = {}

    # --- Entry island (centre of map) ---
    entry_radius = rng.randint(4, 6)
    entry_cloud = _place_cloud_island(tiles, SKY_ENTRY_X, SKY_ENTRY_Y, entry_radius, rng)

    # Place sky_entrance at entry centre
    tiles[(SKY_ENTRY_X, SKY_ENTRY_Y)] = "sky_entrance"

    # Place a sky_chest near the entry island periphery
    if entry_cloud:
        far_entry = sorted(entry_cloud, key=lambda p: _dist(p[0], p[1], SKY_ENTRY_X, SKY_ENTRY_Y), reverse=True)
        if far_entry:
            ex, ey = far_entry[0]
            if (ex, ey) != (SKY_ENTRY_X, SKY_ENTRY_Y):
                tiles[(ex, ey)] = "sky_chest"

    # --- Satellite islands ---
    num_satellites = rng.randint(3, 6)
    island_centers: list[tuple[int, int]] = [(SKY_ENTRY_X, SKY_ENTRY_Y)]
    all_cloud_tiles: list[tuple[int, int]] = list(entry_cloud)

    for _ in range(num_satellites):
        # Pick direction from a random existing island
        src = rng.choice(island_centers)
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.randint(14, 22)
        nx = int(round(src[0] + math.cos(angle) * dist))
        ny = int(round(src[1] + math.sin(angle) * dist))
        nx = max(3, min(SKY_WIDTH - 4, nx))
        ny = max(3, min(SKY_HEIGHT - 4, ny))

        radius = rng.randint(2, 5)
        cloud_tiles = _place_cloud_island(tiles, nx, ny, radius, rng)
        all_cloud_tiles.extend(cloud_tiles)

        # Bridge to nearest existing island
        nearest = min(island_centers, key=lambda c: _dist(c[0], c[1], nx, ny))
        _bridge_to(tiles, nearest[0], nearest[1], nx, ny)

        island_centers.append((nx, ny))

        # Place structures on larger islands
        if radius >= 4 and cloud_tiles:
            roll = rng.random()
            center_tile = (nx, ny)
            if roll < 0.3:
                tiles[center_tile] = "sky_temple"
            elif roll < 0.5:
                tiles[center_tile] = "sky_altar"
            # chest on the far edge
            far_tiles = sorted(cloud_tiles, key=lambda p: _dist(p[0], p[1], nx, ny), reverse=True)
            for ct in far_tiles:
                if ct != center_tile:
                    tiles[ct] = "sky_chest"
                    break
        elif radius >= 2 and cloud_tiles and rng.random() < 0.4:
            # Small island — just a chest
            for ct in cloud_tiles:
                if ct != (nx, ny):
                    tiles[ct] = "sky_chest"
                    break

    # --- Fill rest as sky_void ---
    result: list[tuple[int, int, str]] = []
    for y in range(SKY_HEIGHT):
        for x in range(SKY_WIDTH):
            tile_type = tiles.get((x, y), "sky_void")
            result.append((x, y, tile_type))

    return SKY_WIDTH, SKY_HEIGHT, result


async def create_sky_biome(sky_id: int, world_seed: int, db) -> tuple[int, int]:
    """Create sky biome in DB and return (entry_x, entry_y)."""
    width, height, tile_list = generate_sky_biome(sky_id, world_seed)

    await db.execute(
        "UPDATE sky_biomes SET width = ?, height = ? WHERE sky_id = ?",
        (width, height, sky_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO sky_tiles (sky_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(sky_id, lx, ly, tt) for lx, ly, tt in tile_list],
    )
    return SKY_ENTRY_X, SKY_ENTRY_Y


async def get_or_create_sky_biome(
    world_seed: int, world_x: int, world_y: int, db
) -> tuple[int, int, int]:
    """Return (sky_id, entry_x, entry_y) for the sky portal at (world_x, world_y).

    Creates the biome on first entry.
    """
    row = await db.fetch_one(
        "SELECT sky_id FROM sky_portals WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    if row:
        sky_id = row["sky_id"]
        # Check if already generated
        tiles_row = await db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM sky_tiles WHERE sky_id = ?", (sky_id,)
        )
        if tiles_row and tiles_row["cnt"] > 0:
            return sky_id, SKY_ENTRY_X, SKY_ENTRY_Y
        ex, ey = await create_sky_biome(sky_id, world_seed, db)
        return sky_id, ex, ey

    # Create new biome row
    cursor = await db.execute(
        "INSERT INTO sky_biomes (width, height) VALUES (1, 1)"
    )
    sky_id = cursor.lastrowid
    await db.execute(
        "INSERT OR IGNORE INTO sky_portals (world_x, world_y, sky_id) VALUES (?, ?, ?)",
        (world_x, world_y, sky_id),
    )
    ex, ey = await create_sky_biome(sky_id, world_seed, db)
    return sky_id, ex, ey


async def load_sky_viewport(
    sky_id: int, center_x: int, center_y: int, db
) -> list[list[TileData]]:
    """Load a 9x9 viewport centred at (center_x, center_y) in sky biome sky_id."""
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM sky_tiles"
        " WHERE sky_id = ? AND local_x >= ? AND local_x <= ?"
        "   AND local_y >= ? AND local_y <= ?",
        (sky_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}
    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row_tiles: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row_tiles.append(TileData(terrain=tile_map.get((cx, cy), "sky_void"),
                                      world_x=cx, world_y=cy))
        grid.append(row_tiles)
    return grid


async def load_sky_single_tile(sky_id: int, local_x: int, local_y: int, db) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM sky_tiles"
        " WHERE sky_id = ? AND local_x = ? AND local_y = ?",
        (sky_id, local_x, local_y),
    )
    return TileData(terrain=row["tile_type"] if row else "sky_void",
                    world_x=local_x, world_y=local_y)
