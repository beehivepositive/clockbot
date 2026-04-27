from __future__ import annotations

import re as _re
import random as _random
from datetime import datetime, timedelta

import discord

from dwarf_explorer.config import (
    DIRECTIONS, SHOP_CATALOG, EQUIP_BONUSES, ITEM_EQUIP_SLOTS,
    TWO_HANDED_ITEMS, ITEM_SELL_PRICES, CAVE_ENEMY_TYPES, CAVE_CHEST_TYPES,
    CAVE_ENCOUNTER_RATES, CAVE_LEVEL_ENCOUNTER_RATES, ENEMY_STATS, COMBAT_MOVES_DEFAULT,
    POUCH_SIZES, SURFACE_ENCOUNTER_MOBS, CANOE_PASSABLE, WORLD_SIZE, FOOD_HP_RESTORE,
    CAVE_EMOJI, BUILDING_EMOJI, CRAFT_RECIPES,
    HOUSE_DECORATION_CATALOG, PLAYER_HOUSE_DECO_TILES, PH_CHEST_TYPES,
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
    get_or_create_ph_chest,
    get_chest_items,
    add_to_chest,
    remove_from_chest,
    get_farm_last_watered,
    set_farm_watered,
    get_treasure_map,
    set_treasure_map,
    mark_treasure_found,
    get_nearby_players,
    get_all_overworld_players,
)
from dwarf_explorer.game.combat import (
    build_arena_from_viewport,
    action_move, action_attack, action_flee, action_use_potion,
    resolve_enemy_turn, apply_victory, apply_death_reset,
    render_arena, ARENA_SIZE,
)
from dwarf_explorer.world.generator import load_viewport, load_single_tile
from dwarf_explorer.world.caves import get_or_create_cave, load_cave_viewport, load_cave_single_tile, populate_chest_loot
from dwarf_explorer.world.player_houses import (
    create_player_house, get_player_house_at, get_player_house_owner,
    delete_player_house, load_player_house_viewport, load_player_house_single_tile,
    set_player_house_tile, HOUSE_SPAWN_X, HOUSE_SPAWN_Y,
)
from dwarf_explorer.world.villages import (
    get_or_create_village, get_building_at,
    load_village_viewport, load_village_single_tile,
    load_building_viewport, load_building_single_tile,
)
from dwarf_explorer.game.player import Player, can_move, can_move_village, can_move_building
from dwarf_explorer.game.renderer import (
    render_grid, render_inventory, render_bank, render_shop, render_chest,
)

_CUSTOM_EMOJI_RE = _re.compile(r"^<a?:(\w+):(\d+)>$")


def _parse_emoji(s: str) -> discord.PartialEmoji | None:
    """Parse a custom emoji string '<:name:id>' into a PartialEmoji, or None for plain text."""
    m = _CUSTOM_EMOJI_RE.match(s)
    if m:
        return discord.PartialEmoji(name=m.group(1), id=int(m.group(2)))
    return None


# ── In-memory UI state (transient per user) ───────────────────────────────────
# {user_id: {"type": str, "selected": int, "bank_view": str, "mode": str}}
_ui_state: dict[int, dict] = {}


def _embed(content: str) -> discord.Embed:
    """Wrap game content in an embed to bypass Discord's 2000-char content limit."""
    return discord.Embed(description=content)


def _custom_id(guild_id: int, user_id: int, action: str) -> str:
    return f"dex:{guild_id}:{user_id}:{action}"


class GameView(discord.ui.View):
    """Main game view.

    Layout:
      Row 0: [Sprint/🥾] [⬆️] [⬇️] [Action] [🗺️ Map]
      Row 1: [⬅️] [Center/Interact] [➡️] [🎒 Inv] [❓ Help]

    center_label / center_enabled — on-tile contextual button (Enter cave, Chop, Harvest…)
    action_label / action_enabled — adjacent-tile contextual button (Forge, Smith, Fish…)
    """

    def __init__(self, guild_id: int, user_id: int, boots_equipped: bool = False,
                 sprinting: bool = False, mine_dirs: frozenset[str] = frozenset(),
                 center_label: str = "", center_enabled: bool = False,
                 action_label: str = "", action_enabled: bool = False):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self._build_buttons(boots_equipped, sprinting, mine_dirs,
                            center_label, center_enabled,
                            action_label, action_enabled)

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
                       mine_dirs: frozenset[str],
                       center_label: str, center_enabled: bool,
                       action_label: str, action_enabled: bool) -> None:
        sprint_style = discord.ButtonStyle.success if sprinting else discord.ButtonStyle.secondary

        # ── Row 0: Sprint | ⬆️ | Action | Map | spacer ───────────────────────
        #   Col:    0        1     2         3     4
        if boots_equipped:
            sprint_btn = discord.ui.Button(
                style=sprint_style,
                label="\U0001F97E",  # 🥾
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

        up_btn = self._dir_btn("up", "\u2B06\uFE0F", 0, "up" in mine_dirs)

        if action_enabled and action_label:
            action_btn = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=action_label,
                custom_id=_custom_id(self.guild_id, self.user_id, "action"),
                row=0,
            )
        else:
            action_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp2"),
                row=0,
            )

        map_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Map",
            emoji="\U0001F5FA\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "map"),
            row=0,
        )
        sp4_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(self.guild_id, self.user_id, "sp4"),
            row=0,
        )

        # ── Row 1: ⬅️ | Center | ➡️ | Inventory | Help ──────────────────────
        #   Col:   0     1         2     3             4
        left_btn  = self._dir_btn("left",  "\u2B05\uFE0F", 1, "left"  in mine_dirs)
        right_btn = self._dir_btn("right", "\u27A1\uFE0F", 1, "right" in mine_dirs)

        if center_enabled and center_label:
            _center_emoji = _parse_emoji(center_label)
            center_btn = discord.ui.Button(
                style=discord.ButtonStyle.success,
                **( {"emoji": _center_emoji, "label": None}
                    if _center_emoji else {"label": center_label} ),
                custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                row=1,
            )
        else:
            center_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                row=1,
            )

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

        # ── Row 2: spacer | ⬇️ | spacer ──────────────────────────────────────
        #   Col:   0         1     2
        #   ⬇️ sits directly below Center (col 1), ⬆️ above it (col 1) → clean cross
        sp3_btn  = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(self.guild_id, self.user_id, "sp3"),
            row=2,
        )
        down_btn = self._dir_btn("down", "\u2B07\uFE0F", 2, "down" in mine_dirs)
        sp5_btn  = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(self.guild_id, self.user_id, "sp5"),
            row=2,
        )

        for btn in [
            sprint_btn, up_btn, action_btn, map_btn, sp4_btn,   # row 0
            left_btn, center_btn, right_btn, inventory_btn, help_btn,  # row 1
            sp3_btn, down_btn, sp5_btn,                          # row 2
        ]:
            self.add_item(btn)


class InventoryView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int,
                 equip_label: str = "⚔️ Equip",
                 equip_action: str = "inv_equip",
                 selections: dict | None = None,
                 cursor_item_id: str | None = None,
                 sel_mode: str = "add"):
        super().__init__(timeout=None)
        selections = selections or {}
        cursor_selected = cursor_item_id is not None and cursor_item_id in selections

        # Row 0: ◀ | ▶ | Eat/Equip/Unequip | Select/Deselect | ❌ Close
        row0_items = [
            ("◀", "inv_prev", discord.ButtonStyle.secondary, False),
            ("▶", "inv_next", discord.ButtonStyle.secondary, False),
            (equip_label, equip_action, discord.ButtonStyle.primary, False),
            ("✖ Deselect" if cursor_selected else "✚ Select", "inv_select",
             discord.ButtonStyle.danger if cursor_selected else discord.ButtonStyle.secondary,
             cursor_item_id is None),  # disabled if no item under cursor
            ("❌ Close", "inv_close", discord.ButtonStyle.danger, False),
        ]
        for label, action, style, disabled in row0_items:
            self.add_item(discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(guild_id, user_id, action), row=0,
            ))

        # Row 1: selected item buttons (up to 5)
        from dwarf_explorer.game.renderer import _ITEM_SLOT_EMOJI as _ise
        sel_items = list(selections.items())  # [(item_id, qty), ...]
        for idx, (item_id, qty) in enumerate(sel_items[:5]):
            emoji_s = _ise.get(item_id, "📦")
            parsed_emoji = _parse_emoji(emoji_s)
            if parsed_emoji:
                # Custom Discord emoji: use emoji= param so it actually renders
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    emoji=parsed_emoji,
                    label=f"×{qty}",
                    custom_id=_custom_id(guild_id, user_id, f"inv_item_{idx}"),
                    row=1,
                ))
            else:
                # Unicode emoji: safe to embed directly in label
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.secondary,
                    label=f"{emoji_s}×{qty}",
                    custom_id=_custom_id(guild_id, user_id, f"inv_item_{idx}"),
                    row=1,
                ))

        # Row 2: Unselect All + mode toggle + Craft if recipe matches
        if selections:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="🗑 Unselect All",
                custom_id=_custom_id(guild_id, user_id, "inv_unselect_all"),
                row=2,
            ))
            mode_label = "➖ Sub" if sel_mode == "sub" else "➕ Add"
            mode_style = discord.ButtonStyle.danger if sel_mode == "sub" else discord.ButtonStyle.secondary
            self.add_item(discord.ui.Button(
                style=mode_style,
                label=mode_label,
                custom_id=_custom_id(guild_id, user_id, "inv_toggle_mode"),
                row=2,
            ))
            # Check if selections match any recipe
            sel_set = frozenset((k, v) for k, v in selections.items())
            if sel_set in CRAFT_RECIPES:
                recipe = CRAFT_RECIPES[sel_set]
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label=recipe["label"],
                    custom_id=_custom_id(guild_id, user_id, "inv_craft"),
                    row=2,
                ))


