"""
sokoban_gen.py — Backward-BFS Sokoban puzzle generator for the FQ chamber.

Based on Taylor & Parberry (2011): work backwards from the solved state to
find starting log positions that maximise the number of pushes required.
Quality metric: push count first, box lines (direction changes) second.

Usage:
    python sokoban_gen.py            # test all built-in rooms
    python sokoban_gen.py --room A   # test one room
    python sokoban_gen.py --apply A  # print config.py snippet for room A

The grid
--------
  y=16-17  : chamber (fully open, player can reach any x)
  y=18-28  : 11×11 puzzle area  (x=5-15)
  y=29     : near stream  — logs enter here, become ford tiles
  y=30     : far stream   — second log slides here via ford

Win condition: one log at y=29 AND one log at y=30 (any x in 9-11 for a
usable bridge, but the BFS uses all x to maximise the state space searched).
"""

from __future__ import annotations
import argparse, sys, time
from collections import deque

# ── Grid constants (mirror config.py) ─────────────────────────────────────────
PX0, PX1 = 5, 15        # puzzle x range (inclusive)
PY0, PY1 = 18, 28       # puzzle y range (inclusive)
SY,  SY2 = 29, 30       # stream rows
CH0, CH1 = 16, 17       # chamber rows (always open)
W        = 21           # zone width
BRIDGE_X = frozenset({9, 10, 11})   # valid x for a usable bridge


# ── Cell-set builders ──────────────────────────────────────────────────────────

def build_sets(obstacles: frozenset) -> tuple[frozenset, frozenset]:
    """
    Return (player_walkable, log_walkable) for a given obstacle set.

    Player:  chamber rows + puzzle floor (no stream, no obstacles)
    Log:     puzzle floor + both stream rows (no obstacles)
    """
    pw, lw = set(), set()
    for y in range(CH0, CH1 + 1):          # chamber — full width
        for x in range(1, W - 1):
            pw.add((x, y))
    for y in range(PY0, PY1 + 1):          # puzzle area
        for x in range(PX0, PX1 + 1):
            if (x, y) not in obstacles:
                pw.add((x, y))
                lw.add((x, y))
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
ROOM_CORRIDORS = _obs(
    # Left–centre divider (x=8): solid except gaps at y=20 and y=26
    (8,19),(8,21),(8,22),(8,23),(8,24),(8,25),(8,27),(8,28),
    # Centre–right divider (x=12): solid except gaps at y=23 and y=27
    (12,19),(12,20),(12,21),(12,22),(12,24),(12,25),(12,26),(12,28),
    # Horizontal cross-bars to break long open stretches
    (6,22),(7,22),           # left lane y=22
    (9,25),(10,25),(11,25),  # centre lane y=25
    (13,22),(14,22),         # right lane y=22
)

# ── Room C: "Chambers" ────────────────────────────────────────────────────────
# Two side chambers (left x=5-7, right x=13-15) connected to a central
# corridor (x=9-11) via single-cell openings.  Getting logs out of the
# side chambers requires precise sequencing.
ROOM_CHAMBERS = _obs(
    # Left chamber wall (x=8): open at y=21 and y=25
    (8,18),(8,19),(8,20),(8,22),(8,23),(8,24),(8,26),(8,27),(8,28),
    # Right chamber wall (x=12): open at y=22 and y=26
    (12,18),(12,19),(12,20),(12,21),(12,23),(12,24),(12,25),(12,27),(12,28),
    # Centre blocker: single pillar at (10,23) breaks direct path
    (10,23),
)

# ── Room D: "Cross" ───────────────────────────────────────────────────────────
# A cross-shaped open area with obstacle blocks in the four quadrants.
# Logs start in the corners and must navigate through the cross to the stream.
ROOM_CROSS = _obs(
    # Top-left quadrant obstacles
    (6,19),(7,19),(6,20),(7,20),
    # Top-right quadrant obstacles
    (13,19),(14,19),(13,20),(14,20),
    # Middle-left pillar
    (6,23),(6,24),
    # Middle-right pillar
    (14,23),(14,24),
    # Bottom-left quadrant obstacles
    (6,26),(7,26),(6,27),(7,27),
    # Bottom-right quadrant obstacles
    (13,26),(14,26),(13,27),(14,27),
    # Centre pillar
    (10,21),
    (10,26),
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
# staggered so logs MUST switch lanes to progress south; the two logs must
# choreograph which lane each occupies at each step.
ROOM_SLOT = _obs(
    # Left divider (x=8): open at y=21 and y=25
    (8,18),(8,19),(8,20),(8,22),(8,23),(8,24),(8,26),(8,27),(8,28),
    # Right divider (x=12): open at y=23 and y=27
    (12,18),(12,19),(12,20),(12,21),(12,22),(12,24),(12,25),(12,26),(12,28),
    # Bottom funnel (y=28): only x=9-11 open  (x=5-8 and 12-15 blocked)
    # (x=8 and x=12 already covered; add extra blocks for the funnel)
    (5,28),(6,28),(7,28),(13,28),(14,28),(15,28),
    # Centre deflector
    (10,20),(10,25),
)

ROOMS = {
    "A": ("Pinball",       ROOM_PINBALL),
    "B": ("Corridors",     ROOM_CORRIDORS),
    "C": ("Chambers",      ROOM_CHAMBERS),
    "D": ("Cross",         ROOM_CROSS),
    "E": ("Classic Plus",  ROOM_CLASSIC_PLUS),
    "F": ("Slot",          ROOM_SLOT),
}


# ── Visualiser ────────────────────────────────────────────────────────────────

def visualise(obstacles: frozenset,
              log_a: tuple | None = None,
              log_b: tuple | None = None) -> None:
    CHARS = {
        "obs":   "#",
        "log_a": "A",
        "log_b": "B",
        "floor": ".",
    }
    print()
    for y in range(PY0, PY1+1):
        row = f"y={y}: "
        for x in range(PX0, PX1+1):
            if (x,y) == log_a:
                row += CHARS["log_a"]
            elif (x,y) == log_b:
                row += CHARS["log_b"]
            elif (x,y) in obstacles:
                row += CHARS["obs"]
            else:
                row += CHARS["floor"]
        print(row)
    print()


# ── Config snippet generator ──────────────────────────────────────────────────

def config_snippet(name: str, obstacles: frozenset,
                   log_a: tuple, log_b: tuple,
                   push_count: int, box_lines_n: int) -> str:
    obs_sorted = sorted(obstacles)
    lines = [
        f"    # ── {name}  ({len(obstacles)} obstacles, ~{push_count} pushes, ~{box_lines_n} box lines)",
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
                    help="Room key (A/B/C/D) or 'all'")
    ap.add_argument("--apply", default=None,
                    help="Print config.py snippet for this room key")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--y18", action="store_true",
                    help="Only allow log starts on y=18")
    args = ap.parse_args()

    if args.apply:
        key = args.apply.upper()
        if key not in ROOMS:
            sys.exit(f"Unknown room: {key}")
        room_name, obs = ROOMS[key]
        print(f"Solving room {key} ({room_name})…")
        results = best_starts(obs, top_n=1)
        if results:
            d, bl, la, lb = results[0]
            print(config_snippet(room_name, obs, la, lb, d, bl))
            visualise(obs, la, lb)
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


if __name__ == "__main__":
    main()
