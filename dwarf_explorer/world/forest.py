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

# ── Forest map dimensions ────────────────────────────────────────────────────────
FOREST_W = 120    # fixed width for bead-chain forest
FOREST_H = 120    # fixed height

# Clearing radii
_CLEARING_R = 4   # normal clearing: circle of radius 4 (~9×9 bounding box)
_CENTRAL_R  = 6   # Tree City central clearing (~13×13)

# Chain parameters
_NUM_CHAIN_BEADS = 5    # intermediate beads per chain (between entry clearing and center)
_NUM_TRIBUTARIES = 3    # tributary branches off each main chain
_TRIB_STEP_MIN   = 16  # min distance for tributary bead from parent
_TRIB_STEP_MAX   = 24  # max distance for tributary bead from parent
_MEANDER_SPREAD  = 12  # max random offset per axis per intermediate bead

# Legacy constants kept for maze viewport loader compatibility
_MAZE_CELLS  = 8
_MAZE_STRIDE = 4
MAZE_W = _MAZE_CELLS * _MAZE_STRIDE + 1   # = 33
MAZE_H = _MAZE_CELLS * _MAZE_STRIDE + 1   # = 33
_MAZE_ENTRY_CX = _MAZE_CELLS // 2
MAZE_ENTRY_X   = _MAZE_ENTRY_CX * _MAZE_STRIDE + 2
MAZE_ENTRY_Y   = 1

# How many dense-forest entrance clusters to place per world
FOREST_AREA_COUNT = 6
# Minimum Manhattan distance between separate forest entrances (overworld tiles)
FOREST_MIN_SEPARATION = 40


# ── Internal helpers ─────────────────────────────────────────────────────────────

def _carve_circ(
    grid: list[list[str]], cx: int, cy: int, r: int, W: int, H: int
) -> None:
    """Carve a filled circle of fst_floor, clamped to inner boundary."""
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                px, py = cx + dx, cy + dy
                if 1 <= px < W - 1 and 1 <= py < H - 1:
                    if grid[py][px] == "fst_tree":
                        grid[py][px] = "fst_floor"


def _carve_path(
    grid: list[list[str]], x1: int, y1: int, x2: int, y2: int, W: int, H: int
) -> None:
    """Carve a 1-tile-wide L-shaped corridor including both endpoints."""
    x, y = x1, y1
    # Set starting tile
    if 0 <= x < W and 0 <= y < H and grid[y][x] == "fst_tree":
        grid[y][x] = "fst_floor"
    # Horizontal leg
    while x != x2:
        x += 1 if x < x2 else -1
        if 0 <= x < W and 0 <= y < H and grid[y][x] == "fst_tree":
            grid[y][x] = "fst_floor"
    # Vertical leg
    while y != y2:
        y += 1 if y < y2 else -1
        if 0 <= x < W and 0 <= y < H and grid[y][x] == "fst_tree":
            grid[y][x] = "fst_floor"


def _meander(
    rng: random.Random, sx: int, sy: int, tx: int, ty: int,
    n: int, W: int, H: int, spread: int = _MEANDER_SPREAD,
) -> list[tuple[int, int]]:
    """Return n intermediate bead positions that meander from (sx,sy) toward (tx,ty).

    Neither endpoint is included in the returned list.
    """
    PAD = _CLEARING_R + 3
    pts: list[tuple[int, int]] = []
    for i in range(1, n + 1):
        t = i / (n + 1)
        bx = int(sx + (tx - sx) * t + rng.randint(-spread, spread))
        by = int(sy + (ty - sy) * t + rng.randint(-spread, spread))
        bx = max(PAD, min(W - PAD - 1, bx))
        by = max(PAD, min(H - PAD - 1, by))
        pts.append((bx, by))
    return pts


def _branch_off(
    rng: random.Random,
    grid: list[list[str]],
    parent_x: int, parent_y: int,
    W: int, H: int,
    depth: int = 0, max_depth: int = 1,
) -> list[tuple[int, int]]:
    """Carve one tributary clearing off (parent_x, parent_y) and optionally recurse.

    Returns a list of dead-end clearing centres created.
    """
    PAD = _CLEARING_R + 3
    angle = rng.uniform(0, 2 * math.pi)
    step  = rng.randint(_TRIB_STEP_MIN, _TRIB_STEP_MAX)
    tx = max(PAD, min(W - PAD - 1, parent_x + int(math.cos(angle) * step)))
    ty = max(PAD, min(H - PAD - 1, parent_y + int(math.sin(angle) * step)))

    _carve_circ(grid, tx, ty, _CLEARING_R, W, H)
    _carve_path(grid, parent_x, parent_y, tx, ty, W, H)

    dead_ends: list[tuple[int, int]] = [(tx, ty)]
    if depth < max_depth and rng.random() < 0.55:
        sub = _branch_off(rng, grid, tx, ty, W, H, depth + 1, max_depth)
        dead_ends.extend(sub)
    return dead_ends


