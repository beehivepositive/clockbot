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
_seed_cache: int | None = None  # cached world seed — never changes during a run


async def get_or_create_world(db: Database, guild_id: int) -> int:
    """Return the current world seed. All guilds share one world (guild_id ignored)."""
    global _seed_cache
    if _seed_cache is not None:
        return _seed_cache
    row = await db.fetch_one("SELECT seed FROM world WHERE guild_id = ?", (_GLOBAL_WORLD_KEY,))
    if row:
        _seed_cache = row["seed"]
        return _seed_cache
    # First run ever — pick a random seed and store it
    new_seed = random.randint(1, 2**31 - 1)
    await db.execute(
        "INSERT INTO world (guild_id, seed, initialized) VALUES (?, ?, 0)",
        (_GLOBAL_WORLD_KEY, new_seed),
    )
    _seed_cache = new_seed
    return new_seed


async def is_world_initialized(db: Database, guild_id: int) -> bool:
    row = await db.fetch_one("SELECT initialized FROM world WHERE guild_id = ?", (_GLOBAL_WORLD_KEY,))
    return bool(row and row["initialized"])


async def mark_world_initialized(db: Database, guild_id: int) -> None:
    await db.execute("UPDATE world SET initialized = 1 WHERE guild_id = ?", (_GLOBAL_WORLD_KEY,))


async def reset_world_seed(db: Database) -> int:
    """Generate a fresh random seed, clear initialized flag, return the new seed."""
    global _seed_cache
    _seed_cache = None  # bust the in-memory seed cache
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

        cols = set(row.keys())  # set for O(1) membership tests (was O(N) sqlite3.Row.keys())
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
            cave_lit=await _is_lava_cave(db, row["cave_id"]) if row["cave_id"] else False,
            in_village=bool(row["in_village"]),
            village_id=row["village_id"],
            village_x=row["village_x"] or 0,
            village_y=row["village_y"] or 0,
            village_wx=row["village_wx"] or 0,
            village_wy=row["village_wy"] or 0,
            village_type=row["village_type"] if "village_type" in row.keys() else "village",
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
            avatar_emoji=row["avatar_emoji"] if "avatar_emoji" in cols else None,
            # Shipwreck state
            in_shipwreck=bool(row["in_shipwreck"]) if "in_shipwreck" in cols else False,
            shipwreck_wx=row["shipwreck_wx"] if "shipwreck_wx" in cols else 0,
            shipwreck_wy=row["shipwreck_wy"] if "shipwreck_wy" in cols else 0,
            shipwreck_x=row["shipwreck_x"] if "shipwreck_x" in cols else 0,
            shipwreck_y=row["shipwreck_y"] if "shipwreck_y" in cols else 0,
            breath=row["breath"] if "breath" in cols else 100,
            # Sky biome state
            in_sky=bool(row["in_sky"]) if "in_sky" in cols else False,
            sky_id=row["sky_id"] if "sky_id" in cols else None,
            sky_x=row["sky_x"] if "sky_x" in cols else 0,
            sky_y=row["sky_y"] if "sky_y" in cols else 0,
            sky_portal_wx=row["sky_portal_wx"] if "sky_portal_wx" in cols else 0,
            sky_portal_wy=row["sky_portal_wy"] if "sky_portal_wy" in cols else 0,
            # Temple state
            in_temple=bool(row["in_temple"]) if "in_temple" in cols else False,
            temple_id=row["temple_id"] if "temple_id" in cols else None,
            temple_x=row["temple_x"] if "temple_x" in cols else 0,
            temple_y=row["temple_y"] if "temple_y" in cols else 0,
            temple_wx=row["temple_wx"] if "temple_wx" in cols else 0,
            temple_wy=row["temple_wy"] if "temple_wy" in cols else 0,
            # Forest state
            in_forest=bool(row["in_forest"]) if "in_forest" in cols else False,
            forest_id=row["forest_id"] if "forest_id" in cols else None,
            forest_x=row["forest_x"] if "forest_x" in cols else 0,
            forest_y=row["forest_y"] if "forest_y" in cols else 0,
            forest_wx=row["forest_wx"] if "forest_wx" in cols else 0,
            forest_wy=row["forest_wy"] if "forest_wy" in cols else 0,
            # Maze state
            in_maze=bool(row["in_maze"]) if "in_maze" in cols else False,
            maze_id=row["maze_id"] if "maze_id" in cols else None,
            maze_x=row["maze_x"] if "maze_x" in cols else 0,
            maze_y=row["maze_y"] if "maze_y" in cols else 0,
            # Tree City interior state
            in_tree_city=bool(row["in_tree_city"]) if "in_tree_city" in cols else False,
            tc_forest_id=row["tc_forest_id"] if "tc_forest_id" in cols else None,
            tc_floor=row["tc_floor"] if "tc_floor" in cols else 1,
            tc_x=row["tc_x"] if "tc_x" in cols else 0,
            tc_y=row["tc_y"] if "tc_y" in cols else 0,
            # Grove state
            in_grove=bool(row["in_grove"]) if "in_grove" in cols else False,
            grove_id=row["grove_id"] if "grove_id" in cols else None,
            grove_x=row["grove_x"] if "grove_x" in cols else 0,
            grove_y=row["grove_y"] if "grove_y" in cols else 0,
            grove_forest_id=row["grove_forest_id"] if "grove_forest_id" in cols else None,
            has_warp_crystal=bool(row["has_warp_crystal"]) if "has_warp_crystal" in cols else False,
            has_mountain_crystal=bool(row["has_mountain_crystal"]) if "has_mountain_crystal" in cols else False,
            has_tide_crystal=bool(row["has_tide_crystal"]) if "has_tide_crystal" in cols else False,
            has_sky_crystal=bool(row["has_sky_crystal"]) if "has_sky_crystal" in cols else False,
            watering_can_uses=int(row["watering_can_uses"]) if "watering_can_uses" in cols else 0,
            # Forest Quest zone state
            in_forest_quest=bool(int(row["in_forest_quest"] or 0)) if "in_forest_quest" in cols else False,
            fq_area_id=row["fq_area_id"] if "fq_area_id" in cols else None,
            fq_x=row["fq_x"] if "fq_x" in cols else 0,
            fq_y=row["fq_y"] if "fq_y" in cols else 0,
            fq_quest_stage=row["fq_quest_stage"] if "fq_quest_stage" in cols else "none",
            # Thornwarden boss combat state
            in_fq_boss_combat=bool(row["in_fq_boss_combat"]) if "in_fq_boss_combat" in cols else False,
            fq_boss_turn=row["fq_boss_turn"] if "fq_boss_turn" in cols else 0,
            fq_boss_eye_idx=row["fq_boss_eye_idx"] if "fq_boss_eye_idx" in cols else 0,
            fq_boss_eyes=row["fq_boss_eyes"] if "fq_boss_eyes" in cols else "1111",
            fq_boss_aim_mode=bool(row["fq_boss_aim_mode"]) if "fq_boss_aim_mode" in cols else False,
            fq_boss_aim_x=row["fq_boss_aim_x"] if "fq_boss_aim_x" in cols else 10,
            fq_boss_aim_y=row["fq_boss_aim_y"] if "fq_boss_aim_y" in cols else 66,
            fq_boss_eye_opened_at=float(row["fq_boss_eye_opened_at"] or 0.0) if "fq_boss_eye_opened_at" in cols else 0.0,
            # Bandit camp interior state
            in_bandit_camp=bool(row["in_bandit_camp"]) if "in_bandit_camp" in cols else False,
            bandit_camp_id=row["bandit_camp_id"] if "bandit_camp_id" in cols else None,
            bc_x=row["bc_x"] if "bc_x" in cols else 0,
            bc_y=row["bc_y"] if "bc_y" in cols else 0,
            bandit_bribe_remaining=row["bandit_bribe_remaining"] if "bandit_bribe_remaining" in cols else 0,
            # Hermit Hut interior state
            in_hermit_hut=bool(row["in_hermit_hut"]) if "in_hermit_hut" in cols else False,
            hermit_hut_forest_id=row["hermit_hut_forest_id"] if "hermit_hut_forest_id" in cols else None,
            hermit_hut_floor=row["hermit_hut_floor"] if "hermit_hut_floor" in cols else 1,
            hermit_hut_x=row["hermit_hut_x"] if "hermit_hut_x" in cols else 0,
            hermit_hut_y=row["hermit_hut_y"] if "hermit_hut_y" in cols else 0,
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
) -> list[tuple[int, int, str, int]]:
    """Return [(world_x, world_y, display_name, user_id)] for overworld players active within 24 h."""
    rows = await db.fetch_all(
        "SELECT world_x, world_y, display_name, user_id FROM players"
        " WHERE user_id != ? AND in_cave = 0 AND in_village = 0 AND in_house = 0"
        " AND COALESCE(in_ocean, 0) = 0"
        " AND last_active >= datetime('now', '-24 hours')",
        (exclude_user_id,),
    )
    return [(r["world_x"], r["world_y"], r["display_name"], r["user_id"]) for r in rows]


