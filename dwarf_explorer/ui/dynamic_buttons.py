from __future__ import annotations

import re

import discord

from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import get_or_create_player
from dwarf_explorer.ui.game_view import (
    handle_move, handle_interact, handle_sprint,
    handle_help, handle_help_back, handle_map,
    handle_inventory, handle_inv_nav, handle_inv_equip, handle_inv_close,
    handle_shop_nav, handle_shop_buy, handle_shop_sell, handle_shop_mode, handle_shop_close,
    handle_bank_nav, handle_bank_switch,
    handle_bank_deposit, handle_bank_withdraw, handle_bank_close,
    handle_combat_move, handle_combat_attack, handle_combat_flee,
    handle_combat_eat, handle_combat_end_turn,
    handle_chest_nav, handle_chest_switch, handle_chest_take,
    handle_chest_give, handle_chest_lootall, handle_chest_close,
    handle_mine,
    handle_canoe_move, handle_canoe_dock, handle_canoe_sail,
    handle_canoe_dest, handle_canoe_dest_nav, handle_canoe_dest_cancel,
    handle_ocean_move, handle_ocean_dock, handle_boat_grapple,
    handle_ship_enter, handle_ship_leave, handle_ship_move, handle_ship_room,
    handle_ship_repair,
    handle_ship_chest_open_personal, handle_ship_chest_open_cargo,
    handle_ship_chest_close,
    handle_island_move, handle_island_loot, handle_island_leave,
    _ship_chest_action,
    handle_merchant_nav, handle_merchant_buy, handle_merchant_close,
    handle_action,
    handle_forge_iron, handle_forge_close,
    handle_anvil_dagger, handle_anvil_sword, handle_anvil_close,
    handle_anvil_helmet, handle_anvil_chestplate, handle_anvil_leggings,
    handle_inv_eat,
    handle_inv_select, handle_inv_unselect_all,
    handle_inv_item_btn, handle_inv_item_inc, handle_inv_item_dec,
    handle_inv_item_unsel, handle_inv_item_back, handle_inv_craft,
    handle_inv_toggle_mode,
    handle_house_edit_move, handle_house_add, handle_house_remove,
    handle_house_delete, handle_house_edit_close,
    handle_house_deco_nav, handle_house_deco_sel, handle_house_deco_place,
    handle_house_deco_cancel,
)

_MOVE_ACTIONS   = {"up", "down", "left", "right"}
_MINE_ACTIONS   = {"mine_up", "mine_down", "mine_left", "mine_right"}
_COMBAT_MOVE_ACTIONS = {
    "c_up", "c_down", "c_left", "c_right",
    "c_upleft", "c_upright", "c_downleft", "c_downright",
}
_CANOE_MOVE_ACTIONS = {
    "canoe_up", "canoe_down", "canoe_left", "canoe_right",
    "canoe_upleft", "canoe_upright", "canoe_downleft", "canoe_downright",
}
_OCEAN_MOVE_ACTIONS = {
    "ocean_up", "ocean_down", "ocean_left", "ocean_right",
    "ocean_upleft", "ocean_upright", "ocean_downleft", "ocean_downright",
}
_IGNORED_ACTIONS = {
    "ship_hp_sp",
    "sp1", "sp2", "sp3", "sp4", "sp5", "c_wait", "csp0", "csp1", "c_free",
    "csp_a", "csp_b", "csp_c", "csp_d",
    "csp_5", "csp_6", "csp_7", "csp_8", "csp_9",
    "c_potion",
    # House edit spacers
    "hesp1", "hesp2", "hesp3",
    # Ocean spacers
    "ocsp1", "ocsp3", "ocsp4",
}
_HEDIT_MOVE_ACTIONS = {"hedit_up", "hedit_down", "hedit_left", "hedit_right"}


