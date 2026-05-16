from __future__ import annotations

import re

import discord

from dwarf_explorer.config import ADMIN_PLAYER_ID, ADMIN_DISCORD_ID
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import get_or_create_player
from dwarf_explorer.ui.game_view import (
    handle_move, handle_interact, handle_sprint,
    handle_help, handle_help_back, handle_map,
    handle_inventory, handle_inv_nav, handle_inv_equip, handle_inv_close,
    handle_shop_nav, handle_shop_buy, handle_shop_sell, handle_shop_mode,
    handle_shop_switch, handle_shop_up, handle_shop_down,
    handle_shop_qty_inc, handle_shop_qty_dec, handle_shop_close,
    handle_bank_nav, handle_bank_up, handle_bank_down, handle_bank_switch,
    handle_bank_qty_inc, handle_bank_qty_dec,
    handle_bank_deposit, handle_bank_withdraw, handle_bank_close,
    handle_bank_qty_modal, handle_shop_qty_modal,
    handle_combat_move, handle_combat_attack, handle_combat_flee,
    handle_combat_eat, handle_combat_end_turn,
    handle_chest_nav, handle_chest_switch, handle_chest_take,
    handle_chest_give, handle_chest_lootall, handle_chest_close,
    handle_fst_chest_nav, handle_fst_chest_take,
    handle_fst_chest_lootall, handle_fst_chest_close,
    handle_mine,
    handle_canoe_move, handle_canoe_dock, handle_canoe_sail,
    handle_canoe_dest, handle_canoe_dest_nav, handle_canoe_dest_cancel,
    handle_ocean_move, handle_ocean_dock, handle_boat_grapple,
    handle_ship_enter, handle_ship_leave, handle_ship_move, handle_ship_room,
    handle_ship_repair,
    handle_ship_chest_open_personal, handle_ship_chest_open_cargo,
    handle_ship_chest_close,
    handle_island_move, handle_island_loot, handle_island_leave,
    handle_ocean_fish, handle_island_dock_hs,
    _ship_chest_action,
    handle_merchant_nav, handle_merchant_buy, handle_merchant_close,
    handle_action,
    handle_forge_iron, handle_forge_gold, handle_forge_gold_ring, handle_forge_close,
    handle_anvil_up, handle_anvil_down, handle_anvil_prev, handle_anvil_next,
    handle_anvil_mat_prev, handle_anvil_mat_next,
    handle_anvil_mat_iron, handle_anvil_mat_wyvern,
    handle_anvil_craft, handle_anvil_close,
    handle_anvil_dagger, handle_anvil_sword,
    handle_anvil_helmet, handle_anvil_chestplate, handle_anvil_leggings,
    handle_anvil_cannonball, handle_anvil_iron_boots, handle_anvil_iron_shield,
    handle_anvil_wyvern_helmet, handle_anvil_wyvern_chestplate,
    handle_anvil_wyvern_leggings, handle_anvil_wyvern_shield,
    handle_shrine_enchant, handle_shrine_cancel,
    handle_combat_consume, handle_combat_consume_cancel,
    handle_bribe,
    handle_inv_eat,
    handle_inv_select, handle_inv_unselect_all,
    handle_inv_item_btn, handle_inv_item_inc, handle_inv_item_dec,
    handle_inv_item_unsel, handle_inv_item_back, handle_inv_craft,
    handle_inv_toggle_mode,
    handle_inv_up, handle_inv_down,
    handle_inv_sel_inc, handle_inv_sel_dec,
    handle_inv_drop,
    handle_inv_move, handle_inv_move_confirm, handle_inv_move_cancel,
    handle_inv_move_qty_inc, handle_inv_move_qty_dec,
    handle_inv_qty_modal,
    handle_inv_unequip,
    handle_bank_qty_modal,
    handle_shop_qty_modal,
    handle_house_edit_move, handle_house_add, handle_house_remove,
    handle_house_delete, handle_house_edit_close,
    handle_house_deco_nav, handle_house_deco_sel, handle_house_deco_place,
    handle_house_deco_cancel,
    handle_quests, handle_quest_nav, handle_quest_cancel,
    handle_quest_cancel_confirm, handle_quest_cancel_back, handle_quest_close,
    handle_quest_set_target,
    handle_quest_up, handle_quest_down,
    handle_quest_tab_left, handle_quest_tab_right,
    handle_quest_abandon, handle_quest_abandon_confirm, handle_quest_abandon_back,
    handle_open_quest_pool, handle_qpool_nav, handle_qpool_accept, handle_qpool_close,
    handle_merchant_quest_offer, handle_quest_offer_accept, handle_quest_offer_decline,
    handle_qswap, handle_qswap_pass,
    handle_npc_quest,
    handle_quest_main,
    handle_mq_nav,
    handle_mq_close,
    handle_tavern_buy, handle_tavern_close,
    handle_crew_npc_talk, handle_dialogue_nav, handle_dialogue_confirm, handle_dialogue_cancel,
    handle_ship_crew_view, handle_crew_task_cycle, handle_crew_fire, handle_crew_close,
    handle_village_recruit_confirm, handle_village_recruit_cancel,
    handle_heal_accept, handle_heal_decline,
    handle_lumber_convert_confirm, handle_lumber_convert_cancel,
    handle_lumber_craft_canoe,
    handle_farmer_buy, handle_farmer_close,
    handle_embark,
    handle_feed_cat,
    handle_plant,
    handle_plant_choice,
    handle_plant_cancel,
    handle_puzzle_move,
    handle_puzzle_reset,
    handle_puzzle_close,
    handle_gear_slot,
    handle_gear_machine_close,
    handle_tree_city_buy,
    handle_tree_city_close,
    handle_warp_open,
    handle_warp_close,
    _execute_warp,
    handle_nav_open,
    handle_nav_close,
    handle_npc_talk,
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
# Actions that open a modal — must NOT defer first (send_modal IS the response)
_MODAL_ACTIONS = {"inv_qty_modal", "bank_qty_modal", "shop_qty_modal"}

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
    # Bank/shop spacers
    "bank_sp4", "shop_sp4",
    # Inventory spacers (all inv_sp*)
    "inv_sp1", "inv_sp2", "inv_sp3", "inv_sp4", "inv_sp5", "inv_sp6",
    "inv_sp_r0c", "inv_sp_r0d",
    # Quest spacers (qsp_*)  — caught dynamically below
    # NPC button spacer
    "sp_npc",
    # Dialogue spacer
    "dlg_sp1",
    # Puzzle board info labels (disabled counters)
    "pzsp0a", "pzsp0b",
    # D-pad blank flanking buttons
    "sp_ul", "sp_ur", "sp_dl", "sp_dr",
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
        # Admin account buttons are owned by the ADMIN_DISCORD_ID user
        if self.user_id == ADMIN_PLAYER_ID:
            if interaction.user.id != ADMIN_DISCORD_ID:
                await interaction.response.send_message(
                    "This is the admin account. Use `/explore` for your own game.", ephemeral=True
                )
                return False
            return True
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
                # Route through handle_move → _move_steps island branch
                direction = act.removeprefix("island_")
                await handle_move(interaction, gid, uid, direction)
            elif act == "island_loot":
                await handle_island_loot(interaction, gid, uid)
            elif act == "island_leave":
                await handle_island_leave(interaction, gid, uid)
            elif act == "island_dock_hs":
                await handle_island_dock_hs(interaction, gid, uid)
            elif act == "ocean_fish":
                await handle_ocean_fish(interaction, gid, uid)
            elif act in _CANOE_MOVE_ACTIONS:
                direction = act[6:]  # strip "canoe_" prefix
                await handle_canoe_move(interaction, gid, uid, direction)
            elif act == "canoe_dock" or act.startswith("canoe_dock_"):
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
            elif act == "c_bribe":
                await handle_bribe(interaction, gid, uid)
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
            elif act == "forge_gold":
                await handle_forge_gold(interaction, gid, uid)
            elif act == "forge_gold_ring":
                await handle_forge_gold_ring(interaction, gid, uid)
            elif act == "forge_close":
                await handle_forge_close(interaction, gid, uid)
            # Anvil (list-style navigation)
            elif act == "anvil_up":
                await handle_anvil_up(interaction, gid, uid)
            elif act == "anvil_down":
                await handle_anvil_down(interaction, gid, uid)
            elif act == "anvil_prev":
                await handle_anvil_prev(interaction, gid, uid)
            elif act == "anvil_next":
                await handle_anvil_next(interaction, gid, uid)
            elif act == "anvil_mat_prev":
                await handle_anvil_mat_prev(interaction, gid, uid)
            elif act == "anvil_mat_next":
                await handle_anvil_mat_next(interaction, gid, uid)
            elif act == "anvil_mat_iron":
                await handle_anvil_mat_iron(interaction, gid, uid)
            elif act == "anvil_mat_wyvern":
                await handle_anvil_mat_wyvern(interaction, gid, uid)
            elif act == "anvil_craft":
                await handle_anvil_craft(interaction, gid, uid)
            elif act == "anvil_close":
                await handle_anvil_close(interaction, gid, uid)
            # Anvil (legacy individual-button handlers — kept for compatibility)
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
            elif act == "anvil_cannonball":
                await handle_anvil_cannonball(interaction, gid, uid)
            elif act == "anvil_iron_boots":
                await handle_anvil_iron_boots(interaction, gid, uid)
            elif act == "anvil_iron_shield":
                await handle_anvil_iron_shield(interaction, gid, uid)
            elif act == "anvil_wyvern_helmet":
                await handle_anvil_wyvern_helmet(interaction, gid, uid)
            elif act == "anvil_wyvern_chestplate":
                await handle_anvil_wyvern_chestplate(interaction, gid, uid)
            elif act == "anvil_wyvern_leggings":
                await handle_anvil_wyvern_leggings(interaction, gid, uid)
            elif act == "anvil_wyvern_shield":
                await handle_anvil_wyvern_shield(interaction, gid, uid)
            # Shrine
            elif act.startswith("shrine_") and act[7:] in ("strength", "time", "defense", "sight", "luck"):
                await handle_shrine_enchant(interaction, gid, uid, act[7:])
            elif act == "shrine_cancel":
                await handle_shrine_cancel(interaction, gid, uid)
            # Consumables (combat food menu)
            elif act.startswith("consume_") and act != "consume_cancel":
                item_id = act[8:]  # strip "consume_"
                await handle_combat_consume(interaction, gid, uid, item_id)
            elif act == "consume_cancel":
                await handle_combat_consume_cancel(interaction, gid, uid)
            elif act in _MOVE_ACTIONS:
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
            elif act == "inv_up":
                await handle_inv_up(interaction, gid, uid)
            elif act == "inv_down":
                await handle_inv_down(interaction, gid, uid)
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
            elif act == "shop_up":
                await handle_shop_up(interaction, gid, uid)
            elif act == "shop_down":
                await handle_shop_down(interaction, gid, uid)
            elif act == "shop_qty_inc":
                await handle_shop_qty_inc(interaction, gid, uid)
            elif act == "shop_qty_dec":
                await handle_shop_qty_dec(interaction, gid, uid)
            elif act == "shop_qty_modal":
                await handle_shop_qty_modal(interaction, gid, uid)
            elif act == "shop_buy":
                await handle_shop_buy(interaction, gid, uid)
            elif act == "shop_sell":
                await handle_shop_sell(interaction, gid, uid)
            elif act == "shop_switch":
                await handle_shop_switch(interaction, gid, uid)
            elif act == "shop_mode":
                await handle_shop_mode(interaction, gid, uid)
            elif act == "shop_close":
                await handle_shop_close(interaction, gid, uid)
            # Bank
            elif act == "bank_prev":
                await handle_bank_nav(interaction, gid, uid, -1)
            elif act == "bank_next":
                await handle_bank_nav(interaction, gid, uid, +1)
            elif act == "bank_up":
                await handle_bank_up(interaction, gid, uid)
            elif act == "bank_down":
                await handle_bank_down(interaction, gid, uid)
            elif act == "bank_qty_inc":
                await handle_bank_qty_inc(interaction, gid, uid)
            elif act == "bank_qty_dec":
                await handle_bank_qty_dec(interaction, gid, uid)
            elif act == "bank_qty_modal":
                await handle_bank_qty_modal(interaction, gid, uid)
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
            elif act == "fst_chest_prev":
                await handle_fst_chest_nav(interaction, gid, uid, -1)
            elif act == "fst_chest_next":
                await handle_fst_chest_nav(interaction, gid, uid, 1)
            elif act == "fst_chest_take":
                await handle_fst_chest_take(interaction, gid, uid)
            elif act == "fst_chest_lootall":
                await handle_fst_chest_lootall(interaction, gid, uid)
            elif act == "fst_chest_close":
                await handle_fst_chest_close(interaction, gid, uid)
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
            # Inventory quantity selection
            elif act == "inv_sel_inc":
                await handle_inv_sel_inc(interaction, gid, uid)
            elif act == "inv_sel_dec":
                await handle_inv_sel_dec(interaction, gid, uid)
            # Inventory drop
            elif act == "inv_drop":
                await handle_inv_drop(interaction, gid, uid)
            # Inventory move mode
            elif act == "inv_move":
                await handle_inv_move(interaction, gid, uid)
            elif act == "inv_move_confirm":
                await handle_inv_move_confirm(interaction, gid, uid)
            elif act == "inv_move_cancel":
                await handle_inv_move_cancel(interaction, gid, uid)
            elif act == "inv_move_qty_inc":
                await handle_inv_move_qty_inc(interaction, gid, uid)
            elif act == "inv_move_qty_dec":
                await handle_inv_move_qty_dec(interaction, gid, uid)
            elif act == "inv_qty_modal":
                await handle_inv_qty_modal(interaction, gid, uid)
            # Inventory unequip
            elif act == "inv_unequip":
                await handle_inv_unequip(interaction, gid, uid)
            # Quest spacer buttons
            elif act.startswith("qsp_"):
                await interaction.response.defer()
            # Quests
            elif act == "quests":
                await handle_quests(interaction, gid, uid)
            elif act == "quest_prev":
                await handle_quest_nav(interaction, gid, uid, -1)
            elif act == "quest_next":
                await handle_quest_nav(interaction, gid, uid, +1)
            elif act == "quest_cancel":
                await handle_quest_cancel(interaction, gid, uid)
            elif act == "quest_cancel_confirm":
                await handle_quest_cancel_confirm(interaction, gid, uid)
            elif act == "quest_cancel_back":
                await handle_quest_cancel_back(interaction, gid, uid)
            elif act == "quest_close":
                await handle_quest_close(interaction, gid, uid)
            elif act == "quest_set_target":
                await handle_quest_set_target(interaction, gid, uid)
            # New D-pad quest navigation
            elif act == "quest_up":
                await handle_quest_up(interaction, gid, uid)
            elif act == "quest_down":
                await handle_quest_down(interaction, gid, uid)
            elif act == "quest_tab_left":
                await handle_quest_tab_left(interaction, gid, uid)
            elif act == "quest_tab_right":
                await handle_quest_tab_right(interaction, gid, uid)
            elif act == "quest_abandon":
                await handle_quest_abandon(interaction, gid, uid)
            elif act == "quest_abandon_confirm":
                await handle_quest_abandon_confirm(interaction, gid, uid)
            elif act == "quest_abandon_back":
                await handle_quest_abandon_back(interaction, gid, uid)
            elif act == "quest_main":
                await handle_quest_main(interaction, gid, uid)
            elif act == "mq_prev":
                await handle_mq_nav(interaction, gid, uid, -1)
            elif act == "mq_next":
                await handle_mq_nav(interaction, gid, uid, 1)
            elif act == "mq_close":
                await handle_mq_close(interaction, gid, uid)
            elif act == "mq_header":
                await interaction.response.defer()
            # Quest pool (village / bounty board)
            elif act == "qpool_prev":
                await handle_qpool_nav(interaction, gid, uid, -1)
            elif act == "qpool_next":
                await handle_qpool_nav(interaction, gid, uid, +1)
            elif act == "qpool_accept":
                await handle_qpool_accept(interaction, gid, uid)
            elif act == "qpool_close":
                await handle_qpool_close(interaction, gid, uid)
            # NPC talk button (bottom-right) — new dialogue system
            elif act == "npc_talk":
                await handle_npc_talk(interaction, gid, uid)
            # NPC quest button (bottom-right) — legacy routing for old messages
            elif act == "npc_quest":
                await handle_npc_quest(interaction, gid, uid)
            # Merchant quest offer
            elif act == "merch_quest":
                await handle_merchant_quest_offer(interaction, gid, uid)
            elif act == "quest_offer_accept":
                await handle_quest_offer_accept(interaction, gid, uid)
            elif act == "quest_offer_decline":
                await handle_quest_offer_decline(interaction, gid, uid)
            # Quest swap (merchant offer when at max quests)
            elif act.startswith("qswap_") and act[6:].isdigit():
                await handle_qswap(interaction, gid, uid, int(act[6:]))
            elif act == "qswap_pass":
                await handle_qswap_pass(interaction, gid, uid)
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
            # Tavern buy menu
            elif act.startswith("tavern_buy_"):
                item_id = act[len("tavern_buy_"):]
                await handle_tavern_buy(interaction, gid, uid, item_id)
            elif act == "tavern_close":
                await handle_tavern_close(interaction, gid, uid)
            # NPC Dialogue system
            elif act == "dlg_up":
                await handle_dialogue_nav(interaction, gid, uid, -1)
            elif act == "dlg_down":
                await handle_dialogue_nav(interaction, gid, uid, +1)
            elif act == "dlg_cancel":
                await handle_dialogue_cancel(interaction, gid, uid)
            elif act.startswith("dlg_confirm_"):
                action = act[len("dlg_confirm_"):]
                await handle_dialogue_confirm(interaction, gid, uid, action)
            # Ship crew management
            elif act == "ship_crew_view":
                await handle_ship_crew_view(interaction, gid, uid)
            elif act.startswith("crew_task_") and act[len("crew_task_"):].isdigit():
                slot = int(act[len("crew_task_"):])
                await handle_crew_task_cycle(interaction, gid, uid, slot)
            elif act.startswith("crew_fire_") and act[len("crew_fire_"):].isdigit():
                slot = int(act[len("crew_fire_"):])
                await handle_crew_fire(interaction, gid, uid, slot)
            elif act == "crew_close":
                await handle_crew_close(interaction, gid, uid)
            elif act.startswith("crew_sp_"):
                await interaction.response.defer()  # crew slot name label spacer
            # Village open-world recruitable NPC
            elif act == "village_recruit_confirm":
                await handle_village_recruit_confirm(interaction, gid, uid)
            elif act == "village_recruit_cancel":
                await handle_village_recruit_cancel(interaction, gid, uid)
            # Hospital heal confirm
            elif act == "heal_accept":
                await handle_heal_accept(interaction, gid, uid)
            elif act == "heal_decline":
                await handle_heal_decline(interaction, gid, uid)
            # Lumber convert
            elif act == "lumber_convert":
                await handle_lumber_convert_confirm(interaction, gid, uid)
            elif act == "lumber_convert_cancel":
                await handle_lumber_convert_cancel(interaction, gid, uid)
            elif act == "lumber_craft_canoe":
                await handle_lumber_craft_canoe(interaction, gid, uid)
            elif act == "embark":
                await handle_embark(interaction, gid, uid)
            elif act == "feed_cat":
                await handle_feed_cat(interaction, gid, uid)
            elif act == "plant":
                await handle_plant(interaction, gid, uid)
            elif act == "plant_cancel":
                await handle_plant_cancel(interaction, gid, uid)
            elif act.startswith("plant_choice_"):
                seed_type = act[len("plant_choice_"):]
                await handle_plant_choice(interaction, gid, uid, seed_type)
            # Farmer shop
            elif act.startswith("farmer_buy_"):
                item_id = act[len("farmer_buy_"):]
                await handle_farmer_buy(interaction, gid, uid, item_id)
            elif act == "farmer_close":
                await handle_farmer_close(interaction, gid, uid)
            # Puzzle board
            elif act in ("puzzle_up", "puzzle_down", "puzzle_left", "puzzle_right"):
                direction = act[7:]  # strip "puzzle_"
                await handle_puzzle_move(interaction, gid, uid, direction)
            elif act == "puzzle_reset":
                await handle_puzzle_reset(interaction, gid, uid)
            elif act == "puzzle_close":
                await handle_puzzle_close(interaction, gid, uid)
            elif act == "gear_machine_close":
                await handle_gear_machine_close(interaction, gid, uid)
            # Tree city shop
            elif act.startswith("tree_city_buy_"):
                item_id = act[len("tree_city_buy_"):]
                await handle_tree_city_buy(interaction, gid, uid, item_id)
            elif act == "tree_city_close":
                await handle_tree_city_close(interaction, gid, uid)
            # Navigation overlay
            elif act == "nav_open":
                await handle_nav_open(interaction, gid, uid)
            elif act == "nav_close":
                await handle_nav_close(interaction, gid, uid)
            # Warp crystal
            elif act == "warp_open":
                await handle_warp_open(interaction, gid, uid)
            elif act == "warp_close":
                await handle_warp_close(interaction, gid, uid)
            elif act.startswith("warp_"):
                wp_id = act[len("warp_"):]
                await _execute_warp(interaction, gid, uid, wp_id)
            elif act.startswith("gear_slot_"):
                try:
                    slot_idx = int(act[len("gear_slot_"):])
                    await handle_gear_slot(interaction, gid, uid, slot_idx)
                except (ValueError, IndexError):
                    pass

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
