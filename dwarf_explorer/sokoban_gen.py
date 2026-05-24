"""
sokoban_gen.py — Backward-BFS Sokoban puzzle generator for the FQ chamber.

Based on Taylor & Parberry (2011): work backwards from the solved state to
find starting log positions that maximise the number of pushes required.
Quality metric: push count first, box lines (direction changes) second.

Usage:
    python sokoban_gen.py                     # test all built-in rooms
    python sokoban_gen.py --room A            # test one room
    python sokoban_gen.py --apply A           # print config.py snippet for room A
    python sokoban_gen.py --generate 200      # T&P random generation: try 200 random
                                              # obstacle layouts, report best puzzles
    python sokoban_gen.py --generate 200 --seed 42 --min-pushes 35 --obs-min 16 --obs-max 28

T&P generation algorithm (Taylor & Parberry 2011)
-------------------------------------------------
  1. Randomly scatter N obstacles (N drawn from [--obs-min, --obs-max]).
  2. Pre-filter: reject if puzzle floor is disconnected.
  3. Run backward BFS from all goal states (logs in stream rows).
  4. Accept if max push count ≥ --min-pushes.
  5. Keep the top --top results and display them.

The grid
--------
  y=16-17  : chamber (fully open, player can reach any x)
  y=18-27  : puzzle area  (x=5-15, 11×10 = 110 cells)
  y=28     : barrier row  — all obstacle except cutaway at x=10
  y=29     : near stream  — logs enter here, become ford tiles
  y=30     : far stream   — second log slides here via ford

Win condition: one log at y=29 AND one log at y=30 (any x in 9-11 for a
usable bridge, but the BFS uses all x to maximise the state space searched).
"""

from __future__ import annotations
import argparse, random as _rng_mod, sys, time
from collections import deque

# ── Grid constants (mirror config.py) ─────────────────────────────────────────
PX0, PX1 = 5, 15        # puzzle x range (inclusive)
PY0, PY1 = 18, 27       # puzzle y range (inclusive) — 10 rows; y=28 is barrier
BY,  BX  = 28, 10       # barrier row y, cutaway column x (only opening at y=28)
SY,  SY2 = 29, 30       # stream rows
CH0, CH1 = 16, 17       # chamber rows (always open)
W        = 21           # zone width
BRIDGE_X = frozenset({9, 10, 11})   # valid x for a usable bridge


# ── Cell-set builders ──────────────────────────────────────────────────────────

def build_sets(obstacles: frozenset) -> tuple[frozenset, frozenset]:
    """
    Return (player_walkable, log_walkable) for a given obstacle set.

    Player:  chamber rows + puzzle floor (x=5-15, y=18-27, no obstacles)
             + barrier cutaway (10, 28)
             Edge columns x=4 and x=16 are walls for y=18-27 (not in pw).
    Log:     puzzle floor + barrier cutaway + both stream rows (no obstacles)
    """
    pw, lw = set(), set()
    for y in range(CH0, CH1 + 1):          # chamber — full width
        for x in range(1, W - 1):
            pw.add((x, y))
    for y in range(PY0, PY1 + 1):          # puzzle area y=18-27
        for x in range(PX0, PX1 + 1):
            if (x, y) not in obstacles:
                pw.add((x, y))
                lw.add((x, y))
    # Barrier cutaway — both player and log can pass through
    pw.add((BX, BY))
    lw.add((BX, BY))
    for y in (SY, SY2):                    # stream — logs only
        for x in range(PX0, PX1 + 1):
            lw.add((x, y))
    return frozenset(pw), frozenset(lw)


# ── Canonical player position (flood fill) ───────────────────────────────────

def canonical(start: tuple, pw: frozenset, logs: frozenset) -> tuple | None:
    """
    BFS flood fill from *start* within *pw*, treating *logs* as extra walls.
    Returns the lexicographically smallest reachable cell (= canonical ID for
    the player's connected component), or None if start is blocked.
    """
    if start not in pw or start in logs:
        return None
    seen = {start}
    q = [start]
    while q:
        x, y = q.pop()
        for nb in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if nb in pw and nb not in logs and nb not in seen:
                seen.add(nb)
                q.append(nb)
    return min(seen)


def _reachable_set(start: tuple, pw: frozenset, logs: frozenset) -> frozenset:
    """Flood fill from *start*, return full set of reachable cells."""
    if start not in pw or start in logs:
        return frozenset()
    seen = {start}
    q = [start]
    while q:
        x, y = q.pop()
        for nb in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if nb in pw and nb not in logs and nb not in seen:
                seen.add(nb)
                q.append(nb)
    return frozenset(seen)


