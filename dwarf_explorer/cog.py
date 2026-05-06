from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from dwarf_explorer.config import SPAWN_X, SPAWN_Y, ADMIN_PLAYER_ID, ADMIN_DISCORD_ID
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world, update_player_message,
    update_player_stats,
    is_world_initialized, mark_world_initialized,
    reset_world_seed,
)
from dwarf_explorer.world.generator import load_viewport, init_world, find_walkable_spawn, find_walkable_near, find_village_spawn
from dwarf_explorer.world.villages import load_village_viewport
from dwarf_explorer.game.renderer import render_grid
from dwarf_explorer.ui.game_view import GameView
from dwarf_explorer.ui.dynamic_buttons import GameButton


async def _place_in_village(db, seed: int, user_id: int, player) -> None:
    """Place a fresh player inside the first available village.

    Eagerly creates the village interior (get_or_create_village) so the
    interior tiles exist before the player's state is saved.  Falls back
    to find_walkable_spawn if no village tile exists in tile_overrides.
    """
    vs = await find_village_spawn(seed, db)
    if vs:
        vwx, vwy, vid, vex, vey = vs
        await update_player_stats(
            db, user_id, world_x=vwx, world_y=vwy,
            in_village=1, village_id=vid,
            village_x=vex, village_y=vey,
            village_wx=vwx, village_wy=vwy,
        )
        player.world_x, player.world_y = vwx, vwy
        player.in_village = True
        player.village_id = vid
        player.village_x = vex
        player.village_y = vey
        player.village_wx = vwx
        player.village_wy = vwy
    else:
        sx, sy = await find_walkable_spawn(seed, db)
        if (sx, sy) != (player.world_x, player.world_y):
            await update_player_stats(db, user_id, world_x=sx, world_y=sy)
            player.world_x, player.world_y = sx, sy


async def _player_grid(player, seed: int, db):
    """Load the correct viewport for the player's current location."""
    if player.in_village:
        return await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    return await load_viewport(player.world_x, player.world_y, seed, db)


