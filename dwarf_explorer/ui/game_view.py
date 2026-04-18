from __future__ import annotations

import discord

from dwarf_explorer.config import DIRECTIONS
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world,
    update_player_position, update_player_message,
    update_player_cave_state,
    update_player_village_state,
    update_player_house_state,
    get_cave_entrance_exit,
)
from dwarf_explorer.world.generator import load_viewport, load_single_tile
from dwarf_explorer.world.caves import get_or_create_cave, load_cave_viewport, load_cave_single_tile, open_chest
from dwarf_explorer.world.villages import (
    get_or_create_village, get_or_create_house,
    load_village_viewport, load_village_single_tile,
    load_house_viewport, load_house_single_tile,
)
from dwarf_explorer.game.player import can_move, can_move_village, can_move_house
from dwarf_explorer.game.renderer import render_grid


def _custom_id(guild_id: int, user_id: int, action: str) -> str:
    return f"dex:{guild_id}:{user_id}:{action}"


class GameView(discord.ui.View):
    """Main game view with movement and action buttons."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self._build_buttons()

    def _build_buttons(self):
        # Row 0: spacer, up, spacer, interact, map
        spacer1 = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(self.guild_id, self.user_id, "sp1"),
            row=0,
        )
        up_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="\u2B06\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "up"),
            row=0,
        )
        spacer2 = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="\u200b", disabled=True,
            custom_id=_custom_id(self.guild_id, self.user_id, "sp2"),
            row=0,
        )
        interact_btn = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Interact",
            emoji="\U0001F91A",
            custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
            row=0,
        )
        map_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Map",
            emoji="\U0001F5FA\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "map"),
            row=0,
        )

        # Row 1: left, down, right, inventory, help
        left_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="\u2B05\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "left"),
            row=1,
        )
        down_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="\u2B07\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "down"),
            row=1,
        )
        right_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji="\u27A1\uFE0F",
            custom_id=_custom_id(self.guild_id, self.user_id, "right"),
            row=1,
        )
        inventory_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Inventory",
            emoji="\U0001F392",
            custom_id=_custom_id(self.guild_id, self.user_id, "inventory"),
            row=1,
        )
        help_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Help",
            emoji="\u2753",
            custom_id=_custom_id(self.guild_id, self.user_id, "help"),
            row=1,
        )

        for btn in [spacer1, up_btn, spacer2, interact_btn, map_btn,
                     left_btn, down_btn, right_btn, inventory_btn, help_btn]:
            self.add_item(btn)


async def handle_move(interaction: discord.Interaction, guild_id: int, user_id: int, direction: str) -> None:
    """Process a movement button press."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    dx, dy = DIRECTIONS[direction]

    if player.in_house:
        # --- House movement ---
        nx, ny = player.house_x + dx, player.house_y + dy
        target_tile = await load_house_single_tile(player.house_id, nx, ny, db)

        if target_tile.terrain == "house_door":
            # Step through door → back to village at the door's village position
            vx, vy = player.house_vx, player.house_vy
            player.in_house = False
            player.house_id = None
            player.village_x = vx
            player.village_y = vy
            await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
            await update_player_village_state(
                db, user_id, True, player.village_id,
                vx, vy, player.village_wx, player.village_wy,
            )
            grid = await load_village_viewport(player.village_id, vx, vy, db)
            content = render_grid(grid, player, status_msg="You step outside.")
        else:
            allowed, reason = can_move_house(target_tile)
            if allowed:
                player.house_x = nx
                player.house_y = ny
                await update_player_house_state(
                    db, user_id, True, player.house_id, nx, ny,
                    player.house_vx, player.house_vy,
                )
                grid = await load_house_viewport(player.house_id, nx, ny, db)
                content = render_grid(grid, player)
            else:
                grid = await load_house_viewport(player.house_id, player.house_x, player.house_y, db)
                content = render_grid(grid, player, status_msg=reason)

    elif player.in_village:
        # --- Village movement ---
        nx, ny = player.village_x + dx, player.village_y + dy
        target_tile = await load_village_single_tile(player.village_id, nx, ny, db)

        if target_tile.terrain == "void":
            # Walked off the edge → exit to wilderness
            wx, wy = player.village_wx, player.village_wy
            player.in_village = False
            player.village_id = None
            player.world_x = wx
            player.world_y = wy
            await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
            await update_player_position(db, user_id, wx, wy)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, status_msg="You leave the village.")
        else:
            allowed, reason = can_move_village(target_tile)
            if allowed:
                player.village_x = nx
                player.village_y = ny
                await update_player_village_state(
                    db, user_id, True, player.village_id,
                    nx, ny, player.village_wx, player.village_wy,
                )
                grid = await load_village_viewport(player.village_id, nx, ny, db)
                content = render_grid(grid, player)
            else:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
                content = render_grid(grid, player, status_msg=reason)

    elif player.in_cave:
        # --- Cave movement ---
        nx, ny = player.cave_x + dx, player.cave_y + dy
        target_tile = await load_cave_single_tile(player.cave_id, nx, ny, db)
        allowed, reason = can_move(player, direction, target_tile)

        if allowed:
            player.cave_x = nx
            player.cave_y = ny
            await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)
            grid = await load_cave_viewport(player.cave_id, nx, ny, db)
            content = render_grid(grid, player)
        else:
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, status_msg=reason)

    else:
        # --- Wilderness movement ---
        nx, ny = player.world_x + dx, player.world_y + dy
        target_tile = await load_single_tile(nx, ny, seed, db)
        allowed, reason = can_move(player, direction, target_tile)

        if allowed:
            player.world_x = nx
            player.world_y = ny
            await update_player_position(db, user_id, nx, ny)
            grid = await load_viewport(nx, ny, seed, db)
            content = render_grid(grid, player)
        else:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, status_msg=reason)

    view = GameView(guild_id, user_id)
    await interaction.response.edit_message(content=content, view=view)