class InventoryItemView(discord.ui.View):
    """Sub-menu view shown when the player taps a selected-item button in InventoryView."""
    def __init__(self, guild_id: int, user_id: int, qty: int):
        super().__init__(timeout=None)
        for label, action, style, disabled in [
            ("+ More",   "inv_item_inc",   discord.ButtonStyle.secondary, False),
            ("− Less",   "inv_item_dec",   discord.ButtonStyle.secondary, qty <= 1),
            ("✖ Unselect", "inv_item_unsel", discord.ButtonStyle.danger,   False),
            ("↩ Back",   "inv_item_back",  discord.ButtonStyle.secondary, False),
        ]:
            self.add_item(discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(guild_id, user_id, action), row=0,
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
            action_label, action_id = "🪙 Buy", "shop_buy"
            mode_label, mode_id = "💲 Sell", "shop_mode"
        else:
            action_label, action_id = "🪙 Sell", "shop_sell"
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
    """Chest inventory view.

    Row 0 (always): ◀  ▶  Take/Give  🔄 Switch  ❌ Close
    Row 1 (chest only): 📦 Loot All
    """

    def __init__(self, guild_id: int, user_id: int, view_mode: str = "chest"):
        super().__init__(timeout=None)
        if view_mode == "chest":
            action_label, action_id = "📤 Take", "chest_take"
        else:
            action_label, action_id = "📥 Give", "chest_give"

        # Row 0: always present
        for label, act in [
            ("◀", "chest_prev"),
            ("▶", "chest_next"),
            (action_label, action_id),
            ("🔄 Switch", "chest_switch"),
            ("❌ Close", "chest_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))

        # Row 1: Loot All only on chest side
        if view_mode == "chest":
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="📦 Loot All",
                custom_id=_custom_id(guild_id, user_id, "chest_lootall"),
                row=1,
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

        # Row 1: ← · → 🍗 🏃  (center is always a spacer — cobweb escape via arrows)
        for label, action, dis in [
            ("⬅️", "c_left",  disabled),
            ("·",  "c_wait",  True),
            ("➡️", "c_right", disabled),
            ("🍗", "c_eat",   disabled),
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


# ── Canoe views ──────────────────────────────────────────────────────────────

class CanoeView(discord.ui.View):
    """8-directional canoe movement + Dock + Sail-to-destination."""

    def __init__(self, guild_id: int, user_id: int, dock_available: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label: str, action: str, row: int,
                 style=discord.ButtonStyle.primary, disabled: bool = False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: ↖ ↑ ↗ | 🏝️ Dock
        self.add_item(_btn("↖", "canoe_upleft",   0))
        self.add_item(_btn("⬆️", "canoe_up",       0))
        self.add_item(_btn("↗", "canoe_upright",  0))
        self.add_item(_btn("🏝️ Dock", "canoe_dock", 0,
                           style=discord.ButtonStyle.success,
                           disabled=not dock_available))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, "csp_a"), row=0,
        ))

        # Row 1: ← ⛵ → | 🗺️ Sail
        self.add_item(_btn("⬅️", "canoe_left",   1))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="⛵", disabled=True,
            custom_id=_custom_id(gid, uid, "csp_b"), row=1,
        ))
        self.add_item(_btn("➡️", "canoe_right",  1))
        self.add_item(_btn("🗺️ Sail", "canoe_sail", 1,
                           style=discord.ButtonStyle.secondary))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, "csp_c"), row=1,
        ))

        # Row 2: ↙ ↓ ↘ | 🎒 Inventory
        self.add_item(_btn("↙", "canoe_downleft",  2))
        self.add_item(_btn("⬇️", "canoe_down",      2))
        self.add_item(_btn("↘", "canoe_downright", 2))
        self.add_item(_btn("🎒", "inventory", 2,
                           style=discord.ButtonStyle.secondary))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, "csp_d"), row=2,
        ))


class CanoeDestView(discord.ui.View):
    """Shows up to 5 reachable landing destinations per page."""

    def __init__(self, guild_id: int, user_id: int, dests: list[tuple[int, int]],
                 page: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        per_page = 5
        total_pages = max(1, (len(dests) + per_page - 1) // per_page)
        page_dests = dests[page * per_page: page * per_page + per_page]

        # Row 0: up to 5 destination buttons
        for i, (dx, dy) in enumerate(page_dests):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=f"🏝️ ({dx},{dy})",
                custom_id=_custom_id(gid, uid, f"csail_{i}"),
                row=0,
            ))
        # Pad row 0 if fewer than 5 dests
        for i in range(len(page_dests), per_page):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
                custom_id=_custom_id(gid, uid, f"csp_{5 + i}"), row=0,
            ))

        # Row 1: prev / next / cancel
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="◀",
            disabled=(page == 0),
            custom_id=_custom_id(gid, uid, "csail_prev"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="▶",
            disabled=(page >= total_pages - 1),
            custom_id=_custom_id(gid, uid, "csail_next"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "csail_cancel"), row=1,
        ))


class MerchantView(discord.ui.View):
    """Travelling merchant trade view."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        for label, act, style in [
            ("◀",       "merch_prev",  discord.ButtonStyle.secondary),
            ("▶",       "merch_next",  discord.ButtonStyle.secondary),
            ("🪙 Buy",  "merch_buy",   discord.ButtonStyle.success),
            ("👋 Leave", "merch_close", discord.ButtonStyle.danger),
        ]:
            self.add_item(discord.ui.Button(
                style=style, label=label,
                custom_id=_custom_id(guild_id, user_id, act), row=0,
            ))


class ForgeView(discord.ui.View):
    """Forge interaction menu: smelt iron ore into ingots."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        for label, act, style in [
            ("🧱 Smelt (3 ore → 1 ingot)", "forge_iron",  discord.ButtonStyle.primary),
            ("❌ Close",                   "forge_close", discord.ButtonStyle.danger),
        ]:
            self.add_item(discord.ui.Button(
                style=style, label=label,
                custom_id=_custom_id(guild_id, user_id, act), row=0,
            ))


class AnvilView(discord.ui.View):
    """Anvil interaction menu: craft weapons and armor from iron ingots."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        for label, act, style, row in [
            ("🗡️ Dagger (1 ingot)",     "anvil_dagger",      discord.ButtonStyle.primary, 0),
            ("⚔️ Sword (2 ingots)",     "anvil_sword",       discord.ButtonStyle.primary, 0),
            ("🪖 Helmet (2 ingots)",    "anvil_helmet",      discord.ButtonStyle.primary, 0),
            ("🛡️ Chestplate (4 ingots)","anvil_chestplate",  discord.ButtonStyle.primary, 1),
            ("👕 Leggings (3 ingots)",  "anvil_leggings",    discord.ButtonStyle.primary, 1),
            ("❌ Close",                "anvil_close",        discord.ButtonStyle.danger,  1),
        ]:
            self.add_item(discord.ui.Button(
                style=style, label=label,
                custom_id=_custom_id(guild_id, user_id, act), row=row,
            ))


class PlayerHouseEditView(discord.ui.View):
    """Edit mode for player-built houses: navigate + add decoration + remove + delete + close."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _sp(tag: str) -> discord.ui.Button:
            return discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
                custom_id=_custom_id(gid, uid, tag),
            )

        # Row 0: [spacer] [⬆️] [spacer] [➕ Add] [🗑 Delete]
        sp1 = _sp("hesp1"); sp1.row = 0
        up_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="⬆️",
                                   custom_id=_custom_id(gid, uid, "hedit_up"), row=0)
        sp2 = _sp("hesp2"); sp2.row = 0
        add_btn = discord.ui.Button(style=discord.ButtonStyle.success, label="➕ Add",
                                    custom_id=_custom_id(gid, uid, "hedit_add"), row=0)
        del_btn = discord.ui.Button(style=discord.ButtonStyle.danger, label="🗑 Delete House",
                                    custom_id=_custom_id(gid, uid, "hedit_delete"), row=0)

        # Row 1: [⬅️] [✖ Remove] [➡️] [❌ Close]
        left_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="⬅️",
                                     custom_id=_custom_id(gid, uid, "hedit_left"), row=1)
        rem_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, label="✖ Remove",
                                    custom_id=_custom_id(gid, uid, "hedit_remove"), row=1)
        right_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="➡️",
                                      custom_id=_custom_id(gid, uid, "hedit_right"), row=1)
        close_btn = discord.ui.Button(style=discord.ButtonStyle.danger, label="❌ Close Edit",
                                      custom_id=_custom_id(gid, uid, "hedit_close"), row=1)

        # Row 2: [spacer] [⬇️]
        sp3 = _sp("hesp3"); sp3.row = 2
        down_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="⬇️",
                                     custom_id=_custom_id(gid, uid, "hedit_down"), row=2)

        for btn in [sp1, up_btn, sp2, add_btn, del_btn,
                    left_btn, rem_btn, right_btn, close_btn,
                    sp3, down_btn]:
            self.add_item(btn)


