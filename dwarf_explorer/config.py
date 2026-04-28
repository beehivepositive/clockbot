CHUNK_SIZE = 7
WORLD_CHUNKS = 64
WORLD_SIZE = CHUNK_SIZE * WORLD_CHUNKS  # 448

VIEWPORT_SIZE = 9
VIEWPORT_CENTER = 4  # 0-indexed center of 9x9 grid


SPAWN_X = WORLD_SIZE // 2  # 112
SPAWN_Y = WORLD_SIZE // 2

# Fixed world seed — all servers share the same world layout
WORLD_SEED = 902599462

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
    "sand": "\U0001F3D6\uFE0F",     # 🏖️  (overridable with :sand:)
    "plains": "\U0001F33E",          # 🌾  (overridable with :dry_grass:)
    "grass": "\U0001F33F",           # 🌿  (overridable with :grass:)
    "forest": "\U0001F332",          # 🌲
    "dense_forest": "\U0001F333",    # 🌳
    "hills": "\u26F0\uFE0F",        # ⛰️
    "mountain": "\U0001F3D4\uFE0F", # 🏔️
    "snow": "\u2744\uFE0F\U0001F3D4\uFE0F",  # ❄️🏔️ snowy mountains — impassable
    "path": "\U0001F7EB",           # 🟫
    "void": "\u2B1B",               # ⬛
    "river_landing": "\u26F5",      # ⛵ canoe launch point
    "farmland":     "\U0001F7E4",    # 🟤 bare soil
    "crop_planted": "\U0001F331",    # 🌱 seedling
    "crop_sprout":  "\U0001F33F",    # 🌿 herb
    "crop_ripe":    "\U0001F33B",    # 🌻 sunflower
    # Player-modifiable terrain
    "sapling":     "\U0001F331",    # 🌱
    "short_grass": "\U0001F7E9",    # 🟩
    "seedling":    "\U0001FAB4",    # 🪴
}

STRUCTURE_EMOJI = {
    "village": "\U0001F3D8\uFE0F",  # 🏘️
    "ruins": "\U0001F3DA\uFE0F",    # 🏚️
    "ruins_looted": "\U0001F3DA\uFE0F",  # 🏚️ (already looted)
    "shrine": "\u26E9\uFE0F",       # ⛩️
    "cave": "\U0001F573\uFE0F",     # 🕳️
    "bridge": "\U0001F309",          # 🌉
    "player_house": "\U0001F3E0",   # 🏠
    "harbor": "\U0001F6A2",         # 🚢 harbor/dock
    "shipwreck": "\u2693",          # ⚓ shipwreck
    "island": "\U0001F3DD\uFE0F",  # 🏝️ high-seas island
}

ENTITY_EMOJI = {
    "player":      "\U0001F9D9",     # 🧙
    "player_boat": "\u26F5",         # ⛵  shown when player is in boat on ocean
    "wolf": "\U0001F43A",            # 🐺
    "bear": "\U0001F43B",            # 🐻
    "spider": "\U0001F577\uFE0F",   # 🕷️
    "npc": "\U0001F9D1",             # 🧑
    # Ocean creatures
    "shark": "\U0001F988",           # 🦈
    "crab": "\U0001F980",            # 🦀
    "sea_serpent": "\U0001F40D",     # 🐍
}

