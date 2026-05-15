"""Dense forest interior generation, maze generation, and viewport loading."""
from __future__ import annotations

import asyncio
import math
import math as _math
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
    forest_id: int, seed: int, world_x: int, world_y: int, num_exits: int = 1,
) -> tuple[int, int, list[tuple[int, int, str]], list[tuple[int, int]], tuple[int, int]]:
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

    # Decorative trees scattered inside the central clearing
    for _ty_dec in range(center_y - _CENTRAL_R + 1, center_y + _CENTRAL_R):
        for _tx_dec in range(center_x - _CENTRAL_R + 1, center_x + _CENTRAL_R):
            _d2 = (_tx_dec - center_x) ** 2 + (_ty_dec - center_y) ** 2
            # Only in inner zone (not outermost ring — keep paths clear)
            if 4 <= _d2 <= (_CENTRAL_R - 2) ** 2:
                if (_tx_dec, _ty_dec) not in specials and grid[_ty_dec][_tx_dec] == "fst_floor":
                    if rng.random() < 0.22:
                        grid[_ty_dec][_tx_dec] = "fst_tree"

    # Exit tiles on boundary
    for ex, ey in exits:
        grid[ey][ex] = "fst_exit"

    # Ancient tree: farthest dead-end from center
    if dead_ends:
        far = max(dead_ends, key=lambda p: abs(p[0] - center_x) + abs(p[1] - center_y))
        if far not in specials:
            grid[far[1]][far[0]] = "fst_ancient_tree"
            specials.add(far)

    # Place exactly 5 chest positions (all stored as fst_chest; mimic randomised at runtime)
    # Pick the 5 dead-ends that are farthest from the center
    remaining = [d for d in dead_ends if d not in specials]
    remaining.sort(key=lambda p: -(abs(p[0] - center_x) + abs(p[1] - center_y)))
    for (cx2, cy2) in remaining[:5]:
        grid[cy2][cx2] = "fst_chest"
        specials.add((cx2, cy2))

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

    # Wayerwood target: a fst_tree tile just outside the central clearing
    _ww_angle = _math.radians((forest_id * 73 + seed * 37) % 360)
    _ww_tx = center_x + round((_CENTRAL_R + 1) * _math.cos(_ww_angle))
    _ww_ty = center_y + round((_CENTRAL_R + 1) * _math.sin(_ww_angle))
    _ww_tx = max(1, min(W - 2, _ww_tx))
    _ww_ty = max(1, min(H - 2, _ww_ty))
    # Ensure it's actually a tree tile; if not, search nearby
    for _da in range(0, 360, 10):
        _r2 = _math.radians(_da)
        _cx2 = center_x + round((_CENTRAL_R + 1) * _math.cos(_r2))
        _cy2 = center_y + round((_CENTRAL_R + 1) * _math.sin(_r2))
        _cx2 = max(1, min(W - 2, _cx2))
        _cy2 = max(1, min(H - 2, _cy2))
        if grid[_cy2][_cx2] == "fst_tree":
            _ww_tx, _ww_ty = _cx2, _cy2
            break
    wayerwood_target = (_ww_tx, _ww_ty)

    return W, H, tiles, exits, wayerwood_target


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
    width, height, forest_tiles, exit_positions, wayerwood_target = await asyncio.to_thread(
        _generate_forest_interior,
        forest_id, seed, overworld_positions[0][0], overworld_positions[0][1], n,
    )

    await db.execute(
        "UPDATE forest_areas SET width=?, height=? WHERE forest_id=?",
        (width, height, forest_id),
    )

    # Store wayerwood target tile
    _ww_tx_store, _ww_ty_store = wayerwood_target
    await db.execute(
        "UPDATE forest_areas SET wayerwood_tx=?, wayerwood_ty=? WHERE forest_id=?",
        (_ww_tx_store, _ww_ty_store, forest_id),
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

from dwarf_explorer.config import TC_W, TC_H, TC_NUM_FLOORS

_TC_CX = 14       # ellipse center X
_TC_CY = 12       # ellipse center Y
_TC_RX = 9.0      # ellipse X radius
_TC_RY = 8.0      # ellipse Y radius
_TC_ENTRY_X, _TC_ENTRY_Y = 14, 21   # player spawn when entering from forest
_TC_LAND_UP_X, _TC_LAND_UP_Y = 14, 7     # spawn when arriving via stair UP (south of north alcove)
_TC_LAND_DOWN_X, _TC_LAND_DOWN_Y = 14, 17 # spawn when arriving via stair DOWN (north of south alcove)

# ── Grove constants ─────────────────────────────────────────────────────────────
_GROVE_W  = 19
_GROVE_H  = 19
_GROVE_R  = 7
_GROVE_CX = 9
_GROVE_CY = 9


def _in_tc_ellipse(x: int, y: int) -> bool:
    return ((x - _TC_CX) / _TC_RX) ** 2 + ((y - _TC_CY) / _TC_RY) ** 2 < 1.0


def _tc_fill(grid: list[list[str]], x1: int, y1: int, x2: int, y2: int,
             tile: str = "tc_floor") -> None:
    for y in range(max(0, y1), min(TC_H, y2 + 1)):
        for x in range(max(0, x1), min(TC_W, x2 + 1)):
            grid[y][x] = tile


def _tc_set(grid: list[list[str]], x: int, y: int, tile: str) -> None:
    if 0 <= x < TC_W and 0 <= y < TC_H:
        grid[y][x] = tile


def _tc_room_walls(grid: list[list[str]], x1: int, y1: int, x2: int, y2: int,
                   door_side: str = "left", door_pos: int | None = None) -> None:
    """Fill a room rect with floor, draw log-wall perimeter, then open one door gap.

    Args:
        door_side: 'left' | 'right' | 'top' | 'bottom'
        door_pos:  y-coord for left/right door; x-coord for top/bottom door (default = centre)
    """
    # Fill interior
    for y in range(max(0, y1), min(TC_H, y2 + 1)):
        for x in range(max(0, x1), min(TC_W, x2 + 1)):
            grid[y][x] = "tc_floor"
    # Perimeter walls
    for x in range(max(0, x1), min(TC_W, x2 + 1)):
        if 0 <= y1 < TC_H: grid[y1][x] = "tc_wall"
        if 0 <= y2 < TC_H: grid[y2][x] = "tc_wall"
    for y in range(max(0, y1), min(TC_H, y2 + 1)):
        if 0 <= x1 < TC_W: grid[y][x1] = "tc_wall"
        if 0 <= x2 < TC_W: grid[y][x2] = "tc_wall"
    # Door gap
    if door_side == "left":
        dp = door_pos if door_pos is not None else (y1 + y2) // 2
        _tc_set(grid, x1, dp, "tc_floor")
    elif door_side == "right":
        dp = door_pos if door_pos is not None else (y1 + y2) // 2
        _tc_set(grid, x2, dp, "tc_floor")
    elif door_side == "top":
        dp = door_pos if door_pos is not None else (x1 + x2) // 2
        _tc_set(grid, dp, y1, "tc_floor")
    elif door_side == "bottom":
        dp = door_pos if door_pos is not None else (x1 + x2) // 2
        _tc_set(grid, dp, y2, "tc_floor")


def _gen_tc_floor(floor_num: int) -> list[list[str]]:
    """Generate a single tree-city floor as a 2-D grid of tile-type strings.

    All floors share the same elliptical trunk interior.  Rooms are enclosed
    rectangular alcoves with log-wall perimeters and a single doorway each.
    """
    # ── Base: solid log walls ──────────────────────────────────────────────
    grid = [["tc_wall"] * TC_W for _ in range(TC_H)]

    # ── Carve elliptical trunk interior ────────────────────────────────────
    for y in range(TC_H):
        for x in range(TC_W):
            if _in_tc_ellipse(x, y):
                grid[y][x] = "tc_floor"

    # ── North stair alcove (floors 1-3): x=12..16, y=1..5 ─────────────────
    # Door at bottom-centre (14, 5) opens into main hall.
    if floor_num < 4:
        _tc_room_walls(grid, 12, 1, 16, 5, door_side="bottom", door_pos=14)
        _tc_set(grid, 14, 2, "tc_stair_up")
        _tc_set(grid, 13, 3, "tc_lantern")
        _tc_set(grid, 15, 3, "tc_lantern")

    # ── South stair alcove (floors 2-4): x=12..16, y=19..22 ───────────────
    # Door at top-centre (14, 19) opens into main hall.
    if floor_num > 1:
        _tc_room_walls(grid, 12, 19, 16, 22, door_side="top", door_pos=14)
        _tc_set(grid, 14, 21, "tc_stair_down")
        _tc_set(grid, 13, 22, "tc_lantern")
        _tc_set(grid, 15, 22, "tc_lantern")

    # ══════════════════════════════════════════════════════════════════════
    # ── Floor 1: Entry Hall ───────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════
    if floor_num == 1:
        # South entry corridor (extends past ellipse to the door)
        for y in range(20, 23):
            _tc_set(grid, 14, y, "tc_floor")   # centre tile is floor
            _tc_set(grid, 13, y, "tc_wall")    # left log wall
            _tc_set(grid, 15, y, "tc_wall")    # right log wall
        _tc_set(grid, 14, 23, "tc_door")

        # ── East market room: x=20..27, y=8..16 ──────────────────────────
        # Door in left wall at y=12.  One shop NPC (tc_shop) at (25,12).
        _tc_room_walls(grid, 20, 8, 27, 16, door_side="left", door_pos=12)
        # Counter along the east inner wall
        for cy in range(9, 16):
            _tc_set(grid, 26, cy, "tc_counter")
        # Rug in the middle of the room
        _tc_fill(grid, 21, 9, 24, 15, "tc_rug")
        # Decorations
        _tc_set(grid, 21, 9,  "tc_lantern")
        _tc_set(grid, 21, 15, "tc_lantern")
        _tc_set(grid, 25, 9,  "tc_plant")
        _tc_set(grid, 25, 15, "tc_plant")
        # Shop NPC (overwrites rug if necessary)
        _tc_set(grid, 25, 12, "tc_shop")

        # ── West storage room: x=1..8, y=9..15 ───────────────────────────
        # Door in right wall at y=12.
        _tc_room_walls(grid, 1, 9, 8, 15, door_side="right", door_pos=12)
        _tc_set(grid, 2, 10, "tc_barrel")
        _tc_set(grid, 2, 11, "tc_barrel")
        _tc_set(grid, 2, 13, "tc_barrel")
        _tc_set(grid, 2, 14, "tc_barrel")
        _tc_set(grid, 5, 12, "tc_table")
        _tc_set(grid, 7, 10, "tc_lantern")
        _tc_set(grid, 7, 14, "tc_lantern")
        _tc_set(grid, 4, 10, "tc_plant")
        _tc_set(grid, 4, 14, "tc_plant")

        # ── Main hall decorations ─────────────────────────────────────────
        _tc_fill(grid, 13, 7, 15, 18, "tc_rug")   # central rug runner
        _tc_set(grid, 9,  8,  "tc_lantern")
        _tc_set(grid, 19, 8,  "tc_lantern")
        _tc_set(grid, 9,  16, "tc_lantern")
        _tc_set(grid, 19, 16, "tc_lantern")
        _tc_set(grid, 9,  12, "tc_plant")
        _tc_set(grid, 19, 12, "tc_plant")
        # Quest villager in south-west area of the main hall
        _tc_set(grid, 10, 15, "tc_villager")
        # Restore stair (rug runner may have overwritten)
        _tc_set(grid, 14, 2, "tc_stair_up")

    # ══════════════════════════════════════════════════════════════════════
    # ── Floor 2: Living Quarters ──────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════
    elif floor_num == 2:
        # ── East bedroom wing — two stacked rooms ─────────────────────────
        # Room A (upper): x=20..27, y=7..13  door left at y=10
        _tc_room_walls(grid, 20, 7, 27, 13, door_side="left", door_pos=10)
        _tc_set(grid, 25, 8,  "tc_bed")
        _tc_set(grid, 26, 8,  "tc_bed")
        _tc_set(grid, 25, 9,  "tc_bed")
        _tc_set(grid, 26, 9,  "tc_bed")
        _tc_set(grid, 23, 11, "tc_table")
        _tc_set(grid, 21, 8,  "tc_lantern")
        _tc_set(grid, 27, 12, "tc_plant")

        # Room B (lower): x=20..27, y=14..20  door left at y=17
        _tc_room_walls(grid, 20, 14, 27, 20, door_side="left", door_pos=17)
        _tc_set(grid, 25, 18, "tc_bed")
        _tc_set(grid, 26, 18, "tc_bed")
        _tc_set(grid, 25, 19, "tc_bed")
        _tc_set(grid, 26, 19, "tc_bed")
        _tc_set(grid, 23, 16, "tc_table")
        _tc_set(grid, 21, 19, "tc_lantern")
        _tc_set(grid, 27, 15, "tc_plant")

        # ── West library: x=1..8, y=8..17  door right at y=12 ────────────
        _tc_room_walls(grid, 1, 8, 8, 17, door_side="right", door_pos=12)
        for _by in [9, 10, 11, 13, 14, 15, 16]:
            _tc_set(grid, 2, _by, "tc_bookshelf")
        _tc_set(grid, 2, 12, "tc_lantern")
        _tc_set(grid, 7, 9,  "tc_lantern")
        _tc_set(grid, 7, 15, "tc_lantern")
        _tc_set(grid, 5, 10, "tc_table")
        _tc_set(grid, 5, 15, "tc_table")
        _tc_set(grid, 4, 13, "tc_plant")
        _tc_fill(grid, 3, 11, 6, 14, "tc_rug")

        # ── Main hall decorations + quest villager ────────────────────────
        _tc_fill(grid, 13, 7, 15, 18, "tc_rug")
        _tc_set(grid, 9,  8,  "tc_lantern")
        _tc_set(grid, 19, 8,  "tc_lantern")
        _tc_set(grid, 9,  16, "tc_lantern")
        _tc_set(grid, 19, 16, "tc_lantern")
        _tc_set(grid, 9,  12, "tc_plant")
        _tc_set(grid, 19, 12, "tc_plant")
        # Quest villager in north-east area of main hall
        _tc_set(grid, 18, 9, "tc_villager")
        # Restore stairs
        _tc_set(grid, 14, 2,  "tc_stair_up")
        _tc_set(grid, 14, 21, "tc_stair_down")

    # ══════════════════════════════════════════════════════════════════════
    # ── Floor 3: Upper Hall ───────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════
    elif floor_num == 3:
        # ── West bedroom wing — two stacked rooms ─────────────────────────
        # Room A (upper): x=1..8, y=7..13  door right at y=10
        _tc_room_walls(grid, 1, 7, 8, 13, door_side="right", door_pos=10)
        _tc_set(grid, 2, 8,  "tc_bed")
        _tc_set(grid, 3, 8,  "tc_bed")
        _tc_set(grid, 2, 9,  "tc_bed")
        _tc_set(grid, 3, 9,  "tc_bed")
        _tc_set(grid, 5, 11, "tc_table")
        _tc_set(grid, 7, 8,  "tc_lantern")
        _tc_set(grid, 1, 12, "tc_plant")

        # Room B (lower): x=1..8, y=14..20  door right at y=17
        _tc_room_walls(grid, 1, 14, 8, 20, door_side="right", door_pos=17)
        _tc_set(grid, 2, 18, "tc_bed")
        _tc_set(grid, 3, 18, "tc_bed")
        _tc_set(grid, 2, 19, "tc_bed")
        _tc_set(grid, 3, 19, "tc_bed")
        _tc_set(grid, 5, 16, "tc_table")
        _tc_set(grid, 7, 19, "tc_lantern")
        _tc_set(grid, 1, 15, "tc_plant")

        # ── North shrine alcove: x=10..18, y=1..5  door bottom at x=14 ───
        _tc_room_walls(grid, 10, 1, 18, 5, door_side="bottom", door_pos=14)
        _tc_set(grid, 14, 2, "tc_shrine")
        _tc_set(grid, 11, 3, "tc_lantern")
        _tc_set(grid, 17, 3, "tc_lantern")
        _tc_set(grid, 12, 2, "tc_plant")
        _tc_set(grid, 16, 2, "tc_plant")
        _tc_fill(grid, 11, 4, 17, 4, "tc_rug")

        # ── Main hall decorations ─────────────────────────────────────────
        _tc_fill(grid, 13, 7, 15, 18, "tc_rug")
        _tc_set(grid, 9,  8,  "tc_lantern")
        _tc_set(grid, 19, 8,  "tc_lantern")
        _tc_set(grid, 9,  16, "tc_lantern")
        _tc_set(grid, 19, 16, "tc_lantern")
        _tc_set(grid, 9,  12, "tc_plant")
        _tc_set(grid, 19, 12, "tc_plant")
        # Restore stairs
        _tc_set(grid, 14, 2,  "tc_stair_up")
        _tc_set(grid, 14, 21, "tc_stair_down")

    # ══════════════════════════════════════════════════════════════════════
    # ── Floor 4: Elder's Chamber ──────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════
    elif floor_num == 4:
        # ── North ceremony alcove (wide): x=8..20, y=1..6  door bottom x=14 ─
        _tc_room_walls(grid, 8, 1, 20, 6, door_side="bottom", door_pos=14)
        _tc_set(grid, 10, 2, "tc_shrine")
        _tc_set(grid, 18, 2, "tc_shrine")
        _tc_set(grid, 9,  2, "tc_lantern")
        _tc_set(grid, 19, 2, "tc_lantern")
        _tc_set(grid, 12, 2, "tc_plant")
        _tc_set(grid, 16, 2, "tc_plant")
        _tc_fill(grid, 9, 3, 19, 5, "tc_rug")
        _tc_set(grid, 14, 2, "tc_elder")   # elder NPC at ceremony altar

        # ── East shrine alcove: x=21..27, y=9..15  door left at y=12 ─────
        _tc_room_walls(grid, 21, 9, 27, 15, door_side="left", door_pos=12)
        _tc_fill(grid, 22, 10, 26, 14, "tc_rug")
        _tc_set(grid, 24, 11, "tc_shrine")
        _tc_set(grid, 24, 13, "tc_shrine")
        _tc_set(grid, 22, 9,  "tc_lantern")
        _tc_set(grid, 26, 9,  "tc_lantern")
        _tc_set(grid, 22, 15, "tc_lantern")
        _tc_set(grid, 26, 15, "tc_lantern")

        # ── West meditation alcove: x=1..7, y=9..15  door right at y=12 ──
        _tc_room_walls(grid, 1, 9, 7, 15, door_side="right", door_pos=12)
        _tc_fill(grid, 2, 10, 6, 14, "tc_rug")
        _tc_set(grid, 4, 11, "tc_shrine")
        _tc_set(grid, 4, 13, "tc_shrine")
        _tc_set(grid, 2, 9,  "tc_lantern")
        _tc_set(grid, 6, 9,  "tc_lantern")
        _tc_set(grid, 2, 15, "tc_lantern")
        _tc_set(grid, 6, 15, "tc_lantern")

        # ── Main hall: ceremonial approach ────────────────────────────────
        _tc_fill(grid, 13, 7, 15, 18, "tc_rug")
        _tc_set(grid, 9,  9,  "tc_lantern")
        _tc_set(grid, 19, 9,  "tc_lantern")
        _tc_set(grid, 9,  15, "tc_lantern")
        _tc_set(grid, 19, 15, "tc_lantern")
        _tc_set(grid, 9,  12, "tc_plant")
        _tc_set(grid, 19, 12, "tc_plant")
        # Restore stair_down (rug may have overwritten)
        _tc_set(grid, 14, 21, "tc_stair_down")

    return grid


def _generate_tc_interior(forest_id: int) -> dict[int, list[tuple[int, int, str]]]:
    """Generate all floors of the tree city interior."""
    floors: dict[int, list[tuple[int, int, str]]] = {}
    for floor_num in range(1, TC_NUM_FLOORS + 1):
        grid = _gen_tc_floor(floor_num)
        tiles: list[tuple[int, int, str]] = []
        for y in range(TC_H):
            for x in range(TC_W):
                tiles.append((x, y, grid[y][x]))
        floors[floor_num] = tiles
    return floors


async def ensure_tree_city_built(forest_id: int, db) -> bool:
    """Lazily generate (or rebuild) tree city floors. Returns True if rebuilt."""
    expected = TC_W * TC_H * TC_NUM_FLOORS
    row = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM tree_city_tiles WHERE forest_id=?", (forest_id,)
    )
    if row and row["cnt"] == expected:
        return False   # already up to date
    # Clear stale tiles and rebuild
    await db.execute("DELETE FROM tree_city_tiles WHERE forest_id=?", (forest_id,))
    floors = _generate_tc_interior(forest_id)
    for floor_num, tiles in floors.items():
        await db.executemany(
            "INSERT OR IGNORE INTO tree_city_tiles"
            "(forest_id, floor_num, local_x, local_y, tile_type) VALUES(?,?,?,?,?)",
            [(forest_id, floor_num, lx, ly, tt) for lx, ly, tt in tiles],
        )
    return True