class HouseDecorationView(discord.ui.View):
    """Select a decoration to place in a player house."""

    def __init__(self, guild_id: int, user_id: int, page: int = 0, selected: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        catalog = HOUSE_DECORATION_CATALOG
        per_page = 5
        total_pages = max(1, (len(catalog) + per_page - 1) // per_page)
        page_items = catalog[page * per_page: page * per_page + per_page]

        # Row 0: up to 5 decoration item buttons
        for i, item in enumerate(page_items):
            abs_idx = page * per_page + i
            cost_str = "+".join(f"{v}{k}" for k, v in item["cost"].items())
            lbl = f"{item['name']} ({cost_str})"
            style = discord.ButtonStyle.success if abs_idx == selected else discord.ButtonStyle.secondary
            self.add_item(discord.ui.Button(
                style=style, label=lbl,
                custom_id=_custom_id(gid, uid, f"hdeco_sel_{abs_idx}"),
                row=0,
            ))
        # Pad row 0 to 5 buttons
        for i in range(len(page_items), per_page):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
                custom_id=_custom_id(gid, uid, f"hdsp_{i}"), row=0,
            ))

        # Row 1: ◀ ▶ Place Cancel
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="◀", disabled=(page == 0),
            custom_id=_custom_id(gid, uid, "hdeco_prev"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="▶", disabled=(page >= total_pages - 1),
            custom_id=_custom_id(gid, uid, "hdeco_next"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, label="🏗️ Place",
            custom_id=_custom_id(gid, uid, "hdeco_place"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "hdeco_cancel"), row=1,
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


def _inv_action_btn(items: list[dict], selected: int, equipped: dict) -> tuple[str, str]:
    """Return (button_label, button_action) for the primary inventory action button."""
    if selected < len(items):
        item_id = items[selected]["item_id"]
        if item_id in FOOD_HP_RESTORE:
            return ("🍗 Eat", "inv_eat")
        if item_id in equipped.values():
            return ("↩ Unequip", "inv_equip")
    return ("⚔️ Equip", "inv_equip")


def _equip_label(items: list[dict], selected: int, equipped: dict) -> str:
    """Legacy helper — returns the display label only (no action id)."""
    return _inv_action_btn(items, selected, equipped)[0]


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

def _compute_context_labels(
    grid: list[list],
    player: Player,
    hand_items: set[str],
) -> tuple[str, bool, str, bool]:
    """Return (center_label, center_enabled, action_label, action_enabled).

    center = on-tile interaction (interact button at row-1 center)
    action = adjacent-tile interaction (action button at row-0 right)
    """
    vc = 4  # VIEWPORT_CENTER

    center_label, center_enabled = "", False
    action_label, action_enabled = "", False

    if not grid or len(grid) <= vc:
        return center_label, center_enabled, action_label, action_enabled

    # ── Inside a player house ─────────────────────────────────────────────────
    _in_ph = player.in_house and player.house_type == "player_house"
    if _in_ph:
        if _ui_state.get(player.user_id, {}).get("is_house_owner", False):
            action_label, action_enabled = "⚒️ Edit", True
        # Fall through to center_tile checks so b_stove etc. still work.
        # PH chests are handled after the main block below.

    center_tile = grid[vc][vc] if len(grid[vc]) > vc else None
    if center_tile:
        t = center_tile.terrain
        s = center_tile.structure

        # Structural overrides (cave/village on overworld)
        if s == "player_house":
            center_label, center_enabled = "🏠", True
        elif t == "player_house_cave":
            center_label, center_enabled = "🏠", True
        elif s == "cave":
            center_label, center_enabled = "🕳️", True
        elif s == "village":
            center_label, center_enabled = "🏘️", True
        # Canoe launch
        elif t == "river_landing":
            center_label, center_enabled = "⛵", True
        # Cave chest — use custom chest emoji if available
        elif t in CAVE_CHEST_TYPES:
            center_label, center_enabled = CAVE_EMOJI.get(t, "📦"), True
        # Cave exit / building door / village buildings (enter)
        elif t in ("cave_entrance", "b_door"):
            center_label, center_enabled = "🚪", True
        elif t in ("vil_house", "vil_church", "vil_bank", "vil_shop", "vil_blacksmith"):
            center_label, center_enabled = "🚪", True
        # Building NPCs (on-tile)
        elif t == "b_bank_npc":
            center_label, center_enabled = "🏦", True
        elif t == "b_shop_npc":
            center_label, center_enabled = "🛒", True
        elif t == "b_stove":
            center_label, center_enabled = "🔥", True
        elif t == "b_blacksmith_npc":
            center_label, center_enabled = "⚒️", True
        elif t == "b_priest":
            center_label, center_enabled = "💬", True
        elif t == "b_altar":
            center_label, center_enabled = "⛩️", True
        elif t == "b_safe":
            center_label, center_enabled = "🔒", True
        elif t == "vil_well":
            center_label, center_enabled = "⛲", True
        # Tool × terrain interactions
        elif t in ("forest", "dense_forest") and "axe" in hand_items:
            center_label, center_enabled = "🪓", True
        elif t == "crop_ripe":
            center_label, center_enabled = "🌻", True
        elif t in ("crop_planted", "crop_sprout") and "watering_can" in hand_items:
            center_label, center_enabled = "💧", True
        elif t in ("sapling", "short_grass", "seedling") and "watering_can" in hand_items:
            center_label, center_enabled = "💧", True
        elif t == "farmland" and "seed" in hand_items:
            center_label, center_enabled = "🌱", True
        elif t in ("path", "farmland") and "sapling" in hand_items:
            center_label, center_enabled = "🌱", True
        elif t == "path" and "seed" in hand_items:
            center_label, center_enabled = "🌱", True
        elif t == "sapling" and "shovel" in hand_items:
            center_label, center_enabled = "⛏️", True
        elif t in ("grass", "plains", "sand") and "shovel" in hand_items:
            center_label, center_enabled = "⛏️", True
        elif t in ("grass", "plains") and "knife" in hand_items:
            center_label, center_enabled = "✂️", True
        # Item-based interactions (lower priority)
        elif "cooked_fish" in hand_items or "fish" in hand_items:
            center_label, center_enabled = "🍗", True
        elif "map_fragment" in hand_items:
            center_label, center_enabled = "🗺️", True
        elif "shovel" in hand_items:
            # Could be digging a treasure; handler checks coordinates
            center_label, center_enabled = "⛏️", True

    # ── Action label: adjacent-tile interactions ──────────────────────────────
    adj_terrains: set[str] = set()
    for ro, co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        r, c = vc + ro, vc + co
        if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
            adj = grid[r][c]
            if adj.terrain:
                adj_terrains.add(adj.terrain)
            if adj.structure:
                adj_terrains.add(adj.structure)

    if "b_forge" in adj_terrains:
        action_label, action_enabled = "🔥 Forge", True
    elif "b_anvil" in adj_terrains:
        action_label, action_enabled = "⚒️ Smith", True
    elif "b_shop_npc" in adj_terrains:
        action_label, action_enabled = "🛒 Shop", True
    elif "b_bank_npc" in adj_terrains:
        action_label, action_enabled = "🏦 Bank", True
    elif "fishing_rod" in hand_items and adj_terrains & {"river", "bridge", "shallow_water", "deep_water"}:
        action_label, action_enabled = "🎣 Fish", True
    elif not action_enabled and center_tile and not player.in_house and "house_kit" in hand_items:
        # Offer to build a house on the current tile if house_kit is equipped and tile is buildable
        _bt = center_tile.terrain
        _build_ok = (
            not center_tile.structure
            and center_tile.walkable
            and _bt not in {"void", "deep_water", "shallow_water", "river", "river_landing",
                            "mountain", "snow", "player_house_cave"}
        )
        if _build_ok:
            action_label, action_enabled = "🏠 Build", True

    # ── Player-house chest override (highest priority for center label) ────────
    if _in_ph and center_tile and center_tile.terrain in PH_CHEST_TYPES:
        center_label, center_enabled = BUILDING_EMOJI.get(center_tile.terrain, "📦"), True

    return center_label, center_enabled, action_label, action_enabled


async def _load_house_grid(player: Player, db) -> list[list]:
    """Load the correct viewport for whichever house type the player is in."""
    if player.house_type == "player_house":
        return await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    return await load_building_viewport(player.house_id, player.house_x, player.house_y, db)


def _game_view(guild_id: int, user_id: int, player: Player,
               mine_dirs: frozenset[str] = frozenset(),
               grid: list[list] | None = None) -> discord.ui.View:
    """Build the appropriate game view, computing context labels if grid is provided."""
    if player.in_canoe:
        return CanoeView(guild_id, user_id, dock_available=False)

    center_label, center_enabled = "", False
    action_label, action_enabled = "", False

    if grid is not None:
        hand_items: set[str] = set()
        if player.hand_1:
            hand_items.add(player.hand_1)
        if player.hand_2:
            hand_items.add(player.hand_2)
        center_label, center_enabled, action_label, action_enabled = _compute_context_labels(
            grid, player, hand_items
        )

    return GameView(guild_id, user_id,
                    boots_equipped=(player.boots is not None),
                    sprinting=player.sprinting,
                    mine_dirs=mine_dirs,
                    center_label=center_label,
                    center_enabled=center_enabled,
                    action_label=action_label,
                    action_enabled=action_enabled)


async def _cave_game_view(guild_id: int, user_id: int, player: Player, db,
                           grid: list[list] | None = None) -> GameView:
    """Build a GameView with mine buttons for any adjacent cave_rock tiles."""
    mine_dirs: set[str] = set()
    if player.in_cave:
        for direction, (dx, dy) in DIRECTIONS.items():
            tile = await load_cave_single_tile(
                player.cave_id, player.cave_x + dx, player.cave_y + dy, db
            )
            if tile.terrain == "cave_rock":
                mine_dirs.add(direction)
    return _game_view(guild_id, user_id, player, frozenset(mine_dirs), grid=grid)


_CANOE_DIRS: dict[str, tuple[int, int]] = {
    "up":        (0, -1),
    "down":      (0, 1),
    "left":      (-1, 0),
    "right":     (1, 0),
    "upleft":    (-1, -1),
    "upright":   (1, -1),
    "downleft":  (-1, 1),
    "downright": (1, 1),
}


async def _adjacent_landing(player, seed: int, db) -> tuple[int, int] | None:
    """Return the first adjacent river_landing tile, or None."""
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if t.terrain == "river_landing":
                return (ax, ay)
    return None


async def _is_adjacent_to_water(player: Player, seed: int, db) -> bool:
    """Return True if any of the 4 cardinal neighbours is a river/water tile."""
    water_types = {"river", "bridge", "shallow_water", "deep_water"}
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if (t.structure or t.terrain) in water_types:
                return True
    return False


async def _find_treasure_location(user_id: int, world_seed: int, db) -> tuple[int, int]:
    """Pick a deterministic random walkable overworld tile ≥40 tiles from spawn."""
    from dwarf_explorer.config import WALKABLE_TILES as _WT
    rng = _random.Random(hash((user_id, world_seed, "treasure_v1")))
    cx, cy = WORLD_SIZE // 2, WORLD_SIZE // 2
    for _ in range(300):
        tx = rng.randint(10, WORLD_SIZE - 11)
        ty = rng.randint(10, WORLD_SIZE - 11)
        if abs(tx - cx) + abs(ty - cy) < 40:
            continue
        t = await load_single_tile(tx, ty, world_seed, db)
        if t.terrain in _WT and t.terrain not in ("river_landing", "cave") and not t.structure:
            return tx, ty
    return cx + 45, cy + 45


async def _find_canoe_destinations(
    player, db
) -> list[tuple[int, int]]:
    """BFS through connected river/bridge tiles; return reachable landing positions."""
    # Load river/bridge tile set from DB
    water_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides"
        " WHERE tile_type IN ('river', 'bridge')"
    )
    water_set: set[tuple[int, int]] = {(r["world_x"], r["world_y"]) for r in water_rows}

    start = (player.world_x, player.world_y)
    if start not in water_set:
        return []

    # Load all river_landing positions
    land_rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'river_landing'"
    )
    all_landings: set[tuple[int, int]] = {(r["world_x"], r["world_y"]) for r in land_rows}

    # BFS (8-directional, limited to 10 000 tiles)
    visited: set[tuple[int, int]] = {start}
    queue = [start]
    head = 0
    while head < len(queue) and len(visited) < 10_000:
        x, y = queue[head]; head += 1
        for ddx, ddy in ((0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)):
            nb = (x + ddx, y + ddy)
            if nb not in visited and nb in water_set:
                visited.add(nb)
                queue.append(nb)

    # Collect landings adjacent to reachable water (cardinal only for embark)
    found: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for lx, ly in all_landings:
        if (lx, ly) in seen:
            continue
        for ddx, ddy in ((0,1),(0,-1),(1,0),(-1,0)):
            if (lx + ddx, ly + ddy) in visited:
                found.append((lx, ly))
                seen.add((lx, ly))
                break

    # Sort by distance from player, skip current player position's adjacent landing
    px, py = player.world_x, player.world_y
    found.sort(key=lambda p: (p[0] - px) ** 2 + (p[1] - py) ** 2)
    # Remove the landing the player is right next to (distance 1) to avoid "sail to here"
    found = [(lx, ly) for lx, ly in found
             if abs(lx - px) + abs(ly - py) > 1]
    return found


def _generate_merchant_catalog(rng: _random.Random) -> list[dict]:
    """Pick 5 random shop items at 130% price for a travelling merchant."""
    items = rng.sample(SHOP_CATALOG, min(5, len(SHOP_CATALOG)))
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "emoji": item.get("emoji", "📦"),
            "price": int(item["price"] * 1.3 + 0.5),
            "description": item.get("description", ""),
        }
        for item in items
    ]


def _render_merchant(catalog: list[dict], selected: int, player) -> str:
    lines = ["🧑‍💼 **A travelling merchant stops you!**\n"]
    for i, item in enumerate(catalog):
        prefix = "▶ " if i == selected else "  "
        lines.append(f"{prefix}{item.get('emoji','📦')} **{item['name']}** — {item['price']}g")
    lines.append(f"\n🪙 You have **{player.gold}g**")
    if 0 <= selected < len(catalog):
        desc = catalog[selected].get("description", "")
        if desc:
            lines.append(f"*{desc}*")
    return "\n".join(lines)


