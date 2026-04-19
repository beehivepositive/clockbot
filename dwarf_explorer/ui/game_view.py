from __future__ import annotations

import discord

from dwarf_explorer.config import DIRECTIONS, SHOP_CATALOG, EQUIP_BONUSES, ITEM_EQUIP_SLOTS
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world,
    update_player_position, update_player_message,
    update_player_cave_state,
    update_player_village_state,
    update_player_house_state,
    update_player_sprint,
    update_player_stats,
    get_cave_entrance_exit,
    equip_item, unequip_item,
    get_inventory,
    add_to_inventory,
    remove_from_inventory,
    get_bank_items,
    bank_deposit,
    bank_withdraw,
)
from dwarf_explorer.world.generator import load_viewport, load_single_tile
from dwarf_explorer.world.caves import get_or_create_cave, load_cave_viewport, load_cave_single_tile, open_chest
from dwarf_explorer.world.villages import (
    get_or_create_village, get_building_at,
    load_village_viewport, load_village_single_tile,
    load_building_viewport, load_building_single_tile,
)
from dwarf_explorer.game.player import Player, can_move, can_move_village, can_move_building
from dwarf_explorer.game.renderer import (
    render_grid, render_inventory, render_bank, render_shop,
)

# ── In-memory UI state (transient per user) ───────────────────────────────────
# {user_id: {"type": str, "selected": int, "bank_view": str}}
_ui_state: dict[int, dict] = {}


def _embed(content: str) -> discord.Embed:
    """Wrap game content in an embed to bypass Discord's 2000-char content limit.

    Discord embeds allow up to 4096 chars in description, vs 2000 for content.
    Custom emojis like <:dry_grass:123456789012345678> are ~31 chars each;
    a full 9×9 grid of them would be ~2600 chars — safely under 4096.
    """
    return discord.Embed(description=content)


def _custom_id(guild_id: int, user_id: int, action: str) -> str:
    return f"dex:{guild_id}:{user_id}:{action}"


class GameView(discord.ui.View):
    """Main game view.  Shows sprint button when boots are equipped."""

    def __init__(self, guild_id: int, user_id: int, boots_equipped: bool = False,
                 sprinting: bool = False):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self._build_buttons(boots_equipped, sprinting)

    def _build_buttons(self, boots_equipped: bool, sprinting: bool):
        sprint_label = "\U0001F97E"  # 🥾
        sprint_style = discord.ButtonStyle.success if sprinting else discord.ButtonStyle.secondary

        if boots_equipped:
            sprint_btn = discord.ui.Button(
                style=sprint_style,
                label=sprint_label,
                custom_id=_custom_id(self.guild_id, self.user_id, "sprint"),
                row=0,
            )
        else:
            sprint_btn = discord.ui.Button(
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
        for btn in [sprint_btn, up_btn, spacer2, interact_btn, map_btn,
                    left_btn, down_btn, right_btn, inventory_btn, help_btn]:
            self.add_item(btn)


class InventoryView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, equip_label: str = "⚔️ Equip"):
        super().__init__(timeout=None)
        for label, action in [
            ("◀", "inv_prev"),
            ("▶", "inv_next"),
            (equip_label, "inv_equip"),
            ("❌ Close", "inv_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, action),
                row=0,
            ))