class GameButton(discord.ui.DynamicItem[discord.ui.Button],
                 template=r"dex:(?P<gid>\d+):(?P<uid>\d+):(?P<action>\w+)"):
    def __init__(self, guild_id: int, user_id: int, action: str):
        self.guild_id = guild_id
        self.user_id = user_id
        self.action = action
        super().__init__(
            discord.ui.Button(custom_id=f"dex:{guild_id}:{user_id}:{action}")
        )

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]
    ) -> GameButton:
        return cls(int(match.group("gid")), int(match.group("uid")), match.group("action"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your game! Use `/explore` to start your own.", ephemeral=True
            )
            return False
        return True

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.action in _IGNORED_ACTIONS:
            await interaction.response.defer()
            return

        gid, uid, act = self.guild_id, self.user_id, self.action

        try:
            if act in _OCEAN_MOVE_ACTIONS:
                direction = act[6:]  # strip "ocean_" prefix
                await handle_ocean_move(interaction, gid, uid, direction)
            elif act == "ocean_dock":
                await handle_ocean_dock(interaction, gid, uid)
            elif act == "boat_grapple":
                await handle_boat_grapple(interaction, gid, uid)
            # Ship interior
            elif act == "ship_enter":
                await handle_ship_enter(interaction, gid, uid)
            elif act == "ship_leave":
                await handle_ship_leave(interaction, gid, uid)
            elif act in ("ship_room_helm", "ship_room_quarters", "ship_room_lower_deck"):
                room = act.removeprefix("ship_room_")
                await handle_ship_room(interaction, gid, uid, room)
            elif act == "ship_repair":
                await handle_ship_repair(interaction, gid, uid)
            elif act == "ship_chest_personal_open":
                await handle_ship_chest_open_personal(interaction, gid, uid)
            elif act == "ship_chest_cargo_open":
                await handle_ship_chest_open_cargo(interaction, gid, uid)
            elif act == "ship_chest_close":
                await handle_ship_chest_close(interaction, gid, uid)
            elif act.startswith("ship_chest_personal_"):
                sub = act.removeprefix("ship_chest_personal_")
                await _ship_chest_action(interaction, gid, uid, "personal", sub)
            elif act.startswith("ship_chest_cargo_"):
                sub = act.removeprefix("ship_chest_cargo_")
                await _ship_chest_action(interaction, gid, uid, "cargo", sub)
            # Island
            elif act in ("island_up", "island_down", "island_left", "island_right"):
                direction = act.removeprefix("island_")
                await handle_island_move(interaction, gid, uid, direction)
            elif act == "island_loot":
                await handle_island_loot(interaction, gid, uid)
            elif act == "island_leave":
                await handle_island_leave(interaction, gid, uid)
            elif act in _CANOE_MOVE_ACTIONS:
                direction = act[6:]  # strip "canoe_" prefix
                await handle_canoe_move(interaction, gid, uid, direction)
            elif act == "canoe_dock":
                await handle_canoe_dock(interaction, gid, uid)
            elif act == "canoe_sail":
                await handle_canoe_sail(interaction, gid, uid)
            elif act.startswith("csail_") and act[6:].isdigit():
                await handle_canoe_dest(interaction, gid, uid, int(act[6:]))
            elif act == "csail_prev":
                await handle_canoe_dest_nav(interaction, gid, uid, -1)
            elif act == "csail_next":
                await handle_canoe_dest_nav(interaction, gid, uid, +1)
            elif act == "csail_cancel":
                await handle_canoe_dest_cancel(interaction, gid, uid)
            elif act in _MINE_ACTIONS:
                direction = act[5:]  # strip "mine_" prefix
                await handle_mine(interaction, gid, uid, direction)
            elif act in _COMBAT_MOVE_ACTIONS:
                direction = act[2:]  # strip "c_" prefix
                await handle_combat_move(interaction, gid, uid, direction)
            elif act == "c_attack":
                await handle_combat_attack(interaction, gid, uid)
            elif act == "c_flee":
                await handle_combat_flee(interaction, gid, uid)
            elif act == "c_eat":
                await handle_combat_eat(interaction, gid, uid)
            elif act == "c_endturn":
                await handle_combat_end_turn(interaction, gid, uid)
            elif act == "c_inventory":
                await handle_inventory(interaction, gid, uid)
            elif act == "action":
                await handle_action(interaction, gid, uid)
            # Forge
            elif act == "forge_iron":
                await handle_forge_iron(interaction, gid, uid)
            elif act == "forge_close":
                await handle_forge_close(interaction, gid, uid)
            # Anvil
            elif act == "anvil_dagger":
                await handle_anvil_dagger(interaction, gid, uid)
            elif act == "anvil_sword":
                await handle_anvil_sword(interaction, gid, uid)
            elif act == "anvil_helmet":
                await handle_anvil_helmet(interaction, gid, uid)
            elif act == "anvil_chestplate":
                await handle_anvil_chestplate(interaction, gid, uid)
            elif act == "anvil_leggings":
                await handle_anvil_leggings(interaction, gid, uid)
            elif act == "anvil_close":
                await handle_anvil_close(interaction, gid, uid)
            elif act in _MOVE_ACTIONS:
                # Route ship interior movement separately
                db = await get_database(gid)
                _player = await get_or_create_player(db, uid, interaction.user.display_name)
                if _player.in_ship:
                    await handle_ship_move(interaction, gid, uid, act)
                else:
                    await handle_move(interaction, gid, uid, act)
            elif act == "interact":
                await handle_interact(interaction, gid, uid)
            elif act == "sprint":
                await handle_sprint(interaction, gid, uid)
            elif act == "help":
                await handle_help(interaction, gid, uid)
            elif act == "help_back":
                await handle_help_back(interaction, gid, uid)
            elif act == "map":
                await handle_map(interaction, gid, uid)
            elif act == "inventory":
                await handle_inventory(interaction, gid, uid)
            # Inventory navigation
            elif act == "inv_prev":
                await handle_inv_nav(interaction, gid, uid, -1)
            elif act == "inv_next":
                await handle_inv_nav(interaction, gid, uid, +1)
            elif act == "inv_equip":
                await handle_inv_equip(interaction, gid, uid)
            elif act == "inv_eat":
                await handle_inv_eat(interaction, gid, uid)
            elif act == "inv_select":
                await handle_inv_select(interaction, gid, uid)
            elif act == "inv_unselect_all":
                await handle_inv_unselect_all(interaction, gid, uid)
            elif act == "inv_craft":
                await handle_inv_craft(interaction, gid, uid)
            elif act == "inv_item_inc":
                await handle_inv_item_inc(interaction, gid, uid)
            elif act == "inv_item_dec":
                await handle_inv_item_dec(interaction, gid, uid)
            elif act == "inv_item_unsel":
                await handle_inv_item_unsel(interaction, gid, uid)
            elif act == "inv_item_back":
                await handle_inv_item_back(interaction, gid, uid)
            elif act.startswith("inv_item_") and act[9:].isdigit():
                await handle_inv_item_btn(interaction, gid, uid, int(act[9:]))
            elif act == "inv_close":
                await handle_inv_close(interaction, gid, uid)
            # Shop
            elif act == "shop_prev":
                await handle_shop_nav(interaction, gid, uid, -1)
            elif act == "shop_next":
                await handle_shop_nav(interaction, gid, uid, +1)
            elif act == "shop_buy":
                await handle_shop_buy(interaction, gid, uid)
            elif act == "shop_sell":
                await handle_shop_sell(interaction, gid, uid)
            elif act == "shop_mode":
                await handle_shop_mode(interaction, gid, uid)
            elif act == "shop_close":
                await handle_shop_close(interaction, gid, uid)
            # Bank
            elif act == "bank_prev":
                await handle_bank_nav(interaction, gid, uid, -1)
            elif act == "bank_next":
                await handle_bank_nav(interaction, gid, uid, +1)
            elif act == "bank_switch":
                await handle_bank_switch(interaction, gid, uid)
            elif act == "bank_deposit":
                await handle_bank_deposit(interaction, gid, uid)
            elif act == "bank_withdraw":
                await handle_bank_withdraw(interaction, gid, uid)
            elif act == "bank_close":
                await handle_bank_close(interaction, gid, uid)
            # Chest
            elif act == "chest_prev":
                await handle_chest_nav(interaction, gid, uid, -1)
            elif act == "chest_next":
                await handle_chest_nav(interaction, gid, uid, +1)
            elif act == "chest_take":
                await handle_chest_take(interaction, gid, uid)
            elif act == "chest_give":
                await handle_chest_give(interaction, gid, uid)
            elif act == "chest_lootall":
                await handle_chest_lootall(interaction, gid, uid)
            elif act == "chest_switch":
                await handle_chest_switch(interaction, gid, uid)
            elif act == "chest_close":
                await handle_chest_close(interaction, gid, uid)
            # Merchant
            elif act == "merch_prev":
                await handle_merchant_nav(interaction, gid, uid, -1)
            elif act == "merch_next":
                await handle_merchant_nav(interaction, gid, uid, +1)
            elif act == "merch_buy":
                await handle_merchant_buy(interaction, gid, uid)
            elif act == "merch_close":
                await handle_merchant_close(interaction, gid, uid)
            # Inventory mode toggle
            elif act == "inv_toggle_mode":
                await handle_inv_toggle_mode(interaction, gid, uid)
            # Player house edit
            elif act in _HEDIT_MOVE_ACTIONS:
                direction = act[6:]  # strip "hedit_"
                await handle_house_edit_move(interaction, gid, uid, direction)
            elif act == "hedit_add":
                await handle_house_add(interaction, gid, uid)
            elif act == "hedit_remove":
                await handle_house_remove(interaction, gid, uid)
            elif act == "hedit_delete":
                await handle_house_delete(interaction, gid, uid)
            elif act == "hedit_close":
                await handle_house_edit_close(interaction, gid, uid)
            # House decoration
            elif act == "hdeco_prev":
                await handle_house_deco_nav(interaction, gid, uid, "prev")
            elif act == "hdeco_next":
                await handle_house_deco_nav(interaction, gid, uid, "next")
            elif act == "hdeco_place":
                await handle_house_deco_place(interaction, gid, uid)
            elif act == "hdeco_cancel":
                await handle_house_deco_cancel(interaction, gid, uid)
            elif act.startswith("hdeco_sel_") and act[10:].isdigit():
                await handle_house_deco_sel(interaction, gid, uid, int(act[10:]))
            elif act.startswith("hdsp_") and act[5:].isdigit():
                await interaction.response.defer()  # decoration page padding spacer

        except discord.NotFound:
            await interaction.followup.send(
                "Your game message was deleted. Use `/explore` to start again.", ephemeral=True
            )
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"Something went wrong: {e}", ephemeral=True)
            except Exception:
                pass
