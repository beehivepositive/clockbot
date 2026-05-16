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

-- Ground items (is_drop=1 means placed by a player; expires after 1 hour)
CREATE TABLE IF NOT EXISTS ground_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    item_id      TEXT    NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    is_drop      INTEGER NOT NULL DEFAULT 0,
    spawned_at   TEXT    NOT NULL DEFAULT (datetime('now'))
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

-- Player inventory (slot_index allows multiple stacks of same item; no UNIQUE constraint)
CREATE TABLE IF NOT EXISTS inventory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES players(user_id),
    item_id      TEXT    NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    slot_index   INTEGER NOT NULL DEFAULT 0
);

-- Quest definitions (generated dynamically; rows persist until all referencing player_quests are gone)
CREATE TABLE IF NOT EXISTS quests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    quest_type    TEXT    NOT NULL,          -- human-readable type label
    title         TEXT    NOT NULL,
    description   TEXT    NOT NULL,
    target_id     TEXT    NOT NULL,          -- enemy_type or item_id
    target_count  INTEGER NOT NULL DEFAULT 1,
    reward_gold   INTEGER NOT NULL DEFAULT 0,
    reward_xp     INTEGER NOT NULL DEFAULT 0,
    reward_item   TEXT,
    location_x    INTEGER,                   -- world_x of target area / destination
    location_y    INTEGER,                   -- world_y of target area / destination
    source_type   TEXT    NOT NULL DEFAULT 'village_npc',  -- 'village_npc'|'bounty'|'merchant'
    quest_subtype TEXT    NOT NULL DEFAULT 'kill',          -- 'kill'|'fetch'|'investigation'|'delivery'
    location_type TEXT    NOT NULL DEFAULT 'overworld'      -- 'overworld'|'ocean'
);

-- Player quest progress
CREATE TABLE IF NOT EXISTS player_quests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES players(user_id),
    quest_id     INTEGER NOT NULL REFERENCES quests(id),
    progress     INTEGER NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL DEFAULT 'active',   -- 'active'|'completed'|'cancelled'
    accepted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    bounty_wx    INTEGER DEFAULT NULL,   -- personal marker world_x (bounty quests only)
    bounty_wy    INTEGER DEFAULT NULL,   -- personal marker world_y (bounty quests only)
    source_type  TEXT    NOT NULL DEFAULT 'village_npc',
    UNIQUE(user_id, quest_id)
);

-- Available quest pool per source (refreshed every 24h)
CREATE TABLE IF NOT EXISTS quest_pool (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type  TEXT    NOT NULL,  -- 'village_npc' | 'bounty'
    source_key   TEXT    NOT NULL,  -- village_id (str) | 'overworld' | 'ocean'
    quest_id     INTEGER NOT NULL REFERENCES quests(id),
    generated_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at   TEXT    NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id, slot_index);
CREATE INDEX IF NOT EXISTS idx_player_quests_user ON player_quests(user_id);

-- Farm watered timestamps (5-minute cooldown between watering stages)
CREATE TABLE IF NOT EXISTS farm_watered_at (
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    last_watered TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (world_x, world_y)
);

-- Treasure map locations (one active treasure per player)
CREATE TABLE IF NOT EXISTS treasure_maps (
    user_id     INTEGER PRIMARY KEY REFERENCES players(user_id),
    treasure_x  INTEGER NOT NULL,
    treasure_y  INTEGER NOT NULL,
    found       INTEGER NOT NULL DEFAULT 0
);

-- Ship crew members (max 3 per player)
CREATE TABLE IF NOT EXISTS ship_crew (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    slot      INTEGER NOT NULL,   -- 1, 2, or 3
    name      TEXT    NOT NULL DEFAULT 'Sailor',
    task      TEXT    NOT NULL DEFAULT 'idle',
    UNIQUE(user_id, slot)
);

-- Per-player tile overrides inside villages (e.g. recruited NPC removed, replacement placed)
CREATE TABLE IF NOT EXISTS player_village_overrides (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    village_id INTEGER NOT NULL,
    tile_x     INTEGER NOT NULL,
    tile_y     INTEGER NOT NULL,
    tile_type  TEXT    NOT NULL,
    UNIQUE(user_id, village_id, tile_x, tile_y)
);

-- Sky biomes
CREATE TABLE IF NOT EXISTS sky_biomes (
    sky_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    width    INTEGER NOT NULL,
    height   INTEGER NOT NULL
);

-- Sky interior tiles
CREATE TABLE IF NOT EXISTS sky_tiles (
    sky_id   INTEGER NOT NULL REFERENCES sky_biomes(sky_id),
    local_x  INTEGER NOT NULL,
    local_y  INTEGER NOT NULL,
    tile_type TEXT   NOT NULL,
    PRIMARY KEY (sky_id, local_x, local_y)
);