# --- Caves ---

_lava_cave_cache: dict[int, bool] = {}  # cave_id → True if lava cave; permanent (type never changes)


async def _is_lava_cave(db: Database, cave_id: int) -> bool:
    """Return True if this cave has cave_type='lava' (a volcano island lava cave)."""
    if cave_id in _lava_cave_cache:
        return _lava_cave_cache[cave_id]
    row = await db.fetch_one(
        "SELECT cave_type FROM caves WHERE cave_id = ?", (cave_id,)
    )
    result = bool(row and row["cave_type"] == "lava")
    _lava_cave_cache[cave_id] = result
    return result


async def register_island_cave(
    db: Database, island_id: int, local_x: int, local_y: int, cave_id: int
) -> None:
    """Link a vol_cave tile on a volcano island to a lava cave."""
    await db.execute(
        "INSERT OR IGNORE INTO island_cave_entrances (island_id, local_x, local_y, cave_id)"
        " VALUES (?, ?, ?, ?)",
        (island_id, local_x, local_y, cave_id),
    )


async def update_player_cave_state(
    db: Database, user_id: int, in_cave: bool, cave_id: int | None, cave_x: int, cave_y: int
) -> None:
    await db.execute(
        "UPDATE players SET in_cave = ?, cave_id = ?, cave_x = ?, cave_y = ?, "
        "last_active = datetime('now') WHERE user_id = ?",
        (int(in_cave), cave_id, cave_x, cave_y, user_id),
    )


async def update_player_shipwreck_state(
    db: Database, user_id: int,
    in_shipwreck: bool, shipwreck_wx: int, shipwreck_wy: int,
    sw_x: int, sw_y: int,
    breath: int,
) -> None:
    await db.execute(
        "UPDATE players SET in_shipwreck=?, shipwreck_wx=?, shipwreck_wy=?, "
        "shipwreck_x=?, shipwreck_y=?, breath=?, last_active=datetime('now') "
        "WHERE user_id=?",
        (int(in_shipwreck), shipwreck_wx, shipwreck_wy, sw_x, sw_y, breath, user_id),
    )


