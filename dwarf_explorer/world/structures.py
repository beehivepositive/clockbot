from __future__ import annotations

import asyncio
import math
import random

from dwarf_explorer.world.terrain import get_biome
from dwarf_explorer.world.noise import fbm
from dwarf_explorer.config import WORLD_SIZE, WALKABLE_TILES

_STRUCTURE_SEED_OFFSET = 2000
_PATH_SEED_OFFSET      = 3000
_SPAWN_BUFFER = 12


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


def _norm2(dx: float, dy: float) -> tuple[float, float]:
    m = math.hypot(dx, dy)
    return (dx / m, dy / m) if m > 1e-9 else (1.0, 0.0)


def _rotate2(dx: float, dy: float, angle: float) -> tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return (c * dx - s * dy, s * dx + c * dy)


def _path_worm(
    start: tuple[int, int],
    end: tuple[int, int],
    seed: int,
    stop_tiles: set[tuple[int, int]],
    max_steps: int = 500,
) -> list[tuple[int, int]]:
    """Perlin-worm path from start toward end with strong meanders.

    Uses a persistent worm direction that rotates via fBm noise (±80°), with
    only moderate pull toward the destination (40%).  This produces natural
    S-curve roads that still reliably reach their target.

    Diagonal steps are widened: when the worm moves diagonally, one corner tile
    is also added so the path looks consistently 1 tile wide around bends.
    """
    x, y = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    freq = 0.15   # lower frequency = broader meander waves
    path: list[tuple[int, int]] = []
    # Start direction: toward target
    dx, dy = _norm2(ex - x, ey - y)

    for _ in range(max_steps):
        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))
        if not path or (ix, iy) != path[-1]:
            # Widen diagonals: if we moved diagonally, also paint one corner tile
            if path:
                lx, ly = path[-1]
                step_dx, step_dy = ix - lx, iy - ly
                if abs(step_dx) == 1 and abs(step_dy) == 1:
                    path.append((lx + step_dx, ly))   # fill corner so no gaps
            path.append((ix, iy))

        # Check adjacency to stop tiles
        if len(path) > 3:
            for nx, ny in [(ix+1,iy),(ix-1,iy),(ix,iy+1),(ix,iy-1)]:
                if (nx, ny) in stop_tiles:
                    path.append((nx, ny))
                    return path
            if (ix, iy) in stop_tiles:
                return path

        # Worm direction: persistent momentum + Perlin rotation + convergence pull
        n = fbm(x * freq, y * freq, seed, octaves=3)
        rot = math.radians((n - 0.5) * 160.0)   # ±80° strong meander
        ndx, ndy = _norm2(*_rotate2(dx, dy, rot))
        tdx, tdy = _norm2(ex - x, ey - y)
        # 40% toward target, 60% worm noise — meanders but still converges
        dx, dy = _norm2(0.40 * tdx + 0.60 * ndx, 0.40 * tdy + 0.60 * ndy)

        x = max(0.0, min(WORLD_SIZE - 1.0, x + dx))
        y = max(0.0, min(WORLD_SIZE - 1.0, y + dy))

    return path


def _generate_structures_sync(seed: int) -> list[tuple[int, int, str]]:
    """Synchronously compute all structure placements (excludes village paths).

    Returns list of (x, y, tile_type).
    Villages are placed as a SINGLE tile each.
    """
    rng = random.Random(seed + _STRUCTURE_SEED_OFFSET)
    overrides: list[tuple[int, int, str]] = []
    village_centers: list[tuple[int, int]] = []

    # --- Villages (4-6): plains/grass, single tile, minimum 40 tiles apart ---
    village_count = rng.randint(4, 6)
    found = 0
    for _ in range(800):
        if found >= village_count:
            break
        x = rng.randint(5, WORLD_SIZE - 6)
        y = rng.randint(5, WORLD_SIZE - 6)
        if _near_spawn(x, y):
            continue
        if get_biome(x, y, seed) not in ('plains', 'grass'):
            continue
        if any(abs(x - vx) + abs(y - vy) < 40 for vx, vy in village_centers):
            continue
        village_centers.append((x, y))
        overrides.append((x, y, 'village'))
        # Surround the village tile with a 1-tile ring of path
        for ry in range(y - 1, y + 2):
            for rx in range(x - 1, x + 2):
                if (rx, ry) != (x, y) and 0 <= rx < WORLD_SIZE and 0 <= ry < WORLD_SIZE:
                    overrides.append((rx, ry, 'path'))
        found += 1

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

    # --- Caves (4-8): walkable tile adjacent to mountain ---
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


def _generate_village_paths_sync(
    seed: int,
    village_positions: list[tuple[int, int]],
    bridge_positions: list[tuple[int, int]],
    existing_path_tiles: set[tuple[int, int]],
) -> list[tuple[int, int, str]]:
    """Generate Perlin-worm paths connecting each village to its nearest
    neighbour (village or bridge).

    Returns list of (x, y, 'path') overrides.
    """
    rng = random.Random(seed + _PATH_SEED_OFFSET)
    path_tiles: set[tuple[int, int]] = set(existing_path_tiles)
    overrides: list[tuple[int, int, str]] = []

    all_targets = list(village_positions) + list(bridge_positions)

    for i, (vx, vy) in enumerate(village_positions):
        # Find nearest other target that is not this village itself
        candidates = [(math.hypot(tx - vx, ty - vy), (tx, ty))
                      for (tx, ty) in all_targets
                      if (tx, ty) != (vx, vy)]
        if not candidates:
            continue
        candidates.sort()

        # Connect to closest AND second-closest (if within 2× the distance)
        targets_to_connect = [candidates[0][1]]
        if len(candidates) > 1 and candidates[1][0] < candidates[0][0] * 2.0:
            targets_to_connect.append(candidates[1][1])

        path_seed = (seed + _PATH_SEED_OFFSET + i * 7) & 0xFFFFFFFF
        for target in targets_to_connect:
            worm = _path_worm(
                start=(vx, vy),
                end=target,
                seed=path_seed,
                stop_tiles=path_tiles,
                max_steps=500,
            )
            for px, py in worm:
                if (px, py) not in path_tiles:
                    path_tiles.add((px, py))
                    overrides.append((px, py, 'path'))
            path_seed = (path_seed + 1337) & 0xFFFFFFFF

    return overrides


async def place_structures(seed: int, db) -> None:
    """Generate all structures and store as tile_overrides.

    Order: base structures → bridges (already done) → inter-village paths.
    """
    # 1. Base structures
    overrides = await asyncio.to_thread(_generate_structures_sync, seed)
    if overrides:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
            overrides,
        )

    # 2. Collect village positions from what we just placed
    village_positions = [(x, y) for x, y, t in overrides if t == 'village']

    # 3. Fetch bridge positions from DB (placed before structures)
    bridge_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'bridge'"
    )
    bridge_positions = [(r["world_x"], r["world_y"]) for r in bridge_rows]

    # 4. Existing path tiles (so worms stop at them)
    path_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'path'"
    )
    existing_paths = {(r["world_x"], r["world_y"]) for r in path_rows}

    if village_positions:
        path_overrides = await asyncio.to_thread(
            _generate_village_paths_sync,
            seed, village_positions, bridge_positions, existing_paths,
        )
        if path_overrides:
            await db.executemany(
                "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
                path_overrides,
            )
