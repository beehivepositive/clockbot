from __future__ import annotations

import random

from dwarf_explorer.config import SPAWN_X, SPAWN_Y, PLAYER_START_HP, PLAYER_START_ATTACK, PLAYER_START_DEFENSE
from dwarf_explorer.database.connection import Database
from dwarf_explorer.game.player import Player


# --- World ---

async def get_or_create_world(db: Database, guild_id: int) -> int:
    """Get the world seed for a guild, creating the world if needed. Returns the seed."""
    row = await db.fetch_one("SELECT seed FROM world WHERE guild_id = ?", (guild_id,))
    if row:
        return row["seed"]
    seed = random.randint(0, 2**31)
    await db.execute(
        "INSERT INTO world (guild_id, seed, initialized) VALUES (?, ?, 0)",
        (guild_id, seed),
    )
    return seed


async def is_world_initialized(db: Database, guild_id: int) -> bool:
    row = await db.fetch_one("SELECT initialized FROM world WHERE guild_id = ?", (guild_id,))
    return bool(row and row["initialized"])


async def mark_world_initialized(db: Database, guild_id: int) -> None:
    await db.execute("UPDATE world SET initialized = 1 WHERE guild_id = ?", (guild_id,))


# --- Players ---

async def get_or_create_player(db: Database, user_id: int, display_name: str) -> Player:
    """Load a player from the DB, or create a new one at spawn."""
    row = await db.fetch_one("SELECT * FROM players WHERE user_id = ?", (user_id,))
    if row:
        return Player(
            user_id=row["user_id"],
            display_name=row["display_name"],
            world_x=row["world_x"],
            world_y=row["world_y"],
            hp=row["hp"],
            max_hp=row["max_hp"],
            attack=row["attack"],
            defense=row["defense"],
            gold=row["gold"],
            xp=row["xp"],
            level=row["level"],
            message_id=row["message_id"],
            channel_id=row["channel_id"],
            in_cave=bool(row["in_cave"]),
            cave_id=row["cave_id"],
            cave_x=row["cave_x"] or 0,
            cave_y=row["cave_y"] or 0,
            in_village=bool(row["in_village"]),
            village_id=row["village_id"],
            village_x=row["village_x"] or 0,
            village_y=row["village_y"] or 0,
            village_wx=row["village_wx"] or 0,
            village_wy=row["village_wy"] or 0,
            in_house=bool(row["in_house"]),
            house_id=row["house_id"],
            house_x=row["house_x"] or 0,
            house_y=row["house_y"] or 0,
            house_vx=row["house_vx"] or 0,
            house_vy=row["house_vy"] or 0,
        )
    await db.execute(
        "INSERT INTO players (user_id, display_name, world_x, world_y, hp, max_hp, attack, defense) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, display_name, SPAWN_X, SPAWN_Y,
         PLAYER_START_HP, PLAYER_START_HP, PLAYER_START_ATTACK, PLAYER_START_DEFENSE),
    )
    return Player(user_id=user_id, display_name=display_name)


async def update_player_position(db: Database, user_id: int, x: int, y: int) -> None:
    await db.execute(
        "UPDATE players SET world_x = ?, world_y = ?, last_active = datetime('now') WHERE user_id = ?",
        (x, y, user_id),
    )


async def update_player_message(db: Database, user_id: int, message_id: int, channel_id: int) -> None:
    await db.execute(
        "UPDATE players SET message_id = ?, channel_id = ? WHERE user_id = ?",
        (message_id, channel_id, user_id),
    )


async def update_player_stats(db: Database, user_id: int, **kwargs) -> None:
    """Update arbitrary player stats. Keys must match column names."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    await db.execute(
        f"UPDATE players SET {set_clause}, last_active = datetime('now') WHERE user_id = ?",
        tuple(values),
    )


# --- Caves ---

async def update_player_cave_state(
    db: Database, user_id: int, in_cave: bool, cave_id: int | None, cave_x: int, cave_y: int
) -> None:
    await db.execute(
        "UPDATE players SET in_cave = ?, cave_id = ?, cave_x = ?, cave_y = ?, "
        "last_active = datetime('now') WHERE user_id = ?",
        (int(in_cave), cave_id, cave_x, cave_y, user_id),
    )


# --- Villages ---

async def update_player_village_state(
    db: Database, user_id: int,
    in_village: bool, village_id: int | None,
    village_x: int, village_y: int,
    village_wx: int, village_wy: int,
) -> None:
    await db.execute(
        "UPDATE players SET in_village = ?, village_id = ?, village_x = ?, village_y = ?, "
        "village_wx = ?, village_wy = ?, last_active = datetime('now') WHERE user_id = ?",
        (int(in_village), village_id, village_x, village_y, village_wx, village_wy, user_id),
    )


async def update_player_house_state(
    db: Database, user_id: int,
    in_house: bool, house_id: int | None,
    house_x: int, house_y: int,
    house_vx: int, house_vy: int,
) -> None:
    await db.execute(
        "UPDATE players SET in_house = ?, house_id = ?, house_x = ?, house_y = ?, "
        "house_vx = ?, house_vy = ?, last_active = datetime('now') WHERE user_id = ?",
        (int(in_house), house_id, house_x, house_y, house_vx, house_vy, user_id),
    )


# --- Caves ---

async def get_cave_at_position(db: Database, world_x: int, world_y: int) -> int | None:
    """Look up a cave_id from its wilderness entrance position."""
    row = await db.fetch_one(
        "SELECT cave_id FROM cave_entrances WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    return row["cave_id"] if row else None


async def get_cave_entrance_exit(
    db: Database, cave_id: int, local_x: int, local_y: int
) -> tuple[int, int] | None:
    """Get the wilderness (world_x, world_y) for a cave entrance tile."""
    row = await db.fetch_one(
        "SELECT world_x, world_y FROM cave_entrances "
        "WHERE cave_id = ? AND local_x = ? AND local_y = ?",
        (cave_id, local_x, local_y),
    )
    return (row["world_x"], row["world_y"]) if row else None