class BankView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, view_mode: str = "player"):
        super().__init__(timeout=None)
        action = "bank_withdraw" if view_mode == "bank" else "bank_deposit"
        action_label = "⬆ Withdraw" if view_mode == "bank" else "⬇ Deposit"
        for label, act in [
            ("◀", "bank_prev"),
            ("▶", "bank_next"),
            (action_label, action),
            ("🔄 Switch", "bank_switch"),
            ("❌ Close", "bank_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))


class ShopView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        for label, action in [
            ("◀", "shop_prev"),
            ("▶", "shop_next"),
            ("💰 Buy", "shop_buy"),
            ("❌ Close", "shop_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, action),
                row=0,
            ))


# ── Inventory helpers ─────────────────────────────────────────────────────────

def _equipped_dict(player: Player) -> dict:
    d = {}
    if player.weapon: d["weapon"] = player.weapon
    if player.boots:  d["boots"]  = player.boots
    if player.light:  d["light"]  = player.light
    return d


def _equip_label(items: list[dict], selected: int, equipped: dict) -> str:
    """Return 'Unequip' if selected item is currently equipped, else 'Equip'."""
    if selected < len(items) and items[selected]["item_id"] in equipped.values():
        return "↩ Unequip"
    return "⚔️ Equip"


# ── Movement ──────────────────────────────────────────────────────────────────

def _game_view(guild_id: int, user_id: int, player: Player) -> GameView:
    return GameView(guild_id, user_id,
                    boots_equipped=(player.boots is not None),
                    sprinting=player.sprinting)


async def _move_steps(
    player: Player, direction: str, steps: int, seed: int, db,
    guild_id: int, user_id: int,
) -> tuple[str, discord.ui.View]:
    """Move player 1 or 2 tiles, returning (content, view)."""
    dx, dy = DIRECTIONS[direction]

    if player.in_house:
        for _ in range(steps):
            nx, ny = player.house_x + dx, player.house_y + dy
            target = await load_building_single_tile(player.house_id, nx, ny, db)
            if target.terrain == "b_door":
                # Auto-exit house on walking into door
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
                return render_grid(grid, player, "You step outside."), _game_view(guild_id, user_id, player)
            allowed, reason = can_move_building(target)
            if not allowed:
                grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player)
            player.house_x, player.house_y = nx, ny
            await update_player_house_state(
                db, user_id, True, player.house_id,
                nx, ny, player.house_vx, player.house_vy, player.house_type,
            )
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player)

    elif player.in_village:
        for _ in range(steps):
            nx, ny = player.village_x + dx, player.village_y + dy
            target = await load_village_single_tile(player.village_id, nx, ny, db)
            if target.terrain == "void":
                wx, wy = player.village_wx, player.village_wy
                player.in_village = False
                player.village_id = None
                player.world_x, player.world_y = wx, wy
                await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
                await update_player_position(db, user_id, wx, wy)
                grid = await load_viewport(wx, wy, seed, db)
                return render_grid(grid, player, "You leave the village."), _game_view(guild_id, user_id, player)
            allowed, reason = can_move_village(target)
            if not allowed:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player)
            player.village_x, player.village_y = nx, ny
            await update_player_village_state(
                db, user_id, True, player.village_id,
                nx, ny, player.village_wx, player.village_wy,
            )
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player)

    elif player.in_cave:
        for _ in range(steps):
            nx, ny = player.cave_x + dx, player.cave_y + dy
            target = await load_cave_single_tile(player.cave_id, nx, ny, db)
            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player)
            player.cave_x, player.cave_y = nx, ny
            await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player)

    else:
        for _ in range(steps):
            nx, ny = player.world_x + dx, player.world_y + dy
            target = await load_single_tile(nx, ny, seed, db)
            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_viewport(player.world_x, player.world_y, seed, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player)
            player.world_x, player.world_y = nx, ny
            await update_player_position(db, user_id, nx, ny)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player)


