from __future__ import annotations

import random

from dwarf_explorer.config import (
    SPAWN_X, SPAWN_Y, PLAYER_START_HP, PLAYER_START_ATTACK, PLAYER_START_DEFENSE,
    COMBAT_MOVES_DEFAULT, OCEAN_SIZE, MAX_STACK_SIZE, COIN_PURSE_CAPACITY,
)
from dwarf_explorer.database.connection import Database
from dwarf_explorer.game.player import Player


# --- World ---
# All servers share one world stored under guild_id = 0 (global key).
_GLOBAL_WORLD_KEY = 0


async def get_or_create_world(db: Database, guild_id: int) -> int:
    """Return the current world seed. All guilds share one world (guild_id ignored)."""
    row = await db.fetch_one("SELECT seed FROM world WHERE guild_id = ?", (_GLOBAL_WORLD_KEY,))
    if row:
        return row["seed"]
    # First run ever — pick a random seed and store it
    new_seed = random.randint(1, 2**31 - 1)
    await db.execute(
        "INSERT INTO world (guild_id, seed, initialized) VALUES (?, ?, 0)",
        (_GLOBAL_WORLD_KEY, new_seed),
    )
    return new_seed


async def is_world_initialized(db: Database, guild_id: int) -> bool:
    row = await db.fetch_one("SELECT initialized FROM world WHERE guild_id = ?", (_GLOBAL_WORLD_KEY,))
    return bool(row and row["initialized"])


async def mark_world_initialized(db: Database, guild_id: int) -> None:
    await db.execute("UPDATE world SET initialized = 1 WHERE guild_id = ?", (_GLOBAL_WORLD_KEY,))


async def reset_world_seed(db: Database) -> int:
    """Generate a fresh random seed, clear initialized flag, return the new seed."""
    new_seed = random.randint(1, 2**31 - 1)
    row = await db.fetch_one("SELECT guild_id FROM world WHERE guild_id = ?", (_GLOBAL_WORLD_KEY,))
    if row:
        await db.execute(
            "UPDATE world SET seed = ?, initialized = 0 WHERE guild_id = ?",
            (new_seed, _GLOBAL_WORLD_KEY),
        )
    else:
        await db.execute(
            "INSERT INTO world (guild_id, seed, initialized) VALUES (?, ?, 0)",
            (_GLOBAL_WORLD_KEY, new_seed),
        )
    return new_seed


# --- Players ---

