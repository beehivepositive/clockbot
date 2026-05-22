from __future__ import annotations

import asyncio
import re as _re
import random as _random
from datetime import datetime, timedelta

import discord

from dwarf_explorer.config import (
    ADMIN_PLAYER_ID,
    DIRECTIONS, SHOP_CATALOG, EQUIP_BONUSES, ITEM_EQUIP_SLOTS,
    TWO_HANDED_ITEMS, ITEM_SELL_PRICES, CAVE_ENEMY_TYPES, CAVE_CHEST_TYPES,
    CAVE_ENCOUNTER_RATES, CAVE_LEVEL_ENCOUNTER_RATES, LAVA_CAVE_ENCOUNTER_RATES, ENEMY_STATS, COMBAT_MOVES_DEFAULT,
    POUCH_SIZES, SURFACE_ENCOUNTER_MOBS, CANOE_PASSABLE, WORLD_SIZE, FOOD_HP_RESTORE,
    ITEM_EMOJI as _ITEM_EMOJI,
    CAVE_EMOJI, BUILDING_EMOJI, CRAFT_RECIPES,
    HOUSE_DECORATION_CATALOG, PLAYER_HOUSE_DECO_TILES, PH_CHEST_TYPES,
    OCEAN_SIZE, OCEAN_ENCOUNTER_RATES, OCEAN_WALKABLE, SHIP_WALKABLE,
    COIN_PURSE_CAPACITY, CONSUMABLE_ITEMS, SHRINE_SACRIFICES,
    FARM_ANIMALS, FARMER_SHOP, FARM_CROPS, TAVERN_MENU,
    MAX_CREW_SIZE, CREW_HIRE_COST, CREW_NAMES, CREW_TASKS,
    SHIPWRECK_ENTRY_X, SHIPWRECK_ENTRY_Y, SHIPWRECK_SIZE, BREATH_MAX, BREATH_PER_STEP,
    SPAWN_X, SPAWN_Y,
    WAYPOINTS,
    SKY_ENCOUNTER_RATES,
    TEMPLE_WALKABLE, TEMPLE_EMOJI, SKY_LORE,
    TC_WALKABLE,
)
from dwarf_explorer.world.ships import load_ship_viewport, get_door_target, HELM_SPAWN
from dwarf_explorer.world.sky import (
    get_or_create_sky_biome, load_sky_viewport, load_sky_single_tile,
)
from dwarf_explorer.world.temples import (
    get_or_create_outer_temple, get_or_create_main_temple,
    load_temple_viewport, load_temple_single_tile,
    fill_gear_slot, remove_gear_slot,
    is_outer_temple_solved, are_all_outer_temples_solved,
    get_main_temple_sky_id,
    build_machine_grid,
    TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y, OUTER_ENTRANCE_POS, MAIN_ENTRANCE_POS,
)
from dwarf_explorer.database.connection import get_database
from dwarf_explorer.database.repositories import (
    get_or_create_player, get_or_create_world,
    update_player_position, update_player_message,
    update_player_cave_state,
    update_player_village_state,
    update_player_house_state,
    update_player_sprint,
    update_player_stats,
    update_player_ocean_state,
    save_combat_state,
    clear_combat_state,
    update_player_ship_state, update_player_ship_hp,
    get_ship_personal_items, ship_personal_deposit, ship_personal_withdraw,
    get_ship_cargo_items, ship_cargo_deposit, ship_cargo_withdraw, ship_cargo_consume,
    update_player_island_state,
    is_island_looted, mark_island_looted,
    update_island_tile,
    get_island_type, get_or_create_island_cave,
    get_cave_entrance_exit,
    equip_item, unequip_item,
    get_inventory,
    add_to_inventory,
    get_inventory_slot_count,
    remove_from_inventory,
    swap_inventory_slots,
    create_drop_box,
    pickup_drop_box,
    create_cave_drop_box,
    pickup_cave_drop,
    get_bank_items,
    bank_deposit,
    bank_withdraw,
    set_tile_override,
    set_village_tile,
    get_or_create_chest,
    get_or_create_maze_chest,
    get_or_create_ph_chest,
    get_chest_items,
    add_to_chest,
    remove_from_chest,
    get_farm_last_watered,
    set_farm_watered,
    get_treasure_map,
    set_treasure_map,
    mark_treasure_found,
    get_nearby_players,
    get_all_overworld_players,
    get_player_quest_markers,
    get_player_ocean_quest_markers,
    get_ship_crew,
    hire_crew_member,
    fire_crew_member,
    set_crew_task,
    get_player_village_overrides,
    set_player_village_override,
    update_player_shipwreck_state,
    is_shipwreck_chest_looted,
    mark_shipwreck_chest_looted,
    update_player_sky_state,
    is_sky_chest_looted,
    mark_sky_chest_looted,
    update_player_temple_state,
    grant_warp_crystal,
    get_player_waypoints,
    unlock_waypoint,
    get_avatar_cache,
    store_avatar_cache,
)
from dwarf_explorer.game.combat import (
    build_arena_from_viewport,
    action_move, action_attack, action_flee, action_use_potion,
    resolve_enemy_turn, apply_victory, apply_death_reset,
    render_arena, ARENA_SIZE,
    resolve_echo_deposits, spawn_extra_enemies, promote_extra_enemy,
)
from dwarf_explorer.world.rift import (
    create_rift, get_rift_for_sundial,
    RIFT_SPAWN_X, RIFT_SPAWN_Y, RIFT_BOSS_Y,
    RIFT_BOSS_SPAWN_X, RIFT_BOSS_SPAWN_Y,
    RIFT_ENTRANCE_X, RIFT_ENTRANCE_Y,
)
from dwarf_explorer.world.generator import load_viewport, load_single_tile, find_nearest_village
from dwarf_explorer.world.ocean import load_ocean_viewport, load_ocean_single_tile
from dwarf_explorer.world.caves import get_or_create_cave, load_cave_viewport, load_cave_single_tile, populate_chest_loot
from dwarf_explorer.world.player_houses import (
    create_player_house, get_player_house_at, get_player_house_owner,
    delete_player_house, load_player_house_viewport, load_player_house_single_tile,
    set_player_house_tile, HOUSE_SPAWN_X, HOUSE_SPAWN_Y,
)
from dwarf_explorer.world.villages import (
    get_or_create_village, get_or_create_harbor_village, get_building_at,
    load_village_viewport, load_village_single_tile,
    load_building_viewport, load_building_single_tile,
    get_recruitable_npc_positions, is_npc_recruitable_for_player,
    get_replacement_npc_position,
)
from dwarf_explorer.game.player import Player, can_move, can_move_village, can_move_building, can_move_ship, can_move_shipwreck, can_move_grove
from dwarf_explorer.world.shipwrecks import load_shipwreck_viewport, get_tile_at as get_shipwreck_tile
from dwarf_explorer.game.renderer import (
    render_grid, render_inventory, render_bank, render_shop, render_chest,
    render_ship_room, render_ship_chest, render_island, _build_slot_map,
)

_CUSTOM_EMOJI_RE = _re.compile(r"^<a?:(\w+):(\d+)>$")


def _cursor_item(visible: list[dict], slot_pos: int) -> dict | None:
    """Return the inventory item whose slot_index == slot_pos (grid cell), or None.

    A 'canoe' item occupies two adjacent slots (N and N+1), so if there's no
    item at slot_pos but the previous slot holds a canoe, return that canoe.
    """
    item = next((it for it in visible if it["slot_index"] == slot_pos), None)
    if item is not None:
        return item
    prev = next((it for it in visible if it["slot_index"] == slot_pos - 1), None)
    if prev is not None and prev["item_id"] == "canoe":
        return prev
    return None


# ── Ancient 2×2 tree helpers ──────────────────────────────────────────────────
_ANCIENT_TREE_TILES: frozenset[str] = frozenset({
    "ancient_tree_top_left", "ancient_tree_top_right",
    "ancient_tree_bottom_left", "ancient_tree_bottom_right",
})


def _ancient_tree_root(tile_type: str, ax: int, ay: int) -> tuple[int, int]:
    """Given an ancient tree tile type at (ax, ay), return the root (bottom-left) coords."""
    if tile_type == "ancient_tree_top_left":
        return (ax, ay + 1)
    elif tile_type == "ancient_tree_top_right":
        return (ax - 1, ay + 1)
    elif tile_type == "ancient_tree_bottom_right":
        return (ax - 1, ay)
    else:  # ancient_tree_bottom_left
        return (ax, ay)


def _ancient_tree_positions(root_x: int, root_y: int) -> list[tuple[int, int, str]]:
    """Return all 4 (x, y, tile_type) positions for an ancient tree given its root."""
    return [
        (root_x,     root_y - 1, "ancient_tree_top_left"),
        (root_x + 1, root_y - 1, "ancient_tree_top_right"),
        (root_x,     root_y,     "ancient_tree_bottom_left"),
        (root_x + 1, root_y,     "ancient_tree_bottom_right"),
    ]


async def _count_inv(db, user_id: int, item_id: str) -> int:
    """Return total quantity of item_id in the player's inventory (0 if none)."""
    row = await db.fetch_one(
        "SELECT COALESCE(SUM(quantity), 0) AS n FROM inventory WHERE user_id=? AND item_id=?",
        (user_id, item_id),
    )
    return int(row["n"]) if row else 0


async def _player_has_canoe(db, user_id: int) -> bool:
    """Return True if the player has a canoe in inventory."""
    row = await db.fetch_one(
        "SELECT 1 FROM inventory WHERE user_id=? AND item_id='canoe' LIMIT 1",
        (user_id,),
    )
    return bool(row)


def _canoe_nav_adjust(slot_map: dict, current_sel: int, new_sel: int,
                       total: int, inv_cols: int, delta_col: int = 0) -> int:
    """Skip the cursor past canoe_left virtual cells so it always lands on
    canoe_right. When moving LEFT from canoe_right, skip past the canoe_left
    cell on the way out so it takes one button press, not two.

    Works on any slot_map that has been expanded by _build_slot_map (so canoes
    show as virtual canoe_left at slot N and canoe_right at slot N+1).
    """
    if total <= 0:
        return new_sel
    canoe_left_pos: set[int] = set()
    canoe_right_pos: set[int] = set()
    for ci in range(total - 1):
        l = slot_map.get(ci)
        r = slot_map.get(ci + 1)
        if (l and l.get("item_id") == "canoe_left"
                and r and r.get("item_id") == "canoe_right"
                and ci // inv_cols == (ci + 1) // inv_cols):
            canoe_left_pos.add(ci)
            canoe_right_pos.add(ci + 1)
    if delta_col == -1 and current_sel in canoe_right_pos:
        return (new_sel - 1) % max(1, total)
    if new_sel in canoe_left_pos:
        return (new_sel + 1) % max(1, total)
    return new_sel


def _canoe_cursor_adjust(visible: list[dict], sel: int, inv_cols: int) -> int:
    """If cursor lands on canoe_left, redirect it to canoe_right.

    The cursor always rests on the RIGHT half so its visual column matches
    the navigation column (prevents off-by-one confusion in the row above).
    """
    left = _cursor_item(visible, sel)
    if left is None or left["item_id"] != "canoe_left":
        return sel
    right = _cursor_item(visible, sel + 1)
    if right is None or right["item_id"] != "canoe_right":
        return sel
    if sel // inv_cols != (sel + 1) // inv_cols:
        return sel  # different rows — can't pair
    return sel + 1  # redirect to canoe_right


def _parse_emoji(s: str) -> discord.PartialEmoji | None:
    """Parse a custom emoji string '<:name:id>' into a PartialEmoji, or None for plain text."""
    m = _CUSTOM_EMOJI_RE.match(s)
    if m:
        return discord.PartialEmoji(name=m.group(1), id=int(m.group(2)))
    return None


# ── In-memory UI state (transient per user) ───────────────────────────────────
# {user_id: {"type": str, "selected": int, "bank_view": str, "mode": str}}
_ui_state: dict[int, dict] = {}

# ── In-memory puzzle state keyed by (guild_id, user_id) ──────────────────────
# {(gid, uid): {"puzzle": dict, "px": int, "py": int, "moves": int, "won": bool}}
_PUZZLE_STATES: dict[tuple[int, int], dict] = {}

# ── Viewport grid cache (persists across UI state resets) ─────────────────────
# {user_id: (cache_key_tuple, grid_list)}
# Keyed by player's location state; invalidated explicitly after tile changes.
_VP_CACHE: dict[int, tuple[tuple, list]] = {}

# Stores the tile type that was under a bomb before placement so it can be restored after blast.
# Key: (cave_id, local_x, local_y).  Values are consumed by _bomb_blast_cave.
_bomb_original_tiles: dict[tuple[int, int, int], str] = {}


def _vp_cache_key(player) -> tuple:
    """Return a tuple that uniquely identifies the viewport the player currently sees."""
    if player.in_ship:
        return ("ship", player.ship_room, player.ship_x, player.ship_y)
    if player.in_house:
        return ("house", player.house_id, player.house_x, player.house_y)
    if player.in_village:
        return ("village", player.village_id, player.village_x, player.village_y)
    if getattr(player, "in_hermit_hut", False):
        return ("hermit_hut", getattr(player, "hermit_hut_forest_id", 0), getattr(player, "hermit_hut_floor", 1),
                getattr(player, "hermit_hut_x", 0), getattr(player, "hermit_hut_y", 0))
    if player.in_cave:
        return ("cave", player.cave_id, player.cave_x, player.cave_y)
    if getattr(player, "in_shipwreck", False):
        return ("shipwreck", getattr(player, "shipwreck_wx", 0), getattr(player, "shipwreck_wy", 0),
                getattr(player, "shipwreck_x", 0), getattr(player, "shipwreck_y", 0))
    if getattr(player, "in_temple", False):
        return ("temple", getattr(player, "temple_id", 0), getattr(player, "temple_x", 0), getattr(player, "temple_y", 0))
    if getattr(player, "in_sky", False):
        return ("sky", getattr(player, "sky_id", 0), getattr(player, "sky_x", 0), getattr(player, "sky_y", 0))
    if getattr(player, "in_tree_city", False):
        return ("tree_city", player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y)
    if getattr(player, "in_maze", False):
        return ("maze", getattr(player, "maze_id", 0), getattr(player, "maze_x", 0), getattr(player, "maze_y", 0))
    if getattr(player, "in_grove", False):
        return ("grove", getattr(player, "grove_id", 0), getattr(player, "grove_x", 0), getattr(player, "grove_y", 0))
    if getattr(player, "in_forest", False):
        return ("forest", getattr(player, "forest_id", 0), getattr(player, "forest_x", 0), getattr(player, "forest_y", 0))
    if getattr(player, "in_bandit_camp", False):
        return ("bandit_camp", getattr(player, "bandit_camp_id", 0), getattr(player, "bc_x", 0), getattr(player, "bc_y", 0))
    if getattr(player, "in_forest_quest", False):
        return ("forest_quest", getattr(player, "fq_area_id", 0), getattr(player, "fq_x", 0), getattr(player, "fq_y", 0))
    return ("world", player.world_x, player.world_y)


def _invalidate_vp(uid: int) -> None:
    """Bust the viewport cache for uid — call after any tile change without movement."""
    _VP_CACHE.pop(uid, None)


async def _cached_grid(uid: int, player, seed: int, db) -> list:
    """Return the viewport grid from cache when position is unchanged; else load and cache it."""
    key = _vp_cache_key(player)
    cached = _VP_CACHE.get(uid)
    if cached and cached[0] == key:
        return cached[1]
    # Cache miss — load the right viewport for the player's current state
    if player.in_ship:
        grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
    elif player.in_house:
        grid = await _load_house_grid(player, db)
    elif player.in_village:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=uid)
    elif getattr(player, "in_hermit_hut", False):
        from dwarf_explorer.world.hermit_hut import load_hut_viewport as _lhv_cache, ensure_hermit_hut_built as _ehb_cache
        await _ehb_cache(player.hermit_hut_forest_id, db)
        grid = await _lhv_cache(player.hermit_hut_forest_id, player.hermit_hut_floor,
                                player.hermit_hut_x, player.hermit_hut_y, db)
    elif player.in_cave:
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
    elif getattr(player, "in_shipwreck", False):
        grid = load_shipwreck_viewport(
            player.shipwreck_wx, player.shipwreck_wy,
            player.shipwreck_x, player.shipwreck_y, seed
        )
    elif getattr(player, "in_temple", False):
        temple_row = await db.fetch_one(
            "SELECT temple_type FROM sky_temples WHERE id=?", (player.temple_id,)
        )
        is_main = temple_row and temple_row["temple_type"] == "main"
        grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db, is_main=bool(is_main))
    elif getattr(player, "in_tree_city", False):
        from dwarf_explorer.world.forest import load_tree_city_viewport as _ltcv_cache
        grid = await _ltcv_cache(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
    elif getattr(player, "in_maze", False):
        from dwarf_explorer.world.forest import load_maze_viewport as _lmv_cache
        grid = await _lmv_cache(player.maze_id, player.maze_x, player.maze_y, db)
    elif getattr(player, "in_grove", False):
        from dwarf_explorer.world.forest import load_grove_viewport as _lgv_cache
        grid = await _lgv_cache(player.grove_id, player.grove_x, player.grove_y, db)
    elif getattr(player, "in_forest", False):
        from dwarf_explorer.world.forest import load_forest_viewport as _lfv_cache
        grid = await _lfv_cache(player.forest_id, player.forest_x, player.forest_y, db)
    elif getattr(player, "in_bandit_camp", False):
        from dwarf_explorer.world.bandit_camp import load_camp_viewport as _lbcv_cache
        _bc_row_cache = await db.fetch_one(
            "SELECT world_x, world_y FROM bandit_camps WHERE id=?", (player.bandit_camp_id,)
        )
        if _bc_row_cache:
            grid = _lbcv_cache(player.bc_x, player.bc_y, int(_bc_row_cache["world_x"]), int(_bc_row_cache["world_y"]))
        else:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
    elif getattr(player, "in_forest_quest", False):
        from dwarf_explorer.world.forest_quest import load_fq_viewport as _lfqv_cache
        _bst_cache = ({"eyes": getattr(player, "fq_boss_eyes", "1111"),
                       "warn_eye": None, "open_eye": None}
                      if getattr(player, "in_fq_boss_combat", False) else None)
        _ac_cache = None
        if getattr(player, "fq_boss_aim_mode", False):
            _ac_cache = (player.fq_boss_aim_x, player.fq_boss_aim_y)
        grid = await _lfqv_cache(player.fq_area_id, player.fq_x, player.fq_y, db,
                                  boss_state=_bst_cache, aim_cursor=_ac_cache)
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
    _VP_CACHE[uid] = (key, grid)
    return grid


async def _build_player_view(
    guild_id: int, user_id: int, player, db, grid: list
) -> discord.ui.View:
    """Return the correct View subclass for the player's current location.

    This is the canonical helper to use whenever you need to reconstruct the
    game view after a non-movement action (sprint toggle, status messages,
    etc.). It covers every interior type so no location falls through to
    the wrong view.
    """
    if player.in_cave:
        return await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    if player.in_ship:
        return _ship_game_view(guild_id, user_id, player)
    if getattr(player, "in_bandit_camp", False):
        return _game_view(guild_id, user_id, player, grid=grid)
    has_canoe = await _player_has_canoe(db, user_id)
    if player.in_canoe:
        seed = await get_or_create_world(db, guild_id)
        dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
        return _game_view(guild_id, user_id, player, grid=grid, has_canoe=has_canoe, dock_dirs=dock_dirs)
    return _game_view(guild_id, user_id, player, grid=grid, has_canoe=has_canoe)


def _embed(content: str) -> discord.Embed:
    """Wrap game content in an embed to bypass Discord's 2000-char content limit."""
    return discord.Embed(description=content)


def _pickup_desc(results: list[tuple[str, int]]) -> str:
    """Build a human-readable pickup description."""
    parts = []
    for iid, qty in results:
        if iid == "canoe":
            parts.append(f"{qty}× canoe")
        else:
            parts.append(f"{qty}× {iid.replace('_', ' ')}")
    return ", ".join(parts)


def _custom_id(guild_id: int, user_id: int, action: str) -> str:
    return f"dex:{guild_id}:{user_id}:{action}"


class GameView(discord.ui.View):
    """Main game view.

    Layout:
      Row 0: [🗺️ Map] [🎒 Inv] [📋 Quests] [❓ Help] [Edit (owner only)]
      Row 1: [Sprint/sp] [⬆️] [Action]
      Row 2: [⬅️] [Center/Interact] [➡️]
      Row 3: [sp] [⬇️] [NPC/Quest context]

    center_label / center_enabled — on-tile contextual button (Enter cave, Chop, Harvest…)
    action_label / action_enabled — adjacent-tile contextual button (Forge, Smith, Fish…)
    edit_enabled                  — show ⚒️ Edit at row-0 col-4 (player house owners only)
    npc_label / npc_enabled       — bottom-right NPC/quest context button
    """

    def __init__(self, guild_id: int, user_id: int, boots_equipped: bool = False,
                 sprinting: bool = False, mine_dirs: frozenset[str] = frozenset(),
                 center_label: str = "", center_enabled: bool = False,
                 action_label: str = "", action_enabled: bool = False,
                 edit_enabled: bool = False,
                 npc_label: str = "", npc_enabled: bool = False,
                 embark_enabled: bool = False,
                 feed_enabled: bool = False,
                 plant_enabled: bool = False,
                 action2_label: str = "", action2_enabled: bool = False,
                 action2_id: str = "sp_action2",
                 interact2_label: str = "", interact2_enabled: bool = False,
                 h1_item: str | None = None,
                 h2_item: str | None = None,
                 h1_action_enabled: bool = False,
                 h2_action_enabled: bool = False,
                 canoe_dirs: frozenset[str] = frozenset(),
                 chop_dirs: frozenset[str] = frozenset()):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.canoe_dirs = canoe_dirs
        self.chop_dirs = chop_dirs
        self._build_buttons(boots_equipped, sprinting, mine_dirs,
                            center_label, center_enabled,
                            action_label, action_enabled,
                            edit_enabled, npc_label, npc_enabled,
                            embark_enabled, feed_enabled, plant_enabled,
                            action2_label, action2_enabled, action2_id,
                            interact2_label, interact2_enabled,
                            h1_item, h2_item, h1_action_enabled, h2_action_enabled)

    def _dir_btn(self, direction: str, arrow_emoji: str, row: int,
                 mine: bool) -> discord.ui.Button:
        if mine:
            return discord.ui.Button(
                style=discord.ButtonStyle.danger,
                emoji="\u26CF\uFE0F",  # ⛏️
                custom_id=_custom_id(self.guild_id, self.user_id, f"mine_{direction}"),
                row=row,
            )
        if direction in self.canoe_dirs:
            _ce = _ITEM_EMOJI.get("canoe") or "\U0001F6F6"
            _cp = _parse_emoji(_ce) if _ce else None
            _cd = _cp or (_ce.split()[0] if _ce else "\U0001F6F6")
            return discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji=_cd,
                custom_id=_custom_id(self.guild_id, self.user_id, f"embark_{direction}"),
                row=row,
            )
        if direction in self.chop_dirs:
            return discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="\U0001FA93",  # 🪓
                custom_id=_custom_id(self.guild_id, self.user_id, f"chop_{direction}"),
                row=row,
            )
        return discord.ui.Button(
            style=discord.ButtonStyle.primary,
            emoji=arrow_emoji,
            custom_id=_custom_id(self.guild_id, self.user_id, direction),
            row=row,
        )

    def _build_buttons(self, boots_equipped: bool, sprinting: bool,
                       mine_dirs: frozenset[str],
                       center_label: str, center_enabled: bool,
                       action_label: str, action_enabled: bool,
                       edit_enabled: bool,
                       npc_label: str = "", npc_enabled: bool = False,
                       embark_enabled: bool = False,
                       feed_enabled: bool = False,
                       plant_enabled: bool = False,
                       action2_label: str = "", action2_enabled: bool = False,
                       action2_id: str = "sp_action2",
                       interact2_label: str = "", interact2_enabled: bool = False,
                       h1_item: str | None = None,
                       h2_item: str | None = None,
                       h1_action_enabled: bool = False,
                       h2_action_enabled: bool = False,
                       ) -> None:
        sprint_style = discord.ButtonStyle.success if sprinting else discord.ButtonStyle.secondary

        # ── Row 0: Inventory | Nav | Quests | Edit ────────────────────────────
        inventory_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Inv", emoji="\U0001F392",
            custom_id=_custom_id(self.guild_id, self.user_id, "inventory"),
            row=0,
        )
        nav_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Nav", emoji="\U0001F9ED",
            custom_id=_custom_id(self.guild_id, self.user_id, "nav_open"),
            row=0,
        )
        quests_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Quests", emoji="\U0001F4CB",
            custom_id=_custom_id(self.guild_id, self.user_id, "quests"),
            row=0,
        )
        edit_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="⛏️ Edit",
            custom_id=_custom_id(self.guild_id, self.user_id, "action"),
            row=0,
        ) if edit_enabled else None

        # ── Row 1: Sprint (or spacer) | ⬆️ | Action ─────────────────────────
        if boots_equipped:
            sp1_btn = discord.ui.Button(
                style=sprint_style, label="\U0001F97E",
                custom_id=_custom_id(self.guild_id, self.user_id, "sprint"),
                row=1,
            )
        else:
            sp1_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp2"),
                row=1,
            )
        up_btn = self._dir_btn("up", "\u2B06\uFE0F", 1, "up" in mine_dirs)
        if action_enabled and action_label:
            _action_parsed = _parse_emoji(action_label)
            if _action_parsed:
                action_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    emoji=_action_parsed,
                    custom_id=_custom_id(self.guild_id, self.user_id, "action"),
                    row=1,
                )
            else:
                action_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label=action_label,
                    custom_id=_custom_id(self.guild_id, self.user_id, "action"),
                    row=1,
                )
        else:
            action_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="​", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp3"),
                row=1,
            )

        # ── H1: main hand tool action button (row 1 col 3) ──────────────────
        if h1_item:
            from dwarf_explorer.config import ITEM_EMOJI as _IE_h
            _h1_emoji_str = _IE_h.get(h1_item, "")
            _h1_parsed = _parse_emoji(_h1_emoji_str) if _h1_emoji_str else None
            _h1_display = _h1_parsed or (_h1_emoji_str.split()[0] if _h1_emoji_str else None)
            if h1_action_enabled:
                if _h1_display:
                    h1_btn = discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        emoji=_h1_display,
                        custom_id=_custom_id(self.guild_id, self.user_id, "use_hand1"),
                        row=1,
                    )
                else:
                    h1_btn = discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        label=h1_item[:8],
                        custom_id=_custom_id(self.guild_id, self.user_id, "use_hand1"),
                        row=1,
                    )
            else:
                if _h1_display:
                    h1_btn = discord.ui.Button(
                        style=discord.ButtonStyle.secondary,
                        emoji=_h1_display,
                        custom_id=_custom_id(self.guild_id, self.user_id, "hand1_show"),
                        disabled=True,
                        row=1,
                    )
                else:
                    h1_btn = discord.ui.Button(
                        style=discord.ButtonStyle.secondary,
                        label=h1_item[:8],
                        custom_id=_custom_id(self.guild_id, self.user_id, "hand1_show"),
                        disabled=True,
                        row=1,
                    )
        else:
            h1_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="✋",  # ✋ empty main hand
                disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "hand1_empty"),
                row=1,
            )

        # ── H2: off-hand action button (row 1 col 4) ─────────────────────────
        if h2_item:
            from dwarf_explorer.config import ITEM_EMOJI as _IE_h2
            _h2_emoji_str = _IE_h2.get(h2_item, "")
            _h2_parsed = _parse_emoji(_h2_emoji_str) if _h2_emoji_str else None
            _h2_display = _h2_parsed or (_h2_emoji_str.split()[0] if _h2_emoji_str else None)
            if h2_action_enabled:
                if _h2_display:
                    h2_btn = discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        emoji=_h2_display,
                        custom_id=_custom_id(self.guild_id, self.user_id, "use_hand2"),
                        row=1,
                    )
                else:
                    h2_btn = discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        label=h2_item[:8],
                        custom_id=_custom_id(self.guild_id, self.user_id, "use_hand2"),
                        row=1,
                    )
            else:
                if _h2_display:
                    h2_btn = discord.ui.Button(
                        style=discord.ButtonStyle.secondary,
                        emoji=_h2_display,
                        custom_id=_custom_id(self.guild_id, self.user_id, "hand2_show"),
                        disabled=True,
                        row=1,
                    )
                else:
                    h2_btn = discord.ui.Button(
                        style=discord.ButtonStyle.secondary,
                        label=h2_item[:8],
                        custom_id=_custom_id(self.guild_id, self.user_id, "hand2_show"),
                        disabled=True,
                        row=1,
                    )
        else:
            h2_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="🤚",  # 🤚 empty off hand
                disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "hand2_empty"),
                row=1,
            )

        # ── Row 2: ⬅️ | Center | ➡️ ──────────────────────────────────────────
        left_btn  = self._dir_btn("left",  "\u2B05\uFE0F", 2, "left"  in mine_dirs)
        right_btn = self._dir_btn("right", "\u27A1\uFE0F", 2, "right" in mine_dirs)
        if center_enabled and center_label:
            _center_emoji = _parse_emoji(center_label)
            if _center_emoji:
                center_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    emoji=_center_emoji,
                    custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                    row=2,
                )
            else:
                # Unicode emoji — use only the first word (the emoji character), no label text
                _emoji_char = center_label.split()[0]
                center_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    emoji=_emoji_char,
                    custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                    row=2,
                )
        else:
            center_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "interact"),
                row=2,
            )

        # ── Row 3: interact2/feed/plant/embark/spacer | ⬇️ | NPC ─────────────
        if interact2_enabled and interact2_label:
            _i2_emoji = _parse_emoji(interact2_label)
            if _i2_emoji:
                sp5_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    emoji=_i2_emoji,
                    custom_id=_custom_id(self.guild_id, self.user_id, "interact2"),
                    row=3,
                )
            else:
                _i2_emoji_char = interact2_label.split()[0]
                sp5_btn = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    emoji=_i2_emoji_char,
                    custom_id=_custom_id(self.guild_id, self.user_id, "interact2"),
                    row=3,
                )
        elif feed_enabled:
            sp5_btn = discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="🐟",
                custom_id=_custom_id(self.guild_id, self.user_id, "feed_cat"),
                row=3,
            )
        elif plant_enabled:
            sp5_btn = discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="🌱",
                custom_id=_custom_id(self.guild_id, self.user_id, "plant"),
                row=3,
            )
        elif embark_enabled:
            from dwarf_explorer.config import ITEM_EMOJI as _IE
            _canoe_emoji = _IE.get("canoe_whole") or _IE.get("canoe_left") or _IE.get("canoe") or "🛶"
            sp5_btn = discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji=_canoe_emoji,
                custom_id=_custom_id(self.guild_id, self.user_id, "embark"),
                row=3,
            )
        else:
            sp5_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="​", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp5"),
                row=3,
            )
        down_btn = self._dir_btn("down", "⬇️", 3, "down" in mine_dirs)
        if npc_enabled and npc_label:
            npc_btn = discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji=npc_label,
                custom_id=_custom_id(self.guild_id, self.user_id, "npc_talk"),
                row=3,
            )
        else:
            npc_btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="​", disabled=True,
                custom_id=_custom_id(self.guild_id, self.user_id, "sp_npc"),
                row=3,
            )

        row0 = [inventory_btn, nav_btn, quests_btn]
        if edit_btn is not None:
            row0.append(edit_btn)
        for btn in [
            *row0,                              # row 0
            sp1_btn, up_btn, action_btn, h1_btn, h2_btn,  # row 1
            left_btn, center_btn, right_btn,    # row 2
            sp5_btn, down_btn, npc_btn,         # row 3: [embark/feed/spacer][⬇][npc]
        ]:
            self.add_item(btn)


class InventoryView(discord.ui.View):
    """Inventory view with D-pad navigation, ±qty controls, drop/move/unequip actions.

    cursor_mode:
      "inventory"  — navigating item grid
      "equipped"   — navigating equipped slots row
      "gold"       — gold pseudo-slot (select only)
      "move"       — move mode: select destination slot then confirm/cancel

    Layout (5 rows × up to 5 buttons each):
      Row 0: [Select/Desel] [Move/Confirm] [Craft?/Cancel?] [UnselAll?] [spacer]
      Row 1: [−?] [⬆️] [+?] [spacer] [spacer]
      Row 2: [⬅️] [action/spacer] [➡️] [spacer] [spacer]
      Row 3: [spacer] [⬇️] [spacer] [🫳 Drop?] [spacer]
      Row 4: [❌ Close] [spacer] [spacer] [spacer] [spacer]
    """
    def __init__(
        self, guild_id: int, user_id: int,
        equip_label: str = "",
        equip_action: str = "inv_equip",
        selections: dict | None = None,
        cursor_item_id: str | None = None,
        sel_mode: str = "add",
        cursor_mode: str = "inventory",
        show_plus_minus: bool = False,
        show_drop: bool = False,
        move_mode: bool = False,
        move_qty: int = 1,
    ):
        super().__init__(timeout=None)
        selections = selections or {}
        cursor_selected = cursor_item_id is not None and cursor_item_id in selections
        has_cursor = cursor_item_id is not None and cursor_mode == "inventory"
        # ± buttons appear in move mode (always when moving) or select mode (when item is selected)
        show_pm_move = move_mode
        show_pm_sel  = show_plus_minus and not move_mode
        show_notepad = show_pm_move or show_pm_sel

        _sp = lambda act, r: self.add_item(discord.ui.Button(  # noqa
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(guild_id, user_id, act), row=r,
        ))

        # ── Row 0: Select/Move/Craft/UnselAll ─────────────────────────────────
        if move_mode:
            # Move mode: Confirm + Cancel only
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success, label="✔ Confirm",
                custom_id=_custom_id(guild_id, user_id, "inv_move_confirm"), row=0,
            ))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, label="✖ Cancel",
                custom_id=_custom_id(guild_id, user_id, "inv_move_cancel"), row=0,
            ))
        elif cursor_selected:
            # Cursor is ON a selected item — Unselect, Craft (if recipe matches), Unselect All
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="◎ Unselect",
                custom_id=_custom_id(guild_id, user_id, "inv_select"),
                row=0,
            ))
            if selections:
                sel_set = frozenset((k, v) for k, v in selections.items())
                if sel_set in CRAFT_RECIPES:
                    recipe = CRAFT_RECIPES[sel_set]
                    self.add_item(discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        label=recipe["label"],
                        custom_id=_custom_id(guild_id, user_id, "inv_craft"),
                        row=0,
                    ))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, label="◎ All",
                custom_id=_custom_id(guild_id, user_id, "inv_unselect_all"), row=0,
            ))
        else:
            # Normal mode — ⬤ Select, Move, Craft (if recipe matches), Unselect All (if any)
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⬤ Select",
                custom_id=_custom_id(guild_id, user_id, "inv_select"),
                disabled=cursor_item_id is None,
                row=0,
            ))
            # Move button — allow whenever cursor is on an inventory item (even with selections)
            can_move_item = cursor_mode == "inventory" and has_cursor
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="↕ Move",
                custom_id=_custom_id(guild_id, user_id, "inv_move"),
                disabled=not can_move_item,
                row=0,
            ))
            # Craft button (when recipe matches); Unselect All (when any selected)
            if selections:
                sel_set = frozenset((k, v) for k, v in selections.items())
                if sel_set in CRAFT_RECIPES:
                    recipe = CRAFT_RECIPES[sel_set]
                    self.add_item(discord.ui.Button(
                        style=discord.ButtonStyle.success,
                        label=recipe["label"],
                        custom_id=_custom_id(guild_id, user_id, "inv_craft"),
                        row=0,
                    ))
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.danger, label="◎ All",
                    custom_id=_custom_id(guild_id, user_id, "inv_unselect_all"), row=0,
                ))

        # ── Row 1: [−?] [⬆️] [+?] ─────────────────────────────────────────────
        if show_pm_move:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➖",
                custom_id=_custom_id(guild_id, user_id, "inv_move_qty_dec"), row=1,
            ))
        elif show_pm_sel:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➖",
                custom_id=_custom_id(guild_id, user_id, "inv_sel_dec"), row=1,
            ))
        else:
            _sp("inv_sp1", 1)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B06\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_up"), row=1,
        ))
        if show_pm_move:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➕",
                custom_id=_custom_id(guild_id, user_id, "inv_move_qty_inc"), row=1,
            ))
        elif show_pm_sel:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="➕",
                custom_id=_custom_id(guild_id, user_id, "inv_sel_inc"), row=1,
            ))
        else:
            _sp("inv_sp2", 1)

        # ── Row 2: ⬅️ | action | ➡️ ──────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B05\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_prev"), row=2,
        ))
        if equip_label and (has_cursor or cursor_mode == "equipped"):
            _emoji_char = equip_label.split()[0] if " " in equip_label else equip_label
            _parsed = _parse_emoji(_emoji_char)
            if _parsed:
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success, emoji=_parsed,
                    custom_id=_custom_id(guild_id, user_id, equip_action), row=2,
                ))
            else:
                # Unicode emoji — use emoji= for correct rendering
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.success, emoji=_emoji_char,
                    custom_id=_custom_id(guild_id, user_id, equip_action), row=2,
                ))
        else:
            _sp("inv_sp3", 2)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u27A1\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_next"), row=2,
        ))

        # ── Row 3: 📒?/spacer | ⬇️ | 🫳? ───────────────────────────────────
        if show_notepad:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, emoji="✏️",  # ✏️
                custom_id=_custom_id(guild_id, user_id, "inv_qty_modal"), row=3,
            ))
        else:
            _sp("inv_sp4", 3)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B07\uFE0F",
            custom_id=_custom_id(guild_id, user_id, "inv_down"), row=3,
        ))
        if show_drop and not move_mode:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger, emoji="\U0001FAF3",  # 🫳
                custom_id=_custom_id(guild_id, user_id, "inv_drop"), row=3,
            ))
        # (no trailing spacer — user requested it be removed)

        # ── Row 4: Close ──────────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(guild_id, user_id, "inv_close"), row=4,
        ))


class InvQtyModal(discord.ui.Modal, title="Enter Quantity"):
    """Modal that lets the player type a custom quantity for move or select operations."""

    qty_input: discord.ui.TextInput = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter a number…",
        min_length=1,
        max_length=6,
        required=True,
    )

    def __init__(self, guild_id: int, user_id: int, mode: str, max_qty: int):
        super().__init__()
        self.guild_id  = guild_id
        self.user_id   = user_id
        self.mode      = mode       # "move" or "select"
        self.max_qty   = max_qty
        self.qty_input.placeholder = f"1 – {max_qty}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()  # ACK immediately; edit_original_response updates the game view
        raw = self.qty_input.value.strip()
        try:
            entered = int(raw)
        except ValueError:
            await interaction.followup.send("*Not a valid number.*", ephemeral=True)
            return

        entered = max(1, min(entered, self.max_qty))
        db     = await get_database(self.guild_id)
        player = await get_or_create_player(db, self.user_id, interaction.user.display_name)
        state  = _ui_state.get(self.user_id, {"selected": 0})
        items  = await get_inventory(db, self.user_id)
        sel    = state.get("selected", 0)
        equipped   = _equipped_dict(player)
        inv_rows, inv_cols = _inv_capacity(player)

        if self.mode == "move":
            _ui_state[self.user_id] = {**state, "move_qty": entered}
            msg = f"\n*📋 Move quantity set to ×{entered}.*"
            content, view = _inv_view(
                self.guild_id, self.user_id, items, sel, equipped,
                inv_rows, inv_cols, _ui_state[self.user_id], msg, gold=player.gold,
            )
            await interaction.edit_original_response(embed=_embed(content), content=None, view=view)

        elif self.mode == "select":
            visible = [it for it in items if it["item_id"] != "gold_coin"]
            cursor_mode = state.get("cursor_mode", "inventory")
            selections  = dict(state.get("selections", {}))
            if cursor_mode == "gold":
                item_id = "gold_coin"
            else:
                ci = _cursor_item(visible, sel)
                item_id = ci["item_id"] if ci else None
            if item_id:
                selections[item_id] = entered
                _ui_state[self.user_id] = {**state, "selections": selections}
                msg = f"\n*📋 Quantity set to ×{entered}.*"
            else:
                msg = "\n*(No item at cursor)*"
            content, view = _inv_view(
                self.guild_id, self.user_id, items, sel, equipped,
                inv_rows, inv_cols, _ui_state[self.user_id], msg, gold=player.gold,
            )
            await interaction.edit_original_response(embed=_embed(content), content=None, view=view)

        elif self.mode == "bank":
            new_state = {**state, "qty": entered}
            _ui_state[self.user_id] = new_state
            bank_items = await get_bank_items(db, self.user_id)
            bv = state.get("bank_view", "player")
            content = _bank_render(new_state, items, bank_items, equipped, player.gold, inv_rows, inv_cols)
            content += f"\n*📋 Quantity set to ×{entered}.*"
            await interaction.edit_original_response(embed=_embed(content), content=None,
                                                    view=BankView(self.guild_id, self.user_id, bv))

        elif self.mode == "shop":
            new_state = {**state, "qty": entered}
            _ui_state[self.user_id] = new_state
            content = _shop_render(new_state, items, equipped, player.gold, inv_rows, inv_cols)
            content += f"\n*📋 Quantity set to ×{entered}.*"
            view_mode = state.get("shop_view", "shop")
            await interaction.edit_original_response(embed=_embed(content), content=None,
                                                    view=ShopView(self.guild_id, self.user_id, view_mode))


class InventoryItemView(discord.ui.View):
    """Sub-menu view shown when the player taps a selected-item button in InventoryView."""
    def __init__(self, guild_id: int, user_id: int, qty: int):
        super().__init__(timeout=None)
        for label, action, style, disabled in [
            ("+ More",   "inv_item_inc",   discord.ButtonStyle.secondary, False),
            ("− Less",   "inv_item_dec",   discord.ButtonStyle.secondary, qty <= 1),
            ("✖ Unselect", "inv_item_unsel", discord.ButtonStyle.danger,   False),
            ("↩ Back",   "inv_item_back",  discord.ButtonStyle.secondary, False),
        ]:
            self.add_item(discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(guild_id, user_id, action), row=0,
            ))


class BankView(discord.ui.View):
    """Bank UI — D-pad layout matching InventoryView but deposit/withdraw instead of equip."""
    def __init__(self, guild_id: int, user_id: int, view_mode: str = "player"):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        _sp = lambda act, r: self.add_item(discord.ui.Button(  # noqa
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, act), row=r,
        ))

        # ── Row 0: Switch (🏦 to go to vault / 🎒 to go to player inv) ───────
        switch_emoji = "\U0001F3E6" if view_mode == "player" else "\U0001F392"  # 🏦 / 🎒
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji=switch_emoji,
            custom_id=_custom_id(gid, uid, "bank_switch"), row=0,
        ))

        # ── Row 1: [−] [⬆] [+] ───────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➖",
            custom_id=_custom_id(gid, uid, "bank_qty_dec"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B06\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_up"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➕",
            custom_id=_custom_id(gid, uid, "bank_qty_inc"), row=1,
        ))

        # ── Row 2: ⬅ | 📤/📥 | ➡ ────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B05\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_prev"), row=2,
        ))
        action_emoji = "\U0001F4E4" if view_mode == "player" else "\U0001F4E5"  # 📤 / 📥
        action_id = "bank_deposit" if view_mode == "player" else "bank_withdraw"
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, emoji=action_emoji,
            custom_id=_custom_id(gid, uid, action_id), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u27A1\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_next"), row=2,
        ))

        # ── Row 3: 📋 | ⬇ ───────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji="\U0001F4CB",  # 📋
            custom_id=_custom_id(gid, uid, "bank_qty_modal"), row=3,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B07\uFE0F",
            custom_id=_custom_id(gid, uid, "bank_down"), row=3,
        ))

        # ── Row 4: Close ─────────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(gid, uid, "bank_close"), row=4,
        ))


class ShipChestView(discord.ui.View):
    """Reusable view for ship personal and cargo chests."""
    def __init__(self, guild_id: int, user_id: int,
                 chest_type: str = "personal",   # "personal" | "cargo"
                 view_mode: str = "player"):
        super().__init__(timeout=None)
        dep_act = f"ship_chest_{chest_type}_deposit"
        wth_act = f"ship_chest_{chest_type}_withdraw"
        action = wth_act if view_mode == "chest" else dep_act
        action_label = "⬆ Withdraw" if view_mode == "chest" else "⬇ Deposit"
        for label, act in [
            ("◀", f"ship_chest_{chest_type}_prev"),
            ("▶", f"ship_chest_{chest_type}_next"),
            (action_label, action),
            ("🔄 Switch", f"ship_chest_{chest_type}_switch"),
            ("🔙 Back", "ship_chest_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))


class ShipView(discord.ui.View):
    """Scene-based ship interior navigation view."""

    def __init__(self, guild_id: int, user_id: int,
                 room: str = "helm",
                 ship_hp: int = 100, ship_max_hp: int = 100):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.secondary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv | HP status (disabled label)
        self.add_item(_btn("Map",  "map",       0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory", 0, discord.ButtonStyle.secondary))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=f"🛳️ {ship_hp}/{ship_max_hp}", disabled=True,
            custom_id=_custom_id(gid, uid, "ship_hp_sp"), row=0,
        ))

        if room == "helm":
            # Row 1: → Captain's Quarters | → Lower Deck
            self.add_item(_btn("🛏️ Quarters",   "ship_room_quarters",   1, discord.ButtonStyle.primary))
            self.add_item(_btn("🪜 Lower Deck", "ship_room_lower_deck", 1, discord.ButtonStyle.primary))
            # Row 2: ⚓ Back to Ocean
            self.add_item(_btn("⚓ Back to Ocean", "ship_leave", 2, discord.ButtonStyle.danger))

        elif room == "quarters":
            # Row 1: Personal chest
            self.add_item(_btn("📦 Personal Chest", "ship_chest_personal_open", 1, discord.ButtonStyle.primary))
            # Row 2: Return to helm
            self.add_item(_btn("🔙 Return to Helm", "ship_room_helm", 2, discord.ButtonStyle.secondary))

        else:  # lower_deck
            # Row 1: Cargo chest | Crew
            self.add_item(_btn("📦 Cargo",   "ship_chest_cargo_open", 1, discord.ButtonStyle.primary))
            self.add_item(_btn("👥 Crew",    "ship_crew_view",        1, discord.ButtonStyle.primary))
            # Row 2: Return to helm
            self.add_item(_btn("🔙 Return to Helm", "ship_room_helm", 2, discord.ButtonStyle.secondary))


class PuzzleView(discord.ui.View):
    """Sliding-block puzzle UI for the village puzzle board.

    Layout (3-column D-pad):
      Row 0: [Moves: N]  [⬆️]  [Optimal: N]
      Row 1: [⬅️]        [🔄]  [➡️]
      Row 2: [❌ Close]  [⬇️]  [🎁 Claim]  ← claim only if reward available
    """

    def __init__(
        self, guild_id: int, user_id: int,
        moves: int, min_moves: int,
        claim_available: bool = False,
    ):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.primary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        def _sp(act, row):
            return discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="​", disabled=True,
                custom_id=_custom_id(gid, uid, act), row=row,
            )

        # Row 0: [spacer] | ⬆️ | [spacer]
        self.add_item(_sp("pzsp0a", 0))
        self.add_item(_btn("⬆️", "puzzle_up", 0))
        self.add_item(_sp("pzsp0b", 0))

        # Row 1: ⬅️ | 🔄 (emoji only) | ➡️
        self.add_item(_btn("⬅️", "puzzle_left", 1))
        self.add_item(_btn("🔄", "puzzle_reset", 1, style=discord.ButtonStyle.secondary))
        self.add_item(_btn("➡️", "puzzle_right", 1))

        # Row 2: ❌ Close | ⬇️ | 🎁 Claim (conditional)
        self.add_item(_btn("❌", "puzzle_close", 2, style=discord.ButtonStyle.danger))
        self.add_item(_btn("⬇️", "puzzle_down", 2))
        if claim_available:
            self.add_item(_btn("🎁", "puzzle_claim", 2, style=discord.ButtonStyle.success))


class IslandView(discord.ui.View):
    """Movement + interaction view for island interiors."""

    def __init__(self, guild_id: int, user_id: int,
                 can_loot: bool = False, on_dock: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.primary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv
        self.add_item(_btn("Map",  "map",       0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory", 0, discord.ButtonStyle.secondary))

        # Row 1: ↑  (+ interact if on dock/chest)
        self.add_item(_btn("⬆️", "island_up", 1))
        if can_loot:
            self.add_item(_btn("📦 Loot", "island_loot", 1, discord.ButtonStyle.success))
        elif on_dock:
            self.add_item(_btn("⛵ Leave", "island_leave", 1, discord.ButtonStyle.danger))

        # Row 2: ← | ↓ | →
        self.add_item(_btn("⬅️", "island_left",  2))
        self.add_item(_btn("⬇️", "island_down",  2))
        self.add_item(_btn("➡️", "island_right", 2))


class ShopView(discord.ui.View):
    """Shop UI — D-pad layout matching BankView but buy/sell instead of deposit/withdraw."""
    def __init__(self, guild_id: int, user_id: int, view_mode: str = "shop",
                 farmer_mode: bool = False, tavern_mode: bool = False,
                 tree_city_mode: bool = False, armory_mode: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        _sp = lambda act, r: self.add_item(discord.ui.Button(  # noqa
            style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
            custom_id=_custom_id(gid, uid, act), row=r,
        ))

        # ── Row 0: Switch (🛒 to go to shop / 🎒 to go to player inv)
        #           Disabled spacer in buy-only modes (no sell tab)
        if farmer_mode or tavern_mode or tree_city_mode or armory_mode:
            _sp("shop_switch", 0)
        else:
            switch_emoji = "\U0001F6D2" if view_mode == "player" else "\U0001F392"  # 🛒 / 🎒
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, emoji=switch_emoji,
                custom_id=_custom_id(gid, uid, "shop_switch"), row=0,
            ))

        # ── Row 1: [−] [⬆] [+] ───────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➖",
            custom_id=_custom_id(gid, uid, "shop_qty_dec"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B06\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_up"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="➕",
            custom_id=_custom_id(gid, uid, "shop_qty_inc"), row=1,
        ))

        # ── Row 2: ⬅ | 🪙 Buy / 🪙 Sell | ➡ ────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B05\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_prev"), row=2,
        ))
        action_id = "shop_buy" if view_mode == "shop" else "shop_sell"
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, emoji="\U0001FA99",  # 🪙
            custom_id=_custom_id(gid, uid, action_id), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u27A1\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_next"), row=2,
        ))

        # ── Row 3: 📋 | ⬇ ───────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji="\U0001F4CB",  # 📋
            custom_id=_custom_id(gid, uid, "shop_qty_modal"), row=3,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="\u2B07\uFE0F",
            custom_id=_custom_id(gid, uid, "shop_down"), row=3,
        ))

        # ── Row 4: Close ─────────────────────────────────────────────────────
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(gid, uid, "shop_close"), row=4,
        ))


class FstChestView(discord.ui.View):
    """Forest chest UI — simple single-view (chest contents only).

    Row 0: ◀  ▶  📤 Take  📦 Loot All  ❌ Close
    """

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        from dwarf_explorer.config import FOREST_EMOJI as _FE
        loot_emoji = _FE.get("fst_chest", "📦")
        for label, act in [
            ("◀", "fst_chest_prev"),
            ("▶", "fst_chest_next"),
            ("📤 Take", "fst_chest_take"),
            ("❌ Close", "fst_chest_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))
        # Loot All button: use emoji= for custom emoji support
        _loot_parsed = _parse_emoji(loot_emoji)
        if _loot_parsed:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji=_loot_parsed,
                label="Loot All",
                custom_id=_custom_id(guild_id, user_id, "fst_chest_lootall"),
                row=0,
            ))
        else:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=f"{loot_emoji} Loot All",
                custom_id=_custom_id(guild_id, user_id, "fst_chest_lootall"),
                row=0,
            ))


class ChestView(discord.ui.View):
    """Chest inventory view.

    Row 0 (always): ◀  ▶  Take/Give  🔄 Switch  ❌ Close
    Row 1 (chest only): 📦 Loot All
    """

    def __init__(self, guild_id: int, user_id: int, view_mode: str = "chest"):
        super().__init__(timeout=None)
        if view_mode == "chest":
            action_label, action_id = "📤 Take", "chest_take"
        else:
            action_label, action_id = "📥 Give", "chest_give"

        # Row 0: always present
        for label, act in [
            ("◀", "chest_prev"),
            ("▶", "chest_next"),
            (action_label, action_id),
            ("🔄 Switch", "chest_switch"),
            ("❌ Close", "chest_close"),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=_custom_id(guild_id, user_id, act),
                row=0,
            ))

        # Row 1: Loot All only on chest side
        if view_mode == "chest":
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="📦 Loot All",
                custom_id=_custom_id(guild_id, user_id, "chest_lootall"),
                row=1,
            ))


class GearMachineView(discord.ui.View):
    """Gear-puzzle machine UI — opened by stepping onto the gear_machine tile in an outer temple.

    2 slot buttons per row; close button on the row after the last slot row.
    slot_states: list of (required_gear, is_filled) in chain order (variable length per layout).
    """

    def __init__(
        self,
        guild_id: int,
        user_id: int,
        slot_states: list[tuple[str, bool]],
        inv_item_ids: set[str],
    ):
        super().__init__(timeout=None)
        for i, (required, is_filled) in enumerate(slot_states):
            gear_icon = "⚙️" if required == "small_gear" else "🔩"
            if is_filled:
                label = f"🔧 Slot {i + 1} — Remove"
                style = discord.ButtonStyle.danger
            else:
                has_gear = required in inv_item_ids
                label = f"{gear_icon} Slot {i + 1} — Place"
                style = discord.ButtonStyle.success if has_gear else discord.ButtonStyle.secondary

            self.add_item(discord.ui.Button(
                style=style,
                label=label,
                custom_id=_custom_id(guild_id, user_id, f"gear_slot_{i}"),
                row=i // 2,
            ))

        close_row = len(slot_states) // 2
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="❌ Close",
            custom_id=_custom_id(guild_id, user_id, "gear_machine_close"),
            row=close_row,
        ))


def _render_gear_machine(
    slot_states: list[tuple[str, bool]],
    solved: bool,
    player=None,
    temple_id: int = 0,
) -> str:
    """Render the gear machine as a plain 9×9 emoji grid (no player icon)."""
    from dwarf_explorer.config import TEMPLE_EMOJI
    machine_grid = build_machine_grid(slot_states, temple_id=temple_id)
    lines: list[str] = []
    for row in machine_grid:
        lines.append("".join(TEMPLE_EMOJI.get(cell.terrain, "⬛") for cell in row))
    filled = sum(1 for _, f in slot_states if f)
    total  = len(slot_states)
    lines.append("")
    if solved:
        lines.append("✨ All gears installed — temple active!")
    else:
        lines.append(f"⚙️ Gear Machine — {filled}/{total} gears installed")
    return "\n".join(lines)


class CombatView(discord.ui.View):
    """Arena combat view. Arrows attempt cobweb escape when trapped. Attack disabled while trapped."""

    def __init__(self, guild_id: int, user_id: int, trapped: bool = False,
                 moves_left: int = COMBAT_MOVES_DEFAULT, enemy_type: str = "",
                 has_bomb: bool = False, bomb_fuse: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        disabled = (moves_left <= 0)
        attack_disabled = disabled or trapped  # can't attack while trapped

        # Row 0: ↖ ↑ ↗ ⚔️ ⏭
        for emoji, action in [("↖", "c_upleft"), ("⬆️", "c_up"), ("↗", "c_upright"),
                               ("⚔️", "c_attack"), ("⏭", "c_endturn")]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary if emoji in ("↖","⬆️","↗")
                      else discord.ButtonStyle.danger if emoji == "⚔️"
                      else discord.ButtonStyle.secondary,
                label=emoji,
                disabled=attack_disabled if emoji == "⚔️" else disabled,
                custom_id=_custom_id(gid, uid, action), row=0,
            ))

        # Row 1: ← · → 🍗 🏃  (center is always a spacer — cobweb escape via arrows)
        for label, action, dis in [
            ("⬅️", "c_left",  disabled),
            ("·",  "c_wait",  True),
            ("➡️", "c_right", disabled),
            ("🍗", "c_eat",   disabled),
            ("🏃", "c_flee",  disabled),
        ]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label, disabled=dis,
                custom_id=_custom_id(gid, uid, action), row=1,
            ))

        # Row 2: ↙ ↓ ↘ [💰 Bribe if bandit] spacer
        for emoji, action in [("↙", "c_downleft"), ("⬇️", "c_down"), ("↘", "c_downright")]:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=emoji, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=2,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="​", disabled=True,
            custom_id=_custom_id(gid, uid, "csp0"), row=2,
        ))
        # Bomb button (row 2, slot 4): shows fuse countdown if active, else \ud83d\udca3 if player has bomb
        if bomb_fuse > 0:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label=f"\U0001F4A3{bomb_fuse}", disabled=True,
                custom_id=_custom_id(gid, uid, "csp_a"), row=2,
            ))
        elif has_bomb:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="\U0001F4A3", disabled=disabled,
                custom_id=_custom_id(gid, uid, "c_bomb"), row=2,
            ))
        else:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="\u200b", disabled=True,
                custom_id=_custom_id(gid, uid, "csp_a"), row=2,
            ))


class BribeModal(discord.ui.Modal, title="Bribe the Bandit"):
    """Modal for entering a bribe amount when fighting a bandit."""
    amount = discord.ui.TextInput(
        label="Coins to offer",
        placeholder="1 coin = 5%  |  50 coins = 100%  |  more = always 100%",
        min_length=1,
        max_length=6,
    )

    def __init__(self, guild_id: int, user_id: int):
        super().__init__()
        self._gid = guild_id
        self._uid = user_id

    async def on_submit(self, interaction: discord.Interaction):  # type: ignore[override]
        await handle_bribe_submit(interaction, self._gid, self._uid, self.amount.value)


class _BandtCampBribeModal(discord.ui.Modal, title="Bribe the Bandit"):
    """Modal for bribing a bandit inside a camp (dialogue context, not combat)."""
    amount = discord.ui.TextInput(
        label="Coins to offer",
        placeholder="10 coins = ~25%  |  50 coins = 100%  |  success = 10 moves safe",
        min_length=1,
        max_length=6,
    )

    def __init__(self, guild_id: int, user_id: int):
        super().__init__()
        self._gid = guild_id
        self._uid = user_id

    async def on_submit(self, interaction: discord.Interaction):  # type: ignore[override]
        await _handle_camp_bribe_submit(interaction, self._gid, self._uid, self.amount.value)


class ConsumablesView(discord.ui.View):
    """Combat food/consumables menu — one button per item the player has."""

    def __init__(self, guild_id: int, user_id: int,
                 available_items: list[tuple[str, int]]):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        for i, (item_id, qty) in enumerate(available_items[:8]):  # max 8 items + cancel
            info = CONSUMABLE_ITEMS.get(item_id, {})
            desc = info.get("desc", "")
            name = item_id.replace("_", " ").title()
            label = f"{name} ×{qty} ({desc})"[:80]
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=label,
                custom_id=_custom_id(gid, uid, f"consume_{item_id}"),
                row=i // 4,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="❌ Back",
            custom_id=_custom_id(gid, uid, "consume_cancel"),
            row=2,
        ))


# ── Canoe views ──────────────────────────────────────────────────────────────

class CanoeView(discord.ui.View):
    """8-directional canoe movement. Dock buttons replace arrows toward land."""

    def __init__(self, guild_id: int, user_id: int,
                 dock_dirs: frozenset[str] = frozenset(),
                 has_fishing_rod: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _spacer(key: str, row: int):
            return discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="​", disabled=True,
                custom_id=_custom_id(gid, uid, key), row=row,
            )

        def _dir_btn(direction: str, arrow: str, row: int):
            """Movement button — replaced with dock emoji if that direction leads to land."""
            if direction in dock_dirs:
                return discord.ui.Button(
                    style=discord.ButtonStyle.success, emoji="🏝️",
                    custom_id=_custom_id(gid, uid, f"canoe_dock_{direction}"), row=row,
                )
            return discord.ui.Button(
                style=discord.ButtonStyle.primary, label=arrow,
                custom_id=_custom_id(gid, uid, f"canoe_{direction}"), row=row,
            )

        # Row 0: Inv | Nav | Quests
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Inv", emoji="🎒",
            custom_id=_custom_id(gid, uid, "inventory"), row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Nav", emoji="🧭",
            custom_id=_custom_id(gid, uid, "nav_open"), row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="Quests", emoji="📋",
            custom_id=_custom_id(gid, uid, "quests"), row=0,
        ))
        self.add_item(_spacer("csp_r0a", 0))
        self.add_item(_spacer("csp_r0b", 0))

        # Row 1: ↖ ⬆️ ↗
        self.add_item(_dir_btn("upleft",  "↖", 1))
        self.add_item(_dir_btn("up",      "⬆️", 1))
        self.add_item(_dir_btn("upright", "↗", 1))

        # Row 2: ⬅️ [action] ➡️
        self.add_item(_dir_btn("left",  "⬅️", 2))
        if has_fishing_rod:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success, emoji="🎣",
                custom_id=_custom_id(gid, uid, "fish"), row=2,
            ))
        else:
            self.add_item(_spacer("csp_mid", 2))
        self.add_item(_dir_btn("right", "➡️", 2))

        # Row 3: ↙ ⬇️ ↘
        self.add_item(_dir_btn("downleft",  "↙", 3))
        self.add_item(_dir_btn("down",      "⬇️", 3))
        self.add_item(_dir_btn("downright", "↘", 3))

class CanoeDestView(discord.ui.View):
    """Shows up to 5 reachable landing destinations per page."""

    def __init__(self, guild_id: int, user_id: int, dests: list[tuple[int, int]],
                 page: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        per_page = 5
        total_pages = max(1, (len(dests) + per_page - 1) // per_page)
        page_dests = dests[page * per_page: page * per_page + per_page]

        # Row 0: up to 5 destination buttons
        for i, (dx, dy) in enumerate(page_dests):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=f"🏝️ ({dx},{dy})",
                custom_id=_custom_id(gid, uid, f"csail_{i}"),
                row=0,
            ))
        # Pad row 0 if fewer than 5 dests
        for i in range(len(page_dests), per_page):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
                custom_id=_custom_id(gid, uid, f"csp_{5 + i}"), row=0,
            ))

        # Row 1: prev / next / cancel
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="◀",
            disabled=(page == 0),
            custom_id=_custom_id(gid, uid, "csail_prev"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="▶",
            disabled=(page >= total_pages - 1),
            custom_id=_custom_id(gid, uid, "csail_next"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "csail_cancel"), row=1,
        ))


# ── Boat view (wilderness ocean navigation) ───────────────────────────────────

class BoatView(discord.ui.View):
    """8-directional boat navigation on the wilderness ocean.

    Row 0: 🗺️ Map | 🎒 Inv | ❓ Help | [⚓ Dock if adjacent harbor]
    Row 1: ↖ ↑ ↗
    Row 2: ← 🌊 →
    Row 3: ↙ ↓ ↘
    """

    def __init__(self, guild_id: int, user_id: int, dock_available: bool = False,
                 island_nearby: bool = False, has_fishing_rod: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.primary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv | Quests | Dock (if available)
        self.add_item(_btn("Map",  "map",        0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory",  0, discord.ButtonStyle.secondary))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Quests", emoji="📋",
            custom_id=_custom_id(gid, uid, "quests"),
            row=0,
        ))
        if dock_available:
            self.add_item(_btn("⚓ Dock", "ocean_dock", 0, discord.ButtonStyle.success))
        # Row 1: ↖ ↑ ↗
        self.add_item(_btn("↖", "ocean_upleft",   1))
        self.add_item(_btn("⬆️", "ocean_up",       1))
        self.add_item(_btn("↗", "ocean_upright",  1))
        # Row 2: ← 🪝 →
        self.add_item(_btn("⬅️", "ocean_left",   2))
        self.add_item(discord.ui.Button(
            emoji="🪝", custom_id=_custom_id(gid, uid, "boat_grapple"),
            style=discord.ButtonStyle.secondary, row=2,
        ))
        self.add_item(_btn("➡️", "ocean_right",  2))
        # Row 3: ↙ ↓ ↘
        self.add_item(_btn("↙", "ocean_downleft",  3))
        self.add_item(_btn("⬇️", "ocean_down",      3))
        self.add_item(_btn("↘", "ocean_downright", 3))
        # Row 4: Ship interior | optional Fishing | 🏝️ Island (if nearby)
        self.add_item(_btn("🚢 Ship", "ship_enter", 4, discord.ButtonStyle.secondary))
        if has_fishing_rod:
            self.add_item(_btn("🎣 Fish", "ocean_fish", 4, discord.ButtonStyle.secondary))
        if island_nearby:
            self.add_item(_btn("🏝️ Island", "island_dock_hs", 4, discord.ButtonStyle.success))


# ── High-seas view (separate 200×200 open-ocean grid) ────────────────────────

class OceanView(discord.ui.View):
    """8-directional high-seas navigation + Dock button."""

    def __init__(self, guild_id: int, user_id: int, dock_available: bool = False,
                 island_nearby: bool = False, has_fishing_rod: bool = False):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label: str, action: str, row: int,
                 style=discord.ButtonStyle.primary, disabled: bool = False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: Map | Inv | Quests | ⚓ Dock
        self.add_item(_btn("Map",  "map",       0, discord.ButtonStyle.secondary))
        self.add_item(_btn("Inv",  "inventory", 0, discord.ButtonStyle.secondary))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Quests", emoji="📋",
            custom_id=_custom_id(gid, uid, "quests"),
            row=0,
        ))
        if dock_available:
            self.add_item(_btn("⚓ Dock", "ocean_dock", 0, discord.ButtonStyle.success))

        # Row 1: ↖ ↑ ↗
        self.add_item(_btn("↖", "ocean_upleft",   1))
        self.add_item(_btn("⬆️", "ocean_up",       1))
        self.add_item(_btn("↗", "ocean_upright",  1))

        # Row 2: ← 🪝 →
        self.add_item(_btn("⬅️", "ocean_left",   2))
        self.add_item(discord.ui.Button(
            emoji="🪝", custom_id=_custom_id(gid, uid, "boat_grapple"),
            style=discord.ButtonStyle.secondary, row=2,
        ))
        self.add_item(_btn("➡️", "ocean_right",  2))

        # Row 3: ↙ ↓ ↘
        self.add_item(_btn("↙", "ocean_downleft",  3))
        self.add_item(_btn("⬇️", "ocean_down",      3))
        self.add_item(_btn("↘", "ocean_downright", 3))

        # Row 4: Ship interior | optional Fishing | 🏝️ Island (if nearby)
        self.add_item(_btn("🚢 Ship", "ship_enter", 4, discord.ButtonStyle.secondary))
        if has_fishing_rod:
            self.add_item(_btn("🎣 Fish", "ocean_fish", 4, discord.ButtonStyle.secondary))
        if island_nearby:
            self.add_item(_btn("🏝️ Island", "island_dock_hs", 4, discord.ButtonStyle.success))


class MerchantView(discord.ui.View):
    """Travelling merchant trade view."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        for label, act, style in [
            ("◀",       "merch_prev",  discord.ButtonStyle.secondary),
            ("▶",       "merch_next",  discord.ButtonStyle.secondary),
            ("🪙 Buy",  "merch_buy",   discord.ButtonStyle.success),
            ("📋 Quest", "merch_quest", discord.ButtonStyle.primary),
            ("👋 Leave", "merch_close", discord.ButtonStyle.danger),
        ]:
            self.add_item(discord.ui.Button(
                style=style, label=label,
                custom_id=_custom_id(guild_id, user_id, act), row=0,
            ))


class ShrineView(discord.ui.View):
    """Shrine enchantment menu — choose a gem imbuing sacrifice."""

    def __init__(self, guild_id: int, user_id: int,
                 inv_counts: dict[str, int] | None = None):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        inv_counts = inv_counts or {}
        keys = list(SHRINE_SACRIFICES.keys())
        for i, stype in enumerate(keys):
            data = SHRINE_SACRIFICES[stype]
            have = inv_counts.get(data["item"], 0)
            need = data["qty"]
            enough = have >= need
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary if enough else discord.ButtonStyle.secondary,
                label=f"{data['label']} ({have}/{need})"[:80],
                disabled=not enough,
                custom_id=_custom_id(gid, uid, f"shrine_{stype}"),
                row=i // 3,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "shrine_cancel"),
            row=2,
        ))


class ForgeView(discord.ui.View):
    """Forge interaction menu: smelt iron/gold ore into ingots. Ore-smelt
    buttons only appear when the player actually has that ore — anything
    further (weapons, nails, rings, etc.) is crafted at the anvil.
    """

    def __init__(self, guild_id: int, user_id: int,
                 iron_ore: int = 0, gold_ore: int = 0):
        super().__init__(timeout=None)
        if iron_ore > 0:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"🔥 Smelt {iron_ore} Iron Ore → {iron_ore} Ingot" + ("s" if iron_ore > 1 else ""),
                custom_id=_custom_id(guild_id, user_id, "forge_iron"), row=0,
            ))
        if gold_ore > 0:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"🟡 Smelt {gold_ore} Gold Ore → {gold_ore} Ingot" + ("s" if gold_ore > 1 else ""),
                custom_id=_custom_id(guild_id, user_id, "forge_gold"), row=0,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(guild_id, user_id, "forge_close"), row=1,
        ))


# ── Hearth recipe data ────────────────────────────────────────────────────────

_HEARTH_RECIPES: list[dict] = [
    # input_id, input_qty, output_id, output_qty, label, in_emoji, out_emoji
    {"input_id": "fish",   "input_qty": 1, "output_id": "cooked_fish",  "output_qty": 1,
     "label": "Cook Fish",   "in_emoji": "🐟", "out_emoji": "🍖"},
    {"input_id": "potato", "input_qty": 1, "output_id": "baked_potato", "output_qty": 1,
     "label": "Bake Potato", "in_emoji": "🥔", "out_emoji": "🍠"},
]


def _hearth_content(available: list[tuple[int, int, int]]) -> str:
    """Build the hearth recipe-list embed content.
    available: list of (recipe_idx, have_qty, max_batches)
    """
    lines = ["🔥 **Hearth** — What would you like to cook?", ""]
    for ridx, have_qty, max_batches in available:
        r = _HEARTH_RECIPES[ridx]
        lines.append(
            f"{r['in_emoji']} **{r['label']}** — "
            f"you have **{have_qty}** {r['input_id'].replace('_',' ')} "
            f"(can make up to **{max_batches}**)"
        )
    if not available:
        lines.append("*Bring fish or potatoes to cook here.*")
    return "\n".join(lines)


def _hearth_qty_content(recipe_idx: int, qty: int, max_qty: int) -> str:
    r = _HEARTH_RECIPES[recipe_idx]
    return (
        f"🔥 **Hearth — {r['label']}**\n\n"
        f"{r['in_emoji']} × {qty} → {r['out_emoji']} × {qty * r['output_qty']}\n"
        f"*(max: {max_qty})*"
    )


class HearthView(discord.ui.View):
    """Recipe-chooser menu for the hearth."""

    def __init__(self, guild_id: int, user_id: int,
                 available: list[tuple[int, int, int]]):
        """available: list of (recipe_idx, have_qty, max_batches)"""
        super().__init__(timeout=None)
        for row_i, (ridx, _have, _max) in enumerate(available):
            r = _HEARTH_RECIPES[ridx]
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"{r['in_emoji']}→{r['out_emoji']} {r['label']}",
                custom_id=_custom_id(guild_id, user_id, f"hearth_choose_{ridx}"),
                row=row_i,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="❌ Close",
            custom_id=_custom_id(guild_id, user_id, "hearth_close"),
            row=min(len(available), 3),
        ))


class HearthQtyView(discord.ui.View):
    """Quantity-selector for a specific hearth recipe."""

    def __init__(self, guild_id: int, user_id: int,
                 recipe_idx: int, qty: int, max_qty: int):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        rid = recipe_idx
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="−",
            custom_id=_custom_id(gid, uid, "hearth_qty_dec"), row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label=f"×{qty}",
            custom_id=_custom_id(gid, uid, "hearth_qty_display"),
            disabled=True, row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="+",
            custom_id=_custom_id(gid, uid, "hearth_qty_inc"), row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, label="All",
            custom_id=_custom_id(gid, uid, "hearth_qty_all"), row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="📝 Custom",
            custom_id=_custom_id(gid, uid, "hearth_qty_modal"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, label=f"🔥 Cook ×{qty}",
            custom_id=_custom_id(gid, uid, "hearth_qty_cook"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "hearth_close"), row=1,
        ))


class HearthQtyModal(discord.ui.Modal, title="How many to cook?"):
    """Modal for entering a custom hearth cook quantity."""

    qty_input: discord.ui.TextInput = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter a number…",
        min_length=1,
        max_length=4,
        required=True,
    )

    def __init__(self, guild_id: int, user_id: int, max_qty: int):
        super().__init__()
        self.guild_id = guild_id
        self.user_id  = user_id
        self.max_qty  = max_qty
        self.qty_input.placeholder = f"1 – {max_qty}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        raw = self.qty_input.value.strip()
        try:
            entered = max(1, min(int(raw), self.max_qty))
        except ValueError:
            await interaction.followup.send("*Not a valid number.*", ephemeral=True)
            return
        state = _ui_state.get(self.user_id, {})
        _ui_state[self.user_id] = {**state, "hearth_qty": entered}
        rid   = state.get("hearth_recipe", 0)
        content = _hearth_qty_content(rid, entered, self.max_qty)
        await interaction.edit_original_response(
            embed=_embed(content), content=None,
            view=HearthQtyView(self.guild_id, self.user_id, rid, entered, self.max_qty),
        )


# ── Anvil recipe data ─────────────────────────────────────────────────────────

_ANVIL_RECIPES: list[dict] = [
    # category, item_id, emoji, name, cost_item, cost_qty, base_item, stat, output_qty (default 1)
    {"category": "Iron Weapons",    "item_id": "dagger",           "emoji": "🗡️",  "name": "Dagger",           "cost_item": "iron_ingot",    "cost_qty": 1, "base_item": None,            "stat": "+8 atk"},
    {"category": "Iron Weapons",    "item_id": "sword",            "emoji": "⚔️",  "name": "Sword",            "cost_item": "iron_ingot",    "cost_qty": 2, "base_item": None,            "stat": "+12 atk"},
    {"category": "Iron Armor",      "item_id": "iron_helmet",      "emoji": "🪖",  "name": "Iron Helmet",      "cost_item": "iron_ingot",    "cost_qty": 2, "base_item": None,            "stat": "+3 def"},
    {"category": "Iron Armor",      "item_id": "iron_chestplate",  "emoji": "🛡️",  "name": "Iron Chestplate",  "cost_item": "iron_ingot",    "cost_qty": 4, "base_item": None,            "stat": "+5 def"},
    {"category": "Iron Armor",      "item_id": "iron_leggings",    "emoji": "👖",  "name": "Iron Leggings",    "cost_item": "iron_ingot",    "cost_qty": 3, "base_item": None,            "stat": "+4 def"},
    {"category": "Iron Armor",      "item_id": "iron_boots",       "emoji": "🥾",  "name": "Iron Boots",       "cost_item": "iron_ingot",    "cost_qty": 2, "base_item": None,            "stat": "+2 def"},
    {"category": "Iron Armor",      "item_id": "iron_shield",      "emoji": "🛡️",  "name": "Iron Shield",      "cost_item": "iron_ingot",    "cost_qty": 4, "base_item": None,            "stat": "+4 def"},
    {"category": "Iron Ammo",       "item_id": "cannonball",       "emoji": "💣",  "name": "Cannonball",       "cost_item": "iron_ingot",    "cost_qty": 2, "base_item": None,            "stat": "cannon ammo"},
    {"category": "Iron Misc",       "item_id": "nail",             "emoji": "📌",  "name": "Iron Nails",       "cost_item": "iron_ingot",    "cost_qty": 1, "base_item": None,            "stat": "ship repair", "output_qty": 9},
    {"category": "Wyvern Upgrades", "item_id": "wyvern_helmet",    "emoji": "🐉",  "name": "Wyvern Helmet",    "cost_item": "wyvern_scale",  "cost_qty": 2, "base_item": "iron_helmet",   "stat": "+5 def"},
    {"category": "Wyvern Upgrades", "item_id": "wyvern_chestplate","emoji": "🐉",  "name": "Wyvern Chestplate","cost_item": "wyvern_scale",  "cost_qty": 4, "base_item": "iron_chestplate","stat": "+8 def"},
    {"category": "Wyvern Upgrades", "item_id": "wyvern_leggings",  "emoji": "🐉",  "name": "Wyvern Leggings",  "cost_item": "wyvern_scale",  "cost_qty": 3, "base_item": "iron_leggings", "stat": "+6 def"},
    {"category": "Wyvern Upgrades", "item_id": "wyvern_shield",    "emoji": "🐉",  "name": "Wyvern Shield",    "cost_item": "wyvern_scale",  "cost_qty": 4, "base_item": "iron_shield",   "stat": "+7 def"},
    {"category": "Wyvern Upgrades", "item_id": "wyvern_boots",     "emoji": "🐉",  "name": "Wyvern Boots",     "cost_item": "wyvern_scale",  "cost_qty": 2, "base_item": "iron_boots",    "stat": "+3 def"},
    {"category": "Gold",            "item_id": "gold_ring",        "emoji": "💍",  "name": "Gold Ring",        "cost_item": "gold_ingot",    "cost_qty": 2, "base_item": None,            "stat": "combine w/ gem"},
]


_ANVIL_MATERIALS = ["iron_ingot", "wyvern_scale", "gold_ingot"]
_ANVIL_MATERIAL_LABELS = ["🧱 Iron", "🐉 Wyvern", "🟡 Gold"]


def _anvil_filtered_recipes(material_idx: int) -> list[dict]:
    """Return recipes for the active material."""
    cost_key = _ANVIL_MATERIALS[material_idx % len(_ANVIL_MATERIALS)]
    return [r for r in _ANVIL_RECIPES if r["cost_item"] == cost_key]


def _render_anvil(cursor_idx: int, inv_counts: dict[str, int], material_idx: int = 0) -> str:
    """Render the anvil as a shop-style grid embed.

    cursor_idx  : index within the filtered recipe list for the active material.
    inv_counts  : mapping of item_id -> quantity owned by the player.
    material_idx: 0 = Iron, 1 = Wyvern.
    """
    from dwarf_explorer.game.renderer import _item_emoji, _PAD, _EMPTY_SLOT
    COLS = 7

    iron_qty  = inv_counts.get("iron_ingot", 0)
    scale_qty = inv_counts.get("wyvern_scale", 0)
    gold_qty  = inv_counts.get("gold_ingot", 0)
    mat_label = _ANVIL_MATERIAL_LABELS[material_idx % len(_ANVIL_MATERIAL_LABELS)]

    lines: list[str] = [f"⚒️ **Anvil** — {mat_label}"]
    lines.append(f"🧱 Iron ingots: **{iron_qty}**  |  🐉 Wyvern scales: **{scale_qty}**  |  🟡 Gold ingots: **{gold_qty}**\n")

    recipes = _anvil_filtered_recipes(material_idx)

    # Build emoji grid (same style as render_shop)
    slots: list[str] = []
    for i, recipe in enumerate(recipes):
        emoji = _item_emoji(recipe["item_id"])
        if i == cursor_idx:
            slots.append(f"{emoji}◄︎{_PAD}")
        else:
            slots.append(f"{emoji}{_PAD * 2}")
    while len(slots) % COLS != 0:
        slots.append(f"{_EMPTY_SLOT}{_PAD * 2}")
    for row in range(max(1, len(slots) // COLS)):
        lines.append("".join(slots[row * COLS: row * COLS + COLS]))

    lines.append("")

    # Detail line for the cursor item
    if 0 <= cursor_idx < len(recipes):
        recipe = recipes[cursor_idx]
        have   = inv_counts.get(recipe["cost_item"], 0)
        if recipe["base_item"]:
            base_have = inv_counts.get(recipe["base_item"], 0)
            base_name = recipe["base_item"].replace("_", " ").title()
            cost_str  = f"{recipe['cost_qty']}× scale + {base_name}"
            avail_str = f"scales: {have}/{recipe['cost_qty']}, base: {'✓' if base_have >= 1 else '✗'}"
        else:
            cost_str  = f"{recipe['cost_qty']}× ingot{'s' if recipe['cost_qty'] > 1 else ''}"
            avail_str = f"have {have}/{recipe['cost_qty']}"
        lines.append(f"**{recipe['name']}** — {cost_str}  |  {recipe['stat']}")
        lines.append(f"*{avail_str}*")
    else:
        lines.append("*(No recipes available)*")

    return "\n".join(lines)


class AnvilView(discord.ui.View):
    """Anvil recipe menu — ShopView-style 5-row layout with material selector at bottom."""

    def __init__(self, guild_id: int, user_id: int, material_idx: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        _sp = lambda act, r: self.add_item(discord.ui.Button(  # noqa: E731
            style=discord.ButtonStyle.secondary, label="​", disabled=True,
            custom_id=_custom_id(gid, uid, act), row=r,
        ))

        # Row 0: spacer (no tab switch — crafting only)
        _sp("anvil_sp0a", 0)

        # Row 1: [spacer] [⬆️] [spacer]
        _sp("anvil_sp1a", 1)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="⬆️",
            custom_id=_custom_id(gid, uid, "anvil_up"), row=1,
        ))
        _sp("anvil_sp1b", 1)

        # Row 2: [⬅️ prev recipe] [🔨 Craft] [➡️ next recipe]
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="⬅️",
            custom_id=_custom_id(gid, uid, "anvil_prev"), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, emoji="🔨",
            custom_id=_custom_id(gid, uid, "anvil_craft"), row=2,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="➡️",
            custom_id=_custom_id(gid, uid, "anvil_next"), row=2,
        ))

        # Row 3: [spacer] [⬇️]
        _sp("anvil_sp3a", 3)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji="⬇️",
            custom_id=_custom_id(gid, uid, "anvil_down"), row=3,
        ))

        # Row 4: [⬅ mat] [disabled: current material label] [➡ mat] [spacer] [❌ Close]
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji="⬅️",
            custom_id=_custom_id(gid, uid, "anvil_mat_prev"), row=4,
        ))
        mat_label = _ANVIL_MATERIAL_LABELS[material_idx % len(_ANVIL_MATERIAL_LABELS)]
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label=mat_label, disabled=True,
            custom_id=_custom_id(gid, uid, "anvil_mat_lbl"), row=4,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji="➡️",
            custom_id=_custom_id(gid, uid, "anvil_mat_next"), row=4,
        ))
        _sp("anvil_sp4d", 4)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Close",
            custom_id=_custom_id(gid, uid, "anvil_close"), row=4,
        ))


class PlayerHouseEditView(discord.ui.View):
    """Edit mode for player-built houses: navigate + add decoration + remove + delete + close."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _sp(tag: str) -> discord.ui.Button:
            return discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
                custom_id=_custom_id(gid, uid, tag),
            )

        # Row 0: [spacer] [⬆️] [spacer] [➕ Add] [🗑 Delete]
        sp1 = _sp("hesp1"); sp1.row = 0
        up_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="⬆️",
                                   custom_id=_custom_id(gid, uid, "hedit_up"), row=0)
        sp2 = _sp("hesp2"); sp2.row = 0
        add_btn = discord.ui.Button(style=discord.ButtonStyle.success, label="➕ Add",
                                    custom_id=_custom_id(gid, uid, "hedit_add"), row=0)
        del_btn = discord.ui.Button(style=discord.ButtonStyle.danger, label="🗑 Delete House",
                                    custom_id=_custom_id(gid, uid, "hedit_delete"), row=0)

        # Row 1: [⬅️] [✖ Remove] [➡️] [❌ Close]
        left_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="⬅️",
                                     custom_id=_custom_id(gid, uid, "hedit_left"), row=1)
        rem_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, label="✖ Remove",
                                    custom_id=_custom_id(gid, uid, "hedit_remove"), row=1)
        right_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="➡️",
                                      custom_id=_custom_id(gid, uid, "hedit_right"), row=1)
        close_btn = discord.ui.Button(style=discord.ButtonStyle.danger, label="❌ Close Edit",
                                      custom_id=_custom_id(gid, uid, "hedit_close"), row=1)

        # Row 2: [spacer] [⬇️]
        sp3 = _sp("hesp3"); sp3.row = 2
        down_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="⬇️",
                                     custom_id=_custom_id(gid, uid, "hedit_down"), row=2)

        for btn in [sp1, up_btn, sp2, add_btn, del_btn,
                    left_btn, rem_btn, right_btn, close_btn,
                    sp3, down_btn]:
            self.add_item(btn)


class HouseDecorationView(discord.ui.View):
    """Select a decoration to place in a player house."""

    def __init__(self, guild_id: int, user_id: int, page: int = 0, selected: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        catalog = HOUSE_DECORATION_CATALOG
        per_page = 5
        total_pages = max(1, (len(catalog) + per_page - 1) // per_page)
        page_items = catalog[page * per_page: page * per_page + per_page]

        # Row 0: up to 5 decoration item buttons
        for i, item in enumerate(page_items):
            abs_idx = page * per_page + i
            cost_str = "+".join(f"{v}{k}" for k, v in item["cost"].items())
            lbl = f"{item['name']} ({cost_str})"
            style = discord.ButtonStyle.success if abs_idx == selected else discord.ButtonStyle.secondary
            self.add_item(discord.ui.Button(
                style=style, label=lbl,
                custom_id=_custom_id(gid, uid, f"hdeco_sel_{abs_idx}"),
                row=0,
            ))
        # Pad row 0 to 5 buttons
        for i in range(len(page_items), per_page):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary, label="\u200b", disabled=True,
                custom_id=_custom_id(gid, uid, f"hdsp_{i}"), row=0,
            ))

        # Row 1: ◀ ▶ Place Cancel
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="◀", disabled=(page == 0),
            custom_id=_custom_id(gid, uid, "hdeco_prev"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="▶", disabled=(page >= total_pages - 1),
            custom_id=_custom_id(gid, uid, "hdeco_next"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success, label="🏗️ Place",
            custom_id=_custom_id(gid, uid, "hdeco_place"), row=1,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "hdeco_cancel"), row=1,
        ))


# ── Tavern buy view ───────────────────────────────────────────────────────────

class TavernBuyView(discord.ui.View):
    """One button per menu item (up to 4 per row) + a close button."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        from dwarf_explorer.config import TAVERN_MENU
        gid, uid = guild_id, user_id
        _items_per_row = 4
        for idx, item in enumerate(TAVERN_MENU):
            label = f"{item['name']} {item['price']}🪙"
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary, label=label,
                custom_id=_custom_id(gid, uid, f"tavern_buy_{item['id']}"),
                row=idx // _items_per_row,
            ))
        close_row = (len(TAVERN_MENU) - 1) // _items_per_row + 1
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Leave",
            custom_id=_custom_id(gid, uid, "tavern_close"), row=close_row,
        ))


# ── Heal confirm view ─────────────────────────────────────────────────────────

class HealConfirmView(discord.ui.View):
    """Accept / decline the healer's offer."""

    def __init__(self, guild_id: int, user_id: int, cost: int):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=f"✅ Pay {cost}🪙",
            custom_id=_custom_id(gid, uid, "heal_accept"),
            row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="❌ No thanks",
            custom_id=_custom_id(gid, uid, "heal_decline"),
            row=0,
        ))


# ── Farmer shop view ─────────────────────────────────────────────────────────

class FarmerShopView(discord.ui.View):
    """One button per farmer shop item + a close button (max 4 items per row)."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        from dwarf_explorer.config import FARMER_SHOP
        gid, uid = guild_id, user_id
        _items_per_row = 4
        for idx, item in enumerate(FARMER_SHOP):
            label = f"{item['name']} {item['price']}🪙"
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary, label=label,
                custom_id=_custom_id(gid, uid, f"farmer_buy_{item['id']}"),
                row=idx // _items_per_row,
            ))
        close_row = (len(FARMER_SHOP) // _items_per_row) + 1
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Leave",
            custom_id=_custom_id(gid, uid, "farmer_close"), row=close_row,
        ))


# ── Tree City Shop view ───────────────────────────────────────────────────────

class TreeCityShopView(discord.ui.View):
    """One button per tree-city item + a close button."""

    def __init__(self, guild_id: int, user_id: int, shop_catalog: list[dict]):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        for idx, item in enumerate(shop_catalog):
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"{item['name']} {item['price']}🪙",
                custom_id=_custom_id(gid, uid, f"tree_city_buy_{item['id']}"),
                row=idx // 4,
            ))
        close_row = (len(shop_catalog) // 4) + 1
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.danger, label="❌ Leave",
            custom_id=_custom_id(gid, uid, "tree_city_close"), row=close_row,
        ))


# ── Lumber convert view ────────────────────────────────────────────────────────

class LumberConvertView(discord.ui.View):
    """Lumber NPC menu: craft a canoe from planks.

    Log → plank conversion is handled by the conveyor (📥 / 📤), not the NPC.
    """

    def __init__(self, guild_id: int, user_id: int, log_count: int = 0, plank_count: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        if plank_count >= 18:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="🛶 Craft Canoe (18 planks)",
                custom_id=_custom_id(gid, uid, "lumber_craft_canoe"),
                row=0,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "lumber_convert_cancel"), row=1,
        ))


# ── NPC Dialogue view ─────────────────────────────────────────────────────────

class DialogueView(discord.ui.View):
    """Scrollable NPC dialogue with option list.

    State in _ui_state[user_id]:
      {"type": "npc_dialogue", "npc_type": str, "text": str,
       "options": [{"label": str, "action": str}, ...], "selected": int}
    """

    def __init__(self, guild_id: int, user_id: int, options: list[dict], selected: int = 0):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.secondary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # Row 0: ✅ Confirm currently-highlighted option
        if options and selected < len(options):
            opt = options[selected]
            self.add_item(_btn(
                f"✅ {opt['label']}", f"dlg_confirm_{opt['action']}",
                0, discord.ButtonStyle.success
            ))

        # Row 1: ⬅️ prev option | ➡️ next option (same arrow emojis as the D-pad)
        self.add_item(_btn("⬅️", "dlg_up",   1, disabled=(selected == 0)))
        self.add_item(_btn("➡️", "dlg_down", 1, disabled=(selected >= len(options) - 1)))

        # Row 2: ❌ Cancel
        self.add_item(_btn("❌ Cancel", "dlg_cancel", 2, discord.ButtonStyle.danger))


# ── Crew management view ───────────────────────────────────────────────────────

class CrewView(discord.ui.View):
    """Below-deck crew management: assign tasks, fire crew."""

    def __init__(self, guild_id: int, user_id: int, crew: list[dict]):
        super().__init__(timeout=None)
        from dwarf_explorer.config import CREW_TASKS, MAX_CREW_SIZE
        gid, uid = guild_id, user_id

        def _btn(label, action, row, style=discord.ButtonStyle.secondary, disabled=False):
            return discord.ui.Button(
                style=style, label=label, disabled=disabled,
                custom_id=_custom_id(gid, uid, action), row=row,
            )

        # One row per crew slot (up to MAX_CREW_SIZE rows)
        for i, member in enumerate(crew[:MAX_CREW_SIZE]):
            slot = member["slot"]
            name = member["name"]
            task_info = CREW_TASKS.get(member["task"], CREW_TASKS["idle"])
            task_label = f"{task_info['emoji']} {task_info['label']}"
            row = i
            # Name label (disabled)
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"⚓ {name}",
                disabled=True,
                custom_id=_custom_id(gid, uid, f"crew_sp_{slot}"),
                row=row,
            ))
            # Task cycle button
            self.add_item(_btn(task_label, f"crew_task_{slot}", row, discord.ButtonStyle.primary))
            # Fire button
            self.add_item(_btn("🔥 Fire", f"crew_fire_{slot}", row, discord.ButtonStyle.danger))

        # Close button on last row
        close_row = min(len(crew), MAX_CREW_SIZE)
        self.add_item(_btn("❌ Close", "crew_close", close_row, discord.ButtonStyle.secondary))


class VillageRecruitView(discord.ui.View):
    """Recruit / cancel buttons shown when player interacts with a recruitable harbour NPC."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="⚓ Recruit",
            custom_id=_custom_id(gid, uid, "village_recruit_confirm"),
            row=0,
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Not now",
            custom_id=_custom_id(gid, uid, "village_recruit_cancel"),
            row=0,
        ))


# ── Gold cap helper ───────────────────────────────────────────────────────────

def _apply_gold_cap(player: Player, amount: int) -> int:
    """Add amount to player.gold respecting coin purse capacity. Returns actual added."""
    cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
    before = player.gold
    player.gold = min(player.gold + amount, cap)
    return player.gold - before


# ── Equipment helpers ─────────────────────────────────────────────────────────

def _equipped_dict(player: Player) -> dict:
    d = {}
    for slot, val in [
        ("hand_1", player.hand_1), ("hand_2", player.hand_2),
        ("head", player.head), ("chest", player.chest),
        ("legs", player.legs), ("boots", player.boots),
        ("accessory", player.accessory), ("pouch", player.pouch),
        ("coin_purse", player.coin_purse),
    ]:
        if val:
            d[slot] = val
    return d


def _inv_capacity(player: Player) -> tuple[int, int]:
    """Return (rows, cols) for player's current inventory based on equipped pouch."""
    return POUCH_SIZES.get(player.pouch, POUCH_SIZES[None])


async def _give_items_or_drop(
    db, guild_id: int, user_id: int, player: "Player",
    loot: list[tuple[str, int]],
) -> tuple[list[str], str]:
    """Give loot to player, dropping overflow as a drop box if inventory is full.

    Returns (gained_descriptions, overflow_msg).
    gained_descriptions: list of strings like "3 iron ore"
    overflow_msg: empty string or a sentence about items dropped on the ground.
    """
    rows, cols = _inv_capacity(player)
    max_slots = rows * cols
    gained: list[str] = []
    overflow: list[tuple[str, int]] = []

    for item_id, qty in loot:
        leftover = await add_to_inventory(db, user_id, item_id, qty, max_slots=max_slots)
        added = qty - leftover
        if added > 0:
            gained.append(f"{added} {item_id.replace('_', ' ')}")
        if leftover > 0:
            overflow.append((item_id, leftover))

    drop_msg = ""
    if overflow:
        wx = player.world_x
        wy = player.world_y
        await create_drop_box(db, wx, wy, overflow)
        names = ", ".join(f"{q} {i.replace('_', ' ')}" for i, q in overflow)
        drop_msg = f" 🎒 Inventory full! {names} left in a 📦 at the cave entrance."
    return gained, drop_msg


def _inv_action_btn(
    items: list[dict], selected: int, equipped: dict,
    cursor_mode: str = "inventory", equipped_cursor: int = 0,
) -> tuple[str, str]:
    """Return (button_emoji, button_action) for the primary inventory action button.
    Labels are emoji-only — no text."""
    if cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
        if equipped_cursor < len(_EQUIP_SLOT_ORDER):
            slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
            if equipped.get(slot):
                return ("\u2935\uFE0F", "inv_unequip")  # ⤵️ arrow heading down = unequip
        return ("", "")
    if cursor_mode == "gold":
        return ("", "")
    # inventory mode — use slot_index-aware lookup
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    ci = _cursor_item(visible, selected)
    if ci is not None:
        item_id = ci["item_id"]
        _hp_food = item_id in FOOD_HP_RESTORE or (
            item_id in CONSUMABLE_ITEMS and CONSUMABLE_ITEMS[item_id].get("hp", 0) > 0
        )
        if _hp_food or item_id == "breath_of_the_sea":
            return ("\U0001F357", "inv_eat")            # 🍗 eat / use
        if item_id in ITEM_EQUIP_SLOTS:
            if item_id in equipped.values():
                return ("🫴", "inv_equip")      # 🫴 = unequip/give back
            # Use the same emojis as the empty equipped-row slots so the button
            # always shows the slot destination, not the item's own icon.
            _SLOT_EMOJI = {
                "hand":       "✋",          # ✋  empty hand
                "boots":      "\U0001F9B6",      # 🦶  empty boot slot
                "head":       "\U0001F9D4",      # 🧔  empty head slot
                "chest":      "\U0001F455",      # 👕  empty chest slot
                "legs":       "\U0001F456",      # 👖  empty legs slot
                "accessory":  "\U0001F48D",      # 💍  empty accessory
                "pouch":      "\U0001F45C",      # 👜  empty pouch
                "coin_purse": "\U0001F4B0",      # 💰  empty coin purse
            }
            slot = ITEM_EQUIP_SLOTS.get(item_id, "hand")
            equip_emoji = _SLOT_EMOJI.get(slot, "\U0001F91A")  # 🤚 fallback
            return (equip_emoji, "inv_equip")
    return ("", "")


def _equip_label(items: list[dict], selected: int, equipped: dict) -> str:
    """Legacy helper — returns the display label only (no action id)."""
    return _inv_action_btn(items, selected, equipped)[0]


async def _auto_unequip_depleted(db, user_id: int, item_id: str, player: Player) -> None:
    """Unequip item from hand slots if all inventory stacks of it are now empty."""
    rows = await db.fetch_all(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
    )
    total = sum(r["quantity"] for r in rows)
    if total > 0:
        return
    for slot in ("hand_1", "hand_2"):
        if getattr(player, slot, None) == item_id:
            await unequip_item(db, user_id, slot)


async def _resolve_cave_combat(
    player: Player, enemy_type: str,
    cave_x: int, cave_y: int, db, user_id: int
) -> str:
    from dwarf_explorer.config import ENEMY_STATS
    hp, atk, defn, xp_rew, gold_rew = ENEMY_STATS[enemy_type]
    enemy_dmg = max(0, atk - player.defense)
    player_dmg = max(1, player.attack - defn)
    player.hp = max(0, player.hp - enemy_dmg)
    _apply_gold_cap(player, gold_rew)
    player.xp += xp_rew
    await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
    await db.execute(
        "UPDATE cave_tiles SET tile_type='stone_floor'"
        " WHERE cave_id=? AND local_x=? AND local_y=?",
        (player.cave_id, cave_x, cave_y),
    )
    name = enemy_type.replace("cave_", "").replace("_", " ").title()
    result = f"\u2694\uFE0F You fight the {name}! Dealt {player_dmg}. Took {enemy_dmg} damage."
    if player.hp <= 0:
        result += " You have been knocked out! (HP: 0)"
    else:
        result += f" Got {xp_rew}XP, {gold_rew}g."
    return result


# ── Movement ──────────────────────────────────────────────────────────────────

# NPC tiles that can offer quests — player must be adjacent to trigger the NPC button
_QUEST_NPC_TILES = {
    "b_priest", "b_tavern_npc", "b_farmer_npc",
    "b_blacksmith_npc", "b_resident",
    "vil_villager", "vil_guard",
    # Tree city NPCs
    "tc_elder", "tc_archivist", "tc_villager",
    # Rift NPC
    "rift_archivist",
}


_VIL_SEEDS_TILES = {"vil_seeds_wheat", "vil_seeds_carrot", "vil_seeds_potato"}
_VIL_CROP_TILES  = {"vil_crop_wheat", "vil_crop_carrot", "vil_crop_potato"}

def _compute_context_labels(
    grid: list[list],
    player: Player,
    hand_items: set[str],
    has_canoe: bool = False,
) -> tuple[str, bool, str, bool, bool, str, bool, bool, bool, bool, str, bool, str, str, bool]:
    """Return (center_label, center_enabled, action_label, action_enabled, edit_enabled,
               npc_label, npc_enabled, embark_enabled, feed_enabled, plant_enabled,
               action2_label, action2_enabled, action2_id,
               interact2_label, interact2_enabled).

    center = on-tile interaction (interact button at row-2 center)
    action = adjacent-tile interaction (action button at row-1 col-2)
    edit   = ⚒️ Edit button at row-0 col-4 (player-house owners only)
    npc    = bottom-right contextual button; lights up when adjacent to a quest NPC
    plant  = bottom-left button; lights up when standing on vil_farmland in village
    """
    vc = 4  # VIEWPORT_CENTER

    center_label, center_enabled = "", False
    action_label, action_enabled = "", False
    action2_label, action2_enabled, action2_id = "", False, "sp_action2"
    edit_enabled = False

    if not grid or len(grid) <= vc:
        return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

    # ── Inside a player house ─────────────────────────────────────────────────
    _in_ph = player.in_house and player.house_type == "player_house"
    if _in_ph:
        if _ui_state.get(player.user_id, {}).get("is_house_owner", False):
            edit_enabled = True
        # Fall through to center_tile checks so b_stove etc. still work.
        # PH chests are handled after the main block below.

    center_tile = grid[vc][vc] if len(grid[vc]) > vc else None
    if center_tile:
        t = center_tile.terrain
        s = center_tile.structure

        # Ship tile context (highest priority when in_ship)
        if player.in_ship:
            if t == "ship_helm":
                center_label, center_enabled = "⚓", True
            elif t == "ship_door":
                center_label, center_enabled = "🚪", True
            elif t == "ship_chest_personal":
                from dwarf_explorer.config import SHIP_EMOJI
                center_label, center_enabled = SHIP_EMOJI.get("ship_chest_personal", "📦"), True
            elif t == "ship_chest_cargo":
                from dwarf_explorer.config import SHIP_EMOJI
                center_label, center_enabled = SHIP_EMOJI.get("ship_chest_cargo", "📦"), True
            elif t == "ship_hull_damage":
                hand_items = {player.hand_1, player.hand_2} - {None}
                if "hammer" in hand_items:
                    center_label, center_enabled = "🔨 Repair", True
                else:
                    center_label, center_enabled = "🕳️ Damage", False
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Shipwreck tile context
        if getattr(player, "in_shipwreck", False):
            if t == "sw_entrance":
                center_label, center_enabled = "\U0001F300 Exit", True
            elif t == "sw_chest":
                center_label, center_enabled = "\U0001F4B0 Open", True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Temple tile context (outer & main)
        if getattr(player, "in_temple", False):
            if t == "gear_machine":
                center_label, center_enabled = "⚙️ Gears", True
            elif t == "temple_entrance":
                center_label, center_enabled = "🚪 Exit", True
            elif t in ("temple_altar", "temple_rune"):
                center_label, center_enabled = "📜 Inspect", True
            elif t == "temple_portal_open":
                center_label, center_enabled = "🌀 Enter", True
            elif t == "temple_portal_locked":
                center_label, center_enabled = "🔒 Locked", True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Sky biome tile context
        if getattr(player, "in_sky", False):
            if t == "sky_entrance":
                center_label, center_enabled = "\U0001F300 Descend", True
            elif t == "sky_chest":
                center_label, center_enabled = "\U0001F4B0 Open", True
            elif t == "sky_altar":
                center_label, center_enabled = "✨ Inspect", True
            elif t == "sky_temple":
                center_label, center_enabled = "\U0001F3DB️ Inspect", True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Forest tile context
        if getattr(player, "in_forest", False) and not getattr(player, "in_tree_city", False) and not getattr(player, "in_hermit_hut", False):
            if t == "fst_exit":
                center_label, center_enabled = "🌲 Exit", True
            elif t == "fst_nut_tree":
                center_label, center_enabled = "🌰 Gather", True
            elif t == "fst_ancient_tree":
                if "axe" in hand_items:
                    center_label, center_enabled = "🪓 Chop", True
                elif "watering_can" in hand_items:
                    center_label, center_enabled = "🪣 Water", True
                else:
                    center_label, center_enabled = "🌲 Inspect", True
            elif t == "fst_tree_city":
                from dwarf_explorer.config import FOREST_EMOJI as _FE_tc
                _tc_e = _FE_tc.get("fst_tree_city", "🏡")
                center_label, center_enabled = f"{_tc_e} Enter", True
            elif t == "fst_maze_door":
                center_label, center_enabled = "🌀 Enter", True
            elif t == "fst_hermit_house":
                center_label, center_enabled = "🛖 Enter", True
            elif t in ("fst_chest", "fst_mimic", "fst_map_chest"):
                # fst_mimic and fst_map_chest look identical to fst_chest
                from dwarf_explorer.config import FOREST_EMOJI as _FE
                _ce = _FE.get("fst_chest", "📦")
                center_label, center_enabled = f"{_ce} Open", True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Tree City tile context
        if getattr(player, "in_tree_city", False):
            if t == "tc_door":
                center_label, center_enabled = "🚪 Exit", True
            elif t == "tc_bed":
                center_label, center_enabled = "🛏️ Rest", True
            elif t == "tc_stair_up":
                from dwarf_explorer.config import TC_EMOJI as _TCE
                _sc_e = _TCE.get("tc_stair_up", "🔼")
                center_label, center_enabled = f"{_sc_e} Up", True
            elif t == "tc_stair_down":
                from dwarf_explorer.config import TC_EMOJI as _TCE
                _sc_e = _TCE.get("tc_stair_down", "🔽")
                center_label, center_enabled = f"{_sc_e} Down", True
            # Adjacency: show action button when next to a merchant NPC
            for _dy2, _dx2 in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _ar2, _ac2 = vc + _dy2, vc + _dx2
                if 0 <= _ar2 < len(grid) and 0 <= _ac2 < len(grid[_ar2]):
                    _adj_t = grid[_ar2][_ac2].terrain
                    if _adj_t == "tc_shop":
                        action_label, action_enabled = "🛍️ Shop", True
                        break
            # TC NPC tiles → bottom-right talk button
            _tc_npc_adj = False
            for _dy_n, _dx_n in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _ar_n, _ac_n = vc + _dy_n, vc + _dx_n
                if 0 <= _ar_n < len(grid) and 0 <= _ac_n < len(grid[_ar_n]):
                    if grid[_ar_n][_ac_n].terrain in _QUEST_NPC_TILES:
                        _tc_npc_adj = True
                        break
            _tc_npc_label = ("💬", True) if _tc_npc_adj else ("", False)
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, _tc_npc_label[0], _tc_npc_label[1], False, False, False, "", False, "sp_action2", "", False

        # Maze tile context
        if getattr(player, "in_maze", False):
            if t == "maze_exit":
                center_label, center_enabled = "🚪 Exit", True
            elif t in ("maze_chest", "maze_mimic"):
                # maze_mimic looks identical to maze_chest intentionally
                center_label, center_enabled = "💰 Open", True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Grove tile context
        if getattr(player, "in_grove", False):
            if t == "grove_exit":
                center_label, center_enabled = "🚪 Exit", True
            # Adjacency: grove_statue gives warp crystal
            for _dy_g, _dx_g in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _ar_g, _ac_g = vc + _dy_g, vc + _dx_g
                if 0 <= _ar_g < len(grid) and 0 <= _ac_g < len(grid[_ar_g]):
                    if grid[_ar_g][_ac_g].terrain == "grove_statue":
                        action_label, action_enabled = "🗿 Touch", True
                        break
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Hermit Hut tile context — checked BEFORE bandit camp to avoid stale flag conflicts
        if getattr(player, "in_hermit_hut", False):
            if t == "b_door":
                center_label, center_enabled = "🚪 Exit", True
            elif t == "hut_stair_up":
                center_label, center_enabled = "🔼 Ascend", True
            elif t == "hut_stair_down":
                center_label, center_enabled = "🔽 Descend", True
            # Show Talk action when adjacent to the hermit NPC
            for _dy_hh, _dx_hh in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _ar_hh, _ac_hh = vc + _dy_hh, vc + _dx_hh
                if 0 <= _ar_hh < len(grid) and 0 <= _ac_hh < len(grid[_ar_hh]):
                    if grid[_ar_hh][_ac_hh].terrain == "hermit_npc":
                        action_label, action_enabled = "🧙 Talk", True
                        break
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Bandit camp tile context
        if getattr(player, "in_bandit_camp", False):
            if t == "bc_exit":
                center_label, center_enabled = "🚪 Leave", True
            # NPC button when adjacent to a bandit
            _bc_bandit_adj = False
            for _dy_bc, _dx_bc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _ar_bc, _ac_bc = vc + _dy_bc, vc + _dx_bc
                if 0 <= _ar_bc < len(grid) and 0 <= _ac_bc < len(grid[_ar_bc]):
                    _bc_tile = grid[_ar_bc][_ac_bc]
                    if _bc_tile and _bc_tile.terrain == "bc_bandit":
                        _bc_bandit_adj = True
                        break
            _bc_npc = ("💬", True) if _bc_bandit_adj else ("", False)
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, _bc_npc[0], _bc_npc[1], False, False, False, "", False, "sp_action2", "", False

        # Island tile context
        if player.in_island:
            if t in ("island_dock", "vol_dock"):
                center_label, center_enabled = "⛵ Leave", True
            elif t in ("island_chest", "vol_chest"):
                center_label, center_enabled = "💰 Loot", True
            elif t == "vol_cave":
                center_label, center_enabled = "⛰️ Enter", True
            elif t == "vol_outpost":
                center_label, center_enabled = "🛒 Shop", True
            elif t in ("island_forest", "island_tree") and "axe" in hand_items:
                center_label, center_enabled = "🪓", True
            # Fishing: adjacent to island_void or vol_void (open ocean surrounding island)
            local_adj: set[str] = set()
            for _ro, _co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _r, _c = vc + _ro, vc + _co
                if 0 <= _r < len(grid) and 0 <= _c < len(grid[_r]):
                    _adj = grid[_r][_c]
                    if _adj.terrain:
                        local_adj.add(_adj.terrain)
            if "fishing_rod" in hand_items and local_adj & {"island_void", "vol_void"}:
                action_label, action_enabled = "🎣 Fish", True
            return center_label, center_enabled, action_label, action_enabled, edit_enabled, "", False, False, False, False, "", False, "sp_action2", "", False

        # Structural overrides (cave/village on overworld)
        if s == "player_house":
            center_label, center_enabled = "🏠", True
        elif t == "player_house_cave":
            center_label, center_enabled = "🏠", True
        elif s == "cave":
            center_label, center_enabled = "🕳️", True
        elif s == "shipwreck":
            center_label, center_enabled = "⚓ Dive", True
        elif s == "village":
            center_label, center_enabled = "🏘️", True
        elif s == "shrine":
            center_label, center_enabled = "⛩️", True
        elif s in ("ruins", "ruins_looted"):
            center_label, center_enabled = "🏚️", True
        elif s == "harbor":
            center_label, center_enabled = "🚢 Harbor", True
        elif s == "sky_portal":
            if player.boots == "climbing_boots":
                center_label, center_enabled = "\U0001F300 Enter Sky", True
            else:
                center_label, center_enabled = "\U0001F300 Sky Portal", False
        elif s == "sky_temple_outer":
            center_label, center_enabled = "🏛️ Enter Temple", True
        elif s == "sky_temple_main":
            center_label, center_enabled = "🏰 Enter Temple", True
        # Cave boss door — show lock; key check handled in movement
        elif t == "cave_boss_door":
            center_label, center_enabled = "🔒 Locked", False
        # Cave chest — use custom chest emoji if available
        elif t in CAVE_CHEST_TYPES:
            center_label, center_enabled = CAVE_EMOJI.get(t, "📦"), True
        # Cave exit / building door / village buildings (enter)
        elif t in ("cave_entrance", "b_door"):
            center_label, center_enabled = "🚪", True
        elif t in ("vil_house", "vil_church", "vil_bank", "vil_shop",
                    "vil_blacksmith", "vil_tavern", "vil_hospital",
                    "vil_lumber_mill", "vil_farmhouse", "vil_armory"):
            center_label, center_enabled = "🚪", True
        elif t == "vil_villager":
            center_label, center_enabled = "💬 Talk", True
        elif t == "vil_guard":
            center_label, center_enabled = "💬 Talk", True
        # Building NPCs (on-tile)
        elif t == "b_bank_npc":
            center_label, center_enabled = "🏦", True
        elif t == "b_shop_npc":
            center_label, center_enabled = "🛒", True
        elif t == "b_blacksmith_npc":
            center_label, center_enabled = "⚒️", True
        elif t == "b_priest":
            center_label, center_enabled = "💬", True
        elif t == "b_altar":
            center_label, center_enabled = "⛩️", True
        elif t == "b_safe":
            center_label, center_enabled = "🔒", True
        elif t == "b_barkeep":
            center_label, center_enabled = "🍺 Order", True
        elif t == "b_tavern_npc":
            center_label, center_enabled = "📋 Quest", True
        elif t == "b_crew_npc":
            center_label, center_enabled = "💬 Talk", True
        elif t == "b_healer":
            center_label, center_enabled = "💊 Heal", True
        elif t == "b_bar_counter":
            center_label, center_enabled = "🍺", True
        elif t == "b_medicine_shelf":
            center_label, center_enabled = "💬", True
        elif t == "b_resident":
            center_label, center_enabled = "💬 Talk", True
        elif t == "b_lumber_npc":
            center_label, center_enabled = "🪵 Convert", True
        # Lumbermill conveyor: player interacts while standing ADJACENT to input/output
        # (those tiles are not walkable, so we check neighbours)
        if (player.in_house and getattr(player, "house_type", None) == "lumber_mill"
                and not center_enabled):
            for _dy_lm, _dx_lm in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _r_lm, _c_lm = vc + _dy_lm, vc + _dx_lm
                if 0 <= _r_lm < len(grid) and 0 <= _c_lm < len(grid[_r_lm]):
                    _adj_lm = grid[_r_lm][_c_lm].terrain
                    if _adj_lm == "b_log_input":
                        center_label, center_enabled = "📥 Insert", True
                        break
                    elif _adj_lm == "b_plank_output":
                        # Only show pickup if planks are waiting (key uses player.user_id)
                        _lm_planks = _ui_state.get(f"lm_planks_{player.user_id}", 0)
                        if _lm_planks > 0:
                            center_label, center_enabled = "📤 Take planks", True
                        break
        elif t == "b_chest":
            center_label, center_enabled = "🔒 Open", True
        elif t == "b_farmer_npc":
            center_label, center_enabled = "🌾 Shop", True
        elif t == "b_pet":
            center_label, center_enabled = "🐱", True
        elif t == "vil_well":
            center_label, center_enabled = "⛲", True
        elif t == "vil_puzzle_board":
            center_label, center_enabled = "🎮 Play", True
        elif t == "vil_dock":
            center_label, center_enabled = "⚓ Board", True
        # Village farmland interactions
        elif t in _VIL_SEEDS_TILES and "watering_can" in hand_items:
            center_label, center_enabled = "💧 Water", True
        elif t in _VIL_CROP_TILES:
            center_label, center_enabled = "🌾 Harvest", True
        elif t == "vil_grass" and "hoe" in hand_items:
            center_label, center_enabled = "🟤 Till", True
        # Item-based interactions (lower priority)
        elif t == "crop_ripe":
            center_label, center_enabled = "🌻", True
        elif t == "farmland" and "seed" in hand_items:
            center_label, center_enabled = "🌱", True
        elif t == "path" and "seed" in hand_items:
            center_label, center_enabled = "🌱", True
        elif t in ("drop_box", "canoe_box"):
            center_label, center_enabled = "🤲", True

    # ── Action label: adjacent-tile interactions ──────────────────────────────
    adj_terrains: set[str] = set()
    for ro, co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        r, c = vc + ro, vc + co
        if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
            adj = grid[r][c]
            if adj.terrain:
                adj_terrains.add(adj.terrain)
            if adj.structure:
                adj_terrains.add(adj.structure)

    if "gear_machine" in adj_terrains and getattr(player, "in_temple", False):
        action_label, action_enabled = "⚙️ Gears", True
    elif "b_stove" in adj_terrains:
        action_label, action_enabled = "🔥 Cook", True
    elif "b_forge" in adj_terrains:
        action_label, action_enabled = "🔥 Forge", True
    elif "b_anvil" in adj_terrains:
        action_label, action_enabled = "⚒️ Smith", True
    elif "b_shop_npc" in adj_terrains:
        action_label, action_enabled = "🛒 Shop", True
    elif "b_bank_npc" in adj_terrains:
        action_label, action_enabled = "🏦 Bank", True
    elif "b_barkeep" in adj_terrains:
        action_label, action_enabled = "🍺 Order", True
    elif "b_healer" in adj_terrains:
        action_label, action_enabled = "💊 Heal", True
    elif "b_farmer_npc" in adj_terrains and not action_enabled:
        action_label, action_enabled = "🌾 Farmer", True
    elif "b_lumber_npc" in adj_terrains and not action_enabled:
        action_label, action_enabled = "🪵 Mill", True
    elif "b_pet" in adj_terrains and not action_enabled:
        action_label, action_enabled = "🐱 Pet", True
    # Fishing rod and watering can fill are now handled by H1/H2 hand buttons.

    if not action_enabled and center_tile and not player.in_house and "house_kit" in hand_items:
        # Offer to build a house on the current tile if house_kit is equipped and tile is buildable
        _bt = center_tile.terrain
        _build_ok = (
            not center_tile.structure
            and center_tile.walkable
            and _bt not in {"void", "deep_water", "shallow_water", "river", "river_landing",
                            "mountain", "snow", "player_house_cave"}
        )
        if _build_ok:
            action_label, action_enabled = "🏠 Build", True

    # ── Player-house chest override (highest priority for center label) ────────
    if _in_ph and center_tile and center_tile.terrain in PH_CHEST_TYPES:
        center_label, center_enabled = BUILDING_EMOJI.get(center_tile.terrain, "📦"), True

    # ── NPC quest button: bottom-right, lights up when adjacent to a quest NPC ─
    npc_label, npc_enabled = "", False
    if adj_terrains & _QUEST_NPC_TILES:
        npc_label, npc_enabled = "💬", True

    # ── Embark canoe: directional arrow replacement (computed in _game_view) ──
    embark_enabled = False  # no longer uses bottom-left slot

    # ── Feed cat: bottom-left button when adjacent to a pet inside a house ──────
    feed_enabled = False
    if player.in_house:
        for ro, co in ((-1,0),(1,0),(0,-1),(0,1)):
            r, c = vc + ro, vc + co
            if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
                if grid[r][c].terrain == "b_pet":
                    feed_enabled = True
                    break

    # ── Plant seeds/saplings: bottom-left button ─────────────────────────────
    plant_enabled = False
    if player.in_village and not player.in_house:
        if center_tile and center_tile.terrain == "vil_farmland":
            plant_enabled = True
    elif not player.in_village and not player.in_house:
        # Overworld: show plant button on dirt tiles (sapling / ancient_seed)
        if center_tile and center_tile.terrain == "dirt":
            plant_enabled = True

    # ── interact2: overflow second center action to bottom-left D-pad ─────────
    interact2_label, interact2_enabled = "", False

    return (center_label, center_enabled, action_label, action_enabled, edit_enabled,
            npc_label, npc_enabled, embark_enabled, feed_enabled, plant_enabled,
            action2_label, action2_enabled, action2_id,
            interact2_label, interact2_enabled)


async def _load_house_grid(player: Player, db) -> list[list]:
    """Load the correct viewport for whichever house type the player is in."""
    if player.house_type == "player_house":
        return await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    return await load_building_viewport(player.house_id, player.house_x, player.house_y, db)


def _game_view(guild_id: int, user_id: int, player: Player,
               mine_dirs: frozenset[str] = frozenset(),
               grid: list[list] | None = None,
               dock_available: bool = False,
               embark_enabled: bool = False,
               has_canoe: bool = False,
               dock_dirs: frozenset[str] = frozenset()) -> discord.ui.View:
    """Build the appropriate game view, computing context labels if grid is provided."""
    has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")

    # When player is in ship, use ship tile view (GameView with ship grid)
    if player.in_ship:
        if grid is None:
            grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
        # Fall through to GameView builder below (skip other mode checks)
    elif player.in_island:
        pass  # Fall through to GameView; caller must supply grid
    elif player.in_high_seas:
        island_nearby = bool(_ui_state.get(user_id, {}).get("island_target"))
        return OceanView(guild_id, user_id,
                         dock_available=(player.ocean_y == 0),
                         island_nearby=island_nearby,
                         has_fishing_rod=has_fishing_rod)
    elif player.in_ocean:
        return BoatView(guild_id, user_id, dock_available=dock_available,
                        has_fishing_rod=has_fishing_rod)
    elif player.in_canoe:
        has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        return CanoeView(guild_id, user_id, dock_dirs=dock_dirs, has_fishing_rod=has_fishing_rod)

    center_label, center_enabled = "", False
    action_label, action_enabled = "", False
    action2_label, action2_enabled, action2_id = "", False, "sp_action2"
    edit_enabled = False
    npc_label, npc_enabled = "", False

    plant_enabled = False
    interact2_label = ""
    interact2_enabled = False
    h1_item = player.hand_1
    h2_item = player.hand_2
    h1_action_enabled = False
    h2_action_enabled = False
    if grid is not None:
        hand_items: set[str] = set()
        if player.hand_1:
            hand_items.add(player.hand_1)
        if player.hand_2:
            hand_items.add(player.hand_2)
        (center_label, center_enabled, action_label, action_enabled, edit_enabled,
         npc_label, npc_enabled, embark_enabled, feed_enabled, plant_enabled,
         action2_label, action2_enabled, action2_id,
         interact2_label, interact2_enabled) = \
            _compute_context_labels(grid, player, hand_items, has_canoe=has_canoe)

        # ── Bomb: always enabled in hand (overworld AND cave) ─────────────
        if h1_item == "bomb":
            h1_action_enabled = True
        if h2_item == "bomb":
            h2_action_enabled = True
        if h1_item in ("wayerwood", "attuned_wayerwood"):
            h1_action_enabled = True
        if h2_item in ("wayerwood", "attuned_wayerwood"):
            h2_action_enabled = True

        # ── H1 / H2 tool-on-tile action ───────────────────────────────────
        if not player.in_cave and not player.in_ship:
            _ct = grid[4][4] if len(grid) > 4 and len(grid[4]) > 4 else None
            if _ct:
                _t = _ct.terrain
                _WATER_TILES = {"sapling", "pinecone_planted", "ancient_planted", "ancient_sapling", "short_grass", "seedling",
                                "crop_planted", "crop_sprout"}
                _SHOVEL_TILES = {"sapling", "dirt", "grass", "plains", "sand", "short_grass"}
                _FILL_WATER = {"river", "bridge", "shallow_water", "deep_water",
                               "vil_well", "vil_fountain"}
                # Check all 4 adjacent grid cells for a water source or ancient tree
                _vc4 = 4
                _adj_water = any(
                    0 <= _vc4 + _ro < len(grid)
                    and 0 <= _vc4 + _co < len(grid[_vc4 + _ro])
                    and grid[_vc4 + _ro][_vc4 + _co].terrain in _FILL_WATER
                    for _ro, _co in ((-1, 0), (1, 0), (0, -1), (0, 1))
                )
                _adj_ancient_tree = any(
                    0 <= _vc4 + _ro < len(grid)
                    and 0 <= _vc4 + _co < len(grid[_vc4 + _ro])
                    and grid[_vc4 + _ro][_vc4 + _co].terrain in _ANCIENT_TREE_TILES
                    for _ro, _co in ((-1, 0), (1, 0), (0, -1), (0, 1))
                )

                def _tool_action_enabled(item: str | None) -> bool:
                    if not item:
                        return False
                    return bool(
                        (item == "watering_can" and (_t in _WATER_TILES or _adj_water))
                        or (item == "fishing_rod" and _adj_water)
                        or (item == "shovel" and _t in _SHOVEL_TILES)
                        or (item == "hoe" and _t in ("grass", "plains", "dirt"))
                        or (item == "axe" and (_t in ("forest", "dense_forest") or _adj_ancient_tree))
                        or (item == "knife" and _t in ("grass", "plains"))
                        or item in ("cooked_fish", "fish")
                        or item == "map_fragment"
                        or item == "shovel"  # treasure dig fallback
                        or item == "bomb"       # bomb always enabled when in hand (handler checks for flint_and_steel)
                        or item in ("wayerwood", "attuned_wayerwood")  # always enabled
                    )

                h1_action_enabled = _tool_action_enabled(h1_item)
                h2_action_enabled = _tool_action_enabled(h2_item)

    # ── Directional canoe embark (replace arrow with 🛶 when water adjacent) ─
    canoe_dirs: frozenset[str] = frozenset()
    chop_dirs: frozenset[str] = frozenset()
    if (grid is not None
            and not player.in_cave and not player.in_village
            and not player.in_house and not player.in_ocean
            and not player.in_canoe and not player.in_ship):
        _vc = 4  # viewport center index
        _CANOE_WATER = {"river", "bridge", "shallow_water", "deep_water"}
        _has_canoe_item = has_canoe or bool(player.hand_1 == "canoe" or player.hand_2 == "canoe")
        _dir_offsets = [("up", -1, 0), ("down", 1, 0), ("left", 0, -1), ("right", 0, 1)]
        if _has_canoe_item:
            _cd: set[str] = set()
            for _dn, _ro, _co in _dir_offsets:
                _r, _c = _vc + _ro, _vc + _co
                if 0 <= _r < len(grid) and 0 <= _c < len(grid[_r]):
                    if grid[_r][_c].terrain in _CANOE_WATER:
                        _cd.add(_dn)
            canoe_dirs = frozenset(_cd)
        # ── Directional ancient tree chop (replace arrow with 🪓 when adj) ─
        _has_axe = (player.hand_1 == "axe" or player.hand_2 == "axe")
        if _has_axe:
            _chopd: set[str] = set()
            for _dn, _ro, _co in _dir_offsets:
                _r, _c = _vc + _ro, _vc + _co
                if 0 <= _r < len(grid) and 0 <= _c < len(grid[_r]):
                    if grid[_r][_c].terrain in _ANCIENT_TREE_TILES:
                        _chopd.add(_dn)
            chop_dirs = frozenset(_chopd)

    # ── Thornwarden boss fight: inject slingshot aim buttons ─────────────────
    if getattr(player, "in_fq_boss_combat", False):
        _has_sling = (player.hand_1 == "slingshot" or player.hand_2 == "slingshot")
        if getattr(player, "fq_boss_aim_mode", False):
            # In aim mode: action = Fire, interact2 = Cancel
            action_label, action_enabled = "🪨 Fire", True
            interact2_label, interact2_enabled = "❌ Cancel Aim", True
        elif _has_sling:
            # Has slingshot but not aiming: show Aim button via action2
            action2_label, action2_enabled, action2_id = "🎯 Aim", True, "fq_aim"

    return GameView(guild_id, user_id,
                    boots_equipped=(player.boots == "hiking_boots"),
                    sprinting=player.sprinting,
                    mine_dirs=mine_dirs,
                    center_label=center_label,
                    center_enabled=center_enabled,
                    action_label=action_label,
                    action_enabled=action_enabled,
                    edit_enabled=edit_enabled,
                    npc_label=npc_label,
                    npc_enabled=npc_enabled,
                    embark_enabled=embark_enabled,
                    feed_enabled=feed_enabled,
                    plant_enabled=plant_enabled,
                    action2_label=action2_label,
                    action2_enabled=action2_enabled,
                    action2_id=action2_id,
                    interact2_label=interact2_label,
                    interact2_enabled=interact2_enabled,
                    h1_item=h1_item,
                    h2_item=h2_item,
                    h1_action_enabled=h1_action_enabled,
                    h2_action_enabled=h2_action_enabled,
                    canoe_dirs=canoe_dirs,
                    chop_dirs=chop_dirs)


async def _cave_game_view(guild_id: int, user_id: int, player: Player, db,
                           grid: list[list] | None = None) -> GameView:
    """Build a GameView with mine buttons for any adjacent mineable tiles."""
    mine_dirs: set[str] = set()
    if player.in_cave:
        # Fetch all four adjacent tiles in one range query instead of 4 individual queries
        adj_rows = await db.fetch_all(
            "SELECT local_x, local_y, tile_type FROM cave_tiles"
            " WHERE cave_id=? AND local_x BETWEEN ? AND ? AND local_y BETWEEN ? AND ?",
            (player.cave_id,
             player.cave_x - 1, player.cave_x + 1,
             player.cave_y - 1, player.cave_y + 1),
        )
        adj = {(r["local_x"], r["local_y"]): r["tile_type"] for r in adj_rows}
        _mineable = frozenset(("cave_rock", "iron_ore_deposit", "gold_ore_deposit", "rift_deposit"))
        for direction, (dx, dy) in DIRECTIONS.items():
            if adj.get((player.cave_x + dx, player.cave_y + dy)) in _mineable:
                mine_dirs.add(direction)
    return _game_view(guild_id, user_id, player, frozenset(mine_dirs), grid=grid)


def _ship_game_view(guild_id: int, user_id: int, player: Player) -> discord.ui.View:
    """Build a GameView for ship interior with contextual center button."""
    grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
    return _game_view(guild_id, user_id, player, grid=grid)


_CANOE_DIRS: dict[str, tuple[int, int]] = {
    "up":        (0, -1),
    "down":      (0, 1),
    "left":      (-1, 0),
    "right":     (1, 0),
    "upleft":    (-1, -1),
    "upright":   (1, -1),
    "downleft":  (-1, 1),
    "downright": (1, 1),
}


async def _compute_canoe_dock_dirs(player, seed: int, db) -> frozenset[str]:
    """Return the set of directions where the adjacent tile is not canoe-passable (land to dock on)."""
    result: set[str] = set()
    for dir_name, (dx, dy) in _CANOE_DIRS.items():
        ax, ay = player.world_x + dx, player.world_y + dy
        if not (0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE):
            result.add(dir_name)  # world edge acts as land
            continue
        t = await load_single_tile(ax, ay, seed, db)
        if (t.structure or t.terrain) not in CANOE_PASSABLE:
            result.add(dir_name)
    return frozenset(result)


async def _adjacent_landing(player, seed: int, db) -> tuple[int, int] | None:
    """Return the first adjacent river_landing tile, or None."""
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if t.terrain == "river_landing":
                return (ax, ay)
    return None


async def _adjacent_harbor(player: Player, seed: int, db) -> tuple[int, int] | None:
    """Return world coords of the first adjacent harbor structure tile, or None.

    Used by boat mode to decide whether to show the ⚓ Dock button.
    """
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if t.structure == "harbor":
                return (ax, ay)
    return None


async def _is_adjacent_to_water(player: Player, seed: int, db) -> bool:
    """Return True if any of the 4 cardinal neighbours is a river/water tile."""
    water_types = {"river", "bridge", "shallow_water", "deep_water"}
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if (t.structure or t.terrain) in water_types:
                return True
    return False


async def _find_ocean_tile_near(wx: int, wy: int, seed: int, db) -> tuple[int, int]:
    """Scan outward from (wx, wy) and return the nearest ocean tile coords.

    Tries cardinal neighbours first, then diagonals, then 2-tile radius.
    Falls back to (wx, wy) itself if nothing found within range.
    """
    ocean_types = {"deep_water", "shallow_water"}
    search_offsets = [
        (0, -1), (0, 1), (-1, 0), (1, 0),
        (-1, -1), (1, -1), (-1, 1), (1, 1),
        (0, -2), (0, 2), (-2, 0), (2, 0),
        (-1, -2), (1, -2), (-1, 2), (1, 2),
        (-2, -1), (2, -1), (-2, 1), (2, 1),
    ]
    for ddx, ddy in search_offsets:
        ax, ay = wx + ddx, wy + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if (t.structure or t.terrain) in ocean_types:
                return (ax, ay)
    return (wx, wy)


async def _find_treasure_location(user_id: int, world_seed: int, db) -> tuple[int, int]:
    """Pick a deterministic random walkable overworld tile ≥40 tiles from spawn."""
    from dwarf_explorer.config import WALKABLE_TILES as _WT
    rng = _random.Random(hash((user_id, world_seed, "treasure_v1")))
    cx, cy = WORLD_SIZE // 2, WORLD_SIZE // 2
    for _ in range(300):
        tx = rng.randint(10, WORLD_SIZE - 11)
        ty = rng.randint(10, WORLD_SIZE - 11)
        if abs(tx - cx) + abs(ty - cy) < 40:
            continue
        t = await load_single_tile(tx, ty, world_seed, db)
        if t.terrain in _WT and t.terrain not in ("river_landing", "cave") and not t.structure:
            return tx, ty
    return cx + 45, cy + 45


async def _find_canoe_destinations(
    player, db
) -> list[tuple[int, int]]:
    """Canoe fast-travel destinations. (Feature pending river rework.)"""
    return []


_MERCHANT_RARE_ITEMS: list[dict] = [
    # Rare armour & weapons not normally sold in shops
    {"id": "iron_helmet",     "name": "Iron Helmet",      "emoji": "🪖", "price": 55,  "description": "Sturdy helm. +3 defense."},
    {"id": "iron_chestplate", "name": "Iron Chestplate",  "emoji": "👕", "price": 90,  "description": "Heavy chest armour. +5 defense."},
    {"id": "iron_leggings",   "name": "Iron Leggings",    "emoji": "👖", "price": 75,  "description": "Armoured legs. +4 defense."},
    {"id": "iron_boots",      "name": "Iron Boots",       "emoji": "🥾", "price": 55,  "description": "Reinforced footwear. +2 defense."},
    {"id": "iron_shield",     "name": "Iron Shield",      "emoji": "🛡️","price": 65,  "description": "Sturdy shield. +4 defense."},
    {"id": "dagger",          "name": "Dagger",           "emoji": "🗡️","price": 55,  "description": "Fast blade. +8 attack."},
    {"id": "sword",           "name": "Sword",            "emoji": "🗡️","price": 90,  "description": "Sharp longsword. +12 attack."},
    # Crafting components hard to find
    {"id": "iron_ingot",      "name": "Iron Ingot",       "emoji": "🧱", "price": 30,  "description": "Smelted iron bar. Used for forging."},
    {"id": "resin",           "name": "Resin",            "emoji": "🟡", "price": 10,  "description": "Tree resin. Used for torches."},
    {"id": "flint",           "name": "Flint",            "emoji": "🪨", "price": 9,   "description": "Sharp stone. Used for arrows & fire."},
    # Food items at a bargain
    {"id": "cooked_fish",     "name": "Cooked Fish",      "emoji": "🍖", "price": 7,   "description": "Restores +15 HP. Tastes like camp smoke."},
    {"id": "bread",           "name": "Bread",            "emoji": "🍞", "price": 3,   "description": "Restores +10 HP."},
    {"id": "meat_stew",       "name": "Meat Stew",        "emoji": "🍲", "price": 8,   "description": "Restores +20 HP. Traveller's favourite."},
    # Consumable ingredients
    {"id": "healing_herb",    "name": "Healing Herb",     "emoji": "🌿", "price": 7,   "description": "Hospital quest ingredient. Restores minor HP."},
    # Rare unique items (low-weight pool)
    {"id": "gold_ring",       "name": "Gold Ring",        "emoji": "💍", "price": 120, "description": "A fine ring. Craft with an enchanted gem for a power ring."},
    {"id": "star_fragment",   "name": "Star Fragment",    "emoji": "⭐", "price": 70,  "description": "Fallen starlight. Opens sundial rifts."},
    {"id": "arrow",           "name": "Arrows (×9)",      "emoji": "🏹", "price": 18,  "description": "Nine arrows for the slingshot. Bulk deal."},
    {"id": "fishing_net",     "name": "Fishing Net",      "emoji": "🎣", "price": 22,  "description": "Catch fish in rivers faster."},
]

_MERCHANT_DISCOUNT_RATE = 0.80  # 20% discount vs normal shop price
_MERCHANT_RARE_WEIGHT   = 0.40  # 40% of slots come from rare pool, rest from SHOP_CATALOG


def _generate_merchant_catalog(rng: _random.Random) -> list[dict]:
    """Generate a 6-item merchant catalog: mix of discounted shop items and rare goods."""
    catalog: list[dict] = []
    n_rare   = round(6 * _MERCHANT_RARE_WEIGHT)   # ~2-3 rare items
    n_shop   = 6 - n_rare

    rare_picks = rng.sample(_MERCHANT_RARE_ITEMS, min(n_rare, len(_MERCHANT_RARE_ITEMS)))
    shop_picks = rng.sample(SHOP_CATALOG, min(n_shop, len(SHOP_CATALOG)))

    # Discount shop items; rare items keep their listed price (already fair)
    for item in shop_picks:
        catalog.append({
            "id":          item["id"],
            "name":        item["name"],
            "emoji":       item.get("emoji", "📦"),
            "price":       max(1, int(item["price"] * _MERCHANT_DISCOUNT_RATE + 0.5)),
            "description": item.get("description", "") + " *(discounted)*",
        })
    for item in rare_picks:
        catalog.append({
            "id":          item["id"],
            "name":        item["name"],
            "emoji":       item["emoji"],
            "price":       item["price"],
            "description": item["description"],
        })

    rng.shuffle(catalog)
    return catalog


def _render_merchant(catalog: list[dict], selected: int, player) -> str:
    lines = ["🧑‍💼 **A travelling merchant stops you!**\n"]
    for i, item in enumerate(catalog):
        prefix = "▶ " if i == selected else "  "
        lines.append(f"{prefix}{item.get('emoji','📦')} **{item['name']}** — {item['price']}g")
    lines.append(f"\n🪙 You have **{player.gold}g**")
    if 0 <= selected < len(catalog):
        desc = catalog[selected].get("description", "")
        if desc:
            lines.append(f"*{desc}*")
    return "\n".join(lines)


def _roll_encounter(rng: _random.Random, rates: dict | None = None, gate: float = 0.01) -> str | None:
    """Roll for a random encounter. Returns enemy_type or None.

    Rolls once for a `gate` encounter chance (default 1%), then picks a mob by
    relative weight (values in `rates` are used as weights, not independent
    probabilities).
    """
    if rates is None:
        rates = CAVE_ENCOUNTER_RATES
    if rng.random() >= gate:
        return None
    total = sum(rates.values())
    if total <= 0:
        return None
    roll = rng.random() * total
    for enemy_type, weight in rates.items():
        roll -= weight
        if roll <= 0:
            return enemy_type
    return list(rates.keys())[-1]


async def _move_steps(
    player: Player, direction: str, steps: int, seed: int, db,
    guild_id: int, user_id: int,
) -> tuple[str, discord.ui.View]:
    """Move player 1 or 2 tiles, returning (content, view)."""
    vec = _CANOE_DIRS.get(direction, DIRECTIONS.get(direction, (0, 0)))
    dx, dy = vec

    if player.in_canoe:
        nx, ny = player.world_x + dx, player.world_y + dy
        if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
            has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
            return render_grid(grid, player, "You've reached the edge of the world!"), \
                   CanoeView(guild_id, user_id, dock_dirs=dock_dirs, has_fishing_rod=has_fishing_rod)
        target = await load_single_tile(nx, ny, seed, db)
        t = target.structure or target.terrain
        if t not in CANOE_PASSABLE:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
            has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
            return render_grid(grid, player, "You can't paddle in that direction. Press 🏝️ to go ashore."), \
                   CanoeView(guild_id, user_id, dock_dirs=dock_dirs, has_fishing_rod=has_fishing_rod)
        player.world_x, player.world_y = nx, ny
        await update_player_position(db, user_id, nx, ny)
        grid = await load_viewport(nx, ny, seed, db)
        dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
        has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        return render_grid(grid, player), CanoeView(guild_id, user_id, dock_dirs=dock_dirs, has_fishing_rod=has_fishing_rod)

    if player.in_ship:
        nx, ny = player.ship_x + dx, player.ship_y + dy
        # Door transition takes priority over walkability
        door_target = get_door_target(player.ship_room, nx, ny)
        if door_target:
            new_room, new_x, new_y = door_target
            player.ship_room = new_room
            player.ship_x, player.ship_y = new_x, new_y
            await update_player_ship_state(db, user_id, True, new_room,
                                           ship_x=new_x, ship_y=new_y)
            _room_names = {"helm": "the helm deck",
                           "quarters": "the captain's quarters",
                           "lower_deck": "the lower deck"}
            grid = load_ship_viewport(new_room, new_x, new_y, player=player)
            return (render_grid(grid, player,
                                f"\U0001F6AA You enter {_room_names.get(new_room, new_room)}."),
                    _game_view(guild_id, user_id, player, grid=grid))
        target_grid = load_ship_viewport(player.ship_room, nx, ny)
        target_tile = target_grid[4][4]
        ok, msg = can_move_ship(target_tile)
        if not ok:
            grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
            return render_grid(grid, player, f"\U0001F6AB {msg}"), \
                   _game_view(guild_id, user_id, player, grid=grid)
        player.ship_x, player.ship_y = nx, ny
        await update_player_ship_state(db, user_id, True, player.ship_room,
                                       ship_x=nx, ship_y=ny)
        grid = load_ship_viewport(player.ship_room, nx, ny, player=player)
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

    elif player.in_house:
        _is_ph = (player.house_type == "player_house")
        _house_nav = _ui_state.get(user_id, {}).get("nav_target")
        for _ in range(steps):
            nx, ny = player.house_x + dx, player.house_y + dy
            if _is_ph:
                target = await load_player_house_single_tile(player.house_id, nx, ny, db)
            else:
                target = await load_building_single_tile(player.house_id, nx, ny, db)
            if target.terrain == "b_door":
                # Auto-exit house on walking into door
                vx, vy = player.house_vx, player.house_vy
                player.in_house = False
                player.house_id = None
                await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
                if _is_ph:
                    if player.ph_cave_id is not None:
                        # Return to cave
                        cid = player.ph_cave_id
                        player.cave_id = cid
                        player.cave_x, player.cave_y = vx, vy
                        player.in_cave = True
                        player.ph_cave_id = None
                        await update_player_cave_state(db, user_id, True, cid, vx, vy)
                        grid = await load_cave_viewport(cid, vx, vy, db)
                        return render_grid(grid, player, "You step outside.", nav_target=_house_nav), \
                               await _cave_game_view(guild_id, user_id, player, db, grid=grid)
                    else:
                        # Return to overworld
                        player.world_x, player.world_y = vx, vy
                        await update_player_position(db, user_id, vx, vy)
                        grid = await load_viewport(vx, vy, seed, db)
                        return render_grid(grid, player, "You step outside.", nav_target=_house_nav), \
                               _game_view(guild_id, user_id, player, grid=grid)
                else:
                    # Return to village
                    player.village_x, player.village_y = vx, vy
                    await update_player_village_state(
                        db, user_id, True, player.village_id,
                        vx, vy, player.village_wx, player.village_wy,
                    )
                    grid = await load_village_viewport(player.village_id, vx, vy, db, user_id=user_id)
                    return render_grid(grid, player, "You step outside.", nav_target=_house_nav), \
                           _game_view(guild_id, user_id, player, grid=grid)
            allowed, reason = can_move_building(target)
            if not allowed:
                if _is_ph:
                    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
                else:
                    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
                return render_grid(grid, player, reason, nav_target=_house_nav), _game_view(guild_id, user_id, player, grid=grid)
            player.house_x, player.house_y = nx, ny
            await update_player_house_state(
                db, user_id, True, player.house_id,
                nx, ny, player.house_vx, player.house_vy, player.house_type,
            )
        if _is_ph:
            grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
        else:
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
        # If in edit mode, return edit view
        if _ui_state.get(user_id, {}).get("type") == "house_edit":
            return render_grid(grid, player, nav_target=_house_nav), PlayerHouseEditView(guild_id, user_id)
        return render_grid(grid, player, nav_target=_house_nav), _game_view(guild_id, user_id, player, grid=grid)

    elif player.in_village:
        _vil_nav = _ui_state.get(user_id, {}).get("nav_target")
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
                return render_grid(grid, player, "You leave the village.", nav_target=_vil_nav), _game_view(guild_id, user_id, player, grid=grid)
            allowed, reason = can_move_village(target)
            if not allowed:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
                return render_grid(grid, player, reason, nav_target=_vil_nav), _game_view(guild_id, user_id, player, grid=grid)
            player.village_x, player.village_y = nx, ny
            await update_player_village_state(
                db, user_id, True, player.village_id,
                nx, ny, player.village_wx, player.village_wy,
            )

        # ── Errand quest completion: check current tile ──────────────────────
        cur_vtile = await load_village_single_tile(
            player.village_id, player.village_x, player.village_y, db
        )
        errand_msg = ""
        if cur_vtile.terrain:
            from dwarf_explorer.game.quests import get_completable_errand_quests, complete_quest
            from dwarf_explorer.database.repositories import give_quest_reward
            errand_qs = await get_completable_errand_quests(
                db, user_id, cur_vtile.terrain, player.village_id
            )
            if errand_qs:
                q = errand_qs[0]
                reward = await complete_quest(db, user_id, q["pq_id"])
                if reward:
                    reward_str = await give_quest_reward(
                        db, user_id, reward["gold"], reward["xp"], reward.get("item")
                    )
                    errand_msg = f"📜 Quest complete: **{q['title']}**! {reward_str}"

        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
        return render_grid(grid, player, errand_msg, nav_target=_vil_nav), _game_view(guild_id, user_id, player, grid=grid)

    elif player.in_island:
        from dwarf_explorer.config import ISLAND_WALKABLE
        from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
        ox, oy = player.island_ox, player.island_oy
        px, py = player.ocean_x, player.ocean_y
        nx, ny = px + dx, py + dy

        _island_id, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
        tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
        target_terrain = tile_map.get((nx, ny), "island_void")

        if target_terrain not in ISLAND_WALKABLE:
            grid = load_island_viewport(tiles, px, py)
            return render_grid(grid, player, "You can't go that way."), \
                   _game_view(guild_id, user_id, player, grid=grid)

        player.ocean_x, player.ocean_y = nx, ny
        await update_player_ocean_state(db, user_id, False, nx, ny)
        grid = load_island_viewport(tiles, nx, ny)
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

    elif getattr(player, "in_shipwreck", False):
        _sw_nav = _ui_state.get(user_id, {}).get("nav_target")
        sw_wx = getattr(player, "shipwreck_wx", 0)
        sw_wy = getattr(player, "shipwreck_wy", 0)
        nx, ny = player.shipwreck_x + dx, player.shipwreck_y + dy
        target = get_shipwreck_tile(sw_wx, sw_wy, nx, ny, seed)
        ok, reason = can_move_shipwreck(target)
        if not ok:
            grid = load_shipwreck_viewport(sw_wx, sw_wy, player.shipwreck_x, player.shipwreck_y, seed)
            return render_grid(grid, player, f"\U0001F6AB {reason}"), \
                   _game_view(guild_id, user_id, player, grid=grid)
        player.shipwreck_x, player.shipwreck_y = nx, ny
        # Deduct breath per step
        player.breath = max(0, getattr(player, "breath", BREATH_MAX) - BREATH_PER_STEP)
        await update_player_shipwreck_state(db, user_id, True, sw_wx, sw_wy, nx, ny, player.breath)
        # Check drowning
        if player.breath <= 0:
            # Player drowns — reset to spawn
            player.in_shipwreck = False
            player.shipwreck_wx = 0
            player.shipwreck_wy = 0
            player.shipwreck_x = 0
            player.shipwreck_y = 0
            player.breath = BREATH_MAX
            player.world_x, player.world_y = SPAWN_X, SPAWN_Y
            await update_player_shipwreck_state(db, user_id, False, 0, 0, 0, 0, BREATH_MAX)
            await update_player_position(db, user_id, SPAWN_X, SPAWN_Y)
            grid = await load_viewport(SPAWN_X, SPAWN_Y, seed, db)
            return (render_grid(grid, player,
                                "\U0001F4A7\U0001F480 You ran out of breath and drowned! "
                                "You wake up gasping at the spawn point.",
                                nav_target=_sw_nav),
                    _game_view(guild_id, user_id, player, grid=grid))
        # Exit check: sw_entrance tile at entry position exits the shipwreck
        if target.terrain == "sw_entrance":
            player.in_shipwreck = False
            player.shipwreck_wx = 0
            player.shipwreck_wy = 0
            player.shipwreck_x = 0
            player.shipwreck_y = 0
            player.breath = BREATH_MAX
            await update_player_shipwreck_state(db, user_id, False, 0, 0, 0, 0, BREATH_MAX)
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            return render_grid(grid, player, "\U0001F300 You surface from the sunken ship, gasping for air!",
                               nav_target=_sw_nav), \
                   _game_view(guild_id, user_id, player, grid=grid)
        grid = load_shipwreck_viewport(sw_wx, sw_wy, nx, ny, seed)
        breath_warn = ""
        if player.breath <= 40:
            breath_warn = f"  ⚠️ Low breath: {player.breath}/{BREATH_MAX}!"
        return render_grid(grid, player, breath_warn), _game_view(guild_id, user_id, player, grid=grid)

    elif getattr(player, "in_sky", False):
        _sky_nav = _ui_state.get(user_id, {}).get("nav_target")
        for _ in range(steps):
            nx, ny = player.sky_x + dx, player.sky_y + dy
            target = await load_sky_single_tile(player.sky_id, nx, ny, db)
            from dwarf_explorer.game.player import can_move_sky
            ok, reason = can_move_sky(target)
            if not ok:
                grid = await load_sky_viewport(player.sky_id, player.sky_x, player.sky_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player, grid=grid)

            # Exit: stepping on sky_entrance returns to overworld
            if target.terrain == "sky_entrance":
                wx = getattr(player, "sky_portal_wx", player.world_x)
                wy = getattr(player, "sky_portal_wy", player.world_y)
                player.in_sky = False
                player.sky_id = None
                player.sky_x = player.sky_y = 0
                player.sky_portal_wx = player.sky_portal_wy = 0
                player.world_x, player.world_y = wx, wy
                await update_player_sky_state(db, user_id, False, None, 0, 0)
                await update_player_position(db, user_id, wx, wy)
                grid = await load_viewport(wx, wy, seed, db)
                return (
                    render_grid(grid, player,
                        "🌀 The portal swirls shut beneath you. You're back on solid ground.",
                        nav_target=_sky_nav),
                    _game_view(guild_id, user_id, player, grid=grid),
                )

            player.sky_x, player.sky_y = nx, ny
            await update_player_sky_state(db, user_id, True, player.sky_id, nx, ny,
                                          getattr(player, "sky_portal_wx", 0),
                                          getattr(player, "sky_portal_wy", 0))

            # Random encounter on sky tiles
            if target.terrain in ("sky_cloud", "sky_bridge"):
                enc_rng = _random.Random(hash((user_id, nx, ny, player.sky_id, player.gold)))
                if enc_rng.random() < 0.01:
                    # Pick enemy weighted by their rates (only cloud/bridge-appropriate)
                    if target.terrain == "sky_bridge":
                        enc_rates_filtered = {"storm_hawk": SKY_ENCOUNTER_RATES.get("storm_hawk", 0.06)}
                    else:
                        enc_rates_filtered = {"wind_wisp": SKY_ENCOUNTER_RATES.get("wind_wisp", 0.08)}
                    enemy_type = _roll_encounter(enc_rng, enc_rates_filtered)
                    if enemy_type:
                        grid = await load_sky_viewport(player.sky_id, nx, ny, db)
                        arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type)))
                        arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
                        player.in_combat = True
                        player.combat_enemy_type = enemy_type
                        player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                        player.combat_enemy_x = ex
                        player.combat_enemy_y = ey
                        player.combat_player_x = ARENA_SIZE // 2
                        player.combat_player_y = ARENA_SIZE // 2
                        player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
                        _ui_state[user_id] = {"type": "combat", "arena": arena}
                        await save_combat_state(db, user_id, player)
                        content = render_arena(arena, player)
                        view = CombatView(guild_id, user_id,
                                          trapped=arena["player_trapped"],
                                          moves_left=player.combat_moves_left)
                        return content, view

        grid = await load_sky_viewport(player.sky_id, player.sky_x, player.sky_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

    elif getattr(player, "in_temple", False):
        _temple_nav = _ui_state.get(user_id, {}).get("nav_target")
        _temple_row = await db.fetch_one(
            "SELECT temple_type FROM sky_temples WHERE id=?", (player.temple_id,)
        )
        _is_main = _temple_row and _temple_row["temple_type"] == "main"
        for _ in range(steps):
            nx, ny = player.temple_x + dx, player.temple_y + dy
            target = await load_temple_single_tile(player.temple_id, nx, ny, db, is_main=bool(_is_main))
            if target.terrain == "temple_entrance":
                # Auto-exit temple
                wx, wy = player.temple_wx, player.temple_wy
                player.in_temple = False
                player.temple_id = None
                await update_player_temple_state(db, user_id, False, None, 0, 0)
                player.world_x, player.world_y = wx, wy
                await update_player_position(db, user_id, wx, wy)
                grid = await load_viewport(wx, wy, seed, db)
                return render_grid(grid, player, "You exit the temple.", nav_target=_temple_nav), \
                       _game_view(guild_id, user_id, player, grid=grid)
            if target.terrain not in TEMPLE_WALKABLE:
                grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db, is_main=bool(_is_main))
                return render_grid(grid, player, "⛔ Solid stone."), \
                       _game_view(guild_id, user_id, player, grid=grid)
            player.temple_x, player.temple_y = nx, ny
            await update_player_temple_state(db, user_id, True, player.temple_id,
                                             nx, ny, player.temple_wx, player.temple_wy)
        grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db, is_main=bool(_is_main))
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

    elif getattr(player, "in_maze", False):
        from dwarf_explorer.world.forest import load_maze_viewport, load_maze_single_tile, get_maze_exit_forest_pos
        from dwarf_explorer.game.player import can_move_maze
        for _ in range(steps):
            nx, ny = player.maze_x + dx, player.maze_y + dy
            target = await load_maze_single_tile(player.maze_id, nx, ny, db)
            ok, reason = can_move_maze(target)
            if not ok:
                grid = await load_maze_viewport(player.maze_id, player.maze_x, player.maze_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player, grid=grid)

            # Exit maze → return to forest
            if target.terrain == "maze_exit":
                fx, fy = await get_maze_exit_forest_pos(db, player.forest_id)
                player.in_maze = False
                player.maze_id = None
                player.maze_x = player.maze_y = 0
                player.forest_x, player.forest_y = fx, fy
                await db.execute(
                    "UPDATE players SET in_maze=0, maze_id=NULL, maze_x=0, maze_y=0, "
                    "forest_x=?, forest_y=? WHERE user_id=?",
                    (fx, fy, user_id)
                )
                grid = await load_forest_viewport(player.forest_id, fx, fy, db)
                return render_grid(grid, player,
                    "🌿 You wind back through the hedge and emerge in the ancient forest."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Maze chest / mimic — just move to tile; open on interact
            if target.terrain in ("maze_chest", "maze_mimic"):
                player.maze_x, player.maze_y = nx, ny
                await db.execute(
                    "UPDATE players SET maze_x=?, maze_y=? WHERE user_id=?", (nx, ny, user_id)
                )
                grid = await load_maze_viewport(player.maze_id, nx, ny, db)
                return render_grid(grid, player,
                    "💰 A chest glints in the depths. Press **Open** (⚙️) to search it."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            player.maze_x, player.maze_y = nx, ny
            await db.execute(
                "UPDATE players SET maze_x=?, maze_y=? WHERE user_id=?", (nx, ny, user_id)
            )

            # Random encounter in maze
            enc_rng = _random.Random(hash((user_id, nx, ny, player.maze_id, player.gold)))
            from dwarf_explorer.config import FOREST_ENCOUNTER_MOBS as _fem
            enemy_type = _roll_encounter(enc_rng, _fem)
            if enemy_type:
                grid = await load_maze_viewport(player.maze_id, nx, ny, db)
                arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type)))
                arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
                player.in_combat = True
                player.combat_enemy_type = enemy_type
                player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                player.combat_enemy_x = ex
                player.combat_enemy_y = ey
                player.combat_player_x = ARENA_SIZE // 2
                player.combat_player_y = ARENA_SIZE // 2
                player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
                _ui_state[user_id] = {"type": "combat", "arena": arena}
                await save_combat_state(db, user_id, player)
                content = render_arena(arena, player)
                view = CombatView(guild_id, user_id,
                                  trapped=arena["player_trapped"],
                                  moves_left=player.combat_moves_left)
                return content, view

        grid = await load_maze_viewport(player.maze_id, player.maze_x, player.maze_y, db)
        return render_grid(grid, player), _game_view(guild_id, user_id, player, grid=grid)

    elif getattr(player, "in_bandit_camp", False):
        _bc_nav = _ui_state.get(user_id, {}).get("nav_target")
        from dwarf_explorer.world.bandit_camp import (
            load_camp_viewport as _lbcv_mv,
            generate_camp_grid as _bcgrid_mv,
            get_bandit_positions as _bcbandits,
            BANDIT_CAMP_SIZE as _BCS,
        )
        from dwarf_explorer.game.player import can_move_bandit_camp as _cmbc
        # Look up camp world coords from DB
        _bc_camp_row = await db.fetch_one(
            "SELECT world_x, world_y, max_bandits, bandit_kills, cleared_at "
            "FROM bandit_camps WHERE id=?", (player.bandit_camp_id,)
        )
        _bc_wx = int(_bc_camp_row["world_x"]) if _bc_camp_row else 0
        _bc_wy = int(_bc_camp_row["world_y"]) if _bc_camp_row else 0
        import time as _bctime
        _cleared = _bc_camp_row and _bc_camp_row["cleared_at"] and \
                   (int(_bctime.time()) - int(_bc_camp_row["cleared_at"])) < 86400

        nx_bc, ny_bc = player.bc_x + dx, player.bc_y + dy
        # Bounds check
        if 0 <= nx_bc < _BCS and 0 <= ny_bc < _BCS:
            _bc_full_grid = _bcgrid_mv(_bc_wx, _bc_wy)
            _bc_tile_type = _bc_full_grid[ny_bc][nx_bc]
            from dwarf_explorer.world.generator import TileData as _TileData
            _bc_td = _TileData(terrain=_bc_tile_type, world_x=nx_bc, world_y=ny_bc)
            ok_bc, reason_bc = _cmbc(_bc_td)
        else:
            ok_bc, reason_bc = False, "You can't go that way."
            _bc_tile_type = "bc_void"

        if not ok_bc:
            _bc_grid_err = _lbcv_mv(player.bc_x, player.bc_y, _bc_wx, _bc_wy)
            content = render_grid(_bc_grid_err, player, reason_bc or "That's in the way.")
            return content, _game_view(guild_id, user_id, player, grid=_bc_grid_err)

        # Check exit tile — return to overworld
        if _bc_tile_type == "bc_exit":
            player.in_bandit_camp = False
            player.bandit_camp_id = None
            player.bandit_bribe_remaining = 0
            await db.execute(
                "UPDATE players SET in_bandit_camp=0, bandit_camp_id=NULL, "
                "bandit_bribe_remaining=0 WHERE user_id=?", (user_id,)
            )
            _exit_grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(_exit_grid, player, "🚪 You leave the bandit camp.", nav_target=_bc_nav)
            has_canoe_bc = await _player_has_canoe(db, user_id)
            return content, _game_view(guild_id, user_id, player, grid=_exit_grid, has_canoe=has_canoe_bc)

        # Move player inside the camp
        player.bc_x, player.bc_y = nx_bc, ny_bc
        # Decrement bribe counter
        if player.bandit_bribe_remaining > 0:
            player.bandit_bribe_remaining -= 1
        await db.execute(
            "UPDATE players SET bc_x=?, bc_y=?, bandit_bribe_remaining=? WHERE user_id=?",
            (nx_bc, ny_bc, player.bandit_bribe_remaining, user_id)
        )

        # Check proximity combat (within Manhattan 2 of any bc_bandit, camp not cleared, not bribed)
        _bc_full_grid2 = _bcgrid_mv(_bc_wx, _bc_wy)
        _bandit_positions = _bcbandits(_bc_wx, _bc_wy)
        _nearest_dist = min(
            (abs(bx - player.bc_x) + abs(by - player.bc_y) for bx, by in _bandit_positions),
            default=999
        )
        if _nearest_dist <= 2 and not _cleared and player.bandit_bribe_remaining == 0:
            # Trigger bandit combat
            _bc_view_grid = _lbcv_mv(player.bc_x, player.bc_y, _bc_wx, _bc_wy)
            _ui_state[user_id] = {
                "type": "combat",
                "arena": None,
                "camp_id": player.bandit_camp_id,
                "camp_wx": _bc_wx,
                "camp_wy": _bc_wy,
            }
            arena_rng_bc = _random.Random(hash((user_id, player.bc_x, player.bc_y, "bc_combat")))
            arena_bc, _ex, _ey = build_arena_from_viewport(_bc_view_grid, "bandit", arena_rng_bc)
            _ui_state[user_id]["arena"] = arena_bc
            player.in_combat = True
            player.combat_enemy_type = "bandit"
            player.combat_enemy_hp = ENEMY_STATS["bandit"][0]
            player.combat_enemy_x = _ex
            player.combat_enemy_y = _ey
            player.combat_player_x = ARENA_SIZE // 2
            player.combat_player_y = ARENA_SIZE // 2
            player.combat_moves_left = COMBAT_MOVES_DEFAULT + (
                1 if player.accessory == "ring_of_time" else 0
            )
            await save_combat_state(db, user_id, player)
            content_bc = render_arena(arena_bc, player)
            view_bc = CombatView(guild_id, user_id,
                                 trapped=arena_bc["player_trapped"],
                                 moves_left=player.combat_moves_left,
                                 enemy_type="bandit")
            return content_bc, view_bc

        # Normal move — load viewport
        _bc_vp = _lbcv_mv(player.bc_x, player.bc_y, _bc_wx, _bc_wy)
        # Determine if a bandit is adjacent (for NPC talk button)
        _bc_full3 = _bcgrid_mv(_bc_wx, _bc_wy)
        _bc_adj_bandit = any(
            0 <= player.bc_x + ddx < _BCS and 0 <= player.bc_y + ddy < _BCS
            and _bc_full3[player.bc_y + ddy][player.bc_x + ddx] == "bc_bandit"
            for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]
        )
        _bc_content = render_grid(_bc_vp, player)
        _bc_view = _game_view(
            guild_id, user_id, player, grid=_bc_vp,
            npc_label="\U0001F9B9" if _bc_adj_bandit else "",
            npc_enabled=_bc_adj_bandit,
        )
        return _bc_content, _bc_view

    elif getattr(player, "in_grove", False):
        from dwarf_explorer.world.forest import load_grove_viewport as _lgv2, load_grove_single_tile as _lgst2
        nx, ny = player.grove_x + dx, player.grove_y + dy
        target = await _lgst2(player.grove_id, nx, ny, db)
        ok_move, block_msg = can_move_grove(target)
        if not ok_move:
            grove_grid2 = await _lgv2(player.grove_id, player.grove_x, player.grove_y, db)
            content = render_grid(grove_grid2, player, block_msg or "🌳 Ancient trees bar your path.")
            return content, _game_view(guild_id, user_id, player, grid=grove_grid2)
        # Check grove exit
        if target.terrain == "grove_exit":
            # Return to forest
            player.in_grove = False
            player.grove_id = None
            await db.execute(
                "UPDATE players SET in_grove=0, grove_id=NULL WHERE user_id=?", (user_id,)
            )
            from dwarf_explorer.world.forest import load_forest_viewport as _lfv_gr
            forest_grid2 = await _lfv_gr(player.forest_id, player.forest_x, player.forest_y, db)
            content = render_grid(forest_grid2, player, "🌿 You step back through the bark into the forest.")
            return content, _game_view(guild_id, user_id, player, grid=forest_grid2)
        player.grove_x, player.grove_y = nx, ny
        await db.execute(
            "UPDATE players SET grove_x=?, grove_y=? WHERE user_id=?", (nx, ny, user_id)
        )
        grove_grid3 = await _lgv2(player.grove_id, player.grove_x, player.grove_y, db)
        content = render_grid(grove_grid3, player)
        return content, _game_view(guild_id, user_id, player, grid=grove_grid3)

    elif getattr(player, "in_forest_quest", False):
        from dwarf_explorer.world.forest_quest import (
            load_fq_viewport as _lfqv,
            load_fq_single_tile as _lfqst,
            move_fq_log as _mfql,
            reset_fq_logs as _rfql,
            reset_canal_logs as _rcanal,
            check_and_solve_puzzle as _cfqp,
            check_and_solve_canal as _cfqc,
            step_ents_toward_player as _setp,
            step_ancient_ents as _step_anc,
            get_warden_defeated as _gwdef,
            defeat_warden as _dfwarden,
        )
        from dwarf_explorer.game.player import can_move_forest_quest as _cmfq
        from dwarf_explorer.config import (
            FQ_CHAMBER_Y0 as _FQ_CY0,
            FQ_STREAM_Y as _FQ_SY,
            FQ_ENTRY_X as _FQ_EX, FQ_ENTRY_Y as _FQ_EY,
            FQ_BOSS_CHAMBER_Y0 as _FQ_BCY0, FQ_BOSS_CHAMBER_Y1 as _FQ_BCY1,
            FQ_WARDEN_EYE_CYCLE as _FQ_WEC,
            FQ_WARDEN_EYE_POSITIONS as _FQ_WEP,
            FQ_WARDEN_WARN_TURN as _FQ_WARN, FQ_WARDEN_OPEN_TURN as _FQ_OPEN,
            FQ_WARDEN_CYCLE_LEN as _FQ_CYCLEN,
            FQ_WARDEN_THORN_DAMAGE_MIN as _FQ_DMIN,
            FQ_WARDEN_THORN_DAMAGE_MAX as _FQ_DMAX,
            FQ_ENT_CORE_DROP_ENT as _FQ_ECDE,
            FQ_FINAL_ROOM_Y0 as _FQ_FINAL_Y0,
        )
        fq_id = player.fq_area_id

        # ── Aim mode: arrows move slingshot cursor, not player ────────────
        if getattr(player, "fq_boss_aim_mode", False):
            new_aim_x = player.fq_boss_aim_x + dx
            new_aim_y = player.fq_boss_aim_y + dy
            # Clamp aim cursor within zone bounds
            new_aim_x = max(0, min(FQ_WIDTH - 1, new_aim_x))
            new_aim_y = max(0, min(FQ_HEIGHT - 1, new_aim_y))
            player.fq_boss_aim_x = new_aim_x
            player.fq_boss_aim_y = new_aim_y
            await db.execute(
                "UPDATE players SET fq_boss_aim_x=?, fq_boss_aim_y=? WHERE user_id=?",
                (new_aim_x, new_aim_y, user_id),
            )
            _bs_aim = {
                "eyes": player.fq_boss_eyes,
                "warn_eye": None, "open_eye": None,
            }
            _ac = (new_aim_x, new_aim_y)
            fq_grid_aim = await _lfqv(fq_id, player.fq_x, player.fq_y, db,
                                      boss_state=_bs_aim, aim_cursor=_ac)
            content = render_grid(fq_grid_aim, player,
                f"🎯 Aim cursor: ({new_aim_x}, {new_aim_y}) — press 🪨 Fire to shoot or ❌ Cancel")
            return content, _game_view(guild_id, user_id, player, grid=fq_grid_aim)

        nx_fq, ny_fq = player.fq_x + dx, player.fq_y + dy
        target_fq = await _lfqst(fq_id, nx_fq, ny_fq, db)

        # ── Zone exit (top of corridor) ──────────────────────────────────
        if target_fq.terrain == "fq_exit":
            player.in_forest_quest = False
            player.in_fq_boss_combat = False
            player.fq_area_id = None
            player.fq_x = player.fq_y = 0
            await db.execute(
                "UPDATE players SET in_forest_quest=0, in_fq_boss_combat=0, "
                "fq_area_id=NULL, fq_x=0, fq_y=0 WHERE user_id=?", (user_id,)
            )
            from dwarf_explorer.world.forest import load_forest_viewport as _lfv_fq
            forest_grid_fq = await _lfv_fq(player.forest_id, player.forest_x, player.forest_y, db)
            content = render_grid(forest_grid_fq, player,
                "🌲 You push back through the ancient wall into the forest.")
            return content, _game_view(guild_id, user_id, player, grid=forest_grid_fq)

        # ── Grove exit (post-stream area — placeholder) ───────────────────
        if target_fq.terrain == "fq_grove_exit":
            fq_grid_ge = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
            content = render_grid(fq_grid_ge, player,
                "✨ *A golden light spills from the hidden grove. "
                "The ancient trees seem to welcome you… but the path ahead is not yet revealed.*")
            return content, _game_view(guild_id, user_id, player, grid=fq_grid_ge)

        # ── Boss door (locked) ─────────────────────────────────────────────
        if target_fq.terrain == "fq_boss_door":
            _bst = {"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
            fq_grid_bd = await _lfqv(fq_id, player.fq_x, player.fq_y, db, boss_state=_bst)
            return (render_grid(fq_grid_bd, player,
                    "🚧 The iron-briar gate is sealed. Destroy the Thornwarden to open it."),
                    _game_view(guild_id, user_id, player, grid=fq_grid_bd))

        # ── Reset stone ──────────────────────────────────────────────────
        if target_fq.terrain == "fq_reset":
            await _rfql(db, fq_id)
            player.fq_x, player.fq_y = nx_fq, ny_fq
            await db.execute(
                "UPDATE players SET fq_x=?, fq_y=? WHERE user_id=?",
                (nx_fq, ny_fq, user_id)
            )
            fq_grid_rst = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
            content = render_grid(fq_grid_rst, player,
                "🪨 *The ancient stone hums. The logs roll back to their starting positions.*")
            return content, _game_view(guild_id, user_id, player, grid=fq_grid_rst)

        # ── Canal gate (locked until puzzle solved) ──────────────────────
        if target_fq.terrain == "fq_canal_gate":
            fq_grid_cg = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
            return (render_grid(fq_grid_cg, player,
                    "🔒 The canal gate is sealed. Push both blocks onto their ⭕ targets to open it."),
                    _game_view(guild_id, user_id, player, grid=fq_grid_cg))

        # ── Canal reset stone (step-on resets canal blocks) ──────────────
        if target_fq.terrain == "fq_canal_reset":
            await _rcanal(db, fq_id)
            player.fq_x, player.fq_y = nx_fq, ny_fq
            await db.execute(
                "UPDATE players SET fq_x=?, fq_y=? WHERE user_id=?",
                (nx_fq, ny_fq, user_id)
            )
            fq_grid_cr = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
            content = render_grid(fq_grid_cr, player,
                "🪨 *The reset stone hums. The canal blocks slide back to their starting positions.*")
            return content, _game_view(guild_id, user_id, player, grid=fq_grid_cr)

        # ── Log / canal-block push mechanic ──────────────────────────────
        if target_fq.terrain == "fq_log":
            beyond_x, beyond_y = nx_fq + dx, ny_fq + dy
            beyond = await _lfqst(fq_id, beyond_x, beyond_y, db)
            _sokoban_valid = ("fq_puzzle_floor", "fq_log_target")
            _canal_valid   = ("fq_canal_floor",  "fq_canal_target")
            if beyond.terrain in _sokoban_valid + _canal_valid:
                await _mfql(db, fq_id, nx_fq, ny_fq, beyond_x, beyond_y)
                player.fq_x, player.fq_y = nx_fq, ny_fq
                await db.execute(
                    "UPDATE players SET fq_x=?, fq_y=? WHERE user_id=?",
                    (nx_fq, ny_fq, user_id)
                )
                if beyond.terrain == "fq_log_target":
                    solved = await _cfqp(db, fq_id)
                    if solved:
                        # Advance quest stage if needed
                        if getattr(player, "fq_quest_stage", "none") == "map_marked":
                            player.fq_quest_stage = "puzzle_solved"
                            await db.execute(
                                "UPDATE players SET fq_quest_stage='puzzle_solved' WHERE user_id=?",
                                (user_id,)
                            )
                        fq_grid_push = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                        content = render_grid(fq_grid_push, player,
                            "🪵 *The log thuds into place over the stream! "
                            "Ancient stepping stones rise — the way across is open.*")
                    else:
                        fq_grid_push = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                        content = render_grid(fq_grid_push, player, "🪵 You heave the log forward.")
                elif beyond.terrain == "fq_canal_target":
                    canal_solved = await _cfqc(db, fq_id)
                    if canal_solved:
                        _cstage = getattr(player, "fq_quest_stage", "none")
                        if _cstage not in ("canal_solved", "quest_complete"):
                            player.fq_quest_stage = "canal_solved"
                            await db.execute(
                                "UPDATE players SET fq_quest_stage='canal_solved' WHERE user_id=?",
                                (user_id,)
                            )
                        fq_grid_push = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                        content = render_grid(fq_grid_push, player,
                            "💧 *Both canal blocks slot into place. A deep rumble echoes — "
                            "the 🔓 canal gate grinds open!*")
                    else:
                        fq_grid_push = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                        content = render_grid(fq_grid_push, player,
                            "💧 The block splashes into the canal channel.")
                else:
                    fq_grid_push = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                    content = render_grid(fq_grid_push, player, "🪵 You heave the block forward.")
                return content, _game_view(guild_id, user_id, player, grid=fq_grid_push)
            else:
                fq_grid_nb = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                _ledge_msg = (
                    "🪵 The ledge is too steep — the block can't go that way."
                    if beyond.terrain in ("fq_wall", "fq_obstacle", "fq_floor", "fq_canal_floor",
                                          "fq_stream", "fq_stream_ford", "fq_log")
                    else "🪵 Something blocks the log from moving that way."
                )
                return render_grid(fq_grid_nb, player, _ledge_msg), \
                       _game_view(guild_id, user_id, player, grid=fq_grid_nb)

        # ── Normal movement ──────────────────────────────────────────────
        ok_fq, block_fq = _cmfq(target_fq)
        if not ok_fq:
            _bst_blk = ({"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
                        if getattr(player, "in_fq_boss_combat", False) else None)
            fq_grid_blk = await _lfqv(fq_id, player.fq_x, player.fq_y, db, boss_state=_bst_blk)
            return render_grid(fq_grid_blk, player, block_fq), \
                   _game_view(guild_id, user_id, player, grid=fq_grid_blk)

        _was_in_chamber = (player.fq_y >= _FQ_CY0)
        _entering_chamber = (ny_fq >= _FQ_CY0) and not _was_in_chamber
        _was_in_boss     = (player.fq_y >= _FQ_BCY0)
        _entering_boss   = (ny_fq >= _FQ_BCY0) and not _was_in_boss \
                           and not getattr(player, "in_fq_boss_combat", False)

        player.fq_x, player.fq_y = nx_fq, ny_fq
        await db.execute(
            "UPDATE players SET fq_x=?, fq_y=? WHERE user_id=?",
            (nx_fq, ny_fq, user_id)
        )

        # Reset Sokoban logs when player re-enters the puzzle chamber
        _extra_fq_msg = ""
        if _entering_chamber:
            await _rfql(db, fq_id)
            _extra_fq_msg = ("🌿 *You step into the ancient hollow. "
                             "The chamber hums and the logs roll back to their resting places…*\n")

        # Boss chamber entry — initialise Thornwarden combat
        if _entering_boss:
            _warden_already_dead = await _gwdef(db, fq_id)
            if not _warden_already_dead:
                player.in_fq_boss_combat = True
                player.fq_boss_turn = 0
                player.fq_boss_eye_idx = 0
                player.fq_boss_eyes = "1111"
                player.fq_boss_aim_mode = False
                player.fq_boss_aim_x = player.fq_x
                player.fq_boss_aim_y = player.fq_y
                await db.execute(
                    "UPDATE players SET in_fq_boss_combat=1, fq_boss_turn=0, "
                    "fq_boss_eye_idx=0, fq_boss_eyes='1111', fq_boss_aim_mode=0, "
                    "fq_boss_aim_x=?, fq_boss_aim_y=? WHERE user_id=?",
                    (player.fq_x, player.fq_y, user_id),
                )
                _extra_fq_msg = (
                    "🌿 *The air grows thick with briars. Something vast stirs in the dark...*\n\n"
                    "**THE THORNWARDEN AWAKENS!** 🟤🟤🟤🟤 Four dormant eyes pulse with cold light.\n"
                    "🎯 Equip your slingshot and shoot an eye **just before it opens** to destroy it!"
                )

        # Step regular ents (corridor section only)
        if player.fq_y < _FQ_CY0:
            combat_tiles = await _setp(db, fq_id, player.fq_x, player.fq_y)
            if combat_tiles:
                fq_grid_c = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                _ent_arena_rng = _random.Random(
                    hash((user_id, player.fq_x, player.fq_y, "ent_combat"))
                )
                arena_ent, _eex, _eey = build_arena_from_viewport(fq_grid_c, "ent", _ent_arena_rng)
                _ui_state[user_id] = {"type": "combat", "arena": arena_ent}
                player.in_combat = True
                player.combat_enemy_type = "ent"
                player.combat_enemy_hp = ENEMY_STATS["ent"][0]
                player.combat_enemy_x = _eex
                player.combat_enemy_y = _eey
                player.combat_player_x = ARENA_SIZE // 2
                player.combat_player_y = ARENA_SIZE // 2
                player.combat_moves_left = COMBAT_MOVES_DEFAULT + (
                    1 if player.accessory == "ring_of_time" else 0
                )
                await save_combat_state(db, user_id, player)
                content_ent = render_arena(arena_ent, player)
                view_ent = CombatView(guild_id, user_id,
                                      trapped=arena_ent["player_trapped"],
                                      moves_left=player.combat_moves_left,
                                      enemy_type="ent")
                return content_ent, view_ent

        # Step ancient ents (final room only)
        if player.fq_y >= _FQ_FINAL_Y0:
            anc_combat_tiles = await _step_anc(db, fq_id, player.fq_x, player.fq_y)
            if anc_combat_tiles:
                fq_grid_ac = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                _anc_rng = _random.Random(
                    hash((user_id, player.fq_x, player.fq_y, "ancient_ent_combat"))
                )
                arena_anc, _aex, _aey = build_arena_from_viewport(
                    fq_grid_ac, "ancient_ent", _anc_rng
                )
                _ui_state[user_id] = {"type": "combat", "arena": arena_anc}
                player.in_combat = True
                player.combat_enemy_type = "ancient_ent"
                player.combat_enemy_hp = ENEMY_STATS["ancient_ent"][0]
                player.combat_enemy_x = _aex
                player.combat_enemy_y = _aey
                player.combat_player_x = ARENA_SIZE // 2
                player.combat_player_y = ARENA_SIZE // 2
                player.combat_moves_left = COMBAT_MOVES_DEFAULT + (
                    1 if player.accessory == "ring_of_time" else 0
                )
                await save_combat_state(db, user_id, player)
                content_anc = render_arena(arena_anc, player)
                view_anc = CombatView(guild_id, user_id,
                                      trapped=arena_anc["player_trapped"],
                                      moves_left=player.combat_moves_left,
                                      enemy_type="ancient_ent")
                return content_anc, view_anc

        # Warden turn processing (after every move in boss combat)
        _warn_eye_mv = None
        _open_eye_mv = None
        if getattr(player, "in_fq_boss_combat", False) and not _entering_boss:
            player.fq_boss_turn = (player.fq_boss_turn + 1) % _FQ_CYCLEN

            if player.fq_boss_turn == _FQ_WARN:
                # Find next alive eye
                for _wi in range(4):
                    _widx = (player.fq_boss_eye_idx + _wi) % 4
                    if player.fq_boss_eyes[_widx] == "1":
                        _warn_eye_mv = _FQ_WEC[_widx]
                        player.fq_boss_eye_idx = _widx
                        _wpos = _FQ_WEP[_warn_eye_mv]
                        _extra_fq_msg = (
                            f"⚠️ *The Thornwarden's **{_warn_eye_mv}** eye begins to glow…* "
                            f"Position: ({_wpos[0]}, {_wpos[1]})\n"
                            "🎯 Aim your slingshot at it NOW before it opens!"
                        )
                        break
                await db.execute(
                    "UPDATE players SET fq_boss_turn=?, fq_boss_eye_idx=? WHERE user_id=?",
                    (player.fq_boss_turn, player.fq_boss_eye_idx, user_id),
                )

            elif player.fq_boss_turn == _FQ_OPEN:
                _open_eye_mv = _FQ_WEC[player.fq_boss_eye_idx]
                _thorn_dmg = _random.randint(_FQ_DMIN, _FQ_DMAX)
                player.hp = max(0, player.hp - _thorn_dmg)
                _extra_fq_msg = (
                    f"🔴 *The **{_open_eye_mv}** eye snaps open — thorns lash out!*\n"
                    f"💥 You take **{_thorn_dmg} damage**! ({player.hp}/{player.max_hp} HP)"
                )
                # Advance to next alive eye and reset turn
                player.fq_boss_turn = 0
                for _ni in range(1, 5):
                    _nidx = (player.fq_boss_eye_idx + _ni) % 4
                    if player.fq_boss_eyes[_nidx] == "1":
                        player.fq_boss_eye_idx = _nidx
                        break
                await db.execute(
                    "UPDATE players SET hp=?, fq_boss_turn=?, fq_boss_eye_idx=? WHERE user_id=?",
                    (player.hp, player.fq_boss_turn, player.fq_boss_eye_idx, user_id),
                )
                if player.hp <= 0:
                    # Player died — handled by caller; return death state
                    fq_grid_d = await _lfqv(fq_id, player.fq_x, player.fq_y, db)
                    return (render_grid(fq_grid_d, player,
                            "💀 The thorns pierce deep. Darkness claims you..."),
                            _game_view(guild_id, user_id, player, grid=fq_grid_d))
            else:
                await db.execute(
                    "UPDATE players SET fq_boss_turn=? WHERE user_id=?",
                    (player.fq_boss_turn, user_id),
                )

        _bst_mv = ({"eyes": player.fq_boss_eyes,
                    "warn_eye": _warn_eye_mv, "open_eye": _open_eye_mv}
                   if getattr(player, "in_fq_boss_combat", False) else None)
        fq_grid_mv = await _lfqv(fq_id, player.fq_x, player.fq_y, db, boss_state=_bst_mv)
        content = render_grid(fq_grid_mv, player, _extra_fq_msg or None)
        return content, _game_view(guild_id, user_id, player, grid=fq_grid_mv)

    elif getattr(player, "in_forest", False) and not getattr(player, "in_tree_city", False) and not getattr(player, "in_hermit_hut", False):
        _for_nav = _ui_state.get(user_id, {}).get("nav_target")
        from dwarf_explorer.world.forest import (
            load_forest_viewport, load_forest_single_tile,
            get_forest_exit_world, get_maze_for_forest,
        )
        from dwarf_explorer.game.player import can_move_forest
        print(f"[DBG forest_handler] entered forest handler fid={player.forest_id} pos=({player.forest_x},{player.forest_y}) dx={dx} dy={dy}", flush=True)
        for _ in range(steps):
            nx, ny = player.forest_x + dx, player.forest_y + dy
            target = await load_forest_single_tile(player.forest_id, nx, ny, db)
            ok, reason = can_move_forest(target)
            print(f"[DBG forest_handler] target=({nx},{ny}) terrain={target.terrain} ok={ok} reason={reason!r}", flush=True)
            if not ok:
                # Wayerwood secret passage
                if (target.terrain == "fst_tree"
                        and (player.hand_1 == "attuned_wayerwood" or player.hand_2 == "attuned_wayerwood")):
                    from dwarf_explorer.world.forest import get_wayerwood_target as _gwwt2
                    _ww_tgt = await _gwwt2(player.forest_id, db)
                    if _ww_tgt and nx == _ww_tgt[0] and ny == _ww_tgt[1]:
                        # Enter the grove!
                        from dwarf_explorer.world.forest import (
                            ensure_grove_built as _egb, load_grove_viewport as _lgv,
                        )
                        _grove_id = await _egb(player.forest_id, db)
                        # Enter at south exit tile of grove (cy + R = 9+7=16, cx=9)
                        _gx, _gy = 9, 16
                        player.in_grove = True
                        player.grove_id = _grove_id
                        player.grove_x = _gx
                        player.grove_y = _gy
                        player.grove_forest_id = player.forest_id
                        await db.execute(
                            "UPDATE players SET in_grove=1, grove_id=?, grove_x=?, grove_y=?, "
                            "grove_forest_id=?, forest_x=?, forest_y=? WHERE user_id=?",
                            (_grove_id, _gx, _gy, player.forest_id,
                             player.forest_x, player.forest_y, user_id),
                        )
                        _grove_grid = await _lgv(_grove_id, _gx, _gy, db)
                        return (
                            render_grid(
                                _grove_grid, player,
                                "🌿 *The wayerwood glows white — the bark parts before you...*\n"
                                "You step through into a hidden grove.",
                            ),
                            _game_view(guild_id, user_id, player, grid=_grove_grid),
                        )
                # Forest Quest entrance: fst_fq_entrance tile is passable when
                # quest is hermit_met or further; fst_tree coordinate fallback
                # also works for worlds generated before the tile type existed.
                _fq_stage_now = getattr(player, "fq_quest_stage", "none")
                _is_fq_entrance_tile = target.terrain == "fst_fq_entrance"
                _FQ_VALID_ENTRY_STAGES = (
                    "hermit_met", "wayerwood_crafted",
                    "map_marked", "puzzle_solved",
                    "warden_defeated", "canal_solved", "quest_complete",
                )
                _is_fq_entry_eligible = _is_fq_entrance_tile and _fq_stage_now in _FQ_VALID_ENTRY_STAGES
                if not _is_fq_entry_eligible and target.terrain == "fst_tree":
                    # Legacy coordinate-based check (worlds where entrance is a plain tree)
                    if _fq_stage_now in _FQ_VALID_ENTRY_STAGES:
                        from dwarf_explorer.world.forest_quest import get_fq_entry_info as _gfqei_leg
                        _fq_efid_l, _fq_efx_l, _fq_efy_l = await _gfqei_leg(db, guild_id)
                        if (_fq_efid_l == player.forest_id
                                and nx == _fq_efx_l and ny == _fq_efy_l):
                            _is_fq_entry_eligible = True
                if _is_fq_entry_eligible:
                    from dwarf_explorer.world.forest_quest import (
                        get_fq_entry_info as _gfqei,
                        get_or_create_fq_area as _gfqa,
                        load_fq_viewport as _lfqv_entry,
                    )
                    fq_id_entry = await _gfqa(
                        db, guild_id, player.forest_id, nx, ny
                    )
                    from dwarf_explorer.config import FQ_ENTRY_X as _FQEntX, FQ_ENTRY_Y as _FQEntY
                    player.in_forest_quest = True
                    player.fq_area_id = fq_id_entry
                    player.fq_x = _FQEntX
                    player.fq_y = _FQEntY + 1   # one step inside (exit tile is at 0)
                    player.forest_x, player.forest_y = nx, ny  # remember re-entry tile
                    # Advance quest stage: hermit_met/wayerwood_crafted → map_marked on first entry
                    _fq_new_stage = _fq_stage_now
                    if _fq_stage_now in ("hermit_met", "wayerwood_crafted"):
                        _fq_new_stage = "map_marked"
                        player.fq_quest_stage = "map_marked"
                        from dwarf_explorer.game.quests import (
                            update_forest_depths_quest_target as _ufdqt_entry,
                        )
                        # Null out tracker — player is inside now, no overworld marker needed
                        await _ufdqt_entry(db, user_id, None, None)
                    await db.execute(
                        "UPDATE players SET in_forest_quest=1, fq_area_id=?, "
                        "fq_x=?, fq_y=?, forest_x=?, forest_y=?, fq_quest_stage=? "
                        "WHERE user_id=?",
                        (fq_id_entry, player.fq_x, player.fq_y,
                         nx, ny, _fq_new_stage, user_id),
                    )
                    _fq_entry_grid = await _lfqv_entry(fq_id_entry, player.fq_x, player.fq_y, db)
                    return (
                        render_grid(
                            _fq_entry_grid, player,
                            "🌳 *A gap in the ancient wall — just as the hermit described. "
                            "You push through into the unknown.*",
                        ),
                        _game_view(guild_id, user_id, player, grid=_fq_entry_grid),
                    )
                grid = await load_forest_viewport(player.forest_id, player.forest_x, player.forest_y, db)
                return render_grid(grid, player, reason), _game_view(guild_id, user_id, player, grid=grid)

            # Exit forest → return to overworld
            if target.terrain == "fst_exit":
                wx, wy = await get_forest_exit_world(db, player.forest_id, nx, ny)
                if wx is None:
                    wx, wy = player.forest_wx, player.forest_wy
                player.in_forest = False
                player.forest_id = None
                player.forest_x = player.forest_y = 0
                player.world_x, player.world_y = wx, wy
                await db.execute(
                    "UPDATE players SET in_forest=0, forest_id=NULL, forest_x=0, forest_y=0, "
                    "world_x=?, world_y=? WHERE user_id=?",
                    (wx, wy, user_id)
                )
                grid = await load_viewport(wx, wy, seed, db)
                return render_grid(grid, player,
                    "🌲 You push through the undergrowth and emerge back into the open world.",
                    nav_target=_for_nav), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Enter maze
            if target.terrain == "fst_maze_door":
                player.forest_x, player.forest_y = nx, ny
                maze_id = await get_maze_for_forest(db, player.forest_id)
                if maze_id is None:
                    grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                    return render_grid(grid, player,
                        "🌀 The hedge door seems sealed shut. The maze remains out of reach."), \
                           _game_view(guild_id, user_id, player, grid=grid)
                player.in_maze = True
                player.maze_id = maze_id
                # Entry position stored in maze_areas; fall back to (1,1) for legacy mazes
                _maze_meta = await db.fetch_one(
                    "SELECT entry_x, entry_y FROM maze_areas WHERE maze_id=?", (maze_id,)
                )
                _mex = _maze_meta["entry_x"] if _maze_meta and _maze_meta["entry_x"] else 1
                _mey = _maze_meta["entry_y"] if _maze_meta and _maze_meta["entry_y"] else 1
                player.maze_x, player.maze_y = _mex, _mey
                await db.execute(
                    "UPDATE players SET in_maze=1, maze_id=?, maze_x=?, maze_y=?, "
                    "forest_x=?, forest_y=? WHERE user_id=?",
                    (maze_id, _mex, _mey, nx, ny, user_id)
                )
                from dwarf_explorer.world.forest import load_maze_viewport as _lmv
                grid = await _lmv(maze_id, _mex, _mey, db)
                return render_grid(grid, player,
                    "🌀 The hedge twists around you — you've entered the **Forest Maze**. "
                    "Find the treasure chest hidden within its depths."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Forest chest — stop on tile and prompt interact
            if target.terrain == "fst_chest":
                player.forest_x, player.forest_y = nx, ny
                await db.execute(
                    "UPDATE players SET forest_x=?, forest_y=? WHERE user_id=?", (nx, ny, user_id)
                )
                grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                return render_grid(grid, player,
                    "📦 A cache hidden in the roots. Press ⚙️ to open it."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Forest mimic — looks like a chest; springs to life on interact
            if target.terrain == "fst_mimic":
                player.forest_x, player.forest_y = nx, ny
                await db.execute(
                    "UPDATE players SET forest_x=?, forest_y=? WHERE user_id=?", (nx, ny, user_id)
                )
                grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                return render_grid(grid, player,
                    "📦 A chest sits in the clearing. Press ⚙️ to open it."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Nut tree — prompt interact
            if target.terrain == "fst_nut_tree":
                player.forest_x, player.forest_y = nx, ny
                await db.execute(
                    "UPDATE players SET forest_x=?, forest_y=? WHERE user_id=?", (nx, ny, user_id)
                )
                grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                return render_grid(grid, player,
                    "🌰 A nut tree droops with ripe clusters. Interact (⚙️) to gather forest nuts."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Ancient tree — prompt interact
            if target.terrain == "fst_ancient_tree":
                player.forest_x, player.forest_y = nx, ny
                await db.execute(
                    "UPDATE players SET forest_x=?, forest_y=? WHERE user_id=?", (nx, ny, user_id)
                )
                grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                has_can = player.hand_1 == "watering_can" or player.hand_2 == "watering_can"
                if has_can:
                    return render_grid(grid, player,
                        "🌲 The **Ancient Tree** pulses with old magic. Your watering can glows. "
                        "Interact (⚙️) to water it."), \
                           _game_view(guild_id, user_id, player, grid=grid)
                return render_grid(grid, player,
                    "🌲 The **Ancient Tree** towers before you, older than memory. "
                    "Etched at its base: *'Water me, and I shall give you what the forest guards.'*"), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Hermit hut — stand on tile, prompt to enter
            if target.terrain == "fst_hermit_house":
                player.forest_x, player.forest_y = nx, ny
                await db.execute(
                    "UPDATE players SET forest_x=?, forest_y=? WHERE user_id=?",
                    (nx, ny, user_id),
                )
                grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                return render_grid(grid, player,
                    "🛖 The hermit's hut looms before you. Press ⚙️ to enter."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Tree city — stand on tile, prompt to enter
            if target.terrain == "fst_tree_city":
                player.forest_x, player.forest_y = nx, ny
                await db.execute(
                    "UPDATE players SET forest_x=?, forest_y=? WHERE user_id=?",
                    (nx, ny, user_id),
                )
                grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                return render_grid(grid, player,
                    "🌲 The great wooden gate of the **Tree City** stands before you. Press ⚙️ to enter."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            player.forest_x, player.forest_y = nx, ny
            await db.execute(
                "UPDATE players SET forest_x=?, forest_y=? WHERE user_id=?", (nx, ny, user_id)
            )

            # Random forest encounter
            enc_rng = _random.Random(hash((user_id, nx, ny, player.forest_id, player.gold)))
            from dwarf_explorer.config import FOREST_ENCOUNTER_MOBS as _fem2
            enemy_type = _roll_encounter(enc_rng, _fem2)
            if enemy_type:
                grid = await load_forest_viewport(player.forest_id, nx, ny, db)
                arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type)))
                arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
                player.in_combat = True
                player.combat_enemy_type = enemy_type
                player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                player.combat_enemy_x = ex
                player.combat_enemy_y = ey
                player.combat_player_x = ARENA_SIZE // 2
                player.combat_player_y = ARENA_SIZE // 2
                player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
                _ui_state[user_id] = {"type": "combat", "arena": arena}
                await save_combat_state(db, user_id, player)
                content = render_arena(arena, player)
                view = CombatView(guild_id, user_id,
                                  trapped=arena["player_trapped"],
                                  moves_left=player.combat_moves_left)
                return content, view

        print(f"[DBG forest_handler] loading viewport fid={player.forest_id} final_pos=({player.forest_x},{player.forest_y})", flush=True)
        grid = await load_forest_viewport(player.forest_id, player.forest_x, player.forest_y, db)
        _dbg_terrains = [grid[r][c].terrain for r in range(len(grid)) for c in range(len(grid[r]))]
        _dbg_tree_count = sum(1 for t in _dbg_terrains if t == "fst_tree")
        print(f"[DBG forest_handler] grid tiles={len(_dbg_terrains)} trees={_dbg_tree_count} sample={_dbg_terrains[:9]}", flush=True)
        return render_grid(grid, player, None), _game_view(guild_id, user_id, player, grid=grid)

    elif getattr(player, "in_tree_city", False):
        from dwarf_explorer.world.forest import (
            load_tree_city_viewport as _ltcv3,
            load_tree_city_single_tile as _ltcs,
            ensure_tree_city_built,
        )
        _tc_nav = _ui_state.get(user_id, {}).get("nav_target")
        _tc_rebuilt = await ensure_tree_city_built(player.tc_forest_id, db)
        if _tc_rebuilt:
            player.tc_floor = 1
            player.tc_x, player.tc_y = 14, 21
            await db.execute(
                "UPDATE players SET tc_floor=1, tc_x=14, tc_y=21 WHERE user_id=?", (user_id,)
            )

        for _ in range(steps):
            nx, ny = player.tc_x + dx, player.tc_y + dy
            target = await _ltcs(player.tc_forest_id, player.tc_floor, nx, ny, db)
            if target.terrain not in TC_WALKABLE:
                grid = await _ltcv3(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
                _tc_block_msg = "🌲 Solid bark walls — you can't push through."
                if target.terrain in ("tc_shop", "tc_elder", "tc_villager"):
                    _tc_block_msg = "🛍️ Step adjacent and use the action button to interact."
                elif target.terrain in ("tc_counter", "tc_table", "tc_lantern", "tc_plant",
                                        "tc_barrel", "tc_bookshelf", "tc_shrine"):
                    _tc_block_msg = "🌲 Something is in the way."
                return render_grid(grid, player, _tc_block_msg, nav_target=_tc_nav), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Exit door (floor 1 only) → back to forest
            if target.terrain == "tc_door":
                fx = player.forest_x
                fy = player.forest_y
                fid = player.tc_forest_id
                player.in_tree_city = False
                player.tc_forest_id = None
                player.tc_floor = 1
                player.tc_x = player.tc_y = 0
                await db.execute(
                    "UPDATE players SET in_tree_city=0, tc_forest_id=NULL, tc_floor=1, "
                    "tc_x=0, tc_y=0, forest_x=?, forest_y=? WHERE user_id=?",
                    (fx, fy, user_id)
                )
                from dwarf_explorer.world.forest import load_forest_viewport as _lfv3
                grid = await _lfv3(fid, fx, fy, db)
                return render_grid(grid, player,
                    "🚪 You step out of the Tree City back into the forest.",
                    nav_target=_tc_nav), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Stairs up
            if target.terrain == "tc_stair_up":
                if player.tc_floor < 4:
                    player.tc_floor += 1
                    player.tc_x, player.tc_y = 14, 16   # appear near stair_down on next floor
                    await db.execute(
                        "UPDATE players SET tc_floor=?, tc_x=14, tc_y=16 WHERE user_id=?",
                        (player.tc_floor, user_id)
                    )
                    grid = await _ltcv3(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
                    floor_names = {1: "Ground Hall", 2: "Living Quarters", 3: "Upper Hall", 4: "Elder's Chamber"}
                    fname = floor_names.get(player.tc_floor, f"Floor {player.tc_floor}")
                    return render_grid(grid, player,
                        f"🔼 You climb the stairs to the **{fname}**.", nav_target=_tc_nav), \
                           _game_view(guild_id, user_id, player, grid=grid)
                else:
                    grid = await _ltcv3(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
                    return render_grid(grid, player, "🌲 This is the highest floor.", nav_target=_tc_nav), \
                           _game_view(guild_id, user_id, player, grid=grid)

            # Stairs down
            if target.terrain == "tc_stair_down":
                if player.tc_floor > 1:
                    player.tc_floor -= 1
                    player.tc_x, player.tc_y = 14, 9   # appear near stair_up on previous floor
                    await db.execute(
                        "UPDATE players SET tc_floor=?, tc_x=14, tc_y=9 WHERE user_id=?",
                        (player.tc_floor, user_id)
                    )
                    grid = await _ltcv3(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
                    floor_names = {1: "Ground Hall", 2: "Living Quarters", 3: "Upper Hall", 4: "Elder's Chamber"}
                    fname = floor_names.get(player.tc_floor, f"Floor {player.tc_floor}")
                    return render_grid(grid, player,
                        f"🔽 You descend to the **{fname}**.", nav_target=_tc_nav), \
                           _game_view(guild_id, user_id, player, grid=grid)
                else:
                    grid = await _ltcv3(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
                    return render_grid(grid, player, "🌲 This is the ground floor.", nav_target=_tc_nav), \
                           _game_view(guild_id, user_id, player, grid=grid)

            player.tc_x, player.tc_y = nx, ny
            await db.execute(
                "UPDATE players SET tc_x=?, tc_y=? WHERE user_id=?", (nx, ny, user_id)
            )

        grid = await _ltcv3(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
        return render_grid(grid, player, nav_target=_tc_nav), _game_view(guild_id, user_id, player, grid=grid)

    elif getattr(player, "in_hermit_hut", False):
        from dwarf_explorer.world.hermit_hut import (
            load_hut_viewport as _lhv_mv,
            load_hut_single_tile as _lhst_mv,
            ensure_hermit_hut_built as _ehb_mv,
            HUT_F1_STAIR_X, HUT_F1_STAIR_Y,
            HUT_F2_STAIR_X, HUT_F2_STAIR_Y,
            HUT_F2_ENTRY_X, HUT_F2_ENTRY_Y,
            HUT_F1_RETURN_X, HUT_F1_RETURN_Y,
            HUT_DOOR_X, HUT_DOOR_Y,
        )
        from dwarf_explorer.config import HERMIT_HUT_WALKABLE as _HHW
        await _ehb_mv(player.hermit_hut_forest_id, db)

        for _ in range(steps):
            nx, ny = player.hermit_hut_x + dx, player.hermit_hut_y + dy
            target = await _lhst_mv(player.hermit_hut_forest_id, player.hermit_hut_floor, nx, ny, db)
            if target.terrain not in _HHW:
                grid = await _lhv_mv(player.hermit_hut_forest_id, player.hermit_hut_floor,
                                     player.hermit_hut_x, player.hermit_hut_y, db)
                _hh_msg = (
                    "🔥 The old hearth radiates heat — you can't step there."
                    if target.terrain == "b_stove"
                    else "🪵 Rough log walls bar your path."
                )
                return render_grid(grid, player, _hh_msg), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Exit door → back to forest
            if target.terrain == "b_door":
                fx, fy = player.forest_x, player.forest_y
                fid = player.hermit_hut_forest_id
                player.in_hermit_hut = False
                player.hermit_hut_forest_id = None
                player.hermit_hut_floor = 1
                player.hermit_hut_x = player.hermit_hut_y = 0
                await db.execute(
                    "UPDATE players SET in_hermit_hut=0, hermit_hut_forest_id=NULL, "
                    "hermit_hut_floor=1, hermit_hut_x=0, hermit_hut_y=0, "
                    "forest_x=?, forest_y=? WHERE user_id=?",
                    (fx, fy, user_id),
                )
                from dwarf_explorer.world.forest import load_forest_viewport as _lfv_hh
                grid = await _lfv_hh(fid, fx, fy, db)
                return render_grid(grid, player,
                    "🚪 You step out of the hermit's hut back into the forest."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Stair up → floor 2
            if target.terrain == "hut_stair_up":
                player.hermit_hut_floor = 2
                player.hermit_hut_x, player.hermit_hut_y = HUT_F2_ENTRY_X, HUT_F2_ENTRY_Y
                await db.execute(
                    "UPDATE players SET hermit_hut_floor=2, hermit_hut_x=?, hermit_hut_y=? WHERE user_id=?",
                    (HUT_F2_ENTRY_X, HUT_F2_ENTRY_Y, user_id),
                )
                grid = await _lhv_mv(player.hermit_hut_forest_id, 2, HUT_F2_ENTRY_X, HUT_F2_ENTRY_Y, db)
                return render_grid(grid, player,
                    "🔼 You climb the creaky stairs into the **upper room**. "
                    "Vines and old tomes fill every corner."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Stair down → floor 1
            if target.terrain == "hut_stair_down":
                player.hermit_hut_floor = 1
                player.hermit_hut_x, player.hermit_hut_y = HUT_F1_RETURN_X, HUT_F1_RETURN_Y
                await db.execute(
                    "UPDATE players SET hermit_hut_floor=1, hermit_hut_x=?, hermit_hut_y=? WHERE user_id=?",
                    (HUT_F1_RETURN_X, HUT_F1_RETURN_Y, user_id),
                )
                grid = await _lhv_mv(player.hermit_hut_forest_id, 1, HUT_F1_RETURN_X, HUT_F1_RETURN_Y, db)
                return render_grid(grid, player,
                    "🔽 You descend back to the ground floor of the hut."), \
                       _game_view(guild_id, user_id, player, grid=grid)

            # Normal step
            player.hermit_hut_x, player.hermit_hut_y = nx, ny
            await db.execute(
                "UPDATE players SET hermit_hut_x=?, hermit_hut_y=? WHERE user_id=?",
                (nx, ny, user_id),
            )

        grid = await _lhv_mv(player.hermit_hut_forest_id, player.hermit_hut_floor,
                              player.hermit_hut_x, player.hermit_hut_y, db)
        return render_grid(grid, player, None), _game_view(guild_id, user_id, player, grid=grid)

    elif player.in_cave:
        _cave_nav = _ui_state.get(user_id, {}).get("nav_target")
        # Determine cave metadata (level, type, boss defeated)
        cave_meta_row = await db.fetch_one(
            "SELECT cave_level, cave_type, boss_defeated FROM caves WHERE cave_id = ?",
            (player.cave_id,)
        )
        cave_level = cave_meta_row["cave_level"] if cave_meta_row else 1
        is_rift = cave_meta_row and cave_meta_row["cave_type"] == "rift"
        rift_boss_defeated = cave_meta_row and bool(cave_meta_row["boss_defeated"])
        is_lava_cave = getattr(player, "cave_lit", False)
        if is_lava_cave:
            enc_rates = LAVA_CAVE_ENCOUNTER_RATES
        else:
            enc_rates = CAVE_LEVEL_ENCOUNTER_RATES.get(cave_level, CAVE_ENCOUNTER_RATES)

        for _ in range(steps):
            nx, ny = player.cave_x + dx, player.cave_y + dy
            target = await load_cave_single_tile(player.cave_id, nx, ny, db)

            # ── Rift exit: stepping onto the rift_entrance portal exits to overworld ──
            if is_rift and target.terrain == "rift_entrance":
                player.in_cave = False
                player.cave_id = None
                player.cave_x = player.cave_y = 0
                await update_player_cave_state(db, user_id, False, None, 0, 0)
                grid = await load_viewport(player.world_x, player.world_y, seed, db)
                return (
                    render_grid(grid, player,
                        "🌀 The portal swirls shut behind you. You're back at the sundial.",
                        nav_target=_cave_nav),
                    _game_view(guild_id, user_id, player, grid=grid),
                )

            # ── Rift boss trigger: entering the boss room spawns the Temporal Echo ──
            if (is_rift and not rift_boss_defeated
                    and target.terrain in ("rift_floor", "rift_deposit")
                    and ny >= RIFT_BOSS_Y):
                # Move player to the target tile first
                player.cave_x, player.cave_y = nx, ny
                await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)

                enemy_type = "temporal_echo"
                grid = await load_cave_viewport(player.cave_id, nx, ny, db)
                arena_rng = _random.Random(hash((user_id, player.cave_id, "echo")))
                arena, _ex, _ey = build_arena_from_viewport(grid, enemy_type, arena_rng)

                # Place echo at its designated spawn location in the arena
                # (arena is 9×9 centred on player; echo's world position is boss spawn)
                arena["echo_deposits"] = set()
                arena["echo_rewind_counter"] = 0
                arena["echo_deposit_move"] = 1  # first turn spawns on move 1
                arena["golem_slam_used"] = arena.get("golem_slam_used", False)

                player.in_combat = True
                player.combat_enemy_type = enemy_type
                player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                player.combat_enemy_x = _ex
                player.combat_enemy_y = _ey
                player.combat_player_x = ARENA_SIZE // 2
                player.combat_player_y = ARENA_SIZE // 2
                player.combat_moves_left = (
                    COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
                )
                _ui_state[user_id] = {"type": "combat", "arena": arena}
                await save_combat_state(db, user_id, player)
                content = render_arena(arena, player)
                view = CombatView(guild_id, user_id,
                                  trapped=arena["player_trapped"],
                                  moves_left=player.combat_moves_left)
                return content, view

            # ── Boss door: costs one Cave Key per entry attempt (per player) ──
            if target.terrain == "cave_boss_door":
                # Only check key when approaching from outside the boss room
                cur_tile = await load_cave_single_tile(player.cave_id, player.cave_x, player.cave_y, db)
                entering_from_outside = cur_tile.terrain not in (
                    "cave_boss_floor", "cave_boss_door", "cave_boss_trigger", "cave_boss_chest"
                )
                if entering_from_outside:
                    key_row = await db.fetch_one(
                        "SELECT id FROM inventory WHERE user_id=? AND item_id='cave_key' LIMIT 1",
                        (user_id,),
                    )
                    if not key_row:
                        msgs.append(
                            "🔒 A heavy stone door seals the chamber. You need a **Cave Key** to enter.\n"
                            "*Defeat trolls or wyverns deeper in the cave to find one.*"
                        )
                        break
                    await remove_from_inventory(db, user_id, "cave_key", 1)
                    msgs.append("🗝️ You use the **Cave Key** — the stone door grinds open. Good luck.")
                # Fall through; door tile is walkable; door tile is NOT altered in DB

            # ── Boss trigger: stepping here always spawns the Stone Guardian ──
            if target.terrain == "cave_boss_trigger" and cave_level == 3:
                player.cave_x, player.cave_y = nx, ny
                await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)

                enemy_type = "stone_guardian"
                grid = await load_cave_viewport(player.cave_id, nx, ny, db)
                arena_rng = _random.Random(hash((user_id, player.cave_id, nx, ny, "guardian")))
                arena, _ex, _ey = build_arena_from_viewport(grid, enemy_type, arena_rng)

                player.in_combat = True
                player.combat_enemy_type = enemy_type
                player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                player.combat_enemy_x = _ex
                player.combat_enemy_y = _ey
                player.combat_player_x = ARENA_SIZE // 2
                player.combat_player_y = ARENA_SIZE // 2
                player.combat_moves_left = (
                    COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
                )
                _ui_state[user_id] = {"type": "combat", "arena": arena}
                await save_combat_state(db, user_id, player)
                content = render_arena(arena, player)
                view = CombatView(guild_id, user_id,
                                  trapped=arena["player_trapped"],
                                  moves_left=player.combat_moves_left)
                return content, view

            # Handle stairdown: descend to child cave (generated lazily on first visit)
            if target.terrain == "cave_stairdown":
                deep_row = await db.fetch_one(
                    "SELECT child_cave_id, child_local_x, child_local_y"
                    " FROM cave_deep_entrances"
                    " WHERE parent_cave_id = ? AND parent_local_x = ? AND parent_local_y = ?",
                    (player.cave_id, nx, ny),
                )
                if not deep_row:
                    from dwarf_explorer.world.caves import _create_child_cave
                    await _create_child_cave(seed, player.cave_id, nx, ny, cave_level + 1, db)
                    deep_row = await db.fetch_one(
                        "SELECT child_cave_id, child_local_x, child_local_y"
                        " FROM cave_deep_entrances"
                        " WHERE parent_cave_id = ? AND parent_local_x = ? AND parent_local_y = ?",
                        (player.cave_id, nx, ny),
                    )
                if deep_row:
                    player.cave_id = deep_row["child_cave_id"]
                    player.cave_x = deep_row["child_local_x"]
                    player.cave_y = deep_row["child_local_y"]
                    await update_player_cave_state(db, user_id, True, player.cave_id,
                                                   player.cave_x, player.cave_y)
                    grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                    return render_grid(grid, player, "You descend deeper into the cave..."), \
                           await _cave_game_view(guild_id, user_id, player, db, grid=grid)

            # Handle stairup: ascend to parent cave
            if target.terrain == "cave_stairup":
                up_row = await db.fetch_one(
                    "SELECT parent_cave_id, parent_local_x, parent_local_y"
                    " FROM cave_deep_entrances"
                    " WHERE child_cave_id = ?",
                    (player.cave_id,),
                )
                if up_row:
                    player.cave_id = up_row["parent_cave_id"]
                    player.cave_x = up_row["parent_local_x"]
                    player.cave_y = up_row["parent_local_y"]
                    await update_player_cave_state(db, user_id, True, player.cave_id,
                                                   player.cave_x, player.cave_y)
                    grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                    return render_grid(grid, player, "You climb back up..."), \
                           await _cave_game_view(guild_id, user_id, player, db, grid=grid)
                # No parent cave — treat as normal floor
                player.cave_x, player.cave_y = nx, ny
                await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                return render_grid(grid, player), await _cave_game_view(guild_id, user_id, player, db, grid=grid)

            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                return render_grid(grid, player, reason), await _cave_game_view(guild_id, user_id, player, db, grid=grid)
            player.cave_x, player.cave_y = nx, ny
            await update_player_cave_state(db, user_id, True, player.cave_id, nx, ny)
            # Random encounter on floor tiles (stone_floor or lava_floor)
            if target.terrain in ("stone_floor", "lava_floor"):
                enc_rng = _random.Random(hash((user_id, nx, ny,
                                              player.cave_id, player.gold)))
                enemy_type = _roll_encounter(enc_rng, enc_rates)
                if enemy_type:
                    grid = await load_cave_viewport(player.cave_id, nx, ny, db)
                    arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type)))
                    arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
                    # Bat swarm: 25% chance of 2 simultaneous bats, 5% chance of 3
                    if enemy_type == "cave_bat":
                        _swarm_roll = enc_rng.random()
                        _n_extra = 2 if _swarm_roll < 0.05 else (1 if _swarm_roll < 0.30 else 0)
                        if _n_extra > 0:
                            spawn_extra_enemies(
                                arena, arena_rng, enemy_type, _n_extra,
                                ex, ey, (ARENA_SIZE // 2, ARENA_SIZE // 2),
                            )
                    player.in_combat = True
                    player.combat_enemy_type = enemy_type
                    player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                    player.combat_enemy_x = ex
                    player.combat_enemy_y = ey
                    player.combat_player_x = ARENA_SIZE // 2
                    player.combat_player_y = ARENA_SIZE // 2
                    player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
                    _ui_state[user_id] = {"type": "combat", "arena": arena}
                    await save_combat_state(db, user_id, player)
                    content = render_arena(arena, player)
                    view = CombatView(guild_id, user_id,
                                      trapped=arena["player_trapped"],
                                      moves_left=player.combat_moves_left)
                    return content, view
        grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
        return render_grid(grid, player), await _cave_game_view(guild_id, user_id, player, db, grid=grid)

    else:
        _ow_has_canoe = await _player_has_canoe(db, user_id)
        for _ in range(steps):
            nx, ny = player.world_x + dx, player.world_y + dy
            target = await load_single_tile(nx, ny, seed, db)
            allowed, reason = can_move(player, direction, target)
            if not allowed:
                grid = await load_viewport(player.world_x, player.world_y, seed, db)
                nearby = await get_nearby_players(db, user_id, player.world_x, player.world_y)
                qmarks = await get_player_quest_markers(db, user_id)
                nav = _ui_state.get(user_id, {}).get("nav_target")
                return render_grid(grid, player, reason, other_players=nearby, quest_markers=qmarks, nav_target=nav), _game_view(guild_id, user_id, player, grid=grid, has_canoe=_ow_has_canoe)
            player.world_x, player.world_y = nx, ny
            await update_player_position(db, user_id, nx, ny)

            # ── Auto-enter forest when stepping onto forest_entrance ──────────
            if target.structure == "forest_entrance":
                from dwarf_explorer.world.forest import (
                    get_forest_entrance, load_forest_viewport, ensure_forests_placed,
                )
                await ensure_forests_placed(seed, db)
                entrance = await get_forest_entrance(db, nx, ny)
                if entrance is not None:
                    forest_id, local_x, local_y = entrance
                    player.in_forest = True
                    player.forest_id = forest_id
                    player.forest_x = local_x
                    player.forest_y = local_y
                    player.forest_wx = nx
                    player.forest_wy = ny
                    await db.execute(
                        "UPDATE players SET in_forest=1, forest_id=?, forest_x=?, forest_y=?, "
                        "forest_wx=?, forest_wy=? WHERE user_id=?",
                        (forest_id, local_x, local_y, nx, ny, user_id)
                    )
                    grid = await load_forest_viewport(forest_id, local_x, local_y, db)
                    return render_grid(grid, player,
                        "🌳 You push through the ancient boughs and enter the **Dense Forest**. "
                        "The canopy closes behind you. Find the 🏡 Tree City, the 🌲 Ancient Tree, "
                        "or seek the 🌀 maze deep within."), \
                           _game_view(guild_id, user_id, player, grid=grid)

            # ── Bandit camp entry: step onto tile to enter the interior ────────────
            if target.structure == "bandit_camp":
                _bc_row = await db.fetch_one(
                    "SELECT id, world_x, world_y, max_bandits, bandit_kills, cleared_at "
                    "FROM bandit_camps WHERE world_x=? AND world_y=?",
                    (nx, ny),
                )
                if not _bc_row:
                    # Lazy-init the DB row on first visit
                    await db.execute(
                        "INSERT OR IGNORE INTO bandit_camps (world_x, world_y) VALUES (?, ?)",
                        (nx, ny),
                    )
                    # db auto-commits on execute(); no explicit commit needed
                    _bc_row = await db.fetch_one(
                        "SELECT id, world_x, world_y, max_bandits, bandit_kills, cleared_at "
                        "FROM bandit_camps WHERE world_x=? AND world_y=?",
                        (nx, ny),
                    )
                if _bc_row:
                    from dwarf_explorer.world.bandit_camp import BC_ENTRY_X, BC_ENTRY_Y
                    player.in_bandit_camp = True
                    player.bandit_camp_id = int(_bc_row["id"])
                    player.bc_x = BC_ENTRY_X
                    player.bc_y = BC_ENTRY_Y
                    # Store the overworld return position
                    await db.execute(
                        "UPDATE players SET in_bandit_camp=1, bandit_camp_id=?, bc_x=?, bc_y=?, "
                        "world_x=?, world_y=? WHERE user_id=?",
                        (_bc_row["id"], BC_ENTRY_X, BC_ENTRY_Y, nx, ny, user_id),
                    )
                    from dwarf_explorer.world.bandit_camp import load_camp_viewport as _lbcv
                    bc_grid = _lbcv(player.bc_x, player.bc_y, int(_bc_row["world_x"]), int(_bc_row["world_y"]))
                    content = render_grid(bc_grid, player,
                        "⛺ You enter the **Bandit Camp**. Stay sharp — they attack on sight.")
                    return content, _game_view(guild_id, user_id, player, grid=bc_grid)

            # 0.2% travelling merchant encounter
            merch_rng = _random.Random(hash((user_id, nx, ny, player.xp // 20, "merchant")))
            if merch_rng.random() < 0.002 and not player.in_combat:
                catalog = _generate_merchant_catalog(merch_rng)
                _ui_state[user_id] = {"type": "merchant", "catalog": catalog, "selected": 0}
                grid = await load_viewport(nx, ny, seed, db)
                content = _render_merchant(catalog, 0, player)
                view = MerchantView(guild_id, user_id)
                return content, view
            # Random surface encounter (1%, biome-specific, skip short_grass)
            mob_table = SURFACE_ENCOUNTER_MOBS.get(target.terrain)
            if mob_table:
                enc_rng = _random.Random(hash((user_id, nx, ny, seed, player.gold)))
                if enc_rng.random() < 0.01:
                    # Pick enemy from weighted table
                    _enemies, _weights = zip(*mob_table)
                    enemy_type = enc_rng.choices(_enemies, weights=_weights, k=1)[0]
                    grid = await load_viewport(nx, ny, seed, db)
                    arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type)))
                    arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
                    player.in_combat = True
                    player.combat_enemy_type = enemy_type
                    player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
                    player.combat_enemy_x = ex
                    player.combat_enemy_y = ey
                    player.combat_player_x = ARENA_SIZE // 2
                    player.combat_player_y = ARENA_SIZE // 2
                    player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
                    _ui_state[user_id] = {"type": "combat", "arena": arena}
                    await save_combat_state(db, user_id, player)
                    content = render_arena(arena, player)
                    view = CombatView(guild_id, user_id,
                                      trapped=arena["player_trapped"],
                                      moves_left=player.combat_moves_left,
                                      enemy_type=enemy_type)
                    return content, view
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        nearby = await get_nearby_players(db, user_id, player.world_x, player.world_y)
        qmarks = await get_player_quest_markers(db, user_id)
        nav = _ui_state.get(user_id, {}).get("nav_target")
        return render_grid(grid, player, other_players=nearby, quest_markers=qmarks, nav_target=nav), _game_view(guild_id, user_id, player, grid=grid, has_canoe=_ow_has_canoe)


async def handle_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # DEBUG — remove after diagnosis
    print(
        f"[DBG handle_move] uid={user_id} dir={direction} "
        f"in_forest={player.in_forest} forest_id={player.forest_id} "
        f"forest_x={player.forest_x} forest_y={player.forest_y} "
        f"in_hermit_hut={getattr(player,'in_hermit_hut',None)} "
        f"in_bandit_camp={getattr(player,'in_bandit_camp',None)} "
        f"in_grove={getattr(player,'in_grove',None)} "
        f"in_tree_city={getattr(player,'in_tree_city',None)} "
        f"in_forest_quest={getattr(player,'in_forest_quest',None)} "
        f"in_cave={player.in_cave}",
        flush=True,
    )

    # No sprinting inside shipwreck (grid is only 7×7 and movement costs breath)
    if getattr(player, "in_shipwreck", False):
        steps = 1
    else:
        steps = 2 if (player.sprinting and player.boots == "hiking_boots") else 1
    content, view = await _move_steps(player, direction, steps, seed, db, guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Combat handlers ───────────────────────────────────────────────────────────

def _combat_view(guild_id: int, user_id: int, arena: dict, player) -> CombatView:
    _has_bomb = (getattr(player, "hand_1", None) == "bomb"
                 or getattr(player, "hand_2", None) == "bomb")
    return CombatView(guild_id, user_id,
                      trapped=arena["player_trapped"],
                      moves_left=player.combat_moves_left,
                      enemy_type=player.combat_enemy_type or "",
                      has_bomb=_has_bomb,
                      bomb_fuse=arena.get("bomb_fuse", 0))


async def _finish_combat(
    db, guild_id: int, user_id: int, player,
    arena: dict, extra_msg: str,
    won: bool = False,
) -> tuple[str, discord.ui.View]:
    """Clean up after combat ends (win, flee, or death). Return (content, view)."""
    seed = await get_or_create_world(db, guild_id)
    # Extract bandit camp info BEFORE clearing state
    _pre_state  = _ui_state.get(user_id, {})
    _camp_id    = _pre_state.get("camp_id")
    player.in_combat = False
    _ui_state.pop(user_id, None)
    await clear_combat_state(db, user_id)

    # Quest kill progress tracking
    if won and player.combat_enemy_type:
        from dwarf_explorer.game.quests import increment_kill_progress
        completed_quests = await increment_kill_progress(db, user_id, player.combat_enemy_type)
        for title in completed_quests:
            extra_msg += f" 📋 Quest ready to complete: **{title}**!"

    # Spider poison sac drop on victory
    if won and player.combat_enemy_type in ("cave_spider", "spider"):
        drop_rng = _random.Random(hash((user_id, player.cave_x, player.cave_y, "sac")))
        if drop_rng.random() < 0.50:
            await add_to_inventory(db, user_id, "poison_sac", 1)
            extra_msg += " 🧪 The spider dropped a **Poison Sac**!"

    # Bandit dagger drop on victory (~25%)
    if won and player.combat_enemy_type == "bandit":
        drop_rng = _random.Random(hash((user_id, player.world_x, player.world_y, "bandit_drop")))
        if drop_rng.random() < 0.25:
            await add_to_inventory(db, user_id, "dagger", 1)
            extra_msg += " 🗡️ The bandit dropped a **Dagger**!"

    # Bandit camp kill tracking
    if won and player.combat_enemy_type == "bandit" and _camp_id is not None:
        try:
            await db.execute(
                "UPDATE bandit_camps SET bandit_kills = bandit_kills + 1 WHERE id = ?",
                (_camp_id,),
            )
            camp_row = await db.fetch_one(
                "SELECT bandit_kills, max_bandits FROM bandit_camps WHERE id = ?",
                (_camp_id,),
            )
            if camp_row and camp_row["bandit_kills"] >= camp_row["max_bandits"]:
                import time as _ct
                await db.execute(
                    "UPDATE bandit_camps SET cleared_at = ? WHERE id = ?",
                    (int(_ct.time()), _camp_id),
                )
                extra_msg += (
                    " 🏕️ **The bandit camp has been cleared!** "
                    "The roads are safer now. The camp will respawn in 24 hours."
                )
        except Exception:
            pass

    # Ent defeated — mark it dead in the fq_ents table
    if won and player.combat_enemy_type == "ent" and getattr(player, "in_forest_quest", False):
        try:
            await db.execute(
                "UPDATE fq_ents SET alive=0 "
                "WHERE fq_id=? AND local_x=? AND local_y=? AND alive=1 AND ent_type='regular'",
                (player.fq_area_id, player.fq_x, player.fq_y),
            )
            await db.commit()
        except Exception:
            pass
        drop_rng_ent = _random.Random(hash((user_id, player.fq_x, player.fq_y, "ent_drop")))
        if drop_rng_ent.random() < 0.60:
            await add_to_inventory(db, user_id, "log", 1)
            extra_msg += " 🪵 The ent crumbles into a **Log**!"
        if drop_rng_ent.random() < 0.40:
            await add_to_inventory(db, user_id, "stick", 1)
            extra_msg += " 🪵 It also drops a **Stick**!"
        # Ent core drop
        await add_to_inventory(db, user_id, "ent_core", _FQ_ECDE)
        extra_msg += f" 🟢 **Ent Core** × {_FQ_ECDE}!"

    # Ancient ent defeated — mark it dead, drop ent_core × 2
    if won and player.combat_enemy_type == "ancient_ent" and getattr(player, "in_forest_quest", False):
        from dwarf_explorer.config import FQ_ENT_CORE_DROP_ANCIENT as _FQ_ECDA
        try:
            await db.execute(
                "UPDATE fq_ents SET alive=0 "
                "WHERE fq_id=? AND local_x=? AND local_y=? AND alive=1 AND ent_type='ancient'",
                (player.fq_area_id, player.fq_x, player.fq_y),
            )
            await db.commit()
        except Exception:
            pass
        await add_to_inventory(db, user_id, "ent_core", _FQ_ECDA)
        extra_msg += (
            f" 🌲 The ancient guardian dissolves into bark and shadow...\n"
            f"🟢 **Ent Core** × {_FQ_ECDA}!"
        )

    # Sky enemy drops on victory
    if won and player.combat_enemy_type == "wind_wisp":
        drop_rng = _random.Random(hash((user_id, getattr(player, "sky_x", 0), getattr(player, "sky_y", 0), "wisp_drop")))
        if drop_rng.random() < 0.40:
            await add_to_inventory(db, user_id, "gust_of_aevos", 1)
            extra_msg += " \U0001F32C️ The wisp dispersed into a **Gust of Aevos**!"

    if won and player.combat_enemy_type == "storm_hawk":
        drop_rng = _random.Random(hash((user_id, getattr(player, "sky_x", 0), getattr(player, "sky_y", 0), "hawk_drop")))
        if drop_rng.random() < 0.60:
            await add_to_inventory(db, user_id, "gust_of_aevos", 1)
            extra_msg += " \U0001F32C️ The hawk dropped a **Gust of Aevos**!"
        if drop_rng.random() < 0.40:
            await add_to_inventory(db, user_id, "hawk_feather", 1)
            extra_msg += " \U0001FAB6 You pluck a **Hawk Feather** from the fallen storm hawk!"

    # Mimic defeated — clear the mimic tile (maze or forest)
    if won and player.combat_enemy_type == "chest_mimic":
        _mimic_mid = _ui_state.get(user_id, {}).get("mimic_maze_id")
        _mimic_mx  = _ui_state.get(user_id, {}).get("mimic_x")
        _mimic_my  = _ui_state.get(user_id, {}).get("mimic_y")
        if _mimic_mid is not None and _mimic_mx is not None:
            await db.execute(
                "UPDATE maze_tiles SET tile_type='maze_floor' "
                "WHERE maze_id=? AND local_x=? AND local_y=?",
                (_mimic_mid, _mimic_mx, _mimic_my),
            )
            _invalidate_vp(user_id)
        _mimic_fid = _ui_state.get(user_id, {}).get("mimic_forest_id")
        _mimic_ffx = _ui_state.get(user_id, {}).get("mimic_forest_x")
        _mimic_ffy = _ui_state.get(user_id, {}).get("mimic_forest_y")
        if _mimic_fid is not None and _mimic_ffx is not None:
            await db.execute(
                "UPDATE forest_tiles SET tile_type='fst_floor' "
                "WHERE forest_id=? AND local_x=? AND local_y=?",
                (_mimic_fid, _mimic_ffx, _mimic_ffy),
            )
            _invalidate_vp(user_id)
        extra_msg += " 💀 The mimic collapses — a **fake chest** lies defeated!"

    # Wyvern scale drop on victory
    if won and player.combat_enemy_type == "cave_wyvern":
        drop_rng = _random.Random(hash((user_id, player.cave_x, player.cave_y, "wyvern_scale")))
        if drop_rng.random() < 0.60:
            scale_count = drop_rng.randint(1, 3)
            await add_to_inventory(db, user_id, "wyvern_scale", scale_count)
            extra_msg += f" 🐉 The wyvern dropped **{scale_count} Wyvern Scale{'s' if scale_count > 1 else ''}**!"

    # Temporal Echo victory: mark boss defeated and give 2 chronolite directly
    if won and player.combat_enemy_type == "temporal_echo" and player.in_cave:
        await db.execute(
            "UPDATE caves SET boss_defeated=1 WHERE cave_id=?", (player.cave_id,)
        )
        await add_to_inventory(db, user_id, "chronolite", 2)
        extra_msg += (
            " ⏪ The Echo collapses into shards of frozen time! "
            "💠 You collect **2 Chronolite**. The rift deposits are now yours to mine."
        )

    # Stone Guardian victory: mark cave boss defeated, boss chest now lootable
    if player.combat_enemy_type == "stone_guardian" and player.in_cave:
        if won:
            extra_msg += (
                " 💀 The **Stone Guardian** crumbles to rubble! "
                "The 💰 chest is yours."
            )
        elif player.hp > 0:
            # Fled — reposition to just inside the door (antechamber), before the trigger tile
            door_row = await db.fetch_one(
                "SELECT local_x, local_y FROM cave_tiles "
                "WHERE cave_id=? AND tile_type='cave_boss_door' LIMIT 1",
                (player.cave_id,),
            )
            if door_row:
                # Place player one tile past the door — safe antechamber, before trigger
                flee_x = door_row["local_x"] + 1
                flee_y = door_row["local_y"]
                player.cave_x, player.cave_y = flee_x, flee_y
                await update_player_cave_state(db, user_id, True, player.cave_id, flee_x, flee_y)
            extra_msg += " 🏃 You scramble back to the antechamber. The Guardian still lurks within."

    # Cave Key drop: cave_troll or cave_wyvern in a level-3 cave (boss not yet defeated)
    if won and player.combat_enemy_type in ("cave_troll", "cave_wyvern") and player.in_cave:
        cave_meta_k = await db.fetch_one(
            "SELECT cave_level FROM caves WHERE cave_id=?", (player.cave_id,)
        )
        if cave_meta_k and cave_meta_k["cave_level"] == 3:
            existing_key = await db.fetch_one(
                "SELECT id FROM inventory WHERE user_id=? AND item_id='cave_key' LIMIT 1",
                (user_id,),
            )
            if not existing_key:
                drop_chance = 0.30 if player.combat_enemy_type == "cave_wyvern" else 0.20
                key_rng = _random.Random(hash((user_id, player.cave_x, player.cave_y, "cave_key")))
                if key_rng.random() < drop_chance:
                    await add_to_inventory(db, user_id, "cave_key", 1)
                    extra_msg += " 🗝️ A **Cave Key** falls from the creature's grasp!"

    # Admin account never dies — clamp to 1 HP before the death check fires
    if player.hp <= 0 and user_id == ADMIN_PLAYER_ID:
        player.hp = 1
        await update_player_stats(db, user_id, hp=1)
        extra_msg += " 🛡️ *Admin resilience — held at 1 HP.*"

    if player.hp <= 0:
        # Drop all inventory items at the death location before resetting
        inv_rows = await get_inventory(db, user_id)
        if inv_rows:
            death_items = [(r["item_id"], r["quantity"]) for r in inv_rows]
            if player.in_cave and player.cave_id is not None:
                await create_cave_drop_box(db, player.cave_id, player.cave_x, player.cave_y, death_items)
            elif getattr(player, "in_temple", False) and player.temple_id is not None:
                await create_drop_box(db, player.temple_wx, player.temple_wy, death_items)
            else:
                await create_drop_box(db, player.world_x, player.world_y, death_items)
            await db.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
            extra_msg += " 📦 Your belongings lie where you fell."
        msg = apply_death_reset(player)
        player.in_canoe = False
        player.in_ocean = False
        player.in_high_seas = False
        player.in_shipwreck = False
        player.breath = BREATH_MAX
        player.in_sky = False
        player.sky_id = None
        player.sky_x = player.sky_y = 0
        player.sky_portal_wx = player.sky_portal_wy = 0
        player.in_temple = False
        player.temple_id = None
        player.temple_x = player.temple_y = 0
        player.temple_wx = player.temple_wy = 0
        player.in_forest_quest = False
        player.fq_area_id = None
        player.fq_x = player.fq_y = 0
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_cave_state(db, user_id, False, None, 0, 0)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        await update_player_shipwreck_state(db, user_id, False, 0, 0, 0, 0, BREATH_MAX)
        await update_player_sky_state(db, user_id, False, None, 0, 0)
        await update_player_temple_state(db, user_id, False, None, 0, 0)
        await db.execute(
            "UPDATE players SET in_forest_quest=0, fq_area_id=NULL, "
            "fq_x=0, fq_y=0 WHERE user_id=?", (user_id,)
        )
        # Respawn in the nearest village at full health
        death_x, death_y = player.world_x, player.world_y
        nearest = await find_nearest_village(seed, db, death_x, death_y)
        if nearest:
            vwx, vwy, vid, vex, vey = nearest
            player.world_x, player.world_y = vwx, vwy
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = vex, vey
            player.village_wx, player.village_wy = vwx, vwy
            await update_player_position(db, user_id, vwx, vwy)
            await update_player_village_state(db, user_id, True, vid, vex, vey, vwx, vwy)
            await update_player_stats(db, user_id, hp=player.hp, in_canoe=0, in_ocean=0)
            grid = await load_village_viewport(vid, vex, vey, db, user_id=user_id)
            view = _game_view(guild_id, user_id, player, grid=grid)
        else:
            await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
            await update_player_stats(db, user_id, hp=player.hp, in_canoe=0, in_ocean=0)
            await update_player_position(db, user_id, player.world_x, player.world_y)
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            view = _game_view(guild_id, user_id, player, grid=grid)
        return render_grid(grid, player, f"{extra_msg} {msg}"), view

    # Ship sank during naval combat
    if player.ship_hp <= 0:
        player.ship_hp = 1  # needs repair but ship isn't gone
        await update_player_ship_hp(db, user_id, player.ship_hp)
        # Wash player ashore at harbor world position
        harbor_wx = getattr(player, "ocean_harbor_wx", player.world_x)
        harbor_wy = getattr(player, "ocean_harbor_wy", player.world_y)
        player.in_high_seas = False
        player.in_ocean = False
        player.in_ship = False
        player.world_x, player.world_y = harbor_wx, harbor_wy
        await update_player_ocean_state(db, user_id, False, 0, 0, in_high_seas=False)
        await update_player_ship_state(db, user_id, False, player.ship_room)
        await update_player_position(db, user_id, player.world_x, player.world_y)
        await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        sink_msg = f"{extra_msg} 🛳️💥 Your ship sinks! You wash ashore near the harbor. Hull at 1/{player.ship_max_hp} — repair with logs from the cargo chest."
        _sink_nav = _ui_state.get(user_id, {}).get("nav_target")
        return render_grid(grid, player, sink_msg, nav_target=_sink_nav), _game_view(guild_id, user_id, player, grid=grid)

    await update_player_stats(db, user_id, hp=player.hp, gold=player.gold, xp=player.xp)
    # Return to the appropriate location view.
    # High-seas and boat use specialised view classes with extra kwargs — keep explicit.
    if player.in_high_seas:
        from dwarf_explorer.world.terrain import get_coast_boundary as _gcb2
        _hs_ce, _ = _gcb2(seed)
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        nav = _ui_state.get(user_id, {}).get("nav_target")
        return render_grid(grid, player, extra_msg, nav_target=nav), OceanView(guild_id, user_id,
                                                               dock_available=_hs_at_harbor(player.ocean_x, player.ocean_y, _hs_ce),
                                                               has_fishing_rod=has_rod)
    if player.in_ocean:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        harbor_adj = await _adjacent_harbor(player, seed, db)
        return render_grid(grid, player, extra_msg), BoatView(guild_id, user_id,
                                                              dock_available=(harbor_adj is not None))
    # All other locations (cave, sky, forest, maze, temple, ship, village, house, overworld):
    # use canonical helpers so nothing falls through to the wrong viewport.
    _invalidate_vp(user_id)
    grid = await _cached_grid(user_id, player, seed, db)
    view = await _build_player_view(guild_id, user_id, player, db, grid)
    qmarks = await get_player_quest_markers(db, user_id)
    nav = _ui_state.get(user_id, {}).get("nav_target")
    return render_grid(grid, player, extra_msg, quest_markers=qmarks, nav_target=nav), view


def _explode_bomb(arena: dict, player) -> list[str]:
    """Fire bomb explosion in arena. Deletes bomb_fuse from arena, applies damage in-place."""
    bx2, by2 = arena.get("bomb_x", 0), arena.get("bomb_y", 0)
    del arena["bomb_fuse"]
    enemy_in_blast = any(
        player.combat_enemy_x == bx2 + dx and player.combat_enemy_y == by2 + dy
        for dx, dy in _BOMB_CROSS_OFFSETS
    )
    player_in_blast = any(
        player.combat_player_x == bx2 + dx and player.combat_player_y == by2 + dy
        for dx, dy in _BOMB_CROSS_OFFSETS
    )
    blast_log = ["💥 **BOOM!** The bomb explodes!"]
    if enemy_in_blast:
        enemy_dmg = 25
        player.combat_enemy_hp = max(0, player.combat_enemy_hp - enemy_dmg)
        blast_log.append(f"Enemy takes **{enemy_dmg}** blast damage!")
    if player_in_blast:
        pdmg = max(1, 15 - player.defense)
        player.hp = max(0, player.hp - pdmg)
        blast_log.append(f"You were caught in the blast! **−{pdmg} HP**")
    # Remove bomb tile from arena grid if placed
    for dx2, dy2 in _BOMB_CROSS_OFFSETS:
        tx2, ty2 = bx2 + dx2, by2 + dy2
        if 0 <= ty2 < len(arena.get("grid", [])) and 0 <= tx2 < len(arena["grid"][ty2]):
            if arena["grid"][ty2][tx2] == "bomb_lit":
                arena["grid"][ty2][tx2] = arena.get("bomb_orig_tile", "grass")
    return blast_log


async def _after_player_action(
    interaction: discord.Interaction,
    db, guild_id: int, user_id: int,
    player, arena: dict, msg: str,
) -> None:
    """Called after a player action. Run enemy turn if moves exhausted, or re-render."""
    arena["combat_log"].append(msg)

    # Temporal Echo: check if deposits should spawn this move
    deposit_msg = resolve_echo_deposits(arena, player)
    if deposit_msg:
        arena["combat_log"].append(deposit_msg)
        # If deposit landed on player and they're now dead, handle immediately
        if player.hp <= 0:
            content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                                 " ".join(arena["combat_log"][-4:]))
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    is_naval = arena.get("naval", False)

    def _is_dead() -> bool:
        return (player.ship_hp <= 0) if is_naval else (player.hp <= 0)

    # ── Bomb fuse: tick for this player action ───────────────────────────────────
    if "bomb_fuse" in arena:
        arena["bomb_fuse"] -= 1
        if arena["bomb_fuse"] <= 0:
            blast_log = _explode_bomb(arena, player)
            arena["combat_log"].extend(blast_log)
            if player.combat_enemy_hp <= 0:
                victory_msg = apply_victory(player)
                arena["combat_log"].append(victory_msg)
                content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                                     " ".join(arena["combat_log"][-5:]), won=True)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            if _is_dead():
                content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                                     " ".join(arena["combat_log"][-5:]))
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

    # Enemy dead?
    if player.combat_enemy_hp <= 0:
        if promote_extra_enemy(arena, player):
            # Another bat in the swarm — reset moves and continue combat
            player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
            await save_combat_state(db, user_id, player)
            content = render_arena(arena, player)
            view = _combat_view(guild_id, user_id, arena, player)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        victory_msg = apply_victory(player)
        arena["combat_log"].append(victory_msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]), won=True)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Player / ship dead?
    if _is_dead():
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]))
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Still has moves left?
    if player.combat_moves_left > 0:
        await save_combat_state(db, user_id, player)
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # No moves left → enemy turn
    rng = _random.Random(hash((user_id, player.combat_enemy_x, player.combat_enemy_y,
                               player.combat_enemy_hp)))
    enemy_msg = resolve_enemy_turn(arena, player, rng, naval=is_naval)
    arena["combat_log"].append(enemy_msg)

    # ── Bomb fuse: tick for enemy turn ──────────────────────────────────────────
    if "bomb_fuse" in arena:
        arena["bomb_fuse"] -= 1
        if arena["bomb_fuse"] <= 0:
            blast_log = _explode_bomb(arena, player)
            arena["combat_log"].extend(blast_log)
            if player.combat_enemy_hp <= 0:
                victory_msg = apply_victory(player)
                arena["combat_log"].append(victory_msg)
                content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                                     " ".join(arena["combat_log"][-5:]), won=True)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            if _is_dead():
                content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                                     " ".join(arena["combat_log"][-5:]))
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

    # Restore player moves for next turn
    player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)

    # Check outcomes after enemy turn
    if _is_dead():
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]))
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if player.combat_enemy_hp <= 0:
        if promote_extra_enemy(arena, player):
            # Another bat in the swarm — reset moves and continue combat
            player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
            await save_combat_state(db, user_id, player)
            content = render_arena(arena, player)
            view = _combat_view(guild_id, user_id, arena, player)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        victory_msg = apply_victory(player)
        arena["combat_log"].append(victory_msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-4:]), won=True)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await save_combat_state(db, user_id, player)
    content = render_arena(arena, player)
    view = _combat_view(guild_id, user_id, arena, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def _load_combat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> tuple | None:
    """Load combat state. Returns (db, player, arena) or None if not in combat."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    arena = _ui_state.get(user_id, {}).get("arena")
    if not player.in_combat or arena is None:
        # Combat state lost (e.g. bot restart) — clear and return to game
        if player.in_combat:
            player.in_combat = False
            await clear_combat_state(db, user_id)
            seed = await get_or_create_world(db, guild_id)
            if player.in_cave:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            else:
                grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, "Combat session lost — you escape unharmed.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player)
            )
        return None
    return db, player, arena


async def handle_combat_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    rng = _random.Random(hash((user_id, player.combat_player_x, player.combat_player_y,
                               arena.get("poison_turns", 0))))
    msg = action_move(arena, player, direction, rng)
    await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)


async def handle_combat_attack(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    rng = _random.Random(hash((user_id, player.combat_player_x, player.combat_enemy_x)))

    # Slingshot: check for equipped slingshot and consume 1 rock
    has_slingshot = player.hand_1 == "slingshot" or player.hand_2 == "slingshot"
    if has_slingshot:
        rock_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id='rock'", (user_id,)
        )
        if not rock_row:
            arena["combat_log"].append("No rocks left! Mine cave_rocks with a pickaxe.")
            content = render_arena(arena, player)
            view = _combat_view(guild_id, user_id, arena, player)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        await remove_from_inventory(db, user_id, "rock", 1)

    msg = action_attack(arena, player, rng, has_slingshot=has_slingshot)
    await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)


async def handle_combat_flee(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    rng = _random.Random()  # non-deterministic: flee shouldn't be predictable
    msg, success = action_flee(arena, player, rng)
    if success:
        arena["combat_log"].append(msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-3:]))
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
    else:
        await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)



async def handle_bribe(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Show the bribe modal when fighting a bandit."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    _db, player, _arena = result
    if player.combat_enemy_type != "bandit":
        await interaction.response.send_message("You can only bribe bandits!", ephemeral=True)
        return
    await interaction.response.send_modal(BribeModal(guild_id, user_id))


async def handle_bribe_submit(
    interaction: discord.Interaction, guild_id: int, user_id: int, amount_str: str
) -> None:
    """Process a bribe attempt after the player submits the modal."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result

    try:
        amount = int(amount_str.strip())
    except ValueError:
        await interaction.response.send_message("Please enter a whole number.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Must offer at least 1 coin.", ephemeral=True)
        return
    if amount > player.gold:
        await interaction.response.send_message(
            f"You only have **{player.gold}** coins!", ephemeral=True
        )
        return

    # Deduct coins and calculate success chance (5% @ 1 coin, 100% @ 50+, linear)
    player.gold -= amount
    chance = min(1.0, 0.05 + (amount - 1) * (0.95 / 49))
    pct = int(chance * 100)

    bribe_rng = _random.Random()  # non-deterministic — bribe outcome should not be predictable
    if bribe_rng.random() < chance:
        msg = (
            f"💰 You offered **{amount} coin{'s' if amount != 1 else ''}** "
            f"({pct}% chance) — the bandit pockets the gold and melts back into "
            f"the shadows. You escape unharmed!"
        )
        arena["combat_log"].append(msg)
        content, view = await _finish_combat(db, guild_id, user_id, player, arena,
                                             " ".join(arena["combat_log"][-3:]))
    else:
        msg = (
            f"💸 The bandit snatches your **{amount} coin{'s' if amount != 1 else ''}** "
            f"but attacks anyway! ({pct}% chance — failed)"
        )
        arena["combat_log"].append(msg)
        await save_combat_state(db, user_id, player)
        from dwarf_explorer.game.combat import render_arena
        render_content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(render_content), content=None, view=view)
        return

    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def _handle_camp_bribe_submit(
    interaction: discord.Interaction, guild_id: int, user_id: int, amount_str: str
) -> None:
    """Process a bribe offered to a bandit inside a camp (dialogue, not combat)."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    try:
        amount = int(amount_str.strip())
    except ValueError:
        await interaction.response.send_message("Please enter a whole number.", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("Must offer at least 1 coin.", ephemeral=True)
        return
    if amount > player.gold:
        await interaction.response.send_message(
            f"You only have **{player.gold}** coins!", ephemeral=True
        )
        return

    # Deduct coins; 10 coins = 25%, 50 coins = 100%, linear clamp
    player.gold -= amount
    chance = min(1.0, 0.05 + (amount - 1) * (0.95 / 49))
    pct = int(chance * 100)

    from dwarf_explorer.world.bandit_camp import load_camp_viewport as _lbcv_bribe
    _bc_row_bribe = await db.fetch_one(
        "SELECT world_x, world_y FROM bandit_camps WHERE id=?", (player.bandit_camp_id,)
    )

    import random as _r_bribe
    if _r_bribe.random() < chance:
        player.bandit_bribe_remaining = 10
        await db.execute(
            "UPDATE players SET gold=?, bandit_bribe_remaining=10 WHERE user_id=?",
            (player.gold, user_id)
        )
        msg = (
            f"💰 You offered **{amount} coin{'s' if amount != 1 else ''}** ({pct}% chance) — "
            f"the bandit pockets the gold and waves you off. "
            f"**You have 10 moves of safe passage.**"
        )
    else:
        await db.execute("UPDATE players SET gold=? WHERE user_id=?", (player.gold, user_id))
        msg = (
            f"💸 The bandit snatches your **{amount} coin{'s' if amount != 1 else ''}** "
            f"and laughs in your face! ({pct}% chance — failed) Watch your back."
        )

    if _bc_row_bribe:
        bc_grid = _lbcv_bribe(player.bc_x, player.bc_y, int(_bc_row_bribe["world_x"]), int(_bc_row_bribe["world_y"]))
    else:
        bc_grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(bc_grid, player, msg)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=bc_grid),
    )


async def handle_combat_eat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open the consumables menu in combat."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result

    # Naval combat: food can't repair the ship
    if arena.get("naval"):
        arena["combat_log"].append("⚓ You can't eat to repair the ship! Use logs from the cargo chest.")
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Build list of consumables the player has
    available: list[tuple[str, int]] = []
    for item_id in CONSUMABLE_ITEMS:
        rows = await db.fetch_all(
            "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
            (user_id, item_id)
        )
        total = rows[0]["total"] if rows and rows[0]["total"] else 0
        if total > 0:
            available.append((item_id, total))

    if not available:
        arena["combat_log"].append("🍗 You have no food! Fish and cook at a hearth for HP recovery.")
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    lines = ["**🍗 Consumables** — select an item to use (costs 1 turn):", ""]
    for item_id, qty in available:
        info = CONSUMABLE_ITEMS.get(item_id, {})
        desc = info.get("desc", "")
        name = item_id.replace("_", " ").title()
        lines.append(f"• **{name}** ×{qty}  —  {desc}")
    content = "\n".join(lines)
    view = ConsumablesView(guild_id, user_id, available)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_combat_consume(
    interaction: discord.Interaction, guild_id: int, user_id: int, item_id: str
) -> None:
    """Consume a specific food item during combat."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result

    row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
    )
    if not row:
        arena["combat_log"].append(f"You no longer have any {item_id.replace('_', ' ')}.")
        content = render_arena(arena, player)
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await remove_from_inventory(db, user_id, item_id, 1)

    # Coward's Ale: guaranteed escape with no parting blow
    item_info = CONSUMABLE_ITEMS.get(item_id, {})
    if item_info.get("escape"):
        msg = "🍺 You chug the Coward's Ale and bolt for the exit — guaranteed escape!"
        arena["combat_log"].append(msg)
        content, view = await _finish_combat(
            db, guild_id, user_id, player, arena,
            " ".join(arena["combat_log"][-3:]),
            won=False,
        )
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    heal_amt = FOOD_HP_RESTORE.get(item_id, item_info.get("hp", 10))
    heal = min(heal_amt, player.max_hp - player.hp)
    player.hp += heal
    player.combat_moves_left -= 1
    msg = f"🍗 You eat {item_id.replace('_', ' ')}! Restored **{heal}** HP. ({player.hp}/{player.max_hp})"
    await _after_player_action(interaction, db, guild_id, user_id, player, arena, msg)


async def handle_combat_consume_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel consumables menu, return to combat."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    content = render_arena(arena, player)
    view = _combat_view(guild_id, user_id, arena, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)



async def handle_combat_end_turn(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Force end player's turn immediately."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result
    player.combat_moves_left = 0  # exhaust moves
    await _after_player_action(interaction, db, guild_id, user_id, player, arena,
                               "You end your turn.")


async def handle_combat_bomb(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Place a lit bomb in combat (requires bomb in hand + flint_and_steel available)."""
    result = await _load_combat(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, arena = result

    # Check bomb in hand
    if player.hand_1 != "bomb" and player.hand_2 != "bomb":
        await interaction.response.defer()
        return

    # Check flint_and_steel
    other_hand = player.hand_2 if player.hand_1 == "bomb" else player.hand_1
    has_flint = other_hand == "flint_and_steel"
    if not has_flint:
        flint_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id='flint_and_steel'", (user_id,)
        )
        has_flint = bool(flint_row and flint_row["quantity"] > 0)
    if not has_flint:
        await save_combat_state(db, user_id, player)
        content = render_arena(arena, player)
        content += "\n*You need flint and steel to light the bomb!*"
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Already a bomb placed?
    if "bomb_fuse" in arena:
        await save_combat_state(db, user_id, player)
        content = render_arena(arena, player)
        content += "\n*A bomb is already burning!*"
        view = _combat_view(guild_id, user_id, arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Place bomb at player position
    px_c = player.combat_player_x
    py_c = player.combat_player_y
    arena["bomb_fuse"] = 5
    arena["bomb_x"] = px_c
    arena["bomb_y"] = py_c
    # Stamp bomb_lit tile into arena grid so it renders visually
    if 0 <= py_c < len(arena.get("grid", [])) and 0 <= px_c < len(arena["grid"][py_c]):
        arena["bomb_orig_tile"] = arena["grid"][py_c][px_c]
        arena["grid"][py_c][px_c] = "bomb_lit"
    # Remove bomb from player
    await remove_from_inventory(db, user_id, "bomb", 1)
    await _auto_unequip_depleted(db, user_id, "bomb", player)
    # Use a move
    player.combat_moves_left = max(0, player.combat_moves_left - 1)
    await _after_player_action(interaction, db, guild_id, user_id, player, arena,
                               "💣 You place the bomb and light the fuse! (**5 moves**)")


# ── Mine adjacent rock ────────────────────────────────────────────────────────

async def handle_mine(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)  # free — cached in memory
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_cave:
        return

    dx, dy = DIRECTIONS[direction]
    nx, ny = player.cave_x + dx, player.cave_y + dy

    hand_items: set[str] = {player.hand_1, player.hand_2} - {None}
    if "pickaxe" not in hand_items:
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "You need a pickaxe to mine that rock.")
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    tile = await load_cave_single_tile(player.cave_id, nx, ny, db)
    if tile.terrain not in ("cave_rock", "iron_ore_deposit", "gold_ore_deposit", "rift_deposit"):
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "That rock has already been mined.")
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Rift deposit: only minable after boss is defeated ──
    if tile.terrain == "rift_deposit":
        cave_meta = await db.fetch_one(
            "SELECT boss_defeated FROM caves WHERE cave_id=?", (player.cave_id,)
        )
        if not cave_meta or not cave_meta["boss_defeated"]:
            grid = await _cached_grid(user_id, player, seed, db)
            content = render_grid(grid, player,
                "💠 This Chronolite formation is protected by the Echo's power. "
                "Defeat the Temporal Echo first.")
            view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        # Mine the deposit — tile is modified, bust cache then reload fresh
        rng_rift = _random.Random(hash((user_id, nx, ny, "rift")))
        ore_count = rng_rift.randint(2, 4) + (1 if player.accessory == "ring_of_luck" else 0)
        await db.execute(
            "UPDATE cave_tiles SET tile_type='rift_floor' WHERE cave_id=? AND local_x=? AND local_y=?",
            (player.cave_id, nx, ny),
        )
        gained, drop_msg = await _give_items_or_drop(db, guild_id, user_id, player,
                                                      [("chronolite", ore_count)])
        loot_str = ", ".join(gained) if gained else "nothing"
        _invalidate_vp(user_id)
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player,
            f"💠 You shatter the deposit! Got: {loot_str}.{drop_msg}")
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    rng = _random.Random(hash((user_id, nx, ny, player.xp)))
    await db.execute(
        "UPDATE cave_tiles SET tile_type='stone_floor'"
        " WHERE cave_id=? AND local_x=? AND local_y=?",
        (player.cave_id, nx, ny),
    )
    # Record break time for 48h regeneration
    await db.execute(
        "INSERT OR REPLACE INTO cave_rock_breaks (cave_id, local_x, local_y, broken_at)"
        " VALUES (?, ?, ?, datetime('now'))",
        (player.cave_id, nx, ny),
    )
    # Get cave level for drop bonuses
    cave_meta = await db.fetch_one(
        "SELECT cave_level FROM caves WHERE cave_id=?", (player.cave_id,)
    )
    cave_level = cave_meta["cave_level"] if cave_meta else 1

    # Build raw loot list, then give with overflow handling
    raw_loot: list[tuple[str, int]] = []
    if tile.terrain == "gold_ore_deposit":
        ore_count = rng.randint(2, 6)
        raw_loot.append(("gold_ore", ore_count))
    elif tile.terrain == "iron_ore_deposit":
        ore_count = rng.randint(3, 9)
        if player.accessory == "ring_of_luck":
            ore_count += 1
        raw_loot.append(("iron_ore", ore_count))
    else:
        rock_count = rng.randint(1, 3)
        raw_loot.append(("rock", rock_count))
        if rng.random() < 0.33:
            raw_loot.append(("flint", 1))
        iron_chance = {1: 0.15, 2: 0.15, 3: 0.15}.get(cave_level, 0.15)
        if rng.random() < iron_chance:
            raw_loot.append(("iron_ore", 1))
        gold_chance = {2: 0.01, 3: 0.05}.get(cave_level, 0.0)
        if gold_chance > 0 and rng.random() < gold_chance:
            raw_loot.append(("gold_ore", 1))

    gained, drop_msg = await _give_items_or_drop(db, guild_id, user_id, player, raw_loot)
    loot_str = ", ".join(gained) if gained else "nothing"

    # Tile was modified — bust cache so next press sees the cleared rock
    _invalidate_vp(user_id)
    grid = await _cached_grid(user_id, player, seed, db)
    content = render_grid(grid, player, f"You mine the rock! Got: {loot_str}.{drop_msg}")
    view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Sprint toggle ─────────────────────────────────────────────────────────────

async def handle_sprint(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.boots != "hiking_boots":
        await interaction.response.send_message("You need hiking boots to sprint (climbing boots don't sprint).", ephemeral=True)
        return

    player.sprinting = not player.sprinting
    await update_player_sprint(db, user_id, player.sprinting)

    status = "Sprint ON \U0001F3C3" if player.sprinting else "Sprint OFF"
    # Use the canonical helpers so every interior type gets the right grid and view.
    grid = await _cached_grid(user_id, player, seed, db)
    view = await _build_player_view(guild_id, user_id, player, db, grid)
    _nav = _ui_state.get(user_id, {}).get("nav_target")
    content = render_grid(grid, player, status, nav_target=_nav)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Canoe handlers ───────────────────────────────────────────────────────────

async def handle_canoe_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not player.in_canoe:
        # Fallback: player got off canoe somehow
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        await interaction.response.edit_message(
            embed=_embed(render_grid(grid, player)), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return
    content, view = await _move_steps(player, direction, 1, seed, db, guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_canoe_dock(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_canoe:
        return

    # Find any adjacent walkable land tile (not water)
    _WATER = {"river", "bridge", "shallow_water", "deep_water"}
    landing = None
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if t.terrain not in _WATER and t.walkable:
                landing = (ax, ay)
                break

    if not landing:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
        has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        content = render_grid(grid, player, "No walkable land nearby to dock at.")
        view = CanoeView(guild_id, user_id, dock_dirs=dock_dirs, has_fishing_rod=has_fishing_rod)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    lx, ly = landing
    player.world_x, player.world_y = lx, ly
    player.in_canoe = False
    await update_player_stats(db, user_id, world_x=lx, world_y=ly, in_canoe=0)
    grid = await load_viewport(lx, ly, seed, db)
    content = render_grid(grid, player, "🏞️ You pull the canoe ashore.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_embark_dir(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    direction: str,
) -> None:
    """Embark onto the water tile in a specific cardinal direction."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.in_canoe:
        return

    dx, dy = DIRECTIONS[direction]
    ax, ay = player.world_x + dx, player.world_y + dy

    if not (0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE):
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "Can't embark there — world boundary.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    t = await load_single_tile(ax, ay, seed, db)
    _CANOE_WATER = {"river", "bridge", "shallow_water", "deep_water"}
    if t.terrain not in _CANOE_WATER:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "No water to launch from there.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    player.world_x, player.world_y = ax, ay
    player.in_canoe = True
    await update_player_stats(db, user_id, world_x=ax, world_y=ay, in_canoe=1)
    grid = await load_viewport(ax, ay, seed, db)
    content = render_grid(grid, player, "\U0001F6F6 You push off from the bank and onto the water.")
    dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
    has_fishing_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
    view = CanoeView(guild_id, user_id, dock_dirs=dock_dirs, has_fishing_rod=has_fishing_rod)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_chop_dir(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    direction: str,
) -> None:
    """Chop the ancient tree in a specific cardinal direction."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.hand_1 == "axe" or player.hand_2 == "axe"):
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "\U0001FA93 You need an axe equipped to chop the ancient tree.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    dx, dy = DIRECTIONS[direction]
    wx, wy = player.world_x, player.world_y
    ax, ay = wx + dx, wy + dy
    t = await load_single_tile(ax, ay, seed, db)

    if t.terrain not in _ANCIENT_TREE_TILES:
        grid = await load_viewport(wx, wy, seed, db)
        content = render_grid(grid, player, "\U0001FA93 Nothing to chop there.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    _root_x, _root_y = _ancient_tree_root(t.terrain, ax, ay)
    _chop_row = await db.fetch_one(
        "SELECT chops FROM tree_chop_progress WHERE world_x=? AND world_y=?",
        (_root_x, _root_y)
    )
    _chops = (_chop_row["chops"] if _chop_row else 0) + 1
    if _chops >= 10:
        await db.execute(
            "DELETE FROM tree_chop_progress WHERE world_x=? AND world_y=?",
            (_root_x, _root_y)
        )
        for _tx, _ty, _ in _ancient_tree_positions(_root_x, _root_y):
            await set_tile_override(db, _tx, _ty, "dirt")
        await add_to_inventory(db, user_id, "log", 6)
        await add_to_inventory(db, user_id, "ancient_sapling", 1)
        grid = await load_viewport(wx, wy, seed, db)
        content = render_grid(grid, player, "\U0001FA93 The ancient tree crashes down! You gather **6 logs** and recover the **ancient sapling**.")
    else:
        if _chop_row:
            await db.execute(
                "UPDATE tree_chop_progress SET chops=? WHERE world_x=? AND world_y=?",
                (_chops, _root_x, _root_y)
            )
        else:
            await db.execute(
                "INSERT INTO tree_chop_progress(world_x, world_y, chops) VALUES(?,?,?)",
                (_root_x, _root_y, _chops)
            )
        grid = await load_viewport(wx, wy, seed, db)
        content = render_grid(grid, player, f"\U0001FA93 You strike the ancient tree. ({_chops}/10 chops)")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_embark(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Embark onto an adjacent river tile using the canoe from inventory."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if player.in_canoe:
        return

    # Find adjacent river/water tile — only harbor is truly too rough for a canoe
    _CANOE_WATER = {"river", "bridge", "shallow_water", "deep_water"}
    _ROUGH_WATER = {"harbor"}
    water_pos: tuple[int, int] | None = None
    rough_adjacent = False
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = player.world_x + ddx, player.world_y + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if t.terrain in _CANOE_WATER:
                water_pos = (ax, ay)
                break
            elif t.terrain in _ROUGH_WATER:
                rough_adjacent = True

    if not water_pos:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        if rough_adjacent:
            msg = "🌊 These waters are too rough for a canoe — your little vessel would be swamped instantly."
        else:
            msg = "No water to launch from nearby."
        content = render_grid(grid, player, msg)
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    wx, wy = water_pos
    player.world_x, player.world_y = wx, wy
    player.in_canoe = True
    await update_player_stats(db, user_id, world_x=wx, world_y=wy, in_canoe=1)
    grid = await load_viewport(wx, wy, seed, db)
    content = render_grid(grid, player, "🛶 You push off from the bank and onto the water.")
    dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
    view = CanoeView(guild_id, user_id, dock_dirs=dock_dirs)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_fill_watering_can(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Fill the equipped watering can from an adjacent water source."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    has_can = player.hand_1 == "watering_can" or player.hand_2 == "watering_can"
    if not has_can:
        seed = await get_or_create_world(db, guild_id)
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "🪣 You don't have a watering can equipped.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return
    player.watering_can_uses = 9
    await db.execute("UPDATE players SET watering_can_uses=9 WHERE user_id=?", (user_id,))
    seed = await get_or_create_world(db, guild_id)
    grid = await _cached_grid(user_id, player, seed, db)
    content = render_grid(grid, player, "🪣 You fill the watering can. **(9/9)**")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_fish_secondary(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Fish from water — called when fishing rod is the off-hand secondary action."""
    # Reuse the same logic as handle_action's fishing branch
    await handle_action(interaction, guild_id, user_id)


async def handle_feed_cat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Feed a fish to the adjacent house cat (bottom-left button)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house:
        return

    grid = await _load_house_grid(player, db)
    _fish_rows = await db.fetch_all(
        "SELECT item_id FROM inventory WHERE user_id=? AND item_id IN ('fish','cooked_fish')",
        (user_id,)
    )
    if _fish_rows:
        await remove_from_inventory(db, user_id, _fish_rows[0]["item_id"], 1)
        _flavour = [
            "🐱 The cat sniffs your fish eagerly, then devours it whole. It purrs loudly.",
            "🐱 The cat takes the fish delicately, retreats to a corner, and eats with great dignity.",
            "🐱 The cat headbutts your ankle after finishing the fish. High praise.",
            "🐱 The cat snatches the fish before you can reconsider. Typical.",
        ]
        import hashlib as _fh
        _fi = int(_fh.md5(f"cat{player.house_id}{player.house_x}{player.house_y}".encode()).hexdigest(), 16) % len(_flavour)
        content = render_grid(grid, player, _flavour[_fi])
    else:
        content = render_grid(grid, player, "🐱 The cat eyes you hopefully. You have no fish to offer.")

    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Plant seeds view (choose seed type) ───────────────────────────────────────

class PlantOverworldView(discord.ui.View):
    """Choose what to plant on an overworld dirt tile (sapling, ancient_seed, or ancient_sapling)."""

    _LABELS = {
        "pinecone":         ("🌲", "Pinecone"),
        "sapling":          ("🌱", "Sapling"),
        "ancient_seed":     ("🌱", "Ancient Seed"),
        "ancient_sapling":  ("🌳", "Ancient Sapling"),
    }

    def __init__(self, guild_id: int, user_id: int, choices: list[str]):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        for item_id in choices:
            emoji, name = self._LABELS.get(item_id, ("🌱", item_id.replace("_", " ").title()))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"{emoji} {name}",
                custom_id=_custom_id(gid, uid, f"plant_ow_{item_id}"),
                row=0,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "plant_cancel"), row=1,
        ))


class PlantSeedView(discord.ui.View):
    """Choose which seed type to plant on vil_farmland."""

    def __init__(self, guild_id: int, user_id: int, seed_types: list[str]):
        super().__init__(timeout=None)
        gid, uid = guild_id, user_id
        for stype in seed_types:
            crop = FARM_CROPS.get(stype, {})
            emoji = crop.get("emoji", "🌱")
            name = stype.replace("_", " ").title()
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=f"{emoji} {name}",
                custom_id=_custom_id(gid, uid, f"plant_choice_{stype}"),
                row=0,
            ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="❌ Cancel",
            custom_id=_custom_id(gid, uid, "plant_cancel"), row=1,
        ))


async def handle_plant(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Bottom-left plant button: plant seeds on vil_farmland OR saplings/ancient seeds on overworld dirt."""
    db = await get_database(guild_id)
    seed_w = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # ── Overworld: plant sapling / ancient_seed on dirt ──────────────────────
    if not player.in_village and not player.in_house and not player.in_cave:
        wx, wy = player.world_x, player.world_y
        grid = await _cached_grid(user_id, player, seed_w, db)
        vc_ = 4
        center_t = grid[vc_][vc_].terrain if len(grid) > vc_ and len(grid[vc_]) > vc_ else None
        if center_t != "dirt":
            content = render_grid(grid, player, "🌱 You need to be standing on a dirt patch to plant here.")
            await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
            return
        inv = await get_inventory(db, user_id)
        has_sapling = any(it["item_id"] == "sapling" and it["quantity"] > 0 for it in inv)
        has_ancient = any(it["item_id"] == "ancient_seed" and it["quantity"] > 0 for it in inv)
        has_ancient_sapling = any(it["item_id"] == "ancient_sapling" and it["quantity"] > 0 for it in inv)
        has_pinecone = any(it["item_id"] == "pinecone" and it["quantity"] > 0 for it in inv)
        choices = ([item for item, flag in [
            ("pinecone", has_pinecone),
            ("sapling", has_sapling),
            ("ancient_seed", has_ancient),
            ("ancient_sapling", has_ancient_sapling),
        ] if flag])
        if not choices:
            content = render_grid(grid, player, "🌱 You have no saplings, pinecones, or ancient seeds to plant.")
            await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
            return
        if len(choices) == 1:
            await _plant_overworld_item(interaction, guild_id, user_id, player, db, choices[0])
            return
        # Multiple choices — show picker
        content = render_grid(grid, player, "🌱 What would you like to plant?")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=PlantOverworldView(guild_id, user_id, choices))
        return

    if not player.in_village or player.in_house:
        return

    grid = await _cached_grid(user_id, player, seed_w, db)
    vc_ = 4  # VIEWPORT_CENTER
    center_t = grid[vc_][vc_].terrain if len(grid) > vc_ and len(grid[vc_]) > vc_ else None
    if center_t != "vil_farmland":
        content = render_grid(grid, player, "You're not standing on farmland.")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
        return

    # Check inventory for seed types
    inv_items = await get_inventory(db, user_id)
    seed_types_held = [
        it["item_id"] for it in inv_items
        if it["item_id"] in FARM_CROPS and it["quantity"] > 0
    ]
    if not seed_types_held:
        content = render_grid(grid, player, "🌱 You have no seeds to plant.")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
        return

    if len(seed_types_held) == 1:
        # Plant directly — tile modified, invalidate then reload fresh
        stype = seed_types_held[0]
        crop = FARM_CROPS[stype]
        await remove_from_inventory(db, user_id, stype, 1)
        await set_village_tile(db, player.village_id, player.village_x, player.village_y, crop["planted"])
        _invalidate_vp(user_id)
        grid = await _cached_grid(user_id, player, seed_w, db)
        content = render_grid(grid, player, f"🌱 You plant {stype.replace('_',' ')} in the soil. Water it to grow!")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
        return

    # Multiple seed types — show selection menu
    seed_types_unique = list(dict.fromkeys(seed_types_held))  # deduplicated, preserves order
    content = render_grid(grid, player, "🌱 Which seeds do you want to plant?")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=PlantSeedView(guild_id, user_id, seed_types_unique))


async def handle_plant_choice(
    interaction: discord.Interaction, guild_id: int, user_id: int, seed_type: str
) -> None:
    """Confirm a specific seed choice from PlantSeedView."""
    db = await get_database(guild_id)
    seed_w = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_village or player.in_house:
        return

    grid = await _cached_grid(user_id, player, seed_w, db)
    crop = FARM_CROPS.get(seed_type)
    if not crop:
        content = render_grid(grid, player, "Unknown seed type.")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
        return

    inv_items = await get_inventory(db, user_id)
    has_seed = any(it["item_id"] == seed_type and it["quantity"] > 0 for it in inv_items)
    vc_ = 4  # VIEWPORT_CENTER
    center_t = grid[vc_][vc_].terrain if len(grid) > vc_ and len(grid[vc_]) > vc_ else None

    if not has_seed:
        content = render_grid(grid, player, f"🌱 You don't have any {seed_type.replace('_',' ')}.")
    elif center_t != "vil_farmland":
        content = render_grid(grid, player, "You're no longer standing on farmland.")
    else:
        await remove_from_inventory(db, user_id, seed_type, 1)
        await set_village_tile(db, player.village_id, player.village_x, player.village_y, crop["planted"])
        _invalidate_vp(user_id)
        grid = await _cached_grid(user_id, player, seed_w, db)
        content = render_grid(grid, player, f"🌱 You plant {seed_type.replace('_',' ')} in the soil. Water it to grow!")

    await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_plant_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel seed selection."""
    db = await get_database(guild_id)
    seed_w = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await _cached_grid(user_id, player, seed_w, db)
    content = render_grid(grid, player, "Planting cancelled.")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))


async def _plant_overworld_item(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player, db, item_id: str
) -> None:
    """Plant a sapling, ancient_seed, or ancient_sapling item on the player's current dirt tile."""
    seed_w = await get_or_create_world(db, guild_id)
    wx, wy = player.world_x, player.world_y
    if item_id == "pinecone":
        tile_type = "pinecone_planted"
        msg = "🌲 You press the pinecone into the dirt. Water it to sprout a sapling!"
    elif item_id == "ancient_seed":
        tile_type = "ancient_planted"
        msg = "🌱 You plant the ancient seed in the dirt. Water it to sprout a sapling!"
    elif item_id == "ancient_sapling":
        tile_type = "ancient_sapling"
        msg = "🌳 You plant the ancient sapling in the dirt. Water it to grow a mighty tree!"
    else:
        tile_type = "sapling"
        msg = "🌱 You plant the sapling in the dirt. Water it to grow a tree!"
    await set_tile_override(db, wx, wy, tile_type)
    await remove_from_inventory(db, user_id, item_id, 1)
    grid = await load_viewport(wx, wy, seed_w, db)
    content = render_grid(grid, player, msg)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_plant_overworld_choice(
    interaction: discord.Interaction, guild_id: int, user_id: int, item_id: str
) -> None:
    """Handle overworld plant choice from PlantOverworldView."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    seed_w = await get_or_create_world(db, guild_id)
    wx, wy = player.world_x, player.world_y
    grid = await load_viewport(wx, wy, seed_w, db)
    vc_ = 4
    center_t = grid[vc_][vc_].terrain if len(grid) > vc_ and len(grid[vc_]) > vc_ else None
    if center_t != "dirt":
        content = render_grid(grid, player, "You're no longer standing on a dirt patch.")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
        return
    inv = await get_inventory(db, user_id)
    has_item = any(it["item_id"] == item_id and it["quantity"] > 0 for it in inv)
    if not has_item:
        content = render_grid(grid, player, f"🌱 You don't have any {item_id.replace('_', ' ')}.")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=_game_view(guild_id, user_id, player, grid=grid))
        return
    await _plant_overworld_item(interaction, guild_id, user_id, player, db, item_id)


async def handle_canoe_sail(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open destination picker for canoe fast-travel."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_canoe:
        return

    dests = await _find_canoe_destinations(player, db)
    if not dests:
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "No reachable landings found on this waterway.")
        dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=CanoeView(guild_id, user_id, dock_dirs=dock_dirs),
        )
        return

    _ui_state[user_id] = {"type": "canoe_dest", "dests": dests, "page": 0}
    dest_lines = "\n".join(
        f"**{i+1}.** 🏝️ ({lx}, {ly})"
        for i, (lx, ly) in enumerate(dests[:5])
    )
    total = len(dests)
    page_count = max(1, (total + 4) // 5)
    content = (
        f"🗺️ **Choose a destination** (Page 1/{page_count})\n"
        f"{dest_lines}\n\n"
        f"*{total} landing{'s' if total != 1 else ''} reachable on this waterway.*"
    )
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeDestView(guild_id, user_id, dests, page=0),
    )


async def handle_canoe_dest(
    interaction: discord.Interaction, guild_id: int, user_id: int, idx: int
) -> None:
    """Teleport canoe to selected landing's adjacent water tile."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    dests = state.get("dests", [])
    page = state.get("page", 0)
    abs_idx = page * 5 + idx
    if abs_idx >= len(dests):
        return

    lx, ly = dests[abs_idx]
    # Find a water tile adjacent to the landing for the canoe to sit at
    water_tile: tuple[int, int] | None = None
    for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        ax, ay = lx + ddx, ly + ddy
        if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
            t = await load_single_tile(ax, ay, seed, db)
            if (t.structure or t.terrain) in CANOE_PASSABLE:
                water_tile = (ax, ay)
                break

    if not water_tile:
        # Landing has no adjacent water — place on landing itself (rare edge case)
        player.world_x, player.world_y = lx, ly
        player.in_canoe = False
        await update_player_stats(db, user_id, world_x=lx, world_y=ly, in_canoe=0)
        _ui_state.pop(user_id, None)
        grid = await load_viewport(lx, ly, seed, db)
        content = render_grid(grid, player, f"You sail to the landing at ({lx},{ly}).")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return

    wx, wy = water_tile
    player.world_x, player.world_y = wx, wy
    await update_player_position(db, user_id, wx, wy)
    _ui_state.pop(user_id, None)
    grid = await load_viewport(wx, wy, seed, db)
    content = render_grid(grid, player, f"You sail to the landing at ({lx},{ly}). Dock to go ashore.")
    dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeView(guild_id, user_id, dock_dirs=dock_dirs),
    )


async def handle_canoe_dest_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    dests = state.get("dests", [])
    page = state.get("page", 0)
    total_pages = max(1, (len(dests) + 4) // 5)
    new_page = max(0, min(total_pages - 1, page + delta))
    _ui_state[user_id] = {"type": "canoe_dest", "dests": dests, "page": new_page}
    page_dests = dests[new_page * 5: new_page * 5 + 5]
    dest_lines = "\n".join(
        f"**{new_page*5+i+1}.** 🏝️ ({lx}, {ly})"
        for i, (lx, ly) in enumerate(page_dests)
    )
    content = (
        f"🗺️ **Choose a destination** (Page {new_page+1}/{total_pages})\n"
        f"{dest_lines}\n\n"
        f"*{len(dests)} landing{'s' if len(dests) != 1 else ''} reachable.*"
    )
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeDestView(guild_id, user_id, dests, page=new_page),
    )


async def handle_canoe_dest_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    _ui_state.pop(user_id, None)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player)
    dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=CanoeView(guild_id, user_id, dock_dirs=dock_dirs),
    )


# ── Ocean handlers ────────────────────────────────────────────────────────────

_OCEAN_DIRS: dict[str, tuple[int, int]] = {
    "up":        (0, -1),
    "down":      (0,  1),
    "left":      (-1,  0),
    "right":     (1,  0),
    "upleft":    (-1, -1),
    "upright":   (1, -1),
    "downleft":  (-1,  1),
    "downright": (1,  1),
}


def _hs_spawn(world_x: int, world_y: int, coast_edge: int) -> tuple[int, int]:
    """Return (ocean_x, ocean_y) spawn position when entering the high seas.

    The player always spawns one tile in from the harbor/coast boundary so
    they can sail back with a single move.
      edge 0 (south): harbor at oy=0, deep at high oy  → spawn oy=1
      edge 1 (north): harbor at oy=OCEAN_SIZE-1         → spawn oy=OCEAN_SIZE-2
      edge 2 (west) : harbor at ox=OCEAN_SIZE-1         → spawn ox=OCEAN_SIZE-2
      edge 3 (east) : harbor at ox=0                    → spawn ox=1
    """
    cross = int
    if coast_edge in (0, 1):        # N/S ocean: world_x maps to ocean_x
        ox = max(0, min(OCEAN_SIZE - 1, int(world_x / WORLD_SIZE * OCEAN_SIZE)))
        oy = 1 if coast_edge == 0 else OCEAN_SIZE - 2
    else:                            # E/W ocean: world_y maps to ocean_y
        oy = max(0, min(OCEAN_SIZE - 1, int(world_y / WORLD_SIZE * OCEAN_SIZE)))
        ox = OCEAN_SIZE - 2 if coast_edge == 2 else 1
    return ox, oy


def _hs_at_harbor(ox: int, oy: int, coast_edge: int) -> bool:
    """True when one more step toward shore would leave the high-seas grid."""
    return (
        (coast_edge == 0 and oy == 0) or
        (coast_edge == 1 and oy == OCEAN_SIZE - 1) or
        (coast_edge == 2 and ox == OCEAN_SIZE - 1) or
        (coast_edge == 3 and ox == 0)
    )


def _hs_past_harbor(nx: int, ny: int, coast_edge: int) -> bool:
    """True when the proposed move steps outside the high-seas grid on the harbor side."""
    return (
        (coast_edge == 0 and ny < 0) or
        (coast_edge == 1 and ny >= OCEAN_SIZE) or
        (coast_edge == 2 and nx >= OCEAN_SIZE) or
        (coast_edge == 3 and nx < 0)
    )


async def handle_ocean_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        return

    dx, dy = _OCEAN_DIRS.get(direction, (0, 0))

    # ── High-seas mode (separate 200×200 grid) ──────────────────────────────
    if player.in_high_seas:
        nx, ny = player.ocean_x + dx, player.ocean_y + dy

        from dwarf_explorer.world.terrain import get_coast_boundary as _gcb
        _hs_coast_edge, _ = _gcb(seed)

        # Moving back past the harbor boundary → auto-return to harbour village
        if _hs_past_harbor(nx, ny, _hs_coast_edge):
            hwx, hwy = player.ocean_harbor_wx, player.ocean_harbor_wy
            vid, _vx, _vy, dock_x, dock_y = await get_or_create_harbor_village(seed, hwx, hwy, db)
            player.in_high_seas = False
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = dock_x, dock_y
            player.village_wx, player.village_wy = hwx, hwy
            await update_player_ocean_state(db, user_id, False, 0, 0)
            await update_player_village_state(db, user_id, True, vid, dock_x, dock_y, hwx, hwy)
            grid = await load_village_viewport(vid, dock_x, dock_y, db, user_id=user_id)
            delivery_msg = await _complete_delivery_quests_for_village(db, user_id, hwx, hwy)
            _hs_msg = f"⚓ You sail back into the harbour.{' ' + delivery_msg if delivery_msg else ''}"
            content = render_grid(grid, player, _hs_msg)
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return

        if not (0 <= nx < OCEAN_SIZE and 0 <= ny < OCEAN_SIZE):
            grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
            nav = _ui_state.get(user_id, {}).get("nav_target")
            content = render_grid(grid, player, "The vast ocean stretches endlessly in that direction.", nav_target=nav)
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=OceanView(guild_id, user_id,
                               dock_available=_hs_at_harbor(player.ocean_x, player.ocean_y, _hs_coast_edge)),
            )
            return

        target_ocean = load_ocean_single_tile(nx, ny, seed)
        if target_ocean.structure in ("island", "volcano_island"):
            # Block movement onto island tile — show dock button instead
            _ui_state[user_id] = {**_ui_state.get(user_id, {}), "island_target": (nx, ny)}
            has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
            grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
            nav = _ui_state.get(user_id, {}).get("nav_target")
            if target_ocean.structure == "volcano_island":
                shore_msg = "🌋 A volcano island looms ahead. Use 🏝️ Island to go ashore."
            else:
                shore_msg = "🏝️ An island lies ahead. Use 🏝️ Island to go ashore."
            content = render_grid(grid, player, shore_msg, nav_target=nav)
            view = OceanView(guild_id, user_id,
                             dock_available=_hs_at_harbor(player.ocean_x, player.ocean_y, _hs_coast_edge),
                             island_nearby=True,
                             has_fishing_rod=has_rod)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        player.ocean_x, player.ocean_y = nx, ny
        await update_player_ocean_state(db, user_id, False, nx, ny, in_high_seas=True)

        # Check for ocean encounter (1% per tile)
        enc_rng = _random.Random(hash((user_id, nx, ny, seed, "ocean")))
        enemy_type = _roll_encounter(enc_rng, OCEAN_ENCOUNTER_RATES, gate=0.01)
        if enemy_type:
            grid = load_ocean_viewport(nx, ny, seed)
            arena_rng = _random.Random(hash((user_id, nx, ny, enemy_type, "ocean")))
            arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
            arena["naval"] = True  # enemy attacks damage ship_hp, not player_hp
            player.in_combat = True
            player.combat_enemy_type = enemy_type
            player.combat_enemy_hp = ENEMY_STATS[enemy_type][0]
            player.combat_enemy_x = ex
            player.combat_enemy_y = ey
            player.combat_player_x = ARENA_SIZE // 2
            player.combat_player_y = ARENA_SIZE // 2
            player.combat_moves_left = COMBAT_MOVES_DEFAULT + (1 if player.accessory == "ring_of_time" else 0)
            _ui_state[user_id] = {"type": "combat", "arena": arena}
            await save_combat_state(db, user_id, player)
            content = render_arena(arena, player)
            view = CombatView(guild_id, user_id,
                              trapped=arena["player_trapped"],
                              moves_left=player.combat_moves_left)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        # Check all 8 neighbours for island tiles — show Island button if any found
        _island_adj: tuple[int, int] | None = None
        for _adx in (-1, 0, 1):
            for _ady in (-1, 0, 1):
                if _adx == 0 and _ady == 0:
                    continue
                _adj = load_ocean_single_tile(nx + _adx, ny + _ady, seed)
                if _adj.structure in ("island", "volcano_island"):
                    _island_adj = (nx + _adx, ny + _ady)
                    break
            if _island_adj:
                break

        if _island_adj:
            _ui_state[user_id] = {**_ui_state.get(user_id, {}), "island_target": _island_adj}
        else:
            # Clear stale island_target when moving away from all islands
            if _ui_state.get(user_id, {}).get("island_target"):
                _ui_state[user_id] = {k: v for k, v in _ui_state.get(user_id, {}).items()
                                       if k != "island_target"}

        has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        island_nearby = bool(_island_adj)
        grid = load_ocean_viewport(nx, ny, seed)
        nav = _ui_state.get(user_id, {}).get("nav_target")
        content = render_grid(grid, player, nav_target=nav)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=OceanView(guild_id, user_id,
                           dock_available=_hs_at_harbor(nx, ny, _hs_coast_edge),
                           island_nearby=island_nearby,
                           has_fishing_rod=has_rod),
        )
        return

    # ── Boat wilderness mode (in_ocean=True, world_x/world_y used) ──────────
    nx, ny = player.world_x + dx, player.world_y + dy

    # Moving off the world edge → enter the high seas
    if not (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE):
        from dwarf_explorer.world.terrain import get_coast_boundary as _gcb
        _coast_edge, _ = _gcb(seed)
        spawn_ox, spawn_oy = _hs_spawn(player.world_x, player.world_y, _coast_edge)
        player.in_ocean = False
        player.in_high_seas = True
        player.ocean_x = spawn_ox
        player.ocean_y = spawn_oy
        has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
        await update_player_ocean_state(
            db, user_id, False,
            player.ocean_x, player.ocean_y,
            player.ocean_harbor_wx, player.ocean_harbor_wy,
            in_high_seas=True,
        )
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        content = render_grid(grid, player, "🌊 You sail beyond the horizon into the open ocean!")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=OceanView(guild_id, user_id, dock_available=False, has_fishing_rod=has_rod),
        )
        return

    target = await load_single_tile(nx, ny, seed, db)
    terrain = target.structure or target.terrain

    if terrain not in OCEAN_WALKABLE:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        harbor_adj = await _adjacent_harbor(player, seed, db)
        content = render_grid(grid, player, "Your boat can't sail onto land.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=BoatView(guild_id, user_id, dock_available=(harbor_adj is not None)),
        )
        return

    # Moving onto a harbor tile → sail into harbour village
    if terrain == "harbor":
        vid, vx, vy, _dk_x, _dk_y = await get_or_create_harbor_village(seed, nx, ny, db)
        player.in_ocean = False
        player.in_village = True
        player.village_id = vid
        player.village_x, player.village_y = vx, vy
        player.village_wx, player.village_wy = nx, ny
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_village_state(db, user_id, True, vid, vx, vy, nx, ny)
        grid = await load_village_viewport(vid, vx, vy, db, user_id=user_id)
        delivery_msg = await _complete_delivery_quests_for_village(db, user_id, nx, ny)
        _harbour_msg = f"⚓ You sail into the harbour.{' ' + delivery_msg if delivery_msg else ''}"
        content = render_grid(grid, player, _harbour_msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
        return

    player.world_x, player.world_y = nx, ny
    await update_player_position(db, user_id, nx, ny)
    await update_player_ocean_state(db, user_id, True)

    harbor_adj = await _adjacent_harbor(player, seed, db)
    grid = await load_viewport(nx, ny, seed, db)
    content = render_grid(grid, player)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=BoatView(guild_id, user_id, dock_available=(harbor_adj is not None)),
    )


async def handle_ocean_dock(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Dock from ocean (boat or high-seas mode) back to the harbour village."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # ── Boat wilderness mode: dock at adjacent harbour ───────────────────────
    if player.in_ocean:
        harbor = await _adjacent_harbor(player, seed, db)
        if harbor is None:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, "No harbour nearby to dock at.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=BoatView(guild_id, user_id, dock_available=False),
            )
            return
        hwx, hwy = harbor
        vid, _vx, _vy, dock_x, dock_y = await get_or_create_harbor_village(seed, hwx, hwy, db)
        player.in_ocean = False
        player.in_village = True
        player.village_id = vid
        player.village_x, player.village_y = dock_x, dock_y
        player.village_wx, player.village_wy = hwx, hwy
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_village_state(db, user_id, True, vid, dock_x, dock_y, hwx, hwy)
        grid = await load_village_viewport(vid, dock_x, dock_y, db, user_id=user_id)
        delivery_msg = await _complete_delivery_quests_for_village(db, user_id, hwx, hwy)
        _dock_msg = f"⚓ You dock at the harbour and step ashore.{' ' + delivery_msg if delivery_msg else ''}"
        content = render_grid(grid, player, _dock_msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
        return

    # ── High-seas mode: must be at coast row (y=0) to dock ──────────────────
    if player.in_high_seas:
        if player.ocean_y != 0:
            grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
            content = render_grid(grid, player,
                                  "You must sail back to the shoreline (row 0) to dock.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=OceanView(guild_id, user_id, dock_available=False),
            )
            return
        hwx, hwy = player.ocean_harbor_wx, player.ocean_harbor_wy
        vid, _vx, _vy, dock_x, dock_y = await get_or_create_harbor_village(seed, hwx, hwy, db)
        player.in_high_seas = False
        player.in_village = True
        player.village_id = vid
        player.village_x, player.village_y = dock_x, dock_y
        player.village_wx, player.village_wy = hwx, hwy
        await update_player_ocean_state(db, user_id, False, 0, 0)
        await update_player_village_state(db, user_id, True, vid, dock_x, dock_y, hwx, hwy)
        grid = await load_village_viewport(vid, dock_x, dock_y, db, user_id=user_id)
        delivery_msg = await _complete_delivery_quests_for_village(db, user_id, hwx, hwy)
        _hs_dock_msg = f"⚓ You dock at the harbour and step ashore.{' ' + delivery_msg if delivery_msg else ''}"
        content = render_grid(grid, player, _hs_dock_msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
        return



async def handle_boat_grapple(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Toss the grappling hook overboard to dredge up sunken treasure."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        return

    rng = _random.Random()  # fresh random every cast
    roll = rng.random()
    if roll < 0.04:
        items = [("gold_coin", rng.randint(5, 20)), ("map_fragment", 1)]
        item_id, qty = rng.choice(items)
        await add_to_inventory(db, user_id, item_id, qty)
        label = "gold coins" if item_id == "gold_coin" else "a map fragment"
        msg = f"🪝 You haul up the hook… **{label} found!**"
    elif roll < 0.18:
        await add_to_inventory(db, user_id, "fish", 1)
        msg = "🪝 You haul up the hook… a **fish** tangled in the line!"
    elif roll < 0.22:
        await add_to_inventory(db, user_id, "seaweed", 1)
        msg = "🪝 You haul up a clump of **seaweed**."
    else:
        msg = "🪝 You toss the hook overboard… nothing but water."

    if player.in_high_seas:
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        content = render_grid(grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=OceanView(guild_id, user_id, dock_available=(player.ocean_y == 0)),
        )
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        harbor_adj = await _adjacent_harbor(player, seed, db)
        content = render_grid(grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=BoatView(guild_id, user_id, dock_available=(harbor_adj is not None)),
        )


# ── Ship interior handlers ────────────────────────────────────────────────────

async def handle_ship_enter(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Board the ship interior from boat mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        return

    player.in_ship = True
    player.ship_room = "helm"
    player.ship_x, player.ship_y = HELM_SPAWN
    await update_player_ship_state(db, user_id, True, "helm", ship_x=player.ship_x, ship_y=player.ship_y)

    grid = load_ship_viewport("helm", player.ship_x, player.ship_y, player=player)
    content = render_grid(grid, player, "\u2693 You board your ship at the helm.")
    view = _ship_game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_leave(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Return from ship interior back to boat navigation."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        return

    was_high_seas = player.in_high_seas
    player.in_ship = False
    player.ship_room = "helm"
    player.ship_x = 0
    player.ship_y = 0
    await update_player_ship_state(db, user_id, False, "helm", ship_x=0, ship_y=0)

    has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
    if was_high_seas:
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        content = render_grid(grid, player, "⚓ You return to the helm and take the wheel.")
        view = OceanView(guild_id, user_id, dock_available=(player.ocean_y == 0),
                        has_fishing_rod=has_rod)
    else:
        harbor_adj = await _adjacent_harbor(player, seed, db)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "⚓ You return to the helm and take the wheel.")
        view = BoatView(guild_id, user_id, dock_available=(harbor_adj is not None),
                        has_fishing_rod=has_rod)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Move player within ship interior."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        return

    dx, dy = DIRECTIONS[direction]
    nx, ny = player.ship_x + dx, player.ship_y + dy

    # Load target tile and check walkability
    target_grid = load_ship_viewport(player.ship_room, nx, ny, player=player)
    target_tile = target_grid[4][4]  # center = new position
    ok, msg = can_move_ship(target_tile)
    if not ok:
        grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
        content = render_grid(grid, player, f"\U0001F6AB {msg}")
        view = _ship_game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Check for door at target position
    door_target = get_door_target(player.ship_room, nx, ny)
    if door_target:
        new_room, new_x, new_y = door_target
        player.ship_room = new_room
        player.ship_x, player.ship_y = new_x, new_y
        await update_player_ship_state(db, user_id, True, new_room, ship_x=new_x, ship_y=new_y)
        room_names = {"helm": "the helm deck", "quarters": "the captain's quarters", "lower_deck": "the lower deck"}
        grid = load_ship_viewport(new_room, new_x, new_y, player=player)
        content = render_grid(grid, player, f"\U0001F6AA You enter {room_names.get(new_room, new_room)}.")
        view = _ship_game_view(guild_id, user_id, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Normal move
    player.ship_x, player.ship_y = nx, ny
    await update_player_ship_state(db, user_id, True, player.ship_room, ship_x=nx, ship_y=ny)
    grid = load_ship_viewport(player.ship_room, nx, ny, player=player)
    content = render_grid(grid, player, "")
    view = _ship_game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_room(
    interaction: discord.Interaction, guild_id: int, user_id: int, room: str
) -> None:
    """Navigate between ship rooms: helm / quarters / lower_deck."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        return

    player.ship_room = room
    await update_player_ship_state(db, user_id, True, room)

    if room == "helm":
        # Switch to grid-based GameView for the helm so hull damage holes are visible
        from dwarf_explorer.world.ships import HELM_SPAWN
        player.ship_x, player.ship_y = HELM_SPAWN
        await update_player_ship_state(db, user_id, True, "helm", ship_x=HELM_SPAWN[0], ship_y=HELM_SPAWN[1])
        grid = load_ship_viewport("helm", player.ship_x, player.ship_y, player=player)
        content = render_grid(grid, player, "⚓ Helm deck. Walk to 🕳️ holes and press Interact (hammer equipped) to repair them.")
        view = _ship_game_view(guild_id, user_id, player)
    else:
        content = render_ship_room(player)
        view = ShipView(guild_id, user_id, room=room,
                        ship_hp=player.ship_hp, ship_max_hp=player.ship_max_hp)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_repair(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Legacy repair action — redirects player to the new hull damage repair mechanic."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_ship:
        return

    # Send player to helm deck grid view so they can find and repair hull damage holes
    from dwarf_explorer.world.ships import HELM_SPAWN
    player.ship_room = "helm"
    player.ship_x, player.ship_y = HELM_SPAWN
    await update_player_ship_state(db, user_id, True, "helm", ship_x=HELM_SPAWN[0], ship_y=HELM_SPAWN[1])
    grid = load_ship_viewport("helm", player.ship_x, player.ship_y, player=player)
    msg = ("🔨 Repair holes in the helm deck: equip a **hammer**, carry **nails** and **planks**, "
           "walk to a 🕳️ hull damage tile, and press Interact to patch it (+5 HP per hole, costs 2 nails + 1 plank).")
    content = render_grid(grid, player, msg)
    view = _ship_game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def _open_ship_chest(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    chest_type: str,  # "personal" | "cargo"
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if chest_type == "personal":
        chest_items = await get_ship_personal_items(db, user_id)
        chest_name = "Personal Chest"
    else:
        chest_items = await get_ship_cargo_items(db, user_id)
        chest_name = "Ship Cargo"

    player_items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    prev_arena = _ui_state.get(user_id, {}).get("arena")
    _ui_state[user_id] = {
        "type": f"ship_chest_{chest_type}",
        "selected": 0,
        "chest_view": "player",
        "prev_arena": prev_arena,
    }
    content = render_ship_chest(chest_items, player_items, 0, "player",
                                chest_name, player, inv_rows, inv_cols)
    view = ShipChestView(guild_id, user_id, chest_type, "player")
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_chest_open_personal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _open_ship_chest(interaction, guild_id, user_id, "personal")


async def handle_ship_chest_open_cargo(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _open_ship_chest(interaction, guild_id, user_id, "cargo")


async def _ship_chest_action(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    chest_type: str, action: str,  # "prev" | "next" | "switch" | "deposit" | "withdraw"
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    expected_type = f"ship_chest_{chest_type}"
    if state.get("type") != expected_type:
        return

    selected = state.get("selected", 0)
    view_mode = state.get("chest_view", "player")
    chest_name = "Personal Chest" if chest_type == "personal" else "Ship Cargo"

    get_fn = get_ship_personal_items if chest_type == "personal" else get_ship_cargo_items
    dep_fn = ship_personal_deposit if chest_type == "personal" else ship_cargo_deposit
    wth_fn = ship_personal_withdraw if chest_type == "personal" else ship_cargo_withdraw

    chest_items = await get_fn(db, user_id)
    player_items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)

    msg = ""
    if action == "prev":
        source = player_items if view_mode == "player" else chest_items
        total = inv_rows * inv_cols if view_mode == "player" else 9 * 4
        selected = (selected - 1) % max(1, min(len(source), total))
    elif action == "next":
        source = player_items if view_mode == "player" else chest_items
        total = inv_rows * inv_cols if view_mode == "player" else 9 * 4
        selected = (selected + 1) % max(1, min(len(source), total))
    elif action == "switch":
        view_mode = "chest" if view_mode == "player" else "player"
        selected = 0
    elif action == "deposit":
        if selected < len(player_items):
            item = player_items[selected]
            ok = await dep_fn(db, user_id, item["item_id"], 1)
            msg = f"⬇ Deposited {item['item_id'].replace('_',' ').title()}." if ok else "❌ Could not deposit."
            chest_items = await get_fn(db, user_id)
            player_items = await get_inventory(db, user_id)
    elif action == "withdraw":
        if selected < len(chest_items):
            item = chest_items[selected]
            ok = await wth_fn(db, user_id, item["item_id"], 1)
            msg = f"⬆ Withdrew {item['item_id'].replace('_',' ').title()}." if ok else "❌ Inventory full."
            chest_items = await get_fn(db, user_id)
            player_items = await get_inventory(db, user_id)

    _ui_state[user_id] = {
        "type": expected_type, "selected": selected, "chest_view": view_mode,
        "prev_arena": state.get("prev_arena"),  # preserve so combat can be restored
    }
    content = render_ship_chest(chest_items, player_items, selected, view_mode,
                                chest_name, player, inv_rows, inv_cols)
    if msg:
        content += f"\n> {msg}"
    view = ShipChestView(guild_id, user_id, chest_type, view_mode)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ship_chest_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Return from ship chest view back to the ship room (or combat if opened during a fight)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    prev_arena = _ui_state.get(user_id, {}).get("prev_arena")
    _ui_state.pop(user_id, None)

    # If chest was opened during combat, restore the combat view
    if player.in_combat and prev_arena is not None:
        _ui_state[user_id] = {"type": "combat", "arena": prev_arena}
        content = render_arena(prev_arena, player)
        view = _combat_view(guild_id, user_id, prev_arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
    content = render_grid(grid, player, "\U0001F4E6 You close the chest.")
    view = _ship_game_view(guild_id, user_id, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Island handlers ───────────────────────────────────────────────────────────

async def handle_island_arrive(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    ox: int, oy: int,
) -> None:
    """Called when player sails onto an island tile in the high seas."""
    from dwarf_explorer.world.ocean import get_ocean_structure
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # Determine island type from ocean structure
    structure = get_ocean_structure(ox, oy, seed)
    is_volcano = (structure == "volcano_island")
    island_type = "volcano" if is_volcano else "regular"

    from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
    _island_id, tiles, (dock_x, dock_y) = await get_or_create_island_data(
        db, ox, oy, seed, island_type=island_type
    )

    player.in_high_seas = False
    player.in_island = True
    player.island_ox = ox
    player.island_oy = oy
    # Place player at the dock
    player.ocean_x = dock_x
    player.ocean_y = dock_y
    await update_player_ocean_state(db, user_id, False, 0, 0, in_high_seas=False)
    await update_player_island_state(db, user_id, True, ox, oy)
    # Reuse ocean_x/ocean_y as island_x/island_y for position
    await update_player_ocean_state(db, user_id, False, dock_x, dock_y)

    grid = load_island_viewport(tiles, dock_x, dock_y)
    arrive_msg = "🌋 You approach the volcano island and row ashore." if is_volcano else "🏝️ You row ashore onto the island."
    content = render_grid(grid, player, arrive_msg)
    # Clear any island_target from high-seas ui_state
    _ui_state.pop(user_id, None)
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Move player within island interior."""
    from dwarf_explorer.config import ISLAND_WALKABLE
    from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport, ISLAND_SIZE
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_island:
        return

    ox, oy = player.island_ox, player.island_oy
    # player position stored in ocean_x/ocean_y while on island
    px, py = player.ocean_x, player.ocean_y

    _DIRS = {"up": (0,-1), "down": (0,1), "left": (-1,0), "right": (1,0)}
    dx, dy = _DIRS.get(direction, (0, 0))
    nx, ny = px + dx, py + dy

    _island_id, tiles, (dock_x, dock_y) = await get_or_create_island_data(db, ox, oy, seed)
    tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
    target_terrain = tile_map.get((nx, ny), "island_void")

    if target_terrain == "vol_lava":
        grid = load_island_viewport(tiles, px, py)
        content = render_grid(grid, player, "🔥 The lava is impassable!")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if target_terrain == "vol_crater":
        grid = load_island_viewport(tiles, px, py)
        content = render_grid(grid, player, "🌑 The volcano crater is too dangerous to enter!")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if target_terrain not in ISLAND_WALKABLE:
        grid = load_island_viewport(tiles, px, py)
        content = render_grid(grid, player, "You can't go that way.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    player.ocean_x, player.ocean_y = nx, ny
    await update_player_ocean_state(db, user_id, False, nx, ny)

    grid = load_island_viewport(tiles, nx, ny)
    content = render_grid(grid, player)
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_loot(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Loot the island chest (once per island)."""
    from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_island:
        return

    ox, oy = player.island_ox, player.island_oy
    px, py = player.ocean_x, player.ocean_y

    already = await is_island_looted(db, ox, oy)
    _island_id, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
    grid = load_island_viewport(tiles, px, py)
    if already:
        content = render_grid(grid, player, "💰 The chest has already been looted.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await mark_island_looted(db, ox, oy)

    loot_rng = _random.Random(hash((ox, oy, seed, "island_loot")))
    roll = loot_rng.random()
    if roll < 0.4:
        item_id, qty = "gold_coin", loot_rng.randint(10, 50)
    elif roll < 0.65:
        item_id, qty = "gem", loot_rng.randint(1, 3)
    elif roll < 0.80:
        item_id, qty = "map_fragment", 1
    else:
        item_id, qty = "iron_ingot", loot_rng.randint(2, 5)

    await add_to_inventory(db, user_id, item_id, qty)
    label = item_id.replace("_", " ").title()

    content = render_grid(grid, player, f"💰 You pry open the chest — **{label} ×{qty}**!")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_leave(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Leave island, return to high seas at the island's ocean coordinates."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_island:
        return

    ox, oy = player.island_ox, player.island_oy
    player.in_island = False
    player.in_high_seas = True
    player.ocean_x, player.ocean_y = ox, oy
    await update_player_island_state(db, user_id, False)
    await update_player_ocean_state(db, user_id, False, ox, oy, in_high_seas=True)

    has_rod = (player.hand_1 == "fishing_rod" or player.hand_2 == "fishing_rod")
    grid = load_ocean_viewport(ox, oy, seed)
    content = render_grid(grid, player, "⛵ You row back to your boat.")
    view = OceanView(guild_id, user_id, dock_available=(oy == 0), has_fishing_rod=has_rod)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_ocean_fish(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Handle the 🎣 Fish button from OceanView or BoatView."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not (player.in_ocean or player.in_high_seas):
        return

    hand_items: set[str] = set()
    if player.hand_1:
        hand_items.add(player.hand_1)
    if player.hand_2:
        hand_items.add(player.hand_2)

    if "fishing_rod" not in hand_items:
        return

    roll = _random.random()
    if roll < 0.45:
        await add_to_inventory(db, user_id, "fish", 1)
        msg = "🎣 You cast your line into the ocean... and reel in a **fish**!"
    elif roll < 0.50:
        await add_to_inventory(db, user_id, "gem", 1)
        msg = "🎣 Something shiny on the hook — you pulled up a **gem**!"
    elif roll < 0.51:
        await add_to_inventory(db, user_id, "map_fragment", 1)
        msg = "🎣 You reel in something unusual — a **map fragment**!"
    elif roll < 0.516 and player.in_high_seas:
        # 0.6% chance (high seas only) — Star Fragment
        await add_to_inventory(db, user_id, "star_fragment", 1)
        msg = "🎣 ⭐ Something otherworldly on the line — a **Star Fragment**! The sundial calls to you."
    elif roll < 0.522:
        # ~0.6% chance — Gust of Aevos (rare ingredient for Breath of the Sea)
        await add_to_inventory(db, user_id, "gust_of_aevos", 1)
        msg = "\U0001F4A8 A magical current wraps around your line — you reel in a **Gust of Aevos**! *(Craft: 2 seaweed + 1 Gust of Aevos → Breath of the Sea)*"
    else:
        msg = "🎣 You cast your line... the fish got away."

    has_rod = True
    if player.in_high_seas:
        grid = load_ocean_viewport(player.ocean_x, player.ocean_y, seed)
        island_nearby = bool(_ui_state.get(user_id, {}).get("island_target"))
        view = OceanView(guild_id, user_id,
                         dock_available=(player.ocean_y == 0),
                         island_nearby=island_nearby,
                         has_fishing_rod=has_rod)
    else:
        harbor_adj = await _adjacent_harbor(player, seed, db)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        view = BoatView(guild_id, user_id,
                        dock_available=(harbor_adj is not None),
                        has_fishing_rod=has_rod)
    content = render_grid(grid, player, msg)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_island_dock_hs(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Dock at an island from the high seas (triggered by 🏝️ Island button)."""
    state = _ui_state.get(user_id, {})
    island_target = state.get("island_target")
    if not island_target:
        return
    ox, oy = island_target
    await handle_island_arrive(interaction, guild_id, user_id, ox, oy)


# ── Merchant handlers ────────────────────────────────────────────────────────

async def handle_merchant_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    if state.get("type") != "merchant":
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        await interaction.response.edit_message(
            embed=_embed(render_grid(grid, player)), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return
    catalog = state["catalog"]
    new_sel = (state["selected"] + delta) % max(1, len(catalog))
    _ui_state[user_id]["selected"] = new_sel
    content = _render_merchant(catalog, new_sel, player)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=MerchantView(guild_id, user_id))


async def handle_merchant_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    if state.get("type") != "merchant":
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        await interaction.response.edit_message(
            embed=_embed(render_grid(grid, player)), content=None,
            view=_game_view(guild_id, user_id, player),
        )
        return
    catalog = state["catalog"]
    sel = state.get("selected", 0)
    if sel >= len(catalog):
        return
    item = catalog[sel]
    if user_id != ADMIN_PLAYER_ID and player.gold < item["price"]:
        content = _render_merchant(catalog, sel, player) + f"\n\n*Not enough gold!*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=MerchantView(guild_id, user_id))
        return
    if user_id != ADMIN_PLAYER_ID:
        player.gold -= item["price"]
        await update_player_stats(db, user_id, gold=player.gold)
    await add_to_inventory(db, user_id, item["id"], 1)
    content = _render_merchant(catalog, sel, player) + f"\n\n*Bought {item['name']}!*"
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=MerchantView(guild_id, user_id))


async def handle_merchant_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    _ui_state.pop(user_id, None)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player, "The merchant waves farewell and continues on their way.")
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


# ── Village entry helpers ─────────────────────────────────────────────────────

async def _complete_delivery_quests_for_village(
    db, user_id: int, village_wx: int, village_wy: int
) -> str:
    """Auto-complete delivery quests whose destination matches this village.

    Returns a bonus notification string (empty if nothing completed).
    """
    from dwarf_explorer.game.quests import get_completable_delivery_quests, complete_quest
    from dwarf_explorer.database.repositories import give_quest_reward as _give_qr
    completable = await get_completable_delivery_quests(db, user_id, village_wx, village_wy)
    if not completable:
        return ""
    msgs: list[str] = []
    for pq in completable:
        reward = await complete_quest(db, user_id, pq["id"])
        if reward:
            reward_str = await _give_qr(db, user_id,
                                        reward["gold"], reward["xp"], reward.get("item"))
            msgs.append(f"\U0001F4CB Quest **{pq['title']}** complete! {reward_str}")
            # Remove the delivery parcel that was granted on quest accept
            await remove_from_inventory(db, user_id, "merchant_parcel", 1)
    return " ".join(msgs)


# ── Wayerwood signal helper ───────────────────────────────────────────────────

def _wayerwood_signal(user_id: int, dist_now: int) -> str:
    """Return the hot/cold flavour string by comparing dist_now to the last
    stored reading.  Always updates the stored value after comparing.

    "Hums steadily" is reserved for when the player is directly adjacent
    (cardinal distance == 1) — right next to the bombable wall.
    """
    last_dist = _ui_state.get(user_id, {}).get("ww_last_dist")
    _ui_state.setdefault(user_id, {})["ww_last_dist"] = dist_now
    if dist_now == 1:
        return "🪄 *The wayerwood hums steadily. The wall is right before you.*"
    if last_dist is None:
        return "🪄 *The wayerwood pulses faintly. Something stirs within these walls...*"
    elif dist_now < last_dist:
        return "🪄 *The wayerwood pulses... pulling you forward.*"
    elif dist_now > last_dist:
        return "🪄 *The wayerwood dims... you've veered away.*"
    else:
        return "🪄 *The wayerwood quivers faintly — keep moving to get a clearer reading.*"


async def _try_wayerwood_attune(player, user_id: int, db) -> str | None:
    """Hot/cold cave signal for an attuned wayerwood held in hand.

    Returns a flavour-text string when attuned_wayerwood is in hand.
    Returns None otherwise (caller falls through to default message).
    No resources consumed — attunement already happened during crafting.
    """
    if player.hand_1 != "attuned_wayerwood" and player.hand_2 != "attuned_wayerwood":
        return None

    # Outside a cave → lifeless flavour
    if not getattr(player, "in_cave", False):
        return "🪄 *The wayerwood feels lifeless here. It only stirs in the depths of the earth.*"

    # In cave — find nearest cracked_stone
    cracks = await db.fetch_all(
        "SELECT local_x, local_y FROM cave_tiles WHERE cave_id=? AND tile_type='cracked_stone'",
        (player.cave_id,)
    )
    if not cracks:
        return "🪄 *The wayerwood hums quietly. No hidden passages stir within these walls.*"

    cx, cy = player.cave_x, player.cave_y
    nearest = min(cracks, key=lambda r: abs(r["local_x"] - cx) + abs(r["local_y"] - cy))
    dist_now = abs(nearest["local_x"] - cx) + abs(nearest["local_y"] - cy)
    return _wayerwood_signal(user_id, dist_now)


# ── Interact ──────────────────────────────────────────────────────────────────

async def handle_interact(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # Ship interior tile interactions
    if player.in_ship:
        center_tile_type = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)[4][4].terrain
        if center_tile_type == "ship_helm":
            await handle_ship_leave(interaction, guild_id, user_id)
            return
        elif center_tile_type == "ship_chest_personal":
            await handle_ship_chest_open_personal(interaction, guild_id, user_id)
            return
        elif center_tile_type == "ship_chest_cargo":
            await handle_ship_chest_open_cargo(interaction, guild_id, user_id)
            return
        elif center_tile_type == "ship_hull_damage":
            # Repair hull damage: requires hammer equipped + 2 nails + 1 plank in inventory
            hand_items = {player.hand_1, player.hand_2} - {None}
            if "hammer" not in hand_items:
                grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
                content = render_grid(grid, player, "🔨 You need a **hammer** equipped to repair hull damage.")
                view = _ship_game_view(guild_id, user_id, player)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            inv = await get_inventory(db, user_id)
            nail_count = sum(r["quantity"] for r in inv if r["item_id"] == "nail")
            plank_count = sum(r["quantity"] for r in inv if r["item_id"] == "plank")
            if nail_count < 2 or plank_count < 1:
                need = []
                if nail_count < 2:
                    need.append(f"{2 - nail_count} more nail(s)")
                if plank_count < 1:
                    need.append("1 plank")
                grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
                content = render_grid(grid, player, f"🔨 Need {' and '.join(need)} to patch this hole.")
                view = _ship_game_view(guild_id, user_id, player)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            # Consume materials and heal 5 HP
            await remove_from_inventory(db, user_id, "nail", 2)
            await remove_from_inventory(db, user_id, "plank", 1)
            player.ship_hp = min(player.ship_max_hp, player.ship_hp + 5)
            await update_player_stats(db, user_id, ship_hp=player.ship_hp)
            grid = load_ship_viewport(player.ship_room, player.ship_x, player.ship_y, player=player)
            content = render_grid(grid, player,
                f"🔨 Hull patched! Ship HP: {player.ship_hp}/{player.ship_max_hp}. Used 2 nails + 1 plank.")
            view = _ship_game_view(guild_id, user_id, player)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        else:
            return

    if player.in_house:
        _is_ph = (player.house_type == "player_house")
        if _is_ph:
            htile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
        else:
            htile = await load_building_single_tile(player.house_id, player.house_x, player.house_y, db)

        if htile.terrain == "b_door":
            vx, vy = player.house_vx, player.house_vy
            player.in_house = False
            await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
            if _is_ph:
                if player.ph_cave_id is not None:
                    cid = player.ph_cave_id
                    player.cave_id = cid
                    player.cave_x, player.cave_y = vx, vy
                    player.in_cave = True
                    player.ph_cave_id = None
                    await update_player_cave_state(db, user_id, True, cid, vx, vy)
                    grid = await load_cave_viewport(cid, vx, vy, db)
                    content = render_grid(grid, player, "You step outside.")
                    view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
                else:
                    player.world_x, player.world_y = vx, vy
                    await update_player_position(db, user_id, vx, vy)
                    grid = await load_viewport(vx, vy, seed, db)
                    content = render_grid(grid, player, "You step outside.")
                    view = _game_view(guild_id, user_id, player, grid=grid)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
            player.village_x, player.village_y = vx, vy
            await update_player_village_state(
                db, user_id, True, player.village_id,
                vx, vy, player.village_wx, player.village_wy,
            )
            grid = await load_village_viewport(player.village_id, vx, vy, db, user_id=user_id)
            content = render_grid(grid, player, "You step outside.")

        elif htile.terrain == "b_bank_npc" and player.house_type == "bank":
            return await _open_bank(interaction, guild_id, user_id, player, db)

        elif htile.terrain == "b_shop_npc" and player.house_type == "shop":
            return await _open_shop(interaction, guild_id, user_id, player)

        elif htile.terrain in PH_CHEST_TYPES and _is_ph:
            chest_id = await get_or_create_ph_chest(
                db, player.house_id, player.house_x, player.house_y, htile.terrain
            )
            chest_inv = await get_chest_items(db, chest_id)
            player_inv = await get_inventory(db, user_id)
            inv_rows, inv_cols = _inv_capacity(player)
            _ui_state[user_id] = {
                **_ui_state.get(user_id, {}),
                "type": "chest",
                "chest_id": chest_id,
                "chest_type": htile.terrain,
                "selected": 0,
                "chest_view": "chest",
            }
            content = render_chest(chest_inv, player_inv, 0, "chest",
                                   htile.terrain, inv_rows, inv_cols)
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=ChestView(guild_id, user_id, "chest"),
            )
            return

        else:
            # Generic tile interactions (same for village buildings and player houses)
            async def _load_house_grid():
                if _is_ph:
                    return await load_player_house_viewport(
                        player.house_id, player.house_x, player.house_y, db)
                return await load_building_viewport(
                    player.house_id, player.house_x, player.house_y, db)

            if htile.terrain in ("b_bed", "b_table", "b_bookshelf", "b_chair", "b_candle"):
                msgs = {
                    "b_bed": "A cozy bed. You feel rested.",
                    "b_table": "A sturdy wooden table.",
                    "b_bookshelf": "Rows of dusty books.",
                    "b_chair": "A simple chair.",
                    "b_candle": "A flickering candle.",
                }
                grid = await _load_house_grid()
                content = render_grid(grid, player, msgs.get(htile.terrain, "..."))

            elif htile.terrain == "b_altar" and player.house_type == "church":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "You kneel before the altar. You feel at peace.")

            elif htile.terrain == "b_priest":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "\"May the light guide your path, traveller.\"")

            elif htile.terrain == "b_safe":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "A locked vault. Speak with the banker.")

            elif htile.terrain == "b_blacksmith_npc" and player.house_type == "blacksmith":
                stick_rows = await db.fetch_all(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='stick'", (user_id,)
                )
                resin_rows = await db.fetch_all(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='resin'", (user_id,)
                )
                ingot_rows = await db.fetch_all(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
                )
                stick_count = sum(r["quantity"] for r in stick_rows)
                resin_count = sum(r["quantity"] for r in resin_rows)
                ingot_count = sum(r["quantity"] for r in ingot_rows)
                torch_batches = min(stick_count, resin_count)
                cannonball_batches = ingot_count // 2
                grid = await _load_house_grid()
                if cannonball_batches > 0:
                    await remove_from_inventory(db, user_id, "iron_ingot", cannonball_batches * 2)
                    await add_to_inventory(db, user_id, "cannonball", cannonball_batches)
                    content = render_grid(grid, player, f"⚒️ Forged {cannonball_batches} cannonball{'s' if cannonball_batches > 1 else ''} from {cannonball_batches * 2} iron ingots!")
                elif torch_batches > 0:
                    await remove_from_inventory(db, user_id, "stick", torch_batches)
                    await remove_from_inventory(db, user_id, "resin", torch_batches)
                    await add_to_inventory(db, user_id, "torch", torch_batches)
                    content = render_grid(grid, player, f"⚒️ Crafted {torch_batches} torch{'es' if torch_batches > 1 else ''} from sticks & resin.")
                else:
                    content = render_grid(grid, player, "\"1 stick + 1 resin = 1 torch. 2 iron ingots = 1 cannonball. Use 🔥 Forge to smelt ore, ⚒️ Anvil to craft weapons.\"")

            elif htile.terrain == "b_anvil":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "An anvil. Stand adjacent to it and use the ⚒️ Smith button.")

            elif htile.terrain == "b_barkeep" and player.house_type == "tavern":
                # ── Tavern barkeep — open tavern shop (ShopView) ──────────
                return await _open_tavern_shop(interaction, guild_id, user_id, player)

            elif htile.terrain == "b_tavern_npc" and player.house_type == "tavern":
                # ── Tavern quest NPC — each NPC at a unique position offers a different quest
                from dwarf_explorer.game.quests import get_or_refresh_bounty_pool
                grid = await _load_house_grid()
                bounty_pool = await get_or_refresh_bounty_pool(
                    db, seed,
                    village_id=player.village_id,
                    village_wx=player.world_x,
                    village_wy=player.world_y,
                )
                if bounty_pool:
                    # Use the NPC's tile position to deterministically pick a unique quest
                    idx = (player.house_x * 7 + player.house_y * 13) % len(bounty_pool)
                    pool = bounty_pool[idx:idx + 1]
                    await handle_open_quest_pool(
                        interaction, guild_id, user_id,
                        pool=pool,
                        source_label="Tavern Regular",
                        source_type="village_npc",
                    )
                    return
                content = render_grid(grid, player,
                    "\"No work posted today. Check back another time.\"")

            elif htile.terrain == "b_crew_npc":
                # ── Harbour tavern crew recruit — open hiring dialogue ─────────
                await handle_crew_npc_talk(interaction, guild_id, user_id)
                return

            elif htile.terrain == "b_healer" and player.house_type == "hospital":
                # ── Hospital healer — free heal ────────────────────────────────
                grid = await _load_house_grid()
                max_hp = getattr(player, "max_hp", 100)
                missing = max_hp - player.hp
                if missing <= 0:
                    content = render_grid(grid, player,
                        "\"You look in fine health! Nothing for me to do here.\"")
                else:
                    player.hp = max_hp
                    await update_player_stats(db, user_id, hp=max_hp)
                    content = render_grid(grid, player,
                        f"\"Rest easy — you're in good hands here.\"\n"
                        f"❤️ Healed **{missing} HP** for free! ({player.hp}/{max_hp})")

            elif htile.terrain == "b_medicine_shelf":
                grid = await _load_house_grid()
                content = render_grid(grid, player,
                    "Rows of dried herbs and tinctures line the shelves.")

            elif htile.terrain == "b_barrel":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "A barrel of ale. The smell is inviting.")

            elif htile.terrain == "b_bar_counter":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "The bar counter. Step up and speak with the barkeep.")

            elif htile.terrain == "b_lumber_npc":
                grid = await _load_house_grid()
                inv_items = await get_inventory(db, user_id)
                plank_count = sum(it["quantity"] for it in inv_items if it["item_id"] == "plank")
                _ui_state[user_id] = {**_ui_state.get(user_id, {}), "type": "lumber_convert"}
                if plank_count >= 18:
                    content = render_grid(grid, player,
                        f"\"Bring me 18 planks and I'll shape them into a canoe.\"\n"
                        f"You have **{plank_count}** planks.")
                else:
                    content = render_grid(grid, player,
                        f"\"Run logs through the saw, then bring me 18 planks for a canoe.\"\n"
                        f"You have **{plank_count}** planks.")
                view = LumberConvertView(guild_id, user_id, 0, plank_count)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

            # ── Lumbermill adjacent-tile interactions ─────────────────────────
            # Conveyor tiles are non-walkable; player stands on adjacent b_floor.
            elif player.house_type == "lumber_mill":
                grid = await _load_house_grid()
                _adj_lm_tile = None
                _vc_lm = len(grid) // 2
                for _dy_lm2, _dx_lm2 in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    _gr_lm2 = _vc_lm + _dy_lm2
                    _gc_lm2 = _vc_lm + _dx_lm2
                    if 0 <= _gr_lm2 < len(grid) and 0 <= _gc_lm2 < len(grid[_gr_lm2]):
                        _t_lm2 = grid[_gr_lm2][_gc_lm2].terrain
                        if _t_lm2 in ("b_log_input", "b_plank_output"):
                            _adj_lm_tile = _t_lm2
                            break
                if _adj_lm_tile == "b_log_input":
                    return await handle_lumbermill_insert(interaction, guild_id, user_id)
                elif _adj_lm_tile == "b_plank_output":
                    return await handle_lumbermill_pickup(interaction, guild_id, user_id)
                else:
                    content = render_grid(grid, player,
                        "The mill hums with activity. Stand next to 📥 to insert logs, 📤 to collect planks.")

            elif htile.terrain == "b_farmer_npc":
                return await _open_farmer_shop(interaction, guild_id, user_id, player)

            elif htile.terrain == "b_armory_npc" and player.house_type == "armory":
                return await _open_armory_shop(interaction, guild_id, user_id, player)

            elif htile.terrain in ("b_weapons_rack", "b_ammo_shelf") and player.house_type == "armory":
                grid = await _load_house_grid()
                msg = "Rows of blades and shields are mounted on the wall." if htile.terrain == "b_weapons_rack" else "Shelves stocked with bombs and flint."
                content = render_grid(grid, player, msg)

            elif htile.terrain == "b_resident":
                # ── House resident NPC — random gossip ───────────────────────
                grid = await _load_house_grid()
                _gossip = [
                    "\"Have you tried the stew at the tavern? Best in the region.\"",
                    "\"The old ruins to the north give me the creeps...\"",
                    "\"The mill's been running all night. Something's not right.\"",
                    "\"My cat keeps bringing in dead rats. I think it's proud.\"",
                    "\"Trade's been slow lately. Bandits on the roads, they say.\"",
                    "\"The blacksmith's been forging day and night. Wonder what for.\"",
                    "\"I heard someone found a map fragment near the old shrine.\"",
                    "\"Don't wander off after dark. Strange things move in the forest.\"",
                ]
                import hashlib
                _gidx = int(hashlib.md5(f"{player.house_id}{player.house_x}{player.house_y}".encode()).hexdigest(), 16) % len(_gossip)
                content = render_grid(grid, player, _gossip[_gidx])

            elif htile.terrain == "b_pet":
                grid = await _load_house_grid()
                _fish_rows = await db.fetch_all(
                    "SELECT item_id FROM inventory WHERE user_id=? AND item_id IN ('fish','cooked_fish')",
                    (user_id,)
                )
                if _fish_rows:
                    await remove_from_inventory(db, user_id, _fish_rows[0]["item_id"], 1)
                    content = render_grid(grid, player, "🐱 The cat sniffs your fish eagerly, then devours it whole. It purrs loudly.")
                else:
                    content = render_grid(grid, player, "🐱 The cat blinks slowly at you.")

            elif htile.terrain == "b_chest":
                grid = await _load_house_grid()
                content = render_grid(grid, player, "🔒 *This chest is locked.* You shouldn't go through other people's things.")

            else:
                grid = await _load_house_grid()
                content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    elif player.in_village:
        vtile = await load_village_single_tile(player.village_id, player.village_x, player.village_y, db)

        if vtile.terrain in ("vil_house", "vil_church", "vil_bank", "vil_shop",
                              "vil_blacksmith", "vil_tavern", "vil_hospital", "vil_mill",
                              "vil_lumber_mill", "vil_farmhouse", "vil_armory"):
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
                labels = {
                    "house": "house", "church": "church", "bank": "bank",
                    "shop": "shop", "blacksmith": "blacksmith",
                    "tavern": "tavern", "hospital": "hospital", "mill": "mill",
                    "lumber_mill": "lumber mill", "farmhouse": "farmhouse",
                    "armory": "armory",
                }
                grid = await load_building_viewport(house_id, hx, hy, db)
                content = render_grid(grid, player, f"You enter the {labels.get(btype, 'building')}.")
            else:
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
                content = render_grid(grid, player, "Nothing to interact with here.")

        elif vtile.terrain == "vil_puzzle_board":
            await _open_puzzle(interaction, guild_id, user_id)
            return

        elif vtile.terrain == "vil_well":
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
            content = render_grid(grid, player, "⛲ The well gurgles softly.")

        elif vtile.terrain == "vil_villager":
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)

            # ── Check if this is a recruitable NPC in a harbour village ──────
            _harbor_row = await db.fetch_one(
                "SELECT 1 FROM village_tiles WHERE village_id = ? AND tile_type = 'vil_dock' LIMIT 1",
                (player.village_id,),
            )
            _is_harbor_village = _harbor_row is not None

            if _is_harbor_village:
                _recruitable_positions = get_recruitable_npc_positions(
                    player.village_id, player.village_wx, player.village_wy, seed
                )
                _npc_pos = (player.village_x, player.village_y)
                if _npc_pos in _recruitable_positions and is_npc_recruitable_for_player(
                    user_id, player.village_id, player.village_x, player.village_y
                ):
                    # This NPC can be recruited by this player
                    await handle_village_recruit_npc(interaction, guild_id, user_id, player, seed, grid)
                    return

            # ── Regular villager gossip ───────────────────────────────────────
            _vil_gossip = [
                "\"Beautiful day, isn't it?\"",
                "\"Watch yourself on the roads at night.\"",
                "\"The mill grinds the finest flour in the region.\"",
                "\"I heard adventurers have been clearing out the old cave.\"",
                "\"My daughter says she saw something large in the forest last week.\"",
                "\"The church blesses travellers on request.\"",
                "\"Best bread in the land — straight from our miller.\"",
                "\"Trade caravans are rare these days. Dangerous roads.\"",
                "\"Stick to the paths and you'll be fine.\"",
                "\"The well water is the sweetest you'll find anywhere.\"",
            ]
            import hashlib as _hs
            _vidx = int(_hs.md5(f"v{player.village_id}{player.village_x}{player.village_y}".encode()).hexdigest(), 16) % len(_vil_gossip)
            content = render_grid(grid, player, _vil_gossip[_vidx])

        elif vtile.terrain == "vil_guard":
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
            _guard_lines = [
                "\"Move along, stranger. Keep your weapons sheathed in the village.\"",
                "\"We've had trouble with wolves on the north road. Stay sharp.\"",
                "\"The village is under our protection. Cause no trouble.\"",
                "\"Check the notice board near the well for posted work.\"",
                "\"Travellers welcome. Troublemakers are not.\"",
            ]
            import hashlib as _hg
            _gidx2 = int(_hg.md5(f"g{player.village_id}{player.village_x}{player.village_y}".encode()).hexdigest(), 16) % len(_guard_lines)
            content = render_grid(grid, player, _guard_lines[_gidx2])

        elif vtile.terrain == "vil_dock":
            # ── Board the boat from the harbour dock → wilderness ocean ───────
            hwx, hwy = player.village_wx, player.village_wy
            # Find the nearest ocean tile adjacent to the harbor world position
            ox, oy = await _find_ocean_tile_near(hwx, hwy, seed, db)
            player.in_village = False
            player.in_ocean = True
            player.world_x, player.world_y = ox, oy
            player.ocean_harbor_wx = hwx
            player.ocean_harbor_wy = hwy
            await update_player_village_state(db, user_id, False, None, 0, 0, 0, 0)
            await update_player_ocean_state(db, user_id, True, 0, 0, hwx, hwy)
            await update_player_position(db, user_id, ox, oy)
            grid = await load_viewport(ox, oy, seed, db)
            harbor_adj = await _adjacent_harbor(player, seed, db)
            content = render_grid(grid, player,
                "⚓ You cast off from the dock! Sail into the ocean or use ⚓ Dock to return.")
            view = BoatView(guild_id, user_id, dock_available=(harbor_adj is not None))
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif vtile.terrain == "drop_box":
            from dwarf_explorer.database.repositories import pickup_village_drop
            picked = await pickup_village_drop(db, player.village_id, player.village_x, player.village_y, user_id)
            _invalidate_vp(user_id)
            grid = await _cached_grid(user_id, player, seed, db)
            if picked:
                desc = _pickup_desc(picked)
                content = render_grid(grid, player, f"🤲 Picked up: {desc}.")
            else:
                content = render_grid(grid, player, "🤲 The box is empty.")

        elif vtile.terrain in _VIL_SEEDS_TILES:
            # Water seeded farmland
            grid = await _cached_grid(user_id, player, seed, db)
            hand_items_v = {h for h in (player.hand_1, player.hand_2) if h}
            if "watering_can" not in hand_items_v:
                content = render_grid(grid, player, "🌱 Equip your watering can to water these seeds.")
            elif player.watering_can_uses <= 0:
                content = render_grid(grid, player, "🪣 Your watering can is empty! Fill it next to a water source.")
            else:
                crop_info = next(
                    (c for c in FARM_CROPS.values() if c["planted"] == vtile.terrain), None
                )
                if crop_info:
                    await set_village_tile(db, player.village_id, player.village_x, player.village_y, crop_info["mature"])
                    _invalidate_vp(user_id)
                    grid = await _cached_grid(user_id, player, seed, db)
                    content = render_grid(grid, player, f"💧 You water the seeds. A {crop_info['emoji']} crop sprouts!")
                else:
                    content = render_grid(grid, player, "💧 You water the soil.")
                player.watering_can_uses = max(0, player.watering_can_uses - 1)
                await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))

        elif vtile.terrain in _VIL_CROP_TILES:
            # Harvest ripe crop
            grid = await _cached_grid(user_id, player, seed, db)
            crop_info = next(
                (c for c in FARM_CROPS.values() if c["mature"] == vtile.terrain), None
            )
            if crop_info:
                await set_village_tile(db, player.village_id, player.village_x, player.village_y, "vil_farmland")
                qty = _random.randint(1, crop_info["yield_qty"] + 1)
                await add_to_inventory(db, user_id, crop_info["yield"], qty)
                # Wheat and carrot also drop 1-2 seeds back; potatoes are their own seed
                seed_item = crop_info.get("seed_drop")
                seed_qty = 0
                if seed_item:
                    seed_qty = _random.randint(1, crop_info.get("seed_drop_max", 2))
                    await add_to_inventory(db, user_id, seed_item, seed_qty)
                _invalidate_vp(user_id)
                grid = await _cached_grid(user_id, player, seed, db)
                seed_suffix = f" + {seed_qty}× 🌰 seed" if seed_qty else ""
                content = render_grid(grid, player, f"🌾 You harvest the crop! Got {qty}× {crop_info['emoji']} {crop_info['yield']}{seed_suffix}.")
            else:
                content = render_grid(grid, player, "🌾 You harvest the crop.")

        elif vtile.terrain == "vil_grass":
            # Till grass into farmland (requires hoe)
            grid = await _cached_grid(user_id, player, seed, db)
            hand_items_v = {h for h in (player.hand_1, player.hand_2) if h}
            if "hoe" in hand_items_v:
                await set_village_tile(db, player.village_id, player.village_x, player.village_y, "vil_farmland")
                _invalidate_vp(user_id)
                grid = await _cached_grid(user_id, player, seed, db)
                content = render_grid(grid, player, "🟤 You till the soil into farmland.")
            else:
                content = render_grid(grid, player, "Nothing to interact with here.")

        else:
            grid = await _cached_grid(user_id, player, seed, db)
            _ww_msg = await _try_wayerwood_attune(player, user_id, db)
            content = render_grid(grid, player, _ww_msg if _ww_msg else "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    elif getattr(player, "in_shipwreck", False):
        _int_sw_nav = _ui_state.get(user_id, {}).get("nav_target")
        sw_wx = player.shipwreck_wx
        sw_wy = player.shipwreck_wy
        sw_tile = get_shipwreck_tile(sw_wx, sw_wy, player.shipwreck_x, player.shipwreck_y, seed)

        if sw_tile.terrain == "sw_entrance":
            # Exit the shipwreck
            player.in_shipwreck = False
            player.shipwreck_wx = 0
            player.shipwreck_wy = 0
            player.shipwreck_x = 0
            player.shipwreck_y = 0
            player.breath = BREATH_MAX
            await update_player_shipwreck_state(db, user_id, False, 0, 0, 0, 0, BREATH_MAX)
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            content = render_grid(grid, player, "\U0001F300 You surface from the sunken ship, gasping for air!",
                                  nav_target=_int_sw_nav)
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif sw_tile.terrain == "sw_chest":
            cx, cy = player.shipwreck_x, player.shipwreck_y
            already_looted = await is_shipwreck_chest_looted(db, user_id, sw_wx, sw_wy, cx, cy)
            if already_looted:
                grid = load_shipwreck_viewport(sw_wx, sw_wy, player.shipwreck_x, player.shipwreck_y, seed)
                content = render_grid(grid, player, "\U0001F4B0 This chest has already been picked clean.")
            else:
                # Generate loot
                loot_rng = _random.Random(hash((user_id, sw_wx, sw_wy, cx, cy, seed, "sw_chest")))
                loot_msgs: list[str] = []
                # Iron ingots 1-4
                n_iron = loot_rng.randint(1, 4)
                await add_to_inventory(db, user_id, "iron_ingot", n_iron)
                loot_msgs.append(f"{n_iron}x iron ingot")
                # Gold coins 5-20
                gold_found = loot_rng.randint(5, 20)
                player.gold = min(player.gold + gold_found, COIN_PURSE_CAPACITY.get(player.coin_purse, 100))
                await update_player_stats(db, user_id, gold=player.gold)
                loot_msgs.append(f"{gold_found}g")
                # Seaweed 1-3
                n_seaweed = loot_rng.randint(1, 3)
                await add_to_inventory(db, user_id, "seaweed", n_seaweed)
                loot_msgs.append(f"{n_seaweed}x seaweed")
                # Log/rope 1-2
                n_log = loot_rng.randint(1, 2)
                await add_to_inventory(db, user_id, "log", n_log)
                loot_msgs.append(f"{n_log}x log")
                # Rare: map_fragment (20% chance)
                if loot_rng.random() < 0.20:
                    await add_to_inventory(db, user_id, "map_fragment", 1)
                    loot_msgs.append("1x map fragment!")
                await mark_shipwreck_chest_looted(db, user_id, sw_wx, sw_wy, cx, cy)
                grid = load_shipwreck_viewport(sw_wx, sw_wy, player.shipwreck_x, player.shipwreck_y, seed)
                content = render_grid(grid, player,
                    f"\U0001F4B0 You pry open a waterlogged chest! Found: {', '.join(loot_msgs)}")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        else:
            grid = load_shipwreck_viewport(sw_wx, sw_wy, player.shipwreck_x, player.shipwreck_y, seed)
            content = render_grid(grid, player, "Nothing to interact with here.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    elif getattr(player, "in_sky", False):
        sky_tile = await load_sky_single_tile(
            getattr(player, "sky_id", 0), getattr(player, "sky_x", 0), getattr(player, "sky_y", 0), db
        )
        sky_terrain = sky_tile.terrain if sky_tile else "sky_void"

        if sky_terrain == "sky_entrance":
            # Exit the sky biome → return to overworld at the portal tile
            wx = getattr(player, "sky_portal_wx", player.world_x)
            wy = getattr(player, "sky_portal_wy", player.world_y)
            player.in_sky = False
            player.sky_id = None
            player.sky_x = player.sky_y = 0
            player.sky_portal_wx = player.sky_portal_wy = 0
            player.world_x, player.world_y = wx, wy
            await update_player_sky_state(db, user_id, False, None, 0, 0)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player,
                "\U0001F300 You step back through the swirling portal and land on solid mountain ground.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif sky_terrain == "sky_chest":
            sx, sy = getattr(player, "sky_x", 0), getattr(player, "sky_y", 0)
            sid = getattr(player, "sky_id", 0)
            already_looted = await is_sky_chest_looted(db, sid, sx, sy)
            if already_looted:
                grid = await load_sky_viewport(sid, sx, sy, db)
                content = render_grid(grid, player, "\U0001F4B0 This sky chest has already been looted.")
            else:
                loot_rng = _random.Random(hash((user_id, sid, sx, sy, seed, "sky_chest")))
                loot_msgs: list[str] = []
                gold_found = loot_rng.randint(20, 60)
                _apply_gold_cap(player, gold_found)
                await update_player_stats(db, user_id, gold=player.gold)
                loot_msgs.append(f"{gold_found}g")
                if loot_rng.random() < 0.50:
                    await add_to_inventory(db, user_id, "gust_of_aevos", 1)
                    loot_msgs.append("1x gust of aevos \U0001F32C️")
                if loot_rng.random() < 0.30:
                    await add_to_inventory(db, user_id, "hawk_feather", 1)
                    loot_msgs.append("1x hawk feather \U0001FAB6")
                if loot_rng.random() < 0.20:
                    await add_to_inventory(db, user_id, "map_fragment", 1)
                    loot_msgs.append("1x map fragment")
                await mark_sky_chest_looted(db, sid, sx, sy)
                grid = await load_sky_viewport(sid, sx, sy, db)
                content = render_grid(grid, player,
                    f"\U0001F4B0 You open the sky chest! Found: {', '.join(loot_msgs)}")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif sky_terrain == "sky_altar":
            sx, sy = getattr(player, "sky_x", 0), getattr(player, "sky_y", 0)
            sid = getattr(player, "sky_id", 0)
            grid = await load_sky_viewport(sid, sx, sy, db)
            content = render_grid(grid, player,
                "✨ **Ancient Sky Altar** — An altar carved from living cloud-stone, "
                "etched with runes of the wind god Aevos. "
                "The air hums with faint energy. Perhaps a **gust of aevos** offered here holds significance...")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif sky_terrain == "sky_temple":
            sx, sy = getattr(player, "sky_x", 0), getattr(player, "sky_y", 0)
            sid = getattr(player, "sky_id", 0)
            grid = await load_sky_viewport(sid, sx, sy, db)
            lore_list = SKY_LORE.get("sky_temple", ["\U0001F3DB️ **Temple of Aevos** — Towering cloud-marble columns rise into the endless sky."])
            lore_text = lore_list[hash((sid, sx, sy)) % len(lore_list)]
            content = render_grid(grid, player, lore_text)
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif sky_terrain in ("sky_rune_stone", "sky_storm_tower", "sky_wind_shrine"):
            sx, sy = getattr(player, "sky_x", 0), getattr(player, "sky_y", 0)
            sid = getattr(player, "sky_id", 0)
            grid = await load_sky_viewport(sid, sx, sy, db)
            lore_list = SKY_LORE.get(sky_terrain, ["Nothing unusual here."])
            lore_text = lore_list[hash((sid, sx, sy)) % len(lore_list)]
            content = render_grid(grid, player, lore_text)
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        else:
            sid = getattr(player, "sky_id", 0)
            sx, sy = getattr(player, "sky_x", 0), getattr(player, "sky_y", 0)
            grid = await load_sky_viewport(sid, sx, sy, db)
            content = render_grid(grid, player, "Nothing to interact with here.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    elif getattr(player, "in_temple", False):
        temple_row = await db.fetch_one(
            "SELECT temple_type FROM sky_temples WHERE id=?", (player.temple_id,)
        )
        is_main = temple_row and temple_row["temple_type"] == "main"
        temple_tile = await load_temple_single_tile(
            player.temple_id, player.temple_x, player.temple_y, db, is_main=bool(is_main)
        )
        terrain = temple_tile.terrain

        if terrain == "temple_entrance":
            wx, wy = player.temple_wx, player.temple_wy
            player.in_temple = False
            player.temple_id = None
            await update_player_temple_state(db, user_id, False, None, 0, 0)
            player.world_x, player.world_y = wx, wy
            await update_player_position(db, user_id, wx, wy)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You exit the temple.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return

        elif terrain == "gear_machine":
            # Open the gear machine UI
            await _open_gear_machine(interaction, guild_id, user_id)
            return

        elif terrain in ("temple_altar", "temple_rune", "temple_pillar"):
            lore_list = SKY_LORE.get(terrain, ["Nothing unusual here."])
            lore_text = lore_list[hash((player.temple_id, player.temple_x, player.temple_y)) % len(lore_list)]
            grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db, is_main=bool(is_main))
            content = render_grid(grid, player, lore_text)
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return

        elif terrain == "temple_portal_locked":
            lore = SKY_LORE.get("temple_portal_locked", ["🔒 The portal is sealed."])
            solved_count = 0
            outer_temples = await db.fetch_all("SELECT id FROM sky_temples WHERE temple_type='outer'")
            for ot in outer_temples:
                if await is_outer_temple_solved(db, ot["id"]):
                    solved_count += 1
            msg = lore[0] + f"\n\n*{solved_count}/3 outer temple puzzles completed.*"
            grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db, is_main=True)
            content = render_grid(grid, player, msg)
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return

        elif terrain == "temple_portal_open":
            sky_id = await get_main_temple_sky_id(db, player.temple_id, seed)
            from dwarf_explorer.world.sky import SKY_ENTRY_X, SKY_ENTRY_Y
            player.in_sky = True
            player.sky_id = sky_id
            player.sky_x = SKY_ENTRY_X
            player.sky_y = SKY_ENTRY_Y
            player.sky_portal_wx = player.temple_wx
            player.sky_portal_wy = player.temple_wy
            player.in_temple = False
            await update_player_temple_state(db, user_id, False, None, 0, 0)
            await update_player_sky_state(db, user_id, True, sky_id, SKY_ENTRY_X, SKY_ENTRY_Y,
                                          player.temple_wx, player.temple_wy)
            player.temple_id = None
            grid = await load_sky_viewport(sky_id, SKY_ENTRY_X, SKY_ENTRY_Y, db)
            content = render_grid(grid, player,
                "🌀 You step through the portal — the mountain falls away below you as you soar into the **Sky Realm**!")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return

        else:
            grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db, is_main=bool(is_main))
            content = render_grid(grid, player, "Nothing to interact with here.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return

    elif getattr(player, "in_maze", False):
        from dwarf_explorer.world.forest import (
            load_maze_viewport as _lmv_i, load_maze_single_tile as _lmst_i,
            get_maze_exit_forest_pos as _gmefp_i, load_forest_viewport as _lfv_i2,
        )
        maze_tile = await _lmst_i(player.maze_id, player.maze_x, player.maze_y, db)
        grid = await _lmv_i(player.maze_id, player.maze_x, player.maze_y, db)

        # ── Maze exit tile (both entrance and far-end shortcut) ───────────────
        if maze_tile.terrain == "maze_exit":
            fx, fy = await _gmefp_i(db, player.forest_id)
            player.in_maze = False
            player.maze_id = None
            player.maze_x = player.maze_y = 0
            player.forest_x, player.forest_y = fx, fy
            await db.execute(
                "UPDATE players SET in_maze=0, maze_id=NULL, maze_x=0, maze_y=0, "
                "forest_x=?, forest_y=? WHERE user_id=?",
                (fx, fy, user_id)
            )
            grid = await _lfv_i2(player.forest_id, fx, fy, db)
            content = render_grid(grid, player,
                "🌿 You push back through the hedge and emerge in the ancient forest.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        # ── Maze treasure chest — inventory-style ────────────────────────────
        if maze_tile.terrain == "maze_chest":
            chest_id, is_new = await get_or_create_maze_chest(db, player.maze_id)
            if is_new:
                # Populate with loot (deterministic per maze_id so every player sees same items)
                import random as _mrng
                loot_rng = _mrng.Random(hash((player.maze_id, "chest_loot")))
                gold_reward = loot_rng.randint(80, 200)
                item_pool = ["gem", "living_root", "bark_shield", "iron_ingot"]
                items = loot_rng.sample(item_pool, k=loot_rng.randint(2, 3))
                await add_to_chest(db, chest_id, "gold_coin", gold_reward)
                for it in items:
                    qty = loot_rng.randint(1, 3) if it in ("forest_nut", "living_root") else 1
                    await add_to_chest(db, chest_id, it, qty)
            chest_inv = await get_chest_items(db, chest_id)
            player_inv = await get_inventory(db, user_id)
            inv_rows, inv_cols = _inv_capacity(player)
            _ui_state[user_id] = {
                "type": "chest",
                "chest_id": chest_id,
                "chest_type": "maze_chest",
                "selected": 0,
                "chest_view": "chest",
            }
            content = render_chest(chest_inv, player_inv, 0, "chest",
                                   "maze_chest", inv_rows, inv_cols)
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=ChestView(guild_id, user_id, "chest"))
            return

        # ── Maze mimic — looks like a chest; springs to life on open ─────────
        if maze_tile.terrain == "maze_mimic":
            enemy_type = "chest_mimic"
            from dwarf_explorer.config import ENEMY_STATS as _ES, COMBAT_MOVES_DEFAULT as _CMD
            arena_rng = _random.Random(hash((user_id, player.maze_x, player.maze_y, enemy_type)))
            arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
            player.in_combat = True
            player.combat_enemy_type = enemy_type
            player.combat_enemy_hp = _ES[enemy_type][0]
            player.combat_enemy_x = ex
            player.combat_enemy_y = ey
            player.combat_player_x = ARENA_SIZE // 2
            player.combat_player_y = ARENA_SIZE // 2
            player.combat_moves_left = _CMD + (1 if player.accessory == "ring_of_time" else 0)
            # Store mimic location so we can clear the tile after combat
            _ui_state[user_id] = {
                "type": "combat", "arena": arena,
                "mimic_maze_id": player.maze_id,
                "mimic_x": player.maze_x,
                "mimic_y": player.maze_y,
            }
            await save_combat_state(db, user_id, player)
            content = (
                "💀 **It's a MIMIC!** The chest snaps open to reveal rows of teeth — "
                "and lunges at you!\n\n" + render_arena(arena, player)
            )
            view = CombatView(guild_id, user_id,
                              trapped=arena["player_trapped"],
                              moves_left=player.combat_moves_left)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        # Generic maze tile
        content = render_grid(grid, player, "🌳 Dense forest walls surround the path. Keep exploring.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return

    elif getattr(player, "in_forest_quest", False):
        from dwarf_explorer.world.forest_quest import (
            load_fq_viewport as _lfqv_i,
            load_fq_single_tile as _lfqst_i,
            reset_fq_logs as _rfql_i,
        )
        _fq_bst_i = ({"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
                     if getattr(player, "in_fq_boss_combat", False) else None)
        fq_grid_i = await _lfqv_i(player.fq_area_id, player.fq_x, player.fq_y, db,
                                   boss_state=_fq_bst_i)
        fq_tile_i = await _lfqst_i(player.fq_area_id, player.fq_x, player.fq_y, db)

        if fq_tile_i.terrain == "fq_exit":
            player.in_forest_quest = False
            player.in_fq_boss_combat = False
            player.fq_area_id = None
            player.fq_x = player.fq_y = 0
            await db.execute(
                "UPDATE players SET in_forest_quest=0, in_fq_boss_combat=0, "
                "fq_area_id=NULL, fq_x=0, fq_y=0 WHERE user_id=?", (user_id,)
            )
            from dwarf_explorer.world.forest import load_forest_viewport as _lfv_fqi
            forest_grid_fqi = await _lfv_fqi(player.forest_id, player.forest_x, player.forest_y, db)
            content = render_grid(forest_grid_fqi, player,
                "🌲 You push back through the ancient wall into the forest.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=forest_grid_fqi))
            return

        if fq_tile_i.terrain == "fq_reset":
            await _rfql_i(db, player.fq_area_id)
            _invalidate_vp(user_id)
            fq_grid_i = await _lfqv_i(player.fq_area_id, player.fq_x, player.fq_y, db)
            content = render_grid(fq_grid_i, player,
                "🪨 *The ancient stone hums. The logs roll back to their starting positions.*")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
            return

        if fq_tile_i.terrain == "fq_shopkeeper":
            # Forest shopkeeper — sells basic supplies
            _fq_shop_items = [
                {"item_id": "forest_nut",   "name": "Forest Nut",   "price": 8,
                 "desc": "Restores 3 HP. Gathered from the ancient canopy."},
                {"item_id": "rock",         "name": "Rock",          "price": 4,
                 "desc": "Smooth stone — good for a slingshot."},
                {"item_id": "forest_nut",   "name": "Forest Nut ×3", "price": 20,
                 "desc": "Three nuts bundled together. Bulk discount."},
            ]
            _ui_state[user_id] = {
                "type": "fq_shop",
                "items": _fq_shop_items,
                "selected": 0,
            }
            _shop_lines = "\n".join(
                f"**{it['name']}** — {it['price']}🪙  _{it['desc']}_"
                for it in _fq_shop_items
            )
            content = render_grid(fq_grid_i, player,
                "🧙 *A hunched figure peers out from beneath a mossy hood.*\n\n"
                "*'Lost, are ya? Things get worse ahead. Buy something.'*\n\n"
                + _shop_lines +
                "\n\n*Use the shop interface to purchase.*")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
            return

        if fq_tile_i.terrain == "fq_boss_chest":
            # Loot chest after Thornwarden defeat
            import datetime as _dt_fqbc
            _fqbc_day = _dt_fqbc.date.today().toordinal()
            _fqbc_already = await db.fetch_one(
                "SELECT 1 FROM player_forest_chest_loots "
                "WHERE user_id=? AND forest_id=? AND local_x=? AND local_y=? AND loot_day=?",
                (user_id, -(player.fq_area_id or 0),
                 player.fq_x, player.fq_y, _fqbc_day),
            )
            if _fqbc_already:
                content = render_grid(fq_grid_i, player,
                    "📦 The chest is empty — already claimed today.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
                return
            from dwarf_explorer.config import (
                FQ_ENT_CORE_DROP_WARDEN as _wdrp,
                FQ_WARDEN_EYE_CYCLE as _wec_drop,
            )
            from dwarf_explorer.database.repositories import add_to_inventory as _ati
            _warden_gold = _random.randint(60, 120)
            await _ati(db, user_id, "ent_core", _wdrp)
            player.gold = min(player.gold + _warden_gold,
                              getattr(player, "coin_purse_cap", 9999))
            await db.execute(
                "UPDATE players SET gold=? WHERE user_id=?", (player.gold, user_id)
            )
            await db.execute(
                "INSERT OR IGNORE INTO player_forest_chest_loots"
                "(user_id, forest_id, local_x, local_y, loot_day) VALUES(?,?,?,?,?)",
                (user_id, -(player.fq_area_id or 0),
                 player.fq_x, player.fq_y, _fqbc_day),
            )
            await db.commit()
            content = render_grid(fq_grid_i, player,
                f"📦 **Thornwarden's Hoard!**\n"
                f"🟢 {_wdrp}× Ent Core — *for crafting the Forest Heart Amulet*\n"
                f"🪙 {_warden_gold} gold")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
            return

        if fq_tile_i.terrain == "fq_fork_chest":
            # Side-branch reward chest — daily loot
            import datetime as _dt_fork
            _fork_day = _dt_fork.date.today().toordinal()
            _fork_already = await db.fetch_one(
                "SELECT 1 FROM player_forest_chest_loots "
                "WHERE user_id=? AND forest_id=? AND local_x=? AND local_y=? AND loot_day=?",
                (user_id, -(player.fq_area_id or 0),
                 player.fq_x, player.fq_y, _fork_day),
            )
            if _fork_already:
                content = render_grid(fq_grid_i, player,
                    "🎁 The chest is empty — already claimed today.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
                return
            from dwarf_explorer.database.repositories import add_to_inventory as _ati_fork
            _fork_gold = _random.randint(15, 35)
            await _ati_fork(db, user_id, "log", 2)
            await _ati_fork(db, user_id, "stick", 3)
            player.gold = min(player.gold + _fork_gold,
                              getattr(player, "coin_purse_cap", 9999))
            await db.execute("UPDATE players SET gold=? WHERE user_id=?", (player.gold, user_id))
            await db.execute(
                "INSERT OR IGNORE INTO player_forest_chest_loots"
                "(user_id, forest_id, local_x, local_y, loot_day) VALUES(?,?,?,?,?)",
                (user_id, -(player.fq_area_id or 0),
                 player.fq_x, player.fq_y, _fork_day),
            )
            await db.commit()
            content = render_grid(fq_grid_i, player,
                f"🎁 **Fork Cache!**\n"
                f"🪵 2× Log  🪵 3× Stick\n"
                f"🪙 {_fork_gold} gold\n"
                f"*Someone stashed supplies on this dead-end path.*")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
            return

        if fq_tile_i.terrain in ("fq_ancient_tree", "fq_ancient_tree_done"):
            # Ancient heart tree — quest completion
            _anc_alive = await db.fetch_one(
                "SELECT COUNT(*) AS cnt FROM fq_ents "
                "WHERE fq_id=? AND ent_type='ancient' AND alive=1",
                (player.fq_area_id,),
            )
            if _anc_alive and _anc_alive["cnt"] > 0:
                content = render_grid(fq_grid_i, player,
                    "🌳 The ancient tree radiates immense power — "
                    "but the corrupted guardians still block your approach.\n"
                    "*Defeat the ancient ents first.*")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
                return
            _cur_stage = getattr(player, "fq_quest_stage", "none")
            if _cur_stage != "quest_complete":
                player.fq_quest_stage = "quest_complete"
                await db.execute(
                    "UPDATE players SET fq_quest_stage='quest_complete' WHERE user_id=?",
                    (user_id,)
                )
                # Mark tree tile as activated
                await db.execute(
                    "UPDATE forest_quest_tiles SET tile_type='fq_ancient_tree_done' "
                    "WHERE fq_id=? AND local_x=? AND local_y=?",
                    (player.fq_area_id, player.fq_x, player.fq_y),
                )
                await db.commit()
                _invalidate_vp(user_id)
                fq_grid_i = await _lfqv_i(player.fq_area_id, player.fq_x, player.fq_y, db)
                content = render_grid(fq_grid_i, player,
                    "✨ **FOREST DEPTHS — QUEST COMPLETE!**\n\n"
                    "The ancient tree pulses with warm golden light. "
                    "Its roots shudder, reaching toward you...\n\n"
                    "*'You have cleansed the darkness from these depths. "
                    "The forest breathes again.'*\n\n"
                    "🌳 The ancient heart tree awakens. "
                    "Return to the hermit to complete your journey — or claim the chest nearby.")
            else:
                content = render_grid(fq_grid_i, player,
                    "✨ The ancient heart tree pulses with warm golden light.\n"
                    "*The forest breathes easily in this place.*")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
            return

        if fq_tile_i.terrain == "fq_ancient_chest":
            # Final room reward chest — daily loot
            import datetime as _dt_anc
            _anc_day = _dt_anc.date.today().toordinal()
            _anc_already = await db.fetch_one(
                "SELECT 1 FROM player_forest_chest_loots "
                "WHERE user_id=? AND forest_id=? AND local_x=? AND local_y=? AND loot_day=?",
                (user_id, -(player.fq_area_id or 0),
                 player.fq_x, player.fq_y, _anc_day),
            )
            if _anc_already:
                content = render_grid(fq_grid_i, player,
                    "📦 The ancient chest is empty — already claimed today.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
                return
            from dwarf_explorer.database.repositories import add_to_inventory as _ati_anc
            from dwarf_explorer.config import FQ_ENT_CORE_DROP_ANCIENT as _FQECDA
            _anc_gold = _random.randint(80, 150)
            _anc_cores = _FQECDA * 2   # double the ancient ent drop
            await _ati_anc(db, user_id, "ent_core", _anc_cores)
            await _ati_anc(db, user_id, "living_root", 2)
            player.gold = min(player.gold + _anc_gold,
                              getattr(player, "coin_purse_cap", 9999))
            await db.execute("UPDATE players SET gold=? WHERE user_id=?", (player.gold, user_id))
            await db.execute(
                "INSERT OR IGNORE INTO player_forest_chest_loots"
                "(user_id, forest_id, local_x, local_y, loot_day) VALUES(?,?,?,?,?)",
                (user_id, -(player.fq_area_id or 0),
                 player.fq_x, player.fq_y, _anc_day),
            )
            await db.commit()
            content = render_grid(fq_grid_i, player,
                f"📦 **Ancient Hoard!**\n"
                f"🟢 {_anc_cores}× Ent Core  🌿 2× Living Root\n"
                f"🪙 {_anc_gold} gold\n"
                f"*Craft these into the **Forest Heart Amulet** (+15 max HP).*")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
            return

        content = render_grid(fq_grid_i, player, "🌿 Nothing to interact with here in the depths.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=fq_grid_i))
        return

    elif getattr(player, "in_grove", False):
        from dwarf_explorer.world.forest import load_grove_viewport as _lgv_i
        grid = await _lgv_i(player.grove_id, player.grove_x, player.grove_y, db)
        content = render_grid(grid, player, "🌿 Nothing to interact with in the grove here.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return

    elif getattr(player, "in_forest", False) and not getattr(player, "in_hermit_hut", False):
        _int_for_nav = _ui_state.get(user_id, {}).get("nav_target")
        from dwarf_explorer.world.forest import load_forest_viewport as _lfv_i, load_forest_single_tile as _lfst_i
        ftile = await _lfst_i(player.forest_id, player.forest_x, player.forest_y, db)
        grid = await _lfv_i(player.forest_id, player.forest_x, player.forest_y, db)

        if ftile.terrain == "fst_exit":
            wx, wy = player.forest_wx, player.forest_wy
            player.in_forest = False
            player.forest_id = None
            player.forest_x = player.forest_y = 0
            player.world_x, player.world_y = wx, wy
            await db.execute(
                "UPDATE players SET in_forest=0, forest_id=NULL, forest_x=0, forest_y=0, "
                "world_x=?, world_y=? WHERE user_id=?",
                (wx, wy, user_id)
            )
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player,
                "🌲 You push through the undergrowth and emerge back into the open world.",
                nav_target=_int_for_nav)
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        elif ftile.terrain == "fst_nut_tree":
            # Gather forest nuts — 1–3 nuts, small cooldown via DB
            cooldown_row = await db.fetch_one(
                "SELECT last_watered FROM farm_watered_at WHERE world_x=? AND world_y=?",
                (player.forest_x + player.forest_id * 10000,
                 player.forest_y + player.forest_id * 10000)
            )
            import datetime as _dt
            if cooldown_row:
                last = _dt.datetime.fromisoformat(cooldown_row["last_watered"])
                if (_dt.datetime.utcnow() - last).total_seconds() < 120:
                    content = render_grid(grid, player, "🌰 You already picked this tree clean. Come back later.")
                    await interaction.response.edit_message(embed=_embed(content), content=None,
                                                            view=_game_view(guild_id, user_id, player, grid=grid))
                    return
            qty = _random.randint(1, 3)
            await add_to_inventory(db, user_id, "forest_nut", qty)
            await db.execute(
                "INSERT OR REPLACE INTO farm_watered_at(world_x, world_y, last_watered) VALUES(?,?,datetime('now'))",
                (player.forest_x + player.forest_id * 10000,
                 player.forest_y + player.forest_id * 10000)
            )
            content = render_grid(grid, player,
                f"🌰 You gather **{qty} Forest Nut{'s' if qty > 1 else ''}** from the branches.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        elif ftile.terrain == "fst_ancient_tree":
            has_axe = player.hand_1 == "axe" or player.hand_2 == "axe"
            if has_axe:
                # 10-chop fell mechanic — consistent with overworld ancient tree
                _fac_key_x = player.forest_x + player.forest_id * 10000 + 2
                _fac_key_y = player.forest_y + player.forest_id * 10000 + 2
                _fac_row = await db.fetch_one(
                    "SELECT chops FROM tree_chop_progress WHERE world_x=? AND world_y=?",
                    (_fac_key_x, _fac_key_y),
                )
                _fac_chops = (_fac_row["chops"] if _fac_row else 0) + 1
                if _fac_chops >= 10:
                    # Tree felled — replace tile, award loot
                    await db.execute(
                        "DELETE FROM tree_chop_progress WHERE world_x=? AND world_y=?",
                        (_fac_key_x, _fac_key_y),
                    )
                    await db.execute(
                        "UPDATE forest_tiles SET tile_type='fst_floor' "
                        "WHERE forest_id=? AND local_x=? AND local_y=?",
                        (player.forest_id, player.forest_x, player.forest_y),
                    )
                    _invalidate_vp(user_id)
                    await add_to_inventory(db, user_id, "ancient_log",  3)
                    await add_to_inventory(db, user_id, "ancient_seed", 1)
                    from dwarf_explorer.world.forest import load_forest_viewport as _lfv_anc
                    grid = await _lfv_anc(player.forest_id, player.forest_x, player.forest_y, db)
                    content = render_grid(grid, player,
                        "🪓 The **Ancient Tree** crashes down! You gather **3 Ancient Logs** 🪵 "
                        "and recover **1 Ancient Seed** 🌱.")
                else:
                    # Still chopping — update progress
                    if _fac_row:
                        await db.execute(
                            "UPDATE tree_chop_progress SET chops=? WHERE world_x=? AND world_y=?",
                            (_fac_chops, _fac_key_x, _fac_key_y),
                        )
                    else:
                        await db.execute(
                            "INSERT INTO tree_chop_progress(world_x, world_y, chops) VALUES(?,?,?)",
                            (_fac_key_x, _fac_key_y, _fac_chops),
                        )
                    _fac_left = 10 - _fac_chops
                    content = render_grid(grid, player,
                        f"🪓 You swing at the **Ancient Tree** ({_fac_chops}/10). "
                        f"{_fac_left} more blow{'s' if _fac_left != 1 else ''} to fell it.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return

            has_can = player.hand_1 == "watering_can" or player.hand_2 == "watering_can"
            if not has_can:
                content = render_grid(grid, player,
                    "🌲 *'Water me, and I shall give you what the forest guards.'*\n"
                    "Equip a 🪣 **Watering Can** and interact again.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return
            if player.watering_can_uses <= 0:
                content = render_grid(grid, player, "🪣 Your watering can is empty! Fill it next to a water source.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return
            # Check cooldown (once per forest instance)
            key_x = player.forest_x + player.forest_id * 10000 + 1
            key_y = player.forest_y + player.forest_id * 10000 + 1
            cooldown_row = await db.fetch_one(
                "SELECT last_watered FROM farm_watered_at WHERE world_x=? AND world_y=?",
                (key_x, key_y)
            )
            import datetime as _dt2
            if cooldown_row:
                last = _dt2.datetime.fromisoformat(cooldown_row["last_watered"])
                if (_dt2.datetime.utcnow() - last).total_seconds() < 3600:
                    content = render_grid(grid, player,
                        "🌲 The ancient tree soaks in the water slowly. It needs more time to bloom.")
                    await interaction.response.edit_message(embed=_embed(content), content=None,
                                                            view=_game_view(guild_id, user_id, player, grid=grid))
                    return
            qty = _random.randint(1, 2)
            await add_to_inventory(db, user_id, "ancient_seed", qty)
            await db.execute(
                "INSERT OR REPLACE INTO farm_watered_at(world_x, world_y, last_watered) VALUES(?,?,datetime('now'))",
                (key_x, key_y)
            )
            player.watering_can_uses = max(0, player.watering_can_uses - 1)
            await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
            content = render_grid(grid, player,
                f"🌲 You pour water at the roots of the **Ancient Tree**. "
                f"It shudders — and drops **{qty} Ancient Seed{'s' if qty > 1 else ''}** at your feet!\n"
                "🌱 *Plant these in the world to grow something extraordinary.*")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        elif ftile.terrain in ("fst_chest", "fst_map_chest"):
            _is_map_chest = ftile.terrain == "fst_map_chest"
            # If this is the special map chest, award the forest map on first open
            _map_bonus_msg = ""
            if _is_map_chest:
                _fmap_have = await db.fetch_one(
                    "SELECT 1 FROM player_map_collection WHERE user_id=? AND map_type='forest' AND ref_id=?",
                    (user_id, player.forest_id),
                )
                if not _fmap_have:
                    await db.execute(
                        "INSERT OR IGNORE INTO player_map_collection(user_id, map_type, ref_id) VALUES(?,?,?)",
                        (user_id, "forest", player.forest_id),
                    )
                    _map_bonus_msg = "\n🗺️ **Forest Map** discovered — added to your 🧭 navigation!"
            import datetime as _dt_fst
            _today_ord = _dt_fst.date.today().toordinal()
            fx, fy = player.forest_x, player.forest_y
            # 24-hour server-wide reset: loot_day must equal today
            already = await db.fetch_one(
                "SELECT 1 FROM player_forest_chest_loots "
                "WHERE user_id=? AND forest_id=? AND local_x=? AND local_y=? AND loot_day=?",
                (user_id, player.forest_id, fx, fy, _today_ord),
            )
            # Determine if this position is a mimic today (daily hash) — map chest is never a mimic
            _mimic_rng = _random.Random(hash((player.forest_id, fx, fy, _today_ord, "mimic")))
            _is_mimic_today = (not _is_map_chest) and _mimic_rng.random() < 0.33
            # Re-open existing partially-looted chest from state if available
            existing_fst = _ui_state.get(user_id, {})
            if (already and existing_fst.get("type") == "fst_chest"
                    and existing_fst.get("forest_id") == player.forest_id
                    and existing_fst.get("fx") == fx and existing_fst.get("fy") == fy
                    and existing_fst.get("loot_day") == _today_ord):
                items = existing_fst.get("items", [])
                from dwarf_explorer.game.renderer import render_chest as _rc_fst
                content = _rc_fst(items, [], existing_fst.get("selected", 0), "chest", "fst_chest")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=FstChestView(guild_id, user_id))
                return
            if already:
                content = render_grid(grid, player, "📦 The cache is empty — resets at midnight.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return
            # Mimic check
            if _is_mimic_today:
                enemy_type = "chest_mimic"
                from dwarf_explorer.config import ENEMY_STATS as _ES_fm2, COMBAT_MOVES_DEFAULT as _CMD_fm2
                arena_rng2 = _random.Random(hash((user_id, fx, fy, "fst_chest_mimic", _today_ord)))
                arena2, ex2, ey2 = build_arena_from_viewport(grid, enemy_type, arena_rng2)
                player.in_combat = True
                player.combat_enemy_type = enemy_type
                player.combat_enemy_hp = _ES_fm2[enemy_type][0]
                player.combat_enemy_x = ex2
                player.combat_enemy_y = ey2
                player.combat_player_x = ARENA_SIZE // 2
                player.combat_player_y = ARENA_SIZE // 2
                player.combat_moves_left = _CMD_fm2 + (1 if player.accessory == "ring_of_time" else 0)
                _ui_state[user_id] = {
                    "type": "combat", "arena": arena2,
                    "mimic_forest_id": player.forest_id,
                    "mimic_forest_x":  fx,
                    "mimic_forest_y":  fy,
                }
                await save_combat_state(db, user_id, player)
                content = (
                    "💀 **It's a MIMIC!** The chest snaps open — rows of teeth, lunging!\n\n"
                    + render_arena(arena2, player)
                )
                view = CombatView(guild_id, user_id, trapped=arena2["player_trapped"],
                                  moves_left=player.combat_moves_left)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            # Roll loot (seeded by forest + position + day so same player always gets same loot today)
            loot_rng = _random.Random(hash((player.forest_id, fx, fy, _today_ord, "loot")))
            gold_reward = loot_rng.randint(30, 100)
            item_pool = ["forest_nut", "living_root", "bark_shield", "iron_ingot"]
            item = loot_rng.choice(item_pool)
            qty = loot_rng.randint(1, 3) if item in ("forest_nut", "living_root") else 1
            await db.execute(
                "INSERT OR IGNORE INTO player_forest_chest_loots"
                "(user_id, forest_id, local_x, local_y, loot_day) VALUES(?,?,?,?,?)",
                (user_id, player.forest_id, fx, fy, _today_ord),
            )
            items = [
                {"item_id": "gold_coin", "quantity": gold_reward},
                {"item_id": item, "quantity": qty},
            ]
            _ui_state[user_id] = {
                "type": "fst_chest", "items": items, "selected": 0,
                "fx": fx, "fy": fy, "forest_id": player.forest_id,
                "loot_day": _today_ord,
            }
            from dwarf_explorer.game.renderer import render_chest as _rc_fst
            content = _rc_fst(items, [], 0, "chest", "fst_chest")
            if _map_bonus_msg:
                content = _map_bonus_msg.lstrip("\n") + "\n\n" + content
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=FstChestView(guild_id, user_id))
            return

        elif ftile.terrain == "fst_chamber_chest":
            # Hidden chamber chest — better loot, no mimic, daily reset
            import datetime as _dt_ch
            _ch_today_ord = _dt_ch.date.today().toordinal()
            fx_ch, fy_ch = player.forest_x, player.forest_y
            _ch_already = await db.fetch_one(
                "SELECT 1 FROM player_forest_chest_loots "
                "WHERE user_id=? AND forest_id=? AND local_x=? AND local_y=? AND loot_day=?",
                (user_id, player.forest_id, fx_ch, fy_ch, _ch_today_ord),
            )
            # Re-open existing partially-looted chamber chest from state if available
            _ch_existing = _ui_state.get(user_id, {})
            if (_ch_already and _ch_existing.get("type") == "fst_chest"
                    and _ch_existing.get("chest_type") == "fst_chamber_chest"
                    and _ch_existing.get("forest_id") == player.forest_id
                    and _ch_existing.get("fx") == fx_ch and _ch_existing.get("fy") == fy_ch
                    and _ch_existing.get("loot_day") == _ch_today_ord):
                _ch_items = _ch_existing.get("items", [])
                from dwarf_explorer.game.renderer import render_chest as _rc_ch
                content = _rc_ch(_ch_items, [], _ch_existing.get("selected", 0),
                                 "chest", "fst_chamber_chest")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=FstChestView(guild_id, user_id))
                return
            if _ch_already:
                content = render_grid(grid, player, "💎 The chamber chest is empty — resets at midnight.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return
            # Roll chamber loot (better than regular forest chests)
            _ch_loot_rng = _random.Random(hash((player.forest_id, fx_ch, fy_ch, _ch_today_ord, "chamber")))
            _ch_gold = _ch_loot_rng.randint(60, 150)
            _ch_pool = ["living_root", "bark_shield", "iron_ingot",
                        "forest_nut", "cave_crystal", "deep_ore", "pinecone"]
            _ch_item = _ch_loot_rng.choice(_ch_pool)
            _ch_qty = _ch_loot_rng.randint(1, 3) if _ch_item in ("forest_nut", "living_root", "cave_crystal") else 1
            await db.execute(
                "INSERT OR IGNORE INTO player_forest_chest_loots"
                "(user_id, forest_id, local_x, local_y, loot_day) VALUES(?,?,?,?,?)",
                (user_id, player.forest_id, fx_ch, fy_ch, _ch_today_ord),
            )
            _ch_items = [
                {"item_id": "gold_coin", "quantity": _ch_gold},
                {"item_id": _ch_item, "quantity": _ch_qty},
            ]
            _ui_state[user_id] = {
                "type": "fst_chest", "chest_type": "fst_chamber_chest",
                "items": _ch_items, "selected": 0,
                "fx": fx_ch, "fy": fy_ch, "forest_id": player.forest_id,
                "loot_day": _ch_today_ord,
            }
            from dwarf_explorer.game.renderer import render_chest as _rc_ch2
            content = _rc_ch2(_ch_items, [], 0, "chest", "fst_chamber_chest")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=FstChestView(guild_id, user_id))
            return

        elif ftile.terrain == "fst_mimic":
            # Forest mimic — identical look to fst_chest; triggers combat on interact
            enemy_type = "chest_mimic"
            from dwarf_explorer.config import ENEMY_STATS as _ES_fm, COMBAT_MOVES_DEFAULT as _CMD_fm
            arena_rng = _random.Random(hash((user_id, player.forest_x, player.forest_y, "fst_mimic")))
            arena, ex, ey = build_arena_from_viewport(grid, enemy_type, arena_rng)
            player.in_combat = True
            player.combat_enemy_type = enemy_type
            player.combat_enemy_hp = _ES_fm[enemy_type][0]
            player.combat_enemy_x = ex
            player.combat_enemy_y = ey
            player.combat_player_x = ARENA_SIZE // 2
            player.combat_player_y = ARENA_SIZE // 2
            player.combat_moves_left = _CMD_fm + (1 if player.accessory == "ring_of_time" else 0)
            # Store forest mimic location so we can clear the tile after combat
            _ui_state[user_id] = {
                "type": "combat", "arena": arena,
                "mimic_forest_id": player.forest_id,
                "mimic_forest_x":  player.forest_x,
                "mimic_forest_y":  player.forest_y,
            }
            await save_combat_state(db, user_id, player)
            content = (
                "💀 **It's a MIMIC!** The chest snaps open to reveal rows of teeth — "
                "and lunges at you!\n\n" + render_arena(arena, player)
            )
            view = CombatView(guild_id, user_id,
                              trapped=arena["player_trapped"],
                              moves_left=player.combat_moves_left)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif ftile.terrain == "fst_hermit_house":
            # ── Enter hermit hut interior ─────────────────────────────────────
            from dwarf_explorer.world.hermit_hut import (
                ensure_hermit_hut_built as _ehb_act,
                load_hut_viewport as _lhv_act,
                HUT_ENTRY_X as _HEX, HUT_ENTRY_Y as _HEY,
            )
            await _ehb_act(player.forest_id, db)
            player.in_hermit_hut = True
            player.hermit_hut_forest_id = player.forest_id
            player.hermit_hut_floor = 1
            player.hermit_hut_x, player.hermit_hut_y = _HEX, _HEY
            player.in_cave = False
            player.in_bandit_camp = False
            player.in_house = False
            player.in_village = False
            await db.execute(
                "UPDATE players SET in_hermit_hut=1, in_cave=0, in_house=0, in_village=0, "
                "in_bandit_camp=0, bandit_camp_id=NULL, "
                "hermit_hut_forest_id=?, "
                "hermit_hut_floor=1, hermit_hut_x=?, hermit_hut_y=? WHERE user_id=?",
                (player.forest_id, _HEX, _HEY, user_id),
            )
            grid = await _lhv_act(player.forest_id, 1, _HEX, _HEY, db)
            content = render_grid(grid, player,
                "🛖 You push open the creaking door of the hermit's hut...")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        elif ftile.terrain == "fst_tree_city":
            # Enter the tree city interior
            from dwarf_explorer.world.forest import ensure_tree_city_built, load_tree_city_viewport as _ltcv_enter
            _tc_rebuilt_i = await ensure_tree_city_built(player.forest_id, db)
            if _tc_rebuilt_i:
                player.tc_floor = 1
                player.tc_x, player.tc_y = 14, 21
                await db.execute(
                    "UPDATE players SET tc_floor=1, tc_x=14, tc_y=21 WHERE user_id=?", (user_id,)
                )
                from dwarf_explorer.world.forest import load_tree_city_viewport as _ltcv_i
                grid = await _ltcv_i(player.forest_id, 1, 14, 21, db)
                content = render_grid(grid, player, "🌲 The Tree City was rebuilt — you appear at the entrance.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return
            player.in_tree_city = True
            player.tc_forest_id = player.forest_id
            player.tc_floor = 1
            player.tc_x, player.tc_y = 14, 21
            await db.execute(
                "UPDATE players SET in_tree_city=1, tc_forest_id=?, tc_floor=1, tc_x=14, tc_y=21 WHERE user_id=?",
                (player.forest_id, user_id)
            )
            grid = await _ltcv_enter(player.tc_forest_id, 1, 14, 21, db)
            content = render_grid(grid, player,
                "🌲 You push open the great wooden door and step inside the **Tree City**.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        else:
            content = render_grid(grid, player, "🌿 Ancient forest. Nothing to interact with here.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

    elif getattr(player, "in_hermit_hut", False):
        from dwarf_explorer.world.hermit_hut import (
            load_hut_single_tile as _lhst_i,
            load_hut_viewport as _lhv_i,
            ensure_hermit_hut_built as _ehb_i,
            HUT_F2_ENTRY_X as _HF2EX, HUT_F2_ENTRY_Y as _HF2EY,
            HUT_F1_RETURN_X as _HF1RX, HUT_F1_RETURN_Y as _HF1RY,
        )
        await _ehb_i(player.hermit_hut_forest_id, db)
        hhtile = await _lhst_i(player.hermit_hut_forest_id, player.hermit_hut_floor,
                               player.hermit_hut_x, player.hermit_hut_y, db)
        grid = await _lhv_i(player.hermit_hut_forest_id, player.hermit_hut_floor,
                            player.hermit_hut_x, player.hermit_hut_y, db)

        if hhtile.terrain == "b_door":
            # Exit back to forest
            fx, fy = player.forest_x, player.forest_y
            fid = player.hermit_hut_forest_id
            player.in_hermit_hut = False
            player.hermit_hut_forest_id = None
            player.hermit_hut_floor = 1
            player.hermit_hut_x = player.hermit_hut_y = 0
            await db.execute(
                "UPDATE players SET in_hermit_hut=0, hermit_hut_forest_id=NULL, "
                "hermit_hut_floor=1, hermit_hut_x=0, hermit_hut_y=0 WHERE user_id=?", (user_id,)
            )
            from dwarf_explorer.world.forest import load_forest_viewport as _lfv_hhi
            grid = await _lfv_hhi(fid, fx, fy, db)
            content = render_grid(grid, player, "🚪 You step back out into the forest.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        elif hhtile.terrain == "hut_stair_up":
            player.hermit_hut_floor = 2
            player.hermit_hut_x, player.hermit_hut_y = _HF2EX, _HF2EY
            await db.execute(
                "UPDATE players SET hermit_hut_floor=2, hermit_hut_x=?, hermit_hut_y=? WHERE user_id=?",
                (_HF2EX, _HF2EY, user_id),
            )
            grid = await _lhv_i(player.hermit_hut_forest_id, 2, _HF2EX, _HF2EY, db)
            content = render_grid(grid, player,
                "🔼 You climb the creaky stairs into the **upper room**. "
                "Vines and old tomes fill every corner.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        elif hhtile.terrain == "hut_stair_down":
            player.hermit_hut_floor = 1
            player.hermit_hut_x, player.hermit_hut_y = _HF1RX, _HF1RY
            await db.execute(
                "UPDATE players SET hermit_hut_floor=1, hermit_hut_x=?, hermit_hut_y=? WHERE user_id=?",
                (_HF1RX, _HF1RY, user_id),
            )
            grid = await _lhv_i(player.hermit_hut_forest_id, 1, _HF1RX, _HF1RY, db)
            content = render_grid(grid, player, "🔽 You descend back to the ground floor of the hut.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        else:
            content = render_grid(grid, player, "🛖 The old timber walls creak in the wind.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

    elif getattr(player, "in_tree_city", False):
        from dwarf_explorer.world.forest import load_tree_city_single_tile as _ltcs_i, load_tree_city_viewport as _ltcv_i
        tctile = await _ltcs_i(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
        grid = await _ltcv_i(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)

        if tctile.terrain == "tc_door":
            # Exit back to forest
            fx, fy, fid = player.forest_x, player.forest_y, player.tc_forest_id
            player.in_tree_city = False
            player.tc_forest_id = None
            await db.execute(
                "UPDATE players SET in_tree_city=0, tc_forest_id=NULL, tc_floor=1, "
                "tc_x=0, tc_y=0 WHERE user_id=?", (user_id,)
            )
            from dwarf_explorer.world.forest import load_forest_viewport as _lfv_i
            grid = await _lfv_i(fid, fx, fy, db)
            content = render_grid(grid, player, "🚪 You step back into the forest.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        elif tctile.terrain in ("tc_shop", "tc_elder"):
            # Open tree city shop
            await _open_tree_city_shop(interaction, guild_id, user_id, player)
            return

        elif tctile.terrain == "tc_bed":
            # Rest: restore full HP
            if player.hp >= player.max_hp:
                content = render_grid(grid, player, "🛏️ You're already well-rested.")
            else:
                player.hp = player.max_hp
                await update_player_stats(db, user_id, hp=player.hp)
                content = render_grid(grid, player,
                    f"🛏️ You rest in the carved alcove. **HP fully restored!** ({player.hp}/{player.max_hp})")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        else:
            content = render_grid(grid, player, "🌲 The ancient wood is smooth and warm to the touch.")
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

    elif player.in_cave:
        _int_cave_nav = _ui_state.get(user_id, {}).get("nav_target")
        cave_tile = await load_cave_single_tile(player.cave_id, player.cave_x, player.cave_y, db)

        if cave_tile.terrain == "cave_entrance":
            # Check if this is an island lava cave (exits back to the island)
            island_link = await db.fetch_one(
                "SELECT island_id, local_x, local_y FROM island_cave_entrances WHERE cave_id=?",
                (player.cave_id,),
            )
            if island_link:
                # Return to the island at the vol_cave tile
                iid = island_link["island_id"]
                ret_lx = island_link["local_x"]
                ret_ly = island_link["local_y"]
                # Look up the island's ocean position
                irow = await db.fetch_one(
                    "SELECT ocean_x, ocean_y FROM ocean_islands WHERE island_id=?", (iid,)
                )
                if irow:
                    ox, oy = irow["ocean_x"], irow["ocean_y"]
                    player.in_cave = False
                    player.cave_lit = False
                    player.in_island = True
                    player.island_ox = ox
                    player.island_oy = oy
                    player.ocean_x = ret_lx
                    player.ocean_y = ret_ly
                    await update_player_cave_state(db, user_id, False, None, 0, 0)
                    await update_player_island_state(db, user_id, True, ox, oy)
                    await update_player_ocean_state(db, user_id, False, ret_lx, ret_ly)
                    from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
                    _iid2, island_tiles, _ = await get_or_create_island_data(db, ox, oy, seed, "volcano")
                    grid = load_island_viewport(island_tiles, ret_lx, ret_ly)
                    content = render_grid(grid, player, "🌋 You climb back out of the lava cave.")
                    view = _game_view(guild_id, user_id, player, grid=grid)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
                else:
                    grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                    content = render_grid(grid, player, "Nothing to interact with here.")
            else:
                result = await get_cave_entrance_exit(db, player.cave_id, player.cave_x, player.cave_y)
                if result:
                    wx, wy = result
                    player.world_x, player.world_y = wx, wy
                    player.in_cave = False
                    player.cave_id = None
                    player.cave_lit = False
                    await update_player_position(db, user_id, wx, wy)
                    await update_player_cave_state(db, user_id, False, None, 0, 0)
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, "You exit the cave.", nav_target=_int_cave_nav)
                else:
                    grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                    content = render_grid(grid, player, "Nothing to interact with here.")

        elif cave_tile.terrain == "player_house_cave":
            house_id = await get_player_house_at(
                db, player.cave_x, player.cave_y, True, player.cave_id
            )
            if house_id:
                owner_id = await get_player_house_owner(db, house_id)
                is_owner = (owner_id == user_id)
                player.in_house = True
                player.house_id = house_id
                player.house_x = HOUSE_SPAWN_X
                player.house_y = HOUSE_SPAWN_Y
                player.house_vx = player.cave_x
                player.house_vy = player.cave_y
                player.house_type = "player_house"
                player.ph_cave_id = player.cave_id
                await update_player_house_state(
                    db, user_id, True, house_id,
                    HOUSE_SPAWN_X, HOUSE_SPAWN_Y,
                    player.cave_x, player.cave_y, "player_house",
                )
                await update_player_stats(db, user_id, ph_cave_id=player.cave_id)
                _ui_state.setdefault(user_id, {})["is_house_owner"] = is_owner
                grid = await load_player_house_viewport(house_id, HOUSE_SPAWN_X, HOUSE_SPAWN_Y, db)
                content = render_grid(grid, player, "You enter the house.")
            else:
                grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                content = render_grid(grid, player, "Nothing to interact with here.")
            view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif cave_tile.terrain in CAVE_CHEST_TYPES:
            chest_id, is_new = await get_or_create_chest(
                db, player.cave_id, player.cave_x, player.cave_y, cave_tile.terrain
            )
            if is_new:
                # lava_mode=True for lava caves → sea-themed bonus loot
                await populate_chest_loot(chest_id, cave_tile.terrain, db,
                                          lava_mode=getattr(player, "cave_lit", False))
            chest_inv = await get_chest_items(db, chest_id)
            inv_rows, inv_cols = _inv_capacity(player)
            _ui_state[user_id] = {
                "type": "chest", "chest_id": chest_id,
                "chest_type": cave_tile.terrain, "selected": 0, "chest_view": "chest",
            }
            content = render_chest(chest_inv, [], 0, "chest", cave_tile.terrain,
                                   inv_rows, inv_cols)
            view = ChestView(guild_id, user_id, "chest")
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif cave_tile.terrain == "drop_box":
            # Pick up items from a drop box inside the cave
            picked = await pickup_cave_drop(db, player.cave_id, player.cave_x, player.cave_y, user_id)
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            if picked:
                desc = _pickup_desc(picked)
                content = render_grid(grid, player, f"🤲 Picked up: {desc}.")
            else:
                content = render_grid(grid, player, "🤲 The box is empty.")

        elif cave_tile.terrain == "bomb_lit":
            # Pick up a lit bomb (danger!)
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            content = render_grid(grid, player, "💣 The fuse is already lit! **Move away!**")

        else:
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            _ww_msg = await _try_wayerwood_attune(player, user_id, db)
            content = render_grid(grid, player, _ww_msg if _ww_msg else "Nothing to interact with here.")

        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)

    elif player.in_island:
        from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
        ox, oy = player.island_ox, player.island_oy
        px, py = player.ocean_x, player.ocean_y

        _iid, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
        tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
        current_terrain = tile_map.get((px, py), "island_void")

        hand_items: set[str] = set()
        if player.hand_1:
            hand_items.add(player.hand_1)
        if player.hand_2:
            hand_items.add(player.hand_2)

        if current_terrain in ("island_dock", "vol_dock"):
            # Leave island → return to high seas
            player.in_island = False
            player.in_high_seas = True
            player.ocean_x, player.ocean_y = ox, oy
            await update_player_island_state(db, user_id, False)
            await update_player_ocean_state(db, user_id, False, ox, oy, in_high_seas=True)
            has_rod = "fishing_rod" in hand_items
            grid = load_ocean_viewport(ox, oy, seed)
            content = render_grid(grid, player, "⛵ You row back to your boat.")
            view = OceanView(guild_id, user_id, dock_available=(oy == 0),
                             has_fishing_rod=has_rod)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif current_terrain == "vol_cave":
            # Enter a lava cave from the volcano island
            from dwarf_explorer.world.caves import create_island_lava_cave
            island_id_row = await db.fetch_one(
                "SELECT island_id FROM ocean_islands WHERE ocean_x=? AND ocean_y=?",
                (ox, oy),
            )
            if not island_id_row:
                grid = load_island_viewport(tiles, px, py)
                content = render_grid(grid, player, "⛰️ The cave entrance is unstable...")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            iid = island_id_row["island_id"]
            cave_id = await create_island_lava_cave(seed, iid, px, py, db)
            # Find the entrance position in the cave
            ent_row = await db.fetch_one(
                "SELECT local_x, local_y FROM cave_tiles WHERE cave_id=? AND tile_type='cave_entrance'",
                (cave_id,),
            )
            ent_x = ent_row["local_x"] if ent_row else 1
            ent_y = ent_row["local_y"] if ent_row else 1
            player.in_island = False
            player.in_cave = True
            player.cave_id = cave_id
            player.cave_x = ent_x
            player.cave_y = ent_y
            player.cave_lit = True  # lava caves are self-lit
            await update_player_island_state(db, user_id, False)
            await update_player_cave_state(db, user_id, True, cave_id, ent_x, ent_y)
            # Store island return point in players table (using island_ox/oy)
            grid = await load_cave_viewport(cave_id, ent_x, ent_y, db)
            content = render_grid(grid, player, "🌋 You descend into the lava cave!")
            view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif current_terrain == "vol_outpost":
            # Volcano island outpost shop
            player_items = await get_inventory(db, user_id)
            equipped = _equipped_dict(player)
            inv_rows, inv_cols = _inv_capacity(player)
            _ui_state[user_id] = {"type": "shop", "selected": 0, "shop_view": "shop", "qty": 1}
            content_shop = _shop_render(_ui_state[user_id], player_items, equipped, player.gold, inv_rows, inv_cols)
            await interaction.response.edit_message(
                embed=_embed(content_shop), content=None,
                view=ShopView(guild_id, user_id, "shop")
            )
            return

        elif current_terrain == "vol_chest":
            # Volcano island chests: use (ox, oy, px, py) to allow multiple chests per island
            already = await db.fetch_one(
                "SELECT 1 FROM island_loots WHERE ocean_x=? AND ocean_y=?",
                (ox * 10000 + px, oy * 10000 + py),
            ) is not None
            grid = load_island_viewport(tiles, px, py)
            if already:
                content = render_grid(grid, player, "💰 This chest has already been looted.")
            else:
                await db.execute(
                    "INSERT OR IGNORE INTO island_loots (ocean_x, ocean_y) VALUES (?, ?)",
                    (ox * 10000 + px, oy * 10000 + py),
                )
                loot_rng = _random.Random(hash((ox, oy, seed, "vol_chest", px, py)))
                roll = loot_rng.random()
                if roll < 0.30:
                    item_id, qty = "gold_coin", loot_rng.randint(40, 120)
                elif roll < 0.55:
                    item_id, qty = "gem", loot_rng.randint(2, 5)
                elif roll < 0.70:
                    item_id, qty = "map_fragment", 1
                elif roll < 0.85:
                    item_id, qty = "iron_ingot", loot_rng.randint(3, 8)
                else:
                    item_id, qty = "obsidian", loot_rng.randint(1, 3)
                await add_to_inventory(db, user_id, item_id, qty)
                label = item_id.replace("_", " ").title()
                content = render_grid(grid, player,
                                      f"💰 You pry open the chest — **{label} ×{qty}**!")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif current_terrain == "island_chest":
            # Regular island chest — one-time loot per island tile
            already = await db.fetch_one(
                "SELECT 1 FROM island_loots WHERE ocean_x=? AND ocean_y=?",
                (ox * 10000 + px, oy * 10000 + py),
            ) is not None
            grid = load_island_viewport(tiles, px, py)
            if already:
                content = render_grid(grid, player, "💰 This chest has already been looted.")
            else:
                await db.execute(
                    "INSERT OR IGNORE INTO island_loots (ocean_x, ocean_y) VALUES (?, ?)",
                    (ox * 10000 + px, oy * 10000 + py),
                )
                loot_rng = _random.Random(hash((ox, oy, seed, "island_chest", px, py)))
                roll = loot_rng.random()
                if roll < 0.35:
                    item_id, qty = "gold_coin", loot_rng.randint(20, 80)
                elif roll < 0.60:
                    item_id, qty = "gem", loot_rng.randint(1, 3)
                elif roll < 0.75:
                    item_id, qty = "map_fragment", 1
                elif roll < 0.88:
                    item_id, qty = "iron_ingot", loot_rng.randint(2, 5)
                else:
                    item_id, qty = "log", loot_rng.randint(3, 8)
                await add_to_inventory(db, user_id, item_id, qty)
                label = item_id.replace("_", " ").title()
                content = render_grid(grid, player,
                                      f"💰 You pry open the chest — **{label} ×{qty}**!")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif current_terrain in ("island_forest", "island_tree") and "axe" in hand_items:
            # Chop island tree
            await update_island_tile(db, _iid, px, py, "island_sapling")
            await add_to_inventory(db, user_id, "log", 1)
            chop_rng = _random.Random()
            extras = []
            if chop_rng.random() < 0.66:
                await add_to_inventory(db, user_id, "stick", 1)
                extras.append("a stick")
            if chop_rng.random() < 0.33:
                await add_to_inventory(db, user_id, "resin", 1)
                extras.append("some resin")
            extra_str = (", " + ", ".join(extras)) if extras else ""
            # Reload tiles after update
            _iid2, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
            grid = load_island_viewport(tiles, px, py)
            content = render_grid(grid, player,
                f"🪓 You chop down the palm tree! Got a log{extra_str}. A sapling remains.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        else:
            grid = load_island_viewport(tiles, px, py)
            content = render_grid(grid, player, "Nothing to interact with here.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    else:
        # Wilderness interact
        tile = await load_single_tile(player.world_x, player.world_y, seed, db)
        wx, wy = player.world_x, player.world_y

        # Items currently held in hands
        hand_items: set[str] = set()
        if player.hand_1:
            hand_items.add(player.hand_1)
        if player.hand_2:
            hand_items.add(player.hand_2)

        terrain = tile.terrain

        # Treasure map: dig at location if shovel equipped
        if "shovel" in hand_items:
            tmap = await get_treasure_map(db, user_id)
            if tmap:
                tx, ty = tmap
                if wx == tx and wy == ty:
                    await mark_treasure_found(db, user_id)
                    await remove_from_inventory(db, user_id, "treasure_map", 1)
                    # Treasure reward
                    t_rng = _random.Random(hash((user_id, seed, tx, ty, "reward")))
                    gold_found = t_rng.randint(150, 400)
                    _apply_gold_cap(player, gold_found)
                    await update_player_stats(db, user_id, gold=player.gold)
                    reward_item = t_rng.choice(["gem", "iron_ingot", "sword"])
                    await add_to_inventory(db, user_id, reward_item, 1)
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player,
                        f"🪙 Your shovel strikes something! You dig up **{gold_found}g** and a **{reward_item.replace('_', ' ')}**!")
                    view = _game_view(guild_id, user_id, player)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return

        # Map fragment assembly: equip map_fragment + have 5+ in inventory
        if "map_fragment" in hand_items:
            frag_row = await db.fetch_one(
                "SELECT quantity FROM inventory WHERE user_id=? AND item_id='map_fragment'", (user_id,)
            )
            if frag_row and frag_row["quantity"] >= 5:
                existing = await get_treasure_map(db, user_id)
                if existing:
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player,
                        f"🗺️ You already have an active treasure map! The X is near ({existing[0]}, {existing[1]}).")
                    view = _game_view(guild_id, user_id, player)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
                await remove_from_inventory(db, user_id, "map_fragment", 5)
                await _auto_unequip_depleted(db, user_id, "map_fragment", player)
                tx, ty = await _find_treasure_location(user_id, seed, db)
                await set_treasure_map(db, user_id, tx, ty)
                await add_to_inventory(db, user_id, "treasure_map", 1)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player,
                    f"🗺️ You assemble the fragments into a **treasure map**! "
                    f"The X is marked near coordinates **({tx}, {ty})**. "
                    f"Dig there with your shovel to claim the treasure!")
                view = _game_view(guild_id, user_id, player)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        if terrain == "river_landing":
            # Embark canoe: find adjacent water tile
            water_pos: tuple[int, int] | None = None
            for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                ax, ay = wx + ddx, wy + ddy
                if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
                    adj = await load_single_tile(ax, ay, seed, db)
                    if (adj.structure or adj.terrain) in CANOE_PASSABLE:
                        water_pos = (ax, ay)
                        break
            if water_pos:
                player.world_x, player.world_y = water_pos
                player.in_canoe = True
                await update_player_stats(db, user_id,
                                          world_x=water_pos[0], world_y=water_pos[1],
                                          in_canoe=1)
                grid = await load_viewport(water_pos[0], water_pos[1], seed, db)
                content = render_grid(grid, player, "You launch the canoe! Dock at a 🏝️ landing to go ashore.")
                dock_dirs = await _compute_canoe_dock_dirs(player, seed, db)
                view: discord.ui.View = CanoeView(guild_id, user_id, dock_dirs=dock_dirs)
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "There's no water here to launch a canoe.")
                view = _game_view(guild_id, user_id, player)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "player_house":
            house_id = await get_player_house_at(db, wx, wy, False, None)
            if house_id:
                owner_id = await get_player_house_owner(db, house_id)
                is_owner = (owner_id == user_id)
                player.in_house = True
                player.house_id = house_id
                player.house_x = HOUSE_SPAWN_X
                player.house_y = HOUSE_SPAWN_Y
                player.house_vx = wx
                player.house_vy = wy
                player.house_type = "player_house"
                player.ph_cave_id = None
                await update_player_house_state(
                    db, user_id, True, house_id,
                    HOUSE_SPAWN_X, HOUSE_SPAWN_Y,
                    wx, wy, "player_house",
                )
                await update_player_stats(db, user_id, ph_cave_id=None)
                _ui_state.setdefault(user_id, {})["is_house_owner"] = is_owner
                grid = await load_player_house_viewport(house_id, HOUSE_SPAWN_X, HOUSE_SPAWN_Y, db)
                content = render_grid(grid, player, "You enter your house.")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "Nothing to interact with here.")

        elif tile.structure == "shipwreck":
            # ── Enter sunken ship interior ──────────────────────────────────────
            player.in_shipwreck = True
            player.shipwreck_wx = wx
            player.shipwreck_wy = wy
            player.shipwreck_x = SHIPWRECK_ENTRY_X
            player.shipwreck_y = SHIPWRECK_ENTRY_Y
            player.breath = BREATH_MAX
            await update_player_shipwreck_state(
                db, user_id, True, wx, wy,
                SHIPWRECK_ENTRY_X, SHIPWRECK_ENTRY_Y, BREATH_MAX,
            )
            grid = load_shipwreck_viewport(wx, wy, SHIPWRECK_ENTRY_X, SHIPWRECK_ENTRY_Y, seed)
            content = render_grid(grid, player,
                "\U0001F30A You dive into the wreck! Your breath is at 100. "
                "Each step costs 20 breath — use \U0001FAB7 Breath of the Sea to refill. "
                "Interact with \U0001F4B0 chests for loot. Step on the \U0001F573️ hatch (or interact) to exit.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "cave":
            cave_id, ex, ey = await get_or_create_cave(seed, wx, wy, db)
            # Step 4 tiles inward from the entrance edge so the viewport
            # shows cave interior instead of mostly-out-of-bounds walls.
            cave_meta = await db.fetch_one(
                "SELECT width, height FROM caves WHERE cave_id=?", (cave_id,)
            )
            cw = cave_meta["width"] if cave_meta else 40
            ch = cave_meta["height"] if cave_meta else 40
            # Step 4 tiles inward as a candidate, then snap to nearest floor tile
            INWARD = 4
            if ey == 0:            cand_x, cand_y = ex, min(INWARD, ch - 1)
            elif ey == ch - 1:     cand_x, cand_y = ex, max(ch - 1 - INWARD, 0)
            elif ex == 0:          cand_x, cand_y = min(INWARD, cw - 1), ey
            else:                  cand_x, cand_y = max(cw - 1 - INWARD, 0), ey
            # Find nearest walkable floor tile so the player never spawns in a wall
            floor_rows = await db.fetch_all(
                "SELECT local_x, local_y FROM cave_tiles "
                "WHERE cave_id=? AND tile_type IN ('stone_floor', 'cave_entrance')",
                (cave_id,)
            )
            if floor_rows:
                sx, sy = min(
                    ((r["local_x"], r["local_y"]) for r in floor_rows),
                    key=lambda t: abs(t[0] - cand_x) + abs(t[1] - cand_y),
                )
            else:
                sx, sy = cand_x, cand_y
            player.in_cave = True
            player.cave_id = cave_id
            player.cave_x, player.cave_y = sx, sy
            await update_player_cave_state(db, user_id, True, cave_id, sx, sy)
            grid = await load_cave_viewport(cave_id, sx, sy, db)
            content = render_grid(grid, player, "You enter the cave...")

        elif tile.structure == "village":
            vid, vx, vy = await get_or_create_village(seed, wx, wy, db)
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = vx, vy
            player.village_wx, player.village_wy = wx, wy
            await update_player_village_state(db, user_id, True, vid, vx, vy, wx, wy)
            grid = await load_village_viewport(vid, vx, vy, db, user_id=user_id)
            delivery_msg = await _complete_delivery_quests_for_village(db, user_id, wx, wy)
            _entry_msg = f"You enter the village.{' ' + delivery_msg if delivery_msg else ''}"
            content = render_grid(grid, player, _entry_msg)

        elif tile.structure == "sundial":
            # ── Sundial: consume a Star Fragment to open / enter the Temporal Rift ──
            has_frag = await db.fetch_one(
                "SELECT quantity FROM inventory WHERE user_id=? AND item_id='star_fragment' LIMIT 1",
                (user_id,),
            )
            if not has_frag or has_frag["quantity"] < 1:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player,
                    "🕛 **Sundial Ruins** — an ancient portal frozen in time. "
                    "You sense it needs a ⭐ **Star Fragment** to open. "
                    "Fish in the high seas and hope the ocean yields one.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return

            # Consume one star fragment
            await remove_from_inventory(db, user_id, "star_fragment", 1)

            # Create (or retrieve) the rift linked to this sundial
            cave_id, _, _ = await create_rift(wx, wy, db)

            # Enter rift at spawn tile
            player.in_cave = True
            player.cave_id = cave_id
            player.cave_x, player.cave_y = RIFT_SPAWN_X, RIFT_SPAWN_Y
            await update_player_cave_state(db, user_id, True, cave_id, RIFT_SPAWN_X, RIFT_SPAWN_Y)
            grid = await load_cave_viewport(cave_id, RIFT_SPAWN_X, RIFT_SPAWN_Y, db)
            content = render_grid(grid, player,
                "🌀 The sundial pulses — the Star Fragment dissolves into light. "
                "A rift tears open and pulls you through...")
            view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "sky_portal":
            # ── Sky Portal: enter the sky biome (requires climbing_boots) ──────────
            if player.boots != "climbing_boots":
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player,
                    "\U0001F300 **Sky Portal** — A swirling vortex that leads to the Sky Realm. "
                    "The wind howls violently. You'd need **climbing boots** to keep your footing long enough to enter.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return

            sky_id, entry_x, entry_y = await get_or_create_sky_biome(seed, wx, wy, db)
            player.in_sky = True
            player.sky_id = sky_id
            player.sky_x = entry_x
            player.sky_y = entry_y
            player.sky_portal_wx = wx
            player.sky_portal_wy = wy
            await update_player_sky_state(db, user_id, True, sky_id, entry_x, entry_y, wx, wy)
            grid = await load_sky_viewport(sky_id, entry_x, entry_y, db)
            content = render_grid(grid, player,
                "\U0001F300 You step into the swirling portal — the world below vanishes as you soar upward "
                "into the **Sky Realm**! Clouds stretch endlessly around you. "
                "Return to the \U0001F300 entrance to descend.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "sky_temple_outer":
            temple_id = await get_or_create_outer_temple(db, wx, wy)
            player.in_temple = True
            player.temple_id = temple_id
            player.temple_x, player.temple_y = TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y
            player.temple_wx, player.temple_wy = wx, wy
            await update_player_temple_state(db, user_id, True, temple_id,
                                             TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y, wx, wy)
            grid = await load_temple_viewport(temple_id, TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y, db, is_main=False)
            content = render_grid(grid, player,
                "🏛️ You enter the mountain temple. Ancient gear mechanisms line the walls.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "sky_temple_main":
            temple_id, ex, ey = await get_or_create_main_temple(db, wx, wy, seed)
            player.in_temple = True
            player.temple_id = temple_id
            player.temple_x, player.temple_y = ex, ey
            player.temple_wx, player.temple_wy = wx, wy
            await update_player_temple_state(db, user_id, True, temple_id, ex, ey, wx, wy)
            grid = await load_temple_viewport(temple_id, ex, ey, db, is_main=True)
            content = render_grid(grid, player,
                "🏰 You enter the main temple. A massive sealed archway dominates the chamber.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "forest_entrance":
            # ── Forest Entrance: enter the forest interior ────────────────────────
            from dwarf_explorer.world.forest import (
                get_forest_entrance, load_forest_viewport,
                ensure_forests_placed,
            )
            from dwarf_explorer.world.generator import get_biome
            await ensure_forests_placed(seed, db)
            entrance = await get_forest_entrance(db, wx, wy)
            if entrance is None:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player,
                    "🌲 The forest entrance seems sealed. Try again after the world initialises.")
                await interaction.response.edit_message(embed=_embed(content), content=None,
                                                        view=_game_view(guild_id, user_id, player, grid=grid))
                return
            forest_id, local_x, local_y = entrance
            player.in_forest = True
            player.forest_id = forest_id
            player.forest_x = local_x
            player.forest_y = local_y
            player.forest_wx = wx
            player.forest_wy = wy
            await db.execute(
                "UPDATE players SET in_forest=1, forest_id=?, forest_x=?, forest_y=?, "
                "forest_wx=?, forest_wy=? WHERE user_id=?",
                (forest_id, local_x, local_y, wx, wy, user_id)
            )
            grid = await load_forest_viewport(forest_id, local_x, local_y, db)
            content = render_grid(grid, player,
                "🌳 You push through the ancient boughs and enter the **Dense Forest**. "
                "The canopy closes behind you. Find the 🏡 Tree City, the 🌲 Ancient Tree, "
                "or seek the 🌀 maze deep within.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif tile.structure == "bandit_camp":
            # ── Bandit Camp: interact to enter the interior ───────────────────────
            _bc_row_i = await db.fetch_one(
                "SELECT id, world_x, world_y, max_bandits, bandit_kills, cleared_at "
                "FROM bandit_camps WHERE world_x=? AND world_y=?",
                (wx, wy),
            )
            if not _bc_row_i:
                await db.execute(
                    "INSERT OR IGNORE INTO bandit_camps (world_x, world_y) VALUES (?, ?)",
                    (wx, wy),
                )
                # db auto-commits on execute(); no explicit commit needed
                _bc_row_i = await db.fetch_one(
                    "SELECT id, world_x, world_y, max_bandits, bandit_kills, cleared_at "
                    "FROM bandit_camps WHERE world_x=? AND world_y=?",
                    (wx, wy),
                )
            if _bc_row_i:
                from dwarf_explorer.world.bandit_camp import BC_ENTRY_X, BC_ENTRY_Y, load_camp_viewport as _lbcv_i
                player.in_bandit_camp = True
                player.bandit_camp_id = int(_bc_row_i["id"])
                player.bc_x = BC_ENTRY_X
                player.bc_y = BC_ENTRY_Y
                await db.execute(
                    "UPDATE players SET in_bandit_camp=1, bandit_camp_id=?, bc_x=?, bc_y=?, "
                    "world_x=?, world_y=? WHERE user_id=?",
                    (_bc_row_i["id"], BC_ENTRY_X, BC_ENTRY_Y, wx, wy, user_id),
                )
                bc_grid = _lbcv_i(player.bc_x, player.bc_y, wx, wy)
                content = render_grid(bc_grid, player,
                    "⛺ You enter the **Bandit Camp**. Stay sharp — they attack on sight.")
                view = _game_view(guild_id, user_id, player, grid=bc_grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        elif tile.structure == "shrine":
            # ── Shrine: imbue a held gem with a sacrifice to create enchanted gems ──
            gem_slot = None
            if player.hand_1 == "gem":
                gem_slot = "hand_1"
            elif player.hand_2 == "gem":
                gem_slot = "hand_2"

            if gem_slot is None:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player,
                    "⛩️ An ancient shrine. Equip a gem to hand and interact to imbue it with power.")
            else:
                # Build inventory counts for each sacrifice item
                inv_counts: dict[str, int] = {}
                for stype, data in SHRINE_SACRIFICES.items():
                    sac_item = data["item"]
                    if sac_item not in inv_counts:
                        rows_q = await db.fetch_all(
                            "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
                            (user_id, sac_item)
                        )
                        inv_counts[sac_item] = (rows_q[0]["total"] if rows_q and rows_q[0]["total"] else 0)
                view = ShrineView(guild_id, user_id, inv_counts)
                content = (
                    "⛩️ **Ancient Shrine** — The gem in your hand glows faintly.\n"
                    "Choose a sacrifice to imbue the gem with power.\n"
                    "The resulting enchanted gem can be combined with a **gold ring** to craft a special ring."
                )
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        elif tile.structure == "ruins_looted":
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player,
                "🏚️ These ruins have already been picked clean.")

        elif tile.structure == "ruins":
            # ── Ruins: one-time buried loot ────────────────────────────────────
            rng_r = _random.Random(hash((user_id, wx, wy, seed, "ruins")))
            gold_found = rng_r.randint(15, 60)
            _apply_gold_cap(player, gold_found)
            await update_player_stats(db, user_id, gold=player.gold)
            await set_tile_override(db, wx, wy, "ruins_looted")
            extras: list[str] = []
            if rng_r.random() < 0.45:
                await add_to_inventory(db, user_id, "map_fragment", 1)
                extras.append("a map fragment")
            if rng_r.random() < 0.20:
                await add_to_inventory(db, user_id, "gem", 1)
                extras.append("a gem")
            elif rng_r.random() < 0.35:
                await add_to_inventory(db, user_id, "iron_ingot", 1)
                extras.append("an iron ingot")
            extra_str = (" You also find " + ", ".join(extras) + "!") if extras else ""
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player,
                f"🏚️ You sift through the rubble and find **{gold_found}g**.{extra_str}")

        elif tile.structure == "harbor":
            # ── Harbor village: enter the harbour village from the overworld ──
            vid, vx, vy, _dk_x, _dk_y = await get_or_create_harbor_village(seed, wx, wy, db)
            player.in_village = True
            player.village_id = vid
            player.village_x, player.village_y = vx, vy
            player.village_wx, player.village_wy = wx, wy
            await update_player_village_state(db, user_id, True, vid, vx, vy, wx, wy)
            grid = await load_village_viewport(vid, vx, vy, db, user_id=user_id)
            content = render_grid(grid, player,
                "🚢 You enter the harbour village. Head to the ⚓ dock to set sail.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        elif terrain in ("drop_box", "canoe_box"):
            # Pick up items from a drop box on the overworld
            results = await pickup_drop_box(db, wx, wy, user_id)
            grid = await load_viewport(wx, wy, seed, db)
            if results:
                desc = _pickup_desc(results)
                content = render_grid(grid, player, f"🤲 Picked up: {desc}.")
            else:
                content = render_grid(grid, player, "🤲 The box is empty.")

        elif terrain == "path" and "seed" in hand_items:
            # Plant seed → seedling
            await set_tile_override(db, wx, wy, "seedling")
            await remove_from_inventory(db, user_id, "seed", 1)
            await _auto_unequip_depleted(db, user_id, "seed", player)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You plant the seed. A seedling sprouts!")

        elif terrain == "crop_ripe":
            # Harvest ripe crop
            await set_tile_override(db, wx, wy, "farmland")
            seed_yield = _random.randint(2, 3)
            await add_to_inventory(db, user_id, "seed", seed_yield)
            await add_to_inventory(db, user_id, "dry_grass", 1)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"🌻 You harvest the crop! Got {seed_yield} seeds and some dry grass.")

        elif terrain == "farmland" and "seed" in hand_items:
            # Plant seed on farmland
            await set_tile_override(db, wx, wy, "crop_planted")
            await remove_from_inventory(db, user_id, "seed", 1)
            await _auto_unequip_depleted(db, user_id, "seed", player)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "🌱 You plant a seed in the farmland.")

        else:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "Nothing to interact with here.")

        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_use_hand1(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Use the main hand (hand_1) item/tool on the current tile."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    tool = player.hand_1
    if not tool:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "Nothing in your main hand.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await _execute_tool_action(interaction, guild_id, user_id, tool, player, db, seed)


_BOMB_BLAST_OVERWORLD_DESTROYS = {
    "forest", "plains", "grass", "sapling", "short_grass", "seedling",
    "ancient_planted", "ancient_sapling",
}
_BOMB_BLAST_FOREST_DESTROYS = {
    "fst_tree", "fst_log", "fst_bramble",
    "fst_secret_wall",   # secret wall → chamber floor (reveals chamber!)
    "bomb_lit",
}
_BOMB_BLAST_OVERWORLD_EXCLUDES = {
    "mountain", "hills", "snow", "deep_water", "shallow_water", "river",
    "village", "ruins", "player_house", "harbor",
    "ancient_tree_top_left", "ancient_tree_top_right",
    "ancient_tree_bottom_left", "ancient_tree_bottom_right",
    "dense_forest",
}
_BOMB_BLAST_CAVE_DESTROYS = {
    "cave_rock", "iron_ore_deposit", "gold_ore_deposit", "cracked_stone",
}

_BOMB_CROSS_OFFSETS = [(0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)]


async def _bomb_blast_overworld(
    client, message_id: int | None, channel_id: int | None,
    guild_id: int, user_id: int,
    bx: int, by: int, seed: int, db,
) -> None:
    """Fires 4 seconds after a bomb is placed in the overworld."""
    import logging as _bbo
    _bbo_log = _bbo.getLogger(__name__)
    await asyncio.sleep(4)
    db = await get_database(guild_id)
    try:
        blast_msg_parts: list[str] = ["💥 **BOOM!** The bomb explodes!"]
        player = await get_or_create_player(db, user_id, "?")
        # Damage player if still within blast range
        player_in_blast = any(
            player.world_x == bx + dx and player.world_y == by + dy
            for dx, dy in _BOMB_CROSS_OFFSETS
        )
        if player_in_blast:
            dmg = max(1, 15 - player.defense)
            player.hp = max(0, player.hp - dmg)
            await update_player_stats(db, user_id, hp=player.hp)
            blast_msg_parts.append(f"You were caught in the blast! **−{dmg} HP** ({player.hp}/{player.max_hp})")
        # Blast tiles
        for dx, dy in _BOMB_CROSS_OFFSETS:
            tx, ty = bx + dx, by + dy
            if not (0 <= tx < WORLD_SIZE and 0 <= ty < WORLD_SIZE):
                continue
            tile = await load_single_tile(tx, ty, seed, db)
            t = tile.terrain
            if t in _BOMB_BLAST_OVERWORLD_DESTROYS:
                await set_tile_override(db, tx, ty, "dirt")
            elif t == "bomb_lit":
                await set_tile_override(db, tx, ty, "dirt")
        # Remove bomb tile
        await set_tile_override(db, bx, by, "dirt")
        # Refresh player's view and edit message
        if message_id and channel_id:
            ch = client.get_channel(channel_id)
            if ch:
                try:
                    msg = await ch.fetch_message(message_id)
                    grid = await load_viewport(player.world_x, player.world_y, seed, db)
                    view = _game_view(guild_id, user_id, player, grid=grid)
                    content = render_grid(grid, player, " ".join(blast_msg_parts))
                    await msg.edit(embed=_embed(content), content=None, view=view)
                except Exception as _msg_err2:
                    _bbo_log.warning("bomb blast overworld: message edit failed: %s", _msg_err2)
    except Exception as _blast_err2:
        _bbo_log.exception("bomb blast overworld error (guild=%s user=%s): %s",
                           guild_id, user_id, _blast_err2)


async def _bomb_blast_forest(
    client, message_id: int | None, channel_id: int | None,
    guild_id: int, user_id: int,
    forest_id: int, bx: int, by: int, db,
) -> None:
    """Fires 4 seconds after a bomb is placed in a forest interior."""
    import logging as _bbf
    _bbf_log = _bbf.getLogger(__name__)
    await asyncio.sleep(4)
    db = await get_database(guild_id)
    try:
        blast_msg_parts: list[str] = ["💥 **BOOM!** The bomb explodes!"]
        player = await get_or_create_player(db, user_id, "?")
        # Damage player if still within blast range (check forest coords)
        if getattr(player, "in_forest", False) and player.forest_id == forest_id:
            player_in_blast = any(
                player.forest_x == bx + dx and player.forest_y == by + dy
                for dx, dy in _BOMB_CROSS_OFFSETS
            )
            if player_in_blast:
                dmg = max(1, 15 - player.defense)
                player.hp = max(0, player.hp - dmg)
                await update_player_stats(db, user_id, hp=player.hp)
                blast_msg_parts.append(f"You were caught in the blast! **−{dmg} HP** ({player.hp}/{player.max_hp})")
        # Blast forest tiles in cross pattern
        for dx, dy in _BOMB_CROSS_OFFSETS:
            tx, ty = bx + dx, by + dy
            tile_row = await db.fetch_one(
                "SELECT tile_type FROM forest_tiles WHERE forest_id=? AND local_x=? AND local_y=?",
                (forest_id, tx, ty),
            )
            if not tile_row:
                continue
            t = tile_row["tile_type"]
            if t == "fst_secret_wall":
                # Bomb reveals the hidden chamber by converting wall → chamber floor
                await db.execute(
                    "UPDATE forest_tiles SET tile_type='fst_chamber_floor' "
                    "WHERE forest_id=? AND local_x=? AND local_y=?",
                    (forest_id, tx, ty),
                )
                blast_msg_parts.append("✨ A hidden passage is revealed!")
            elif t in _BOMB_BLAST_FOREST_DESTROYS:
                # Restore the original tile under bomb_lit, clear trees/logs
                if t == "bomb_lit":
                    orig_t = _bomb_original_tiles.pop(("forest", forest_id, tx, ty), "fst_floor")
                    await db.execute(
                        "UPDATE forest_tiles SET tile_type=? WHERE forest_id=? AND local_x=? AND local_y=?",
                        (orig_t, forest_id, tx, ty),
                    )
                else:
                    await db.execute(
                        "UPDATE forest_tiles SET tile_type='fst_floor' "
                        "WHERE forest_id=? AND local_x=? AND local_y=?",
                        (forest_id, tx, ty),
                    )
        # Refresh player's view and edit message
        _invalidate_vp(user_id)
        if message_id and channel_id:
            ch = client.get_channel(channel_id)
            if ch:
                try:
                    msg = await ch.fetch_message(message_id)
                    if getattr(player, "in_forest", False) and player.forest_id == forest_id:
                        from dwarf_explorer.world.forest import load_forest_viewport as _lfv_bomb
                        grid = await _lfv_bomb(forest_id, player.forest_x, player.forest_y, db)
                    else:
                        seed = await get_or_create_world(db, guild_id)
                        grid = await load_viewport(player.world_x, player.world_y, seed, db)
                    view = _game_view(guild_id, user_id, player, grid=grid)
                    content = render_grid(grid, player, " ".join(blast_msg_parts))
                    await msg.edit(embed=_embed(content), content=None, view=view)
                except Exception as _msg_err3:
                    _bbf_log.warning("bomb blast forest: message edit failed: %s", _msg_err3)
    except Exception as _blast_err3:
        _bbf_log.exception("bomb blast forest error (guild=%s user=%s): %s",
                           guild_id, user_id, _blast_err3)


async def _bomb_blast_cave(
    client, message_id: int | None, channel_id: int | None,
    guild_id: int, user_id: int,
    cave_id: int, bx: int, by: int, db,
) -> None:
    """Fires 4 seconds after a bomb is placed in a cave."""
    import logging as _bbl
    _bbl_log = _bbl.getLogger(__name__)
    await asyncio.sleep(4)
    # Re-fetch db in case the reference has gone stale over 4 seconds
    db = await get_database(guild_id)
    try:
        blast_msg_parts: list[str] = ["💥 **BOOM!** The bomb explodes!"]
        player = await get_or_create_player(db, user_id, "?")
        # Damage player if still within blast range
        player_in_blast = any(
            player.cave_x == bx + dx and player.cave_y == by + dy
            for dx, dy in _BOMB_CROSS_OFFSETS
        )
        if player_in_blast and player.in_cave:
            dmg = max(1, 15 - player.defense)
            player.hp = max(0, player.hp - dmg)
            await update_player_stats(db, user_id, hp=player.hp)
            blast_msg_parts.append(f"You were caught in the blast! **−{dmg} HP** ({player.hp}/{player.max_hp})")
        # Blast cave tiles in cross pattern
        for dx, dy in _BOMB_CROSS_OFFSETS:
            tx, ty = bx + dx, by + dy
            tile_row = await db.fetch_one(
                "SELECT tile_type FROM cave_tiles WHERE cave_id=? AND local_x=? AND local_y=?",
                (cave_id, tx, ty)
            )
            if not tile_row:
                continue
            t = tile_row["tile_type"]
            # Destroy any dropped items on this blast tile
            await db.execute(
                "DELETE FROM ground_items WHERE cave_id=? AND cave_x=? AND cave_y=? AND is_drop=1",
                (cave_id, tx, ty),
            )
            if t in _BOMB_BLAST_CAVE_DESTROYS or t == "bomb_lit":
                if t == "bomb_lit":
                    # Restore the tile that was under the bomb before placement
                    _MINEABLE = {"cave_rock", "iron_ore_deposit", "gold_ore_deposit", "rift_deposit"}
                    _orig_t = _bomb_original_tiles.pop((cave_id, tx, ty), "stone_floor")
                    restore_t = "stone_floor" if _orig_t in _MINEABLE else _orig_t
                    await db.execute(
                        "UPDATE cave_tiles SET tile_type=? WHERE cave_id=? AND local_x=? AND local_y=?",
                        (restore_t, cave_id, tx, ty)
                    )
                elif t == "cracked_stone":
                    # Convert cracked wall to floor
                    await db.execute(
                        "UPDATE cave_tiles SET tile_type='stone_floor' WHERE cave_id=? AND local_x=? AND local_y=?",
                        (cave_id, tx, ty)
                    )
                    # Flood-fill through hidden_chamber tiles to reveal the entire chamber
                    fq: list[tuple[int, int]] = [(tx, ty)]
                    fv: set[tuple[int, int]] = {(tx, ty)}
                    while fq:
                        qx, qy = fq.pop(0)
                        for nx2, ny2 in ((qx+1, qy), (qx-1, qy), (qx, qy+1), (qx, qy-1)):
                            if (nx2, ny2) in fv:
                                continue
                            fv.add((nx2, ny2))
                            nb = await db.fetch_one(
                                "SELECT tile_type FROM cave_tiles WHERE cave_id=? AND local_x=? AND local_y=?",
                                (cave_id, nx2, ny2)
                            )
                            if nb and nb["tile_type"] == "hidden_chamber":
                                await db.execute(
                                    "UPDATE cave_tiles SET tile_type='stone_floor' "
                                    "WHERE cave_id=? AND local_x=? AND local_y=?",
                                    (cave_id, nx2, ny2)
                                )
                                fq.append((nx2, ny2))
                    # Record this cracked chamber destruction for later regeneration
                    await db.execute(
                        "INSERT INTO cave_crack_breaks (cave_id, broken_at) VALUES (?, datetime('now'))",
                        (cave_id,),
                    )
                    blast_msg_parts.append("🪨 A hidden passage is revealed!")
                else:
                    # Standard mineable rock: remove it (become floor) + drop items as ground tile
                    await db.execute(
                        "UPDATE cave_tiles SET tile_type='stone_floor' WHERE cave_id=? AND local_x=? AND local_y=?",
                        (cave_id, tx, ty)
                    )
                    drop_loot: list[tuple[str, int]] = []
                    if t == "iron_ore_deposit":
                        drop_loot = [("iron_ore", _random.randint(1, 2))]
                    elif t == "gold_ore_deposit":
                        drop_loot = [("gold_ore", 1)]
                    elif t == "cave_rock":
                        drop_loot = [("rock", _random.randint(1, 3))]
                    if drop_loot:
                        await create_cave_drop_box(db, cave_id, tx, ty, drop_loot)
        # Edit message
        if message_id and channel_id and player.in_cave:
            ch = client.get_channel(channel_id)
            if ch:
                try:
                    msg = await ch.fetch_message(message_id)
                    cave_grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                    view = await _cave_game_view(guild_id, user_id, player, db, grid=cave_grid)
                    content = render_grid(cave_grid, player, " ".join(blast_msg_parts))
                    await msg.edit(embed=_embed(content), content=None, view=view)
                except Exception as _msg_err:
                    _bbl_log.warning("bomb blast cave: message edit failed: %s", _msg_err)
    except Exception as _blast_err:
        _bbl_log.exception("bomb blast cave error (guild=%s user=%s cave=%s): %s",
                           guild_id, user_id, cave_id, _blast_err)


async def _execute_tool_action(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    tool: str, player: "Player", db, seed: int
) -> None:
    """Shared tool-on-tile logic for both hand slots."""
    wx, wy = player.world_x, player.world_y
    tile = await load_single_tile(wx, wy, seed, db)
    terrain = tile.terrain
    grid = None
    content = None

    # ── Watering can ──────────────────────────────────────────────────────────
    if tool == "watering_can":
        if player.watering_can_uses <= 0:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "🪣 Your watering can is empty! Fill it next to a water source.")
        elif terrain == "pinecone_planted":
            await set_tile_override(db, wx, wy, "sapling")
            player.watering_can_uses = max(0, player.watering_can_uses - 1)
            await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
            _invalidate_vp(user_id)
            grid = await _cached_grid(user_id, player, seed, db)
            content = render_grid(grid, player, "🌱 You water the pinecone. A tiny sapling sprouts! Water it again to grow a tree.")
        elif terrain == "sapling":
            await set_tile_override(db, wx, wy, "forest")
            player.watering_can_uses = max(0, player.watering_can_uses - 1)
            await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You water the sapling. It grows into a tree!")
        elif terrain == "ancient_planted":
            await set_tile_override(db, wx, wy, "ancient_sapling")
            player.watering_can_uses = max(0, player.watering_can_uses - 1)
            await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "🌱 You water the ancient seed. A sapling sprouts! Water it again to grow the ancient tree.")
        elif terrain == "ancient_sapling":
            # Try to grow a 2×2 ancient tree (sapling = bottom-left corner)
            _at_positions = _ancient_tree_positions(wx, wy)
            _space_ok = True
            for _tx, _ty, _ in _at_positions[:-1]:  # skip bottom-left (already checked — it's the sapling)
                if not (0 <= _tx < WORLD_SIZE and 0 <= _ty < WORLD_SIZE):
                    _space_ok = False
                    break
                _check = await load_single_tile(_tx, _ty, seed, db)
                if not _check.walkable or _check.structure:
                    _space_ok = False
                    break
            if not _space_ok:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "🌱 Not enough space — the ancient tree needs a 2×2 clearing to grow.")
            else:
                for _tx, _ty, _tt in _at_positions:
                    await set_tile_override(db, _tx, _ty, _tt)
                player.watering_can_uses = max(0, player.watering_can_uses - 1)
                await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "🌲 You water the ancient sapling. A vast ancient tree erupts from the earth!")
        elif terrain == "short_grass":
            await set_tile_override(db, wx, wy, "grass")
            player.watering_can_uses = max(0, player.watering_can_uses - 1)
            await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You water the short grass. It grows lush!")
        elif terrain == "seedling":
            await set_tile_override(db, wx, wy, "grass")
            player.watering_can_uses = max(0, player.watering_can_uses - 1)
            await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "You water the seedling. It grows into grass!")
        elif terrain in ("crop_planted", "crop_sprout"):
            last_str = await get_farm_last_watered(db, wx, wy)
            can_water = True
            if last_str:
                try:
                    last_dt = datetime.fromisoformat(last_str)
                    can_water = (datetime.utcnow() - last_dt) >= timedelta(minutes=5)
                except ValueError:
                    can_water = True
            if can_water:
                next_stage = "crop_sprout" if terrain == "crop_planted" else "crop_ripe"
                stage_name = "a sprout" if next_stage == "crop_sprout" else "a ripe crop"
                await set_tile_override(db, wx, wy, next_stage)
                await set_farm_watered(db, wx, wy)
                player.watering_can_uses = max(0, player.watering_can_uses - 1)
                await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, f"💧 You water the crop. It grows into {stage_name}!")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "💧 The crop needs more time before the next watering (5 min cooldown).")
        else:
            # Check adjacent tiles for a water source to fill from
            _FILL_SRC = {"river", "bridge", "shallow_water", "deep_water",
                         "vil_well", "vil_fountain"}
            _can_fill = False
            for _ddx, _ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                _at = await load_single_tile(wx + _ddx, wy + _ddy, seed, db)
                if _at.terrain in _FILL_SRC:
                    _can_fill = True
                    break
            if _can_fill:
                player.watering_can_uses = 9
                await db.execute(
                    "UPDATE players SET watering_can_uses=9 WHERE user_id=?", (user_id,)
                )
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "\U0001FAA3 You fill the watering can. **(9/9)**")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "\U0001FAA3 Nothing to water here.")

    # ── Fishing rod ───────────────────────────────────────────────────────────
    elif tool == "fishing_rod":
        _FISH_SRC = {"river", "bridge", "shallow_water", "deep_water"}
        _fish_water = False
        for _ddx, _ddy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            _at = await load_single_tile(wx + _ddx, wy + _ddy, seed, db)
            if _at.terrain in _FISH_SRC:
                _fish_water = True
                break
        if not _fish_water:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "\U0001F3A3 No water nearby to fish from.")
        else:
            roll = _random.random()
            if roll < 0.50:
                await add_to_inventory(db, user_id, "fish", 1)
                msg = "\U0001F3A3 You cast your line... and reel in a **fish**!"
            elif roll < 0.51:
                await add_to_inventory(db, user_id, "map_fragment", 1)
                msg = "\U0001F3A3 You reel in something unusual — a **map fragment**!"
            else:
                msg = "\U0001F3A3 You cast your line... the fish got away."
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, msg)

    # ── Shovel ────────────────────────────────────────────────────────────────
    elif tool == "shovel":
        _shovel_e = _ITEM_EMOJI.get("shovel", "⛏️")
        if terrain == "sapling":
            await set_tile_override(db, wx, wy, "dirt")
            await add_to_inventory(db, user_id, "sapling", 1)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"{_shovel_e} You dig up the sapling. The ground turns to dirt.")
        elif terrain in ("grass", "plains", "sand", "short_grass", "dirt"):
            await set_tile_override(db, wx, wy, "dirt")
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"{_shovel_e} You dig up the soil and create a dirt patch.")
        else:
            # Treasure dig fallback
            tmap = await get_treasure_map(db, user_id)
            if tmap:
                tx, ty = tmap
                if wx == tx and wy == ty:
                    await mark_treasure_found(db, user_id)
                    await remove_from_inventory(db, user_id, "treasure_map", 1)
                    t_rng = _random.Random(hash((user_id, seed, tx, ty, "reward")))
                    gold_found = t_rng.randint(150, 400)
                    _apply_gold_cap(player, gold_found)
                    await update_player_stats(db, user_id, gold=player.gold)
                    reward_item = t_rng.choice(["gem", "iron_ingot", "sword"])
                    await add_to_inventory(db, user_id, reward_item, 1)
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, f"💰 **X marks the spot!** You dig up **{gold_found}g** and a **{reward_item.replace('_', ' ')}**!")
                else:
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, f"{_shovel_e} You dig here but find nothing of interest.")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, f"{_shovel_e} You dig here but find nothing of interest.")

    # ── Hoe ───────────────────────────────────────────────────────────────────
    elif tool == "hoe":
        if terrain in ("grass", "plains", "dirt"):
            await set_tile_override(db, wx, wy, "farmland")
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "🟤 You till the soil into farmland.")
        else:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "🟤 Nothing to till here.")

    # ── Axe (on-tile forest chop) ─────────────────────────────────────────────
    elif tool == "axe":
        if terrain in ("forest", "dense_forest"):
            # Chop the tree you're standing on — highest priority
            rng = _random.Random()
            await set_tile_override(db, wx, wy, "dirt")
            await add_to_inventory(db, user_id, "log", 1)
            extras = []
            if rng.random() < 0.66:
                await add_to_inventory(db, user_id, "stick", 1)
                extras.append("a stick")
            if rng.random() < 0.33:
                await add_to_inventory(db, user_id, "resin", 1)
                extras.append("some resin")
            pinecone_count = rng.randint(0, 3)
            if pinecone_count > 0:
                await add_to_inventory(db, user_id, "pinecone", pinecone_count)
                cone_str = f"{pinecone_count} pinecone{'s' if pinecone_count > 1 else ''}"
                extras.append(cone_str)
            extra_str = (", " + ", ".join(extras)) if extras else ""
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"🪓 You chop down the tree! Got a log{extra_str}.")
        else:
            # No forest underfoot — check adjacent tiles for an ancient tree (up > down > left > right)
            _adj_dir = None
            for _dn in ("up", "down", "left", "right"):
                _ddx, _ddy = DIRECTIONS[_dn]
                _adj_t = await load_single_tile(wx + _ddx, wy + _ddy, seed, db)
                if _adj_t.terrain in _ANCIENT_TREE_TILES:
                    _adj_dir = _dn
                    break
            if _adj_dir is not None:
                _ddx, _ddy = DIRECTIONS[_adj_dir]
                _ax, _ay = wx + _ddx, wy + _ddy
                _at = await load_single_tile(_ax, _ay, seed, db)
                _root_x, _root_y = _ancient_tree_root(_at.terrain, _ax, _ay)
                _chop_row = await db.fetch_one(
                    "SELECT chops FROM tree_chop_progress WHERE world_x=? AND world_y=?",
                    (_root_x, _root_y)
                )
                _chops = (_chop_row["chops"] if _chop_row else 0) + 1
                if _chops >= 10:
                    await db.execute(
                        "DELETE FROM tree_chop_progress WHERE world_x=? AND world_y=?",
                        (_root_x, _root_y)
                    )
                    for _tx, _ty, _ in _ancient_tree_positions(_root_x, _root_y):
                        await set_tile_override(db, _tx, _ty, "dirt")
                    await add_to_inventory(db, user_id, "log", 6)
                    await add_to_inventory(db, user_id, "ancient_sapling", 1)
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, "\U0001FA93 The ancient tree crashes down! You gather **6 logs** and recover the **ancient sapling**.")
                else:
                    if _chop_row:
                        await db.execute(
                            "UPDATE tree_chop_progress SET chops=? WHERE world_x=? AND world_y=?",
                            (_chops, _root_x, _root_y)
                        )
                    else:
                        await db.execute(
                            "INSERT INTO tree_chop_progress(world_x, world_y, chops) VALUES(?,?,?)",
                            (_root_x, _root_y, _chops)
                        )
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, f"\U0001FA93 You strike the ancient tree. ({_chops}/10 chops)")
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "🪓 Nothing to chop here.")

    # ── Knife ─────────────────────────────────────────────────────────────────
    elif tool == "knife":
        if terrain == "grass":
            await set_tile_override(db, wx, wy, "short_grass")
            await add_to_inventory(db, user_id, "plant_fiber", 1)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "✂️ You cut the grass and collect plant fiber.")
        elif terrain == "plains":
            rng = _random.Random()
            await set_tile_override(db, wx, wy, "short_grass")
            await add_to_inventory(db, user_id, "dry_grass", 1)
            seeds = 2 + (1 if rng.random() < 0.5 else 0)
            await add_to_inventory(db, user_id, "seed", seeds)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"✂️ You cut the plains grass. Got dry grass and {seeds} seeds!")
        else:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "✂️ Nothing to cut here.")

    # ── Fish / cooked fish (eat) ───────────────────────────────────────────────
    elif tool in ("fish", "cooked_fish"):
        food_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, tool)
        )
        if food_row:
            await remove_from_inventory(db, user_id, tool, 1)
            await _auto_unequip_depleted(db, user_id, tool, player)
            heal_amt = FOOD_HP_RESTORE.get(tool, 15)
            heal = min(heal_amt, player.max_hp - player.hp)
            player.hp += heal
            await update_player_stats(db, user_id, hp=player.hp)
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"🍗 You eat the {tool.replace('_', ' ')}. Restored **{heal}** HP. ({player.hp}/{player.max_hp})")
        else:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, "Nothing to eat.")

    # ── Map fragment assembly ─────────────────────────────────────────────────
    elif tool == "map_fragment":
        frag_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id='map_fragment'", (user_id,)
        )
        count = frag_row["quantity"] if frag_row else 0
        if count >= 5:
            existing = await get_treasure_map(db, user_id)
            if existing:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "🗺️ You already have an active treasure map.")
            else:
                await remove_from_inventory(db, user_id, "map_fragment", 5)
                await _auto_unequip_depleted(db, user_id, "map_fragment", player)
                tx, ty = await _find_treasure_location(user_id, seed, db)
                await set_treasure_map(db, user_id, tx, ty)
                await add_to_inventory(db, user_id, "treasure_map", 1)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "🗺️ You assemble 5 map fragments into a **treasure map**! Check your inventory.")
        else:
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, f"🗺️ You need 5 map fragments to make a treasure map. ({count}/5)")

    # ── Bomb placement ────────────────────────────────────────────────────────
    elif tool == "bomb":
        # Check for flint_and_steel in other hand or inventory
        other_hand = player.hand_2 if tool == player.hand_1 else player.hand_1
        has_flint = other_hand == "flint_and_steel"
        if not has_flint:
            flint_row = await db.fetch_one(
                "SELECT quantity FROM inventory WHERE user_id=? AND item_id='flint_and_steel'",
                (user_id,)
            )
            has_flint = bool(flint_row and flint_row["quantity"] > 0)
        if not has_flint:
            if player.in_cave:
                cave_grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
                content = render_grid(cave_grid, player, "💣 You need **flint and steel** to light the bomb!")
                grid = cave_grid
            else:
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "💣 You need **flint and steel** to light the bomb!")
        else:
            # Remove 1 bomb from inventory/hand
            await remove_from_inventory(db, user_id, "bomb", 1)
            await _auto_unequip_depleted(db, user_id, "bomb", player)
            if player.in_cave:
                # Place bomb_lit in cave, remembering the original tile so it can be restored
                cx, cy = player.cave_x, player.cave_y
                _orig_row = await db.fetch_one(
                    "SELECT tile_type FROM cave_tiles WHERE cave_id=? AND local_x=? AND local_y=?",
                    (player.cave_id, cx, cy),
                )
                _bomb_original_tiles[(player.cave_id, cx, cy)] = (
                    _orig_row["tile_type"] if _orig_row else "stone_floor"
                )
                await db.execute(
                    "UPDATE cave_tiles SET tile_type='bomb_lit' WHERE cave_id=? AND local_x=? AND local_y=?",
                    (player.cave_id, cx, cy)
                )
                await db.execute(
                    "INSERT OR IGNORE INTO cave_tiles (cave_id, local_x, local_y, tile_type) VALUES (?,?,?,'bomb_lit')",
                    (player.cave_id, cx, cy)
                )
                cave_grid = await load_cave_viewport(player.cave_id, cx, cy, db)
                content = render_grid(cave_grid, player, "💣 You light the fuse! **Get clear!** (4 seconds...)")
                grid = cave_grid
                # Schedule blast
                asyncio.create_task(_bomb_blast_cave(
                    interaction.client, player.message_id, player.channel_id,
                    guild_id, user_id, player.cave_id, cx, cy, db
                ))
            elif getattr(player, "in_forest", False) and not getattr(player, "in_grove", False) and not getattr(player, "in_hermit_hut", False):
                # Place bomb in forest tiles
                from dwarf_explorer.world.forest import load_forest_viewport as _lfv_bomb_place
                fx, fy = player.forest_x, player.forest_y
                _orig_f = await db.fetch_one(
                    "SELECT tile_type FROM forest_tiles WHERE forest_id=? AND local_x=? AND local_y=?",
                    (player.forest_id, fx, fy),
                )
                _bomb_original_tiles[("forest", player.forest_id, fx, fy)] = (
                    _orig_f["tile_type"] if _orig_f else "fst_floor"
                )
                await db.execute(
                    "UPDATE forest_tiles SET tile_type='bomb_lit' WHERE forest_id=? AND local_x=? AND local_y=?",
                    (player.forest_id, fx, fy),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO forest_tiles(forest_id, local_x, local_y, tile_type) VALUES(?,?,?,'bomb_lit')",
                    (player.forest_id, fx, fy),
                )
                _invalidate_vp(user_id)
                grid = await _lfv_bomb_place(player.forest_id, fx, fy, db)
                content = render_grid(grid, player, "💣 You light the fuse! **Get clear!** (4 seconds...)")
                asyncio.create_task(_bomb_blast_forest(
                    interaction.client, player.message_id, player.channel_id,
                    guild_id, user_id, player.forest_id, fx, fy, db
                ))
            else:
                # Place bomb_lit tile override on player's position (overworld)
                await set_tile_override(db, wx, wy, "bomb_lit")
                _invalidate_vp(user_id)
                grid = await _cached_grid(user_id, player, seed, db)
                content = render_grid(grid, player, "💣 You light the fuse! **Get clear!** (4 seconds...)")
                # Schedule blast
                asyncio.create_task(_bomb_blast_overworld(
                    interaction.client, player.message_id, player.channel_id,
                    guild_id, user_id, wx, wy, seed, db
                ))

    # ── Wayerwood (unattuned) ─────────────────────────────────────────────────
    elif tool == "wayerwood":
        grid = await load_viewport(wx, wy, seed, db)
        content = render_grid(grid, player,
            "🪄 *The wayerwood feels inert. Combine it with a **rock** in your inventory to attune it.*")

    # ── Attuned wayerwood ────────────────────────────────────────────────────
    elif tool == "attuned_wayerwood":
        if player.in_cave:
            # Reset last-reading if we've entered a different cave
            _ww_state = _ui_state.setdefault(user_id, {})
            if _ww_state.get("ww_cave_id") != player.cave_id:
                _ww_state.pop("ww_last_dist", None)
                _ww_state["ww_cave_id"] = player.cave_id
            # Hot/cold signal toward nearest cracked_stone
            grid = await load_cave_viewport(player.cave_id, player.cave_x, player.cave_y, db)
            cracks = await db.fetch_all(
                "SELECT local_x, local_y FROM cave_tiles WHERE cave_id=? AND tile_type='cracked_stone'",
                (player.cave_id,)
            )
            if not cracks:
                ww_msg = "🪄 *The wayerwood hums quietly. No hidden passages stir within these walls.*"
            else:
                cx, cy = player.cave_x, player.cave_y
                nearest = min(cracks, key=lambda r: abs(r["local_x"] - cx) + abs(r["local_y"] - cy))
                dist_now = abs(nearest["local_x"] - cx) + abs(nearest["local_y"] - cy)
                ww_msg = _wayerwood_signal(user_id, dist_now)
        elif getattr(player, "in_forest", False) and not getattr(player, "in_grove", False):
            # Forest: hot/cold signal — toward fst_secret_wall if pinecone in inventory,
            # else toward the grove (wayerwood target).
            _ww_state = _ui_state.setdefault(user_id, {})
            # Reset last-reading when moving to a different forest
            if _ww_state.get("ww_cave_id") != ("forest", player.forest_id):
                _ww_state.pop("ww_last_dist", None)
                _ww_state["ww_cave_id"] = ("forest", player.forest_id)
            from dwarf_explorer.world.forest import (
                get_wayerwood_target as _gwwt_ex,
                load_forest_viewport as _lfv_ex,
            )
            grid = await _lfv_ex(player.forest_id, player.forest_x, player.forest_y, db)
            # Check if player carries a pinecone — if so, sniff for hidden chamber walls
            _pc_row = await db.fetch_one(
                "SELECT 1 FROM inventory WHERE user_id=? AND item_id='pinecone' LIMIT 1",
                (user_id,),
            )
            if _pc_row:
                # Query all fst_secret_wall positions in this forest
                _secret_walls = await db.fetch_all(
                    "SELECT local_x, local_y FROM forest_tiles "
                    "WHERE forest_id=? AND tile_type='fst_secret_wall'",
                    (player.forest_id,),
                )
                if _secret_walls:
                    fx, fy = player.forest_x, player.forest_y
                    _nearest_sw = min(_secret_walls,
                                      key=lambda r: abs(r["local_x"] - fx) + abs(r["local_y"] - fy))
                    dist_now = abs(_nearest_sw["local_x"] - fx) + abs(_nearest_sw["local_y"] - fy)
                    # Forest-flavoured signal variants
                    _ww_state_fst = _ui_state.setdefault(user_id, {})
                    _last = _ww_state_fst.get("ww_last_dist")
                    _ww_state_fst["ww_last_dist"] = dist_now
                    if dist_now == 1:
                        ww_msg = "🪄 *The wayerwood thrums intensely. A hidden passage is right beside you.*"
                    elif _last is None:
                        ww_msg = "🪄 *The wayerwood stirs faintly. Something concealed lies within the trees...*"
                    elif dist_now < _last:
                        ww_msg = "🪄 *The wayerwood pulses warmly — you're getting closer.*"
                    elif dist_now > _last:
                        ww_msg = "🪄 *The wayerwood dims... you've wandered from the hidden path.*"
                    else:
                        ww_msg = "🪄 *The wayerwood quivers — keep moving to get a clearer reading.*"
                else:
                    ww_msg = "🪄 *The pinecone resonates faintly, but no hidden chambers stir in this forest.*"
            else:
                # No pinecone — guide toward the grove as before
                _ww_tgt = await _gwwt_ex(player.forest_id, db)
                if _ww_tgt:
                    dist_now = abs(player.forest_x - _ww_tgt[0]) + abs(player.forest_y - _ww_tgt[1])
                    ww_msg = _wayerwood_signal(user_id, dist_now)
                else:
                    ww_msg = "🪄 *The wayerwood hums quietly.*"
        else:
            grid = await load_viewport(wx, wy, seed, db)
            ww_msg = "🪄 *The wayerwood feels lifeless here. It only stirs underground or in the deep forest.*"
        content = render_grid(grid, player, ww_msg)

    # ── Default ───────────────────────────────────────────────────────────────
    else:
        grid = await load_viewport(wx, wy, seed, db)
        content = render_grid(grid, player, f"Can't use {tool.replace('_', ' ')} here.")

    if grid is None:
        grid = await _cached_grid(user_id, player, seed, db)
    if content is None:
        content = render_grid(grid, player, "Nothing happened.")

    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_use_hand2(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Use the off-hand (hand_2) item/tool on the current tile."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    tool = player.hand_2
    if not tool:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "Nothing in your off-hand.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await _execute_tool_action(interaction, guild_id, user_id, tool, player, db, seed)


async def handle_swap_hands(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Swap hand_1 and hand_2 equipment slots."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    h1 = player.hand_1
    h2 = player.hand_2

    await db.execute(
        "DELETE FROM equipment WHERE user_id=? AND slot IN ('hand_1', 'hand_2')",
        (user_id,)
    )
    if h2:
        await db.execute(
            "INSERT INTO equipment(user_id, slot, item_id) VALUES(?,?,?)",
            (user_id, "hand_1", h2)
        )
    if h1:
        await db.execute(
            "INSERT INTO equipment(user_id, slot, item_id) VALUES(?,?,?)",
            (user_id, "hand_2", h1)
        )
    await db.commit()

    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    h1_name = h2.replace("_", " ") if h2 else "empty"
    grid = await _cached_grid(user_id, player, seed, db)
    content = render_grid(grid, player, f"↔️ Swapped hands. Main hand: **{h1_name}**.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_interact2(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Handle the secondary context-sensitive button (bottom-left D-pad overflow).
    Currently handles: eat food (fish/cooked_fish), use map_fragment."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # Boss aim mode overrides: interact2 = Cancel Aim
    if getattr(player, "fq_boss_aim_mode", False):
        await handle_fq_boss_aim_cancel(interaction, guild_id, user_id)
        return

    hand_items: set[str] = set()
    if player.hand_1:
        hand_items.add(player.hand_1)
    if player.hand_2:
        hand_items.add(player.hand_2)

    wx, wy = player.world_x, player.world_y

    if "cooked_fish" in hand_items or "fish" in hand_items:
        food_id = "cooked_fish" if "cooked_fish" in hand_items else "fish"
        food_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, food_id)
        )
        if food_row:
            await remove_from_inventory(db, user_id, food_id, 1)
            await _auto_unequip_depleted(db, user_id, food_id, player)
            heal_amt = FOOD_HP_RESTORE.get(food_id, 15)
            heal = min(heal_amt, player.max_hp - player.hp)
            player.hp += heal
            await update_player_stats(db, user_id, hp=player.hp)
            grid = await _cached_grid(user_id, player, seed, db)
            content = render_grid(grid, player, f"🍗 You eat the {food_id.replace('_', ' ')}. Restored **{heal}** HP. ({player.hp}/{player.max_hp})")
        else:
            grid = await _cached_grid(user_id, player, seed, db)
            content = render_grid(grid, player, "Nothing to eat here.")
    elif "map_fragment" in hand_items:
        frag_row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id='map_fragment'", (user_id,)
        )
        if frag_row and frag_row["quantity"] >= 5:
            existing = await get_treasure_map(db, user_id)
            if existing:
                grid = await _cached_grid(user_id, player, seed, db)
                content = render_grid(grid, player, "🗺️ You already have an active treasure map.")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            await remove_from_inventory(db, user_id, "map_fragment", 5)
            await _auto_unequip_depleted(db, user_id, "map_fragment", player)
            tx, ty = await _find_treasure_location(user_id, seed, db)
            await set_treasure_map(db, user_id, tx, ty)
            await add_to_inventory(db, user_id, "treasure_map", 1)
            grid = await _cached_grid(user_id, player, seed, db)
            content = render_grid(grid, player, "🗺️ You assemble 5 map fragments into a **treasure map**! Check your inventory.")
        else:
            grid = await _cached_grid(user_id, player, seed, db)
            count = frag_row["quantity"] if frag_row else 0
            content = render_grid(grid, player, f"🗺️ You need 5 map fragments to make a treasure map. ({count}/5)")
    else:
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "Nothing to do here.")

    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Action button handlers (adjacent-tile interactions) ───────────────────────

async def handle_action(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Handle the context-sensitive Action button (adjacent-tile interactions)."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # Boss aim mode overrides: action = Fire slingshot
    if getattr(player, "fq_boss_aim_mode", False):
        await handle_fq_boss_shoot(interaction, guild_id, user_id)
        return

    hand_items: set[str] = set()
    if player.hand_1:
        hand_items.add(player.hand_1)
    if player.hand_2:
        hand_items.add(player.hand_2)

    # ── Hermit Hut: adjacent hermit NPC ─────────────────────────────────────────
    if getattr(player, "in_hermit_hut", False):
        from dwarf_explorer.world.hermit_hut import (
            load_hut_viewport as _lhv_hha,
            ensure_hermit_hut_built as _ehb_hha,
        )
        await _ehb_hha(player.hermit_hut_forest_id, db)
        _hh_grid_act = await _lhv_hha(player.hermit_hut_forest_id, player.hermit_hut_floor,
                                      player.hermit_hut_x, player.hermit_hut_y, db)
        vc = 4
        _hh_hermit_adj = any(
            _hh_grid_act[vc + dy][vc + dx].terrain == "hermit_npc"
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if 0 <= vc + dy < len(_hh_grid_act) and 0 <= vc + dx < len(_hh_grid_act[vc + dy])
        )
        if _hh_hermit_adj:
            await _open_hermit_dialogue(interaction, guild_id, user_id, player, db, _hh_grid_act)
            return
        content = render_grid(_hh_grid_act, player, "🛖 Nothing to interact with here.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=_hh_grid_act))
        return

    # ── Tree city: adjacent shop NPC ─────────────────────────────────────────
    if getattr(player, "in_tree_city", False):
        from dwarf_explorer.world.forest import (
            load_tree_city_viewport as _ltcv_act,
            ensure_tree_city_built as _etcb_act,
        )
        await _etcb_act(player.tc_forest_id, db)
        _tc_grid_act = await _ltcv_act(player.tc_forest_id, player.tc_floor,
                                       player.tc_x, player.tc_y, db)
        vc = 4
        for _dy_a, _dx_a in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            _ar_a, _ac_a = vc + _dy_a, vc + _dx_a
            if 0 <= _ar_a < len(_tc_grid_act) and 0 <= _ac_a < len(_tc_grid_act[_ar_a]):
                _adj_terrain_act = _tc_grid_act[_ar_a][_ac_a].terrain
                if _adj_terrain_act == "tc_shop":
                    await _open_tree_city_shop(interaction, guild_id, user_id, player)
                    return
        _tc_grid_act2 = await _ltcv_act(player.tc_forest_id, player.tc_floor,
                                        player.tc_x, player.tc_y, db)
        content = render_grid(_tc_grid_act2, player, "🌲 Nothing to use here.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player,
                                                                grid=_tc_grid_act2))
        return

    # ── Grove: adjacent statue ───────────────────────────────────────────────
    if getattr(player, "in_grove", False):
        from dwarf_explorer.world.forest import load_grove_viewport as _lgv_act, load_grove_single_tile as _lgst_act
        vc = 4
        grove_grid_act = await _lgv_act(player.grove_id, player.grove_x, player.grove_y, db)
        statue_adjacent = any(
            grove_grid_act[vc + dy][vc + dx].terrain == "grove_statue"
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            if 0 <= vc + dy < len(grove_grid_act) and 0 <= vc + dx < len(grove_grid_act[vc + dy])
        )
        if statue_adjacent:
            await _open_grove_statue(interaction, guild_id, user_id, player, db)
            return
        content = render_grid(grove_grid_act, player, "🌿 Nothing to use here.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grove_grid_act))
        return

    # ── Player house: enter edit mode ────────────────────────────────────────
    if player.in_house and player.house_type == "player_house":
        _is_owner = _ui_state.get(user_id, {}).get("is_house_owner", False)
        if not _is_owner:
            grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "Only the house owner can edit this house.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        state = _ui_state.get(user_id, {})
        _ui_state[user_id] = {**state, "type": "house_edit"}
        grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
        cursor = (player.house_x, player.house_y)
        content = render_grid(grid, player, "✏️ **Edit mode** — Move around and use ➕ Add / ✖ Remove to decorate tiles.",
                              cursor_pos=cursor)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=PlayerHouseEditView(guild_id, user_id),
        )
        return

    # ── Forge: adjacent b_forge ───────────────────────────────────────────────
    if player.in_house:
        grid = await _load_house_grid(player, db)
        vc = 4
        adj_terrains = set()
        for ro, co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = vc + ro, vc + co
            if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
                t = grid[r][c].terrain
                if t:
                    adj_terrains.add(t)

        if "b_stove" in adj_terrains:
            return await _open_hearth(interaction, guild_id, user_id, player, db, grid)

        if "b_forge" in adj_terrains:
            iron_ore = await _count_inv(db, user_id, "iron_ore")
            gold_ore = await _count_inv(db, user_id, "gold_ore")
            msg = "🔥 **Forge** — What would you like to smelt?"
            if iron_ore == 0 and gold_ore == 0:
                msg += "\n*Bring iron ore or gold ore to smelt into ingots.*"
            await interaction.response.edit_message(
                embed=_embed(msg), content=None,
                view=ForgeView(guild_id, user_id, iron_ore=iron_ore, gold_ore=gold_ore),
            )
            return

        if "b_anvil" in adj_terrains:
            _ui_state[user_id] = {"type": "anvil", "anvil_cursor": 0}
            inv_rows_anvil = await get_inventory(db, user_id)
            inv_counts_anvil = {r["item_id"]: r["quantity"] for r in inv_rows_anvil}
            content_anvil = _render_anvil(0, inv_counts_anvil)
            await interaction.response.edit_message(
                embed=_embed(content_anvil),
                content=None,
                view=AnvilView(guild_id, user_id, _ui_state.get(user_id, {}).get("anvil_material", 0)),
            )
            return

        if "b_shop_npc" in adj_terrains:
            return await _open_shop(interaction, guild_id, user_id, player)

        if "b_bank_npc" in adj_terrains:
            return await _open_bank(interaction, guild_id, user_id, player, db)

        if "b_barkeep" in adj_terrains:
            return await _open_tavern_shop(interaction, guild_id, user_id, player)

        if "b_healer" in adj_terrains:
            max_hp = getattr(player, "max_hp", 100)
            missing = max_hp - player.hp
            if missing <= 0:
                content = render_grid(grid, player, "\"You look in fine health! Nothing for me to do here.\"")
            else:
                player.hp = max_hp
                await update_player_stats(db, user_id, hp=max_hp)
                content = render_grid(grid, player,
                    f"\"Rest easy — you're in good hands here.\"\n"
                    f"❤️ Healed **{missing} HP** for free! ({player.hp}/{max_hp})")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        if "b_farmer_npc" in adj_terrains:
            return await _open_farmer_shop(interaction, guild_id, user_id, player)

        if "b_lumber_npc" in adj_terrains:
            plank_rows = await db.fetch_all(
                "SELECT COALESCE(SUM(quantity),0) as total FROM inventory WHERE user_id=? AND item_id='plank'",
                (user_id,),
            )
            plank_count_lm = plank_rows[0]["total"] if plank_rows else 0
            _ui_state[user_id] = {**_ui_state.get(user_id, {}), "type": "lumber_convert"}
            content = render_grid(grid, player,
                f"🪵 **Lumber Mill** — Craft a canoe (18 planks). "
                f"Run logs through 📥 → 📤 to make planks.\n"
                f"You have **{plank_count_lm}** planks.")
            view = LumberConvertView(guild_id, user_id, 0, plank_count_lm)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        if "b_resident" in adj_terrains:
            import hashlib as _rh
            _gossip = [
                "\"It's a fine day, isn't it?\"",
                "\"I heard the well has been running dry lately.\"",
                "\"The blacksmith's been forging day and night. Wonder what for.\"",
                "\"I heard someone found a map fragment near the old shrine.\"",
                "\"Don't wander off after dark. Strange things move in the forest.\"",
            ]
            _gi = int(_rh.md5(f"{player.house_id}{player.house_x}{player.house_y}".encode()).hexdigest(), 16) % len(_gossip)
            content = render_grid(grid, player, _gossip[_gi])
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        if "b_pet" in adj_terrains:
            _fish_rows = await db.fetch_all(
                "SELECT item_id FROM inventory WHERE user_id=? AND item_id IN ('fish','cooked_fish')",
                (user_id,)
            )
            if _fish_rows:
                await remove_from_inventory(db, user_id, _fish_rows[0]["item_id"], 1)
                content = render_grid(grid, player, "🐱 The cat sniffs your hand, then rubs its face against you. It purrs.")
            else:
                content = render_grid(grid, player, "🐱 The cat eyes you curiously from across the room.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        _ww_msg = await _try_wayerwood_attune(player, user_id, db)
        content = render_grid(grid, player, _ww_msg if _ww_msg else "Nothing to interact with nearby.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Temple: adjacent gear_machine interaction ─────────────────────────────
    if getattr(player, "in_temple", False):
        grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db)
        vc = 4
        adj_terrains: set[str] = set()
        for ro, co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = vc + ro, vc + co
            if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
                t = grid[r][c].terrain
                if t:
                    adj_terrains.add(t)
        if "gear_machine" in adj_terrains:
            await _open_gear_machine(interaction, guild_id, user_id)
            return
        content = render_grid(grid, player, "Nothing to interact with nearby.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Village (not in building): adjacent NPC/mill interactions ────────────
    if player.in_village and not player.in_house:
        grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
        vc = 4  # VIEWPORT_CENTER
        adj_terrains: set[str] = set()
        for ro, co in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = vc + ro, vc + co
            if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
                t = grid[r][c]
                if t.terrain: adj_terrains.add(t.terrain)
                if t.structure: adj_terrains.add(t.structure)

        if "b_lumber_npc" in adj_terrains:
            plank_rows = await db.fetch_all(
                "SELECT COALESCE(SUM(quantity),0) as total FROM inventory WHERE user_id=? AND item_id='plank'",
                (user_id,)
            )
            plank_count = plank_rows[0]["total"] if plank_rows else 0
            content = render_grid(grid, player,
                f"🪵 **Lumber Mill** — Craft a canoe (18 planks). "
                f"Run logs through 📥 → 📤 to make planks.\n"
                f"You have **{plank_count}** planks.")
            view = LumberConvertView(guild_id, user_id, 0, plank_count)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        if "b_farmer_npc" in adj_terrains:
            return await _open_farmer_shop(interaction, guild_id, user_id, player)

        # ── Village farmland / crop / hoe interactions ────────────────────────
        vc2 = 4  # VIEWPORT_CENTER
        center_vt = grid[vc2][vc2].terrain if len(grid) > vc2 and len(grid[vc2]) > vc2 else None
        hand_items_v: set[str] = set()
        if player.hand_1: hand_items_v.add(player.hand_1)
        if player.hand_2: hand_items_v.add(player.hand_2)

        if center_vt in _VIL_SEEDS_TILES and "watering_can" in hand_items_v:
            # Water seeds → mature crop
            if player.watering_can_uses <= 0:
                content = render_grid(grid, player, "🪣 Your watering can is empty! Fill it next to a water source.")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            crop_info = next(
                (c for c in FARM_CROPS.values() if c["planted"] == center_vt), None
            )
            if crop_info:
                await set_village_tile(db, player.village_id, player.village_x, player.village_y, crop_info["mature"])
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
                content = render_grid(grid, player, f"💧 You water the seeds. A {crop_info['emoji']} crop sprouts!")
            else:
                content = render_grid(grid, player, "💧 You water the soil.")
            player.watering_can_uses = max(0, player.watering_can_uses - 1)
            await db.execute("UPDATE players SET watering_can_uses=? WHERE user_id=?", (player.watering_can_uses, user_id))
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        if center_vt in _VIL_CROP_TILES:
            # Harvest ripe crop
            crop_info = next(
                (c for c in FARM_CROPS.values() if c["mature"] == center_vt), None
            )
            if crop_info:
                await set_village_tile(db, player.village_id, player.village_x, player.village_y, "vil_farmland")
                qty = _random.randint(1, crop_info["yield_qty"] + 1)
                await add_to_inventory(db, user_id, crop_info["yield"], qty)
                seed_item = crop_info.get("seed_drop")
                seed_qty = 0
                if seed_item:
                    seed_qty = _random.randint(1, crop_info.get("seed_drop_max", 2))
                    await add_to_inventory(db, user_id, seed_item, seed_qty)
                grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
                seed_suffix = f" + {seed_qty}× 🌰 seed" if seed_qty else ""
                content = render_grid(grid, player, f"🌾 You harvest the crop! Got {qty}× {crop_info['emoji']} {crop_info['yield']}{seed_suffix}.")
            else:
                content = render_grid(grid, player, "You harvest the crop.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        if center_vt == "vil_grass" and "hoe" in hand_items_v:
            # Till grass → farmland
            await set_village_tile(db, player.village_id, player.village_x, player.village_y, "vil_farmland")
            grid = await load_village_viewport(player.village_id, player.village_x, player.village_y, db, user_id=user_id)
            content = render_grid(grid, player, "🟤 You till the soil into farmland.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        _vil_gossip_act = [
            "\"Beautiful day, isn't it?\"",
            "\"Watch yourself on the roads at night.\"",
            "\"I heard adventurers have been clearing out the old cave.\"",
            "\"My daughter saw something large in the forest last week.\"",
            "\"The church blesses travellers on request.\"",
            "\"Trade caravans are rare these days. Dangerous roads.\"",
            "\"Stick to the paths and you'll be fine.\"",
            "\"The well water is the sweetest you'll find anywhere.\"",
        ]
        _guard_lines_act = [
            "\"Move along. Keep your weapons sheathed.\"",
            "\"We've had trouble with wolves on the north road.\"",
            "\"The village is under our protection.\"",
            "\"Travellers welcome. Troublemakers are not.\"",
        ]
        _resident_lines_act = [
            "\"Oh! You startled me. Can I help you?\"",
            "\"I don't get many visitors.\"",
            "\"The fire's warm tonight, at least.\"",
        ]

        import hashlib as _hact
        if "vil_villager" in adj_terrains:
            _h = int(_hact.md5(f"va{player.village_id}{player.village_x}{player.village_y}".encode()).hexdigest(), 16)
            content = render_grid(grid, player, _vil_gossip_act[_h % len(_vil_gossip_act)])
        elif "vil_guard" in adj_terrains:
            _h = int(_hact.md5(f"ga{player.village_id}{player.village_x}{player.village_y}".encode()).hexdigest(), 16)
            content = render_grid(grid, player, _guard_lines_act[_h % len(_guard_lines_act)])
        elif "b_resident" in adj_terrains:
            _h = int(_hact.md5(f"ra{player.village_id}{player.village_x}{player.village_y}".encode()).hexdigest(), 16)
            content = render_grid(grid, player, _resident_lines_act[_h % len(_resident_lines_act)])
        else:
            content = render_grid(grid, player, "Nothing to interact with nearby.")

        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Island: fishing adjacent to ocean ────────────────────────────────────
    if player.in_island:
        from dwarf_explorer.world.islands import get_or_create_island_data, load_island_viewport
        ox, oy = player.island_ox, player.island_oy
        px, py = player.ocean_x, player.ocean_y
        _iid, tiles, _ = await get_or_create_island_data(db, ox, oy, seed)
        grid = load_island_viewport(tiles, px, py)
        if "fishing_rod" in hand_items:
            tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
            near_water = any(
                tile_map.get((px + ddx, py + ddy), "island_void") == "island_void"
                for ddx, ddy in ((0, -1), (0, 1), (-1, 0), (1, 0))
            )
            if near_water:
                roll = _random.random()
                if roll < 0.50:
                    await add_to_inventory(db, user_id, "fish", 1)
                    msg = "🎣 You cast your line off the island shore... and reel in a **fish**!"
                elif roll < 0.51:
                    await add_to_inventory(db, user_id, "map_fragment", 1)
                    msg = "🎣 You reel in something unusual — a **map fragment**!"
                else:
                    msg = "🎣 You cast your line... the fish got away."
                content = render_grid(grid, player, msg)
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
        content = render_grid(grid, player, "Nothing to interact with nearby.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Build a player house (requires house_kit equipped) ───────────────────
    wx, wy = player.world_x, player.world_y
    if not player.in_cave and not player.in_village:
        # Only proceed if house_kit is in hand
        if "house_kit" in hand_items:
            tile = await load_single_tile(wx, wy, seed, db)
            _build_ok = (
                not tile.structure
                and tile.walkable
                and tile.terrain not in {"void", "deep_water", "shallow_water", "river",
                                         "river_landing", "mountain", "snow", "player_house_cave"}
            )
            if _build_ok:
                # Check no house already here
                existing = await get_player_house_at(db, wx, wy, is_cave=False, loc_cave_id=None)
                if existing is not None:
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, "🏠 A house already exists here.")
                    view = _game_view(guild_id, user_id, player, grid=grid)
                    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                    return
                # Consume house_kit: unequip from whichever hand, remove from inventory
                if player.hand_1 == "house_kit":
                    await unequip_item(db, user_id, "hand_1")
                elif player.hand_2 == "house_kit":
                    await unequip_item(db, user_id, "hand_2")
                await remove_from_inventory(db, user_id, "house_kit", 1)
                # Place overworld structure tile
                await set_tile_override(db, wx, wy, "player_house")
                # Create house record
                await create_player_house(db, user_id, wx, wy, is_cave=False, loc_cave_id=None)
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(grid, player, "🏠 **House built!** Step inside to decorate it.")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        # ── Ancient tree chop (adjacent axe, 10 chops shared across all 4 tiles) ─
        if "axe" in hand_items:
            # Find any adjacent ancient tree tile
            _at_hit_type = None
            _at_hit_x = _at_hit_y = 0
            for _ddy, _ddx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                _ax, _ay = wx + _ddx, wy + _ddy
                _adj_t = await load_single_tile(_ax, _ay, seed, db)
                if _adj_t.terrain in _ANCIENT_TREE_TILES:
                    _at_hit_type = _adj_t.terrain
                    _at_hit_x, _at_hit_y = _ax, _ay
                    break
            if _at_hit_type:
                # All 4 tiles share progress tracked at the root (bottom-left)
                _root_x, _root_y = _ancient_tree_root(_at_hit_type, _at_hit_x, _at_hit_y)
                _chop_row = await db.fetch_one(
                    "SELECT chops FROM tree_chop_progress WHERE world_x=? AND world_y=?",
                    (_root_x, _root_y)
                )
                _chops = (_chop_row["chops"] if _chop_row else 0) + 1
                if _chops >= 10:
                    # Fell the tree — set all 4 tiles to dirt and remove progress
                    await db.execute(
                        "DELETE FROM tree_chop_progress WHERE world_x=? AND world_y=?",
                        (_root_x, _root_y)
                    )
                    for _tx, _ty, _ in _ancient_tree_positions(_root_x, _root_y):
                        await set_tile_override(db, _tx, _ty, "dirt")
                    await add_to_inventory(db, user_id, "log", 6)
                    await add_to_inventory(db, user_id, "ancient_sapling", 1)
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, "🪓 The ancient tree crashes down! You gather **6 logs** and recover the **ancient sapling**.")
                else:
                    if _chop_row:
                        await db.execute(
                            "UPDATE tree_chop_progress SET chops=? WHERE world_x=? AND world_y=?",
                            (_chops, _root_x, _root_y)
                        )
                    else:
                        await db.execute(
                            "INSERT INTO tree_chop_progress(world_x, world_y, chops) VALUES(?,?,?)",
                            (_root_x, _root_y, _chops)
                        )
                    grid = await load_viewport(wx, wy, seed, db)
                    content = render_grid(grid, player, f"🪓 You strike the ancient tree. ({_chops}/10 chops)")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        # Fishing or watering can fill (overworld) — check hand_1 for priority
        _water_adj_act = await _is_adjacent_to_water(player, seed, db)
        if player.hand_1 == "watering_can" and _water_adj_act:
            await handle_fill_watering_can(interaction, guild_id, user_id)
            return
        elif player.hand_1 == "fishing_rod" and _water_adj_act:
            roll = _random.random()
            if roll < 0.50:
                await add_to_inventory(db, user_id, "fish", 1)
                msg = "🎣 You cast your line... and reel in a **fish**!"
            elif roll < 0.51:
                await add_to_inventory(db, user_id, "map_fragment", 1)
                msg = "🎣 You reel in something unusual — a **map fragment**!"
            else:
                msg = "🎣 You cast your line... the fish got away."
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, msg)
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        elif "watering_can" in hand_items and _water_adj_act:
            # watering_can must be hand_2 (hand_1 is something else)
            await handle_fill_watering_can(interaction, guild_id, user_id)
            return
        elif "fishing_rod" in hand_items and _water_adj_act:
            roll = _random.random()
            if roll < 0.50:
                await add_to_inventory(db, user_id, "fish", 1)
                msg = "🎣 You cast your line... and reel in a **fish**!"
            elif roll < 0.51:
                await add_to_inventory(db, user_id, "map_fragment", 1)
                msg = "🎣 You reel in something unusual — a **map fragment**!"
            else:
                msg = "🎣 You cast your line... the fish got away."
            grid = await load_viewport(wx, wy, seed, db)
            content = render_grid(grid, player, msg)
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        # ── Drop-box pickup ──────────────────────────────────────────────────
        cur_tile = await load_single_tile(wx, wy, seed, db)
        if cur_tile.structure in ("drop_box", "canoe_box") or (
            cur_tile.terrain in ("drop_box", "canoe_box")
        ):
            picked = await pickup_drop_box(db, wx, wy, user_id)
            grid = await load_viewport(wx, wy, seed, db)
            if picked:
                msg = f"📦 Picked up: {_pickup_desc(picked)}"
            else:
                msg = "📦 The box is empty."
            content = render_grid(grid, player, msg)
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

        # ── Investigation quest completion (ruins / shrine tiles) ────────────
        struct = cur_tile.structure
        if struct in ("ruins", "shrine"):
            from dwarf_explorer.game.quests import get_completable_investigation_quests, complete_quest
            from dwarf_explorer.database.repositories import give_quest_reward
            completable = await get_completable_investigation_quests(db, user_id, struct, wx, wy)
            if completable:
                q = completable[0]
                reward = await complete_quest(db, user_id, q["pq_id"])
                reward_str = ""
                if reward:
                    reward_str = await give_quest_reward(
                        db, user_id, reward["gold"], reward["xp"], reward.get("item")
                    )
                grid = await load_viewport(wx, wy, seed, db)
                content = render_grid(
                    grid, player,
                    f"📜 Quest complete: **{q['title']}**! You investigate the {struct}. {reward_str}"
                )
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return

        grid = await load_viewport(wx, wy, seed, db)
        content = render_grid(grid, player, "Nothing to interact with nearby.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Cave: build a player house (requires house_kit equipped) ─────────────
    if player.in_cave and not player.in_village and "house_kit" in hand_items:
        cx, cy = player.cave_x, player.cave_y
        cave_tile = await load_cave_single_tile(player.cave_id, cx, cy, db)
        _build_ok_cave = (
            cave_tile.terrain not in {"void", "cave_rock", "cave_wall", "cave_water",
                                      "player_house_cave"}
            and cave_tile.walkable
        )
        if _build_ok_cave:
            existing = await get_player_house_at(db, cx, cy, is_cave=True,
                                                 loc_cave_id=player.cave_id)
            if existing is not None:
                grid = await load_cave_viewport(player.cave_id, cx, cy, db)
                content = render_grid(grid, player, "🏠 A house already exists here.")
                view = _game_view(guild_id, user_id, player, grid=grid)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            # Consume house_kit
            if player.hand_1 == "house_kit":
                await unequip_item(db, user_id, "hand_1")
            elif player.hand_2 == "house_kit":
                await unequip_item(db, user_id, "hand_2")
            await remove_from_inventory(db, user_id, "house_kit", 1)
            # Update cave tile to player_house_cave
            await db.execute(
                "UPDATE cave_tiles SET tile_type='player_house_cave'"
                " WHERE cave_id=? AND local_x=? AND local_y=?",
                (player.cave_id, cx, cy),
            )
            await create_player_house(db, user_id, cx, cy, is_cave=True,
                                      loc_cave_id=player.cave_id)
            grid = await load_cave_viewport(player.cave_id, cx, cy, db)
            content = render_grid(grid, player, "🏠 **House built!** Step inside to decorate it.")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    # Fallback
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    _ww_msg = await _try_wayerwood_attune(player, user_id, db)
    content = render_grid(grid, player, _ww_msg if _ww_msg else "Nothing to interact with nearby.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Player-house edit handlers ────────────────────────────────────────────────

async def _ph_edit_response(
    interaction: discord.Interaction,
    guild_id: int,
    user_id: int,
    player,
    db,
    msg: str,
) -> None:
    """Helper: render house grid in edit mode and respond."""
    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    content = render_grid(grid, player, msg, cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=PlayerHouseEditView(guild_id, user_id),
    )


async def handle_house_edit_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Move the player within their house while in edit mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        return

    dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
    nx, ny = player.house_x + dx, player.house_y + dy

    # Load target tile
    target_tile = await load_player_house_single_tile(player.house_id, nx, ny, db)
    # Passability: walls and void are impassable inside the house
    _impassable = {"b_wall", "void"}
    if target_tile.terrain in _impassable:
        await _ph_edit_response(interaction, guild_id, user_id, player, db, "🚧 Can't move there.")
        return

    await update_player_house_state(
        db, user_id, True, player.house_id, nx, ny,
        player.house_vx, player.house_vy, "player_house",
    )
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            "✏️ Edit mode — use ➕ Add / ✖ Remove on the blue-highlighted tile.")


async def handle_house_add(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open decoration picker for the current tile (must be b_floor_wood)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        return

    tile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
    if tile.terrain != "b_floor_wood":
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "➕ Can only add decorations to bare wood-floor tiles.")
        return

    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {**state, "type": "house_deco", "deco_page": 0, "deco_selected": 0}
    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    content = render_grid(grid, player, "🪑 Choose a decoration to place on the blue tile:",
                          cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HouseDecorationView(guild_id, user_id, page=0, selected=0),
    )


async def handle_house_remove(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Remove a decoration from the current tile, restoring it to b_floor_wood."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        return

    tile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
    if tile.terrain not in PLAYER_HOUSE_DECO_TILES:
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "✖ No decoration here to remove.")
        return

    await set_player_house_tile(player.house_id, player.house_x, player.house_y, "b_floor_wood", db)
    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            f"✖ Removed **{tile.terrain}** — tile restored to wood floor.")


async def handle_house_delete(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Delete the current player house and eject the player."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        return

    # Only owner may delete
    owner_id = await get_player_house_owner(db, player.house_id)
    if owner_id != user_id:
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "🚫 Only the house owner can delete it.")
        return

    loc_x, loc_y, is_cave, loc_cave_id = await delete_player_house(db, player.house_id)

    if is_cave and loc_cave_id is not None:
        # Restore cave tile to cave_floor
        await db.execute(
            "UPDATE cave_tiles SET tile_type='cave_floor'"
            " WHERE cave_id=? AND local_x=? AND local_y=?",
            (loc_cave_id, loc_x, loc_y),
        )
        # Eject player back into cave at the house location, clear house state
        await update_player_cave_state(db, user_id, True, loc_cave_id, loc_x, loc_y)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        _invalidate_vp(user_id)
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "🗑️ House demolished.")
    else:
        # Restore overworld tile structure override (remove player_house)
        await db.execute(
            "DELETE FROM tile_overrides WHERE world_x=? AND world_y=? AND tile_type='player_house'",
            (loc_x, loc_y),
        )
        # Eject player back to overworld, clear house + cave state
        await update_player_position(db, user_id, loc_x, loc_y)
        await update_player_cave_state(db, user_id, False, None, 0, 0)
        await update_player_house_state(db, user_id, False, None, 0, 0, 0, 0)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        _invalidate_vp(user_id)
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "🗑️ House demolished.")

    _ui_state[user_id] = {}
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_house_edit_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Exit edit mode, return to normal house view."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {k: v for k, v in state.items() if k not in ("type",)}

    if not player.in_house or player.house_type != "player_house":
        return

    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "✅ Exited edit mode.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_house_deco_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    """Navigate decoration pages (prev/next)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    per_page = 5
    total_pages = max(1, (len(HOUSE_DECORATION_CATALOG) + per_page - 1) // per_page)
    page = state.get("deco_page", 0)
    if direction == "prev":
        page = max(0, page - 1)
    else:
        page = min(total_pages - 1, page + 1)
    _ui_state[user_id] = {**state, "deco_page": page}

    selected = state.get("deco_selected", 0)
    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    content = render_grid(grid, player, "🪑 Choose a decoration:", cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HouseDecorationView(guild_id, user_id, page=page, selected=selected),
    )


async def handle_house_deco_sel(
    interaction: discord.Interaction, guild_id: int, user_id: int, idx: int
) -> None:
    """Select a decoration item from the catalog."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    page = state.get("deco_page", 0)
    _ui_state[user_id] = {**state, "deco_selected": idx}

    grid = await load_player_house_viewport(player.house_id, player.house_x, player.house_y, db)
    cursor = (player.house_x, player.house_y)
    item = HOUSE_DECORATION_CATALOG[idx] if idx < len(HOUSE_DECORATION_CATALOG) else None
    msg = f"🪑 Selected **{item['name']}** — press 🏗️ Place to confirm." if item else "🪑 Choose a decoration:"
    content = render_grid(grid, player, msg, cursor_pos=cursor)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HouseDecorationView(guild_id, user_id, page=page, selected=idx),
    )


async def handle_house_deco_place(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Place the selected decoration on the current tile (consumes materials)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if not player.in_house or player.house_type != "player_house":
        return

    state = _ui_state.get(user_id, {})
    idx = state.get("deco_selected", 0)
    if idx >= len(HOUSE_DECORATION_CATALOG):
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "❌ Invalid selection.")
        return

    deco = HOUSE_DECORATION_CATALOG[idx]
    tile_id = deco["id"]
    cost = deco["cost"]

    # Verify current tile is b_floor_wood
    tile = await load_player_house_single_tile(player.house_id, player.house_x, player.house_y, db)
    if tile.terrain != "b_floor_wood":
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                "➕ Can only place decorations on bare wood-floor tiles.")
        return

    # Check materials
    missing = []
    for mat, qty in cost.items():
        row = await db.fetch_one(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?",
            (user_id, mat),
        )
        have = row["quantity"] if row else 0
        if have < qty:
            missing.append(f"{qty - have}× {mat}")
    if missing:
        await _ph_edit_response(interaction, guild_id, user_id, player, db,
                                f"❌ Need more: {', '.join(missing)}")
        return

    # Consume materials and place tile
    for mat, qty in cost.items():
        await remove_from_inventory(db, user_id, mat, qty)
    await set_player_house_tile(player.house_id, player.house_x, player.house_y, tile_id, db)

    # Return to edit mode
    _ui_state[user_id] = {**state, "type": "house_edit"}
    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            f"🏗️ Placed **{deco['name']}**!")


async def handle_house_deco_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel decoration selection and return to edit mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {**state, "type": "house_edit"}

    await _ph_edit_response(interaction, guild_id, user_id, player, db,
                            "❌ Cancelled.")


async def handle_forge_iron(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Smelt all iron ore into ingots at the forge (1 ore → 1 ingot)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ore_rows = await db.fetch_all(
        "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id='iron_ore'",
        (user_id,)
    )
    ore_count = ore_rows[0]["total"] if ore_rows and ore_rows[0]["total"] else 0

    if ore_count > 0:
        await remove_from_inventory(db, user_id, "iron_ore", ore_count)
        await add_to_inventory(db, user_id, "iron_ingot", ore_count)
        msg = (f"🔥 Smelted **{ore_count}** iron ore → "
               f"**{ore_count} iron ingot{'s' if ore_count > 1 else ''}**!")
    else:
        msg = "🔥 You need iron ore to smelt ingots."

    iron_ore = await _count_inv(db, user_id, "iron_ore")
    gold_ore = await _count_inv(db, user_id, "gold_ore")
    await interaction.response.edit_message(
        embed=_embed(msg), content=None,
        view=ForgeView(guild_id, user_id, iron_ore=iron_ore, gold_ore=gold_ore),
    )


async def handle_forge_gold(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Smelt all gold ore into gold ingots at the forge (1 ore → 1 ingot)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ore_rows = await db.fetch_all(
        "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id='gold_ore'",
        (user_id,)
    )
    ore_count = ore_rows[0]["total"] if ore_rows and ore_rows[0]["total"] else 0

    if ore_count > 0:
        await remove_from_inventory(db, user_id, "gold_ore", ore_count)
        await add_to_inventory(db, user_id, "gold_ingot", ore_count)
        msg = (f"🟡 Smelted **{ore_count}** gold ore → "
               f"**{ore_count} gold ingot{'s' if ore_count > 1 else ''}**!")
    else:
        msg = "🟡 You need gold ore to smelt gold ingots."

    iron_ore = await _count_inv(db, user_id, "iron_ore")
    gold_ore = await _count_inv(db, user_id, "gold_ore")
    await interaction.response.edit_message(
        embed=_embed(msg), content=None,
        view=ForgeView(guild_id, user_id, iron_ore=iron_ore, gold_ore=gold_ore),
    )


async def handle_forge_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "You step away from the forge.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Hearth handlers ──────────────────────────────────────────────────────────

async def _open_hearth(
    interaction: discord.Interaction, guild_id: int, user_id: int, player, db, grid=None
) -> None:
    """Build the hearth recipe menu and present it."""
    items = await get_inventory(db, user_id)
    counts: dict[str, int] = {}
    for it in items:
        counts[it["item_id"]] = counts.get(it["item_id"], 0) + it["quantity"]

    available: list[tuple[int, int, int]] = []
    for ridx, r in enumerate(_HEARTH_RECIPES):
        have = counts.get(r["input_id"], 0)
        if have >= r["input_qty"]:
            max_batches = have // r["input_qty"]
            available.append((ridx, have, max_batches))

    content = _hearth_content(available)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HearthView(guild_id, user_id, available),
    )


async def handle_hearth_choose(
    interaction: discord.Interaction, guild_id: int, user_id: int, recipe_idx: int
) -> None:
    """Player selected a recipe — open the qty chooser, or cook directly if max==1."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    items = await get_inventory(db, user_id)
    r = _HEARTH_RECIPES[recipe_idx]
    have = sum(it["quantity"] for it in items if it["item_id"] == r["input_id"])
    max_batches = max(1, have // r["input_qty"])

    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {**state, "hearth_recipe": recipe_idx, "hearth_qty": 1}

    if max_batches == 1:
        # Skip the qty menu and cook the single batch directly
        await _execute_hearth_cook(interaction, guild_id, user_id, player, db, recipe_idx, 1)
    else:
        content = _hearth_qty_content(recipe_idx, 1, max_batches)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=HearthQtyView(guild_id, user_id, recipe_idx, 1, max_batches),
        )


async def _execute_hearth_cook(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player, db, recipe_idx: int, qty: int
) -> None:
    """Consume ingredients and produce output; return to game view."""
    r = _HEARTH_RECIPES[recipe_idx]
    cost = qty * r["input_qty"]
    output = qty * r["output_qty"]
    await remove_from_inventory(db, user_id, r["input_id"], cost)
    await add_to_inventory(db, user_id, r["output_id"], output)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    in_name  = r["input_id"].replace("_", " ")
    out_name = r["output_id"].replace("_", " ")
    content = render_grid(
        grid, player,
        f"🔥 You {r['label'].lower()} {cost} {in_name} → {output} {out_name}!"
    )
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_hearth_qty_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    rid = state.get("hearth_recipe", 0)
    r = _HEARTH_RECIPES[rid]
    db = await get_database(guild_id)
    items = await get_inventory(db, user_id)
    have = sum(it["quantity"] for it in items if it["item_id"] == r["input_id"])
    max_batches = max(1, have // r["input_qty"])
    qty = state.get("hearth_qty", 1)
    qty = qty % max_batches + 1  # wrap: 1…max
    _ui_state[user_id] = {**state, "hearth_qty": qty}
    content = _hearth_qty_content(rid, qty, max_batches)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HearthQtyView(guild_id, user_id, rid, qty, max_batches),
    )


async def handle_hearth_qty_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    rid = state.get("hearth_recipe", 0)
    r = _HEARTH_RECIPES[rid]
    db = await get_database(guild_id)
    items = await get_inventory(db, user_id)
    have = sum(it["quantity"] for it in items if it["item_id"] == r["input_id"])
    max_batches = max(1, have // r["input_qty"])
    qty = state.get("hearth_qty", 1)
    qty = max_batches if qty <= 1 else qty - 1  # wrap: max…1
    _ui_state[user_id] = {**state, "hearth_qty": qty}
    content = _hearth_qty_content(rid, qty, max_batches)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HearthQtyView(guild_id, user_id, rid, qty, max_batches),
    )


async def handle_hearth_qty_all(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    rid = state.get("hearth_recipe", 0)
    r = _HEARTH_RECIPES[rid]
    db = await get_database(guild_id)
    items = await get_inventory(db, user_id)
    have = sum(it["quantity"] for it in items if it["item_id"] == r["input_id"])
    max_batches = max(1, have // r["input_qty"])
    _ui_state[user_id] = {**state, "hearth_qty": max_batches}
    content = _hearth_qty_content(rid, max_batches, max_batches)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=HearthQtyView(guild_id, user_id, rid, max_batches, max_batches),
    )


async def handle_hearth_qty_modal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    rid = state.get("hearth_recipe", 0)
    r = _HEARTH_RECIPES[rid]
    db = await get_database(guild_id)
    items = await get_inventory(db, user_id)
    have = sum(it["quantity"] for it in items if it["item_id"] == r["input_id"])
    max_batches = max(1, have // r["input_qty"])
    await interaction.response.send_modal(HearthQtyModal(guild_id, user_id, max_batches))


async def handle_hearth_qty_cook(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    rid = state.get("hearth_recipe", 0)
    qty = state.get("hearth_qty", 1)
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    # Clamp qty to what we actually have right now
    r = _HEARTH_RECIPES[rid]
    items = await get_inventory(db, user_id)
    have = sum(it["quantity"] for it in items if it["item_id"] == r["input_id"])
    max_batches = max(1, have // r["input_qty"])
    qty = max(1, min(qty, max_batches))
    await _execute_hearth_cook(interaction, guild_id, user_id, player, db, rid, qty)


async def handle_hearth_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "You step away from the hearth.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def _anvil_refresh(
    interaction: discord.Interaction, guild_id: int, user_id: int, msg: str | None = None
) -> None:
    """Re-render the anvil list and edit the message."""
    db = await get_database(guild_id)
    state = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    cursor   = state.get("anvil_cursor", 0)
    mat_idx  = state.get("anvil_material", 0)
    inv_rows = await get_inventory(db, user_id)
    inv_counts = {r["item_id"]: r["quantity"] for r in inv_rows}
    content = _render_anvil(cursor, inv_counts, mat_idx)
    if msg:
        content = msg + "\n\n" + content
    await interaction.response.edit_message(
        embed=_embed(content), content=None, view=AnvilView(guild_id, user_id, mat_idx)
    )


_ANVIL_COLS = 7


async def handle_anvil_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move the anvil cursor up one row (7 slots back) within the recipe list."""
    state   = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    mat_idx = state.get("anvil_material", 0)
    cursor  = state.get("anvil_cursor", 0)
    count   = len(_anvil_filtered_recipes(mat_idx))
    cursor  = (cursor - _ANVIL_COLS) % max(count, 1)
    _ui_state[user_id] = {**state, "anvil_cursor": cursor}
    await _anvil_refresh(interaction, guild_id, user_id)


async def handle_anvil_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move the anvil cursor down one row (7 slots forward) within the recipe list."""
    state   = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    mat_idx = state.get("anvil_material", 0)
    cursor  = state.get("anvil_cursor", 0)
    count   = len(_anvil_filtered_recipes(mat_idx))
    cursor  = (cursor + _ANVIL_COLS) % max(count, 1)
    _ui_state[user_id] = {**state, "anvil_cursor": cursor}
    await _anvil_refresh(interaction, guild_id, user_id)


async def handle_anvil_prev(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move the anvil cursor to the previous recipe (wraps)."""
    state   = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    mat_idx = state.get("anvil_material", 0)
    count   = len(_anvil_filtered_recipes(mat_idx))
    cursor  = (state.get("anvil_cursor", 0) - 1) % max(count, 1)
    _ui_state[user_id] = {**state, "anvil_cursor": cursor}
    await _anvil_refresh(interaction, guild_id, user_id)


async def handle_anvil_next(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move the anvil cursor to the next recipe (wraps)."""
    state   = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    mat_idx = state.get("anvil_material", 0)
    count   = len(_anvil_filtered_recipes(mat_idx))
    cursor  = (state.get("anvil_cursor", 0) + 1) % max(count, 1)
    _ui_state[user_id] = {**state, "anvil_cursor": cursor}
    await _anvil_refresh(interaction, guild_id, user_id)


async def handle_anvil_mat_prev(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Switch to the previous material page (wraps)."""
    state = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    mat_idx = (state.get("anvil_material", 0) - 1) % len(_ANVIL_MATERIALS)
    _ui_state[user_id] = {**state, "anvil_material": mat_idx, "anvil_cursor": 0}
    await _anvil_refresh(interaction, guild_id, user_id)


async def handle_anvil_mat_next(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Switch to the next material page (wraps)."""
    state = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    mat_idx = (state.get("anvil_material", 0) + 1) % len(_ANVIL_MATERIALS)
    _ui_state[user_id] = {**state, "anvil_material": mat_idx, "anvil_cursor": 0}
    await _anvil_refresh(interaction, guild_id, user_id)


# Aliases for backward-compat with old button IDs
async def handle_anvil_mat_iron(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    _ui_state[user_id] = {**state, "anvil_material": 0, "anvil_cursor": 0}
    await _anvil_refresh(interaction, guild_id, user_id)


async def handle_anvil_mat_wyvern(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    _ui_state[user_id] = {**state, "anvil_material": 1, "anvil_cursor": 0}
    await _anvil_refresh(interaction, guild_id, user_id)


async def handle_anvil_craft(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft the currently selected recipe."""
    state   = _ui_state.get(user_id, {"anvil_cursor": 0, "anvil_material": 0})
    mat_idx = state.get("anvil_material", 0)
    cursor  = state.get("anvil_cursor", 0)
    recipes = _anvil_filtered_recipes(mat_idx)
    if not recipes:
        await _anvil_refresh(interaction, guild_id, user_id, "No recipes available.")
        return
    cursor = max(0, min(cursor, len(recipes) - 1))
    recipe = recipes[cursor]

    db = await get_database(guild_id)

    cost_item = recipe["cost_item"]
    cost_qty  = recipe["cost_qty"]
    output_qty = recipe.get("output_qty", 1)

    if recipe["base_item"]:
        # Wyvern-style upgrade: needs base iron piece + cost_item (scales/etc)
        base_row = await db.fetch_one(
            "SELECT SUM(quantity) AS total FROM inventory WHERE user_id=? AND item_id=?",
            (user_id, recipe["base_item"]),
        )
        mat_row = await db.fetch_one(
            "SELECT SUM(quantity) AS total FROM inventory WHERE user_id=? AND item_id=?",
            (user_id, cost_item),
        )
        base_qty = (base_row["total"] or 0) if base_row else 0
        mat_qty  = (mat_row["total"] or 0) if mat_row else 0

        if base_qty >= 1 and mat_qty >= cost_qty:
            await remove_from_inventory(db, user_id, recipe["base_item"], 1)
            await remove_from_inventory(db, user_id, cost_item, cost_qty)
            await add_to_inventory(db, user_id, recipe["item_id"], output_qty)
            msg = f"🐉 You forge a **{recipe['name']}**! ({recipe['stat']})"
        elif base_qty < 1:
            base_name = recipe["base_item"].replace("_", " ")
            msg = f"🐉 You need a **{base_name}** to upgrade."
        else:
            mat_name = cost_item.replace("_", " ")
            msg = f"🐉 You need {cost_qty} {mat_name}{'s' if cost_qty > 1 else ''} (have {mat_qty})."
    else:
        mat_row = await db.fetch_one(
            "SELECT SUM(quantity) AS total FROM inventory WHERE user_id=? AND item_id=?",
            (user_id, cost_item),
        )
        mat_qty = (mat_row["total"] or 0) if mat_row else 0

        if mat_qty >= cost_qty:
            await remove_from_inventory(db, user_id, cost_item, cost_qty)
            await add_to_inventory(db, user_id, recipe["item_id"], output_qty)
            if output_qty > 1:
                msg = f"⚒️ You craft **{output_qty}× {recipe['name']}**!"
            else:
                msg = f"⚒️ You craft a **{recipe['name']}**! ({recipe['stat']})"
        else:
            mat_name = cost_item.replace("_", " ")
            msg = (
                f"⚒️ You need {cost_qty} {mat_name}{'s' if cost_qty > 1 else ''} "
                f"to craft a {recipe['name']} (have {mat_qty})."
            )

    await _anvil_refresh(interaction, guild_id, user_id, msg)


async def handle_anvil_dagger(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft a dagger at the anvil (1 iron ingot)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ingot_row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
    )
    ingot_count = ingot_row["quantity"] if ingot_row else 0

    if ingot_count >= 1:
        await remove_from_inventory(db, user_id, "iron_ingot", 1)
        await add_to_inventory(db, user_id, "dagger", 1)
        msg = "⚒️ You craft a **dagger**! (+8 attack, equip to hand)"
    else:
        msg = "⚒️ You need 1 iron ingot to craft a dagger."

    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=AnvilView(guild_id, user_id, _ui_state.get(user_id, {}).get("anvil_material", 0))
    )


async def handle_anvil_sword(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft a sword at the anvil (2 iron ingots)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    ingot_row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
    )
    ingot_count = ingot_row["quantity"] if ingot_row else 0

    if ingot_count >= 2:
        await remove_from_inventory(db, user_id, "iron_ingot", 2)
        await add_to_inventory(db, user_id, "sword", 1)
        msg = "⚒️ You forge a **sword**! (+12 attack, equip to hand)"
    else:
        msg = "⚒️ You need 2 iron ingots to forge a sword."

    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=AnvilView(guild_id, user_id, _ui_state.get(user_id, {}).get("anvil_material", 0))
    )


async def _anvil_craft(interaction: discord.Interaction, guild_id: int, user_id: int,
                       item_id: str, ingot_cost: int, name: str, stat_desc: str) -> None:
    """Generic anvil crafting helper."""
    db = await get_database(guild_id)
    ingot_row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id='iron_ingot'", (user_id,)
    )
    ingot_count = ingot_row["quantity"] if ingot_row else 0
    if ingot_count >= ingot_cost:
        await remove_from_inventory(db, user_id, "iron_ingot", ingot_cost)
        await add_to_inventory(db, user_id, item_id, 1)
        msg = f"⚒️ You craft a **{name}**! ({stat_desc})"
    else:
        msg = f"⚒️ You need {ingot_cost} iron ingot{'s' if ingot_cost > 1 else ''} to craft a {name}."
    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=AnvilView(guild_id, user_id, _ui_state.get(user_id, {}).get("anvil_material", 0))
    )


async def handle_anvil_helmet(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_helmet", 2, "Iron Helmet", "+3 defense, equip to head")


async def handle_anvil_chestplate(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_chestplate", 4, "Iron Chestplate", "+5 defense, equip to chest")


async def handle_anvil_leggings(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_leggings", 3, "Iron Leggings", "+4 defense, equip to legs")


async def handle_anvil_cannonball(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "cannonball", 2, "Cannonball", "ammunition for ship cannons")


async def handle_anvil_iron_boots(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_boots", 2, "Iron Boots", "+2 defense, equip to boots")


async def handle_anvil_iron_shield(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_craft(interaction, guild_id, user_id, "iron_shield", 4, "Iron Shield", "+4 defense, equip to hand")


async def _anvil_wyvern_upgrade(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    base_item: str, scale_cost: int, result_item: str, name: str, stat_desc: str,
) -> None:
    """Upgrade an iron armor/shield piece to wyvern using scales."""
    db = await get_database(guild_id)
    base_row = await db.fetch_one(
        "SELECT SUM(quantity) AS total FROM inventory WHERE user_id=? AND item_id=?",
        (user_id, base_item),
    )
    scale_row = await db.fetch_one(
        "SELECT SUM(quantity) AS total FROM inventory WHERE user_id=? AND item_id='wyvern_scale'",
        (user_id,),
    )
    base_qty = (base_row["total"] or 0) if base_row else 0
    scale_qty = (scale_row["total"] or 0) if scale_row else 0

    if base_qty >= 1 and scale_qty >= scale_cost:
        await remove_from_inventory(db, user_id, base_item, 1)
        await remove_from_inventory(db, user_id, "wyvern_scale", scale_cost)
        await add_to_inventory(db, user_id, result_item, 1)
        msg = f"🐉 You forge a **{name}**! ({stat_desc})"
    elif base_qty < 1:
        base_name = base_item.replace("_", " ")
        msg = f"🐉 You need a **{base_name}** to upgrade."
    else:
        msg = f"🐉 You need {scale_cost} wyvern scales to upgrade (have {scale_qty})."
    await interaction.response.edit_message(
        embed=_embed(msg), content=None, view=AnvilView(guild_id, user_id, _ui_state.get(user_id, {}).get("anvil_material", 0))
    )


async def handle_anvil_wyvern_helmet(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_wyvern_upgrade(interaction, guild_id, user_id,
                                "iron_helmet", 2, "wyvern_helmet",
                                "Wyvern Helmet", "+5 defense, equip to head")


async def handle_anvil_wyvern_chestplate(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_wyvern_upgrade(interaction, guild_id, user_id,
                                "iron_chestplate", 4, "wyvern_chestplate",
                                "Wyvern Chestplate", "+8 defense, equip to chest")


async def handle_anvil_wyvern_leggings(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_wyvern_upgrade(interaction, guild_id, user_id,
                                "iron_leggings", 3, "wyvern_leggings",
                                "Wyvern Leggings", "+6 defense, equip to legs")


async def handle_anvil_wyvern_shield(interaction: discord.Interaction, guild_id: int, user_id: int) -> None:
    await _anvil_wyvern_upgrade(interaction, guild_id, user_id,
                                "iron_shield", 4, "wyvern_shield",
                                "Wyvern Shield", "+7 defense, equip to hand")


async def handle_anvil_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "You step away from the anvil.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Shrine handlers ───────────────────────────────────────────────────────────

async def handle_shrine_enchant(
    interaction: discord.Interaction, guild_id: int, user_id: int, shrine_type: str
) -> None:
    """Imbue gem with selected enchantment at the shrine."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    seed = await get_or_create_world(db, guild_id)

    if shrine_type not in SHRINE_SACRIFICES:
        return

    data = SHRINE_SACRIFICES[shrine_type]
    sac_item = data["item"]
    sac_qty = data["qty"]
    result_item = data["result"]

    # Verify gem is still in hand
    gem_slot = None
    if player.hand_1 == "gem":
        gem_slot = "hand_1"
    elif player.hand_2 == "gem":
        gem_slot = "hand_2"

    if gem_slot is None:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player, "⛩️ You no longer have a gem equipped.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Check sacrifice items
    sac_rows = await db.fetch_all(
        "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
        (user_id, sac_item)
    )
    have = sac_rows[0]["total"] if sac_rows and sac_rows[0]["total"] else 0
    if have < sac_qty:
        # Rebuild shrine view with updated counts
        inv_counts: dict[str, int] = {}
        for st, sdata in SHRINE_SACRIFICES.items():
            si = sdata["item"]
            if si not in inv_counts:
                r2 = await db.fetch_all(
                    "SELECT SUM(quantity) as total FROM inventory WHERE user_id=? AND item_id=?",
                    (user_id, si)
                )
                inv_counts[si] = (r2[0]["total"] if r2 and r2[0]["total"] else 0)
        view = ShrineView(guild_id, user_id, inv_counts)
        content = (
            f"⛩️ Not enough {sac_item.replace('_', ' ')} — need {sac_qty}, have {have}.\n"
            "Choose a different enchantment or gather more materials."
        )
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Consume gem (unequip + remove from inventory)
    await unequip_item(db, user_id, gem_slot)
    await remove_from_inventory(db, user_id, "gem", 1)
    # Consume sacrifice
    await remove_from_inventory(db, user_id, sac_item, sac_qty)
    # Give enchanted gem
    await add_to_inventory(db, user_id, result_item, 1)

    result_name = result_item.replace("_", " ")
    sac_name = sac_item.replace("_", " ")
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(
        grid, player,
        f"⛩️ The shrine blazes with light! Your gem is imbued — you receive a **{result_name}**!\n"
        f"Combine it with a **gold ring** in your inventory to craft a special ring."
    )
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_shrine_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel shrine enchantment menu and return to game."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    seed = await get_or_create_world(db, guild_id)
    grid = await load_viewport(player.world_x, player.world_y, seed, db)
    content = render_grid(grid, player, "⛩️ You step away from the shrine.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Inventory handlers ────────────────────────────────────────────────────────

async def handle_inventory(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    prev_state = _ui_state.get(user_id, {})
    prev_arena = prev_state.get("arena")

    # On ship (in or out of combat) → show ship cargo chest instead of personal inventory
    if player.in_ship:
        chest_items = await get_ship_cargo_items(db, user_id)
        player_items = await get_inventory(db, user_id)
        inv_rows, inv_cols = _inv_capacity(player)
        _ui_state[user_id] = {
            "type": "ship_chest_cargo",
            "selected": 0,
            "chest_view": "chest",
            "prev_arena": prev_arena,
        }
        content = render_ship_chest(chest_items, player_items, 0, "chest",
                                    "Ship Cargo", player, inv_rows, inv_cols)
        view = ShipChestView(guild_id, user_id, "cargo", "chest")
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # In combat (not on ship) → normal inventory, preserving prev_arena
    # Not in combat → normal inventory regardless of location (ship chest is a separate interaction)
    prev_selections = prev_state.get("selections", {})
    prev_mode = prev_state.get("sel_mode", "add")
    prev_nav_target = prev_state.get("nav_target")
    _ui_state[user_id] = {
        "type": "inventory", "selected": 0, "prev_arena": prev_arena,
        "selections": prev_selections, "sel_mode": prev_mode,
        "cursor_mode": "inventory", "equipped_cursor": 0,
        "move_mode": False, "move_origin": None,
        "nav_target": prev_nav_target,
        "watering_can_uses": player.watering_can_uses,
    }
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, 0, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    """Navigate inventory left/right (prev/next) — also handles equipped/gold row."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    cursor_mode = state.get("cursor_mode", "inventory")
    total_slots = inv_rows * inv_cols

    if cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
        num_eq = len(_EQUIP_SLOT_ORDER)
        new_eq = (state.get("equipped_cursor", 0) + delta) % num_eq
        _ui_state[user_id] = {**state, "equipped_cursor": new_eq}
    elif cursor_mode == "inventory":
        visible = [it for it in items if it["item_id"] != "gold_coin"]
        current_sel = state.get("selected", 0)
        new_sel = (current_sel + delta) % max(1, total_slots)

        # Canoe pair: cursor always lives on canoe_right, never canoe_left.
        # Build canoe positions (only slots on the same row count as a pair).
        _slot_map_nav = _build_slot_map(visible, total_slots, inv_cols)
        _canoe_left_pos: set[int] = set()
        _canoe_right_pos: set[int] = set()
        for _ci in range(total_slots - 1):
            _l = _slot_map_nav.get(_ci)
            _r = _slot_map_nav.get(_ci + 1)
            if (_l and _l["item_id"] == "canoe_left"
                    and _r and _r["item_id"] == "canoe_right"
                    and _ci // inv_cols == (_ci + 1) // inv_cols):
                _canoe_left_pos.add(_ci)
                _canoe_right_pos.add(_ci + 1)

        if delta == -1 and current_sel in _canoe_right_pos:
            # LEFT from canoe_right → skip the whole pair, land on item before canoe_left
            new_sel = (current_sel - 2) % max(1, total_slots)
        elif new_sel in _canoe_left_pos:
            # Landed on canoe_left → redirect to canoe_right
            new_sel += 1

        _ui_state[user_id] = {**state, "type": "inventory", "selected": new_sel}
    else:
        _ui_state[user_id] = {**state}

    content, view = _inv_view(guild_id, user_id, items, _ui_state[user_id].get("selected", 0),
                              equipped, inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move inventory cursor up one row (or to equipped/gold row)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    cursor_mode = state.get("cursor_mode", "inventory")

    visible = [it for it in items if it["item_id"] != "gold_coin"]
    if cursor_mode == "inventory":
        current_row = state.get("selected", 0) // inv_cols
        if current_row == 0:
            # Move up into equipped row
            new_state = {**state, "cursor_mode": "equipped", "equipped_cursor": 0}
        else:
            new_sel = max(0, state["selected"] - inv_cols)
            new_sel = _canoe_cursor_adjust(visible, new_sel, inv_cols)
            new_state = {**state, "selected": new_sel}
    elif cursor_mode == "equipped":
        new_state = {**state, "cursor_mode": "gold"}
    else:
        new_state = {**state}  # already at gold (top)

    _ui_state[user_id] = {**new_state, "type": "inventory"}
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, _ui_state[user_id].get("selected", 0),
                              equipped, inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Move inventory cursor down one row (or from equipped/gold into grid)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    total_slots = inv_rows * inv_cols
    cursor_mode = state.get("cursor_mode", "inventory")

    visible = [it for it in items if it["item_id"] != "gold_coin"]
    if cursor_mode == "gold":
        new_state = {**state, "cursor_mode": "equipped", "equipped_cursor": 0}
    elif cursor_mode == "equipped":
        start_sel = _canoe_cursor_adjust(visible, 0, inv_cols)
        new_state = {**state, "cursor_mode": "inventory", "selected": start_sel}
    else:
        new_sel = min(total_slots - 1, state.get("selected", 0) + inv_cols)
        new_sel = _canoe_cursor_adjust(visible, new_sel, inv_cols)
        new_state = {**state, "selected": new_sel}

    _ui_state[user_id] = {**new_state, "type": "inventory"}
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, _ui_state[user_id].get("selected", 0),
                              equipped, inv_rows, inv_cols, _ui_state[user_id], gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


def _inv_view(guild_id: int, user_id: int, items: list, sel: int, equipped: dict,
              inv_rows: int, inv_cols: int, state: dict, msg_suffix: str = "",
              gold: int = 0, watering_can_uses: int = 0) -> tuple[str, "InventoryView"]:
    """Helper: build inventory content + view with consistent state."""
    from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
    selections = state.get("selections", {})
    sel_mode = state.get("sel_mode", "add")
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)
    move_mode = state.get("move_mode", False)

    # Visible items (gold_coin filtered out)
    visible = [it for it in items if it["item_id"] != "gold_coin"]

    label, action = _inv_action_btn(items, sel, equipped, cursor_mode, equipped_cursor)

    # Resolve cursor_id for all modes so Select / ± work everywhere
    if cursor_mode == "inventory":
        _ci = _cursor_item(visible, sel)
        cursor_id = _ci["item_id"] if _ci else None
    elif cursor_mode == "gold":
        cursor_id = "gold_coin"
    elif cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER as _ESO
        if equipped_cursor < len(_ESO):
            _eq_slot, _ = _ESO[equipped_cursor]
            cursor_id = equipped.get(_eq_slot)  # None if slot is empty
        else:
            cursor_id = None
    else:
        cursor_id = None

    # ± buttons: show when cursor item is in the selection basket
    show_pm = cursor_id is not None and cursor_id in selections
    # Drop button: only for inventory and gold mode (equipped items must be unequipped first)
    show_drop = show_pm and cursor_mode in ("inventory", "gold")

    move_qty = state.get("move_qty", 1)

    _wcu = watering_can_uses or state.get("watering_can_uses", 0)
    content = render_inventory(
        items, sel, equipped, label, inv_rows, inv_cols, selections,
        gold=gold, cursor_mode=cursor_mode, equipped_cursor=equipped_cursor,
        watering_can_uses=_wcu,
    )
    if move_mode:
        # Show move qty and total in move mode suffix
        total_max = state.get("move_qty_max") or move_qty
        content += f"\n*↔️ Moving ×{move_qty} of {total_max} — navigate to destination, then Confirm.*"
    # Consumable tooltip: show what the item does when cursor rests on one
    if cursor_mode == "inventory" and cursor_id and cursor_id in CONSUMABLE_ITEMS:
        _cons = CONSUMABLE_ITEMS[cursor_id]
        _cons_name = cursor_id.replace("_", " ").title()
        content += f"\n*{_cons_name}: {_cons['desc']}*"
    if msg_suffix:
        content += msg_suffix

    # Determine max qty for modal
    if move_mode:
        modal_max = state.get("move_qty_max") or 1
    elif show_pm and cursor_id is not None:
        modal_max = sum(it["quantity"] for it in items if it["item_id"] == cursor_id)
    else:
        modal_max = 1

    view = InventoryView(
        guild_id, user_id, label, action, selections, cursor_id, sel_mode,
        cursor_mode=cursor_mode,
        show_plus_minus=show_pm,
        show_drop=show_drop,
        move_mode=move_mode,
        move_qty=move_qty,
    )
    # Stash modal_max on view so the button handler can read it
    view._modal_max = modal_max
    return content, view


async def _recalculate_attack_stat(db, user_id: int, just_equipped: str,
                                    slot_type: str,
                                    old_hand_1: str | None,
                                    old_hand_2: str | None) -> None:
    """Recalculate player attack using only main-hand weapon bonus."""
    from dwarf_explorer.config import PLAYER_START_ATTACK, EQUIP_BONUSES, ITEM_EQUIP_SLOTS
    # Determine what will be in hand_1 after this equip
    if slot_type == "hand":
        # Just equipped to hand_1 (first free hand) or hand_2
        new_hand_1 = just_equipped if not old_hand_1 else old_hand_1
    else:
        new_hand_1 = old_hand_1
    atk_bonus = EQUIP_BONUSES.get(new_hand_1 or "", {}).get("attack", 0)
    await update_player_stats(db, user_id, attack=PLAYER_START_ATTACK + atk_bonus)


async def handle_inv_equip(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Equip the item under the cursor (also redirects food → eat)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    visible = [it for it in items if it["item_id"] != "gold_coin"]

    cur_item = _cursor_item(visible, sel)
    if cur_item is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item selected)*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    item_id = cur_item["item_id"]

    # Food items are handled by handle_inv_eat — redirect
    _is_hp_food = item_id in FOOD_HP_RESTORE or (
        item_id in CONSUMABLE_ITEMS and CONSUMABLE_ITEMS[item_id].get("hp", 0) > 0
    )
    if _is_hp_food:
        await handle_inv_eat(interaction, guild_id, user_id)
        return

    # Look up slot type
    slot_type = ITEM_EQUIP_SLOTS.get(item_id)
    if not slot_type:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*{item_id.replace('_', ' ').title()} cannot be equipped.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Pouch unequip capacity check (if equipping a smaller pouch to replace)
    existing_in_slot = equipped.get(slot_type)
    if existing_in_slot:
        # Return old equipped item to inventory first
        if existing_in_slot == "canoe":
            from dwarf_explorer.database.repositories import add_canoe_pair as _acp
            await _acp(db, user_id)
        else:
            await add_to_inventory(db, user_id, existing_in_slot, 1)

    # Resolve hand slot
    if slot_type == "hand":
        if item_id in TWO_HANDED_ITEMS:
            if equipped.get("hand_1") or equipped.get("hand_2"):
                content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                          inv_rows, inv_cols, state,
                                          "\n*Your hands must be free for a two-handed item.*",
                                          gold=player.gold)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            await equip_item(db, user_id, "hand_1", item_id)
            await equip_item(db, user_id, "hand_2", item_id)
        else:
            if not equipped.get("hand_1"):
                resolved_slot = "hand_1"
            elif not equipped.get("hand_2"):
                resolved_slot = "hand_2"
            else:
                content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                          inv_rows, inv_cols, state,
                                          "\n*Both hands are full.*",
                                          gold=player.gold)
                await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
                return
            await equip_item(db, user_id, resolved_slot, item_id)
    else:
        await equip_item(db, user_id, slot_type, item_id)

    # Remove 1 of the equipped item from inventory
    await remove_from_inventory(db, user_id, item_id, 1)

    bonuses = EQUIP_BONUSES.get(item_id, {})
    if bonuses:
        non_attack_bonuses = {k: v for k, v in bonuses.items() if k != "attack"}
        if non_attack_bonuses:
            await update_player_stats(db, user_id, **non_attack_bonuses)
    # Recalculate attack from main hand only
    await _recalculate_attack_stat(db, user_id, item_id, slot_type,
                                   getattr(player, "hand_1", None),
                                   getattr(player, "hand_2", None))
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, state,
                              f"\n*Equipped {item_id.replace('_', ' ').title()}!*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_unequip(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Unequip the item at the equipped-row cursor (returns it to inventory)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    equipped_cursor = state.get("equipped_cursor", 0)

    from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
    if equipped_cursor >= len(_EQUIP_SLOT_ORDER):
        return

    slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
    item_id = equipped.get(slot)
    if not item_id:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0),
                                  equipped, inv_rows, inv_cols, state,
                                  "\n*(Nothing equipped in that slot.)*", gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Special: coin purse unequip with overflow
    if slot == "coin_purse":
        new_cap = COIN_PURSE_CAPACITY[None]  # bare capacity
        overflow = max(0, player.gold - new_cap)
        if overflow > 0:
            await db.execute("UPDATE players SET gold=? WHERE user_id=?", (new_cap, user_id))
            px = player.world_x if not player.in_cave else player.cave_x
            py = player.world_y if not player.in_cave else player.cave_y
            await create_drop_box(db, px, py, [("gold_coin", overflow)])

    # Pouch unequip: check inventory fits in smaller grid
    if slot == "pouch":
        pouch_order = [None, "small_pouch", "medium_pouch", "large_pouch"]
        cur_idx = pouch_order.index(item_id) if item_id in pouch_order else 0
        new_rows, new_cols = POUCH_SIZES[pouch_order[cur_idx - 1]] if cur_idx > 0 else POUCH_SIZES[None]
        new_capacity = new_rows * new_cols
        visible = [it for it in items if it["item_id"] != "gold_coin"]
        if len(visible) > new_capacity:
            content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0),
                equipped, inv_rows, inv_cols, state,
                f"\n*Can't unequip: inventory has {len(visible)} items but smaller pouch fits {new_capacity}. Remove items first.*",
                gold=player.gold)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    if item_id in TWO_HANDED_ITEMS:
        await unequip_item(db, user_id, "hand_1")
        await unequip_item(db, user_id, "hand_2")
    else:
        await unequip_item(db, user_id, slot)

    if item_id == "canoe":
        # Canoe needs a 2-slot adjacent pair, not the regular add_to_inventory path
        from dwarf_explorer.database.repositories import add_canoe_pair
        await add_canoe_pair(db, user_id)
    else:
        await add_to_inventory(db, user_id, item_id, 1)
    # Recalculate attack: if main hand was unequipped, reset to base
    if slot in ("hand_1",) or item_id in TWO_HANDED_ITEMS:
        from dwarf_explorer.config import PLAYER_START_ATTACK
        hand_2_item = equipped.get("hand_2")
        if item_id in TWO_HANDED_ITEMS:
            hand_2_item = None
        # After unequipping hand_1, hand_2 may have a weapon but main hand is empty = base attack
        await update_player_stats(db, user_id, attack=PLAYER_START_ATTACK)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0),
                              equipped, inv_rows, inv_cols, state,
                              f"\n*Unequipped {item_id.replace('_', ' ').title()}.*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_eat(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Eat a food item from inventory, restoring HP."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    cur_item = _cursor_item(visible, sel)
    if cur_item is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item selected)*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    item_id = cur_item["item_id"]

    # ── Breath of the Sea: restores breath when inside a shipwreck ──────────
    if item_id == "breath_of_the_sea":
        if not getattr(player, "in_shipwreck", False):
            content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                      inv_rows, inv_cols, state,
                                      "\n*\U0001FAB7 You can only use Breath of the Sea underwater (inside a shipwreck).*",
                                      gold=player.gold)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
        player.breath = BREATH_MAX
        await update_player_shipwreck_state(
            db, user_id, True,
            player.shipwreck_wx, player.shipwreck_wy,
            player.shipwreck_x, player.shipwreck_y,
            BREATH_MAX,
        )
        await remove_from_inventory(db, user_id, item_id, 1)
        items = await get_inventory(db, user_id)
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*\U0001FAB7 You inhale a magical bubble — breath restored to {BREATH_MAX}/{BREATH_MAX}!*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    restore = FOOD_HP_RESTORE.get(item_id)
    if restore is None:
        restore = CONSUMABLE_ITEMS.get(item_id, {}).get("hp")
    if restore is None or restore <= 0:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  f"\n*{item_id.replace('_', ' ').title()} is not food.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if player.hp >= player.max_hp:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*You're already at full health!*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    new_hp = min(player.max_hp, player.hp + restore)
    await update_player_stats(db, user_id, hp=new_hp)
    await remove_from_inventory(db, user_id, item_id, 1)
    await _auto_unequip_depleted(db, user_id, item_id, player)
    # Auto-deselect if selection qty now exceeds remaining (across all stacks)
    selections = dict(state.get("selections", {}))
    if item_id in selections:
        remain_rows = await db.fetch_all(
            "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id)
        )
        remain = sum(r["quantity"] for r in remain_rows)
        if remain <= 0:
            del selections[item_id]
        else:
            selections[item_id] = min(selections[item_id], remain)
        state = {**state, "selections": selections}
        _ui_state[user_id] = state
    items = await get_inventory(db, user_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, state,
                              f"\n*🍗 Ate {item_id.replace('_', ' ')}. HP: {new_hp}/{player.max_hp}*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_select(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Select or deselect the current cursor item for crafting."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    selections = dict(state.get("selections", {}))
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)

    if cursor_mode == "gold":
        if "gold_coin" in selections:
            del selections["gold_coin"]
            msg = "\n*Deselected coins.*"
        elif player.gold > 0:
            selections["gold_coin"] = 1
            msg = f"\n*Selected 1 coin (have {player.gold}). Use ➖/➕ to adjust qty.*"
        else:
            msg = "\n*(No coins to select)*"
    elif cursor_mode == "equipped":
        from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER
        equipped = _equipped_dict(player)
        if equipped_cursor < len(_EQUIP_SLOT_ORDER):
            slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
            item_id = equipped.get(slot)
            if item_id:
                if item_id in selections:
                    del selections[item_id]
                    msg = f"\n*Deselected {item_id.replace('_', ' ').title()}.*"
                else:
                    selections[item_id] = 1
                    msg = f"\n*Selected equipped {item_id.replace('_', ' ').title()}.*"
            else:
                msg = "\n*(No item equipped in that slot)*"
        else:
            msg = "\n*(No item at cursor)*"
    else:  # cursor_mode == "inventory"
        cur_item = _cursor_item(visible, sel)
        if cur_item is not None:
            item_id = cur_item["item_id"]
            if item_id in selections:
                del selections[item_id]
                msg = f"\n*Deselected {item_id.replace('_', ' ').title()}.*"
            else:
                selections[item_id] = 1
                msg = f"\n*Selected {item_id.replace('_', ' ').title()} ×1.*"
        else:
            msg = "\n*(No item at cursor)*"

    _ui_state[user_id] = {**state, "selections": selections}
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_unselect_all(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Clear all item selections."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    _ui_state[user_id] = {**state, "selections": {}}
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], "\n*Cleared all selections.*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_item_btn(
    interaction: discord.Interaction, guild_id: int, user_id: int, idx: int
) -> None:
    """Add or subtract 1 from the Nth selected item based on current sel_mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    selections = dict(state.get("selections", {}))
    sel_mode = state.get("sel_mode", "add")
    sel_list = list(selections.items())
    if idx >= len(sel_list):
        return
    item_id, qty = sel_list[idx]
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    sel = state.get("selected", 0)
    if sel_mode == "add":
        have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
        new_qty = min(have, qty + 1)
        selections[item_id] = new_qty
        msg = f"\n*➕ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    else:
        new_qty = qty - 1
        if new_qty <= 0:
            del selections[item_id]
            msg = f"\n*➖ Removed {item_id.replace('_', ' ').title()} from selection.*"
        else:
            selections[item_id] = new_qty
            msg = f"\n*➖ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    _ui_state[user_id] = {**state, "selections": selections}
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_toggle_mode(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Toggle selection mode between Add (➕) and Subtract (➖)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    new_mode = "sub" if state.get("sel_mode", "add") == "add" else "add"
    _ui_state[user_id] = {**state, "sel_mode": new_mode}
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    mode_name = "➖ Subtract" if new_mode == "sub" else "➕ Add"
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              f"\n*Mode switched to {mode_name}*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_item_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Increase quantity of the item in the sub-menu selection."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    item_id = state.get("item_view")
    selections = dict(state.get("selections", {}))
    if item_id and item_id in selections:
        # Cap at player's actual stack
        items = await get_inventory(db, user_id)
        have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
        new_qty = min(have, selections[item_id] + 1)
        selections[item_id] = new_qty
        _ui_state[user_id] = {**state, "selections": selections}
        content = (f"🎒 **Item Detail: {item_id.replace('_', ' ').title()}**\n"
                   f"Selected quantity: **×{new_qty}** (have ×{have})\n"
                   f"Use + More / − Less to adjust, or Unselect to remove.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=InventoryItemView(guild_id, user_id, new_qty)
        )
    else:
        pass  # no matching item in selections


async def handle_inv_item_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Decrease quantity of the item in the sub-menu selection."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    item_id = state.get("item_view")
    selections = dict(state.get("selections", {}))
    if item_id and item_id in selections:
        new_qty = selections[item_id] - 1
        if new_qty <= 0:
            del selections[item_id]
            item_id = None
        else:
            selections[item_id] = new_qty
        _ui_state[user_id] = {**state, "selections": selections, "item_view": item_id}
        if item_id:
            content = (f"🎒 **Item Detail: {item_id.replace('_', ' ').title()}**\n"
                       f"Selected quantity: **×{new_qty}**\n"
                       f"Use + More / − Less to adjust, or Unselect to remove.")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=InventoryItemView(guild_id, user_id, new_qty)
            )
        else:
            # Quantity hit zero, return to main inventory
            await handle_inv_item_back(interaction, guild_id, user_id)
    # else: item_id not in selections — nothing to do


async def handle_inv_item_unsel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Unselect the item currently shown in the sub-menu."""
    state = _ui_state.get(user_id, {})
    item_id = state.get("item_view")
    selections = dict(state.get("selections", {}))
    if item_id and item_id in selections:
        del selections[item_id]
    _ui_state[user_id] = {**state, "selections": selections, "item_view": None}
    await handle_inv_item_back(interaction, guild_id, user_id)


async def handle_inv_item_back(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Return from item sub-menu to main inventory view."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    _ui_state[user_id] = {**state, "item_view": None}
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_craft(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft item if current selections exactly match a recipe."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    selections = state.get("selections", {})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    sel_set = frozenset((k, v) for k, v in selections.items())
    recipe = CRAFT_RECIPES.get(sel_set)
    if recipe is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*No matching recipe for the selected items.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Verify player has enough of each ingredient (sum across all stacks)
    for item_id, qty in selections.items():
        total_have = sum(
            it["quantity"] for it in items if it["item_id"] == item_id
        )
        if total_have < qty:
            content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                      inv_rows, inv_cols, state,
                                      f"\n*Not enough {item_id.replace('_', ' ')} to craft.*",
                                      gold=player.gold)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    # ── Special recipe: wayerwood attunement ─────────────────────────────────
    if recipe.get("special") == "wayerwood_attune":
        # Consume rock only; wayerwood stays in inventory
        await remove_from_inventory(db, user_id, "rock", 1)
        _ui_state[user_id] = {**state, "selections": {}}
        items = await get_inventory(db, user_id)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        equipped = _equipped_dict(player)
        # Compute hot/cold signal
        if not getattr(player, "in_cave", False):
            ww_msg = "🪄 *The wayerwood feels lifeless here. It only stirs in the depths of the earth.*"
        else:
            cracks = await db.fetch_all(
                "SELECT local_x, local_y FROM cave_tiles "
                "WHERE cave_id=? AND tile_type='cracked_stone'",
                (player.cave_id,)
            )
            if not cracks:
                ww_msg = "🪄 *The wayerwood hums quietly. No hidden passages stir within these walls.*"
            else:
                cx, cy = player.cave_x, player.cave_y
                nearest = min(cracks, key=lambda r: abs(r["local_x"] - cx) + abs(r["local_y"] - cy))
                dist_now = abs(nearest["local_x"] - cx) + abs(nearest["local_y"] - cy)
                last_dist = _ui_state.get(user_id, {}).get("ww_last_dist")
                _ui_state.setdefault(user_id, {})["ww_last_dist"] = dist_now
                if last_dist is None:
                    ww_msg = "🪄 *The wayerwood pulses faintly. Something stirs within these walls...*"
                elif dist_now < last_dist:
                    ww_msg = "🪄 *The wayerwood pulses... pulling you forward.*"
                elif dist_now > last_dist:
                    ww_msg = "🪄 *The wayerwood dims... you've veered away.*"
                else:
                    ww_msg = "🪄 *The wayerwood hums steadily.*"
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, _ui_state[user_id],
                                  f"\n{ww_msg}",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Consume ingredients and add result
    for item_id, qty in selections.items():
        await remove_from_inventory(db, user_id, item_id, qty)
    await add_to_inventory(db, user_id, recipe["result"], recipe["qty"])

    # Clear selections and refresh
    _ui_state[user_id] = {**state, "selections": {}}
    items = await get_inventory(db, user_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              f"\n*✨ Crafted {recipe['qty']}× {recipe['result'].replace('_', ' ').title()}!*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    prev_state = _ui_state.get(user_id, {})
    prev_arena = prev_state.get("prev_arena")
    is_house_owner = prev_state.get("is_house_owner", False)
    saved_nav_target = prev_state.get("nav_target")
    _ui_state.pop(user_id, None)
    # Restore nav_target so quest marker stays on the viewport
    if saved_nav_target:
        _ui_state[user_id] = {"nav_target": saved_nav_target}
    # Restore player-house owner flag so Edit button re-appears after close
    if player.in_house and player.house_type == "player_house" and is_house_owner:
        _ui_state.setdefault(user_id, {})["is_house_owner"] = True
    # If inventory was opened during combat, return to combat view
    if player.in_combat and prev_arena is not None:
        _ui_state[user_id] = {"type": "combat", "arena": prev_arena}
        content = render_arena(prev_arena, player)
        view = _combat_view(guild_id, user_id, prev_arena, player)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return
    grid = await _cached_grid(user_id, player, seed, db)
    if player.in_cave:
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    else:
        has_canoe = await _player_has_canoe(db, user_id)
        view = _game_view(guild_id, user_id, player, grid=grid, has_canoe=has_canoe)
    nav = _ui_state.get(user_id, {}).get("nav_target")
    content = render_grid(grid, player, nav_target=nav)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_sel_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Increase the selected quantity for the cursor item (+1, wrapping)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    selections = dict(state.get("selections", {}))
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    cursor_mode = state.get("cursor_mode", "inventory")
    msg = None
    if cursor_mode == "gold":
        total_have = player.gold
        current = selections.get("gold_coin", 0)
        new_qty = (current % max(total_have, 1)) + 1
        selections["gold_coin"] = new_qty
        _ui_state[user_id] = {**state, "selections": selections}
        msg = f"\n*➕ Coins → ×{new_qty}*"
    else:
        cur_item = _cursor_item(visible, sel)
        if cur_item is not None:
            item_id = cur_item["item_id"]
            total_have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
            current = selections.get(item_id, 0)
            new_qty = (current % max(total_have, 1)) + 1
            selections[item_id] = new_qty
            _ui_state[user_id] = {**state, "selections": selections}
            msg = f"\n*➕ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    if msg is None:
        msg = "\n*(No item at cursor)*"

    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_sel_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Decrease the selected quantity for the cursor item (−1, wrapping to max)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    selections = dict(state.get("selections", {}))
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    cursor_mode = state.get("cursor_mode", "inventory")
    msg = None
    if cursor_mode == "gold":
        total_have = player.gold
        current = selections.get("gold_coin", 1)
        new_qty = total_have if current <= 1 else current - 1
        selections["gold_coin"] = new_qty
        _ui_state[user_id] = {**state, "selections": selections}
        msg = f"\n*➖ Coins → ×{new_qty}*"
    else:
        cur_item = _cursor_item(visible, sel)
        if cur_item is not None:
            item_id = cur_item["item_id"]
            total_have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
            current = selections.get(item_id, 1)
            new_qty = total_have if current <= 1 else current - 1
            selections[item_id] = new_qty
            _ui_state[user_id] = {**state, "selections": selections}
            msg = f"\n*➖ {item_id.replace('_', ' ').title()} → ×{new_qty}*"
    if msg is None:
        msg = "\n*(No item at cursor)*"

    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_fq_enter_aim_mode(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Toggle slingshot aim mode in the Thornwarden boss fight."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not getattr(player, "in_fq_boss_combat", False):
        await interaction.response.defer()
        return
    # Has slingshot?
    if player.hand_1 != "slingshot" and player.hand_2 != "slingshot":
        from dwarf_explorer.world.forest_quest import load_fq_viewport as _lfqv_aim
        _bst_chk = {"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
        grid = await _lfqv_aim(player.fq_area_id, player.fq_x, player.fq_y, db, boss_state=_bst_chk)
        content = render_grid(grid, player, "🎯 You need a **Slingshot** equipped to aim.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return
    player.fq_boss_aim_mode = True
    player.fq_boss_aim_x = player.fq_x
    player.fq_boss_aim_y = player.fq_y
    await db.execute(
        "UPDATE players SET fq_boss_aim_mode=1, fq_boss_aim_x=?, fq_boss_aim_y=? WHERE user_id=?",
        (player.fq_x, player.fq_y, user_id),
    )
    from dwarf_explorer.world.forest_quest import load_fq_viewport as _lfqv_aim2
    _bst_a = {"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
    _ac = (player.fq_boss_aim_x, player.fq_boss_aim_y)
    grid = await _lfqv_aim2(player.fq_area_id, player.fq_x, player.fq_y, db,
                            boss_state=_bst_a, aim_cursor=_ac)
    content = render_grid(grid, player,
        "🎯 **Aim mode** — use arrow buttons to move the cursor, then press 🪨 Fire!\n"
        f"Cursor: ({player.fq_boss_aim_x}, {player.fq_boss_aim_y})")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_fq_boss_shoot(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Fire the slingshot at the current aim cursor position in the boss fight."""
    import random as _rand_shoot
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not getattr(player, "in_fq_boss_combat", False):
        await interaction.response.defer()
        return

    from dwarf_explorer.world.forest_quest import (
        load_fq_viewport as _lfqv_shoot,
        defeat_warden as _dfw,
    )
    from dwarf_explorer.config import (
        FQ_WARDEN_EYE_CYCLE as _wec_s,
        FQ_WARDEN_EYE_POSITIONS as _wep_s,
        FQ_WARDEN_WARN_TURN as _fq_warn_s,
        FQ_ENT_CORE_DROP_WARDEN as _wdrp_s,
    )
    from dwarf_explorer.database.repositories import (
        remove_from_inventory as _rfi_s,
    )

    cx, cy = player.fq_boss_aim_x, player.fq_boss_aim_y

    # Exit aim mode regardless of outcome
    player.fq_boss_aim_mode = False
    await db.execute(
        "UPDATE players SET fq_boss_aim_mode=0 WHERE user_id=?", (user_id,)
    )

    # Check rock availability
    _rock_row = await db.fetch_one(
        "SELECT COALESCE(SUM(quantity),0) AS q FROM inventory WHERE user_id=? AND item_id='rock'",
        (user_id,),
    )
    _rock_qty = int(_rock_row["q"]) if _rock_row else 0
    if _rock_qty < 1:
        _bst_nr = {"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
        grid = await _lfqv_shoot(player.fq_area_id, player.fq_x, player.fq_y, db, boss_state=_bst_nr)
        content = render_grid(grid, player,
            "🪨 You have no rocks! Buy some from the shopkeeper further back.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return

    await _rfi_s(db, user_id, "rock", 1)

    # Is this the warning-phase eye?
    msg = ""
    if player.fq_boss_turn == _fq_warn_s:
        _cur_eye = _wec_s[player.fq_boss_eye_idx]
        _eye_pos = _wep_s[_cur_eye]
        if (cx, cy) == _eye_pos:
            # HIT — destroy this eye
            _eyes_list = list(player.fq_boss_eyes)
            _eyes_list[player.fq_boss_eye_idx] = "0"
            player.fq_boss_eyes = "".join(_eyes_list)
            # Update DB tile to dead
            await db.execute(
                "UPDATE forest_quest_tiles SET tile_type='fq_warden_dead' "
                "WHERE fq_id=? AND local_x=? AND local_y=?",
                (player.fq_area_id, cx, cy),
            )
            # Interrupt attack: reset turn counter
            player.fq_boss_turn = 0
            # Advance eye index to next alive eye
            for _ni in range(1, 5):
                _nidx = (player.fq_boss_eye_idx + _ni) % 4
                if player.fq_boss_eyes[_nidx] == "1":
                    player.fq_boss_eye_idx = _nidx
                    break
            msg = (
                f"🎯 **DIRECT HIT!** The **{_cur_eye}** eye shatters in a burst of light!\n"
                f"*Eyes remaining: {player.fq_boss_eyes.count('1')}/4*"
            )
            # Check all eyes dead
            if player.fq_boss_eyes.count("1") == 0:
                await _dfw(db, player.fq_area_id)
                player.in_fq_boss_combat = False
                # Advance quest stage
                _ws = getattr(player, "fq_quest_stage", "none")
                if _ws not in ("warden_defeated", "canal_solved", "quest_complete"):
                    player.fq_quest_stage = "warden_defeated"
                    await db.execute(
                        "UPDATE players SET fq_quest_stage='warden_defeated' WHERE user_id=?",
                        (user_id,)
                    )
                msg += (
                    "\n\n🌿 **THE THORNWARDEN COLLAPSES!**\n"
                    "Ancient brambles crash to the earth. "
                    "A heavy gate grinds open at the far end of the chamber...\n"
                    "📦 A chest lies in the rubble."
                )
            await db.execute(
                "UPDATE players SET fq_boss_eyes=?, fq_boss_turn=?, fq_boss_eye_idx=?, "
                "in_fq_boss_combat=? WHERE user_id=?",
                (player.fq_boss_eyes, player.fq_boss_turn, player.fq_boss_eye_idx,
                 1 if player.in_fq_boss_combat else 0, user_id),
            )
        else:
            msg = f"🪨 The rock skips off the bark — missed the **{_cur_eye}** eye at ({_eye_pos[0]},{_eye_pos[1]})."
    else:
        _phase = "open" if player.fq_boss_turn > _fq_warn_s else "dormant"
        msg = (f"🪨 Rock flies wide. The eye is **{_phase}** — only shoot during the ⚠️ warning phase!")

    await db.commit()
    _bst_sh = {"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
    grid = await _lfqv_shoot(player.fq_area_id, player.fq_x, player.fq_y, db, boss_state=_bst_sh)
    content = render_grid(grid, player, msg)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_fq_boss_aim_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel slingshot aim mode without firing."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player.fq_boss_aim_mode = False
    await db.execute(
        "UPDATE players SET fq_boss_aim_mode=0 WHERE user_id=?", (user_id,)
    )
    from dwarf_explorer.world.forest_quest import load_fq_viewport as _lfqv_ac
    _bst_ac = {"eyes": player.fq_boss_eyes, "warn_eye": None, "open_eye": None}
    grid = await _lfqv_ac(player.fq_area_id, player.fq_x, player.fq_y, db, boss_state=_bst_ac)
    content = render_grid(grid, player, "🎯 Aim cancelled.")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_inv_drop(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Drop selected items onto the player's current tile as a drop box."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    selections = dict(state.get("selections", {}))
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    # Can't drop in buildings, ships, ocean, or other special locations
    if (player.in_house or player.in_high_seas
            or player.in_ship or player.in_island or getattr(player, "in_shipwreck", False)):
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*You can only drop items in the overworld.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Can't drop on structure tiles (overworld only check)
    seed = await get_or_create_world(db, guild_id)
    wx, wy = player.world_x, player.world_y
    if not player.in_cave and not player.in_village:
        cur_tile = await load_single_tile(wx, wy, seed, db)
        if cur_tile.structure is not None:
            content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                      inv_rows, inv_cols, state,
                                      "\n*You can't drop items on a structure tile.*",
                                      gold=player.gold)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    if not selections:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                  inv_rows, inv_cols, state,
                                  "\n*Select items first (use Select/Desel, then ➖/➕ to set qty).*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    drop_pairs: list[tuple[str, int]] = []
    gold_to_drop = 0
    for item_id, qty in selections.items():
        if item_id == "gold_coin":
            gold_to_drop = min(qty, player.gold)
        else:
            total_have = sum(it["quantity"] for it in items if it["item_id"] == item_id)
            drop_qty = min(qty, total_have)
            if drop_qty > 0:
                drop_pairs.append((item_id, drop_qty))

    if not drop_pairs and not gold_to_drop:
        content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                                  inv_rows, inv_cols, state, "\n*Nothing to drop.*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    for item_id, qty in drop_pairs:
        await remove_from_inventory(db, user_id, item_id, qty)
    if gold_to_drop:
        drop_pairs.append(("gold_coin", gold_to_drop))
        await db.execute(
            "UPDATE players SET gold=gold-? WHERE user_id=?", (gold_to_drop, user_id)
        )

    if player.in_cave:
        from dwarf_explorer.database.repositories import create_cave_drop_box
        await create_cave_drop_box(db, player.cave_id, player.cave_x, player.cave_y, drop_pairs)
    elif player.in_village:
        from dwarf_explorer.database.repositories import create_village_drop_box
        await create_village_drop_box(db, player.village_id, player.village_x, player.village_y, drop_pairs)
    else:
        _is_canoe_drop = any(iid == "canoe" for iid, _ in drop_pairs)
        _drop_tile_type = "canoe_box" if _is_canoe_drop else "drop_box"
        await create_drop_box(db, wx, wy, drop_pairs, tile_type=_drop_tile_type)
    _invalidate_vp(user_id)  # tile changed without movement — bust cache

    _ui_state[user_id] = {**state, "selections": {}}
    items = await get_inventory(db, user_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    def _drop_name(iid: str) -> str:
        if iid == "gold_coin":
            return "Gold Coin"
        return iid.replace("_", " ").title()
    drop_desc = ", ".join(f"{qty}× {_drop_name(iid)}" for iid, qty in drop_pairs)
    content, view = _inv_view(guild_id, user_id, items, state.get("selected", 0), equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              f"\n*🫳 Dropped: {drop_desc}.*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Enter move mode: remember the current slot as origin."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    sel = state.get("selected", 0)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    origin_item = _cursor_item(visible, sel)
    if origin_item is None:
        content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                                  inv_rows, inv_cols, state, "\n*(No item to move)*",
                                  gold=player.gold)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # move_qty_max = total of this item across ALL stacks (user can consolidate)
    total_of_item = sum(it["quantity"] for it in items if it["item_id"] == origin_item["item_id"])
    _ui_state[user_id] = {
        **state,
        "move_mode": True,
        "move_origin": sel,
        "move_qty": origin_item["quantity"],  # default to this slot's qty
        "move_qty_max": total_of_item,
    }
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_confirm(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Confirm move: move/split/swap origin to destination using move_qty."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    visible = [it for it in items if it["item_id"] != "gold_coin"]
    sel = state.get("selected", 0)
    origin = state.get("move_origin", sel)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    origin_item = _cursor_item(visible, origin)
    dest_item   = _cursor_item(visible, sel)
    move_qty    = max(1, state.get("move_qty", 1))

    if origin == sel or origin_item is None:
        msg = "\n*(Nothing to move)*"

    elif origin_item["item_id"] == "canoe":
        # Canoe occupies 2 adjacent slots. dest_left is where the canoe's left
        # half should land; the right half then sits at dest_left+1.
        # The cursor lives on the right half visually, so sel points at the
        # destination right cell — meaning dest_left = sel - 1.
        dest_left = sel - 1 if _cursor_item(visible, sel - 1) is None or _cursor_item(visible, sel - 1) is origin_item else sel
        dest_right = dest_left + 1
        total = inv_rows * inv_cols
        if (dest_left < 0 or dest_right >= total
                or dest_left // inv_cols != dest_right // inv_cols):
            msg = "\n*(Canoe needs 2 adjacent slots on the same row)*"
        elif dest_left == origin_item["slot_index"]:
            msg = "\n*(Canoe is already here)*"
        else:
            # Move the canoe row's slot_index. If items occupy dest_left/dest_right,
            # they slide back to where the canoe used to be.
            canoe_old = origin_item["slot_index"]
            blockers = [it for it in visible
                        if it["slot_index"] in (dest_left, dest_right)
                        and it is not origin_item]
            if len(blockers) > 1:
                msg = "\n*(Destination blocked by multiple items)*"
            else:
                await db.execute(
                    "UPDATE inventory SET slot_index = -1 WHERE user_id=? AND item_id='canoe' AND slot_index=?",
                    (user_id, canoe_old),
                )
                if blockers:
                    await db.execute(
                        "UPDATE inventory SET slot_index=? WHERE user_id=? AND slot_index=?",
                        (canoe_old, user_id, blockers[0]["slot_index"]),
                    )
                await db.execute(
                    "UPDATE inventory SET slot_index=? WHERE user_id=? AND item_id='canoe' AND slot_index=-1",
                    (dest_left, user_id),
                )
                msg = "\n*🛶 Canoe moved.*"

    elif dest_item is not None and dest_item["item_id"] != origin_item["item_id"]:
        # Different item types — swap full stacks, ignore move_qty
        await swap_inventory_slots(db, user_id, origin_item["slot_index"], dest_item["slot_index"])
        msg = "\n*↔️ Items swapped.*"

    elif dest_item is not None and dest_item["item_id"] == origin_item["item_id"]:
        # Same item type — fill destination up to MAX_STACK_SIZE from source stacks
        from dwarf_explorer.config import MAX_STACK_SIZE
        space = MAX_STACK_SIZE - dest_item["quantity"]
        if space <= 0:
            msg = "\n*(Destination stack is full)*"
        else:
            # Available = sum of all stacks EXCEPT the destination slot
            available = sum(
                it["quantity"] for it in visible
                if it["item_id"] == origin_item["item_id"]
                and it["slot_index"] != dest_item["slot_index"]
            )
            transfer = min(move_qty, space, available)
            if transfer <= 0:
                msg = "\n*(Nothing to move)*"
            else:
                # Grow the destination slot
                await db.execute(
                    "UPDATE inventory SET quantity = quantity + ? WHERE user_id=? AND slot_index=?",
                    (transfer, user_id, dest_item["slot_index"]),
                )
                # Drain from all other stacks of same item (LIFO), excluding destination
                stacks = await db.fetch_all(
                    "SELECT id, quantity FROM inventory "
                    "WHERE user_id=? AND item_id=? AND slot_index!=? ORDER BY slot_index DESC",
                    (user_id, origin_item["item_id"], dest_item["slot_index"]),
                )
                remaining = transfer
                for stack in stacks:
                    if remaining <= 0:
                        break
                    take = min(stack["quantity"], remaining)
                    if take == stack["quantity"]:
                        await db.execute("DELETE FROM inventory WHERE id=?", (stack["id"],))
                    else:
                        await db.execute(
                            "UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                            (take, stack["id"]),
                        )
                    remaining -= take
                msg = f"\n*↔️ Merged ×{transfer} into stack.*"

    else:
        # Empty destination — move up to MAX_STACK_SIZE, drawing from all stacks
        from dwarf_explorer.config import MAX_STACK_SIZE
        total_avail = sum(
            it["quantity"] for it in visible if it["item_id"] == origin_item["item_id"]
        )
        transfer = min(move_qty, MAX_STACK_SIZE, total_avail)
        # Drain stacks (LIFO)
        stacks = await db.fetch_all(
            "SELECT id, quantity FROM inventory "
            "WHERE user_id=? AND item_id=? ORDER BY slot_index DESC",
            (user_id, origin_item["item_id"]),
        )
        remaining = transfer
        for stack in stacks:
            if remaining <= 0:
                break
            take = min(stack["quantity"], remaining)
            if take == stack["quantity"]:
                await db.execute("DELETE FROM inventory WHERE id=?", (stack["id"],))
            else:
                await db.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                    (take, stack["id"]),
                )
            remaining -= take
        # Place at destination slot
        await db.execute(
            "INSERT INTO inventory(user_id, item_id, quantity, slot_index) VALUES(?,?,?,?)",
            (user_id, origin_item["item_id"], transfer, sel),
        )
        msg = f"\n*↔️ Moved ×{transfer}.*"

    _ui_state[user_id] = {
        **state, "move_mode": False, "move_origin": None, "move_qty": 1, "move_qty_max": None,
    }
    items = await get_inventory(db, user_id)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id], msg,
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel move mode, returning cursor to origin slot."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    origin = state.get("move_origin", state.get("selected", 0))
    items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)

    _ui_state[user_id] = {**state, "move_mode": False, "move_origin": None,
                          "move_qty": 1, "move_qty_max": None, "selected": origin}
    content, view = _inv_view(guild_id, user_id, items, origin, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              "\n*↔️ Move cancelled.*",
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_qty_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Increase move quantity by 1, wrapping at move_qty_max (total of item across all stacks)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    total_max = state.get("move_qty_max") or 1

    current = state.get("move_qty", total_max)
    new_qty = (current % total_max) + 1  # wraps 1 → total_max
    _ui_state[user_id] = {**state, "move_qty": new_qty}

    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_move_qty_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Decrease move quantity by 1, wrapping at 1 → move_qty_max."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0})
    items = await get_inventory(db, user_id)
    total_max = state.get("move_qty_max") or 1

    current = state.get("move_qty", total_max)
    new_qty = total_max if current <= 1 else current - 1
    _ui_state[user_id] = {**state, "move_qty": new_qty}

    sel = state.get("selected", 0)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content, view = _inv_view(guild_id, user_id, items, sel, equipped,
                              inv_rows, inv_cols, _ui_state[user_id],
                              gold=player.gold)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_inv_qty_modal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open a modal to enter a custom quantity (for move or select)."""
    state = _ui_state.get(user_id, {"selected": 0})
    move_mode = state.get("move_mode", False)

    if move_mode:
        max_qty = state.get("move_qty_max") or 1
        modal = InvQtyModal(guild_id, user_id, "move", max_qty)
    else:
        # select mode — look up total across stacks
        db = await get_database(guild_id)
        player = await get_or_create_player(db, user_id, interaction.user.display_name)
        items = await get_inventory(db, user_id)
        visible = [it for it in items if it["item_id"] != "gold_coin"]
        sel = state.get("selected", 0)
        cursor_mode = state.get("cursor_mode", "inventory")
        if cursor_mode == "gold":
            max_qty = player.gold
        else:
            ci = _cursor_item(visible, sel)
            if ci:
                max_qty = sum(it["quantity"] for it in items if it["item_id"] == ci["item_id"])
            else:
                max_qty = 1
        modal = InvQtyModal(guild_id, user_id, "select", max_qty)

    await interaction.response.send_modal(modal)


# ── Shop helpers ──────────────────────────────────────────────────────────────

def _get_shop_catalog(state: dict) -> list:
    """Return the correct shop catalog based on ui_state mode flags."""
    if state.get("tree_city_mode"):
        from dwarf_explorer.config import TREE_CITY_SHOP as _TCS_gc
        return _TCS_gc
    elif state.get("tavern_mode"):
        return TAVERN_MENU
    elif state.get("farmer_mode"):
        return FARMER_SHOP
    elif state.get("armory_mode"):
        from dwarf_explorer.config import ARMORY_CATALOG as _AC_gc
        return _AC_gc
    else:
        return SHOP_CATALOG


def _shop_render(state: dict, player_items: list, equipped: dict,
                 player_gold: int, inv_rows: int, inv_cols: int) -> str:
    """Build shop content string from current state."""
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    catalog = _get_shop_catalog(state)
    return render_shop(
        catalog, player_items, sel, view_mode, equipped,
        player_gold, inv_rows, inv_cols, ITEM_SELL_PRICES, qty,
    )


# ── Shop handlers ─────────────────────────────────────────────────────────────

async def _open_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player: Player,
) -> None:
    db = await get_database(guild_id)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    _ui_state[user_id] = {"type": "shop", "selected": 0, "shop_view": "shop", "qty": 1}
    content = _shop_render(_ui_state[user_id], player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop"))


async def _open_farmer_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player: Player,
) -> None:
    """Open the farmer shop (buy-only, uses FARMER_SHOP catalog)."""
    db = await get_database(guild_id)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    _ui_state[user_id] = {"type": "farmer_shop", "selected": 0, "shop_view": "shop",
                          "qty": 1, "farmer_mode": True}
    content = _shop_render(_ui_state[user_id], player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop",
                                                          farmer_mode=True))


async def _open_tavern_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player: Player,
) -> None:
    """Open the tavern shop (buy-only, uses TAVERN_MENU catalog)."""
    db = await get_database(guild_id)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    _ui_state[user_id] = {"type": "tavern_shop", "selected": 0, "shop_view": "shop",
                          "qty": 1, "tavern_mode": True}
    content = _shop_render(_ui_state[user_id], player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop",
                                                          tavern_mode=True))


async def _open_armory_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player: Player,
) -> None:
    """Open the armory shop (buy-only, uses ARMORY_CATALOG)."""
    from dwarf_explorer.config import ARMORY_CATALOG
    db = await get_database(guild_id)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    _ui_state[user_id] = {"type": "armory_shop", "selected": 0, "shop_view": "shop",
                          "qty": 1, "armory_mode": True}
    content = _shop_render(_ui_state[user_id], player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop",
                                                          armory_mode=True))


async def _open_hermit_dialogue(
    interaction: discord.Interaction,
    guild_id: int, user_id: int, player, db, grid: list,
) -> None:
    """Hermit NPC dialogue — triggered by 🧙 Talk when adjacent to hermit_npc tile."""
    from dwarf_explorer.world.forest import get_hermit_forest_info as _ghfi_hh
    from dwarf_explorer.game.quests import update_forest_depths_quest_target as _ufdqt_hh
    _stage = getattr(player, "fq_quest_stage", "none")

    if _stage == "none":
        msg = (
            "🧙 The hermit barely glances up from a tattered book, surrounded by "
            "tangled vines and scattered notes.\n\n"
            "*'Hmph. Another wanderer. These woods have many secrets, traveller. "
            "But you don't look ready for them yet.'*"
        )
    elif _stage == "seek_hermit":
        _fmap = await db.fetch_one(
            "SELECT 1 FROM player_map_collection "
            "WHERE user_id=? AND map_type='forest' AND ref_id=?",
            (user_id, player.forest_id),
        )
        if not _fmap:
            msg = (
                "🧙 The hermit squints at you from beneath a wild brow of unruly grey.\n\n"
                "*'You're looking for something deeper in these woods? "
                "You'll need a proper map of this forest first — "
                "find the hidden cache nearby. It holds a chart of the grounds.'*\n\n"
                "🗺️ *Explore the forest for a hidden chest containing a **Forest Map**.*"
            )
        else:
            # Has map → advance quest to hermit_met, redirect tracker to FQ entrance
            _hinfo_hh = await _ghfi_hh(db)
            _new_wx_hh = _hinfo_hh["world_x"] if _hinfo_hh else None
            _new_wy_hh = _hinfo_hh["world_y"] if _hinfo_hh else None
            player.fq_quest_stage = "hermit_met"
            await db.execute(
                "UPDATE players SET fq_quest_stage='hermit_met' WHERE user_id=?", (user_id,)
            )
            if _new_wx_hh is not None:
                await _ufdqt_hh(db, user_id, _new_wx_hh, _new_wy_hh)
            msg = (
                "🧙 The old man's eyes widen as he sees your forest chart.\n\n"
                "*'Ah — you've mapped this place. Good. Then you're ready to hear it.'*\n\n"
                "He sets down his book and leans forward, voice dropping to a murmur:\n"
                "*'There is an entrance deeper in the forest — looks just like any other tree. "
                "I've marked it on your chart. Beyond it lies something ancient. "
                "Something that predates even the Tree City.'*\n\n"
                "*'Bring your wits. And perhaps something sharp.'*\n\n"
                "📍 *Quest updated — the marker now points to the Forest Depths entrance.*"
            )
    elif _stage == "hermit_met":
        msg = (
            "🧙 The hermit nods slowly, gesturing at the door.\n\n"
            "*'You haven't gone in yet? The entrance is marked on your map. "
            "Look for it at the edge of this forest — it blends in with the trees.'*\n\n"
            "*'Once you pass through, you'll be in the old growth. "
            "Mind the roots — and the things that move in the dark.'*"
        )
    elif _stage in ("wayerwood_crafted", "map_marked", "puzzle_solved",
                    "warden_defeated", "canal_solved"):
        _hh_hints = {
            "wayerwood_crafted": (
                "*'The Wayerwood is forged. Head to the Forest Depths entrance — "
                "my mark is on your tracker.'*"
            ),
            "map_marked": (
                "*'You've entered the depths. Good. Push the heavy logs to bridge the stream — "
                "the forest will show you the way.'*"
            ),
            "puzzle_solved": (
                "*'The stream is bridged. Press deeper — something old waits beyond. "
                "It won't be friendly.'*"
            ),
            "warden_defeated": (
                "*'The Thornwarden is slain. Impressive. "
                "Navigate the fork and solve the canal ahead.'*"
            ),
            "canal_solved": (
                "*'The canal is open. The final chamber awaits. "
                "Whatever lies within — you are ready.'*"
            ),
        }
        msg = (
            "🧙 The hermit sets aside a crumbling scroll and fixes you with a steady gaze.\n\n"
            + _hh_hints.get(_stage, "*'Keep pushing forward. The forest does not reward hesitation.'*")
        )
    else:
        # quest_complete or rewarded
        msg = (
            "🧙 The hermit looks up from his work with a rare, quiet smile.\n\n"
            "*'You've seen it all now, haven't you. The depths. The warden. "
            "The heart tree.'*\n\n"
            "*'You carry that knowledge well. The forest breathes a little easier "
            "because of what you did in there.'*\n\n"
            "He returns to his reading, content."
        )

    content = render_grid(grid, player, msg)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


async def _open_tree_city_villager(
    interaction: discord.Interaction, guild_id: int, user_id: int, player,
) -> None:
    """Tree city villager NPC — offers a bounty quest."""
    from dwarf_explorer.game.quests import get_or_refresh_bounty_pool
    import datetime as _dt_tcv
    db = await get_database(guild_id)
    _seed_tcv = ((getattr(player, "tc_forest_id", 0) or 0) * 9973
                 + _dt_tcv.date.today().toordinal())
    bounty_pool = await get_or_refresh_bounty_pool(
        db, _seed_tcv,
        village_id=0,
        village_wx=getattr(player, "world_x", 0),
        village_wy=getattr(player, "world_y", 0),
    )
    pool = bounty_pool[:1] if bounty_pool else []
    if not pool:
        from dwarf_explorer.game.renderer import render_grid
        from dwarf_explorer.world.forest import load_tree_city_viewport as _ltcv_vill
        _grid_v = await _ltcv_vill(player.tc_forest_id, player.tc_floor,
                                   player.tc_x, player.tc_y, db)
        content = render_grid(_grid_v, player,
                              "\"I have no work for you today, traveller.\"")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=_grid_v),
        )
        return
    await handle_open_quest_pool(
        interaction, guild_id, user_id,
        pool=pool,
        source_label="Tree City Villager",
        source_type="tree_city_npc",
    )


async def _open_tree_city_elder(
    interaction: discord.Interaction, guild_id: int, user_id: int, player,
) -> None:
    """Floor 4 elder NPC — single main quest: The Forest Depths (stage-driven)."""
    from dwarf_explorer.game.quests import (
        has_forest_depths_quest, create_forest_depths_quest,
        update_forest_depths_quest_target,
    )
    from dwarf_explorer.ui.quest_view import QuestOfferView, render_quest_offer
    from dwarf_explorer.world.forest import load_tree_city_viewport as _ltcv_eld, get_hermit_forest_info
    db = await get_database(guild_id)

    already_has = await has_forest_depths_quest(db, user_id)
    _stage = getattr(player, "fq_quest_stage", "none") or "none"

    grid = await _ltcv_eld(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)

    # Always resolve the hermit forest entrance and keep quests.location_x/y correct.
    # This repairs broken/missing coordinates for players who accepted before it was stored.
    _hf_info_early = await get_hermit_forest_info(db)
    if _hf_info_early is not None:
        _early_quest_id = await create_forest_depths_quest(db)
        await db.execute(
            "UPDATE quests SET location_x=?, location_y=? WHERE id=?",
            (_hf_info_early["world_x"], _hf_info_early["world_y"], _early_quest_id),
        )

    # ── Player has the quest ──────────────────────────────────────────────────
    if already_has:

        # Quest fully complete — award XP and mark done
        if _stage == "quest_complete":
            pq_row = await db.fetch_one(
                "SELECT pq.id FROM player_quests pq JOIN quests q ON pq.quest_id=q.id "
                "WHERE pq.user_id=? AND q.title='The Forest Depths' AND pq.status='active'",
                (user_id,),
            )
            if pq_row:
                await db.execute(
                    "UPDATE player_quests SET status='completed', completed_at=datetime('now') "
                    "WHERE id=?", (pq_row["id"],)
                )
                await db.execute("UPDATE players SET xp=xp+500 WHERE user_id=?", (user_id,))
                player.fq_quest_stage = "rewarded"
                await db.execute(
                    "UPDATE players SET fq_quest_stage='rewarded' WHERE user_id=?", (user_id,)
                )
                content = render_grid(
                    grid, player,
                    "🌳 *\"You have walked the depths and returned. The forest remembers.\"*\n\n"
                    "⚔️ **Quest Completed: The Forest Depths** — +500 XP\n\n"
                    "The elder nods slowly, as if this outcome was never in doubt.",
                )
            else:
                content = render_grid(
                    grid, player,
                    "🌳 *\"You have done what few dare. The forest is grateful.\"*",
                )
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        # Already rewarded
        if _stage == "rewarded":
            content = render_grid(
                grid, player,
                "🌳 *\"The forest depths hold more secrets still — but you have earned your rest.\"*",
            )
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        # Seek hermit first — player hasn't visited the hermit yet
        if _stage == "seek_hermit":
            content = render_grid(
                grid, player,
                "🌿 *\"The hermit holds the knowledge you need. Find him — "
                "the tracker will guide you to his forest. Return once you have spoken with him.\"*",
            )
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        # Hermit has been met — craft the Wayerwood
        if _stage == "hermit_met":
            alog_rows = await db.fetch_all(
                "SELECT quantity FROM inventory WHERE user_id=? AND item_id='ancient_log'", (user_id,))
            alog_count = sum(r["quantity"] for r in alog_rows)

            if alog_count >= 3:
                # Forge the Wayerwood and advance the quest stage
                await remove_from_inventory(db, user_id, "ancient_log", 3)
                await add_to_inventory(db, user_id, "wayerwood", 1)
                player.fq_quest_stage = "wayerwood_crafted"
                await db.execute(
                    "UPDATE players SET fq_quest_stage='wayerwood_crafted' WHERE user_id=?",
                    (user_id,),
                )
                content = render_grid(
                    grid, player,
                    "🪄 *\"The ancient wood yields its secret...\"*\n\n"
                    "The hermit shapes the ancient logs into a slender rod. A faint glow pulses through it.\n"
                    "You receive the **Wayerwood** 🪄 — equip it to feel the forest's pull.\n"
                    "Combine it with a **rock** to attune it for caves, or a **pinecone** for hidden chambers.\n\n"
                    "The hermit already marked the **Forest Depths entrance** on your tracker. "
                    "Head there when you are ready.",
                )
            else:
                content = render_grid(
                    grid, player,
                    f"🌿 *\"The hermit's recipe requires:\"*\n\n"
                    f"{'✅' if alog_count >= 3 else '❌'} **3 Ancient Logs** ({alog_count}/3)\n"
                    f"— chop the **Ancient Tree** inside any forest with an 🪓 axe\n\n"
                    f"Bring them and I shall craft you a Wayerwood.",
                )
            await interaction.response.edit_message(embed=_embed(content), content=None,
                                                    view=_game_view(guild_id, user_id, player, grid=grid))
            return

        # Any active in-depths stage — give a concise hint
        _hints = {
            "wayerwood_crafted": "Head to the **Forest Depths entrance** — the hermit's mark is on your tracker.",
            "map_marked":        "You're inside the Forest Depths. Push the **heavy logs** to bridge the stream.",
            "puzzle_solved":     "The stream is bridged. Press deeper — something waits beyond.",
            "warden_defeated":   "The Thornwarden is slain. Navigate the fork and **solve the canal** ahead.",
            "canal_solved":      "The canal is open. The **final chamber** awaits.",
        }
        hint = _hints.get(_stage, "Keep following the trail — the forest will show you the way.")
        content = render_grid(
            grid, player,
            f"🌳 *\"Walk carefully, traveller.\"*\n\n{hint}",
        )
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return

    # ── Offer the quest for the first time ────────────────────────────────────
    _hf_info = await get_hermit_forest_info(db)
    if _hf_info is None:
        content = render_grid(
            grid, player,
            "🌿 *\"The forest is not yet ready to reveal its secrets. Come back soon.\"*",
        )
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return

    _hf_wx, _hf_wy = _hf_info["world_x"], _hf_info["world_y"]
    quest_id = await create_forest_depths_quest(db)
    quest_row = await db.fetch_one(
        "SELECT id, quest_type, quest_subtype, title, description, target_id, target_count, "
        "reward_gold, reward_xp, reward_item FROM quests WHERE id=?",
        (quest_id,),
    )
    if not quest_row:
        return
    _ui_state[user_id] = {
        "type": "quest_offer", "quest_id": quest_id, "is_main_quest": True,
        "fq_hermit_wx": _hf_wx, "fq_hermit_wy": _hf_wy,
    }
    content = (
        "🌿 *\"Traveller — you have reached the heart of the tree. Good. "
        "There is a hermit in the distant forest who guards old knowledge: "
        "the secret of the **Wayerwood**, and the path to what lies beyond. "
        "Seek him out. The tracker will show you the way.\"*\n\n"
        + render_quest_offer(dict(quest_row), "Elder of the Grove")
    )
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=QuestOfferView(guild_id, user_id),
    )


async def _open_tree_city_shop(
    interaction: discord.Interaction, guild_id: int, user_id: int, player,
) -> None:
    """Open the Tree City market (buy-only, uses TREE_CITY_SHOP catalog)."""
    from dwarf_explorer.config import TREE_CITY_SHOP as _TCS_open
    db = await get_database(guild_id)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    _ui_state[user_id] = {"type": "tree_city_shop", "selected": 0, "shop_view": "shop",
                          "qty": 1, "tree_city_mode": True}
    content = _shop_render(_ui_state[user_id], player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop",
                                                          tree_city_mode=True))


# ══════════════════════════════════════════════════════════════════════════════
# ── Archivist / Warp Crystal handlers ────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

async def _open_tc_archivist(
    interaction: discord.Interaction, guild_id: int, user_id: int, player,
) -> None:
    """The Archivist in the Tree City (present day) — cryptic keeper of lore."""
    from dwarf_explorer.world.forest import load_tree_city_viewport as _ltcv_arch
    grid = await _ltcv_arch(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y,
                            await get_database(guild_id))
    has_crystal = getattr(player, "has_warp_crystal", False)
    if has_crystal:
        dialogue = (
            "📜 **The Archivist** sets down a hefty tome and peers at you over half-moon spectacles.\n\n"
            "*\"Ah — you've been to the grove. You carry its light now. The resonance is faint... "
            "but growing.\"*\n\n"
            "*\"Guard that crystal well. The seals are not as permanent as the Founders believed. "
            "Something stirs in the deep strata.\"*\n\n"
            "*\"If you must ask what I know — I know less than I did yesterday, "
            "and far less than I will tomorrow. Such is the price of honest scholarship.\"*"
        )
    else:
        dialogue = (
            "📜 **The Archivist** barely looks up from an enormous, ink-stained ledger.\n\n"
            "*\"Hm? A traveller. Rare, these days.\"*\n\n"
            "*\"The grove lies deeper in the forest — if the forest deigns to let you reach it. "
            "I wouldn't attempt it without knowing the paths.\"*\n\n"
            "*\"Come back when you've found something worth discussing.\"*"
        )
    content = render_grid(grid, player, dialogue)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


async def _open_rift_archivist(
    interaction: discord.Interaction, guild_id: int, user_id: int, player,
) -> None:
    """The Archivist in the Time Rift (the past) — panicked, warning of dimensional collapse."""
    db = await get_database(guild_id)
    from dwarf_explorer.world.caves import load_cave_viewport as _lcv_rift_arch
    grid = await _lcv_rift_arch(player.cave_id, player.cave_x, player.cave_y, db)
    has_crystal = getattr(player, "has_warp_crystal", False)
    if has_crystal:
        dialogue = (
            "📜 **A Frantic Scholar** clutches a stack of papers, eyes wide with recognition.\n\n"
            "*\"You — you have one! A warp crystal from the grove! But that's impossible "
            "unless... unless you already traversed the rift from a point further along "
            "the timeline—\"*\n\n"
            "*\"Don't try to explain it. Paradoxes only resolve if you stop pulling at the threads.\"*\n\n"
            "*\"Listen: the Temporal Echo you'll face — it is what remains of a Founder "
            "who tried to stop the collapse himself. He failed. That's why we're all here "
            "in this conversation.\"*\n\n"
            "*\"The crystal will help you find your way back. Don't lose it.\"*"
        )
    else:
        dialogue = (
            "📜 **A Frantic Scholar** spins around at your approach, scattering papers everywhere.\n\n"
            "*\"Stop — don't go further! The resonance field beyond that arch is unstable. "
            "The Echo has been active for— I don't even know how long.\"*\n\n"
            "*\"I'm recording everything I can before the rift collapses this section "
            "of the timeline. The Founders built this place as a failsafe, but something "
            "went wrong in the grove. Something is always going wrong in the grove.\"*\n\n"
            "*\"You need more than courage to face what lies ahead. Have you found "
            "the grove yet? The statue there holds a key.\"*"
        )
    content = render_grid(grid, player, dialogue)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=await _cave_game_view(guild_id, user_id, player, db, grid=grid))


async def _open_grove_statue(
    interaction: discord.Interaction, guild_id: int, user_id: int, player, db,
) -> None:
    """Touch the grove statue — grants the warp crystal on first contact."""
    from dwarf_explorer.world.forest import load_grove_viewport as _lgv_stat
    grid = await _lgv_stat(player.grove_id, player.grove_x, player.grove_y, db)
    has_crystal = getattr(player, "has_warp_crystal", False)
    if has_crystal:
        waypoints = await get_player_waypoints(db, user_id)
        wp_lines = "\n".join(
            f"  {WAYPOINTS[wp_id]['emoji']} **{WAYPOINTS[wp_id]['name']}** — {WAYPOINTS[wp_id]['desc']}"
            for wp_id in ("spawn", "forest", "grove") if wp_id in waypoints
        )
        msg = (
            "🗿 **The Wayerwood Statue**\n\n"
            "The crystal in your pack pulses warmly as you touch the ancient stone.\n\n"
            "Your known waypoints:\n" + wp_lines + "\n\n"
            "*Use the 🔮 Warp button in the main view to teleport between them.*"
        )
    else:
        # First time — grant the crystal
        await grant_warp_crystal(db, user_id)
        player.has_warp_crystal = True
        wp_lines = "\n".join(
            f"  {WAYPOINTS[wp_id]['emoji']} **{WAYPOINTS[wp_id]['name']}**"
            for wp_id in ("spawn", "forest", "grove")
        )
        msg = (
            "🗿 **The Wayerwood Statue**\n\n"
            "You place your hand on the moss-covered stone. A pulse of warm light "
            "travels up your arm — and in your palm appears a small, faceted crystal "
            "that hums with distant harmonics.\n\n"
            "✨ **You received a Warp Crystal!**\n\n"
            "Three waypoints have been unlocked:\n" + wp_lines + "\n\n"
            "*The 🔮 Warp button now appears in your main view.*"
        )
    content = render_grid(grid, player, msg)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


# ── WarpView ──────────────────────────────────────────────────────────────────

class WarpView(discord.ui.View):
    """Warp crystal destination selector."""

    def __init__(self, guild_id: int, user_id: int, waypoints: set[str]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        for wp_id in ("spawn", "forest", "grove"):
            if wp_id in waypoints and wp_id in WAYPOINTS:
                wp = WAYPOINTS[wp_id]
                self.add_item(discord.ui.Button(
                    style=discord.ButtonStyle.primary,
                    emoji=wp["emoji"],
                    label=wp["name"],
                    custom_id=_custom_id(guild_id, user_id, f"warp_{wp_id}"),
                    row=0,
                ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="✖ Close",
            custom_id=_custom_id(guild_id, user_id, "warp_close"),
            row=1,
        ))


async def handle_warp_open(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open the warp crystal destination list."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not getattr(player, "has_warp_crystal", False):
        await interaction.response.defer()
        return
    waypoints = await get_player_waypoints(db, user_id)
    wp_lines = "\n".join(
        f"{WAYPOINTS[wp_id]['emoji']} **{WAYPOINTS[wp_id]['name']}** — {WAYPOINTS[wp_id]['desc']}"
        for wp_id in ("spawn", "forest", "grove") if wp_id in waypoints
    ) or "*No waypoints unlocked yet.*"
    content = f"🔮 **Warp Crystal**\n\nChoose a destination:\n\n{wp_lines}"
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=WarpView(guild_id, user_id, waypoints))


async def _execute_warp(
    interaction: discord.Interaction, guild_id: int, user_id: int, waypoint_id: str
) -> None:
    """Teleport the player to a named waypoint and return to game view."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    if waypoint_id == "spawn":
        # Clear all interiors, return to overworld spawn
        await db.execute(
            "UPDATE players SET in_cave=0, cave_id=NULL, cave_x=0, cave_y=0, "
            "in_village=0, village_id=NULL, in_house=0, house_id=NULL, "
            "in_forest=0, forest_id=NULL, forest_x=0, forest_y=0, "
            "in_grove=0, grove_id=NULL, grove_x=0, grove_y=0, "
            "in_maze=0, maze_id=NULL, in_tree_city=0, tc_floor=1, tc_x=0, tc_y=0, "
            "in_sky=0, sky_id=NULL, in_ship=0, in_ocean=0, in_high_seas=0, "
            "world_x=?, world_y=? WHERE user_id=?",
            (SPAWN_X, SPAWN_Y, user_id)
        )
        player.in_cave = player.in_village = player.in_house = False
        player.in_forest = player.in_grove = player.in_maze = player.in_tree_city = False
        player.in_sky = player.in_ship = player.in_ocean = player.in_high_seas = False
        player.in_forest_quest = False
        player.fq_area_id = None
        player.fq_x = player.fq_y = 0
        player.world_x, player.world_y = SPAWN_X, SPAWN_Y
        grid = await load_viewport(SPAWN_X, SPAWN_Y, seed, db)
        msg = f"🌍 **Warp: {WAYPOINTS['spawn']['name']}**\nYou dissolve into a shimmer of light and reappear at the World's Navel."

    elif waypoint_id == "forest":
        # Warp to overworld forest entrance tile (first known entrance)
        ent = await db.fetch_one("SELECT world_x, world_y FROM forest_entrances LIMIT 1")
        if not ent:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            msg = "🔮 The crystal flickers — no forest entrance is known yet."
        else:
            wx, wy = ent["world_x"], ent["world_y"]
            await db.execute(
                "UPDATE players SET in_cave=0, cave_id=NULL, in_village=0, village_id=NULL, "
                "in_house=0, house_id=NULL, in_forest=0, forest_id=NULL, "
                "in_grove=0, grove_id=NULL, in_maze=0, maze_id=NULL, "
                "in_tree_city=0, in_sky=0, sky_id=NULL, in_ship=0, in_ocean=0, in_high_seas=0, "
                "world_x=?, world_y=? WHERE user_id=?",
                (wx, wy, user_id)
            )
            player.in_cave = player.in_village = player.in_house = False
            player.in_forest = player.in_grove = player.in_maze = player.in_tree_city = False
            player.in_sky = player.in_ship = player.in_ocean = player.in_high_seas = False
            player.in_forest_quest = False
            player.fq_area_id = None
            player.fq_x = player.fq_y = 0
            player.world_x, player.world_y = wx, wy
            grid = await load_viewport(wx, wy, seed, db)
            msg = f"🌲 **Warp: {WAYPOINTS['forest']['name']}**\nYou step through a curtain of light and arrive at the forest's edge."

    elif waypoint_id == "grove":
        # Warp directly into the grove interior (near statue)
        grove_forest_id = player.grove_forest_id
        grove_id = player.grove_id
        if not grove_id:
            # Try to look it up from DB
            g_row = await db.fetch_one(
                "SELECT grove_id, forest_id FROM grove_areas LIMIT 1"
            )
            if g_row:
                grove_id = g_row["grove_id"]
                grove_forest_id = g_row["forest_id"]
        if not grove_id:
            grid = await load_viewport(player.world_x, player.world_y, seed, db)
            msg = "🔮 The crystal flickers — no grove has been discovered yet."
        else:
            gx, gy = 9, 10   # just south of centre statue
            # Preserve forest_x/y so exit-grove returns to the right forest tile
            fx = player.forest_x or 0
            fy = player.forest_y or 0
            await db.execute(
                "UPDATE players SET in_cave=0, cave_id=NULL, in_village=0, village_id=NULL, "
                "in_house=0, house_id=NULL, in_forest=1, forest_id=?, forest_x=?, forest_y=?, "
                "in_grove=1, grove_id=?, grove_x=?, grove_y=?, grove_forest_id=?, "
                "in_maze=0, maze_id=NULL, in_tree_city=0, in_sky=0, sky_id=NULL, "
                "in_ship=0, in_ocean=0, in_high_seas=0 WHERE user_id=?",
                (grove_forest_id, fx, fy, grove_id, gx, gy, grove_forest_id, user_id)
            )
            player.in_cave = player.in_village = player.in_house = False
            player.in_forest = True
            player.forest_id = grove_forest_id
            player.forest_x = fx
            player.forest_y = fy
            player.in_grove = True
            player.grove_id = grove_id
            player.grove_x, player.grove_y = gx, gy
            player.grove_forest_id = grove_forest_id
            player.in_maze = player.in_tree_city = False
            player.in_sky = player.in_ship = player.in_ocean = player.in_high_seas = False
            from dwarf_explorer.world.forest import load_grove_viewport as _lgv_warp
            grid = await _lgv_warp(grove_id, gx, gy, db)
            msg = f"✨ **Warp: {WAYPOINTS['grove']['name']}**\nThe crystal sings and the grove unfolds around you."
    else:
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        msg = "🔮 Unknown destination."

    content = render_grid(grid, player, msg)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_warp_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Close the warp view and return to game."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await _cached_grid(user_id, player, seed, db)
    if player.in_cave:
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    else:
        view = _game_view(guild_id, user_id, player, grid=grid)
    content = render_grid(grid, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


class NavView(discord.ui.View):
    """Navigation overlay: World Map | Warp (if crystal) | Forest Map (if unlocked) | Close."""

    def __init__(self, guild_id: int, user_id: int, has_warp_crystal: bool = False,
                 has_forest_map: bool = False):
        super().__init__(timeout=None)
        map_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Map", emoji="\U0001F5FA️",
            custom_id=_custom_id(guild_id, user_id, "map"),
            row=0,
        )
        self.add_item(map_btn)
        if has_warp_crystal:
            warp_btn = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Warp", emoji="\U0001F52E",
                custom_id=_custom_id(guild_id, user_id, "warp_open"),
                row=0,
            )
            self.add_item(warp_btn)
        if has_forest_map:
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Forest Map", emoji="🌲",
                custom_id=_custom_id(guild_id, user_id, "forest_map"),
                row=0,
            ))
        close_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="✖ Close",
            custom_id=_custom_id(guild_id, user_id, "nav_close"),
            row=0,
        )
        self.add_item(close_btn)


class MapCloseView(discord.ui.View):
    """Attached to the standalone map message so the player can close it."""

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="✖ Close Map",
            custom_id=_custom_id(guild_id, user_id, "map_close"),
            row=0,
        ))


async def _fetch_or_cache_avatar(
    db, guild, user_id: int, size: int = 32
) -> bytes | None:
    """Return avatar PNG bytes for *user_id*, using DB cache (24 h TTL).

    Checks the avatar_cache table first.  On a miss or a stale entry, fetches
    from Discord, stores the fresh bytes, then returns them.  Never raises —
    returns None on any failure.
    """
    cached = await get_avatar_cache(db, user_id)
    if cached is not None:
        return cached
    try:
        member = guild.get_member(user_id) or await guild.fetch_member(user_id)
        asset = member.guild_avatar or member.avatar
        if asset:
            data = await asset.with_size(size).read()
            await store_avatar_cache(db, user_id, data)
            return data
    except Exception:
        pass
    return None


async def handle_nav_open(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Show the navigation overlay with map/warp/forest map buttons."""
    await interaction.response.defer()
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    has_crystal = getattr(player, "has_warp_crystal", False)
    has_forest_map = False
    if player.in_forest and player.forest_id:
        _fmap = await db.fetch_one(
            "SELECT 1 FROM player_map_collection WHERE user_id=? AND map_type='forest' AND ref_id=?",
            (user_id, player.forest_id)
        )
        has_forest_map = (_fmap is not None)
    view = NavView(guild_id, user_id, has_warp_crystal=has_crystal, has_forest_map=has_forest_map)
    await interaction.edit_original_response(content=None, embed=None, attachments=[], view=view)


async def handle_forest_map(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Render the current forest interior as a PIL image with key, avatars, and icons."""
    await interaction.response.defer()
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not player.in_forest or not player.forest_id:
        await interaction.edit_original_response(
            content="📍 You're not currently in a forest.", embed=None, attachments=[], view=None
        )
        return
    tiles = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM forest_tiles WHERE forest_id=?",
        (player.forest_id,)
    )
    if not tiles:
        await interaction.edit_original_response(
            content="🗺️ Forest map data not available.", embed=None, attachments=[], view=None
        )
        return

    import io
    from PIL import Image, ImageDraw, ImageFont
    from dwarf_explorer.world.forest import FOREST_W, FOREST_H
    from dwarf_explorer.world.world_map import _draw_icon, _paste_avatar

    SCALE = 4
    MAP_W = FOREST_W * SCALE   # 480 px
    MAP_H = FOREST_H * SCALE   # 480 px

    # ── Legend / key layout ───────────────────────────────────────────────────
    # Legend is placed ABOVE the map. Each entry is a swatch + label.
    _TREE_COL   = (10, 80, 20)       # same as dense_forest in TILE_COLORS
    _FLOOR_COL  = (80, 160, 60)      # lighter green for walkable paths
    _CHEST_COL  = (200, 170, 50)
    _NUT_COL    = (60, 130, 40)
    _ANC_COL    = (20, 200, 120)
    _CITY_COL   = (220, 140, 30)
    _EXIT_COL   = (50, 200, 80)
    _MAZE_COL   = (150, 50, 200)
    _SELF_COL   = (255, 50, 50)
    _OTHER_COL  = (60, 120, 255)

    # (label, color, style)  — style "square" = filled rect; others match _draw_icon
    _LEGEND = [
        ("Tree Wall",    _TREE_COL,  "square"),
        ("Forest Path",  _FLOOR_COL, "square"),
        ("Chest",        _CHEST_COL, "filled_diamond"),
        ("Nut Tree",     _NUT_COL,   "filled_circle"),
        ("Ancient Tree", _ANC_COL,   "filled_circle"),
        ("Tree City",    _CITY_COL,  "filled_diamond"),
        ("Exit",         _EXIT_COL,  "filled_triangle"),
        ("Maze Door",    _MAZE_COL,  "filled_diamond"),
        ("You",          _SELF_COL,  "dot_red"),
        ("Other Player", _OTHER_COL, "dot_blue"),
    ]
    _SW   = 14   # swatch width/height px
    _ROW_H = 18  # px per legend row
    _COL_W = 110 # px per legend column
    _COLS  = 5   # legend columns
    _MARGIN = 6
    _LEGEND_H = _MARGIN * 2 + (_ROW_H * ((len(_LEGEND) + _COLS - 1) // _COLS))
    TOTAL_H = _LEGEND_H + MAP_H

    img = Image.new("RGB", (MAP_W, TOTAL_H), (20, 20, 20))  # dark bg for legend area
    draw = ImageDraw.Draw(img)

    # Draw legend header
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        font = ImageFont.load_default()

    for i, (label, color, style) in enumerate(_LEGEND):
        col = i % _COLS
        row = i // _COLS
        x0 = _MARGIN + col * _COL_W
        y0 = _MARGIN + row * _ROW_H
        cx = x0 + _SW // 2
        cy = y0 + _SW // 2
        if style == "square":
            draw.rectangle([x0, y0, x0 + _SW - 1, y0 + _SW - 1], fill=color, outline=(180, 180, 180))
        elif style in ("dot_red", "dot_blue"):
            draw.ellipse([x0 + 1, y0 + 1, x0 + _SW - 2, y0 + _SW - 2], fill=color, outline=(255, 255, 255))
        else:
            draw.rectangle([x0, y0, x0 + _SW - 1, y0 + _SW - 1], fill=(30, 30, 30))
            _draw_icon(draw, cx, cy, style, color, r=5)
        draw.text((x0 + _SW + 3, y0 + (_SW - 10) // 2), label, fill=(210, 210, 210), font=font)

    # ── Render map tiles (offset below legend) ────────────────────────────────
    OFFSET_Y = _LEGEND_H   # map starts after legend

    # Background = tree wall color
    draw.rectangle([0, OFFSET_Y, MAP_W - 1, TOTAL_H - 1], fill=_TREE_COL)

    # Special tile types that draw as plain filled rectangles
    RECT_TILES = {
        "fst_floor": _FLOOR_COL,
    }
    # Icon tiles — drawn as icons on top of the floor/tree base
    ICON_TILES = {
        "fst_chest":        (_CHEST_COL, "filled_diamond"),
        "fst_map_chest":    (_CHEST_COL, "filled_diamond"),
        "fst_nut_tree":     (_NUT_COL,   "filled_circle"),
        "fst_ancient_tree": (_ANC_COL,   "filled_circle"),
        "fst_tree_city":    (_CITY_COL,  "filled_diamond"),
        "fst_exit":         (_EXIT_COL,  "filled_triangle"),
        "fst_maze_door":    (_MAZE_COL,  "filled_diamond"),
    }

    for tile in tiles:
        tx, ty, tt = tile["local_x"], tile["local_y"], tile["tile_type"]
        px0 = tx * SCALE
        py0 = ty * SCALE + OFFSET_Y
        px1 = px0 + SCALE - 1
        py1 = py0 + SCALE - 1
        if tt in RECT_TILES:
            draw.rectangle([px0, py0, px1, py1], fill=RECT_TILES[tt])
        elif tt in ICON_TILES:
            # Draw floor background under icon
            draw.rectangle([px0, py0, px1, py1], fill=_FLOOR_COL)
            ic, ist = ICON_TILES[tt]
            cx = tx * SCALE + SCALE // 2
            cy = ty * SCALE + SCALE // 2 + OFFSET_Y
            _draw_icon(draw, cx, cy, ist, ic, r=SCALE)

    # ── Fetch other forest players ────────────────────────────────────────────
    other_rows = await db.fetch_all(
        "SELECT user_id, forest_x, forest_y FROM players "
        "WHERE in_forest=1 AND forest_id=? AND user_id!=?",
        (player.forest_id, user_id),
    )

    # ── Fetch avatars ─────────────────────────────────────────────────────────
    player_avatar = await _fetch_or_cache_avatar(db, interaction.guild, user_id)
    other_avatars: list[bytes | None] = [
        await _fetch_or_cache_avatar(db, interaction.guild, r["user_id"]) for r in other_rows
    ]

    # ── Draw other players (blue) ─────────────────────────────────────────────
    for i, row in enumerate(other_rows):
        cx = row["forest_x"] * SCALE + SCALE // 2
        cy = row["forest_y"] * SCALE + SCALE // 2 + OFFSET_Y
        av = other_avatars[i] if i < len(other_avatars) else None
        if av:
            img = _paste_avatar(img, av, cx, cy, 16, _OTHER_COL)
            draw = ImageDraw.Draw(img)
        else:
            draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=_OTHER_COL, outline=(255, 255, 255))

    # ── Draw current player (red) ─────────────────────────────────────────────
    cx_p = player.forest_x * SCALE + SCALE // 2
    cy_p = player.forest_y * SCALE + SCALE // 2 + OFFSET_Y
    if player_avatar:
        img = _paste_avatar(img, player_avatar, cx_p, cy_p, 20, _SELF_COL)
        draw = ImageDraw.Draw(img)
    else:
        draw.ellipse([cx_p - 5, cy_p - 5, cx_p + 5, cy_p + 5], fill=_SELF_COL, outline=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    file = discord.File(buf, filename="forest_map.png")
    has_crystal = getattr(player, "has_warp_crystal", False)
    view = NavView(guild_id, user_id, has_warp_crystal=has_crystal, has_forest_map=True)
    await interaction.edit_original_response(
        content=None, embed=None, attachments=[file], view=view
    )


async def handle_nav_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Close navigation overlay and return to game view."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await _cached_grid(user_id, player, seed, db)
    if player.in_cave:
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    else:
        view = _game_view(guild_id, user_id, player, grid=grid)
    _nav = _ui_state.get(user_id, {}).get("nav_target")
    content = render_grid(grid, player, nav_target=_nav)
    # attachments=[] clears the map image that was set by handle_nav_open / handle_map
    await interaction.response.edit_message(
        embed=_embed(content), content=None, attachments=[], view=view
    )


def _shop_nav_bounds(state: dict, player_items: list, inv_rows: int = 1, inv_cols: int = 7) -> int:
    """Return total navigable slots in current shop view."""
    view_mode = state.get("shop_view", "shop")
    if view_mode == "player":
        # Use full grid slot count so up/down steps of inv_cols land on the right row
        return max(1, inv_rows * inv_cols)
    else:
        cols = 7
        catalog = _get_shop_catalog(state)
        cat_len = max(1, len(catalog))
        # Round up to full rows so wrapping aligns with the rendered grid
        return ((cat_len + cols - 1) // cols) * cols


async def _shop_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    delta_col: int = 0, delta_row: int = 0,
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    sel = state.get("selected", 0)
    total = _shop_nav_bounds(state, player_items, inv_rows, inv_cols)
    cols = inv_cols if state.get("shop_view") == "player" else 7
    new_sel = (sel + delta_col + delta_row * cols) % total
    # Apply canoe-pair cursor skip when navigating the player's inventory view
    if state.get("shop_view") == "player":
        from dwarf_explorer.game.renderer import _build_slot_map as _bsm
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map_nav = _bsm(visible, total, cols)
        new_sel = _canoe_nav_adjust(slot_map_nav, sel, new_sel, total, cols, delta_col)
    new_state = {**state, "selected": new_sel, "qty": 1}  # reset qty on nav
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, new_state.get("shop_view", "shop"),
                                                          farmer_mode=bool(new_state.get("farmer_mode")),
                                                          tavern_mode=bool(new_state.get("tavern_mode")),
                                                          tree_city_mode=bool(new_state.get("tree_city_mode")),
                                                          armory_mode=bool(new_state.get("armory_mode"))))


async def handle_shop_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    await _shop_nav(interaction, guild_id, user_id, delta_col=delta)


async def handle_shop_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _shop_nav(interaction, guild_id, user_id, delta_row=-1)


async def handle_shop_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _shop_nav(interaction, guild_id, user_id, delta_row=1)


async def handle_shop_qty_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    _catalog = _get_shop_catalog(state)
    if view_mode == "shop" and sel < len(_catalog):
        max_qty = max(1, player.gold // max(1, _catalog[sel]["price"]))
        new_qty = (qty % max_qty) + 1
    elif view_mode == "player":
        from dwarf_explorer.game.renderer import _build_slot_map
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        new_qty = ((qty % max(1, item["quantity"])) + 1) if item else 1
    else:
        new_qty = qty
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, view_mode,
                                                          farmer_mode=bool(state.get("farmer_mode")),
                                                          tavern_mode=bool(state.get("tavern_mode")),
                                                          tree_city_mode=bool(state.get("tree_city_mode")),
                                                          armory_mode=bool(state.get("armory_mode"))))


async def handle_shop_qty_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    _catalog = _get_shop_catalog(state)
    if view_mode == "shop" and sel < len(_catalog):
        max_qty = max(1, player.gold // max(1, _catalog[sel]["price"]))
        new_qty = max_qty if qty <= 1 else qty - 1
    elif view_mode == "player":
        from dwarf_explorer.game.renderer import _build_slot_map
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
        new_qty = max_qty if qty <= 1 else qty - 1
    else:
        new_qty = qty
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, view_mode,
                                                          farmer_mode=bool(state.get("farmer_mode")),
                                                          tavern_mode=bool(state.get("tavern_mode")),
                                                          tree_city_mode=bool(state.get("tree_city_mode")),
                                                          armory_mode=bool(state.get("armory_mode"))))


async def handle_shop_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    _farmer = bool(state.get("farmer_mode"))
    _tavern = bool(state.get("tavern_mode"))
    _tree_city = bool(state.get("tree_city_mode"))
    _armory = bool(state.get("armory_mode"))
    _catalog = _get_shop_catalog(state)
    _sv_kwargs = dict(farmer_mode=_farmer, tavern_mode=_tavern, tree_city_mode=_tree_city,
                      armory_mode=_armory)
    if sel >= len(_catalog):
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols)
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "shop", **_sv_kwargs))
        return
    item = _catalog[sel]
    total_cost = item["price"] * qty
    if user_id != ADMIN_PLAYER_ID and player.gold < total_cost:
        suffix = f"\n*Not enough gold! Need {total_cost}g for ×{qty}.*"
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "shop", **_sv_kwargs))
        return
    if user_id != ADMIN_PLAYER_ID:
        player.gold -= total_cost
        await update_player_stats(db, user_id, gold=player.gold)
    await add_to_inventory(db, user_id, item["id"], qty)
    # Watering can arrives empty — player must fill it at a water source.
    if item["id"] == "watering_can":
        await db.execute("UPDATE players SET watering_can_uses=0 WHERE user_id=?", (user_id,))
    player_items = await get_inventory(db, user_id)
    suffix = f"\n*Purchased {qty}× {item['name']} for {total_cost}g!*"
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "shop", **_sv_kwargs))


async def handle_shop_sell(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "player", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    from dwarf_explorer.game.renderer import _build_slot_map
    visible = [it for it in player_items if it["item_id"] != "gold_coin"]
    slot_map = _build_slot_map(visible, inv_rows * inv_cols)
    item = slot_map.get(sel)
    if item is None:
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols) + "\n*(No item at cursor)*"
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "player"))
        return
    item_id = item["item_id"]
    price = ITEM_SELL_PRICES.get(item_id, 0)
    if price == 0:
        suffix = f"\n*The shop won't buy {item_id.replace('_', ' ').title()}.*"
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "player"))
        return
    actual_qty = min(qty, item["quantity"])
    await remove_from_inventory(db, user_id, item_id, actual_qty)
    earned = price * actual_qty
    _apply_gold_cap(player, earned)
    await update_player_stats(db, user_id, gold=player.gold)
    player_items = await get_inventory(db, user_id)
    suffix = f"\n*Sold {actual_qty}× {item_id.replace('_', ' ').title()} for {earned}g!*"
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, "player"))


async def handle_shop_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Switch between shop catalog and player inventory. No-op in farmer_mode."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop"})
    # Buy-only shops have no sell tab — treat switch as a no-op
    if state.get("farmer_mode") or state.get("tavern_mode") or state.get("tree_city_mode") or state.get("armory_mode"):
        _sv_kwargs = dict(farmer_mode=bool(state.get("farmer_mode")),
                          tavern_mode=bool(state.get("tavern_mode")),
                          tree_city_mode=bool(state.get("tree_city_mode")),
                          armory_mode=bool(state.get("armory_mode")))
        content = _shop_render(state, player_items, equipped, player.gold, inv_rows, inv_cols)
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=ShopView(guild_id, user_id, "shop", **_sv_kwargs))
        return
    new_view = "player" if state.get("shop_view", "shop") == "shop" else "shop"
    new_state = {"type": "shop", "selected": 0, "shop_view": new_view, "qty": 1}
    _ui_state[user_id] = new_state
    content = _shop_render(new_state, player_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ShopView(guild_id, user_id, new_view))


# handle_shop_mode kept for backward compatibility (old buttons may still trigger it)
async def handle_shop_mode(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_shop_switch(interaction, guild_id, user_id)


async def handle_shop_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Bank helpers ──────────────────────────────────────────────────────────────

def _bank_render(state: dict, player_items: list, bank_items: list,
                 equipped: dict, player_gold: int,
                 inv_rows: int, inv_cols: int) -> str:
    """Build bank content string from current state."""
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)
    return render_bank(player_items, bank_items, sel, bv, equipped,
                       inv_rows, inv_cols, gold=player_gold, qty=qty,
                       cursor_mode=cursor_mode, equipped_cursor=equipped_cursor)


# ── Bank handlers ─────────────────────────────────────────────────────────────

async def _open_bank(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player: Player, db,
) -> None:
    _ui_state[user_id] = {
        "type": "bank", "selected": 0, "bank_view": "player", "qty": 1,
        "cursor_mode": "inventory", "equipped_cursor": 0,
    }
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content = _bank_render(_ui_state[user_id], player_items, bank_items,
                           equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "player"))


async def _bank_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    delta_col: int = 0, delta_row: int = 0,
) -> None:
    """Navigate bank cursor with full cursor_mode support (gold → equipped → inventory)."""
    from dwarf_explorer.game.renderer import _EQUIP_SLOT_ORDER as _ESO
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1,
                                     "cursor_mode": "inventory", "equipped_cursor": 0})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    cursor_mode = state.get("cursor_mode", "inventory")
    eq_cur = state.get("equipped_cursor", 0)

    from dwarf_explorer.game.renderer import _build_slot_map as _bsm
    if bv == "player":
        cols = inv_cols
        total = max(1, inv_rows * inv_cols)
        visible_p = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map_nav = _bsm(visible_p, total, inv_cols)
        prev_sel = sel
        if delta_row < 0:   # UP
            if cursor_mode == "inventory" and sel < cols:
                cursor_mode = "equipped"
                eq_cur = min(eq_cur, len(_ESO) - 1)
            elif cursor_mode == "inventory":
                sel = (sel - cols) % total
            elif cursor_mode == "equipped":
                cursor_mode = "gold"
        elif delta_row > 0:  # DOWN
            if cursor_mode == "gold":
                cursor_mode = "equipped"
            elif cursor_mode == "equipped":
                cursor_mode = "inventory"
                sel = 0
            else:
                sel = min(sel + cols, total - 1)
        else:  # LEFT/RIGHT
            if cursor_mode == "equipped":
                eq_cur = (eq_cur + delta_col) % len(_ESO)
            elif cursor_mode == "inventory":
                new_sel = sel + delta_col
                if 0 <= new_sel < total:
                    sel = new_sel
                else:
                    sel = new_sel % total
        if cursor_mode == "inventory":
            sel = _canoe_nav_adjust(slot_map_nav, prev_sel, sel, total, cols, delta_col)
    else:
        # Bank vault — grid nav with gold row above
        bank_gold = next((it["quantity"] for it in bank_items if it["item_id"] == "gold_coin"), 0)
        cols = 7
        vault_total = 9 * 7  # 63 slots (9×7)
        vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
        slot_map_nav = _bsm(vault_items, vault_total, cols)
        prev_sel = sel
        if cursor_mode == "gold":
            if delta_row > 0:
                cursor_mode = "inventory"
                sel = 0
        else:
            cursor_mode = "inventory"
            if delta_row < 0 and sel < cols and bank_gold > 0:
                cursor_mode = "gold"
            elif delta_row < 0:
                sel = (sel - cols) % vault_total
            elif delta_row > 0:
                sel = (sel + cols) % vault_total
            else:
                sel = (sel + delta_col) % vault_total
        if cursor_mode == "inventory":
            sel = _canoe_nav_adjust(slot_map_nav, prev_sel, sel, vault_total, cols, delta_col)

    new_state = {**state, "selected": sel, "qty": 1, "cursor_mode": cursor_mode,
                 "equipped_cursor": eq_cur}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, bv))


async def handle_bank_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    await _bank_nav(interaction, guild_id, user_id, delta_col=delta)


async def handle_bank_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _bank_nav(interaction, guild_id, user_id, delta_row=-1)


async def handle_bank_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await _bank_nav(interaction, guild_id, user_id, delta_row=1)


async def handle_bank_qty_inc(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    cursor_mode = state.get("cursor_mode", "inventory")
    from dwarf_explorer.game.renderer import _build_slot_map
    if bv == "bank":
        if cursor_mode == "gold":
            bank_gold = next((it["quantity"] for it in bank_items if it["item_id"] == "gold_coin"), 0)
            cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
            remaining_cap = max(0, cap - player.gold)
            max_qty = max(1, min(bank_gold, remaining_cap))
        else:
            vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
            slot_map = _build_slot_map(vault_items, 9 * 7)
            item = slot_map.get(sel)
            max_qty = item["quantity"] if item else 1
    elif cursor_mode == "gold":
        max_qty = max(player.gold, 1)
    else:
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    new_qty = (qty % max_qty) + 1
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, bv))


async def handle_bank_qty_dec(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    qty = state.get("qty", 1)
    cursor_mode = state.get("cursor_mode", "inventory")
    from dwarf_explorer.game.renderer import _build_slot_map
    if bv == "bank":
        if cursor_mode == "gold":
            bank_gold = next((it["quantity"] for it in bank_items if it["item_id"] == "gold_coin"), 0)
            cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
            remaining_cap = max(0, cap - player.gold)
            max_qty = max(1, min(bank_gold, remaining_cap))
        else:
            vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
            slot_map = _build_slot_map(vault_items, 9 * 7)
            item = slot_map.get(sel)
            max_qty = item["quantity"] if item else 1
    elif cursor_mode == "gold":
        max_qty = max(player.gold, 1)
    else:
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    new_qty = max_qty if qty <= 1 else qty - 1
    new_state = {**state, "qty": new_qty}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, bv))


async def handle_bank_qty_modal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open a modal to enter a custom quantity for bank deposit/withdraw."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    bv = state.get("bank_view", "player")
    sel = state.get("selected", 0)
    cursor_mode = state.get("cursor_mode", "inventory")
    from dwarf_explorer.game.renderer import _build_slot_map
    inv_rows, inv_cols = _inv_capacity(player)
    if bv == "bank":
        if cursor_mode == "gold":
            bank_gold = next((it["quantity"] for it in bank_items if it["item_id"] == "gold_coin"), 0)
            cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
            remaining_cap = max(0, cap - player.gold)
            max_qty = max(1, min(bank_gold, remaining_cap))
        else:
            vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
            slot_map = _build_slot_map(vault_items, 9 * 7)
            item = slot_map.get(sel)
            max_qty = item["quantity"] if item else 1
    elif cursor_mode == "gold":
        max_qty = max(player.gold, 1)
    else:
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    await interaction.response.send_modal(InvQtyModal(guild_id, user_id, "bank", max_qty))


async def handle_shop_qty_modal(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open a modal to enter a custom quantity for shop buy/sell."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    state = _ui_state.get(user_id, {"selected": 0, "shop_view": "shop", "qty": 1})
    view_mode = state.get("shop_view", "shop")
    sel = state.get("selected", 0)
    inv_rows, inv_cols = _inv_capacity(player)
    _catalog_modal = _get_shop_catalog(state)
    if view_mode == "shop" and sel < len(_catalog_modal):
        max_qty = max(1, player.gold // max(1, _catalog_modal[sel]["price"]))
    elif view_mode == "player":
        from dwarf_explorer.game.renderer import _build_slot_map
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        max_qty = item["quantity"] if item else 1
    else:
        max_qty = 1
    await interaction.response.send_modal(InvQtyModal(guild_id, user_id, "shop", max_qty))


async def handle_bank_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player"})
    new_view = "bank" if state.get("bank_view") == "player" else "player"
    new_state = {"type": "bank", "selected": 0, "bank_view": new_view, "qty": 1,
                 "cursor_mode": "inventory", "equipped_cursor": 0}
    _ui_state[user_id] = new_state
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, new_view))


async def handle_bank_deposit(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "player", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    cursor_mode = state.get("cursor_mode", "inventory")
    equipped_cursor = state.get("equipped_cursor", 0)
    player_items = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    from dwarf_explorer.game.renderer import _build_slot_map, _EQUIP_SLOT_ORDER as _ESO

    suffix = "\n*Deposit failed.*"

    if cursor_mode == "gold":
        # Deposit gold: deduct from players.gold, add to bank_items
        actual_qty = min(qty, player.gold)
        if actual_qty > 0:
            await db.execute("UPDATE players SET gold=gold-? WHERE user_id=?",
                             (actual_qty, user_id))
            await db.execute(
                "INSERT INTO bank_items(user_id, item_id, quantity) VALUES(?,'gold_coin',?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity=quantity+?",
                (user_id, actual_qty, actual_qty),
            )
            suffix = f"\n*Deposited {actual_qty}g into bank.*"
        else:
            suffix = "\n*(No gold to deposit)*"

    elif cursor_mode == "equipped":
        # Deposit equipped item: unequip it first, then bank_deposit
        if equipped_cursor < len(_ESO):
            slot, _ = _ESO[equipped_cursor]
            item_id = equipped.get(slot)
            if item_id:
                from dwarf_explorer.database.repositories import unequip_item as _unequip_item
                await _unequip_item(db, user_id, slot)
                await add_to_inventory(db, user_id, item_id, 1)
                player_items = await get_inventory(db, user_id)
                ok = await bank_deposit(db, user_id, item_id, 1)
                suffix = f"\n*Unequipped and deposited {item_id.replace('_', ' ').title()}.*" if ok else "\n*Deposit failed.*"
            else:
                suffix = "\n*(No item equipped in that slot)*"
        else:
            suffix = "\n*(No item at cursor)*"

    else:
        # Normal inventory deposit — remove from the exact cursor slot (not LIFO)
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        slot_map = _build_slot_map(visible, inv_rows * inv_cols)
        item = slot_map.get(sel)
        # Resolve canoe virtual halves back to the real DB row
        if item is not None and item.get("_canoe_origin") is not None:
            origin = item["_canoe_origin"]
            item = next((it for it in visible if it["item_id"] == "canoe" and it["slot_index"] == origin), item)
        if item is None:
            suffix = "\n*(Empty slot)*"
        elif item["item_id"] == "canoe":
            ok = await bank_deposit(db, user_id, "canoe", 1)
            suffix = "\n*Deposited 1× Canoe.*" if ok else "\n*Deposit failed.*"
        else:
            actual_qty = min(qty, item["quantity"])
            # Find the exact inventory row for this slot and remove directly
            inv_row = await db.fetch_one(
                "SELECT id, quantity FROM inventory WHERE user_id=? AND slot_index=?",
                (user_id, item["slot_index"]),
            )
            if inv_row:
                if inv_row["quantity"] <= actual_qty:
                    await db.execute("DELETE FROM inventory WHERE id=?", (inv_row["id"],))
                else:
                    await db.execute(
                        "UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                        (actual_qty, inv_row["id"]),
                    )
                # Add to bank (single-row-per-item, no stack limit in storage)
                await db.execute(
                    "INSERT INTO bank_items(user_id, item_id, quantity) VALUES(?,?,?) "
                    "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
                    (user_id, item["item_id"], actual_qty, actual_qty),
                )
                suffix = f"\n*Deposited {actual_qty}× {item['item_id'].replace('_', ' ')}.*"
            else:
                suffix = "\n*Deposit failed.*"

    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    inv_rows, inv_cols = _inv_capacity(player)
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "player"))


async def handle_bank_withdraw(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {"selected": 0, "bank_view": "bank", "qty": 1})
    sel = state.get("selected", 0)
    qty = max(1, state.get("qty", 1))
    cursor_mode = state.get("cursor_mode", "inventory")
    bank_items = await get_bank_items(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    player_items = await get_inventory(db, user_id)
    equipped = _equipped_dict(player)

    # ── Gold withdrawal ────────────────────────────────────────────────────────
    if cursor_mode == "gold":
        bank_gold_row = await db.fetch_one(
            "SELECT quantity FROM bank_items WHERE user_id=? AND item_id='gold_coin'", (user_id,)
        )
        bank_gold = bank_gold_row["quantity"] if bank_gold_row else 0
        cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
        remaining_cap = max(0, cap - player.gold)
        actual_qty = min(qty, bank_gold, remaining_cap)
        if actual_qty > 0:
            new_bank = bank_gold - actual_qty
            if new_bank <= 0:
                await db.execute(
                    "DELETE FROM bank_items WHERE user_id=? AND item_id='gold_coin'", (user_id,)
                )
            else:
                await db.execute(
                    "UPDATE bank_items SET quantity=? WHERE user_id=? AND item_id='gold_coin'",
                    (new_bank, user_id),
                )
            await db.execute("UPDATE players SET gold=gold+? WHERE user_id=?", (actual_qty, user_id))
            player = await get_or_create_player(db, user_id, interaction.user.display_name)
            suffix = f"\n*Withdrew {actual_qty}g from bank.*"
            if actual_qty < qty:
                suffix += f" *(purse holds {cap}g max)*"
        elif remaining_cap <= 0:
            suffix = "\n*(Purse is full — can't hold more gold)*"
        else:
            suffix = "\n*(No gold in bank)*"
        bank_items_new = await get_bank_items(db, user_id)
        new_state = {**state, "qty": 1}
        _ui_state[user_id] = new_state
        content = _bank_render(new_state, player_items, bank_items_new, equipped, player.gold, inv_rows, inv_cols) + suffix
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=BankView(guild_id, user_id, "bank"))
        return

    # ── Item withdrawal ────────────────────────────────────────────────────────
    from dwarf_explorer.game.renderer import _build_slot_map
    vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
    slot_map = _build_slot_map(vault_items, 9 * 7)
    item = slot_map.get(sel)
    if item is None:
        suffix = "\n*(Empty slot)*"
        content = _bank_render(state, player_items, bank_items, equipped, player.gold, inv_rows, inv_cols) + suffix
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=BankView(guild_id, user_id, "bank"))
        return
    # Resolve canoe virtual halves to the real 'canoe' item entry
    if item.get("_canoe_origin") is not None:
        item = next((it for it in vault_items if it["item_id"] == "canoe" and it["slot_index"] == item["_canoe_origin"]), item)
    actual_qty = min(qty, item["quantity"])
    cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
    ok = await bank_withdraw(db, user_id, item["item_id"], actual_qty, gold_cap=cap)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    player_items = await get_inventory(db, user_id)
    bank_items_new = await get_bank_items(db, user_id)
    equipped = _equipped_dict(player)
    if ok:
        if item["item_id"] == "canoe":
            suffix = f"\n*Withdrew {actual_qty}× Canoe.*"
        else:
            suffix = f"\n*Withdrew {actual_qty}× {item['item_id'].replace('_', ' ')}.*"
    else:
        suffix = "\n*Withdraw failed.*"
    new_state = {**state, "qty": 1}
    _ui_state[user_id] = new_state
    content = _bank_render(new_state, player_items, bank_items_new, equipped, player.gold, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=BankView(guild_id, user_id, "bank"))


async def handle_bank_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Chest handlers ────────────────────────────────────────────────────────────

async def _render_chest_state(
    db, user_id: int, player, state: dict,
) -> tuple[str, ChestView]:
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    view_mode = state.get("chest_view", "chest")
    sel = state.get("selected", 0)
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_chest(chest_inv, player_inv, sel, view_mode,
                           chest_type, inv_rows, inv_cols)
    view = ChestView(player.channel_id or 0, user_id, view_mode)
    # Rebuild view with correct guild_id from state if available
    return content, view


async def _load_chest(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> tuple | None:
    state = _ui_state.get(user_id, {})
    if state.get("type") != "chest":
        await handle_inv_close(interaction, guild_id, user_id)
        return None
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    return db, player, state


async def handle_chest_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    view_mode = state.get("chest_view", "chest")
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    if view_mode == "chest":
        chest_inv = await get_chest_items(db, chest_id)
        source_len = len(chest_inv)
        from dwarf_explorer.game.renderer import render_chest as _rc
        chest_sizes = {
            "cave_chest": (2,9), "cave_chest_medium": (3,9), "cave_chest_large": (4,9),
            "ph_chest_small": (2,9), "ph_chest_medium": (3,9), "ph_chest_large": (4,9),
        }
        c_rows, c_cols = chest_sizes.get(chest_type, (2, 9))
        total = c_rows * c_cols
    else:
        player_inv = await get_inventory(db, user_id)
        source_len = len(player_inv)
        inv_rows, inv_cols = _inv_capacity(player)
        total = inv_rows * inv_cols
    new_sel = (state["selected"] + delta) % max(1, total)
    _ui_state[user_id]["selected"] = new_sel
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_chest(chest_inv, player_inv, new_sel, view_mode,
                           chest_type, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, view_mode))


async def handle_chest_switch(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    new_view = "chest" if state.get("chest_view") == "player" else "player"
    _ui_state[user_id]["chest_view"] = new_view
    _ui_state[user_id]["selected"] = 0
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    content = render_chest(chest_inv, player_inv, 0, new_view,
                           chest_type, inv_rows, inv_cols)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, new_view))


async def handle_chest_take(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Take selected item from chest into player inventory."""
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    sel = state.get("selected", 0)
    chest_inv = await get_chest_items(db, chest_id)
    inv_rows, inv_cols = _inv_capacity(player)
    player_inv = await get_inventory(db, user_id)

    suffix = ""
    if sel < len(chest_inv):
        item_id = chest_inv[sel]["item_id"]
        # Check inventory capacity for new items
        existing_ids = {it["item_id"] for it in player_inv}
        has_space = item_id in existing_ids or len(player_inv) < inv_rows * inv_cols
        if not has_space:
            suffix = "\n*Inventory full! Remove items or equip a larger pouch.*"
        else:
            if item_id == "gold_coin":
                qty = chest_inv[sel]["quantity"]
                _apply_gold_cap(player, qty)
                await update_player_stats(db, user_id, gold=player.gold)
                await remove_from_chest(db, chest_id, item_id, qty)
                suffix = f"\n*Collected {qty} gold!*"
            else:
                await remove_from_chest(db, chest_id, item_id, 1)
                await add_to_inventory(db, user_id, item_id, 1)
                suffix = f"\n*Took {item_id.replace('_',' ').title()}.*"
    else:
        suffix = "\n*(Empty slot)*"

    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    new_sel = min(sel, max(0, len(chest_inv) - 1))
    _ui_state[user_id]["selected"] = new_sel
    content = render_chest(chest_inv, player_inv, new_sel, "chest",
                           chest_type, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, "chest"))


async def handle_chest_give(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Give selected player item to chest."""
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    sel = state.get("selected", 0)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)

    suffix = ""
    if sel < len(player_inv):
        item_id = player_inv[sel]["item_id"]
        chest_inv = await get_chest_items(db, chest_id)
        # Check chest capacity
        chest_sizes = {
            "cave_chest": (2,9), "cave_chest_medium": (3,9), "cave_chest_large": (4,9),
            "ph_chest_small": (2,9), "ph_chest_medium": (3,9), "ph_chest_large": (4,9),
        }
        c_rows, c_cols = chest_sizes.get(chest_type, (2,9))
        c_capacity = c_rows * c_cols
        existing_chest_ids = {it["item_id"] for it in chest_inv}
        has_space = item_id in existing_chest_ids or len(chest_inv) < c_capacity
        if not has_space:
            suffix = "\n*Chest is full!*"
        else:
            await remove_from_inventory(db, user_id, item_id, 1)
            await add_to_chest(db, chest_id, item_id, 1)
            suffix = f"\n*Put {item_id.replace('_',' ').title()} in chest.*"
    else:
        suffix = "\n*(Empty slot)*"

    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    new_sel = min(sel, max(0, len(player_inv) - 1))
    _ui_state[user_id]["selected"] = new_sel
    content = render_chest(chest_inv, player_inv, new_sel, "player",
                           chest_type, inv_rows, inv_cols) + suffix
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, "player"))


async def handle_chest_lootall(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Loot all chest items into player inventory up to capacity."""
    result = await _load_chest(interaction, guild_id, user_id)
    if result is None:
        return
    db, player, state = result
    chest_id = state["chest_id"]
    chest_type = state.get("chest_type", "cave_chest")
    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    inv_rows, inv_cols = _inv_capacity(player)
    max_cap = inv_rows * inv_cols
    existing_ids = {it["item_id"] for it in player_inv}

    taken, skipped = [], []
    for chest_item in chest_inv:
        item_id = chest_item["item_id"]
        qty = chest_item["quantity"]
        if item_id == "gold_coin":
            _apply_gold_cap(player, qty)
            await remove_from_chest(db, chest_id, item_id, qty)
            taken.append(f"{qty} gold")
            continue
        # Can we fit this item?
        player_inv_fresh = await get_inventory(db, user_id)
        cur_ids = {it["item_id"] for it in player_inv_fresh}
        if item_id in cur_ids or len(player_inv_fresh) < max_cap:
            await remove_from_chest(db, chest_id, item_id, qty)
            await add_to_inventory(db, user_id, item_id, qty)
            taken.append(item_id.replace('_',' ').title())
        else:
            skipped.append(item_id.replace('_',' ').title())

    if player.gold != (await get_or_create_player(db, user_id, interaction.user.display_name)).gold:
        await update_player_stats(db, user_id, gold=player.gold)

    chest_inv = await get_chest_items(db, chest_id)
    player_inv = await get_inventory(db, user_id)
    suffix = ""
    if taken:
        suffix += f"\n*Looted: {', '.join(taken)}.*"
    if skipped:
        suffix += f"\n*Inventory full — left behind: {', '.join(skipped)}.*"
    if not taken and not skipped:
        suffix = "\n*Chest is empty.*"

    content = render_chest(chest_inv, player_inv, 0, "chest",
                           chest_type, inv_rows, inv_cols) + suffix
    _ui_state[user_id]["selected"] = 0
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=ChestView(guild_id, user_id, "chest"))


async def handle_chest_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_inv_close(interaction, guild_id, user_id)


# ── Forest chest handlers ─────────────────────────────────────────────────────

async def _fst_chest_render(guild_id: int, user_id: int) -> tuple[str, discord.ui.View]:
    """Rebuild the forest chest UI from _ui_state."""
    state = _ui_state.get(user_id, {})
    items = state.get("items", [])
    selected = state.get("selected", 0)
    chest_type = state.get("chest_type", "fst_chest")
    from dwarf_explorer.game.renderer import render_chest as _rc_fst2
    content = _rc_fst2(items, [], selected, "chest", chest_type)
    return content, FstChestView(guild_id, user_id)


async def handle_fst_chest_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    state = _ui_state.get(user_id, {})
    if state.get("type") != "fst_chest":
        await handle_inv_close(interaction, guild_id, user_id)
        return
    items = state.get("items", [])
    total = max(1, len(items))
    _ui_state[user_id]["selected"] = (state.get("selected", 0) + delta) % total
    content, view = await _fst_chest_render(guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_fst_chest_take(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    if state.get("type") != "fst_chest":
        await handle_inv_close(interaction, guild_id, user_id)
        return
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    items = state.get("items", [])
    sel = state.get("selected", 0)
    suffix = ""
    if sel < len(items):
        item = items[sel]
        item_id = item["item_id"]
        qty = item.get("quantity", 1)
        if item_id == "gold_coin":
            _apply_gold_cap(player, qty)
            await update_player_stats(db, user_id, gold=player.gold)
            suffix = f"\n*Collected {qty} gold!*"
        else:
            await add_to_inventory(db, user_id, item_id, qty)
            qty_s = f"×{qty} " if qty > 1 else ""
            suffix = f"\n*Took {qty_s}{item_id.replace('_', ' ').title()}.*"
        # Remove taken item and clamp cursor
        new_items = [it for i, it in enumerate(items) if i != sel]
        new_sel = min(sel, max(0, len(new_items) - 1))
        _ui_state[user_id]["items"] = new_items
        _ui_state[user_id]["selected"] = new_sel
    else:
        suffix = "\n*(Empty slot)*"
    content, view = await _fst_chest_render(guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content + suffix), content=None, view=view)


async def handle_fst_chest_lootall(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    if state.get("type") != "fst_chest":
        await handle_inv_close(interaction, guild_id, user_id)
        return
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    items = state.get("items", [])
    taken: list[str] = []
    for item in items:
        item_id = item["item_id"]
        qty = item.get("quantity", 1)
        if item_id == "gold_coin":
            _apply_gold_cap(player, qty)
            taken.append(f"{qty} gold")
        else:
            await add_to_inventory(db, user_id, item_id, qty)
            qty_s = f"×{qty} " if qty > 1 else ""
            taken.append(f"{qty_s}{item_id.replace('_', ' ').title()}")
    if player.gold != (await get_or_create_player(db, user_id, interaction.user.display_name)).gold:
        await update_player_stats(db, user_id, gold=player.gold)
    _ui_state[user_id]["items"] = []
    _ui_state[user_id]["selected"] = 0
    suffix = f"\n*Looted: {', '.join(taken)}.*" if taken else "\n*Cache was empty.*"
    content, view = await _fst_chest_render(guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content + suffix), content=None, view=view)


async def handle_fst_chest_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.pop(user_id, {})
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await _cached_grid(user_id, player, seed, db)
    content = render_grid(grid, player)
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Gear Machine handlers ─────────────────────────────────────────────────────

async def _open_gear_machine(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Show the gear machine UI for the current outer temple."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not getattr(player, "in_temple", False):
        await interaction.response.send_message("No gear machine here.", ephemeral=True)
        return
    temple_row = await db.fetch_one("SELECT temple_type FROM sky_temples WHERE id=?", (player.temple_id,))
    if not temple_row or temple_row["temple_type"] == "main":
        await interaction.response.send_message("No gear machine here.", ephemeral=True)
        return

    from dwarf_explorer.world.temples import get_layout_gear_slots
    layout_slots = get_layout_gear_slots(player.temple_id)
    slot_rows = await db.fetch_all(
        "SELECT slot_x, slot_y, required_gear, is_filled FROM temple_gear_slots WHERE temple_id=?",
        (player.temple_id,),
    )
    slot_map = {(r["slot_x"], r["slot_y"]): (r["required_gear"], bool(r["is_filled"])) for r in slot_rows}
    slot_states = [slot_map.get((ax, ay), (req, False)) for ax, ay, req in layout_slots]

    inv = await get_inventory(db, user_id)
    inv_item_ids = {r["item_id"] for r in inv if r["quantity"] > 0}

    solved = await is_outer_temple_solved(db, player.temple_id)
    content = _render_gear_machine(slot_states, solved, player, temple_id=player.temple_id)
    view = GearMachineView(guild_id, user_id, slot_states, inv_item_ids)
    await interaction.response.edit_message(content=None, embed=_embed(content), view=view)


async def handle_gear_slot(
    interaction: discord.Interaction, guild_id: int, user_id: int, slot_index: int
) -> None:
    """Handle clicking a gear slot button in the GearMachineView."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if not getattr(player, "in_temple", False):
        await interaction.response.send_message("Not in a temple.", ephemeral=True)
        return

    from dwarf_explorer.world.temples import get_layout_gear_slots
    layout_slots = get_layout_gear_slots(player.temple_id)

    if slot_index < 0 or slot_index >= len(layout_slots):
        await interaction.response.send_message("Invalid slot.", ephemeral=True)
        return

    ax, ay, required = layout_slots[slot_index]
    sr = await db.fetch_one(
        "SELECT required_gear, is_filled FROM temple_gear_slots WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (player.temple_id, ax, ay),
    )
    if not sr:
        await interaction.response.send_message("Slot not found.", ephemeral=True)
        return

    is_filled = bool(sr["is_filled"])
    msg = ""

    if is_filled:
        # Remove the gear
        removed = await remove_gear_slot(db, player.temple_id, ax, ay)
        if removed:
            await add_to_inventory(db, user_id, removed, 1)
            gear_name = removed.replace("_", " ")
            msg = f"🔧 You retrieve the **{gear_name}** from slot {slot_index + 1}."
        else:
            msg = "Nothing to remove."
    else:
        # Place the gear
        inv = await get_inventory(db, user_id)
        has_gear = any(r["item_id"] == required and r["quantity"] > 0 for r in inv)
        if not has_gear:
            gear_name = "small gear (⚙️)" if required == "small_gear" else "large gear (🔩)"
            msg = f"🔧 Slot {slot_index + 1} needs a **{gear_name}**. Craft one from iron ingots or find one in chests."
        else:
            gear_placed = await fill_gear_slot(db, player.temple_id, ax, ay, user_id)
            if gear_placed:
                await remove_from_inventory(db, user_id, required, 1)
                gear_name = required.replace("_", " ")
                msg = f"⚙️ You install the **{gear_name}** into slot {slot_index + 1}."
                solved = await is_outer_temple_solved(db, player.temple_id)
                all_solved = await are_all_outer_temples_solved(db)
                if solved:
                    msg += " ✨ **All gears installed — this temple's puzzle is complete!**"
                if all_solved:
                    msg += " 🌀 **All temples solved! The main temple portal has opened!**"
            else:
                msg = "Slot is already filled."

    # Refresh the machine UI
    slot_rows = await db.fetch_all(
        "SELECT slot_x, slot_y, required_gear, is_filled FROM temple_gear_slots WHERE temple_id=?",
        (player.temple_id,),
    )
    slot_map = {(r["slot_x"], r["slot_y"]): (r["required_gear"], bool(r["is_filled"])) for r in slot_rows}
    slot_states = [slot_map.get((ax2, ay2), (req2, False)) for ax2, ay2, req2 in layout_slots]
    solved2 = await is_outer_temple_solved(db, player.temple_id)
    inv2 = await get_inventory(db, user_id)
    inv_item_ids = {r["item_id"] for r in inv2 if r["quantity"] > 0}
    content = _render_gear_machine(slot_states, solved2, player, temple_id=player.temple_id)
    if msg:
        content = msg + "\n\n" + content
    view = GearMachineView(guild_id, user_id, slot_states, inv_item_ids)
    await interaction.response.edit_message(content=None, embed=_embed(content), view=view)


async def handle_gear_machine_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Close the gear machine and return to the temple viewport."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_temple_viewport(player.temple_id, player.temple_x, player.temple_y, db, is_main=False)
    content = render_grid(grid, player, "You step back from the machine.")
    await interaction.response.edit_message(
        content=None, embed=_embed(content),
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


# ── Map / Help ────────────────────────────────────────────────────────────────

async def handle_map(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    # Defer immediately — map generation fetches avatar images and renders a PNG,
    # which routinely exceeds Discord's 3-second interaction window.
    await interaction.response.defer()
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    has_crystal = getattr(player, "has_warp_crystal", False)

    from dwarf_explorer.database.repositories import get_player_ocean_quest_markers

    async def _send_ocean_map(buf: "io.BytesIO", title: str) -> None:
        """Send an ocean map as a separate channel message and restore the game view."""
        grid = await _cached_grid(user_id, player, seed, db)
        _nav = _ui_state.get(user_id, {}).get("nav_target")
        game_content = render_grid(grid, player, nav_target=_nav)
        game_v = _game_view(guild_id, user_id, player, grid=grid)
        buf.seek(0)
        map_file = discord.File(buf, filename="ocean_map.png")
        embed = discord.Embed(title=title)
        embed.set_image(url="attachment://ocean_map.png")
        await interaction.edit_original_response(
            embed=_embed(game_content), attachments=[], view=game_v
        )
        await interaction.followup.send(
            embed=embed, file=map_file, view=MapCloseView(guild_id, user_id)
        )

    if player.in_high_seas:
        ocean_qmarks = await get_player_ocean_quest_markers(db, user_id)
        overworld_qmarks = await get_player_quest_markers(db, user_id)
        ocean_avatar = await _fetch_or_cache_avatar(db, interaction.guild, user_id)
        from dwarf_explorer.world.world_map import generate_ocean_map
        buf = await generate_ocean_map(
            seed, guild_id,
            player.ocean_x, player.ocean_y,
            ocean_quest_markers=ocean_qmarks,
            has_wilderness_quests=bool(overworld_qmarks),
            player_avatar=ocean_avatar,
        )
        await _send_ocean_map(buf, "🗺️ Ocean Map")
        return

    if player.in_island or (player.in_cave and getattr(player, "cave_lit", False)):
        ocean_qmarks = await get_player_ocean_quest_markers(db, user_id)
        overworld_qmarks = await get_player_quest_markers(db, user_id)
        ocean_avatar_b = await _fetch_or_cache_avatar(db, interaction.guild, user_id)
        from dwarf_explorer.world.world_map import generate_ocean_map
        buf = await generate_ocean_map(
            seed, guild_id,
            player.island_ox, player.island_oy,
            ocean_quest_markers=ocean_qmarks,
            has_wilderness_quests=bool(overworld_qmarks),
            player_avatar=ocean_avatar_b,
        )
        await _send_ocean_map(buf, "🗺️ Ocean Map")
        return

    other_players = await get_all_overworld_players(db, user_id)
    qmarks = await get_player_quest_markers(db, user_id)
    ocean_qmarks = await get_player_ocean_quest_markers(db, user_id)

    # Fetch avatars — DB cache first (24 h TTL), Discord CDN only on miss/stale
    player_avatar = await _fetch_or_cache_avatar(db, interaction.guild, user_id)
    other_avatars: list[bytes | None] = []
    for _op in other_players:
        _op_uid = _op[3] if len(_op) > 3 else None
        other_avatars.append(
            await _fetch_or_cache_avatar(db, interaction.guild, _op_uid)
            if _op_uid else None
        )

    from dwarf_explorer.world.world_map import generate_world_map_with_key
    combined_buf = await generate_world_map_with_key(
        seed, db, guild_id, player.world_x, player.world_y,
        other_players, quest_markers=qmarks, ocean_quest_markers=ocean_qmarks,
        player_avatar=player_avatar, other_avatars=other_avatars,
    )
    combined_buf.seek(0)
    map_file = discord.File(combined_buf, filename="world_map.png")
    embed = discord.Embed(title="🗺️ World Map")
    embed.set_image(url="attachment://world_map.png")
    # Return the original game message to normal viewport
    grid = await _cached_grid(user_id, player, seed, db)
    _nav = _ui_state.get(user_id, {}).get("nav_target")
    game_content = render_grid(grid, player, nav_target=_nav)
    game_v = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.edit_original_response(
        embed=_embed(game_content), attachments=[], view=game_v
    )
    # Send map as a separate channel message with a close button
    await interaction.followup.send(
        embed=embed,
        file=map_file,
        view=MapCloseView(guild_id, user_id),
    )


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


WALKABLE_WILDERNESS = {"sand", "plains", "grass", "forest", "hills", "path",
                       "sapling", "short_grass", "seedling"}


async def handle_help_back(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await _cached_grid(user_id, player, seed, db)
    if player.in_cave:
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
    else:
        view = _game_view(guild_id, user_id, player, grid=grid)
    content = render_grid(grid, player)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Quest handlers ────────────────────────────────────────────────────────────

async def handle_quests(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open the quest log (unified D-pad view)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    # Preserve tab + index if already in quest_log state
    if state.get("type") == "quest_log":
        tab = state.get("tab", "side")
        idx = state.get("quest_index", 0)
        nav_target = state.get("nav_target")
    else:
        tab, idx, nav_target = "side", 0, state.get("nav_target")
    _ui_state[user_id] = {"type": "quest_log", "tab": tab, "quest_index": idx,
                          "nav_target": nav_target}
    await _render_quest_view(interaction, guild_id, user_id, db, player, tab, idx)


async def _render_quest_view(
    interaction: discord.Interaction,
    guild_id: int, user_id: int,
    db, player,
    tab: str, idx: int,
    extra_msg: str = "",
    confirm_abandon: bool = False,
) -> None:
    """Common renderer for the unified quest D-pad view."""
    from dwarf_explorer.game.quests import get_active_quests, get_main_quests
    from dwarf_explorer.ui.quest_view import QuestView, render_unified_quest_list

    state = _ui_state.get(user_id, {})
    nav_target = state.get("nav_target")

    if tab == "main":
        quests = await get_main_quests(db, user_id)
    else:
        quests = await get_active_quests(db, user_id)

    no_quests = len(quests) == 0
    idx = max(0, min(idx, len(quests) - 1)) if quests else 0

    # Determine if the currently displayed quest has the nav_target set, and if it's trackable
    has_target = False
    trackable = False
    if not no_quests and quests:
        q = quests[idx]
        tx = q.get("bounty_wx") or q.get("location_x")
        ty = q.get("bounty_wy") or q.get("location_y")
        trackable = tx is not None and ty is not None
        if trackable and nav_target:
            has_target = (nav_target == (int(tx), int(ty)))

    content = await render_unified_quest_list(
        db, user_id, tab, idx,
        in_village=player.in_village,
        nav_target=nav_target if has_target else None,
    )
    if extra_msg:
        content = extra_msg + "\n\n" + content

    view = QuestView(
        guild_id, user_id,
        tab=tab, quest_index=idx,
        has_target=has_target,
        confirm_abandon=confirm_abandon,
        no_quests=no_quests,
        trackable=trackable,
    )
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_quest_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    """Legacy handler (prev/next buttons on old messages)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    from dwarf_explorer.game.quests import get_active_quests
    quests = await get_active_quests(db, user_id)
    current = state.get("quest_index", 0)
    new_idx = (current + delta) % max(1, len(quests))
    tab = state.get("tab", "side")
    _ui_state[user_id] = {**state, "type": "quest_log", "tab": tab, "quest_index": new_idx}
    await _render_quest_view(interaction, guild_id, user_id, db, player, tab, new_idx)


async def handle_quest_up(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Navigate to previous quest in the current tab."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    from dwarf_explorer.game.quests import get_active_quests, get_main_quests
    tab = state.get("tab", "side")
    quests = await get_main_quests(db, user_id) if tab == "main" else await get_active_quests(db, user_id)
    current = state.get("quest_index", 0)
    new_idx = (current - 1) % max(1, len(quests))
    _ui_state[user_id] = {**state, "type": "quest_log", "tab": tab, "quest_index": new_idx}
    await _render_quest_view(interaction, guild_id, user_id, db, player, tab, new_idx)


async def handle_quest_down(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Navigate to next quest in the current tab."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    from dwarf_explorer.game.quests import get_active_quests, get_main_quests
    tab = state.get("tab", "side")
    quests = await get_main_quests(db, user_id) if tab == "main" else await get_active_quests(db, user_id)
    current = state.get("quest_index", 0)
    new_idx = (current + 1) % max(1, len(quests))
    _ui_state[user_id] = {**state, "type": "quest_log", "tab": tab, "quest_index": new_idx}
    await _render_quest_view(interaction, guild_id, user_id, db, player, tab, new_idx)


async def handle_quest_tab_left(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Switch quest tab (left arrow)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    tab = state.get("tab", "side")
    new_tab = "main" if tab == "side" else "side"
    _ui_state[user_id] = {**state, "type": "quest_log", "tab": new_tab, "quest_index": 0}
    await _render_quest_view(interaction, guild_id, user_id, db, player, new_tab, 0)


async def handle_quest_tab_right(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Switch quest tab (right arrow)."""
    await handle_quest_tab_left(interaction, guild_id, user_id)


async def handle_quest_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Legacy cancel → redirect to new abandon flow."""
    await handle_quest_abandon(interaction, guild_id, user_id)


async def handle_quest_abandon(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Show confirmation prompt before abandoning (side quests only)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    tab = state.get("tab", "side")
    idx = state.get("quest_index", 0)
    if tab == "main":
        # Main quests cannot be abandoned — silently re-render without confirm flag
        _ui_state[user_id] = {**state, "type": "quest_log"}
        await _render_quest_view(interaction, guild_id, user_id, db, player, tab, idx,
                                 extra_msg="ℹ️ Main quests cannot be abandoned.")
        return
    _ui_state[user_id] = {**state, "type": "quest_log"}
    await _render_quest_view(
        interaction, guild_id, user_id, db, player, tab, idx,
        extra_msg="⚠️ *Abandon this quest? All progress will be lost.*",
        confirm_abandon=True,
    )


async def handle_quest_cancel_confirm(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Legacy alias."""
    await handle_quest_abandon_confirm(interaction, guild_id, user_id)


async def handle_quest_abandon_confirm(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    tab = state.get("tab", "side")
    idx = state.get("quest_index", 0)
    # Guard: main quests cannot be abandoned — the button shouldn't appear, but
    # protect in case an old button is clicked.
    if tab == "main":
        _ui_state[user_id] = {**state, "type": "quest_log"}
        await _render_quest_view(interaction, guild_id, user_id, db, player, tab, idx,
                                 extra_msg="ℹ️ Main quests cannot be abandoned.")
        return
    from dwarf_explorer.game.quests import get_active_quests, cancel_quest
    quests = await get_active_quests(db, user_id)
    if quests and idx < len(quests):
        pq = quests[idx]
        await cancel_quest(db, user_id, pq["pq_id"])
        if pq.get("quest_subtype") == "delivery":
            await remove_from_inventory(db, user_id, "merchant_parcel", 1)
        new_idx = 0
        extra = "✖ Quest abandoned."
    else:
        new_idx = 0
        extra = "No quest to abandon."
    _ui_state[user_id] = {**state, "type": "quest_log", "tab": "side", "quest_index": new_idx}
    await _render_quest_view(interaction, guild_id, user_id, db, player, "side", new_idx,
                             extra_msg=extra)


async def handle_quest_cancel_back(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Legacy alias."""
    await handle_quest_abandon_back(interaction, guild_id, user_id)


async def handle_quest_abandon_back(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    tab = state.get("tab", "side")
    idx = state.get("quest_index", 0)
    await _render_quest_view(interaction, guild_id, user_id, db, player, tab, idx)


async def handle_quest_set_target(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Toggle nav target for the currently displayed quest."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    tab = state.get("tab", "side")
    idx = state.get("quest_index", 0)
    current_target = state.get("nav_target")

    from dwarf_explorer.game.quests import get_active_quests, get_main_quests
    quests = await get_main_quests(db, user_id) if tab == "main" else await get_active_quests(db, user_id)
    if quests and idx < len(quests):
        q = quests[idx]
        tx = q.get("bounty_wx") or q.get("location_x")
        ty = q.get("bounty_wy") or q.get("location_y")
        if tx is not None and ty is not None:
            this_target = (int(tx), int(ty))
            if current_target == this_target:
                # Unset target
                _ui_state[user_id] = {**state, "nav_target": None}
                extra = "📍 **Target cleared.**"
            else:
                # Set (or switch to) this target
                _ui_state[user_id] = {**state, "nav_target": this_target}
                extra = "📍 **Target set!** A ♦️ diamond will appear at the edge of your viewport."
        else:
            subtype = q.get("quest_subtype", "")
            if subtype == "kill":
                extra = "⚔️ This quest requires defeating enemies — no specific location to navigate to."
            else:
                extra = "⚠️ This quest has no map location to target."
    else:
        extra = ""

    await _render_quest_view(interaction, guild_id, user_id, db, player, tab, idx,
                             extra_msg=extra)


async def handle_quest_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    # Preserve nav_target if set, but clear quest_log state
    old_state = _ui_state.pop(user_id, {})
    nav_target = old_state.get("nav_target")
    if nav_target:
        _ui_state[user_id] = {"nav_target": nav_target}
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await _cached_grid(user_id, player, seed, db)
    nav = _ui_state.get(user_id, {}).get("nav_target")
    content = render_grid(grid, player, nav_target=nav)
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_quest_main(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Legacy: open main quest tab via old button."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    _ui_state[user_id] = {**state, "type": "quest_log", "tab": "main", "quest_index": 0}
    await _render_quest_view(interaction, guild_id, user_id, db, player, "main", 0)


async def handle_mq_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    """Legacy handler for old mq_prev/mq_next buttons."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    from dwarf_explorer.game.quests import get_main_quests
    quests = await get_main_quests(db, user_id)
    idx = state.get("quest_index", state.get("index", 0)) + delta
    idx = max(0, min(idx, len(quests) - 1)) if quests else 0
    _ui_state[user_id] = {**state, "type": "quest_log", "tab": "main", "quest_index": idx}
    await _render_quest_view(interaction, guild_id, user_id, db, player, "main", idx)


async def handle_mq_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Legacy: close main quest view → same as quest_close."""
    await handle_quest_close(interaction, guild_id, user_id)


# ── NPC quest button ─────────────────────────────────────────────────────────

async def handle_npc_talk(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Triggered when the player clicks the 💬 Talk button.

    Detects which NPC is adjacent, then opens a DialogueView with:
      - A lore/greeting option
      - A quest option (if the NPC has quests to offer), marked with 📋
      - A farewell option
    """
    from dwarf_explorer.game.quests import get_or_refresh_village_pool, get_or_refresh_bounty_pool
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    import hashlib as _h_mod
    def _hash(s): return int(_h_mod.md5(s.encode()).hexdigest(), 16)

    # ── Bandit camp context ──────────────────────────────────────────────────
    if getattr(player, "in_bandit_camp", False):
        from dwarf_explorer.world.bandit_camp import load_camp_viewport as _lbcv_talk
        _bc_row_talk = await db.fetch_one(
            "SELECT world_x, world_y FROM bandit_camps WHERE id=?", (player.bandit_camp_id,)
        )
        if _bc_row_talk:
            bc_grid = _lbcv_talk(player.bc_x, player.bc_y, int(_bc_row_talk["world_x"]), int(_bc_row_talk["world_y"]))
            vc = len(bc_grid) // 2
            _bc_adj = False
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = vc + dr, vc + dc
                if 0 <= nr < len(bc_grid) and 0 <= nc < len(bc_grid[nr]):
                    _t = bc_grid[nr][nc]
                    if _t and _t.terrain == "bc_bandit":
                        _bc_adj = True
                        break
            if not _bc_adj:
                await interaction.response.send_message("No one is close enough to talk to.", ephemeral=True)
                return
        import hashlib as _bh_mod
        def _bh(s): return int(_bh_mod.md5(s.encode()).hexdigest(), 16)
        _bh_seed = _bh(f"bandit{player.bandit_camp_id}{player.bc_x}{player.bc_y}")
        _bandit_greets = [
            "\"You've got some nerve walking in here. State your business — quickly.\"",
            "\"Trespassing in our camp. That costs you, friend.\"",
            "\"Easy now. Don't make any sudden moves and we can talk like civilised folk.\"",
            "\"Well, well. Lost traveller, or brave fool? Hard to tell the difference.\"",
            "\"My hands are on my knife. Just so you know. Now talk.\"",
        ]
        _bandit_lore = [
            "\"We don't rob for sport. We rob because the roads are taxed to ruin and honest work pays nothing. Think about that.\"",
            "\"Half my crew used to be farmers. The other half — soldiers. Both kinds end up in camps like this eventually.\"",
            "\"You hear things on the road. Caravans talk. We listen. It's a living.\"",
            "\"There's a code out here. Harm the old, harm children, harm healers — and you answer to us. Remember that.\"",
            "\"Don't mistake us for murderers. We're businessmen. Expensive businessmen.\"",
        ]
        _greet = _bandit_greets[_bh_seed % len(_bandit_greets)]
        _lore  = _bandit_lore[(_bh_seed >> 4) % len(_bandit_lore)]
        _bc_options = [
            {"label": "\"Who are you people?\"",        "action": "lore"},
            {"label": "💰 Offer a bribe",               "action": "bribe"},
            {"label": "\"I'll be leaving now.\"",       "action": "close"},
        ]
        _bc_state = {
            "type":       "npc_dialogue",
            "npc_type":   "bc_bandit",
            "npc_name":   "Bandit",
            "text":       _greet,
            "options":    _bc_options,
            "selected":   0,
            "context":    "bandit_camp",
            "lore_text":  _lore,
            "source_label": "Bandit",
        }
        _ui_state[user_id] = _bc_state
        _bc_content = _render_dialogue("Bandit", _greet, _bc_options, 0)
        _bc_view = DialogueView(guild_id, user_id, _bc_options, 0)
        await interaction.response.edit_message(embed=_embed(_bc_content), content=None, view=_bc_view)
        return

    # ── Tree city context ────────────────────────────────────────────────────
    if getattr(player, "in_tree_city", False):
        from dwarf_explorer.world.forest import load_tree_city_viewport as _ltcv_talk
        tc_grid = await _ltcv_talk(
            player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db
        )
        vc = len(tc_grid) // 2
        adj_npc: dict[str, tuple] = {}
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = vc + dr, vc + dc
            if 0 <= nr < len(tc_grid) and 0 <= nc < len(tc_grid[nr]):
                tile = tc_grid[nr][nc]
                if tile and tile.terrain in _QUEST_NPC_TILES:
                    adj_npc[tile.terrain] = (getattr(tile, "local_x", 0), getattr(tile, "local_y", 0))

        npc_name, lore_text, pool, context = "Tree Dweller", "...", [], "tree_city"
        _elder_mq_label = ""  # set only for tc_elder
        # Stable hash for this NPC position — used for quest phrase, rumors, and
        # villager lore regardless of which NPC type is being spoken to.
        _hv = _hash(f"tcv{player.tc_forest_id}{player.tc_x}{player.tc_y}")

        if "tc_elder" in adj_npc:
            npc_name = "Tree Elder"
            _elder_lore = [
                "This great tree has stood for centuries. We who dwell within it are its memory — and its will. You have climbed far, traveller. That is not nothing.",
                "There are those who come here seeking power. They rarely find what they expect. The tree gives what is needed, not what is wanted.",
                "I have seen three generations of travellers pass through this city. Most are looking for something. Few know what it is.",
                "The roots of this tree reach the bedrock. Some say they reach further. I do not contradict them.",
            ]
            _eh = _hash(f"tc_elder{player.tc_forest_id}{player.tc_floor}")
            lore_text = _elder_lore[_eh % len(_elder_lore)]
            # Determine main quest label based on current stage
            from dwarf_explorer.game.quests import has_forest_depths_quest as _hfdq
            _has_fq  = await _hfdq(db, user_id)
            _fq_stg  = getattr(player, "fq_quest_stage", "none") or "none"
            if not _has_fq:
                _mq_label = "⚔️ I seek purpose (Main Quest)"
            elif _fq_stg in ("quest_complete", "rewarded"):
                _mq_label = "✅ The Forest Depths: Complete"
            elif _fq_stg == "hermit_met":
                _alog_n = sum(r["quantity"] for r in await db.fetch_all(
                    "SELECT quantity FROM inventory WHERE user_id=? AND item_id='ancient_log'", (user_id,)))
                if _alog_n >= 3:
                    _mq_label = "🪄 Craft the Wayerwood (ready!)"
                else:
                    _mq_label = f"📋 Gather materials: {_alog_n}/3 ancient logs (chop forest ancient tree)"
            elif _fq_stg == "seek_hermit":
                _mq_label = "⚔️ Find the Hermit"
            elif _fq_stg == "wayerwood_crafted":
                _mq_label = "⚔️ Enter the Forest Depths"
            else:
                _mq_label = "⚔️ The Forest Depths: In progress"
            _elder_mq_label = _mq_label
            # Elder side-quest pool on floor 4
            if getattr(player, "tc_floor", 1) == 4:
                from dwarf_explorer.game.quests import get_or_refresh_village_pool as _gvp_tc
                # Use tc_forest_id as a pseudo-village so pool is stable per forest
                _tc_pool = await _gvp_tc(db, player.tc_forest_id, seed)
                pool = _tc_pool[:1]
        elif "tc_archivist" in adj_npc:
            npc_name = "Tree City Archivist"
            has_crystal = getattr(player, "has_warp_crystal", False)
            if has_crystal:
                lore_text = (
                    "You already hold a Chronolite shard — I see its resonance in the air around you. "
                    "Good. Guard it well. The Temporal Rifts grow unstable. Each activation weakens the boundary."
                )
            else:
                lore_text = (
                    "I have catalogued every ring of this ancient tree. Did you know there is a grove "
                    "deep in the forest where time moves strangely? A stone idol stands at its heart. "
                    "Those who touch it... change. A Chronolite shard, they call what emerges."
                )
        elif "tc_villager" in adj_npc:
            npc_name = "Tree Dweller"
            tc_lore = [
                "High up in the canopy the wind sounds different. Like breathing.",
                "We rarely go to the ground anymore. The forest floor is not safe at night.",
                "The elder knows things about this tree that no scroll records.",
                "I was born in this tree. Forty rings up. Never seen the ocean.",
                "Visitors always look surprised that we have kitchens up here. Where did they think we cooked?",
                "The view from the top platform at dawn is something you'll remember your whole life.",
                "My grandmother planted a seedling on the eastern branch. It's a proper tree now, sixty years on.",
                "We trade with the ground villages twice a year. It's always a shock to walk on flat earth again.",
            ]
            lore_text = tc_lore[_hv % len(tc_lore)]

        _tc_quest_phrases = [
            "Got any work for me?",
            "Any jobs you need done?",
            "I'm looking for work.",
            "Need any errands run?",
            "What work do you have?",
        ]
        _tc_qp_label = _tc_quest_phrases[_hv % len(_tc_quest_phrases)]
        _tc_rumors = [
            "Deep in the forest, there are ruins from before the first tree cities were built.",
            "A merchant spoke of a great sea creature near the western isles — sailors won't go there alone.",
            "The elders whisper about something stirring in the old caves beneath the roots.",
            "Word is the lowland bounty boards are paying well for rare herbs this season.",
            "I heard there's an archivist who knows how to open the old rifts. Haven't seen them myself.",
            "There are paths in the canopy that lead nowhere, they say — doors that only open at dawn.",
            "A traveller left an old map fragment at the trading post. No one's claimed it yet.",
            "They say on clear nights you can see the lights of three villages from the highest platform.",
        ]
        tc_rumors_text = _tc_rumors[_hv % len(_tc_rumors)]
        options = [{"label": "Tell me about yourself", "action": "lore"}]
        # Main quest option — only for the elder
        if "tc_elder" in adj_npc:
            options.append({"label": _elder_mq_label or "⚔️ Main Quest", "action": "elder_main_quest"})
        if pool:
            options.append({"label": f"📋 {_tc_qp_label} (Quest)", "action": "quest_pool"})
        options.append({"label": "Heard any rumors?", "action": "rumors"})
        options.append({"label": "Farewell", "action": "close"})
        state = {
            "type": "npc_dialogue", "npc_type": "tc_npc",
            "npc_name": npc_name,
            "text": "Greetings, wanderer. What brings you to the great tree?",
            "options": options, "selected": 0,
            "context": context, "quest_pool": pool,
            "lore_text": lore_text, "rumors_text": tc_rumors_text, "source_label": npc_name,
        }
        _ui_state[user_id] = state
        content = _render_dialogue(npc_name, state["text"], options, 0)
        view = DialogueView(guild_id, user_id, options, 0)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # ── Cave/Rift context ────────────────────────────────────────────────────
    if player.in_cave and not getattr(player, "in_tree_city", False):
        from dwarf_explorer.world.caves import load_cave_viewport as _lcv_talk
        cave_grid = await _lcv_talk(player.cave_id, player.cave_x, player.cave_y, db)
        vc = len(cave_grid) // 2
        adj_npc_cave: dict[str, tuple] = {}
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = vc + dr, vc + dc
            if 0 <= nr < len(cave_grid) and 0 <= nc < len(cave_grid[nr]):
                tile = cave_grid[nr][nc]
                if tile and tile.terrain in _QUEST_NPC_TILES:
                    adj_npc_cave[tile.terrain] = ()

        if "rift_archivist" in adj_npc_cave:
            has_crystal = getattr(player, "has_warp_crystal", False)
            if has_crystal:
                npc_name = "Panicked Scholar"
                lore_text = (
                    "You already carry Chronolite resonance — then you understand the danger! "
                    "The temporal echo that haunts this rift was once a person, like you and I. "
                    "Time fractured around them. Please — do not linger here."
                )
            else:
                npc_name = "Panicked Scholar"
                lore_text = (
                    "I was studying the sundial when it activated and pulled me here! "
                    "This is a Temporal Rift — a fold in time itself. The creature deeper in "
                    "this place is dangerous beyond measure. There is a grove in the forest... "
                    "a stone idol there holds the key to navigating these rifts safely."
                )
            options = [
                {"label": "Tell me what you know", "action": "lore"},
                {"label": "Farewell", "action": "close"},
            ]
            state = {
                "type": "npc_dialogue", "npc_type": "rift_npc",
                "npc_name": npc_name,
                "text": "Oh thank goodness — a living person! Please, you must listen!",
                "options": options, "selected": 0,
                "context": "rift",
                "lore_text": lore_text, "source_label": npc_name,
            }
            _ui_state[user_id] = state
            content = _render_dialogue(npc_name, state["text"], options, 0)
            view = DialogueView(guild_id, user_id, options, 0)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return

    # ── Village / building context ───────────────────────────────────────────
    # Load the correct grid based on context
    if player.in_house:
        context = "building"
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        context = "village"
        grid = await load_village_viewport(
            player.village_id, player.village_x, player.village_y, db, user_id=user_id
        )
    else:
        return

    vc = len(grid) // 2
    adj_npc: dict[str, tuple[int, int]] = {}
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = vc + dr, vc + dc
        if 0 <= nr < len(grid) and 0 <= nc < len(grid[nr]):
            tile = grid[nr][nc]
            if tile and tile.terrain in _QUEST_NPC_TILES:
                adj_npc[tile.terrain] = (tile.world_x, tile.world_y)

    village_pool = await get_or_refresh_village_pool(
        db, player.village_id, seed,
        village_wx=player.village_wx, village_wy=player.village_wy,
    )
    bounty_pool  = await get_or_refresh_bounty_pool(
        db, seed,
        village_id=player.village_id,
        village_wx=player.village_wx,
        village_wy=player.village_wy,
    )

    # NPC-specific lore texts and quest pool resolution
    _vh = _hash(f"vlt{player.village_id}{player.village_x}{player.village_y}")
    if "b_priest" in adj_npc:
        npc_name = "Village Priest"
        _priest_lore = [
            "The light of the gods watches over this village. May your journey be blessed.",
            "We hold a harvest prayer every full moon. Even the bandits in the hills stay quiet that night.",
            "Faith is the armour no blacksmith can forge. I have seen it turn back blades.",
            "Many pass through seeking glory. Few return to give thanks. You seem like one of the ones who will.",
            "The old shrines in the wilderness still carry power. Tread carefully near them.",
        ]
        lore_text = _priest_lore[_vh % len(_priest_lore)]
        pool = village_pool[:1]
    elif "b_tavern_npc" in adj_npc:
        nx, ny = adj_npc["b_tavern_npc"]
        _th = _hash(f"tvlt{player.village_id}{nx}{ny}")
        idx = _th % max(1, len(bounty_pool)) if bounty_pool else 0
        npc_name = "Tavern Regular"
        _tavern_lore = [
            "Heard some strange rumors from the road lately... adventurers keep disappearing in the wilds.",
            "A merchant passed through last week. Said the bandit camps to the east have gotten bolder.",
            "My uncle used to say: never sleep near a sundial. Whatever that means.",
            "You look like you've seen things. Buy me a drink and I'll tell you what I know.",
            "There's gold in the caves, they say. There's also something else in the caves. They don't mention that part.",
            "Three hunters went into the forest last month. Two came back. The third sends letters, apparently.",
            "The river to the north runs fast this time of year. Good fishing if you know where to stand.",
        ]
        lore_text = _tavern_lore[_th % len(_tavern_lore)]
        pool = bounty_pool[idx:idx + 1]
    elif "b_farmer_npc" in adj_npc:
        _fh = _hash(f"farm{player.village_id}{player.village_x}{player.village_y}")
        npc_name = "Farmer"
        _farmer_lore = [
            "The soil has been good to us this season. But we can always use an extra pair of hands.",
            "Wheat doesn't water itself. I start before sunrise and finish after dark. Every day.",
            "My grandfather cleared this land. His father before him. I'll give it to my children.",
            "The crows have been bad this year. Lost half a row to them last week.",
            "You want advice? Plant early, water often, and don't trust anyone who doesn't know soil.",
        ]
        lore_text = _farmer_lore[_fh % len(_farmer_lore)]
        pool = village_pool[:1]
    elif "b_blacksmith_npc" in adj_npc:
        _bsh = _hash(f"bslt{player.village_id}{player.village_x}{player.village_y}")
        npc_name = "Blacksmith"
        _smith_lore = [
            "Steel and sweat — that's the honest life. Not everyone appreciates it, but the village would fall without us.",
            "I can work iron, bronze, even some alloys from the deep caves. Bring me good ore and I'll make you something worth carrying.",
            "A blade is only as good as the hand that holds it — but a poorly made blade is bad in any hand.",
            "The wyvern scales they bring from the eastern caves... I've never worked anything harder. Beautiful edge though.",
            "My apprentice quit last spring. Said he wanted adventure. Came back three months later, missing two fingers. Still won't tell me why.",
        ]
        lore_text = _smith_lore[_bsh % len(_smith_lore)]
        pool = bounty_pool[:1]
    elif "vil_villager" in adj_npc:
        npc_name = "Villager"
        _vill_lore = [
            "Life is quiet here, but I like it that way.",
            "Have you seen the market? Finest goods in the region.",
            "They say there's something strange in the forest to the north. A city up in the branches. Mad, right?",
            "The children play near the well every evening. It's nice.",
            "A traveller like you came through last season. Bought half our supplies and never came back. Curious.",
            "Don't let the elder hear you complaining about the mud. She'll tell you about the flood of '87 again.",
            "My sister moved to the coast. Says the salt air cures everything. I miss her.",
            "We had a wolf problem three winters back. The hunters sorted it, but I still bar my door at night.",
        ]
        lore_text = _vill_lore[_vh % len(_vill_lore)]
        pool = bounty_pool[:1] if _vh % 2 == 0 else []
    elif "vil_guard" in adj_npc:
        npc_name = "Village Guard"
        _gh = _hash(f"glt{player.village_id}{player.village_x}{player.village_y}")
        _guard_lore = [
            "Stay out of trouble and we won't have a problem. The village gates are watched at all hours.",
            "Bandit activity has picked up to the east. I'd avoid that road at night if I were you.",
            "We lost two good guards last winter. Wolves from the hills. We've set traps since then.",
            "I've been posted here six years. Seen all kinds pass through. Most aren't worth the worry.",
            "Move along, traveller. Unless you've got business here, in which case — what business?",
        ]
        lore_text = _guard_lore[_gh % len(_guard_lore)]
        pool = bounty_pool[:1] if _gh % 2 == 0 else []
    elif "b_resident" in adj_npc:
        npc_name = "Resident"
        _rh = _hash(f"rlt{player.village_id}{player.house_x}{player.house_y}")
        _res_lore = [
            "Nice place you've found here. Almost as nice as mine.",
            "I moved here three years ago. Haven't regretted it since.",
            "You're not from here, are you? I can always tell.",
            "The nights here are remarkably quiet. After where I came from, that still surprises me.",
            "My neighbour has chickens. I have opinions about those chickens.",
        ]
        lore_text = _res_lore[_rh % len(_res_lore)]
        pool = bounty_pool[:1] if _rh % 10 < 4 else []
    else:
        npc_name = "Stranger"
        lore_text = "..."
        pool = []

    # Build dialogue options
    _vil_quest_phrases = [
        "Got any work for me?",
        "Any jobs you need done?",
        "I'm looking for work.",
        "Need any errands run?",
        "What work do you have?",
    ]
    _vil_rumors_pool = [
        "Traders from the east coast say there are creatures in the deep ocean no one has named yet.",
        "A hunter saw lights in the forest canopy at night. Others say it's just the tree city folk.",
        "The price of iron has gone up. Someone's been buying it in bulk and nobody knows who.",
        "Word is a merchant guild is forming in the southern villages. Prices might change soon.",
        "A traveller found a map fragment in some ruins last month. Wouldn't show anyone though.",
        "The wells have been running lower than usual. Nobody's talking about it, but everyone's noticed.",
        "Three caravans took the northern pass this season. Only two came back the usual way.",
        "There's a bounty board in the market square. Pays decent coin if you've got the stomach for it.",
    ]
    _qph = _hash(f"qph{player.village_id}{player.world_x}{player.world_y}")
    _vil_qp_label = _vil_quest_phrases[_qph % len(_vil_quest_phrases)]
    vil_rumors_text = _vil_rumors_pool[_qph % len(_vil_rumors_pool)]
    options = [{"label": "Tell me about yourself", "action": "lore"}]
    if pool:
        options.append({"label": f"📋 {_vil_qp_label} (Quest)", "action": "quest_pool"})
    options.append({"label": "Heard any rumors?", "action": "rumors"})
    options.append({"label": "Farewell", "action": "close"})

    state = {
        "type": "npc_dialogue",
        "npc_type": "village_npc",
        "npc_name": npc_name,
        "text": "What brings you to me, traveller?",
        "options": options,
        "selected": 0,
        "context": context,
        "quest_pool": pool,
        "lore_text": lore_text,
        "rumors_text": vil_rumors_text,
        "source_label": npc_name,
    }
    _ui_state[user_id] = state
    content = _render_dialogue(npc_name, state["text"], options, 0)
    view = DialogueView(guild_id, user_id, options, 0)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_npc_quest(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Triggered when the player clicks the NPC quest button (bottom-right).
    Detects which quest NPC is adjacent and opens the appropriate quest pool.
    """
    from dwarf_explorer.game.quests import get_or_refresh_village_pool, get_or_refresh_bounty_pool
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # Determine which NPC tile the player is adjacent to and load the right grid
    if player.in_house:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    elif player.in_village:
        grid = await load_village_viewport(
            player.village_id, player.village_x, player.village_y, db, user_id=user_id
        )
    else:
        return

    vc = len(grid) // 2
    # Build a map of adjacent terrain → (world_x, world_y) of that tile
    adj_npc: dict[str, tuple[int, int]] = {}
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = vc + dr, vc + dc
        if 0 <= nr < len(grid) and 0 <= nc < len(grid[nr]):
            tile = grid[nr][nc]
            if tile and tile.terrain in _QUEST_NPC_TILES:
                adj_npc[tile.terrain] = (tile.world_x, tile.world_y)

    village_pool = await get_or_refresh_village_pool(
        db, player.village_id, seed,
        village_wx=player.village_wx, village_wy=player.village_wy,
    )
    bounty_pool  = await get_or_refresh_bounty_pool(
        db, seed,
        village_id=player.village_id,
        village_wx=player.village_wx,
        village_wy=player.village_wy,
    )

    if "b_priest" in adj_npc:
        # Priest offers a village quest (index 0 — always the current village quest)
        pool = village_pool[:1]
        source_label = "Priest"
    elif "b_tavern_npc" in adj_npc:
        # Each tavern NPC at a unique position offers a different bounty quest
        nx, ny = adj_npc["b_tavern_npc"]
        idx = (nx * 7 + ny * 13) % max(1, len(bounty_pool)) if bounty_pool else 0
        pool = bounty_pool[idx:idx + 1]
        source_label = "Tavern Regular"
    elif "b_farmer_npc" in adj_npc:
        pool = village_pool[:1]
        source_label = "Farmer"
    elif "b_blacksmith_npc" in adj_npc:
        pool = bounty_pool[:1]
        source_label = "Blacksmith"
    elif "vil_villager" in adj_npc:
        import hashlib as _hvill
        _h = int(_hvill.md5(f"vnq{player.village_id}{player.village_x}{player.village_y}".encode()).hexdigest(), 16)
        if _h % 2 == 0:
            pool = bounty_pool[:1]
            source_label = "Villager"
        else:
            content = render_grid(grid, player, "\"I have no work for you today, stranger.\"")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
    elif "vil_guard" in adj_npc:
        import hashlib as _hguard
        _h = int(_hguard.md5(f"gnq{player.village_id}{player.village_x}{player.village_y}".encode()).hexdigest(), 16)
        if _h % 2 == 0:
            pool = bounty_pool[:1]
            source_label = "Guard"
        else:
            content = render_grid(grid, player, "\"I have no work for you today, stranger.\"")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
    elif "b_resident" in adj_npc:
        import hashlib as _hres
        _h = int(_hres.md5(f"rnq{player.village_id}{player.house_x}{player.house_y}".encode()).hexdigest(), 16)
        if _h % 10 < 4:  # 40% chance
            pool = bounty_pool[:1]
            source_label = "Resident"
        else:
            content = render_grid(grid, player, "\"I'm just a resident here.\"")
            view = _game_view(guild_id, user_id, player, grid=grid)
            await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
            return
    else:
        # Fallback: combined pool first entry
        pool = (village_pool + bounty_pool)[:1]
        source_label = "Villager"

    if pool:
        await handle_open_quest_pool(
            interaction, guild_id, user_id,
            pool=pool,
            source_label=source_label,
            source_type="village_npc",
        )
        return

    content = render_grid(grid, player, f"📋 {source_label} has no work available right now.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Quest pool (village / bounty board) ──────────────────────────────────────

async def handle_open_quest_pool(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    pool: list, source_label: str, source_type: str,
) -> None:
    """Open the quest pool offer list (called from interact handler)."""
    from dwarf_explorer.game.quests import get_active_quests
    from dwarf_explorer.ui.quest_view import QuestPoolView, render_quest_pool
    db = await get_database(guild_id)
    active_quests = await get_active_quests(db, user_id)
    _ui_state[user_id] = {
        "type": "quest_pool", "pool": pool, "selected": 0,
        "source_label": source_label, "source_type": source_type,
    }
    content = await render_quest_pool(pool, active_quests, 0, source_label)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=QuestPoolView(guild_id, user_id, quest_count=len(pool)),
    )


async def handle_qpool_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, delta: int
) -> None:
    db = await get_database(guild_id)
    state = _ui_state.get(user_id, {})
    if state.get("type") != "quest_pool":
        return
    from dwarf_explorer.game.quests import get_active_quests
    from dwarf_explorer.ui.quest_view import QuestPoolView, render_quest_pool
    pool   = state["pool"]
    active = await get_active_quests(db, user_id)
    avail  = [q for q in pool if (q.get("id") or q.get("quest_id")) not in {a["quest_id"] for a in active}]
    sel    = (state.get("selected", 0) + delta) % max(1, len(avail))
    _ui_state[user_id]["selected"] = sel
    content = await render_quest_pool(pool, active, sel, state["source_label"])
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=QuestPoolView(guild_id, user_id, quest_count=len(avail), selected=sel),
    )


async def handle_qpool_accept(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    if state.get("type") != "quest_pool":
        return
    from dwarf_explorer.game.quests import (
        get_active_quests, accept_quest, MAX_PLAYER_QUESTS, get_active_quest_count
    )
    from dwarf_explorer.ui.quest_view import (
        QuestPoolView, render_quest_pool, QuestView, render_quest_list
    )
    pool   = state["pool"]
    active = await get_active_quests(db, user_id)
    avail  = [q for q in pool if (q.get("id") or q.get("quest_id")) not in {a["quest_id"] for a in active}]
    sel    = state.get("selected", 0)
    if not avail or sel >= len(avail):
        await interaction.response.edit_message(
            embed=_embed("No quest selected."), content=None,
            view=QuestPoolView(guild_id, user_id, 0),
        )
        return
    q = avail[sel]
    count = await get_active_quest_count(db, user_id)
    if count >= MAX_PLAYER_QUESTS:
        content = (f"⚠️ Your quest log is full "
                   f"({MAX_PLAYER_QUESTS}/{MAX_PLAYER_QUESTS}). Abandon a quest first.")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=QuestPoolView(guild_id, user_id, len(avail), sel),
        )
        return
    src_type  = state.get("source_type", "village_npc")
    bounty_wx = q.get("location_x") if src_type == "bounty" else None
    bounty_wy = q.get("location_y") if src_type == "bounty" else None
    ok = await accept_quest(db, user_id, q.get("id") or q.get("quest_id"), source_type=src_type,
                            bounty_wx=bounty_wx, bounty_wy=bounty_wy)
    if ok:
        if q.get("quest_subtype") == "delivery":
            await add_to_inventory(db, user_id, "merchant_parcel", 1)
        _updated_quests = await get_active_quests(db, user_id)
        _new_idx = max(0, len(_updated_quests) - 1)
        _ui_state[user_id] = {"type": "quest_log", "quest_index": _new_idx}
        content = f"✅ Quest accepted: **{q['title']}**\n\n"
        content += await render_quest_list(db, user_id, _new_idx, in_village=player.in_village)
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=QuestView(guild_id, user_id))
    else:
        await interaction.response.edit_message(
            embed=_embed("Could not accept quest (already accepted or log full)."), content=None,
            view=QuestPoolView(guild_id, user_id, len(avail), sel),
        )


async def handle_qpool_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    await handle_quest_close(interaction, guild_id, user_id)


# ── Open-world harbour village recruitable NPC ───────────────────────────────

async def handle_village_recruit_npc(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player, seed: int, grid,
) -> None:
    """Show recruit dialogue when a player interacts with a recruitable villager NPC."""
    db = await get_database(guild_id)
    crew = await get_ship_crew(db, user_id)
    crew_count = len(crew)

    import hashlib as _hrn
    _seed = abs(int(_hrn.md5(
        f"recruit:{user_id}:{player.village_id}:{player.village_x}:{player.village_y}".encode()
    ).hexdigest(), 16))
    npc_name = CREW_NAMES[_seed % len(CREW_NAMES)]

    if crew_count >= MAX_CREW_SIZE:
        content = render_grid(grid, player,
            f"**{npc_name}**: \"Yer ship's full already! Come back if ye ever need hands.\"")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Store recruit context in UI state then show the recruit view
    _ui_state[user_id] = {
        "type": "village_recruit_npc",
        "npc_name": npc_name,
        "npc_x": player.village_x,
        "npc_y": player.village_y,
        "village_id": player.village_id,
        "village_wx": player.village_wx,
        "village_wy": player.village_wy,
        "seed": seed,
    }
    npc_text = (
        f"**{npc_name}**: \"Aye, I've been looking for steady work on a ship. "
        f"Could use someone like me, couldn't ye? "
        f"(Crew: {crew_count}/{MAX_CREW_SIZE})\""
    )
    content = render_grid(grid, player, npc_text)
    view = VillageRecruitView(guild_id, user_id)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_village_recruit_confirm(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Player confirmed recruiting a village NPC."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.pop(user_id, {})
    if state.get("type") != "village_recruit_npc":
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "Something went wrong.")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return

    crew = await get_ship_crew(db, user_id)
    if len(crew) >= MAX_CREW_SIZE:
        grid = await _cached_grid(user_id, player, seed, db)
        content = render_grid(grid, player, "Your crew is already full!")
        await interaction.response.edit_message(embed=_embed(content), content=None,
                                                view=_game_view(guild_id, user_id, player, grid=grid))
        return

    npc_name = state["npc_name"]
    npc_x = state["npc_x"]
    npc_y = state["npc_y"]
    village_id = state["village_id"]
    village_wx = state["village_wx"]
    village_wy = state["village_wy"]
    seed_val = state["seed"]

    # Hire the crew member
    slot = await hire_crew_member(db, user_id, npc_name)

    # Remove NPC from this player's view (replace with grass)
    await set_player_village_override(db, user_id, village_id, npc_x, npc_y, "vil_grass")

    # Place a replacement non-recruitable villager somewhere else in the village
    rep_pos = await get_replacement_npc_position(
        village_id, village_wx, village_wy, seed_val, user_id, npc_x, npc_y, db
    )
    if rep_pos is not None:
        await set_player_village_override(db, user_id, village_id, rep_pos[0], rep_pos[1], "vil_villager")

    _invalidate_vp(user_id)
    grid = await _cached_grid(user_id, player, seed, db)
    content = render_grid(grid, player,
        f"⚓ **{npc_name}** joins your crew! (slot {slot}) "
        f"Assign them tasks from the ship's below deck.")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


async def handle_village_recruit_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Player cancelled recruiting a village NPC."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    _ui_state.pop(user_id, None)
    grid = await _cached_grid(user_id, player, seed, db)
    content = render_grid(grid, player, "\"Safe travels, stranger.\"")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


# ── Merchant quest offer ──────────────────────────────────────────────────────

async def handle_merchant_quest_offer(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Called when player presses the Quest button inside a merchant encounter."""
    db = await get_database(guild_id)
    seed = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    merch_quest = state.get("merch_quest")
    if merch_quest is None:
        from dwarf_explorer.game.quests import generate_merchant_quest
        merch_quest = await generate_merchant_quest(db, seed, player.world_x, player.world_y)
        if merch_quest is None:
            await interaction.response.edit_message(
                embed=_embed("\U0001f9d1 The merchant shrugs. 'No deliveries today.'"),
                content=None, view=MerchantView(guild_id, user_id),
            )
            return
        _ui_state[user_id]["merch_quest"] = merch_quest
    from dwarf_explorer.game.quests import get_active_quest_count, MAX_PLAYER_QUESTS, get_active_quests
    from dwarf_explorer.ui.quest_view import QuestOfferView, render_quest_offer, QuestSwapView, render_quest_swap
    count = await get_active_quest_count(db, user_id)
    if count >= MAX_PLAYER_QUESTS:
        active  = await get_active_quests(db, user_id)
        content = await render_quest_swap(active, merch_quest)
        _ui_state[user_id]["type"] = "merch_swap"
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=QuestSwapView(guild_id, user_id, len(active)),
        )
    else:
        content = render_quest_offer(merch_quest, "Travelling Merchant")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=QuestOfferView(guild_id, user_id),
        )


async def handle_quest_offer_accept(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})

    # Handle elder/NPC quest offer (quest_offer type with quest_id)
    if state.get("type") == "quest_offer" and state.get("quest_id"):
        from dwarf_explorer.game.quests import accept_quest
        quest_id = state["quest_id"]
        _is_main = state.get("is_main_quest", False)
        _fq_hwx  = state.get("fq_hermit_wx")
        _fq_hwy  = state.get("fq_hermit_wy")
        accepted = await accept_quest(db, user_id, quest_id, source_type="tree_city_elder",
                                      is_main_quest=_is_main,
                                      bounty_wx=_fq_hwx, bounty_wy=_fq_hwy)
        # If this was the Forest Depths quest, also set fq_quest_stage → seek_hermit
        if accepted and _fq_hwx is not None:
            player.fq_quest_stage = "seek_hermit"
            await db.execute(
                "UPDATE players SET fq_quest_stage='seek_hermit' WHERE user_id=?", (user_id,)
            )
        _ui_state.pop(user_id, None)
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        if accepted:
            from dwarf_explorer.ui.quest_view import QuestView, render_unified_quest_list
            from dwarf_explorer.game.quests import get_main_quests
            if _is_main:
                _upd = await get_main_quests(db, user_id)
                _tab = "main"
            else:
                _upd = await get_active_quests(db, user_id)
                _tab = "side"
            _new_idx = max(0, len(_upd) - 1)
            _ui_state[user_id] = {"type": "quest_log", "quest_index": _new_idx, "tab": _tab}
            content = "✅ Quest accepted!\n\n" + await render_unified_quest_list(db, user_id, _tab, _new_idx)
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=QuestView(guild_id, user_id, tab=_tab, quest_index=_new_idx),
            )
        else:
            content = render_grid(grid, player, "⚠️ Could not accept quest (already accepted or log full).")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
        return

    merch_quest = state.get("merch_quest")
    if not merch_quest:
        return
    from dwarf_explorer.game.quests import accept_quest
    _is_main = state.get("is_main_quest", False)
    ok = await accept_quest(db, user_id, merch_quest["id"], source_type="merchant",
                            is_main_quest=_is_main)
    if ok:
        await add_to_inventory(db, user_id, "merchant_parcel", 1)
        _ui_state.pop(user_id, None)
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player,
                              f"\U0001f4cb Quest accepted: **{merch_quest['title']}**")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
    else:
        await interaction.response.edit_message(
            embed=_embed("Quest log full."), content=None,
            view=MerchantView(guild_id, user_id),
        )


async def handle_quest_offer_decline(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    state.pop("merch_quest", None)
    state["type"] = "merchant"
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    catalog = state.get("catalog", [])
    content = _render_merchant(catalog, state.get("selected", 0), player)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=MerchantView(guild_id, user_id))


async def handle_qswap(
    interaction: discord.Interaction, guild_id: int, user_id: int, quest_slot: int
) -> None:
    """Cancel active quest at slot, then accept merchant quest."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    merch_quest = state.get("merch_quest")
    if not merch_quest:
        return
    from dwarf_explorer.game.quests import get_active_quests, cancel_quest, accept_quest
    active = await get_active_quests(db, user_id)
    if quest_slot >= len(active):
        return
    pq = active[quest_slot]
    await cancel_quest(db, user_id, pq["pq_id"])
    if pq.get("quest_subtype") == "delivery":
        await remove_from_inventory(db, user_id, "merchant_parcel", 1)
    ok = await accept_quest(db, user_id, merch_quest["id"], source_type="merchant")
    if ok:
        await add_to_inventory(db, user_id, "merchant_parcel", 1)
        _ui_state.pop(user_id, None)
        seed = await get_or_create_world(db, guild_id)
        grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player,
                              f"\U0001f4cb Quest accepted: **{merch_quest['title']}**")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
    # else: no quest offered — nothing to do


async def handle_qswap_pass(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _ui_state.get(user_id, {})
    state.pop("merch_quest", None)
    state["type"] = "merchant"
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    catalog = state.get("catalog", [])
    content = _render_merchant(catalog, state.get("selected", 0), player)
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=MerchantView(guild_id, user_id))


# ── Tavern handlers ───────────────────────────────────────────────────────────

async def handle_tavern_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int, item_id: str
) -> None:
    """Buy a single food/drink item from the tavern barkeep."""
    from dwarf_explorer.config import TAVERN_MENU
    from dwarf_explorer.database.repositories import add_to_inventory

    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    item = next((i for i in TAVERN_MENU if i["id"] == item_id), None)
    if item is None:
        return

    cost = item["price"]
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)

    if user_id != ADMIN_PLAYER_ID and player.gold < cost:
        content = render_grid(grid, player,
            f"\"You don't have enough coin for that.\" (need {cost}🪙, have {player.gold}🪙)")
    else:
        if user_id != ADMIN_PLAYER_ID:
            player.gold -= cost
            await db.execute("UPDATE players SET gold=? WHERE user_id=?", (player.gold, user_id))
        await add_to_inventory(db, user_id, item_id, 1)
        content = render_grid(grid, player,
            f"\"Enjoy your {item['name']}!\" 🍺 Bought 1× {item['name']} for {cost}🪙.")

    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=TavernBuyView(guild_id, user_id),
    )


async def handle_tavern_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Close the tavern menu and return to the building view."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "You step away from the bar.")
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


# ── NPC Dialogue handlers ─────────────────────────────────────────────────────

def _render_dialogue(npc_name: str, text: str, options: list[dict], selected: int) -> str:
    """Render NPC dialogue as text block with option list."""
    lines = [f"**{npc_name}** says:", f'> *"{text}"*', ""]
    for i, opt in enumerate(options):
        prefix = "▶ " if i == selected else "  "
        lines.append(f"{prefix}**{opt['label']}**")
    return "\n".join(lines)


async def handle_crew_npc_talk(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open dialogue with harbour tavern crew recruit NPC."""
    import random as _rand_mod
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    crew = await get_ship_crew(db, user_id)
    crew_count = len(crew)

    # Pick a deterministic name for this NPC based on their house tile position
    _seed = hash((user_id, player.house_id, player.house_x, player.house_y))
    npc_name = CREW_NAMES[abs(_seed) % len(CREW_NAMES)]

    if crew_count >= MAX_CREW_SIZE:
        options = [{"label": "Maybe next time", "action": "close"}]
        npc_text = f"Yer ship's already got a full crew! I'd only be in the way."
    else:
        options = [
            {"label": f"Hire for {CREW_HIRE_COST}🪙", "action": "hire_crew"},
            {"label": "Not right now", "action": "close"},
        ]
        npc_text = (
            f"Aye, I'm lookin' for work! I can join yer crew for {CREW_HIRE_COST} gold. "
            f"Just say the word and I'll be on yer ship. "
            f"(Crew: {crew_count}/{MAX_CREW_SIZE})"
        )

    state = {
        "type": "npc_dialogue",
        "npc_type": "crew_recruit",
        "npc_name": npc_name,
        "text": npc_text,
        "options": options,
        "selected": 0,
    }
    _ui_state[user_id] = state
    content = _render_dialogue(npc_name, npc_text, options, 0)
    view = DialogueView(guild_id, user_id, options, 0)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_dialogue_nav(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: int
) -> None:
    """Scroll dialogue option up (-1) or down (+1)."""
    state = _ui_state.get(user_id, {})
    if state.get("type") != "npc_dialogue":
        return
    options = state.get("options", [])
    sel = state.get("selected", 0)
    sel = max(0, min(len(options) - 1, sel + direction))
    state["selected"] = sel
    _ui_state[user_id] = state
    content = _render_dialogue(state["npc_name"], state["text"], options, sel)
    view = DialogueView(guild_id, user_id, options, sel)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def _dialogue_return_to_view(
    interaction: discord.Interaction, guild_id: int, user_id: int,
    player, ctx: str, db, msg: str
) -> None:
    """Return to the correct game view after closing a dialogue, based on context."""
    seed = await get_or_create_world(db, guild_id)
    if ctx == "bandit_camp" and getattr(player, "in_bandit_camp", False):
        from dwarf_explorer.world.bandit_camp import load_camp_viewport as _lbcv_dlg
        _bc_row_dlg = await db.fetch_one(
            "SELECT world_x, world_y FROM bandit_camps WHERE id=?", (player.bandit_camp_id,)
        )
        if _bc_row_dlg:
            bc_grid = _lbcv_dlg(player.bc_x, player.bc_y, int(_bc_row_dlg["world_x"]), int(_bc_row_dlg["world_y"]))
        else:
            bc_grid = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(bc_grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=bc_grid),
        )
        return
    if ctx == "tree_city" and getattr(player, "in_tree_city", False):
        from dwarf_explorer.world.forest import load_tree_city_viewport as _ltcv_dlg
        grid = await _ltcv_dlg(player.tc_forest_id, player.tc_floor, player.tc_x, player.tc_y, db)
        content = render_grid(grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
    elif ctx == "rift" and player.in_cave:
        from dwarf_explorer.world.caves import load_cave_viewport as _lcv_dlg
        grid = await _lcv_dlg(player.cave_id, player.cave_x, player.cave_y, db)
        content = render_grid(grid, player, msg)
        view = await _cave_game_view(guild_id, user_id, player, db, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
    elif ctx == "village" and player.in_village:
        grid = await load_village_viewport(
            player.village_id, player.village_x, player.village_y, db, user_id=user_id
        )
        content = render_grid(grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
    else:
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
        content = render_grid(grid, player, msg)
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )


async def handle_dialogue_confirm(
    interaction: discord.Interaction, guild_id: int, user_id: int, action: str
) -> None:
    """Execute the confirmed dialogue option action."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})

    if action == "close" or state.get("type") != "npc_dialogue":
        _ui_state.pop(user_id, None)
        ctx = state.get("context", "building") if state else "building"
        await _dialogue_return_to_view(interaction, guild_id, user_id, player, ctx, db, "Farewell.")
        return

    if action == "lore":
        # Show lore text response; keep options available for further interaction
        lore_text = state.get("lore_text", "I have nothing more to say.")
        options = state.get("options", [])
        sel = state.get("selected", 0)
        state["text"] = lore_text
        _ui_state[user_id] = state
        content = _render_dialogue(state["npc_name"], lore_text, options, sel)
        view = DialogueView(guild_id, user_id, options, sel)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if action == "rumors":
        rumors_text = state.get("rumors_text", "I haven't heard anything worth mentioning lately.")
        options = state.get("options", [])
        sel = state.get("selected", 0)
        state["text"] = rumors_text
        _ui_state[user_id] = state
        content = _render_dialogue(state["npc_name"], rumors_text, options, sel)
        view = DialogueView(guild_id, user_id, options, sel)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    if action == "bribe" and state.get("npc_type") == "bc_bandit":
        # Open bribe modal — opens BribeModal but in camp context
        _ui_state.pop(user_id, None)
        await interaction.response.send_modal(_BandtCampBribeModal(guild_id, user_id))
        return

    if action == "elder_main_quest":
        _ui_state.pop(user_id, None)
        await _open_tree_city_elder(interaction, guild_id, user_id, player)
        return

    if action == "quest_pool":
        pool = state.get("quest_pool", [])
        source_label = state.get("source_label", "Villager")
        _ui_state.pop(user_id, None)
        if pool:
            await handle_open_quest_pool(
                interaction, guild_id, user_id,
                pool=pool,
                source_label=source_label,
                source_type="village_npc",
            )
        else:
            ctx = state.get("context", "building")
            await _dialogue_return_to_view(interaction, guild_id, user_id, player, ctx, db, "I have no work for you right now.")
        return

    if action == "hire_crew":
        npc_name = state.get("npc_name", "Sailor")
        crew = await get_ship_crew(db, user_id)
        if len(crew) >= MAX_CREW_SIZE:
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player, "Your crew is already full!")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return
        if user_id != ADMIN_PLAYER_ID and player.gold < CREW_HIRE_COST:
            grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
            content = render_grid(grid, player,
                f"\"You don't have enough coin, friend.\" (need {CREW_HIRE_COST}🪙, have {player.gold}🪙)")
            await interaction.response.edit_message(
                embed=_embed(content), content=None,
                view=_game_view(guild_id, user_id, player, grid=grid),
            )
            return
        if user_id != ADMIN_PLAYER_ID:
            player.gold -= CREW_HIRE_COST
            await update_player_stats(db, user_id, gold=player.gold)
        slot = await hire_crew_member(db, user_id, npc_name)
        _ui_state.pop(user_id, None)
        grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
        content = render_grid(grid, player,
            f"⚓ **{npc_name}** joins your crew! (slot {slot}) "
            f"Assign them tasks from below deck. (-{CREW_HIRE_COST}🪙)")
        await interaction.response.edit_message(
            embed=_embed(content), content=None,
            view=_game_view(guild_id, user_id, player, grid=grid),
        )
        return

    # Unknown action — close
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "Goodbye.")
    _ui_state.pop(user_id, None)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


async def handle_dialogue_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel NPC dialogue and return to the appropriate view."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.pop(user_id, {})
    ctx = state.get("context", "building")
    await _dialogue_return_to_view(interaction, guild_id, user_id, player, ctx, db, "You end the conversation.")


# ── Ship crew management handlers ─────────────────────────────────────────────

def _render_crew(crew: list[dict]) -> str:
    """Render crew list with task assignments."""
    from dwarf_explorer.config import CREW_TASKS, MAX_CREW_SIZE
    lines = [f"**👥 Ship Crew** ({len(crew)}/{MAX_CREW_SIZE})", ""]
    if not crew:
        lines.append("*No crew hired yet. Visit a harbour tavern to recruit sailors.*")
    for m in crew:
        task_info = CREW_TASKS.get(m["task"], CREW_TASKS["idle"])
        lines.append(
            f"**Slot {m['slot']}** — ⚓ {m['name']}"
            f"\n    {task_info['emoji']} **{task_info['label']}**: {task_info['desc']}"
        )
        lines.append("")
    lines.append("Press a task button to cycle through assignments. 🔥 Fire dismisses the crew member.")
    return "\n".join(lines)


async def handle_ship_crew_view(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Open crew management view from below deck."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    crew = await get_ship_crew(db, user_id)
    content = _render_crew(crew)
    view = CrewView(guild_id, user_id, crew)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_crew_task_cycle(
    interaction: discord.Interaction, guild_id: int, user_id: int, slot: int
) -> None:
    """Cycle through available tasks for a crew member slot."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    crew = await get_ship_crew(db, user_id)
    member = next((m for m in crew if m["slot"] == slot), None)
    if not member:
        return
    task_keys = list(CREW_TASKS.keys())
    cur_idx = task_keys.index(member["task"]) if member["task"] in task_keys else 0
    next_task = task_keys[(cur_idx + 1) % len(task_keys)]
    await set_crew_task(db, user_id, slot, next_task)
    # Refresh crew list
    crew = await get_ship_crew(db, user_id)
    content = _render_crew(crew)
    view = CrewView(guild_id, user_id, crew)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_crew_fire(
    interaction: discord.Interaction, guild_id: int, user_id: int, slot: int
) -> None:
    """Dismiss crew member at the given slot."""
    db = await get_database(guild_id)
    await get_or_create_player(db, user_id, interaction.user.display_name)
    await fire_crew_member(db, user_id, slot)
    crew = await get_ship_crew(db, user_id)
    content = _render_crew(crew)
    view = CrewView(guild_id, user_id, crew)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_crew_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Return to lower deck from crew view."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    from dwarf_explorer.game.renderer import render_ship_room
    content = render_ship_room(player)
    view = ShipView(guild_id, user_id, room="lower_deck",
                    ship_hp=player.ship_hp, ship_max_hp=player.ship_max_hp)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Hospital handlers ─────────────────────────────────────────────────────────

async def handle_heal_accept(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Player accepts the healer's offer — deduct gold, restore HP."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    state = _ui_state.get(user_id, {})
    cost = state.get("heal_cost", 0)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)

    max_hp = getattr(player, "max_hp", 100)
    if user_id != ADMIN_PLAYER_ID and player.gold < cost:
        content = render_grid(grid, player,
            f"\"I'm afraid you don't have the coin.\" (need {cost}🪙, have {player.gold}🪙)")
    elif player.hp >= max_hp:
        content = render_grid(grid, player, "\"You are already in perfect health!\"")
    else:
        if user_id != ADMIN_PLAYER_ID:
            player.gold -= cost
        player.hp = max_hp
        await db.execute("UPDATE players SET gold=?, hp=? WHERE user_id=?",
                         (player.gold, player.hp, user_id))
        content = render_grid(grid, player,
            f"✨ The healer tends your wounds. You are fully restored! (-{cost}🪙)")

    _ui_state.pop(user_id, None)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


async def handle_heal_decline(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Player declines the healer's offer."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "\"Come back if you change your mind.\"")
    _ui_state.pop(user_id, None)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


# ── Lumber convert handlers ─────────────────────────────────────────────────

async def handle_lumber_convert_confirm(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Convert all logs in inventory to planks (2 planks per log)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    inv_items = await get_inventory(db, user_id)
    log_count = sum(it["quantity"] for it in inv_items if it["item_id"] == "log")
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    if log_count <= 0:
        content = render_grid(grid, player, '"No logs to convert."')
    else:
        plank_count = log_count * 2
        await remove_from_inventory(db, user_id, "log", log_count)
        await add_to_inventory(db, user_id, "plank", plank_count)
        content = render_grid(grid, player,
            f"🪵 Converted **{log_count} logs** into **{plank_count} planks**!")
    _ui_state.pop(user_id, None)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


async def handle_lumber_convert_cancel(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Cancel lumber conversion."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "Come back when you're ready.")
    _ui_state.pop(user_id, None)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


async def _add_canoe_to_inventory(db, user_id: int) -> None:
    """Add a canoe to the player's inventory. Delegates to add_canoe_pair, which
    inserts a single 'canoe' row at a slot that leaves room for the visual
    two-cell pair on the same display row.
    """
    from dwarf_explorer.database.repositories import add_canoe_pair
    await add_canoe_pair(db, user_id)
    # db auto-commits on execute(); no explicit commit needed


async def handle_lumber_craft_canoe(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Craft a canoe from 18 planks (one canoe max, does not stack)."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    inv_items = await get_inventory(db, user_id)
    log_count = sum(it["quantity"] for it in inv_items if it["item_id"] == "log")
    plank_count = sum(it["quantity"] for it in inv_items if it["item_id"] == "plank")
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    if plank_count < 18:
        content = render_grid(grid, player, f"You need **18 planks** to build a canoe. You have {plank_count}.")
        view = LumberConvertView(guild_id, user_id, log_count, plank_count)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return
    await remove_from_inventory(db, user_id, "plank", 18)
    # Add canoe as 2-piece: canoe_left in next slot, canoe_right in the slot after.
    # add_canoe_pair always inserts new slot rows, so each crafted canoe lives
    # in its own pair of slots — canoes never stack.
    await _add_canoe_to_inventory(db, user_id)
    content = render_grid(grid, player,
        "🛶 The mill worker shapes the planks into a **canoe**! "
        "Equip the left piece and stand next to a river to embark.")
    _ui_state.pop(user_id, None)
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


# ── Lumbermill conveyor insert handler ─────────────────────────────────────
#
# Conveyor column is at building x=3 (conv_x), running y=1..H-2 (top_y..bot_y).
# Log enters at (3, 1), travels one tile per second, gets sawed at (3, saw_y),
# and arrives as planks at (3, H-2).
#
# The animation runs INSIDE the viewport: each frame we load a fresh grid and
# replace the current log/plank tile with "b_log_moving" (renders as 🪵) before
# calling render_grid.  Everything else in the mill renders normally.
#
# Planks are NOT auto-deposited — player walks to 📤 and interacts to collect.

_LM_CONV_X   = 3   # building X of conveyor column (must match villages.py conv_x)
_LM_TOP_Y    = 1   # first interior row (log input)
_LM_BOT_Y    = 7   # last interior row (plank output)  — assumes 9-tall building
_LM_SAW_Y    = 4   # saw row (aligns with small gear; middle of 9-tall interior)


async def handle_lumbermill_insert(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Player inserts a log — animate it moving through the viewport in real time."""
    import dataclasses

    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    # Check the player has at least one log
    inv_items = await get_inventory(db, user_id)
    log_count = sum(it["quantity"] for it in inv_items if it["item_id"] == "log")

    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)

    if log_count < 1:
        content = render_grid(grid, player, "⚠️ You don't have any logs to insert!")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Prevent concurrent runs
    _lm_key      = f"lm_planks_{user_id}"
    _lm_busy_key = f"lm_busy_{user_id}"
    if _ui_state.get(_lm_busy_key):
        content = render_grid(grid, player, "⚠️ The conveyor is still running!")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    await remove_from_inventory(db, user_id, "log", 1)
    _ui_state[_lm_busy_key] = True

    # Defer — we'll send multiple edits for each frame
    await interaction.response.defer()

    vc = 4  # viewport centre index (9×9 grid, index 4)
    original_house_id = player.house_id

    # Build the frame script. Each entry is (y_position, overlay_tile, status).
    # overlay_tile=None means render the underlying tile (e.g., the saw alone).
    # We insert a "plank emerges at saw" transformation frame right after the
    # saw frame so the moment of transformation is visible at the saw position
    # before the planks travel up to the output.
    frames: list[tuple[int, str | None, str]] = []
    for y in range(_LM_BOT_Y, _LM_SAW_Y, -1):           # 7,6,5  (below saw)
        frames.append((y, "b_log_moving", "⚙️ Log moving toward the saw..."))
    frames.append((_LM_SAW_Y, None, "🪚 Sawing..."))                          # 4: saw alone
    frames.append((_LM_SAW_Y, "b_plank_moving", "🪵 Planks emerging..."))     # 4: planks at saw
    for y in range(_LM_SAW_Y - 1, _LM_TOP_Y - 1, -1):   # 3,2,1  (above saw)
        frames.append((y, "b_plank_moving", "🪵 Planks moving to output..."))

    try:
        for y_step, overlay_tile, status in frames:
            # Re-fetch player each frame so movement is respected. If the player
            # has walked out of the mill (or to a different building), stop
            # editing the message — they're looking at something else now and
            # we shouldn't overwrite their view. The animation continues in the
            # background and the planks will be ready when they return.
            cur_player = await get_or_create_player(db, user_id, interaction.user.display_name)
            in_same_mill = (cur_player.in_house and cur_player.house_id == original_house_id
                            and cur_player.house_type == "lumber_mill")

            if in_same_mill:
                grid = await load_building_viewport(
                    cur_player.house_id, cur_player.house_x, cur_player.house_y, db
                )

                # Calculate where this building tile appears in the 9×9 viewport
                g_row = vc + (y_step      - cur_player.house_y)
                g_col = vc + (_LM_CONV_X  - cur_player.house_x)

                # Overlay the moving item onto the grid if we have one and it's on-screen
                if overlay_tile is not None and 0 <= g_row < len(grid) and 0 <= g_col < len(grid[g_row]):
                    grid[g_row][g_col] = dataclasses.replace(
                        grid[g_row][g_col], terrain=overlay_tile
                    )

                content = render_grid(grid, player=cur_player, status_msg=status)
                try:
                    await interaction.edit_original_response(embed=_embed(content))
                except Exception:
                    # Message may have been superseded by another handler; ignore
                    pass
            await asyncio.sleep(1.0)

        # All done — store planks for manual pickup
        _ui_state[_lm_key] = _ui_state.get(_lm_key, 0) + 3
    finally:
        _ui_state[_lm_busy_key] = False

    # Final frame: only update if player is still in the mill; otherwise leave
    # whatever view they're looking at alone.
    final_player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if final_player.in_house and final_player.house_id == original_house_id:
        grid = await load_building_viewport(
            final_player.house_id, final_player.house_x, final_player.house_y, db
        )
        content = render_grid(
            grid, final_player,
            "✅ **3 planks** are waiting at 📤 — walk to the output and interact to collect."
        )
        view = _game_view(guild_id, user_id, final_player, grid=grid)
        try:
            await interaction.edit_original_response(embed=_embed(content), view=view)
        except Exception:
            pass


async def handle_lumbermill_pickup(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Player collects processed planks from the output box."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)

    _lm_key = f"lm_planks_{user_id}"
    planks_ready = _ui_state.get(_lm_key, 0)

    if planks_ready <= 0:
        content = render_grid(grid, player, "📤 The output tray is empty. Insert a log at 📥 first.")
        view = _game_view(guild_id, user_id, player, grid=grid)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    # Give planks to player
    await add_to_inventory(db, user_id, "plank", planks_ready)
    _ui_state[_lm_key] = 0

    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, f"🤲 Collected **{planks_ready} planks** from the output tray.")
    view = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


# ── Farmer shop handlers ────────────────────────────────────────────────────

async def handle_farmer_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int, item_id: str
) -> None:
    """Buy an item from the farmer shop."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    item = next((i for i in FARMER_SHOP if i["id"] == item_id), None)
    if item is None:
        return
    cost = item["price"]
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    if user_id != ADMIN_PLAYER_ID and player.gold < cost:
        content = render_grid(grid, player,
            f"That'll be {cost}🪙 and you've only got {player.gold}🪙.")
    else:
        if user_id != ADMIN_PLAYER_ID:
            player.gold -= cost
            await db.execute("UPDATE players SET gold=? WHERE user_id=?", (player.gold, user_id))
        await add_to_inventory(db, user_id, item_id, 1)
        content = render_grid(grid, player,
            f"🌾 Bought 1× {item['name']} for {cost}🪙.")
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=FarmerShopView(guild_id, user_id),
    )


async def handle_farmer_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Close the farmer shop."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    grid = await load_building_viewport(player.house_id, player.house_x, player.house_y, db)
    content = render_grid(grid, player, "Come back any time!")
    await interaction.response.edit_message(
        embed=_embed(content), content=None,
        view=_game_view(guild_id, user_id, player, grid=grid),
    )


# ── Tree City Shop handlers ───────────────────────────────────────────────────

async def handle_tree_city_buy(
    interaction: discord.Interaction, guild_id: int, user_id: int, item_id: str
) -> None:
    """Purchase an item from the Tree City market."""
    from dwarf_explorer.config import TREE_CITY_SHOP, ITEM_EMOJI as _ie_tc
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)

    item_def = next((i for i in TREE_CITY_SHOP if i["id"] == item_id), None)
    if item_def is None:
        await interaction.response.send_message("Unknown item.", ephemeral=True)
        return

    price = item_def["price"]
    if player.gold < price:
        from dwarf_explorer.world.forest import load_forest_viewport as _lf_tc
        grid = await _lf_tc(player.forest_id, player.forest_x, player.forest_y, db)
        lines = [f"💰 Not enough gold! Need **{price}** 🪙, you have **{player.gold}**.\n"]
        for it in TREE_CITY_SHOP:
            e = _ie_tc.get(it["id"], "📦")
            lines.append(f"{e} **{it['name']}** — {it['price']} 🪙")
        lines.append(f"\n💰 Your gold: **{player.gold}**")
        content = render_grid(grid, player, "\n".join(lines))
        view = TreeCityShopView(guild_id, user_id, TREE_CITY_SHOP)
        await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
        return

    player.gold -= price
    await db.execute("UPDATE players SET gold=? WHERE user_id=?", (player.gold, user_id))
    await add_to_inventory(db, user_id, item_id, 1)

    from dwarf_explorer.world.forest import load_forest_viewport as _lf_tc2
    grid = await _lf_tc2(player.forest_id, player.forest_x, player.forest_y, db)
    emoji = _ie_tc.get(item_id, "📦")
    lines = [f"✅ Purchased {emoji} **{item_def['name']}** for {price} 🪙!\n"]
    for it in TREE_CITY_SHOP:
        e = _ie_tc.get(it["id"], "📦")
        lines.append(f"{e} **{it['name']}** — {it['price']} 🪙  _{it['description']}_")
    lines.append(f"\n💰 Your gold: **{player.gold}**")
    content = render_grid(grid, player, "\n".join(lines))
    view = TreeCityShopView(guild_id, user_id, TREE_CITY_SHOP)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_tree_city_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Close the tree city shop."""
    db = await get_database(guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    from dwarf_explorer.world.forest import load_forest_viewport as _lf_tc3
    grid = await _lf_tc3(player.forest_id, player.forest_x, player.forest_y, db)
    content = render_grid(grid, player, "🏡 *'Safe travels, wanderer.'*")
    await interaction.response.edit_message(embed=_embed(content), content=None,
                                            view=_game_view(guild_id, user_id, player, grid=grid))


# ── Village puzzle board ───────────────────────────────────────────────────────

def _puzzle_content(state: dict, extra: str = "") -> str:
    """Render puzzle board + status into a message string."""
    from dwarf_explorer.game.ricochet import render_board
    puzzle = state["puzzle"]
    board  = render_board(puzzle, state["px"], state["py"])
    moves  = state["moves"]
    opt    = puzzle.get("min_moves", "?")
    lines  = [
        "🎮 **Village Puzzle Board**",
        board,
        f"Moves: **{moves}** | Optimal: **{opt}**",
        "*Slide 🔵 onto 🔴 using walls and 🟧 blocks.*",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def _next_puzzle_seed(daily_seed: int, user_id: int, solve_count: int) -> int:
    """Deterministic seed for puzzle N solved by this player today."""
    return (daily_seed * 1_000_003 + user_id * 999_983 + solve_count * 99_991) & 0xFFFF_FFFF


async def _open_puzzle(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    """Initialise and display the daily puzzle."""
    from dwarf_explorer.game.ricochet import generate_puzzle
    puzzle = generate_puzzle()          # seed = today's date
    state: dict = {
        "puzzle":      puzzle,
        "px":          puzzle["start"][0],
        "py":          puzzle["start"][1],
        "moves":       0,
        "solve_count": 0,
        "daily_seed":  puzzle["seed"],
    }
    _PUZZLE_STATES[(guild_id, user_id)] = state
    content = _puzzle_content(state)
    view = PuzzleView(guild_id, user_id, moves=0, min_moves=puzzle["min_moves"],
                      claim_available=False)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_puzzle_move(
    interaction: discord.Interaction, guild_id: int, user_id: int, direction: str
) -> None:
    state = _PUZZLE_STATES.get((guild_id, user_id))
    if state is None:
        await _open_puzzle(interaction, guild_id, user_id)
        return

    from dwarf_explorer.game.ricochet import apply_move, generate_puzzle
    puzzle = state["puzzle"]
    nx, ny = apply_move(
        state["px"], state["py"], direction,
        puzzle["obstacles"], puzzle["size"],
    )
    if nx == state["px"] and ny == state["py"]:
        return

    state["px"], state["py"] = nx, ny
    state["moves"] += 1
    tx, ty = puzzle["target"]

    if nx == tx and ny == ty:
        # ── Puzzle solved ────────────────────────────────────────────────────
        solved_in  = state["moves"]
        solve_count = state.get("solve_count", 0) + 1

        # Auto-claim daily reward on first solve
        from dwarf_explorer.database.repositories import claim_puzzle_reward, give_quest_reward
        db = await get_database(guild_id)
        reward_line = ""
        ok = await claim_puzzle_reward(db, user_id)
        if ok:
            rs = await give_quest_reward(db, user_id, 15, 75)
            reward_line = f"🎁 Daily reward: {rs}  •  "

        # Generate the next puzzle immediately
        next_seed   = _next_puzzle_seed(state["daily_seed"], user_id, solve_count)
        next_puzzle = generate_puzzle(next_seed)
        state.update({
            "puzzle":      next_puzzle,
            "px":          next_puzzle["start"][0],
            "py":          next_puzzle["start"][1],
            "moves":       0,
            "solve_count": solve_count,
        })

        extra   = f"{reward_line}Solved in **{solved_in}** moves! Here's the next one."
        content = _puzzle_content(state, extra)
        view    = PuzzleView(guild_id, user_id, moves=0, min_moves=next_puzzle["min_moves"],
                             claim_available=False)
    else:
        content = _puzzle_content(state)
        view    = PuzzleView(guild_id, user_id,
                             moves=state["moves"], min_moves=puzzle["min_moves"],
                             claim_available=False)

    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_puzzle_reset(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    state = _PUZZLE_STATES.get((guild_id, user_id))
    if state is None:
        await _open_puzzle(interaction, guild_id, user_id)
        return
    puzzle = state["puzzle"]
    state["px"], state["py"] = puzzle["start"]
    state["moves"] = 0
    content = _puzzle_content(state)
    view = PuzzleView(guild_id, user_id, moves=0, min_moves=puzzle["min_moves"],
                      claim_available=False)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)


async def handle_puzzle_close(
    interaction: discord.Interaction, guild_id: int, user_id: int
) -> None:
    _PUZZLE_STATES.pop((guild_id, user_id), None)
    db = await get_database(guild_id)
    seed   = await get_or_create_world(db, guild_id)
    player = await get_or_create_player(db, user_id, interaction.user.display_name)
    if player.in_village:
        grid    = await load_village_viewport(
            player.village_id, player.village_x, player.village_y, db, user_id=user_id
        )
        content = render_grid(grid, player, "")
        view    = _game_view(guild_id, user_id, player, grid=grid)
    else:
        grid    = await load_viewport(player.world_x, player.world_y, seed, db)
        content = render_grid(grid, player)
        view    = _game_view(guild_id, user_id, player, grid=grid)
    await interaction.response.edit_message(embed=_embed(content), content=None, view=view)
