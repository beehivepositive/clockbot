CHUNK_SIZE = 7
WORLD_CHUNKS = 64
WORLD_SIZE = CHUNK_SIZE * WORLD_CHUNKS  # 448

VIEWPORT_SIZE = 9
VIEWPORT_CENTER = 4  # 0-indexed center of 9x9 grid


SPAWN_X = WORLD_SIZE // 2  # 112
SPAWN_Y = WORLD_SIZE // 2

# Admin account — persists across /newworld resets.
# ADMIN_PLAYER_ID is the DB user_id for the persistent admin character (never a
# real Discord snowflake).  ADMIN_DISCORD_ID is the Discord user who owns it.
ADMIN_PLAYER_ID  = 1
ADMIN_DISCORD_ID = 926541705279315988

# Fixed world seed — all servers share the same world layout
WORLD_SEED = 902599462

# Noise generation defaults
NOISE_OCTAVES = 4
NOISE_LACUNARITY = 2.0
NOISE_GAIN = 0.5
NOISE_BASE_SCALE = 16.0

# --- Emoji Maps ---

TERRAIN_EMOJI = {
    "drop_box":   "\U0001F4E6",      # 📦 dropped item box
    "deep_water": "\U0001F30A",      # 🌊
    "shallow_water": "\U0001F4A7",   # 💧
    "river": "\U0001F30A",           # 🌊
    "sand": "🟨",            # 🟨  (overridable with :sand:)
    "plains": "\U0001F33E",          # 🌾  (overridable with :dry_grass:)
    "grass": "\U0001F33F",           # 🌿  (overridable with :grass:)
    "forest": "\U0001F332",          # 🌲
    "dense_forest": "\U0001F333",    # 🌳
    "hills": "\u26F0\uFE0F",        # ⛰️
    "mountain": "\U0001F3D4\uFE0F", # 🏔️
    "snow": "❄️",           # snowy mountains — impassable
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
    "island": "\U0001F3DD️",  # 🏝️ high-seas island
    "volcano_island": "\U0001F30B",  # 🌋 volcano island
    "sundial": "\U0001F55B",        # 🕛 sundial ruins (rift portal)
    "sky_portal": "\U0001F300",    # 🌀 sky portal on mountain tile (legacy, no longer placed)
    "sky_temple_outer": "\U0001F3DB️",  # 🏛️ outer/puzzle temple (overworld)
    "sky_temple_main":  "\U0001F3F0",        # 🏰 main/portal temple (overworld)
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
    # Rift boss
    "temporal_echo": "\U0001F47B",   # 👻 ghostly temporal apparition
}

# ── Custom gear emoji IDs ──────────────────────────────────────────────────────
# Replace each 0 with the actual Discord emoji ID once uploaded to your server.
# Animated emojis use <a:name:id>; static emojis use <:name:id>.
# Leave as 0 to use the Unicode fallback (⚙️ / 🔩).
_GEAR_IDS: dict[str, int] = {
    "gear_small":                0,   # small gear CW (animated)
    "gear_small_reverse":        0,   # small gear CCW (animated)
    "gear_small_still":          0,   # small gear static (item icon)
    "gear_top_left":             0,   # large gear top-left CW
    "gear_top_right":            0,   # large gear top-right CW
    "gear_bottom_left":          0,   # large gear bottom-left CW
    "gear_bottom_right":         0,   # large gear bottom-right CW
    "gear_top_left_reverse":     0,   # large gear top-left CCW
    "gear_top_right_reverse":    0,   # large gear top-right CCW
    "gear_bottom_left_reverse":  0,   # large gear bottom-left CCW
    "gear_bottom_right_reverse": 0,   # large gear bottom-right CCW
}


def _ge(name: str, fallback: str = "⚙️") -> str:
    """Return Discord animated emoji string if an ID is set, else the fallback."""
    eid = _GEAR_IDS.get(name, 0)
    return f"<a:{name}:{eid}>" if eid else fallback


