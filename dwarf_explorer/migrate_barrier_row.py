"""
One-shot migration: add barrier row (y=28) and edge walls (x=4, x=16 for y=18-27)
to the live Sokoban chamber for fq_id=1.

Changes applied:
  - y=28, x=5-9,11-15 → fq_obstacle  (barrier wall)
  - y=28, x=10        → fq_puzzle_floor  (single cutaway at FQ_BARRIER_X)
  - y=18-27, x=4      → fq_wall  (left edge wall — prevents outside-edge push)
  - y=18-27, x=16     → fq_wall  (right edge wall)
  - Then re-runs the sokoban variant migration to pick a fresh puzzle variant

After this migration the old puzzle variant (which assumed y=28 was openable)
is no longer valid.  The variant migration is called at the end to reset
everything to a consistent state for the new barrier layout.
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
        FQ_PUZZLE_X0, FQ_PUZZLE_X1,
        FQ_PUZZLE_Y0, FQ_PUZZLE_Y1,
        FQ_BARRIER_X,
        FQ_STREAM_Y,
        FQ_STREAM_Y2,
        FQ_WIDTH,
    )

    BARRIER_Y = FQ_STREAM_Y - 1  # 28

    print(f"Connecting to {DB_PATH}")
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    # ── Step 1: Rebuild barrier row (y=28) ───────────────────────────────────
    # First ensure fq_floor exists for the full width at y=28 so there are no
    # missing tiles outside the puzzle x-range.
    print(f"  Building barrier row at y={BARRIER_Y}...")
    for x in range(1, FQ_WIDTH - 1):
        if FQ_PUZZLE_X0 <= x <= FQ_PUZZLE_X1:
            tile = "fq_puzzle_floor" if x == FQ_BARRIER_X else "fq_obstacle"
        else:
            tile = "fq_floor"
        c.execute(
            "INSERT OR REPLACE INTO forest_quest_tiles "
            "(fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
            (FQ_ID, x, BARRIER_Y, tile),
        )
    print(f"    Done — x=1-{FQ_WIDTH - 2} at y={BARRIER_Y} set")

    # ── Step 2: Edge walls at x=4 and x=16 for y=18-27 ───────────────────────
    print(f"  Setting edge walls (x=4, x=16) for y={FQ_PUZZLE_Y0}-{FQ_PUZZLE_Y1}...")
    edge_xs = (FQ_PUZZLE_X0 - 1, FQ_PUZZLE_X1 + 1)  # (4, 16)
    for y in range(FQ_PUZZLE_Y0, FQ_PUZZLE_Y1 + 1):
        for x in edge_xs:
            c.execute(
                "INSERT OR REPLACE INTO forest_quest_tiles "
                "(fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
                (FQ_ID, x, y, "fq_wall"),
            )
    print(f"    Done — {2 * (FQ_PUZZLE_Y1 - FQ_PUZZLE_Y0 + 1)} edge-wall tiles written")

    db.commit()

    # ── Step 3: Re-run sokoban variant migration ──────────────────────────────
    # (resets obstacles, log positions, ford tiles, solved flag to a fresh variant)
    print("\n  Running sokoban variant migration...")
    variant = random.choice(FQ_PUZZLE_VARIANTS)
    print(f"  Chosen variant: {variant['name']!r}")

    # Normalise all puzzle-area cells to fq_puzzle_floor first
    all_puzzle_cells = [
        (FQ_ID, x, y, "fq_puzzle_floor")
        for y in range(FQ_PUZZLE_Y0, FQ_PUZZLE_Y1 + 1)
        for x in range(FQ_PUZZLE_X0, FQ_PUZZLE_X1 + 1)
    ]
    c.executemany(
        "INSERT OR IGNORE INTO forest_quest_tiles "
        "(fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        all_puzzle_cells,
    )
    c.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_puzzle_floor' "
        "WHERE fq_id=? AND tile_type='fq_obstacle' "
        "AND local_y BETWEEN ? AND ?",
        (FQ_ID, FQ_PUZZLE_Y0, FQ_PUZZLE_Y1),
    )

    # Stamp new obstacle tiles
    new_obs = [(FQ_ID, ox, oy, "fq_obstacle") for (ox, oy) in variant["obstacles"]]
    c.executemany(
        "INSERT OR REPLACE INTO forest_quest_tiles "
        "(fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        new_obs,
    )
    print(f"    {len(new_obs)} obstacle tiles placed")

    # Reset log positions
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
    print(f"    Log A → {variant['log_a']},  Log B → {variant['log_b']}")

    # Old fq_log tiles back to fq_puzzle_floor
    c.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_puzzle_floor' "
        "WHERE fq_id=? AND tile_type='fq_log' "
        "AND local_y BETWEEN ? AND ?",
        (FQ_ID, FQ_PUZZLE_Y0, FQ_PUZZLE_Y1),
    )

    # Clear ford tiles
    c.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_stream' "
        "WHERE fq_id=? AND tile_type='fq_stream_ford' "
        "AND local_y BETWEEN ? AND ?",
        (FQ_ID, FQ_STREAM_Y, FQ_STREAM_Y2),
    )

    # Clear solved flag
    c.execute("UPDATE forest_quest_areas SET solved=0 WHERE fq_id=?", (FQ_ID,))

    db.commit()
    db.close()
    print(f"\nMigration complete.")
    print(f"  Barrier row at y={BARRIER_Y}: obstacles x=5-9,11-15; cutaway at x=10")
    print(f"  Edge walls: x=4 and x=16 for y={FQ_PUZZLE_Y0}-{FQ_PUZZLE_Y1}")
    print(f"  Variant: {variant['name']!r}")


if __name__ == "__main__":
    main()
