from __future__ import annotations
from dataclasses import dataclass

from dwarf_explorer.config import (
    PLAYER_START_HP, PLAYER_START_ATTACK, PLAYER_START_DEFENSE,
    SPAWN_X, SPAWN_Y, DIRECTIONS, WORLD_SIZE, CAVE_WALKABLE,
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
    in_cave: bool = False
    cave_id: int | None = None
    cave_x: int = 0
    cave_y: int = 0


def can_move(player: Player, direction: str, target_tile: TileData) -> tuple[bool, str]:
    """Check if the player can move in the given direction.

    Returns (allowed, reason_if_blocked).
    """
    if player.in_cave:
        return _can_move_cave(target_tile)

    dx, dy = DIRECTIONS[direction]
    nx = player.world_x + dx
    ny = player.world_y + dy

    if nx < 0 or nx >= WORLD_SIZE or ny < 0 or ny >= WORLD_SIZE:
        return False, "You've reached the edge of the world!"

    if not target_tile.walkable:
        terrain = target_tile.structure or target_tile.terrain
        messages = {
            "mountain": "A mountain blocks your path.",
            "dense_forest": "The forest is too thick to pass through.",
            "shallow_water": "The water is too deep to cross.",
            "deep_water": "The ocean stretches endlessly before you.",
        }
        return False, messages.get(terrain, f"You can't walk through {terrain}.")

    return True, ""


def _can_move_cave(target_tile: TileData) -> tuple[bool, str]:
    """Check walkability inside a cave."""
    if target_tile.terrain == "void":
        return False, "You can't go that way."
    if target_tile.terrain not in CAVE_WALKABLE:
        return False, "A solid rock wall blocks your path."
    return True, ""
