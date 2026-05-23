"""
One-shot migration: rebuild the boss approach + chamber + post-boss tiles for the
circular Thornwarden arena (v2 layout, radius-5 circle centred at (10, 63)).

This migration:
  1. Deletes all forest_quest_tiles for fq_id=1 in y-range 54–87
     (old rectangular chamber y=58-79 + surrounding corridor).
  2. Re-inserts them using the current _tile_for() logic from forest_quest.py
     (circular chamber, narrow funnel approach, corrected post-boss start).
  3. If the warden was already defeated, re-stamps the boss chest/door-open tiles
     at the new positions (FQ_BOSS_CHEST_X/Y = 10/62, boss door open at 10/68).
  4. Resets in_fq_boss_combat=0 for any player currently flagged as fighting the
     warden (stale state after the layout change).

Run on the server with:
  cd /home/discord-bot && python3 migrate_chamber.py
"""
import sqlite3
import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "dwarf_explorer", "data", "shared.db")

# Add project root to sys.path so we can import from the package
sys.path.insert(0, _HERE)

FQ_ID = 1
Y_MIN = 54   # start of boss approach
Y_MAX = 87   # end of post-boss corridor


def main():
    print(f"Connecting to {DB_PATH}")
    db = sqlite3.connect(DB_PATH)
    c  = db.cursor()

    # ── Import tile generation logic from the updated package ────────────────
    from dwarf_explorer.world.forest_quest import _tile_for as _tf
    from dwarf_explorer.config import (
        FQ_WIDTH, FQ_BOSS_CHEST_X, FQ_BOSS_CHEST_Y,
        FQ_BOSS_DOOR_X, FQ_BOSS_DOOR_Y,
    )

    # ── 1. Delete old tiles in affected y range ───────────────────────────────
    c.execute(
        "DELETE FROM forest_quest_tiles "
        "WHERE fq_id=? AND local_y BETWEEN ? AND ?",
        (FQ_ID, Y_MIN, Y_MAX),
    )
    print(f"  Deleted {c.rowcount} old tiles (y={Y_MIN}–{Y_MAX})")

    # ── 2. Re-generate tiles using new _tile_for() logic ─────────────────────
    new_tiles = []
    for y in range(Y_MIN, Y_MAX + 1):
        for x in range(FQ_WIDTH):
            t = _tf(x, y, set())   # log_positions not relevant here (no logs in this zone)
            new_tiles.append((FQ_ID, x, y, t))

    c.executemany(
        "INSERT INTO forest_quest_tiles (fq_id, local_x, local_y, tile_type) "
        "VALUES (?,?,?,?)",
        new_tiles,
    )
    print(f"  Inserted {len(new_tiles)} new tiles (y={Y_MIN}–{Y_MAX})")

    # ── 3. If warden was already defeated: re-stamp chest + open door ─────────
    warden_defeated = c.execute(
        "SELECT COUNT(*) FROM players "
        "WHERE fq_quest_stage IN ('warden_defeated','canal_solved','quest_complete')"
    ).fetchone()[0]

    if warden_defeated:
        print(f"  Warden defeated by {warden_defeated} player(s) — stamping chest + open door")
        c.execute(
            "UPDATE forest_quest_tiles SET tile_type='fq_boss_chest' "
            "WHERE fq_id=? AND local_x=? AND local_y=?",
            (FQ_ID, FQ_BOSS_CHEST_X, FQ_BOSS_CHEST_Y),
        )
        c.execute(
            "UPDATE forest_quest_tiles SET tile_type='fq_boss_door_open' "
            "WHERE fq_id=? AND local_x=? AND local_y=?",
            (FQ_ID, FQ_BOSS_DOOR_X, FQ_BOSS_DOOR_Y),
        )
        # Also ensure all warden tiles are marked dead (chamber rebuilt clean)
        c.execute(
            "UPDATE forest_quest_tiles SET tile_type='fq_warden_dead' "
            "WHERE fq_id=? AND tile_type IN "
            "('fq_warden_body','fq_warden_eye_nw','fq_warden_eye_ne',"
            " 'fq_warden_eye_sw','fq_warden_eye_se')",
            (FQ_ID,),
        )
        print(f"    chest at ({FQ_BOSS_CHEST_X}, {FQ_BOSS_CHEST_Y}), door open at ({FQ_BOSS_DOOR_X}, {FQ_BOSS_DOOR_Y})")
    else:
        print("  Warden not yet defeated — no chest/door fixup needed")

    # ── 4. Clear stale boss-combat state ─────────────────────────────────────
    c.execute(
        "UPDATE players SET in_fq_boss_combat=0, fq_boss_eye_opened_at=0.0 "
        "WHERE in_fq_boss_combat=1"
    )
    print(f"  Boss combat state cleared for {c.rowcount} player(s)")

    db.commit()
    db.close()
    print("Migration complete (circular chamber v2)")


if __name__ == "__main__":
    main()