# ── Backward BFS ──────────────────────────────────────────────────────────────

def backward_bfs(obstacles: frozenset) -> tuple[dict, dict]:
    """
    Explore all states reachable by reverse-pulling logs from every goal state.

    State  = (frozenset_of_2_log_positions, canonical_player_cell)
    Goal   = one log at y=SY, one at y=SY2  (any x in PX0..PX1)
    Return = (dist: state→pushes, parent: state→(prev_state, L_before, L_after, dir))
    """
    pw, lw = build_sets(obstacles)
    DIRS = ((0,1),(0,-1),(1,0),(-1,0))

    dist:   dict = {}
    parent: dict = {}
    q = deque()

    # ── Seed goal states ──────────────────────────────────────────────────────
    for xa in range(PX0, PX1+1):
        for xb in range(PX0, PX1+1):
            la, lb = (xa, SY), (xb, SY2)
            if la == lb:
                continue
            logs = frozenset({la, lb})
            # Find any reachable canonical player position
            for ty in range(PY1, PY0-1, -1):
                for tx in range(PX0, PX1+1):
                    c = canonical((tx, ty), pw, logs)
                    if c:
                        s = (logs, c)
                        if s not in dist:
                            dist[s] = 0
                            q.append(s)
                        break
                else:
                    continue
                break

    # ── BFS ───────────────────────────────────────────────────────────────────
    while q:
        state = q.popleft()
        logs, _ = state
        d = dist[state]

        for L in list(logs):
            lx, ly = L
            other = logs - {L}

            for dx, dy in DIRS:
                # Reverse: log came FROM L_prev = (lx-dx, ly-dy)
                #          player was at  P_prev = (lx-2dx, ly-2dy)
                Lp = (lx-dx, ly-dy)
                Pp = (lx-2*dx, ly-2*dy)

                if Lp not in lw:       continue   # invalid log cell
                if Lp in other:        continue   # blocked by other log
                if Pp not in pw:       continue   # player couldn't be there
                if Pp in other or Pp == L: continue

                new_logs = frozenset({Lp} | other)
                c = canonical(Pp, pw, new_logs)
                if c is None:
                    continue

                ns = (new_logs, c)
                if ns not in dist:
                    dist[ns] = d + 1
                    parent[ns] = (state, Lp, L, (dx, dy))
                    q.append(ns)

    return dist, parent


# ── Box-lines counter ─────────────────────────────────────────────────────────

def box_lines(start: tuple, parent: dict) -> int:
    """
    Walk the parent chain start→goal, count "box lines" per Taylor & Parberry:
    consecutive pushes of the SAME log in the SAME direction count as one line.
    Uses log position at the time of each push to track log identity.
    Higher = more complex routing.
    """
    path: list[tuple] = []
    cur = start
    while cur in parent:
        _, Lp, L, direction = parent[cur]
        path.append((Lp, L, direction))
        cur = parent[cur][0]

    if not path:
        return 0

    # path is goal→start; reverse for forward order
    fwd = list(reversed(path))

    # Track each log's trajectory: map last_known_pos → last_direction
    # When a log at position Lp is pushed to La in direction d:
    #   - find the trajectory whose last pos == Lp
    #   - if direction changed (or new log), increment lines
    traj: dict = {}  # last_pos -> last_dir
    lines = 0
    for Lp, La, d in fwd:
        if Lp in traj:
            if traj[Lp] != d:
                lines += 1          # direction changed for this log
            del traj[Lp]
            traj[La] = d
        else:
            lines += 1              # first push of this log (new line)
            traj[La] = d
    return lines


# ── Solver entry point ────────────────────────────────────────────────────────

def best_starts(obstacles: frozenset, top_n: int = 5,
                require_y18: bool = False
                ) -> list[tuple[int, int, tuple, tuple]]:
    """
    Run BFS for *obstacles*, return top_n hardest starting configurations:
    [(push_count, box_lines_approx, log_a_pos, log_b_pos), ...]
    sorted best-first.
    """
    t0 = time.perf_counter()
    dist, parent = backward_bfs(obstacles)
    dt = time.perf_counter() - t0
    total = len(dist)

    # Keep states where BOTH logs are in the puzzle area (not stream)
    def _ok(s):
        positions = s[0]
        if not all(PY0 <= p[1] <= PY1 for p in positions):
            return False
        if require_y18 and not all(p[1] == PY0 for p in positions):
            return False
        return True
    puzzle_only = {s: d for s, d in dist.items() if _ok(s)}

    if not puzzle_only:
        print(f"  [{dt:.1f}s, {total} states] — no valid puzzle states")
        return []

    max_d = max(puzzle_only.values())
    farthest = [s for s, d in puzzle_only.items() if d == max_d]

    results = []
    for s in farthest:
        bl = box_lines(s, parent)
        la, lb = sorted(s[0])
        results.append((max_d, bl, la, lb))

    results.sort(key=lambda r: (-r[0], -r[1]))
    print(f"  [{dt:.1f}s, {total} states] max_pushes={max_d} "
          f"candidates={len(farthest)} best_box_lines~{results[0][1]}")
    return results[:top_n]