# ── Forest interior generation ───────────────────────────────────────────────────

def _generate_forest_interior(
    forest_id: int, seed: int, world_x: int, world_y: int, num_exits: int = 2,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]]]:
    """Generate a forest interior as a bead-chain of clearings.

    Design:
    - Central large clearing holds the Tree City.
    - Each overworld exit spawns a chain of clearings meandering to the center,
      connected by 1-tile-wide corridors.
    - Tributary branches (and sub-tributaries) hang off each main chain.
    - Chests, mimics, nut trees, and the ancient tree are distributed through
      the tributary dead-ends and chain clearings.

    Returns (width, height, tiles, exit_local_positions).
    exit_local_positions[i] is the (local_x, local_y) of the i-th fst_exit tile
    (on the map boundary), corresponding to overworld_positions[i].
    """
    rng = random.Random(
        seed + _FOREST_SEED_OFFSET + forest_id * 7919 + world_x * 1009 + world_y
    )

    W, H = FOREST_W, FOREST_H
    grid: list[list[str]] = [["fst_tree"] * W for _ in range(H)]
    PAD = _CLEARING_R + 3  # minimum distance from any clearing centre to the map edge

    center_x, center_y = W // 2, H // 2

    # ── 1. Central clearing ──────────────────────────────────────────────────────
    _carve_circ(grid, center_x, center_y, _CENTRAL_R, W, H)

    # ── 2. Determine exit positions (on the map boundary) ────────────────────────
    edges = ["top", "bottom", "left", "right"]
    rng.shuffle(edges)

    exits:        list[tuple[int, int]] = []
    inners:       list[tuple[int, int]] = []   # 1 tile inside the boundary
    first_clears: list[tuple[int, int]] = []   # centre of first clearing per chain

    for i in range(min(num_exits, 4)):
        edge = edges[i]
        if edge == "top":
            ex, ey   = rng.randint(PAD, W - PAD - 1), 0
            inner    = (ex, 1)
            first_c  = (ex, PAD + 1)
        elif edge == "bottom":
            ex, ey   = rng.randint(PAD, W - PAD - 1), H - 1
            inner    = (ex, H - 2)
            first_c  = (ex, H - PAD - 2)
        elif edge == "left":
            ex, ey   = 0, rng.randint(PAD, H - PAD - 1)
            inner    = (1, ey)
            first_c  = (PAD + 1, ey)
        else:   # right
            ex, ey   = W - 1, rng.randint(PAD, H - PAD - 1)
            inner    = (W - 2, ey)
            first_c  = (W - PAD - 2, ey)

        exits.append((ex, ey))
        inners.append(inner)
        first_clears.append(first_c)

    # ── 3. Generate chains ───────────────────────────────────────────────────────
    all_chain_beads: list[list[tuple[int, int]]] = []
    dead_ends:       list[tuple[int, int]] = []

    for i in range(len(exits)):
        inner   = inners[i]
        first_c = first_clears[i]

        # Narrow corridor from boundary inner-point to first clearing
        _carve_path(grid, inner[0], inner[1], first_c[0], first_c[1], W, H)
        _carve_circ(grid, first_c[0], first_c[1], _CLEARING_R, W, H)

        # Intermediate beads meandering toward center
        # Aim slightly off-center so two chains don't perfectly overlap
        aim_x = center_x + rng.randint(-6, 6)
        aim_y = center_y + rng.randint(-6, 6)
        mid_beads = _meander(rng, first_c[0], first_c[1], aim_x, aim_y,
                             _NUM_CHAIN_BEADS, W, H)

        # chain = [first_c] + mid_beads (doesn't include center)
        chain = [first_c] + mid_beads

        # Carve each intermediate bead and the corridor from its predecessor
        for j, (bx, by) in enumerate(mid_beads):
            prev = chain[j]   # chain[0]=first_c, chain[1]=mid_beads[0], …
            _carve_circ(grid, bx, by, _CLEARING_R, W, H)
            _carve_path(grid, prev[0], prev[1], bx, by, W, H)

        # Connect last bead to central clearing
        last = mid_beads[-1] if mid_beads else first_c
        _carve_path(grid, last[0], last[1], center_x, center_y, W, H)

        all_chain_beads.append(chain)

        # Tributaries branch off interior beads (skip first — it's near the exit)
        interior = list(chain[1:])
        rng.shuffle(interior)
        for bx, by in interior[:_NUM_TRIBUTARIES]:
            ends = _branch_off(rng, grid, bx, by, W, H, max_depth=1)
            dead_ends.extend(ends)

    # ── 4. Place special tiles ───────────────────────────────────────────────────
    specials: set[tuple[int, int]] = set()

    # Tree City at center of central clearing
    grid[center_y][center_x] = "fst_tree_city"
    specials.add((center_x, center_y))

    # Exit tiles on boundary
    for ex, ey in exits:
        grid[ey][ex] = "fst_exit"

    # Ancient tree: farthest dead-end from center
    if dead_ends:
        far = max(dead_ends, key=lambda p: abs(p[0] - center_x) + abs(p[1] - center_y))
        if far not in specials:
            grid[far[1]][far[0]] = "fst_ancient_tree"
            specials.add(far)

    # Chests and mimics in remaining dead-ends
    remaining = [d for d in dead_ends if d not in specials]
    rng.shuffle(remaining)
    num_chests = min(4, len(remaining))
    num_mimics = min(5, max(0, len(remaining) - num_chests))
    for di, (dx, dy) in enumerate(remaining):
        if di < num_chests:
            grid[dy][dx] = "fst_chest"
        elif di < num_chests + num_mimics:
            grid[dy][dx] = "fst_mimic"
        else:
            break
        specials.add((dx, dy))

    # Nut trees scattered in chain clearings (not on specials, not near center)
    chain_flat = [b for chain in all_chain_beads for b in chain]
    rng.shuffle(chain_flat)
    nut_count = 0
    for bx, by in chain_flat:
        if nut_count >= rng.randint(4, 7):
            break
        if (bx, by) in specials:
            continue
        if abs(bx - center_x) + abs(by - center_y) < 10:
            continue   # don't place nut trees inside the central clearing area
        grid[by][bx] = "fst_nut_tree"
        specials.add((bx, by))
        nut_count += 1

    # ── 5. Build tile list ───────────────────────────────────────────────────────
    tiles: list[tuple[int, int, str]] = [
        (x, y, grid[y][x]) for y in range(H) for x in range(W)
    ]
    return W, H, tiles, exits