async def handle_interact(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    """Process the interact button — cave entry/exit and future interactions."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.in_cave:
        cave_tile = await load_cave_single_tile(player.cave_id, player.cave_x, player.cave_y, db)

        if cave_tile.terrain == "cave_entrance":
            # Exit the cave back to wilderness
            result = await get_cave_entrance_exit(db, player.cave_id, player.cave_x, player.cave_y)
            if result:
                wx, wy = result
                player.world_x = wx
                player.world_y = wy
                player.in_cave = False
                player.cave_id = None
                await update_player_position(db, user_id, wx, wy)
                await update_player_cave_state(db, user_id, False, None, 0, 0)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, status_msg="You exit the cave.")
            else:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                content = render_grid(grid, player, status_msg="Nothing to interact with here.")

        elif cave_tile.terrain == "cave_chest":
            # Open the chest and award loot
            from dwarf_explorer.database.repositories import update_player_stats
            loot = await open_chest(player.cave_id, player.cave_x, player.cave_y, db)
            new_gold = player.gold + loot["gold"]
            new_xp = player.xp + loot["xp"]
            await update_player_stats(db, user_id, gold=new_gold, xp=new_xp)
            player.gold = new_gold
            player.xp = new_xp
            if loot["item"]:
                msg = f"You open the chest! Found {loot['gold']} gold, {loot['xp']} XP, and a {loot['item']}!"
            else:
                msg = f"You open the chest! Found {loot['gold']} gold and {loot['xp']} XP."
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, status_msg=msg)

        else:
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, status_msg="Nothing to interact with here.")
    elif player.in_village:
        # --- Interacting inside a village ---
        vtile = await load_village_single_tile(player.village_id, player.village_x, player.village_y, db)
        if vtile.terrain == "vil_door":
            # Enter house
            result = await get_or_create_house(
                player.village_id, player.village_x, player.village_y, db
            )
            if result:
                house_id, hentry_x, hentry_y = result
                player.in_house = True
                player.house_id = house_id
                player.house_x = hentry_x
                player.house_y = hentry_y
                player.house_vx = player.village_x
                player.house_vy = player.village_y
                await update_player_house_state(
                    db, user_id, True, house_id,
                    hentry_x, hentry_y,
                    player.village_x, player.village_y,
                )
                grid = await load_house_viewport(house_id, hentry_x, hentry_y, db)
                content = render_grid(grid, player, status_msg="You enter the house.")
            else:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
                content = render_grid(grid, player, status_msg="Nothing to interact with here.")
        elif vtile.terrain == "vil_well":
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
            content = render_grid(grid, player, status_msg="A stone well. The water is cool and clear.")
        else:
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
            content = render_grid(grid, player, status_msg="Nothing to interact with here.")

    elif player.in_house:
        # --- Interacting inside a house ---
        htile = await load_house_single_tile(player.house_id, player.house_x, player.house_y, db)
        if htile.terrain == "house_door":
            # Exit house → village
            vx, vy = player.house_vx, player.house_vy
            player.in_house = False
            player.house_id = None
            player.village_x = vx
            player.village_y = vy
            await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
            await update_player_village_state(
                db, user_id, True, player.village_id,
                vx, vy, player.village_wx, player.village_wy,
            )
            grid = await load_village_viewport(player.village_id, vx, vy, db)
            content = render_grid(grid, player, status_msg="You step outside.")
        elif htile.terrain == "house_stove":
            grid = await load_house_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, status_msg="A warm stove. Something smells good.")
        elif htile.terrain == "house_bed":
            grid = await load_house_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, status_msg="A cozy bed. You feel rested.")
        elif htile.terrain == "house_table":
            grid = await load_house_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, status_msg="A sturdy wooden table.")
        else:
            grid = await load_house_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, status_msg="Nothing to interact with here.")

    else:
        # --- Wilderness interact ---
        tile = await load_single_tile(player.world_x, player.world_y, seed, db)
        if tile.structure == "cave":
            cave_id, entrance_x, entrance_y = await get_or_create_cave(
                seed, player.world_x, player.world_y, db
            )
            player.in_cave = True
            player.cave_id = cave_id
            player.cave_x = entrance_x
            player.cave_y = entrance_y
            await update_player_cave_state(db, user_id, True, cave_id, entrance_x, entrance_y)
            grid = await load_cave_viewport(cave_id, entrance_x, entrance_y, db)
            content = render_grid(grid, player, status_msg="You enter the cave...")
        elif tile.structure == "village":
            village_id, ventry_x, ventry_y = await get_or_create_village(
                seed, player.world_x, player.world_y, db
            )
            player.in_village = True
            player.village_id = village_id
            player.village_x = ventry_x
            player.village_y = ventry_y
            player.village_wx = player.world_x
            player.village_wy = player.world_y
            await update_player_village_state(
                db, user_id, True, village_id,
                ventry_x, ventry_y,
                player.world_x, player.world_y,
            )
            grid = await load_village_viewport(village_id, ventry_x, ventry_y, db)
            content = render_grid(grid, player, status_msg="You enter the village.")
        else:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, status_msg="Nothing to interact with here.")

    view = GameView(guild_id, user_id)
    await interaction.response.edit_message(content=content, view=view)


async def handle_map(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    """Generate and send a world map image as an ephemeral message."""
    await interaction.response.defer(ephemeral=True)

    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    from dwarf_explorer.world.world_map import generate_world_map
    buf = await generate_world_map(seed, db, player.world_x, player.world_y)
    file = discord.File(buf, filename="world_map.png")
    await interaction.followup.send(file=file, ephemeral=True)


async def handle_help(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    """Show help/legend screen."""
    from dwarf_explorer.config import TERRAIN_EMOJI, STRUCTURE_EMOJI, ENTITY_EMOJI, ITEM_EMOJI

    lines = ["**Dwarf Explorer - Help**", ""]
    lines.append("**Controls:**")
    lines.append("Arrow buttons = Move | Interact = Pick up / use / enter caves")
    lines.append("Inventory = View items | Map = View world map")
    lines.append("")
    lines.append("**Terrain:**")
    for name, emoji in TERRAIN_EMOJI.items():
        if name == "void":
            continue
        walkable = "\u2705" if name in ("sand", "plains", "grass", "forest", "hills", "snow", "path") else "\u274C"
        lines.append(f"{emoji} {name.replace('_', ' ').title()} {walkable}")
    lines.append("")
    lines.append("**Structures:**")
    for name, emoji in STRUCTURE_EMOJI.items():
        lines.append(f"{emoji} {name.replace('_', ' ').title()}")
    lines.append("")
    lines.append("**Items:**")
    for name, emoji in ITEM_EMOJI.items():
        lines.append(f"{emoji} {name.replace('_', ' ').title()}")

    content = "\n".join(lines)

    view = discord.ui.View(timeout=None)
    back_btn = discord.ui.Button(
        style=discord.ButtonStyle.primary,
        label="Back to Map",
        emoji="\U0001F5FA\uFE0F",
        custom_id=f"dex:{guild_id}:{user_id}:help_back",
        row=0,
    )
    view.add_item(back_btn)
    await interaction.response.edit_message(content=content, view=view)


async def handle_help_back(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    """Return from help to the map view."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.in_house:
        grid = await load_house_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player)

    view = GameView(guild_id, user_id)
    await interaction.response.edit_message(content=content, view=view)