# ── T&P Random Layout Generator ───────────────────────────────────────────────

# Cells that must never be obstacles (barrier approach path)
_FORBIDDEN = frozenset({(BX, PY1), (BX, PY1 - 1)})   # (10,27), (10,26)

# All valid obstacle candidate positions
_CANDIDATES = tuple(
    (x, y)
    for y in range(PY0, PY1 + 1)
    for x in range(PX0, PX1 + 1)
    if (x, y) not in _FORBIDDEN
)


def _floor_connected(obs: frozenset) -> bool:
    """
    Check that every non-obstacle cell in the puzzle area is reachable from
    every other non-obstacle cell (single connected component for logs).
    Isolated pockets guarantee dead positions.
    """
    floor = frozenset(
        (x, y)
        for x in range(PX0, PX1 + 1)
        for y in range(PY0, PY1 + 1)
        if (x, y) not in obs
    )
    if not floor:
        return False
    start = next(iter(floor))
    seen = {start}
    q = [start]
    while q:
        cx, cy = q.pop()
        for nb in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if nb in floor and nb not in seen:
                seen.add(nb)
                q.append(nb)
    return len(seen) == len(floor)


def _simple_deadlock_count(obs: frozenset) -> int:
    """
    Count "corner deadlock" cells — cells where a log pushed in cannot
    be pushed back out, because walls block two perpendicular sides.

    Wall definition (from a log's perspective):
      • x < PX0 or x > PX1          : left/right boundary
      • y < PY0                      : north boundary (chamber rows not in lw)
      • y > PY1 and not (y==BY,x==BX): barrier obstacle or out-of-range
      • (x,y) in obs                 : obstacle tile

    Cells at the left/right boundary (x=PX0 or x=PX1) always have one
    perpendicular wall; they contribute to the count only when the second
    wall is also present (i.e. top-row or obstacle above/below).
    A layout is rejected if count > MAX_DEADLOCKS (see generate_random_puzzles).
    """
    def is_wall(x: int, y: int) -> bool:
        if x < PX0 or x > PX1:
            return True
        if y < PY0:
            return True
        if y > PY1:
            # barrier row: obstacle everywhere except cutaway
            return not (y == BY and x == BX)
        return (x, y) in obs

    count = 0
    for x in range(PX0, PX1 + 1):
        for y in range(PY0, PY1 + 1):
            if (x, y) in obs:
                continue
            if (is_wall(x - 1, y) and is_wall(x, y - 1)):  # NW
                count += 1
            elif (is_wall(x + 1, y) and is_wall(x, y - 1)):  # NE
                count += 1
            elif (is_wall(x - 1, y) and is_wall(x, y + 1)):  # SW
                count += 1
            elif (is_wall(x + 1, y) and is_wall(x, y + 1)):  # SE
                count += 1
    return count


def generate_random_puzzles(
    n_attempts: int = 200,
    obs_min: int = 15,
    obs_max: int = 26,
    min_pushes: int = 30,
    seed: int | None = None,
    top_n: int = 5,
    max_deadlocks: int = 8,  # boundary corners alone give ~4; allow a few more
    verbose: bool = True,
) -> list[tuple[int, int, tuple, tuple, frozenset]]:
    """
    Taylor & Parberry (2011) random puzzle generation.

    For each of n_attempts iterations:
      1. Draw a random number of obstacles in [obs_min, obs_max].
      2. Randomly scatter them across the valid positions (excluding (10,26)
         and (10,27) which are needed for the barrier approach).
      3. Pre-filter: reject disconnected floor or too many corner deadlocks.
      4. Run full backward BFS.
      5. Accept if max push count ≥ min_pushes.

    Returns a list of (push_count, box_lines, log_a, log_b, obstacles) for the
    top_n hardest puzzles found, sorted best-first.
    """
    rng = _rng_mod.Random(seed)
    results: list = []
    passed_prefilter = 0
    t_start = time.perf_counter()

    for attempt in range(1, n_attempts + 1):
        n_obs = rng.randint(obs_min, obs_max)
        obs = frozenset(rng.sample(_CANDIDATES, n_obs))

        # ── Pre-filter: connectivity only ─────────────────────────────────
        # (The deadlock count is too conservative for random layouts; the BFS
        # already handles dead-position detection correctly.)
        if not _floor_connected(obs):
            continue
        passed_prefilter += 1

        # ── Full backward BFS ─────────────────────────────────────────────
        starts = best_starts(obs, top_n=1)
        if not starts:
            continue

        d, bl, la, lb = starts[0]
        if d < min_pushes:
            continue

        results.append((d, bl, la, lb, obs))
        if verbose:
            elapsed = time.perf_counter() - t_start
            print(f"  [{attempt:4d}/{n_attempts}] +HIT  "
                  f"pushes={d:3d}  box_lines={bl:3d}  obs={n_obs:2d}  "
                  f"la={la}  lb={lb}  ({elapsed:.0f}s elapsed)")

    results.sort(key=lambda r: (-r[0], -r[1]))

    elapsed = time.perf_counter() - t_start
    print(f"\n{'-'*60}")
    print(f"Done: {n_attempts} attempts, {passed_prefilter} passed pre-filter, "
          f"{len(results)} met min_pushes={min_pushes}  ({elapsed:.1f}s)")
    return results[:top_n]


