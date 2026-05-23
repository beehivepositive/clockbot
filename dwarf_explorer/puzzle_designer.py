#!/usr/bin/env python3
"""
Sokoban solver / designer for the FQ stream-bridge puzzle.

Mechanic:
  - Two logs must both enter the stream (y=29 near, y=30 far)
  - Both must be at the SAME x column
  - First log pushed into fq_stream (y=29) at col X → creates ford at (X,29)
  - Second log pushed to (X,28), pushed south → hits ford, slides to (X,30) → done
  - Either log can go first (puzzle is symmetric in ordering)

Run:   python puzzle_designer.py
"""

from collections import deque

# ── Puzzle geometry ─────────────────────────────────────────────────────────────
PX0, PX1   = 5, 15     # puzzle floor x range
PY0, PY1   = 18, 28    # puzzle floor y range
STREAM_Y   = 29        # near stream row
STREAM_Y2  = 30        # far stream row (slide destination)

RESET_X, RESET_Y = 3, 22  # reset stone (not an obstacle, but reference)

# Chamber walkable area for the player (outside puzzle floor)
CHAMBER_X0, CHAMBER_X1 = 1, 19
CHAMBER_Y0, CHAMBER_Y1 = 16, STREAM_Y


# ── Core solver ─────────────────────────────────────────────────────────────────

def player_can_stand(pos, logs, obs):
    x, y = pos
    if pos in logs or pos in obs:
        return False
    # Puzzle floor
    if PX0 <= x <= PX1 and PY0 <= y <= PY1:
        return True
    # Wider chamber floor (lets player get behind logs at puzzle edges)
    if CHAMBER_X0 <= x <= CHAMBER_X1 and CHAMBER_Y0 <= y <= CHAMBER_Y1:
        return True
    return False


def get_reachable(start, logs, obs):
    r = {start}
    q = deque([start])
    while q:
        p = q.popleft()
        for dx, dy in ((0,1),(0,-1),(1,0),(-1,0)):
            np = (p[0]+dx, p[1]+dy)
            if np not in r and player_can_stand(np, logs, obs):
                r.add(np)
                q.append(np)
    return r


def canonical(start, logs, obs):
    """Canonical player position = lex-min of reachable region."""
    return min(get_reachable(start, logs, obs))


def log_dest_valid(dest, logs, obs):
    x, y = dest
    if dest in obs or dest in logs:
        return False
    if y == STREAM_Y and CHAMBER_X0 <= x <= CHAMBER_X1:
        return True   # pushing into near stream always valid
    return PX0 <= x <= PX1 and PY0 <= y <= PY1


def try_push(logs, log_pos, dx, dy, obs):
    """
    Apply a push of log_pos in direction (dx,dy).
    Returns new frozenset of log positions, or None if blocked.
    Handles slide mechanic for fq_stream_ford.
    """
    dest = (log_pos[0]+dx, log_pos[1]+dy)

    # ── Slide mechanic ──────────────────────────────────────────────────────────
    # dest is fq_stream_ford (a log already in STREAM_Y at same column)?
    if dest[1] == STREAM_Y and dest in logs:
        beyond = (dest[0]+dx, dest[1]+dy)
        if beyond[1] == STREAM_Y2 and beyond not in logs and beyond not in obs:
            return frozenset((logs - {log_pos}) | {beyond})
        return None   # something blocking beyond the ford

    if not log_dest_valid(dest, logs, obs):
        return None
    return frozenset((logs - {log_pos}) | {dest})


def is_solved(logs):
    near_x = {p[0] for p in logs if p[1] == STREAM_Y}
    far_x  = {p[0] for p in logs if p[1] == STREAM_Y2}
    return bool(near_x & far_x)


def solve(obstacles, log_starts, player_start=(10, 17), max_pushes=500):
    """
    BFS solver. Returns (push_count, path_of_log_positions) or (None, None).
    path_of_log_positions: list of frozensets showing log positions at each push.
    """
    obs = frozenset(obstacles)

    if not player_can_stand(player_start, frozenset(log_starts), obs):
        player_start = (10, 16)

    logs0 = frozenset(log_starts)
    cp0   = canonical(player_start, logs0, obs)
    start = (logs0, cp0)

    if is_solved(logs0):
        return 0, [logs0]

    visited = {start: None}   # state -> parent state
    queue   = deque([(start, 0)])

    while queue:
        (logs, cp), pushes = queue.popleft()

        if pushes >= max_pushes:
            continue

        reachable = get_reachable(cp, logs, obs)

        for log_pos in logs:
            if log_pos[1] >= STREAM_Y:
                continue
            for dx, dy in ((0,1),(0,-1),(1,0),(-1,0)):
                push_from = (log_pos[0]-dx, log_pos[1]-dy)
                if push_from not in reachable:
                    continue

                new_logs = try_push(logs, log_pos, dx, dy, obs)
                if new_logs is None:
                    continue

                new_cp    = canonical(log_pos, new_logs, obs)
                new_state = (new_logs, new_cp)

                if new_state in visited:
                    continue

                visited[new_state] = (logs, cp)
                new_pushes = pushes + 1

                if is_solved(new_logs):
                    # Reconstruct path
                    path = [new_logs]
                    s = (logs, cp)
                    while visited[s] is not None:
                        path.append(s[0])
                        s = visited[s]
                    path.append(s[0])
                    path.reverse()
                    return new_pushes, path

                queue.append((new_state, new_pushes))

    return None, None