async def handle_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    steps = 2 if (player.sprinting and player.boots is not None) else 1
    content, view = await _move_steps(player, direction, steps, seed, db, guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Sprint toggle ─────────────────────────────────────────────────────────────

async def handle_sprint(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.boots is None:
        await interaction.response.send_message("You need hiking boots to sprint.", ephemeral=True)
        return

    player.sprinting = not player.sprinting
    await update_player_sprint(db, user_id, player.sprinting)

    status = "Sprint ON \U0001F3C3" if player.sprinting else "Sprint OFF"
    if player.in_house:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player, status)
    view = _game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Interact ──────────────────────────────────────────────────────────────────

async def handle_interact(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.in_house:
        htile = await load_building_single_tile(player.house_id, player.house_x, player.house_y, db)

        if htile.terrain == "b_door":
            vx, vy = player.house_vx, player.house_vy
            player.in_house = False
            await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
            player.village_x, player.village_y = vx, vy
            await update_player_village_state(
                db, user_id, True, player.village_id,
                vx, vy, player.village_wx, player.village_wy,
            )
            grid = await load_village_viewport(player.village_id, vx, vy, db)
            content = render_grid(grid, player, "You step outside.")

        elif htile.terrain == "b_bank_npc" and player.house_type == "bank":
            # Enter bank UI
            return await _open_bank(interaction, guild_id, user_id, player, db)

        elif htile.terrain == "b_shop_npc" and player.house_type == "shop":
            # Enter shop UI
            return await _open_shop(interaction, guild_id, user_id, player)

        elif htile.terrain in ("b_bed", "b_stove", "b_table", "b_bookshelf"):
            msgs = {
                "b_bed": "A cozy bed. You feel rested.",
                "b_stove": "A warm hearth. Something smells delicious.",
                "b_table": "A sturdy wooden table.",
                "b_bookshelf": "Rows of dusty books.",
            }
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, msgs.get(htile.terrain, "..."))

        elif htile.terrain == "b_altar" and player.house_type == "church":
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "You kneel before the altar. You feel at peace.")

        elif htile.terrain == "b_priest":
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "\"May the light guide your path, traveller.\"")

        elif htile.terrain == "b_safe":
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "A locked vault. Speak with the banker.")

        else:
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    elif player.in_village:
        vtile = await load_village_single_tile(player.village_id, player.village_x, player.village_y, db)

        if vtile.terrain in ("vil_house", "vil_church", "vil_bank", "vil_shop"):
            result = await get_building_at(player.village_id, player.village_x, player.village_y, db)
            if result:
                house_id, btype, hx, hy = result
                player.in_house = True
                player.house_id = house_id
                player.house_x = hx
                player.house_y = hy
                player.house_vx = player.village_x
                player.house_vy = player.village_y
                player.house_type = btype
                await update_player_house_state(
                    db, user_id, True, house_id, hx, hy,
                    player.village_x, player.village_y, btype,
                )
                labels = {"house": "house", "church": "church", "bank": "bank", "shop": "shop"}
                grid = await load_building_viewport(house_id, hx, hy, db)
                content = render_grid(grid, player, f"You enter the {labels.get(btype, 'building')}.")
            else:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
                content = render_grid(grid, player, "Nothing to interact with here.")

        elif vtile.terrain == "vil_well":
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
            content = render_grid(grid, player, "A stone well. The water is cool and clear.")

        else:
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    elif player.in_cave:
        cave_tile = await load_cave_single_tile(player.cave_id, player.cave_x, player.cave_y, db)

        if cave_tile.terrain == "cave_entrance":
            result = await get_cave_entrance_exit(db, player.cave_id, player.cave_x, player.cave_y)
            if result:
                wx, wy = result
                player.world_x, player.world_y = wx, wy
                player.in_cave = False
                player.cave_id = None
                await update_player_position(db, user_id, wx, wy)
                await update_player_cave_state(db, user_id, False, None, 0, 0)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "You exit the cave.")
            else:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                content = render_grid(grid, player, "Nothing to interact with here.")

        elif cave_tile.terrain == "cave_chest":
            loot = await open_chest(player.cave_id, player.cave_x, player.cave_y, db)
            player.gold += loot["gold"]
            player.xp += loot["xp"]
            await update_player_stats(db, user_id, gold=player.gold, xp=player.xp)
            msg = (f"You open the chest! Found {loot['gold']} gold, {loot['xp']} XP"
                   + (f", and a {loot['item']}!" if loot["item"] else "."))
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, msg)

        else:
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    else:
        tile = await load_single_tile(player.world_x, player.world_y, seed, db)
        if tile.structure == "cave":
            cave_id, ex, ey = await get_or_create_cave(seed, player.world_x, player.world_y, db)
            player.in_cave = True
            player.cave_id = cave_id
            player.cave_x, player.cave_y = ex, ey
            await update_player_cave_state(db, user_id, True, cave_id, ex, ey)
            grid = await load_cave_viewport(cave_id, ex, ey, db)
            content = render_grid(grid, player, "You enter the cave...")

        elif tile.structure == "village":
            vid, vx, vy = await get_or_create_village(seed, player.world_x, player.world_y, db)
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = vx, vy
            player.village_wx, player.village_wy = player.world_x, player.world_y
            await update_player_village_state(
                db, user_id, True, vid, vx, vy, player.world_x, player.world_y,
            )
            grid = await load_village_viewport(vid, vx, vy, db)
            content = render_grid(grid, player, "You enter the village.")

        else:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Inventory handlers ────────────────────────────────────────────────────────

