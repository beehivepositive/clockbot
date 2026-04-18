CHUNK_SIZE = 7
WORLD_CHUNKS = 32
WORLD_SIZE = CHUNK_SIZE * WORLD_CHUNKS  # 224

VIEWPORT_SIZE = 9
VIEWPORT_CENTER = 4  # 0-indexed center of 9x9 grid

SPAWN_X = WORLD_SIZE // 2  # 112
SPAWN_Y = WORLD_SIZE // 2

# Noise generation defaults
NOISE_OCTAVES = 4
NOISE_LACUNARITY = 2.0
NOISE_GAIN = 0.5
NOISE_BASE_SCALE = 16.0

# --- Emoji Maps ---

TERRAIN_EMOJI = {
    "deep_water": "\U0001F30A",      # 🌊
    "shallow_water": "\U0001F4A7",   # 💧
    "river": "\U0001F30A",           # 🌊
    "sand": "\U0001F3D6\uFE0F",     # 🏖️
    "plains": "\U0001F33E",          # 🌾
    "grass": "\U0001F33F",           # 🌿
    "forest": "\U0001F332",          # 🌲
    "dense_forest": "\U0001F333",    # 🌳
    "hills": "\u26F0\uFE0F",        # ⛰️
    "mountain": "\U0001F3D4\uFE0F", # 🏔️
    "snow": "\u2744\uFE0F",         # ❄️
    "path": "\U0001F7EB",           # 🟫
    "void": "\u2B1B",               # ⬛ (out-of-bounds border)
}

STRUCTURE_EMOJI = {
    "village": "\U0001F3D8\uFE0F",  # 🏘️
    "ruins": "\U0001F3DA\uFE0F",    # 🏚️
    "shrine": "\u26E9\uFE0F",       # ⛩️
    "campfire": "\U0001F525",        # 🔥
    "cave": "\U0001F573\uFE0F",     # 🕳️
    "bridge": "\U0001F309",          # 🌉
}

ENTITY_EMOJI = {
    "player": "\U0001F9D9",          # 🧙
    "wolf": "\U0001F43A",            # 🐺
    "bear": "\U0001F43B",            # 🐻
    "spider": "\U0001F577\uFE0F",   # 🕷️
    "npc": "\U0001F9D1",             # 🧑
}

ITEM_EMOJI = {
    "wood": "\U0001FAB5",            # 🪵
    "stone": "\U0001FAA8",           # 🪨
    "gem": "\U0001F48E",             # 💎
    "sword": "\U0001F5E1\uFE0F",    # 🗡️
    "shield": "\U0001F6E1\uFE0F",   # 🛡️
    "potion": "\U0001F9EA",          # 🧪
    "key": "\U0001F511",             # 🔑
    "fish": "\U0001F41F",            # 🐟
    "map_fragment": "\U0001F5FA\uFE0F",  # 🗺️
}

WALKABLE_TILES = {
    "sand", "plains", "grass", "forest", "hills", "snow", "path",
    "village", "ruins", "shrine", "campfire", "cave", "bridge",
}

# Tile types that come from STRUCTURE_EMOJI (drawn as structures, not terrain)
STRUCTURE_TILES = {"village", "ruins", "shrine", "campfire", "cave", "bridge"}

# Direction vectors: (dx, dy)
DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

# Enemy definitions: {type: (hp, attack, defense, xp_reward, gold_reward)}
ENEMY_STATS = {
    "wolf": (20, 5, 2, 10, 5),
    "bear": (40, 10, 5, 25, 15),
    "spider": (15, 8, 1, 15, 8),
}

# Player defaults
PLAYER_START_HP = 100
PLAYER_START_ATTACK = 10
PLAYER_START_DEFENSE = 5

# --- Cave System ---

CAVE_EMOJI = {
    "stone_floor": "\U0001F7EB",            # 🟫
    "stone_wall": "\u2B1B",                  # ⬛
    "cave_entrance": "\U0001F573\uFE0F",    # 🕳️
    "cave_chest": "\U0001F4E6",             # 📦
}

CAVE_WALKABLE = {"stone_floor", "cave_entrance", "cave_chest"}

# --- Village System ---

VILLAGE_EMOJI = {
    "vil_grass":  "\U0001F33F",            # 🌿
    "vil_path":   "\U0001F7EB",            # 🟫
    "vil_wall":   "\U0001F9F1",            # 🧱
    "vil_door":   "\U0001F6AA",            # 🚪
    "vil_well":   "\u26F2",               # ⛲
    "vil_garden": "\U0001F33B",            # 🌻
}

HOUSE_EMOJI = {
    "house_floor": "\U0001F7EB",           # 🟫
    "house_wall":  "\U0001F9F1",           # 🧱
    "house_door":  "\U0001F6AA",           # 🚪
    "house_bed":   "\U0001F6CF\uFE0F",    # 🛏️
    "house_table": "\U0001FAB5",           # 🪵
    "house_chair": "\U0001FA91",           # 🪑
    "house_stove": "\U0001F525",           # 🔥
}

VILLAGE_WALKABLE = {"vil_grass", "vil_path", "vil_door", "vil_garden"}
HOUSE_WALKABLE = {"house_floor", "house_door"}

VILLAGE_MIN_SIZE = 32
VILLAGE_MAX_SIZE = 48

# Chest loot tiers: (weight, gold_min, gold_max, xp_min, xp_max, item_or_none)
CHEST_LOOT = [
    (50, 10,  40,  5,  20, None),
    (30, 30,  80,  15, 40, "potion"),
    (15, 60,  130, 30, 60, "gem"),
    (5,  100, 250, 50, 100, "sword"),
]

CAVE_MIN_SIZE = 40
CAVE_MAX_SIZE = 80
CAVE_WALK_STEPS = 350

# --- World Map Image ---

MAP_PIXEL_SCALE = 3  # Each tile = 3x3 pixels → 672x672 image

TILE_COLORS = {
    "deep_water": (20, 50, 120),
    "shallow_water": (60, 100, 180),
    "sand": (210, 190, 130),
    "plains": (160, 190, 80),
    "grass": (80, 160, 60),
    "forest": (30, 120, 30),
    "dense_forest": (10, 80, 20),
    "hills": (140, 130, 100),
    "mountain": (100, 100, 100),
    "snow": (240, 240, 255),
    "path": (139, 90, 43),
    "village": (200, 160, 60),
    "ruins": (120, 100, 80),
    "shrine": (200, 50, 50),
    "campfire": (255, 100, 0),
    "cave": (60, 40, 30),
    "river": (30, 80, 180),
    "bridge": (160, 120, 60),
}