def render_puzzle(obstacles, log_starts, label=""):
    """ASCII render of the puzzle area."""
    obs_set  = set(obstacles)
    log_set  = set(log_starts)
    lines = [f"\n  === {label} ===" if label else ""]
    lines.append("     " + "".join(f"{x:2}" for x in range(PX0, PX1+1)))
    for y in range(PY0, PY1+1):
        row = f"y{y:2}: "
        for x in range(PX0, PX1+1):
            p = (x, y)
            if p in log_set:
                row += " L"
            elif p in obs_set:
                row += " #"
            else:
                row += " ."
        lines.append(row)
    lines.append("      stream:  " + "  ".join("~" for _ in range(PX0, PX1+1)))
    print("\n".join(lines))


# ── Candidate layouts ────────────────────────────────────────────────────────────
# Describe using (FQ_PUZZLE_X0 + col_offset, FQ_PUZZLE_Y0 + row_offset)
# PX0=5, PY0=18

def layout_v1():
    """
    Candidate 1: Zigzag corridors funneling to center column.
    Symmetric start (far corners), logs must thread through pinched passages.
    """
    # Logs in upper outer corners
    logs = [(6, 18), (14, 18)]

    # Obstacles designed to force zigzag routes and prevent trivial straight pushes
    obs = [
        # Row 19 — block direct south paths from start positions
        (9, 19), (11, 19),
        # Row 20 — funnel inward
        (6, 20), (14, 20),
        # Row 21 — center pinch
        (8, 21), (12, 21),
        # Row 22 — side walls narrow the corridor
        (5, 22), (15, 22),
        # Row 23 — stagger obstacles
        (7, 23), (13, 23),
        (10, 23),
        # Row 24 — open row (allow maneuvering)
        # Row 25 — re-pinch toward center
        (6, 25), (14, 25),
        (9, 25), (11, 25),
        # Row 26 — final obstacles before last row
        (8, 26), (12, 26),
        # Row 27 — near-bottom obstacles forcing column convergence
        (7, 27), (13, 27),
    ]
    return logs, obs

def layout_v2():
    """
    Candidate 2: S-curve design. Logs must travel opposite directions to converge.
    One log starts left-top, other right-top; both must cross to center.
    More obstacles, tighter corridors.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Upper funnel — prevent straight south
        (8, 19), (12, 19),
        (5, 20), (15, 20), (10, 20),
        # Mid cross — force horizontal travel
        (7, 21), (9, 21), (11, 21), (13, 21),
        # Open row 22 but side-blocked
        (5, 22), (15, 22),
        # Lower pinch — center column blocked, must navigate around
        (8, 23), (12, 23),
        (10, 24),
        # S-turn obstacles
        (6, 25), (14, 25),
        (9, 25), (11, 25),
        # Bottleneck approach
        (7, 26), (13, 26),
        (5, 27), (15, 27), (9, 27), (11, 27),
    ]
    return logs, obs

def layout_v3():
    """
    Candidate 3: Maze-style with multiple dead-end temptations.
    Logs start near center, must navigate outward then back in.
    """
    logs = [(8, 19), (12, 19)]

    obs = [
        # Force logs to not go straight south
        (8, 20), (12, 20),
        # Side corridors
        (6, 19), (14, 19),
        (5, 21), (15, 21),
        # Mid obstacles — create decision points
        (7, 22), (13, 22), (10, 22),
        (9, 23), (11, 23),
        (6, 24), (14, 24),
        # Traps — tempting but lead to corners
        (5, 25), (15, 25),
        (8, 25), (12, 25),
        # Lower convergence
        (7, 27), (13, 27),
        (9, 26), (11, 26),
        (10, 27),
    ]
    return logs, obs


def layout_v4():
    """
    Candidate 4: Interlocking corridors — designed for longer solution.
    Both logs must navigate through shared passages, forcing careful sequencing.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Top barrier — both logs must go through specific gaps
        (7, 19), (8, 19), (10, 19), (12, 19), (13, 19),
        # Row 20: open except corners
        (5, 20), (15, 20),
        # Row 21: staggered wall
        (6, 21), (9, 21), (11, 21), (14, 21),
        # Row 22: center blocked
        (7, 22), (10, 22), (13, 22),
        # Row 23: open but side walls
        (5, 23), (15, 23),
        # Row 24: checker pattern
        (8, 24), (10, 24), (12, 24),
        # Row 25: force toward center
        (6, 25), (9, 25), (11, 25), (14, 25),
        # Row 26: near-bottom obstacles
        (7, 26), (10, 26), (13, 26),
        # Row 27: funnel to column 10
        (8, 27), (12, 27),
    ]
    return logs, obs


