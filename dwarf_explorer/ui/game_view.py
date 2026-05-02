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
    OCEAN_SIZE, OCEAN_ENCOUNTER_RATES, OCEAN_WALKABLE, SHIP_WALKABLE,
    COIN_PURSE_CAPACITY, CONSUMABLE_ITEMS, SHRINE_SACRIFICES,
)
from dwarf_explorer.world.ships import load_ship_viewport, get_door_target, HELM_SPAWN
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world,
    update_player_position, update_player_message,
    update_player_cave_state,
    update_player_village_state,
    update_player_house_state,
    update_player_sprint,
    update_player_stats,
    update_player_ocean_state,
    save_combat_state,
    clear_combat_state,
    update_player_ship_state, update_player_ship_hp,
    get_ship_personal_items, ship_personal_deposit, ship_personal_withdraw,
    get_ship_cargo_items, ship_cargo_deposit, ship_cargo_withdraw, ship_cargo_consume,
    update_player_island_state,
    is_island_looted, mark_island_looted,
    update_island_tile,
    get_cave_entrance_exit,
    equip_item, unequip_item,
    get_inventory,
    add_to_inventory,
    remove_from_inventory,
    swap_inventory_slots,
    create_drop_box,
    pickup_drop_box,
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
from dwarf_explorer.world.ocean import load_ocean_viewport, load_ocean_single_tile
from dwarf_explorer.world.caves import get_or_create_cave, load_cave_viewport, load_cave_single_tile, populate_chest_loot
from dwarf_explorer.world.player_houses import (
    create_player_house, get_player_house_at, get_player_house_owner,
    delete_player_house, load_player_house_viewport, load_player_house_single_tile,
    set_player_house_tile, HOUSE_SPAWN_X, HOUSE_SPAWN_Y,
)
from dwarf_explorer.world.villages import (
    get_or_create_village, get_or_create_harbor_village, get_building_at,
    load_village_viewport, load_village_single_tile,
    load_building_viewport, load_building_single_tile,
)
from dwarf_explorer.game.player import Player, can_move, can_move_village, can_move_building, can_move_ship
from dwarf_explorer.game.renderer import (
    render_grid, render_inventory, render_bank, render_shop, render_chest,
    render_ship_room, render_ship_chest, render_island,
)

_CUSTOM_EMOJI_RE = _re.compile(r"^<a?:(\w+):(\d+)>$")


def _cursor_item(visible: list[dict], slot_pos: int) -> dict | None:
    """Return the inventory item whose slot_index == slot_pos (grid cell), or None."""
    return next((it for it in visible if it["slot_index"] == slot_pos), None)


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
      Row 0: [Sprint/🥾] [⬆️] [Action] [🗺️ Map] [Edit (owner only)]
      Row 1: [⬅️] [Center/Interact] [➡️] [🎒 Inv] [❓ Help]

    center_label / center_enabled — on-tile contextual button (Enter cave, Chop, Harvest…)
    action_label / action_enabled — adjacent-tile contextual button (Forge, Smith, Fish…)
    edit_enabled                  — show ⚒️ Edit at row-0 col-4 (player house owners only)
    """

    def __init__(self, guild_id: int, user_id: int, boots_equipped: bool = False,
                 sprinting: bool = False, mine_dirs: frozenset[str] = frozenset(),
                 center_label: str = "", center_enabled: bool = False,
                 action_label: str = "", action_enabled: bool = False,
                 edit_enabled: bool = False):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self._build_buttons(boots_equipped, sprinting, mine_dirs,
                            center_label, center_enabled,
                            action_label, action_enabled,
                            edit_enabled)

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
                       action_label: str, action_enabled: bool,
                       edit_enabled: bool) -> None:
        sprint_style = discord.ButtonStyle.success if sprinting else discord.ButtonStyle.secondary

        # ── Row 0: Map | Inventory | Help | Sprint | Edit ─────────────────────
        map_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Map", emoji="\U0001F5FA\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "map"),
            row=0,
        )
        inventory_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Inv", emoji="\U0001F392",
            custom_id=_custom_id(self.guild_id, self.user_id, "inventory"),
            row=0,
        )
        help_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Help", emoji="\u2753",
            custom_id=_custom_id(self.guild_id, self.user_id, "help"),
            row=0,
        )
        edit_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="\u26CF\uFE0F Edit",
            custom_id=_custom_id(self.guild_id, self.user_id, "action"),
            row=0,
        ) if edit_enabled else None

        # ── Row 1: Sprint (or spacer) | ⬆️ | Action ─────────────────────────
        if boots_equipped:
            sp1_btn = discord.ui.Button(
                style=sprint_style, label="\U0001F97E",
                custom_id=_custom_id(self.guild_id, self.user_id, "sprint"),
                row=1,
            )
        else:
            sp1_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp2"),
                row=1,
            )
        up_btn = self._dir_btn("up", "\u2B06\uFE0F", 1, "up" in mine_dirs)
        if action_enabled and action_label:
            action_btn = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=action_label,
                custom_id=_custom_id(self.guild_id, self.user_id, "action"),
                row=1,
            )
        else:
            action_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp3"),
                row=1,
            )

        # ── Row 2: ⬅️ | Center | ➡️ ──────────────────────────────────────────
        left_btn  = self._dir_btn("left",  "\u2B05\uFE0F", 2, "left"  in mine_dirs)
        right_btn = self._dir_btn("right", "\u27A1\uFE0F", 2, "right" in mine_dirs)
        if center_enabled and center_label:
            _center_emoji = _parse_emoji(center_label)
            if _center_emoji:
                center_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    emoji=_center_emoji,
                    custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                    row=2,
                )
            else:
                # Unicode emoji — use only the first word (the emoji character), no label text
                _emoji_char = center_label.split()[0]
                center_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    emoji=_emoji_char,
                    custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                    row=2,
                )
        else:
            center_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                row=2,
            )

        # ── Row 3: spacer | ⬇️ | spacer ──────────────────────────────────────
        sp5_btn  = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(self.guild_id, self.user_id, "sp5"),
            row=3,
        )
        down_btn = self._dir_btn("down", "\u2B07\uFE0F", 3, "down" in mine_dirs)

        row0 = [map_btn, inventory_btn, help_btn]
        if edit_btn is not None:
            row0.append(edit_btn)
        for btn in [
            *row0,                                   # row 0
            sp1_btn, up_btn, action_btn,             # row 1
            left_btn, center_btn, right_btn,         # row 2
            sp5_btn, down_btn,                       # row 3
        ]:
            self.add_item(btn)


class InventoryView(discord.ui.View):
    """Inventory view with D-pad navigation, ±qty controls, drop/move/unequip actions.

    cursor_mode:
      "inventory"  — navigating item grid
      "equipped"   — navigating equipped slots row
      "gold"       — gold pseudo-slot (select only)
      "move"       — move mode: select destination slot then confirm/cancel

    Layout (5 rows × up to 5 buttons each):
      Row 0: [Select/Desel] [Move/Confirm] [Craft?/Cancel?] [UnselAll?] [spacer]
      Row 1: [−?] [⬆️] [+?] [spacer] [spacer]
      Row 2: [⬅️] [action/spacer] [➡️] [spacer] [spacer]
      Row 3: [spacer] [⬇️] [spacer] [🫳 Drop?] [spacer]
      Row 4: [❌ Close] [spacer] [spacer] [spacer] [spacer]
    """
    def __init__(
        self, guild_id: int, user_id: int,
        equip_label: str = "",
        equip_action: str = "inv_equip",
        selections: dict | None = None,
        cursor_item_id: str | None = None,
        sel_mode: str = "add",
        cursor_mode: str = "inventory",
        show_plus_minus: bool = False,
        show_drop: bool = False,
        move_mode: bool = False,
        move_qty: int = 1,
    ):
        super().__init__(timeout=None)
        selections = selections or {}
        cursor_selected = cursor_item_id is not None and cursor_item_id in selections
        has_cursor = cursor_item_id is not None and cursor_mode == "inventory"
        # ± buttons appear in move mode (always when moving) or select mode (when item is selected)
        show_pm_move = move_mode
        show_pm_sel  = show_plus_minus and not move_mode
        show_notepad = show_pm_move or show_pm_sel

        _sp = lambda act, r: self.add_item(discord.ui.Button(  # noqa
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(guild_id, user_id, act), row=r,
        ))

        # ── Row 0: Select/Move/Craft/UnselAll ─────────────────────────────────
        if move_mode:
            # Move mode: Confirm + Cancel only
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success, label="✔ Confirm",
                custom_id=_custom_id(guild_id, user_id, "inv_move_confirm"), row=0,
            ))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, label="✖ Cancel",
                custom_id=_custom_id(guild_id, user_id, "inv_move_cancel"), row=0,
            ))
        elif cursor_selected:
            # Cursor is ON a selected item — show only Unselect + Unselect All
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="◎ Unselect",
                custom_id=_custom_id(guild_id, user_id, "inv_select"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, label="◎ All",
                custom_id=_custom_id(guild_id, user_id, "inv_unselect_all"), row=0,
            ))
        else:
            # Normal mode — ⬤ Select, Move, Craft (if recipe matches), Unselect All (if any)
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⬤ Select",
                custom_id=_custom_id(guild_id, user_id, "inv_select"),
                disabled=cursor_item_id is None,
                row=0,
            ))
            # Move button — allow whenever cursor is on an inventory item (even with selections)
            can_move_item = cursor_mode == "inventory" and has_cursor
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="↕ Move",
                custom_id=_custom_id(guild_id, user_id, "inv_move"),
                disabled=not can_move_item,
                row=0,
            ))
            # Craft button (when recipe matches); Unselect All (when any selected)
            if selections:
                sel_set = frozenset((k, v) for k, v in selections.items())
                if sel_set in CRAFT_RECIPES:
                    recipe = CRAFT_RECIPES[sel_set]
                    self.add_item(discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        label=recipe["label"],
                        custom_id=_custom_id(guild_id, user_id, "inv_craft"),
                        row=0,
                    ))
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.danger, label="◎ All",
                    custom_id=_custom_id(guild_id, user_id, "inv_unselect_all"), row=0,
                ))

        # ── Row 1: [−?] [⬆️] [+?] ─────────────────────────────────────────────
        if show_pm_move:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➖",
                custom_id=_custom_id(guild_id, user_id, "inv_move_qty_dec"), row=1,
            ))
        elif show_pm_sel:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➖",
                custom_id=_custom_id(guild_id, user_id, "inv_sel_dec"), row=1,
            ))
        else:
            _sp("inv_sp1", 1)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B06\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_up"), row=1,
        ))
        if show_pm_move:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➕",
                custom_id=_custom_id(guild_id, user_id, "inv_move_qty_inc"), row=1,
            ))
        elif show_pm_sel:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➕",
                custom_id=_custom_id(guild_id, user_id, "inv_sel_inc"), row=1,
            ))
        else:
            _sp("inv_sp2", 1)

        # ── Row 2: ⬅️ | action | ➡️ ──────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B05\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_prev"), row=2,
        ))
        if equip_label and (has_cursor or cursor_mode == "equipped"):
            _emoji_char = equip_label.split()[0] if " " in equip_label else equip_label
            _parsed = _parse_emoji(_emoji_char)
            if _parsed:
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success, emoji=_parsed,
                    custom_id=_custom_id(guild_id, user_id, equip_action), row=2,
                ))
            else:
                # Unicode emoji — use emoji= for correct rendering
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success, emoji=_emoji_char,
                    custom_id=_custom_id(guild_id, user_id, equip_action), row=2,
                ))
        else:
            _sp("inv_sp3", 2)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u27A1\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_next"), row=2,
        ))

        # ── Row 3: 📒?/spacer | ⬇️ | 🫳? ───────────────────────────────────
        if show_notepad:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, emoji="\U0001F4CB",  # 📋
                custom_id=_custom_id(guild_id, user_id, "inv_qty_modal"), row=3,
            ))
        else:
            _sp("inv_sp4", 3)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B07\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_down"), row=3,
        ))
        if show_drop and not move_mode:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, emoji="\U0001FAF3",  # 🫳
                custom_id=_custom_id(guild_id, user_id, "inv_drop"), row=3,
            ))
        # (no trailing spacer — user requested it be removed)

        # ── Row 4: Close ──────────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(guild_id, user_id, "inv_close"), row=4,
        ))


class InvQtyModal(discord.ui.Modal, title="Enter Quantity"):
    """Modal that lets the player type a custom quantity for move or select operations."""

    qty_input: discord.ui.TextInput = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter a number…",
        min_length=1,
        max_length=6,
        required=True,
    )

    def __init__(self, guild_id: int, user_id: int, mode: str, max_qty: int):
        super().__init__()
        self.guild_id  = guild_id
        self.user_id   = user_id
        self.mode      = mode       # "move" or "select"
        self.max_qty   = max_qty
        self.qty_input.placeholder = f"1 – {max_qty}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.qty_input.value.strip()
        try:
            entered = int(raw)
        except ValueError:
            await interaction.response.send_message("*Not a valid number.*", ephemeral=True)
            return

        entered = max(1, min(entered, self.max_qty))
        db     = await get_database(self.guild_id)
        player = await get_or_create_player(db, self.user_id, interaction.user.display_name)
        state  = _ui_state.get(self.user_id, {"selected": 0})
        items  = await get_inventory(db, self.user_id)
        sel    = state.get("selected", 0)
        equipped   = _equipped_dict(player)
        inv_rows, inv_cols = _inv_capacity(player)

        if self.mode == "move":
            _ui_state[self.user_id] = {**state, "move_qty": entered}
            msg = f"\n*📋 Move quantity set to ×{entered}.*"
            content, view = _inv_view(
                self.guild_id, self.user_id, items, sel, equipped,
                inv_rows, inv_cols, _ui_state[self.user_id], msg, gold=player.gold,
            )
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

        elif self.mode == "select":
            visible = [it for it in items if it["item_id"] != "gold_coin"]
            cursor_mode = state.get("cursor_mode", "inventory")
            selections  = dict(state.get("selections", {}))
            if cursor_mode == "gold":
                item_id = "gold_coin"
            else:
                ci = _cursor_item(visible, sel)
                item_id = ci["item_id"] if ci else None
            if item_id:
                selections[item_id] = entered
                _ui_state[self.user_id] = {**state, "selections": selections}
                msg = f"\n*📋 Quantity set to ×{entered}.*"
            else:
                msg = "\n*(No item at cursor)*"
            content, view = _inv_view(
                self.guild_id, self.user_id, items, sel, equipped,
                inv_rows, inv_cols, _ui_state[self.user_id], msg, gold=player.gold,
            )
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

        elif self.mode == "bank":
            new_state = {**state, "qty": entered}
            _ui_state[self.user_id] = new_state
            bank_items = await get_bank_items(db, self.user_id)
            bv = state.get("bank_view", "player")
            content = _bank_render(new_state, items, bank_items, equipped, player.gold, inv_rows, inv_cols)
            content += f"\n*📋 Quantity set to ×{entered}.*"
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=BankView(self.guild_id, self.user_id, bv))

        elif self.mode == "shop":
            new_state = {**state, "qty": entered}
            _ui_state[self.user_id] = new_state
            content = _shop_render(new_state, items, equipped, player.gold, inv_rows, inv_cols)
            content += f"\n*📋 Quantity set to ×{entered}.*"
            view_mode = state.get("shop_view", "shop")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=ShopView(self.guild_id, self.user_id, view_mode))


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
    """Bank UI — D-pad layout matching InventoryView but deposit/withdraw instead of equip."""
    def __init__(self, guild_id: int, user_id: int, view_mode: str = "player"):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        _sp = lambda act, r: self.add_item(discord.ui.Button(  # noqa
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, act), row=r,
        ))

        # ── Row 0: Switch (🏦 to go to vault / 🎒 to go to player inv) ───────
        switch_emoji = "\U0001F3E6" if view_mode == "player" else "\U0001F392"  # 🏦 / 🎒
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji=switch_emoji,
            custom_id=_custom_id(gid, uid, "bank_switch"), row=0,
        ))

        # ── Row 1: [−] [⬆] [+] ───────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➖",
            custom_id=_custom_id(gid, uid, "bank_qty_dec"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B06\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_up"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➕",
            custom_id=_custom_id(gid, uid, "bank_qty_inc"), row=1,
        ))

        # ── Row 2: ⬅ | 📤/📥 | ➡ ────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B05\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_prev"), row=2,
        ))
        action_emoji = "\U0001F4E4" if view_mode == "player" else "\U0001F4E5"  # 📤 / 📥
        action_id = "bank_deposit" if view_mode == "player" else "bank_withdraw"
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, emoji=action_emoji,
            custom_id=_custom_id(gid, uid, action_id), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u27A1\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_next"), row=2,
        ))

        # ── Row 3: 📋 | ⬇ ───────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji="\U0001F4CB",  # 📋
            custom_id=_custom_id(gid, uid, "bank_qty_modal"), row=3,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B07\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_down"), row=3,
        ))

        # ── Row 4: Close ─────────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(gid, uid, "bank_close"), row=4,
        ))


class ShipChestView(discord.ui.View):
    """Reusable view for ship personal and cargo chests."""
    def __init__(self, guild_id: int, user_id: int,
                 chest_type: str = "personal",   # "personal" | "cargo"
                 view_mode: str = "player"):
        super().__init__(timeout=None)
        dep_act = f"ship_chest_{chest_type}_deposit"
        wth_act = f"ship_chest_{chest_type}_withdraw"
        action = wth_act if view_mode == "chest" else dep_act
        action_label = "⬆ Withdraw" if view_mode == "chest" else "⬇ Deposit"
        for label, act in [
            ("◀", f"ship_chest_{chest_type}_prev"),
            ("▶", f"ship_chest_{chest_type}_next"),
            (action_label, action),
            ("🔄 Switch", f"ship_chest_{chest_type}_switch"),
            ("🔙 Back", "ship_chest_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))


class ShipView(discord.ui.View):
    """Scene-based ship interior navigation view."""

    def __init__(self, guild_id: int, user_id: int,
                 room: str = "helm",
                 ship_hp: int = 100, ship_max_hp: int = 100,
                 has_repair_logs: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.secondary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv | Help | HP status (disabled label)
        self.add_item(_btn("Map",  "map",       0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory", 0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Help", "help",      0, discord.ButtonStyle.secondary))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"🛳️ {ship_hp}/{ship_max_hp}", disabled=True,
            custom_id=_custom_id(gid, uid, "ship_hp_sp"), row=0,
        ))

        if room == "helm":
            # Row 1: → Captain's Quarters | → Lower Deck
            self.add_item(_btn("🛏️ Quarters",   "ship_room_quarters",   1, discord.ButtonStyle.primary))
            self.add_item(_btn("🪜 Lower Deck", "ship_room_lower_deck", 1, discord.ButtonStyle.primary))
            # Row 2: ⚓ Back to Ocean
            self.add_item(_btn("⚓ Back to Ocean", "ship_leave", 2, discord.ButtonStyle.danger))

        elif room == "quarters":
            # Row 1: Personal chest
            self.add_item(_btn("📦 Personal Chest", "ship_chest_personal_open", 1, discord.ButtonStyle.primary))
            # Row 2: Return to helm
            self.add_item(_btn("🔙 Return to Helm", "ship_room_helm", 2, discord.ButtonStyle.secondary))

        else:  # lower_deck
            # Row 1: Cargo chest | Repair
            self.add_item(_btn("📦 Cargo",  "ship_chest_cargo_open",  1, discord.ButtonStyle.primary))
            repair_disabled = (ship_hp >= ship_max_hp) or not has_repair_logs
            repair_label = "🔨 Repair (3 🪵)" if not repair_disabled else "🔨 Repair"
            self.add_item(_btn(repair_label, "ship_repair", 1,
                               discord.ButtonStyle.success, disabled=repair_disabled))
            # Row 2: Return to helm
            self.add_item(_btn("🔙 Return to Helm", "ship_room_helm", 2, discord.ButtonStyle.secondary))


class IslandView(discord.ui.View):
    """Movement + interaction view for island interiors."""

    def __init__(self, guild_id: int, user_id: int,
                 can_loot: bool = False, on_dock: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.primary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv | Help
        self.add_item(_btn("Map",  "map",       0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory", 0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Help", "help",      0, discord.ButtonStyle.secondary))

        # Row 1: ↑  (+ interact if on dock/chest)
        self.add_item(_btn("⬆️", "island_up", 1))
        if can_loot:
            self.add_item(_btn("📦 Loot", "island_loot", 1, discord.ButtonStyle.success))
        elif on_dock:
            self.add_item(_btn("⛵ Leave", "island_leave", 1, discord.ButtonStyle.danger))

        # Row 2: ← | ↓ | →
        self.add_item(_btn("⬅️", "island_left",  2))
        self.add_item(_btn("⬇️", "island_down",  2))
        self.add_item(_btn("➡️", "island_right", 2))


class ShopView(discord.ui.View):
    """Shop UI — D-pad layout matching BankView but buy/sell instead of deposit/withdraw."""
    def __init__(self, guild_id: int, user_id: int, view_mode: str = "shop"):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        _sp = lambda act, r: self.add_item(discord.ui.Button(  # noqa
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, act), row=r,
        ))

        # ── Row 0: Switch (🛒 to go to shop / 🎒 to go to player inv) ────────
        switch_emoji = "\U0001F6D2" if view_mode == "player" else "\U0001F392"  # 🛒 / 🎒
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji=switch_emoji,
            custom_id=_custom_id(gid, uid, "shop_switch"), row=0,
        ))

        # ── Row 1: [−] [⬆] [+] ───────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➖",
            custom_id=_custom_id(gid, uid, "shop_qty_dec"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B06\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_up"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➕",
            custom_id=_custom_id(gid, uid, "shop_qty_inc"), row=1,
        ))

        # ── Row 2: ⬅ | 🪙 Buy / 🪙 Sell | ➡ ────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B05\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_prev"), row=2,
        ))
        action_id = "shop_buy" if view_mode == "shop" else "shop_sell"
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, emoji="\U0001FA99",  # 🪙
            custom_id=_custom_id(gid, uid, action_id), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u27A1\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_next"), row=2,
        ))

        # ── Row 3: 📋 | ⬇ ───────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji="\U0001F4CB",  # 📋
            custom_id=_custom_id(gid, uid, "shop_qty_modal"), row=3,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B07\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_down"), row=3,
        ))

        # ── Row 4: Close ─────────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(gid, uid, "shop_close"), row=4,
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

        # Row 2: ↙ ↓ ↘ spacer spacer
        for emoji, action in [("↙", "c_downleft"), ("⬇️", "c_down"), ("↘", "c_downright")]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=emoji, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=2,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, "csp0"), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, "csp_a"), row=2,
        ))


class ConsumablesView(discord.ui.View):
    """Combat food/consumables menu — one button per item the player has."""

    def __init__(self, guild_id: int, user_id: int,
                 available_items: list[tuple[str, int]]):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        for i, (item_id, qty) in enumerate(available_items[:8]):  # max 8 items + cancel
            info = CONSUMABLE_ITEMS.get(item_id, {})
            desc = info.get("desc", "")
            name = item_id.replace("_", " ").title()
            label = f"{name} ×{qty} ({desc})"[:80]
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=label,
                custom_id=_custom_id(gid, uid, f"consume_{item_id}"),
                row=i // 4,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="❌ Back",
            custom_id=_custom_id(gid, uid, "consume_cancel"),
            row=2,
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


# ── Boat view (wilderness ocean navigation) ───────────────────────────────────

class BoatView(discord.ui.View):
    """8-directional boat navigation on the wilderness ocean.

    Row 0: 🗺️ Map | 🎒 Inv | ❓ Help | [⚓ Dock if adjacent harbor]
    Row 1: ↖ ↑ ↗
    Row 2: ← 🌊 →
    Row 3: ↙ ↓ ↘
    """

    def __init__(self, guild_id: int, user_id: int, dock_available: bool = False,
                 has_fishing_rod: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.primary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv | Help | Dock (if available)
        self.add_item(_btn("Map",  "map",        0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory",  0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Help", "help",       0, discord.ButtonStyle.secondary))
        if dock_available:
            self.add_item(_btn("⚓ Dock", "ocean_dock", 0, discord.ButtonStyle.success))
        # Row 1: ↖ ↑ ↗
        self.add_item(_btn("↖", "ocean_upleft",   1))
        self.add_item(_btn("⬆️", "ocean_up",       1))
        self.add_item(_btn("↗", "ocean_upright",  1))
        # Row 2: ← 🪝 →
        self.add_item(_btn("⬅️", "ocean_left",   2))
        self.add_item(_btn("🪝 Hook", "boat_grapple", 2, discord.ButtonStyle.secondary))
        self.add_item(_btn("➡️", "ocean_right",  2))
        # Row 3: ↙ ↓ ↘
        self.add_item(_btn("↙", "ocean_downleft",  3))
        self.add_item(_btn("⬇️", "ocean_down",      3))
        self.add_item(_btn("↘", "ocean_downright", 3))
        # Row 4: Ship interior | optional Fishing
        self.add_item(_btn("🚢 Ship", "ship_enter", 4, discord.ButtonStyle.secondary))
        if has_fishing_rod:
            self.add_item(_btn("🎣 Fish", "ocean_fish", 4, discord.ButtonStyle.secondary))


# ── High-seas view (separate 200×200 open-ocean grid) ────────────────────────

class OceanView(discord.ui.View):
    """8-directional high-seas navigation + Dock button."""

    def __init__(self, guild_id: int, user_id: int, dock_available: bool = False,
                 island_nearby: bool = False, has_fishing_rod: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label: str, action: str, row: int,
                 style=discord.ButtonStyle.primary, disabled: bool = False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv | Help | ⚓ Dock | 🏝️ Island (if nearby)
        self.add_item(_btn("Map",  "map",       0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory", 0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Help", "help",      0, discord.ButtonStyle.secondary))
        if dock_available:
            self.add_item(_btn("⚓ Dock", "ocean_dock", 0, discord.ButtonStyle.success))
        if island_nearby:
            self.add_item(_btn("🏝️ Island", "island_dock_hs", 0, discord.ButtonStyle.success))

        # Row 1: ↖ ↑ ↗
        self.add_item(_btn("↖", "ocean_upleft",   1))
        self.add_item(_btn("⬆️", "ocean_up",       1))
        self.add_item(_btn("↗", "ocean_upright",  1))

        # Row 2: ← 🪝 →
        self.add_item(_btn("⬅️", "ocean_left",   2))
        self.add_item(_btn("🪝 Hook", "boat_grapple", 2, discord.ButtonStyle.secondary))
        self.add_item(_btn("➡️", "ocean_right",  2))

        # Row 3: ↙ ↓ ↘
        self.add_item(_btn("↙", "ocean_downleft",  3))
        self.add_item(_btn("⬇️", "ocean_down",      3))
        self.add_item(_btn("↘", "ocean_downright", 3))

        # Row 4: Ship interior | optional Fishing
        self.add_item(_btn("🚢 Ship", "ship_enter", 4, discord.ButtonStyle.secondary))
        if has_fishing_rod:
            self.add_item(_btn("🎣 Fish", "ocean_fish", 4, discord.ButtonStyle.secondary))


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


class ShrineView(discord.ui.View):
    """Shrine enchantment menu — choose a gem imbuing sacrifice."""

    def __init__(self, guild_id: int, user_id: int,
                 inv_counts: dict[str, int] | None = None):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        inv_counts = inv_counts or {}
        keys = list(SHRINE_SACRIFICES.keys())
        for i, stype in enumerate(keys):
            data = SHRINE_SACRIFICES[stype]
            have = inv_counts.get(data["item"], 0)
            need = data["qty"]
            enough = have >= need
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary if enough else discord.ButtonStyle.secondary,
                label=f"{data['label']} ({have}/{need})"[:80],
                disabled=not enough,
                custom_id=_custom_id(gid, uid, f"shrine_{stype}"),
                row=i // 3,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "shrine_cancel"),
            row=2,
        ))


class ForgeView(discord.ui.View):
    """Forge interaction menu: smelt iron/gold ore into ingots, craft gold ring."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        for label, act, style, row in [
            ("🔥 Smelt Iron (1 ore → 1 ingot)",    "forge_iron",      discord.ButtonStyle.primary, 0),
            ("🟡 Smelt Gold (1 ore → 1 ingot)",    "forge_gold",      discord.ButtonStyle.primary, 0),
            ("💍 Gold Ring (2 gold ingots)",        "forge_gold_ring", discord.ButtonStyle.primary, 1),
            ("❌ Close",                            "forge_close",     discord.ButtonStyle.danger,  1),
        ]:
            self.add_item(discord.ui.Button(
                style=style, label=label,
                custom_id=_custom_id(guild_id, user_id, act), row=row,
            ))


