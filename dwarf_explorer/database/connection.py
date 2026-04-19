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


_databases: dict[int, Database] = {}


async def get_database(guild_id: int) -> Database:
    """Get or create a Database instance for a guild."""
    if guild_id not in _databases:
        base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        db_path = os.path.join(base_dir, f"{guild_id}.db")
        db = Database(db_path)
        await db.init_schema()
        _databases[guild_id] = db
    return _databases[guild_id]