def layout_v5():
    """
    Candidate 5: Two separate maze corridors merge at bottom.
    Logs go through dedicated left/right corridors then meet at center.
    Lots of dead-end temptations.
    """
    logs = [(7, 18), (13, 18)]

    obs = [
        # Central divider (most of it)
        (10, 18), (10, 19), (10, 20), (10, 21), (10, 22),
        # Left corridor obstacles
        (5, 19), (8, 20), (6, 21), (5, 23), (8, 23),
        (7, 24), (5, 25), (6, 26),
        # Right corridor obstacles
        (15, 19), (12, 20), (14, 21), (15, 23), (12, 23),
        (13, 24), (15, 25), (14, 26),
        # Bottom merge area
        (8, 27), (12, 27),
        (9, 26), (11, 26),
    ]
    return logs, obs


def layout_v6():
    """
    Candidate 6: Wide open approach with traps. High obstacle count, longer solution.
    Key idea: obstacles create 'one way' zones where logs must travel specific directions.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Top row: wide gap in middle only
        (5, 18), (15, 18),   # corner blocks (logs start just inside)
        # Row 19
        (7, 19), (9, 19), (11, 19), (13, 19),
        # Row 20: open but cornertraps
        (5, 20), (15, 20),
        (8, 20), (12, 20),
        # Row 21
        (6, 21), (10, 21), (14, 21),
        # Row 22: partial wall
        (7, 22), (9, 22), (11, 22), (13, 22),
        # Row 23: open
        (5, 23), (15, 23),
        # Row 24: pinch
        (6, 24), (8, 24), (12, 24), (14, 24),
        # Row 25
        (10, 25),
        (7, 25), (13, 25),
        # Row 26
        (9, 26), (11, 26),
        (5, 26), (15, 26),
        # Row 27: funnel
        (8, 27), (12, 27),
        (6, 27), (14, 27),
    ]
    return logs, obs


def print_path(path, label=""):
    """Print each push as a before/after log position change."""
    if not path:
        return
    print(f"  Path ({len(path)-1} pushes):")
    for i in range(1, len(path)):
        prev = path[i-1]
        curr = path[i]
        moved_from = sorted(prev - curr)
        moved_to   = sorted(curr - prev)
        print(f"    push {i:3d}: {moved_from} -> {moved_to}")


def layout_v7():
    """
    Hard: forced exit at column 10 only (obstacles block y=28 except x=9,10,11).
    Logs must thread a maze to reach the center exit.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Bottom funnel — only columns 9,10,11 passable at y=27-28
        (5, 27), (6, 27), (7, 27), (8, 27),
        (12, 27), (13, 27), (14, 27), (15, 27),
        # Middle obstacles — force circuitous paths
        (7, 19), (13, 19),
        (5, 20), (15, 20), (9, 20), (11, 20),
        (6, 21), (14, 21),
        (8, 22), (12, 22),
        (10, 23),
        (7, 24), (13, 24),
        (5, 25), (15, 25),
        (9, 25), (11, 25),
        (8, 26), (12, 26),
    ]
    return logs, obs


def layout_v8():
    """
    Hard: narrow corridors, no direct routes. Both logs travel long zigzag paths.
    Exit only at column 10 (y=28 locked except center).
    """
    logs = [(5, 18), (15, 18)]

    obs = [
        # Lock y=28 to columns 9-11 only
        (5, 28), (6, 28), (7, 28), (8, 28),
        (12, 28), (13, 28), (14, 28), (15, 28),
        # Top area: force inward
        (7, 18), (13, 18),
        (6, 19), (10, 19), (14, 19),
        (8, 20), (12, 20),
        # Mid maze
        (5, 21), (15, 21), (9, 21), (11, 21),
        (7, 22), (13, 22),
        (10, 22),
        (6, 23), (14, 23),
        (8, 24), (12, 24),
        # Lower funnel
        (5, 25), (15, 25),
        (7, 26), (13, 26), (10, 26),
        (9, 27), (11, 27),
    ]
    return logs, obs


