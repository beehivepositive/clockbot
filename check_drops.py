import sqlite3
db = sqlite3.connect('/home/discord-bot/dwarf_explorer/game.db')
db.row_factory = sqlite3.Row

sql = "SELECT gi.world_x, gi.world_y, gi.item_id, gi.quantity FROM ground_items gi LEFT JOIN tile_overrides t ON gi.world_x=t.world_x AND gi.world_y=t.world_y WHERE t.world_x IS NULL AND gi.is_drop=1"
rows = db.execute(sql).fetchall()
print("ORPHANED (no drop_box tile):", len(rows))
for r in rows:
    print("  (%d,%d) %s x%d" % (r['world_x'], r['world_y'], r['item_id'], r['quantity']))

boxes = db.execute("SELECT world_x, world_y FROM tile_overrides WHERE tile_type='drop_box'").fetchall()
print("Active drop boxes:", len(boxes))
for b in boxes:
    print("  (%d,%d)" % (b['world_x'], b['world_y']))
