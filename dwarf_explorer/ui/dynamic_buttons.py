from __future__ import annotations

import re

import discord

from dwarf_explorer.ui.game_view import (
    handle_move, handle_interact, handle_help, handle_help_back, handle_map,
)

# Matches: dex:{guild_id}:{user_id}:{action}
_PATTERN = re.compile(r"dex:(?P<gid>\d+):(?P<uid>\d+):(?P<action>\w+)")

_MOVE_ACTIONS = {"up", "down", "left", "right"}
_IGNORED_ACTIONS = {"sp1", "sp2"}  # Spacer buttons


class GameButton(discord.ui.DynamicItem[discord.ui.Button],
                 template=r"dex:(?P<gid>\d+):(?P<uid>\d+):(?P<action>\w+)"):
    """Persistent button handler that survives bot restarts.

    discord.py matches the custom_id against the template regex,
    calls from_custom_id to reconstruct, then dispatches callback.
    """

    def __init__(self, guild_id: int, user_id: int, action: str):
        self.guild_id = guild_id
        self.user_id = user_id
        self.action = action
        super().__init__(
            discord.ui.Button(
                custom_id=f"dex:{guild_id}:{user_id}:{action}",
            )
        )

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]
    ) -> GameButton:
        guild_id = int(match.group("gid"))
        user_id = int(match.group("uid"))
        action = match.group("action")
        return cls(guild_id, user_id, action)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the owning player can press their buttons."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your game! Use `/explore` to start your own.",
                ephemeral=True,
            )
            return False
        return True

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.action in _IGNORED_ACTIONS:
            return

        try:
            if self.action in _MOVE_ACTIONS:
                await handle_move(interaction, self.guild_id, self.user_id, self.action)
            elif self.action == "interact":
                await handle_interact(interaction, self.guild_id, self.user_id)
            elif self.action == "help":
                await handle_help(interaction, self.guild_id, self.user_id)
            elif self.action == "help_back":
                await handle_help_back(interaction, self.guild_id, self.user_id)
            elif self.action == "map":
                await handle_map(interaction, self.guild_id, self.user_id)
            elif self.action == "inventory":
                # Placeholder — will be expanded later
                await handle_interact(interaction, self.guild_id, self.user_id)
        except discord.NotFound:
            await interaction.followup.send(
                "Your game message was deleted. Use `/explore` to start again.",
                ephemeral=True,
            )
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"Something went wrong: {e}", ephemeral=True
                    )
            except Exception:
                pass