def _roll_encounter(rng: _random.Random, rates: dict | None = None) -> str | None:
    """Roll for a random cave encounter. Returns enemy_type or None.

    Rolls once for a 7% encounter chance, then picks a mob by relative weight
    (values in `rates` are used as weights, not independent probabilities).
    """
    if rates is None:
        rates = CAVE_ENCOUNTER_RATES
    if rng.random() >= 0.07:
        return None
    total = sum(rates.values())
    if total <= 0:
        return None
    roll = rng.random() * total
    for enemy_type, weight in rates.items():
        roll -= weight
        if roll <= 0:
            return enemy_type
    return list(rates.keys())[-1]


async def _move_steps(
    player: Player, direction: str, steps: int, seed: int, db,
    guild_id: int, user_id: int,
) -> tuple[str, discord.ui.View]:
    """Move player 1 or 2 tiles, returning (content, view)."""
    vec = _CANOE_DIRS.get(direction, DIRECTIONS.get(direction, (0, 0)))
    dx, dy = vec

    if player.in_canoe:
        nx, ny = player.world_x + dx, player.world_y + dy
        if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            return render_grid(grid, player, "You've reached the edge of the world!"), \
                   CanoeView(guild_id, user_id, dock_available=False)
        target = await load_single_tile(nx, ny, seed, db)
        t = target.structure or target.terrain
        if t not in CANOE_PASSABLE:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            return render_grid(grid, player, "You can't paddle onto land. Dock at a 🏝️ landing first."), \
                   CanoeView(guild_id, user_id, dock_available=await _adjacent_landing(player, seed, db) is not None)
        player.world_x, player.world_y = nx, ny
        await update_player_position(db, user_id, nx, ny)
        landing = await _adjacent_landing(player, seed, db)
        grid = await load_viewport(nx, ny, seed, db)
        return render_grid(grid, player), CanoeView(guild_id, user_id, dock_available=(landing is not None))

    if player.in_house:
        _is_ph = (player.house_type == "player_house")
        for _ in range(steps):
            nx, ny = player.house_x + dx, player.house_y + dy
            if _is_ph:
                target = await load_player_house_single_tile(player.house_id, nx, ny, db)
            else:
                target = await load_building_single_tile(player.house_id, nx, ny, db)
            if target.terrain == "b_door":
                # Auto-exit house on walking into door
                vx, vy = player.house_vx, player.house_vy
                player.in_house = False
                player.house_id = None
                await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
                if _is_ph:
                    if player.ph_cave_id is not None:
                        # Return to cave
                        cid = player.ph_cave_id
                        player.cave_id = cid
                        player.cave_x, player.cave_y = vx, vy
                        player.in_cave = True
                        player.ph_cave_id = None
                        await update_player_cave_state(db, user_id, True, cid, vx, vy)
                        grid = await load_cave_viewport(cid, vx, vy, db)
                        return render_grid(grid, player, "You step outside."), \
                               await _cave_game_view(guild_id, user_id, player, db, grid=grid)
                    else:
                        # Return to overworld
                        player.world_x, player.world_y = vx, vy
                        await update_player_position(db, user_id, vx, vy)
                        grid = await load_viewport(vx, vy, seed, db)
                        return render_grid(grid, player, "You step outside."), \
                               _game_view(guild_id, user_id, player, grid=grid)
                else:
                    # Return to village
                    player.village_x, player.village_y = vx, vy
                    await update_player_village_state(
                        db, user_id, True, player.village_id,
                        vx, vy, player.village_wx, player.village_wy,
                    )
                    grid = await load_village_viewport(player.village_id, vx, vy, db)
                    return render_grid(grid, player, "You step outside."), \
                           _game_view(guild_id, user_id, player, grid=grid)
            allowed, reason = can_move_building(target)
            if not allowed:
                if _is_ph:
                    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
                else:
                    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player, grid=grid)
            player.house_x, player.house_y = nx, ny
            await update_player_house_state(
                db, user_id, True, player.house_id,
                nx, ny, player.house_vx, player.house_vy, player.house_type,
            )
        if _is_ph:
            grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
        else:
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
        # If in edit mode, return edit view
        if _ui_state.get(user_id, {}).get("type") == "house_edit":
            return render_grid(grid, player), PlayerHouseEditView(guild_id, user_id)
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

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
                return render_grid(grid, player, "You leave the village."), _game_view(guild_id, user_id, player, grid=grid)
            allowed, reason = can_move_village(target)
            if not allowed:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player, grid=grid)
            player.village_x, player.village_y = nx, ny
            await update_player_village_state(
                db, user_id, True, player.village_id,
                nx, ny, player.village_wx, player.village_wy,
            )
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

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
                           await _cave_game_view(guild_id, user_id, player, db, grid=grid)

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
                           await _cave_game_view(guild_id, user_id, player, db, grid=grid)
                # No parent cave — treat as normal floor
                player.cave_x, player.cave_y = nx, ny
                await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                return render_grid(grid, player), await _cave_game_view(guild_id, user_id, player, db, grid=grid)

            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                return render_grid(grid, player, reason), await _cave_game_view(guild_id, user_id, player, db, grid=grid)
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
        return render_grid(grid, player), await _cave_game_view(guild_id, user_id, player, db, grid=grid)

    else:
        for _ in range(steps):
            nx, ny = player.world_x + dx, player.world_y + dy
            target = await load_single_tile(nx, ny, seed, db)
            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_viewport(player.world_x, player.world_y, seed, db)
                nearby = await get_nearby_players(db, user_id, player.world_x, player.world_y)
                return render_grid(grid, player, reason, other_players=nearby), _game_view(guild_id, user_id, player, grid=grid)
            player.world_x, player.world_y = nx, ny
            await update_player_position(db, user_id, nx, ny)
            # 0.2% travelling merchant encounter
            merch_rng = _random.Random(hash((user_id, nx, ny, player.xp // 20, "merchant")))
            if merch_rng.random() < 0.002 and not player.in_combat:
                catalog = _generate_merchant_catalog(merch_rng)
                _ui_state[user_id] = {"type": "merchant", "catalog": catalog, "selected": 0}
                grid = await load_viewport(nx, ny, seed, db)
                content = _render_merchant(catalog, 0, player)
                view = MerchantView(guild_id, user_id)
                return content, view
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
        nearby = await get_nearby_players(db, user_id, player.world_x, player.world_y)
        return render_grid(grid, player, other_players=nearby), _game_view(guild_id, user_id, player, grid=grid)


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
        player.in_canoe = False
        await update_player_stats(db, user_id, hp=player.hp, in_canoe=0)
        await update_player_cave_state(db, user_id, False, None, 0, 0)
        await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        await update_player_position(db, user_id, player.world_x, player.world_y)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        return render_grid(grid, player, f"{extra_msg} {msg}"), _game_view(guild_id, user_id, player, grid=grid)

    await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
    # Return to the appropriate location view
    if player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        return render_grid(grid, player, extra_msg), await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    return render_grid(grid, player, extra_msg), _game_view(guild_id, user_id, player, grid=grid)


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


async def handle_combat_eat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    # Prefer cooked_fish, then fish
    for food_id in ("cooked_fish", "fish"):
        row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, food_id)
        )
        if row:
            await remove_from_inventory(db, user_id, food_id, 1)
            heal_amt = FOOD_HP_RESTORE.get(food_id, 15)
            heal = min(heal_amt, player.max_hp - player.hp)
            player.hp += heal
            player.combat_moves_left -= 1
            msg = f"🍗 You eat {food_id.replace('_', ' ')}! Restored **{heal}** HP. ({player.hp}/{player.max_hp})"
            await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)
            return
    arena["combat_log"].append("You have no food! Fish and cook at a hearth for HP recovery.")
    content = render_arena(arena, player)
    view = _combat_view(guild_id, user_id, arena, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)



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
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    tile = await load_cave_single_tile(player.cave_id, nx, ny, db)
    if tile.terrain != "cave_rock":
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        content = render_grid(grid, player, "That rock has already been mined.")
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    rng = _random.Random(hash((user_id, nx, ny, player.xp)))
    await db.execute(
        "UPDATE cave_tiles SET tile_type='stone_floor'"
        " WHERE cave_id=? AND local_x=? AND local_y=?",
        (player.cave_id, nx, ny),
    )
    # Record break time for 48h regeneration
    await db.execute(
        "INSERT OR REPLACE INTO cave_rock_breaks (cave_id, local_x, local_y, broken_at)"
        " VALUES (?, ?, ?, datetime('now'))",
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
    view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
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
        grid = await _load_house_grid(player, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    content = render_grid(grid, player, status)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Canoe handlers ───────────────────────────────────────────────────────────

async def handle_canoe_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not player.in_canoe:
        # Fallback: player got off canoe somehow
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        await interaction.response.edit_message(
            embed=_embed(render_grid(grid, player)), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return
    content, view = await _move_steps(player, direction, 1, seed, db, guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_canoe_dock(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_canoe:
        await interaction.response.defer()
        return

    landing = await _adjacent_landing(player, seed, db)
    if not landing:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "No landing nearby to dock at.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=CanoeView(guild_id, user_id, dock_available=False),
        )
        return

    lx, ly = landing
    player.world_x, player.world_y = lx, ly
    player.in_canoe = False
    await update_player_stats(db, user_id, world_x=lx, world_y=ly, in_canoe=0)
    grid = await load_viewport(lx, ly, seed, db)
    content = render_grid(grid, player, "You dock the canoe at the landing.")
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player),
    )


async def handle_canoe_sail(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open destination picker for canoe fast-travel."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_canoe:
        await interaction.response.defer()
        return

    dests = await _find_canoe_destinations(player, db)
    if not dests:
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "No reachable landings found on this waterway.")
        landing = await _adjacent_landing(player, seed, db)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=CanoeView(guild_id, user_id, dock_available=(landing is not None)),
        )
        return

    _ui_state[user_id] = {"type": "canoe_dest", "dests": dests, "page": 0}
    dest_lines = "\n".join(
        f"**{i+1}.** 🏝️ ({lx}, {ly})"
        for i, (lx, ly) in enumerate(dests[:5])
    )
    total = len(dests)
    page_count = max(1, (total + 4) // 5)
    content = (
        f"🗺️ **Choose a destination** (Page 1/{page_count})\n"
        f"{dest_lines}\n\n"
        f"*{total} landing{'s' if total != 1 else ''} reachable on this waterway.*"
    )
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeDestView(guild_id, user_id, dests, page=0),
    )


async def handle_canoe_dest(
    interaction: discord.Interaction, guild_id: int, user_id: int, idx: int
) -> None:
    """Teleport canoe to selected landing's adjacent water tile."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    dests = state.get("dests", [])
    page = state.get("page", 0)
    abs_idx = page * 5 + idx
    if abs_idx >= len(dests):
        await interaction.response.defer()
        return

    lx, ly = dests[abs_idx]
    # Find a water tile adjacent to the landing for the canoe to sit at
    water_tile: tuple[int, int] | None = None
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = lx + ddx, ly + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if (t.structure or t.terrain) in CANOE_PASSABLE:
                water_tile = (ax, ay)
                break

    if not water_tile:
        # Landing has no adjacent water — place on landing itself (rare edge case)
        player.world_x, player.world_y = lx, ly
        player.in_canoe = False
        await update_player_stats(db, user_id, world_x=lx, world_y=ly, in_canoe=0)
        _ui_state.pop(user_id, None)
        grid = await load_viewport(lx, ly, seed, db)
        content = render_grid(grid, player, f"You sail to the landing at ({lx},{ly}).")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return

    wx, wy = water_tile
    player.world_x, player.world_y = wx, wy
    await update_player_position(db, user_id, wx, wy)
    _ui_state.pop(user_id, None)
    grid = await load_viewport(wx, wy, seed, db)
    content = render_grid(grid, player, f"You sail to the landing at ({lx},{ly}). Dock to go ashore.")
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeView(guild_id, user_id, dock_available=True),
    )


async def handle_canoe_dest_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    dests = state.get("dests", [])
    page = state.get("page", 0)
    total_pages = max(1, (len(dests) + 4) // 5)
    new_page = max(0, min(total_pages - 1, page + delta))
    _ui_state[user_id] = {"type": "canoe_dest", "dests": dests, "page": new_page}
    page_dests = dests[new_page * 5: new_page * 5 + 5]
    dest_lines = "\n".join(
        f"**{new_page*5+i+1}.** 🏝️ ({lx}, {ly})"
        for i, (lx, ly) in enumerate(page_dests)
    )
    content = (
        f"🗺️ **Choose a destination** (Page {new_page+1}/{total_pages})\n"
        f"{dest_lines}\n\n"
        f"*{len(dests)} landing{'s' if len(dests) != 1 else ''} reachable.*"
    )
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeDestView(guild_id, user_id, dests, page=new_page),
    )


async def handle_canoe_dest_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    _ui_state.pop(user_id, None)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    landing = await _adjacent_landing(player, seed, db)
    content = render_grid(grid, player)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeView(guild_id, user_id, dock_available=(landing is not None)),
    )


# ── Merchant handlers ────────────────────────────────────────────────────────

async def handle_merchant_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    if state.get("type") != "merchant":
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        await interaction.response.edit_message(
            embed=_embed(render_grid(grid, player)), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return
    catalog = state["catalog"]
    new_sel = (state["selected"] + delta) % max(1, len(catalog))
    _ui_state[user_id]["selected"] = new_sel
    content = _render_merchant(catalog, new_sel, player)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=MerchantView(guild_id, user_id))


async def handle_merchant_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    if state.get("type") != "merchant":
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        await interaction.response.edit_message(
            embed=_embed(render_grid(grid, player)), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return
    catalog = state["catalog"]
    sel = state.get("selected", 0)
    if sel >= len(catalog):
        await interaction.response.defer()
        return
    item = catalog[sel]
    if player.gold < item["price"]:
        content = _render_merchant(catalog, sel, player) + f"\n\n*Not enough gold!*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=MerchantView(guild_id, user_id))
        return
    player.gold -= item["price"]
    await update_player_stats(db, user_id, gold=player.gold)
    await add_to_inventory(db, user_id, item["id"], 1)
    content = _render_merchant(catalog, sel, player) + f"\n\n*Bought {item['name']}!*"
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=MerchantView(guild_id, user_id))


async def handle_merchant_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    _ui_state.pop(user_id, None)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player, "The merchant waves farewell and continues on their way.")
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


# ── Interact ──────────────────────────────────────────────────────────────────

async def handle_interact(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.in_house:
        _is_ph = (player.house_type == "player_house")
        if _is_ph:
            htile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
        else:
            htile = await load_building_single_tile(player.house_id, player.house_x, player.house_y, db)

        if htile.terrain == "b_door":
            vx, vy = player.house_vx, player.house_vy
            player.in_house = False
            await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
            if _is_ph:
                if player.ph_cave_id is not None:
                    cid = player.ph_cave_id
                    player.cave_id = cid
                    player.cave_x, player.cave_y = vx, vy
                    player.in_cave = True
                    player.ph_cave_id = None
                    await update_player_cave_state(db, user_id, True, cid, vx, vy)
                    grid = await load_cave_viewport(cid, vx, vy, db)
                    content = render_grid(grid, player, "You step outside.")
                    view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
                else:
                    player.world_x, player.world_y = vx, vy
                    await update_player_position(db, user_id, vx, vy)
                    grid = await load_viewport(vx, vy, seed, db)
                    content = render_grid(grid, player, "You step outside.")
                    view = _game_view(guild_id, user_id, player, grid=grid)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
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

        elif htile.terrain in PH_CHEST_TYPES and _is_ph:
            chest_id = await get_or_create_ph_chest(
                db, player.house_id, player.house_x, player.house_y, htile.terrain
            )
            chest_inv = await get_chest_items(db, chest_id)
            player_inv = await get_inventory(db, user_id)
            inv_rows, inv_cols = _inv_capacity(player)
            _ui_state[user_id] = {
                **_ui_state.get(user_id, {}),
                "type": "chest",
                "chest_id": chest_id,
                "chest_type": htile.terrain,
                "selected": 0,
                "chest_view": "chest",
            }
            content = render_chest(chest_inv, player_inv, 0, "chest",
                                   htile.terrain, inv_rows, inv_cols)
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=ChestView(guild_id, user_id, "chest"),
            )
            return

        else:
            # Generic tile interactions (same for village buildings and player houses)
            async def _load_house_grid():
                if _is_ph:
                    return await load_player_house_viewport(
                        player.house_id, player.house_x, player.house_y, db)
                return await load_building_viewport(
                    player.house_id, player.house_x, player.house_y, db)

            if htile.terrain == "b_stove":
                fish_row = await db.fetch_one(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='fish'", (user_id,)
                )
                grid = await _load_house_grid()
                if fish_row and fish_row["quantity"] > 0:
                    count = fish_row["quantity"]
                    await remove_from_inventory(db, user_id, "fish", count)
                    await add_to_inventory(db, user_id, "cooked_fish", count)
                    content = render_grid(grid, player, f"🔥 You cook {count} fish at the hearth. Got {count} cooked fish!")
                else:
                    content = render_grid(grid, player, "A warm hearth. Bring raw fish to cook here.")

            elif htile.terrain in ("b_bed", "b_table", "b_bookshelf", "b_chair", "b_candle"):
                msgs = {
                    "b_bed": "A cozy bed. You feel rested.",
                    "b_table": "A sturdy wooden table.",
                    "b_bookshelf": "Rows of dusty books.",
                    "b_chair": "A simple chair.",
                    "b_candle": "A flickering candle.",
                }
                grid = await _load_house_grid()
                content = render_grid(grid, player, msgs.get(htile.terrain, "..."))

            elif htile.terrain == "b_altar" and player.house_type == "church":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "You kneel before the altar. You feel at peace.")

            elif htile.terrain == "b_priest":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "\"May the light guide your path, traveller.\"")

            elif htile.terrain == "b_safe":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "A locked vault. Speak with the banker.")

            elif htile.terrain == "b_blacksmith_npc" and player.house_type == "blacksmith":
                stick_row = await db.fetch_one(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='stick'", (user_id,)
                )
                resin_row = await db.fetch_one(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='resin'", (user_id,)
                )
                stick_count = stick_row["quantity"] if stick_row else 0
                resin_count = resin_row["quantity"] if resin_row else 0
                torch_batches = min(stick_count, resin_count)
                grid = await _load_house_grid()
                if torch_batches > 0:
                    await remove_from_inventory(db, user_id, "stick", torch_batches)
                    await remove_from_inventory(db, user_id, "resin", torch_batches)
                    await add_to_inventory(db, user_id, "torch", torch_batches)
                    content = render_grid(grid, player, f"⚒️ Crafted {torch_batches} torch{'es' if torch_batches > 1 else ''} from sticks & resin.")
                else:
                    content = render_grid(grid, player, "\"1 stick + 1 resin = 1 torch. Use the 🔥 Forge to smelt ore, ⚒️ Anvil to craft weapons.\"")

            elif htile.terrain == "b_anvil":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "An anvil. Stand adjacent to it and use the ⚒️ Smith button.")

            else:
                grid = await _load_house_grid()
                content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player, grid=grid)
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

        view = _game_view(guild_id, user_id, player, grid=grid)
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

        elif cave_tile.terrain == "player_house_cave":
            house_id = await get_player_house_at(
                db, player.cave_x, player.cave_y, True, player.cave_id
            )
            if house_id:
                owner_id = await get_player_house_owner(db, house_id)
                is_owner = (owner_id == user_id)
                player.in_house = True
                player.house_id = house_id
                player.house_x = HOUSE_SPAWN_X
                player.house_y = HOUSE_SPAWN_Y
                player.house_vx = player.cave_x
                player.house_vy = player.cave_y
                player.house_type = "player_house"
                player.ph_cave_id = player.cave_id
                await update_player_house_state(
                    db, user_id, True, house_id,
                    HOUSE_SPAWN_X, HOUSE_SPAWN_Y,
                    player.cave_x, player.cave_y, "player_house",
                )
                await update_player_stats(db, user_id, ph_cave_id=player.cave_id)
                _ui_state.setdefault(user_id, {})["is_house_owner"] = is_owner
                grid = await load_player_house_viewport(house_id, HOUSE_SPAWN_X, HOUSE_SPAWN_Y, db)
                content = render_grid(grid, player, "You enter the house.")
            else:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                content = render_grid(grid, player, "Nothing to interact with here.")
            view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

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

        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
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

        # Treasure map: dig at location if shovel equipped
        if "shovel" in hand_items:
            tmap = await get_treasure_map(db, user_id)
            if tmap:
                tx, ty = tmap
                if wx == tx and wy == ty:
                    await mark_treasure_found(db, user_id)
                    await remove_from_inventory(db, user_id, "treasure_map", 1)
                    # Treasure reward
                    t_rng = _random.Random(hash((user_id, seed, tx, ty, "reward")))
                    gold_found = t_rng.randint(150, 400)
                    player.gold += gold_found
                    await update_player_stats(db, user_id, gold=player.gold)
                    reward_item = t_rng.choice(["gem", "iron_ingot", "sword"])
                    await add_to_inventory(db, user_id, reward_item, 1)
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player,
                        f"🪙 Your shovel strikes something! You dig up **{gold_found}g** and a **{reward_item.replace('_', ' ')}**!")
                    view = _game_view(guild_id, user_id, player)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return

        # Map fragment assembly: equip map_fragment + have 5+ in inventory
        if "map_fragment" in hand_items:
            frag_row = await db.fetch_one(
                "SELECT quantity FROM inventory WHERE user_id=? AND item_id='map_fragment'", (user_id,)
            )
            if frag_row and frag_row["quantity"] >= 5:
                existing = await get_treasure_map(db, user_id)
                if existing:
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player,
                        f"🗺️ You already have an active treasure map! The X is near ({existing[0]}, {existing[1]}).")
                    view = _game_view(guild_id, user_id, player)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
                await remove_from_inventory(db, user_id, "map_fragment", 5)
                await _auto_unequip_depleted(db, user_id, "map_fragment", player)
                tx, ty = await _find_treasure_location(user_id, seed, db)
                await set_treasure_map(db, user_id, tx, ty)
                await add_to_inventory(db, user_id, "treasure_map", 1)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player,
                    f"🗺️ You assemble the fragments into a **treasure map**! "
                    f"The X is marked near coordinates **({tx}, {ty})**. "
                    f"Dig there with your shovel to claim the treasure!")
                view = _game_view(guild_id, user_id, player)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        if terrain == "river_landing":
            # Embark canoe: find adjacent water tile
            water_pos: tuple[int, int] | None = None
            for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                ax, ay = wx + ddx, wy + ddy
                if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
                    adj = await load_single_tile(ax, ay, seed, db)
                    if (adj.structure or adj.terrain) in CANOE_PASSABLE:
                        water_pos = (ax, ay)
                        break
            if water_pos:
                player.world_x, player.world_y = water_pos
                player.in_canoe = True
                await update_player_stats(db, user_id,
                                          world_x=water_pos[0], world_y=water_pos[1],
                                          in_canoe=1)
                grid = await load_viewport(water_pos[0], water_pos[1], seed, db)
                content = render_grid(grid, player, "You launch the canoe! Dock at a 🏝️ landing to go ashore.")
                view: discord.ui.View = CanoeView(guild_id, user_id, dock_available=True)
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "There's no water here to launch a canoe.")
                view = _game_view(guild_id, user_id, player)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "player_house":
            house_id = await get_player_house_at(db, wx, wy, False, None)
            if house_id:
                owner_id = await get_player_house_owner(db, house_id)
                is_owner = (owner_id == user_id)
                player.in_house = True
                player.house_id = house_id
                player.house_x = HOUSE_SPAWN_X
                player.house_y = HOUSE_SPAWN_Y
                player.house_vx = wx
                player.house_vy = wy
                player.house_type = "player_house"
                player.ph_cave_id = None
                await update_player_house_state(
                    db, user_id, True, house_id,
                    HOUSE_SPAWN_X, HOUSE_SPAWN_Y,
                    wx, wy, "player_house",
                )
                await update_player_stats(db, user_id, ph_cave_id=None)
                _ui_state.setdefault(user_id, {})["is_house_owner"] = is_owner
                grid = await load_player_house_viewport(house_id, HOUSE_SPAWN_X, HOUSE_SPAWN_Y, db)
                content = render_grid(grid, player, "You enter your house.")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "Nothing to interact with here.")

        elif tile.structure == "cave":
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

        elif terrain == "crop_ripe":
            # Harvest ripe crop
            await set_tile_override(db, wx, wy, "farmland")
            seed_yield = _random.randint(2, 3)
            await add_to_inventory(db, user_id, "seed", seed_yield)
            await add_to_inventory(db, user_id, "dry_grass", 1)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"🌻 You harvest the crop! Got {seed_yield} seeds and some dry grass.")

        elif terrain in ("crop_planted", "crop_sprout") and "watering_can" in hand_items:
            # Water the crop — 5-minute cooldown between stages
            last_str = await get_farm_last_watered(db, wx, wy)
            can_water = True
            if last_str:
                try:
                    last_dt = datetime.fromisoformat(last_str)
                    can_water = (datetime.utcnow() - last_dt) >= timedelta(minutes=5)
                except ValueError:
                    can_water = True
            if can_water:
                next_stage = "crop_sprout" if terrain == "crop_planted" else "crop_ripe"
                stage_name = "a sprout" if next_stage == "crop_sprout" else "a ripe crop"
                await set_tile_override(db, wx, wy, next_stage)
                await set_farm_watered(db, wx, wy)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, f"💧 You water the crop. It grows into {stage_name}!")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "💧 The crop needs more time before the next watering (5 min cooldown).")

        elif terrain == "farmland" and "seed" in hand_items:
            # Plant seed on farmland
            await set_tile_override(db, wx, wy, "crop_planted")
            await remove_from_inventory(db, user_id, "seed", 1)
            await _auto_unequip_depleted(db, user_id, "seed", player)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "🌱 You plant a seed in the farmland.")

        elif terrain in ("grass", "plains", "sand") and "shovel" in hand_items and terrain != "sapling":
            # Create farmland from soft terrain
            await set_tile_override(db, wx, wy, "farmland")
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "🟤 You dig up the soil and create farmland.")

        elif "cooked_fish" in hand_items or "fish" in hand_items:
            food_id = "cooked_fish" if "cooked_fish" in hand_items else "fish"
            food_row = await db.fetch_one(
                "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, food_id)
            )
            if food_row:
                await remove_from_inventory(db, user_id, food_id, 1)
                await _auto_unequip_depleted(db, user_id, food_id, player)
                heal_amt = FOOD_HP_RESTORE.get(food_id, 15)
                heal = min(heal_amt, player.max_hp - player.hp)
                player.hp += heal
                await update_player_stats(db, user_id, hp=player.hp)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, f"🍗 You eat the {food_id.replace('_', ' ')}. Restored **{heal}** HP. ({player.hp}/{player.max_hp})")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "Nothing to eat here.")

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

        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Action button handlers (adjacent-tile interactions) ───────────────────────

async def handle_action(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Handle the context-sensitive Action button (adjacent-tile interactions)."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    hand_items: set[str] = set()
    if player.hand_1:
        hand_items.add(player.hand_1)
    if player.hand_2:
        hand_items.add(player.hand_2)

    # ── Player house: enter edit mode ────────────────────────────────────────
    if player.in_house and player.house_type == "player_house":
        _is_owner = _ui_state.get(user_id, {}).get("is_house_owner", False)
        if not _is_owner:
            grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "Only the house owner can edit this house.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        state = _ui_state.get(user_id, {})
        _ui_state[user_id] = {**state, "type": "house_edit"}
        grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
        cursor = (player.house_x, player.house_y)
        content = render_grid(grid, player, "✏️ **Edit mode** — Move around and use ➕ Add / ✖ Remove to decorate tiles.",
                              cursor_pos=cursor)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=PlayerHouseEditView(guild_id, user_id),
        )
        return

    # ── Forge: adjacent b_forge ───────────────────────────────────────────────
    if player.in_house:
        grid = await _load_house_grid(player, db)
        vc = 4
        adj_terrains = set()
        for ro, co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = vc + ro, vc + co
            if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
                t = grid[r][c].terrain
                if t:
                    adj_terrains.add(t)

        if "b_forge" in adj_terrains:
            await interaction.response.edit_message(
                embed=_embed("🔥 **Forge** — What would you like to smelt?"),
                content=None,
                view=ForgeView(guild_id, user_id),
            )
            return

        if "b_anvil" in adj_terrains:
            await interaction.response.edit_message(
                embed=_embed("⚒️ **Anvil** — What would you like to craft?"),
                content=None,
                view=AnvilView(guild_id, user_id),
            )
            return

        if "b_shop_npc" in adj_terrains:
            return await _open_shop(interaction, guild_id, user_id, player)

        if "b_bank_npc" in adj_terrains:
            return await _open_bank(interaction, guild_id, user_id, player, db)

        content = render_grid(grid, player, "Nothing to interact with nearby.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Build a player house (requires house_kit equipped) ───────────────────
    wx, wy = player.world_x, player.world_y
    if not player.in_cave and not player.in_village:
        # Only proceed if house_kit is in hand
        if "house_kit" in hand_items:
            tile = await load_single_tile(wx, wy, seed, db)
            _build_ok = (
                not tile.structure
                and tile.walkable
                and tile.terrain not in {"void", "deep_water", "shallow_water", "river",
                                         "river_landing", "mountain", "snow", "player_house_cave"}
            )
            if _build_ok:
                # Check no house already here
                existing = await get_player_house_at(db, wx, wy, is_cave=False, loc_cave_id=None)
                if existing is not None:
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, "🏠 A house already exists here.")
                    view = _game_view(guild_id, user_id, player, grid=grid)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
                # Consume house_kit: unequip from whichever hand, remove from inventory
                if player.hand_1 == "house_kit":
                    await unequip_item(db, user_id, "hand_1")
                elif player.hand_2 == "house_kit":
                    await unequip_item(db, user_id, "hand_2")
                await remove_from_inventory(db, user_id, "house_kit", 1)
                # Place overworld structure tile
                await set_tile_override(db, wx, wy, "player_house")
                # Create house record
                await create_player_house(db, user_id, wx, wy, is_cave=False, loc_cave_id=None)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "🏠 **House built!** Step inside to decorate it.")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        # Fishing (overworld)
        if "fishing_rod" in hand_items and await _is_adjacent_to_water(player, seed, db):
            fish_rng = _random.Random(hash((user_id, wx, wy, player.xp, "fish")))
            roll = fish_rng.random()
            if roll < 0.50:
                await add_to_inventory(db, user_id, "fish", 1)
                msg = "🎣 You cast your line... and reel in a **fish**!"
            elif roll < 0.51:
                # 1% chance: map fragment
                await add_to_inventory(db, user_id, "map_fragment", 1)
                msg = "🎣 You reel in something unusual — a **map fragment**!"
            else:
                msg = "🎣 You cast your line... the fish got away."
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, msg)
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        grid = await load_viewport(wx, wy, seed, db)
        content = render_grid(grid, player, "Nothing to interact with nearby.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Cave: build a player house (requires house_kit equipped) ─────────────
    if player.in_cave and not player.in_village and "house_kit" in hand_items:
        cx, cy = player.cave_x, player.cave_y
        cave_tile = await load_cave_single_tile(player.cave_id, cx, cy, db)
        _build_ok_cave = (
            cave_tile.terrain not in {"void", "cave_rock", "cave_wall", "cave_water",
                                      "player_house_cave"}
            and cave_tile.walkable
        )
        if _build_ok_cave:
            existing = await get_player_house_at(db, cx, cy, is_cave=True,
                                                 loc_cave_id=player.cave_id)
            if existing is not None:
                grid = await load_cave_viewport(player.cave_id, cx, cy, db)
                content = render_grid(grid, player, "🏠 A house already exists here.")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            # Consume house_kit
            if player.hand_1 == "house_kit":
                await unequip_item(db, user_id, "hand_1")
            elif player.hand_2 == "house_kit":
                await unequip_item(db, user_id, "hand_2")
            await remove_from_inventory(db, user_id, "house_kit", 1)
            # Update cave tile to player_house_cave
            await db.execute(
                "UPDATE cave_tiles SET tile_type='player_house_cave'"
                " WHERE cave_id=? AND local_x=? AND local_y=?",
                (player.cave_id, cx, cy),
            )
            await create_player_house(db, user_id, cx, cy, is_cave=True,
                                      loc_cave_id=player.cave_id)
            grid = await load_cave_viewport(player.cave_id, cx, cy, db)
            content = render_grid(grid, player, "🏠 **House built!** Step inside to decorate it.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    # Fallback
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player, "Nothing to interact with nearby.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Player-house edit handlers ────────────────────────────────────────────────

async def _ph_edit_response(
    interaction: discord.Interaction,
    guild_id: int,
    user_id: int,
    player,
    db,
    msg: str,
) -> None:
    """Helper: render house grid in edit mode and respond."""
    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    content = render_grid(grid, player, msg, cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=PlayerHouseEditView(guild_id, user_id),
    )


async def handle_house_edit_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Move the player within their house while in edit mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        await interaction.response.defer()
        return

    dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
    nx, ny = player.house_x + dx, player.house_y + dy

    # Load target tile
    target_tile = await load_player_house_single_tile(player.house_id, nx, ny, db)
    # Passability: walls and void are impassable inside the house
    _impassable = {"b_wall", "void"}
    if target_tile.terrain in _impassable:
        await _ph_edit_response(interaction, guild_id, user_id, player, db, "🚧 Can't move there.")
        return

    await update_player_house_state(
        db, user_id, True, player.house_id, nx, ny,
        player.house_vx, player.house_vy, "player_house",
    )
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            "✏️ Edit mode — use ➕ Add / ✖ Remove on the blue-highlighted tile.")


async def handle_house_add(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open decoration picker for the current tile (must be b_floor_wood)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        await interaction.response.defer()
        return

    tile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
    if tile.terrain != "b_floor_wood":
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "➕ Can only add decorations to bare wood-floor tiles.")
        return

    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {**state, "type": "house_deco", "deco_page": 0, "deco_selected": 0}
    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    content = render_grid(grid, player, "🪑 Choose a decoration to place on the blue tile:",
                          cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HouseDecorationView(guild_id, user_id, page=0, selected=0),
    )


async def handle_house_remove(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Remove a decoration from the current tile, restoring it to b_floor_wood."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        await interaction.response.defer()
        return

    tile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
    if tile.terrain not in PLAYER_HOUSE_DECO_TILES:
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "✖ No decoration here to remove.")
        return

    await set_player_house_tile(player.house_id, player.house_x, player.house_y, "b_floor_wood", db)
    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            f"✖ Removed **{tile.terrain}** — tile restored to wood floor.")


async def handle_house_delete(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Delete the current player house and eject the player."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        await interaction.response.defer()
        return

    # Only owner may delete
    owner_id = await get_player_house_owner(db, player.house_id)
    if owner_id != user_id:
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "🚫 Only the house owner can delete it.")
        return

    loc_x, loc_y, is_cave, loc_cave_id = await delete_player_house(db, player.house_id)

    if is_cave and loc_cave_id is not None:
        # Restore cave tile to cave_floor
        await db.execute(
            "UPDATE cave_tiles SET tile_type='cave_floor'"
            " WHERE cave_id=? AND local_x=? AND local_y=?",
            (loc_cave_id, loc_x, loc_y),
        )
        # Eject player back into cave at the house location, clear house state
        await update_player_cave_state(db, user_id, True, loc_cave_id, loc_x, loc_y)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        grid = await load_cave_viewport(loc_cave_id, loc_x, loc_y, db)
        content = render_grid(grid, player, "🗑️ House demolished.")
    else:
        # Restore overworld tile structure override (remove player_house)
        await db.execute(
            "DELETE FROM tile_overrides WHERE world_x=? AND world_y=? AND tile_type='player_house'",
            (loc_x, loc_y),
        )
        # Eject player back to overworld, clear house + cave state
        await update_player_position(db, user_id, loc_x, loc_y)
        await update_player_cave_state(db, user_id, False, None, 0, 0)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        grid = await load_viewport(loc_x, loc_y, seed, db)
        content = render_grid(grid, player, "🗑️ House demolished.")

    _ui_state[user_id] = {}
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_house_edit_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Exit edit mode, return to normal house view."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {k: v for k, v in state.items() if k not in ("type",)}

    if not player.in_house or player.house_type != "player_house":
        await interaction.response.defer()
        return

    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "✅ Exited edit mode.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_house_deco_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Navigate decoration pages (prev/next)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    per_page = 5
    total_pages = max(1, (len(HOUSE_DECORATION_CATALOG) + per_page - 1) // per_page)
    page = state.get("deco_page", 0)
    if direction == "prev":
        page = max(0, page - 1)
    else:
        page = min(total_pages - 1, page + 1)
    _ui_state[user_id] = {**state, "deco_page": page}

    selected = state.get("deco_selected", 0)
    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    content = render_grid(grid, player, "🪑 Choose a decoration:", cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HouseDecorationView(guild_id, user_id, page=page, selected=selected),
    )


async def handle_house_deco_sel(
    interaction: discord.Interaction, guild_id: int, user_id: int, idx: int
) -> None:
    """Select a decoration item from the catalog."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    page = state.get("deco_page", 0)
    _ui_state[user_id] = {**state, "deco_selected": idx}

    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    item = HOUSE_DECORATION_CATALOG[idx] if idx < len(HOUSE_DECORATION_CATALOG) else None
    msg = f"🪑 Selected **{item['name']}** — press 🏗️ Place to confirm." if item else "🪑 Choose a decoration:"
    content = render_grid(grid, player, msg, cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HouseDecorationView(guild_id, user_id, page=page, selected=idx),
    )


async def handle_house_deco_place(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Place the selected decoration on the current tile (consumes materials)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        await interaction.response.defer()
        return

    state = _ui_state.get(user_id, {})
    idx = state.get("deco_selected", 0)
    if idx >= len(HOUSE_DECORATION_CATALOG):
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "❌ Invalid selection.")
        return

    deco = HOUSE_DECORATION_CATALOG[idx]
    tile_id = deco["id"]
    cost = deco["cost"]

    # Verify current tile is b_floor_wood
    tile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
    if tile.terrain != "b_floor_wood":
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "➕ Can only place decorations on bare wood-floor tiles.")
        return

    # Check materials
    missing = []
    for mat, qty in cost.items():
        row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?",
            (user_id, mat),
        )
        have = row["quantity"] if row else 0
        if have < qty:
            missing.append(f"{qty - have}× {mat}")
    if missing:
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                f"❌ Need more: {', '.join(missing)}")
        return

    # Consume materials and place tile
    for mat, qty in cost.items():
        await remove_from_inventory(db, user_id, mat, qty)
    await set_player_house_tile(player.house_id, player.house_x, player.house_y, tile_id, db)

    # Return to edit mode
    _ui_state[user_id] = {**state, "type": "house_edit"}
    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            f"🏗️ Placed **{deco['name']}**!")


