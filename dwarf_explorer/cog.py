from __future__ import annotations

import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks

from dwarf_explorer.config import SPAWN_X, SPAWN_Y, ADMIN_PLAYER_ID, ADMIN_DISCORD_ID, WORLD_SIZE, ITEM_EMOJI as _ITEM_EMOJI
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world, update_player_message,
    update_player_stats,
    update_player_village_state,
    is_world_initialized, mark_world_initialized,
    reset_world_seed,
    add_to_inventory,
    remove_from_inventory,
)
from dwarf_explorer.world.generator import load_viewport, init_world, find_walkable_spawn, find_walkable_near, find_village_spawn, find_nearest_village
from dwarf_explorer.world.villages import load_village_viewport
from dwarf_explorer.world.forest import get_city_forest_info, get_hermit_forest_info, load_forest_viewport
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


async def _ensure_admin_resources(db, player_id: int) -> None:
    """Top up admin gold to 999999, ensure 999 cooked fish, and give a canoe if missing."""
    await db.execute("UPDATE players SET gold=999999 WHERE user_id=?", (player_id,))
    existing = await db.fetch_one(
        "SELECT id, quantity FROM inventory WHERE user_id=? AND item_id='cooked_fish' ORDER BY slot_index LIMIT 1",
        (player_id,)
    )
    if not existing:
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity, slot_index) VALUES (?, 'cooked_fish', 999, 0)",
            (player_id,)
        )
    elif existing["quantity"] < 999:
        await db.execute(
            "UPDATE inventory SET quantity=999 WHERE id=?",
            (existing["id"],)
        )
    # Give admin a canoe for testing if they don't have one
    canoe_row = await db.fetch_one(
        "SELECT COUNT(*) as cnt FROM inventory WHERE user_id=? AND item_id='canoe'",
        (player_id,)
    )
    if not canoe_row or canoe_row["cnt"] == 0:
        from dwarf_explorer.ui.game_view import _add_canoe_to_inventory
        await _add_canoe_to_inventory(db, player_id)
    # Give admin maps for all forests
    forest_rows = await db.fetch_all("SELECT forest_id FROM forest_areas")
    for _fr in forest_rows:
        await db.execute(
            "INSERT OR IGNORE INTO player_map_collection(user_id, map_type, ref_id) VALUES(?,?,?)",
            (player_id, "forest", _fr["forest_id"]),
        )


