"""One-off: fix script created_at/updated_at that were stored as UTC dates.

The old code used naive datetime.now() on a UTC server, so evening-Central actions
got tomorrow's date. The image files' modification times record the actual moment,
so we recompute the dates in US Central:
  * never-updated rows: created_at = earliest image mtime (that's the creation time)
  * updated rows:        updated_at = latest image mtime (the update time)
Backs up the DB first. Run once, then delete.
"""
import os
import shutil
import sqlite3
import datetime
import pytz

CST = pytz.timezone("America/Chicago")
BASE = "/home/discord-bot" if os.path.isdir("/home/discord-bot") else "."
DB = os.path.join(BASE, "botc_scripts.db")


def _cent_date(ts):
    return datetime.datetime.fromtimestamp(ts, CST).strftime("%Y-%m-%d")


def main():
    shutil.copy2(DB, DB + ".tzbak")
    print(f"backed up -> {DB}.tzbak")
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute("SELECT * FROM scripts")]
    changes = []
    for r in rows:
        files = [p for p in (r["char_path"], r["night_path"]) if p and os.path.exists(p)]
        if not files:
            continue
        mtimes = [os.path.getmtime(p) for p in files]
        if r["updated_at"] is None:
            new = _cent_date(min(mtimes))
            if new != r["created_at"]:
                c.execute("UPDATE scripts SET created_at=? WHERE id=?", (new, r["id"]))
                changes.append(f"id={r['id']} {r['name']!r} created {r['created_at']} -> {new}")
        else:
            new = _cent_date(max(mtimes))
            if new != r["updated_at"]:
                c.execute("UPDATE scripts SET updated_at=? WHERE id=?", (new, r["id"]))
                changes.append(f"id={r['id']} {r['name']!r} updated {r['updated_at']} -> {new}")
    c.commit()
    print("changes:")
    print("\n".join("  " + x for x in changes) if changes else "  none")


if __name__ == "__main__":
    main()
