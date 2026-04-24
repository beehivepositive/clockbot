from __future__ import annotations

import random as _random

import discord

from dwarf_explorer.config import (
    DIRECTIONS, SHOP_CATALOG, EQUIP_BONUSES, ITEM_EQUIP_SLOTS,
    TWO_HANDED_ITEMS, ITEM_SELL_PRICES, CAVE_ENEMY_TYPES, CAVE_CHEST_TYPES,
    CAVE_ENCOUNTER_RATES, CAVE_LEVEL_ENCOUNTER_RATES, ENEMY_STATS, COMBAT_MOVES_DEFAULT,
    POUCH_SIZES, SURFACE_ENCOUNTER_MOBS,
)
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world,
    update_player_position, update_player_message,
    update_player_cave_state,
    update_player_village_state,
    update_player_house_state,
    update_player_sprint,
    update_player_stats,
    save_combat_state,
    clear_combat_state,
    get_cave_entrance_exit,
    equip_item, unequip_item,
    get_inventory,
    add_to_inventory,
    remove_from_inventory,
    get_bank_items,
    bank_deposit,
    bank_withdraw,
    set_tile_override,
    get_or_create_chest,
    get_chest_items,
    add_to_chest,
    remove_from_chest,
)
from dwarf_explorer.game.combat import (
    build_arena_from_viewport,
    action_move, action_attack, action_flee, action_use_potion,
    resolve_enemy_turn, apply_victory, apply_death_reset,
    render_arena, ARENA_SIZE,
)
from dwarf_explorer.world.generator import load_viewport, load_single_tile
from dwarf_explorer.world.caves import get_or_create_cave, load_cave_viewport, load_cave_single_tile, populate_chest_loot
from dwarf_explorer.world.villages import (
    get_or_create_village, get_building_at,
    load_village_viewport, load_village_single_tile,
    load_building_viewport, load_building_single_tile,
)
from dwarf_explorer.game.player import Player, can_move, can_move_village, can_move_building
from dwarf_explorer.game.renderer import (
    render_grid, render_inventory, render_bank, render_shop, render_chest,
)

# ── In-memory UI state (transient per user) ───────────────────────────────────
# {user_id: {"type": str, "selected": int, "bank_view": str, "mode": str}}
_ui_state: dict[int, dict] = {}


def _embed(content: str) -> discord.Embed:
    """Wrap game content in an embed to bypass Discord's 2000-char content limit."""
    return discord.Embed(description=content)


def _custom_id(guild_id: int, user_id: int, action: str) -> str:
    return f"dex:{guild_id}:{user_id}:{action}"


class GameView(discord.ui.View):
    """Main game view.  Shows sprint button when boots are equipped."""

    def __init__(self, guild_id: int, user_id: int, boots_equipped: bool = False,
                 sprinting: bool = False, mine_dirs: frozenset[str] = frozenset()):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self._build_buttons(boots_equipped, sprinting, mine_dirs)

    def _dir_btn(self, direction: str, arrow_emoji: str, row: int,
                 mine: bool) -> discord.ui.Button:
        if mine:
            return discord.ui.Button(
                style=discord.ButtonStyle.danger,
                emoji="\u26CF\uFE0F",  # ⛏️
                custom_id=_custom_id(self.guild_id, self.user_id, f"mine_{direction}"),
                row=row,
            )
        return discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji=arrow_emoji,
            custom_id=_custom_id(self.guild_id, self.user_id, direction),
            row=row,
        )

    def _build_buttons(self, boots_equipped: bool, sprinting: bool,
                       mine_dirs: frozenset[str]):
        sprint_label = "\U0001F97E"  # 🥾
        sprint_style = discord.ButtonStyle.success if sprinting else discord.ButtonStyle.secondary

        if boots_equipped:
            sprint_btn = discord.ui.Button(
                style=sprint_style,
                label=sprint_label,
                custom_id=_custom_id(self.guild_id, self.user_id, "sprint"),
                row=0,
            )
        else:
            sprint_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp1"),
                row=0,
            )

        up_btn   = self._dir_btn("up",    "\u2B06\uFE0F", 0, "up"    in mine_dirs)
        spacer2  = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(self.guild_id, self.user_id, "sp2"),
            row=0,
        )
        interact_btn = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Interact",
            emoji="\U0001F91A",
            custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
            row=0,
        )
        map_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Map",
            emoji="\U0001F5FA\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "map"),
            row=0,
        )
        left_btn  = self._dir_btn("left",  "\u2B05\uFE0F", 1, "left"  in mine_dirs)
        down_btn  = self._dir_btn("down",  "\u2B07\uFE0F", 1, "down"  in mine_dirs)
        right_btn = self._dir_btn("right", "\u27A1\uFE0F", 1, "right" in mine_dirs)
        inventory_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Inventory",
            emoji="\U0001F392",
            custom_id=_custom_id(self.guild_id, self.user_id, "inventory"),
            row=1,
        )
        help_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Help",
            emoji="\u2753",
            custom_id=_custom_id(self.guild_id, self.user_id, "help"),
            row=1,
        )
        for btn in [sprint_btn, up_btn, spacer2, interact_btn, map_btn,
                    left_btn, down_btn, right_btn, inventory_btn, help_btn]:
            self.add_item(btn)


class InventoryView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, equip_label: str = "⚔️ Equip"):
        super().__init__(timeout=None)
        for label, action in [
            ("◀", "inv_prev"),
            ("▶", "inv_next"),
            (equip_label, "inv_equip"),
            ("❌ Close", "inv_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, action),
                row=0,
            ))


