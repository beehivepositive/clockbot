from __future__ import annotations

import asyncio
import random

from dwarf_explorer.world.terrain import get_biome
from dwarf_explorer.config import WORLD_SIZE, WALKABLE_TILES

_STRUCTURE_SEED_OFFSET = 2000
_SPAWN_BUFFER = 12  # Don't place structures this close to world spawn


def _near_spawn(x: int, y: int) -> bool:
    cx, cy = WORLD_SIZE // 2, WORLD_SIZE // 2
    return abs(x - cx) < _SPAWN_BUFFER and abs(y - cy) < _SPAWN_BUFFER


def _is_adjacent_to(x: int, y: int, seed: int, biome: str) -> bool:
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            if get_biome(nx, ny, seed) == biome:
                return True
    return False


def _generate_structures_sync(seed: int) -> list[tuple[int, int, str]]:
    """Synchronously compute all structure placements. Returns list of (x, y, tile_type)."""
    rng = random.Random(seed + _STRUCTURE_SEED_OFFSET)
    overrides: list[tuple[int, int, str]] = []
    village_centers: list[tuple[int, int]] = []

    # --- Villages (4-6): plains/grass, minimum 30 tiles apart ---
    village_count = rng.randint(4, 6)
    found = 0
    for _ in range(600):
        if found >= village_count:
            break
        x = rng.randint(5, WORLD_SIZE - 6)
        y = rng.randint(5, WORLD_SIZE - 6)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) not in ('plains', 'grass'):
            continue
        if any(abs(x - vx) + abs(y - vy) < 30 for vx, vy in village_centers):
            continue

        village_centers.append((x, y))
        found += 1

        # 3x3 village cluster
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                vx, vy = x + dx, y + dy
                if 0 <= vx < WORLD_SIZE and 0 <= vy < WORLD_SIZE:
                    overrides.append((vx, vy, 'village'))

        # Paths extending 6-10 tiles in 4 directions
        path_len = rng.randint(6, 10)
        for direction in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            px, py = x + direction[0] * 2, y + direction[1] * 2
            for _ in range(path_len):
                px += direction[0]
                py += direction[1]
                if not (0 <= px < WORLD_SIZE and 0 <= py < WORLD_SIZE):
                    break
                overrides.append((px, py, 'path'))

    # --- Shrines (6-10): on hills tiles ---
    shrine_count = rng.randint(6, 10)
    found = 0
    for _ in range(600):
        if found >= shrine_count:
            break
        x = rng.randint(1, WORLD_SIZE - 2)
        y = rng.randint(1, WORLD_SIZE - 2)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) == 'hills':
            overrides.append((x, y, 'shrine'))
            found += 1

    # --- Caves (4-8): walkable tile adjacent to a mountain ---
    cave_count = rng.randint(4, 8)
    found = 0
    for _ in range(1200):
        if found >= cave_count:
            break
        x = rng.randint(1, WORLD_SIZE - 2)
        y = rng.randint(1, WORLD_SIZE - 2)
        if _near_spawn(x, y):
            continue
        biome = get_biome(x, y, seed)
        if biome in WALKABLE_TILES and _is_adjacent_to(x, y, seed, 'mountain'):
            overrides.append((x, y, 'cave'))
            found += 1

    # --- Campfires (8-12): open terrain, minimum 20 tiles apart ---
    campfire_count = rng.randint(8, 12)
    campfire_positions: list[tuple[int, int]] = []
    found = 0
    for _ in range(600):
        if found >= campfire_count:
            break
        x = rng.randint(1, WORLD_SIZE - 2)
        y = rng.randint(1, WORLD_SIZE - 2)
        if _near_spawn(x, y):
            continue
        biome = get_biome(x, y, seed)
        if biome not in ('plains', 'grass', 'forest'):
            continue
        if any(abs(x - cx) + abs(y - cy) < 20 for cx, cy in campfire_positions):
            continue
        overrides.append((x, y, 'campfire'))
        campfire_positions.append((x, y))
        found += 1

    # --- Ruins (3-5): 2x2 clusters on walkable terrain ---
    ruins_count = rng.randint(3, 5)
    found = 0
    for _ in range(500):
        if found >= ruins_count:
            break
        x = rng.randint(1, WORLD_SIZE - 3)
        y = rng.randint(1, WORLD_SIZE - 3)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) in WALKABLE_TILES:
            for dy in range(2):
                for dx in range(2):
                    rx, ry = x + dx, y + dy
                    if 0 <= rx < WORLD_SIZE and 0 <= ry < WORLD_SIZE:
                        overrides.append((rx, ry, 'ruins'))
            found += 1

    return overrides


async def place_structures(seed: int, db) -> None:
    """Generate all structures and store as tile_overrides."""
    overrides = await asyncio.to_thread(_generate_structures_sync, seed)
    if overrides:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
            overrides,
        )
