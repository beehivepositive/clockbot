from __future__ import annotations
from dataclasses import dataclass

from dwarf_explorer.config import (
    CHUNK_SIZE, WALKABLE_TILES, STRUCTURE_TILES, SPAWN_X, SPAWN_Y,
    VIEWPORT_SIZE, VIEWPORT_CENTER, WORLD_SIZE,
)
from dwarf_explorer.world.terrain import get_biome
from dwarf_explorer.utils.helpers import chunk_to_world


@dataclass
class TileData:
    terrain: str
    structure: str | None = None
    ground_item: str | None = None
    enemy: str | None = None
    world_x: int = 0
    world_y: int = 0

    @property
    def walkable(self) -> bool:
        effective = self.structure if self.structure else self.terrain
        return effective in WALKABLE_TILES


def generate_chunk_terrain(chunk_x: int, chunk_y: int, seed: int) -> list[list[TileData]]:
    """Generate a 7x7 grid of TileData from terrain noise alone.

    Returns grid[row_y][col_x] — grid[0][0] is the top-left tile.
    """
    origin_x, origin_y = chunk_to_world(chunk_x, chunk_y)
    grid: list[list[TileData]] = []

    for local_y in range(CHUNK_SIZE):
        row: list[TileData] = []
        for local_x in range(CHUNK_SIZE):
            wx = origin_x + local_x
            wy = origin_y + local_y
            biome = get_biome(wx, wy, seed)
            row.append(TileData(terrain=biome, world_x=wx, world_y=wy))
        grid.append(row)

    return grid


async def load_chunk(chunk_x: int, chunk_y: int, seed: int, db=None) -> list[list[TileData]]:
    """Load a chunk, applying tile overrides from the database if available.

    For Stage 1, this just returns base terrain. Later stages will layer
    rivers, structures, items, and enemies from the DB.
    """
    grid = generate_chunk_terrain(chunk_x, chunk_y, seed)

    if db is not None:
        origin_x, origin_y = chunk_to_world(chunk_x, chunk_y)
        # Load tile overrides (rivers, structures)
        overrides = await db.fetch_all(
            "SELECT world_x, world_y, tile_type FROM tile_overrides "
            "WHERE world_x >= ? AND world_x < ? AND world_y >= ? AND world_y < ?",
            (origin_x, origin_x + CHUNK_SIZE, origin_y, origin_y + CHUNK_SIZE),
        )
        for row in overrides:
            lx = row["world_x"] - origin_x
            ly = row["world_y"] - origin_y
            tile = grid[ly][lx]
            tile_type = row["tile_type"]
            if tile_type in STRUCTURE_TILES:
                tile.structure = tile_type
            else:
                tile.terrain = tile_type

        # Load ground items
        items = await db.fetch_all(
            "SELECT world_x, world_y, item_id FROM ground_items "
            "WHERE world_x >= ? AND world_x < ? AND world_y >= ? AND world_y < ?",
            (origin_x, origin_x + CHUNK_SIZE, origin_y, origin_y + CHUNK_SIZE),
        )
        for row in items:
            lx = row["world_x"] - origin_x
            ly = row["world_y"] - origin_y
            grid[ly][lx].ground_item = row["item_id"]

        # Load enemies
        enemies = await db.fetch_all(
            "SELECT world_x, world_y, enemy_type FROM enemies "
            "WHERE world_x >= ? AND world_x < ? AND world_y >= ? AND world_y < ? "
            "AND (defeated_at IS NULL OR datetime(defeated_at, '+10 minutes') < datetime('now'))",
            (origin_x, origin_x + CHUNK_SIZE, origin_y, origin_y + CHUNK_SIZE),
        )
        for row in enemies:
            lx = row["world_x"] - origin_x
            ly = row["world_y"] - origin_y
            grid[ly][lx].enemy = row["enemy_type"]

    return grid