class BankView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, view_mode: str = "player"):
        super().__init__(timeout=None)
        action = "bank_withdraw" if view_mode == "bank" else "bank_deposit"
        action_label = "⬆ Withdraw" if view_mode == "bank" else "⬇ Deposit"
        for label, act in [
            ("◀", "bank_prev"),
            ("▶", "bank_next"),
            (action_label, action),
            ("🔄 Switch", "bank_switch"),
            ("❌ Close", "bank_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))


class ShopView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, mode: str = "buy"):
        super().__init__(timeout=None)
        if mode == "buy":
            action_label, action_id = "💰 Buy", "shop_buy"
            mode_label, mode_id = "💲 Sell", "shop_mode"
        else:
            action_label, action_id = "💰 Sell", "shop_sell"
            mode_label, mode_id = "🛒 Buy", "shop_mode"
        for label, act in [
            ("◀", "shop_prev"),
            ("▶", "shop_next"),
            (action_label, action_id),
            (mode_label, mode_id),
            ("❌ Close", "shop_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))


class ChestView(discord.ui.View):
    """Chest inventory view — chest side shows Take + LootAll, player side shows Give + Switch."""

    def __init__(self, guild_id: int, user_id: int, view_mode: str = "chest"):
        super().__init__(timeout=None)
        if view_mode == "chest":
            action_label, action_id = "📤 Take", "chest_take"
            extra_label, extra_id = "📦 Loot All", "chest_lootall"
        else:
            action_label, action_id = "📥 Give", "chest_give"
            extra_label, extra_id = "🔄 Switch", "chest_switch"
        for label, act in [
            ("◀", "chest_prev"),
            ("▶", "chest_next"),
            (action_label, action_id),
            (extra_label, extra_id),
            ("❌ Close", "chest_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))


class CombatView(discord.ui.View):
    """Arena combat view. Arrows attempt cobweb escape when trapped. Attack disabled while trapped."""

    def __init__(self, guild_id: int, user_id: int, trapped: bool = False,
                 moves_left: int = COMBAT_MOVES_DEFAULT):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        disabled = (moves_left <= 0)
        attack_disabled = disabled or trapped  # can't attack while trapped

        # Row 0: ↖ ↑ ↗ ⚔️ ⏭
        for emoji, action in [("↖", "c_upleft"), ("⬆️", "c_up"), ("↗", "c_upright"),
                               ("⚔️", "c_attack"), ("⏭", "c_endturn")]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary if emoji in ("↖","⬆️","↗")
                      else discord.ButtonStyle.danger if emoji == "⚔️"
                      else discord.ButtonStyle.secondary,
                label=emoji,
                disabled=attack_disabled if emoji == "⚔️" else disabled,
                custom_id=_custom_id(gid, uid, action), row=0,
            ))

        # Row 1: ← · → 🧪 🏃  (center is always a spacer — cobweb escape via arrows)
        for label, action, dis in [
            ("⬅️", "c_left",  disabled),
            ("·",  "c_wait",  True),
            ("➡️", "c_right", disabled),
            ("🧪", "c_potion", disabled),
            ("🏃", "c_flee",  disabled),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label, disabled=dis,
                custom_id=_custom_id(gid, uid, action), row=1,
            ))

        # Row 2: ↙ ↓ ↘ 🎒 spacer
        for emoji, action in [("↙", "c_downleft"), ("⬇️", "c_down"), ("↘", "c_downright")]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=emoji, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=2,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🎒", disabled=False,
            custom_id=_custom_id(gid, uid, "c_inventory"), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, "csp0"), row=2,
        ))


# ── Equipment helpers ─────────────────────────────────────────────────────────

def _equipped_dict(player: Player) -> dict:
    d = {}
    for slot, val in [
        ("hand_1", player.hand_1), ("hand_2", player.hand_2),
        ("head", player.head), ("chest", player.chest),
        ("legs", player.legs), ("boots", player.boots),
        ("accessory", player.accessory), ("pouch", player.pouch),
    ]:
        if val:
            d[slot] = val
    return d


def _inv_capacity(player: Player) -> tuple[int, int]:
    """Return (rows, cols) for player's current inventory based on equipped pouch."""
    return POUCH_SIZES.get(player.pouch, POUCH_SIZES[None])


def _equip_label(items: list[dict], selected: int, equipped: dict) -> str:
    """Return 'Unequip' if selected item is currently equipped, else 'Equip'."""
    if selected < len(items) and items[selected]["item_id"] in equipped.values():
        return "↩ Unequip"
    return "⚔️ Equip"


async def _auto_unequip_depleted(db, user_id: int, item_id: str, player: Player) -> None:
    """Unequip item from hand slots if its inventory stack is now empty."""
    row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
    )
    if row:
        return
    for slot in ("hand_1", "hand_2"):
        if getattr(player, slot, None) == item_id:
            await unequip_item(db, user_id, slot)


async def _resolve_cave_combat(
    player: Player, enemy_type: str,
    cave_x: int, cave_y: int, db, user_id: int
) -> str:
    from dwarf_explorer.config import ENEMY_STATS
    hp, atk, defn, xp_rew, gold_rew = ENEMY_STATS[enemy_type]
    enemy_dmg = max(0, atk - player.defense)
    player_dmg = max(1, player.attack - defn)
    player.hp = max(0, player.hp - enemy_dmg)
    player.gold += gold_rew
    player.xp += xp_rew
    await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
    await db.execute(
        "UPDATE cave_tiles SET tile_type='stone_floor'"
        " WHERE cave_id=? AND local_x=? AND local_y=?",
        (player.cave_id, cave_x, cave_y),
    )
    name = enemy_type.replace("cave_", "").replace("_", " ").title()
    result = f"\u2694\uFE0F You fight the {name}! Dealt {player_dmg}. Took {enemy_dmg} damage."
    if player.hp <= 0:
        result += " You have been knocked out! (HP: 0)"
    else:
        result += f" Got {xp_rew}XP, {gold_rew}g."
    return result


# ── Movement ──────────────────────────────────────────────────────────────────

def _game_view(guild_id: int, user_id: int, player: Player,
               mine_dirs: frozenset[str] = frozenset()) -> GameView:
    return GameView(guild_id, user_id,
                    boots_equipped=(player.boots is not None),
                    sprinting=player.sprinting,
                    mine_dirs=mine_dirs)


async def _cave_game_view(guild_id: int, user_id: int, player: Player, db) -> GameView:
    """Build a GameView with mine buttons for any adjacent cave_rock tiles."""
    mine_dirs: set[str] = set()
    if player.in_cave:
        for direction, (dx, dy) in DIRECTIONS.items():
            tile = await load_cave_single_tile(
                player.cave_id, player.cave_x + dx, player.cave_y + dy, db
            )
            if tile.terrain == "cave_rock":
                mine_dirs.add(direction)
    return _game_view(guild_id, user_id, player, frozenset(mine_dirs))


def _roll_encounter(rng: _random.Random, rates: dict | None = None) -> str | None:
    """Roll for a random cave encounter. Returns enemy_type or None."""
    if rates is None:
        rates = CAVE_ENCOUNTER_RATES
    for enemy_type, rate in rates.items():
        if rng.random() < rate:
            return enemy_type
    return None


