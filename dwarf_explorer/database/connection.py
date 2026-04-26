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
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r") as f:
            sql = f.read()
        await self.execute_script(sql)
        # Migrations for existing DBs
        def _migrate():
            conn = self._get_conn()
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
            ]
            for sql in migrations:
                try:
                    conn.execute(sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column already exists
            # Clean up quest_board overrides from old worlds
            conn.execute("DELETE FROM tile_overrides WHERE tile_type = 'quest_board'")
            conn.commit()
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
