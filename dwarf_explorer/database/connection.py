from __future__ import annotations

import asyncio
import os
import sqlite3
from typing import Any


class Database:
    """Async SQLite wrapper using asyncio.to_thread."""

    def __init__(self, db_path: str):
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        def _run():
            conn = self._get_conn()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor
        return await asyncio.to_thread(_run)

    async def executemany(self, sql: str, params_list: list[tuple]) -> None:
        def _run():
            conn = self._get_conn()
            conn.executemany(sql, params_list)
            conn.commit()
        await asyncio.to_thread(_run)

    async def execute_script(self, sql: str) -> None:
        def _run():
            conn = self._get_conn()
            conn.executescript(sql)
        await asyncio.to_thread(_run)

    async def fetch_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        def _run():
            conn = self._get_conn()
            return conn.execute(sql, params).fetchone()
        return await asyncio.to_thread(_run)

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        def _run():
            conn = self._get_conn()
            return conn.execute(sql, params).fetchall()
        return await asyncio.to_thread(_run)

    async def init_schema(self) -> None:
        import logging as _logging
        _log = _logging.getLogger(__name__)
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r") as f:
            schema_sql = f.read()

        # Run schema creation + all migrations in ONE thread so the same
        # sqlite3 connection is used throughout (avoids cross-thread state issues).
        def _migrate():
            conn = self._get_conn()
            # Base schema (CREATE TABLE IF NOT EXISTS … for all core tables)
            conn.executescript(schema_sql)
            migrations = [
                "ALTER TABLE world ADD COLUMN initialized INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN in_cave INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN cave_id INTEGER",
                "ALTER TABLE players ADD COLUMN cave_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN cave_y INTEGER NOT NULL DEFAULT 0",
                # Village / house state
                "ALTER TABLE players ADD COLUMN in_village INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN village_id INTEGER",
                "ALTER TABLE players ADD COLUMN village_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN village_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN village_wx INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN village_wy INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN in_house INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN house_id INTEGER",
                "ALTER TABLE players ADD COLUMN house_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN house_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN house_vx INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN house_vy INTEGER NOT NULL DEFAULT 0",
                # Building type + sprint
                "ALTER TABLE players ADD COLUMN house_type TEXT NOT NULL DEFAULT 'house'",
                "ALTER TABLE players ADD COLUMN sprinting INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN weapon TEXT",
                "ALTER TABLE players ADD COLUMN boots TEXT",
                # buildings table
                "ALTER TABLE houses ADD COLUMN building_type TEXT NOT NULL DEFAULT 'house'",
                # Equipment table (create if missing)
                """CREATE TABLE IF NOT EXISTS equipment (
                    user_id INTEGER NOT NULL,
                    slot TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, slot)
                )""",
                # Bank items table (create if missing)
                """CREATE TABLE IF NOT EXISTS bank_items (
                    user_id INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (user_id, item_id)
                )""",
                # Combat state columns
                "ALTER TABLE players ADD COLUMN in_combat INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN combat_enemy_type TEXT",
                "ALTER TABLE players ADD COLUMN combat_enemy_hp INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN combat_enemy_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN combat_enemy_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN combat_player_x INTEGER NOT NULL DEFAULT 4",
                "ALTER TABLE players ADD COLUMN combat_player_y INTEGER NOT NULL DEFAULT 4",
                "ALTER TABLE players ADD COLUMN combat_moves_left INTEGER NOT NULL DEFAULT 3",
                # Chest inventory tables
                """CREATE TABLE IF NOT EXISTS chests (
                    chest_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cave_id INTEGER NOT NULL,
                    local_x INTEGER NOT NULL,
                    local_y INTEGER NOT NULL,
                    chest_type TEXT NOT NULL DEFAULT 'cave_chest',
                    UNIQUE(cave_id, local_x, local_y)
                )""",
                """CREATE TABLE IF NOT EXISTS chest_items (
                    chest_id INTEGER NOT NULL,
                    item_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (chest_id, item_id)
                )""",
                # Canoe state
                "ALTER TABLE players ADD COLUMN in_canoe INTEGER NOT NULL DEFAULT 0",
                # Multi-level cave columns
                "ALTER TABLE caves ADD COLUMN cave_level INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE caves ADD COLUMN parent_cave_id INTEGER",
                # Deep cave entrances table
                """CREATE TABLE IF NOT EXISTS cave_deep_entrances (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_cave_id   INTEGER NOT NULL REFERENCES caves(cave_id),
                    parent_local_x   INTEGER NOT NULL,
                    parent_local_y   INTEGER NOT NULL,
                    child_cave_id    INTEGER NOT NULL REFERENCES caves(cave_id),
                    child_local_x    INTEGER NOT NULL,
                    child_local_y    INTEGER NOT NULL,
                    UNIQUE(parent_cave_id, parent_local_x, parent_local_y)
                )""",
                """CREATE TABLE IF NOT EXISTS farm_watered_at (
    world_x INTEGER NOT NULL, world_y INTEGER NOT NULL,
    last_watered TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (world_x, world_y)
)""",
                """CREATE TABLE IF NOT EXISTS treasure_maps (
    user_id INTEGER PRIMARY KEY REFERENCES players(user_id),
    treasure_x INTEGER NOT NULL,
    treasure_y INTEGER NOT NULL,
    found INTEGER NOT NULL DEFAULT 0
)""",
                # Chest replenishment timestamp
                "ALTER TABLE chests ADD COLUMN last_reset TEXT DEFAULT NULL",
                # Player-built houses tables
                """CREATE TABLE IF NOT EXISTS player_houses (
    house_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL,
    is_cave      INTEGER NOT NULL DEFAULT 0,
    loc_cave_id  INTEGER,
    loc_x        INTEGER NOT NULL,
    loc_y        INTEGER NOT NULL
)""",
                """CREATE TABLE IF NOT EXISTS player_house_tiles (
    house_id     INTEGER NOT NULL,
    local_x      INTEGER NOT NULL,
    local_y      INTEGER NOT NULL,
    tile_type    TEXT NOT NULL DEFAULT 'b_floor',
    PRIMARY KEY (house_id, local_x, local_y)
)""",
                # Player house return context (which cave to return to on exit)
                "ALTER TABLE players ADD COLUMN ph_cave_id INTEGER DEFAULT NULL",
                # Cave rock regeneration: tracks mined rocks for 48h regen
                """CREATE TABLE IF NOT EXISTS cave_rock_breaks (
    cave_id      INTEGER NOT NULL,
    local_x      INTEGER NOT NULL,
    local_y      INTEGER NOT NULL,
    broken_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (cave_id, local_x, local_y)
)""",
                # Ocean / boat state
                "ALTER TABLE players ADD COLUMN in_ocean INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN in_high_seas INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN ocean_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN ocean_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN ocean_harbor_wx INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN ocean_harbor_wy INTEGER NOT NULL DEFAULT 0",
                # Ship interior state
                "ALTER TABLE players ADD COLUMN in_ship INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN ship_room TEXT NOT NULL DEFAULT 'helm'",
                "ALTER TABLE players ADD COLUMN ship_hp INTEGER NOT NULL DEFAULT 100",
                "ALTER TABLE players ADD COLUMN ship_max_hp INTEGER NOT NULL DEFAULT 100",
                "ALTER TABLE players ADD COLUMN ship_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN ship_y INTEGER NOT NULL DEFAULT 0",
                # Island state
                "ALTER TABLE players ADD COLUMN in_island INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN island_ox INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN island_oy INTEGER NOT NULL DEFAULT 0",
                # Ship chest tables
                """CREATE TABLE IF NOT EXISTS ship_personal_items (
                    user_id  INTEGER NOT NULL,
                    item_id  TEXT    NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (user_id, item_id)
                )""",
                """CREATE TABLE IF NOT EXISTS ship_cargo_items (
                    user_id  INTEGER NOT NULL,
                    item_id  TEXT    NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (user_id, item_id)
                )""",
                # Ocean island tiles
                """CREATE TABLE IF NOT EXISTS ocean_islands (
                    island_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ocean_x   INTEGER NOT NULL,
                    ocean_y   INTEGER NOT NULL,
                    UNIQUE(ocean_x, ocean_y)
                )""",
                """CREATE TABLE IF NOT EXISTS island_tiles (
                    island_id INTEGER NOT NULL,
                    local_x   INTEGER NOT NULL,
                    local_y   INTEGER NOT NULL,
                    tile_type TEXT    NOT NULL,
                    PRIMARY KEY (island_id, local_x, local_y)
                )""",
                """CREATE TABLE IF NOT EXISTS island_loots (
                    ocean_x INTEGER NOT NULL,
                    ocean_y INTEGER NOT NULL,
                    PRIMARY KEY (ocean_x, ocean_y)
                )""",
                # Rift support: cave type marker and boss-defeated flag
                "ALTER TABLE caves ADD COLUMN cave_type TEXT NOT NULL DEFAULT 'cave'",
                "ALTER TABLE caves ADD COLUMN boss_defeated INTEGER NOT NULL DEFAULT 0",
                # Quest system enhancements
                "ALTER TABLE quests ADD COLUMN source_type TEXT NOT NULL DEFAULT 'village_npc'",
                "ALTER TABLE quests ADD COLUMN quest_subtype TEXT NOT NULL DEFAULT 'kill'",
                "ALTER TABLE quests ADD COLUMN location_type TEXT NOT NULL DEFAULT 'overworld'",
                "ALTER TABLE player_quests ADD COLUMN bounty_wx INTEGER DEFAULT NULL",
                "ALTER TABLE player_quests ADD COLUMN bounty_wy INTEGER DEFAULT NULL",
                "ALTER TABLE player_quests ADD COLUMN source_type TEXT NOT NULL DEFAULT 'village_npc'",
                """CREATE TABLE IF NOT EXISTS quest_pool (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type  TEXT    NOT NULL,
    source_key   TEXT    NOT NULL,
    quest_id     INTEGER NOT NULL REFERENCES quests(id),
    generated_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at   TEXT    NOT NULL
)""",
                # Daily puzzle reward tracking (one claim per player per UTC date)
                """CREATE TABLE IF NOT EXISTS puzzle_rewards (
    user_id      INTEGER NOT NULL,
    reward_date  TEXT    NOT NULL,
    PRIMARY KEY (user_id, reward_date)
)""",
                # Volcano island type
                "ALTER TABLE ocean_islands ADD COLUMN island_type TEXT NOT NULL DEFAULT 'regular'",
                # Island cave entrance links: island position → cave
                """CREATE TABLE IF NOT EXISTS island_cave_entrances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    island_id    INTEGER NOT NULL,
    local_x      INTEGER NOT NULL,
    local_y      INTEGER NOT NULL,
    cave_id      INTEGER NOT NULL,
    UNIQUE(island_id, local_x, local_y)
)""",
                # Track which island a cave's entrance returns to
                "ALTER TABLE cave_entrances ADD COLUMN island_id INTEGER DEFAULT NULL",
                "ALTER TABLE cave_entrances ADD COLUMN island_local_x INTEGER DEFAULT NULL",
                "ALTER TABLE cave_entrances ADD COLUMN island_local_y INTEGER DEFAULT NULL",
                # Player custom avatar emoji
                "ALTER TABLE players ADD COLUMN avatar_emoji TEXT DEFAULT NULL",
                # Ship crew system
                """CREATE TABLE IF NOT EXISTS ship_crew (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    slot    INTEGER NOT NULL,
                    name    TEXT    NOT NULL DEFAULT 'Sailor',
                    task    TEXT    NOT NULL DEFAULT 'idle',
                    UNIQUE(user_id, slot)
                )""",
                # Per-player village tile overrides (recruitable NPC removal / replacement)
                """CREATE TABLE IF NOT EXISTS player_village_overrides (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    village_id INTEGER NOT NULL,
                    tile_x     INTEGER NOT NULL,
                    tile_y     INTEGER NOT NULL,
                    tile_type  TEXT    NOT NULL,
                    UNIQUE(user_id, village_id, tile_x, tile_y)
                )""",
                # Sunken ship (shipwreck) interior state
                "ALTER TABLE players ADD COLUMN in_shipwreck INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN shipwreck_id INTEGER DEFAULT NULL",
                "ALTER TABLE players ADD COLUMN shipwreck_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN shipwreck_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN shipwreck_wx INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN shipwreck_wy INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN breath INTEGER NOT NULL DEFAULT 100",
                # Track which shipwreck chests have been looted (per player)
                """CREATE TABLE IF NOT EXISTS shipwreck_looted_chests (
                    user_id    INTEGER NOT NULL,
                    sw_wx      INTEGER NOT NULL,
                    sw_wy      INTEGER NOT NULL,
                    chest_x    INTEGER NOT NULL,
                    chest_y    INTEGER NOT NULL,
                    looted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, sw_wx, sw_wy, chest_x, chest_y)
                )""",
                # Sky biome tables
                """CREATE TABLE IF NOT EXISTS sky_biomes (
                    sky_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                    width   INTEGER NOT NULL,
                    height  INTEGER NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS sky_tiles (
                    sky_id    INTEGER NOT NULL,
                    local_x   INTEGER NOT NULL,
                    local_y   INTEGER NOT NULL,
                    tile_type TEXT    NOT NULL,
                    PRIMARY KEY (sky_id, local_x, local_y)
                )""",
                """CREATE TABLE IF NOT EXISTS sky_portals (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_x INTEGER NOT NULL,
                    world_y INTEGER NOT NULL,
                    sky_id  INTEGER NOT NULL,
                    UNIQUE(world_x, world_y)
                )""",
                """CREATE TABLE IF NOT EXISTS sky_chest_state (
                    sky_id  INTEGER NOT NULL,
                    local_x INTEGER NOT NULL,
                    local_y INTEGER NOT NULL,
                    looted  INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (sky_id, local_x, local_y)
                )""",
                # Sky biome player state columns
                "ALTER TABLE players ADD COLUMN in_sky INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN sky_id INTEGER DEFAULT NULL",
                "ALTER TABLE players ADD COLUMN sky_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN sky_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN sky_portal_wx INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN sky_portal_wy INTEGER NOT NULL DEFAULT 0",
                # Cave-located ground items (for drops inside caves)
                "ALTER TABLE ground_items ADD COLUMN cave_id INTEGER DEFAULT NULL",
                "ALTER TABLE ground_items ADD COLUMN cave_x INTEGER DEFAULT NULL",
                "ALTER TABLE ground_items ADD COLUMN cave_y INTEGER DEFAULT NULL",
                # Sky temples system
                """CREATE TABLE IF NOT EXISTS sky_temples (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_x     INTEGER NOT NULL,
                    world_y     INTEGER NOT NULL,
                    temple_type TEXT    NOT NULL DEFAULT 'outer',
                    sky_id      INTEGER DEFAULT NULL,
                    UNIQUE(world_x, world_y)
                )""",
                """CREATE TABLE IF NOT EXISTS temple_tiles (
                    temple_id INTEGER NOT NULL,
                    local_x   INTEGER NOT NULL,
                    local_y   INTEGER NOT NULL,
                    tile_type TEXT    NOT NULL,
                    PRIMARY KEY (temple_id, local_x, local_y)
                )""",
                """CREATE TABLE IF NOT EXISTS temple_gear_slots (
                    temple_id    INTEGER NOT NULL,
                    slot_x       INTEGER NOT NULL,
                    slot_y       INTEGER NOT NULL,
                    required_gear TEXT   NOT NULL,
                    is_filled    INTEGER NOT NULL DEFAULT 0,
                    filled_by    INTEGER DEFAULT NULL,
                    PRIMARY KEY (temple_id, slot_x, slot_y)
                )""",
                # Temple player state
                "ALTER TABLE players ADD COLUMN in_temple INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN temple_id INTEGER DEFAULT NULL",
                "ALTER TABLE players ADD COLUMN temple_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN temple_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN temple_wx INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN temple_wy INTEGER NOT NULL DEFAULT 0",
                # Forest interior player state
                "ALTER TABLE players ADD COLUMN in_forest INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN forest_id INTEGER DEFAULT NULL",
                "ALTER TABLE players ADD COLUMN forest_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN forest_y INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN forest_wx INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN forest_wy INTEGER NOT NULL DEFAULT 0",
                # Maze interior player state
                "ALTER TABLE players ADD COLUMN in_maze INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN maze_id INTEGER DEFAULT NULL",
                "ALTER TABLE players ADD COLUMN maze_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN maze_y INTEGER NOT NULL DEFAULT 0",
                # Forest tables
                """CREATE TABLE IF NOT EXISTS forest_areas (
    forest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    width     INTEGER NOT NULL,
    height    INTEGER NOT NULL
)""",
                """CREATE TABLE IF NOT EXISTS forest_tiles (
    forest_id INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (forest_id, local_x, local_y)
)""",
                """CREATE TABLE IF NOT EXISTS forest_entrances (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    forest_id INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    world_x   INTEGER NOT NULL,
    world_y   INTEGER NOT NULL,
    UNIQUE(world_x, world_y)
)""",
                """CREATE TABLE IF NOT EXISTS maze_areas (
    maze_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    forest_id INTEGER NOT NULL,
    width     INTEGER NOT NULL,
    height    INTEGER NOT NULL
)""",
                """CREATE TABLE IF NOT EXISTS maze_tiles (
    maze_id   INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (maze_id, local_x, local_y)
)""",
                # Track per-player forest/maze chest loots
                """CREATE TABLE IF NOT EXISTS player_maze_loots (
    user_id  INTEGER NOT NULL,
    maze_id  INTEGER NOT NULL,
    PRIMARY KEY (user_id, maze_id)
)""",
                """CREATE TABLE IF NOT EXISTS player_forest_loots (
    user_id   INTEGER NOT NULL,
    forest_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, forest_id)
)""",
                """CREATE TABLE IF NOT EXISTS player_forest_chest_loots (
    user_id   INTEGER NOT NULL,
    forest_id INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    PRIMARY KEY (user_id, forest_id, local_x, local_y)
)""",
                # Maze entry position columns (added for 3-wide path redesign)
                "ALTER TABLE maze_areas ADD COLUMN entry_x INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE maze_areas ADD COLUMN entry_y INTEGER NOT NULL DEFAULT 1",
                # Tree City interior player state
                "ALTER TABLE players ADD COLUMN in_tree_city INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN tc_forest_id INTEGER",
                "ALTER TABLE players ADD COLUMN tc_floor INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE players ADD COLUMN tc_x INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE players ADD COLUMN tc_y INTEGER NOT NULL DEFAULT 0",
                # Tree City interior tiles table
                """CREATE TABLE IF NOT EXISTS tree_city_tiles (
    forest_id INTEGER NOT NULL,
    floor_num INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (forest_id, floor_num, local_x, local_y)
)""",
                # Grove tables
                """CREATE TABLE IF NOT EXISTS grove_areas (
    grove_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    forest_id INTEGER NOT NULL,
    width     INTEGER NOT NULL DEFAULT 19,
    height    INTEGER NOT NULL DEFAULT 19
)""",
                """CREATE TABLE IF NOT EXISTS grove_tiles (
    grove_id  INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (grove_id, local_x, local_y)
)""",
                # Watering can uses counter
                "ALTER TABLE players ADD COLUMN watering_can_uses INTEGER NOT NULL DEFAULT 0",
                # Player map collection (forest maps etc.)
                """CREATE TABLE IF NOT EXISTS player_map_collection (
    user_id   INTEGER NOT NULL,
    map_type  TEXT    NOT NULL,
    ref_id    INTEGER NOT NULL,
    acquired_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, map_type, ref_id)
)""",
            ]
            for mig_sql in migrations:
                try:
                    conn.execute(mig_sql)
                    conn.commit()
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    # Expected: column already exists, table already exists
                    if "duplicate column" not in msg and "already exists" not in msg:
                        _log.warning("Migration warning (%s): %.120s", e, mig_sql)
                except Exception as e:
                    _log.error("Migration error (%s): %.120s", e, mig_sql)
            # ── Grove state columns on players ───────────────────────────────────
            _player_cols = {r[1] for r in conn.execute("PRAGMA table_info(players)").fetchall()}
            for _col, _def in [("in_grove", "0"), ("grove_id", "NULL"), ("grove_x", "0"),
                               ("grove_y", "0"), ("grove_forest_id", "NULL")]:
                if _col not in _player_cols:
                    try:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {_col} INTEGER DEFAULT {_def}")
                        conn.commit()
                    except Exception as e:
                        _log.warning("Grove column migration warning (%s): %s", e, _col)

            # ── is_main_quest column on player_quests ─────────────────────────────
            _pq_cols = {r[1] for r in conn.execute("PRAGMA table_info(player_quests)").fetchall()}
            if "is_main_quest" not in _pq_cols:
                try:
                    conn.execute("ALTER TABLE player_quests ADD COLUMN is_main_quest INTEGER NOT NULL DEFAULT 0")
                    conn.commit()
                except Exception as e:
                    _log.warning("is_main_quest migration warning: %s", e)

            # ── loot_day column on player_forest_chest_loots ──────────────────────
            _fchest_cols = {r[1] for r in conn.execute("PRAGMA table_info(player_forest_chest_loots)").fetchall()}
            if "loot_day" not in _fchest_cols:
                try:
                    conn.execute("ALTER TABLE player_forest_chest_loots ADD COLUMN loot_day INTEGER NOT NULL DEFAULT 0")
                    conn.commit()
                except Exception as e:
                    _log.warning("loot_day migration warning: %s", e)

            # ── wayerwood_tx / wayerwood_ty columns on forest_areas ───────────────
            _fa_cols = {r[1] for r in conn.execute("PRAGMA table_info(forest_areas)").fetchall()}
            if "wayerwood_tx" not in _fa_cols:
                try:
                    conn.execute("ALTER TABLE forest_areas ADD COLUMN wayerwood_tx INTEGER DEFAULT NULL")
                    conn.execute("ALTER TABLE forest_areas ADD COLUMN wayerwood_ty INTEGER DEFAULT NULL")
                    conn.commit()
                except Exception as e:
                    _log.warning("wayerwood_tx migration warning: %s", e)

            # ── Inventory table rebuild (remove UNIQUE, add slot_index) ──────────
            inv_cols = {row[1] for row in conn.execute("PRAGMA table_info(inventory)").fetchall()}
            if "slot_index" not in inv_cols:
                try:
                    # Rebuild inventory without UNIQUE(user_id, item_id), with slot_index
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS inventory_new (
                            id         INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id    INTEGER NOT NULL,
                            item_id    TEXT    NOT NULL,
                            quantity   INTEGER NOT NULL DEFAULT 1,
                            slot_index INTEGER NOT NULL DEFAULT 0
                        )
                    """)
                    rows = conn.execute(
                        "SELECT id, user_id, item_id, quantity FROM inventory ORDER BY user_id, id"
                    ).fetchall()
                    user_counters: dict = {}
                    for row in rows:
                        uid = row[1]
                        idx = user_counters.get(uid, 0)
                        conn.execute(
                            "INSERT INTO inventory_new (user_id, item_id, quantity, slot_index)"
                            " VALUES (?, ?, ?, ?)",
                            (uid, row[2], row[3], idx),
                        )
                        user_counters[uid] = idx + 1
                    conn.execute("DROP TABLE inventory")
                    conn.execute("ALTER TABLE inventory_new RENAME TO inventory")
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id, slot_index)"
                    )
                    conn.commit()
                    _log.info("Inventory table rebuilt with slot_index column")
                except Exception as e:
                    _log.error("Inventory rebuild error: %s", e)

            # ── Remove equipped items from inventory (one-time migration) ─────────
            # Check via a flag column on world table — add it if missing
            wt_cols = {row[1] for row in conn.execute("PRAGMA table_info(world)").fetchall()}
            if "inv_equip_migrated" not in wt_cols:
                try:
                    conn.execute(
                        "ALTER TABLE world ADD COLUMN inv_equip_migrated INTEGER NOT NULL DEFAULT 0"
                    )
                    conn.commit()
                except Exception:
                    pass
            needs_equip_mig = conn.execute(
                "SELECT COALESCE(inv_equip_migrated, 0) FROM world WHERE guild_id=0"
            ).fetchone()
            if needs_equip_mig and not needs_equip_mig[0]:
                try:
                    eq_rows = conn.execute(
                        "SELECT user_id, item_id FROM equipment"
                    ).fetchall()
                    for uid, item_id in eq_rows:
                        inv_row = conn.execute(
                            "SELECT id, quantity FROM inventory WHERE user_id=? AND item_id=? LIMIT 1",
                            (uid, item_id),
                        ).fetchone()
                        if inv_row:
                            if inv_row[1] <= 1:
                                conn.execute("DELETE FROM inventory WHERE id=?", (inv_row[0],))
                            else:
                                conn.execute(
                                    "UPDATE inventory SET quantity=quantity-1 WHERE id=?",
                                    (inv_row[0],),
                                )
                    # Renumber slot_index per user after removals
                    all_inv = conn.execute(
                        "SELECT id, user_id FROM inventory ORDER BY user_id, slot_index, id"
                    ).fetchall()
                    uc: dict = {}
                    for inv_id, uid in all_inv:
                        idx = uc.get(uid, 0)
                        conn.execute("UPDATE inventory SET slot_index=? WHERE id=?", (idx, inv_id))
                        uc[uid] = idx + 1
                    conn.execute("UPDATE world SET inv_equip_migrated=1 WHERE guild_id=0")
                    conn.commit()
                    _log.info("Equipped items removed from inventory (migration complete)")
                except Exception as e:
                    _log.error("Equip migration error: %s", e)

            # ── Fix player_quests: NULL is_main_quest → 0 (should be side quests) ──
            try:
                conn.execute(
                    "UPDATE player_quests SET is_main_quest = 0 "
                    "WHERE is_main_quest IS NULL AND status = 'active'"
                )
                conn.commit()
            except Exception:
                pass

            # ── Bandit camp interior state columns on players ─────────────────────
            _bc_cols = {r[1] for r in conn.execute("PRAGMA table_info(players)").fetchall()}
            for _bcol, _bdef in [
                ("in_bandit_camp",          "0"),
                ("bandit_camp_id",          "NULL"),
                ("bc_x",                    "0"),
                ("bc_y",                    "0"),
                ("bandit_bribe_remaining",  "0"),
            ]:
                if _bcol not in _bc_cols:
                    try:
                        conn.execute(
                            f"ALTER TABLE players ADD COLUMN {_bcol} INTEGER "
                            f"NOT NULL DEFAULT {_bdef}"
                            if _bdef != "NULL" else
                            f"ALTER TABLE players ADD COLUMN {_bcol} INTEGER DEFAULT NULL"
                        )
                        conn.commit()
                    except Exception as e:
                        _log.warning("Bandit camp column migration warning (%s): %s", e, _bcol)

            # ── has_warp_crystal column on players ───────────────────────────────
            _pc2 = {r[1] for r in conn.execute("PRAGMA table_info(players)").fetchall()}
            if "has_warp_crystal" not in _pc2:
                try:
                    conn.execute("ALTER TABLE players ADD COLUMN has_warp_crystal INTEGER NOT NULL DEFAULT 0")
                    conn.commit()
                except Exception as e:
                    _log.warning("has_warp_crystal migration warning: %s", e)

            # ── player_waypoints table ────────────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS player_waypoints (
                    user_id     INTEGER NOT NULL,
                    waypoint_id TEXT    NOT NULL,
                    PRIMARY KEY (user_id, waypoint_id)
                )
            """)
            conn.commit()

            # ── tree_chop_progress table ──────────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tree_chop_progress (
                    world_x   INTEGER NOT NULL,
                    world_y   INTEGER NOT NULL,
                    chops     INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (world_x, world_y)
                )
            """)
            conn.commit()

            # ── tree_city_tiles: force rebuild if tc_archivist NPC not yet present ─
            try:
                _arch_count = conn.execute(
                    "SELECT COUNT(*) FROM tree_city_tiles WHERE tile_type='tc_archivist'"
                ).fetchone()[0]
                if _arch_count == 0:
                    _tc_forests = conn.execute(
                        "SELECT DISTINCT forest_id FROM tree_city_tiles"
                    ).fetchall()
                    for _tcf in _tc_forests:
                        conn.execute("DELETE FROM tree_city_tiles WHERE forest_id=?",
                                     (_tcf[0],))
                    conn.commit()
                    _log.info("Cleared %d tree city(ies) for tc_archivist rebuild", len(_tc_forests))
            except Exception as e:
                _log.warning("tc_archivist rebuild migration warning: %s", e)

            # ── tree_city_tiles: force rebuild if blocking tc_plant at (9,12) ─────
            # Old layout had decorative plants in doorway corridors; move them clear.
            try:
                _plant_block = conn.execute(
                    "SELECT COUNT(*) FROM tree_city_tiles"
                    " WHERE floor=1 AND local_x=9 AND local_y=12 AND tile_type='tc_plant'"
                ).fetchone()[0]
                if _plant_block > 0:
                    _tc_forests2 = conn.execute(
                        "SELECT DISTINCT forest_id FROM tree_city_tiles"
                    ).fetchall()
                    for _tcf2 in _tc_forests2:
                        conn.execute("DELETE FROM tree_city_tiles WHERE forest_id=?",
                                     (_tcf2[0],))
                    conn.commit()
                    _log.info("Cleared %d tree city(ies) for plant-path rebuild", len(_tc_forests2))
            except Exception as e:
                _log.warning("tc_plant path rebuild migration warning: %s", e)

            # ── ground_items: create if missing, then ensure is_drop column ────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ground_items (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_x    INTEGER NOT NULL,
                    world_y    INTEGER NOT NULL,
                    item_id    TEXT    NOT NULL,
                    quantity   INTEGER NOT NULL DEFAULT 1,
                    is_drop    INTEGER NOT NULL DEFAULT 0,
                    spawned_at TEXT    NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ground_items_pos ON ground_items(world_x, world_y)"
            )
            conn.commit()
            gi_cols = {row[1] for row in conn.execute("PRAGMA table_info(ground_items)").fetchall()}
            if "is_drop" not in gi_cols:
                try:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS ground_items_new (
                            id         INTEGER PRIMARY KEY AUTOINCREMENT,
                            world_x    INTEGER NOT NULL,
                            world_y    INTEGER NOT NULL,
                            item_id    TEXT    NOT NULL,
                            quantity   INTEGER NOT NULL DEFAULT 1,
                            is_drop    INTEGER NOT NULL DEFAULT 0,
                            spawned_at TEXT    NOT NULL DEFAULT (datetime('now'))
                        )
                    """)
                    conn.execute("""
                        INSERT INTO ground_items_new (world_x, world_y, item_id, quantity, spawned_at)
                        SELECT world_x, world_y, item_id, quantity, spawned_at FROM ground_items
                    """)
                    conn.execute("DROP TABLE ground_items")
                    conn.execute("ALTER TABLE ground_items_new RENAME TO ground_items")
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ground_items_pos ON ground_items(world_x, world_y)"
                    )
                    conn.commit()
                    _log.info("ground_items table rebuilt with is_drop column")
                except Exception as e:
                    _log.error("ground_items rebuild error: %s", e)

            # ── bandit_camps table ─────────────────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bandit_camps (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_x      INTEGER NOT NULL,
                    world_y      INTEGER NOT NULL,
                    max_bandits  INTEGER NOT NULL DEFAULT 4,
                    bandit_kills INTEGER NOT NULL DEFAULT 0,
                    cleared_at   INTEGER,
                    UNIQUE(world_x, world_y)
                )
            """)
            conn.commit()

            # Clean up quest_board overrides from old worlds
            try:
                conn.execute("DELETE FROM tile_overrides WHERE tile_type = 'quest_board'")
                conn.commit()
            except Exception:
                pass

            # ── Temple mountain walls (surround air temples with impassable mountain) ──
            # One-time migration: if any temple overrides exist without mountain neighbours, add them.
            try:
                from dwarf_explorer.config import WORLD_SIZE as _WORLD_SIZE
                temple_rows = conn.execute(
                    "SELECT world_x, world_y FROM tile_overrides "
                    "WHERE tile_type IN ('sky_temple_outer', 'sky_temple_main')"
                ).fetchall()
                if temple_rows:
                    mountain_overrides = []
                    for tx, ty in temple_rows:
                        for ddx, ddy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]:
                            nx, ny = tx + ddx, ty + ddy
                            if 0 < nx < _WORLD_SIZE and 0 < ny < _WORLD_SIZE:
                                mountain_overrides.append((nx, ny))
                    conn.executemany(
                        "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) "
                        "VALUES (?, ?, 'mountain')",
                        mountain_overrides,
                    )
                    conn.commit()
            except Exception as e:
                _log.warning("Temple mountain migration warning: %s", e)

            # ── Canoe consolidation: collapse canoe_left+canoe_right pairs into a single "canoe" item ──
            # Inventory: for each user, find adjacent canoe_left @ slot N and canoe_right @ slot N+1,
            # insert a single canoe row at slot N (preserve quantity = min of the two), delete the halves.
            try:
                # Inventory
                rows = conn.execute(
                    "SELECT user_id, slot_index, item_id, quantity FROM inventory "
                    "WHERE item_id IN ('canoe_left','canoe_right') ORDER BY user_id, slot_index"
                ).fetchall()
                by_user: dict[int, list[tuple[int, str, int]]] = {}
                for r in rows:
                    by_user.setdefault(r[0], []).append((r[1], r[2], r[3]))
                for uid, half_list in by_user.items():
                    # Match left at N with right at N+1
                    half_map = {(s, iid): q for (s, iid, q) in half_list}
                    used: set[tuple[int, str]] = set()
                    for (s, iid, q) in half_list:
                        if iid != "canoe_left" or (s, iid) in used:
                            continue
                        right_key = (s + 1, "canoe_right")
                        if right_key in half_map and right_key not in used:
                            qty = min(q, half_map[right_key])
                            used.add((s, "canoe_left"))
                            used.add(right_key)
                            # Insert canoe row at slot s, qty preserved
                            conn.execute(
                                "INSERT INTO inventory(user_id, item_id, quantity, slot_index) VALUES(?,?,?,?)",
                                (uid, "canoe", qty, s),
                            )
                    # Delete all original canoe_left/canoe_right halves for this user
                    conn.execute(
                        "DELETE FROM inventory WHERE user_id=? AND item_id IN ('canoe_left','canoe_right')",
                        (uid,),
                    )
                # Bank: merge canoe_left + canoe_right quantities into single canoe row
                bank_rows = conn.execute(
                    "SELECT user_id, item_id, quantity FROM bank_items "
                    "WHERE item_id IN ('canoe_left','canoe_right')"
                ).fetchall()
                bank_pairs: dict[int, dict[str, int]] = {}
                for uid, iid, qty in bank_rows:
                    bank_pairs.setdefault(uid, {})[iid] = qty
                for uid, halves in bank_pairs.items():
                    pair_qty = min(halves.get("canoe_left", 0), halves.get("canoe_right", 0))
                    conn.execute(
                        "DELETE FROM bank_items WHERE user_id=? AND item_id IN ('canoe_left','canoe_right')",
                        (uid,),
                    )
                    if pair_qty > 0:
                        conn.execute(
                            "INSERT INTO bank_items(user_id, item_id, quantity) VALUES(?, 'canoe', ?) "
                            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
                            (uid, pair_qty, pair_qty),
                        )
                # Ground items: collapse paired halves at same (world_x, world_y) into a single canoe item
                gi_rows = conn.execute(
                    "SELECT world_x, world_y, item_id, SUM(quantity) FROM ground_items "
                    "WHERE item_id IN ('canoe_left','canoe_right') AND is_drop=1 "
                    "GROUP BY world_x, world_y, item_id"
                ).fetchall()
                gi_pairs: dict[tuple[int, int], dict[str, int]] = {}
                for wx, wy, iid, qty in gi_rows:
                    gi_pairs.setdefault((wx, wy), {})[iid] = qty
                for (wx, wy), halves in gi_pairs.items():
                    pair_qty = min(halves.get("canoe_left", 0), halves.get("canoe_right", 0))
                    conn.execute(
                        "DELETE FROM ground_items WHERE world_x=? AND world_y=? AND item_id IN ('canoe_left','canoe_right')",
                        (wx, wy),
                    )
                    if pair_qty > 0:
                        conn.execute(
                            "INSERT INTO ground_items(world_x, world_y, item_id, quantity, is_drop) VALUES(?,?,?,?,1)",
                            (wx, wy, "canoe", pair_qty),
                        )
                # Equipment table: rename canoe_left→canoe; delete canoe_right (canoe is one item now)
                conn.execute(
                    "UPDATE equipment SET item_id='canoe' WHERE item_id='canoe_left'"
                )
                conn.execute(
                    "DELETE FROM equipment WHERE item_id='canoe_right'"
                )
                # Note: players.hand_1/hand_2 are loaded from the equipment table
                # (slot='hand_1'/'hand_2'), already handled by the equipment UPDATE above.
                conn.commit()

                # Canoes must not stack: split any inventory canoe row with qty > 1
                # into individual qty=1 rows at fresh slot pairs.
                stacked = conn.execute(
                    "SELECT id, user_id, slot_index, quantity FROM inventory "
                    "WHERE item_id='canoe' AND quantity > 1"
                ).fetchall()
                INV_COLS = 7
                for row_id, uid, sidx, qty in stacked:
                    # First row keeps qty=1
                    conn.execute("UPDATE inventory SET quantity=1 WHERE id=?", (row_id,))
                    # Add (qty-1) more single canoes at next available 2-wide spots
                    for _ in range(qty - 1):
                        max_row = conn.execute(
                            "SELECT COALESCE(MAX(slot_index)+1, 0) FROM inventory WHERE user_id=?",
                            (uid,),
                        ).fetchone()
                        nxt = max_row[0] if max_row else 0
                        if nxt % INV_COLS == INV_COLS - 1:
                            nxt = (nxt // INV_COLS + 1) * INV_COLS
                        conn.execute(
                            "INSERT INTO inventory(user_id, item_id, quantity, slot_index) VALUES(?,?,1,?)",
                            (uid, "canoe", nxt),
                        )
                    conn.commit()
            except Exception as e:
                _log.warning("Canoe consolidation migration warning: %s", e)

            # ── Canoe slot-gap fix: re-compact every user's inventory so each ──
            # canoe row is followed by an empty slot (its virtual right half).
            # Also un-equip any canoes that ended up in the equipment table.
            # This migration is idempotent — safe to run every startup.
            try:
                # 1. Return equipped canoes to inventory
                equipped_canoe_users = conn.execute(
                    "SELECT DISTINCT user_id FROM equipment WHERE item_id='canoe'"
                ).fetchall()
                INV_COLS = 7
                for (uid,) in equipped_canoe_users:
                    conn.execute(
                        "UPDATE equipment SET item_id=NULL WHERE user_id=? AND item_id='canoe'",
                        (uid,),
                    )
                    max_row = conn.execute(
                        "SELECT COALESCE(MAX(slot_index)+1, 0) FROM inventory WHERE user_id=?",
                        (uid,),
                    ).fetchone()
                    nxt = max_row[0] if max_row else 0
                    if nxt % INV_COLS == INV_COLS - 1:
                        nxt = (nxt // INV_COLS + 1) * INV_COLS
                    conn.execute(
                        "INSERT INTO inventory(user_id, item_id, quantity, slot_index) VALUES(?,?,1,?)",
                        (uid, "canoe", nxt),
                    )

                # 2. Canoe-aware compact for every user who has a canoe in inventory.
                #    Each canoe DB row occupies two visual slots; the slot AFTER the
                #    canoe's slot_index must be free for the virtual right half.
                canoe_users = conn.execute(
                    "SELECT DISTINCT user_id FROM inventory WHERE item_id='canoe'"
                ).fetchall()
                for (uid,) in canoe_users:
                    inv_rows = conn.execute(
                        "SELECT id, item_id FROM inventory WHERE user_id=? ORDER BY slot_index, id",
                        (uid,),
                    ).fetchall()
                    new_idx = 0
                    for row_id, iid in inv_rows:
                        conn.execute(
                            "UPDATE inventory SET slot_index=? WHERE id=?",
                            (new_idx, row_id),
                        )
                        new_idx += 2 if iid == "canoe" else 1
                conn.commit()
            except Exception as e:
                _log.warning("Canoe slot-gap migration warning: %s", e)

        await asyncio.to_thread(_migrate)

    async def close(self) -> None:
        if self._conn:
            def _close():
                self._conn.close()
            await asyncio.to_thread(_close)
            self._conn = None


_databases: dict[str, Database] = {}


async def get_database(guild_id: int) -> Database:
    """Get or create the single shared world Database (all guilds share one world)."""
    if "shared" not in _databases:
        base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        db_path = os.path.join(base_dir, "shared.db")
        db = Database(db_path)
        await db.init_schema()
        _databases["shared"] = db
    return _databases["shared"]