async def handle_house_deco_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel decoration selection and return to edit mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {**state, "type": "house_edit"}

    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            "❌ Cancelled.")


async def handle_forge_iron(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Smelt iron ore into ingots at the forge (3 ore → 1 ingot)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ore_row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ore'", (user_id,)
    )
    ore_count = ore_row["quantity"] if ore_row else 0
    ingot_batches = ore_count // 3

    if ingot_batches > 0:
        await remove_from_inventory(db, user_id, "iron_ore", ingot_batches * 3)
        await add_to_inventory(db, user_id, "iron_ingot", ingot_batches)
        msg = (f"🔥 Smelted {ingot_batches * 3} iron ore → "
               f"**{ingot_batches} iron ingot{'s' if ingot_batches > 1 else ''}**!")
    else:
        msg = "🔥 You need at least 3 iron ore to smelt an ingot."

    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=ForgeView(guild_id, user_id)
    )


async def handle_forge_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "You step away from the forge.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_anvil_dagger(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft a dagger at the anvil (1 iron ingot)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ingot_row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
    )
    ingot_count = ingot_row["quantity"] if ingot_row else 0

    if ingot_count >= 1:
        await remove_from_inventory(db, user_id, "iron_ingot", 1)
        await add_to_inventory(db, user_id, "dagger", 1)
        msg = "⚒️ You craft a **dagger**! (+8 attack, equip to hand)"
    else:
        msg = "⚒️ You need 1 iron ingot to craft a dagger."

    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=AnvilView(guild_id, user_id)
    )


