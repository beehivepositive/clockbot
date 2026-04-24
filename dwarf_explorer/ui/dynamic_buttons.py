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
    handle_combat_potion, handle_combat_end_turn,
    handle_chest_nav, handle_chest_switch, handle_chest_take,
    handle_chest_give, handle_chest_lootall, handle_chest_close,
    handle_mine,
)

_MOVE_ACTIONS   = {"up", "down", "left", "right"}
_MINE_ACTIONS   = {"mine_up", "mine_down", "mine_left", "mine_right"}
_COMBAT_MOVE_ACTIONS = {
    "c_up", "c_down", "c_left", "c_right",
    "c_upleft", "c_upright", "c_downleft", "c_downright",
}
_IGNORED_ACTIONS = {"sp1", "sp2", "c_wait", "csp0", "csp1", "c_free"}


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
            return

        gid, uid, act = self.guild_id, self.user_id, self.action

        try:
            if act in _MINE_ACTIONS:
                direction = act[5:]  # strip "mine_" prefix
                await handle_mine(interaction, gid, uid, direction)
            elif act in _COMBAT_MOVE_ACTIONS:
                direction = act[2:]  # strip "c_" prefix
                await handle_combat_move(interaction, gid, uid, direction)
            elif act == "c_attack":
                await handle_combat_attack(interaction, gid, uid)
            elif act == "c_flee":
                await handle_combat_flee(interaction, gid, uid)
            elif act == "c_potion":
                await handle_combat_potion(interaction, gid, uid)
            elif act == "c_endturn":
                await handle_combat_end_turn(interaction, gid, uid)
            elif act == "c_inventory":
                await handle_inventory(interaction, gid, uid)
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
