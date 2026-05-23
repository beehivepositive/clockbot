"""
One-shot migration: update fq_id=1 to the v25 three-wall gate puzzle.

Three complete horizontal walls, each with one gate:
  Wall 1  y=20  gate at col  5  (far left)
  Wall 2  y=23  gate at col 15  (far right)
  Wall 3  y=26  gate at col 10  (centre)

BFS-verified minimum solution: 62 pushes.

Run on server with:
  python /home/discord-bot/migrate_sokoban.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "dwarf_explorer", "data", "shared.db")

FQ_ID = 1

# ── New obstacle layout (zone-absolute coords) ───────────────────────────────
# Wall 1 at y=20: gate ONLY at col 5 (cols 6-15 blocked)
# Wall 2 at y=23: gate ONLY at col 15 (cols 5-14 blocked)
# Wall 3 at y=26: gate ONLY at col 10 (cols 5-9 and 11-15 blocked)
NEW_OBSTACLES = [
    # Wall 1 (y=20)
    (6,20),(7,20),(8,20),(9,20),(10,20),(11,20),(12,20),(13,20),(14,20),(15,20),
    # Wall 2 (y=23)
    (5,23),(6,23),(7,23),(8,23),(9,23),(10,23),(11,23),(12,23),(13,23),(14,23),
    # Wall 3 (y=26)
    (5,26),(6,26),(7,26),(8,26),(9,26),(11,26),(12,26),(13,26),(14,26),(15,26),
]

# New log starting positions
LOG_A_START = (9,  18)
LOG_B_START = (11, 18)


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
    print(f"  Puzzle area reset: {c.rowcount} tiles -> fq_puzzle_floor")

    # ── 2. Stamp new obstacles ────────────────────────────────────────────────
    for ox, oy in NEW_OBSTACLES:
        c.execute("""
            UPDATE forest_quest_tiles SET tile_type = 'fq_obstacle'
            WHERE fq_id = ? AND local_x = ? AND local_y = ?
        """, (FQ_ID, ox, oy))
    print(f"  Obstacles set: {len(NEW_OBSTACLES)} tiles -> fq_obstacle")

    # ── 3. Convert y=29 floor tiles to fq_stream ─────────────────────────────
    c.execute("""
        UPDATE forest_quest_tiles SET tile_type = 'fq_stream'
        WHERE fq_id = ? AND local_y = 29 AND tile_type != 'fq_wall'
    """, (FQ_ID,))
    print(f"  y=29 stream: {c.rowcount} tiles -> fq_stream")

    # ── 4. Reset any existing ford tiles back to fq_stream ────────────────────
    c.execute("""
        UPDATE forest_quest_tiles SET tile_type = 'fq_stream'
        WHERE fq_id = ? AND tile_type = 'fq_stream_ford'
    """, (FQ_ID,))
    print(f"  Ford reset: {c.rowcount} tiles -> fq_stream")

    # ── 5. Remove stale fq_log_target tiles (old orange markers) ─────────────
    c.execute("""
        UPDATE forest_quest_tiles SET tile_type = 'fq_puzzle_floor'
        WHERE fq_id = ? AND tile_type = 'fq_log_target'
    """, (FQ_ID,))
    print(f"  Log targets removed: {c.rowcount} tiles -> fq_puzzle_floor")

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
    print(f"  Log A reset -> {LOG_A_START}, Log B reset -> {LOG_B_START}")

    # ── 7. Reset solved flag ──────────────────────────────────────────────────
    c.execute("""
        UPDATE forest_quest_areas SET solved=0 WHERE fq_id=?
    """, (FQ_ID,))
    print(f"  Puzzle solved flag reset")

    db.commit()
    db.close()
    print("Migration complete (v25 three-wall gate puzzle)")


if __name__ == "__main__":
    main()