async def handle_anvil_sword(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft a sword at the anvil (2 iron ingots)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ingot_row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
    )
    ingot_count = ingot_row["quantity"] if ingot_row else 0

    if ingot_count >= 2:
        await remove_from_inventory(db, user_id, "iron_ingot", 2)
        await add_to_inventory(db, user_id, "sword", 1)
        msg = "⚒️ You forge a **sword**! (+12 attack, equip to hand)"
    else:
        msg = "⚒️ You need 2 iron ingots to forge a sword."

    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=AnvilView(guild_id, user_id)
    )


async def _anvil_craft(interaction: discord.Interaction, guild_id: int, user_id: int,
                       item_id: str, ingot_cost: int, name: str, stat_desc: str) -> None:
    """Generic anvil crafting helper."""
    db = await get_database(guild_id)
    ingot_row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
    )
    ingot_count = ingot_row["quantity"] if ingot_row else 0
    if ingot_count >= ingot_cost:
        await remove_from_inventory(db, user_id, "iron_ingot", ingot_cost)
        await add_to_inventory(db, user_id, item_id, 1)
        msg = f"⚒️ You craft a **{name}**! ({stat_desc})"
    else:
        msg = f"⚒️ You need {ingot_cost} iron ingot{'s' if ingot_cost > 1 else ''} to craft a {name}."
    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=AnvilView(guild_id, user_id)
    )


