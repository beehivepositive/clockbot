from __future__ import annotations

import asyncio
import random

from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import WORLD_SIZE

_RIVER_SEED_OFFSET = 5000
_PERTURB_OFFSET = 777


def _generate_rivers_sync(seed: int) -> list[tuple[int, int]]:
    """Synchronously compute river tile coordinates from seed. Returns list of (x, y)."""
    rng = random.Random(seed + _RIVER_SEED_OFFSET)
    river_tiles: set[tuple[int, int]] = set()

    # Find 4-6 river sources at high elevation
    sources: list[tuple[int, int]] = []
    attempts = 0
    while len(sources) < 5 and attempts < 400:
        attempts += 1
        x = rng.randint(2, WORLD_SIZE - 3)
        y = rng.randint(2, WORLD_SIZE - 3)
        if fbm(x, y, seed) > 0.65:
            sources.append((x, y))

    for sx, sy in sources:
        x, y = sx, sy
        visited: set[tuple[int, int]] = set()

        for _ in range(300):
            if (x, y) in visited:
                break
            visited.add((x, y))

            e = fbm(x, y, seed)
            if e < 0.28:  # Reached natural water — stop
                break
            if not (1 <= x < WORLD_SIZE - 1 and 1 <= y < WORLD_SIZE - 1):
                break

            river_tiles.add((x, y))

            # Flow to lowest elevation neighbor (with small perturbation to break ties)
            best: tuple[int, int] | None = None
            best_e = e
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
                    ne = fbm(nx, ny, seed) + fbm(nx, ny, seed + _PERTURB_OFFSET) * 0.04
                    if ne < best_e:
                        best_e = ne
                        best = (nx, ny)

            if best is None:
                break
            x, y = best

    return list(river_tiles)


async def generate_rivers(seed: int, db) -> None:
    """Generate rivers and store as tile_overrides in the database."""
    tiles = await asyncio.to_thread(_generate_rivers_sync, seed)
    if tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'shallow_water')",
            [(x, y) for x, y in tiles],
        )