async def handle_inventory(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    _ui_state[user_id] = {"type": "inventory", "selected": 0}
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    label = _equip_label(items, 0, equipped)
    content = render_inventory(items, 0, equipped, label)
    view = InventoryView(guild_id, user_id, label)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    new_sel = (state["selected"] + delta) % max(1, len(items))
    _ui_state[user_id] = {"type": "inventory", "selected": new_sel}
    equipped = _equipped_dict(player)
    label = _equip_label(items, new_sel, equipped)
    content = render_inventory(items, new_sel, equipped, label)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=InventoryView(guild_id, user_id, label))


async def handle_inv_equip(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Handles both equip and unequip based on whether the selected item is already equipped."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)

    if sel >= len(items):
        label = _equip_label(items, sel, equipped)
        content = render_inventory(items, sel, equipped, label) + "\n*(No item selected)*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=InventoryView(guild_id, user_id, label))
        return

    item_id = items[sel]["item_id"]

    # Unequip if already equipped
    if item_id in equipped.values():
        slot = next(s for s, v in equipped.items() if v == item_id)
        await unequip_item(db, user_id, slot)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        equipped = _equipped_dict(player)
        label = _equip_label(items, sel, equipped)
        content = render_inventory(items, sel, equipped, label) + f"\n*Unequipped {item_id.replace('_', ' ').title()}.*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=InventoryView(guild_id, user_id, label))
        return

    # Equip — look up slot from ITEM_EQUIP_SLOTS
    slot = ITEM_EQUIP_SLOTS.get(item_id)
    if not slot:
        label = _equip_label(items, sel, equipped)
        content = render_inventory(items, sel, equipped, label) + f"\n*{item_id.replace('_', ' ').title()} cannot be equipped.*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=InventoryView(guild_id, user_id, label))
        return

    await equip_item(db, user_id, slot, item_id)
    bonuses = EQUIP_BONUSES.get(item_id, {})
    if bonuses:
        await update_player_stats(db, user_id, **bonuses)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    label = _equip_label(items, sel, equipped)
    content = render_inventory(items, sel, equipped, label) + f"\n*Equipped {item_id.replace('_', ' ').title()}!*"
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=InventoryView(guild_id, user_id, label))


async def handle_inv_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    _ui_state.pop(user_id, None)
    if player.in_house:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player)
    view = _game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Shop handlers ─────────────────────────────────────────────────────────────

async def _open_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player: Player,
) -> None:
    _ui_state[user_id] = {"type": "shop", "selected": 0}
    content = render_shop(SHOP_CATALOG, 0, player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=ShopView(guild_id, user_id))


async def handle_shop_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    new_sel = (state["selected"] + delta) % len(SHOP_CATALOG)
    _ui_state[user_id] = {"type": "shop", "selected": new_sel}
    content = render_shop(SHOP_CATALOG, new_sel, player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=ShopView(guild_id, user_id))


async def handle_shop_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    sel = state.get("selected", 0)
    item = SHOP_CATALOG[sel]
    if player.gold < item["price"]:
        content = render_shop(SHOP_CATALOG, sel, player.gold) + f"\n*Not enough gold! Need {item['price']}.*"
        await interaction.response.edit_message(embed=_embed(content), content=None, view=ShopView(guild_id, user_id))
        return
    player.gold -= item["price"]
    await update_player_stats(db, user_id, gold=player.gold)
    await add_to_inventory(db, user_id, item["id"])
    content = render_shop(SHOP_CATALOG, sel, player.gold) + f"\n*Purchased {item['name']}!*"
    await interaction.response.edit_message(embed=_embed(content), content=None, view=ShopView(guild_id, user_id))


async def handle_shop_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Bank handlers ─────────────────────────────────────────────────────────────

async def _open_bank(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player: Player, db,
) -> None:
    _ui_state[user_id] = {"type": "bank", "selected": 0, "bank_view": "player"}
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    content = render_bank(player_items, bank_items, 0, "player", equipped)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=BankView(guild_id, user_id, "player"))


async def handle_bank_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    bv = state.get("bank_view", "player")
    source = await get_inventory(db, user_id) if bv == "player" else await get_bank_items(db, user_id)
    total = max(1, (10 if bv == "player" else 36))
    new_sel = (state["selected"] + delta) % total
    _ui_state[user_id] = {"type": "bank", "selected": new_sel, "bank_view": bv}
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    content = render_bank(player_items, bank_items, new_sel, bv, equipped)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=BankView(guild_id, user_id, bv))