async def load_tree_city_viewport(
    forest_id: int, floor_num: int, center_x: int, center_y: int, db,
) -> list[list[TileData]]:
    """Load a 9×9 viewport of a tree city floor centred on (center_x, center_y)."""
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


# ── Grove interior ────────────────────────────────────────────────────────────────

def _generate_grove(forest_id: int, seed: int) -> list[tuple[int, int, str]]:
    """Generate a small circular grove with a statue at the centre."""
    rng = random.Random(seed ^ forest_id * 0xA5B5C5)
    W, H = _GROVE_W, _GROVE_H
    cx, cy = _GROVE_CX, _GROVE_CY
    grid: list[list[str]] = [["grove_wall"] * W for _ in range(H)]

    # Carve circular clearing
    for gy in range(H):
        for gx in range(W):
            if (gx - cx) ** 2 + (gy - cy) ** 2 <= _GROVE_R ** 2:
                grid[gy][gx] = "grove_floor"

    # Statue at centre
    grid[cy][cx] = "grove_statue"

    # Sparse decorative trees inside
    for gy in range(H):
        for gx in range(W):
            if grid[gy][gx] == "grove_floor" and (gx, gy) != (cx, cy):
                d2 = (gx - cx) ** 2 + (gy - cy) ** 2
                if d2 >= (_GROVE_R - 2) ** 2 and rng.random() < 0.25:
                    grid[gy][gx] = "grove_wall"

    # Exit at south wall
    grid[cy + _GROVE_R][cx] = "grove_exit"

    return [(gx, gy, grid[gy][gx]) for gy in range(H) for gx in range(W)]