async def update_player_sky_state(
    db: Database, user_id: int,
    in_sky: bool, sky_id: int | None, sky_x: int, sky_y: int,
    sky_portal_wx: int = 0, sky_portal_wy: int = 0,
) -> None:
    await db.execute(
        "UPDATE players SET in_sky=?, sky_id=?, sky_x=?, sky_y=?, "
        "sky_portal_wx=?, sky_portal_wy=?, last_active=datetime('now') "
        "WHERE user_id=?",
        (int(in_sky), sky_id, sky_x, sky_y, sky_portal_wx, sky_portal_wy, user_id),
    )


async def update_player_temple_state(
    db: Database,
    user_id: int,
    in_temple: bool,
    temple_id: int | None,
    temple_x: int,
    temple_y: int,
    temple_wx: int = 0,
    temple_wy: int = 0,
) -> None:
    await db.execute(
        "UPDATE players SET in_temple=?, temple_id=?, temple_x=?, temple_y=?, temple_wx=?, temple_wy=?"
        " WHERE user_id=?",
        (int(in_temple), temple_id, temple_x, temple_y, temple_wx, temple_wy, user_id),
    )


async def is_sky_chest_looted(
    db: Database, sky_id: int, local_x: int, local_y: int
) -> bool:
    row = await db.fetch_one(
        "SELECT looted FROM sky_chest_state WHERE sky_id=? AND local_x=? AND local_y=?",
        (sky_id, local_x, local_y),
    )
    return bool(row and row["looted"])


async def mark_sky_chest_looted(
    db: Database, sky_id: int, local_x: int, local_y: int
) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO sky_chest_state (sky_id, local_x, local_y, looted) "
        "VALUES (?, ?, ?, 1)",
        (sky_id, local_x, local_y),
    )


async def is_shipwreck_chest_looted(
    db: Database, user_id: int, sw_wx: int, sw_wy: int, chest_x: int, chest_y: int
) -> bool:
    row = await db.fetch_one(
        "SELECT 1 FROM shipwreck_looted_chests "
        "WHERE user_id=? AND sw_wx=? AND sw_wy=? AND chest_x=? AND chest_y=?",
        (user_id, sw_wx, sw_wy, chest_x, chest_y),
    )
    return row is not None