class AnvilView(discord.ui.View):
    """Anvil interaction menu: craft weapons and armor from iron ingots."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        for label, act, style, row in [
            ("🗡️ Dagger (1 ingot)",       "anvil_dagger",      discord.ButtonStyle.primary, 0),
            ("⚔️ Sword (2 ingots)",       "anvil_sword",       discord.ButtonStyle.primary, 0),
            ("🪖 Helmet (2 ingots)",      "anvil_helmet",      discord.ButtonStyle.primary, 0),
            ("🛡️ Chestplate (4 ingots)",  "anvil_chestplate",  discord.ButtonStyle.primary, 1),
            ("👖 Leggings (3 ingots)",    "anvil_leggings",    discord.ButtonStyle.primary, 1),
            ("💣 Cannonball (4 ingots)",  "anvil_cannonball",  discord.ButtonStyle.primary, 1),
            ("🥾 Iron Boots (2 ingots)",  "anvil_iron_boots",  discord.ButtonStyle.primary, 2),
            ("❌ Close",                  "anvil_close",        discord.ButtonStyle.danger,  2),
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


# ── Gold cap helper ───────────────────────────────────────────────────────────

def _apply_gold_cap(player: Player, amount: int) -> int:
    """Add amount to player.gold respecting coin purse capacity. Returns actual added."""
    cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
    before = player.gold
    player.gold = min(player.gold + amount, cap)
    return player.gold - before


# ── Equipment helpers ─────────────────────────────────────────────────────────

def _equipped_dict(player: Player) -> dict:
    d = {}
    for slot, val in [
        ("hand_1", player.hand_1), ("hand_2", player.hand_2),
        ("head", player.head), ("chest", player.chest),
        ("legs", player.legs), ("boots", player.boots),
        ("accessory", player.accessory), ("pouch", player.pouch),
        ("coin_purse", player.coin_purse),
    ]:
        if val:
            d[slot] = val
    return d


def _inv_capacity(player: Player) -> tuple[int, int]:
    """Return (rows, cols) for player's current inventory based on equipped pouch."""
    return POUCH_SIZES.get(player.pouch, POUCH_SIZES[None])


def _inv_action_btn(
    items: list[dict], selected: int, equipped: dict,
    cursor_mode: str = "inventory", equipped_cursor: int = 0,
) -> tuple[str, str]:
    """Return (button_emoji, button_action) for the primary inventory action button.
    Labels are emoji-only — no text."""
    if cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
        if equipped_cursor < len(_EQUIP_SLOT_ORDER):
            slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
            if equipped.get(slot):
                return ("\u2935\uFE0F", "inv_unequip")  # ⤵️ arrow heading down = unequip
        return ("", "")
    if cursor_mode == "gold":
        return ("", "")
    # inventory mode — use slot_index-aware lookup
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    ci = _cursor_item(visible, selected)
    if ci is not None:
        item_id = ci["item_id"]
        if item_id in FOOD_HP_RESTORE:
            return ("\U0001F357", "inv_eat")            # 🍗 eat
        if item_id in ITEM_EQUIP_SLOTS:
            if item_id in equipped.values():
                return ("\U0001FAF4", "inv_equip")      # 🫴 palm up = give back
            return ("\U0001F590\uFE0F", "inv_equip")    # 🖐️ hand splayed = equip
    return ("", "")


def _equip_label(items: list[dict], selected: int, equipped: dict) -> str:
    """Legacy helper — returns the display label only (no action id)."""
    return _inv_action_btn(items, selected, equipped)[0]