async def ensure_grove_built(forest_id: int, db) -> int:
    """Lazily build the grove for this forest. Returns grove_id."""
    row = await db.fetch_one(
        "SELECT grove_id FROM grove_areas WHERE forest_id=?", (forest_id,)
    )
    if row:
        return row["grove_id"]
    # Build it
    seed_row = await db.fetch_one("SELECT seed FROM world WHERE guild_id=0")
    seed = seed_row["seed"] if seed_row else forest_id
    grove_tiles = _generate_grove(forest_id, seed)
    cur = await db.execute(
        "INSERT INTO grove_areas (forest_id, width, height) VALUES (?, ?, ?)",
        (forest_id, _GROVE_W, _GROVE_H),
    )
    grove_id = cur.lastrowid
    await db.executemany(
        "INSERT OR IGNORE INTO grove_tiles (grove_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        [(grove_id, gx, gy, tt) for gx, gy, tt in grove_tiles],
    )
    return grove_id


async def load_grove_viewport(
    grove_id: int, center_x: int, center_y: int, db,
) -> list:
    """Load a 9×9 viewport of the grove centred on (center_x, center_y)."""
    from dwarf_explorer.config import VIEWPORT_SIZE, VIEWPORT_CENTER
    from dwarf_explorer.world.generator import TileData
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM grove_tiles"
        " WHERE grove_id=? AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (grove_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}
    grid = []
    for vy in range(VIEWPORT_SIZE):
        row = []
        for vx in range(VIEWPORT_SIZE):
            cx2 = x_min + vx
            cy2 = y_min + vy
            row.append(TileData(terrain=tile_map.get((cx2, cy2), "grove_wall"), world_x=cx2, world_y=cy2))
        grid.append(row)
    return grid


async def load_grove_single_tile(grove_id: int, local_x: int, local_y: int, db):
    from dwarf_explorer.world.generator import TileData
    row = await db.fetch_one(
        "SELECT tile_type FROM grove_tiles WHERE grove_id=? AND local_x=? AND local_y=?",
        (grove_id, local_x, local_y),
    )
    return TileData(terrain=row["tile_type"] if row else "grove_wall", world_x=local_x, world_y=local_y)


async def get_wayerwood_target(forest_id: int, db) -> tuple[int, int] | None:
    """Return the wayerwood target (local_x, local_y) for this forest, or None."""
    row = await db.fetch_one(
        "SELECT wayerwood_tx, wayerwood_ty FROM forest_areas WHERE forest_id=?",
        (forest_id,),
    )
    if row and row["wayerwood_tx"] is not None:
        return row["wayerwood_tx"], row["wayerwood_ty"]
    return None