ITEM_EMOJI = {
    # Farming & crops
    "wheat_seed":  "\U0001F330",     # 🌰
    "carrot_seed": "\U0001F955",     # 🥕 (seed placeholder)
    "potato_seed": "\U0001F954",     # 🥔 (seed placeholder)
    "wheat":       "\U0001F33E",     # 🌾
    "carrot":      "\U0001F955",     # 🥕
    "potato":      "\U0001F954",     # 🥔
    "hoe":         "\U0001FAB0",     # 🪰  (overridable with :hoe:)
    "wood": "\U0001FAB5",            # 🪵
    "stone": "\U0001FAA8",           # 🪨
    "gem": "\U0001F48E",             # 💎
    "sword": "\U0001F5E1\uFE0F",    # 🗡️
    "shield": "\U0001F6E1\uFE0F",   # 🛡️
    "key": "\U0001F511",             # 🔑
    "fish": "\U0001F41F",            # 🐟
    "map_fragment": "\U0001F5FA\uFE0F",  # 🗺️
    "knife": "\U0001F5E1\uFE0F",    # 🗡️
    "hiking_boots":    "\U0001F97E",    # 🥾
    "climbing_boots":  "\U0001F9D7",    # 🧗 person climbing
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
    "iron_ingot": "\U0001F9F1",      # 🧱 (overridable with :iron_ingot:)
    "slingshot": "<:slingshot:1495973515722227822>",
    "rock": "\U0001FAA8",            # 🪨
    "poison_sac": "\U0001F9EA",      # 🧪 (green tint in mind)
    "small_pouch": "\U0001F45C",     # 👜
    "medium_pouch": "\U0001F45C",    # 👜
    "large_pouch": "\U0001F45C",     # 👜
    "small_coin_purse":  "\U0001F4B0",  # 💰
    "medium_coin_purse": "\U0001F4B0",  # 💰
    "large_coin_purse":  "\U0001F4B0",  # 💰
    "fishing_net": "\U0001F3A3",     # 🎣
    "fishing_rod": "\U0001F3A3",     # 🎣
    "cooked_fish": "\U0001F956",     # 🍖
    "treasure_map": "\U0001F4DC",    # 📜
    "dagger":      "\U0001F5E1\uFE0F", # 🗡️
    "iron_helmet":     "\U0001FA96",    # 🪖
    "iron_chestplate": "\U0001F455",    # 👕
    "iron_leggings":   "\U0001F456",    # 👖
    "seaweed":         "\U0001F33F",    # 🌿
    "cannonball":      "\U0001F4A3",    # 💣
    "gold_ore":             "\U0001F7E1",           # 🟡
    "gold_ingot":           "\U0001F947",           # 🥇
    "gold_ring":            "\U0001F48D",           # 💍
    "iron_boots":           "\U0001F97E",           # 🥾
    "ring_of_strength":     "\U0001F48D",           # 💍 (red glow in mind)
    "ring_of_time":         "\U0001F48D",           # 💍 (blue glow)
    "ring_of_defense":      "\U0001F48D",           # 💍 (grey glow)
    "ring_of_sight":        "\U0001F48D",           # 💍 (yellow glow)
    "ring_of_luck":         "\U0001F48D",           # 💍 (green glow)
    "enchanted_gem_strength": "\U0001F4AB",         # 💫
    "enchanted_gem_time":     "\U0001F4AB",         # 💫
    "enchanted_gem_defense":  "\U0001F4AB",         # 💫
    "enchanted_gem_sight":    "\U0001F4AB",         # 💫
    "enchanted_gem_luck":     "\U0001F4AB",         # 💫
    "flint_and_steel":      "\U0001F525",           # 🔥
    "arrow":                "\U0001F3F9",           # 🏹
    "star_fragment":        "⭐",               # ⭐
    "chronolite":           "\U0001F4A0",           # 💠 cyan diamond
    "wyvern_scale":         "\U0001F409",           # 🐉 dragon scale
    "wyvern_helmet":        "\U0001FA96",           # 🪖
    "wyvern_chestplate":    "\U0001F455",           # 👕
    "wyvern_leggings":      "\U0001F456",           # 👖
    "iron_shield":          "\U0001F6E1️",     # 🛡️
    "wyvern_shield":        "\U0001F6E1️",     # 🛡️
    "merchant_parcel":      "\U0001F4E6",           # 📦 delivery parcel
    # Tavern food & drink
    "bread":                "\U0001F35E",           # 🍞
    "ale":                  "\U0001F37A",           # 🍺
    "meat_stew":            "\U0001F372",           # 🍲
    # Hospital quest ingredient
    "healing_herb":         "\U0001F33F",           # 🌿
    "plank":            "🪵",       # 🪵  wooden plank
    "canoe":            "🛶",       # 🛶  canoe
    "hammer":           "🔨",       # 🔨  hammer (ship repair)
    "nail":             "📌",       # 📌  nail (ship repair)
    "breath_of_the_sea": "🫧",     # 🫧  breath of the sea (restores breath underwater)
    "gust_of_aevos":    "🌬️",     # 🌬️  rare ingredient for breath_of_the_sea
    "hawk_feather":     "🪶",       # 🪶  dropped by storm_hawk in sky biome
    "gold_coin":        "🪙",       # 🪙  loose gold coin (shipwreck loot)
    "small_gear": _ge("gear_small_still", "⚙️"),
    "large_gear": "🔩",
}

# Maps seed item_id → crop progression for village farmland
FARM_CROPS: dict[str, dict] = {
    "wheat_seed":  {
        "planted": "vil_seeds_wheat",  "mature": "vil_crop_wheat",
        "yield": "wheat",  "yield_qty": 2,  "emoji": "🌾",
    },
    "carrot_seed": {
        "planted": "vil_seeds_carrot", "mature": "vil_crop_carrot",
        "yield": "carrot", "yield_qty": 2,  "emoji": "🥕",
    },
    "potato_seed": {
        "planted": "vil_seeds_potato", "mature": "vil_crop_potato",
        "yield": "potato", "yield_qty": 2,  "emoji": "🥔",
    },
}

WALKABLE_TILES = {
    "sand", "plains", "grass", "forest", "hills", "path",
    "village", "ruins", "ruins_looted", "shrine", "cave", "bridge",
    "sapling", "short_grass", "seedling",
    "farmland", "crop_planted", "crop_sprout", "crop_ripe",
    "player_house",  # player-built house — walkable (enter on interact)
    "harbor",        # harbor dock — walkable
    "drop_box",      # item drop box — walkable, interact to pick up
    "sundial",       # sundial ruins — walkable (interact with star_fragment to open rift)
    "sky_portal",    # sky portal on mountain — walkable (legacy; kept for any existing portals)
    "sky_temple_outer",  # outer puzzle temple — walkable overworld tile
    "sky_temple_main",   # main portal temple — walkable overworld tile
    # NOTE: "snow" and "mountain" are intentionally absent — impassable
    # Shipwreck interior tiles (so TileData.walkable property works for sw_ tiles)
    "sw_floor", "sw_chest", "sw_entrance", "sw_debris",
}

# Tile types passable by canoe (water + bridges)
CANOE_PASSABLE = {"river", "bridge", "shallow_water", "deep_water"}

# Tile types navigable by boat on the wilderness ocean
OCEAN_WALKABLE = {"deep_water", "shallow_water", "harbor"}

# Tile types walkable on an island interior
ISLAND_WALKABLE = {"island_sand", "island_grass", "island_forest", "island_tree",
                   "island_chest", "island_dock", "island_sapling", "island_npc",
                   # Volcano island walkable tiles
                   "vol_sand", "vol_rock", "vol_grass", "vol_forest", "vol_lava_bridge",
                   "vol_cave", "vol_dock", "vol_outpost", "vol_chest"}

VOLCANO_ISLAND_SIZE = 100  # width/height of volcano island grid