-- Sky portals linking overworld mountain tiles to sky biomes
CREATE TABLE IF NOT EXISTS sky_portals (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    world_x  INTEGER NOT NULL,
    world_y  INTEGER NOT NULL,
    sky_id   INTEGER NOT NULL REFERENCES sky_biomes(sky_id),
    UNIQUE(world_x, world_y)
);

-- Sky chest loot state (tracks whether a chest has been opened/looted)
CREATE TABLE IF NOT EXISTS sky_chest_state (
    sky_id   INTEGER NOT NULL,
    local_x  INTEGER NOT NULL,
    local_y  INTEGER NOT NULL,
    looted   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (sky_id, local_x, local_y)
);

-- Player sky biome state columns (added via ALTER TABLE for existing DBs)
-- These ALTER TABLE statements are no-ops if columns already exist (SQLite limitation:
-- we catch errors in the migration code instead).

CREATE INDEX IF NOT EXISTS idx_sky_tiles_biome ON sky_tiles(sky_id, local_x, local_y);
CREATE INDEX IF NOT EXISTS idx_sky_portals_pos ON sky_portals(world_x, world_y);

-- Forest interior areas
CREATE TABLE IF NOT EXISTS forest_areas (
    forest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    width     INTEGER NOT NULL,
    height    INTEGER NOT NULL
);

-- Forest interior tiles
CREATE TABLE IF NOT EXISTS forest_tiles (
    forest_id INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (forest_id, local_x, local_y)
);

-- Forest entrances: overworld tile → forest interior entry point
CREATE TABLE IF NOT EXISTS forest_entrances (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    forest_id INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    world_x   INTEGER NOT NULL,
    world_y   INTEGER NOT NULL,
    UNIQUE(world_x, world_y)
);

-- Maze areas (connected to a forest)
CREATE TABLE IF NOT EXISTS maze_areas (
    maze_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    forest_id INTEGER NOT NULL,
    width     INTEGER NOT NULL,
    height    INTEGER NOT NULL
);

-- Maze interior tiles
CREATE TABLE IF NOT EXISTS maze_tiles (
    maze_id   INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (maze_id, local_x, local_y)
);

-- Per-player loot state for forest/maze chests
CREATE TABLE IF NOT EXISTS player_maze_loots (
    user_id  INTEGER NOT NULL,
    maze_id  INTEGER NOT NULL,
    PRIMARY KEY (user_id, maze_id)
);

CREATE TABLE IF NOT EXISTS player_forest_loots (
    user_id   INTEGER NOT NULL,
    forest_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, forest_id)
);

CREATE TABLE IF NOT EXISTS player_forest_chest_loots (
    user_id   INTEGER NOT NULL,
    forest_id INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    PRIMARY KEY (user_id, forest_id, local_x, local_y)
);

CREATE INDEX IF NOT EXISTS idx_forest_entrances_pos ON forest_entrances(world_x, world_y);
CREATE INDEX IF NOT EXISTS idx_forest_tiles_area ON forest_tiles(forest_id, local_x, local_y);
CREATE INDEX IF NOT EXISTS idx_maze_tiles_area ON maze_tiles(maze_id, local_x, local_y);

CREATE TABLE IF NOT EXISTS tree_city_tiles (
    forest_id INTEGER NOT NULL,
    floor_num INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (forest_id, floor_num, local_x, local_y)
);

CREATE TABLE IF NOT EXISTS grove_areas (
    grove_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    forest_id INTEGER NOT NULL,
    width     INTEGER NOT NULL DEFAULT 19,
    height    INTEGER NOT NULL DEFAULT 19
);

CREATE TABLE IF NOT EXISTS grove_tiles (
    grove_id  INTEGER NOT NULL,
    local_x   INTEGER NOT NULL,
    local_y   INTEGER NOT NULL,
    tile_type TEXT    NOT NULL,
    PRIMARY KEY (grove_id, local_x, local_y)
);

CREATE INDEX IF NOT EXISTS idx_grove_tiles ON grove_tiles(grove_id, local_x, local_y);

-- Warp crystal waypoints unlocked per player
CREATE TABLE IF NOT EXISTS player_waypoints (
    user_id     INTEGER NOT NULL,
    waypoint_id TEXT    NOT NULL,
    PRIMARY KEY (user_id, waypoint_id)
);

-- Bandit camp tiles (placed by world generator, 24h respawn cycle)
CREATE TABLE IF NOT EXISTS bandit_camps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    world_x      INTEGER NOT NULL,
    world_y      INTEGER NOT NULL,
    max_bandits  INTEGER NOT NULL DEFAULT 4,
    bandit_kills INTEGER NOT NULL DEFAULT 0,
    cleared_at   INTEGER,
    UNIQUE(world_x, world_y)
);
