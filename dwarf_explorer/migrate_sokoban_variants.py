"""
One-shot migration: re-roll the Sokoban puzzle for an existing FQ zone (fq_id=1)
to a randomly chosen variant from FQ_PUZZLE_VARIANTS.

Changes applied:
  - Deletes existing fq_obstacle tiles in the puzzle area (y=18-28)
  - Inserts fresh obstacle tiles for the chosen variant
  - Resets log start + current positions to the variant's log_a / log_b
  - Clears any ford tiles so the puzzle must be solved fresh
  - Clears the solved flag so the bridge does NOT exist yet

Usage (run on server):
  ssh -i ~/.ssh/do_key root@64.23.151.82 "cd /home/discord-bot && python3 -c \"
import sys, random
sys.path.insert(0, '/home/discord-bot')
import sqlite3
DB_PATH = '/home/discord-bot/dwarf_explorer/data/shared.db'
db = sqlite3.connect(DB_PATH)

from dwarf_explorer.config import FQ_PUZZLE_VARIANTS, FQ_PUZZLE_Y0, FQ_PUZZLE_Y1, FQ_STREAM_Y, FQ_STREAM_Y2

FQ_ID = 1
variant = random.choice(FQ_PUZZLE_VARIANTS)
print('Chosen variant:', variant['name'])

c = db.cursor()

# Remove old obstacles in puzzle area
c.execute('DELETE FROM forest_quest_tiles WHERE fq_id=? AND tile_type=\\'fq_obstacle\\' AND local_y BETWEEN ? AND ?', (FQ_ID, FQ_PUZZLE_Y0, FQ_PUZZLE_Y1))
print('Deleted', c.rowcount, 'old obstacle tiles')

# Insert new obstacle tiles
new_obs = [(FQ_ID, ox, oy, 'fq_obstacle') for (ox, oy) in variant['obstacles']]
c.executemany('INSERT OR REPLACE INTO forest_quest_tiles (fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)', new_obs)
print('Inserted', len(new_obs), 'new obstacle tiles')

# Ensure obstacle cells that WERE floor are now fq_puzzle_floor (in case of size change)
# (New variants may place obstacles over previously-floor cells — INSERT OR REPLACE covers it)

# Reset Sokoban log positions (indices 0 and 1)
ax, ay = variant['log_a']
bx, by = variant['log_b']
c.execute('UPDATE fq_puzzle_logs SET cur_x=?, cur_y=?, start_x=?, start_y=? WHERE fq_id=? AND log_idx=0', (ax, ay, ax, ay, FQ_ID))
c.execute('UPDATE fq_puzzle_logs SET cur_x=?, cur_y=?, start_x=?, start_y=? WHERE fq_id=? AND log_idx=1', (bx, by, bx, by, FQ_ID))
print(f'Reset log A to {variant[\"log_a\"]}, log B to {variant[\"log_b\"]}')

# Update the tile that WAS fq_log at old positions back to fq_puzzle_floor
c.execute('UPDATE forest_quest_tiles SET tile_type=\\'fq_puzzle_floor\\' WHERE fq_id=? AND tile_type=\\'fq_log\\' AND local_y BETWEEN ? AND ?', (FQ_ID, FQ_PUZZLE_Y0, FQ_PUZZLE_Y1))

# Clear any ford tiles (reset stream to unbroken state)
c.execute('UPDATE forest_quest_tiles SET tile_type=\\'fq_stream\\' WHERE fq_id=? AND tile_type=\\'fq_stream_ford\\' AND local_y BETWEEN ? AND ?', (FQ_ID, FQ_STREAM_Y, FQ_STREAM_Y2))
print('Cleared ford tiles')

# Clear solved flag
c.execute('UPDATE forest_quest_areas SET solved=0 WHERE fq_id=?', (FQ_ID,))

db.commit()
db.close()
print('Migration complete — variant:', variant['name'])
\""
"""

import os
import random
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "dwarf_explorer", "data", "shared.db")
sys.path.insert(0, _HERE)

FQ_ID = 1


def main():
    from dwarf_explorer.config import (
        FQ_PUZZLE_VARIANTS,
        FQ_PUZZLE_Y0, FQ_PUZZLE_Y1,
        FQ_STREAM_Y, FQ_STREAM_Y2,
    )

    variant = random.choice(FQ_PUZZLE_VARIANTS)
    print(f"Connecting to {DB_PATH}")
    print(f"Chosen variant: {variant['name']!r}")

    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    # ── Remove old obstacle tiles in puzzle area ───────────────────────────
    c.execute(
        "DELETE FROM forest_quest_tiles "
        "WHERE fq_id=? AND tile_type='fq_obstacle' AND local_y BETWEEN ? AND ?",
        (FQ_ID, FQ_PUZZLE_Y0, FQ_PUZZLE_Y1),
    )
    print(f"  Deleted {c.rowcount} old obstacle tiles")

    # ── Insert new obstacle tiles ──────────────────────────────────────────
    new_obs = [(FQ_ID, ox, oy, "fq_obstacle") for (ox, oy) in variant["obstacles"]]
    c.executemany(
        "INSERT OR REPLACE INTO forest_quest_tiles "
        "(fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        new_obs,
    )
    print(f"  Inserted {len(new_obs)} new obstacle tiles")

    # ── Reset Sokoban log positions (indices 0 and 1) ─────────────────────
    ax, ay = variant["log_a"]
    bx, by = variant["log_b"]
    c.execute(
        "UPDATE fq_puzzle_logs "
        "SET cur_x=?, cur_y=?, start_x=?, start_y=? "
        "WHERE fq_id=? AND log_idx=0",
        (ax, ay, ax, ay, FQ_ID),
    )
    c.execute(
        "UPDATE fq_puzzle_logs "
        "SET cur_x=?, cur_y=?, start_x=?, start_y=? "
        "WHERE fq_id=? AND log_idx=1",
        (bx, by, bx, by, FQ_ID),
    )
    print(f"  Log A → {variant['log_a']},  Log B → {variant['log_b']}")

    # Old log tiles in puzzle area back to puzzle floor
    c.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_puzzle_floor' "
        "WHERE fq_id=? AND tile_type='fq_log' AND local_y BETWEEN ? AND ?",
        (FQ_ID, FQ_PUZZLE_Y0, FQ_PUZZLE_Y1),
    )

    # ── Clear any existing ford tiles ─────────────────────────────────────
    c.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_stream' "
        "WHERE fq_id=? AND tile_type='fq_stream_ford' AND local_y BETWEEN ? AND ?",
        (FQ_ID, FQ_STREAM_Y, FQ_STREAM_Y2),
    )
    print("  Cleared ford tiles")

    # ── Clear solved flag so bridge must be rebuilt ────────────────────────
    c.execute("UPDATE forest_quest_areas SET solved=0 WHERE fq_id=?", (FQ_ID,))

    db.commit()
    db.close()
    print(f"Migration complete — Sokoban variant: {variant['name']!r}")


if __name__ == "__main__":
    main()