async def _move_steps(
    player: Player, direction: str, steps: int, seed: int, db,
    guild_id: int, user_id: int,
) -> tuple[str, discord.ui.View]:
    """Move player 1 or 2 tiles, returning (content, view)."""
    dx, dy = DIRECTIONS[direction]

    if player.in_house:
        for _ in range(steps):
            nx, ny = player.house_x + dx, player.house_y + dy
            target = await load_building_single_tile(player.house_id, nx, ny, db)
            if target.terrain == "b_door":
                # Auto-exit house on walking into door
                vx, vy = player.house_vx, player.house_vy
                player.in_house = False
                player.house_id = None
                player.village_x = vx
                player.village_y = vy
                await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
                await update_player_village_state(
                    db, user_id, True, player.village_id,
                    vx, vy, player.village_wx, player.village_wy,
                )
                grid = await load_village_viewport(player.village_id, vx, vy, db)
                return render_grid(grid, player, "You step outside."), _game_view(guild_id, user_id, player)
            allowed, reason = can_move_building(target)
            if not allowed:
                grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player)
            player.house_x, player.house_y = nx, ny
            await update_player_house_state(
                db, user_id, True, player.house_id,
                nx, ny, player.house_vx, player.house_vy, player.house_type,
            )
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player)

    elif player.in_village:
        for _ in range(steps):
            nx, ny = player.village_x + dx, player.village_y + dy
            target = await load_village_single_tile(player.village_id, nx, ny, db)
            if target.terrain == "void":
                wx, wy = player.village_wx, player.village_wy
                player.in_village = False
                player.village_id = None
                player.world_x, player.world_y = wx, wy
                await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
                await update_player_position(db, user_id, wx, wy)
                grid = await load_viewport(wx, wy, seed, db)
                return render_grid(grid, player, "You leave the village."), _game_view(guild_id, user_id, player)
            allowed, reason = can_move_village(target)
            if not allowed:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player)
            player.village_x, player.village_y = nx, ny
            await update_player_village_state(
                db, user_id, True, player.village_id,
                nx, ny, player.village_wx, player.village_wy,
            )
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player)

    elif player.in_cave:
        # Determine cave level for encounter rate lookup
        cave_level_row = await db.fetch_one(
            "SELECT cave_level FROM caves WHERE cave_id = ?", (player.cave_id,)
        )
        cave_level = cave_level_row["cave_level"] if cave_level_row else 1
        enc_rates = CAVE_LEVEL_ENCOUNTER_RATES.get(cave_level, CAVE_ENCOUNTER_RATES)

        for _ in range(steps):
            nx, ny = player.cave_x + dx, player.cave_y + dy
            target = await load_cave_single_tile(player.cave_id, nx, ny, db)

            # Handle stairdown: descend to child cave (generated lazily on first visit)
            if target.terrain == "cave_stairdown":
                deep_row = await db.fetch_one(
                    "SELECT child_cave_id, child_local_x, child_local_y"
                    " FROM cave_deep_entrances"
                    " WHERE parent_cave_id = ? AND parent_local_x = ? AND parent_local_y = ?",
                    (player.cave_id, nx, ny),
                )
                if not deep_row:
                    from dwarf_explorer.world.caves import _create_child_cave
                    await _create_child_cave(seed, player.cave_id, nx, ny, cave_level + 1, db)
                    deep_row = await db.fetch_one(
                        "SELECT child_cave_id, child_local_x, child_local_y"
                        " FROM cave_deep_entrances"
                        " WHERE parent_cave_id = ? AND parent_local_x = ? AND parent_local_y = ?",
                        (player.cave_id, nx, ny),
                    )
                if deep_row:
                    player.cave_id = deep_row["child_cave_id"]
                    player.cave_x = deep_row["child_local_x"]
                    player.cave_y = deep_row["child_local_y"]
                    await update_player_cave_state(db, user_id, True, player.cave_id,
                                                   player.cave_x, player.cave_y)
                    grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                    return render_grid(grid, player, "You descend deeper into the cave..."), \
                           await _cave_game_view(guild_id, user_id, player, db)

            # Handle stairup: ascend to parent cave
            if target.terrain == "cave_stairup":
                up_row = await db.fetch_one(
                    "SELECT parent_cave_id, parent_local_x, parent_local_y"
                    " FROM cave_deep_entrances"
                    " WHERE child_cave_id = ?",
                    (player.cave_id,),
                )
                if up_row:
                    player.cave_id = up_row["parent_cave_id"]
                    player.cave_x = up_row["parent_local_x"]
                    player.cave_y = up_row["parent_local_y"]
                    await update_player_cave_state(db, user_id, True, player.cave_id,
                                                   player.cave_x, player.cave_y)
                    grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                    return render_grid(grid, player, "You climb back up..."), \
                           await _cave_game_view(guild_id, user_id, player, db)
                # No parent cave — treat as normal floor
                player.cave_x, player.cave_y = nx, ny
                await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                return render_grid(grid, player), await _cave_game_view(guild_id, user_id, player, db)

            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                return render_grid(grid, player, reason), await _cave_game_view(guild_id, user_id, player, db)
            player.cave_x, player.cave_y = nx, ny
            await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)
            # Random encounter on stone_floor tiles
            if target.terrain == "stone_floor":
                enc_rng = _random.Random(hash((user_id, nx, ny,
                                              player.cave_id, player.gold)))
                enemy_type = _roll_encounter(enc_rng, enc_rates)
                if enemy_type:
                    grid = await load_cave_viewport(player.cave_id, nx, ny, db)
                    arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type)))
                    arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
                    player.in_combat = True
                    player.combat_enemy_type = enemy_type
                    player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                    player.combat_enemy_x = ex
                    player.combat_enemy_y = ey
                    player.combat_player_x = ARENA_SIZE // 2
                    player.combat_player_y = ARENA_SIZE // 2
                    player.combat_moves_left = COMBAT_MOVES_DEFAULT
                    _ui_state[user_id] = {"type": "combat", "arena": arena}
                    await save_combat_state(db, user_id, player)
                    content = render_arena(arena, player)
                    view = CombatView(guild_id, user_id,
                                      trapped=arena["player_trapped"],
                                      moves_left=player.combat_moves_left)
                    return content, view
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        return render_grid(grid, player), await _cave_game_view(guild_id, user_id, player, db)

    else:
        for _ in range(steps):
            nx, ny = player.world_x + dx, player.world_y + dy
            target = await load_single_tile(nx, ny, seed, db)
            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_viewport(player.world_x, player.world_y, seed, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player)
            player.world_x, player.world_y = nx, ny
            await update_player_position(db, user_id, nx, ny)
            # Random surface encounter (1%, biome-specific, skip short_grass)
            enemy_type = SURFACE_ENCOUNTER_MOBS.get(target.terrain)
            if enemy_type:
                enc_rng = _random.Random(hash((user_id, nx, ny, seed, player.gold)))
                if enc_rng.random() < 0.01:
                    grid = await load_viewport(nx, ny, seed, db)
                    arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type)))
                    arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
                    player.in_combat = True
                    player.combat_enemy_type = enemy_type
                    player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                    player.combat_enemy_x = ex
                    player.combat_enemy_y = ey
                    player.combat_player_x = ARENA_SIZE // 2
                    player.combat_player_y = ARENA_SIZE // 2
                    player.combat_moves_left = COMBAT_MOVES_DEFAULT
                    _ui_state[user_id] = {"type": "combat", "arena": arena}
                    await save_combat_state(db, user_id, player)
                    content = render_arena(arena, player)
                    view = CombatView(guild_id, user_id,
                                      trapped=arena["player_trapped"],
                                      moves_left=player.combat_moves_left)
                    return content, view
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player)