async def _auto_unequip_depleted(db, user_id: int, item_id: str, player: Player) -> None:
    """Unequip item from hand slots if all inventory stacks of it are now empty."""
    rows = await db.fetch_all(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
    )
    total = sum(r["quantity"] for r in rows)
    if total > 0:
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
    _apply_gold_cap(player, gold_rew)
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
) -> tuple[str, bool, str, bool, bool]:
    """Return (center_label, center_enabled, action_label, action_enabled, edit_enabled).

    center = on-tile interaction (interact button at row-1 center)
    action = adjacent-tile interaction (action button at row-0 col-2)
    edit   = ⚒️ Edit button at row-0 col-4 (player-house owners only)
    """
    vc = 4  # VIEWPORT_CENTER

    center_label, center_enabled = "", False
    action_label, action_enabled = "", False
    edit_enabled = False

    if not grid or len(grid) <= vc:
        return center_label, center_enabled, action_label, action_enabled, edit_enabled

    # ── Inside a player house ─────────────────────────────────────────────────
    _in_ph = player.in_house and player.house_type == "player_house"
    if _in_ph:
        if _ui_state.get(player.user_id, {}).get("is_house_owner", False):
            edit_enabled = True
        # Fall through to center_tile checks so b_stove etc. still work.
        # PH chests are handled after the main block below.

    center_tile = grid[vc][vc] if len(grid[vc]) > vc else None
    if center_tile:
        t = center_tile.terrain
        s = center_tile.structure

        # Ship tile context (highest priority when in_ship)
        if player.in_ship:
            if t == "ship_helm":
                center_label, center_enabled = "⚓", True
            elif t == "ship_door":
                center_label, center_enabled = "🚪", True
            elif t == "ship_chest_personal":
                from dwarf_explorer.config import SHIP_EMOJI
                center_label, center_enabled = SHIP_EMOJI.get("ship_chest_personal", "📦"), True
            elif t == "ship_chest_cargo":
                from dwarf_explorer.config import SHIP_EMOJI
                center_label, center_enabled = SHIP_EMOJI.get("ship_chest_cargo", "📦"), True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled

        # Island tile context
        if player.in_island:
            if t == "island_dock":
                center_label, center_enabled = "⛵ Leave", True
            elif t == "island_chest":
                center_label, center_enabled = "💰 Loot", True
            elif t in ("island_forest", "island_tree") and "axe" in hand_items:
                center_label, center_enabled = "🪓", True
            # Fishing: adjacent to island_void (open ocean surrounding island)
            local_adj: set[str] = set()
            for _ro, _co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _r, _c = vc + _ro, vc + _co
                if 0 <= _r < len(grid) and 0 <= _c < len(grid[_r]):
                    _adj = grid[_r][_c]
                    if _adj.terrain:
                        local_adj.add(_adj.terrain)
            if "fishing_rod" in hand_items and "island_void" in local_adj:
                action_label, action_enabled = "🎣 Fish", True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled

        # Structural overrides (cave/village on overworld)
        if s == "player_house":
            center_label, center_enabled = "🏠", True
        elif t == "player_house_cave":
            center_label, center_enabled = "🏠", True
        elif s == "cave":
            center_label, center_enabled = "🕳️", True
        elif s == "village":
            center_label, center_enabled = "🏘️", True
        elif s == "shrine":
            center_label, center_enabled = "⛩️", True
        elif s in ("ruins", "ruins_looted"):
            center_label, center_enabled = "🏚️", True
        elif s == "harbor":
            center_label, center_enabled = "🚢 Harbor", True
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
        elif t == "vil_dock":
            center_label, center_enabled = "⚓ Board", True
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
        elif t == "drop_box":
            center_label, center_enabled = "🤲", True
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

    return center_label, center_enabled, action_label, action_enabled, edit_enabled


async def _load_house_grid(player: Player, db) -> list[list]:
    """Load the correct viewport for whichever house type the player is in."""
    if player.house_type == "player_house":
        return await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    return await load_building_viewport(player.house_id, player.house_x, player.house_y, db)


def _game_view(guild_id: int, user_id: int, player: Player,
               mine_dirs: frozenset[str] = frozenset(),
               grid: list[list] | None = None,
               dock_available: bool = False) -> discord.ui.View:
    """Build the appropriate game view, computing context labels if grid is provided."""
    has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")

    # When player is in ship, use ship tile view (GameView with ship grid)
    if player.in_ship:
        if grid is None:
            grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
        # Fall through to GameView builder below (skip other mode checks)
    elif player.in_island:
        pass  # Fall through to GameView; caller must supply grid
    elif player.in_high_seas:
        island_nearby = bool(_ui_state.get(user_id, {}).get("island_target"))
        return OceanView(guild_id, user_id,
                         dock_available=(player.ocean_y == 0),
                         island_nearby=island_nearby,
                         has_fishing_rod=has_fishing_rod)
    elif player.in_ocean:
        return BoatView(guild_id, user_id, dock_available=dock_available,
                        has_fishing_rod=has_fishing_rod)
    elif player.in_canoe:
        return CanoeView(guild_id, user_id, dock_available=False)

    center_label, center_enabled = "", False
    action_label, action_enabled = "", False
    edit_enabled = False

    if grid is not None:
        hand_items: set[str] = set()
        if player.hand_1:
            hand_items.add(player.hand_1)
        if player.hand_2:
            hand_items.add(player.hand_2)
        center_label, center_enabled, action_label, action_enabled, edit_enabled = \
            _compute_context_labels(grid, player, hand_items)

    return GameView(guild_id, user_id,
                    boots_equipped=(player.boots is not None),
                    sprinting=player.sprinting,
                    mine_dirs=mine_dirs,
                    center_label=center_label,
                    center_enabled=center_enabled,
                    action_label=action_label,
                    action_enabled=action_enabled,
                    edit_enabled=edit_enabled)


async def _cave_game_view(guild_id: int, user_id: int, player: Player, db,
                           grid: list[list] | None = None) -> GameView:
    """Build a GameView with mine buttons for any adjacent mineable tiles."""
    mine_dirs: set[str] = set()
    if player.in_cave:
        for direction, (dx, dy) in DIRECTIONS.items():
            tile = await load_cave_single_tile(
                player.cave_id, player.cave_x + dx, player.cave_y + dy, db
            )
            if tile.terrain in ("cave_rock", "iron_ore_deposit", "gold_ore_deposit"):
                mine_dirs.add(direction)
    return _game_view(guild_id, user_id, player, frozenset(mine_dirs), grid=grid)


def _ship_game_view(guild_id: int, user_id: int, player: Player) -> discord.ui.View:
    """Build a GameView for ship interior with contextual center button."""
    grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
    return _game_view(guild_id, user_id, player, grid=grid)


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


async def _adjacent_harbor(player: Player, seed: int, db) -> tuple[int, int] | None:
    """Return world coords of the first adjacent harbor structure tile, or None.

    Used by boat mode to decide whether to show the ⚓ Dock button.
    """
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if t.structure == "harbor":
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


async def _find_ocean_tile_near(wx: int, wy: int, seed: int, db) -> tuple[int, int]:
    """Scan outward from (wx, wy) and return the nearest ocean tile coords.

    Tries cardinal neighbours first, then diagonals, then 2-tile radius.
    Falls back to (wx, wy) itself if nothing found within range.
    """
    ocean_types = {"deep_water", "shallow_water"}
    search_offsets = [
        (0, -1), (0, 1), (-1, 0), (1, 0),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
        (0, -2), (0, 2), (-2, 0), (2, 0),
        (-1, -2), (1, -2), (-1, 2), (1, 2),
        (-2, -1), (2, -1), (-2, 1), (2, 1),
    ]
    for ddx, ddy in search_offsets:
        ax, ay = wx + ddx, wy + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if (t.structure or t.terrain) in ocean_types:
                return (ax, ay)
    return (wx, wy)


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

    if player.in_ship:
        nx, ny = player.ship_x + dx, player.ship_y + dy
        # Door transition takes priority over walkability
        door_target = get_door_target(player.ship_room, nx, ny)
        if door_target:
            new_room, new_x, new_y = door_target
            player.ship_room = new_room
            player.ship_x, player.ship_y = new_x, new_y
            await update_player_ship_state(db, user_id, True, new_room,
                                           ship_x=new_x, ship_y=new_y)
            _room_names = {"helm": "the helm deck",
                           "quarters": "the captain's quarters",
                           "lower_deck": "the lower deck"}
            grid = load_ship_viewport(new_room, new_x, new_y)
            return (render_grid(grid, player,
                                f"\U0001F6AA You enter {_room_names.get(new_room, new_room)}."),
                    _game_view(guild_id, user_id, player, grid=grid))
        target_grid = load_ship_viewport(player.ship_room, nx, ny)
        target_tile = target_grid[4][4]
        ok, msg = can_move_ship(target_tile)
        if not ok:
            grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
            return render_grid(grid, player, f"\U0001F6AB {msg}"), \
                   _game_view(guild_id, user_id, player, grid=grid)
        player.ship_x, player.ship_y = nx, ny
        await update_player_ship_state(db, user_id, True, player.ship_room,
                                       ship_x=nx, ship_y=ny)
        grid = load_ship_viewport(player.ship_room, nx, ny)
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

    elif player.in_house:
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

    elif player.in_island:
        from dwarf_explorer.config import ISLAND_WALKABLE
        from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
        ox, oy = player.island_ox, player.island_oy
        px, py = player.ocean_x, player.ocean_y
        nx, ny = px + dx, py + dy

        _island_id, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
        tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
        target_terrain = tile_map.get((nx, ny), "island_void")

        if target_terrain not in ISLAND_WALKABLE:
            grid = load_island_viewport(tiles, px, py)
            return render_grid(grid, player, "You can't go that way."), \
                   _game_view(guild_id, user_id, player, grid=grid)

        player.ocean_x, player.ocean_y = nx, ny
        await update_player_ocean_state(db, user_id, False, nx, ny)
        grid = load_island_viewport(tiles, nx, ny)
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
                    player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
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
                    player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
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
        player.in_ocean = False
        player.in_high_seas = False
        await update_player_stats(db, user_id, hp=player.hp, in_canoe=0, in_ocean=0)
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_cave_state(db, user_id, False, None, 0, 0)
        await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        await update_player_position(db, user_id, player.world_x, player.world_y)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        return render_grid(grid, player, f"{extra_msg} {msg}"), _game_view(guild_id, user_id, player, grid=grid)

    # Ship sank during naval combat
    if player.ship_hp <= 0:
        player.ship_hp = 1  # needs repair but ship isn't gone
        await update_player_ship_hp(db, user_id, player.ship_hp)
        # Wash player ashore at harbor world position
        harbor_wx = getattr(player, "ocean_harbor_wx", player.world_x)
        harbor_wy = getattr(player, "ocean_harbor_wy", player.world_y)
        player.in_high_seas = False
        player.in_ocean = False
        player.in_ship = False
        player.world_x, player.world_y = harbor_wx, harbor_wy
        await update_player_ocean_state(db, user_id, False, 0, 0, in_high_seas=False)
        await update_player_ship_state(db, user_id, False, player.ship_room)
        await update_player_position(db, user_id, player.world_x, player.world_y)
        await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        sink_msg = f"{extra_msg} 🛳️💥 Your ship sinks! You wash ashore near the harbor. Hull at 1/{player.ship_max_hp} — repair with logs from the cargo chest."
        return render_grid(grid, player, sink_msg), _game_view(guild_id, user_id, player, grid=grid)

    await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
    # Return to the appropriate location view
    if player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        return render_grid(grid, player, extra_msg), await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    if player.in_high_seas:
        from dwarf_explorer.world.terrain import get_coast_boundary as _gcb2
        _hs_ce, _ = _gcb2(seed)
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        return render_grid(grid, player, extra_msg), OceanView(guild_id, user_id,
                                                               dock_available=_hs_at_harbor(player.ocean_x, player.ocean_y, _hs_ce),
                                                               has_fishing_rod=has_rod)
    if player.in_ocean:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        harbor_adj = await _adjacent_harbor(player, seed, db)
        return render_grid(grid, player, extra_msg), BoatView(guild_id, user_id,
                                                              dock_available=(harbor_adj is not None))
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    return render_grid(grid, player, extra_msg), _game_view(guild_id, user_id, player, grid=grid)


async def _after_player_action(
    interaction: discord.Interaction,
    db, guild_id: int, user_id: int,
    player, arena: dict, msg: str,
) -> None:
    """Called after a player action. Run enemy turn if moves exhausted, or re-render."""
    arena["combat_log"].append(msg)

    is_naval = arena.get("naval", False)

    def _is_dead() -> bool:
        return (player.ship_hp <= 0) if is_naval else (player.hp <= 0)

    # Enemy dead?
    if player.combat_enemy_hp <= 0:
        victory_msg = apply_victory(player)
        arena["combat_log"].append(victory_msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]), won=True)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Player / ship dead?
    if _is_dead():
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
    enemy_msg = resolve_enemy_turn(arena, player, rng, naval=is_naval)
    arena["combat_log"].append(enemy_msg)

    # Restore player moves for next turn
    player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)

    # Check outcomes after enemy turn
    if _is_dead():
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
    """Open the consumables menu in combat."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result

    # Naval combat: food can't repair the ship
    if arena.get("naval"):
        arena["combat_log"].append("⚓ You can't eat to repair the ship! Use logs from the cargo chest.")
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Build list of consumables the player has
    available: list[tuple[str, int]] = []
    for item_id in CONSUMABLE_ITEMS:
        rows = await db.fetch_all(
            "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
            (user_id, item_id)
        )
        total = rows[0]["total"] if rows and rows[0]["total"] else 0
        if total > 0:
            available.append((item_id, total))

    if not available:
        arena["combat_log"].append("🍗 You have no food! Fish and cook at a hearth for HP recovery.")
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    lines = ["**🍗 Consumables** — select an item to use (costs 1 turn):", ""]
    for item_id, qty in available:
        info = CONSUMABLE_ITEMS.get(item_id, {})
        desc = info.get("desc", "")
        name = item_id.replace("_", " ").title()
        lines.append(f"• **{name}** ×{qty}  —  {desc}")
    content = "\n".join(lines)
    view = ConsumablesView(guild_id, user_id, available)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_combat_consume(
    interaction: discord.Interaction, guild_id: int, user_id: int, item_id: str
) -> None:
    """Consume a specific food item during combat."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result

    row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
    )
    if not row:
        arena["combat_log"].append(f"You no longer have any {item_id.replace('_', ' ')}.")
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await remove_from_inventory(db, user_id, item_id, 1)
    heal_amt = FOOD_HP_RESTORE.get(item_id, CONSUMABLE_ITEMS.get(item_id, {}).get("hp", 10))
    heal = min(heal_amt, player.max_hp - player.hp)
    player.hp += heal
    player.combat_moves_left -= 1
    msg = f"🍗 You eat {item_id.replace('_', ' ')}! Restored **{heal}** HP. ({player.hp}/{player.max_hp})"
    await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)


async def handle_combat_consume_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel consumables menu, return to combat."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
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
    if tile.terrain not in ("cave_rock", "iron_ore_deposit", "gold_ore_deposit"):
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
    # Get cave level for drop bonuses
    cave_meta = await db.fetch_one(
        "SELECT level FROM caves WHERE cave_id=?", (player.cave_id,)
    )
    cave_level = cave_meta["level"] if cave_meta else 1

    loot = []
    if tile.terrain == "gold_ore_deposit":
        ore_count = rng.randint(2, 6)
        await add_to_inventory(db, user_id, "gold_ore", ore_count)
        loot.append(f"{ore_count} gold ore")
    elif tile.terrain == "iron_ore_deposit":
        ore_count = rng.randint(3, 9)
        # Luck ring bonus: +1 ore
        if player.accessory == "ring_of_luck":
            ore_count += 1
        await add_to_inventory(db, user_id, "iron_ore", ore_count)
        loot.append(f"{ore_count} iron ore")
    else:
        rock_count = rng.randint(1, 3)
        await add_to_inventory(db, user_id, "rock", rock_count)
        loot.append(f"{rock_count} rock{'s' if rock_count > 1 else ''}")
        if rng.random() < 0.33:
            await add_to_inventory(db, user_id, "flint", 1)
            loot.append("flint")
        # Iron ore chance from regular rocks (level-dependent)
        iron_chance = {1: 0.15, 2: 0.15, 3: 0.15}.get(cave_level, 0.15)
        if rng.random() < iron_chance:
            await add_to_inventory(db, user_id, "iron_ore", 1)
            loot.append("iron ore")
        # Gold ore chance from regular rocks (level 2: 1%, level 3: 5%)
        gold_chance = {2: 0.01, 3: 0.05}.get(cave_level, 0.0)
        if gold_chance > 0 and rng.random() < gold_chance:
            await add_to_inventory(db, user_id, "gold_ore", 1)
            loot.append("gold ore")

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
    elif player.in_ship:
        grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
        view = _ship_game_view(guild_id, user_id, player)
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


