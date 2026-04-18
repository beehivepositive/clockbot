from __future__ import annotations

import random

from dwarf_explorer.config import SPAWN_X, SPAWN_Y, PLAYER_START_HP, PLAYER_START_ATTACK, PLAYER_START_DEFENSE
from dwarf_explorer.database.connection import Database
from dwarf_explorer.game.player import Player


# --- World ---

async def get_or_create_world(db: Database, guild_id: int) -> int:
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
    row = await db.fetch_one("SELECT * FROM players WHERE user_id = ?", (user_id,))
    if row:
        # Load equipment
        eq_rows = await db.fetch_all(
            "SELECT slot, item_id FROM equipment WHERE user_id = ?", (user_id,)
        )
        equipped = {r["slot"]: r["item_id"] for r in eq_rows}
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
            house_type=row["house_type"] or "house",
            sprinting=bool(row["sprinting"]),
            weapon=equipped.get("weapon"),
            boots=equipped.get("boots"),
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
    if not kwargs:
        return
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    await db.execute(
        f"UPDATE players SET {set_clause}, last_active = datetime('now') WHERE user_id = ?",
        tuple(values),
    )


async def update_player_sprint(db: Database, user_id: int, sprinting: bool) -> None:
    await db.execute(
        "UPDATE players SET sprinting = ? WHERE user_id = ?",
        (int(sprinting), user_id),
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


async def get_cave_entrance_exit(
    db: Database, cave_id: int, local_x: int, local_y: int
) -> tuple[int, int] | None:
    row = await db.fetch_one(
        "SELECT world_x, world_y FROM cave_entrances "
        "WHERE cave_id = ? AND local_x = ? AND local_y = ?",
        (cave_id, local_x, local_y),
    )
    return (row["world_x"], row["world_y"]) if row else None


async def get_cave_at_position(db: Database, world_x: int, world_y: int) -> int | None:
    row = await db.fetch_one(
        "SELECT cave_id FROM cave_entrances WHERE world_x = ? AND world_y = ?",
        (world_x, world_y),
    )
    return row["cave_id"] if row else None


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
    house_type: str = "house",
) -> None:
    await db.execute(
        "UPDATE players SET in_house = ?, house_id = ?, house_x = ?, house_y = ?, "
        "house_vx = ?, house_vy = ?, house_type = ?, last_active = datetime('now') WHERE user_id = ?",
        (int(in_house), house_id, house_x, house_y, house_vx, house_vy, house_type, user_id),
    )


# --- Equipment ---

async def equip_item(db: Database, user_id: int, slot: str, item_id: str) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO equipment (user_id, slot, item_id) VALUES (?, ?, ?)",
        (user_id, slot, item_id),
    )


async def unequip_item(db: Database, user_id: int, slot: str) -> None:
    await db.execute(
        "DELETE FROM equipment WHERE user_id = ? AND slot = ?",
        (user_id, slot),
    )


# --- Inventory ---

async def get_inventory(db: Database, user_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? ORDER BY rowid",
        (user_id,),
    )
    return [{"item_id": r["item_id"], "quantity": r["quantity"]} for r in rows]


async def add_to_inventory(db: Database, user_id: int, item_id: str, quantity: int = 1) -> None:
    await db.execute(
        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
        (user_id, item_id, quantity, quantity),
    )


async def remove_from_inventory(db: Database, user_id: int, item_id: str, quantity: int = 1) -> bool:
    """Remove quantity of item. Returns True if successful."""
    row = await db.fetch_one(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    )
    if not row or row["quantity"] < quantity:
        return False
    new_qty = row["quantity"] - quantity
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM inventory WHERE user_id = ? AND item_id = ?",
            (user_id, item_id),
        )
    else:
        await db.execute(
            "UPDATE inventory SET quantity = ? WHERE user_id = ? AND item_id = ?",
            (new_qty, user_id, item_id),
        )
    return True


# --- Bank ---

async def get_bank_items(db: Database, user_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT item_id, quantity FROM bank_items WHERE user_id = ? ORDER BY rowid",
        (user_id,),
    )
    return [{"item_id": r["item_id"], "quantity": r["quantity"]} for r in rows]


async def bank_deposit(db: Database, user_id: int, item_id: str, quantity: int = 1) -> bool:
    removed = await remove_from_inventory(db, user_id, item_id, quantity)
    if not removed:
        return False
    await db.execute(
        "INSERT INTO bank_items (user_id, item_id, quantity) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
        (user_id, item_id, quantity, quantity),
    )
    return True


async def bank_withdraw(db: Database, user_id: int, item_id: str, quantity: int = 1) -> bool:
    row = await db.fetch_one(
        "SELECT quantity FROM bank_items WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    )
    if not row or row["quantity"] < quantity:
        return False
    new_qty = row["quantity"] - quantity
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM bank_items WHERE user_id = ? AND item_id = ?",
            (user_id, item_id),
        )
    else:
        await db.execute(
            "UPDATE bank_items SET quantity = ? WHERE user_id = ? AND item_id = ?",
            (new_qty, user_id, item_id),
        )
    await add_to_inventory(db, user_id, item_id, quantity)
    return True
