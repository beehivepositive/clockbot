path = r"C:\ClaudeCode\dwarf_explorer\ui\game_view.py"
with open(path, encoding="utf-8") as f:
    c = f.read()

checks = [
    ('enemy_type: str = ""', "CombatView signature"),
    ("c_bribe", "bribe button custom_id"),
    ('enemy_type == "bandit"', "bandit check in CombatView"),
    ("class BribeModal", "BribeModal class"),
    ("async def handle_bribe(", "handle_bribe function"),
    ("async def handle_bribe_submit(", "handle_bribe_submit function"),
    ("bandit_drop", "bandit drop RNG"),
    ("_enemies, _weights = zip(*mob_table)", "weighted encounter code"),
    ("enemy_type=player.combat_enemy_type", "_combat_view helper"),
    ("enemy_type=enemy_type", "encounter view creation"),
]
for key, label in checks:
    found = key in c
    print(("OK" if found else "MISSING") + ": " + label)
