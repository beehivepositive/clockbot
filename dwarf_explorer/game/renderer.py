import math

from dwarf_explorer.config import (
    TERRAIN_EMOJI, STRUCTURE_EMOJI, ENTITY_EMOJI, ITEM_EMOJI,
    CAVE_EMOJI, VILLAGE_EMOJI, BUILDING_EMOJI, SHIP_EMOJI, POUCH_SIZES,
    EQUIP_BONUSES, SHIPWRECK_EMOJI, BREATH_MAX, SKY_EMOJI, TEMPLE_EMOJI,
    FOREST_EMOJI, TC_EMOJI, WORLD_SIZE, OCEAN_SIZE,
    BANDIT_CAMP_EMOJI, RUINS_EMOJI,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.game.player import Player

_BLACK = "\u2B1B"   # ⬛ — darkness tile
_FOV_RADIUS = 3.0   # torch illumination radius in tiles


def _tile_emoji(tile: TileData, location: str = "wilderness") -> str:
    if location == "ship":
        return SHIP_EMOJI.get(tile.terrain, "\u2B1B")
    if location == "island":
        return _ISLAND_TERRAIN_EMOJI.get(tile.terrain, "🌊")
    if location == "cave":
        return CAVE_EMOJI.get(tile.terrain, _BLACK)
    if location == "shipwreck":
        return SHIPWRECK_EMOJI.get(tile.terrain, _BLACK)
    if location == "sky":
        return SKY_EMOJI.get(tile.terrain, SKY_EMOJI.get("sky_void", "🌌"))
    if location == "temple":
        return TEMPLE_EMOJI.get(tile.terrain, "🧱")
    if location == "forest":
        return FOREST_EMOJI.get(tile.terrain, FOREST_EMOJI["fst_tree"])
    if location == "maze":
        return FOREST_EMOJI.get(tile.terrain, FOREST_EMOJI["maze_wall"])
    if location == "tree_city":
        return TC_EMOJI.get(tile.terrain, TC_EMOJI.get("tc_wall", "\U0001F332"))
    if location == "grove":
        from dwarf_explorer.config import GROVE_EMOJI as _GE
        return _GE.get(tile.terrain, _GE.get("grove_wall", "\U0001F333"))
    if location == "bandit_camp":
        return BANDIT_CAMP_EMOJI.get(tile.terrain, _BLACK)
    if location == "ruins":
        return RUINS_EMOJI.get(tile.terrain, _BLACK)
    if location == "village":
        return VILLAGE_EMOJI.get(tile.terrain, _BLACK)
    if location in ("house", "church", "bank", "shop", "blacksmith",
                    "tavern", "hospital", "lumber_mill", "farmhouse", "player_house",
                    "armory", "hermit_hut"):
        # Wood floors for cozy buildings; stone/grey for blacksmith
        if tile.terrain == "b_floor" and location != "blacksmith":
            return BUILDING_EMOJI.get("b_floor_wood", BUILDING_EMOJI.get("b_floor", _BLACK))
        return BUILDING_EMOJI.get(tile.terrain, _BLACK)
    # Wilderness: structure > enemy > item > terrain
    if tile.structure and tile.structure in STRUCTURE_EMOJI:
        return STRUCTURE_EMOJI[tile.structure]
    if tile.enemy and tile.enemy in ENTITY_EMOJI:
        return ENTITY_EMOJI[tile.enemy]
    # Drop/canoe box tiles render their box emoji even though ground_items
    # are also indexed at that coord — items are conceptually inside the box.
    if tile.terrain in ("drop_box", "canoe_box"):
        return TERRAIN_EMOJI.get(tile.terrain, _BLACK)
    if tile.ground_item and tile.ground_item in ITEM_EMOJI:
        return ITEM_EMOJI[tile.ground_item]
    return TERRAIN_EMOJI.get(tile.terrain, _BLACK)


def render_grid(grid: list[list[TileData]], player: Player, status_msg: str = "",
                other_players: list[tuple[int, int, str]] | None = None,
                cursor_pos: tuple[int, int] | None = None,
                quest_markers: list[tuple[int, int, str]] | None = None,
                nav_target: tuple[int, int] | None = None) -> str:
    """Render viewport with player at centre, plus status bar.

    Viewport size is inferred from the grid dimensions so caves/buildings
    (7×7) and wilderness (9×9) both render correctly.

    Cave FOV rules:
    - Torch equipped: tiles within _FOV_RADIUS tiles of player are lit; rest = ⬛
    - No torch, on entrance: player icon visible, rest = ⬛
    - No torch, elsewhere: everything = ⬛ (player cannot see themselves)

    other_players: list of (world_x, world_y, display_name) for nearby players.
    Only rendered in overworld view.

    quest_markers: list of (world_x, world_y, target_id) for personal quest
    location markers. Rendered as enemy or investigation emoji in wilderness view.
    """
    if player.in_ship:
        location = "ship"
    elif player.in_island:
        location = "island"
    elif player.in_house:
        location = player.house_type  # "house" | "church" | "bank" | "shop"
    elif player.in_village:
        location = getattr(player, "village_type", "village")
    elif getattr(player, "in_hermit_hut", False):
        location = "hermit_hut"
    elif player.in_cave:
        location = "cave"
    elif getattr(player, "in_shipwreck", False):
        location = "shipwreck"
    elif getattr(player, "in_temple", False):
        location = "temple"
    elif getattr(player, "in_sky", False):
        location = "sky"
    elif getattr(player, "in_tree_city", False):
        location = "tree_city"
    elif getattr(player, "in_maze", False):
        location = "maze"
    elif getattr(player, "in_grove", False):
        location = "grove"
    elif getattr(player, "in_forest_quest", False):
        location = "forest_quest"
    elif getattr(player, "in_forest", False):
        location = "forest"
    elif getattr(player, "in_bandit_camp", False):
        location = "bandit_camp"
    else:
        location = "wilderness"

    vp_size   = len(grid)
    vp_center = vp_size // 2

    # Build other-player viewport positions (overworld only)
    _other_pos: set[tuple[int, int]] = set()
    if other_players and location == "wilderness":
        for ox, oy, _ in other_players:
            col = ox - player.world_x + vp_center
            row = oy - player.world_y + vp_center
            if 0 <= col < vp_size and 0 <= row < vp_size:
                _other_pos.add((col, row))

    # Build personal quest-marker viewport positions (overworld only)
    # target_id is an enemy type (wolf/bear/…) or structure type (ruins/shrine/…)
    _quest_vp: dict[tuple[int, int], str] = {}
    if quest_markers and location == "wilderness":
        for qx, qy, target_id in quest_markers:
            col = qx - player.world_x + vp_center
            row = qy - player.world_y + vp_center
            if 0 <= col < vp_size and 0 <= row < vp_size:
                emoji = ENTITY_EMOJI.get(target_id, "\U0001F50D")  # 🔍 fallback
                _quest_vp[(col, row)] = emoji

    # Nav target edge indicator — compute which edge cell to mark with 🟠
    _nav_edge: tuple[int, int] | None = None  # (col, row) in viewport coords
    if nav_target and location in ("wilderness", "ocean", "high_seas"):
        px = player.ocean_x if (player.in_ocean or player.in_high_seas) else player.world_x
        py = player.ocean_y if (player.in_ocean or player.in_high_seas) else player.world_y
        tx, ty = nav_target
        dx, dy = tx - px, ty - py
        if dx != 0 or dy != 0:
            half = vp_center  # 4 for 9×9
            if abs(dx) >= abs(dy):
                # Left or right edge
                edge_col = 0 if dx < 0 else vp_size - 1
                edge_row = max(0, min(vp_size - 1, int(round(half + (dy / abs(dx)) * half))))
            else:
                # Top or bottom edge
                edge_row = 0 if dy < 0 else vp_size - 1
                edge_col = max(0, min(vp_size - 1, int(round(half + (dx / abs(dy)) * half))))
            _nav_edge = (edge_col, edge_row)

    # Cave visibility pre-computation
    torch_on    = False
    on_entrance = False
    _lava_lit: set[tuple[int, int]] = set()   # tiles lit by nearby lava (no torch needed)
    if location == "cave":
        # Torch required for both regular and lava caves; lava tiles emit local light
        torch_on    = (player.hand_1 == "torch" or player.hand_2 == "torch")
        on_entrance = grid[vp_center][vp_center].terrain == "cave_entrance"
        # In lava caves, lava_pool tiles and their 4 cardinal neighbours are always visible
        if player.cave_lit:
            for _ry in range(vp_size):
                for _cx in range(vp_size):
                    if grid[_ry][_cx].terrain == "lava_pool":
                        _lava_lit.add((_cx, _ry))
                        for _ddx, _ddy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                            _nx, _ny = _cx + _ddx, _ry + _ddy
                            if 0 <= _nx < vp_size and 0 <= _ny < vp_size:
                                _lava_lit.add((_nx, _ny))

    _player_emoji = getattr(player, "avatar_emoji", None) or ENTITY_EMOJI["player"]

    lines: list[str] = []
    for row_y in range(vp_size):
        row_emojis: list[str] = []
        for col_x in range(vp_size):
            is_center = (col_x == vp_center and row_y == vp_center)

            if location == "cave":
                dist = math.hypot(col_x - vp_center, row_y - vp_center)
                lava_visible = (col_x, row_y) in _lava_lit
                if is_center:
                    # Show player if torch on, on entrance, or standing near lava
                    if torch_on or on_entrance or lava_visible:
                        row_emojis.append(_player_emoji)
                    else:
                        row_emojis.append(_BLACK)
                else:
                    if (torch_on and dist <= _FOV_RADIUS) or lava_visible:
                        row_emojis.append(_tile_emoji(grid[row_y][col_x], location="cave"))
                    else:
                        row_emojis.append(_BLACK)
            elif location == "shipwreck":
                # Shipwreck is fully visible (bioluminescent water light)
                if is_center:
                    row_emojis.append(_player_emoji)
                else:
                    row_emojis.append(_tile_emoji(grid[row_y][col_x], location="shipwreck"))
            else:  # non-cave location
                if is_center:
                    if (player.in_ocean or player.in_high_seas) and not player.in_ship:
                        row_emojis.append(ENTITY_EMOJI["player_boat"])
                    elif getattr(player, "in_canoe", False):
                        row_emojis.append(_ITEM_SLOT_EMOJI.get("canoe_whole", _player_emoji))
                    else:
                        row_emojis.append(_player_emoji)
                elif (col_x, row_y) in _other_pos:
                    row_emojis.append(ENTITY_EMOJI.get("npc", "\U0001F9D1"))
                elif (col_x, row_y) in _quest_vp:
                    row_emojis.append(_quest_vp[(col_x, row_y)])
                elif _nav_edge and (col_x, row_y) == _nav_edge:
                    row_emojis.append("♦️")  # ♦️ quest direction indicator
                elif (cursor_pos and not is_center
                      and (grid[row_y][col_x].world_x, grid[row_y][col_x].world_y) == cursor_pos):
                    row_emojis.append("\U0001F7E6")  # 🟦 edit cursor
                else:
                    row_emojis.append(_tile_emoji(grid[row_y][col_x], location=location))

        lines.append("".join(row_emojis))

    lines.append("")
    # Breath meter / ship HP / normal HP (breathbar shows while in shipwreck)
    if getattr(player, "in_shipwreck", False):
        _breath = getattr(player, "breath", BREATH_MAX)
        hp_bar = f"\U0001FAB7 {_breath}/{BREATH_MAX}"
    elif player.in_ship or getattr(player, "in_high_seas", False) or getattr(player, "in_ocean", False):
        hp_bar = f"\U0001F6F3\uFE0F {player.ship_hp}/{player.ship_max_hp}"
    else:
        hp_bar = f"\u2764\uFE0F {player.hp}/{player.max_hp}"
    gold = f"\U0001FA99 {player.gold}"
    if player.in_ship:
        room_labels = {"helm": "Helm", "quarters": "Captain's Quarters", "lower_deck": "Lower Deck"}
        room_label = room_labels.get(player.ship_room, player.ship_room)
        pos = f"\u2693 Ship: {room_label} ({player.ship_x},{player.ship_y})"
    elif player.in_house:
        loc_labels = {
            "house": "House", "church": "Church", "bank": "Bank",
            "shop": "Shop", "blacksmith": "Blacksmith",
            "player_house": "My House",
        }
        label = loc_labels.get(player.house_type, "Building")
        pos = f"\U0001F4CD {label} ({player.house_x},{player.house_y})"
    elif player.in_island:
        pos = f"\U0001F3DD\uFE0F Island ({player.ocean_x},{player.ocean_y})"
    elif player.in_village:
        pos = f"\U0001F4CD Village ({player.village_x},{player.village_y})"
    elif player.in_cave:
        if player.cave_lit:
            dark_tag = "  \U0001F525 Lava Cave"
        else:
            _torch_emoji = ITEM_EMOJI.get("torch", "\U0001F526")
            dark_tag = "  ⚫ Darkness" if not torch_on else f"  {_torch_emoji}"
        pos = f"\U0001F4CD Cave ({player.cave_x},{player.cave_y}){dark_tag}"
    elif getattr(player, "in_shipwreck", False):
        _sw_breath = getattr(player, "breath", BREATH_MAX)
        pos = f"\U0001F4CD Shipwreck ({getattr(player, 'shipwreck_x', 0)},{getattr(player, 'shipwreck_y', 0)})  \U0001FAB7 {_sw_breath}"
    elif getattr(player, "in_tree_city", False):
        floor_names = {1: "Ground Hall", 2: "Living Quarters", 3: "Upper Hall", 4: "Elder's Chamber"}
        fname = floor_names.get(player.tc_floor, f"Floor {player.tc_floor}")
        pos = f"🌲 Tree City — {fname} (Fl. {player.tc_floor})  ({player.tc_x},{player.tc_y})"
    elif getattr(player, "in_maze", False):
        pos = "🌀 Forest Maze"   # deliberately no coordinates
    elif getattr(player, "in_grove", False):
        pos = "🌿 Hidden Grove"
    elif getattr(player, "in_hermit_hut", False):
        _hf_names = {1: "Ground Floor", 2: "Upper Room"}
        _hf_name  = _hf_names.get(getattr(player, "hermit_hut_floor", 1), "Upper Floor")
        pos = f"🛖 Hermit's Hut — {_hf_name} (Fl. {getattr(player, 'hermit_hut_floor', 1)})"
    elif getattr(player, "in_forest_quest", False):
        pos = "🌳 Forest Depths"   # deliberately no coordinates
    elif getattr(player, "in_temple", False):
        pos = f"⛩️ Temple ({getattr(player, 'temple_x', 0)},{getattr(player, 'temple_y', 0)})"
    elif getattr(player, "in_forest", False):
        pos = f"🌲 Forest ({getattr(player, 'forest_x', 0)},{getattr(player, 'forest_y', 0)})"
    elif getattr(player, "in_bandit_camp", False):
        pos = f"⛺ Bandit Camp ({getattr(player, 'bc_x', 0)},{getattr(player, 'bc_y', 0)})"
    elif getattr(player, "in_sky", False):
        pos = f"☁️ Sky ({getattr(player, 'sky_x', 0)},{getattr(player, 'sky_y', 0)})"
    elif getattr(player, "in_high_seas", False) or getattr(player, "in_ocean", False):
        sprint_tag = " \U0001F3C3" if player.sprinting else ""
        display_oy = OCEAN_SIZE - 1 - player.ocean_y
        pos = f"\U0001F30A High Seas ({player.ocean_x},{display_oy}){sprint_tag}"
    else:
        sprint_tag = " \U0001F3C3" if player.sprinting else ""
        display_y = WORLD_SIZE - 1 - player.world_y
        pos = f"\U0001F4CD Wilderness ({player.world_x},{display_y}){sprint_tag}"
    lines.append(f"{hp_bar}  {gold}  {pos}")

    # Always append a status line so embed height stays constant.
    # When there's no message, a zero-width space holds the space without
    # visible text, preventing the movement buttons from shifting on message pop-up.
    lines.append(status_msg if status_msg else "​")

    return "\n".join(lines)


# ── Inventory / Bank / Shop text renderers ────────────────────────────────────

_ITEM_SLOT_EMOJI = {
    "knife":        "\U0001F52A",   # default knife emoji
    "hiking_boots": "\U0001F97E",
    "torch":        "\U0001F526",
    "sword":        "\U0001F5E1\uFE0F",
    "shield":       "\U0001F6E1\uFE0F",
    "gem":          "\U0001F48E",
    "wood":         "\U0001FAB5",
    "stone":        "\U0001FAA8",
    "key":          "\U0001F511",
    "fish":         "\U0001F41F",
    "map_fragment": "\U0001F5FA\uFE0F",
    "axe":          "\U0001FA93",
    "shovel":       "\u26CF\uFE0F",
    "watering_can": "\U0001FAA3",
    "pickaxe":      "\u26CF\uFE0F",
    "log":          "\U0001FAB5",
    "stick":        "\U0001F38B",
    "resin":        "\U0001F7E1",
    "plant_fiber":  "\U0001F9F5",
    "dry_grass":    "\U0001F33E",
    "seed":         "\U0001F330",
    "sapling":      "\U0001F331",
    "flint":        "\U0001FAA8",
    "iron_ore":     "\U0001F7EB",
    "iron_ingot":   "\U0001F9F1",
    "slingshot":    "<:slingshot:1495973515722227822>",
    "rock":         "\U0001FAA8",
    "poison_sac":   "\U0001F9EA",
    "small_pouch":  "\U0001F45C",
    "medium_pouch": "\U0001F45C",
    "large_pouch":  "\U0001F45C",
    "fishing_net":  "\U0001F3A3",
    "fishing_rod":  "\U0001F3A3",
    "cooked_fish":  "\U0001F956",
    "treasure_map": "\U0001F4DC",
    "dagger":       "\U0001F5E1\uFE0F",
    "iron_helmet":     "\U0001FA96",
    "iron_chestplate": "\U0001F455",    # 👕
    "iron_leggings":   "\U0001F456",    # 👖
    "house_kit":       "\U0001F3E0",       # 🏠
    "ph_chest_small":  "\U0001F4E6",       # 📦
    "ph_chest_medium": "\U0001F5C4\uFE0F", # 🗄️
    "ph_chest_large":  "\U0001F9F3",       # 🧳
    "gold_coin":         "\U0001FA99",       # 🪙
    "potion":            "\U0001F9EA",       # 🧪
    "small_coin_purse":  "\U0001F4B0",       # 💰
    "medium_coin_purse": "\U0001F4B0",       # 💰
    "large_coin_purse":  "\U0001F4B0",       # 💰
    "cannonball":        "\U0001F4A3",       # 💣
    "drop_box":          "\U0001F4E6",       # 📦
    # Canoe 2-piece (overridden by custom emoji via apply_custom_emojis)
    "canoe_left":        "\U0001F6F6",       # 🛶 left half (fallback)
    "canoe_right":       "\U0001F6F6",       # 🛶 right half (fallback)
    "canoe_whole":       "\U0001F6F6",       # 🛶 whole canoe / player-on-water icon (fallback)
    "canoe":             "\U0001F6F6",       # 🛶 single canoe item (equipped row); overridden with canoe_whole
}
_EMPTY_SLOT = "\u2B1C"   # ⬜

# Ordered list of equipped slots (for the equipped row display)
_EQUIP_SLOT_ORDER = [
    ("hand_1",    "\u270B"),          # ✋  empty hand
    ("hand_2",    "\U0001F91A"),      # 🤚  empty hand
    ("head",      "\U0001F9D4"),      # 🧔  empty head slot
    ("chest",     "\U0001F455"),      # 👕  empty chest slot
    ("legs",      "\U0001F456"),      # 👖  empty legs slot
    ("boots",     "\U0001F9B6"),      # 🦶  empty boots
    ("pouch",     "\U0001F45C"),      # 👜  empty pouch
    ("accessory", "\U0001F48D"),      # 💍  empty accessory
    ("coin_purse","\U0001F4B0"),      # 💰  empty coin purse
]
_EQUIP_SLOT_LABELS = {
    "hand_1": "Main hand", "hand_2": "Off hand",
    "head": "Head", "chest": "Chest", "legs": "Legs",
    "boots": "Boots", "pouch": "Pouch", "accessory": "Accessory",
    "coin_purse": "Coin Purse",
}


def _item_emoji(item_id: str) -> str:
    if item_id in _ITEM_SLOT_EMOJI:
        return _ITEM_SLOT_EMOJI[item_id]
    from dwarf_explorer.config import ITEM_EMOJI as _IE
    return _IE.get(item_id, "\U0001F4E6")


_PAD = "\u2000"  # EN QUAD — wider than a regular space, won't collapse in Discord
_CUR = "◄"  # ◄ U+25C4 BLACK LEFT-POINTING SMALL TRIANGLE — matches EN QUAD width in Discord
_SEL = "«"  # « Left double angle quotation — text-only punctuation, ~0.5em

def _fmt_slot(item_id: str, qty: int, cursor_on: bool, is_selected: bool) -> str:
    """Format a single inventory slot cell — always exactly 4 units wide.

    Unit layout (all qty):
      [qty_or_pad][emoji][CUR/SEL/PAD][pad]

    Quantity (or a placeholder pad for qty=1) sits at unit 0, immediately left
    of the emoji. Cursor and selection markers live at unit 2, immediately
    right of the emoji, so the ◄ is always anchored to its emoji regardless
    of stack size. 2-digit quantities (≥10) use both units 0 and 3 for the
    digits, with the cursor still at unit 2.
    """
    emoji = _item_emoji(item_id)
    if qty > 9:  # above stack cap — display as ∞ (admin infinite pool)
        # ∞ sits at unit 0 (left of emoji), matching the normal qty-digit position
        if cursor_on:
            return f"∞{emoji}{_CUR}"
        if is_selected:
            return f"∞{emoji}{_SEL}"
        return f"∞{emoji}{_PAD}{_PAD}"
    if qty >= 10:
        # 2-digit qty straddles emoji: tens digit unit 0, ones digit unit 3.
        # Cursor/selection at unit 2 (immediately right of emoji).
        tens, ones = divmod(qty, 10)
        if cursor_on:
            return f"{tens}{emoji}{_CUR}{ones}"
        if is_selected:
            return f"{tens}{emoji}{_SEL}{ones}"
        return f"{tens}{emoji}{_PAD}{ones}"
    elif qty > 1:
        # qty at unit 0, cursor/selection at unit 2; no padding after cursor
        if cursor_on:
            return f"{qty}{emoji}{_CUR}"
        if is_selected:
            return f"{qty}{emoji}{_SEL}"
        return f"{qty}{emoji}{_PAD}{_PAD}"
    else:
        # qty=1: placeholder pad at unit 0, cursor/selection at unit 2; no pad after cursor
        if cursor_on:
            return f"{_PAD}{emoji}{_CUR}"
        if is_selected:
            return f"{_PAD}{emoji}{_SEL}"
        return f"{_PAD}{emoji}{_PAD}{_PAD}"


def _build_slot_map(visible_items: list[dict], total_slots: int, inv_cols: int = 7) -> dict[int, dict]:
    """Map grid cell index → item using slot_index as the grid position.

    Each canoe item ("canoe") in storage occupies TWO adjacent slots in the
    visual grid. At map-build time we expand each canoe row into a virtual
    canoe_left at slot N and canoe_right at slot N+1, so all downstream
    rendering/navigation code can keep treating canoes as two cells without
    knowing about the underlying single-item storage.

    Items whose slot_index falls outside [0, total_slots) are packed into
    the nearest free cell at the end so they are never invisible.

    Row-keep pass: if a canoe lands with canoe_left at the last column of a
    row, rotate three slots so the pair sits together at the start of the
    next row, bumping any item that was there back into the freed slot.
    """
    result: dict[int, dict] = {}
    overflow: list[dict] = []

    def _expand_canoe(it: dict, idx: int) -> None:
        result[idx] = {
            "item_id": "canoe_left",
            "quantity": 1,
            "slot_index": idx,
            "_canoe_origin": idx,
        }
        if idx + 1 < total_slots:
            result[idx + 1] = {
                "item_id": "canoe_right",
                "quantity": 1,
                "slot_index": idx + 1,
                "_canoe_origin": idx,
            }

    for it in visible_items:
        idx = it["slot_index"]
        if 0 <= idx < total_slots:
            if it["item_id"] == "canoe":
                # Need room for both halves.  If the right slot is out of bounds
                # OR already occupied by another item (shouldn't happen after the
                # canoe-aware compact, but be defensive), treat as overflow so the
                # overflow handler can find a clean 2-slot gap.
                if idx + 1 < total_slots and (idx + 1) not in result:
                    _expand_canoe(it, idx)
                else:
                    overflow.append(it)
            else:
                result[idx] = it
        else:
            overflow.append(it)
    for it in overflow:
        for i in range(total_slots - 1, -1, -1):
            if i not in result:
                if it["item_id"] == "canoe" and (i + 1 < total_slots) and (i + 1) not in result:
                    _expand_canoe(it, i)
                elif it["item_id"] != "canoe":
                    result[i] = it
                else:
                    continue
                break

    # Canoe pair row-keeping pass
    for i in range(total_slots - 2):
        left = result.get(i)
        right = result.get(i + 1)
        if (left is not None and left.get("item_id") == "canoe_left"
                and right is not None and right.get("item_id") == "canoe_right"
                and (i % inv_cols) == inv_cols - 1):
            # canoe_left at last column → 3-way rotate forward by 1.
            displaced = result.get(i + 2)
            new_origin = i + 1
            shifted_left = {**left, "slot_index": i + 1, "_canoe_origin": new_origin}
            shifted_right = {**right, "slot_index": i + 2, "_canoe_origin": new_origin}
            result[i + 1] = shifted_left
            result[i + 2] = shifted_right
            if displaced is not None:
                result[i] = displaced
            else:
                result.pop(i, None)
            break  # only one canoe pair expected
    return result


def _render_canoe_aware_slots(
    slot_map: dict[int, dict], total_slots: int, inv_cols: int,
    selected: int, cursor_active: bool,
    selections: dict | None = None,
) -> tuple[list[str], set[int]]:
    """Build a list of slot-cell strings, rendering same-row canoe_left+
    canoe_right pairs as a flush combined emoji with the cursor sitting
    immediately right of canoe_right.

    Returns (slot_strings, canoe_right_positions) so callers that need to
    detect "cursor is on a canoe pair" for the detail line can look it up.
    """
    selections = selections or {}
    canoe_right_skip: set[int] = set()
    for i in range(total_slots - 1):
        left = slot_map.get(i)
        right = slot_map.get(i + 1)
        if (left is not None and left.get("item_id") == "canoe_left"
                and right is not None and right.get("item_id") == "canoe_right"
                and i // inv_cols == (i + 1) // inv_cols):
            canoe_right_skip.add(i + 1)

    slots: list[str] = []
    for i in range(total_slots):
        item = slot_map.get(i)
        if item is not None:
            item_id = item["item_id"]
            qty = item["quantity"]
            is_selected = item_id in selections

            if item_id == "canoe_left" and (i + 1) in canoe_right_skip:
                left_e = _item_emoji("canoe_left")
                slots.append(f"{_PAD}{_PAD}{_PAD}{left_e}")
            elif item_id == "canoe_right" and i in canoe_right_skip:
                right_e = _item_emoji("canoe_right")
                cursor_on = cursor_active and i == selected
                if cursor_on:
                    slots.append(f"{right_e}{_CUR}{_PAD}")
                else:
                    slots.append(f"{right_e}{_PAD}{_PAD}{_PAD}")
            else:
                cursor_on = cursor_active and i == selected
                slots.append(_fmt_slot(item_id, qty, cursor_on, is_selected))
        else:
            if i == selected and cursor_active:
                slots.append(f"{_PAD}{_EMPTY_SLOT}{_CUR}")
            else:
                slots.append(f"{_PAD}{_EMPTY_SLOT}{_PAD}{_PAD}")
    return slots, canoe_right_skip


def render_inventory(
    items: list[dict],
    selected: int,
    equipped: dict,
    equip_label: str = "⚔️ Equip",
    inv_rows: int = 1,
    inv_cols: int = 7,
    selections: dict | None = None,
    gold: int = 0,
    cursor_mode: str = "inventory",
    equipped_cursor: int = 0,
    watering_can_uses: int = 0,
) -> str:
    """Render gold + equipped row + inventory grid as text."""
    total_slots = inv_rows * inv_cols
    selections = selections or {}

    lines = [f"\U0001F392 **Inventory** ({inv_rows}×{inv_cols})"]

    # --- Gold row (above equipped) ---
    if cursor_mode == "gold":
        gold_marker = f" {_CUR}"
    elif selections.get("gold_coin", 0) > 0:
        gold_marker = " «"
    else:
        gold_marker = ""
    lines.append(f"\U0001FA99 **{gold}** coins{gold_marker}")

    # --- Equipped row ---
    eq_line_parts: list[str] = []
    for idx, (slot, empty_emoji) in enumerate(_EQUIP_SLOT_ORDER):
        item_id = equipped.get(slot)
        emoji = _item_emoji(item_id) if item_id else empty_emoji
        cursor_here = cursor_mode == "equipped" and idx == equipped_cursor
        selected_here = item_id is not None and item_id in selections
        if cursor_here:
            eq_line_parts.append(f"{emoji}{_CUR}")   # cursor on right
        elif selected_here:
            eq_line_parts.append(f"{emoji}«")
        else:
            eq_line_parts.append(emoji)
    lines.append("**Equipped:**")
    lines.append(" ".join(eq_line_parts))
    lines.append("")

    # --- Inventory grid (position-aware: slot_index = grid cell index) ---
    visible_items = [it for it in items if it["item_id"] != "gold_coin"]
    slot_map = _build_slot_map(visible_items, total_slots, inv_cols)
    slots, _canoe_right_skip = _render_canoe_aware_slots(
        slot_map, total_slots, inv_cols,
        selected=selected, cursor_active=(cursor_mode == "inventory"),
        selections=selections,
    )

    for row in range(inv_rows):
        lines.append("".join(slots[row * inv_cols: row * inv_cols + inv_cols]))

    lines.append("")
    # Cursor item detail line
    if cursor_mode == "gold":
        lines.append(f"Cursor: **Gold** ({gold} coins)")
    elif cursor_mode == "equipped":
        slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
        item_id = equipped.get(slot)
        label = _EQUIP_SLOT_LABELS.get(slot, slot)
        if item_id:
            stats = EQUIP_BONUSES.get(item_id, {})
            stat_parts: list[str] = []
            if "defense" in stats:
                stat_parts.append(f"+{stats['defense']} def")
            if "attack" in stats:
                stat_parts.append(f"+{stats['attack']} atk")
            if item_id == "watering_can":
                stat_parts.append(f"{watering_can_uses}/9")
            stat_str = f" ({', '.join(stat_parts)})" if stat_parts else ""
            lines.append(f"Cursor: **{label}** — {item_id.replace('_', ' ').title()}{stat_str}")
        else:
            lines.append(f"Cursor: **{label}** — *(empty)*")
    elif slot_map.get(selected) or (selected in _canoe_right_skip and slot_map.get(selected - 1)):
        # For canoe_right slots, look up the canoe_left counterpart for display
        item = slot_map.get(selected) or slot_map.get(selected - 1)
        item_id = item["item_id"]
        # Friendly display name — canoe halves shown as "Canoe"
        if item_id in ("canoe_left", "canoe_right"):
            display_name = "Canoe"
        else:
            display_name = item_id.replace("_", " ").title()
        sel_qty = selections.get(item_id, 0)
        sel_marker = f" ✚ {sel_qty} selected" if sel_qty else ""
        stats = EQUIP_BONUSES.get(item_id, {})
        stat_parts: list[str] = []
        if "defense" in stats:
            stat_parts.append(f"+{stats['defense']} def")
        if "attack" in stats:
            stat_parts.append(f"+{stats['attack']} atk")
        # Watering can: show uses remaining
        if item_id == "watering_can":
            stat_parts.append(f"{watering_can_uses}/9")
        stat_str = f" ({', '.join(stat_parts)})" if stat_parts else ""
        # Equip hint — show slot name so the player knows to press the centre button
        from dwarf_explorer.config import ITEM_EQUIP_SLOTS as _IES_r
        _eq_slot = _IES_r.get(item_id)
        _slot_labels = {
            "hand": "hand", "head": "head", "chest": "chest",
            "legs": "legs", "boots": "boots", "accessory": "accessory",
            "pouch": "pouch", "coin_purse": "coin purse",
        }
        _eq_hint = f" · equip → {_slot_labels.get(_eq_slot, _eq_slot)}" if _eq_slot else ""
        lines.append(
            f"Cursor: **{display_name}** ×{item['quantity']}{stat_str}{_eq_hint}{sel_marker}"
        )
    else:
        lines.append("Cursor: *(empty slot)*")

    if selections:
        sel_parts = [f"{k.replace('_',' ').title()} ×{v}" for k, v in selections.items()]
        lines.append(f"Selected: {', '.join(sel_parts)}")

    return "\n".join(lines)


def render_bank(
    player_items: list[dict], bank_items: list[dict],
    selected: int, view: str, equipped: dict,
    inv_rows: int = 1, inv_cols: int = 7,
    gold: int = 0, qty: int = 1,
    cursor_mode: str = "inventory",
    equipped_cursor: int = 0,
) -> str:
    """Render bank UI. view = 'player' or 'bank'.

    Player view shows full inventory (gold row + equipped row + grid) with
    cursor_mode navigation support (gold / equipped / inventory).
    Bank vault view shows the vault grid.
    """
    BANK_COLS = 7
    BANK_ROWS = 9
    BANK_TOTAL = BANK_COLS * BANK_ROWS

    if view == "player":
        lines = [f"\U0001F3E6 **Bank** — Your Inventory ({inv_rows}×{inv_cols})"]

        # --- Gold row ---
        bank_gold = next((it["quantity"] for it in bank_items if it["item_id"] == "gold_coin"), 0)
        if cursor_mode == "gold":
            gold_marker = f" {_CUR}"
        else:
            gold_marker = ""
        lines.append(f"\U0001FA99 **{gold}** coins{gold_marker}  *(bank: {bank_gold}g)*")

        # --- Equipped row ---
        eq_parts: list[str] = []
        for idx, (slot, empty_emoji) in enumerate(_EQUIP_SLOT_ORDER):
            item_id = equipped.get(slot)
            emoji = _item_emoji(item_id) if item_id else empty_emoji
            if cursor_mode == "equipped" and idx == equipped_cursor:
                eq_parts.append(f"{emoji}{_CUR}")  # cursor on right
            else:
                eq_parts.append(emoji)
        lines.append("**Equipped:**")
        lines.append(" ".join(eq_parts))
        lines.append("")

        # --- Inventory grid (position-aware) ---
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        total_slots = inv_rows * inv_cols
        slot_map = _build_slot_map(visible, total_slots, inv_cols)
        slots, _ = _render_canoe_aware_slots(
            slot_map, total_slots, inv_cols,
            selected=selected, cursor_active=(cursor_mode == "inventory"),
        )
        for row in range(inv_rows):
            lines.append("".join(slots[row * inv_cols: row * inv_cols + inv_cols]))

        lines.append("")
        # Cursor detail
        if cursor_mode == "gold":
            lines.append(f"Cursor: **Gold** ({gold} coins)  |  📤 Deposit qty: **{qty}**")
        elif cursor_mode == "equipped":
            slot, _ = _EQUIP_SLOT_ORDER[equipped_cursor]
            item_id = equipped.get(slot)
            label = _EQUIP_SLOT_LABELS.get(slot, slot)
            if item_id:
                lines.append(f"Cursor: **{label}** — {item_id.replace('_',' ').title()}  |  📤 Deposit (unequip first)")
            else:
                lines.append(f"Cursor: **{label}** — *(empty)*")
        elif slot_map.get(selected):
            item = slot_map[selected]
            lines.append(
                f"Cursor: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}"
                f"  |  📤 Deposit qty: **{qty}**"
            )
        else:
            lines.append("Cursor: *(empty slot)*")

    else:
        # Bank vault — use dense array (bank items have sequential slot_index from get_bank_items)
        vault_items = [it for it in bank_items if it["item_id"] != "gold_coin"]
        bank_gold = next((it["quantity"] for it in bank_items if it["item_id"] == "gold_coin"), 0)
        lines = [f"\U0001F3E6 **Bank Vault** ({BANK_COLS}×{BANK_ROWS})"]
        gold_marker = f" {_CUR}" if cursor_mode == "gold" else ""
        lines.append(f"\U0001FA99 Bank gold: **{bank_gold}**{gold_marker}")
        if cursor_mode == "gold":
            lines.append(f"Cursor: 🪙 **Bank Gold** ×{bank_gold}  |  📥 Withdraw qty: **{qty}**")
        lines.append("")

        slot_map = _build_slot_map(vault_items, BANK_TOTAL, BANK_COLS)
        slots, _ = _render_canoe_aware_slots(
            slot_map, BANK_TOTAL, BANK_COLS,
            selected=selected, cursor_active=(cursor_mode != "gold"),
        )
        for row in range(BANK_ROWS):
            lines.append("".join(slots[row * BANK_COLS: row * BANK_COLS + BANK_COLS]))

        if cursor_mode != "gold":
            lines.append("")
            item = slot_map.get(selected)
            if item:
                lines.append(
                    f"Cursor: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}"
                    f"  |  📥 Withdraw qty: **{qty}**"
                )
            else:
                lines.append("Cursor: *(empty slot)*")

    return "\n".join(lines)


# ── Ship interior rendering ────────────────────────────────────────────────────

_SHIP_ROOMS: dict[str, list[str]] = {
    "helm": [
        "🟫🟫🟫🟫🟫🟫🟫",
        "🟫🔭⬛⬛⬛🪝🟫",
        "🟫⬛⬛🛞⬛⬛🟫",
        "🟫⬛⬛⬛⬛⬛🟫",
        "🟫🟫🚪🟫🚪🟫🟫",
    ],
    "quarters": [
        "🟫🟫🟫🟫🟫🟫🟫",
        "🟫🛏️⬛⬛⬛📜🟫",
        "🟫⬛⬛⬛⬛⬛🟫",
        "🟫⬛⬛⬛⬛📦🟫",
        "🟫🟫🚪🟫🟫🟫🟫",
    ],
    "lower_deck": [
        "🟫🟫🟫🟫🟫🟫🟫",
        "🟫🪣⬛⬛⬛🪣🟫",
        "🟫⬛⬛⚒️⬛⬛🟫",
        "🟫📦⬛⬛⬛⬛🟫",
        "🟫🟫🚪🟫🟫🟫🟫",
    ],
}

_SHIP_ROOM_NAMES = {
    "helm":       "⚓ Helm Deck",
    "quarters":   "🛏️ Captain's Quarters",
    "lower_deck": "🪜 Lower Deck",
}


def render_ship_room(player) -> str:
    """Render the current ship interior room as emoji art."""
    room = getattr(player, "ship_room", "helm")
    grid_lines = _SHIP_ROOMS.get(room, _SHIP_ROOMS["helm"])
    title = _SHIP_ROOM_NAMES.get(room, room)
    hp = getattr(player, "ship_hp", 100)
    max_hp = getattr(player, "ship_max_hp", 100)
    hp_bar = "🟥" * (hp // 20) + "⬛" * (5 - hp // 20)
    body = "\n".join(grid_lines)
    desc = {
        "helm":       "The helm deck. Seabirds cry overhead. Doors aft and fore lead below.",
        "quarters":   "The captain's quarters. A bunk, a map, and a locked personal chest.",
        "lower_deck": "The lower deck. Supply barrels and the repair station fill the hold.",
    }.get(room, "")
    return (
        f"**🚢 Ship Interior — {title}**\n"
        f"{body}\n\n"
        f"🛳️ Hull: {hp_bar} {hp}/{max_hp}\n"
        f"*{desc}*"
    )


def render_ship_chest(
    chest_items: list[dict],
    player_items: list[dict],
    selected: int,
    view: str,
    chest_name: str,
    player,
    inv_rows: int = 1,
    inv_cols: int = 7,
) -> str:
    """Render a ship chest (personal or cargo) using the same layout as the bank."""
    CHEST_COLS = 7
    CHEST_ROWS = 4
    CHEST_TOTAL = CHEST_COLS * CHEST_ROWS

    if view == "player":
        title = f"📦 **{chest_name}** — Your Inventory ({inv_rows}×{inv_cols})"
        source = [it for it in player_items if it["item_id"] != "gold_coin"]
        action_label = "⬇ Deposit"
        COLS_disp, TOTAL_disp = inv_cols, inv_rows * inv_cols
    else:
        title = f"📦 **{chest_name}** — Chest ({CHEST_COLS}×{CHEST_ROWS})"
        source = chest_items
        action_label = "⬆ Withdraw"
        COLS_disp, TOTAL_disp = CHEST_COLS, CHEST_TOTAL

    lines = [title]
    slots: list[str] = []
    for i in range(TOTAL_disp):
        if i < len(source):
            item = source[i]
            emoji = _item_emoji(item["item_id"])
            qty_str = str(item["quantity"]).ljust(2) if item["quantity"] > 1 else "  "
            cell = f"{emoji}{qty_str}"
        else:
            cell = f" {_EMPTY_SLOT}  "
        if i == selected:
            cell = f"[{cell}]"
        slots.append(cell)

    for row in range(TOTAL_disp // COLS_disp):
        lines.append("".join(slots[row * COLS_disp: row * COLS_disp + COLS_disp]))

    lines.append("")
    if selected < len(source):
        item = source[selected]
        lines.append(f"Selected: **{item['item_id'].replace('_',' ').title()}** {item['quantity']}")
    else:
        lines.append("Selected: *(empty slot)*")

    lines.append(f"← → navigate  |  {action_label}  |  🔄 Switch View  |  🔙 Back")
    return "\n".join(lines)


# ── Island rendering ───────────────────────────────────────────────────────────

_ISLAND_TERRAIN_EMOJI: dict[str, str] = {
    "island_void":    "🌊",
    "island_sand":    "🟨",
    "island_grass":   "🌿",
    "island_forest":  "🌴",
    "island_tree":    "🌴",
    "island_sapling": "🌱",
    "island_chest":   "💰",   # distinct treasure-chest look
    "island_dock":    "⚓",
    "island_npc":     "🧑",   # small island merchant
    # Volcano island tiles
    "vol_void":       "🌊",   # ocean surrounding volcano island
    "vol_sand":       "⬛",   # dark ash beach
    "vol_rock":       "⛰️",  # volcanic rock (mountain)
    "vol_grass":      "🌿",   # sparse grass (overridable with custom grass emoji)
    "vol_forest":     "🌲",   # forest
    "vol_lava":       "🟧",   # impassable lava flow (orange square)
    "vol_crater":     "🌑",   # impassable crater
    "vol_lava_bridge":"🌉",   # stone bridge over lava
    "vol_cave":       "🕳️",  # cave entrance (same as wilderness cave hole)
    "vol_dock":       "⚓",   # dock back to sea
    "vol_outpost":    "🏚️",  # trading post
    "vol_chest":      "💰",   # treasure chest
}


def render_island(
    grid: list[list],
    player_x: int,
    player_y: int,
    player,
    msg: str = "",
) -> str:
    """Render island viewport (9×9) centered on player position."""
    SIZE = len(grid)
    half = SIZE // 2
    lines: list[str] = []
    for row_y in range(SIZE):
        row_emojis: list[str] = []
        for col_x in range(SIZE):
            tile = grid[row_y][col_x]
            is_center = (col_x == half and row_y == half)
            if is_center:
                row_emojis.append("🧙")
            else:
                terrain = getattr(tile, "terrain", "island_void")
                row_emojis.append(_ISLAND_TERRAIN_EMOJI.get(terrain, "🌊"))
        lines.append("".join(row_emojis))
    result = "\n".join(lines)
    hp = player.hp
    max_hp = player.max_hp
    status = f"\n❤️ {hp}/{max_hp}"
    if msg:
        status += f"\n> {msg}"
    return result + status


def render_chest(
    chest_items: list[dict], player_items: list[dict],
    selected: int, view: str,
    chest_type: str = "cave_chest",
    player_inv_rows: int = 2, player_inv_cols: int = 5,
) -> str:
    """Render chest UI. view = 'chest' or 'player'."""
    chest_sizes = {
        "cave_chest":        (2, 9),
        "cave_chest_medium": (3, 9),
        "cave_chest_large":  (4, 9),
        "ph_chest_small":    (2, 9),
        "ph_chest_medium":   (3, 9),
        "ph_chest_large":    (4, 9),
        "fst_chest":         (1, 5),
        "maze_chest":        (1, 5),
        "fst_chamber_chest": (2, 5),
    }
    chest_labels = {
        "cave_chest":        "Small Chest",
        "cave_chest_medium": "Medium Chest",
        "cave_chest_large":  "Large Chest",
        "ph_chest_small":    "Small Chest",
        "ph_chest_medium":   "Medium Chest",
        "ph_chest_large":    "Large Chest",
        "fst_chest":         "Forest Cache",
        "maze_chest":        "Maze Chest",
        "fst_chamber_chest": "Hidden Chamber",
    }
    c_rows, c_cols = chest_sizes.get(chest_type, (2, 9))
    c_total = c_rows * c_cols

    # Map chest type to its display emoji (use FOREST_EMOJI for forest/maze types)
    _chest_icon_map: dict[str, str] = {
        "fst_chest":         FOREST_EMOJI.get("fst_chest",         "\U0001F4E6"),
        "fst_map_chest":     FOREST_EMOJI.get("fst_map_chest",     "\U0001F4E6"),
        "fst_chamber_chest": FOREST_EMOJI.get("fst_chamber_chest", "\U0001F48E"),
        "maze_chest":        FOREST_EMOJI.get("maze_chest",        "\U0001F4B0"),
    }
    chest_icon = _chest_icon_map.get(chest_type, "\U0001F4E6")

    if view == "chest":
        title = f"{chest_icon} **{chest_labels.get(chest_type, 'Chest')}** ({c_rows}×{c_cols})"
        source = chest_items
        action_label = "📤 Take"
        total_disp = c_total
        disp_cols = c_cols
    else:
        p_total = player_inv_rows * player_inv_cols
        title = f"{chest_icon} **Chest** — Your Inventory ({player_inv_rows}×{player_inv_cols})"
        source = player_items
        action_label = "📥 Give"
        total_disp = p_total
        disp_cols = player_inv_cols

    lines = [title]
    slots: list[str] = []
    for i in range(total_disp):
        if i < len(source):
            item = source[i]
            slots.append(_fmt_slot(item["item_id"], item["quantity"],
                                   cursor_on=(i == selected), is_selected=False))
        else:
            if i == selected:
                slots.append(f"{_PAD}{_EMPTY_SLOT}{_CUR}")
            else:
                slots.append(f"{_PAD}{_EMPTY_SLOT}{_PAD}{_PAD}")

    for row in range(total_disp // disp_cols):
        lines.append("  ".join(slots[row * disp_cols: row * disp_cols + disp_cols]))

    lines.append("")
    if selected < len(source):
        item = source[selected]
        lines.append(f"Selected: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}")
    else:
        lines.append("Selected: *(empty slot)*")

    if view == "chest":
        lines.append("← → navigate  |  📤 Take  |  📦 Loot All  |  ❌ Close")
    else:
        lines.append("← → navigate  |  📥 Give  |  🔄 Switch View  |  ❌ Close")
    return "\n".join(lines)


def render_shop(
    catalog: list[dict],
    player_items: list[dict],
    selected: int,
    view: str,
    equipped: dict,
    player_gold: int,
    inv_rows: int = 1,
    inv_cols: int = 7,
    sell_prices: dict | None = None,
    qty: int = 1,
) -> str:
    """Render shop UI.

    view = 'shop'   — shop catalog grid; buy button active.
    view = 'player' — full player inventory; sell button active.
    """
    from dwarf_explorer.config import ITEM_EMOJI as _IE

    SHOP_COLS = 7

    if view == "player":
        # Full inventory display for selling
        lines = [f"\U0001F3EA **Shop — Sell** | \U0001FA99 {player_gold}g"]

        # Gold row
        lines.append(f"\U0001FA99 **{player_gold}** coins")

        # Equipped row
        eq_parts: list[str] = []
        for slot, empty_emoji in _EQUIP_SLOT_ORDER:
            item_id = equipped.get(slot)
            eq_parts.append(_item_emoji(item_id) if item_id else empty_emoji)
        lines.append("**Equipped:**")
        lines.append(" ".join(eq_parts))
        lines.append("")

        # Inventory grid
        visible = [it for it in player_items if it["item_id"] != "gold_coin"]
        total_slots = inv_rows * inv_cols
        slot_map = _build_slot_map(visible, total_slots, inv_cols)
        slots, _ = _render_canoe_aware_slots(
            slot_map, total_slots, inv_cols,
            selected=selected, cursor_active=True,
        )
        for row in range(inv_rows):
            lines.append("".join(slots[row * inv_cols: row * inv_cols + inv_cols]))

        lines.append("")
        item = slot_map.get(selected)
        if item:
            price = (sell_prices or {}).get(item["item_id"], 0)
            price_str = f"{price}g each" if price else "*(no value)*"
            lines.append(
                f"Cursor: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}"
                f"  |  Sell qty **{qty}** for {price * qty if price else 0}g"
            )
        else:
            lines.append("Cursor: *(empty slot)*")

    else:
        # Shop catalog grid
        shop_rows = max(1, (len(catalog) + SHOP_COLS - 1) // SHOP_COLS)
        lines = [f"\U0001F3EA **Shop** | \U0001FA99 {player_gold}g"]
        lines.append("")

        slots = []
        for i, item in enumerate(catalog):
            emoji = _IE.get(item["id"], item.get("emoji", "\U0001F4E6"))
            cursor_on = (i == selected)
            # Pad to 3 chars wide (emoji + 2 trailing pads)
            if cursor_on:
                slots.append(f"{_PAD}{emoji}{_CUR}")  # cursor on right
            else:
                slots.append(f"{_PAD}{emoji}{_PAD}")
        # Pad to full grid
        while len(slots) % SHOP_COLS != 0:
            slots.append(f"{_PAD}{_EMPTY_SLOT}{_PAD * 2}")

        for row in range(len(slots) // SHOP_COLS):
            lines.append("".join(slots[row * SHOP_COLS: row * SHOP_COLS + SHOP_COLS]))

        lines.append("")
        if 0 <= selected < len(catalog):
            item = catalog[selected]
            lines.append(
                f"Cursor: **{item['name']}** — {item['price']}g"
                f"  |  Buy qty **{qty}** for {item['price'] * qty}g"
            )
            if item.get("description"):
                lines.append(f"*{item['description']}*")
        else:
            lines.append("Cursor: *(empty slot)*")

    return "\n".join(lines)