# ── Room layouts ──────────────────────────────────────────────────────────────
# Each room is a frozenset of (x, y) obstacle cells in the puzzle area.
# Design goals:
#   • No spanning walls (every row has open cells on both left and right)
#   • Scattered pillars + short segments that create deflection points
#   • Narrow corridors near x=9-11 so reaching the stream is non-trivial
#   • No isolated dead-end cells (3-sided walls)

def _obs(*pairs):
    return frozenset(pairs)


# ── Room A: "Pinball" ─────────────────────────────────────────────────────────
# Scattered single and double pillars.  No spanning walls.
# Logs deflect off pillars and must navigate indirect paths to x=9-11.
ROOM_PINBALL = _obs(
    # Upper blocker row (y=20): two segments, open at x=5,10,15
    (7,20),(8,20),(9,20),    # blocks right-of-left corridor
    (11,20),(12,20),(13,20), # blocks left-of-right corridor
    # Mid-upper pillars (y=22)
    (6,22),(7,22),           # left pair
    (13,22),(14,22),         # right pair
    # Center column pillar (y=23-24)
    (10,23),
    (10,24),
    # Mid-lower pillars (y=25)
    (6,25),(7,25),           # left pair (mirror of y=22)
    (13,25),(14,25),         # right pair
    # Lower blocker row (y=27): mirrors y=20, open at x=5,10,15
    (7,27),(8,27),(9,27),
    (11,27),(12,27),(13,27),
)

# ── Room B: "Corridors" ───────────────────────────────────────────────────────
# Three vertical "lanes" (left/centre/right) connected by horizontal
# passages at specific rows.  Forces logs to switch lanes.
# y=28 obstacles omitted — barrier row handles the bottom wall uniformly.
ROOM_CORRIDORS = _obs(
    # Left–centre divider (x=8): solid except gaps at y=20 and y=26
    (8,19),(8,21),(8,22),(8,23),(8,24),(8,25),(8,27),
    # Centre–right divider (x=12): solid except gaps at y=23 and y=27
    (12,19),(12,20),(12,21),(12,22),(12,24),(12,25),(12,26),
    # Horizontal cross-bars to break long open stretches
    (6,22),(7,22),           # left lane y=22
    (9,25),(10,25),(11,25),  # centre lane y=25
    (13,22),(14,22),         # right lane y=22
)

# ── Room C: "Chambers" ────────────────────────────────────────────────────────
# Two side chambers (left x=5-7, right x=13-15) connected to a central
# corridor (x=9-11) via single-cell openings.  Getting logs out of the
# side chambers requires precise sequencing.
# y=28 obstacles omitted — barrier row handles the bottom wall uniformly.
ROOM_CHAMBERS = _obs(
    # Left chamber wall (x=8): open at y=21 and y=25
    (8,18),(8,19),(8,20),(8,22),(8,23),(8,24),(8,26),(8,27),
    # Right chamber wall (x=12): open at y=22 and y=26
    (12,18),(12,19),(12,20),(12,21),(12,23),(12,24),(12,25),(12,27),
    # Centre blocker: single pillar at (10,23) breaks direct path
    (10,23),
)

