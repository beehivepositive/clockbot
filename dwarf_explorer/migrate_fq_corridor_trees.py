"""
One-shot migration: stamp corridor-tree tiles (fq_wall) into the existing
Forest Quest corridor (y 2-14, x 8-12, excluding centre x=10) using the same
deterministic hash as _tile_for so the live zone matches freshly generated ones.

Usage (run on server after git pull):
    cd /home/discord-bot && python3 -m dwarf_explorer.migrate_fq_corridor_trees

Safe to re-run: uses UPDATE WHERE tile_type='fq_floor', so running it again is a no-op.
"""
from __future__ import annotations

import os
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DB_PATH = os.path.join(_HERE, "data", "shared.db")
sys.path.insert(0, _ROOT)

# Corridor geometry (must stay in sync with config.py)
FQ_CORRIDOR_X0 = 8
FQ_CORRIDOR_X1 = 12
FQ_CORRIDOR_Y0 = 0    # y=0..1 kept clear (entry/exit approach)
FQ_CORRIDOR_Y1 = 15
FQ_ENTRY_X = 10       # centre column — always clear


def _is_tree(x: int, y: int) -> bool:
    """Return True for positions that should hold a corridor tree tile."""
    if x == FQ_ENTRY_X:
        return False       # centre path always clear
    if y < 2:
        return False       # keep entry/exit approach open
    _ch = (x * 7919 + y * 3571) & 0xFFFF_FFFF
    return _ch % 4 == 0


def main() -> None:
    print(f"Connecting to {DB_PATH}")
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()

    # Fetch all active FQ zone IDs
    fq_ids = [row[0] for row in c.execute("SELECT fq_id FROM forest_quest_areas").fetchall()]
    if not fq_ids:
        print("No forest quest zones found — nothing to do.")
        db.close()
        return

    total_updated = 0
    for fq_id in fq_ids:
        tree_positions = [
            (fq_id, x, y)
            for y in range(FQ_CORRIDOR_Y0 + 2, FQ_CORRIDOR_Y1 + 1)
            for x in range(FQ_CORRIDOR_X0, FQ_CORRIDOR_X1 + 1)
            if _is_tree(x, y)
        ]
        newly_set = 0
        for params in tree_positions:
            c.execute(
                "UPDATE forest_quest_tiles "
                "SET tile_type='fq_wall' "
                "WHERE fq_id=? AND local_x=? AND local_y=? AND tile_type='fq_floor'",
                params,
            )
            newly_set += c.rowcount
        print(
            f"  fq_id={fq_id}: {len(tree_positions)} tree positions total, "
            f"{newly_set} newly converted from fq_floor → fq_wall"
        )
        total_updated += newly_set

    db.commit()
    db.close()
    print(f"Migration complete — {total_updated} corridor tree positions processed across {len(fq_ids)} zone(s).")


if __name__ == "__main__":
    main()
