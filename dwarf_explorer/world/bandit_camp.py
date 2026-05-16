"""Bandit camp interior generator.

Each bandit_camp overworld tile has a deterministic 11×11 interior grid.
The player enters from the south (bottom) and exits via the bc_exit tile.
"""
from __future__ import annotations

import random as _random

from dwarf_explorer.config import (
    BANDIT_CAMP_SIZE,
    BANDIT_CAMP_EMOJI,
    BANDIT_CAMP_WALKABLE,
    VIEWPORT_SIZE,
    VIEWPORT_CENTER,
)
from dwarf_explorer.world.generator import TileData

# ── Grid generation ──────────────────────────────────────────────────────────

# Player entry position (row, col) inside the 11×11 grid
# Row 9 is just inside the fence gap at the bottom.
BC_ENTRY_X = 5   # col 5 = horizontal centre
BC_ENTRY_Y = 9   # row 9 = just inside south fence


def generate_camp_grid(camp_wx: int, camp_wy: int) -> list[list[str]]:
    """Return an 11×11 list-of-lists of tile type strings.

    Layout (. = bc_dirt, F = bc_fence, B = bc_bandit,
            T = bc_tent, C = bc_campfire, X = bc_exit, # = bc_void):

        Row 0: # # # # # # # # # # #   (void outside camp)
        Row 1: # F F F F F F F F F #   (top fence)
        Row 2: # F . . . . . . . F #
        Row 3: # F . B . . . B . F #
        Row 4: # F . . T . T . . F #
        Row 5: # F . . . C . . . F #   (campfire centre)
        Row 6: # F . . T . T . . F #
        Row 7: # F . B . . . B . F #
        Row 8: # F . . . . . . . F #
        Row 9: # F F F F X F F F F #   (south fence with exit gap)
        Row10: # # # # # X # # # # #   (void, X = player spawns here)
    """
    rng = _random.Random(hash((camp_wx, camp_wy, "bc_gen")))

    S = BANDIT_CAMP_SIZE  # 11
    grid = [["bc_void"] * S for _ in range(S)]

    # ── Outer fence ring (rows 1 and 9, cols 1 and 9) ────────────────────────
    for col in range(1, S - 1):           # top fence
        grid[1][col] = "bc_fence"
    for col in range(1, S - 1):           # bottom fence
        grid[9][col] = "bc_fence"
    for row in range(1, 10):              # left + right fence
        grid[row][1] = "bc_fence"
        grid[row][S - 2] = "bc_fence"

    # Exit gap in south fence (centre column)
    grid[9][5] = "bc_exit"

    # ── Interior floor ────────────────────────────────────────────────────────
    for row in range(2, 9):
        for col in range(2, S - 2):
            grid[row][col] = "bc_dirt"

    # ── Campfire in centre ────────────────────────────────────────────────────
    grid[5][5] = "bc_campfire"

    # ── Tents (2-3 tents at corners of interior) ──────────────────────────────
    tent_candidates = [(3, 3), (3, 7), (7, 3), (7, 7), (2, 6), (6, 2)]
    rng.shuffle(tent_candidates)
    tent_count = rng.randint(2, 3)
    placed_tents: set[tuple[int, int]] = set()
    for row, col in tent_candidates[:tent_count]:
        if 2 <= row <= 8 and 2 <= col <= 8:
            grid[row][col] = "bc_tent"
            placed_tents.add((row, col))

    # ── Log pile / crate (1-2 decorations) ────────────────────────────────────
    deco_candidates = [(2, 7), (8, 3), (8, 7), (2, 3), (4, 7), (6, 3)]
    rng.shuffle(deco_candidates)
    deco_type = rng.choice(["bc_log", "bc_crate"])
    for row, col in deco_candidates[:rng.randint(1, 2)]:
        if grid[row][col] == "bc_dirt":
            grid[row][col] = deco_type

    # ── Bandits (3-5, avoiding tent/campfire/crate positions) ────────────────
    bandit_candidates = [
        (3, 4), (3, 6), (4, 3), (4, 7),
        (5, 3), (5, 7), (6, 4), (6, 6),
        (7, 4), (7, 6), (3, 5), (7, 5),
    ]
    rng.shuffle(bandit_candidates)
    bandit_count = rng.randint(3, 5)
    placed = 0
    for row, col in bandit_candidates:
        if placed >= bandit_count:
            break
        if grid[row][col] == "bc_dirt":
            grid[row][col] = "bc_bandit"
            placed += 1

    return grid


# ── Viewport loading ──────────────────────────────────────────────────────────

def _tile(tile_type: str, lx: int, ly: int, camp_wx: int, camp_wy: int) -> TileData:
    """Build a TileData for a bandit camp interior cell."""
    emoji = BANDIT_CAMP_EMOJI.get(tile_type, "⬛")
    walkable = tile_type in BANDIT_CAMP_WALKABLE
    td = TileData(
        terrain=tile_type,
        emoji=emoji,
        walkable=walkable,
        world_x=lx,
        world_y=ly,
    )
    return td


def load_camp_viewport(
    bc_x: int, bc_y: int, camp_wx: int, camp_wy: int
) -> list[list[TileData | None]]:
    """Return a 9×9 viewport grid centred on (bc_x, bc_y) inside the camp."""
    grid_data = generate_camp_grid(camp_wx, camp_wy)
    S = BANDIT_CAMP_SIZE   # 11
    vp = VIEWPORT_SIZE     # 9
    vc = VIEWPORT_CENTER   # 4

    viewport: list[list[TileData | None]] = [[None] * vp for _ in range(vp)]
    for vr in range(vp):
        for vc_col in range(vp):
            gx = bc_x + (vc_col - vc)
            gy = bc_y + (vr - vc)
            if 0 <= gx < S and 0 <= gy < S:
                viewport[vr][vc_col] = _tile(grid_data[gy][gx], gx, gy, camp_wx, camp_wy)
            else:
                viewport[vr][vc_col] = _tile("bc_void", gx, gy, camp_wx, camp_wy)
    return viewport


def get_bandit_positions(camp_wx: int, camp_wy: int) -> list[tuple[int, int]]:
    """Return list of (bc_x, bc_y) positions of bandit tiles in this camp."""
    grid_data = generate_camp_grid(camp_wx, camp_wy)
    positions = []
    for row in range(BANDIT_CAMP_SIZE):
        for col in range(BANDIT_CAMP_SIZE):
            if grid_data[row][col] == "bc_bandit":
                positions.append((col, row))  # (x=col, y=row)
    return positions