async def handle_anvil_helmet(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_helmet", 2, "Iron Helmet", "+3 defense, equip to head")


async def handle_anvil_chestplate(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_chestplate", 4, "Iron Chestplate", "+5 defense, equip to chest")


async def handle_anvil_leggings(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_leggings", 3, "Iron Leggings", "+4 defense, equip to legs")


async def handle_anvil_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "You step away from the anvil.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Inventory handlers ────────────────────────────────────────────────────────

async def handle_inventory(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    prev_state = _ui_state.get(user_id, {})
    prev_arena = prev_state.get("arena")
    prev_selections = prev_state.get("selections", {})
    prev_mode = prev_state.get("sel_mode", "add")
    _ui_state[user_id] = {"type": "inventory", "selected": 0, "prev_arena": prev_arena,
                          "selections": prev_selections, "sel_mode": prev_mode}
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, 0, equipped,
                              inv_rows, inv_cols, _ui_state[user_id])
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
    _ui_state[user_id] = {**state, "type": "inventory", "selected": new_sel}
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, new_sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id])
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


def _inv_view(guild_id: int, user_id: int, items: list, sel: int, equipped: dict,
              inv_rows: int, inv_cols: int, state: dict, msg_suffix: str = "") -> tuple[str, "InventoryView"]:
    """Helper: build inventory content + view with consistent state."""
    selections = state.get("selections", {})
    sel_mode = state.get("sel_mode", "add")
    label, action = _inv_action_btn(items, sel, equipped)
    cursor_id = items[sel]["item_id"] if sel < len(items) else None
    content = render_inventory(items, sel, equipped, label, inv_rows, inv_cols, selections)
    if msg_suffix:
        content += msg_suffix
    view = InventoryView(guild_id, user_id, label, action, selections, cursor_id, sel_mode)
    return content, view


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
    inv_rows, inv_cols = _inv_capacity(player)

    if sel >= len(items):
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item selected)*")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    item_id = items[sel]["item_id"]

    # Food items are handled by handle_inv_eat — if this is called with food, redirect
    if item_id in FOOD_HP_RESTORE:
        await handle_inv_eat(interaction, guild_id, user_id)
        return

    # Unequip if already equipped
    if item_id in equipped.values():
        # Pouch unequip: check if current inv fits in smaller size
        if item_id in ("small_pouch", "medium_pouch", "large_pouch"):
            pouch_order = [None, "small_pouch", "medium_pouch", "large_pouch"]
            cur_idx = pouch_order.index(item_id)
            new_rows, new_cols = POUCH_SIZES[pouch_order[cur_idx - 1]] if cur_idx > 0 else POUCH_SIZES[None]
            new_capacity = new_rows * new_cols
            if len(items) > new_capacity:
                content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                    inv_rows, inv_cols, state,
                    f"\n*Can't unequip: inventory has {len(items)} items but smaller pouch fits {new_capacity}. Remove items first.*")
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
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
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*Unequipped {item_id.replace('_', ' ').title()}.*")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Look up slot type
    slot_type = ITEM_EQUIP_SLOTS.get(item_id)
    if not slot_type:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*{item_id.replace('_', ' ').title()} cannot be equipped.*")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Resolve hand slot
    if slot_type == "hand":
        if item_id in TWO_HANDED_ITEMS:
            if equipped.get("hand_1") or equipped.get("hand_2"):
                content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                          inv_rows, inv_cols, state,
                                          "\n*Your hands must be free for a two-handed item.*")
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            await equip_item(db, user_id, "hand_1", item_id)
            await equip_item(db, user_id, "hand_2", item_id)
        else:
            if not equipped.get("hand_1"):
                resolved_slot = "hand_1"
            elif not equipped.get("hand_2"):
                resolved_slot = "hand_2"
            else:
                content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                          inv_rows, inv_cols, state,
                                          "\n*Both hands are full.*")
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
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
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, state,
                              f"\n*Equipped {item_id.replace('_', ' ').title()}!*")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_eat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Eat a food item from inventory, restoring HP."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    if sel >= len(items):
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item selected)*")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    item_id = items[sel]["item_id"]
    restore = FOOD_HP_RESTORE.get(item_id)
    if restore is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*{item_id.replace('_', ' ').title()} is not food.*")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if player.hp >= player.max_hp:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*You're already at full health!*")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    new_hp = min(player.max_hp, player.hp + restore)
    await update_player_stats(db, user_id, hp=new_hp)
    await remove_from_inventory(db, user_id, item_id, 1)
    await _auto_unequip_depleted(db, user_id, item_id, player)
    # Auto-deselect if selection qty now exceeds remaining stack (or stack is gone)
    selections = dict(state.get("selections", {}))
    if item_id in selections:
        remain_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
        )
        remain = remain_row["quantity"] if remain_row else 0
        if remain <= 0:
            del selections[item_id]
        else:
            selections[item_id] = min(selections[item_id], remain)
        state = {**state, "selections": selections}
        _ui_state[user_id] = state
    items = await get_inventory(db, user_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, state,
                              f"\n*🍗 Ate {item_id.replace('_', ' ')}. HP: {new_hp}/{player.max_hp}*")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_select(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Select or deselect the current cursor item for crafting."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    selections = dict(state.get("selections", {}))

    if sel < len(items):
        item_id = items[sel]["item_id"]
        if item_id in selections:
            del selections[item_id]
            msg = f"\n*Deselected {item_id.replace('_', ' ').title()}.*"
        else:
            # Add with qty 1 (can be adjusted via item sub-menu)
            selections[item_id] = 1
            msg = f"\n*Selected {item_id.replace('_', ' ').title()} ×1.*"
    else:
        msg = "\n*(No item at cursor)*"

    _ui_state[user_id] = {**state, "selections": selections}
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_unselect_all(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Clear all item selections."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    _ui_state[user_id] = {**state, "selections": {}}
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], "\n*Cleared all selections.*")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_item_btn(
    interaction: discord.Interaction, guild_id: int, user_id: int, idx: int
) -> None:
    """Add or subtract 1 from the Nth selected item based on current sel_mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    selections = dict(state.get("selections", {}))
    sel_mode = state.get("sel_mode", "add")
    sel_list = list(selections.items())
    if idx >= len(sel_list):
        await interaction.response.defer()
        return
    item_id, qty = sel_list[idx]
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    sel = state.get("selected", 0)
    if sel_mode == "add":
        have = next((it["quantity"] for it in items if it["item_id"] == item_id), 0)
        new_qty = min(have, qty + 1)
        selections[item_id] = new_qty
        msg = f"\n*➕ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    else:
        new_qty = qty - 1
        if new_qty <= 0:
            del selections[item_id]
            msg = f"\n*➖ Removed {item_id.replace('_', ' ').title()} from selection.*"
        else:
            selections[item_id] = new_qty
            msg = f"\n*➖ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    _ui_state[user_id] = {**state, "selections": selections}
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_toggle_mode(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Toggle selection mode between Add (➕) and Subtract (➖)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    new_mode = "sub" if state.get("sel_mode", "add") == "add" else "add"
    _ui_state[user_id] = {**state, "sel_mode": new_mode}
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    mode_name = "➖ Subtract" if new_mode == "sub" else "➕ Add"
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              f"\n*Mode switched to {mode_name}*")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_item_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Increase quantity of the item in the sub-menu selection."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    item_id = state.get("item_view")
    selections = dict(state.get("selections", {}))
    if item_id and item_id in selections:
        # Cap at player's actual stack
        items = await get_inventory(db, user_id)
        have = next((it["quantity"] for it in items if it["item_id"] == item_id), 0)
        new_qty = min(have, selections[item_id] + 1)
        selections[item_id] = new_qty
        _ui_state[user_id] = {**state, "selections": selections}
        content = (f"🎒 **Item Detail: {item_id.replace('_', ' ').title()}**\n"
                   f"Selected quantity: **×{new_qty}** (have ×{have})\n"
                   f"Use + More / − Less to adjust, or Unselect to remove.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=InventoryItemView(guild_id, user_id, new_qty)
        )
    else:
        await interaction.response.defer()


async def handle_inv_item_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Decrease quantity of the item in the sub-menu selection."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    item_id = state.get("item_view")
    selections = dict(state.get("selections", {}))
    if item_id and item_id in selections:
        new_qty = selections[item_id] - 1
        if new_qty <= 0:
            del selections[item_id]
            item_id = None
        else:
            selections[item_id] = new_qty
        _ui_state[user_id] = {**state, "selections": selections, "item_view": item_id}
        if item_id:
            content = (f"🎒 **Item Detail: {item_id.replace('_', ' ').title()}**\n"
                       f"Selected quantity: **×{new_qty}**\n"
                       f"Use + More / − Less to adjust, or Unselect to remove.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=InventoryItemView(guild_id, user_id, new_qty)
            )
        else:
            # Quantity hit zero, return to main inventory
            await handle_inv_item_back(interaction, guild_id, user_id)
    else:
        await interaction.response.defer()


async def handle_inv_item_unsel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Unselect the item currently shown in the sub-menu."""
    state = _ui_state.get(user_id, {})
    item_id = state.get("item_view")
    selections = dict(state.get("selections", {}))
    if item_id and item_id in selections:
        del selections[item_id]
    _ui_state[user_id] = {**state, "selections": selections, "item_view": None}
    await handle_inv_item_back(interaction, guild_id, user_id)


