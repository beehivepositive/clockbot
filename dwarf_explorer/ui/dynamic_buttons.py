from __future__ import annotations

import re

import discord

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
    handle_merchant_nav, handle_merchant_buy, handle_merchant_close,
    handle_action,
    handle_forge_iron, handle_forge_close,
    handle_anvil_dagger, handle_anvil_sword, handle_anvil_close,
    handle_anvil_helmet, handle_anvil_chestplate, handle_anvil_leggings,
    handle_inv_eat,
    handle_inv_select, handle_inv_unselect_all,
    handle_inv_item_btn, handle_inv_item_inc, handle_inv_item_dec,
    handle_inv_item_unsel, handle_inv_item_back, handle_inv_craft,
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
_IGNORED_ACTIONS = {
    "sp1", "sp2", "sp3", "sp4", "sp5", "c_wait", "csp0", "csp1", "c_free",
    "csp_a", "csp_b", "csp_c", "csp_d",
    "csp_5", "csp_6", "csp_7", "csp_8", "csp_9",
    "c_potion",
}


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
            if act in _CANOE_MOVE_ACTIONS:
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