# ── Maze generation (kept for legacy forests) ────────────────────────────────────

def _generate_maze(
    maze_id: int, seed: int, forest_id: int,
) -> tuple[int, int, list[tuple[int, int, str]], int, int]:
    """Generate a 3-wide-path maze (legacy; new forests no longer include a maze door).

    Returns (width, height, tiles, entry_x, entry_y).
    """
    rng = random.Random(seed + _MAZE_SEED_OFFSET + maze_id * 3571 + forest_id * 1319)

    CELLS  = _MAZE_CELLS
    STRIDE = _MAZE_STRIDE
    W = MAZE_W
    H = MAZE_H

    grid: list[list[str]] = [["maze_wall"] * W for _ in range(H)]

    def _carve_cell(cx: int, cy: int) -> None:
        x0 = cx * STRIDE + 1
        y0 = cy * STRIDE + 1
        for ry in range(y0, y0 + 3):
            for rx in range(x0, x0 + 3):
                grid[ry][rx] = "maze_floor"

    def _carve_passage(cx: int, cy: int, dx: int, dy: int) -> None:
        if dx == 1:
            wx = cx * STRIDE + 4
            y0 = cy * STRIDE + 1
            for ry in range(y0, y0 + 3):
                grid[ry][wx] = "maze_floor"
        elif dx == -1:
            wx = (cx - 1) * STRIDE + 4
            y0 = cy * STRIDE + 1
            for ry in range(y0, y0 + 3):
                grid[ry][wx] = "maze_floor"
        elif dy == 1:
            wy = cy * STRIDE + 4
            x0 = cx * STRIDE + 1
            for rx in range(x0, x0 + 3):
                grid[wy][rx] = "maze_floor"
        elif dy == -1:
            wy = (cy - 1) * STRIDE + 4
            x0 = cx * STRIDE + 1
            for rx in range(x0, x0 + 3):
                grid[wy][rx] = "maze_floor"

    visited: set[tuple[int, int]] = set()
    stack = [(0, 0)]
    visited.add((0, 0))
    _carve_cell(0, 0)

    while stack:
        cx, cy = stack[-1]
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        rng.shuffle(dirs)
        moved = False
        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < CELLS and 0 <= ny < CELLS and (nx, ny) not in visited:
                _carve_cell(nx, ny)
                _carve_passage(cx, cy, dx, dy)
                visited.add((nx, ny))
                stack.append((nx, ny))
                moved = True
                break
        if not moved:
            stack.pop()

    entry_x = MAZE_ENTRY_X
    entry_y = MAZE_ENTRY_Y
    grid[0][entry_x] = "maze_exit"

    def _non_wall_adj(x: int, y: int) -> int:
        return sum(
            1 for ddx, ddy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
            if 0 <= x + ddx < W and 0 <= y + ddy < H
            and grid[y + ddy][x + ddx] != "maze_wall"
        )

    dead_ends: list[tuple[int, int, int]] = []
    for y in range(1, H):
        for x in range(W):
            if grid[y][x] == "maze_floor" and _non_wall_adj(x, y) == 1:
                dist = abs(x - entry_x) + y
                dead_ends.append((dist, x, y))

    dead_ends.sort(reverse=True)

    _MIMIC_MAX = 5
    for i, (_, tx, ty) in enumerate(dead_ends):
        if i == 0:
            grid[ty][tx] = "maze_chest"
        elif i == 1:
            grid[ty][tx] = "maze_exit"
        elif i <= 1 + _MIMIC_MAX:
            grid[ty][tx] = "maze_mimic"
        else:
            break

    tiles: list[tuple[int, int, str]] = [
        (x, y, grid[y][x]) for y in range(H) for x in range(W)
    ]
    return W, H, tiles, entry_x, entry_y


