from __future__ import annotations

import discord

from dwarf_explorer.config import DIRECTIONS
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world,
    update_player_position, update_player_message,
    update_player_cave_state,
    get_cave_entrance_exit,
)
from dwarf_explorer.world.generator import load_viewport, load_single_tile
from dwarf_explorer.world.caves import get_or_create_cave, load_cave_viewport, load_cave_single_tile
from dwarf_explorer.game.player import can_move
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

    if player.in_cave:
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
        # Check if standing on a cave entrance → exit to wilderness
        cave_tile = await load_cave_single_tile(player.cave_id, player.cave_x, player.cave_y, db)
        if cave_tile.terrain == "cave_entrance":
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
        else:
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, status_msg="Nothing to interact with here.")
    else:
        # Check if standing on a cave tile → enter cave
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

    if player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player)

    view = GameView(guild_id, user_id)
    await interaction.response.edit_message(content=content, view=view)
