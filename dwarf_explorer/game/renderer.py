from dwarf_explorer.config import (
    TERRAIN_EMOJI, STRUCTURE_EMOJI, ENTITY_EMOJI, ITEM_EMOJI,
    CAVE_EMOJI, VILLAGE_EMOJI, BUILDING_EMOJI,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.game.player import Player


def _tile_emoji(tile: TileData, location: str = "wilderness") -> str:
    if location == "cave":
        return CAVE_EMOJI.get(tile.terrain, "\u2B1B")
    if location == "village":
        return VILLAGE_EMOJI.get(tile.terrain, "\u2B1B")
    if location in ("house", "church", "bank", "shop"):
        return BUILDING_EMOJI.get(tile.terrain, "\u2B1B")
    # Wilderness: structure > enemy > item > terrain
    if tile.structure and tile.structure in STRUCTURE_EMOJI:
        return STRUCTURE_EMOJI[tile.structure]
    if tile.enemy and tile.enemy in ENTITY_EMOJI:
        return ENTITY_EMOJI[tile.enemy]
    if tile.ground_item and tile.ground_item in ITEM_EMOJI:
        return ITEM_EMOJI[tile.ground_item]
    return TERRAIN_EMOJI.get(tile.terrain, "\u2B1B")


def render_grid(grid: list[list[TileData]], player: Player, status_msg: str = "") -> str:
    """Render viewport with player at centre, plus status bar.

    Viewport size is inferred from the grid dimensions so caves/buildings
    (7×7) and wilderness (9×9) both render correctly.
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

    lines: list[str] = []
    for row_y in range(vp_size):
        row_emojis: list[str] = []
        for col_x in range(vp_size):
            if col_x == vp_center and row_y == vp_center:
                row_emojis.append(ENTITY_EMOJI["player"])
            else:
                row_emojis.append(_tile_emoji(grid[row_y][col_x], location=location))
        lines.append("".join(row_emojis))

    lines.append("")
    hp_bar = f"\u2764\uFE0F {player.hp}/{player.max_hp}"
    gold = f"\U0001F4B0 {player.gold}"
    if player.in_house:
        loc_labels = {"house": "House", "church": "Church", "bank": "Bank", "shop": "Shop"}
        label = loc_labels.get(player.house_type, "Building")
        pos = f"\U0001F4CD {label} ({player.house_x},{player.house_y})"
    elif player.in_village:
        pos = f"\U0001F4CD Village ({player.village_x},{player.village_y})"
    elif player.in_cave:
        pos = f"\U0001F4CD Cave ({player.cave_x},{player.cave_y})"
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
    "sword":        "\U0001F5E1\uFE0F",
    "shield":       "\U0001F6E1\uFE0F",
    "potion":       "\U0001F9EA",
    "gem":          "\U0001F48E",
    "wood":         "\U0001FAB5",
    "stone":        "\U0001FAA8",
    "key":          "\U0001F511",
    "fish":         "\U0001F41F",
    "map_fragment": "\U0001F5FA\uFE0F",
}
_EMPTY_SLOT = "\u2B1C"   # ⬜


def _item_emoji(item_id: str) -> str:
    return _ITEM_SLOT_EMOJI.get(item_id, "\U0001F4E6")


def render_inventory(items: list[dict], selected: int, equipped: dict) -> str:
    """Render 5×2 inventory grid as text. selected = slot index 0-9."""
    COLS = 5
    lines = ["\U0001F392 **Inventory**"]
    slots: list[str] = []
    for i in range(10):
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

    for row in range(2):
        lines.append("  ".join(slots[row * COLS: row * COLS + COLS]))

    lines.append("")
    if selected < len(items):
        item = items[selected]
        e_slots = [f"{slot}:{iid}" for slot, iid in equipped.items()]
        eq_str = f"  Equipped: {', '.join(e_slots)}" if e_slots else ""
        lines.append(f"Selected: **{item['item_id'].replace('_',' ').title()}** ×{item['quantity']}{eq_str}")
    else:
        lines.append("Selected: *(empty slot)*")

    lines.append("◀▶ navigate  |  ⚔️ Equip  |  ❌ Close")
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


def render_shop(catalog: list[dict], selected: int, player_gold: int) -> str:
    """Render shop menu."""
    lines = ["\U0001F3EA **Shop**", f"\U0001F4B0 You have: **{player_gold} gold**", ""]
    for i, item in enumerate(catalog):
        prefix = "▶ " if i == selected else "  "
        bracket_open  = "[" if i == selected else ""
        bracket_close = "]" if i == selected else ""
        lines.append(f"{prefix}{bracket_open}{item['emoji']} {item['name']} — {item['price']} gold{bracket_close}")
        lines.append(f"   *{item['description']}*")
    lines.append("")
    lines.append("◀▶ navigate  |  💰 Buy  |  ❌ Close")
    return "\n".join(lines)