async def handle_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    steps = 2 if (player.sprinting and player.boots is not None) else 1
    content, view = await _move_steps(player, direction, steps, seed, db, guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Combat handlers ───────────────────────────────────────────────────────────

def _combat_view(guild_id: int, user_id: int, arena: dict, player) -> CombatView:
    return CombatView(guild_id, user_id,
                      trapped=arena["player_trapped"],
                      moves_left=player.combat_moves_left)


async def _finish_combat(
    db, guild_id: int, user_id: int, player,
    arena: dict, extra_msg: str,
    won: bool = False,
) -> tuple[str, discord.ui.View]:
    """Clean up after combat ends (win, flee, or death). Return (content, view)."""
    seed = await get_or_create_world(db, guild_id)
    player.in_combat = False
    _ui_state.pop(user_id, None)
    await clear_combat_state(db, user_id)

    # Spider poison sac drop on victory
    if won and player.combat_enemy_type in ("cave_spider", "spider"):
        drop_rng = _random.Random(hash((user_id, player.cave_x, player.cave_y, "sac")))
        if drop_rng.random() < 0.50:
            await add_to_inventory(db, user_id, "poison_sac", 1)
            extra_msg += " 🧪 The spider dropped a **Poison Sac**!"

    if player.hp <= 0:
        msg = apply_death_reset(player)
        await update_player_stats(db, user_id, hp=player.hp)
        await update_player_cave_state(db, user_id, False, None, 0, 0)
        await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        await update_player_position(db, user_id, player.world_x, player.world_y)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        return render_grid(grid, player, f"{extra_msg} {msg}"), _game_view(guild_id, user_id, player)

    await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
    # Return to the appropriate location view
    if player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        return render_grid(grid, player, extra_msg), await _cave_game_view(guild_id, user_id, player, db)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    return render_grid(grid, player, extra_msg), _game_view(guild_id, user_id, player)


async def _after_player_action(
    interaction: discord.Interaction,
    db, guild_id: int, user_id: int,
    player, arena: dict, msg: str,
) -> None:
    """Called after a player action. Run enemy turn if moves exhausted, or re-render."""
    arena["combat_log"].append(msg)

    # Enemy dead?
    if player.combat_enemy_hp <= 0:
        victory_msg = apply_victory(player)
        arena["combat_log"].append(victory_msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]), won=True)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Player dead?
    if player.hp <= 0:
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]))
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Still has moves left?
    if player.combat_moves_left > 0:
        await save_combat_state(db, user_id, player)
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # No moves left → enemy turn
    rng = _random.Random(hash((user_id, player.combat_enemy_x, player.combat_enemy_y,
                               player.combat_enemy_hp)))
    enemy_msg = resolve_enemy_turn(arena, player, rng)
    arena["combat_log"].append(enemy_msg)

    # Restore player moves for next turn
    player.combat_moves_left = COMBAT_MOVES_DEFAULT

    # Check outcomes after enemy turn
    if player.hp <= 0:
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]))
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if player.combat_enemy_hp <= 0:
        victory_msg = apply_victory(player)
        arena["combat_log"].append(victory_msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]), won=True)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await save_combat_state(db, user_id, player)
    content = render_arena(arena, player)
    view = _combat_view(guild_id, user_id, arena, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def _load_combat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> tuple | None:
    """Load combat state. Returns (db, player, arena) or None if not in combat."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    arena = _ui_state.get(user_id, {}).get("arena")
    if not player.in_combat or arena is None:
        # Combat state lost (e.g. bot restart) — clear and return to game
        if player.in_combat:
            player.in_combat = False
            await clear_combat_state(db, user_id)
            seed = await get_or_create_world(db, guild_id)
            if player.in_cave:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            else:
                grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, "Combat session lost — you escape unharmed.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player)
            )
        return None
    return db, player, arena


async def handle_combat_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    rng = _random.Random(hash((user_id, player.combat_player_x, player.combat_player_y,
                               arena.get("poison_turns", 0))))
    msg = action_move(arena, player, direction, rng)
    await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)


async def handle_combat_attack(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    rng = _random.Random(hash((user_id, player.combat_player_x, player.combat_enemy_x)))

    # Slingshot: check for equipped slingshot and consume 1 rock
    has_slingshot = player.hand_1 == "slingshot" or player.hand_2 == "slingshot"
    if has_slingshot:
        rock_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id='rock'", (user_id,)
        )
        if not rock_row:
            arena["combat_log"].append("No rocks left! Mine cave_rocks with a pickaxe.")
            content = render_arena(arena, player)
            view = _combat_view(guild_id, user_id, arena, player)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        await remove_from_inventory(db, user_id, "rock", 1)

    msg = action_attack(arena, player, rng, has_slingshot=has_slingshot)
    await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)


async def handle_combat_flee(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    rng = _random.Random()  # non-deterministic: flee shouldn't be predictable
    msg, success = action_flee(arena, player, rng)
    if success:
        arena["combat_log"].append(msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-3:]))
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
    else:
        await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)


async def handle_combat_potion(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    # Check inventory for potion
    has_potion = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='potion'", (user_id,)
    )
    if not has_potion:
        arena["combat_log"].append("You have no potions!")
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return
    await remove_from_inventory(db, user_id, "potion", 1)
    msg = action_use_potion(arena, player)
    await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)



async def handle_combat_end_turn(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Force end player's turn immediately."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    player.combat_moves_left = 0  # exhaust moves
    await _after_player_action(interaction, db, guild_id, user_id, player, arena,
                               "You end your turn.")


# ── Mine adjacent rock ────────────────────────────────────────────────────────

async def handle_mine(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_cave:
        await interaction.response.defer()
        return

    dx, dy = DIRECTIONS[direction]
    nx, ny = player.cave_x + dx, player.cave_y + dy

    hand_items: set[str] = {player.hand_1, player.hand_2} - {None}
    if "pickaxe" not in hand_items:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        content = render_grid(grid, player, "You need a pickaxe to mine that rock.")
        view = await _cave_game_view(guild_id, user_id, player, db)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    tile = await load_cave_single_tile(player.cave_id, nx, ny, db)
    if tile.terrain != "cave_rock":
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        content = render_grid(grid, player, "That rock has already been mined.")
        view = await _cave_game_view(guild_id, user_id, player, db)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    rng = _random.Random(hash((user_id, nx, ny, player.xp)))
    await db.execute(
        "UPDATE cave_tiles SET tile_type='stone_floor'"
        " WHERE cave_id=? AND local_x=? AND local_y=?",
        (player.cave_id, nx, ny),
    )
    loot = []
    rock_count = rng.randint(1, 3)
    await add_to_inventory(db, user_id, "rock", rock_count)
    loot.append(f"{rock_count} rock{'s' if rock_count > 1 else ''}")
    if rng.random() < 0.33:
        await add_to_inventory(db, user_id, "flint", 1)
        loot.append("flint")
    if rng.random() < 0.15:
        await add_to_inventory(db, user_id, "iron_ore", 1)
        loot.append("iron ore")

    grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    content = render_grid(grid, player, f"You mine the rock! Got: {', '.join(loot)}.")
    view = await _cave_game_view(guild_id, user_id, player, db)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Sprint toggle ─────────────────────────────────────────────────────────────

async def handle_sprint(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.boots is None:
        await interaction.response.send_message("You need hiking boots to sprint.", ephemeral=True)
        return

    player.sprinting = not player.sprinting
    await update_player_sprint(db, user_id, player.sprinting)

    status = "Sprint ON \U0001F3C3" if player.sprinting else "Sprint OFF"
    if player.in_house:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player, status)
    view = _game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Interact ──────────────────────────────────────────────────────────────────

async def handle_interact(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.in_house:
        htile = await load_building_single_tile(player.house_id, player.house_x, player.house_y, db)

        if htile.terrain == "b_door":
            vx, vy = player.house_vx, player.house_vy
            player.in_house = False
            await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
            player.village_x, player.village_y = vx, vy
            await update_player_village_state(
                db, user_id, True, player.village_id,
                vx, vy, player.village_wx, player.village_wy,
            )
            grid = await load_village_viewport(player.village_id, vx, vy, db)
            content = render_grid(grid, player, "You step outside.")

        elif htile.terrain == "b_bank_npc" and player.house_type == "bank":
            return await _open_bank(interaction, guild_id, user_id, player, db)

        elif htile.terrain == "b_shop_npc" and player.house_type == "shop":
            return await _open_shop(interaction, guild_id, user_id, player)

        elif htile.terrain in ("b_bed", "b_stove", "b_table", "b_bookshelf"):
            msgs = {
                "b_bed": "A cozy bed. You feel rested.",
                "b_stove": "A warm hearth. Something smells delicious.",
                "b_table": "A sturdy wooden table.",
                "b_bookshelf": "Rows of dusty books.",
            }
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, msgs.get(htile.terrain, "..."))

        elif htile.terrain == "b_altar" and player.house_type == "church":
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "You kneel before the altar. You feel at peace.")

        elif htile.terrain == "b_priest":
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "\"May the light guide your path, traveller.\"")

        elif htile.terrain == "b_safe":
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "A locked vault. Speak with the banker.")

        elif htile.terrain == "b_blacksmith_npc" and player.house_type == "blacksmith":
            # Smelt iron ore → iron ingot
            ore_row = await db.fetch_one(
                "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ore'", (user_id,)
            )
            if not ore_row or ore_row["quantity"] < 1:
                grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
                content = render_grid(grid, player, "\"Bring me iron ore and I'll smelt it into ingots.\"")
            else:
                count = ore_row["quantity"]
                await remove_from_inventory(db, user_id, "iron_ore", count)
                await add_to_inventory(db, user_id, "iron_ingot", count)
                grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
                content = render_grid(grid, player, f"The blacksmith smelts {count} iron ore into {count} iron ingots!")

        elif htile.terrain == "b_anvil":
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "A sturdy anvil. Speak with the blacksmith to smelt ore.")

        else:
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    elif player.in_village:
        vtile = await load_village_single_tile(player.village_id, player.village_x, player.village_y, db)

        if vtile.terrain in ("vil_house", "vil_church", "vil_bank", "vil_shop", "vil_blacksmith"):
            result = await get_building_at(player.village_id, player.village_x, player.village_y, db)
            if result:
                house_id, btype, hx, hy = result
                player.in_house = True
                player.house_id = house_id
                player.house_x = hx
                player.house_y = hy
                player.house_vx = player.village_x
                player.house_vy = player.village_y
                player.house_type = btype
                await update_player_house_state(
                    db, user_id, True, house_id, hx, hy,
                    player.village_x, player.village_y, btype,
                )
                labels = {"house": "house", "church": "church", "bank": "bank", "shop": "shop", "blacksmith": "blacksmith"}
                grid = await load_building_viewport(house_id, hx, hy, db)
                content = render_grid(grid, player, f"You enter the {labels.get(btype, 'building')}.")
            else:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
                content = render_grid(grid, player, "Nothing to interact with here.")

        elif vtile.terrain == "vil_well":
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
            content = render_grid(grid, player, "A stone well. The water is cool and clear.")

        else:
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    elif player.in_cave:
        cave_tile = await load_cave_single_tile(player.cave_id, player.cave_x, player.cave_y, db)

        if cave_tile.terrain == "cave_entrance":
            result = await get_cave_entrance_exit(db, player.cave_id, player.cave_x, player.cave_y)
            if result:
                wx, wy = result
                player.world_x, player.world_y = wx, wy
                player.in_cave = False
                player.cave_id = None
                await update_player_position(db, user_id, wx, wy)
                await update_player_cave_state(db, user_id, False, None, 0, 0)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "You exit the cave.")
            else:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                content = render_grid(grid, player, "Nothing to interact with here.")

        elif cave_tile.terrain in CAVE_CHEST_TYPES:
            chest_id, is_new = await get_or_create_chest(
                db, player.cave_id, player.cave_x, player.cave_y, cave_tile.terrain
            )
            if is_new:
                await populate_chest_loot(chest_id, cave_tile.terrain, db)
            chest_inv = await get_chest_items(db, chest_id)
            inv_rows, inv_cols = _inv_capacity(player)
            _ui_state[user_id] = {
                "type": "chest", "chest_id": chest_id,
                "chest_type": cave_tile.terrain, "selected": 0, "chest_view": "chest",
            }
            content = render_chest(chest_inv, [], 0, "chest", cave_tile.terrain,
                                   inv_rows, inv_cols)
            view = ChestView(guild_id, user_id, "chest")
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        else:
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = await _cave_game_view(guild_id, user_id, player, db)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    else:
        # Wilderness interact
        tile = await load_single_tile(player.world_x, player.world_y, seed, db)
        wx, wy = player.world_x, player.world_y

        # Items currently held in hands
        hand_items: set[str] = set()
        if player.hand_1:
            hand_items.add(player.hand_1)
        if player.hand_2:
            hand_items.add(player.hand_2)

        terrain = tile.terrain

        if tile.structure == "cave":
            cave_id, ex, ey = await get_or_create_cave(seed, wx, wy, db)
            # Step 4 tiles inward from the entrance edge so the viewport
            # shows cave interior instead of mostly-out-of-bounds walls.
            cave_meta = await db.fetch_one(
                "SELECT width, height FROM caves WHERE cave_id=?", (cave_id,)
            )
            cw = cave_meta["width"] if cave_meta else 40
            ch = cave_meta["height"] if cave_meta else 40
            INWARD = 4
            if ey == 0:            sx, sy = ex, min(INWARD, ch - 1)
            elif ey == ch - 1:     sx, sy = ex, max(ch - 1 - INWARD, 0)
            elif ex == 0:          sx, sy = min(INWARD, cw - 1), ey
            else:                  sx, sy = max(cw - 1 - INWARD, 0), ey
            player.in_cave = True
            player.cave_id = cave_id
            player.cave_x, player.cave_y = sx, sy
            await update_player_cave_state(db, user_id, True, cave_id, sx, sy)
            grid = await load_cave_viewport(cave_id, sx, sy, db)
            content = render_grid(grid, player, "You enter the cave...")

        elif tile.structure == "village":
            vid, vx, vy = await get_or_create_village(seed, wx, wy, db)
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = vx, vy
            player.village_wx, player.village_wy = wx, wy
            await update_player_village_state(db, user_id, True, vid, vx, vy, wx, wy)
            grid = await load_village_viewport(vid, vx, vy, db)
            content = render_grid(grid, player, "You enter the village.")

        elif terrain in ("forest", "dense_forest") and "axe" in hand_items:
            # Chop tree
            rng = _random.Random()
            await set_tile_override(db, wx, wy, "sapling")
            await add_to_inventory(db, user_id, "log", 1)
            extras = []
            if rng.random() < 0.66:
                await add_to_inventory(db, user_id, "stick", 1)
                extras.append("a stick")
            if rng.random() < 0.33:
                await add_to_inventory(db, user_id, "resin", 1)
                extras.append("some resin")
            extra_str = (", " + ", ".join(extras)) if extras else ""
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"You chop down the tree! Got a log{extra_str}. A sapling remains.")

        elif terrain == "sapling" and "shovel" in hand_items:
            # Dig up sapling
            await set_tile_override(db, wx, wy, "path")
            await add_to_inventory(db, user_id, "sapling", 1)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You dig up the sapling. The ground becomes a path.")

        elif terrain == "path" and "sapling" in hand_items:
            # Plant sapling
            await set_tile_override(db, wx, wy, "sapling")
            await remove_from_inventory(db, user_id, "sapling", 1)
            await _auto_unequip_depleted(db, user_id, "sapling", player)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You plant the sapling.")

        elif terrain == "path" and "seed" in hand_items:
            # Plant seed → seedling
            await set_tile_override(db, wx, wy, "seedling")
            await remove_from_inventory(db, user_id, "seed", 1)
            await _auto_unequip_depleted(db, user_id, "seed", player)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You plant the seed. A seedling sprouts!")

        elif terrain == "sapling" and "watering_can" in hand_items:
            # Water sapling → forest
            await set_tile_override(db, wx, wy, "forest")
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You water the sapling. It grows into a tree!")

        elif terrain == "short_grass" and "watering_can" in hand_items:
            # Water short grass → grass
            await set_tile_override(db, wx, wy, "grass")
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You water the short grass. It grows lush!")

        elif terrain == "seedling" and "watering_can" in hand_items:
            # Water seedling → grass
            await set_tile_override(db, wx, wy, "grass")
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You water the seedling. It grows into grass!")

        elif terrain == "grass" and "knife" in hand_items:
            # Cut grass → short_grass + plant_fiber
            await set_tile_override(db, wx, wy, "short_grass")
            await add_to_inventory(db, user_id, "plant_fiber", 1)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You cut the grass and collect plant fiber.")

        elif terrain == "plains" and "knife" in hand_items:
            # Cut plains → short_grass + dry_grass item + seeds
            rng = _random.Random()
            await set_tile_override(db, wx, wy, "short_grass")
            await add_to_inventory(db, user_id, "dry_grass", 1)
            seeds = 2 + (1 if rng.random() < 0.5 else 0)
            await add_to_inventory(db, user_id, "seed", seeds)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"You cut the plains grass. Got dry grass and {seeds} seeds!")

        else:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Inventory handlers ────────────────────────────────────────────────────────

async def handle_inventory(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    prev_arena = _ui_state.get(user_id, {}).get("arena")
    _ui_state[user_id] = {"type": "inventory", "selected": 0, "prev_arena": prev_arena}
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    label = _equip_label(items, 0, equipped)
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_inventory(items, 0, equipped, label, inv_rows, inv_cols)
    view = InventoryView(guild_id, user_id, label)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    total_slots = inv_rows * inv_cols
    new_sel = (state["selected"] + delta) % max(1, total_slots)
    _ui_state[user_id] = {"type": "inventory", "selected": new_sel,
                          "prev_arena": state.get("prev_arena")}
    equipped = _equipped_dict(player)
    label = _equip_label(items, new_sel, equipped)
    content = render_inventory(items, new_sel, equipped, label, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=InventoryView(guild_id, user_id, label))


async def handle_inv_equip(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Handles both equip and unequip based on whether the selected item is already equipped."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)

    if sel >= len(items):
        label = _equip_label(items, sel, equipped)
        content = render_inventory(items, sel, equipped, label) + "\n*(No item selected)*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=InventoryView(guild_id, user_id, label))
        return

    item_id = items[sel]["item_id"]
    inv_rows, inv_cols = _inv_capacity(player)

    # Unequip if already equipped
    if item_id in equipped.values():
        # Pouch unequip: check if current inv fits in smaller size
        if item_id in ("small_pouch", "medium_pouch", "large_pouch"):
            new_rows, new_cols = POUCH_SIZES[None]  # default size after unequip
            # Find next smaller pouch that fits
            pouch_order = [None, "small_pouch", "medium_pouch", "large_pouch"]
            cur_idx = pouch_order.index(item_id)
            new_rows, new_cols = POUCH_SIZES[pouch_order[cur_idx - 1]] if cur_idx > 0 else POUCH_SIZES[None]
            new_capacity = new_rows * new_cols
            if len(items) > new_capacity:
                content = render_inventory(items, sel, equipped, "⚔️ Equip", inv_rows, inv_cols)
                content += f"\n*Can't unequip: your inventory has {len(items)} items but the smaller pouch only fits {new_capacity}. Remove some items first.*"
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=InventoryView(guild_id, user_id, "⚔️ Equip"))
                return
        if item_id in TWO_HANDED_ITEMS:
            await unequip_item(db, user_id, "hand_1")
            await unequip_item(db, user_id, "hand_2")
        else:
            slot = next(s for s, v in equipped.items() if v == item_id)
            await unequip_item(db, user_id, slot)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        equipped = _equipped_dict(player)
        inv_rows, inv_cols = _inv_capacity(player)
        label = _equip_label(items, sel, equipped)
        content = render_inventory(items, sel, equipped, label, inv_rows, inv_cols) + f"\n*Unequipped {item_id.replace('_', ' ').title()}.*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=InventoryView(guild_id, user_id, label))
        return

    # Look up slot type
    slot_type = ITEM_EQUIP_SLOTS.get(item_id)
    if not slot_type:
        label = _equip_label(items, sel, equipped)
        content = render_inventory(items, sel, equipped, label, inv_rows, inv_cols) + f"\n*{item_id.replace('_', ' ').title()} cannot be equipped.*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=InventoryView(guild_id, user_id, label))
        return

    # Resolve hand slot
    if slot_type == "hand":
        if item_id in TWO_HANDED_ITEMS:
            if equipped.get("hand_1") or equipped.get("hand_2"):
                label = _equip_label(items, sel, equipped)
                content = render_inventory(items, sel, equipped, label, inv_rows, inv_cols) + "\n*Your hands must be free for a two-handed item.*"
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=InventoryView(guild_id, user_id, label))
                return
            await equip_item(db, user_id, "hand_1", item_id)
            await equip_item(db, user_id, "hand_2", item_id)
        else:
            if not equipped.get("hand_1"):
                resolved_slot = "hand_1"
            elif not equipped.get("hand_2"):
                resolved_slot = "hand_2"
            else:
                label = _equip_label(items, sel, equipped)
                content = render_inventory(items, sel, equipped, label, inv_rows, inv_cols) + "\n*Both hands are full.*"
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=InventoryView(guild_id, user_id, label))
                return
            await equip_item(db, user_id, resolved_slot, item_id)
    else:
        # Direct slot (boots, head, chest, legs, accessory, pouch) — replace if occupied
        await equip_item(db, user_id, slot_type, item_id)

    bonuses = EQUIP_BONUSES.get(item_id, {})
    if bonuses:
        await update_player_stats(db, user_id, **bonuses)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    label = _equip_label(items, sel, equipped)
    content = render_inventory(items, sel, equipped, label, inv_rows, inv_cols) + f"\n*Equipped {item_id.replace('_', ' ').title()}!*"
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=InventoryView(guild_id, user_id, label))


async def handle_inv_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    prev_arena = _ui_state.get(user_id, {}).get("prev_arena")
    _ui_state.pop(user_id, None)
    # If inventory was opened during combat, return to combat view
    if player.in_combat and prev_arena is not None:
        _ui_state[user_id] = {"type": "combat", "arena": prev_arena}
        content = render_arena(prev_arena, player)
        view = _combat_view(guild_id, user_id, prev_arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return
    if player.in_house:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player)
    view = _game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Shop handlers ─────────────────────────────────────────────────────────────

async def _open_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player: Player,
) -> None:
    _ui_state[user_id] = {"type": "shop", "selected": 0, "mode": "buy"}
    content = render_shop(SHOP_CATALOG, 0, player.gold, mode="buy")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "buy"))


async def handle_shop_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "mode": "buy"})
    mode = state.get("mode", "buy")
    if mode == "sell":
        items = await get_inventory(db, user_id)
        total = max(1, len(items))
        new_sel = (state["selected"] + delta) % total
        _ui_state[user_id] = {**state, "selected": new_sel}
        content = render_shop(SHOP_CATALOG, new_sel, player.gold,
                              mode="sell", sell_items=items, sell_prices=ITEM_SELL_PRICES)
    else:
        total = len(SHOP_CATALOG)
        new_sel = (state["selected"] + delta) % total
        _ui_state[user_id] = {**state, "selected": new_sel}
        content = render_shop(SHOP_CATALOG, new_sel, player.gold, mode="buy")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, mode))


async def handle_shop_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "mode": "buy"})
    sel = state.get("selected", 0)
    item = SHOP_CATALOG[sel]
    if player.gold < item["price"]:
        content = render_shop(SHOP_CATALOG, sel, player.gold, mode="buy") + f"\n*Not enough gold! Need {item['price']}.*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "buy"))
        return
    player.gold -= item["price"]
    await update_player_stats(db, user_id, gold=player.gold)
    await add_to_inventory(db, user_id, item["id"])
    content = render_shop(SHOP_CATALOG, sel, player.gold, mode="buy") + f"\n*Purchased {item['name']}!*"
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "buy"))


async def handle_shop_sell(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "mode": "sell"})
    sel = state.get("selected", 0)
    items = await get_inventory(db, user_id)
    if sel >= len(items):
        content = render_shop(SHOP_CATALOG, sel, player.gold,
                              mode="sell", sell_items=items, sell_prices=ITEM_SELL_PRICES) + "\n*(No item selected)*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "sell"))
        return
    item_id = items[sel]["item_id"]
    price = ITEM_SELL_PRICES.get(item_id, 0)
    if price == 0:
        content = render_shop(SHOP_CATALOG, sel, player.gold,
                              mode="sell", sell_items=items, sell_prices=ITEM_SELL_PRICES) + \
                  f"\n*The shop won't buy {item_id.replace('_', ' ').title()}.*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "sell"))
        return
    await remove_from_inventory(db, user_id, item_id, 1)
    player.gold += price
    await update_player_stats(db, user_id, gold=player.gold)
    items = await get_inventory(db, user_id)
    new_sel = min(sel, max(0, len(items) - 1))
    if user_id in _ui_state:
        _ui_state[user_id]["selected"] = new_sel
    content = render_shop(SHOP_CATALOG, new_sel, player.gold,
                          mode="sell", sell_items=items, sell_prices=ITEM_SELL_PRICES) + \
              f"\n*Sold {item_id.replace('_', ' ').title()} for {price} gold!*"
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "sell"))


async def handle_shop_mode(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "mode": "buy"})
    new_mode = "sell" if state.get("mode", "buy") == "buy" else "buy"
    _ui_state[user_id] = {"type": "shop", "selected": 0, "mode": new_mode}
    if new_mode == "sell":
        items = await get_inventory(db, user_id)
        content = render_shop(SHOP_CATALOG, 0, player.gold,
                              mode="sell", sell_items=items, sell_prices=ITEM_SELL_PRICES)
    else:
        content = render_shop(SHOP_CATALOG, 0, player.gold, mode="buy")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, new_mode))


async def handle_shop_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Bank handlers ─────────────────────────────────────────────────────────────

async def _open_bank(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player: Player, db,
) -> None:
    _ui_state[user_id] = {"type": "bank", "selected": 0, "bank_view": "player"}
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    content = render_bank(player_items, bank_items, 0, "player", equipped)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "player"))


async def handle_bank_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    bv = state.get("bank_view", "player")
    total = max(1, (10 if bv == "player" else 36))
    new_sel = (state["selected"] + delta) % total
    _ui_state[user_id] = {"type": "bank", "selected": new_sel, "bank_view": bv}
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    content = render_bank(player_items, bank_items, new_sel, bv, equipped)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, bv))


async def handle_bank_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    new_view = "bank" if state.get("bank_view") == "player" else "player"
    _ui_state[user_id] = {"type": "bank", "selected": 0, "bank_view": new_view}
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    content = render_bank(player_items, bank_items, 0, new_view, equipped)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, new_view))


async def handle_bank_deposit(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    sel = state.get("selected", 0)
    items = await get_inventory(db, user_id)
    if sel >= len(items):
        player_items = items
        bank_items = await get_bank_items(db, user_id)
        equipped = _equipped_dict(player)
        content = render_bank(player_items, bank_items, sel, "player", equipped) + "\n*(Empty slot)*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=BankView(guild_id, user_id, "player"))
        return
    item_id = items[sel]["item_id"]
    ok = await bank_deposit(db, user_id, item_id)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    new_sel = min(sel, max(0, len(player_items) - 1))
    _ui_state[user_id]["selected"] = new_sel
    suffix = f"\n*Deposited {item_id}.*" if ok else "\n*Deposit failed.*"
    content = render_bank(player_items, bank_items, new_sel, "player", equipped) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "player"))


async def handle_bank_withdraw(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "bank"})
    sel = state.get("selected", 0)
    items = await get_bank_items(db, user_id)
    if sel >= len(items):
        player_items = await get_inventory(db, user_id)
        bank_items = items
        equipped = _equipped_dict(player)
        content = render_bank(player_items, bank_items, sel, "bank", equipped) + "\n*(Empty slot)*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=BankView(guild_id, user_id, "bank"))
        return
    item_id = items[sel]["item_id"]
    ok = await bank_withdraw(db, user_id, item_id)
    player_items = await get_inventory(db, user_id)
    bank_items_new = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    new_sel = min(sel, max(0, len(bank_items_new) - 1))
    _ui_state[user_id]["selected"] = new_sel
    suffix = f"\n*Withdrew {item_id}.*" if ok else "\n*Withdraw failed.*"
    content = render_bank(player_items, bank_items_new, new_sel, "bank", equipped) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "bank"))


async def handle_bank_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Chest handlers ────────────────────────────────────────────────────────────

async def _render_chest_state(
    db, user_id: int, player, state: dict,
) -> tuple[str, ChestView]:
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    view_mode = state.get("chest_view", "chest")
    sel = state.get("selected", 0)
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_chest(chest_inv, player_inv, sel, view_mode,
                           chest_type, inv_rows, inv_cols)
    view = ChestView(player.channel_id or 0, user_id, view_mode)
    # Rebuild view with correct guild_id from state if available
    return content, view


async def _load_chest(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> tuple | None:
    state = _ui_state.get(user_id, {})
    if state.get("type") != "chest":
        await handle_inv_close(interaction, guild_id, user_id)
        return None
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    return db, player, state


async def handle_chest_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    view_mode = state.get("chest_view", "chest")
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    if view_mode == "chest":
        chest_inv = await get_chest_items(db, chest_id)
        source_len = len(chest_inv)
        from dwarf_explorer.game.renderer import render_chest as _rc
        chest_sizes = {"cave_chest": (2,9), "cave_chest_medium": (3,9), "cave_chest_large": (4,9)}
        c_rows, c_cols = chest_sizes.get(chest_type, (2, 9))
        total = c_rows * c_cols
    else:
        player_inv = await get_inventory(db, user_id)
        source_len = len(player_inv)
        inv_rows, inv_cols = _inv_capacity(player)
        total = inv_rows * inv_cols
    new_sel = (state["selected"] + delta) % max(1, total)
    _ui_state[user_id]["selected"] = new_sel
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_chest(chest_inv, player_inv, new_sel, view_mode,
                           chest_type, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, view_mode))


async def handle_chest_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    new_view = "chest" if state.get("chest_view") == "player" else "player"
    _ui_state[user_id]["chest_view"] = new_view
    _ui_state[user_id]["selected"] = 0
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_chest(chest_inv, player_inv, 0, new_view,
                           chest_type, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, new_view))


async def handle_chest_take(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Take selected item from chest into player inventory."""
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    sel = state.get("selected", 0)
    chest_inv = await get_chest_items(db, chest_id)
    inv_rows, inv_cols = _inv_capacity(player)
    player_inv = await get_inventory(db, user_id)

    suffix = ""
    if sel < len(chest_inv):
        item_id = chest_inv[sel]["item_id"]
        # Check inventory capacity for new items
        existing_ids = {it["item_id"] for it in player_inv}
        has_space = item_id in existing_ids or len(player_inv) < inv_rows * inv_cols
        if not has_space:
            suffix = "\n*Inventory full! Remove items or equip a larger pouch.*"
        else:
            if item_id == "gold_coin":
                qty = chest_inv[sel]["quantity"]
                player.gold += qty
                await update_player_stats(db, user_id, gold=player.gold)
                await remove_from_chest(db, chest_id, item_id, qty)
                suffix = f"\n*Collected {qty} gold!*"
            else:
                await remove_from_chest(db, chest_id, item_id, 1)
                await add_to_inventory(db, user_id, item_id, 1)
                suffix = f"\n*Took {item_id.replace('_',' ').title()}.*"
    else:
        suffix = "\n*(Empty slot)*"

    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    new_sel = min(sel, max(0, len(chest_inv) - 1))
    _ui_state[user_id]["selected"] = new_sel
    content = render_chest(chest_inv, player_inv, new_sel, "chest",
                           chest_type, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, "chest"))