# ── Ocean handlers ────────────────────────────────────────────────────────────

_OCEAN_DIRS: dict[str, tuple[int, int]] = {
    "up":        (0, -1),
    "down":      (0,  1),
    "left":      (-1,  0),
    "right":     (1,  0),
    "upleft":    (-1, -1),
    "upright":   (1, -1),
    "downleft":  (-1,  1),
    "downright": (1,  1),
}


def _hs_spawn(world_x: int, world_y: int, coast_edge: int) -> tuple[int, int]:
    """Return (ocean_x, ocean_y) spawn position when entering the high seas.

    The player always spawns one tile in from the harbor/coast boundary so
    they can sail back with a single move.
      edge 0 (south): harbor at oy=0, deep at high oy  → spawn oy=1
      edge 1 (north): harbor at oy=OCEAN_SIZE-1         → spawn oy=OCEAN_SIZE-2
      edge 2 (west) : harbor at ox=OCEAN_SIZE-1         → spawn ox=OCEAN_SIZE-2
      edge 3 (east) : harbor at ox=0                    → spawn ox=1
    """
    cross = int
    if coast_edge in (0, 1):        # N/S ocean: world_x maps to ocean_x
        ox = max(0, min(OCEAN_SIZE - 1, int(world_x / WORLD_SIZE * OCEAN_SIZE)))
        oy = 1 if coast_edge == 0 else OCEAN_SIZE - 2
    else:                            # E/W ocean: world_y maps to ocean_y
        oy = max(0, min(OCEAN_SIZE - 1, int(world_y / WORLD_SIZE * OCEAN_SIZE)))
        ox = OCEAN_SIZE - 2 if coast_edge == 2 else 1
    return ox, oy


def _hs_at_harbor(ox: int, oy: int, coast_edge: int) -> bool:
    """True when one more step toward shore would leave the high-seas grid."""
    return (
        (coast_edge == 0 and oy == 0) or
        (coast_edge == 1 and oy == OCEAN_SIZE - 1) or
        (coast_edge == 2 and ox == OCEAN_SIZE - 1) or
        (coast_edge == 3 and ox == 0)
    )


def _hs_past_harbor(nx: int, ny: int, coast_edge: int) -> bool:
    """True when the proposed move steps outside the high-seas grid on the harbor side."""
    return (
        (coast_edge == 0 and ny < 0) or
        (coast_edge == 1 and ny >= OCEAN_SIZE) or
        (coast_edge == 2 and nx >= OCEAN_SIZE) or
        (coast_edge == 3 and nx < 0)
    )


async def handle_ocean_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        await interaction.response.defer()
        return

    dx, dy = _OCEAN_DIRS.get(direction, (0, 0))

    # ── High-seas mode (separate 200×200 grid) ──────────────────────────────
    if player.in_high_seas:
        nx, ny = player.ocean_x + dx, player.ocean_y + dy

        from dwarf_explorer.world.terrain import get_coast_boundary as _gcb
        _hs_coast_edge, _ = _gcb(seed)

        # Moving back past the harbor boundary → auto-return to harbour village
        if _hs_past_harbor(nx, ny, _hs_coast_edge):
            hwx, hwy = player.ocean_harbor_wx, player.ocean_harbor_wy
            vid, _vx, _vy, dock_x, dock_y = await get_or_create_harbor_village(seed, hwx, hwy, db)
            player.in_high_seas = False
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = dock_x, dock_y
            player.village_wx, player.village_wy = hwx, hwy
            await update_player_ocean_state(db, user_id, False, 0, 0)
            await update_player_village_state(db, user_id, True, vid, dock_x, dock_y, hwx, hwy)
            grid = await load_village_viewport(vid, dock_x, dock_y, db)
            content = render_grid(grid, player, "⚓ You sail back into the harbour.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return

        if not (0 <= nx < OCEAN_SIZE and 0 <= ny < OCEAN_SIZE):
            grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
            content = render_grid(grid, player, "The vast ocean stretches endlessly in that direction.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=OceanView(guild_id, user_id,
                               dock_available=_hs_at_harbor(player.ocean_x, player.ocean_y, _hs_coast_edge)),
            )
            return

        target_ocean = load_ocean_single_tile(nx, ny, seed)
        if target_ocean.structure == "island":
            # Block movement onto island tile — show dock button instead
            _ui_state[user_id] = {**_ui_state.get(user_id, {}), "island_target": (nx, ny)}
            has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
            grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
            content = render_grid(grid, player,
                "🏝️ An island lies ahead. Use 🏝️ Island to go ashore.")
            view = OceanView(guild_id, user_id,
                             dock_available=_hs_at_harbor(player.ocean_x, player.ocean_y, _hs_coast_edge),
                             island_nearby=True,
                             has_fishing_rod=has_rod)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        # Clear any stale island_target when moving away
        if _ui_state.get(user_id, {}).get("island_target"):
            _ui_state[user_id] = {k: v for k, v in _ui_state.get(user_id, {}).items()
                                   if k != "island_target"}

        player.ocean_x, player.ocean_y = nx, ny
        await update_player_ocean_state(db, user_id, False, nx, ny, in_high_seas=True)

        # Check for ocean encounter
        enc_rng = _random.Random(hash((user_id, nx, ny, seed, "ocean")))
        enemy_type = _roll_encounter(enc_rng, OCEAN_ENCOUNTER_RATES)
        if enemy_type:
            grid = load_ocean_viewport(nx, ny, seed)
            arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type, "ocean")))
            arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
            arena["naval"] = True  # enemy attacks damage ship_hp, not player_hp
            player.in_combat = True
            player.combat_enemy_type = enemy_type
            player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
            player.combat_enemy_x = ex
            player.combat_enemy_y = ey
            player.combat_player_x = ARENA_SIZE // 2
            player.combat_player_y = ARENA_SIZE // 2
            player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
            _ui_state[user_id] = {"type": "combat", "arena": arena}
            await save_combat_state(db, user_id, player)
            content = render_arena(arena, player)
            view = CombatView(guild_id, user_id,
                              trapped=arena["player_trapped"],
                              moves_left=player.combat_moves_left)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        grid = load_ocean_viewport(nx, ny, seed)
        content = render_grid(grid, player)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=OceanView(guild_id, user_id,
                           dock_available=_hs_at_harbor(nx, ny, _hs_coast_edge),
                           has_fishing_rod=has_rod),
        )
        return

    # ── Boat wilderness mode (in_ocean=True, world_x/world_y used) ──────────
    nx, ny = player.world_x + dx, player.world_y + dy

    # Moving off the world edge → enter the high seas
    if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
        from dwarf_explorer.world.terrain import get_coast_boundary as _gcb
        _coast_edge, _ = _gcb(seed)
        spawn_ox, spawn_oy = _hs_spawn(player.world_x, player.world_y, _coast_edge)
        player.in_ocean = False
        player.in_high_seas = True
        player.ocean_x = spawn_ox
        player.ocean_y = spawn_oy
        has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        await update_player_ocean_state(
            db, user_id, False,
            player.ocean_x, player.ocean_y,
            player.ocean_harbor_wx, player.ocean_harbor_wy,
            in_high_seas=True,
        )
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        content = render_grid(grid, player, "🌊 You sail beyond the horizon into the open ocean!")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=OceanView(guild_id, user_id, dock_available=False, has_fishing_rod=has_rod),
        )
        return

    target = await load_single_tile(nx, ny, seed, db)
    terrain = target.structure or target.terrain

    if terrain not in OCEAN_WALKABLE:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        harbor_adj = await _adjacent_harbor(player, seed, db)
        content = render_grid(grid, player, "Your boat can't sail onto land.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=BoatView(guild_id, user_id, dock_available=(harbor_adj is not None)),
        )
        return

    # Moving onto a harbor tile → sail into harbour village
    if terrain == "harbor":
        vid, vx, vy, _dk_x, _dk_y = await get_or_create_harbor_village(seed, nx, ny, db)
        player.in_ocean = False
        player.in_village = True
        player.village_id = vid
        player.village_x, player.village_y = vx, vy
        player.village_wx, player.village_wy = nx, ny
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_village_state(db, user_id, True, vid, vx, vy, nx, ny)
        grid = await load_village_viewport(vid, vx, vy, db)
        content = render_grid(grid, player, "⚓ You sail into the harbour.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
        return

    player.world_x, player.world_y = nx, ny
    await update_player_position(db, user_id, nx, ny)
    await update_player_ocean_state(db, user_id, True)

    harbor_adj = await _adjacent_harbor(player, seed, db)
    grid = await load_viewport(nx, ny, seed, db)
    content = render_grid(grid, player)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=BoatView(guild_id, user_id, dock_available=(harbor_adj is not None)),
    )


