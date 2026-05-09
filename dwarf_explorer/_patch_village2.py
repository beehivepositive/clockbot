"""Patch config.py: add new village NPCs, notice board, mill, house furnishings."""
import re

with open("dwarf_explorer/config.py", "rb") as f:
    raw = f.read()
if raw[:3] == b"\xef\xbb\xbf":
    raw = raw[3:]
data = raw.decode("utf-8")

# ── 1. VILLAGE_EMOJI: add vil_villager, vil_guard, vil_notice_board, vil_mill ──
old = '    "vil_elder":        "\\U0001F9D3",        # 🧓  village elder NPC (quest giver)'
new = (
    '    "vil_elder":        "\\U0001F9D3",        # 🧓  village elder NPC (quest giver)\n'
    '    "vil_villager":     "\\U0001F9D1",        # 🧑  walking villager NPC\n'
    '    "vil_guard":        "\\U0001F482",        # 💂  guard NPC\n'
    '    "vil_notice_board": "\\U0001F4CB",        # 📋  outdoor bounty/notice board\n'
    '    "vil_mill":         "\\u2699\\uFE0F",      # ⚙️  grain mill'
)
assert old in data, "VILLAGE_EMOJI anchor not found"
data = data.replace(old, new, 1)

# ── 2. BUILDING_EMOJI: add house furnishings and mill tiles after hospital block ──
old = '    # Player-house chests'
new = (
    '    # House furnishings (also used by mil/other interiors)\n'
    '    "b_chest":          "\\U0001F4E6",        # 📦  small storage chest\n'
    '    "b_resident":       "\\U0001F9D3",        # 🧓  house resident NPC\n'
    '    "b_pet":            "\\U0001F431",        # 🐱  house cat\n'
    '    # Mill unique\n'
    '    "b_millstone":      "\\U0001FAA8",        # 🪨  millstone / grinder\n'
    '    "b_miller_npc":     "\\U0001F9D1",        # 🧑  miller NPC\n'
    '    "b_grain_sack":     "\\U0001F6F1",        # 🛱  grain sack (drum shape)\n'
    '    # Player-house chests'
)
assert old in data, "BUILDING_EMOJI anchor not found"
data = data.replace(old, new, 1)

# ── 3. VILLAGE_WALKABLE: add new outdoor tiles ──
old = '    "vil_dock",  # harbor-village boarding point — walkable, triggers ocean'
new = (
    '    "vil_dock",  # harbor-village boarding point — walkable, triggers ocean\n'
    '    "vil_villager",     # walkable NPC (interact for gossip)\n'
    '    "vil_guard",        # walkable NPC (interact for guard dialogue)\n'
    '    "vil_notice_board", # outdoor bounty board — walkable, interact to see quests\n'
    '    "vil_mill",         # enterable mill building'
)
assert old in data, "VILLAGE_WALKABLE anchor not found"
data = data.replace(old, new, 1)

# ── 4. BUILDING_WALKABLE: add new tiles ──
old = '    "b_anvil", "b_chair", "b_bookshelf", "b_candle",'
new = (
    '    "b_anvil", "b_chair", "b_bookshelf", "b_candle",\n'
    '    "b_chest", "b_resident", "b_pet",\n'
    '    "b_millstone", "b_miller_npc", "b_grain_sack",'
)
assert old in data, "BUILDING_WALKABLE anchor not found"
data = data.replace(old, new, 1)

# ── 5. _CANONICAL_BUILDING_TYPE in villages.py handled separately ──

# ── 6. Add MILL_MENU constant after TAVERN_MENU ──
old = '# Hospital heal cost: gold per missing HP (minimum 5 gold)'
new = (
    '# Mill food menu (cheaper than tavern, basic staples)\n'
    'MILL_MENU = [\n'
    '    {"id": "bread",     "name": "Bread",     "price": 3,  "hp": 10},\n'
    '    {"id": "meat_stew", "name": "Meat Stew", "price": 8,  "hp": 20},\n'
    '    {"id": "healing_herb", "name": "Healing Herb", "price": 12, "hp": 0},\n'
    ']\n'
    '\n'
    '# Hospital heal cost: gold per missing HP (minimum 5 gold)'
)
assert old in data, "MILL_MENU anchor not found"
data = data.replace(old, new, 1)

with open("dwarf_explorer/config.py", "wb") as f:
    f.write(data.encode("utf-8"))

print("config.py patched OK")
