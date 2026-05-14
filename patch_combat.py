import sys

path = r"C:\ClaudeCode\dwarf_explorer\ui\game_view.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# === 1. Fix CombatView signature to add enemy_type param ===
old_sig = (
    '    def __init__(self, guild_id: int, user_id: int, trapped: bool = False,\n'
    '                 moves_left: int = COMBAT_MOVES_DEFAULT):\n'
    '        super().__init__(timeout=None)\n'
    '        gid, uid = guild_id, user_id\n'
    '        disabled = (moves_left <= 0)\n'
    '        attack_disabled = disabled or trapped  # can\'t attack while trapped'
)
new_sig = (
    '    def __init__(self, guild_id: int, user_id: int, trapped: bool = False,\n'
    '                 moves_left: int = COMBAT_MOVES_DEFAULT, enemy_type: str = ""):\n'
    '        super().__init__(timeout=None)\n'
    '        gid, uid = guild_id, user_id\n'
    '        disabled = (moves_left <= 0)\n'
    '        attack_disabled = disabled or trapped  # can\'t attack while trapped'
)

# Make sure we only hit the CombatView one (not any other class)
cv_idx = content.find('class CombatView')
if cv_idx == -1:
    print("ERROR: CombatView class not found"); sys.exit(1)

# Replace only within CombatView area
end_of_cv = content.find('\nclass ', cv_idx + 1)
cv_body = content[cv_idx:end_of_cv]
if old_sig in cv_body:
    cv_body = cv_body.replace(old_sig, new_sig, 1)
    content = content[:cv_idx] + cv_body + content[end_of_cv:]
    print("OK: signature updated")
elif 'enemy_type: str = ""' in cv_body:
    print("OK: signature already updated, skipping")
else:
    print("ERROR: signature pattern not found in CombatView")
    print("CombatView body start:", repr(cv_body[:300]))
    sys.exit(1)

# === 2. Row 2 bribe button ===
old_row2 = (
    '        # Row 2: ↙ ↓ ↘ spacer spacer\n'
    '        for emoji, action in [("↙", "c_downleft"), ("⬇️", "c_down"), ("↘", "c_downright")]:\n'
    '            self.add_item(discord.ui.Button(\n'
    '                style=discord.ButtonStyle.primary,\n'
    '                label=emoji, disabled=disabled,\n'
    '                custom_id=_custom_id(gid, uid, action), row=2,\n'
    '            ))\n'
    '        self.add_item(discord.ui.Button(\n'
    '            style=discord.ButtonStyle.secondary,\n'
    '            label="\\u200b", disabled=True,\n'
    '            custom_id=_custom_id(gid, uid, "csp0"), row=2,\n'
    '        ))\n'
    '        self.add_item(discord.ui.Button(\n'
    '            style=discord.ButtonStyle.secondary,\n'
    '            label="\\u200b", disabled=True,\n'
    '            custom_id=_custom_id(gid, uid, "csp_a"), row=2,\n'
    '        ))'
)
new_row2 = (
    '        # Row 2: ↙ ↓ ↘ [\U0001f4b0 Bribe if bandit] spacer\n'
    '        for emoji, action in [("↙", "c_downleft"), ("⬇️", "c_down"), ("↘", "c_downright")]:\n'
    '            self.add_item(discord.ui.Button(\n'
    '                style=discord.ButtonStyle.primary,\n'
    '                label=emoji, disabled=disabled,\n'
    '                custom_id=_custom_id(gid, uid, action), row=2,\n'
    '            ))\n'
    '        if enemy_type == "bandit":\n'
    '            self.add_item(discord.ui.Button(\n'
    '                style=discord.ButtonStyle.success,\n'
    '                label="\U0001f4b0 Bribe", disabled=disabled,\n'
    '                custom_id=_custom_id(gid, uid, "c_bribe"), row=2,\n'
    '            ))\n'
    '        else:\n'
    '            self.add_item(discord.ui.Button(\n'
    '                style=discord.ButtonStyle.secondary,\n'
    '                label="\\u200b", disabled=True,\n'
    '                custom_id=_custom_id(gid, uid, "csp0"), row=2,\n'
    '            ))\n'
    '        self.add_item(discord.ui.Button(\n'
    '            style=discord.ButtonStyle.secondary,\n'
    '            label="\\u200b", disabled=True,\n'
    '            custom_id=_custom_id(gid, uid, "csp_a"), row=2,\n'
    '        ))'
)