async def get_or_create_player(db: Database, user_id: int, display_name: str) -> Player:
    row = await db.fetch_one("SELECT * FROM players WHERE user_id = ?", (user_id,))
    if row:
        # Load equipment — migrate old slot names if present
        eq_rows = await db.fetch_all(
            "SELECT slot, item_id FROM equipment WHERE user_id = ?", (user_id,)
        )
        equipped = {r["slot"]: r["item_id"] for r in eq_rows}

        # Migrate legacy slot names
        if "weapon" in equipped and "hand_1" not in equipped:
            equipped["hand_1"] = equipped.pop("weapon")
            await db.execute(
                "UPDATE equipment SET slot='hand_1' WHERE user_id=? AND slot='weapon'", (user_id,)
            )
        if "light" in equipped:
            if "hand_1" not in equipped:
                equipped["hand_1"] = equipped.pop("light")
                await db.execute(
                    "UPDATE equipment SET slot='hand_1' WHERE user_id=? AND slot='light'", (user_id,)
                )
            elif "hand_2" not in equipped:
                equipped["hand_2"] = equipped.pop("light")
                await db.execute(
                    "UPDATE equipment SET slot='hand_2' WHERE user_id=? AND slot='light'", (user_id,)
                )
            else:
                equipped.pop("light")
                await db.execute(
                    "DELETE FROM equipment WHERE user_id=? AND slot='light'", (user_id,)
                )

        # Give torch for testing if player doesn't already have one
        has_torch_equipped = equipped.get("hand_1") == "torch" or equipped.get("hand_2") == "torch"
        if not has_torch_equipped:
            torch_row = await db.fetch_one(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = 'torch'",
                (user_id,),
            )
            if not torch_row:
                await add_to_inventory(db, user_id, "torch", 1)

        cols = row.keys()
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
            # Canoe state
            in_canoe=bool(row["in_canoe"]) if "in_canoe" in cols else False,
            # Combat state
            in_combat=bool(row["in_combat"]) if "in_combat" in cols else False,
            combat_enemy_type=row["combat_enemy_type"] if "combat_enemy_type" in cols else None,
            combat_enemy_hp=row["combat_enemy_hp"] if "combat_enemy_hp" in cols else 0,
            combat_enemy_x=row["combat_enemy_x"] if "combat_enemy_x" in cols else 0,
            combat_enemy_y=row["combat_enemy_y"] if "combat_enemy_y" in cols else 0,
            combat_player_x=row["combat_player_x"] if "combat_player_x" in cols else 4,
            combat_player_y=row["combat_player_y"] if "combat_player_y" in cols else 4,
            combat_moves_left=row["combat_moves_left"] if "combat_moves_left" in cols else COMBAT_MOVES_DEFAULT,
            sprinting=bool(row["sprinting"]),
            ph_cave_id=row["ph_cave_id"] if "ph_cave_id" in cols else None,
            # Ocean / boat state
            in_ocean=bool(row["in_ocean"]) if "in_ocean" in cols else False,
            in_high_seas=bool(row["in_high_seas"]) if "in_high_seas" in cols else False,
            in_ship=bool(row["in_ship"]) if "in_ship" in cols else False,
            ship_room=row["ship_room"] if "ship_room" in cols else "helm",
            ship_hp=row["ship_hp"] if "ship_hp" in cols else 100,
            ship_max_hp=row["ship_max_hp"] if "ship_max_hp" in cols else 100,
            ship_x=row["ship_x"] if "ship_x" in cols else 0,
            ship_y=row["ship_y"] if "ship_y" in cols else 0,
            in_island=bool(row["in_island"]) if "in_island" in cols else False,
            island_ox=row["island_ox"] if "island_ox" in cols else 0,
            island_oy=row["island_oy"] if "island_oy" in cols else 0,
            ocean_x=row["ocean_x"] if "ocean_x" in cols else 0,
            ocean_y=row["ocean_y"] if "ocean_y" in cols else 0,
            ocean_harbor_wx=row["ocean_harbor_wx"] if "ocean_harbor_wx" in cols else 0,
            ocean_harbor_wy=row["ocean_harbor_wy"] if "ocean_harbor_wy" in cols else 0,
            hand_1=equipped.get("hand_1"),
            hand_2=equipped.get("hand_2"),
            head=equipped.get("head"),
            chest=equipped.get("chest"),
            legs=equipped.get("legs"),
            boots=equipped.get("boots"),
            accessory=equipped.get("accessory"),
            pouch=equipped.get("pouch"),
            coin_purse=equipped.get("coin_purse"),
        )
    await db.execute(
        "INSERT INTO players (user_id, display_name, world_x, world_y, hp, max_hp, attack, defense) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, display_name, SPAWN_X, SPAWN_Y,
         PLAYER_START_HP, PLAYER_START_HP, PLAYER_START_ATTACK, PLAYER_START_DEFENSE),
    )
    await add_to_inventory(db, user_id, "torch", 1)
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


async def get_nearby_players(
    db: Database, exclude_user_id: int, wx: int, wy: int, radius: int = 4
) -> list[tuple[int, int, str]]:
    """Return [(world_x, world_y, display_name)] for overworld players within radius tiles."""
    rows = await db.fetch_all(
        "SELECT world_x, world_y, display_name FROM players"
        " WHERE user_id != ? AND in_cave = 0 AND in_village = 0 AND in_house = 0"
        " AND COALESCE(in_ocean, 0) = 0"
        " AND world_x BETWEEN ? AND ? AND world_y BETWEEN ? AND ?",
        (exclude_user_id, wx - radius, wx + radius, wy - radius, wy + radius),
    )
    return [(r["world_x"], r["world_y"], r["display_name"]) for r in rows]


