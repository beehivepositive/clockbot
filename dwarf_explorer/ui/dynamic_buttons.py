from __future__ import annotations

import re

import discord

from dwarf_explorer.ui.game_view import (
    handle_move, handle_interact, handle_sprint,
    handle_help, handle_help_back, handle_map,
    handle_inventory, handle_inv_nav, handle_inv_equip, handle_inv_close,
    handle_shop_nav, handle_shop_buy, handle_shop_close,
    handle_bank_nav, handle_bank_switch,
    handle_bank_deposit, handle_bank_withdraw, handle_bank_close,
)

_MOVE_ACTIONS   = {"up", "down", "left", "right"}
_IGNORED_ACTIONS = {"sp1", "sp2"}


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
            if act in _MOVE_ACTIONS:
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
