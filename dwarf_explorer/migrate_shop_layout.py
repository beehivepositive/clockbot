"""
One-shot migration: rebuild forest_quest_tiles for y=41-53 (shop section).

Replaces the old 7-wide corridor+alcove with a narrow 3-wide corridor and
left side room for the shopkeeper (new position: x=6, y=47).

Run on server:
  cd /home/discord-bot && python3 dwarf_explorer/migrate_shop_layout.py
"""
import sqlite3, sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "dwarf_explorer", "data", "shared.db")
sys.path.insert(0, _HERE)
FQ_ID  = 1
Y_MIN  = 41
Y_MAX  = 53


def main():
    print(f"Connecting to {DB_PATH}")
    db = sqlite3.connect(DB_PATH)
    c  = db.cursor()

    from dwarf_explorer.world.forest_quest import _tile_for as _tf
    from dwarf_explorer.config import FQ_WIDTH

    c.execute(
        "DELETE FROM forest_quest_tiles WHERE fq_id=? AND local_y BETWEEN ? AND ?",
        (FQ_ID, Y_MIN, Y_MAX),
    )
    print(f"  Deleted {c.rowcount} old tiles (y={Y_MIN}-{Y_MAX})")

    new_tiles = [
        (FQ_ID, x, y, _tf(x, y, set()))
        for y in range(Y_MIN, Y_MAX + 1)
        for x in range(FQ_WIDTH)
    ]
    c.executemany(
        "INSERT INTO forest_quest_tiles (fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        new_tiles,
    )
    print(f"  Inserted {len(new_tiles)} new tiles (y={Y_MIN}-{Y_MAX})")

    db.commit()
    db.close()
    print("Migration complete (shop layout v2)")


if __name__ == "__main__":
    main()
