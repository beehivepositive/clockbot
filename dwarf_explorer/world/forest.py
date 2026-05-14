"""Dense forest interior generation, maze generation, and viewport loading."""
from __future__ import annotations

import asyncio
import math
import random
import sys

from dwarf_explorer.config import (
    FOREST_WALKABLE, MAZE_WALKABLE, VIEWPORT_SIZE, VIEWPORT_CENTER, WORLD_SIZE,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.world.terrain import get_biome

_FOREST_SEED_OFFSET = 0xF07E57   # = 15_762_007
_MAZE_SEED_OFFSET   = 699743      # arbitrary prime

FOREST_SIZE_MIN = 48
FOREST_SIZE_MAX = 68
FOREST_WALK_STEPS = 1200

MAZE_W = 31   # must be odd for recursive-backtracking carving
MAZE_H = 31

# How many dense-forest entrance clusters to place per world
FOREST_AREA_COUNT = 6
# Minimum Manhattan distance between separate forest entrances (overworld tiles)
FOREST_MIN_SEPARATION = 40


# ── Internal helpers ────────────────────────────────────────────────────────────

def _drunkard(rng: random.Random, carved: set, sx: int, sy: int,
              steps: int, width: int, height: int, room_freq: int = 10) -> None:
    cx, cy = sx, sy
    for i in range(steps):
        dx, dy = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
        nx2, ny2 = cx + dx, cy + dy
        if 1 <= nx2 < width - 1 and 1 <= ny2 < height - 1:
            cx, cy = nx2, ny2
            carved.add((cx, cy))
            if i % room_freq == 0:
                r = rng.randint(2, 5)
                for ry in range(-r, r + 1):
                    for rx in range(-r, r + 1):
                        if rx * rx + ry * ry <= r * r:
                            rrx, rry = cx + rx, cy + ry
                            if 1 <= rrx < width - 1 and 1 <= rry < height - 1:
                                carved.add((rrx, rry))


def _corridor(carved: set, sx: int, sy: int, tx: int, ty: int,
              width: int, height: int, hw: int = 2) -> None:
    """L-shaped corridor, half-width hw tiles on each side."""
    x, y = sx, sy
    while x != tx:
        x += 1 if x < tx else -1
        for off in range(-hw + 1, hw):
            px, py = x, y + off
            if 1 <= px < width - 1 and 1 <= py < height - 1:
                carved.add((px, py))
    while y != ty:
        y += 1 if y < ty else -1
        for off in range(-hw + 1, hw):
            px, py = x + off, y
            if 1 <= px < width - 1 and 1 <= py < height - 1:
                carved.add((px, py))


def _inward(ex: int, ey: int, edge: str, width: int, height: int) -> tuple[int, int]:
    if edge == "top":    return ex, 1
    if edge == "bottom": return ex, height - 2
    if edge == "left":   return 1, ey
    return width - 2, ey


# ── Forest interior generation ──────────────────────────────────────────────────

def _generate_forest_interior(
    forest_id: int, seed: int, world_x: int, world_y: int, num_exits: int = 2,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Generate a forest interior.

    Returns (width, height, tiles, exit_local_positions).
    exit_local_positions are the (local_x, local_y) of fst_exit tiles, in the
    same order as the overworld entrance positions passed to create_forest_area.
    """
    rng = random.Random(seed + _FOREST_SEED_OFFSET + forest_id * 7919
                        + world_x * 1009 + world_y)

    width  = rng.randint(FOREST_SIZE_MIN, FOREST_SIZE_MAX)
    height = rng.randint(FOREST_SIZE_MIN, FOREST_SIZE_MAX)

    carved: set[tuple[int, int]] = set()
    cx, cy = width // 2, height // 2

    # Primary organic carve from the centre
    _drunkard(rng, carved, cx, cy, FOREST_WALK_STEPS, width, height)

    # --- Exits on different edges ---
    edges = ["top", "bottom", "left", "right"]
    rng.shuffle(edges)
    min_spread = max(width, height) // max(num_exits, 1)

    exits: list[tuple[int, int]] = []
    inward_pts: list[tuple[int, int]] = []

    for i in range(num_exits):
        edge = edges[i % len(edges)]
        best: tuple[int, int] | None = None
        for _ in range(40):
            if edge == "top":
                pos = (rng.randint(2, width - 3), 0)
            elif edge == "bottom":
                pos = (rng.randint(2, width - 3), height - 1)
            elif edge == "left":
                pos = (0, rng.randint(2, height - 3))
            else:
                pos = (width - 1, rng.randint(2, height - 3))
            if not exits or min(
                abs(pos[0] - px) + abs(pos[1] - py) for px, py in exits
            ) >= min_spread:
                best = pos
                break
        ex, ey = best or pos
        exits.append((ex, ey))
        carved.add((ex, ey))
        ix, iy = _inward(ex, ey, edge, width, height)
        carved.add((ix, iy))
        inward_pts.append((ix, iy))

    # Carve corridors from each exit inward to centre for connectivity
    for ix, iy in inward_pts:
        _corridor(carved, ix, iy, cx, cy, width, height)

    # --- Special feature placement ---
    exit_set = set(exits)
    floor_tiles = [p for p in carved if p not in exit_set]
    rng.shuffle(floor_tiles)

    # Tree City: near centre, away from exits
    tree_city: tuple[int, int] | None = None
    for t in sorted(floor_tiles, key=lambda p: abs(p[0] - cx) + abs(p[1] - cy)):
        if all(abs(t[0] - ex) + abs(t[1] - ey) > 12 for ex, ey in exits):
            tree_city = t
            break
    if tree_city is None and floor_tiles:
        tree_city = floor_tiles[0]

    # Ancient Tree: far from tree city and exits
    ancient: tuple[int, int] | None = None
    for t in floor_tiles:
        if tree_city and abs(t[0] - tree_city[0]) + abs(t[1] - tree_city[1]) < 16:
            continue
        if all(abs(t[0] - ex) + abs(t[1] - ey) > 8 for ex, ey in exits):
            ancient = t
            break
    if ancient is None:
        ancient = floor_tiles[len(floor_tiles) // 3] if floor_tiles else (cx + 5, cy)

    # Maze door: away from centre, near any edge
    maze_door: tuple[int, int] | None = None
    far_tiles = [t for t in floor_tiles
                 if abs(t[0] - cx) + abs(t[1] - cy) > max(width, height) // 3
                 and t not in (tree_city, ancient)
                 and all(abs(t[0] - ex) + abs(t[1] - ey) > 6 for ex, ey in exits)]
    if far_tiles:
        maze_door = far_tiles[0]
    elif floor_tiles:
        maze_door = floor_tiles[len(floor_tiles) // 2]

    specials: set[tuple[int, int]] = set(exits)
    if tree_city: specials.add(tree_city)
    if ancient:   specials.add(ancient)
    if maze_door: specials.add(maze_door)

    # Nut trees (3-5): scattered, 8+ apart
    nut_trees: set[tuple[int, int]] = set()
    for t in floor_tiles:
        if t in specials: continue
        if len(nut_trees) >= rng.randint(3, 5): break
        if all(abs(t[0] - nx) + abs(t[1] - ny) > 8 for nx, ny in nut_trees):
            nut_trees.add(t)
    specials |= nut_trees

    # Chests (2-4): well spread from each other and specials
    chests: set[tuple[int, int]] = set()
    for t in floor_tiles:
        if t in specials: continue
        if len(chests) >= rng.randint(2, 4): break
        if all(abs(t[0] - nx) + abs(t[1] - ny) > 12 for nx, ny in chests):
            chests.add(t)

    # --- Build tile list ---
    tiles: list[tuple[int, int, str]] = []
    for y in range(height):
        for x in range(width):
            p = (x, y)
            if p in exit_set:
                tiles.append((x, y, "fst_exit"))
            elif p == tree_city:
                tiles.append((x, y, "fst_tree_city"))
            elif p == ancient:
                tiles.append((x, y, "fst_ancient_tree"))
            elif p == maze_door:
                tiles.append((x, y, "fst_maze_door"))
            elif p in nut_trees:
                tiles.append((x, y, "fst_nut_tree"))
            elif p in chests:
                tiles.append((x, y, "fst_chest"))
            elif p in carved:
                tiles.append((x, y, "fst_floor"))
            else:
                tiles.append((x, y, "fst_tree"))

    return width, height, tiles, exits


# ── Maze generation ─────────────────────────────────────────────────────────────

def _generate_maze(
    maze_id: int, seed: int, forest_id: int,
) -> tuple[int, int, list[tuple[int, int, str]]]:
    """Generate a maze using recursive-backtracking DFS.

    The maze is MAZE_W × MAZE_H (both odd).
    Entrance is at (1, 0) — top-left hole.
    Treasure chest placed at the dead-end farthest from entrance.
    Returns (width, height, tiles).
    """
    rng = random.Random(seed + _MAZE_SEED_OFFSET + maze_id * 3571 + forest_id * 1319)

    W, H = MAZE_W, MAZE_H
    # grid[y][x]: "maze_wall" | "maze_floor" | "maze_exit" | "maze_chest"
    grid = [["maze_wall"] * W for _ in range(H)]

    cell_w = W // 2   # number of cells horizontally
    cell_h = H // 2   # number of cells vertically

    visited: set[tuple[int, int]] = set()

    # Iterative DFS to avoid Python recursion limit
    stack = [(0, 0)]
    visited.add((0, 0))
    gx0, gy0 = 1, 1
    grid[gy0][gx0] = "maze_floor"

    while stack:
        cx, cy = stack[-1]
        gx, gy = cx * 2 + 1, cy * 2 + 1

        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        rng.shuffle(dirs)
        moved = False
        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < cell_w and 0 <= ny < cell_h and (nx, ny) not in visited:
                # Carve passage between (cx,cy) and (nx,ny)
                wx, wy = gx + dx, gy + dy   # wall tile between them
                ngx, ngy = nx * 2 + 1, ny * 2 + 1
                grid[wy][wx] = "maze_floor"
                grid[ngy][ngx] = "maze_floor"
                visited.add((nx, ny))
                stack.append((nx, ny))
                moved = True
                break
        if not moved:
            stack.pop()

    # Entrance: break wall at top-centre of first cell
    entrance_gx = 1
    grid[0][entrance_gx] = "maze_exit"   # walkable AND acts as exit back to forest

    # Find dead-end farthest from entrance for treasure
    def _floor_adj(x: int, y: int) -> int:
        count = 0
        for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx2, ny2 = x + ddx, y + ddy
            if 0 <= nx2 < W and 0 <= ny2 < H and grid[ny2][nx2] != "maze_wall":
                count += 1
        return count

    dead_ends: list[tuple[int, int, int]] = []   # (dist, x, y)
    for y in range(1, H):
        for x in range(W):
            if grid[y][x] == "maze_floor" and _floor_adj(x, y) == 1:
                dist = abs(x - entrance_gx) + y
                dead_ends.append((dist, x, y))

    dead_ends.sort(reverse=True)
    if dead_ends:
        _, tx, ty = dead_ends[0]
        grid[ty][tx] = "maze_chest"

    tiles: list[tuple[int, int, str]] = [
        (x, y, grid[y][x]) for y in range(H) for x in range(W)
    ]
    return W, H, tiles


# ── DB creation ─────────────────────────────────────────────────────────────────

async def create_forest_area(
    seed: int,
    overworld_positions: list[tuple[int, int]],   # overworld (x, y) of each entrance tile
    db,
) -> None:
    """Create one forest interior linked to overworld_positions entrances.
    Idempotent: silently skips if any position is already linked.
    """
    for wx, wy in overworld_positions:
        existing = await db.fetch_one(
            "SELECT forest_id FROM forest_entrances WHERE world_x=? AND world_y=?",
            (wx, wy),
        )
        if existing:
            return

    n = len(overworld_positions)
    cur = await db.execute(
        "INSERT INTO forest_areas (width, height) VALUES (1, 1)"
    )
    forest_id = cur.lastrowid

    # Generate maze for this forest
    maze_cur = await db.execute(
        "INSERT INTO maze_areas (forest_id, width, height) VALUES (?, 1, 1)",
        (forest_id,),
    )
    maze_id = maze_cur.lastrowid

    # Generate both grids in thread (CPU-heavy)
    width, height, forest_tiles, exit_positions = await asyncio.to_thread(
        _generate_forest_interior,
        forest_id, seed, overworld_positions[0][0], overworld_positions[0][1], n,
    )
    mw, mh, maze_tiles = await asyncio.to_thread(
        _generate_maze, maze_id, seed, forest_id,
    )

    await db.execute(
        "UPDATE forest_areas SET width=?, height=? WHERE forest_id=?",
        (width, height, forest_id),
    )
    await db.execute(
        "UPDATE maze_areas SET width=?, height=? WHERE maze_id=?",
        (mw, mh, maze_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO forest_tiles (forest_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(forest_id, lx, ly, tt) for lx, ly, tt in forest_tiles],
    )
    await db.executemany(
        "INSERT OR IGNORE INTO maze_tiles (maze_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(maze_id, lx, ly, tt) for lx, ly, tt in maze_tiles],
    )

    # Link each overworld tile to its local exit marker, and create tile_override
    for i, (wx, wy) in enumerate(overworld_positions):
        ex, ey = exit_positions[i] if i < len(exit_positions) else exit_positions[-1]
        await db.execute(
            "INSERT OR IGNORE INTO forest_entrances"
            " (forest_id, local_x, local_y, world_x, world_y)"
            " VALUES (?, ?, ?, ?, ?)",
            (forest_id, ex, ey, wx, wy),
        )
        await db.execute(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type)"
            " VALUES (?, ?, 'forest_entrance')",
            (wx, wy),
        )


async def place_forest_areas(seed: int, db) -> None:
    """Find dense-forest edge positions and create FOREST_AREA_COUNT forest interiors.

    Called during world initialisation. Skips positions already linked.
    """
    rng = random.Random(seed ^ 0xF07E57)

    candidates: list[tuple[int, int]] = []
    WALKABLE_BIOMES = {"plains", "grass", "forest", "hills", "sand", "path"}

    # Scan random positions for dense_forest tiles with walkable neighbours
    for _ in range(15_000):
        x = rng.randint(5, WORLD_SIZE - 6)
        y = rng.randint(5, WORLD_SIZE - 6)
        if get_biome(x, y, seed) != "dense_forest":
            continue
        for ddx, ddy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            adj = get_biome(x + ddx, y + ddy, seed)
            if adj in WALKABLE_BIOMES:
                candidates.append((x, y))
                break

    # Pick FOREST_AREA_COUNT spread-out primary entrances
    chosen: list[tuple[int, int]] = []
    for pos in candidates:
        if len(chosen) >= FOREST_AREA_COUNT:
            break
        if not chosen or all(
            abs(pos[0] - cx) + abs(pos[1] - cy) >= FOREST_MIN_SEPARATION
            for cx, cy in chosen
        ):
            chosen.append(pos)

    # For each chosen primary entrance, find a second entrance on the same forest patch
    for wx, wy in chosen:
        ow_entrances = [(wx, wy)]
        # Search for another dense_forest edge tile ≥20 tiles away (same patch)
        for _ in range(500):
            ox = wx + rng.randint(-30, 30)
            oy = wy + rng.randint(-30, 30)
            if not (0 < ox < WORLD_SIZE - 1 and 0 < oy < WORLD_SIZE - 1):
                continue
            if get_biome(ox, oy, seed) != "dense_forest":
                continue
            if abs(ox - wx) + abs(oy - wy) < 20:
                continue
            for ddx, ddy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                if get_biome(ox + ddx, oy + ddy, seed) in WALKABLE_BIOMES:
                    ow_entrances.append((ox, oy))
                    break
            if len(ow_entrances) >= 2:
                break

        # Attempt to skip if entrances already exist (idempotency check)
        already = await db.fetch_one(
            "SELECT 1 FROM forest_entrances WHERE world_x=? AND world_y=?",
            (wx, wy),
        )
        if already:
            continue

        await create_forest_area(seed, ow_entrances, db)


async def ensure_forests_placed(seed: int, db) -> None:
    """Idempotent: place forest areas if not yet done for this world."""
    existing = await db.fetch_one(
        "SELECT 1 FROM tile_overrides WHERE tile_type='forest_entrance' LIMIT 1"
    )
    if not existing:
        await place_forest_areas(seed, db)


# ── Lookup helpers ───────────────────────────────────────────────────────────────

async def get_forest_entrance(
    db, world_x: int, world_y: int,
) -> tuple[int, int, int] | None:
    """Return (forest_id, local_x, local_y) for a world position, or None."""
    row = await db.fetch_one(
        "SELECT forest_id, local_x, local_y FROM forest_entrances"
        " WHERE world_x=? AND world_y=?",
        (world_x, world_y),
    )
    if row:
        return row["forest_id"], row["local_x"], row["local_y"]
    return None


async def get_forest_exit_world(
    db, forest_id: int, local_x: int, local_y: int,
) -> tuple[int, int] | None:
    """Return (world_x, world_y) for an fst_exit tile, or None."""
    row = await db.fetch_one(
        "SELECT world_x, world_y FROM forest_entrances"
        " WHERE forest_id=? AND local_x=? AND local_y=?",
        (forest_id, local_x, local_y),
    )
    if row:
        return row["world_x"], row["world_y"]
    # Fallback: find the nearest entrance for this forest
    row = await db.fetch_one(
        "SELECT world_x, world_y FROM forest_entrances WHERE forest_id=? LIMIT 1",
        (forest_id,),
    )
    return (row["world_x"], row["world_y"]) if row else None


async def get_maze_for_forest(db, forest_id: int) -> int | None:
    """Return the maze_id linked to this forest, or None."""
    row = await db.fetch_one(
        "SELECT maze_id FROM maze_areas WHERE forest_id=?", (forest_id,)
    )
    return row["maze_id"] if row else None


async def get_maze_exit_forest_pos(db, forest_id: int) -> tuple[int, int]:
    """Return the (local_x, local_y) of the fst_maze_door tile for this forest.

    Falls back to the centre of the forest if not found.
    """
    row = await db.fetch_one(
        "SELECT local_x, local_y FROM forest_tiles"
        " WHERE forest_id=? AND tile_type='fst_maze_door' LIMIT 1",
        (forest_id,),
    )
    if row:
        return row["local_x"], row["local_y"]
    # Fallback: forest centre
    sz = await db.fetch_one(
        "SELECT width, height FROM forest_areas WHERE forest_id=?", (forest_id,)
    )
    if sz:
        return sz["width"] // 2, sz["height"] // 2
    return 5, 5


# ── Viewport loading ─────────────────────────────────────────────────────────────

async def load_forest_viewport(
    forest_id: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    """Load a 7×7 viewport of the forest interior centred on (center_x, center_y)."""
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM forest_tiles"
        " WHERE forest_id=? AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (forest_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row.append(TileData(
                terrain=tile_map.get((cx, cy), "fst_tree"),
                world_x=cx, world_y=cy,
            ))
        grid.append(row)
    return grid


async def load_forest_single_tile(
    forest_id: int, local_x: int, local_y: int, db,
) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM forest_tiles WHERE forest_id=? AND local_x=? AND local_y=?",
        (forest_id, local_x, local_y),
    )
    return TileData(
        terrain=row["tile_type"] if row else "fst_tree",
        world_x=local_x, world_y=local_y,
    )


async def load_maze_viewport(
    maze_id: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    """Load a 7×7 viewport of the maze centred on (center_x, center_y)."""
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM maze_tiles"
        " WHERE maze_id=? AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (maze_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row.append(TileData(
                terrain=tile_map.get((cx, cy), "maze_wall"),
                world_x=cx, world_y=cy,
            ))
        grid.append(row)
    return grid


async def load_maze_single_tile(
    maze_id: int, local_x: int, local_y: int, db,
) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM maze_tiles WHERE maze_id=? AND local_x=? AND local_y=?",
        (maze_id, local_x, local_y),
    )
    return TileData(
        terrain=row["tile_type"] if row else "maze_wall",
        world_x=local_x, world_y=local_y,
    )