# ── DB creation ──────────────────────────────────────────────────────────────────

async def create_forest_area(
    seed: int,
    overworld_positions: list[tuple[int, int]],
    db,
) -> None:
    """Create one forest interior linked to overworld_positions entrances.

    Idempotent: silently skips if any position is already linked.
    New forests use the bead-chain design; no standalone maze is created.
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

    # Generate forest grid in a thread (CPU-heavy)
    width, height, forest_tiles, exit_positions = await asyncio.to_thread(
        _generate_forest_interior,
        forest_id, seed, overworld_positions[0][0], overworld_positions[0][1], n,
    )

    await db.execute(
        "UPDATE forest_areas SET width=?, height=? WHERE forest_id=?",
        (width, height, forest_id),
    )
    await db.executemany(
        "INSERT OR IGNORE INTO forest_tiles (forest_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(forest_id, lx, ly, tt) for lx, ly, tt in forest_tiles],
    )

    # Generate tree city floors for this forest (stored once at creation)
    tc_floors = _generate_tc_interior(forest_id)
    for floor_num, tiles in tc_floors.items():
        await db.executemany(
            "INSERT OR IGNORE INTO tree_city_tiles"
            "(forest_id, floor_num, local_x, local_y, tile_type) VALUES(?,?,?,?,?)",
            [(forest_id, floor_num, lx, ly, tt) for lx, ly, tt in tiles],
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
    """Find dense-forest edge positions and create FOREST_AREA_COUNT forest interiors."""
    rng = random.Random(seed ^ 0xF07E57)

    candidates: list[tuple[int, int]] = []
    WALKABLE_BIOMES = {"plains", "grass", "forest", "hills", "sand", "path"}

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

    chosen: list[tuple[int, int]] = []
    for pos in candidates:
        if len(chosen) >= FOREST_AREA_COUNT:
            break
        if not chosen or all(
            abs(pos[0] - cx) + abs(pos[1] - cy) >= FOREST_MIN_SEPARATION
            for cx, cy in chosen
        ):
            chosen.append(pos)

    for wx, wy in chosen:
        ow_entrances = [(wx, wy)]
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


# ── Lookup helpers ────────────────────────────────────────────────────────────────

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
    row = await db.fetch_one(
        "SELECT world_x, world_y FROM forest_entrances WHERE forest_id=? LIMIT 1",
        (forest_id,),
    )
    return (row["world_x"], row["world_y"]) if row else None


async def get_maze_for_forest(db, forest_id: int) -> int | None:
    """Return the maze_id linked to this forest, or None (new forests have no maze)."""
    row = await db.fetch_one(
        "SELECT maze_id FROM maze_areas WHERE forest_id=?", (forest_id,)
    )
    return row["maze_id"] if row else None


async def get_maze_exit_forest_pos(db, forest_id: int) -> tuple[int, int]:
    """Return the (local_x, local_y) of the fst_maze_door for this forest (legacy)."""
    row = await db.fetch_one(
        "SELECT local_x, local_y FROM forest_tiles"
        " WHERE forest_id=? AND tile_type='fst_maze_door' LIMIT 1",
        (forest_id,),
    )
    if row:
        return row["local_x"], row["local_y"]
    sz = await db.fetch_one(
        "SELECT width, height FROM forest_areas WHERE forest_id=?", (forest_id,)
    )
    if sz:
        return sz["width"] // 2, sz["height"] // 2
    return 5, 5


# ── Viewport loading ──────────────────────────────────────────────────────────────

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


# ── Tree City interior ────────────────────────────────────────────────────────────

TC_W = 15   # floor width
TC_H = 7    # floor height
TC_NUM_FLOORS = 3


def _generate_tc_interior(forest_id: int) -> dict[int, list[tuple[int, int, str]]]:
    """Generate 3-floor tree city interior. Layout is the same for all forests."""
    # Floor layout: (floor_num -> list of (x, y, tile_override) for non-floor special tiles)
    specials: dict[int, list[tuple[int, int, str]]] = {
        1: [
            (7, 6, "tc_door"),         # exit (south wall)
            (7, 1, "tc_stair_up"),     # stairs up (north)
            (2, 2, "tc_shop"),         # merchant left
            (2, 4, "tc_shop"),
            (12, 2, "tc_counter"),     # counter right
            (12, 4, "tc_counter"),
        ],
        2: [
            (7, 5, "tc_stair_down"),
            (7, 1, "tc_stair_up"),
            (1, 2, "tc_bed"),
            (1, 3, "tc_bed"),
            (1, 4, "tc_bed"),
            (13, 3, "tc_shop"),
        ],
        3: [
            (7, 5, "tc_stair_down"),
            (7, 3, "tc_elder"),        # elder NPC center
            (1, 2, "tc_bed"),
            (1, 4, "tc_bed"),
            (13, 2, "tc_bed"),
            (13, 4, "tc_bed"),
        ],
    }

    floors: dict[int, list[tuple[int, int, str]]] = {}
    for floor_num in range(1, TC_NUM_FLOORS + 1):
        tiles: list[tuple[int, int, str]] = []
        override = {(sx, sy): st for sx, sy, st in specials.get(floor_num, [])}
        for y in range(TC_H):
            for x in range(TC_W):
                if (x, y) in override:
                    tiles.append((x, y, override[(x, y)]))
                elif y == 0 or y == TC_H - 1 or x == 0 or x == TC_W - 1:
                    tiles.append((x, y, "tc_wall"))
                else:
                    tiles.append((x, y, "tc_floor"))
        floors[floor_num] = tiles
    return floors


async def ensure_tree_city_built(forest_id: int, db) -> None:
    """Lazily generate tree city floors for this forest if not yet stored."""
    existing = await db.fetch_one(
        "SELECT 1 FROM tree_city_tiles WHERE forest_id=? LIMIT 1", (forest_id,)
    )
    if existing:
        return
    floors = _generate_tc_interior(forest_id)
    for floor_num, tiles in floors.items():
        await db.executemany(
            "INSERT OR IGNORE INTO tree_city_tiles"
            "(forest_id, floor_num, local_x, local_y, tile_type) VALUES(?,?,?,?,?)",
            [(forest_id, floor_num, lx, ly, tt) for lx, ly, tt in tiles],
        )


async def load_tree_city_viewport(
    forest_id: int, floor_num: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    """Load a 7×7 viewport of a tree city floor."""
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM tree_city_tiles"
        " WHERE forest_id=? AND floor_num=?"
        " AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (forest_id, floor_num, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row.append(TileData(
                terrain=tile_map.get((cx, cy), "tc_wall"),
                world_x=cx, world_y=cy,
            ))
        grid.append(row)
    return grid


async def load_tree_city_single_tile(
    forest_id: int, floor_num: int, local_x: int, local_y: int, db,
) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM tree_city_tiles"
        " WHERE forest_id=? AND floor_num=? AND local_x=? AND local_y=?",
        (forest_id, floor_num, local_x, local_y),
    )
    return TileData(
        terrain=row["tile_type"] if row else "tc_wall",
        world_x=local_x, world_y=local_y,
    )