class DwarfExplorer(commands.Cog):
    """Dwarf Fortress-inspired emoji grid exploration game."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._pregen_done = False  # guard: only pre-generate once per process

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(GameButton)
        self._hourly_map_regen.start()
        self._boss_eye_rotation.start()

    async def cog_unload(self) -> None:
        self._hourly_map_regen.cancel()
        self._boss_eye_rotation.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        from dwarf_explorer.config import apply_custom_emojis
        apply_custom_emojis(self.bot.emojis)
        # Pre-generate world maps once per process startup (not on every reconnect).
        # Delay 30 s so the bot is fully connected before doing CPU-heavy PIL work.
        if not self._pregen_done:
            self._pregen_done = True
            asyncio.ensure_future(self._pregen_maps_for_all_guilds())

    async def _pregen_maps_for_all_guilds(self) -> None:
        """Background task: warm the world-map image cache for every initialized guild.

        Runs sequentially with a pause between guilds to avoid saturating the
        thread pool and causing event-loop lag.
        """
        await asyncio.sleep(30)  # wait for the bot to be fully online first
        from dwarf_explorer.world.world_map import (
            generate_world_map, generate_ocean_map, generate_world_map_key,
            invalidate_map_cache,
        )
        for guild in self.bot.guilds:
            try:
                db = await get_database(guild.id)
                if not await is_world_initialized(db, guild.id):
                    continue
                seed = await get_or_create_world(db, guild.id)
                # Sequential (not fire-and-forget) so only one heavy PIL task at a time
                await generate_world_map(seed, db, guild.id, 0, 0)
                await generate_world_map_key(guild.id, seed)
                await generate_ocean_map(seed, guild.id, 0, 0)
                await asyncio.sleep(1)  # breathe between guilds
            except Exception:
                pass  # Non-fatal: map will generate on first /map call

    @tasks.loop(hours=1)
    async def _hourly_map_regen(self) -> None:
        """Hourly background task: invalidate and regenerate world-map image caches.

        This ensures that terrain changes (new structures, cleared bandit camps,
        player houses, etc.) appear on the map within one hour without needing
        a player to trigger /map first.
        """
        from dwarf_explorer.world.world_map import (
            generate_world_map, generate_ocean_map, generate_world_map_key,
            invalidate_map_cache, invalidate_ocean_map_cache,
        )
        for guild in self.bot.guilds:
            try:
                db = await get_database(guild.id)
                if not await is_world_initialized(db, guild.id):
                    continue
                seed = await get_or_create_world(db, guild.id)
                invalidate_map_cache(guild.id)
                invalidate_ocean_map_cache(guild.id)
                await generate_world_map(seed, db, guild.id, 0, 0)
                await generate_world_map_key(guild.id, seed)
                await generate_ocean_map(seed, guild.id, 0, 0)
                await asyncio.sleep(1)
            except Exception:
                pass

    @_hourly_map_regen.before_loop
    async def _before_hourly_regen(self) -> None:
        """Wait until the bot is ready and the initial pregen is done."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(3600)  # first run at T+1h (startup pregen covers T+0)

    @tasks.loop(seconds=1)
    async def _boss_eye_rotation(self) -> None:
        """Advance the Thornwarden's rotating eye every FQ_WARDEN_EYE_DURATION seconds.

        For each player currently in boss combat, this task checks whether the
        current eye's open window has expired.  If so it advances fq_boss_eye_idx
        to the next alive eye, resets the timestamp, and edits the player's
        Discord message so the new eye position appears in real time.
        """
        import time as _t_ber
        from dwarf_explorer.config import (
            FQ_WARDEN_EYE_CYCLE as _wec_ber,
            FQ_WARDEN_EYE_DURATION as _dur_ber,
        )
        from dwarf_explorer.ui.game_view import rebuild_boss_view as _rbv

        _now_ber = _t_ber.time()

        for guild in self.bot.guilds:
            try:
                db = await get_database(guild.id)
                rows = await db.fetch_all(
                    "SELECT user_id, fq_boss_eye_idx, fq_boss_eyes, "
                    "fq_boss_eye_opened_at, message_id, channel_id "
                    "FROM players WHERE in_fq_boss_combat=1"
                )
                for row in rows:
                    try:
                        uid        = row["user_id"]
                        opened_at  = float(row["fq_boss_eye_opened_at"] or 0.0)
                        elapsed    = _now_ber - opened_at

                        if elapsed < _dur_ber:
                            continue  # eye still in its open window — nothing to advance

                        # ── Advance to the next alive eye ──────────────────────
                        eyes_str = row["fq_boss_eyes"] or "1111"
                        cur_idx  = int(row["fq_boss_eye_idx"] or 0)
                        next_idx = cur_idx
                        for _ni in range(1, 5):
                            candidate = (cur_idx + _ni) % 4
                            if eyes_str[candidate] == "1":
                                next_idx = candidate
                                break

                        await db.execute(
                            "UPDATE players SET fq_boss_eye_idx=?, fq_boss_eye_opened_at=? "
                            "WHERE user_id=?",
                            (next_idx, _now_ber, uid),
                        )
                        await db.commit()

                        # ── Edit the player's Discord message ──────────────────
                        mid = row["message_id"]
                        cid = row["channel_id"]
                        if not (mid and cid):
                            continue
                        ch = self.bot.get_channel(cid)
                        if ch is None:
                            continue
                        result = await _rbv(guild.id, uid)
                        if result is None:
                            continue
                        embed, view = result
                        try:
                            await ch.get_partial_message(mid).edit(
                                embed=embed, content=None, view=view
                            )
                        except Exception:
                            pass  # message deleted or missing permissions
                    except Exception:
                        pass  # per-player errors are non-fatal
            except Exception:
                pass  # per-guild errors are non-fatal

    @_boss_eye_rotation.before_loop
    async def _before_boss_eye_rotation(self) -> None:
        await self.bot.wait_until_ready()

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
            # Defer immediately — DB + world-gen calls can exceed Discord's 3-second window
            await interaction.response.defer()
            # Ensure forest areas exist (idempotent — only runs once per world)
            from dwarf_explorer.world.forest import ensure_forests_placed
            await ensure_forests_placed(seed, db)
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
            await interaction.followup.send(embed=discord.Embed(description=content), view=view)

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

        if interaction.user.id != ADMIN_DISCORD_ID:
            await interaction.response.send_message(
                "Only the server admin can use this command.", ephemeral=True
            )
            return

        await interaction.response.defer()

        guild_id = interaction.guild.id

        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)
        player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)

        # Ensure admin always has max resources
        await _ensure_admin_resources(db, ADMIN_PLAYER_ID)
        player.gold = 999999

        sx, sy = await find_walkable_spawn(seed, db)

        # Clear every interior/state flag so the player always lands on the overworld
        await db.execute(
            """UPDATE players SET
                world_x=?, world_y=?,
                in_cave=0,  cave_id=NULL,  cave_x=0,  cave_y=0,
                in_village=0, village_id=NULL, village_x=0, village_y=0,
                in_house=0, house_id=NULL, house_x=0, house_y=0, house_vx=0, house_vy=0, house_type='house',
                in_forest=0, forest_id=NULL, forest_x=0, forest_y=0,
                forest_wx=0, forest_wy=0,
                in_tree_city=0, tc_forest_id=NULL, tc_floor=1, tc_x=0, tc_y=0,
                in_forest_quest=0, fq_area_id=NULL, fq_x=0, fq_y=0,
                in_hermit_hut=0, hermit_hut_forest_id=NULL, hermit_hut_floor=1, hermit_hut_x=0, hermit_hut_y=0,
                in_bandit_camp=0, bandit_camp_id=NULL, bc_x=0, bc_y=0, bandit_bribe_remaining=0,
                in_grove=0, grove_id=NULL, grove_x=0, grove_y=0, grove_forest_id=NULL,
                in_maze=0, maze_id=NULL, maze_x=0, maze_y=0,
                in_sky=0, sky_id=NULL, sky_x=0, sky_y=0,
                in_temple=0, temple_id=NULL, temple_x=0, temple_y=0,
                temple_wx=0, temple_wy=0,
                in_ocean=0, in_high_seas=0, ocean_x=0, ocean_y=0,
                in_ship=0,
                in_canoe=0,
                in_combat=0, combat_enemy_type=NULL, combat_enemy_hp=0
            WHERE user_id=?""",
            (sx, sy, ADMIN_PLAYER_ID),
        )
        player.world_x, player.world_y = sx, sy
        player.in_cave = player.in_village = player.in_house = False
        player.in_forest = False
        player.in_tree_city = False
        player.tc_forest_id = None
        player.tc_floor = 1
        player.in_forest_quest = False
        player.in_hermit_hut = False
        player.hermit_hut_forest_id = None
        player.hermit_hut_floor = 1
        player.in_bandit_camp = False
        player.in_grove = False
        player.in_maze = False
        player.in_sky = False
        player.in_temple = False
        player.in_ocean = player.in_canoe = player.in_combat = False

        grid = await load_viewport(sx, sy, seed, db)
        content = render_grid(grid, player)
        view = GameView(guild_id, ADMIN_PLAYER_ID)
        msg = await interaction.followup.send(embed=discord.Embed(description=content), view=view)
        await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)


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
            # Forest quest — child tables before parent to respect FK order
            "fq_puzzle_logs", "fq_ents", "forest_quest_tiles", "forest_quest_areas",
            # Forest world data — regenerated by init_world. Must be wiped too:
            # tile_overrides above is cleared, so any surviving forest rows become
            # un-enterable "ghosts" that pile up on every reset.
            "forest_tiles", "forest_entrances", "forest_areas",
            "maze_tiles", "maze_areas", "tree_city_tiles",
            "grove_tiles", "grove_areas", "hermit_hut_tiles",
            "player_forest_chest_loots", "player_forest_loots", "player_maze_loots",
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
        # Also wipe admin's main quests — they reference world-specific content that
        # no longer exists after a world reset (side quests are kept).
        try:
            await db.execute(
                "DELETE FROM player_quests WHERE user_id = ? AND is_main_quest = 1",
                (ADMIN_PLAYER_ID,)
            )
        except Exception:
            pass

        # ── 4. Generate new world ─────────────────────────────────────────────
        seed = await reset_world_seed(db)
        await init_world(seed, db)
        await mark_world_initialized(db, interaction.guild.id)

        # Invalidate and pre-generate both world maps in the background
        from dwarf_explorer.world.world_map import (
            invalidate_map_cache, invalidate_ocean_map_cache,
            generate_world_map, generate_ocean_map,
        )
        invalidate_map_cache(interaction.guild.id)
        invalidate_ocean_map_cache(interaction.guild.id)
        # Pre-generate base maps now so the first /map is instant
        asyncio.ensure_future(generate_world_map(seed, db, interaction.guild.id, 0, 0))
        asyncio.ensure_future(generate_ocean_map(seed, interaction.guild.id, 0, 0))

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
        await interaction.response.defer()
        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)

        player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)

        # Ensure admin always has max resources
        await _ensure_admin_resources(db, ADMIN_PLAYER_ID)
        player.gold = 999999

        # Relocate if standing on impassable terrain in the new world
        if not player.in_cave and not player.in_village and not player.in_house:
            sx, sy = await find_walkable_near(seed, db, player.world_x, player.world_y)
            if (sx, sy) != (player.world_x, player.world_y):
                await update_player_stats(db, ADMIN_PLAYER_ID, world_x=sx, world_y=sy)
                player.world_x, player.world_y = sx, sy

        grid = await _player_grid(player, seed, db)
        content = render_grid(grid, player)
        view = GameView(guild_id, ADMIN_PLAYER_ID)
        await interaction.followup.send(embed=discord.Embed(description=content), view=view)

        msg = await interaction.original_response()
        await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)


    @app_commands.command(name="harbor", description="Teleport to the nearest harbor (admin only).")
    async def harbor(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id != ADMIN_DISCORD_ID:
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)
        player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)

        # Ensure admin always has max resources
        await _ensure_admin_resources(db, ADMIN_PLAYER_ID)
        player.gold = 999999

        # Find all harbor tile overrides
        harbor_rows = await db.fetch_all(
            "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'harbor'",
        )
        if not harbor_rows:
            await interaction.response.send_message(
                "No harbors found in this world.", ephemeral=True
            )
            return

        # Find the nearest harbor to the player's current position
        px, py = player.world_x, player.world_y
        nearest = min(
            harbor_rows,
            key=lambda r: abs(r["world_x"] - px) + abs(r["world_y"] - py),
        )
        hx, hy = nearest["world_x"], nearest["world_y"]

        # Clear any in-cave/village/house/ocean/forest-quest state
        player.in_cave = False
        player.in_village = False
        player.in_house = False
        player.in_ocean = False
        player.in_high_seas = False
        player.in_island = False
        player.in_ship = False
        player.in_forest = False
        player.in_forest_quest = False
        player.in_fq_boss_combat = False
        player.world_x, player.world_y = hx, hy
        await update_player_stats(
            db, ADMIN_PLAYER_ID,
            world_x=hx, world_y=hy,
            in_cave=0, cave_id=None, cave_x=0, cave_y=0,
            in_village=0, village_id=None,
            in_house=0, house_id=None,
            in_ocean=0, in_high_seas=0, in_island=0, in_ship=0,
            in_forest=0, in_forest_quest=0, in_fq_boss_combat=0,
        )

        grid = await load_viewport(hx, hy, seed, db)
        content = render_grid(grid, player, f"⚓ Teleported to harbor at ({hx}, {hy}).")
        from dwarf_explorer.ui.game_view import GameView as _GV
        view = _GV(guild_id, ADMIN_PLAYER_ID)
        await interaction.response.send_message(embed=discord.Embed(description=content), view=view)

        msg = await interaction.original_response()
        await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)


    @app_commands.command(name="village", description="Teleport to the nearest village (admin only).")
    async def village(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id != ADMIN_DISCORD_ID:
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)
        player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)

        # Ensure admin always has max resources
        await _ensure_admin_resources(db, ADMIN_PLAYER_ID)
        player.gold = 999999

        nearest = await find_nearest_village(seed, db, player.world_x, player.world_y)
        if not nearest:
            await interaction.response.send_message(
                "No villages found in this world.", ephemeral=True
            )
            return

        vwx, vwy, vid, vex, vey = nearest

        # Clear any in-cave/house/ocean/sky state, place inside village
        player.in_cave = False
        player.in_village = True
        player.village_id = vid
        player.village_x, player.village_y = vex, vey
        player.village_wx, player.village_wy = vwx, vwy
        player.in_house = False
        player.in_ocean = False
        player.in_high_seas = False
        player.in_island = False
        player.in_ship = False
        await update_player_stats(
            db, ADMIN_PLAYER_ID,
            world_x=vwx, world_y=vwy,
            in_cave=0, cave_id=None, cave_x=0, cave_y=0,
            in_village=1, village_id=vid,
            in_house=0, house_id=None,
            in_ocean=0, in_high_seas=0, in_island=0, in_ship=0,
        )
        from dwarf_explorer.world.villages import load_village_viewport as _lvv
        await update_player_village_state(db, ADMIN_PLAYER_ID, True, vid, vex, vey, vwx, vwy)
        grid = await _lvv(vid, vex, vey, db)
        content = render_grid(grid, player, f"🏘️ Teleported to village at ({vwx}, {vwy}).")
        from dwarf_explorer.ui.game_view import GameView as _GV
        view = _GV(guild_id, ADMIN_PLAYER_ID)
        await interaction.response.send_message(embed=discord.Embed(description=content), view=view)

        msg = await interaction.original_response()
        await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)


    @app_commands.command(name="tp", description="Teleport admin character to overworld coordinates or a named location.")
    @app_commands.describe(
        x="World X coordinate (0–447)",
        y="World Y coordinate (0–447)",
        location="Named location: 'forestcity', 'hermit', 'warden', 'sokoban', or 'hall' (overrides x/y when provided)",
    )
    async def tp(
        self, interaction: discord.Interaction,
        x: int = 0, y: int = 0, location: str = "",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id != ADMIN_DISCORD_ID:
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer()

        guild_id = interaction.guild.id
        db = await get_database(guild_id)
        seed = await get_or_create_world(db, guild_id)
        await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)
        await _ensure_admin_resources(db, ADMIN_PLAYER_ID)

        loc = location.strip().lower()

        # ── Forest Quest — Thornwarden chamber entrance ───────────────────────────
        if loc == "warden":
            from dwarf_explorer.world.forest_quest import load_fq_viewport as _lfqv_tp
            from dwarf_explorer.config import FQ_BOSS_APPROACH_Y1 as _fq_approach_y1
            # Find (or create) the forest quest area
            _fq_row = await db.fetch_one(
                "SELECT fq_id FROM forest_quest_areas ORDER BY fq_id LIMIT 1"
            )
            if not _fq_row:
                await interaction.followup.send(
                    "⚠️ No forest quest area found — enter the Forest Quest zone at least once first.",
                    ephemeral=True,
                )
                return
            _fq_id_tp = _fq_row["fq_id"]
            # Place just outside the circular chamber (tip of the approach funnel)
            _tp_x, _tp_y = 10, _fq_approach_y1  # (10, 57)

            await update_player_stats(
                db, ADMIN_PLAYER_ID,
                in_cave=0, cave_id=None, cave_x=0, cave_y=0,
                in_village=0, village_id=None,
                in_house=0, house_id=None,
                in_ocean=0, in_high_seas=0, in_island=0, in_ship=0,
            )
            await db.execute(
                "UPDATE players SET "
                "in_temple=0, temple_id=NULL, temple_x=0, temple_y=0, "
                "in_sky=0, sky_id=NULL, sky_x=0, sky_y=0, "
                "in_forest=0, forest_id=NULL, forest_x=0, forest_y=0, "
                "in_tree_city=0, in_hermit_hut=0, hermit_hut_forest_id=NULL, "
                "in_bandit_camp=0, bandit_camp_id=NULL, bc_x=0, bc_y=0, bandit_bribe_remaining=0, "
                "in_grove=0, grove_id=NULL, grove_x=0, grove_y=0, grove_forest_id=NULL, "
                "in_maze=0, maze_id=NULL, maze_x=0, maze_y=0, "
                "in_forest_quest=1, fq_area_id=?, fq_x=?, fq_y=? "
                "WHERE user_id=?",
                (_fq_id_tp, _tp_x, _tp_y, ADMIN_PLAYER_ID)
            )
            await db.commit()

            player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)
            player.gold = 999999
            _fq_grid_tp = await _lfqv_tp(_fq_id_tp, _tp_x, _tp_y, db)
            content = render_grid(_fq_grid_tp, player,
                                  "🌿 Teleported to the Thornwarden chamber entrance.")
            view = GameView(guild_id, ADMIN_PLAYER_ID)
            msg = await interaction.followup.send(
                embed=discord.Embed(description=content), view=view
            )
            await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)
            return

        # ── Forest Quest — Sokoban puzzle ─────────────────────────────────────────
        if loc == "sokoban":
            from dwarf_explorer.world.forest_quest import load_fq_viewport as _lfqv_tp
            from dwarf_explorer.config import FQ_PUZZLE_Y0 as _fq_puz_y0
            _fq_row = await db.fetch_one(
                "SELECT fq_id FROM forest_quest_areas ORDER BY fq_id LIMIT 1"
            )
            if not _fq_row:
                await interaction.followup.send(
                    "⚠️ No forest quest area found — enter the Forest Quest zone at least once first.",
                    ephemeral=True,
                )
                return
            _fq_id_tp = _fq_row["fq_id"]
            _tp_x, _tp_y = 10, _fq_puz_y0   # (10, 18) — top of Sokoban sunken area

            await update_player_stats(
                db, ADMIN_PLAYER_ID,
                in_cave=0, cave_id=None, cave_x=0, cave_y=0,
                in_village=0, village_id=None,
                in_house=0, house_id=None,
                in_ocean=0, in_high_seas=0, in_island=0, in_ship=0,
            )
            await db.execute(
                "UPDATE players SET "
                "in_temple=0, temple_id=NULL, temple_x=0, temple_y=0, "
                "in_sky=0, sky_id=NULL, sky_x=0, sky_y=0, "
                "in_forest=0, forest_id=NULL, forest_x=0, forest_y=0, "
                "in_tree_city=0, in_hermit_hut=0, hermit_hut_forest_id=NULL, "
                "in_bandit_camp=0, bandit_camp_id=NULL, bc_x=0, bc_y=0, bandit_bribe_remaining=0, "
                "in_grove=0, grove_id=NULL, grove_x=0, grove_y=0, grove_forest_id=NULL, "
                "in_maze=0, maze_id=NULL, maze_x=0, maze_y=0, "
                "in_forest_quest=1, fq_area_id=?, fq_x=?, fq_y=? "
                "WHERE user_id=?",
                (_fq_id_tp, _tp_x, _tp_y, ADMIN_PLAYER_ID)
            )
            await db.commit()

            player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)
            player.gold = 999999
            _fq_grid_tp = await _lfqv_tp(_fq_id_tp, _tp_x, _tp_y, db)
            content = render_grid(_fq_grid_tp, player,
                                  "🧩 Teleported to the Sokoban puzzle.")
            view = GameView(guild_id, ADMIN_PLAYER_ID)
            msg = await interaction.followup.send(
                embed=discord.Embed(description=content), view=view
            )
            await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)
            return

        # ── Dwarven Hall ──────────────────────────────────────────────────────────
        if loc in ("hall", "dwarvenhall", "dwarven"):
            from dwarf_explorer.world.dwarven_hall import get_or_create_dwarven_hall as _get_hall
            from dwarf_explorer.world.villages import load_village_viewport as _lvv_hall
            from dwarf_explorer.database.repositories import update_player_village_state as _upvs

            # Find the cracked_mountain_wall or dwarven_entrance tile_override
            _hall_pos = await db.fetch_one(
                "SELECT world_x, world_y FROM tile_overrides "
                "WHERE tile_type IN ('cracked_mountain_wall', 'dwarven_entrance') LIMIT 1"
            )
            if not _hall_pos:
                await interaction.followup.send(
                    "⚠️ No dwarven hall entrance found in this world. "
                    "Use `/newworld` to regenerate, or the wall may not have been placed yet.",
                    ephemeral=True,
                )
                return

            _hwx, _hwy = _hall_pos["world_x"], _hall_pos["world_y"]
            _hall_id, _hex, _hey = await _get_hall(_hwx, _hwy, db)

            # If the entrance tile is still cracked_mountain_wall, bomb it open for the admin
            _entry_tile_row = await db.fetch_one(
                "SELECT tile_type FROM tile_overrides WHERE world_x=? AND world_y=?",
                (_hwx, _hwy),
            )
            if _entry_tile_row and _entry_tile_row["tile_type"] == "cracked_mountain_wall":
                await db.execute(
                    "UPDATE tile_overrides SET tile_type='dwarven_entrance' "
                    "WHERE world_x=? AND world_y=?",
                    (_hwx, _hwy),
                )
                await db.commit()

            # Place admin inside the hall
            player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)
            player.gold = 999999
            player.in_cave = player.in_house = False
            player.in_village = True
            player.village_id = _hall_id
            player.village_type = "dwarven_hall"
            player.village_x, player.village_y = _hex, _hey
            player.village_wx, player.village_wy = _hwx, _hwy
            player.in_ocean = player.in_high_seas = player.in_island = player.in_ship = False
            player.in_forest = player.in_grove = player.in_maze = player.in_tree_city = False
            player.in_sky = player.in_shipwreck = player.in_temple = player.in_canoe = False
            player.in_combat = player.in_hermit_hut = player.in_bandit_camp = False
            player.in_forest_quest = player.in_fq_boss_combat = False
            await db.execute(
                "UPDATE players SET "
                "in_cave=0, cave_id=NULL, cave_x=0, cave_y=0, "
                "in_village=1, village_id=?, village_x=?, village_y=?, "
                "village_wx=?, village_wy=?, village_type='dwarven_hall', "
                "in_house=0, house_id=NULL, in_ocean=0, in_high_seas=0, in_island=0, in_ship=0, "
                "in_forest=0, forest_id=NULL, in_grove=0, grove_id=NULL, "
                "in_maze=0, maze_id=NULL, in_tree_city=0, in_sky=0, sky_id=NULL, "
                "in_shipwreck=0, in_temple=0, in_canoe=0, in_combat=0, "
                "in_hermit_hut=0, in_bandit_camp=0, bandit_camp_id=NULL, "
                "in_forest_quest=0, fq_area_id=NULL, fq_x=0, fq_y=0, in_fq_boss_combat=0 "
                "WHERE user_id=?",
                (_hall_id, _hex, _hey, _hwx, _hwy, ADMIN_PLAYER_ID),
            )
            await db.commit()

            grid = await _lvv_hall(_hall_id, _hex, _hey, db, user_id=ADMIN_PLAYER_ID)
            content = render_grid(grid, player,
                "⚒️ Teleported to the **Ancient Dwarven Hall**.")
            view = GameView(guild_id, ADMIN_PLAYER_ID)
            msg = await interaction.followup.send(
                embed=discord.Embed(description=content), view=view
            )
            await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)
            return

        # ── Named forest locations ────────────────────────────────────────────────
        if loc in ("forestcity", "hermit"):
            if loc == "forestcity":
                info = await get_city_forest_info(db)
                if not info:
                    await interaction.response.send_message(
                        "⚠️ Forest city not yet generated — explore a dense forest first.",
                        ephemeral=True
                    )
                    return
                fid  = info["forest_id"]
                fx   = info["city_x"]
                fy   = info["city_y"]
                label = "🌲 Forest City"
            else:  # hermit
                info = await get_hermit_forest_info(db)
                if not info:
                    await interaction.response.send_message(
                        "⚠️ Hermit's forest not yet generated — explore more of the world first.",
                        ephemeral=True
                    )
                    return
                fid  = info["forest_id"]
                fx   = info.get("hermit_tx") or (info.get("city_x", 60))
                fy   = info.get("hermit_ty") or (info.get("city_y", 60))
                label = "🏚️ Hermit's House"

            # Clear all overworld/sub-location state and place in forest
            await update_player_stats(
                db, ADMIN_PLAYER_ID,
                in_cave=0, cave_id=None, cave_x=0, cave_y=0,
                in_village=0, village_id=None,
                in_house=0, house_id=None,
                in_ocean=0, in_high_seas=0, in_island=0, in_ship=0,
            )
            await db.execute(
                "UPDATE players SET "
                "in_temple=0, temple_id=NULL, temple_x=0, temple_y=0, "
                "in_sky=0, sky_id=NULL, sky_x=0, sky_y=0, "
                "in_forest=1, forest_id=?, forest_x=?, forest_y=?, "
                "in_tree_city=0, in_forest_quest=0, fq_area_id=NULL, fq_x=0, fq_y=0, "
                "in_hermit_hut=0, hermit_hut_forest_id=NULL, "
                "in_bandit_camp=0, bandit_camp_id=NULL, bc_x=0, bc_y=0, bandit_bribe_remaining=0, "
                "in_grove=0, grove_id=NULL, grove_x=0, grove_y=0, grove_forest_id=NULL, "
                "in_maze=0, maze_id=NULL, maze_x=0, maze_y=0 "
                "WHERE user_id=?",
                (fid, fx, fy, ADMIN_PLAYER_ID)
            )

            player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)
            player.gold = 999999
            grid = await load_forest_viewport(fid, fx, fy, db)
            content = render_grid(grid, player, f"🗺️ Teleported to {label}.")
            view = GameView(guild_id, ADMIN_PLAYER_ID)
            msg = await interaction.followup.send(
                embed=discord.Embed(description=content), view=view
            )
            await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)
            return

        # ── Overworld coordinate teleport ─────────────────────────────────────────
        # Clamp to world bounds
        x = max(0, min(WORLD_SIZE - 1, x))
        # Y=0 is displayed at the south (bottom); flip so user coords match the world map
        original_y = max(0, min(WORLD_SIZE - 1, y))   # user-facing y (before flip)
        y = WORLD_SIZE - 1 - original_y

        # Reset all sub-location state and place admin at overworld coordinates
        await update_player_stats(
            db, ADMIN_PLAYER_ID,
            world_x=x, world_y=y,
            in_cave=0, cave_id=None, cave_x=0, cave_y=0,
            in_village=0, village_id=None,
            in_house=0, house_id=None,
            in_ocean=0, in_high_seas=0, in_island=0, in_ship=0,
        )
        # Clear sky/temple/forest/bandit-camp/grove state directly
        await db.execute(
            "UPDATE players SET in_temple=0, temple_id=NULL, temple_x=0, temple_y=0, "
            "in_sky=0, sky_id=NULL, sky_x=0, sky_y=0, "
            "in_forest=0, forest_id=NULL, in_hermit_hut=0, in_tree_city=0, "
            "in_forest_quest=0, fq_area_id=NULL, fq_x=0, fq_y=0, "
            "in_bandit_camp=0, bandit_camp_id=NULL, bc_x=0, bc_y=0, bandit_bribe_remaining=0, "
            "in_grove=0, grove_id=NULL, grove_x=0, grove_y=0, grove_forest_id=NULL, "
            "in_maze=0, maze_id=NULL, maze_x=0, maze_y=0 "
            "WHERE user_id=?",
            (ADMIN_PLAYER_ID,)
        )

        player = await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)
        player.gold = 999999

        grid = await load_viewport(x, y, seed, db)
        content = render_grid(grid, player, f"🗺️ Teleported to ({x}, {original_y}).")
        view = GameView(guild_id, ADMIN_PLAYER_ID)
        msg = await interaction.followup.send(
            embed=discord.Embed(description=content), view=view
        )
        await update_player_message(db, ADMIN_PLAYER_ID, msg.id, interaction.channel_id)


    @app_commands.command(name="avatar", description="Set a custom emoji as your in-game character icon.")
    @app_commands.describe(emoji="The emoji to display as your character (e.g. 🐉, 🧙, 🤖)")
    async def avatar(self, interaction: discord.Interaction, emoji: str) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        import re as _re

        # Accept standard Unicode emoji or custom Discord emoji (<:name:id> / <a:name:id>)
        _UNICODE_RE = _re.compile(
            r"^[\U00000080-\U0010FFFF][\U0000FE00-\U0000FE0F]?$|"
            r"^[\U0001F000-\U0010FFFF][\U0001F3FB-\U0001F3FF]?$|"
            r"^[\U00002600-\U000027BF][\U0000FE0F]?$|"
            r"^[\U0001F300-\U0001FAFF][\U0001F3FB-\U0001F3FF]?$"
        )
        _CUSTOM_RE = _re.compile(r"^<a?:\w+:\d+>$")

        emoji = emoji.strip()
        if not (_UNICODE_RE.match(emoji) or _CUSTOM_RE.match(emoji)):
            await interaction.response.send_message(
                "❌ That doesn't look like a valid emoji. Please use a single standard emoji "
                "(e.g. `🐉`) or a custom server emoji. Your avatar was not changed.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        db = await get_database(guild_id)
        await update_player_stats(db, interaction.user.id, avatar_emoji=emoji)
        await interaction.response.send_message(
            f"✅ Avatar updated! You'll now appear as {emoji} in the viewport.",
            ephemeral=True,
        )


    @app_commands.command(name="give", description="Give the admin account an item (admin only).")
    @app_commands.describe(item_id="Item ID (e.g. ancient_sapling, axe, sword)", quantity="How many to give (default 1)")
    async def give(self, interaction: discord.Interaction, item_id: str, quantity: int = 1) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id != ADMIN_DISCORD_ID:
            await interaction.response.send_message(
                "Only the admin can use this command.", ephemeral=True
            )
            return
        if quantity < 1:
            await interaction.response.send_message(
                "Quantity must be at least 1.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        db = await get_database(guild_id)

        # Validate item ID — must exist in the item registry
        clean_id = item_id.strip()
        if clean_id not in _ITEM_EMOJI:
            # Helpful hint if the user used spaces instead of underscores
            suggested = clean_id.replace(" ", "_")
            hint = (
                f" Did you mean `{suggested}`?"
                if suggested != clean_id and suggested in _ITEM_EMOJI
                else ""
            )
            await interaction.response.send_message(
                f"❌ Unknown item `{clean_id}`.{hint}\n"
                f"Item IDs use underscores (e.g. `resonance_hammer`, `iron_sword`).",
                ephemeral=True,
            )
            return

        # Ensure admin player exists
        await get_or_create_player(db, ADMIN_PLAYER_ID, interaction.user.display_name)

        leftover = await add_to_inventory(db, ADMIN_PLAYER_ID, clean_id, quantity)

        if leftover == 0:
            await interaction.response.send_message(
                f"✅ Added **{quantity}x {clean_id}** to the admin inventory.", ephemeral=True
            )
        else:
            added = quantity - leftover
            await interaction.response.send_message(
                f"⚠️ Added **{added}x {clean_id}** to the admin inventory "
                f"({leftover} could not fit — inventory full).", ephemeral=True
            )


    @app_commands.command(name="take", description="Remove an item from the admin inventory (admin only).")
    @app_commands.describe(item_id="Item ID to remove (underscores, e.g. resonance_hammer)", quantity="How many to remove (default 1, -1 = all)")
    async def take(self, interaction: discord.Interaction, item_id: str, quantity: int = 1) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if interaction.user.id != ADMIN_DISCORD_ID:
            await interaction.response.send_message(
                "Only the admin can use this command.", ephemeral=True
            )
            return

        guild_id = interaction.guild.id
        db = await get_database(guild_id)

        clean_id = item_id.strip()

        # Special case: quantity -1 means remove all
        if quantity == -1:
            # Delete all rows of this item regardless of validity
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ?",
                (ADMIN_PLAYER_ID, clean_id),
            )
            await interaction.response.send_message(
                f"🗑️ Removed all `{clean_id}` from the admin inventory.", ephemeral=True
            )
            return

        if quantity < 1:
            await interaction.response.send_message(
                "Quantity must be at least 1 (or -1 to remove all).", ephemeral=True
            )
            return

        success = await remove_from_inventory(db, ADMIN_PLAYER_ID, clean_id, quantity)
        if success:
            await interaction.response.send_message(
                f"🗑️ Removed **{quantity}x {clean_id}** from the admin inventory.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Could not remove `{clean_id}` — not enough in inventory.", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DwarfExplorer(bot))