async def get_all_overworld_players(
    db: Database, exclude_user_id: int
) -> list[tuple[int, int, str]]:
    """Return [(world_x, world_y, display_name)] for all overworld players."""
    rows = await db.fetch_all(
        "SELECT world_x, world_y, display_name FROM players"
        " WHERE user_id != ? AND in_cave = 0 AND in_village = 0 AND in_house = 0"
        " AND COALESCE(in_ocean, 0) = 0",
        (exclude_user_id,),
    )
    return [(r["world_x"], r["world_y"], r["display_name"]) for r in rows]


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
        "SELECT id, item_id, quantity, slot_index FROM inventory"
        " WHERE user_id = ? ORDER BY slot_index, id",
        (user_id,),
    )
    return [{"item_id": r["item_id"], "quantity": r["quantity"], "slot_index": r["slot_index"]} for r in rows]


async def _next_slot_index(db: Database, user_id: int) -> int:
    """Return the next available slot_index for a user (max + 1, or 0 if empty)."""
    row = await db.fetch_one(
        "SELECT COALESCE(MAX(slot_index) + 1, 0) AS next_idx FROM inventory WHERE user_id = ?",
        (user_id,),
    )
    return row["next_idx"] if row else 0


async def get_inventory_slot_count(db: Database, user_id: int) -> int:
    """Return the number of occupied inventory slots for a user."""
    row = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM inventory WHERE user_id = ?", (user_id,)
    )
    return row["cnt"] if row else 0


async def add_to_inventory(
    db: Database, user_id: int, item_id: str, quantity: int = 1,
    max_slots: int | None = None,
) -> int:
    """Add quantity of item_id, filling existing stacks first, then creating new slots.

    If max_slots is given, no new slots are created beyond that count.
    Returns the leftover quantity that could not be stored (0 = all fit).
    """
    remaining = quantity
    # Fill existing stacks that have room
    rows = await db.fetch_all(
        "SELECT id, quantity FROM inventory WHERE user_id = ? AND item_id = ? ORDER BY slot_index, id",
        (user_id, item_id),
    )
    for row in rows:
        if remaining <= 0:
            break
        space = MAX_STACK_SIZE - row["quantity"]
        if space > 0:
            add = min(space, remaining)
            await db.execute("UPDATE inventory SET quantity = quantity + ? WHERE id = ?", (add, row["id"]))
            remaining -= add
    # Create new slots for any overflow, respecting the slot cap
    while remaining > 0:
        if max_slots is not None:
            used = await get_inventory_slot_count(db, user_id)
            if used >= max_slots:
                break   # inventory full — return whatever is left
        add = min(MAX_STACK_SIZE, remaining)
        next_idx = await _next_slot_index(db, user_id)
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity, slot_index) VALUES (?, ?, ?, ?)",
            (user_id, item_id, add, next_idx),
        )
        remaining -= add
    return remaining  # 0 means everything fit


async def remove_from_inventory(db: Database, user_id: int, item_id: str, quantity: int = 1) -> bool:
    """Remove quantity of item across all stacks (LIFO by slot_index). Returns True if successful."""
    rows = await db.fetch_all(
        "SELECT id, quantity FROM inventory WHERE user_id = ? AND item_id = ? ORDER BY slot_index DESC, id DESC",
        (user_id, item_id),
    )
    total_have = sum(r["quantity"] for r in rows)
    if total_have < quantity:
        return False
    remaining = quantity
    for row in rows:
        if remaining <= 0:
            break
        take = min(row["quantity"], remaining)
        if take == row["quantity"]:
            await db.execute("DELETE FROM inventory WHERE id = ?", (row["id"],))
        else:
            await db.execute("UPDATE inventory SET quantity = quantity - ? WHERE id = ?", (take, row["id"]))
        remaining -= take
    # Compact slot_index after removal to avoid gaps
    await _compact_slot_index(db, user_id)
    return True


async def _compact_slot_index(db: Database, user_id: int) -> None:
    """Renumber slot_index values so they're contiguous starting from 0."""
    rows = await db.fetch_all(
        "SELECT id FROM inventory WHERE user_id = ? ORDER BY slot_index, id",
        (user_id,),
    )
    for new_idx, row in enumerate(rows):
        await db.execute("UPDATE inventory SET slot_index = ? WHERE id = ?", (new_idx, row["id"]))


