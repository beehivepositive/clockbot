"""Patch GameView Row 3 to add NPC quest button."""
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

with open(r'C:\ClaudeCode\dwarf_explorer\ui\game_view.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the sp5_btn definition and surrounding context to do a targeted replacement
idx = content.find('sp5_btn  = discord.ui.Button(')
if idx < 0:
    print("ERROR: sp5_btn not found")
    sys.exit(1)

# Find the closing self.add_item(btn) after sp5_btn
end_marker = '            self.add_item(btn)'
end_idx = content.find(end_marker, idx)
if end_idx < 0:
    print("ERROR: end marker not found")
    sys.exit(1)
end_idx += len(end_marker)

old_section = content[idx:end_idx]
print("OLD SECTION:")
print(repr(old_section[:200]))

# Build the new section
new_section = (
    'sp5_btn  = discord.ui.Button(\n'
    '            style=discord.ButtonStyle.secondary,\n'
    '            label="​", disabled=True,\n'
    '            custom_id=_custom_id(self.guild_id, self.user_id, "sp5"),\n'
    '            row=3,\n'
    '        )\n'
    '        down_btn = self._dir_btn("down", "⬇️", 3, "down" in mine_dirs)\n'
    '        if npc_enabled and npc_label:\n'
    '            npc_btn = discord.ui.Button(\n'
    '                style=discord.ButtonStyle.success,\n'
    '                emoji=npc_label,\n'
    '                custom_id=_custom_id(self.guild_id, self.user_id, "npc_quest"),\n'
    '                row=3,\n'
    '            )\n'
    '        else:\n'
    '            npc_btn = discord.ui.Button(\n'
    '                style=discord.ButtonStyle.secondary,\n'
    '                label="​", disabled=True,\n'
    '                custom_id=_custom_id(self.guild_id, self.user_id, "sp_npc"),\n'
    '                row=3,\n'
    '            )\n'
    '\n'
    '        row0 = [map_btn, inventory_btn, quest_btn, help_btn]\n'
    '        if edit_btn is not None:\n'
    '            row0.append(edit_btn)\n'
    '        for btn in [\n'
    '            *row0,                                   # row 0\n'
    '            sp1_btn, up_btn, action_btn,             # row 1\n'
    '            left_btn, center_btn, right_btn,         # row 2\n'
    '            sp5_btn, down_btn, npc_btn,              # row 3\n'
    '        ]:\n'
    '            self.add_item(btn)'
)

content = content[:idx] + new_section + content[end_idx:]
with open(r'C:\ClaudeCode\dwarf_explorer\ui\game_view.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("OK - Row 3 NPC button added")