async def handle_inv_item_back(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Return from item sub-menu to main inventory view."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    _ui_state[user_id] = {**state, "item_view": None}
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id])
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_craft(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft item if current selections exactly match a recipe."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    selections = state.get("selections", {})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    sel_set = frozenset((k, v) for k, v in selections.items())
    recipe = CRAFT_RECIPES.get(sel_set)
    if recipe is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*No matching recipe for the selected items.*")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Verify player has enough of each ingredient
    for item_id, qty in selections.items():
        row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
        )
        if not row or row["quantity"] < qty:
            content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                      inv_rows, inv_cols, state,
                                      f"\n*Not enough {item_id.replace('_', ' ')} to craft.*")
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    # Consume ingredients and add result
    for item_id, qty in selections.items():
        await remove_from_inventory(db, user_id, item_id, qty)
    await add_to_inventory(db, user_id, recipe["result"], recipe["qty"])

    # Clear selections and refresh
    _ui_state[user_id] = {**state, "selections": {}}
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              f"\n*✨ Crafted {recipe['qty']}× {recipe['result'].replace('_', ' ').title()}!*")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


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
        grid = await _load_house_grid(player, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    content = render_grid(grid, player)
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
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_bank(player_items, bank_items, 0, "player", equipped, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "player"))


async def handle_bank_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    bv = state.get("bank_view", "player")
    inv_rows, inv_cols = _inv_capacity(player)
    total = max(1, (inv_rows * inv_cols if bv == "player" else 36))
    new_sel = (state["selected"] + delta) % total
    _ui_state[user_id] = {"type": "bank", "selected": new_sel, "bank_view": bv}
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    content = render_bank(player_items, bank_items, new_sel, bv, equipped, inv_rows, inv_cols)
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
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_bank(player_items, bank_items, 0, new_view, equipped, inv_rows, inv_cols)
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
    inv_rows, inv_cols = _inv_capacity(player)
    if sel >= len(items):
        player_items = items
        bank_items = await get_bank_items(db, user_id)
        equipped = _equipped_dict(player)
        content = render_bank(player_items, bank_items, sel, "player", equipped, inv_rows, inv_cols) + "\n*(Empty slot)*"
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
    content = render_bank(player_items, bank_items, new_sel, "player", equipped, inv_rows, inv_cols) + suffix
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
    inv_rows, inv_cols = _inv_capacity(player)
    if sel >= len(items):
        player_items = await get_inventory(db, user_id)
        bank_items = items
        equipped = _equipped_dict(player)
        content = render_bank(player_items, bank_items, sel, "bank", equipped, inv_rows, inv_cols) + "\n*(Empty slot)*"
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
    content = render_bank(player_items, bank_items_new, new_sel, "bank", equipped, inv_rows, inv_cols) + suffix
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
        chest_sizes = {
            "cave_chest": (2,9), "cave_chest_medium": (3,9), "cave_chest_large": (4,9),
            "ph_chest_small": (2,9), "ph_chest_medium": (3,9), "ph_chest_large": (4,9),
        }
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
        chest_sizes = {
            "cave_chest": (2,9), "cave_chest_medium": (3,9), "cave_chest_large": (4,9),
            "ph_chest_small": (2,9), "ph_chest_medium": (3,9), "ph_chest_large": (4,9),
        }
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
    other_players = await get_all_overworld_players(db, user_id)
    from dwarf_explorer.world.world_map import generate_world_map
    buf = await generate_world_map(seed, db, player.world_x, player.world_y, other_players)
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
        grid = await _load_house_grid(player, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        view = _game_view(guild_id, user_id, player, grid=grid)
    content = render_grid(grid, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