async def swap_inventory_slots(db: Database, user_id: int, slot_a: int, slot_b: int) -> None:
    """Swap two inventory slots by their slot_index values."""
    if slot_a == slot_b:
        return
    # Use a temporary large index to avoid collisions during swap
    tmp_idx = 999999
    await db.execute(
        "UPDATE inventory SET slot_index = ? WHERE user_id = ? AND slot_index = ?",
        (tmp_idx, user_id, slot_a),
    )
    await db.execute(
        "UPDATE inventory SET slot_index = ? WHERE user_id = ? AND slot_index = ?",
        (slot_a, user_id, slot_b),
    )
    await db.execute(
        "UPDATE inventory SET slot_index = ? WHERE user_id = ? AND slot_index = ?",
        (slot_b, user_id, tmp_idx),
    )


# --- Drop boxes ---

async def create_drop_box(
    db: Database, world_x: int, world_y: int, items: list[tuple[str, int]]
) -> None:
    """Create a drop box at (world_x, world_y) with the given items.

    Items dropped on an existing box are merged into it.
    A tile_override of 'drop_box' is inserted (or left existing) so the renderer shows 📦.
    """
    # Upsert the tile_override
    await db.execute(
        "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'drop_box')",
        (world_x, world_y),
    )
    # Merge items into ground_items (upsert by position + item_id for drop rows)
    for item_id, qty in items:
        existing = await db.fetch_one(
            "SELECT id, quantity FROM ground_items WHERE world_x=? AND world_y=? AND item_id=? AND is_drop=1",
            (world_x, world_y, item_id),
        )
        if existing:
            await db.execute(
                "UPDATE ground_items SET quantity=quantity+?, spawned_at=datetime('now') WHERE id=?",
                (qty, existing["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO ground_items (world_x, world_y, item_id, quantity, is_drop)"
                " VALUES (?, ?, ?, ?, 1)",
                (world_x, world_y, item_id, qty),
            )


async def pickup_drop_box(
    db: Database, world_x: int, world_y: int, user_id: int
) -> list[tuple[str, int]]:
    """Pick up all items in a drop box at (world_x, world_y) into user's inventory.

    Returns list of (item_id, qty) actually picked up.
    """
    items = await db.fetch_all(
        "SELECT id, item_id, quantity FROM ground_items WHERE world_x=? AND world_y=? AND is_drop=1",
        (world_x, world_y),
    )
    picked = []
    for row in items:
        await add_to_inventory(db, user_id, row["item_id"], row["quantity"])
        await db.execute("DELETE FROM ground_items WHERE id=?", (row["id"],))
        picked.append((row["item_id"], row["quantity"]))
    # Remove tile_override if no drop items remain
    remaining = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM ground_items WHERE world_x=? AND world_y=? AND is_drop=1",
        (world_x, world_y),
    )
    if remaining and remaining["cnt"] == 0:
        await db.execute(
            "DELETE FROM tile_overrides WHERE world_x=? AND world_y=? AND tile_type='drop_box'",
            (world_x, world_y),
        )
    return picked


async def cleanup_expired_drop_boxes(db: Database) -> None:
    """Delete drop box items older than 1 hour and remove their tile_overrides."""
    expired_positions = await db.fetch_all(
        "SELECT DISTINCT world_x, world_y FROM ground_items"
        " WHERE is_drop=1 AND spawned_at < datetime('now', '-1 hour')",
    )
    for pos in expired_positions:
        await db.execute(
            "DELETE FROM ground_items WHERE world_x=? AND world_y=? AND is_drop=1",
            (pos["world_x"], pos["world_y"]),
        )
        await db.execute(
            "DELETE FROM tile_overrides WHERE world_x=? AND world_y=? AND tile_type='drop_box'",
            (pos["world_x"], pos["world_y"]),
        )


# --- Gold cap ---

async def add_player_gold(db: Database, user_id: int, delta: int, capacity: int) -> tuple[int, int]:
    """Add delta gold respecting capacity. Returns (actual_added, overflow)."""
    row = await db.fetch_one("SELECT gold FROM players WHERE user_id=?", (user_id,))
    current = row["gold"] if row else 0
    new_val = max(0, min(current + delta, capacity))
    await db.execute("UPDATE players SET gold=? WHERE user_id=?", (new_val, user_id))
    actual = new_val - current
    overflow = delta - actual if delta > 0 else 0
    return actual, overflow


# --- Bank ---

async def get_bank_items(db: Database, user_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT item_id, quantity FROM bank_items WHERE user_id = ? ORDER BY rowid",
        (user_id,),
    )
    # Split oversized stacks into MAX_STACK_SIZE chunks so the vault grid respects limits.
    # gold_coin is never split — it has no cap in the bank.
    result = []
    slot_idx = 0
    for r in rows:
        if r["item_id"] == "gold_coin":
            result.append({"item_id": "gold_coin", "quantity": r["quantity"], "slot_index": slot_idx})
            slot_idx += 1
            continue
        remaining = r["quantity"]
        while remaining > 0:
            stack_qty = min(MAX_STACK_SIZE, remaining)
            result.append({"item_id": r["item_id"], "quantity": stack_qty, "slot_index": slot_idx})
            remaining -= stack_qty
            slot_idx += 1
    return result


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


async def bank_withdraw(db: Database, user_id: int, item_id: str, quantity: int = 1,
                        gold_cap: int | None = None) -> bool:
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
    # Gold goes back to players.gold, not inventory
    if item_id == "gold_coin":
        if gold_cap is not None:
            await db.execute(
                "UPDATE players SET gold = MIN(gold + ?, ?) WHERE user_id = ?",
                (quantity, gold_cap, user_id),
            )
        else:
            await db.execute(
                "UPDATE players SET gold = gold + ? WHERE user_id = ?",
                (quantity, user_id),
            )
    else:
        await add_to_inventory(db, user_id, item_id, quantity)
    return True


# --- Combat state ---

async def save_combat_state(db: Database, user_id: int, player) -> None:
    await db.execute(
        "UPDATE players SET in_combat=?, combat_enemy_type=?, combat_enemy_hp=?,"
        " combat_enemy_x=?, combat_enemy_y=?, combat_player_x=?, combat_player_y=?,"
        " combat_moves_left=?, hp=? WHERE user_id=?",
        (int(player.in_combat), player.combat_enemy_type, player.combat_enemy_hp,
         player.combat_enemy_x, player.combat_enemy_y,
         player.combat_player_x, player.combat_player_y,
         player.combat_moves_left, player.hp, user_id),
    )


async def clear_combat_state(db: Database, user_id: int) -> None:
    await db.execute(
        "UPDATE players SET in_combat=0, combat_enemy_type=NULL, combat_enemy_hp=0,"
        " combat_enemy_x=0, combat_enemy_y=0, combat_player_x=4, combat_player_y=4,"
        " combat_moves_left=3 WHERE user_id=?",
        (user_id,),
    )


# --- Ocean / boat state ---

async def update_player_ocean_state(
    db: Database, user_id: int,
    in_ocean: bool, ocean_x: int = 0, ocean_y: int = 0,
    harbor_wx: int | None = None, harbor_wy: int | None = None,
    in_high_seas: bool = False,
) -> None:
    """Update ocean/boat state.

    in_ocean=True      → boat mode on wilderness ocean tiles
    in_high_seas=True  → navigating the separate 200×200 open-ocean grid
    """
    if harbor_wx is not None and harbor_wy is not None:
        await db.execute(
            "UPDATE players SET in_ocean=?, in_high_seas=?, ocean_x=?, ocean_y=?,"
            " ocean_harbor_wx=?, ocean_harbor_wy=? WHERE user_id=?",
            (int(in_ocean), int(in_high_seas), ocean_x, ocean_y,
             harbor_wx, harbor_wy, user_id),
        )
    else:
        await db.execute(
            "UPDATE players SET in_ocean=?, in_high_seas=?, ocean_x=?, ocean_y=?"
            " WHERE user_id=?",
            (int(in_ocean), int(in_high_seas), ocean_x, ocean_y, user_id),
        )


# --- Ship state ---

async def update_player_ship_state(
    db: Database, user_id: int,
    in_ship: bool, ship_room: str = "helm",
    ship_x: int | None = None, ship_y: int | None = None,
) -> None:
    if ship_x is not None and ship_y is not None:
        await db.execute(
            "UPDATE players SET in_ship=?, ship_room=?, ship_x=?, ship_y=? WHERE user_id=?",
            (int(in_ship), ship_room, ship_x, ship_y, user_id),
        )
    else:
        await db.execute(
            "UPDATE players SET in_ship=?, ship_room=? WHERE user_id=?",
            (int(in_ship), ship_room, user_id),
        )


async def update_player_ship_hp(
    db: Database, user_id: int, hp: int, max_hp: int | None = None,
) -> None:
    if max_hp is not None:
        await db.execute(
            "UPDATE players SET ship_hp=?, ship_max_hp=? WHERE user_id=?",
            (hp, max_hp, user_id),
        )
    else:
        await db.execute(
            "UPDATE players SET ship_hp=? WHERE user_id=?",
            (hp, user_id),
        )


async def get_ship_personal_items(db: Database, user_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT item_id, quantity FROM ship_personal_items WHERE user_id=? ORDER BY rowid",
        (user_id,),
    )
    return [{"item_id": r["item_id"], "quantity": r["quantity"]} for r in rows]


async def ship_personal_deposit(
    db: Database, user_id: int, item_id: str, quantity: int = 1
) -> bool:
    from dwarf_explorer.database.repositories import remove_from_inventory
    removed = await remove_from_inventory(db, user_id, item_id, quantity)
    if not removed:
        return False
    await db.execute(
        "INSERT INTO ship_personal_items (user_id, item_id, quantity) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity",
        (user_id, item_id, quantity),
    )
    return True


async def ship_personal_withdraw(
    db: Database, user_id: int, item_id: str, quantity: int = 1
) -> bool:
    row = await db.fetch_one(
        "SELECT quantity FROM ship_personal_items WHERE user_id=? AND item_id=?",
        (user_id, item_id),
    )
    if not row or row["quantity"] < quantity:
        return False
    new_qty = row["quantity"] - quantity
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM ship_personal_items WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
    else:
        await db.execute(
            "UPDATE ship_personal_items SET quantity=? WHERE user_id=? AND item_id=?",
            (new_qty, user_id, item_id),
        )
    from dwarf_explorer.database.repositories import add_to_inventory
    await add_to_inventory(db, user_id, item_id, quantity)
    return True


async def get_ship_cargo_items(db: Database, user_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT item_id, quantity FROM ship_cargo_items WHERE user_id=? ORDER BY rowid",
        (user_id,),
    )
    return [{"item_id": r["item_id"], "quantity": r["quantity"]} for r in rows]


async def ship_cargo_deposit(
    db: Database, user_id: int, item_id: str, quantity: int = 1
) -> bool:
    from dwarf_explorer.database.repositories import remove_from_inventory
    removed = await remove_from_inventory(db, user_id, item_id, quantity)
    if not removed:
        return False
    await db.execute(
        "INSERT INTO ship_cargo_items (user_id, item_id, quantity) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity",
        (user_id, item_id, quantity),
    )
    return True


async def ship_cargo_withdraw(
    db: Database, user_id: int, item_id: str, quantity: int = 1
) -> bool:
    row = await db.fetch_one(
        "SELECT quantity FROM ship_cargo_items WHERE user_id=? AND item_id=?",
        (user_id, item_id),
    )
    if not row or row["quantity"] < quantity:
        return False
    new_qty = row["quantity"] - quantity
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM ship_cargo_items WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
    else:
        await db.execute(
            "UPDATE ship_cargo_items SET quantity=? WHERE user_id=? AND item_id=?",
            (new_qty, user_id, item_id),
        )
    from dwarf_explorer.database.repositories import add_to_inventory
    await add_to_inventory(db, user_id, item_id, quantity)
    return True


async def ship_cargo_consume(
    db, user_id: int, item_id: str, quantity: int = 1
) -> bool:
    """Remove items from ship cargo without adding to player inventory (consumed in place)."""
    row = await db.fetch_one(
        "SELECT quantity FROM ship_cargo_items WHERE user_id=? AND item_id=?",
        (user_id, item_id),
    )
    if not row or row["quantity"] < quantity:
        return False
    new_qty = row["quantity"] - quantity
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM ship_cargo_items WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
    else:
        await db.execute(
            "UPDATE ship_cargo_items SET quantity=? WHERE user_id=? AND item_id=?",
            (new_qty, user_id, item_id),
        )
    return True


# --- Island state ---

async def update_player_island_state(
    db: Database, user_id: int,
    in_island: bool, ox: int = 0, oy: int = 0,
) -> None:
    await db.execute(
        "UPDATE players SET in_island=?, island_ox=?, island_oy=? WHERE user_id=?",
        (int(in_island), ox, oy, user_id),
    )


async def get_or_create_island(db: Database, ocean_x: int, ocean_y: int) -> int:
    """Return island_id, creating a DB record if it doesn't exist yet."""
    row = await db.fetch_one(
        "SELECT island_id FROM ocean_islands WHERE ocean_x=? AND ocean_y=?",
        (ocean_x, ocean_y),
    )
    if row:
        return row["island_id"]
    cur = await db.execute(
        "INSERT OR IGNORE INTO ocean_islands (ocean_x, ocean_y) VALUES (?, ?)",
        (ocean_x, ocean_y),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = await db.fetch_one(
        "SELECT island_id FROM ocean_islands WHERE ocean_x=? AND ocean_y=?",
        (ocean_x, ocean_y),
    )
    return row["island_id"]


async def store_island_tiles(
    db: Database, island_id: int, tiles: list[tuple[int, int, str]]
) -> None:
    await db.executemany(
        "INSERT OR IGNORE INTO island_tiles (island_id, local_x, local_y, tile_type)"
        " VALUES (?, ?, ?, ?)",
        [(island_id, lx, ly, tt) for lx, ly, tt in tiles],
    )


async def get_island_tiles(db: Database, island_id: int) -> list[tuple]:
    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM island_tiles WHERE island_id=?",
        (island_id,),
    )
    return [(r["local_x"], r["local_y"], r["tile_type"]) for r in rows]


async def update_island_tile(
    db: Database, island_id: int, local_x: int, local_y: int, tile_type: str
) -> None:
    """Change a single island tile type in the DB (e.g. island_forest → island_sapling)."""
    await db.execute(
        "UPDATE island_tiles SET tile_type=? WHERE island_id=? AND local_x=? AND local_y=?",
        (tile_type, island_id, local_x, local_y),
    )


async def is_island_looted(db: Database, ocean_x: int, ocean_y: int) -> bool:
    row = await db.fetch_one(
        "SELECT 1 FROM island_loots WHERE ocean_x=? AND ocean_y=?",
        (ocean_x, ocean_y),
    )
    return row is not None


async def mark_island_looted(db: Database, ocean_x: int, ocean_y: int) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO island_loots (ocean_x, ocean_y) VALUES (?, ?)",
        (ocean_x, ocean_y),
    )


