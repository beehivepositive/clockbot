from dwarf_explorer.config import (
    TERRAIN_EMOJI, STRUCTURE_EMOJI, ENTITY_EMOJI, ITEM_EMOJI,
    CAVE_EMOJI, VILLAGE_EMOJI, HOUSE_EMOJI, VIEWPORT_SIZE, VIEWPORT_CENTER,
)
from dwarf_explorer.world.generator import TileData
from dwarf_explorer.game.player import Player


def _tile_emoji(tile: TileData, location: str = "wilderness") -> str:
    """Get the display emoji for a tile, applying render priority."""
    if location == "cave":
        return CAVE_EMOJI.get(tile.terrain, "\u2B1B")
    if location == "village":
        return VILLAGE_EMOJI.get(tile.terrain, "\u2B1B")
    if location == "house":
        return HOUSE_EMOJI.get(tile.terrain, "\u2B1B")
    # Wilderness priority: structure > enemy > ground_item > terrain
    if tile.structure and tile.structure in STRUCTURE_EMOJI:
        return STRUCTURE_EMOJI[tile.structure]
    if tile.enemy and tile.enemy in ENTITY_EMOJI:
        return ENTITY_EMOJI[tile.enemy]
    if tile.ground_item and tile.ground_item in ITEM_EMOJI:
        return ITEM_EMOJI[tile.ground_item]
    return TERRAIN_EMOJI.get(tile.terrain, "\u2B1B")


def render_grid(grid: list[list[TileData]], player: Player,
                status_msg: str = "") -> str:
    """Render a 9x9 viewport grid with the player at center, plus a status bar."""
    if player.in_house:
        location = "house"
    elif player.in_village:
        location = "village"
    elif player.in_cave:
        location = "cave"
    else:
        location = "wilderness"

    lines: list[str] = []
    for row_y in range(VIEWPORT_SIZE):
        row_emojis: list[str] = []
        for col_x in range(VIEWPORT_SIZE):
            if col_x == VIEWPORT_CENTER and row_y == VIEWPORT_CENTER:
                row_emojis.append(ENTITY_EMOJI["player"])
            else:
                row_emojis.append(_tile_emoji(grid[row_y][col_x], location=location))
        lines.append("".join(row_emojis))

    # Status bar
    lines.append("")
    hp_bar = f"\u2764\uFE0F {player.hp}/{player.max_hp}"
    gold = f"\U0001F4B0 {player.gold}"
    if player.in_house:
        pos = f"\U0001F4CD House ({player.house_x},{player.house_y})"
    elif player.in_village:
        pos = f"\U0001F4CD Village ({player.village_x},{player.village_y})"
    elif player.in_cave:
        pos = f"\U0001F4CD Cave ({player.cave_x},{player.cave_y})"
    else:
        pos = f"\U0001F4CD Wilderness ({player.world_x},{player.world_y})"
    lines.append(f"{hp_bar}  {gold}  {pos}")

    if status_msg:
        lines.append(status_msg)

    return "\n".join(lines)