class DwarfExplorer(commands.Cog):
    """Dwarf Fortress-inspired emoji grid exploration game."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(GameButton)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
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
            from dwarf_explorer.world.world_map import generate_world_map
            # Pre-generate base map so first /map call is instant
            try:
                await generate_world_map(seed, db, guild_id, SPAWN_X, SPAWN_Y)
            except Exception:
                pass  # Non-fatal: map will be generated on demand if this fails
            player = await get_or_create_player(db, user_id, interaction.user.display_name)
            if player.xp == 0 and player.level == 1 and not player.in_village:
                await _place_in_village(db, seed, user_id, player)
            else:
                sx, sy = await find_walkable_spawn(seed, db)
                if (sx, sy) != (player.world_x, player.world_y):
                    await update_player_stats(db, user_id, world_x=sx, world_y=sy)
                    player.world_x, player.world_y = sx, sy
            grid = await _player_grid(player, seed, db)
            content = render_grid(grid, player)
            view = GameView(guild_id, user_id)
            await interaction.followup.send(embed=discord.Embed(description=content), view=view)
        else:
            player = await get_or_create_player(db, user_id, interaction.user.display_name)
            if player.xp == 0 and player.level == 1 and not player.in_village:
                await _place_in_village(db, seed, user_id, player)
            elif not player.in_cave and not player.in_village and not player.in_house:
                sx, sy = await find_walkable_near(seed, db, player.world_x, player.world_y)
                if (sx, sy) != (player.world_x, player.world_y):
                    await update_player_stats(db, user_id, world_x=sx, world_y=sy)
                    player.world_x, player.world_y = sx, sy
            grid = await _player_grid(player, seed, db)
            content = render_grid(grid, player)
            view = GameView(guild_id, user_id)
            await interaction.response.send_message(embed=discord.Embed(description=content), view=view)

        # Store the message reference for future use
        msg = await interaction.original_response()
        await update_player_message(db, user_id, msg.id, interaction.channel_id)


    @app_commands.command(name="spawn", description="Return to the spawn point (use if stuck).")
    async def spawn(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)

        sx, sy = await find_walkable_spawn(seed, db)
        await update_player_stats(
            db, user_id,
            world_x=sx, world_y=sy,
            in_cave=0, cave_id=None, cave_x=0, cave_y=0,
            in_village=0, village_id=None, village_x=0, village_y=0,
            in_house=0, house_id=None, house_x=0, house_y=0,
            in_combat=0, in_canoe=0,
        )

        player.world_x = sx
        player.world_y = sy
        player.in_cave = False
        player.in_village = False
        player.in_house = False
        player.in_combat = False
        player.in_canoe = False

        grid = await load_viewport(sx, sy, seed, db)
        content = render_grid(grid, player)
        view = GameView(guild_id, user_id)
        await interaction.response.send_message(embed=discord.Embed(description=content), view=view)
        msg = await interaction.original_response()
        await update_player_message(db, user_id, msg.id, interaction.channel_id)


    @app_commands.command(name="newworld", description="Reset and regenerate the world (admin only).")
    async def newworld(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.administrator:  # type: ignore[union-attr]
            await interaction.response.send_message(
                "You need Administrator permission to reset the world.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        db = await get_database(interaction.guild.id)

        # ── 1. Preserve admin account ─────────────────────────────────────────
        # If no admin account exists yet, create one from the designated user's data.
        admin_row = await db.fetch_one(
            "SELECT user_id FROM players WHERE user_id = ?", (ADMIN_PLAYER_ID,)
        )
        if not admin_row:
            src = await db.fetch_one(
                "SELECT * FROM players WHERE user_id = ?", (ADMIN_DISCORD_ID,)
            )
            if src:
                cols = [k for k in src.keys() if k != "user_id"]
                placeholders = ", ".join("?" for _ in cols)
                vals = tuple(src[c] for c in cols)
                await db.execute(
                    f"INSERT OR REPLACE INTO players (user_id, {', '.join(cols)}) "
                    f"VALUES (?, {placeholders})",
                    (ADMIN_PLAYER_ID, *vals),
                )
                # Copy inventory
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity, slot_index) "
                    "SELECT ?, item_id, quantity, slot_index FROM inventory WHERE user_id = ?",
                    (ADMIN_PLAYER_ID, ADMIN_DISCORD_ID),
                )
                # Copy equipment
                await db.execute(
                    "INSERT INTO equipment (user_id, slot, item_id) "
                    "SELECT ?, slot, item_id FROM equipment WHERE user_id = ?",
                    (ADMIN_PLAYER_ID, ADMIN_DISCORD_ID),
                )
                # Copy bank
                await db.execute(
                    "INSERT OR IGNORE INTO bank_items (user_id, item_id, quantity) "
                    "SELECT ?, item_id, quantity FROM bank_items WHERE user_id = ?",
                    (ADMIN_PLAYER_ID, ADMIN_DISCORD_ID),
                )

        # ── 2. Wipe all world data ────────────────────────────────────────────
        for table in [
            "tile_overrides", "cave_tiles", "cave_entrances", "cave_deep_entrances",
            "caves", "village_tiles", "village_entrances", "villages",
            "house_tiles", "house_entrances", "houses",
            "ground_items", "enemies", "chests", "chest_items",
        ]:
            try:
                await db.execute(f"DELETE FROM {table}")
            except Exception:
                pass

        # ── 3. Wipe all regular player data (preserve admin account) ─────────
        # Child tables must be deleted BEFORE players to avoid FK constraint errors.
        for tbl in ("inventory", "equipment", "bank_items", "player_quests", "treasure_maps"):
            try:
                await db.execute(f"DELETE FROM {tbl} WHERE user_id != ?", (ADMIN_PLAYER_ID,))
            except Exception:
                pass
        await db.execute("DELETE FROM players WHERE user_id != ?", (ADMIN_PLAYER_ID,))

        # ── 4. Generate new world ─────────────────────────────────────────────
        seed = await reset_world_seed(db)
        await init_world(seed, db)
        await mark_world_initialized(db, interaction.guild.id)

        # Bust the cached world map so the next /map renders the new world
        from dwarf_explorer.world.world_map import invalidate_map_cache
        invalidate_map_cache(interaction.guild.id)

        await interaction.followup.send(
            f"New world generated (seed `{seed}`)! All player data has been reset. "
            f"Use `/explore` to start playing.", ephemeral=True
        )


    @app_commands.command(name="adminexplore", description="Access your persistent admin character.")
    async def adminexplore(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id != ADMIN_DISCORD_ID:
            await interaction.response.send_message(
                "You don't have access to the admin account.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)

        player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)

        # Relocate if standing on impassable terrain in the new world
        if not player.in_cave and not player.in_village and not player.in_house:
            sx, sy = await find_walkable_near(seed, db, player.world_x, player.world_y)
            if (sx, sy) != (player.world_x, player.world_y):
                await update_player_stats(db, ADMIN_PLAYER_ID, world_x=sx, world_y=sy)
                player.world_x, player.world_y = sx, sy

        grid = await _player_grid(player, seed, db)
        content = render_grid(grid, player)
        view = GameView(guild_id, ADMIN_PLAYER_ID)
        await interaction.response.send_message(embed=discord.Embed(description=content), view=view)

        msg = await interaction.original_response()
        await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DwarfExplorer(bot))