# ── Room D: "Offset Chambers" ────────────────────────────────────────────────
# Two chamber walls like Room C but with different opening heights so the
# exit timing doesn't mirror Room C.  Extra interior obstacles create a dense
# centre region that complicates routing to the barrier cutaway.
# Rule: (10,26) and (10,27) intentionally left clear for barrier approach.
ROOM_OFFSET = _obs(
    # Left chamber wall (x=8): open at y=20 and y=24
    (8,18),(8,19),(8,21),(8,22),(8,23),(8,25),(8,26),(8,27),
    # Right chamber wall (x=12): open at y=22 and y=26
    (12,18),(12,19),(12,20),(12,21),(12,23),(12,24),(12,25),(12,27),
    # Centre-top deflector pair (y=19)
    (9,19),(11,19),
    # Mid pillar (y=23)
    (10,23),
    # Near-barrier deflectors (y=25) — keep (10,25) clear, flank it
    (9,25),(11,25),
)

# ── Room G: "ZigzagBar" ──────────────────────────────────────────────────────
# Two full-width pinch bars at y=20 and y=24 but with OFFSET openings:
#   y=20 opens ONLY at x=8  (left-of-centre)
#   y=24 opens ONLY at x=12 (right-of-centre)
# Both logs must pass through x=8, then zigzag right to x=12, then converge
# at x=10 for the barrier — three separate convergence points, no straight
# vertical path exists anywhere.
ROOM_ZIGZAGBAR = _obs(
    # Upper bar (y=20): open ONLY at x=8
    (5,20),(6,20),(7,20),(9,20),(10,20),(11,20),(12,20),(13,20),(14,20),(15,20),
    # Lower bar (y=24): open ONLY at x=12
    (5,24),(6,24),(7,24),(8,24),(9,24),(10,24),(11,24),(13,24),(14,24),(15,24),
)

# ── Room H: "Split Lock" ──────────────────────────────────────────────────────
# Two nearly sealed vertical chambers separated by full-height dividers.
# Left chamber exits only at y=19; right chamber exits only at y=25.
# Getting both logs from their chambers to x=10 requires complex cross-routing.
ROOM_SPLITLOCK = _obs(
    # Left divider (x=7): open only at y=19
    (7,18),(7,20),(7,21),(7,22),(7,23),(7,24),(7,25),(7,26),(7,27),
    # Right divider (x=13): open only at y=25
    (13,18),(13,19),(13,20),(13,21),(13,22),(13,23),(13,24),(13,26),(13,27),
    # Interior centre obstacles — force routing through narrow corridors
    (9,21),(10,21),(11,21),
    (9,24),(10,24),(11,24),
    # Outer-lane bottoms — prevent trivial slides to edge
    (5,26),(5,27),(15,26),(15,27),
)

# ── Room I: "Zigzag Dense" ────────────────────────────────────────────────────
# Three staggered partial walls (NOT spanning — each has 2+ open cells) plus
# scattered pillars.  Logs must weave left–right–left while converging to x=10.
ROOM_ZIGZAG = _obs(
    # Top partial wall (y=19): open at x=13-15 (right gate)
    (5,19),(6,19),(7,19),(8,19),(9,19),(10,19),(11,19),(12,19),
    # Mid partial wall (y=23): open at x=5-7 (left gate) + narrow centre
    (8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),(15,23),
    # Lower partial wall (y=26): open at x=9-11 only (approaches barrier)
    (5,26),(6,26),(7,26),(8,26),(12,26),(13,26),(14,26),(15,26),
    # Side deflectors between walls
    (14,21),(14,22),   # right side, upper
    (6,24),(6,25),     # left side, lower
)