ITEM_EMOJI = {
    "wood": "\U0001FAB5",            # 🪵
    "stone": "\U0001FAA8",           # 🪨
    "gem": "\U0001F48E",             # 💎
    "sword": "\U0001F5E1\uFE0F",    # 🗡️
    "shield": "\U0001F6E1\uFE0F",   # 🛡️
    "key": "\U0001F511",             # 🔑
    "fish": "\U0001F41F",            # 🐟
    "map_fragment": "\U0001F5FA\uFE0F",  # 🗺️
    "knife": "\U0001F5E1\uFE0F",    # 🗡️
    "hiking_boots": "\U0001F97E",    # 🥾
    "torch": "\U0001F526",           # 🔦
    "axe": "\U0001FA93",             # 🪓
    "shovel": "\u26CF\uFE0F",       # ⛏️
    "watering_can": "\U0001FAA3",    # 🪣
    "pickaxe": "\u26CF\uFE0F",      # ⛏️
    "log": "\U0001FAB5",             # 🪵
    "stick": "\U0001F38B",           # 🎋
    "resin": "\U0001F7E1",           # 🟡
    "plant_fiber": "\U0001F9F5",     # 🧵
    "dry_grass": "\U0001F33E",       # 🌾
    "seed": "\U0001F330",            # 🌰
    "sapling": "\U0001F331",         # 🌱
    "flint": "\U0001FAA8",           # 🪨
    "iron_ore": "\U0001F7EB",        # 🟫
    "iron_ingot": "\U0001F9F1",      # 🧱
    "slingshot": "\U0001FA83",       # 🪃
    "rock": "\U0001FAA8",            # 🪨
    "poison_sac": "\U0001F9EA",      # 🧪 (green tint in mind)
    "small_pouch": "\U0001F45C",     # 👜
    "medium_pouch": "\U0001F45C",    # 👜
    "large_pouch": "\U0001F45C",     # 👜
    "fishing_net": "\U0001F3A3",     # 🎣
    "fishing_rod": "\U0001F3A3",     # 🎣
    "cooked_fish": "\U0001F956",     # 🍖
    "treasure_map": "\U0001F4DC",    # 📜
    "dagger":      "\U0001F5E1\uFE0F", # 🗡️
    "iron_helmet":     "\U0001FA96",    # 🪖
    "iron_chestplate": "\U0001F6E1\uFE0F",  # 🛡️
    "iron_leggings":   "\U0001F455",    # 👕 (closest available)
    "seaweed":         "\U0001F33F",    # 🌿
}

WALKABLE_TILES = {
    "sand", "plains", "grass", "forest", "hills", "path",
    "village", "ruins", "ruins_looted", "shrine", "cave", "bridge",
    "sapling", "short_grass", "seedling",
    "river_landing",
    "farmland", "crop_planted", "crop_sprout", "crop_ripe",
    "player_house",  # player-built house — walkable (enter on interact)
    "harbor",        # harbor dock — walkable
    # NOTE: "snow" and "mountain" are intentionally absent — impassable
}

# Tile types passable by canoe (water + bridges)
CANOE_PASSABLE = {"river", "bridge", "shallow_water", "deep_water"}

# Tile types navigable by boat on the wilderness ocean
OCEAN_WALKABLE = {"deep_water", "shallow_water", "harbor"}

# Tile types that come from STRUCTURE_EMOJI (drawn as structures, not terrain)
STRUCTURE_TILES = {"village", "ruins", "ruins_looted", "shrine", "cave", "bridge", "player_house", "harbor", "shipwreck", "island"}

# Direction vectors: (dx, dy)
DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

# Enemy definitions: {type: (hp, attack, defense, xp_reward, gold_reward)}
ENEMY_STATS = {
    "wolf":        (20,  8,  1, 10,  5),
    "bear":        (40, 16,  3, 25, 15),
    "spider":      (15, 12,  1, 15,  8),
    "cave_bat":    (12,  8,  0,  5,  3),
    "cave_spider": (25, 14,  2, 15,  8),
    "cave_golem":  (70, 22,  8, 50, 25),
    "cave_troll":  (50, 18,  5, 35, 20),
    "cave_wyvern": (80, 28,  6, 75, 40),
    # Ocean creatures
    "shark":       (35, 15,  1, 20, 12),
    "crab":        (20,  8,  4, 12,  8),
    "sea_serpent": (60, 22,  4, 50, 30),
}

# Player defaults
PLAYER_START_HP = 100
PLAYER_START_ATTACK = 10
PLAYER_START_DEFENSE = 5

# --- Combat System ---

COMBAT_MOVES_DEFAULT = 3