# --- Tile overrides ---

async def set_tile_override(db: Database, world_x: int, world_y: int, tile_type: str) -> None:
    """Insert or replace a tile override (used for player-modified terrain)."""
    await db.execute(
        "INSERT OR REPLACE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
        (world_x, world_y, tile_type),
    )


# --- Chests ---

async def get_or_create_chest(
    db: Database, cave_id: int, local_x: int, local_y: int, chest_type: str
) -> tuple[int, bool]:
    """Return (chest_id, is_new). Creates chest record if first access.

    For non-death chests, also triggers replenishment if 48h have elapsed
    since last_reset (items cleared and re-populated). Returns is_new=True
    when the chest should be populated (either brand new or replenished).
    """
    REPLENISH_HOURS = 48
    # Death chests never replenish (cave_id == -1 by convention, but we check chest_type)
    is_death_chest = (chest_type == "death_chest")

    row = await db.fetch_one(
        "SELECT chest_id, last_reset FROM chests WHERE cave_id=? AND local_x=? AND local_y=?",
        (cave_id, local_x, local_y),
    )
    if row:
        chest_id = row["chest_id"]
        if not is_death_chest:
            last_reset = row["last_reset"]
            needs_replenish = False
            if last_reset is None:
                needs_replenish = True
            else:
                import datetime as _dt
                try:
                    reset_time = _dt.datetime.fromisoformat(last_reset)
                    if _dt.datetime.utcnow() - reset_time >= _dt.timedelta(hours=REPLENISH_HOURS):
                        needs_replenish = True
                except (ValueError, TypeError):
                    needs_replenish = True
            if needs_replenish:
                await db.execute("DELETE FROM chest_items WHERE chest_id=?", (chest_id,))
                await db.execute(
                    "UPDATE chests SET last_reset=datetime('now') WHERE chest_id=?", (chest_id,)
                )
                return chest_id, True  # signal to populate
        return chest_id, False
    cursor = await db.execute(
        "INSERT INTO chests (cave_id, local_x, local_y, chest_type, last_reset) VALUES (?, ?, ?, ?, datetime('now'))",
        (cave_id, local_x, local_y, chest_type),
    )
    return cursor.lastrowid, True


