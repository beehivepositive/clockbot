"""
One-shot migration: rebuild the post-stream corridor (y=31-40) and shop
section (y=41-53) for fq_id=1.

Changes applied:
  - y=31-40  post-stream corridor narrowed to x=9-11 (was x=6-14)
  - y=41-53  shop section: 3-wide corridor (x=9-11) + 2-wide wall (x=7-8) +
             side room (x=3-6, y=44-50) + 1-tile opening at y=47 (x=7-8 floor)
             + shopkeeper stays at (6, 47)

Run on the server with inline Python (hardcoded DB path):
  python3 - <<'EOF'
  ...see deploy command in session notes...
  EOF
"""
import sqlite3
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "dwarf_explorer", "data", "shared.db")
sys.path.insert(0, _HERE)

FQ_ID = 1
Y_MIN = 31
Y_MAX = 53


def main():
    print(f"Connecting to {DB_PATH}")
    db = sqlite3.connect(DB_PATH)
    c  = db.cursor()

    from dwarf_explorer.world.forest_quest import _tile_for as _tf
    from dwarf_explorer.config import FQ_WIDTH

    c.execute(
        "DELETE FROM forest_quest_tiles "
        "WHERE fq_id=? AND local_y BETWEEN ? AND ?",
        (FQ_ID, Y_MIN, Y_MAX),
    )
    print(f"  Deleted {c.rowcount} old tiles (y={Y_MIN}–{Y_MAX})")

    new_tiles = []
    for y in range(Y_MIN, Y_MAX + 1):
        for x in range(FQ_WIDTH):
            t = _tf(x, y, set())
            new_tiles.append((FQ_ID, x, y, t))

    c.executemany(
        "INSERT INTO forest_quest_tiles (fq_id, local_x, local_y, tile_type) "
        "VALUES (?,?,?,?)",
        new_tiles,
    )
    print(f"  Inserted {len(new_tiles)} new tiles (y={Y_MIN}–{Y_MAX})")

    db.commit()
    db.close()
    print("Migration complete (post-stream + shop layout v2)")


if __name__ == "__main__":
    main()