def layout_v9():
    """
    Harder variant of v5: extend the central divider, add more routing obstacles.
    Central divider blocks column 10 from y=18 to y=24, forcing logs out to sides,
    then obstacles at sides force them back to column 10 at the bottom.
    """
    logs = [(7, 18), (13, 18)]

    obs = [
        # Extended central divider
        (10, 18), (10, 19), (10, 20), (10, 21), (10, 22), (10, 23), (10, 24),
        # Left corridor obstacles (force zigzag)
        (5, 19), (8, 20), (6, 21),
        (5, 22), (7, 23), (5, 24),
        (8, 25), (6, 26), (5, 27),
        # Right corridor obstacles (mirror)
        (15, 19), (12, 20), (14, 21),
        (15, 22), (13, 23), (15, 24),
        (12, 25), (14, 26), (15, 27),
        # Bottom convergence zone
        (9, 25), (11, 25),
        (8, 27), (12, 27),
    ]
    return logs, obs


def layout_v10():
    """
    Hard: 'cross' pattern divider with side rooms.
    Key insight: logs need to enter side rooms and exit in specific directions.
    """
    logs = [(6, 19), (14, 19)]

    obs = [
        # Horizontal bar
        (5, 22), (6, 22), (7, 22), (8, 22), (9, 22),
        (11, 22), (12, 22), (13, 22), (14, 22), (15, 22),
        # Vertical bar (partial)
        (10, 18), (10, 19), (10, 20), (10, 21),
        (10, 23), (10, 24), (10, 25),
        # Side room obstacles
        (6, 20), (14, 20),
        (7, 24), (13, 24),
        (5, 26), (15, 26),
        (8, 27), (12, 27),
        (7, 25), (13, 25),
        (9, 27), (11, 27),
    ]
    return logs, obs


def layout_v11():
    """
    Modified v5 with harder routing. Central divider + additional blocking.
    Force a longer path by blocking shortcut exits.
    """
    logs = [(7, 18), (13, 18)]

    obs = [
        # Central divider (tall)
        (10, 18), (10, 19), (10, 20), (10, 21), (10, 22), (10, 23),
        # Block shortcut exit at left: prevent log going straight down left side
        (5, 19), (5, 21), (5, 23), (5, 25),
        (15, 19), (15, 21), (15, 23), (15, 25),
        # Force S-curves in left corridor
        (8, 20), (6, 21), (9, 22),
        (7, 24), (9, 24), (6, 25),
        # Mirror for right
        (12, 20), (14, 21), (11, 22),
        (13, 24), (11, 24), (14, 25),
        # Bottom funnel
        (8, 26), (12, 26),
        (7, 27), (13, 27),
        (9, 27), (11, 27),
    ]
    return logs, obs


def layout_v12():
    """
    v5 with v5's exact solution path blocked.
    v5 solution: Log A: col7 down→ col9 east → col10 east → south to stream
                 Log B: col13 down → col11 west → col10 west → south to stream
    Block those specific shortcuts, force detours.
    """
    logs = [(7, 18), (13, 18)]

    obs = [
        # Central divider (same as v5)
        (10, 18), (10, 19), (10, 20), (10, 21), (10, 22),
        # v5 base obstacles
        (5, 19), (15, 19),
        (8, 20), (12, 20),
        (6, 21), (14, 21),
        (5, 23), (15, 23), (8, 23), (12, 23),
        (7, 24), (13, 24),
        (5, 25), (15, 25),
        (9, 26), (11, 26),
        (8, 26), (12, 26),
        # NEW: block the direct south path on col 7 & 13
        (7, 20), (13, 20),
        # NEW: block col 9 at row 22-23 to prevent easy eastward push
        (9, 22), (11, 22),
        # NEW: block the direct approach to col 10 at row 25
        (9, 25), (11, 25),
        # NEW: funnel bottom 3 rows
        (5, 27), (6, 27), (14, 27), (15, 27),
    ]
    return logs, obs