if old_row2 in content:
    content = content.replace(old_row2, new_row2, 1)
    print("OK: Row 2 bribe button added")
elif '"\U0001f4b0 Bribe"' in content:
    print("OK: bribe button already present, skipping")
else:
    print("ERROR: Row 2 old_string not found — debug:")
    # show what's in the CombatView body around row 2
    cv_idx2 = content.find('class CombatView')
    end2 = content.find('\nclass ', cv_idx2 + 1)
    cv2 = content[cv_idx2:end2]
    r2_idx = cv2.find('Row 2')
    if r2_idx >= 0:
        print("Row 2 section:", repr(cv2[r2_idx:r2_idx+200]))
    else:
        print("'Row 2' not found in CombatView body")
    sys.exit(1)

# === 3. Update _combat_view helper to pass enemy_type ===
old_cv_helper = (
    'def _combat_view(guild_id: int, user_id: int, arena: dict, player) -> CombatView:\n'
    '    return CombatView(guild_id, user_id,\n'
    '                      trapped=arena["player_trapped"],\n'
    '                      moves_left=player.combat_moves_left)'
)
new_cv_helper = (
    'def _combat_view(guild_id: int, user_id: int, arena: dict, player) -> CombatView:\n'
    '    return CombatView(guild_id, user_id,\n'
    '                      trapped=arena["player_trapped"],\n'
    '                      moves_left=player.combat_moves_left,\n'
    '                      enemy_type=player.combat_enemy_type or "")'
)
if old_cv_helper in content:
    content = content.replace(old_cv_helper, new_cv_helper, 1)
    print("OK: _combat_view helper updated")
elif 'enemy_type=player.combat_enemy_type' in content:
    print("OK: _combat_view helper already updated, skipping")
else:
    print("ERROR: _combat_view helper not found")
    sys.exit(1)

# === 4. Add BribeModal class before ConsumablesView ===
anchor = 'class ConsumablesView(discord.ui.View):\n    """Combat food/consumables menu'
if anchor not in content:
    print("ERROR: ConsumablesView anchor not found"); sys.exit(1)

if 'class BribeModal' not in content:
    bribe_modal = (
        'class BribeModal(discord.ui.Modal, title="Bribe the Bandit"):\n'
        '    """Modal for entering a bribe amount when fighting a bandit."""\n'
        '    amount = discord.ui.TextInput(\n'
        '        label="Coins to offer",\n'
        '        placeholder="1 coin = 5%  |  50 coins = 100%  |  more = always 100%",\n'
        '        min_length=1,\n'
        '        max_length=6,\n'
        '    )\n'
        '\n'
        '    def __init__(self, guild_id: int, user_id: int):\n'
        '        super().__init__()\n'
        '        self._gid = guild_id\n'
        '        self._uid = user_id\n'
        '\n'
        '    async def on_submit(self, interaction: discord.Interaction):  # type: ignore[override]\n'
        '        await handle_bribe_submit(interaction, self._gid, self._uid, self.amount.value)\n'
        '\n'
        '\n'
    )
    insert_pos = content.find(anchor)
    content = content[:insert_pos] + bribe_modal + content[insert_pos:]
    print("OK: BribeModal class inserted")
else:
    print("OK: BribeModal already present, skipping")

# === 5. Add bandit dagger drop in _finish_combat ===
old_drop = '    # Sky enemy drops on victory\n    if won and player.combat_enemy_type == "wind_wisp":'
new_drop = (
    '    # Bandit dagger drop on victory (~25%)\n'
    '    if won and player.combat_enemy_type == "bandit":\n'
    '        drop_rng = _random.Random(hash((user_id, player.world_x, player.world_y, "bandit_drop")))\n'
    '        if drop_rng.random() < 0.25:\n'
    '            await add_to_inventory(db, user_id, "dagger", 1)\n'
    '            extra_msg += " \U0001f5e1️ The bandit dropped a **Dagger**!"\n'
    '\n'
    '    # Sky enemy drops on victory\n'
    '    if won and player.combat_enemy_type == "wind_wisp":'
)
if old_drop in content:
    content = content.replace(old_drop, new_drop, 1)
    print("OK: bandit drop added")