async def get_or_create_ph_chest(
    db: Database, house_id: int, local_x: int, local_y: int, chest_type: str
) -> int:
    """Return chest_id for a player-house chest (never auto-replenishes).

    Uses cave_id = -house_id to distinguish from regular cave chests in the
    shared 'chests' table.
    """
    row = await db.fetch_one(
        "SELECT chest_id FROM chests WHERE cave_id=? AND local_x=? AND local_y=?",
        (-house_id, local_x, local_y),
    )
    if row:
        return row["chest_id"]
    cursor = await db.execute(
        "INSERT INTO chests (cave_id, local_x, local_y, chest_type, last_reset)"
        " VALUES (?, ?, ?, ?, datetime('now'))",
        (-house_id, local_x, local_y, chest_type),
    )
    return cursor.lastrowid


async def get_chest_items(db: Database, chest_id: int) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT item_id, quantity FROM chest_items WHERE chest_id=? ORDER BY rowid",
        (chest_id,),
    )
    return [{"item_id": r["item_id"], "quantity": r["quantity"]} for r in rows]


async def add_to_chest(db: Database, chest_id: int, item_id: str, quantity: int = 1) -> None:
    await db.execute(
        "INSERT INTO chest_items (chest_id, item_id, quantity) VALUES (?, ?, ?) "
        "ON CONFLICT(chest_id, item_id) DO UPDATE SET quantity = quantity + ?",
        (chest_id, item_id, quantity, quantity),
    )


