import math

from dwarf_explorer.config import (
    TERRAIN_EMOJI, STRUCTURE_EMOJI, ENTITY_EMOJI, ITEM_EMOJI,
    CAVE_EMOJI, VILLAGE_EMOJI, BUILDING_EMOJI, POUCH_SIZES,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.game.player import Player

_BLACK = "\u2B1B"   # ⬛ — darkness tile
_FOV_RADIUS = 3.0   # torch illumination radius in tiles


def _tile_emoji(tile: TileData, location: str = "wilderness") -> str:
    if location == "cave":
        return CAVE_EMOJI.get(tile.terrain, _BLACK)
    if location == "village":
        return VILLAGE_EMOJI.get(tile.terrain, _BLACK)
    if location in ("house", "church", "bank", "shop", "blacksmith"):
        return BUILDING_EMOJI.get(tile.terrain, _BLACK)
    # Wilderness: structure > enemy > item > terrain
    if tile.structure and tile.structure in STRUCTURE_EMOJI:
        return STRUCTURE_EMOJI[tile.structure]
    if tile.enemy and tile.enemy in ENTITY_EMOJI:
        return ENTITY_EMOJI[tile.enemy]
    if tile.ground_item and tile.ground_item in ITEM_EMOJI:
        return ITEM_EMOJI[tile.ground_item]
    return TERRAIN_EMOJI.get(tile.terrain, _BLACK)


def render_grid(grid: list[list[TileData]], player: Player, status_msg: str = "") -> str:
    """Render viewport with player at centre, plus status bar.

    Viewport size is inferred from the grid dimensions so caves/buildings
    (7×7) and wilderness (9×9) both render correctly.

    Cave FOV rules:
    - Torch equipped: tiles within _FOV_RADIUS tiles of player are lit; rest = ⬛
    - No torch, on entrance: player icon visible, rest = ⬛
    - No torch, elsewhere: everything = ⬛ (player cannot see themselves)
    """
    if player.in_house:
        location = player.house_type  # "house" | "church" | "bank" | "shop"
    elif player.in_village:
        location = "village"
    elif player.in_cave:
        location = "cave"
    else:
        location = "wilderness"

    vp_size   = len(grid)
    vp_center = vp_size // 2

    # Cave visibility pre-computation
    torch_on   = False
    on_entrance = False
    if location == "cave":
        torch_on    = player.hand_1 == "torch" or player.hand_2 == "torch"
        on_entrance = grid[vp_center][vp_center].terrain == "cave_entrance"

    lines: list[str] = []
    for row_y in range(vp_size):
        row_emojis: list[str] = []
        for col_x in range(vp_size):
            is_center = (col_x == vp_center and row_y == vp_center)

            if location == "cave":
                dist = math.hypot(col_x - vp_center, row_y - vp_center)
                if is_center:
                    # Show player only if torch on OR standing on entrance
                    if torch_on or on_entrance:
                        row_emojis.append(ENTITY_EMOJI["player"])
                    else:
                        row_emojis.append(_BLACK)
                else:
                    if torch_on and dist <= _FOV_RADIUS:
                        row_emojis.append(_tile_emoji(grid[row_y][col_x], location="cave"))
                    else:
                        row_emojis.append(_BLACK)
            else:
                if is_center:
                    row_emojis.append(ENTITY_EMOJI["player"])
                else:
                    row_emojis.append(_tile_emoji(grid[row_y][col_x], location=location))

        lines.append("".join(row_emojis))

    lines.append("")
    hp_bar = f"\u2764\uFE0F {player.hp}/{player.max_hp}"
    gold = f"\U0001F4B0 {player.gold}"
    if player.in_house:
        loc_labels = {"house": "House", "church": "Church", "bank": "Bank", "shop": "Shop", "blacksmith": "Blacksmith"}
        label = loc_labels.get(player.house_type, "Building")
        pos = f"\U0001F4CD {label} ({player.house_x},{player.house_y})"
    elif player.in_village:
        pos = f"\U0001F4CD Village ({player.village_x},{player.village_y})"
    elif player.in_cave:
        dark_tag = "  \u26AB Darkness" if not torch_on else "  \U0001F526"
        pos = f"\U0001F4CD Cave ({player.cave_x},{player.cave_y}){dark_tag}"
    else:
        sprint_tag = " \U0001F3C3" if player.sprinting else ""
        pos = f"\U0001F4CD Wilderness ({player.world_x},{player.world_y}){sprint_tag}"
    lines.append(f"{hp_bar}  {gold}  {pos}")

    if status_msg:
        lines.append(status_msg)

    return "\n".join(lines)


# ── Inventory / Bank / Shop text renderers ────────────────────────────────────

_ITEM_SLOT_EMOJI = {
    "knife":        "\U0001F5E1\uFE0F",
    "hiking_boots": "\U0001F97E",
    "torch":        "\U0001F526",
    "sword":        "\U0001F5E1\uFE0F",
    "shield":       "\U0001F6E1\uFE0F",
    "potion":       "\U0001F9EA",
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
    "slingshot":    "\U0001FA83",
    "rock":         "\U0001FAA8",
    "poison_sac":   "\U0001F9EA",
    "small_pouch":  "\U0001F45C",
    "medium_pouch": "\U0001F45C",
    "large_pouch":  "\U0001F45C",
}
_EMPTY_SLOT = "\u2B1C"   # ⬜


def _item_emoji(item_id: str) -> str:
    return _ITEM_SLOT_EMOJI.get(item_id, "\U0001F4E6")


def render_inventory(items: list[dict], selected: int, equipped: dict,
                     equip_label: str = "⚔️ Equip",
                     inv_rows: int = 2, inv_cols: int = 5) -> str:
    """Render equipped row + inventory grid as text. Grid size from pouch."""
    total_slots = inv_rows * inv_cols
    lines = [f"\U0001F392 **Inventory** ({inv_rows}×{inv_cols})"]

    # --- Equipped bar ---
    h1 = equipped.get("hand_1")
    h2 = equipped.get("hand_2")
    boots_item = equipped.get("boots")
    pouch_item = equipped.get("pouch")

    hand1_cell = _item_emoji(h1) if h1 else "\u270B"      # ✋
    hand2_cell = _item_emoji(h2) if h2 else "\U0001F91A"   # 🤚
    boots_cell = _item_emoji(boots_item) if boots_item else "\U0001F9B6"  # 🦶
    pouch_cell = _item_emoji(pouch_item) if pouch_item else "\U0001F45C"  # 👜 (empty)

    eq_parts = [hand1_cell, hand2_cell, boots_cell, pouch_cell]
    for slot in ("head", "chest", "legs", "accessory"):
        item_id = equipped.get(slot)
        if item_id:
            eq_parts.append(_item_emoji(item_id))

    lines.append("**Equipped:** " + "  ".join(eq_parts))
    lines.append("")

    # --- Inventory grid ---
    slots: list[str] = []
    for i in range(total_slots):
        if i < len(items):
            item = items[i]
            emoji = _item_emoji(item["item_id"])
            qty = f"×{item['quantity']}" if item["quantity"] > 1 else ""
            cell = f"{emoji}{qty}"
        else:
            cell = _EMPTY_SLOT
        if i == selected:
            cell = f"[{cell}]"
        slots.append(cell)

    for row in range(inv_rows):
        lines.append("  ".join(slots[row * inv_cols: row * inv_cols + inv_cols]))

    lines.append("")
    if selected < len(items):
        item = items[selected]
        lines.append(f"Selected: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}")
    else:
        lines.append("Selected: *(empty slot)*")

    lines.append(f"◀▶ navigate  |  {equip_label}  |  ❌ Close")
    return "\n".join(lines)


def render_bank(
    player_items: list[dict], bank_items: list[dict],
    selected: int, view: str, equipped: dict,
) -> str:
    """Render bank UI. view = 'player' or 'bank'."""
    COLS = 9
    ROWS = 4
    TOTAL = COLS * ROWS

    if view == "player":
        title = "\U0001F3E6 **Bank** — Your Inventory (5×2)"
        source = player_items
        action_label = "⬇ Deposit"
        COLS_disp, TOTAL_disp = 5, 10
    else:
        title = "\U0001F3E6 **Bank** — Vault (9×4)"
        source = bank_items
        action_label = "⬆ Withdraw"
        COLS_disp, TOTAL_disp = COLS, TOTAL

    lines = [title]
    slots: list[str] = []
    for i in range(TOTAL_disp):
        if i < len(source):
            item = source[i]
            emoji = _item_emoji(item["item_id"])
            qty = f"×{item['quantity']}" if item["quantity"] > 1 else ""
            cell = f"{emoji}{qty}"
        else:
            cell = _EMPTY_SLOT
        if i == selected:
            cell = f"[{cell}]"
        slots.append(cell)

    for row in range(TOTAL_disp // COLS_disp):
        lines.append("  ".join(slots[row * COLS_disp: row * COLS_disp + COLS_disp]))

    lines.append("")
    if selected < len(source):
        item = source[selected]
        lines.append(f"Selected: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}")
    else:
        lines.append("Selected: *(empty slot)*")

    lines.append(f"◀▶ navigate  |  {action_label}  |  🔄 Switch View  |  ❌ Close")
    return "\n".join(lines)


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
    }
    chest_labels = {
        "cave_chest":        "Small Chest",
        "cave_chest_medium": "Medium Chest",
        "cave_chest_large":  "Large Chest",
    }
    c_rows, c_cols = chest_sizes.get(chest_type, (2, 9))
    c_total = c_rows * c_cols

    if view == "chest":
        title = f"\U0001F4E6 **{chest_labels.get(chest_type, 'Chest')}** ({c_rows}×{c_cols})"
        source = chest_items
        action_label = "📤 Take"
        total_disp = c_total
        disp_cols = c_cols
    else:
        p_total = player_inv_rows * player_inv_cols
        title = f"\U0001F4E6 **Chest** — Your Inventory ({player_inv_rows}×{player_inv_cols})"
        source = player_items
        action_label = "📥 Give"
        total_disp = p_total
        disp_cols = player_inv_cols

    lines = [title]
    slots: list[str] = []
    for i in range(total_disp):
        if i < len(source):
            item = source[i]
            emoji = _item_emoji(item["item_id"])
            qty = f"×{item['quantity']}" if item["quantity"] > 1 else ""
            cell = f"{emoji}{qty}"
        else:
            cell = _EMPTY_SLOT
        if i == selected:
            cell = f"[{cell}]"
        slots.append(cell)

    for row in range(total_disp // disp_cols):
        lines.append("  ".join(slots[row * disp_cols: row * disp_cols + disp_cols]))

    lines.append("")
    if selected < len(source):
        item = source[selected]
        lines.append(f"Selected: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}")
    else:
        lines.append("Selected: *(empty slot)*")

    if view == "chest":
        lines.append("◀▶ navigate  |  📤 Take  |  📦 Loot All  |  ❌ Close")
    else:
        lines.append("◀▶ navigate  |  📥 Give  |  🔄 Switch View  |  ❌ Close")
    return "\n".join(lines)


def render_shop(catalog: list[dict], selected: int, player_gold: int,
                mode: str = "buy", sell_items: list[dict] | None = None,
                sell_prices: dict | None = None) -> str:
    """Render shop menu. mode='buy' shows catalog; mode='sell' shows inventory."""
    if mode == "sell":
        lines = ["\U0001F3EA **Shop — Sell Items**", f"\U0001F4B0 You have: **{player_gold} gold**", ""]
        items = sell_items or []
        if not items:
            lines.append("*(Your inventory is empty)*")
        else:
            for i, item in enumerate(items):
                price = (sell_prices or {}).get(item["item_id"], 0)
                prefix = "▶ " if i == selected else "  "
                brk_o = "[" if i == selected else ""
                brk_c = "]" if i == selected else ""
                qty_str = f" ×{item['quantity']}" if item["quantity"] > 1 else ""
                price_str = f"{price}g" if price else "no value"
                lines.append(
                    f"{prefix}{brk_o}{_item_emoji(item['item_id'])} "
                    f"{item['item_id'].replace('_', ' ').title()}{qty_str} — {price_str}{brk_c}"
                )
        lines.append("")
        lines.append("◀▶ navigate  |  💰 Sell  |  🛒 Buy Mode  |  ❌ Close")
    else:
        lines = ["\U0001F3EA **Shop**", f"\U0001F4B0 You have: **{player_gold} gold**", ""]
        for i, item in enumerate(catalog):
            prefix = "▶ " if i == selected else "  "
            bracket_open  = "[" if i == selected else ""
            bracket_close = "]" if i == selected else ""
            lines.append(f"{prefix}{bracket_open}{item['emoji']} {item['name']} — {item['price']} gold{bracket_close}")
            lines.append(f"   *{item['description']}*")
        lines.append("")
        lines.append("◀▶ navigate  |  💰 Buy  |  💲 Sell Mode  |  ❌ Close")
    return "\n".join(lines)