async def mark_shipwreck_chest_looted(
    db: Database, user_id: int, sw_wx: int, sw_wy: int, chest_x: int, chest_y: int
) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO shipwreck_looted_chests (user_id, sw_wx, sw_wy, chest_x, chest_y) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, sw_wx, sw_wy, chest_x, chest_y),
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
    village_type: str = "village",
) -> None:
    await db.execute(
        "UPDATE players SET in_village = ?, village_id = ?, village_x = ?, village_y = ?, "
        "village_wx = ?, village_wy = ?, village_type = ?, last_active = datetime('now') WHERE user_id = ?",
        (int(in_village), village_id, village_x, village_y, village_wx, village_wy, village_type, user_id),
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

    Canoes are special: they occupy two adjacent display slots and must never
    stack.  Any call with item_id == "canoe" is automatically forwarded to
    add_canoe_pair() so every code path is safe without individual guards.
    """
    if item_id == "canoe":
        for _ in range(quantity):
            await add_canoe_pair(db, user_id)
        return 0  # canoes always fit (no stack limit applies)

    remaining = quantity
    # Fill existing stacks that have room — batch all UPDATEs into one executemany
    rows = await db.fetch_all(
        "SELECT id, quantity FROM inventory WHERE user_id = ? AND item_id = ? ORDER BY slot_index, id",
        (user_id, item_id),
    )
    fill_updates: list[tuple] = []
    for row in rows:
        if remaining <= 0:
            break
        space = MAX_STACK_SIZE - row["quantity"]
        if space > 0:
            add = min(space, remaining)
            fill_updates.append((add, row["id"]))
            remaining -= add
    if fill_updates:
        await db.executemany(
            "UPDATE inventory SET quantity = quantity + ? WHERE id = ?", fill_updates
        )

    # Create new slots for overflow — compute next_idx once, batch INSERTs
    if remaining > 0:
        # Fetch slot count once (not per-iteration)
        used = await get_inventory_slot_count(db, user_id) if max_slots is not None else 0
        next_idx = await _next_slot_index(db, user_id)
        inserts: list[tuple] = []
        while remaining > 0:
            if max_slots is not None and (used + len(inserts)) >= max_slots:
                break
            add = min(MAX_STACK_SIZE, remaining)
            inserts.append((user_id, item_id, add, next_idx))
            next_idx += 1
            remaining -= add
        if inserts:
            await db.executemany(
                "INSERT INTO inventory (user_id, item_id, quantity, slot_index) VALUES (?, ?, ?, ?)",
                inserts,
            )
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
    """Renumber slot_index values so they're contiguous starting from 0.

    Canoe rows occupy TWO visual slots (the DB row is slot N, the virtual
    canoe_right lives at slot N+1).  After compacting we must leave that
    gap so the right half is never overwritten by the next item.
    Uses a single executemany call instead of N individual UPDATEs.
    """
    rows = await db.fetch_all(
        "SELECT id, item_id FROM inventory WHERE user_id = ? ORDER BY slot_index, id",
        (user_id,),
    )
    updates: list[tuple] = []
    new_idx = 0
    for row in rows:
        updates.append((new_idx, row["id"]))
        new_idx += 2 if row["item_id"] == "canoe" else 1
    if updates:
        await db.executemany("UPDATE inventory SET slot_index = ? WHERE id = ?", updates)


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

async def _find_free_tile_override_pos(db: Database, wx: int, wy: int) -> tuple[int, int]:
    """Spiral outward from (wx, wy) to find the nearest position with no tile_override.

    Used by create_drop_box so that a drop box is never silently swallowed by an
    existing cave/village/structure tile at the same coordinate.
    Fetches the entire search area in one query and spirals in Python.
    """
    from dwarf_explorer.config import WORLD_SIZE
    rows = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides"
        " WHERE world_x BETWEEN ? AND ? AND world_y BETWEEN ? AND ?",
        (wx - 9, wx + 9, wy - 9, wy + 9),
    )
    occupied = {(r["world_x"], r["world_y"]) for r in rows}
    for radius in range(1, 10):
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue  # only the ring at this radius
                nx, ny = wx + dx, wy + dy
                if (0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE
                        and (nx, ny) not in occupied):
                    return nx, ny
    return wx, wy  # fallback: original position (rare edge case)


async def create_drop_box(
    db: Database, world_x: int, world_y: int, items: list[tuple[str, int]],
    tile_type: str = "drop_box",
) -> None:
    """Create a drop box at (world_x, world_y) with the given items.

    Items dropped on an existing box are merged into it.
    A tile_override of tile_type is inserted (or left existing) so the renderer shows the box emoji.
    Use tile_type='canoe_box' when dropping a canoe so it renders with :canoe_whole:.

    If the target tile is already occupied by a different structure (cave, village, etc.),
    the box is placed on the nearest free tile so it is always visible and reachable.
    """
    _box_types = ("drop_box", "canoe_box")
    # Check whether the target tile already has a non-box override
    existing_override = await db.fetch_one(
        "SELECT tile_type FROM tile_overrides WHERE world_x=? AND world_y=?",
        (world_x, world_y),
    )
    if existing_override and existing_override["tile_type"] not in _box_types:
        # Occupied by a cave/village/structure — find the nearest free tile instead
        world_x, world_y = await _find_free_tile_override_pos(db, world_x, world_y)

    # Upsert the tile_override (use INSERT OR IGNORE so existing box stays)
    await db.execute(
        "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, ?)",
        (world_x, world_y, tile_type),
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


async def add_canoe_pair(db: Database, user_id: int, inv_cols: int = 7) -> None:
    """Insert a single 'canoe' inventory row. The canoe is one item that
    visually occupies two adjacent slots (rendered as canoe_left + canoe_right).
    If the chosen slot would put the canoe's left half at the rightmost column
    (splitting the pair across rows), bump to the start of the next row.
    Each canoe always lives in its own row — canoes do not stack.
    """
    row_obj = await db.fetch_one(
        "SELECT COALESCE(MAX(slot_index)+1, 0) AS nxt FROM inventory WHERE user_id=?",
        (user_id,),
    )
    nxt = row_obj["nxt"] if row_obj else 0
    if nxt % inv_cols == inv_cols - 1:
        nxt = (nxt // inv_cols + 1) * inv_cols
    await db.execute(
        "INSERT INTO inventory(user_id, item_id, quantity, slot_index) VALUES(?,?,1,?)",
        (user_id, "canoe", nxt),
    )


async def pickup_drop_box(
    db: Database, world_x: int, world_y: int, user_id: int
) -> list[tuple[str, int]]:
    """Pick up all items in a drop box at (world_x, world_y) into user's inventory.

    Returns list of (item_id, qty) actually picked up.
    Gold coins go directly to players.gold rather than inventory.
    Canoes are stored as a single 'canoe' item; each one is added via
    add_canoe_pair so it lands as an adjacent pair of slots on the same row.
    """
    items = await db.fetch_all(
        "SELECT id, item_id, quantity FROM ground_items WHERE world_x=? AND world_y=? AND is_drop=1",
        (world_x, world_y),
    )
    picked = []
    for row in items:
        item_id = row["item_id"]
        qty = row["quantity"]
        if item_id == "gold_coin":
            await db.execute(
                "UPDATE players SET gold=gold+? WHERE user_id=?",
                (qty, user_id),
            )
        elif item_id == "canoe":
            for _ in range(qty):
                await add_canoe_pair(db, user_id)
        else:
            await add_to_inventory(db, user_id, item_id, qty)
        await db.execute("DELETE FROM ground_items WHERE id=?", (row["id"],))
        picked.append((item_id, qty))
    # Remove tile_override if no drop items remain
    remaining = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM ground_items WHERE world_x=? AND world_y=? AND is_drop=1",
        (world_x, world_y),
    )
    if remaining and remaining["cnt"] == 0:
        await db.execute(
            "DELETE FROM tile_overrides WHERE world_x=? AND world_y=? AND tile_type IN ('drop_box','canoe_box')",
            (world_x, world_y),
        )
    return picked


async def cleanup_expired_drop_boxes(db: Database) -> None:
    """Delete drop box items older than 1 hour and remove their tile_overrides."""
    # Delete all expired ground items in one statement
    await db.execute(
        "DELETE FROM ground_items WHERE is_drop=1 AND spawned_at < datetime('now', '-1 hour')"
    )
    # Remove any drop_box/canoe_box tile_overrides that no longer have items under them
    await db.execute(
        "DELETE FROM tile_overrides WHERE tile_type IN ('drop_box','canoe_box')"
        " AND NOT EXISTS ("
        "   SELECT 1 FROM ground_items"
        "   WHERE is_drop=1 AND ground_items.world_x=tile_overrides.world_x"
        "     AND ground_items.world_y=tile_overrides.world_y"
        ")"
    )


async def create_cave_drop_box(
    db: Database, cave_id: int, cave_x: int, cave_y: int, items: list[tuple[str, int]]
) -> None:
    """Create a drop box inside a cave at (cave_id, cave_x, cave_y) with given items.

    Items dropped on an existing box are merged into it.
    Unlike overworld drops, cave drops store cave_id/cave_x/cave_y; the
    load_cave_viewport overlay renders them as "drop_box" terrain.
    """
    for item_id, qty in items:
        existing = await db.fetch_one(
            "SELECT id, quantity FROM ground_items "
            "WHERE cave_id=? AND cave_x=? AND cave_y=? AND item_id=? AND is_drop=1",
            (cave_id, cave_x, cave_y, item_id),
        )
        if existing:
            await db.execute(
                "UPDATE ground_items SET quantity=quantity+?, spawned_at=datetime('now') WHERE id=?",
                (qty, existing["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO ground_items (world_x, world_y, cave_id, cave_x, cave_y, item_id, quantity, is_drop)"
                " VALUES (0, 0, ?, ?, ?, ?, ?, 1)",
                (cave_id, cave_x, cave_y, item_id, qty),
            )


async def pickup_cave_drop(
    db: Database, cave_id: int, cave_x: int, cave_y: int, user_id: int
) -> list[tuple[str, int]]:
    """Pick up all items in a cave drop box at (cave_id, cave_x, cave_y).

    Returns list of (item_id, qty) actually picked up.
    """
    items = await db.fetch_all(
        "SELECT id, item_id, quantity FROM ground_items "
        "WHERE cave_id=? AND cave_x=? AND cave_y=? AND is_drop=1",
        (cave_id, cave_x, cave_y),
    )
    picked = []
    for row in items:
        await add_to_inventory(db, user_id, row["item_id"], row["quantity"])
        await db.execute("DELETE FROM ground_items WHERE id=?", (row["id"],))
        picked.append((row["item_id"], row["quantity"]))
    return picked


async def get_cave_drop_positions(db: Database, cave_id: int) -> set[tuple[int, int]]:
    """Return set of (cave_x, cave_y) positions with active drops inside cave_id."""
    rows = await db.fetch_all(
        "SELECT DISTINCT cave_x, cave_y FROM ground_items "
        "WHERE cave_id=? AND is_drop=1",
        (cave_id,),
    )
    return {(r["cave_x"], r["cave_y"]) for r in rows}


async def create_village_drop_box(
    db: Database, village_id: int, village_x: int, village_y: int,
    items: list[tuple[str, int]]
) -> None:
    """Create/extend a drop box inside a village at (village_id, village_x, village_y)."""
    for item_id, qty in items:
        existing = await db.fetch_one(
            "SELECT id, quantity FROM ground_items "
            "WHERE village_id=? AND village_x=? AND village_y=? AND item_id=? AND is_drop=1",
            (village_id, village_x, village_y, item_id),
        )
        if existing:
            await db.execute(
                "UPDATE ground_items SET quantity=quantity+?, spawned_at=datetime('now') WHERE id=?",
                (qty, existing["id"]),
            )
        else:
            await db.execute(
                "INSERT INTO ground_items (world_x, world_y, village_id, village_x, village_y, item_id, quantity, is_drop)"
                " VALUES (0, 0, ?, ?, ?, ?, ?, 1)",
                (village_id, village_x, village_y, item_id, qty),
            )


async def pickup_village_drop(
    db: Database, village_id: int, village_x: int, village_y: int, user_id: int
) -> list[tuple[str, int]]:
    """Pick up all items in a village drop box. Returns list of (item_id, qty) picked up."""
    rows = await db.fetch_all(
        "SELECT id, item_id, quantity FROM ground_items "
        "WHERE village_id=? AND village_x=? AND village_y=? AND is_drop=1",
        (village_id, village_x, village_y),
    )
    results: list[tuple[str, int]] = []
    for row in rows:
        await add_to_inventory(db, user_id, row["item_id"], row["quantity"])
        await db.execute("DELETE FROM ground_items WHERE id=?", (row["id"],))
        results.append((row["item_id"], row["quantity"]))
    return results


async def get_village_drop_positions(db: Database, village_id: int) -> set[tuple[int, int]]:
    """Return set of (village_x, village_y) positions with active drops in this village."""
    rows = await db.fetch_all(
        "SELECT DISTINCT village_x, village_y FROM ground_items "
        "WHERE village_id=? AND is_drop=1",
        (village_id,),
    )
    return {(r["village_x"], r["village_y"]) for r in rows}


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
    # Canoes are stored as a single 'canoe' item but displayed as a pair of slots
    # (canoe_left + canoe_right) in the vault grid. Emit one 'canoe' entry per
    # canoe; _build_slot_map expands each into the two-cell visual.
    BANK_COLS = 7  # vault grid width — must match render_bank
    result: list[dict] = []
    canoe_count = 0
    slot_idx = 0
    for r in rows:
        if r["item_id"] == "canoe":
            canoe_count += r["quantity"]
            continue
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
    # Append canoes at the end, each occupying 2 slots. If the next slot would
    # split a canoe across rows (left at last col), skip the last col so the
    # canoe lives on the next row's first two cells.
    for _ in range(canoe_count):
        if slot_idx % BANK_COLS == BANK_COLS - 1:
            slot_idx += 1  # leave the rightmost cell empty
        result.append({"item_id": "canoe", "quantity": 1, "slot_index": slot_idx})
        slot_idx += 2
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
    # Gold goes back to players.gold, not inventory.
    # Canoes are stored as a single 'canoe' item but must land in inventory as
    # an adjacent slot pair, so route through add_canoe_pair.
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
    elif item_id == "canoe":
        for _ in range(quantity):
            await add_canoe_pair(db, user_id)
    else:
        await add_to_inventory(db, user_id, item_id, quantity)
    return True


# --- Combat state ---

async def save_combat_state(db: Database, user_id: int, player) -> None:
    await db.execute(
        "UPDATE players SET in_combat=?, combat_enemy_type=?, combat_enemy_hp=?,"
        " combat_enemy_x=?, combat_enemy_y=?, combat_player_x=?, combat_player_y=?,"
        " combat_moves_left=?, hp=?, ship_hp=? WHERE user_id=?",
        (int(player.in_combat), player.combat_enemy_type, player.combat_enemy_hp,
         player.combat_enemy_x, player.combat_enemy_y,
         player.combat_player_x, player.combat_player_y,
         player.combat_moves_left, player.hp, player.ship_hp, user_id),
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


async def get_or_create_island(
    db: Database, ocean_x: int, ocean_y: int,
    island_type: str = "regular",
) -> int:
    """Return island_id, creating a DB record if it doesn't exist yet."""
    row = await db.fetch_one(
        "SELECT island_id FROM ocean_islands WHERE ocean_x=? AND ocean_y=?",
        (ocean_x, ocean_y),
    )
    if row:
        return row["island_id"]
    cur = await db.execute(
        "INSERT OR IGNORE INTO ocean_islands (ocean_x, ocean_y, island_type) VALUES (?, ?, ?)",
        (ocean_x, ocean_y, island_type),
    )
    if cur.lastrowid:
        return cur.lastrowid
    row = await db.fetch_one(
        "SELECT island_id FROM ocean_islands WHERE ocean_x=? AND ocean_y=?",
        (ocean_x, ocean_y),
    )
    return row["island_id"]


async def get_island_type(db: Database, ocean_x: int, ocean_y: int) -> str:
    """Return the island_type ('regular' or 'volcano') for an ocean position."""
    row = await db.fetch_one(
        "SELECT island_type FROM ocean_islands WHERE ocean_x=? AND ocean_y=?",
        (ocean_x, ocean_y),
    )
    return row["island_type"] if row else "regular"


async def get_or_create_island_cave(
    db: Database, island_id: int, local_x: int, local_y: int,
) -> int:
    """Return cave_id for a vol_cave tile on a volcano island, creating it if needed."""
    row = await db.fetch_one(
        "SELECT cave_id FROM island_cave_entrances WHERE island_id=? AND local_x=? AND local_y=?",
        (island_id, local_x, local_y),
    )
    if row:
        return row["cave_id"]
    return 0   # signal to caller to generate the cave


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


async def set_village_tile(
    db: Database, village_id: int, local_x: int, local_y: int, tile_type: str
) -> None:
    """Update a village tile's type (used for farmland, crops, etc.)."""
    await db.execute(
        "UPDATE village_tiles SET tile_type=? WHERE village_id=? AND local_x=? AND local_y=?",
        (tile_type, village_id, local_x, local_y),
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


async def get_or_create_maze_chest(db: "Database", maze_id: int) -> tuple[int, bool]:
    """Return (chest_id, is_new) for the treasure chest of a given maze.

    Uses a virtual cave_id = -(maze_id * 10 + 9) so negative coords never
    collide with player-house chests (which use -house_id directly).
    The chest never auto-replenishes — once emptied, it stays empty.
    """
    virtual_cave_id = -(maze_id * 10 + 9)
    row = await db.fetch_one(
        "SELECT chest_id FROM chests WHERE cave_id=? AND local_x=0 AND local_y=0",
        (virtual_cave_id,),
    )
    if row:
        return row["chest_id"], False
    cursor = await db.execute(
        "INSERT INTO chests (cave_id, local_x, local_y, chest_type, last_reset)"
        " VALUES (?, 0, 0, 'maze_chest', datetime('now'))",
        (virtual_cave_id,),
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


# --- Quest helpers ---

async def give_quest_reward(
    db: Database, user_id: int, gold: int, xp: int, item_id: str | None = None
) -> str:
    """Grant gold, xp and optional item for a completed quest.  Returns a summary string."""
    from dwarf_explorer.config import COIN_PURSE_CAPACITY
    from dwarf_explorer.game.player import Player

    # Grant gold (respecting cap)
    if gold > 0:
        player_row = await db.fetch_one("SELECT gold FROM players WHERE user_id=?", (user_id,))
        if player_row:
            eq_row = await db.fetch_one(
                "SELECT item_id FROM equipment WHERE user_id=? AND slot='coin_purse'", (user_id,)
            )
            purse = eq_row["item_id"] if eq_row else None
            cap = COIN_PURSE_CAPACITY.get(purse, COIN_PURSE_CAPACITY[None])
            current = player_row["gold"]
            new_gold = min(current + gold, cap)
            await db.execute("UPDATE players SET gold=? WHERE user_id=?", (new_gold, user_id))

    # Grant XP (and level-up)
    if xp > 0:
        await db.execute(
            "UPDATE players SET xp = xp + ? WHERE user_id=?", (xp, user_id)
        )
        # Simple level-up check (100 * level^1.5 xp per level)
        import math
        row = await db.fetch_one("SELECT xp, level FROM players WHERE user_id=?", (user_id,))
        if row:
            new_xp   = row["xp"]
            lvl      = row["level"]
            required = int(100 * (lvl ** 1.5))
            while new_xp >= required:
                lvl += 1
                required = int(100 * (lvl ** 1.5))
            if lvl > row["level"]:
                await db.execute(
                    "UPDATE players SET level=?, max_hp=max_hp+10, hp=hp+10 WHERE user_id=?",
                    (lvl, user_id),
                )

    # Grant item
    if item_id:
        await add_to_inventory(db, user_id, item_id, 1)

    parts = []
    if gold:
        parts.append(f"+{gold}🪙")
    if xp:
        parts.append(f"+{xp}xp")
    if item_id:
        from dwarf_explorer.config import ITEM_EMOJI
        emoji = ITEM_EMOJI.get(item_id, "📦")
        parts.append(f"+1 {emoji}")
    return " ".join(parts) or "nothing"


async def has_claimed_puzzle_today(db: Database, user_id: int) -> bool:
    """Return True if the player already claimed today's puzzle reward."""
    from datetime import date
    today = date.today().isoformat()
    row = await db.fetch_one(
        "SELECT 1 FROM puzzle_rewards WHERE user_id=? AND reward_date=?",
        (user_id, today),
    )
    return row is not None


async def claim_puzzle_reward(db: Database, user_id: int) -> bool:
    """Record today's puzzle reward claim. Returns False if already claimed."""
    import sqlite3
    from datetime import date
    today = date.today().isoformat()
    try:
        await db.execute(
            "INSERT INTO puzzle_rewards(user_id, reward_date) VALUES(?, ?)",
            (user_id, today),
        )
        return True
    except sqlite3.IntegrityError:
        return False


async def get_player_quest_markers(db: Database, user_id: int) -> list[tuple[int, int, str]]:
    """Return [(world_x, world_y, label)] for all active quests with overworld markers."""
    rows = await db.fetch_all(
        "SELECT pq.bounty_wx, pq.bounty_wy, q.target_id, q.location_x, q.location_y, "
        "q.quest_subtype, q.location_type "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' "
        "AND (pq.bounty_wx IS NOT NULL OR q.location_x IS NOT NULL)",
        (user_id,),
    )
    markers = []
    for r in rows:
        # Kill bounties: use personal bounty_wx/wy, fall back to quest location
        if r["quest_subtype"] == "kill" and r["location_type"] == "overworld":
            wx = r["bounty_wx"] if r["bounty_wx"] is not None else r["location_x"]
            wy = r["bounty_wy"] if r["bounty_wy"] is not None else r["location_y"]
            if wx is not None and wy is not None:
                markers.append((wx, wy, r["target_id"]))
        elif r["quest_subtype"] in ("investigation", "delivery"):
            if r["location_x"] is not None and r["location_y"] is not None:
                markers.append((r["location_x"], r["location_y"], r["quest_subtype"]))
        elif r["quest_subtype"] == "exploration":
            # Exploration quests use quests.location_x/y (same as investigation).
            # bounty_wx/wy is only used as a fallback if location_x/y isn't set yet.
            wx = r["location_x"] if r["location_x"] is not None else r["bounty_wx"]
            wy = r["location_y"] if r["location_y"] is not None else r["bounty_wy"]
            if wx is not None and wy is not None:
                markers.append((wx, wy, "exploration"))
    return markers


async def get_player_ocean_quest_markers(db, user_id: int) -> list[tuple[int, int, str]]:
    """Return [(ocean_x, ocean_y, target_id)] for active quests located in the ocean."""
    rows = await db.fetch_all(
        "SELECT pq.bounty_wx, pq.bounty_wy, q.target_id, q.location_x, q.location_y "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' "
        "AND q.location_type = 'ocean'",
        (user_id,),
    )
    markers = []
    for r in rows:
        ox = r["bounty_wx"] if r["bounty_wx"] is not None else r["location_x"]
        oy = r["bounty_wy"] if r["bounty_wy"] is not None else r["location_y"]
        if ox is not None and oy is not None:
            markers.append((ox, oy, r["target_id"]))
    return markers


# ── Ship Crew ──────────────────────────────────────────────────────────────────

async def get_ship_crew(db: Database, user_id: int) -> list[dict]:
    """Return list of crew members [{slot, name, task}] sorted by slot."""
    rows = await db.fetch_all(
        "SELECT slot, name, task FROM ship_crew WHERE user_id=? ORDER BY slot",
        (user_id,),
    )
    return [{"slot": r["slot"], "name": r["name"], "task": r["task"]} for r in rows]


async def hire_crew_member(db: Database, user_id: int, name: str) -> int | None:
    """Hire a new crew member into the next available slot (1-3). Returns slot or None if full."""
    from dwarf_explorer.config import MAX_CREW_SIZE
    existing = await db.fetch_all(
        "SELECT slot FROM ship_crew WHERE user_id=? ORDER BY slot",
        (user_id,),
    )
    used_slots = {r["slot"] for r in existing}
    for slot in range(1, MAX_CREW_SIZE + 1):
        if slot not in used_slots:
            await db.execute(
                "INSERT INTO ship_crew (user_id, slot, name, task) VALUES (?,?,?,'idle')",
                (user_id, slot, name),
            )
            return slot
    return None  # full


async def fire_crew_member(db: Database, user_id: int, slot: int) -> bool:
    """Remove crew member at given slot. Returns True if removed."""
    row = await db.fetch_one(
        "SELECT id FROM ship_crew WHERE user_id=? AND slot=?", (user_id, slot)
    )
    if not row:
        return False
    await db.execute("DELETE FROM ship_crew WHERE user_id=? AND slot=?", (user_id, slot))
    return True


async def set_crew_task(db: Database, user_id: int, slot: int, task: str) -> None:
    """Assign a task to a crew member slot."""
    await db.execute(
        "UPDATE ship_crew SET task=? WHERE user_id=? AND slot=?",
        (task, user_id, slot),
    )


async def get_crew_task(db: Database, user_id: int, task: str) -> bool:
    """Return True if any crew member is assigned the given task."""
    row = await db.fetch_one(
        "SELECT 1 FROM ship_crew WHERE user_id=? AND task=?", (user_id, task)
    )
    return row is not None


# --- Player village overrides ---

async def get_player_village_overrides(
    db: Database, user_id: int, village_id: int
) -> dict[tuple[int, int], str]:
    """Return {(tile_x, tile_y): tile_type} for all overrides this player has in this village."""
    rows = await db.fetch_all(
        "SELECT tile_x, tile_y, tile_type FROM player_village_overrides "
        "WHERE user_id = ? AND village_id = ?",
        (user_id, village_id),
    )
    return {(r["tile_x"], r["tile_y"]): r["tile_type"] for r in rows}


async def set_player_village_override(
    db: Database, user_id: int, village_id: int, x: int, y: int, tile_type: str
) -> None:
    """Insert or replace a single player-specific tile override for a village."""
    await db.execute(
        "INSERT OR REPLACE INTO player_village_overrides "
        "(user_id, village_id, tile_x, tile_y, tile_type) VALUES (?, ?, ?, ?, ?)",
        (user_id, village_id, x, y, tile_type),
    )


# --- Warp Crystal / Waypoints ---

async def unlock_waypoint(db: Database, user_id: int, waypoint_id: str) -> None:
    """Unlock a warp waypoint for a player (idempotent)."""
    await db.execute(
        "INSERT OR IGNORE INTO player_waypoints (user_id, waypoint_id) VALUES (?, ?)",
        (user_id, waypoint_id),
    )


async def get_player_waypoints(db: Database, user_id: int) -> set[str]:
    """Return set of waypoint_ids unlocked by this player."""
    rows = await db.fetch_all(
        "SELECT waypoint_id FROM player_waypoints WHERE user_id = ?", (user_id,)
    )
    return {r["waypoint_id"] for r in rows}


async def grant_warp_crystal(db: Database, user_id: int) -> None:
    """Give the player the Forest Crystal (Chapter 1) and unlock the three starter waypoints."""
    await db.execute(
        "UPDATE players SET has_warp_crystal = 1 WHERE user_id = ?", (user_id,)
    )
    for wp_id in ("spawn", "forest", "grove"):
        await unlock_waypoint(db, user_id, wp_id)


async def grant_chapter_crystal(db: Database, user_id: int, crystal: str) -> None:
    """Grant a chapter crystal by name: 'forest'|'mountain'|'tide'|'sky'.

    'forest' is an alias for the original warp crystal (has_warp_crystal).
    The others set the corresponding has_*_crystal column on players.
    """
    if crystal == "forest":
        await grant_warp_crystal(db, user_id)
        return
    col = f"has_{crystal}_crystal"
    await db.execute(f"UPDATE players SET {col} = 1 WHERE user_id = ?", (user_id,))


def get_player_crystal_set(player) -> set[str]:
    """Return the set of crystal names currently held by this player."""
    crystals: set[str] = set()
    if getattr(player, "has_warp_crystal", False):
        crystals.add("forest")
    if getattr(player, "has_mountain_crystal", False):
        crystals.add("mountain")
    if getattr(player, "has_tide_crystal", False):
        crystals.add("tide")
    if getattr(player, "has_sky_crystal", False):
        crystals.add("sky")
    return crystals


# ── Avatar cache ──────────────────────────────────────────────────────────────

_AVATAR_TTL = 86_400   # 24 hours in seconds


async def get_avatar_cache(db: Database, user_id: int) -> bytes | None:
    """Return cached avatar PNG bytes if < 24 h old, else None."""
    import time as _time
    row = await db.fetch_one(
        "SELECT avatar_data, cached_at FROM avatar_cache WHERE user_id = ?",
        (user_id,),
    )
    if row is None:
        return None
    if _time.time() - int(row["cached_at"]) > _AVATAR_TTL:
        return None
    data = row["avatar_data"]
    return bytes(data) if data else None


async def store_avatar_cache(db: Database, user_id: int, avatar_data: bytes) -> None:
    """Upsert avatar bytes with the current timestamp."""
    import time as _time
    await db.execute(
        "INSERT INTO avatar_cache(user_id, avatar_data, cached_at) VALUES(?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "avatar_data = excluded.avatar_data, cached_at = excluded.cached_at",
        (user_id, avatar_data, int(_time.time())),
    )
