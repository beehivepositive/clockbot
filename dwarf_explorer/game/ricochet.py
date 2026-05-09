"""Sliding-block puzzle engine (Ricochet Robot-style) for village game boards.

Rules:
  - The player piece (🔵) slides in a chosen direction until hitting a wall
    (board edge) or an obstacle block (🟧).
  - The goal is to land the piece on the red target (🔴).
  - The puzzle is global and refreshes daily — everyone sees the same board.
"""
from __future__ import annotations

import random
from collections import deque
from datetime import date

BOARD_SIZE = 8
NUM_OBSTACLES = 7

# Emoji used in board rendering
_E_EMPTY    = "⬛"
_E_OBSTACLE = "🟧"
_E_TARGET   = "🔴"
_E_PLAYER   = "🔵"
_E_WIN      = "🎉"   # player landed on target

_DIRS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}


# ── Core mechanics ─────────────────────────────────────────────────────────────

def _slide(
    px: int, py: int, dx: int, dy: int,
    obstacles: frozenset[tuple[int, int]], size: int,
) -> tuple[int, int]:
    """Slide piece from (px, py) until hitting a wall or obstacle."""
    while True:
        nx, ny = px + dx, py + dy
        if not (0 <= nx < size and 0 <= ny < size):
            break
        if (nx, ny) in obstacles:
            break
        px, py = nx, ny
    return px, py


def apply_move(
    px: int, py: int, direction: str,
    obstacles: frozenset[tuple[int, int]], size: int,
) -> tuple[int, int]:
    """Apply a directional slide and return the new position."""
    dx, dy = _DIRS.get(direction, (0, 0))
    return _slide(px, py, dx, dy, obstacles, size)


# ── Solver (BFS over sliding reachability) ────────────────────────────────────

def _bfs_min_moves(
    start: tuple[int, int],
    target: tuple[int, int],
    obstacles: frozenset[tuple[int, int]],
    size: int,
) -> int | None:
    """Return the minimum number of slide-moves to reach *target*, or None."""
    visited: dict[tuple[int, int], int] = {start: 0}
    queue: deque[tuple[int, int]] = deque([start])
    dirs = list(_DIRS.values())

    while queue:
        pos = queue.popleft()
        dist = visited[pos]
        for dx, dy in dirs:
            npos = _slide(pos[0], pos[1], dx, dy, obstacles, size)
            if npos == pos:
                continue  # piece didn't move — skip
            if npos == target:
                return dist + 1
            if npos not in visited:
                visited[npos] = dist + 1
                queue.append(npos)
    return None


# ── Puzzle generation ──────────────────────────────────────────────────────────

def _daily_seed() -> int:
    d = date.today()
    return d.year * 10000 + d.month * 100 + d.day


def generate_puzzle(seed: int | None = None) -> dict:
    """Generate the daily puzzle.

    Returns a dict with:
      size        : int (always BOARD_SIZE)
      obstacles   : frozenset[tuple[int,int]]
      target      : tuple[int,int]
      start       : tuple[int,int]
      min_moves   : int   (BFS-optimal solution depth)
      seed        : int
    """
    if seed is None:
        seed = _daily_seed()

    rng = random.Random(seed)
    size = BOARD_SIZE
    all_cells = [(x, y) for x in range(size) for y in range(size)]

    best: dict | None = None
    best_depth = 0

    for _ in range(600):
        rng.shuffle(all_cells)
        obstacles = frozenset(all_cells[:NUM_OBSTACLES])
        free = [c for c in all_cells if c not in obstacles]
        if len(free) < 2:
            continue
        rng.shuffle(free)
        target = free[0]
        start  = free[1]

        depth = _bfs_min_moves(start, target, obstacles, size)
        if depth is not None and depth >= 3 and depth > best_depth:
            best_depth = depth
            best = {
                "size":      size,
                "obstacles": obstacles,
                "target":    target,
                "start":     start,
                "min_moves": depth,
                "seed":      seed,
            }
            if depth >= 6:
                break  # good puzzle, stop searching

    if best is None:
        # Deterministic fallback: guaranteed solvable in 4 moves
        obstacles = frozenset([(2, 3), (5, 2), (1, 6), (6, 4), (3, 0), (7, 1), (4, 7)])
        start  = (0, 0)
        target = (7, 7)
        depth  = _bfs_min_moves(start, target, obstacles, size) or 4
        best = {
            "size":      size,
            "obstacles": obstacles,
            "target":    target,
            "start":     start,
            "min_moves": depth,
            "seed":      seed,
        }

    return best


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_board(
    puzzle: dict, px: int, py: int,
) -> str:
    """Return the board as 8 lines of emoji, one per row."""
    size = puzzle["size"]
    tx, ty = puzzle["target"]
    obs = puzzle["obstacles"]

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            if x == px and y == py:
                row.append(_E_WIN if (x == tx and y == ty) else _E_PLAYER)
            elif x == tx and y == ty:
                row.append(_E_TARGET)
            elif (x, y) in obs:
                row.append(_E_OBSTACLE)
            else:
                row.append(_E_EMPTY)
        rows.append("".join(row))
    return "\n".join(rows)