async def handle_bank_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    new_view = "bank" if state.get("bank_view") == "player" else "player"
    _ui_state[user_id] = {"type": "bank", "selected": 0, "bank_view": new_view}
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    content = render_bank(player_items, bank_items, 0, new_view, equipped)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=BankView(guild_id, user_id, new_view))


async def handle_bank_deposit(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    sel = state.get("selected", 0)
    items = await get_inventory(db, user_id)
    if sel >= len(items):
        player_items = items
        bank_items = await get_bank_items(db, user_id)
        equipped = _equipped_dict(player)
        content = render_bank(player_items, bank_items, sel, "player", equipped) + "\n*(Empty slot)*"
        await interaction.response.edit_message(embed=_embed(content), content=None, view=BankView(guild_id, user_id, "player"))
        return
    item_id = items[sel]["item_id"]
    ok = await bank_deposit(db, user_id, item_id)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    new_sel = min(sel, max(0, len(player_items) - 1))
    _ui_state[user_id]["selected"] = new_sel
    suffix = f"\n*Deposited {item_id}.*" if ok else "\n*Deposit failed.*"
    content = render_bank(player_items, bank_items, new_sel, "player", equipped) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None, view=BankView(guild_id, user_id, "player"))


async def handle_bank_withdraw(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "bank"})
    sel = state.get("selected", 0)
    items = await get_bank_items(db, user_id)
    if sel >= len(items):
        player_items = await get_inventory(db, user_id)
        bank_items = items
        equipped = _equipped_dict(player)
        content = render_bank(player_items, bank_items, sel, "bank", equipped) + "\n*(Empty slot)*"
        await interaction.response.edit_message(embed=_embed(content), content=None, view=BankView(guild_id, user_id, "bank"))
        return
    item_id = items[sel]["item_id"]
    ok = await bank_withdraw(db, user_id, item_id)
    player_items = await get_inventory(db, user_id)
    bank_items_new = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    new_sel = min(sel, max(0, len(bank_items_new) - 1))
    _ui_state[user_id]["selected"] = new_sel
    suffix = f"\n*Withdrew {item_id}.*" if ok else "\n*Withdraw failed.*"
    content = render_bank(player_items, bank_items_new, new_sel, "bank", equipped) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None, view=BankView(guild_id, user_id, "bank"))


async def handle_bank_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Map / Help ────────────────────────────────────────────────────────────────

async def handle_map(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await interaction.response.defer(ephemeral=True)
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    from dwarf_explorer.world.world_map import generate_world_map
    buf = await generate_world_map(seed, db, player.world_x, player.world_y)
    file = discord.File(buf, filename="world_map.png")
    await interaction.followup.send(file=file, ephemeral=True)


async def handle_help(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    from dwarf_explorer.config import TERRAIN_EMOJI, STRUCTURE_EMOJI, ENTITY_EMOJI, ITEM_EMOJI
    lines = ["**Dwarf Explorer — Help**", "",
             "**Controls:**",
             "Arrow buttons = Move  |  🤚 Interact = Enter / examine / open",
             "🥾 = Toggle sprint (needs hiking boots)  |  🎒 Inventory  |  🗺️ Map", ""]
    lines.append("**Terrain:**")
    for name, emoji in TERRAIN_EMOJI.items():
        if name == "void": continue
        walkable = "\u2705" if name in WALKABLE_WILDERNESS else "\u274C"
        lines.append(f"{emoji} {name.replace('_',' ').title()} {walkable}")
    lines.append("")
    lines.append("**Structures:**")
    for name, emoji in STRUCTURE_EMOJI.items():
        lines.append(f"{emoji} {name.replace('_',' ').title()}")
    content = "\n".join(lines)
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        style=discord.ButtonStyle.primary, label="Back",
        emoji="\U0001F5FA\uFE0F",
        custom_id=f"dex:{guild_id}:{user_id}:help_back", row=0,
    ))
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


WALKABLE_WILDERNESS = {"sand", "plains", "grass", "forest", "hills", "snow", "path"}


async def handle_help_back(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if player.in_house:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player)
    view = _game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
