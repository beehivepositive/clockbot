from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world, update_player_message,
    is_world_initialized, mark_world_initialized,
)
from dwarf_explorer.world.generator import load_viewport, init_world
from dwarf_explorer.game.renderer import render_grid
from dwarf_explorer.ui.game_view import GameView
from dwarf_explorer.ui.dynamic_buttons import GameButton


class DwarfExplorer(commands.Cog):
    """Dwarf Fortress-inspired emoji grid exploration game."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(GameButton)
        from dwarf_explorer.config import apply_custom_emojis
        apply_custom_emojis(self.bot.emojis)

    @app_commands.command(name="explore", description="Start or resume your Dwarf Explorer adventure!")
    async def explore(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)

        # On first use, generate rivers and structures (deferred to avoid timeout)
        if not await is_world_initialized(db, guild_id):
            await interaction.response.defer()
            await init_world(seed, db)
            await mark_world_initialized(db, guild_id)
            player = await get_or_create_player(db, user_id, interaction.user.display_name)
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player)
            view = GameView(guild_id, user_id)
            await interaction.followup.send(content=content, view=view)
        else:
            player = await get_or_create_player(db, user_id, interaction.user.display_name)
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player)
            view = GameView(guild_id, user_id)
            await interaction.response.send_message(content=content, view=view)

        # Store the message reference for future use
        msg = await interaction.original_response()
        await update_player_message(db, user_id, msg.id, interaction.channel_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DwarfExplorer(bot))
