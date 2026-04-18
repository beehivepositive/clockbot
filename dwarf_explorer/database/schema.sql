-- World metadata
CREATE TABLE IF NOT EXISTS world (
    guild_id     INTEGER PRIMARY KEY,
    seed         INTEGER NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    map_name     TEXT    NOT NULL DEFAULT 'wilderness',
    initialized  INTEGER NOT NULL DEFAULT 0
);

-- Visited chunks
CREATE TABLE IF NOT EXISTS chunks (
    chunk_x          INTEGER NOT NULL,
    chunk_y          INTEGER NOT NULL,
    first_visited_by INTEGER,
    first_visited_at TEXT,
    PRIMARY KEY (chunk_x, chunk_y)
);

-- Modified tiles (rivers, structures, player changes)
CREATE TABLE IF NOT EXISTS tile_overrides (
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    tile_type    TEXT    NOT NULL,
    placed_by    INTEGER,
    placed_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (world_x, world_y)
);

-- Ground items
CREATE TABLE IF NOT EXISTS ground_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    item_id      TEXT    NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    spawned_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(world_x, world_y, item_id)
);

-- Enemies
CREATE TABLE IF NOT EXISTS enemies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    enemy_type   TEXT    NOT NULL,
    hp           INTEGER NOT NULL,
    max_hp       INTEGER NOT NULL,
    defeated_at  TEXT,
    UNIQUE(world_x, world_y)
);

-- Players
CREATE TABLE IF NOT EXISTS players (
    user_id      INTEGER PRIMARY KEY,
    display_name TEXT    NOT NULL,
    world_x      INTEGER NOT NULL DEFAULT 112,
    world_y      INTEGER NOT NULL DEFAULT 112,
    hp           INTEGER NOT NULL DEFAULT 100,
    max_hp       INTEGER NOT NULL DEFAULT 100,
    attack       INTEGER NOT NULL DEFAULT 10,
    defense      INTEGER NOT NULL DEFAULT 5,
    gold         INTEGER NOT NULL DEFAULT 0,
    xp           INTEGER NOT NULL DEFAULT 0,
    level        INTEGER NOT NULL DEFAULT 1,
    message_id   INTEGER,
    channel_id   INTEGER,
    last_active  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Player inventory
CREATE TABLE IF NOT EXISTS inventory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES players(user_id),
    item_id      TEXT    NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    UNIQUE(user_id, item_id)
);

-- Quest definitions
CREATE TABLE IF NOT EXISTS quests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    quest_type   TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    description  TEXT    NOT NULL,
    target_id    TEXT    NOT NULL,
    target_count INTEGER NOT NULL DEFAULT 1,
    reward_gold  INTEGER NOT NULL DEFAULT 0,
    reward_xp    INTEGER NOT NULL DEFAULT 0,
    reward_item  TEXT,
    location_x   INTEGER,
    location_y   INTEGER
);

-- Player quest progress
CREATE TABLE IF NOT EXISTS player_quests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES players(user_id),
    quest_id     INTEGER NOT NULL REFERENCES quests(id),
    progress     INTEGER NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL DEFAULT 'active',
    accepted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    UNIQUE(user_id, quest_id)
);

-- Caves
CREATE TABLE IF NOT EXISTS caves (
    cave_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    width        INTEGER NOT NULL,
    height       INTEGER NOT NULL
);

-- Cave interior tiles
CREATE TABLE IF NOT EXISTS cave_tiles (
    cave_id      INTEGER NOT NULL REFERENCES caves(cave_id),
    local_x      INTEGER NOT NULL,
    local_y      INTEGER NOT NULL,
    tile_type    TEXT    NOT NULL,
    PRIMARY KEY (cave_id, local_x, local_y)
);

-- Cave entrances linking interior to wilderness
CREATE TABLE IF NOT EXISTS cave_entrances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cave_id      INTEGER NOT NULL REFERENCES caves(cave_id),
    local_x      INTEGER NOT NULL,
    local_y      INTEGER NOT NULL,
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    UNIQUE(cave_id, local_x, local_y),
    UNIQUE(world_x, world_y)
);

-- Villages
CREATE TABLE IF NOT EXISTS villages (
    village_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    width        INTEGER NOT NULL,
    height       INTEGER NOT NULL
);

-- Village interior tiles
CREATE TABLE IF NOT EXISTS village_tiles (
    village_id   INTEGER NOT NULL REFERENCES villages(village_id),
    local_x      INTEGER NOT NULL,
    local_y      INTEGER NOT NULL,
    tile_type    TEXT    NOT NULL,
    PRIMARY KEY (village_id, local_x, local_y)
);

-- Village entrances linking wilderness tile to village interior
CREATE TABLE IF NOT EXISTS village_entrances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id   INTEGER NOT NULL REFERENCES villages(village_id),
    entry_x      INTEGER NOT NULL,
    entry_y      INTEGER NOT NULL,
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    UNIQUE(world_x, world_y)
);

-- Buildings inside villages (houses, church, bank, shop)
CREATE TABLE IF NOT EXISTS houses (
    house_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id    INTEGER NOT NULL REFERENCES villages(village_id),
    building_type TEXT    NOT NULL DEFAULT 'house',
    width         INTEGER NOT NULL,
    height        INTEGER NOT NULL
);

-- House interior tiles
CREATE TABLE IF NOT EXISTS house_tiles (
    house_id     INTEGER NOT NULL REFERENCES houses(house_id),
    local_x      INTEGER NOT NULL,
    local_y      INTEGER NOT NULL,
    tile_type    TEXT    NOT NULL,
    PRIMARY KEY (house_id, local_x, local_y)
);

-- House entrances: which village tile leads into each house
CREATE TABLE IF NOT EXISTS house_entrances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    house_id     INTEGER NOT NULL REFERENCES houses(house_id),
    entry_x      INTEGER NOT NULL,
    entry_y      INTEGER NOT NULL,
    village_id   INTEGER NOT NULL,
    village_x    INTEGER NOT NULL,
    village_y    INTEGER NOT NULL,
    UNIQUE(village_id, village_x, village_y)
);

-- Player equipment (weapon, boots slots)
CREATE TABLE IF NOT EXISTS equipment (
    user_id  INTEGER NOT NULL REFERENCES players(user_id),
    slot     TEXT    NOT NULL,
    item_id  TEXT    NOT NULL,
    PRIMARY KEY (user_id, slot)
);

-- Bank storage per player
CREATE TABLE IF NOT EXISTS bank_items (
    user_id  INTEGER NOT NULL REFERENCES players(user_id),
    item_id  TEXT    NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, item_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ground_items_pos ON ground_items(world_x, world_y);
CREATE INDEX IF NOT EXISTS idx_enemies_pos ON enemies(world_x, world_y);
CREATE INDEX IF NOT EXISTS idx_tile_overrides_pos ON tile_overrides(world_x, world_y);
CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id);
CREATE INDEX IF NOT EXISTS idx_player_quests_user ON player_quests(user_id);