# ── Room E: "Classic Plus" ────────────────────────────────────────────────────
# Classic 3-wall structure (y=20/23/26 gates x=5/15/10) + strategic pillars in
# the free rows.  The spanning walls force ~60 pushes of lateral travel; the
# pillars inside those corridors force additional direction changes, boosting
# box lines without introducing any deadlocks.
ROOM_CLASSIC_PLUS = _obs(
    # ── Wall 1 (y=20): gate x=5  (x=6-15 blocked) ───────────────────────────
    (6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(14,20),(15,20),
    # ── Wall 2 (y=23): gate x=15 (x=5-14 blocked) ───────────────────────────
    (5,23),(6,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),
    # ── Wall 3 (y=26): gate x=10 (x=5-9, 11-15 blocked) ─────────────────────
    (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
    # ── Pillars in free rows ─────────────────────────────────────────────────
    (9,21),              # deflects eastward traffic in y=21
    (6,22),(14,22),      # side pillars in y=22 narrow the lane
    (8,24),(12,24),      # symmetric pillars in y=24
    (10,27),             # centre pillar forces detour in final stretch y=27
)

# ── Room F: "Slot" ────────────────────────────────────────────────────────────
# Two vertical divider walls split the puzzle into three narrow lanes
# (left x=5-7, centre x=9-11, right x=13-15).  Gaps in the dividers are
# staggered so logs MUST switch lanes to progress south.
# The barrier row at y=28 (only x=10 open) replaces the old bottom funnel.
# y=28 obstacles omitted — barrier row handles the bottom wall uniformly.
ROOM_SLOT = _obs(
    # Left divider (x=8): open at y=21 and y=25
    (8,18),(8,19),(8,20),(8,22),(8,23),(8,24),(8,26),(8,27),
    # Right divider (x=12): open at y=23 and y=27
    (12,18),(12,19),(12,20),(12,21),(12,22),(12,24),(12,25),(12,26),
    # Centre deflector
    (10,20),(10,25),
)

# ── T&P generated variants (keys J-N) ────────────────────────────────────────
# BFS-verified with seed=1337.  Obstacle sets mirror FQ_PUZZLE_VARIANTS in
# config.py so --trace / --apply produce matching output.

ROOM_SCATTER = frozenset({
    (5,23),(5,25),
    (6,20),(6,21),
    (7,23),
    (8,22),(8,27),
    (9,22),
    (10,20),
    (11,21),
    (12,19),(12,26),
    (13,20),
    (14,25),(14,26),
})

ROOM_TANGLE = frozenset({
    (5,20),(5,27),
    (6,24),
    (7,20),(7,21),(7,22),(7,24),(7,26),
    (8,21),(8,22),
    (9,18),(9,22),(9,23),(9,25),
    (10,22),(10,25),
    (12,19),(12,25),(12,26),(12,27),
    (13,20),
    (15,19),(15,21),(15,23),
})

ROOM_DRIFT = frozenset({
    (5,22),(5,23),(5,24),
    (6,19),
    (7,24),
    (8,24),(8,25),(8,26),
    (9,23),
    (10,19),(10,22),
    (11,22),(11,26),
    (12,21),
    (13,19),(13,26),
    (14,21),(14,24),(14,25),
    (15,25),(15,27),
})

ROOM_LATTICE = frozenset({
    (5,19),
    (6,19),(6,20),(6,24),(6,26),
    (7,22),(7,25),
    (8,20),(8,21),(8,26),
    (9,21),
    (10,20),(10,24),
    (11,26),
    (12,18),(12,21),(12,22),(12,24),(12,25),(12,27),
    (13,21),
    (14,20),(14,26),
    (15,22),(15,23),
})

ROOM_BURIED = frozenset({
    (5,20),
    (6,25),
    (7,18),(7,20),(7,27),
    (8,23),
    (9,21),(9,23),
    (10,18),(10,24),(10,25),
    (11,20),(11,25),
    (12,19),(12,23),(12,27),
    (13,19),(13,20),(13,23),(13,25),
    (14,19),(14,27),
    (15,18),
})

ROOMS = {
    "A": ("Pinball",        ROOM_PINBALL),
    "B": ("Corridors",      ROOM_CORRIDORS),
    "C": ("Chambers",       ROOM_CHAMBERS),
    "D": ("Offset",         ROOM_OFFSET),
    "E": ("Classic Plus",   ROOM_CLASSIC_PLUS),
    "F": ("Slot",           ROOM_SLOT),
    "G": ("ZigzagBar",      ROOM_ZIGZAGBAR),
    "H": ("Split Lock",     ROOM_SPLITLOCK),
    "I": ("Zigzag Dense",   ROOM_ZIGZAG),
    # T&P randomly generated variants (live in FQ_PUZZLE_VARIANTS)
    "J": ("Scatter",        ROOM_SCATTER),
    "K": ("Tangle",         ROOM_TANGLE),
    "L": ("Drift",          ROOM_DRIFT),
    "M": ("Lattice",        ROOM_LATTICE),
    "N": ("Buried",         ROOM_BURIED),
}


# ── Visualiser ────────────────────────────────────────────────────────────────

def visualise(obstacles: frozenset,
              log_a: tuple | None = None,
              log_b: tuple | None = None) -> None:
    CHARS = {"obs": "#", "log_a": "A", "log_b": "B", "floor": ".", "barrier": "X", "cut": "O"}
    print()
    for y in range(PY0, BY + 1):       # puzzle rows + barrier row
        row = f"y={y}: "
        for x in range(PX0, PX1 + 1):
            if (x, y) == log_a:
                row += CHARS["log_a"]
            elif (x, y) == log_b:
                row += CHARS["log_b"]
            elif y == BY:              # barrier row
                row += CHARS["cut"] if x == BX else CHARS["barrier"]
            elif (x, y) in obstacles:
                row += CHARS["obs"]
            else:
                row += CHARS["floor"]
        print(row)
    print()


# ── Solution tracer ───────────────────────────────────────────────────────────

def trace_solution(obstacles: frozenset, log_a: tuple, log_b: tuple) -> None:
    """
    Reconstruct the forward solution path from the backward-BFS parent chain
    and print an ASCII overlay showing where each log travels.

    Legend:
      A / B  = log starting positions
      a / b  = cells log A / log B pass through on the way to the stream
      #      = obstacle
      .      = empty floor
      O      = barrier cutaway  (BX, BY)
      X      = barrier wall
    """
    print(f"  Running backward BFS for trace...")
    dist, parent = backward_bfs(obstacles)

    logs_start = frozenset({log_a, log_b})
    matching = [(s, d) for s, d in dist.items() if s[0] == logs_start]
    if not matching:
        print(f"  [trace] No solution found — logs {log_a} / {log_b} are unreachable from any goal state.")
        return

    best_state, push_count = max(matching, key=lambda sd: sd[1])

    # Walk parent chain from best_state toward the goal.
    # parent[ns] = (prev_state, Lp, L_after, direction)
    #   ns        = state where the pushed log is at Lp  (BEFORE the push in forward play)
    #   prev_state = state where the pushed log is at L_after (AFTER the push in forward play)
    #
    # Walking best_state → prev_state → ... → goal collects steps in FORWARD
    # chronological order (first push first), because best_state IS the start.
    forward_steps: list[tuple] = []
    cur = best_state
    while cur in parent:
        prev_state, Lp, L_after, direction = parent[cur]
        forward_steps.append((Lp, L_after, direction))
        cur = prev_state

    # Build per-log trails by tracking each log's current position
    a_pos, b_pos = log_a, log_b
    a_trail: set = {log_a}
    b_trail: set = {log_b}
    a_pushes = b_pushes = 0

    for Lp, L_after, _ in forward_steps:
        if Lp == a_pos:
            a_pos = L_after
            a_trail.add(L_after)
            a_pushes += 1
        elif Lp == b_pos:
            b_pos = L_after
            b_trail.add(L_after)
            b_pushes += 1

    # ── ASCII map overlay ─────────────────────────────────────────────────────
    print()
    print(f"  Solution: {push_count} pushes total  (log A: {a_pushes}  log B: {b_pushes})")
    print(f"  A/B=start  a/b=trail  #=wall  .=floor  O=exit  X=barrier")
    print()
    for y in range(PY0, BY + 1):
        row = f"  y={y:2d}: "
        for x in range(PX0, PX1 + 1):
            pos = (x, y)
            if pos == log_a:
                row += "A"
            elif pos == log_b:
                row += "B"
            elif y == BY:
                row += "O" if x == BX else "X"
            elif pos in obstacles:
                row += "#"
            elif pos in a_trail:
                row += "a"
            elif pos in b_trail:
                row += "b"
            else:
                row += "."
        print(row)
    print()

    # ── Forward simulation: validate each push is physically reachable ────────
    # For each push the player must stand at Pp = Lp - dir.  We simulate the
    # game state (log positions + player canonical) forward and check that Pp
    # is inside the flood-fill component of the current canonical position.
    pw, _ = build_sets(obstacles)
    sim_logs = frozenset({log_a, log_b})
    sim_can  = best_state[1]          # initial player canonical
    sim_a, sim_b = log_a, log_b
    step_valid: list[bool] = []

    for Lp, L_after, dir_ in forward_steps:
        dx, dy = dir_
        Pp = (Lp[0] - dx, Lp[1] - dy)          # where player must stand
        reachable = _reachable_set(sim_can, pw, sim_logs)
        ok = Pp in reachable
        step_valid.append(ok)
        # Advance simulation: player steps into Lp after the push
        if Lp == sim_a:
            sim_a = L_after
        elif Lp == sim_b:
            sim_b = L_after
        sim_logs = frozenset({sim_a, sim_b})
        new_can = canonical(Lp, pw, sim_logs)
        sim_can = new_can if new_can is not None else sim_can

    n_invalid = step_valid.count(False)
    if n_invalid == 0:
        print(f"  Validation: ALL {len(forward_steps)} pushes are physically reachable.")
    else:
        print(f"  Validation: {n_invalid} IMPOSSIBLE push(es) detected!")

    # ── Step-by-step list ─────────────────────────────────────────────────────
    DIR_NAMES = {(0, 1): "S", (0, -1): "N", (1, 0): "E", (-1, 0): "W"}
    a_pos, b_pos = log_a, log_b
    print(f"  Steps ({len(forward_steps)} pushes):")
    for i, (Lp, L_after, dir_) in enumerate(forward_steps, 1):
        which = "?"
        if Lp == a_pos:
            which = "A"
            a_pos = L_after
        elif Lp == b_pos:
            which = "B"
            b_pos = L_after
        dx, dy = dir_
        Pp = (Lp[0] - dx, Lp[1] - dy)
        d_name = DIR_NAMES.get(dir_, str(dir_))
        flag = "" if step_valid[i - 1] else f"  !! IMPOSSIBLE (player needs {Pp})"
        print(f"    {i:3d}. Log {which}  {Lp} -> {L_after}  [{d_name}]{flag}")
    print()


# ── Config snippet generator ──────────────────────────────────────────────────

def config_snippet(name: str, obstacles: frozenset,
                   log_a: tuple, log_b: tuple,
                   push_count: int, box_lines_n: int) -> str:
    obs_sorted = sorted(obstacles)
    lines = [
        f"    # -- {name}  ({len(obstacles)} obstacles, ~{push_count} pushes, ~{box_lines_n} box lines)",
        f"    {{",
        f'        "name": "{name}",',
        f'        "log_a": {log_a!r},',
        f'        "log_b": {log_b!r},',
        f'        "obstacles": frozenset({{',
    ]
    for x, y in obs_sorted:
        lines.append(f"            ({x}, {y}),")
    lines.append("        }),")
    lines.append("    },")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default="all",
                    help="Room key (A-I) or 'all'")
    ap.add_argument("--apply", default=None,
                    help="Print config.py snippet for this room key")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--y18", action="store_true",
                    help="Only allow log starts on y=18")
    # T&P random generation
    ap.add_argument("--generate", type=int, default=0, metavar="N",
                    help="T&P mode: try N random obstacle layouts and report best puzzles")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for --generate (reproducible runs)")
    ap.add_argument("--min-pushes", type=int, default=30,
                    help="Minimum push count to accept a generated layout (default 30)")
    ap.add_argument("--obs-min", type=int, default=15,
                    help="Min obstacles per random layout (default 15)")
    ap.add_argument("--obs-max", type=int, default=26,
                    help="Max obstacles per random layout (default 26)")
    ap.add_argument("--trace", action="store_true",
                    help="After solving a room, print the full solution path overlay")
    args = ap.parse_args()

    # ── T&P random generation mode ────────────────────────────────────────
    if args.generate > 0:
        print(f"T&P random generation: {args.generate} attempts, "
              f"obs=[{args.obs_min},{args.obs_max}], "
              f"min_pushes={args.min_pushes}, seed={args.seed}")
        print("-" * 60)
        hits = generate_random_puzzles(
            n_attempts=args.generate,
            obs_min=args.obs_min,
            obs_max=args.obs_max,
            min_pushes=args.min_pushes,
            seed=args.seed,
            top_n=args.top,
        )
        if not hits:
            print("No layouts met the criteria.")
            return
        print(f"\nTop {len(hits)} results:\n")
        for rank, (d, bl, la, lb, obs) in enumerate(hits, 1):
            print(f"{'='*60}")
            print(f"Rank #{rank}  pushes={d}  box_lines={bl}  obs={len(obs)}")
            print(f"  log_a={la}  log_b={lb}")
            visualise(obs, la, lb)
            print(config_snippet(f"Random_{rank}", obs, la, lb, d, bl))
        return

    if args.apply:
        key = args.apply.upper()
        if key not in ROOMS:
            sys.exit(f"Unknown room: {key}")
        room_name, obs = ROOMS[key]
        print(f"Solving room {key} ({room_name})...")
        results = best_starts(obs, top_n=1)
        if results:
            d, bl, la, lb = results[0]
            print(config_snippet(room_name, obs, la, lb, d, bl))
            visualise(obs, la, lb)
            if args.trace:
                trace_solution(obs, la, lb)
        return

    rooms_to_test = (
        [(args.room.upper(), *ROOMS[args.room.upper()])]
        if args.room != "all"
        else [(k, n, o) for k, (n, o) in ROOMS.items()]
    )

    for key, room_name, obs in rooms_to_test:
        print(f"\n{'='*60}")
        print(f"Room {key}: {room_name}  ({len(obs)} obstacles)")
        print(f"{'='*60}")
        results = best_starts(obs, top_n=args.top, require_y18=args.y18)
        if not results:
            continue
        for i, (d, bl, la, lb) in enumerate(results):
            print(f"  #{i+1}  pushes={d}  box_lines={bl}  log_a={la}  log_b={lb}")
        best = results[0]
        visualise(obs, best[2], best[3])
        if args.trace:
            trace_solution(obs, best[2], best[3])


if __name__ == "__main__":
    main()