def layout_v13():
    """
    Serpentine maze. The corridor snakes back and forth across the puzzle width.
    Logs must travel the snake path to reach bottom center.
    Each turn = more pushes. Designed for 50+ push solution.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Row 19: wall with RIGHT passage only
        (5, 19), (6, 19), (7, 19), (8, 19), (9, 19), (10, 19), (11, 19), (12, 19),
        # Row 21: wall with LEFT passage only
        (8, 21), (9, 21), (10, 21), (11, 21), (12, 21), (13, 21), (14, 21), (15, 21),
        # Row 23: wall with RIGHT passage only
        (5, 23), (6, 23), (7, 23), (8, 23), (9, 23), (10, 23), (11, 23), (12, 23),
        # Row 25: wall with LEFT passage only
        (8, 25), (9, 25), (10, 25), (11, 25), (12, 25), (13, 25), (14, 25), (15, 25),
        # Bottom: narrow to center
        (5, 27), (6, 27), (7, 27), (13, 27), (14, 27), (15, 27),
    ]
    return logs, obs


def layout_v14():
    """
    Asymmetric maze — the right log's path is deliberately longer.
    Both can go in either order, but the puzzle tests awareness of the other log.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Left section: moderate obstacles
        (5, 19), (7, 20), (5, 21),
        (8, 22), (6, 23), (5, 24),
        (7, 25), (5, 26),
        # Right section: more complex routing
        (15, 19), (13, 19), (12, 20),
        (14, 21), (15, 22), (11, 22), (13, 22),
        (12, 23), (15, 24), (14, 24),
        (11, 25), (13, 25), (15, 25),
        (12, 26), (14, 26),
        # Central obstacles to prevent easy center rush
        (10, 20), (10, 22), (10, 24),
        (9, 21), (11, 21), (9, 23), (11, 23),
        # Bottom funnel
        (5, 27), (6, 27), (14, 27), (15, 27),
        (8, 27), (12, 27),
    ]
    return logs, obs