async def load_viewport(center_x: int, center_y: int, seed: int, db=None) -> list[list[TileData]]:
    """Load a 9x9 grid of tiles centered on (center_x, center_y).

    Player is always at grid[VIEWPORT_CENTER][VIEWPORT_CENTER].
    Out-of-bounds tiles use terrain="void".
    """
    half = VIEWPORT_CENTER
    grid: list[list[TileData]] = []

    for local_y in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            wx = center_x - half + local_x
            wy = center_y - half + local_y
            if not (0 <= wx < WORLD_SIZE and 0 <= wy < WORLD_SIZE):
                row.append(TileData(terrain="void", world_x=wx, world_y=wy))
            else:
                biome = get_biome(wx, wy, seed)
                row.append(TileData(terrain=biome, world_x=wx, world_y=wy))
        grid.append(row)

    if db is not None:
        x_min = center_x - half
        x_max = center_x + half
        y_min = center_y - half
        y_max = center_y + half

        # Tile overrides (rivers, structures)
        overrides = await db.fetch_all(
            "SELECT world_x, world_y, tile_type FROM tile_overrides "
            "WHERE world_x >= ? AND world_x <= ? AND world_y >= ? AND world_y <= ?",
            (x_min, x_max, y_min, y_max),
        )
        for r in overrides:
            lx = r["world_x"] - x_min
            ly = r["world_y"] - y_min
            if 0 <= lx < VIEWPORT_SIZE and 0 <= ly < VIEWPORT_SIZE:
                tile = grid[ly][lx]
                tile_type = r["tile_type"]
                if tile_type in STRUCTURE_TILES:
                    tile.structure = tile_type
                else:
                    tile.terrain = tile_type

        # Ground items
        items = await db.fetch_all(
            "SELECT world_x, world_y, item_id FROM ground_items "
            "WHERE world_x >= ? AND world_x <= ? AND world_y >= ? AND world_y <= ?",
            (x_min, x_max, y_min, y_max),
        )
        for r in items:
            lx = r["world_x"] - x_min
            ly = r["world_y"] - y_min
            if 0 <= lx < VIEWPORT_SIZE and 0 <= ly < VIEWPORT_SIZE:
                grid[ly][lx].ground_item = r["item_id"]

        # Enemies
        enemies = await db.fetch_all(
            "SELECT world_x, world_y, enemy_type FROM enemies "
            "WHERE world_x >= ? AND world_x <= ? AND world_y >= ? AND world_y <= ? "
            "AND (defeated_at IS NULL OR datetime(defeated_at, '+10 minutes') < datetime('now'))",
            (x_min, x_max, y_min, y_max),
        )
        for r in enemies:
            lx = r["world_x"] - x_min
            ly = r["world_y"] - y_min
            if 0 <= lx < VIEWPORT_SIZE and 0 <= ly < VIEWPORT_SIZE:
                grid[ly][lx].enemy = r["enemy_type"]

    return grid


async def load_single_tile(wx: int, wy: int, seed: int, db=None) -> TileData:
    """Load a single tile for walkability checks."""
    if not (0 <= wx < WORLD_SIZE and 0 <= wy < WORLD_SIZE):
        return TileData(terrain="void", world_x=wx, world_y=wy)

    biome = get_biome(wx, wy, seed)
    tile = TileData(terrain=biome, world_x=wx, world_y=wy)

    if db is not None:
        row = await db.fetch_one(
            "SELECT tile_type FROM tile_overrides WHERE world_x = ? AND world_y = ?",
            (wx, wy),
        )
        if row:
            tile_type = row["tile_type"]
            if tile_type in STRUCTURE_TILES:
                tile.structure = tile_type
            else:
                tile.terrain = tile_type

    return tile


async def find_walkable_spawn(seed: int, db) -> tuple[int, int]:
    """Find the nearest walkable tile to (SPAWN_X, SPAWN_Y).

    Searches outward in expanding rings so the player always lands on dry,
    passable ground even if a river flows through the default spawn point.
    """
    # Quick check: is default spawn already walkable?
    default = await load_single_tile(SPAWN_X, SPAWN_Y, seed, db)
    if default.walkable:
        return (SPAWN_X, SPAWN_Y)

    for radius in range(1, 30):
        for dx in range(-radius, radius + 1):
            for dy in ((-radius, radius) if abs(dx) < radius else range(-radius, radius + 1)):
                wx, wy = SPAWN_X + dx, SPAWN_Y + dy
                if 0 <= wx < WORLD_SIZE and 0 <= wy < WORLD_SIZE:
                    tile = await load_single_tile(wx, wy, seed, db)
                    if tile.walkable:
                        return (wx, wy)
    return (SPAWN_X, SPAWN_Y)


async def init_world(seed: int, db) -> None:
    """Generate and store all world features (rivers + structures) for a new world."""
    from dwarf_explorer.world.rivers import generate_rivers
    from dwarf_explorer.world.structures import place_structures
    await generate_rivers(seed, db)
    await place_structures(seed, db)
