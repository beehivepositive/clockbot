"""
One-shot migration: update fq_id=1 to the new 2-wide stream / no-target Sokoban design.

Run on server with:
  python /home/discord-bot/migrate_sokoban.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "dwarf_explorer", "data", "shared.db")

FQ_ID = 1

# New obstacle layout (zone-absolute coords)
# FQ_PUZZLE_X0=5, FQ_PUZZLE_Y0=18
NEW_OBSTACLES = [
    (10, 20),                         # center top blocker
    (8,  21), (12, 21),               # upper funnel
    (6,  23), (14, 23), (9, 23), (11, 23),  # mid section
    (7,  25), (13, 25), (10, 25),     # lower section
    (8,  27), (12, 27),               # near bottom
]

# New log starting positions
LOG_A_START = (6,  18)
LOG_B_START = (14, 18)


def main():
    print(f"Connecting to {DB_PATH}")
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    # ── 1. Reset entire puzzle area to fq_puzzle_floor ────────────────────────
    c.execute("""
        UPDATE forest_quest_tiles
        SET tile_type = 'fq_puzzle_floor'
        WHERE fq_id = ? AND local_x BETWEEN 5 AND 15 AND local_y BETWEEN 18 AND 28
    """, (FQ_ID,))
    print(f"  Puzzle area reset: {c.rowcount} tiles → fq_puzzle_floor")

    # ── 2. Stamp new obstacles ────────────────────────────────────────────────
    for ox, oy in NEW_OBSTACLES:
        c.execute("""
            UPDATE forest_quest_tiles SET tile_type = 'fq_obstacle'
            WHERE fq_id = ? AND local_x = ? AND local_y = ?
        """, (FQ_ID, ox, oy))
    print(f"  Obstacles set: {len(NEW_OBSTACLES)} tiles → fq_obstacle")

    # ── 3. Convert y=29 floor tiles to fq_stream ─────────────────────────────
    c.execute("""
        UPDATE forest_quest_tiles SET tile_type = 'fq_stream'
        WHERE fq_id = ? AND local_y = 29 AND tile_type != 'fq_wall'
    """, (FQ_ID,))
    print(f"  y=29 stream: {c.rowcount} tiles → fq_stream")

    # ── 4. Reset any existing ford tiles back to fq_stream ────────────────────
    c.execute("""
        UPDATE forest_quest_tiles SET tile_type = 'fq_stream'
        WHERE fq_id = ? AND tile_type = 'fq_stream_ford'
    """, (FQ_ID,))
    print(f"  Ford reset: {c.rowcount} tiles → fq_stream")

    # ── 5. Remove stale fq_log_target tiles (old orange markers) ─────────────
    c.execute("""
        UPDATE forest_quest_tiles SET tile_type = 'fq_puzzle_floor'
        WHERE fq_id = ? AND tile_type = 'fq_log_target'
    """, (FQ_ID,))
    print(f"  Log targets removed: {c.rowcount} tiles → fq_puzzle_floor")

    # ── 6. Reset Sokoban log positions ────────────────────────────────────────
    ax, ay = LOG_A_START
    bx, by = LOG_B_START
    c.execute("""
        UPDATE fq_puzzle_logs SET cur_x=?, cur_y=?, start_x=?, start_y=?
        WHERE fq_id=? AND log_idx=0
    """, (ax, ay, ax, ay, FQ_ID))
    c.execute("""
        UPDATE fq_puzzle_logs SET cur_x=?, cur_y=?, start_x=?, start_y=?
        WHERE fq_id=? AND log_idx=1
    """, (bx, by, bx, by, FQ_ID))
    print(f"  Log A reset → {LOG_A_START}, Log B reset → {LOG_B_START}")

    # ── 7. Reset solved flag ──────────────────────────────────────────────────
    c.execute("""
        UPDATE forest_quest_areas SET solved=0 WHERE fq_id=?
    """, (FQ_ID,))
    print(f"  Puzzle solved flag reset")

    db.commit()
    db.close()
    print("Migration complete ✓")


if __name__ == "__main__":
    main()
