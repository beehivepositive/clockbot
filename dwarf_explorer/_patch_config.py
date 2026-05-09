"""Patch vil_elder into VILLAGE_EMOJI in config.py."""
with open(r'C:\ClaudeCode\dwarf_explorer\config.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '    # Harbor-village specific tiles\n    "vil_water":'
new = '    "vil_elder":        "\\U0001F9D3",        # \U0001F9D3  village elder NPC (quest giver)\n    # Harbor-village specific tiles\n    "vil_water":'

if old in content:
    content = content.replace(old, new, 1)
    with open(r'C:\ClaudeCode\dwarf_explorer\config.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK - vil_elder added")
else:
    print("ERROR - pattern not found")
