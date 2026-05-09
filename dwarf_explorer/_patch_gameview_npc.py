"""Patch _compute_context_labels early return and _game_view unpacking."""
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

with open(r'C:\ClaudeCode\dwarf_explorer\ui\game_view.py', 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. Fix early return in _compute_context_labels (missing npc values)
old1 = '    if not grid or len(grid) <= vc:\n        return center_label, center_enabled, action_label, action_enabled, edit_enabled\n'
new1 = '    if not grid or len(grid) <= vc:\n        return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False\n'
if old1 in content:
    content = content.replace(old1, new1, 1)
    changes += 1
    print("Fix 1: early return OK")
else:
    print("Fix 1: NOT FOUND")

# 2. Fix _game_view unpack (5 values -> 7)
old2 = (
    '    center_label, center_enabled = "", False\n'
    '    action_label, action_enabled = "", False\n'
    '    edit_enabled = False\n'
    '\n'
    '    if grid is not None:\n'
    '        hand_items: set[str] = set()\n'
    '        if player.hand_1:\n'
    '            hand_items.add(player.hand_1)\n'
    '        if player.hand_2:\n'
    '            hand_items.add(player.hand_2)\n'
    '        center_label, center_enabled, action_label, action_enabled, edit_enabled = \\\n'
    '            _compute_context_labels(grid, player, hand_items)\n'
    '\n'
    '    return GameView(guild_id, user_id,\n'
    '                    boots_equipped=(player.boots is not None),\n'
    '                    sprinting=player.sprinting,\n'
    '                    mine_dirs=mine_dirs,\n'
    '                    center_label=center_label,\n'
    '                    center_enabled=center_enabled,\n'
    '                    action_label=action_label,\n'
    '                    action_enabled=action_enabled,\n'
    '                    edit_enabled=edit_enabled)'
)
new2 = (
    '    center_label, center_enabled = "", False\n'
    '    action_label, action_enabled = "", False\n'
    '    edit_enabled = False\n'
    '    npc_label, npc_enabled = "", False\n'
    '\n'
    '    if grid is not None:\n'
    '        hand_items: set[str] = set()\n'
    '        if player.hand_1:\n'
    '            hand_items.add(player.hand_1)\n'
    '        if player.hand_2:\n'
    '            hand_items.add(player.hand_2)\n'
    '        center_label, center_enabled, action_label, action_enabled, edit_enabled, npc_label, npc_enabled = \\\n'
    '            _compute_context_labels(grid, player, hand_items)\n'
    '\n'
    '    return GameView(guild_id, user_id,\n'
    '                    boots_equipped=(player.boots is not None),\n'
    '                    sprinting=player.sprinting,\n'
    '                    mine_dirs=mine_dirs,\n'
    '                    center_label=center_label,\n'
    '                    center_enabled=center_enabled,\n'
    '                    action_label=action_label,\n'
    '                    action_enabled=action_enabled,\n'
    '                    edit_enabled=edit_enabled,\n'
    '                    npc_label=npc_label,\n'
    '                    npc_enabled=npc_enabled)'
)
if old2 in content:
    content = content.replace(old2, new2, 1)
    changes += 1
    print("Fix 2: _game_view unpack OK")
else:
    print("Fix 2: NOT FOUND - trying to locate...")
    idx = content.find('edit_enabled = False\n\n    if grid is not None:')
    print(f"  locate idx={idx}")

with open(r'C:\ClaudeCode\dwarf_explorer\ui\game_view.py', 'w', encoding='utf-8') as f:
    f.write(content)
print(f"Done. {changes}/2 changes applied")