async def handle_chest_give(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Give selected player item to chest."""
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    sel = state.get("selected", 0)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)

    suffix = ""
    if sel < len(player_inv):
        item_id = player_inv[sel]["item_id"]
        chest_inv = await get_chest_items(db, chest_id)
        # Check chest capacity
        chest_sizes = {"cave_chest": (2,9), "cave_chest_medium": (3,9), "cave_chest_large": (4,9)}
        c_rows, c_cols = chest_sizes.get(chest_type, (2,9))
        c_capacity = c_rows * c_cols
        existing_chest_ids = {it["item_id"] for it in chest_inv}
        has_space = item_id in existing_chest_ids or len(chest_inv) < c_capacity
        if not has_space:
            suffix = "\n*Chest is full!*"
        else:
            await remove_from_inventory(db, user_id, item_id, 1)
            await add_to_chest(db, chest_id, item_id, 1)
            suffix = f"\n*Put {item_id.replace('_',' ').title()} in chest.*"
    else:
        suffix = "\n*(Empty slot)*"

    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    new_sel = min(sel, max(0, len(player_inv) - 1))
    _ui_state[user_id]["selected"] = new_sel
    content = render_chest(chest_inv, player_inv, new_sel, "player",
                           chest_type, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, "player"))


async def handle_chest_lootall(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Loot all chest items into player inventory up to capacity."""
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    max_cap = inv_rows * inv_cols
    existing_ids = {it["item_id"] for it in player_inv}

    taken, skipped = [], []
    for chest_item in chest_inv:
        item_id = chest_item["item_id"]
        qty = chest_item["quantity"]
        if item_id == "gold_coin":
            player.gold += qty
            await remove_from_chest(db, chest_id, item_id, qty)
            taken.append(f"{qty} gold")
            continue
        # Can we fit this item?
        player_inv_fresh = await get_inventory(db, user_id)
        cur_ids = {it["item_id"] for it in player_inv_fresh}
        if item_id in cur_ids or len(player_inv_fresh) < max_cap:
            await remove_from_chest(db, chest_id, item_id, qty)
            await add_to_inventory(db, user_id, item_id, qty)
            taken.append(item_id.replace('_',' ').title())
        else:
            skipped.append(item_id.replace('_',' ').title())

    if player.gold != (await get_or_create_player(db, user_id, interaction.user.display_name)).gold:
        await update_player_stats(db, user_id, gold=player.gold)

    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    suffix = ""
    if taken:
        suffix += f"\n*Looted: {', '.join(taken)}.*"
    if skipped:
        suffix += f"\n*Inventory full — left behind: {', '.join(skipped)}.*"
    if not taken and not skipped:
        suffix = "\n*Chest is empty.*"

    content = render_chest(chest_inv, player_inv, 0, "chest",
                           chest_type, inv_rows, inv_cols) + suffix
    _ui_state[user_id]["selected"] = 0
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, "chest"))