# Tile types that come from STRUCTURE_EMOJI (drawn as structures, not terrain)
STRUCTURE_TILES = {"village", "ruins", "ruins_looted", "shrine", "cave", "bridge", "player_house", "harbor", "shipwreck", "island", "volcano_island", "sundial", "sky_portal", "sky_temple_outer", "sky_temple_main"}

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
    "cave_bat":    ( 8,  5,  0,  5,  3),   # weaker solo — can swarm 2-3
    "cave_spider": (25, 14,  2, 15,  8),
    "cave_golem":  (70, 22,  8, 50, 25),
    "cave_troll":  (50, 18,  5, 35, 20),
    "cave_wyvern": (80, 28,  6, 75, 40),
    # Lava cave enemies
    "cinder_imp":      (22, 13,  0, 20, 10),
    "lava_salamander": (18, 11,  1, 15,  8),
    "obsidian_golem":  (90, 28, 12, 60, 30),
    # Ocean creatures
    "shark":       (35, 15,  1, 20, 12),
    "crab":        (20,  8,  4, 12,  8),
    "sea_serpent": (60, 22,  4, 50, 30),
    # Rift boss
    "temporal_echo": (200, 25, 5, 150, 0),  # high HP, no gold — drops chronolite instead
    # Sky biome enemies
    "wind_wisp":  (25,  6, 1,  8, 5),
    "storm_hawk": (40,  9, 3, 15, 8),
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
    "cave_bat":        {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
    "cave_spider":     {"cobweb": True,  "poison": True,  "hit_run": False, "roar": False, "slam": False},
    "cave_golem":      {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": True},
    "cave_troll":      {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": True},
    "cave_wyvern":     {"cobweb": False, "poison": True,  "hit_run": True,  "roar": False, "slam": False},
    # Lava cave enemies
    "cinder_imp":      {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
    "lava_salamander": {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
    "obsidian_golem":  {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": True},
    # Ocean creatures
    "shark":       {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
    "crab":        {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": False},
    "sea_serpent": {"cobweb": False, "poison": True,  "hit_run": False, "roar": False, "slam": True},
    # Rift boss — custom AI, these flags are unused
    "temporal_echo": {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": False},
    # Sky biome enemies
    "wind_wisp":  {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
    "storm_hawk": {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False},
}

ARENA_EMOJI = {
    "cobweb": "\U0001F578\uFE0F",   # 🕸️
}

FOOD_HP_RESTORE = {"fish": 5, "cooked_fish": 15, "bread": 10, "meat_stew": 20}

# Consumable items: shown in combat food menu
CONSUMABLE_ITEMS = {
    "fish":        {"hp": 5,   "desc": "+5 HP"},
    "cooked_fish": {"hp": 15,  "desc": "+15 HP"},
    "bread":       {"hp": 10,  "desc": "+10 HP"},
    "meat_stew":   {"hp": 20,  "desc": "+20 HP"},
}

# Tavern food/drink menu (price in gold)
TAVERN_MENU = [
    {"id": "bread",     "name": "Bread",     "price": 4,  "hp": 10},
    {"id": "ale",       "name": "Ale",       "price": 6,  "hp": 0},
    {"id": "meat_stew", "name": "Meat Stew", "price": 10, "hp": 20},
]

# Farm animal types for farmhouse enclosures
FARM_ANIMALS = ["vil_cow", "vil_pig", "vil_chicken", "vil_goat", "vil_sheep"]

# Farmer shop catalog (price in gold)
FARMER_SHOP = [
    {"id": "wheat_seed",   "name": "Wheat Seeds",  "price": 3},
    {"id": "carrot_seed",  "name": "Carrot Seeds", "price": 3},
    {"id": "potato_seed",  "name": "Potato Seeds", "price": 3},
    {"id": "hoe",          "name": "Hoe",          "price": 20},
    {"id": "watering_can", "name": "Watering Can", "price": 35},
    {"id": "dry_grass",    "name": "Hay",          "price": 1},
    {"id": "plant_fiber",  "name": "Fiber",        "price": 3},
    {"id": "healing_herb", "name": "Herb",         "price": 8},
]

# Hospital heal cost: gold per missing HP (minimum 5 gold)
HEAL_COST_PER_HP = 2
HEAL_MINIMUM_COST = 5

# Shrine enchantment sacrifices: type → {item, qty, result, label}
SHRINE_SACRIFICES = {
    "strength": {
        "item": "iron_ore",    "qty": 63,
        "result": "enchanted_gem_strength",
        "label": "⚔️ Strength (63 iron ore)",
    },
    "time": {
        "item": "chronolite",  "qty": 3,
        "result": "enchanted_gem_time",
        "label": "⏱️ Time (3 chronolite)",
    },
    "defense": {
        "item": "wyvern_scale", "qty": 20,
        "result": "enchanted_gem_defense",
        "label": "🛡️ Defense (20 wyvern scales)",
    },
    "sight": {
        "item": "gem",         "qty": 5,
        "result": "enchanted_gem_sight",
        "label": "👁️ Sight (5 gems)",
    },
    "luck": {
        "item": "poison_sac",  "qty": 10,
        "result": "enchanted_gem_luck",
        "label": "🍀 Luck (10 poison sacs)",
    },
}

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
    # Flint recipes
    frozenset({("flint", 1), ("iron_ingot", 1)}):       {"result": "flint_and_steel", "qty": 1, "label": "🔥 Flint & Steel"},
    frozenset({("flint", 1), ("stick", 3)}):            {"result": "arrow",           "qty": 9, "label": "🏹 Arrows (×9)"},
    # Ring crafting (enchanted gem + gold ring)
    frozenset({("enchanted_gem_strength", 1), ("gold_ring", 1)}): {"result": "ring_of_strength", "qty": 1, "label": "💪 Ring of Strength"},
    frozenset({("enchanted_gem_time", 1),     ("gold_ring", 1)}): {"result": "ring_of_time",     "qty": 1, "label": "⏱️ Ring of Time"},
    frozenset({("enchanted_gem_defense", 1),  ("gold_ring", 1)}): {"result": "ring_of_defense",  "qty": 1, "label": "🛡️ Ring of Defense"},
    frozenset({("enchanted_gem_sight", 1),    ("gold_ring", 1)}): {"result": "ring_of_sight",    "qty": 1, "label": "👁️ Ring of Sight"},
    frozenset({("enchanted_gem_luck", 1),     ("gold_ring", 1)}): {"result": "ring_of_luck",     "qty": 1, "label": "🍀 Ring of Luck"},
    # Ship repair materials
    frozenset({("iron_ingot", 1)}):                              {"result": "nail",            "qty": 18, "label": "📌 Forge Nails (×18)"},
    # Underwater breathing
    frozenset({("seaweed", 2), ("gust_of_aevos", 1)}):          {"result": "breath_of_the_sea", "qty": 1, "label": "🫧 Brew Breath of the Sea"},
    # Sky temple gears
    frozenset({("iron_ingot", 2)}):                              {"result": "small_gear",        "qty": 1, "label": "⚙️ Forge Small Gear"},
    frozenset({("iron_ingot", 3)}):                              {"result": "large_gear",         "qty": 1, "label": "🔩 Forge Large Gear"},
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

# --- Sky Biome ---

SKY_EMOJI = {
    "sky_void":     "\U0001F30C",       # 🌌 starry sky (impassable void)
    "sky_cloud":    "☁️",     # ☁️ cloud tile (walkable)
    "sky_floor":    "\U0001F324️", # 🌤️ partial-sun sky floor (walkable)
    "sky_bridge":   "\U0001F7EB",       # 🟫 wooden sky bridge (walkable)
    "sky_chest":    "\U0001F4B0",       # 💰 sky chest (walkable/interactive)
    "sky_temple":   "\U0001F3DB️", # 🏛️ sky temple (walkable/interactive)
    "sky_altar":    "✨",           # ✨ sky altar (walkable/interactive)
    "sky_entrance": "\U0001F300",       # 🌀 sky entrance portal (exit back to world)
    "sky_rune_stone":   "📜",
    "sky_storm_tower":  "⚡",
    "sky_wind_shrine":  "\U0001F32C️",  # 🌬️
    # Sky enemies
    "wind_wisp":    "\U0001F4A8",       # 💨
    "storm_hawk":   "\U0001F985",       # 🦅
}

SKY_WALKABLE = {
    "sky_cloud", "sky_floor", "sky_bridge",
    "sky_chest", "sky_temple", "sky_altar", "sky_entrance",
    "sky_rune_stone", "sky_storm_tower", "sky_wind_shrine",
}

TEMPLE_EMOJI: dict[str, str] = {
    # Structure tiles
    "temple_floor":           "🟫",
    "temple_wall":            "🧱",
    "temple_entrance":        "🚪",
    "temple_altar":           "🏺",
    "temple_pillar":          "🪨",
    "temple_portal_locked":   "🔒",
    "temple_portal_open":     "🌀",
    "temple_rune":            "📜",
    # Gear slots — empty (motionless socket indicator)
    "gear_slot_s_empty":      "⬡",     # empty small-gear socket
    "gear_slot_l_empty":      "⬡",     # empty large-gear socket (4 tiles share this)
    # Small gears — filled
    "gear_slot_s_cw":         _ge("gear_small",          "⚙️"),   # clockwise
    "gear_slot_s_ccw":        _ge("gear_small_reverse",  "⚙️"),   # counter-clockwise
    # Large gears — filled clockwise (4 quadrants)
    "gear_slot_l_cw_tl":      _ge("gear_top_left",            "🔩"),
    "gear_slot_l_cw_tr":      _ge("gear_top_right",           "🔩"),
    "gear_slot_l_cw_bl":      _ge("gear_bottom_left",         "🔩"),
    "gear_slot_l_cw_br":      _ge("gear_bottom_right",        "🔩"),
    # Large gears — filled counter-clockwise (4 quadrants)
    "gear_slot_l_ccw_tl":     _ge("gear_top_left_reverse",    "🔩"),
    "gear_slot_l_ccw_tr":     _ge("gear_top_right_reverse",   "🔩"),
    "gear_slot_l_ccw_bl":     _ge("gear_bottom_left_reverse", "🔩"),
    "gear_slot_l_ccw_br":     _ge("gear_bottom_right_reverse","🔩"),
}

TEMPLE_WALKABLE: frozenset[str] = frozenset({
    "temple_floor", "temple_entrance",
    "temple_altar", "temple_portal_locked", "temple_portal_open",
    "temple_rune",
    "gear_slot_s_empty", "gear_slot_l_empty",
    "gear_slot_s_cw", "gear_slot_s_ccw",
    "gear_slot_l_cw_tl",  "gear_slot_l_cw_tr",  "gear_slot_l_cw_bl",  "gear_slot_l_cw_br",
    "gear_slot_l_ccw_tl", "gear_slot_l_ccw_tr", "gear_slot_l_ccw_bl", "gear_slot_l_ccw_br",
})

SKY_LORE = {
    "temple_altar": [
        "🏺 The altar thrums with dormant energy.",
        "Etched runes read: *'When the three machines turn, the sky opens its gate.'*",
    ],
    "temple_rune": [
        "📜 *'The large gear drives the small. The small gear drives the world. Together, they lift you to our realm.'*",
        "📜 *'Three temples guard the way. Only when all gears turn as one shall the portal awaken.'*",
        "📜 *'We built these temples as a trial. Only those patient enough to gather the ancient gears may ascend.'*",
    ],
    "temple_portal_locked": [
        "🔒 A massive archway carved from mountain stone. The portal is sealed.",
        "Cold air emanates from the arch. A faint inscription: *'Three machines must turn before I open.'*",
    ],
    "temple_portal_open": [
        "🌀 The portal swirls with otherworldly light. Step through to enter the Sky Realm.",
    ],
    "sky_altar": [
        "✨ An altar of the sky-builders, worn smooth by wind and time.",
        "Offerings of strange metalwork are scattered across its surface.",
    ],
    "sky_temple": [
        "🏛️ A sky temple. The architecture matches the mountain temples far below.",
        "Remnants of gear-work adorn the walls — whoever built this place descended to the world below.",
    ],
    "sky_rune_stone": [
        "📜 *'We came from the mountains. We built our temples above the clouds. Now we are wind.'*",
        "📜 *'The storm hawks were our guardians once. The wind wisps are the echoes of our builders.'*",
        "📜 *'To return below: find the spiral portal and step through. The mountain will remember you.'*",
    ],
    "sky_storm_tower": [
        "⚡ Lightning arcs between the tower's spires. A hum fills the air.",
        "Enormous interlocked gears line the tower walls — the source of the mountain temples' power.",
    ],
    "sky_wind_shrine": [
        "🌬️ A small shrine. Wind whirls gently around it despite the still air.",
        "Tiny carved figures dance in the updraft, suspended by ancient magic.",
    ],
}

SKY_ENCOUNTER_RATES = {
    "wind_wisp":  0.08,  # on sky_cloud tiles
    "storm_hawk": 0.06,  # on sky_bridge tiles
}

# --- Ship System ---

SHIP_EMOJI = {
    "deep_water":            "\U0001F30A",      # 🌊 (ocean surrounding ship)
    "ship_deck":             "\U0001FAB5",      # 🪵 wooden plank
    "ship_wall":             "\U0001F7EB",      # 🟫 brown wall
    "ship_helm":             "\u2693",          # ⚓ steering wheel / helm
    "ship_door":             "\U0001F6AA",      # 🚪 door (between rooms)
    "ship_chest_personal":   "\U0001F4E6",      # 📦 personal chest
    "ship_chest_cargo":      "\U0001F4E6",      # 📦 cargo chest
    "ship_mast":             "\U0001FAA1",      # 🪡 mast
    "ship_cannon":           "\U0001F4A3",      # 💣 cannon
    "ship_bed":              "\U0001F6CF\uFE0F",# 🛏️ bed
    "ship_table":            "\U0001FA91",      # 🪑 chair/table
    "ship_stairs":           "\U0001FA9C",      # 🪜 stairs
    "ship_hull_damage":      "\U0001F573️",# 🕳️ hull breach (overridable with :wood_floor_damaged:)
}

SHIP_WALKABLE = {
    "ship_deck", "ship_helm", "ship_door",
    "ship_chest_personal", "ship_chest_cargo", "ship_stairs",
    "ship_hull_damage",
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
    "iron_ore_deposit":   "\U0001F7EB",            # 🟫 (overridable with :iron_ore:)
    "gold_ore_deposit":   "\U0001F7E1",            # 🟡
    "cave_bat":           "\U0001F987",            # 🦇
    "cave_spider":        "\U0001F577\uFE0F",      # 🕷️
    "cave_golem":         "\U0001F5FF",            # 🗿 (moai — rock golem)
    "cave_troll":         "\U0001F479",            # 👹 troll
    "cave_wyvern":        "\U0001F409",            # 🐉 wyvern/dragon
    "cave_stairdown":     "\U0001F53D",            # 🔽 descend deeper
    "cave_stairup":       "\U0001F53C",            # 🔼 ascend
    "player_house_cave":  "\U0001F3E0",            # 🏠 player-built house in cave
    # Rift tiles (temporal rift pocket dimension)
    "rift_wall":          "\U0001F7E6",            # 🟦 blue wall
    "rift_floor":         "\U0001F535",            # 🔵 blue circle floor
    "rift_deposit":       "\U0001F4A0",            # 💠 chronolite deposit (mineable after boss)
    "rift_entrance":      "\U0001F300",            # 🌀 swirling portal (exit)
    # Lava cave tiles (floor/wall match regular cave; lava = orange square)
    "lava_floor":         "\U0001F7EB",            # 🟫 same as stone_floor (overridable → grey_square)
    "lava_pool":          "\U0001F7E7",            # 🟧 orange square lava river (impassable)
    "lava_wall":          "⬛",                # ⬛ same as stone_wall
    "lava_bridge":        "\U0001F7EB",            # 🟫 stone bridge over lava (overridable → grey_square)
    # Lava cave enemies
    "cinder_imp":         "👺",                    # red goblin demon
    "lava_salamander":    "🦎",                    # lizard
    "obsidian_golem":     "\U0001F5FF",            # 🗿 stone/obsidian golem (same as cave_golem)
}

CAVE_WALKABLE = {"stone_floor", "cave_entrance", "cave_chest", "cave_chest_medium", "cave_chest_large", "cave_stairdown", "cave_stairup", "player_house_cave",
                 "rift_floor", "rift_entrance", "rift_deposit",
                 # Lava cave tiles
                 "lava_floor", "lava_bridge"}
# cave_rock blocks movement; cave_bat/cave_spider/cave_golem are no longer placed as tiles

# --- Shipwreck System ---

SHIPWRECK_EMOJI = {
    "sw_floor":     "\U0001F30A",       # 🌊 flooded deck floor
    "sw_wall":      "⬛",           # ⬛ hull wall (impassable)
    "sw_chest":     "\U0001F4B0",       # 💰 treasure chest
    "sw_entrance":  "\U0001F573️", # 🕳️ entrance/exit hatch
    "sw_debris":    "\U0001FAB5",       # 🪵 wooden debris (walkable flavour)
}

SHIPWRECK_WALKABLE = {"sw_floor", "sw_chest", "sw_entrance", "sw_debris"}
SHIPWRECK_SIZE = 7       # interior grid is 7×7
SHIPWRECK_ENTRY_X = 3   # player spawns at column 3 (centre of bottom row)
SHIPWRECK_ENTRY_Y = 5   # row 5 (one above the bottom wall)
BREATH_MAX = 100
BREATH_PER_STEP = 20

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
    "vil_tavern":       "🍻",        # 🍻  tavern
    "vil_hospital":     "🏥",        # 🏥  hospital / healer
    "vil_elder":        "\U0001F9D3",        # 🧓  village elder NPC (quest giver)
    "vil_villager":     "\U0001F9D1",        # 🧑  walking villager NPC
    "vil_guard":        "\U0001F482",        # 💂  guard NPC
    "vil_lumber_mill":  "⚙️",      # ⚙️  waterwheel lumber mill
    "vil_farmhouse":    "🏡",        # 🏡  farmhouse
    "vil_fence":        "🟫",        # 🟫  fence post (overridable with :fence:)
    "vil_fence_gate":   "🚪",        # 🚪  fence gate — walkable (overridable with :fence_gate:)
    # Farmland tiles
    "vil_farmland":     "🟤",        # 🟤  bare farmland (overridable with :farmland:)
    "vil_seeds_wheat":  "🟤",        # 🟤  planted wheat seeds (overridable with :farmland_seeds:)
    "vil_seeds_carrot": "🟤",        # 🟤  planted carrot seeds
    "vil_seeds_potato": "🟤",        # 🟤  planted potato seeds
    "vil_crop_wheat":   "🌾",        # 🌾  ripe wheat
    "vil_crop_carrot":  "🥕",        # 🥕  ripe carrot
    "vil_crop_potato":  "🥔",        # 🥔  ripe potato
    "vil_cow":          "🐄",        # 🐄  cow
    "vil_pig":          "🐖",        # 🐖  pig
    "vil_chicken":      "🐓",        # 🐓  chicken
    "vil_goat":         "🐐",        # 🐐  goat
    "vil_sheep":        "🐑",        # 🐑  sheep
    # Pen interior (protected from path drawing, but walkable)
    "vil_pen_grass":    "\U0001F33F",        # 🌿  pen interior ground (same as grass)
    # Puzzle board
    "vil_puzzle_board": "🎮",               # 🎮  sliding-block puzzle board
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
    # Tavern unique
    "b_bar_counter":     "🟫",       # 🟫  wood bar counter
    "b_barrel":          "🛢️", # 🛢️  barrel
    "b_barkeep":         "🧑",       # 🧑  barkeep NPC
    "b_tavern_npc":      "🧑",       # 🧑  tavern quest NPC
    "b_crew_npc":        "⚓",       # ⚓  harbour tavern recruit NPC (hireable crew member)
    # Hospital unique
    "b_healer":          "🧑",       # 🧑  healer NPC
    "b_medicine_shelf":  "🌿",       # 🌿  herb/medicine shelf
    # House furnishings (also used by mil/other interiors)
    "b_chest":          "\U0001F4E6",        # 📦  small storage chest
    "b_resident":       "\U0001F9D3",        # 🧓  house resident NPC
    "b_pet":            "\U0001F431",        # 🐱  house cat
    # Lumber mill unique
    "b_waterwheel":     "⚙️",    # ⚙️  water-powered wheel
    "b_saw":            "🔨",       # 🔨  saw
    "b_lumber_npc":     "🧑",       # 🧑  lumber mill worker
    "b_farmer_npc":     "🧑",       # 🧑  farmer NPC
    "b_water":          "🌊",       # 🌊  water tile (lumber mill)
    # Player-house chests
    # Player-house chests
    "ph_chest_small":     "\U0001F4E6",       # 📦
    "ph_chest_medium":    "\U0001F5C4\uFE0F", # 🗄️
    "ph_chest_large":     "\U0001F9F3",       # 🧳
}

VILLAGE_WALKABLE = {
    "vil_grass", "vil_path", "vil_garden",
    "vil_house", "vil_church", "vil_bank", "vil_shop", "vil_blacksmith",
    "vil_tavern", "vil_hospital",
    "vil_dock",  # harbor-village boarding point — walkable, triggers ocean
    "vil_villager",     # walkable NPC (interact for gossip)
    "vil_guard",        # walkable NPC (interact for guard dialogue)
    "vil_lumber_mill",  # enterable lumber mill building
    "vil_farmhouse",    # enterable farmhouse building
    "vil_fence_gate",   # walkable fence gate
    # Farmland & crop tiles (all walkable)
    "vil_farmland",
    "vil_seeds_wheat", "vil_seeds_carrot", "vil_seeds_potato",
    "vil_crop_wheat", "vil_crop_carrot", "vil_crop_potato",
    "vil_pen_grass",       # pen interior ground (walkable, but protected from paths)
    "vil_puzzle_board",   # puzzle board — walkable, triggers puzzle UI
    # Note: vil_fence/animals are solid obstacles (not walkable)
    # Note: "vil_water" is intentionally absent — impassable harbour water
}

BUILDING_WALKABLE = {
    "b_floor", "b_floor_wood", "b_door",
    "b_priest", "b_bank_npc", "b_shop_npc", "b_blacksmith_npc",
    "b_pew", "b_table", "b_stove", "b_bed",
    "b_barkeep", "b_tavern_npc", "b_healer", "b_barrel", "b_bar_counter", "b_medicine_shelf",
    "b_anvil", "b_chair", "b_bookshelf", "b_candle",
    "b_chest", "b_resident", "b_pet",
    "b_waterwheel", "b_saw", "b_lumber_npc", "b_farmer_npc",
    "b_crew_npc",   # harbour tavern recruit NPC — walkable
    # Note: b_water is NOT in BUILDING_WALKABLE (water is impassable inside)
    "ph_chest_small", "ph_chest_medium", "ph_chest_large",
}

VILLAGE_MIN_SIZE = 32
VILLAGE_MAX_SIZE = 32

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
        "id": "climbing_boots",
        "name": "Climbing Boots",
        "emoji": "\U0001F9D7",   # 🧗 person climbing
        "price": 150,
        "equip_slot": "boots",
        "description": "Reinforced boots. Traverse mountain tiles. Required for sky biome portals.",
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
        "description": "Expands inventory to 2×7 (14 slots).",
    },
    {
        "id": "medium_pouch",
        "name": "Medium Pouch",
        "emoji": "\U0001F45C",
        "price": 180,
        "equip_slot": "pouch",
        "description": "Expands inventory to 3×7 (21 slots).",
    },
    {
        "id": "large_pouch",
        "name": "Large Pouch",
        "emoji": "\U0001F45C",
        "price": 350,
        "equip_slot": "pouch",
        "description": "Expands inventory to 4×7 (28 slots).",
    },
    {
        "id": "small_coin_purse",
        "name": "Small Coin Purse",
        "emoji": "\U0001F4B0",
        "price": 100,
        "equip_slot": "coin_purse",
        "description": "Increases coin capacity to 200 coins.",
    },
    {
        "id": "medium_coin_purse",
        "name": "Medium Coin Purse",
        "emoji": "\U0001F4B0",
        "price": 200,
        "equip_slot": "coin_purse",
        "description": "Increases coin capacity to 500 coins.",
    },
    {
        "id": "large_coin_purse",
        "name": "Large Coin Purse",
        "emoji": "\U0001F4B0",
        "price": 500,
        "equip_slot": "coin_purse",
        "description": "Increases coin capacity to 1000 coins.",
    },
    {
        "id": "hammer",
        "name": "Hammer",
        "emoji": "\U0001F528",
        "price": 80,
        "equip_slot": "hand",
        "description": "Repair ship hull damage tiles. Requires nails + planks.",
    },
]

# Equipment slots
EQUIP_SLOTS = {"hand_1", "hand_2", "head", "chest", "legs", "boots", "accessory", "pouch", "coin_purse"}

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
    "hiking_boots":   "boots",
    "climbing_boots": "boots",
    "small_pouch":       "pouch",
    "medium_pouch":      "pouch",
    "large_pouch":       "pouch",
    "house_kit":         "hand",
    "small_coin_purse":  "coin_purse",
    "medium_coin_purse": "coin_purse",
    "large_coin_purse":  "coin_purse",
    "iron_boots":          "boots",
    "wyvern_helmet":       "head",
    "wyvern_chestplate":   "chest",
    "wyvern_leggings":     "legs",
    "iron_shield":         "hand",
    "wyvern_shield":       "hand",
    "gold_ring":           "accessory",
    "ring_of_strength":    "accessory",
    "ring_of_time":        "accessory",
    "ring_of_defense":     "accessory",
    "ring_of_sight":       "accessory",
    "ring_of_luck":        "accessory",
    "flint_and_steel":     "hand",
    "hoe":                 "hand",
    "hammer":              "hand",
}

# Items that occupy both hand slots
TWO_HANDED_ITEMS = {"shovel"}

# Equipment stat bonuses: {item_id: {stat: bonus}}
EQUIP_BONUSES = {
    "knife":        {"attack": 5},
    "axe":          {"attack": 3},
    "pickaxe":      {"attack": 4},
    "slingshot":    {"attack": 4},
    "hiking_boots":   {},
    "climbing_boots": {},
    "torch":        {},
    "shovel":       {},
    "watering_can": {},
    "seed":         {},
    "sapling":      {},
    "small_pouch":       {},
    "medium_pouch":      {},
    "large_pouch":       {},
    "fishing_rod":       {},
    "small_coin_purse":  {},
    "medium_coin_purse": {},
    "large_coin_purse":  {},
    "dagger":       {"attack": 8},
    "iron_helmet":     {"defense": 3},
    "iron_chestplate": {"defense": 5},
    "iron_leggings":   {"defense": 4},
    "sword":        {"attack": 12},
    "iron_boots":          {"defense": 2},
    "wyvern_helmet":       {"defense": 5},
    "wyvern_chestplate":   {"defense": 8},
    "wyvern_leggings":     {"defense": 6},
    "iron_shield":         {"defense": 4},
    "wyvern_shield":       {"defense": 7},
    "gold_ring":           {},
    "ring_of_strength":    {"attack": 5},
    "ring_of_time":        {},    # +1 combat move — handled in combat code
    "ring_of_defense":     {"defense": 5},
    "ring_of_sight":       {},    # 9x9 cave view without torch — handled in cave code
    "ring_of_luck":        {},    # better drops — handled in drop code
    "flint_and_steel":     {},
    "arrow":               {},
    "hoe":                 {},
}

# Pouch inventory sizes: (rows, cols) — default 1×7 when no pouch equipped
POUCH_SIZES: dict[str | None, tuple[int, int]] = {
    None:           (1, 7),
    "small_pouch":  (2, 7),
    "medium_pouch": (3, 7),
    "large_pouch":  (4, 7),
}

# Coin purse capacity: default 100, upgradeable with purse items
COIN_PURSE_CAPACITY: dict[str | None, int] = {
    None:                100,
    "small_coin_purse":  200,
    "medium_coin_purse": 500,
    "large_coin_purse":  1000,
}

# Maximum stack size per inventory slot
MAX_STACK_SIZE = 9

# Cave random encounter rates per step: {enemy_type: chance 0-1}
CAVE_ENCOUNTER_RATES = {
    "cave_bat":    0.07,
    "cave_spider": 0.07,
    "cave_golem":  0.04,
}

# Per-level iron ore deposit spawn probability (fraction of rock tiles replaced)
CAVE_ORE_RATES: dict[int, float] = {1: 0.05, 2: 0.15, 3: 0.30}

# Per-level gold ore deposit spawn probability (additional fraction of rock tiles, level 3 only)
CAVE_GOLD_ORE_RATES: dict[int, float] = {3: 0.05}

# Per-level cave encounter rates: {level: {enemy_type: chance}}
CAVE_LEVEL_ENCOUNTER_RATES = {
    1: {"cave_bat": 0.12, "cave_spider": 0.10},
    2: {"cave_spider": 0.08, "cave_golem": 0.10, "cave_troll": 0.08},
    3: {"cave_golem": 0.10, "cave_troll": 0.12, "cave_wyvern": 0.10},
}

# Lava cave random encounter rates (separate from normal cave rates)
LAVA_CAVE_ENCOUNTER_RATES = {
    "cave_bat":       0.06,
    "cinder_imp":     0.10,
    "lava_salamander":0.08,
    "obsidian_golem": 0.04,
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
    "hiking_boots":   30,
    "climbing_boots": 90,
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
    "small_pouch":       48,
    "medium_pouch":      108,
    "large_pouch":       210,
    "small_coin_purse":  60,
    "medium_coin_purse": 120,
    "large_coin_purse":  300,
    "cannonball":        10,
    "gold_ore":          20,
    "gold_ingot":        50,
    "gold_ring":         100,
    "iron_boots":        60,
    "ring_of_strength":  250,
    "ring_of_time":      250,
    "ring_of_defense":   250,
    "ring_of_sight":     250,
    "ring_of_luck":      250,
    "enchanted_gem_strength": 80,
    "enchanted_gem_time":     80,
    "enchanted_gem_defense":  80,
    "enchanted_gem_sight":    80,
    "enchanted_gem_luck":     80,
    "flint_and_steel":   15,
    "arrow":             3,
    "star_fragment":     50,
    "chronolite":        75,
    "wyvern_scale":      40,
    "wyvern_helmet":     80,
    "wyvern_chestplate": 120,
    "wyvern_leggings":   100,
    "iron_shield":       55,
    "wyvern_shield":     130,
    "bread":             2,
    "ale":               3,
    "meat_stew":         5,
    "healing_herb":      8,
    "wheat_seed":        1,
    "carrot_seed":       1,
    "potato_seed":       1,
    "wheat":             3,
    "carrot":            3,
    "potato":            3,
    "hoe":               12,
    "breath_of_the_sea": 30,
    "gust_of_aevos":     20,
    "gold_coin":         1,
    "seaweed":           3,
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


# --- Ship Crew System ---

MAX_CREW_SIZE = 3
CREW_HIRE_COST = 500

# Crew NPC names (randomly assigned at hire)
CREW_NAMES = [
    "Jake", "Morgan", "Sam", "Alex", "Riley", "Casey", "Drew", "Jordan",
    "Quinn", "Avery", "Reese", "Blake", "Devon", "Sage", "River", "Finley",
]

# Available crew tasks: {task_id: {label, emoji, desc}}
CREW_TASKS = {
    "idle":   {"label": "Idle",        "emoji": "💤", "desc": "No task assigned"},
    "repair": {"label": "Auto-Repair", "emoji": "🔨", "desc": "Repairs hull when damaged and hammer+nails+planks are in cargo"},
    "cannon": {"label": "Gunner",      "emoji": "💣", "desc": "Boosts cannon attack damage by +5"},
    "watch":  {"label": "Lookout",     "emoji": "🔭", "desc": "Reduces ocean encounter rate by half"},
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
        (CAVE_EMOJI,     "lava_floor",        "grey_square"),
        (CAVE_EMOJI,     "lava_bridge",       "grey_square"),
        (BUILDING_EMOJI, "b_stove",           "hearth"),
        (BUILDING_EMOJI, "b_table",           "table"),
        (BUILDING_EMOJI, "b_floor",           "grey_square"),
        (BUILDING_EMOJI, "b_floor_wood",      "wood_floor"),
        (BUILDING_EMOJI, "b_shelf",           "chest"),
        (SHIP_EMOJI,     "ship_deck",         "wood_floor"),
        (SHIP_EMOJI,     "ship_chest_personal", "chest"),
        (SHIP_EMOJI,     "ship_chest_cargo",    "chest"),
        (BUILDING_EMOJI, "b_forge",           "forge"),
        (VILLAGE_EMOJI,  "vil_grass",         "grass"),
        (VILLAGE_EMOJI,  "vil_fence",         "fence"),
        (VILLAGE_EMOJI,  "vil_fence_gate",    "fence_gate"),
        (VILLAGE_EMOJI,  "vil_farmland",      "farmland"),
        (VILLAGE_EMOJI,  "vil_seeds_wheat",   "farmland_seeds"),
        (VILLAGE_EMOJI,  "vil_seeds_carrot",  "farmland_seeds"),
        (VILLAGE_EMOJI,  "vil_seeds_potato",  "farmland_seeds"),
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
        ("iron_ingot",   "iron_ingot"),
        ("fishing_rod",  "fishing_pole"),
        ("poison_sac",   "poison_sac"),
        ("cooked_fish",  "cooked_fish"),
        ("flint",        "flint~1"),   # try numbered variant first
        ("flint",        "flint"),      # then plain name (whichever exists wins)
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

    # Island tiles use custom emojis when available
    if "chest" in cache:
        _renderer._ISLAND_TERRAIN_EMOJI["island_chest"] = cache["chest"]
        _renderer._ISLAND_TERRAIN_EMOJI["vol_chest"] = cache["chest"]
    if "grass" in cache:
        _renderer._ISLAND_TERRAIN_EMOJI["island_grass"] = cache["grass"]
        _renderer._ISLAND_TERRAIN_EMOJI["vol_grass"] = cache["grass"]
    # Ship hull damage tile → :wood_floor_damaged:
    if "wood_floor_damaged" in cache:
        SHIP_EMOJI["ship_hull_damage"] = cache["wood_floor_damaged"]

    # Iron ore deposit uses the same :iron_ore: custom emoji
    if "iron_ore" in cache:
        CAVE_EMOJI["iron_ore_deposit"] = cache["iron_ore"]

    # Gold ore deposit uses :gold_ore: if available
    if "gold_ore" in cache:
        CAVE_EMOJI["gold_ore_deposit"] = cache["gold_ore"]
        ITEM_EMOJI["gold_ore"] = cache["gold_ore"]
