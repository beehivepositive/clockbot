"""Remove vil_well quest trigger from handle_interact."""
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

with open(r'C:\ClaudeCode\dwarf_explorer\ui\game_view.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = (
    '        elif vtile.terrain == "vil_well":\n'
    '            # Village elder / notice board — offer quest pool\n'
    '            from dwarf_explorer.game.quests import get_or_refresh_village_pool, get_or_refresh_bounty_pool\n'
    '            village_pool = await get_or_refresh_village_pool(db, player.village_id, seed)\n'
    '            bounty_pool  = await get_or_refresh_bounty_pool(db, seed)\n'
    '            combined_pool = village_pool + bounty_pool\n'
    '            if combined_pool:\n'
    '                await handle_open_quest_pool(\n'
    '                    interaction, guild_id, user_id,\n'
    '                    pool=combined_pool,\n'
    '                    source_label="Village Notice Board",\n'
    '                    source_type="village_npc",\n'
    '                )\n'
    '                return\n'
    '            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)\n'
    '            content = render_grid(grid, player,\n'
    '                "⛲ The notice board is bare. Check back tomorrow for new work.")\n'
)
new = (
    '        elif vtile.terrain == "vil_well":\n'
    '            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)\n'
    '            content = render_grid(grid, player, "⛲ The well gurgles softly.")\n'
)

if old in content:
    content = content.replace(old, new, 1)
    with open(r'C:\ClaudeCode\dwarf_explorer\ui\game_view.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK - vil_well quest trigger removed")
else:
    # Fallback: search for the key line
    idx = content.find('elif vtile.terrain == "vil_well"')
    print(f"Pattern not found. vil_well at idx={idx}")
    if idx > 0:
        import sys as _sys
        _sys.stderr.buffer.write(repr(content[idx:idx+600]).encode('ascii', errors='replace') + b'\n')