async def handle_chest_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Map / Help ────────────────────────────────────────────────────────────────

async def handle_map(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await interaction.response.defer(ephemeral=True)
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    from dwarf_explorer.world.world_map import generate_world_map
    buf = await generate_world_map(seed, db, player.world_x, player.world_y)
    file = discord.File(buf, filename="world_map.png")
    await interaction.followup.send(file=file, ephemeral=True)


async def handle_help(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    from dwarf_explorer.config import TERRAIN_EMOJI, STRUCTURE_EMOJI, ENTITY_EMOJI, ITEM_EMOJI
    lines = ["**Dwarf Explorer — Help**", "",
             "**Controls:**",
             "Arrow buttons = Move  |  🤚 Interact = Enter / examine / open",
             "🥾 = Toggle sprint (needs hiking boots)  |  🎒 Inventory  |  🗺️ Map", ""]
    lines.append("**Terrain:**")
    for name, emoji in TERRAIN_EMOJI.items():
        if name == "void": continue
        walkable = "\u2705" if name in WALKABLE_WILDERNESS else "\u274C"
        lines.append(f"{emoji} {name.replace('_',' ').title()} {walkable}")
    lines.append("")
    lines.append("**Structures:**")
    for name, emoji in STRUCTURE_EMOJI.items():
        lines.append(f"{emoji} {name.replace('_',' ').title()}")
    content = "\n".join(lines)
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        style=discord.ButtonStyle.primary, label="Back",
        emoji="\U0001F5FA\uFE0F",
        custom_id=f"dex:{guild_id}:{user_id}:help_back", row=0,
    ))
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


WALKABLE_WILDERNESS = {"sand", "plains", "grass", "forest", "hills", "path",
                       "sapling", "short_grass", "seedling"}


async def handle_help_back(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if player.in_house:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player)
    view = _game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