elif 'bandit_drop' in content:
    print("OK: bandit drop already present, skipping")
else:
    print("ERROR: bandit drop anchor not found")
    sys.exit(1)

# === 6. Add handle_bribe and handle_bribe_submit after handle_combat_flee ===
flee_anchor = 'async def handle_combat_flee(\n    interaction: discord.Interaction, guild_id: int, user_id: int\n) -> None:'
if flee_anchor not in content:
    print("ERROR: handle_combat_flee anchor not found"); sys.exit(1)

if 'async def handle_bribe(' not in content:
    flee_idx = content.find(flee_anchor)
    next_async = content.find('\nasync def ', flee_idx + 1)

    bribe_handlers = (
        '\n'
        '\nasync def handle_bribe(\n'
        '    interaction: discord.Interaction, guild_id: int, user_id: int\n'
        ') -> None:\n'
        '    """Show the bribe modal when fighting a bandit."""\n'
        '    result = await _load_combat(interaction, guild_id, user_id)\n'
        '    if result is None:\n'
        '        return\n'
        '    _db, player, _arena = result\n'
        '    if player.combat_enemy_type != "bandit":\n'
        '        await interaction.response.send_message("You can only bribe bandits!", ephemeral=True)\n'
        '        return\n'
        '    await interaction.response.send_modal(BribeModal(guild_id, user_id))\n'
        '\n'
        '\nasync def handle_bribe_submit(\n'
        '    interaction: discord.Interaction, guild_id: int, user_id: int, amount_str: str\n'
        ') -> None:\n'
        '    """Process a bribe attempt after the player submits the modal."""\n'
        '    result = await _load_combat(interaction, guild_id, user_id)\n'
        '    if result is None:\n'
        '        return\n'
        '    db, player, arena = result\n'
        '\n'
        '    try:\n'
        '        amount = int(amount_str.strip())\n'
        '    except ValueError:\n'
        '        await interaction.response.send_message("Please enter a whole number.", ephemeral=True)\n'
        '        return\n'
        '\n'
        '    if amount <= 0:\n'
        '        await interaction.response.send_message("Must offer at least 1 coin.", ephemeral=True)\n'
        '        return\n'
        '    if amount > player.gold:\n'
        '        await interaction.response.send_message(\n'
        '            f"You only have **{player.gold}** coins!", ephemeral=True\n'
        '        )\n'
        '        return\n'
        '\n'
        '    # Deduct coins and calculate success chance (5% @ 1 coin, 100% @ 50+, linear)\n'
        '    player.gold -= amount\n'
        '    chance = min(1.0, 0.05 + (amount - 1) * (0.95 / 49))\n'
        '    pct = int(chance * 100)\n'
        '\n'
        '    bribe_rng = _random.Random()  # non-deterministic — bribe outcome should not be predictable\n'
        '    if bribe_rng.random() < chance:\n'
        '        msg = (\n'
        '            f"\U0001f4b0 You offered **{amount} coin{\'s\' if amount != 1 else \'\'}** "\n'
        '            f"({pct}% chance) — the bandit pockets the gold and melts back into "\n'
        '            f"the shadows. You escape unharmed!"\n'
        '        )\n'
        '        arena["combat_log"].append(msg)\n'
        '        content, view = await _finish_combat(db, guild_id, user_id, player, arena,\n'
        '                                             " ".join(arena["combat_log"][-3:]))\n'
        '    else:\n'
        '        msg = (\n'
        '            f"\U0001f4b8 The bandit snatches your **{amount} coin{\'s\' if amount != 1 else \'\'}** "\n'
        '            f"but attacks anyway! ({pct}% chance — failed)"\n'
        '        )\n'
        '        arena["combat_log"].append(msg)\n'
        '        await save_combat_state(db, user_id, player)\n'
        '        from dwarf_explorer.game.combat import render_arena\n'
        '        render_content = render_arena(arena, player)\n'
        '        view = _combat_view(guild_id, user_id, arena, player)\n'
        '        await interaction.response.edit_message(embed=_embed(render_content), content=None, view=view)\n'
        '        return\n'
        '\n'
        '    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)\n'
        '\n'
    )
    content = content[:next_async] + bribe_handlers + content[next_async:]
    print("OK: handle_bribe and handle_bribe_submit inserted")
else:
    print("OK: handle_bribe already present, skipping")

with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(content)
print("All done.")