async def handle_ocean_dock(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Dock from ocean (boat or high-seas mode) back to the harbour village."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # ── Boat wilderness mode: dock at adjacent harbour ───────────────────────
    if player.in_ocean:
        harbor = await _adjacent_harbor(player, seed, db)
        if harbor is None:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, "No harbour nearby to dock at.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=BoatView(guild_id, user_id, dock_available=False),
            )
            return
        hwx, hwy = harbor
        vid, vx, vy, _dk_x, _dk_y = await get_or_create_harbor_village(seed, hwx, hwy, db)
        player.in_ocean = False
        player.in_village = True
        player.village_id = vid
        player.village_x, player.village_y = vx, vy
        player.village_wx, player.village_wy = hwx, hwy
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_village_state(db, user_id, True, vid, vx, vy, hwx, hwy)
        grid = await load_village_viewport(vid, vx, vy, db)
        content = render_grid(grid, player, "⚓ You dock at the harbour and step ashore.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
        return

    # ── High-seas mode: must be at coast row (y=0) to dock ──────────────────
    if player.in_high_seas:
        if player.ocean_y != 0:
            grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
            content = render_grid(grid, player,
                                  "You must sail back to the shoreline (row 0) to dock.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=OceanView(guild_id, user_id, dock_available=False),
            )
            return
        hwx, hwy = player.ocean_harbor_wx, player.ocean_harbor_wy
        vid, _vx, _vy, dock_x, dock_y = await get_or_create_harbor_village(seed, hwx, hwy, db)
        player.in_high_seas = False
        player.in_village = True
        player.village_id = vid
        player.village_x, player.village_y = dock_x, dock_y
        player.village_wx, player.village_wy = hwx, hwy
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_village_state(db, user_id, True, vid, dock_x, dock_y, hwx, hwy)
        grid = await load_village_viewport(vid, dock_x, dock_y, db)
        content = render_grid(grid, player, "⚓ You dock at the harbour and step ashore.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
        return

    await interaction.response.defer()


async def handle_boat_grapple(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Toss the grappling hook overboard to dredge up sunken treasure."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        await interaction.response.defer()
        return

    rng = _random.Random()  # fresh random every cast
    roll = rng.random()
    if roll < 0.04:
        items = [("gold_coin", rng.randint(5, 20)), ("map_fragment", 1)]
        item_id, qty = rng.choice(items)
        await add_to_inventory(db, user_id, item_id, qty)
        label = "gold coins" if item_id == "gold_coin" else "a map fragment"
        msg = f"🪝 You haul up the hook… **{label} found!**"
    elif roll < 0.18:
        await add_to_inventory(db, user_id, "fish", 1)
        msg = "🪝 You haul up the hook… a **fish** tangled in the line!"
    elif roll < 0.22:
        await add_to_inventory(db, user_id, "seaweed", 1)
        msg = "🪝 You haul up a clump of **seaweed**."
    else:
        msg = "🪝 You toss the hook overboard… nothing but water."

    if player.in_high_seas:
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        content = render_grid(grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=OceanView(guild_id, user_id, dock_available=(player.ocean_y == 0)),
        )
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        harbor_adj = await _adjacent_harbor(player, seed, db)
        content = render_grid(grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=BoatView(guild_id, user_id, dock_available=(harbor_adj is not None)),
        )


# ── Ship interior handlers ────────────────────────────────────────────────────

async def handle_ship_enter(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Board the ship interior from boat mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        await interaction.response.defer()
        return

    player.in_ship = True
    player.ship_room = "helm"
    player.ship_x, player.ship_y = HELM_SPAWN
    await update_player_ship_state(db, user_id, True, "helm", ship_x=player.ship_x, ship_y=player.ship_y)

    grid = load_ship_viewport("helm", player.ship_x, player.ship_y)
    content = render_grid(grid, player, "\u2693 You board your ship at the helm.")
    view = _ship_game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_leave(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Return from ship interior back to boat navigation."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        await interaction.response.defer()
        return

    was_high_seas = player.in_high_seas
    player.in_ship = False
    player.ship_room = "helm"
    player.ship_x = 0
    player.ship_y = 0
    await update_player_ship_state(db, user_id, False, "helm", ship_x=0, ship_y=0)

    has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
    if was_high_seas:
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        content = render_grid(grid, player, "⚓ You return to the helm and take the wheel.")
        view = OceanView(guild_id, user_id, dock_available=(player.ocean_y == 0),
                        has_fishing_rod=has_rod)
    else:
        harbor_adj = await _adjacent_harbor(player, seed, db)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "⚓ You return to the helm and take the wheel.")
        view = BoatView(guild_id, user_id, dock_available=(harbor_adj is not None),
                        has_fishing_rod=has_rod)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Move player within ship interior."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        await interaction.response.defer()
        return

    dx, dy = DIRECTIONS[direction]
    nx, ny = player.ship_x + dx, player.ship_y + dy

    # Load target tile and check walkability
    target_grid = load_ship_viewport(player.ship_room, nx, ny)
    target_tile = target_grid[4][4]  # center = new position
    ok, msg = can_move_ship(target_tile)
    if not ok:
        grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
        content = render_grid(grid, player, f"\U0001F6AB {msg}")
        view = _ship_game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Check for door at target position
    door_target = get_door_target(player.ship_room, nx, ny)
    if door_target:
        new_room, new_x, new_y = door_target
        player.ship_room = new_room
        player.ship_x, player.ship_y = new_x, new_y
        await update_player_ship_state(db, user_id, True, new_room, ship_x=new_x, ship_y=new_y)
        room_names = {"helm": "the helm deck", "quarters": "the captain's quarters", "lower_deck": "the lower deck"}
        grid = load_ship_viewport(new_room, new_x, new_y)
        content = render_grid(grid, player, f"\U0001F6AA You enter {room_names.get(new_room, new_room)}.")
        view = _ship_game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Normal move
    player.ship_x, player.ship_y = nx, ny
    await update_player_ship_state(db, user_id, True, player.ship_room, ship_x=nx, ship_y=ny)
    grid = load_ship_viewport(player.ship_room, nx, ny)
    content = render_grid(grid, player, "")
    view = _ship_game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_room(
    interaction: discord.Interaction, guild_id: int, user_id: int, room: str
) -> None:
    """Navigate between ship rooms: helm / quarters / lower_deck."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        await interaction.response.defer()
        return

    player.ship_room = room
    await update_player_ship_state(db, user_id, True, room)

    # Repair logs come from the cargo chest, not player inventory
    cargo = await get_ship_cargo_items(db, user_id)
    has_logs = any(it["item_id"] == "log" and it["quantity"] >= 3 for it in cargo)
    content = render_ship_room(player)
    view = ShipView(guild_id, user_id, room=room,
                    ship_hp=player.ship_hp, ship_max_hp=player.ship_max_hp,
                    has_repair_logs=has_logs)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_repair(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Repair ship hull using 3 logs from the cargo chest → +20 HP."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        await interaction.response.defer()
        return

    if player.ship_hp >= player.ship_max_hp:
        grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
        content = render_grid(grid, player, "✅ Hull is already at full integrity.")
        view = _ship_game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Logs come from the ship cargo chest, not player inventory
    cargo = await get_ship_cargo_items(db, user_id)
    log_row = next((it for it in cargo if it["item_id"] == "log"), None)

    if not log_row or log_row["quantity"] < 3:
        grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
        content = render_grid(grid, player, "❌ You need at least 3 logs in the cargo chest to repair.")
        view = _ship_game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await ship_cargo_consume(db, user_id, "log", 3)
    heal = min(20, player.ship_max_hp - player.ship_hp)
    player.ship_hp = min(player.ship_max_hp, player.ship_hp + heal)
    await update_player_ship_hp(db, user_id, player.ship_hp)

    # Rebuild has_repair_logs from updated cargo
    cargo = await get_ship_cargo_items(db, user_id)
    has_logs = any(it["item_id"] == "log" and it["quantity"] >= 3 for it in cargo)
    content = render_ship_room(player)
    view = ShipView(guild_id, user_id, room=player.ship_room,
                    ship_hp=player.ship_hp, ship_max_hp=player.ship_max_hp,
                    has_repair_logs=has_logs)
    # Append message to content
    content += f"\n\n🔨 Hull repaired! +{heal} HP. ({player.ship_hp}/{player.ship_max_hp})"
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def _open_ship_chest(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    chest_type: str,  # "personal" | "cargo"
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if chest_type == "personal":
        chest_items = await get_ship_personal_items(db, user_id)
        chest_name = "Personal Chest"
    else:
        chest_items = await get_ship_cargo_items(db, user_id)
        chest_name = "Ship Cargo"

    player_items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    prev_arena = _ui_state.get(user_id, {}).get("arena")
    _ui_state[user_id] = {
        "type": f"ship_chest_{chest_type}",
        "selected": 0,
        "chest_view": "player",
        "prev_arena": prev_arena,
    }
    content = render_ship_chest(chest_items, player_items, 0, "player",
                                chest_name, player, inv_rows, inv_cols)
    view = ShipChestView(guild_id, user_id, chest_type, "player")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_chest_open_personal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _open_ship_chest(interaction, guild_id, user_id, "personal")


async def handle_ship_chest_open_cargo(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _open_ship_chest(interaction, guild_id, user_id, "cargo")


async def _ship_chest_action(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    chest_type: str, action: str,  # "prev" | "next" | "switch" | "deposit" | "withdraw"
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    expected_type = f"ship_chest_{chest_type}"
    if state.get("type") != expected_type:
        await interaction.response.defer()
        return

    selected = state.get("selected", 0)
    view_mode = state.get("chest_view", "player")
    chest_name = "Personal Chest" if chest_type == "personal" else "Ship Cargo"

    get_fn = get_ship_personal_items if chest_type == "personal" else get_ship_cargo_items
    dep_fn = ship_personal_deposit if chest_type == "personal" else ship_cargo_deposit
    wth_fn = ship_personal_withdraw if chest_type == "personal" else ship_cargo_withdraw

    chest_items = await get_fn(db, user_id)
    player_items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)

    msg = ""
    if action == "prev":
        source = player_items if view_mode == "player" else chest_items
        total = inv_rows * inv_cols if view_mode == "player" else 9 * 4
        selected = (selected - 1) % max(1, min(len(source), total))
    elif action == "next":
        source = player_items if view_mode == "player" else chest_items
        total = inv_rows * inv_cols if view_mode == "player" else 9 * 4
        selected = (selected + 1) % max(1, min(len(source), total))
    elif action == "switch":
        view_mode = "chest" if view_mode == "player" else "player"
        selected = 0
    elif action == "deposit":
        if selected < len(player_items):
            item = player_items[selected]
            ok = await dep_fn(db, user_id, item["item_id"], 1)
            msg = f"⬇ Deposited {item['item_id'].replace('_',' ').title()}." if ok else "❌ Could not deposit."
            chest_items = await get_fn(db, user_id)
            player_items = await get_inventory(db, user_id)
    elif action == "withdraw":
        if selected < len(chest_items):
            item = chest_items[selected]
            ok = await wth_fn(db, user_id, item["item_id"], 1)
            msg = f"⬆ Withdrew {item['item_id'].replace('_',' ').title()}." if ok else "❌ Inventory full."
            chest_items = await get_fn(db, user_id)
            player_items = await get_inventory(db, user_id)

    _ui_state[user_id] = {
        "type": expected_type, "selected": selected, "chest_view": view_mode,
        "prev_arena": state.get("prev_arena"),  # preserve so combat can be restored
    }
    content = render_ship_chest(chest_items, player_items, selected, view_mode,
                                chest_name, player, inv_rows, inv_cols)
    if msg:
        content += f"\n> {msg}"
    view = ShipChestView(guild_id, user_id, chest_type, view_mode)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_chest_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Return from ship chest view back to the ship room (or combat if opened during a fight)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    prev_arena = _ui_state.get(user_id, {}).get("prev_arena")
    _ui_state.pop(user_id, None)

    # If chest was opened during combat, restore the combat view
    if player.in_combat and prev_arena is not None:
        _ui_state[user_id] = {"type": "combat", "arena": prev_arena}
        content = render_arena(prev_arena, player)
        view = _combat_view(guild_id, user_id, prev_arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)
    content = render_grid(grid, player, "\U0001F4E6 You close the chest.")
    view = _ship_game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Island handlers ───────────────────────────────────────────────────────────

async def handle_island_arrive(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    ox: int, oy: int,
) -> None:
    """Called when player sails onto an island tile in the high seas."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
    _island_id, tiles, (dock_x, dock_y) = await get_or_create_island_data(db, ox, oy, seed)

    player.in_high_seas = False
    player.in_island = True
    player.island_ox = ox
    player.island_oy = oy
    # Place player at the dock
    player.ocean_x = dock_x
    player.ocean_y = dock_y
    await update_player_ocean_state(db, user_id, False, 0, 0, in_high_seas=False)
    await update_player_island_state(db, user_id, True, ox, oy)
    # Reuse ocean_x/ocean_y as island_x/island_y for position
    await update_player_ocean_state(db, user_id, False, dock_x, dock_y)

    grid = load_island_viewport(tiles, dock_x, dock_y)
    content = render_grid(grid, player, "🏝️ You row ashore onto the island.")
    # Clear any island_target from high-seas ui_state
    _ui_state.pop(user_id, None)
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Move player within island interior."""
    from dwarf_explorer.config import ISLAND_WALKABLE
    from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport, ISLAND_SIZE
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_island:
        await interaction.response.defer()
        return

    ox, oy = player.island_ox, player.island_oy
    # player position stored in ocean_x/ocean_y while on island
    px, py = player.ocean_x, player.ocean_y

    _DIRS = {"up": (0,-1), "down": (0,1), "left": (-1,0), "right": (1,0)}
    dx, dy = _DIRS.get(direction, (0, 0))
    nx, ny = px + dx, py + dy

    _island_id, tiles, (dock_x, dock_y) = await get_or_create_island_data(db, ox, oy, seed)
    tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
    target_terrain = tile_map.get((nx, ny), "island_void")

    if target_terrain not in ISLAND_WALKABLE:
        grid = load_island_viewport(tiles, px, py)
        content = render_grid(grid, player, "You can't go that way.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    player.ocean_x, player.ocean_y = nx, ny
    await update_player_ocean_state(db, user_id, False, nx, ny)

    grid = load_island_viewport(tiles, nx, ny)
    content = render_grid(grid, player)
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_loot(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Loot the island chest (once per island)."""
    from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_island:
        await interaction.response.defer()
        return

    ox, oy = player.island_ox, player.island_oy
    px, py = player.ocean_x, player.ocean_y

    already = await is_island_looted(db, ox, oy)
    _island_id, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
    grid = load_island_viewport(tiles, px, py)
    if already:
        content = render_grid(grid, player, "💰 The chest has already been looted.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await mark_island_looted(db, ox, oy)

    loot_rng = _random.Random(hash((ox, oy, seed, "island_loot")))
    roll = loot_rng.random()
    if roll < 0.4:
        item_id, qty = "gold_coin", loot_rng.randint(10, 50)
    elif roll < 0.65:
        item_id, qty = "gem", loot_rng.randint(1, 3)
    elif roll < 0.80:
        item_id, qty = "map_fragment", 1
    else:
        item_id, qty = "iron_ingot", loot_rng.randint(2, 5)

    await add_to_inventory(db, user_id, item_id, qty)
    label = item_id.replace("_", " ").title()

    content = render_grid(grid, player, f"💰 You pry open the chest — **{label} ×{qty}**!")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_leave(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Leave island, return to high seas at the island's ocean coordinates."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_island:
        await interaction.response.defer()
        return

    ox, oy = player.island_ox, player.island_oy
    player.in_island = False
    player.in_high_seas = True
    player.ocean_x, player.ocean_y = ox, oy
    await update_player_island_state(db, user_id, False)
    await update_player_ocean_state(db, user_id, False, ox, oy, in_high_seas=True)

    has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
    grid = load_ocean_viewport(ox, oy, seed)
    content = render_grid(grid, player, "⛵ You row back to your boat.")
    view = OceanView(guild_id, user_id, dock_available=(oy == 0), has_fishing_rod=has_rod)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ocean_fish(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Handle the 🎣 Fish button from OceanView or BoatView."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        await interaction.response.defer()
        return

    hand_items: set[str] = set()
    if player.hand_1:
        hand_items.add(player.hand_1)
    if player.hand_2:
        hand_items.add(player.hand_2)

    if "fishing_rod" not in hand_items:
        await interaction.response.defer()
        return

    roll = _random.random()
    if roll < 0.45:
        await add_to_inventory(db, user_id, "fish", 1)
        msg = "🎣 You cast your line into the ocean... and reel in a **fish**!"
    elif roll < 0.50:
        await add_to_inventory(db, user_id, "gem", 1)
        msg = "🎣 Something shiny on the hook — you pulled up a **gem**!"
    elif roll < 0.51:
        await add_to_inventory(db, user_id, "map_fragment", 1)
        msg = "🎣 You reel in something unusual — a **map fragment**!"
    else:
        msg = "🎣 You cast your line... the fish got away."

    has_rod = True
    if player.in_high_seas:
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        island_nearby = bool(_ui_state.get(user_id, {}).get("island_target"))
        view = OceanView(guild_id, user_id,
                         dock_available=(player.ocean_y == 0),
                         island_nearby=island_nearby,
                         has_fishing_rod=has_rod)
    else:
        harbor_adj = await _adjacent_harbor(player, seed, db)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        view = BoatView(guild_id, user_id,
                        dock_available=(harbor_adj is not None),
                        has_fishing_rod=has_rod)
    content = render_grid(grid, player, msg)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_dock_hs(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Dock at an island from the high seas (triggered by 🏝️ Island button)."""
    state = _ui_state.get(user_id, {})
    island_target = state.get("island_target")
    if not island_target:
        await interaction.response.defer()
        return
    ox, oy = island_target
    await handle_island_arrive(interaction, guild_id, user_id, ox, oy)


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

    # Ship interior tile interactions
    if player.in_ship:
        center_tile_type = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y)[4][4].terrain
        if center_tile_type == "ship_helm":
            await handle_ship_leave(interaction, guild_id, user_id)
            return
        elif center_tile_type == "ship_chest_personal":
            await handle_ship_chest_open_personal(interaction, guild_id, user_id)
            return
        elif center_tile_type == "ship_chest_cargo":
            await handle_ship_chest_open_cargo(interaction, guild_id, user_id)
            return
        else:
            await interaction.response.defer()
            return

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
                stick_rows = await db.fetch_all(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='stick'", (user_id,)
                )
                resin_rows = await db.fetch_all(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='resin'", (user_id,)
                )
                ingot_rows = await db.fetch_all(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
                )
                stick_count = sum(r["quantity"] for r in stick_rows)
                resin_count = sum(r["quantity"] for r in resin_rows)
                ingot_count = sum(r["quantity"] for r in ingot_rows)
                torch_batches = min(stick_count, resin_count)
                cannonball_batches = ingot_count // 4
                grid = await _load_house_grid()
                if cannonball_batches > 0:
                    await remove_from_inventory(db, user_id, "iron_ingot", cannonball_batches * 4)
                    await add_to_inventory(db, user_id, "cannonball", cannonball_batches)
                    content = render_grid(grid, player, f"⚒️ Forged {cannonball_batches} cannonball{'s' if cannonball_batches > 1 else ''} from {cannonball_batches * 4} iron ingots!")
                elif torch_batches > 0:
                    await remove_from_inventory(db, user_id, "stick", torch_batches)
                    await remove_from_inventory(db, user_id, "resin", torch_batches)
                    await add_to_inventory(db, user_id, "torch", torch_batches)
                    content = render_grid(grid, player, f"⚒️ Crafted {torch_batches} torch{'es' if torch_batches > 1 else ''} from sticks & resin.")
                else:
                    content = render_grid(grid, player, "\"1 stick + 1 resin = 1 torch. 4 iron ingots = 1 cannonball. Use 🔥 Forge to smelt ore, ⚒️ Anvil to craft weapons.\"")

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

        elif vtile.terrain == "vil_dock":
            # ── Board the boat from the harbour dock → wilderness ocean ───────
            hwx, hwy = player.village_wx, player.village_wy
            # Find the nearest ocean tile adjacent to the harbor world position
            ox, oy = await _find_ocean_tile_near(hwx, hwy, seed, db)
            player.in_village = False
            player.in_ocean = True
            player.world_x, player.world_y = ox, oy
            player.ocean_harbor_wx = hwx
            player.ocean_harbor_wy = hwy
            await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
            await update_player_ocean_state(db, user_id, True, 0, 0, hwx, hwy)
            await update_player_position(db, user_id, ox, oy)
            grid = await load_viewport(ox, oy, seed, db)
            harbor_adj = await _adjacent_harbor(player, seed, db)
            content = render_grid(grid, player,
                "⚓ You cast off from the dock! Sail into the ocean or use ⚓ Dock to return.")
            view = BoatView(guild_id, user_id, dock_available=(harbor_adj is not None))
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

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

    elif player.in_island:
        from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
        ox, oy = player.island_ox, player.island_oy
        px, py = player.ocean_x, player.ocean_y

        _iid, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
        tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
        current_terrain = tile_map.get((px, py), "island_void")

        hand_items: set[str] = set()
        if player.hand_1:
            hand_items.add(player.hand_1)
        if player.hand_2:
            hand_items.add(player.hand_2)

        if current_terrain == "island_dock":
            # Leave island → return to high seas
            player.in_island = False
            player.in_high_seas = True
            player.ocean_x, player.ocean_y = ox, oy
            await update_player_island_state(db, user_id, False)
            await update_player_ocean_state(db, user_id, False, ox, oy, in_high_seas=True)
            has_rod = "fishing_rod" in hand_items
            grid = load_ocean_viewport(ox, oy, seed)
            content = render_grid(grid, player, "⛵ You row back to your boat.")
            view = OceanView(guild_id, user_id, dock_available=(oy == 0),
                             has_fishing_rod=has_rod)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif current_terrain == "island_chest":
            already = await is_island_looted(db, ox, oy)
            grid = load_island_viewport(tiles, px, py)
            if already:
                content = render_grid(grid, player, "💰 The chest has already been looted.")
            else:
                await mark_island_looted(db, ox, oy)
                loot_rng = _random.Random(hash((ox, oy, seed, "island_loot")))
                roll = loot_rng.random()
                if roll < 0.4:
                    item_id, qty = "gold_coin", loot_rng.randint(10, 50)
                elif roll < 0.65:
                    item_id, qty = "gem", loot_rng.randint(1, 3)
                elif roll < 0.80:
                    item_id, qty = "map_fragment", 1
                else:
                    item_id, qty = "iron_ingot", loot_rng.randint(2, 5)
                await add_to_inventory(db, user_id, item_id, qty)
                label = item_id.replace("_", " ").title()
                content = render_grid(grid, player,
                                      f"💰 You pry open the chest — **{label} ×{qty}**!")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif current_terrain in ("island_forest", "island_tree") and "axe" in hand_items:
            # Chop island tree
            await update_island_tile(db, _iid, px, py, "island_sapling")
            await add_to_inventory(db, user_id, "log", 1)
            chop_rng = _random.Random()
            extras = []
            if chop_rng.random() < 0.66:
                await add_to_inventory(db, user_id, "stick", 1)
                extras.append("a stick")
            if chop_rng.random() < 0.33:
                await add_to_inventory(db, user_id, "resin", 1)
                extras.append("some resin")
            extra_str = (", " + ", ".join(extras)) if extras else ""
            # Reload tiles after update
            _iid2, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
            grid = load_island_viewport(tiles, px, py)
            content = render_grid(grid, player,
                f"🪓 You chop down the palm tree! Got a log{extra_str}. A sapling remains.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        else:
            grid = load_island_viewport(tiles, px, py)
            content = render_grid(grid, player, "Nothing to interact with here.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

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
                    _apply_gold_cap(player, gold_found)
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
            # Step 4 tiles inward as a candidate, then snap to nearest floor tile
            INWARD = 4
            if ey == 0:            cand_x, cand_y = ex, min(INWARD, ch - 1)
            elif ey == ch - 1:     cand_x, cand_y = ex, max(ch - 1 - INWARD, 0)
            elif ex == 0:          cand_x, cand_y = min(INWARD, cw - 1), ey
            else:                  cand_x, cand_y = max(cw - 1 - INWARD, 0), ey
            # Find nearest walkable floor tile so the player never spawns in a wall
            floor_rows = await db.fetch_all(
                "SELECT local_x, local_y FROM cave_tiles "
                "WHERE cave_id=? AND tile_type IN ('stone_floor', 'cave_entrance')",
                (cave_id,)
            )
            if floor_rows:
                sx, sy = min(
                    ((r["local_x"], r["local_y"]) for r in floor_rows),
                    key=lambda t: abs(t[0] - cand_x) + abs(t[1] - cand_y),
                )
            else:
                sx, sy = cand_x, cand_y
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

        elif tile.structure == "shrine":
            # ── Shrine: imbue a held gem with a sacrifice to create enchanted gems ──
            gem_slot = None
            if player.hand_1 == "gem":
                gem_slot = "hand_1"
            elif player.hand_2 == "gem":
                gem_slot = "hand_2"

            if gem_slot is None:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player,
                    "⛩️ An ancient shrine. Equip a gem to hand and interact to imbue it with power.")
            else:
                # Build inventory counts for each sacrifice item
                inv_counts: dict[str, int] = {}
                for stype, data in SHRINE_SACRIFICES.items():
                    sac_item = data["item"]
                    if sac_item not in inv_counts:
                        rows_q = await db.fetch_all(
                            "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
                            (user_id, sac_item)
                        )
                        inv_counts[sac_item] = (rows_q[0]["total"] if rows_q and rows_q[0]["total"] else 0)
                view = ShrineView(guild_id, user_id, inv_counts)
                content = (
                    "⛩️ **Ancient Shrine** — The gem in your hand glows faintly.\n"
                    "Choose a sacrifice to imbue the gem with power.\n"
                    "The resulting enchanted gem can be combined with a **gold ring** to craft a special ring."
                )
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        elif tile.structure == "ruins_looted":
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player,
                "🏚️ These ruins have already been picked clean.")

        elif tile.structure == "ruins":
            # ── Ruins: one-time buried loot ────────────────────────────────────
            rng_r = _random.Random(hash((user_id, wx, wy, seed, "ruins")))
            gold_found = rng_r.randint(15, 60)
            _apply_gold_cap(player, gold_found)
            await update_player_stats(db, user_id, gold=player.gold)
            await set_tile_override(db, wx, wy, "ruins_looted")
            extras: list[str] = []
            if rng_r.random() < 0.45:
                await add_to_inventory(db, user_id, "map_fragment", 1)
                extras.append("a map fragment")
            if rng_r.random() < 0.20:
                await add_to_inventory(db, user_id, "gem", 1)
                extras.append("a gem")
            elif rng_r.random() < 0.35:
                await add_to_inventory(db, user_id, "iron_ingot", 1)
                extras.append("an iron ingot")
            extra_str = (" You also find " + ", ".join(extras) + "!") if extras else ""
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player,
                f"🏚️ You sift through the rubble and find **{gold_found}g**.{extra_str}")

        elif tile.structure == "harbor":
            # ── Harbor village: enter the harbour village from the overworld ──
            vid, vx, vy, _dk_x, _dk_y = await get_or_create_harbor_village(seed, wx, wy, db)
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = vx, vy
            player.village_wx, player.village_wy = wx, wy
            await update_player_village_state(db, user_id, True, vid, vx, vy, wx, wy)
            grid = await load_village_viewport(vid, vx, vy, db)
            content = render_grid(grid, player,
                "🚢 You enter the harbour village. Head to the ⚓ dock to set sail.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif terrain == "drop_box":
            # Pick up items from a drop box on the overworld
            results = await pickup_drop_box(db, wx, wy, user_id)
            grid = await load_viewport(wx, wy, seed, db)
            if results:
                desc = ", ".join(f"{qty}× {iid.replace('_', ' ')}" for iid, qty in results)
                content = render_grid(grid, player, f"🤲 Picked up: {desc}.")
            else:
                content = render_grid(grid, player, "🤲 The box is empty.")

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

    # ── Island: fishing adjacent to ocean ────────────────────────────────────
    if player.in_island:
        from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
        ox, oy = player.island_ox, player.island_oy
        px, py = player.ocean_x, player.ocean_y
        _iid, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
        grid = load_island_viewport(tiles, px, py)
        if "fishing_rod" in hand_items:
            tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
            near_water = any(
                tile_map.get((px + ddx, py + ddy), "island_void") == "island_void"
                for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0))
            )
            if near_water:
                roll = _random.random()
                if roll < 0.50:
                    await add_to_inventory(db, user_id, "fish", 1)
                    msg = "🎣 You cast your line off the island shore... and reel in a **fish**!"
                elif roll < 0.51:
                    await add_to_inventory(db, user_id, "map_fragment", 1)
                    msg = "🎣 You reel in something unusual — a **map fragment**!"
                else:
                    msg = "🎣 You cast your line... the fish got away."
                content = render_grid(grid, player, msg)
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
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
            roll = _random.random()
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
    """Smelt all iron ore into ingots at the forge (1 ore → 1 ingot)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ore_rows = await db.fetch_all(
        "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id='iron_ore'",
        (user_id,)
    )
    ore_count = ore_rows[0]["total"] if ore_rows and ore_rows[0]["total"] else 0

    if ore_count > 0:
        await remove_from_inventory(db, user_id, "iron_ore", ore_count)
        await add_to_inventory(db, user_id, "iron_ingot", ore_count)
        msg = (f"🔥 Smelted **{ore_count}** iron ore → "
               f"**{ore_count} iron ingot{'s' if ore_count > 1 else ''}**!")
    else:
        msg = "🔥 You need iron ore to smelt ingots."

    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=ForgeView(guild_id, user_id)
    )


async def handle_forge_gold(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Smelt all gold ore into gold ingots at the forge (1 ore → 1 ingot)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ore_rows = await db.fetch_all(
        "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id='gold_ore'",
        (user_id,)
    )
    ore_count = ore_rows[0]["total"] if ore_rows and ore_rows[0]["total"] else 0

    if ore_count > 0:
        await remove_from_inventory(db, user_id, "gold_ore", ore_count)
        await add_to_inventory(db, user_id, "gold_ingot", ore_count)
        msg = (f"🟡 Smelted **{ore_count}** gold ore → "
               f"**{ore_count} gold ingot{'s' if ore_count > 1 else ''}**!")
    else:
        msg = "🟡 You need gold ore to smelt gold ingots."

    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=ForgeView(guild_id, user_id)
    )


async def handle_forge_gold_ring(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft a gold ring from 2 gold ingots at the forge."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ingot_rows = await db.fetch_all(
        "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id='gold_ingot'",
        (user_id,)
    )
    ingot_count = ingot_rows[0]["total"] if ingot_rows and ingot_rows[0]["total"] else 0

    if ingot_count >= 2:
        await remove_from_inventory(db, user_id, "gold_ingot", 2)
        await add_to_inventory(db, user_id, "gold_ring", 1)
        msg = "💍 You craft a **gold ring**! Combine with an enchanted gem in your inventory to make a special ring."
    else:
        msg = f"💍 You need 2 gold ingots to craft a gold ring. (Have: {ingot_count})"

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


async def handle_anvil_cannonball(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "cannonball", 4, "Cannonball", "ammunition for ship cannons")


async def handle_anvil_iron_boots(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_boots", 2, "Iron Boots", "+2 defense, equip to boots")


async def handle_anvil_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "You step away from the anvil.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Shrine handlers ───────────────────────────────────────────────────────────

async def handle_shrine_enchant(
    interaction: discord.Interaction, guild_id: int, user_id: int, shrine_type: str
) -> None:
    """Imbue gem with selected enchantment at the shrine."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    seed = await get_or_create_world(db, guild_id)

    if shrine_type not in SHRINE_SACRIFICES:
        await interaction.response.defer()
        return

    data = SHRINE_SACRIFICES[shrine_type]
    sac_item = data["item"]
    sac_qty = data["qty"]
    result_item = data["result"]

    # Verify gem is still in hand
    gem_slot = None
    if player.hand_1 == "gem":
        gem_slot = "hand_1"
    elif player.hand_2 == "gem":
        gem_slot = "hand_2"

    if gem_slot is None:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "⛩️ You no longer have a gem equipped.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Check sacrifice items
    sac_rows = await db.fetch_all(
        "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
        (user_id, sac_item)
    )
    have = sac_rows[0]["total"] if sac_rows and sac_rows[0]["total"] else 0
    if have < sac_qty:
        # Rebuild shrine view with updated counts
        inv_counts: dict[str, int] = {}
        for st, sdata in SHRINE_SACRIFICES.items():
            si = sdata["item"]
            if si not in inv_counts:
                r2 = await db.fetch_all(
                    "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
                    (user_id, si)
                )
                inv_counts[si] = (r2[0]["total"] if r2 and r2[0]["total"] else 0)
        view = ShrineView(guild_id, user_id, inv_counts)
        content = (
            f"⛩️ Not enough {sac_item.replace('_', ' ')} — need {sac_qty}, have {have}.\n"
            "Choose a different enchantment or gather more materials."
        )
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Consume gem (unequip + remove from inventory)
    await unequip_item(db, user_id, gem_slot)
    await remove_from_inventory(db, user_id, "gem", 1)
    # Consume sacrifice
    await remove_from_inventory(db, user_id, sac_item, sac_qty)
    # Give enchanted gem
    await add_to_inventory(db, user_id, result_item, 1)

    result_name = result_item.replace("_", " ")
    sac_name = sac_item.replace("_", " ")
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(
        grid, player,
        f"⛩️ The shrine blazes with light! Your gem is imbued — you receive a **{result_name}**!\n"
        f"Combine it with a **gold ring** in your inventory to craft a special ring."
    )
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_shrine_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel shrine enchantment menu and return to game."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    seed = await get_or_create_world(db, guild_id)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player, "⛩️ You step away from the shrine.")
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

    # In combat + on ship → show ship cargo, but preserve prev_arena so combat restores
    if player.in_combat and player.in_ship:
        chest_items = await get_ship_cargo_items(db, user_id)
        player_items = await get_inventory(db, user_id)
        inv_rows, inv_cols = _inv_capacity(player)
        _ui_state[user_id] = {
            "type": "ship_chest_cargo",
            "selected": 0,
            "chest_view": "player",
            "prev_arena": prev_arena,
        }
        content = render_ship_chest(chest_items, player_items, 0, "player",
                                    "Ship Cargo", player, inv_rows, inv_cols)
        view = ShipChestView(guild_id, user_id, "cargo", "player")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # In combat (not on ship) → normal inventory, preserving prev_arena
    # Not in combat → normal inventory regardless of location (ship chest is a separate interaction)
    prev_selections = prev_state.get("selections", {})
    prev_mode = prev_state.get("sel_mode", "add")
    _ui_state[user_id] = {
        "type": "inventory", "selected": 0, "prev_arena": prev_arena,
        "selections": prev_selections, "sel_mode": prev_mode,
        "cursor_mode": "inventory", "equipped_cursor": 0,
        "move_mode": False, "move_origin": None,
    }
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, 0, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    """Navigate inventory left/right (prev/next) — also handles equipped/gold row."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    cursor_mode = state.get("cursor_mode", "inventory")
    total_slots = inv_rows * inv_cols

    if cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
        num_eq = len(_EQUIP_SLOT_ORDER)
        new_eq = (state.get("equipped_cursor", 0) + delta) % num_eq
        _ui_state[user_id] = {**state, "equipped_cursor": new_eq}
    elif cursor_mode == "inventory":
        visible = [it for it in items if it["item_id"] != "gold_coin"]
        max_slots = max(1, min(total_slots, len(visible) + 1))
        new_sel = (state.get("selected", 0) + delta) % max(1, total_slots)
        _ui_state[user_id] = {**state, "type": "inventory", "selected": new_sel}
    else:
        _ui_state[user_id] = {**state}

    content, view = _inv_view(guild_id, user_id, items, _ui_state[user_id].get("selected", 0),
                              equipped, inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move inventory cursor up one row (or to equipped/gold row)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    cursor_mode = state.get("cursor_mode", "inventory")

    if cursor_mode == "inventory":
        current_row = state.get("selected", 0) // inv_cols
        if current_row == 0:
            # Move up into equipped row
            new_state = {**state, "cursor_mode": "equipped", "equipped_cursor": 0}
        else:
            new_sel = max(0, state["selected"] - inv_cols)
            new_state = {**state, "selected": new_sel}
    elif cursor_mode == "equipped":
        new_state = {**state, "cursor_mode": "gold"}
    else:
        new_state = {**state}  # already at gold (top)

    _ui_state[user_id] = {**new_state, "type": "inventory"}
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, _ui_state[user_id].get("selected", 0),
                              equipped, inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move inventory cursor down one row (or from equipped/gold into grid)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    total_slots = inv_rows * inv_cols
    cursor_mode = state.get("cursor_mode", "inventory")

    if cursor_mode == "gold":
        new_state = {**state, "cursor_mode": "equipped", "equipped_cursor": 0}
    elif cursor_mode == "equipped":
        new_state = {**state, "cursor_mode": "inventory", "selected": 0}
    else:
        new_sel = min(total_slots - 1, state.get("selected", 0) + inv_cols)
        new_state = {**state, "selected": new_sel}

    _ui_state[user_id] = {**new_state, "type": "inventory"}
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, _ui_state[user_id].get("selected", 0),
                              equipped, inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


def _inv_view(guild_id: int, user_id: int, items: list, sel: int, equipped: dict,
              inv_rows: int, inv_cols: int, state: dict, msg_suffix: str = "",
              gold: int = 0) -> tuple[str, "InventoryView"]:
    """Helper: build inventory content + view with consistent state."""
    from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
    selections = state.get("selections", {})
    sel_mode = state.get("sel_mode", "add")
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)
    move_mode = state.get("move_mode", False)

    # Visible items (gold_coin filtered out)
    visible = [it for it in items if it["item_id"] != "gold_coin"]

    label, action = _inv_action_btn(items, sel, equipped, cursor_mode, equipped_cursor)

    # Resolve cursor_id for all modes so Select / ± work everywhere
    if cursor_mode == "inventory":
        _ci = _cursor_item(visible, sel)
        cursor_id = _ci["item_id"] if _ci else None
    elif cursor_mode == "gold":
        cursor_id = "gold_coin"
    elif cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER as _ESO
        if equipped_cursor < len(_ESO):
            _eq_slot, _ = _ESO[equipped_cursor]
            cursor_id = equipped.get(_eq_slot)  # None if slot is empty
        else:
            cursor_id = None
    else:
        cursor_id = None

    # ± buttons: show when cursor item is in the selection basket
    show_pm = cursor_id is not None and cursor_id in selections
    # Drop button: only for inventory and gold mode (equipped items must be unequipped first)
    show_drop = show_pm and cursor_mode in ("inventory", "gold")

    move_qty = state.get("move_qty", 1)

    content = render_inventory(
        items, sel, equipped, label, inv_rows, inv_cols, selections,
        gold=gold, cursor_mode=cursor_mode, equipped_cursor=equipped_cursor,
    )
    if move_mode:
        # Show move qty and total in move mode suffix
        total_max = state.get("move_qty_max") or move_qty
        content += f"\n*↔️ Moving ×{move_qty} of {total_max} — navigate to destination, then Confirm.*"
    if msg_suffix:
        content += msg_suffix

    # Determine max qty for modal
    if move_mode:
        modal_max = state.get("move_qty_max") or 1
    elif show_pm and cursor_id is not None:
        modal_max = sum(it["quantity"] for it in items if it["item_id"] == cursor_id)
    else:
        modal_max = 1

    view = InventoryView(
        guild_id, user_id, label, action, selections, cursor_id, sel_mode,
        cursor_mode=cursor_mode,
        show_plus_minus=show_pm,
        show_drop=show_drop,
        move_mode=move_mode,
        move_qty=move_qty,
    )
    # Stash modal_max on view so the button handler can read it
    view._modal_max = modal_max
    return content, view


async def handle_inv_equip(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Equip the item under the cursor (also redirects food → eat)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    visible = [it for it in items if it["item_id"] != "gold_coin"]

    cur_item = _cursor_item(visible, sel)
    if cur_item is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item selected)*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    item_id = cur_item["item_id"]

    # Food items are handled by handle_inv_eat — redirect
    if item_id in FOOD_HP_RESTORE:
        await handle_inv_eat(interaction, guild_id, user_id)
        return

    # Look up slot type
    slot_type = ITEM_EQUIP_SLOTS.get(item_id)
    if not slot_type:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*{item_id.replace('_', ' ').title()} cannot be equipped.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Pouch unequip capacity check (if equipping a smaller pouch to replace)
    existing_in_slot = equipped.get(slot_type)
    if existing_in_slot:
        # Return old equipped item to inventory first
        await add_to_inventory(db, user_id, existing_in_slot, 1)

    # Resolve hand slot
    if slot_type == "hand":
        if item_id in TWO_HANDED_ITEMS:
            if equipped.get("hand_1") or equipped.get("hand_2"):
                content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                          inv_rows, inv_cols, state,
                                          "\n*Your hands must be free for a two-handed item.*",
                                          gold=player.gold)
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
                                          "\n*Both hands are full.*",
                                          gold=player.gold)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            await equip_item(db, user_id, resolved_slot, item_id)
    else:
        await equip_item(db, user_id, slot_type, item_id)

    # Remove 1 of the equipped item from inventory
    await remove_from_inventory(db, user_id, item_id, 1)

    bonuses = EQUIP_BONUSES.get(item_id, {})
    if bonuses:
        await update_player_stats(db, user_id, **bonuses)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, state,
                              f"\n*Equipped {item_id.replace('_', ' ').title()}!*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_unequip(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Unequip the item at the equipped-row cursor (returns it to inventory)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    equipped_cursor = state.get("equipped_cursor", 0)

    from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
    if equipped_cursor >= len(_EQUIP_SLOT_ORDER):
        await interaction.response.defer()
        return

    slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
    item_id = equipped.get(slot)
    if not item_id:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0),
                                  equipped, inv_rows, inv_cols, state,
                                  "\n*(Nothing equipped in that slot.)*", gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Special: coin purse unequip with overflow
    if slot == "coin_purse":
        new_cap = COIN_PURSE_CAPACITY[None]  # bare capacity
        overflow = max(0, player.gold - new_cap)
        if overflow > 0:
            await db.execute("UPDATE players SET gold=? WHERE user_id=?", (new_cap, user_id))
            px = player.world_x if not player.in_cave else player.cave_x
            py = player.world_y if not player.in_cave else player.cave_y
            await create_drop_box(db, px, py, [("gold_coin", overflow)])

    # Pouch unequip: check inventory fits in smaller grid
    if slot == "pouch":
        pouch_order = [None, "small_pouch", "medium_pouch", "large_pouch"]
        cur_idx = pouch_order.index(item_id) if item_id in pouch_order else 0
        new_rows, new_cols = POUCH_SIZES[pouch_order[cur_idx - 1]] if cur_idx > 0 else POUCH_SIZES[None]
        new_capacity = new_rows * new_cols
        visible = [it for it in items if it["item_id"] != "gold_coin"]
        if len(visible) > new_capacity:
            content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0),
                equipped, inv_rows, inv_cols, state,
                f"\n*Can't unequip: inventory has {len(visible)} items but smaller pouch fits {new_capacity}. Remove items first.*",
                gold=player.gold)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    if item_id in TWO_HANDED_ITEMS:
        await unequip_item(db, user_id, "hand_1")
        await unequip_item(db, user_id, "hand_2")
    else:
        await unequip_item(db, user_id, slot)

    await add_to_inventory(db, user_id, item_id, 1)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0),
                              equipped, inv_rows, inv_cols, state,
                              f"\n*Unequipped {item_id.replace('_', ' ').title()}.*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_eat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Eat a food item from inventory, restoring HP."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    cur_item = _cursor_item(visible, sel)
    if cur_item is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item selected)*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    item_id = cur_item["item_id"]
    restore = FOOD_HP_RESTORE.get(item_id)
    if restore is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*{item_id.replace('_', ' ').title()} is not food.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if player.hp >= player.max_hp:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*You're already at full health!*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    new_hp = min(player.max_hp, player.hp + restore)
    await update_player_stats(db, user_id, hp=new_hp)
    await remove_from_inventory(db, user_id, item_id, 1)
    await _auto_unequip_depleted(db, user_id, item_id, player)
    # Auto-deselect if selection qty now exceeds remaining (across all stacks)
    selections = dict(state.get("selections", {}))
    if item_id in selections:
        remain_rows = await db.fetch_all(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
        )
        remain = sum(r["quantity"] for r in remain_rows)
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
                              f"\n*🍗 Ate {item_id.replace('_', ' ')}. HP: {new_hp}/{player.max_hp}*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_select(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Select or deselect the current cursor item for crafting."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    selections = dict(state.get("selections", {}))
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)

    if cursor_mode == "gold":
        if "gold_coin" in selections:
            del selections["gold_coin"]
            msg = "\n*Deselected coins.*"
        elif player.gold > 0:
            selections["gold_coin"] = 1
            msg = f"\n*Selected 1 coin (have {player.gold}). Use ➖/➕ to adjust qty.*"
        else:
            msg = "\n*(No coins to select)*"
    elif cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
        equipped = _equipped_dict(player)
        if equipped_cursor < len(_EQUIP_SLOT_ORDER):
            slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
            item_id = equipped.get(slot)
            if item_id:
                if item_id in selections:
                    del selections[item_id]
                    msg = f"\n*Deselected {item_id.replace('_', ' ').title()}.*"
                else:
                    selections[item_id] = 1
                    msg = f"\n*Selected equipped {item_id.replace('_', ' ').title()}.*"
            else:
                msg = "\n*(No item equipped in that slot)*"
        else:
            msg = "\n*(No item at cursor)*"
    else:  # cursor_mode == "inventory"
        cur_item = _cursor_item(visible, sel)
        if cur_item is not None:
            item_id = cur_item["item_id"]
            if item_id in selections:
                del selections[item_id]
                msg = f"\n*Deselected {item_id.replace('_', ' ').title()}.*"
            else:
                selections[item_id] = 1
                msg = f"\n*Selected {item_id.replace('_', ' ').title()} ×1.*"
        else:
            msg = "\n*(No item at cursor)*"

    _ui_state[user_id] = {**state, "selections": selections}
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
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
                              inv_rows, inv_cols, _ui_state[user_id], "\n*Cleared all selections.*",
                              gold=player.gold)
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
        have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
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
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
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
                              f"\n*Mode switched to {mode_name}*",
                              gold=player.gold)
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
        have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
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
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
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
                                  "\n*No matching recipe for the selected items.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Verify player has enough of each ingredient (sum across all stacks)
    for item_id, qty in selections.items():
        total_have = sum(
            it["quantity"] for it in items if it["item_id"] == item_id
        )
        if total_have < qty:
            content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                      inv_rows, inv_cols, state,
                                      f"\n*Not enough {item_id.replace('_', ' ')} to craft.*",
                                      gold=player.gold)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    # Consume ingredients and add result
    for item_id, qty in selections.items():
        await remove_from_inventory(db, user_id, item_id, qty)
    await add_to_inventory(db, user_id, recipe["result"], recipe["qty"])

    # Clear selections and refresh
    _ui_state[user_id] = {**state, "selections": {}}
    items = await get_inventory(db, user_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              f"\n*✨ Crafted {recipe['qty']}× {recipe['result'].replace('_', ' ').title()}!*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    prev_arena = _ui_state.get(user_id, {}).get("prev_arena")
    is_house_owner = _ui_state.get(user_id, {}).get("is_house_owner", False)
    _ui_state.pop(user_id, None)
    # Restore player-house owner flag so Edit button re-appears after close
    if player.in_house and player.house_type == "player_house" and is_house_owner:
        _ui_state.setdefault(user_id, {})["is_house_owner"] = True
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


async def handle_inv_sel_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Increase the selected quantity for the cursor item (+1, wrapping)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    selections = dict(state.get("selections", {}))
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    cursor_mode = state.get("cursor_mode", "inventory")
    msg = None
    if cursor_mode == "gold":
        total_have = player.gold
        current = selections.get("gold_coin", 0)
        new_qty = (current % max(total_have, 1)) + 1
        selections["gold_coin"] = new_qty
        _ui_state[user_id] = {**state, "selections": selections}
        msg = f"\n*➕ Coins → ×{new_qty}*"
    else:
        cur_item = _cursor_item(visible, sel)
        if cur_item is not None:
            item_id = cur_item["item_id"]
            total_have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
            current = selections.get(item_id, 0)
            new_qty = (current % max(total_have, 1)) + 1
            selections[item_id] = new_qty
            _ui_state[user_id] = {**state, "selections": selections}
            msg = f"\n*➕ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    if msg is None:
        msg = "\n*(No item at cursor)*"

    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_sel_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Decrease the selected quantity for the cursor item (−1, wrapping to max)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    selections = dict(state.get("selections", {}))
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    cursor_mode = state.get("cursor_mode", "inventory")
    msg = None
    if cursor_mode == "gold":
        total_have = player.gold
        current = selections.get("gold_coin", 1)
        new_qty = total_have if current <= 1 else current - 1
        selections["gold_coin"] = new_qty
        _ui_state[user_id] = {**state, "selections": selections}
        msg = f"\n*➖ Coins → ×{new_qty}*"
    else:
        cur_item = _cursor_item(visible, sel)
        if cur_item is not None:
            item_id = cur_item["item_id"]
            total_have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
            current = selections.get(item_id, 1)
            new_qty = total_have if current <= 1 else current - 1
            selections[item_id] = new_qty
            _ui_state[user_id] = {**state, "selections": selections}
            msg = f"\n*➖ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    if msg is None:
        msg = "\n*(No item at cursor)*"

    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_drop(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Drop selected items onto the player's current tile as a drop box."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    selections = dict(state.get("selections", {}))
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    # Can't drop in caves, villages, buildings, or on the high seas
    if player.in_cave or player.in_village or player.in_house or player.in_high_seas or player.in_ship or player.in_island:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*You can only drop items in the overworld.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Can't drop on structure tiles
    seed = await get_or_create_world(db, guild_id)
    wx, wy = player.world_x, player.world_y
    cur_tile = await load_single_tile(wx, wy, seed, db)
    if cur_tile.structure is not None:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*You can't drop items on a structure tile.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if not selections:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*Select items first (use Select/Desel, then ➖/➕ to set qty).*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    drop_pairs: list[tuple[str, int]] = []
    gold_to_drop = 0
    for item_id, qty in selections.items():
        if item_id == "gold_coin":
            gold_to_drop = min(qty, player.gold)
        else:
            total_have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
            drop_qty = min(qty, total_have)
            if drop_qty > 0:
                drop_pairs.append((item_id, drop_qty))

    if not drop_pairs and not gold_to_drop:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                  inv_rows, inv_cols, state, "\n*Nothing to drop.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    for item_id, qty in drop_pairs:
        await remove_from_inventory(db, user_id, item_id, qty)
    if gold_to_drop:
        drop_pairs.append(("gold_coin", gold_to_drop))
        await db.execute(
            "UPDATE players SET gold=gold-? WHERE user_id=?", (gold_to_drop, user_id)
        )
    await create_drop_box(db, wx, wy, drop_pairs)

    _ui_state[user_id] = {**state, "selections": {}}
    items = await get_inventory(db, user_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    drop_desc = ", ".join(f"{qty}× {iid.replace('_', ' ')}" for iid, qty in drop_pairs)
    content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              f"\n*🫳 Dropped: {drop_desc}.*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Enter move mode: remember the current slot as origin."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    origin_item = _cursor_item(visible, sel)
    if origin_item is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item to move)*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # move_qty_max = total of this item across ALL stacks (user can consolidate)
    total_of_item = sum(it["quantity"] for it in items if it["item_id"] == origin_item["item_id"])
    _ui_state[user_id] = {
        **state,
        "move_mode": True,
        "move_origin": sel,
        "move_qty": origin_item["quantity"],  # default to this slot's qty
        "move_qty_max": total_of_item,
    }
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_confirm(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Confirm move: move/split/swap origin to destination using move_qty."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    origin = state.get("move_origin", sel)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    origin_item = _cursor_item(visible, origin)
    dest_item   = _cursor_item(visible, sel)
    move_qty    = max(1, state.get("move_qty", 1))

    if origin == sel or origin_item is None:
        msg = "\n*(Nothing to move)*"

    elif dest_item is not None and dest_item["item_id"] != origin_item["item_id"]:
        # Different item types — swap full stacks, ignore move_qty
        await swap_inventory_slots(db, user_id, origin_item["slot_index"], dest_item["slot_index"])
        msg = "\n*↔️ Items swapped.*"

    elif dest_item is not None and dest_item["item_id"] == origin_item["item_id"]:
        # Same item type — fill destination up to MAX_STACK_SIZE from source stacks
        from dwarf_explorer.config import MAX_STACK_SIZE
        space = MAX_STACK_SIZE - dest_item["quantity"]
        if space <= 0:
            msg = "\n*(Destination stack is full)*"
        else:
            # Available = sum of all stacks EXCEPT the destination slot
            available = sum(
                it["quantity"] for it in visible
                if it["item_id"] == origin_item["item_id"]
                and it["slot_index"] != dest_item["slot_index"]
            )
            transfer = min(move_qty, space, available)
            if transfer <= 0:
                msg = "\n*(Nothing to move)*"
            else:
                # Grow the destination slot
                await db.execute(
                    "UPDATE inventory SET quantity = quantity + ? WHERE user_id=? AND slot_index=?",
                    (transfer, user_id, dest_item["slot_index"]),
                )
                # Drain from all other stacks of same item (LIFO), excluding destination
                stacks = await db.fetch_all(
                    "SELECT id, quantity FROM inventory "
                    "WHERE user_id=? AND item_id=? AND slot_index!=? ORDER BY slot_index DESC",
                    (user_id, origin_item["item_id"], dest_item["slot_index"]),
                )
                remaining = transfer
                for stack in stacks:
                    if remaining <= 0:
                        break
                    take = min(stack["quantity"], remaining)
                    if take == stack["quantity"]:
                        await db.execute("DELETE FROM inventory WHERE id=?", (stack["id"],))
                    else:
                        await db.execute(
                            "UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                            (take, stack["id"]),
                        )
                    remaining -= take
                msg = f"\n*↔️ Merged ×{transfer} into stack.*"

    else:
        # Empty destination — move up to MAX_STACK_SIZE, drawing from all stacks
        from dwarf_explorer.config import MAX_STACK_SIZE
        total_avail = sum(
            it["quantity"] for it in visible if it["item_id"] == origin_item["item_id"]
        )
        transfer = min(move_qty, MAX_STACK_SIZE, total_avail)
        # Drain stacks (LIFO)
        stacks = await db.fetch_all(
            "SELECT id, quantity FROM inventory "
            "WHERE user_id=? AND item_id=? ORDER BY slot_index DESC",
            (user_id, origin_item["item_id"]),
        )
        remaining = transfer
        for stack in stacks:
            if remaining <= 0:
                break
            take = min(stack["quantity"], remaining)
            if take == stack["quantity"]:
                await db.execute("DELETE FROM inventory WHERE id=?", (stack["id"],))
            else:
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                    (take, stack["id"]),
                )
            remaining -= take
        # Place at destination slot
        await db.execute(
            "INSERT INTO inventory(user_id, item_id, quantity, slot_index) VALUES(?,?,?,?)",
            (user_id, origin_item["item_id"], transfer, sel),
        )
        msg = f"\n*↔️ Moved ×{transfer}.*"

    _ui_state[user_id] = {
        **state, "move_mode": False, "move_origin": None, "move_qty": 1, "move_qty_max": None,
    }
    items = await get_inventory(db, user_id)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel move mode, returning cursor to origin slot."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    origin = state.get("move_origin", state.get("selected", 0))
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    _ui_state[user_id] = {**state, "move_mode": False, "move_origin": None,
                          "move_qty": 1, "move_qty_max": None, "selected": origin}
    content, view = _inv_view(guild_id, user_id, items, origin, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              "\n*↔️ Move cancelled.*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_qty_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Increase move quantity by 1, wrapping at move_qty_max (total of item across all stacks)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    total_max = state.get("move_qty_max") or 1

    current = state.get("move_qty", total_max)
    new_qty = (current % total_max) + 1  # wraps 1 → total_max
    _ui_state[user_id] = {**state, "move_qty": new_qty}

    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_qty_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Decrease move quantity by 1, wrapping at 1 → move_qty_max."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    total_max = state.get("move_qty_max") or 1

    current = state.get("move_qty", total_max)
    new_qty = total_max if current <= 1 else current - 1
    _ui_state[user_id] = {**state, "move_qty": new_qty}

    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_qty_modal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open a modal to enter a custom quantity (for move or select)."""
    state = _ui_state.get(user_id, {"selected": 0})
    move_mode = state.get("move_mode", False)

    if move_mode:
        max_qty = state.get("move_qty_max") or 1
        modal = InvQtyModal(guild_id, user_id, "move", max_qty)
    else:
        # select mode — look up total across stacks
        db = await get_database(guild_id)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        items = await get_inventory(db, user_id)
        visible = [it for it in items if it["item_id"] != "gold_coin"]
        sel = state.get("selected", 0)
        cursor_mode = state.get("cursor_mode", "inventory")
        if cursor_mode == "gold":
            max_qty = player.gold
        else:
            ci = _cursor_item(visible, sel)
            if ci:
                max_qty = sum(it["quantity"] for it in items if it["item_id"] == ci["item_id"])
            else:
                max_qty = 1
        modal = InvQtyModal(guild_id, user_id, "select", max_qty)

    await interaction.response.send_modal(modal)


# ── Shop helpers ──────────────────────────────────────────────────────────────

def _shop_render(state: dict, player_items: list, equipped: dict,
                 player_gold: int, inv_rows: int, inv_cols: int) -> str:
    """Build shop content string from current state."""
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    return render_shop(
        SHOP_CATALOG, player_items, sel, view_mode, equipped,
        player_gold, inv_rows, inv_cols, ITEM_SELL_PRICES, qty,
    )


# ── Shop handlers ─────────────────────────────────────────────────────────────

async def _open_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player: Player,
) -> None:
    db = await get_database(guild_id)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    _ui_state[user_id] = {"type": "shop", "selected": 0, "shop_view": "shop", "qty": 1}
    content = _shop_render(_ui_state[user_id], player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop"))


def _shop_nav_bounds(state: dict, player_items: list) -> int:
    """Return total navigable slots in current shop view."""
    view_mode = state.get("shop_view", "shop")
    inv_cols = 7
    if view_mode == "player":
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        return max(1, len(visible))
    else:
        return max(1, len(SHOP_CATALOG))


async def _shop_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    delta_col: int = 0, delta_row: int = 0,
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    sel = state.get("selected", 0)
    total = _shop_nav_bounds(state, player_items)
    cols = inv_cols if state.get("shop_view") == "player" else 7
    new_sel = (sel + delta_col + delta_row * cols) % total
    new_state = {**state, "selected": new_sel, "qty": 1}  # reset qty on nav
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, new_state.get("shop_view", "shop")))


async def handle_shop_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    await _shop_nav(interaction, guild_id, user_id, delta_col=delta)


async def handle_shop_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _shop_nav(interaction, guild_id, user_id, delta_row=-1)


async def handle_shop_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _shop_nav(interaction, guild_id, user_id, delta_row=1)


async def handle_shop_qty_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    if view_mode == "shop" and sel < len(SHOP_CATALOG):
        max_qty = max(1, player.gold // max(1, SHOP_CATALOG[sel]["price"]))
        new_qty = (qty % max_qty) + 1
    elif view_mode == "player":
        from dwarf_explorer.game.renderer import _build_slot_map
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        new_qty = ((qty % max(1, item["quantity"])) + 1) if item else 1
    else:
        new_qty = qty
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, view_mode))


async def handle_shop_qty_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    if view_mode == "shop" and sel < len(SHOP_CATALOG):
        max_qty = max(1, player.gold // max(1, SHOP_CATALOG[sel]["price"]))
        new_qty = max_qty if qty <= 1 else qty - 1
    elif view_mode == "player":
        from dwarf_explorer.game.renderer import _build_slot_map
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
        new_qty = max_qty if qty <= 1 else qty - 1
    else:
        new_qty = qty
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, view_mode))


async def handle_shop_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    if sel >= len(SHOP_CATALOG):
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols)
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "shop"))
        return
    item = SHOP_CATALOG[sel]
    total_cost = item["price"] * qty
    if player.gold < total_cost:
        suffix = f"\n*Not enough gold! Need {total_cost}g for ×{qty}.*"
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "shop"))
        return
    player.gold -= total_cost
    await update_player_stats(db, user_id, gold=player.gold)
    await add_to_inventory(db, user_id, item["id"], qty)
    player_items = await get_inventory(db, user_id)
    suffix = f"\n*Purchased {qty}× {item['name']} for {total_cost}g!*"
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop"))


async def handle_shop_sell(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "player", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    from dwarf_explorer.game.renderer import _build_slot_map
    visible = [it for it in player_items if it["item_id"] != "gold_coin"]
    slot_map = _build_slot_map(visible, inv_rows * inv_cols)
    item = slot_map.get(sel)
    if item is None:
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols) + "\n*(No item at cursor)*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "player"))
        return
    item_id = item["item_id"]
    price = ITEM_SELL_PRICES.get(item_id, 0)
    if price == 0:
        suffix = f"\n*The shop won't buy {item_id.replace('_', ' ').title()}.*"
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "player"))
        return
    actual_qty = min(qty, item["quantity"])
    await remove_from_inventory(db, user_id, item_id, actual_qty)
    player.gold += price * actual_qty
    await update_player_stats(db, user_id, gold=player.gold)
    player_items = await get_inventory(db, user_id)
    suffix = f"\n*Sold {actual_qty}× {item_id.replace('_', ' ').title()} for {price * actual_qty}g!*"
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "player"))


async def handle_shop_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Switch between shop catalog and player inventory."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop"})
    new_view = "player" if state.get("shop_view", "shop") == "shop" else "shop"
    new_state = {"type": "shop", "selected": 0, "shop_view": new_view, "qty": 1}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, new_view))


# handle_shop_mode kept for backward compatibility (old buttons may still trigger it)
async def handle_shop_mode(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_shop_switch(interaction, guild_id, user_id)


async def handle_shop_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Bank helpers ──────────────────────────────────────────────────────────────

def _bank_render(state: dict, player_items: list, bank_items: list,
                 equipped: dict, player_gold: int,
                 inv_rows: int, inv_cols: int) -> str:
    """Build bank content string from current state."""
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)
    return render_bank(player_items, bank_items, sel, bv, equipped,
                       inv_rows, inv_cols, gold=player_gold, qty=qty,
                       cursor_mode=cursor_mode, equipped_cursor=equipped_cursor)


# ── Bank handlers ─────────────────────────────────────────────────────────────

async def _open_bank(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player: Player, db,
) -> None:
    _ui_state[user_id] = {
        "type": "bank", "selected": 0, "bank_view": "player", "qty": 1,
        "cursor_mode": "inventory", "equipped_cursor": 0,
    }
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content = _bank_render(_ui_state[user_id], player_items, bank_items,
                           equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "player"))


async def _bank_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    delta_col: int = 0, delta_row: int = 0,
) -> None:
    """Navigate bank cursor with full cursor_mode support (gold → equipped → inventory)."""
    from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER as _ESO
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1,
                                     "cursor_mode": "inventory", "equipped_cursor": 0})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    cursor_mode = state.get("cursor_mode", "inventory")
    eq_cur = state.get("equipped_cursor", 0)

    if bv == "player":
        cols = inv_cols
        total = max(1, inv_rows * inv_cols)
        if delta_row < 0:   # UP
            if cursor_mode == "inventory" and sel < cols:
                # Top row → go to equipped
                cursor_mode = "equipped"
                eq_cur = min(eq_cur, len(_ESO) - 1)
            elif cursor_mode == "inventory":
                sel = (sel - cols) % total
            elif cursor_mode == "equipped":
                cursor_mode = "gold"
            # already at gold — do nothing
        elif delta_row > 0:  # DOWN
            if cursor_mode == "gold":
                cursor_mode = "equipped"
            elif cursor_mode == "equipped":
                cursor_mode = "inventory"
                sel = 0
            else:
                sel = min(sel + cols, total - 1)
        else:  # LEFT/RIGHT
            if cursor_mode == "equipped":
                eq_cur = (eq_cur + delta_col) % len(_ESO)
            elif cursor_mode == "inventory":
                new_sel = sel + delta_col
                if 0 <= new_sel < total:
                    sel = new_sel
                else:
                    sel = new_sel % total
    else:
        # Bank vault — simple grid nav
        vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
        cols = 7
        total = max(1, 28)
        cursor_mode = "inventory"
        sel = (sel + delta_col + delta_row * cols) % total

    new_state = {**state, "selected": sel, "qty": 1, "cursor_mode": cursor_mode,
                 "equipped_cursor": eq_cur}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, bv))


async def handle_bank_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    await _bank_nav(interaction, guild_id, user_id, delta_col=delta)


async def handle_bank_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _bank_nav(interaction, guild_id, user_id, delta_row=-1)


async def handle_bank_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _bank_nav(interaction, guild_id, user_id, delta_row=1)


async def handle_bank_qty_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    cursor_mode = state.get("cursor_mode", "inventory")
    from dwarf_explorer.game.renderer import _build_slot_map
    if bv == "bank":
        vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(vault_items, 28)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    elif cursor_mode == "gold":
        max_qty = max(player.gold, 1)
    else:
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    new_qty = (qty % max_qty) + 1
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, bv))


async def handle_bank_qty_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    cursor_mode = state.get("cursor_mode", "inventory")
    from dwarf_explorer.game.renderer import _build_slot_map
    if bv == "bank":
        vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(vault_items, 28)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    elif cursor_mode == "gold":
        max_qty = max(player.gold, 1)
    else:
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    new_qty = max_qty if qty <= 1 else qty - 1
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, bv))


async def handle_bank_qty_modal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open a modal to enter a custom quantity for bank deposit/withdraw."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    cursor_mode = state.get("cursor_mode", "inventory")
    from dwarf_explorer.game.renderer import _build_slot_map
    inv_rows, inv_cols = _inv_capacity(player)
    if bv == "bank":
        vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(vault_items, 28)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    elif cursor_mode == "gold":
        max_qty = max(player.gold, 1)
    else:
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    await interaction.response.send_modal(InvQtyModal(guild_id, user_id, "bank", max_qty))


async def handle_shop_qty_modal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open a modal to enter a custom quantity for shop buy/sell."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    inv_rows, inv_cols = _inv_capacity(player)
    if view_mode == "shop" and sel < len(SHOP_CATALOG):
        max_qty = max(1, player.gold // max(1, SHOP_CATALOG[sel]["price"]))
    elif view_mode == "player":
        from dwarf_explorer.game.renderer import _build_slot_map
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    else:
        max_qty = 1
    await interaction.response.send_modal(InvQtyModal(guild_id, user_id, "shop", max_qty))


async def handle_bank_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    new_view = "bank" if state.get("bank_view") == "player" else "player"
    new_state = {"type": "bank", "selected": 0, "bank_view": new_view, "qty": 1,
                 "cursor_mode": "inventory", "equipped_cursor": 0}
    _ui_state[user_id] = new_state
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, new_view))


async def handle_bank_deposit(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)
    player_items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    from dwarf_explorer.game.renderer import _build_slot_map, _EQUIP_SLOT_ORDER as _ESO

    suffix = "\n*Deposit failed.*"

    if cursor_mode == "gold":
        # Deposit gold: deduct from players.gold, add to bank_items
        actual_qty = min(qty, player.gold)
        if actual_qty > 0:
            await db.execute("UPDATE players SET gold=gold-? WHERE user_id=?",
                             (actual_qty, user_id))
            await db.execute(
                "INSERT INTO bank_items(user_id, item_id, quantity) VALUES(?,'gold_coin',?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity=quantity+?",
                (user_id, actual_qty, actual_qty),
            )
            suffix = f"\n*Deposited {actual_qty}g into bank.*"
        else:
            suffix = "\n*(No gold to deposit)*"

    elif cursor_mode == "equipped":
        # Deposit equipped item: unequip it first, then bank_deposit
        if equipped_cursor < len(_ESO):
            slot, _ = _ESO[equipped_cursor]
            item_id = equipped.get(slot)
            if item_id:
                from dwarf_explorer.database.repositories import unequip_item as _unequip_item
                await _unequip_item(db, user_id, slot)
                await add_to_inventory(db, user_id, item_id, 1)
                player_items = await get_inventory(db, user_id)
                ok = await bank_deposit(db, user_id, item_id, 1)
                suffix = f"\n*Unequipped and deposited {item_id.replace('_', ' ').title()}.*" if ok else "\n*Deposit failed.*"
            else:
                suffix = "\n*(No item equipped in that slot)*"
        else:
            suffix = "\n*(No item at cursor)*"

    else:
        # Normal inventory deposit — remove from the exact cursor slot (not LIFO)
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        if item is None:
            suffix = "\n*(Empty slot)*"
        else:
            actual_qty = min(qty, item["quantity"])
            # Find the exact inventory row for this slot and remove directly
            inv_row = await db.fetch_one(
                "SELECT id, quantity FROM inventory WHERE user_id=? AND slot_index=?",
                (user_id, item["slot_index"]),
            )
            if inv_row:
                if inv_row["quantity"] <= actual_qty:
                    await db.execute("DELETE FROM inventory WHERE id=?", (inv_row["id"],))
                else:
                    await db.execute(
                        "UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                        (actual_qty, inv_row["id"]),
                    )
                # Add to bank (single-row-per-item, no stack limit in storage)
                await db.execute(
                    "INSERT INTO bank_items(user_id, item_id, quantity) VALUES(?,?,?) "
                    "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
                    (user_id, item["item_id"], actual_qty, actual_qty),
                )
                suffix = f"\n*Deposited {actual_qty}× {item['item_id'].replace('_', ' ')}.*"
            else:
                suffix = "\n*Deposit failed.*"

    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "player"))


async def handle_bank_withdraw(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "bank", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    bank_items = await get_bank_items(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    from dwarf_explorer.game.renderer import _build_slot_map
    # Vault view excludes gold_coin row (shown separately as bank gold)
    vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
    slot_map = _build_slot_map(vault_items, 28)
    item = slot_map.get(sel)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    if item is None:
        suffix = "\n*(Empty slot)*"
        content = _bank_render(state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols) + suffix
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=BankView(guild_id, user_id, "bank"))
        return
    actual_qty = min(qty, item["quantity"])
    cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
    ok = await bank_withdraw(db, user_id, item["item_id"], actual_qty, gold_cap=cap)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items_new = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    suffix = (f"\n*Withdrew {actual_qty}× {item['item_id'].replace('_', ' ')}.*"
              if ok else "\n*Withdraw failed.*")
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items_new, equipped, player.gold, inv_rows, inv_cols) + suffix
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

    if player.in_high_seas:
        from dwarf_explorer.config import OCEAN_SIZE
        pct_x = int(player.ocean_x / OCEAN_SIZE * 100)
        pct_y = int(player.ocean_y / OCEAN_SIZE * 100)
        await interaction.followup.send(
            f"🌊 **High Seas** — You are at ocean position "
            f"({player.ocean_x}, {player.ocean_y}) — "
            f"{pct_x}% east, {pct_y}% south of the ocean grid.\n"
            f"Sail north (↑) toward y=0 to return to shore and dock.",
            ephemeral=True,
        )
        return

    other_players = await get_all_overworld_players(db, user_id)
    from dwarf_explorer.world.world_map import generate_world_map
    buf = await generate_world_map(seed, db, guild_id, player.world_x, player.world_y, other_players)
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
