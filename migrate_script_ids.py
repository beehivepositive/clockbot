"""One-off: shift every script ID down so the lowest becomes 1 (2->1, 3->2, ...).

Updates the scripts table, ratings references, renames the on-disk image files,
rewrites the stored image paths, and resets the AUTOINCREMENT counter. Backs up
the DB first. Run once, then delete.

    ./venv/bin/python migrate_script_ids.py
"""
import os
import shutil
import sqlite3

BASE = "/home/discord-bot" if os.path.isdir("/home/discord-bot") else "."
DB = os.path.join(BASE, "botc_scripts.db")
IMG_DIR = os.path.join(BASE, "script_data")


def main():
    shutil.copy2(DB, DB + ".bak")
    print(f"backed up -> {DB}.bak")

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute("SELECT * FROM scripts ORDER BY id")]
    if not rows:
        print("no scripts; nothing to do")
        return
    delta = rows[0]["id"] - 1
    if delta <= 0:
        print(f"lowest id is {rows[0]['id']}; no shift needed")
        return
    print(f"shifting all ids down by {delta}")

    def _rename(path, old_id, new_id):
        if not path or not os.path.exists(path):
            return path
        d, base = os.path.split(path)
        assert base.startswith(f"{old_id}_"), f"unexpected filename {base}"
        new_base = f"{new_id}_" + base.split("_", 1)[1]
        new_path = os.path.join(d, new_base)
        os.rename(path, new_path)
        return new_path

    try:
        c.execute("BEGIN")
        # Ascending order so each freed id is available before it's reused.
        for r in rows:
            old, new = r["id"], r["id"] - delta
            new_char = _rename(r["char_path"], old, new)
            new_night = _rename(r["night_path"], old, new)
            c.execute("UPDATE scripts SET id=?, char_path=?, night_path=? WHERE id=?",
                      (new, new_char, new_night, old))
            c.execute("UPDATE ratings SET script_id=? WHERE script_id=?", (new, old))
        new_max = rows[-1]["id"] - delta
        c.execute("UPDATE sqlite_sequence SET seq=? WHERE name='scripts'", (new_max,))
        c.execute("COMMIT")
    except Exception as e:
        c.execute("ROLLBACK")
        print("FAILED, rolled back DB:", e)
        print("Restore images/DB from backup if needed.")
        raise

    print("done. new state:")
    for r in c.execute("SELECT id,name FROM scripts ORDER BY id"):
        print(" ", r["id"], r["name"])
    print("seq:", c.execute("SELECT seq FROM sqlite_sequence WHERE name='scripts'").fetchone()[0])
    print("files:", sorted(os.listdir(IMG_DIR)))


if __name__ == "__main__":
    main()
