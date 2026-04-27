from __future__ import annotations
from dataclasses import dataclass

from dwarf_explorer.config import (
    PLAYER_START_HP, PLAYER_START_ATTACK, PLAYER_START_DEFENSE,
    SPAWN_X, SPAWN_Y, DIRECTIONS, WORLD_SIZE,
    CAVE_WALKABLE, VILLAGE_WALKABLE, BUILDING_WALKABLE, PLAYER_HOUSE_DECO_TILES,
    COMBAT_MOVES_DEFAULT, CANOE_PASSABLE,
)
from dwarf_explorer.world.generator import TileData


@dataclass
class Player:
    user_id: int
    display_name: str
    world_x: int = SPAWN_X
    world_y: int = SPAWN_Y
    hp: int = PLAYER_START_HP
    max_hp: int = PLAYER_START_HP
    attack: int = PLAYER_START_ATTACK
    defense: int = PLAYER_START_DEFENSE
    gold: int = 0
    xp: int = 0
    level: int = 1
    message_id: int | None = None
    channel_id: int | None = None
    # Cave state
    in_cave: bool = False
    cave_id: int | None = None
    cave_x: int = 0
    cave_y: int = 0
    # Village state
    in_village: bool = False
    village_id: int | None = None
    village_x: int = 0
    village_y: int = 0
    village_wx: int = 0
    village_wy: int = 0
    # Building (house/church/bank/shop) state
    in_house: bool = False
    house_id: int | None = None
    house_x: int = 0
    house_y: int = 0
    house_vx: int = 0
    house_vy: int = 0
    house_type: str = "house"   # "house" | "church" | "bank" | "shop" | "player_house"
    ph_cave_id: int | None = None  # if set, exiting player_house returns to this cave
    # Canoe state
    in_canoe: bool = False
    # Ocean state
    in_ocean: bool = False
    ocean_x: int = 0
    ocean_y: int = 0
    ocean_harbor_wx: int = 0   # overworld x of harbor used to enter
    ocean_harbor_wy: int = 0   # overworld y of harbor used to enter
    # Combat state
    in_combat: bool = False
    combat_enemy_type: str | None = None
    combat_enemy_hp: int = 0
    combat_enemy_x: int = 0
    combat_enemy_y: int = 0
    combat_player_x: int = 4
    combat_player_y: int = 4
    combat_moves_left: int = COMBAT_MOVES_DEFAULT
    # Equipment & sprint
    sprinting: bool = False
    hand_1: str | None = None
    hand_2: str | None = None
    head: str | None = None
    chest: str | None = None
    legs: str | None = None
    boots: str | None = None
    accessory: str | None = None
    pouch: str | None = None


def can_move_village(target_tile: TileData) -> tuple[bool, str]:
    """Walkability inside a village. void triggers exit in game_view."""
    if target_tile.terrain == "void":
        return True, ""   # game_view handles the exit
    if target_tile.terrain not in VILLAGE_WALKABLE:
        return False, "That's in the way."
    return True, ""


def can_move_building(target_tile: TileData) -> tuple[bool, str]:
    """Walkability inside a building."""
    if target_tile.terrain == "void":
        return False, "You can't go that way."
    if target_tile.terrain not in BUILDING_WALKABLE:
        return False, "That's in the way."
    return True, ""


def can_move(player: Player, direction: str, target_tile: TileData) -> tuple[bool, str]:
    """Check if the player can move in the given direction."""
    if player.in_house:
        return can_move_building(target_tile)
    if player.in_village:
        return can_move_village(target_tile)
    if player.in_cave:
        return _can_move_cave(target_tile)

    terrain = target_tile.structure or target_tile.terrain

    # Canoe movement: only water and bridge tiles
    if player.in_canoe:
        if terrain not in CANOE_PASSABLE:
            return False, "You can't paddle onto land. Dock at a 🚩 landing first."
        return True, ""

    # Eight directional vectors (cardinal + diagonal) for canoe mode;
    # cardinal-only for overworld walking
    _DIRS_8 = {
        "up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0),
        "upleft": (-1, -1), "upright": (1, -1),
        "downleft": (-1, 1), "downright": (1, 1),
    }
    vec = _DIRS_8.get(direction, DIRECTIONS.get(direction, (0, 0)))
    dx, dy = vec
    nx = player.world_x + dx
    ny = player.world_y + dy

    if nx < 0 or nx >= WORLD_SIZE or ny < 0 or ny >= WORLD_SIZE:
        return False, "You've reached the edge of the world!"

    if not target_tile.walkable:
        messages = {
            "mountain": "A mountain blocks your path.",
            "snow": "The snowy mountains are impassable.",
            "dense_forest": "The forest is too thick to pass through.",
            "shallow_water": "The water is too deep to cross.",
            "deep_water": "The ocean stretches endlessly before you.",
        }
        return False, messages.get(terrain, f"You can't walk through {terrain}.")

    return True, ""


def _can_move_cave(target_tile: TileData) -> tuple[bool, str]:
    if target_tile.terrain == "void":
        return False, "You can't go that way."
    if target_tile.terrain not in CAVE_WALKABLE:
        return False, "A solid rock wall blocks your path."
    return True, ""