def layout_v15():
    """
    The 'hourglass' — wide at top, forced through a 3-wide center, wide at bottom.
    Logs must both pass through the narrow waist. Waist is at y=23-24.
    After the waist, both logs have room to maneuver to the exit column.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Hourglass neck at y=22-24 — only columns 9-11 open
        (5, 22), (6, 22), (7, 22), (8, 22),
        (12, 22), (13, 22), (14, 22), (15, 22),
        (5, 23), (6, 23), (7, 23), (8, 23),
        (12, 23), (13, 23), (14, 23), (15, 23),
        # Upper maze (y=18-21) — keep open but with routing obstacles
        (8, 19), (12, 19),
        (10, 20),
        (7, 21), (13, 21),
        # Lower maze (y=24-28) — logs must spread from center then funnel to exit
        (10, 24),
        (8, 25), (12, 25),
        (6, 26), (14, 26),
        (7, 27), (9, 27), (11, 27), (13, 27),
    ]
    return logs, obs


def layout_v16():
    """
    Most careful design yet. Based on analysis of v5 path:
    - Block all direct shortcuts identified in v5
    - Add mid-maze complexity
    - Funnel bottom to 5 columns (8-12)
    Target: 50+ push solution with convergence to col 9-11.
    """
    logs = [(6, 18), (14, 18)]

    obs = [
        # Block outer vertical lanes (prevent coast-down-the-edge routing)
        (5, 19), (15, 19),
        (5, 21), (15, 21),
        (5, 23), (15, 23),
        (5, 25), (15, 25),
        # Block inner easy paths
        (7, 19), (13, 19),
        (9, 20), (11, 20),
        (8, 21), (12, 21),
        (7, 22), (13, 22),
        (10, 22),
        # Mid-puzzle zigzag obstacles
        (6, 23), (14, 23),
        (9, 24), (11, 24),
        (8, 25), (12, 25),
        (10, 25),
        # Lower funnel
        (6, 26), (14, 26),
        (7, 27), (9, 27), (11, 27), (13, 27),
        (5, 27), (15, 27),
    ]
    return logs, obs


def layout_v17():
    """
    Designed path for Log A: zigzag west then east.
    (6,18)→E→(8,18)→S→(8,20)→W→(5,20)→S→(5,23)→E→(9,23)→S→(9,25)→E→(10,25)→S→stream
    Symmetric for Log B: same zigzag on right side to same exit column.
    Obstacles block deviations from these paths.
    """
    logs = [(6, 18), (14, 18)]
    obs = [
        # Force Log A east along y=18: block south at cols 5-7
        (5, 19), (6, 19), (7, 19),
        # Stop Log A east at col 8
        (9, 18),
        # Force Log A south at col 8 to y=20 only (block y=21)
        (8, 21),
        # Force Log A west at y=20 (y=21 blocked, must stay at y=20 going west)
        (6, 20), (7, 20),
        # Force Log A south at col 5 to y=23 (block y=24 at col 5)
        (5, 24),
        # Force Log A east at y=23: block south for cols 5-8
        (6, 23), (7, 23), (8, 23),
        # Stop Log A east at col 9
        (10, 23),
        # Force Log A south at col 9 to y=25
        (9, 26),
        # Force Log A east at y=25
        (8, 25),
        # Stop Log A at col 10, then south to stream
        (11, 25),
        # Symmetric for Log B (right side)
        (15, 19), (14, 19), (13, 19),
        (11, 18),
        (12, 21),
        (14, 20), (13, 20),
        (15, 24),
        (14, 23), (13, 23), (12, 23),
        (11, 23),   # shares with Log A stop — wait, already have (10,23)
        (11, 26),
        (12, 25),
    ]
    # De-duplicate
    obs = list(set(obs))
    return logs, obs


def layout_v18():
    """
    Both logs must cross to the OTHER side of the puzzle to reach the exit.
    Log A starts left, must exit from the RIGHT corridor.
    Log B starts right, must exit from the LEFT corridor.
    Exit column: 10 (center). They literally swap sides.
    """
    logs = [(6, 18), (14, 18)]
    obs = [
        # Central vertical wall cols 9-11 at y=18-21 forces logs to outer sides
        (9, 18), (10, 18), (11, 18),
        (9, 19), (10, 19), (11, 19),
        (9, 20), (10, 20), (11, 20),
        (9, 21), (10, 21), (11, 21),
        # Left corridor obstacles (x=5-8)
        (5, 22), (7, 23), (5, 24), (6, 25), (8, 24),
        # Right corridor obstacles (mirror)
        (15, 22), (13, 23), (15, 24), (14, 25), (12, 24),
        # Cross-over zone: logs must cross at y=22
        # Gaps in central wall at y=22-23 let logs cross
        # Lower funnel
        (5, 26), (15, 26), (7, 27), (13, 27),
        (8, 27), (12, 27),
    ]
    return logs, obs


def layout_v19():
    """
    Comb structure: 5 teeth pointing south from y=20-25.
    Logs must weave through the teeth gaps to reach the bottom.
    Teeth at x=6,8,10,12,14. Gaps at x=7,9,11,13.
    After weaving, funnel to exit.
    """
    logs = [(5, 18), (15, 18)]
    obs = [
        # Comb teeth (5 teeth, each 4 rows tall)
        (6, 20), (6, 21), (6, 22), (6, 23),
        (8, 20), (8, 21), (8, 22), (8, 23),
        (10, 20), (10, 21), (10, 22), (10, 23),
        (12, 20), (12, 21), (12, 22), (12, 23),
        (14, 20), (14, 21), (14, 22), (14, 23),
        # Block top of comb to force logs to enter from sides
        (5, 19), (6, 19), (7, 19),
        (13, 19), (14, 19), (15, 19),
        # Bottom funnel after comb
        (5, 26), (15, 26), (6, 27), (14, 27), (7, 27), (13, 27),
    ]
    return logs, obs


def layout_v20():
    """
    Two separate spiral corridors that both end at (10, 28).
    Left spiral for Log A: (7,18)→down left side→across to center→down to stream
    Right spiral for Log B: mirror.
    Key: each log travels a full spiral path ~25 pushes, total ~50.
    """
    logs = [(7, 18), (13, 18)]
    obs = [
        # Left spiral — guides Log A: down col 7, east at y=22, down col 9-10
        (5, 19), (6, 20), (5, 21), (6, 22),
        (8, 19), (7, 20),   # block col 7 deviation
        (8, 22), (8, 21),   # force east then south at y=22
        (9, 24), (8, 24),   # route through center
        (7, 25), (6, 26),
        # Right spiral mirror
        (15, 19), (14, 20), (15, 21), (14, 22),
        (12, 19), (13, 20),
        (12, 22), (12, 21),
        (11, 24), (12, 24),
        (13, 25), (14, 26),
        # Central separator (keeps Log A on left, Log B on right initially)
        (10, 18), (10, 19), (10, 20), (10, 21),
        # Bottom convergence
        (5, 27), (15, 27), (8, 26), (12, 26),
        (7, 27), (13, 27), (9, 27), (11, 27),
    ]
    return logs, obs


def layout_v21():
    """
    Based on what works in v14 (Log B reuses Log A's path).
    Design specifically to force each log to travel ~18 pushes,
    with forced cross-corridor travel in the upper section.
    Upper half: obstacles force Log B to cross entire width.
    Lower half: shared convergence path.
    """
    logs = [(6, 18), (14, 18)]
    obs = [
        # Right side upper: block Log B from going south directly
        (14, 19), (15, 20), (13, 20), (15, 21), (14, 21),
        (12, 19), (13, 21), (15, 22), (12, 22),
        # Force Log B west across top (Log B can only go west at y=18-19)
        (11, 20), (12, 20),
        # Left side upper: Log A has clear descent path
        (5, 20), (5, 22),
        # Mid section: both logs must share left corridor
        (7, 21), (9, 22), (8, 23),
        (6, 24), (8, 24),
        # Both must converge to col 9-10 at bottom
        (7, 25), (11, 25),
        (5, 26), (15, 26),
        (6, 27), (14, 27), (8, 27), (12, 27),
    ]
    return logs, obs


def layout_v22():
    """
    Deliberate 'wall-with-gate' design.
    Three horizontal walls each with a single-column gate at different positions.
    Logs must zigzag through the gates in sequence.
    Gate positions: y=20 gate at col 13, y=23 gate at col 7, y=26 gate at col 10.
    With 2 logs, they both need to pass through each gate, creating interesting sequencing.
    """
    logs = [(6, 18), (14, 18)]
    obs = [
        # Wall 1 at y=20: gate ONLY at col 13 (cols 5-12 and 14-15 blocked)
        (5,20),(6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(14,20),(15,20),
        # Wall 2 at y=23: gate ONLY at col 7 (cols 5-6 and 8-15 blocked)
        (5,23),(6,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),(15,23),
        # Wall 3 at y=26: gate ONLY at col 10 (cols 5-9 and 11-15 blocked)
        (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
        # Light obstacles in open zones to prevent trivial paths
        (12, 19), (8, 22), (12, 22), (9, 25), (11, 25),
    ]
    return logs, obs


def layout_v22_fixed():
    """
    Three horizontal walls, each with exactly ONE gate.
    Gates alternate corners: (14,20), (6,23), (10,26).
    Both logs MUST pass through all 3 gates — no shortcut possible.
    Either log can go first (symmetric).

    Path per log:
      Start → travel to col 14 at y=19 → gate (14,20) → travel to col 6 at y=22
      → gate (6,23) → travel to col 10 at y=25 → gate (10,26) → stream
    Estimated: ~25 pushes per log = ~50 total.
    """
    logs = [(8, 18), (12, 18)]
    obs = [
        # ── Wall 1 at y=20: only col 14 open ─────────────────────────────────
        (5,20),(6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(15,20),
        # ── Wall 2 at y=23: only col 6 open ──────────────────────────────────
        (5,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),(15,23),
        # ── Wall 3 at y=26: only col 10 open ─────────────────────────────────
        (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
        # ── Zone 1 obstacles (y=18-19): slow approach to gate 1 ───────────────
        (10, 19),              # center bump — log must go around
        (14, 19),              # guard above gate 1: log can't shortcut to col 14 early
        # ── Zone 2 obstacles (y=21-22): slow travel to gate 2 ─────────────────
        (10, 21),              # central bump
        (6,  22), (8, 22),     # guard gate 2 approach
        # ── Zone 3 obstacles (y=24-25): slow approach to gate 3 ───────────────
        (8,  25), (12, 25),    # flanking bumps
    ]
    return logs, obs


def layout_v22_v2():
    """
    Three walls same as v22_fixed but wider zone obstacles to force longer travel.
    Upper zone: logs start at corners, must zigzag to gate at col 14.
    Middle zone: must zigzag from col 14 to col 6.
    Lower zone: must zigzag from col 6 to col 10.
    """
    logs = [(5, 18), (15, 18)]
    obs = [
        # ── Wall 1 at y=21: only col 14 open ─────────────────────────────────
        (5,21),(6,21),(7,21),(8,21),(9,21),(10,21),(11,21),(12,21),(13,21),(15,21),
        # ── Wall 2 at y=24: only col 6 open ──────────────────────────────────
        (5,24),(7,24),(8,24),(9,24),(10,24),(11,24),(12,24),(13,24),(14,24),(15,24),
        # ── Wall 3 at y=27: only col 10 open ─────────────────────────────────
        (5,27),(6,27),(7,27),(8,27),(9,27),(11,27),(12,27),(13,27),(14,27),(15,27),
        # ── Zone 1 (y=18-20): obstacles to route logs to col 14 ───────────────
        (6, 19), (10, 19), (8, 20),
        # ── Zone 2 (y=22-23): obstacles to route from col 14 to col 6 ─────────
        (13, 22), (9, 22), (11, 23),
        # ── Zone 3 (y=25-26): obstacles to route from col 6 to col 10 ─────────
        (7, 25), (9, 26),
    ]
    return logs, obs


def layout_v22_v3():
    """
    Three walls with gates at far-left, far-right, center.
    Forces max horizontal travel: right → left → center.
    Logs start in the center, must travel far left then far right then center.
    Gates: (5,20), (15,23), (10,26) — maximum zig-zag distance.
    """
    logs = [(9, 18), (11, 18)]
    obs = [
        # ── Wall 1 at y=20: only col 5 open (far left) ───────────────────────
        (6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(14,20),(15,20),
        # ── Wall 2 at y=23: only col 15 open (far right) ─────────────────────
        (5,23),(6,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),
        # ── Wall 3 at y=26: only col 10 open (center) ────────────────────────
        (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
        # Zone bumps to prevent instant shortcuts
        (7, 19), (13, 19),
        (8, 22), (12, 22),
        (7, 25), (13, 25),
    ]
    return logs, obs


def layout_v23():
    """
    THREE-GATE CLEAN — gates at col 14 (y=20), col 6 (y=23), col 10 (y=26).
    NO zone obstacles: just the three mandatory walls.
    Every log MUST zigzag: right → left → center.
    Expected path per log: ~29 pushes. Total: ~50+.
    """
    logs = [(8, 18), (12, 18)]
    obs = [
        # Wall 1 y=20: only col 14 open
        (5,20),(6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(15,20),
        # Wall 2 y=23: only col 6 open
        (5,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),(15,23),
        # Wall 3 y=26: only col 10 open
        (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
    ]
    return logs, obs


def layout_v24():
    """
    THREE-GATE CLEAN — gates at col 6 (y=20), col 14 (y=23), col 10 (y=26).
    Mirror of v23: zigzag left → right → center.
    Logs start far apart to force initial convergence.
    """
    logs = [(5, 18), (15, 18)]
    obs = [
        # Wall 1 y=20: only col 6 open
        (5,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(14,20),(15,20),
        # Wall 2 y=23: only col 14 open
        (5,23),(6,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(15,23),
        # Wall 3 y=26: only col 10 open
        (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
    ]
    return logs, obs


def layout_v25():
    """
    THREE-GATE CLEAN — gates at col 5 (y=20), col 15 (y=23), col 10 (y=26).
    Maximum zigzag distance: far-left → far-right → center.
    Logs near center force long initial horizontal travel in both directions.
    """
    logs = [(9, 18), (11, 18)]
    obs = [
        # Wall 1 y=20: only col 5 open (far left)
        (6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(14,20),(15,20),
        # Wall 2 y=23: only col 15 open (far right)
        (5,23),(6,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),
        # Wall 3 y=26: only col 10 open
        (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
    ]
    return logs, obs


def layout_v26():
    """
    THREE-GATE with safe zone obstacles.
    Based on v23 (gates 14/6/10). Add bumps that only block row y=21 or y=22
    (never creating a dead-end: log can always escape north or east/west).
    Key rule: no obstacle at (x, y) where (x, y-1) is wall AND adjacent cells also blocked.
    """
    logs = [(8, 18), (12, 18)]
    obs = [
        # Walls
        (5,20),(6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(15,20),
        (5,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),(15,23),
        (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
        # Zone 1 bumps (y=18-19): force logs to travel further before gate
        (11, 19),   # center-right bump — log at col 12 must detour around
        # Zone 2 bumps (y=21-22): slow zigzag to gate 2
        # Safe: place at y=21 only (wall at y=20 above, but log can escape south at any col)
        (11, 21), (9, 21),   # center bumps force wider arc
        # Zone 3 bumps (y=24-25): slow path from col 6 to col 10
        # Safe: at y=24 only (wall at y=23 above, but log can escape south from gate col)
        # Actually: to push log south from (x,24) to (x,25), player at (x,23).
        # Only col 6 (gate 2) is open at y=23. So logs must pass through (6,24)→(6,25).
        # Obstacles at y=24 in cols != 6 that are EAST of the log path are safe.
        (9, 25), (11, 25),   # flanking bumps near gate 3
    ]
    return logs, obs


if __name__ == "__main__":
    import sys
    show_path = "--path" in sys.argv
    filter_name = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            filter_name = arg

    candidates = [
        ("v14: Asymmetric (36 ref)",              layout_v14),
        ("v17: Designed zigzag paths",            layout_v17),
        ("v18: Cross-sides swap",                 layout_v18),
        ("v19: Comb teeth structure",             layout_v19),
        ("v20: Two spiral corridors",             layout_v20),
        ("v21: Force Log B to cross width",       layout_v21),
        ("v22: Three walls each with one gate",   layout_v22),
        ("v22_fixed: Gates 14/6/10 fixed",        layout_v22_fixed),
        ("v22_v2: Walls y21/24/27 gates 14/6/10", layout_v22_v2),
        ("v22_v3: Gates 5/15/10 max zigzag",      layout_v22_v3),
        ("v23: CLEAN gates 14/6/10 no zone obs",  layout_v23),
        ("v24: CLEAN gates 6/14/10 mirror",       layout_v24),
        ("v25: CLEAN gates 5/15/10 max dist",     layout_v25),
        ("v26: v23+safe zone bumps",              layout_v26),
    ]

    print("=" * 60)
    print("FQ STREAM-BRIDGE SOKOBAN - PUZZLE SOLVER")
    print("=" * 60)

    for name, layout_fn in candidates:
        if filter_name and filter_name not in name:
            continue
        logs, obs = layout_fn()
        render_puzzle(obs, logs, label=name)
        print(f"  Obstacles: {len(obs)}  |  Log starts: {logs}")
        n, path = solve(obs, logs)
        if n is None:
            print(f"  UNSOLVABLE (within 500 pushes)")
        else:
            final_logs = path[-1]
            print(f"  SOLVABLE in {n} pushes  |  Final: {sorted(final_logs)}")
            if show_path:
                print_path(path)
        print()