async def remove_from_chest(db: Database, chest_id: int, item_id: str, quantity: int = 1) -> bool:
    row = await db.fetch_one(
        "SELECT quantity FROM chest_items WHERE chest_id=? AND item_id=?",
        (chest_id, item_id),
    )
    if not row or row["quantity"] < quantity:
        return False
    new_qty = row["quantity"] - quantity
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM chest_items WHERE chest_id=? AND item_id=?", (chest_id, item_id)
        )
    else:
        await db.execute(
            "UPDATE chest_items SET quantity=? WHERE chest_id=? AND item_id=?",
            (new_qty, chest_id, item_id),
        )
    return True


# --- Farming ---

async def get_farm_last_watered(db: Database, world_x: int, world_y: int) -> str | None:
    row = await db.fetch_one(
        "SELECT last_watered FROM farm_watered_at WHERE world_x=? AND world_y=?",
        (world_x, world_y),
    )
    return row["last_watered"] if row else None


async def set_farm_watered(db: Database, world_x: int, world_y: int) -> None:
    await db.execute(
        "INSERT INTO farm_watered_at (world_x, world_y, last_watered) VALUES (?, ?, datetime('now'))"
        " ON CONFLICT(world_x, world_y) DO UPDATE SET last_watered=datetime('now')",
        (world_x, world_y),
    )


# --- Treasure maps ---

async def get_treasure_map(db: Database, user_id: int) -> tuple[int, int] | None:
    row = await db.fetch_one(
        "SELECT treasure_x, treasure_y FROM treasure_maps WHERE user_id=? AND found=0",
        (user_id,),
    )
    return (row["treasure_x"], row["treasure_y"]) if row else None


async def set_treasure_map(db: Database, user_id: int, treasure_x: int, treasure_y: int) -> None:
    await db.execute(
        "INSERT INTO treasure_maps (user_id, treasure_x, treasure_y) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET treasure_x=excluded.treasure_x,"
        " treasure_y=excluded.treasure_y, found=0",
        (user_id, treasure_x, treasure_y),
    )


async def mark_treasure_found(db: Database, user_id: int) -> None:
    await db.execute(
        "UPDATE treasure_maps SET found=1 WHERE user_id=?", (user_id,)
    )