# Special abilities per enemy type
ENEMY_ABILITIES = {
    "wolf":        {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": False},
    "bear":        {"cobweb": False, "poison": False, "hit_run": False, "roar": True,  "slam": False},
    "spider":      {"cobweb": True,  "poison": False, "hit_run": False, "roar": False, "slam": False},
    "cave_bat":    {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
    "cave_spider": {"cobweb": True,  "poison": True,  "hit_run": False, "roar": False, "slam": False},
    "cave_golem":  {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": True},
    "cave_troll":  {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": True},
    "cave_wyvern": {"cobweb": False, "poison": True,  "hit_run": True,  "roar": False, "slam": False},
    # Ocean creatures
    "shark":       {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
    "crab":        {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": False},
    "sea_serpent": {"cobweb": False, "poison": True,  "hit_run": False, "roar": False, "slam": True},
}

ARENA_EMOJI = {
    "cobweb": "\U0001F578\uFE0F",   # 🕸️
}

FOOD_HP_RESTORE = {"fish": 15, "cooked_fish": 35}

# Player-built house: materials needed to construct one
HOUSE_BUILD_COST = {"log": 8, "rock": 4}

# Interior decoration catalog: id → {name, cost dict, tile placed}
HOUSE_DECORATION_CATALOG = [
    {"id": "b_table",          "name": "Table",        "cost": {"log": 2}},
    {"id": "b_chair",          "name": "Chair",        "cost": {"log": 1}},
    {"id": "b_bed",            "name": "Bed",          "cost": {"log": 3}},
    {"id": "b_stove",          "name": "Hearth",       "cost": {"rock": 3}},
    {"id": "b_bookshelf",      "name": "Bookshelf",    "cost": {"log": 2}},
    {"id": "b_candle",         "name": "Candle",       "cost": {"torch": 1}},
    {"id": "ph_chest_small",   "name": "Small Chest",  "cost": {"log": 2}},
    {"id": "ph_chest_medium",  "name": "Medium Chest", "cost": {"log": 4}},
    {"id": "ph_chest_large",   "name": "Large Chest",  "cost": {"log": 6}},
]

# Tiles that count as movable decorations (can be placed/removed by owner)
PLAYER_HOUSE_DECO_TILES = {d["id"] for d in HOUSE_DECORATION_CATALOG}

# Player-house chest tile types
PH_CHEST_TYPES = {"ph_chest_small", "ph_chest_medium", "ph_chest_large"}

# Crafting recipes: frozenset of (item_id, qty) tuples → result
# Selections must match EXACTLY — no extra items, no other quantities
CRAFT_RECIPES: dict[frozenset, dict] = {
    frozenset({("stick", 1), ("resin", 1)}):           {"result": "torch",         "qty": 1, "label": "🔦 Craft Torch"},
    frozenset({("log", 8), ("rock", 4)}):               {"result": "house_kit",     "qty": 1, "label": "🏠 Craft House Kit"},
}

# Terrain that blocks movement inside the combat arena
ARENA_IMPASSABLE = {
    "mountain", "snow", "dense_forest",
    "stone_wall", "b_wall", "void", "cave_rock",
    "river",
    # Note: deep_water and shallow_water are passable for ocean combat
}

# Ocean world size
OCEAN_SIZE = 200

# Ocean random encounter rates (relative weights, 7% total gate in _roll_encounter)
OCEAN_ENCOUNTER_RATES = {
    "shark":       0.05,
    "crab":        0.03,
    "sea_serpent": 0.02,
}

# --- Cave System ---

CAVE_EMOJI = {
    "stone_floor":        "\U0001F7EB",            # 🟫  (overridable with :grey_square:)
    "stone_wall":         "\u2B1B",                # ⬛
    "cave_entrance":      "\U0001F573\uFE0F",      # 🕳️
    "cave_chest":         "\U0001F4E6",            # 📦 small chest (overridable with :chest:)
    "cave_chest_medium":  "\U0001F4E6",            # 📦 medium chest
    "cave_chest_large":   "\U0001F381",            # 🎁 large chest
    "cave_rock":          "\U0001FAA8",            # 🪨
    "cave_bat":           "\U0001F987",            # 🦇
    "cave_spider":        "\U0001F577\uFE0F",      # 🕷️
    "cave_golem":         "\U0001F5FF",            # 🗿 (moai — rock golem)
    "cave_troll":         "\U0001F479",            # 👹 troll
    "cave_wyvern":        "\U0001F409",            # 🐉 wyvern/dragon
    "cave_stairdown":     "\U0001F53D",            # 🔽 descend deeper
    "cave_stairup":       "\U0001F53C",            # 🔼 ascend
    "player_house_cave":  "\U0001F3E0",            # 🏠 player-built house in cave
}

CAVE_WALKABLE = {"stone_floor", "cave_entrance", "cave_chest", "cave_chest_medium", "cave_chest_large", "cave_stairdown", "cave_stairup", "player_house_cave"}
# cave_rock blocks movement; cave_bat/cave_spider/cave_golem are no longer placed as tiles

CAVE_CHEST_TYPES = {"cave_chest", "cave_chest_medium", "cave_chest_large"}

CAVE_ENEMY_TYPES = {"cave_bat", "cave_spider", "cave_golem", "cave_troll", "cave_wyvern"}

# Chest loot tiers: (weight, gold_min, gold_max, xp_min, xp_max, item_or_none)
CHEST_LOOT = [
    (50, 10,  40,  5,  20, None),
    (30, 30,  80,  15, 40, "cooked_fish"),
    (15, 60,  130, 30, 60, "gem"),
    (5,  100, 250, 50, 100, "sword"),
]

CAVE_MIN_SIZE = 60
CAVE_MAX_SIZE = 120
CAVE_WALK_STEPS = 500

# --- Village System ---

VILLAGE_EMOJI = {
    "vil_grass":        "\U0001F33F",        # 🌿  (overridable with :grass:)
    "vil_path":         "\U0001F7EB",        # 🟫
    "vil_well":         "\u26F2",            # ⛲
    "vil_garden":       "\U0001F33B",        # 🌻
    "vil_tree":         "\U0001F332",        # 🌲
    "vil_house":        "\U0001F3E0",        # 🏠
    "vil_church":       "\u26EA",            # ⛪
    "vil_bank":         "\U0001F3E6",        # 🏦
    "vil_shop":         "\U0001F3EA",        # 🏪
    "vil_blacksmith":   "\u2692\uFE0F",      # ⚒️
    # Harbor-village specific tiles
    "vil_water":        "\U0001F30A",        # 🌊  ocean water at village edge
    "vil_dock":         "\u2693",            # ⚓  dock / boarding point
}

# All building interior tiles use BUILDING_EMOJI
BUILDING_EMOJI = {
    # Shared floor/wall/door
    "b_floor":            "\U0001F7EB",       # 🟫  (overridable with :grey_square:)
    "b_floor_wood":       "\U0001F7EB",       # 🟫  (overridable with :wood_floor:) — house/shop/bank/church
    "b_wall":             "\u2B1B",           # ⬛
    "b_door":             "\U0001F6AA",       # 🚪
    # House furniture
    "b_bed":              "\U0001F6CF\uFE0F", # 🛏️
    "b_table":            "\U0001FAB5",       # 🪵  (overridable with :table:)
    "b_chair":            "\U0001FA91",       # 🪑
    "b_stove":            "\U0001F525",       # 🔥  (overridable with :hearth:)
    "b_bookshelf":        "\U0001F4DA",       # 📚
    # Church unique
    "b_pew":              "\U0001FA91",       # 🪑
    "b_altar":            "\u26E9\uFE0F",    # ⛩️
    "b_candle":           "\U0001F56F\uFE0F",# 🕯️
    "b_priest":           "\U0001F9D9",       # 🧙
    # Bank unique
    "b_counter":          "\U0001F7E6",       # 🟦
    "b_bank_npc":         "\U0001F9D1",       # 🧑
    "b_safe":             "\U0001F512",       # 🔒
    # Shop unique
    "b_shelf":            "\U0001F4E6",       # 📦  (overridable with :chest:)
    "b_shop_npc":         "\U0001F9D1",       # 🧑
    "b_shop_counter":     "\U0001F7E6",       # 🟦
    # Blacksmith unique
    "b_anvil":            "\U0001F528",       # 🔨
    "b_blacksmith_npc":   "\U0001F9D1",       # 🧑
    "b_forge":            "\U0001F525",       # 🔥
    # Player-house chests
    "ph_chest_small":     "\U0001F4E6",       # 📦
    "ph_chest_medium":    "\U0001F5C4\uFE0F", # 🗄️
    "ph_chest_large":     "\U0001F9F3",       # 🧳
}

VILLAGE_WALKABLE = {
    "vil_grass", "vil_path", "vil_garden",
    "vil_house", "vil_church", "vil_bank", "vil_shop", "vil_blacksmith",
    "vil_dock",  # harbor-village boarding point — walkable, triggers ocean
    # Note: "vil_water" is intentionally absent — impassable harbour water
}

BUILDING_WALKABLE = {
    "b_floor", "b_floor_wood", "b_door",
    "b_priest", "b_bank_npc", "b_shop_npc", "b_blacksmith_npc",
    "b_pew", "b_table", "b_stove", "b_bed",
    "b_anvil", "b_chair", "b_bookshelf", "b_candle",
    "ph_chest_small", "ph_chest_medium", "ph_chest_large",
}

VILLAGE_MIN_SIZE = 16
VILLAGE_MAX_SIZE = 16

# --- Items & Equipment ---

SHOP_CATALOG = [
    {
        "id": "knife",
        "name": "Knife",
        "emoji": "\U0001F5E1\uFE0F",
        "price": 25,
        "equip_slot": "hand",
        "description": "A sharp blade. +5 attack. Cut grass & plains.",
    },
    {
        "id": "hiking_boots",
        "name": "Hiking Boots",
        "emoji": "\U0001F97E",
        "price": 50,
        "equip_slot": "boots",
        "description": "Sturdy boots. Enables sprinting.",
    },
    {
        "id": "axe",
        "name": "Axe",
        "emoji": "\U0001FA93",
        "price": 40,
        "equip_slot": "hand",
        "description": "Two-handed. Chop down forest tiles. Yields log + drops.",
    },
    {
        "id": "shovel",
        "name": "Shovel",
        "emoji": "\u26CF\uFE0F",
        "price": 60,
        "equip_slot": "hand",
        "description": "Two-handed. Dig up saplings from the ground.",
    },
    {
        "id": "watering_can",
        "name": "Watering Can",
        "emoji": "\U0001FAA3",
        "price": 35,
        "equip_slot": "hand",
        "description": "Water saplings, seedlings & short grass to grow.",
    },
    {
        "id": "pickaxe",
        "name": "Pickaxe",
        "emoji": "\u26CF\uFE0F",
        "price": 55,
        "equip_slot": "hand",
        "description": "Mine cave rocks: yields 1-3 rocks, 33% flint, 15% iron ore.",
    },
    {
        "id": "slingshot",
        "name": "Slingshot",
        "emoji": "\U0001FA83",
        "price": 45,
        "equip_slot": "hand",
        "description": "Ranged weapon. Uses 1 rock per attack. Mine rocks in caves.",
    },
    {
        "id": "fishing_rod",
        "name": "Fishing Rod",
        "emoji": "\U0001F3A3",
        "price": 30,
        "equip_slot": "hand",
        "description": "Fish at riverbanks. Equip and Interact near water to cast.",
    },
    {
        "id": "small_pouch",
        "name": "Small Pouch",
        "emoji": "\U0001F45C",
        "price": 80,
        "equip_slot": "pouch",
        "description": "Expands inventory to 2×9 (18 slots).",
    },
    {
        "id": "medium_pouch",
        "name": "Medium Pouch",
        "emoji": "\U0001F45C",
        "price": 180,
        "equip_slot": "pouch",
        "description": "Expands inventory to 3×9 (27 slots).",
    },
    {
        "id": "large_pouch",
        "name": "Large Pouch",
        "emoji": "\U0001F45C",
        "price": 350,
        "equip_slot": "pouch",
        "description": "Expands inventory to 4×9 (36 slots).",
    },
]

# Equipment slots
EQUIP_SLOTS = {"hand_1", "hand_2", "head", "chest", "legs", "boots", "accessory", "pouch"}

# Maps item_id → equipment slot type ("hand" resolves to hand_1 or hand_2 at equip time)
ITEM_EQUIP_SLOTS = {
    "knife":        "hand",
    "axe":          "hand",
    "torch":        "hand",
    "watering_can": "hand",
    "seed":         "hand",
    "sapling":      "hand",
    "shovel":       "hand",
    "pickaxe":      "hand",
    "slingshot":    "hand",
    "fishing_rod":  "hand",
    "dagger":       "hand",
    "iron_helmet":     "head",
    "iron_chestplate": "chest",
    "iron_leggings":   "legs",
    "sword":        "hand",
    "hiking_boots": "boots",
    "small_pouch":  "pouch",
    "medium_pouch": "pouch",
    "large_pouch":  "pouch",
    "house_kit":    "hand",
}

# Items that occupy both hand slots
TWO_HANDED_ITEMS = {"shovel"}

# Equipment stat bonuses: {item_id: {stat: bonus}}
EQUIP_BONUSES = {
    "knife":        {"attack": 5},
    "axe":          {"attack": 3},
    "pickaxe":      {"attack": 4},
    "slingshot":    {"attack": 4},
    "hiking_boots": {},
    "torch":        {},
    "shovel":       {},
    "watering_can": {},
    "seed":         {},
    "sapling":      {},
    "small_pouch":  {},
    "medium_pouch": {},
    "large_pouch":  {},
    "fishing_rod":  {},
    "dagger":       {"attack": 8},
    "iron_helmet":     {"defense": 3},
    "iron_chestplate": {"defense": 5},
    "iron_leggings":   {"defense": 4},
    "sword":        {"attack": 12},
}

# Pouch inventory sizes: (rows, cols) — default 2×5 when no pouch equipped
POUCH_SIZES: dict[str | None, tuple[int, int]] = {
    None:           (2, 5),
    "small_pouch":  (2, 9),
    "medium_pouch": (3, 9),
    "large_pouch":  (4, 9),
}

# Cave random encounter rates per step: {enemy_type: chance 0-1}
CAVE_ENCOUNTER_RATES = {
    "cave_bat":    0.07,
    "cave_spider": 0.07,
    "cave_golem":  0.04,
}

# Per-level cave encounter rates: {level: {enemy_type: chance}}
CAVE_LEVEL_ENCOUNTER_RATES = {
    1: {"cave_bat": 0.07, "cave_spider": 0.07},
    2: {"cave_spider": 0.05, "cave_golem": 0.06, "cave_troll": 0.05},
    3: {"cave_golem": 0.05, "cave_troll": 0.06, "cave_wyvern": 0.05},
}

# Surface encounters: terrain → enemy_type (1% chance per step, short_grass excluded)
SURFACE_ENCOUNTER_MOBS = {
    "plains":       "wolf",
    "grass":        "wolf",
    "sand":         "wolf",
    "hills":        "bear",
    "forest":       "wolf",
    "dense_forest": "bear",
}

# Sell prices at the shop (60% of buy price for shop items)
ITEM_SELL_PRICES = {
    "knife":        15,
    "hiking_boots": 30,
    "axe":          24,
    "shovel":       36,
    "watering_can": 21,
    "pickaxe":      33,
    "gem":          30,
    "sword":        50,
    "log":          5,
    "stick":        2,
    "resin":        8,
    "plant_fiber":  3,
    "dry_grass":    2,
    "seed":         1,
    "sapling":      4,
    "fish":         8,
    "wood":         5,
    "stone":        3,
    "key":          20,
    "map_fragment": 25,
    "flint":        6,
    "iron_ore":     12,
    "iron_ingot":   25,
    "slingshot":    27,
    "fishing_rod":  18,
    "fish":         5,
    "cooked_fish":  8,
    "treasure_map": 0,
    "rock":         2,
    "poison_sac":   20,
    "dagger":       30,
    "iron_helmet":     40,
    "iron_chestplate": 60,
    "iron_leggings":   50,
    "small_pouch":  48,
    "medium_pouch": 108,
    "large_pouch":  210,
}

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
    "snow": (220, 230, 255),
    "path": (139, 90, 43),
    "village": (200, 160, 60),
    "ruins": (120, 100, 80),
    "shrine": (200, 50, 50),
    "cave": (60, 40, 30),
    "river": (30, 80, 180),
    "bridge": (160, 120, 60),
    "river_landing": (200, 140, 60),
    "sapling": (100, 200, 80),
    "short_grass": (120, 200, 60),
    "seedling": (130, 210, 70),
    "farmland": (120, 80, 40),
    "crop_planted": (100, 140, 40),
    "crop_sprout": (60, 160, 40),
    "crop_ripe": (200, 180, 20),
    "harbor": (40, 80, 200),
    "ruins_looted": (100, 85, 70),
}


# --- Custom Emoji Resolution ---

def apply_custom_emojis(guild_emojis: list) -> None:
    cache = {e.name: f"<:{e.name}:{e.id}>" for e in guild_emojis}

    _replace = [
        (TERRAIN_EMOJI,  "sand",              "sand"),
        (TERRAIN_EMOJI,  "grass",             "grass"),
        (TERRAIN_EMOJI,  "plains",            "dry_grass"),
        (CAVE_EMOJI,     "cave_chest",        "chest"),
        (CAVE_EMOJI,     "cave_chest_medium", "chest"),
        (CAVE_EMOJI,     "cave_chest_large",  "chest"),
        (BUILDING_EMOJI, "ph_chest_small",    "chest"),
        (BUILDING_EMOJI, "ph_chest_medium",   "chest"),
        (BUILDING_EMOJI, "ph_chest_large",    "chest"),
        (CAVE_EMOJI,     "stone_floor",       "grey_square"),
        (BUILDING_EMOJI, "b_stove",           "hearth"),
        (BUILDING_EMOJI, "b_table",           "table"),
        (BUILDING_EMOJI, "b_floor",           "grey_square"),
        (BUILDING_EMOJI, "b_floor_wood",      "wood_floor"),
        (BUILDING_EMOJI, "b_shelf",           "chest"),
        (BUILDING_EMOJI, "b_forge",           "forge"),
        (VILLAGE_EMOJI,  "vil_grass",         "grass"),
    ]

    for d, tile_key, emoji_name in _replace:
        if emoji_name in cache:
            d[tile_key] = cache[emoji_name]

    # Item emoji overrides — update both ITEM_EMOJI (ground) and renderer's inventory dict
    _item_overrides = [
        ("shovel",       "shovel"),
        ("torch",        "torch"),
        ("fishing_net",  "net"),
        ("iron_ore",     "iron_ore"),
        ("fishing_rod",  "fishing_pole"),
        ("poison_sac",   "poison_sac"),
        ("cooked_fish",  "cooked_fish"),
        # Pouches — try specific names first, fallback to generic "pouch"
        ("small_pouch",  "small_pouch"),
        ("medium_pouch", "medium_pouch"),
        ("large_pouch",  "large_pouch"),
        ("small_pouch",  "pouch"),
        ("medium_pouch", "pouch"),
        ("large_pouch",  "pouch"),
    ]
    from dwarf_explorer.game import renderer as _renderer
    for item_key, emoji_name in _item_overrides:
        if emoji_name in cache:
            ITEM_EMOJI[item_key] = cache[emoji_name]
            _renderer._ITEM_SLOT_EMOJI[item_key] = cache[emoji_name]
