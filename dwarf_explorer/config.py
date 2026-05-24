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
    "canoe_box":  "\U0001F6F6",      # 🛶 dropped canoe (overridden with :canoe_whole:)
    "bomb_lit":   "\U0001F4A3",      # 💣 lit bomb placed on the ground
    "deep_water": "\U0001F30A",      # 🌊
    "shallow_water": "\U0001F4A7",   # 💧
    "river": "\U0001F30A",           # 🌊
    "sand": "🟨",            # 🟨  (overridable with :sand:)
    "plains": "\U0001F33E",          # 🌾  (overridable with :dry_grass:)
    "grass": "\U0001F33F",           # 🌿  (overridable with :grass:)
    "forest": "\U0001F332",          # 🌲
    "dense_forest": "\U0001F333",    # 🌳
    "hills": "\U0001F304",  # 🌄  sunrise over mountains
    "mountain": "⛰️",      # ⛰️  :mountain: (no snow cap)
    "snow": "\U0001F3D4️",    # 🏔️  :mountain_snow: — impassable snowy peaks
    "path": "\U0001F7EB",           # 🟫
    "void": "\u2B1B",               # ⬛
    "river_landing": "\u26F5",      # ⛵ canoe launch point
    "farmland":     "\U0001F7E4",    # 🟤 bare soil
    "crop_planted": "\U0001F331",    # 🌱 seedling
    "crop_sprout":  "\U0001F33F",    # 🌿 herb
    "crop_ripe":    "\U0001F33B",    # 🌻 sunflower
    # Player-modifiable terrain
    "sapling":          "\U0001F331",    # 🌱
    "pinecone_planted": "\U0001F331",    # 🌱 planted pinecone (water to grow into sapling)
    "ancient_planted":  "\U0001F331",    # 🌱 planted ancient seed (water to grow into sapling)
    "ancient_sapling":  "\U0001F331",    # 🌱 planted ancient sapling (water to grow into 2×2 tree)
    "short_grass":      "\U0001F7E9",    # 🟩  short grass
    "seedling":         "\U0001FAB4",    # 🪴
    "dirt":             "\U0001F7E4",    # 🟤 dug soil (shovel); hoe turns it into farmland
    # Ancient 2×2 tree (grown by watering ancient_sapling; 10 axe chops to fell)
    "ancient_tree_top_left":     "\U0001F332",   # 🌲 fallback; overridden by custom emoji
    "ancient_tree_top_right":    "\U0001F332",
    "ancient_tree_bottom_left":  "\U0001F332",
    "ancient_tree_bottom_right": "\U0001F332",
    # Forest Quest zone tiles
    "fq_floor":        "\U0001F7EB",  # 🟫 earthy corridor/chamber floor
    "fq_wall":         "\U0001F333",  # 🌳 dense ancient forest wall
    "fq_stream":       "\U0001F30A",  # 🌊 impassable stream
    "fq_stream_ford":  "\U0001FAB5",  # 🪵 log bridge — passable ford
    "fq_puzzle_floor": "\U00002B1B",  # ⬛ sunken dark earth puzzle floor
    "fq_obstacle":     "\U0001FAA8",  # 🪨 immovable mossy rock/stump
    "fq_log":          "\U0001FAB5",  # 🪵 pushable log
    "fq_log_target":   "\U0001F7E7",  # 🟧 target notch at stream edge
    "fq_reset":        "\U0001FAA8",  # 🪨 ancient reset stone
    "fq_exit":         "\U0001F332",  # 🌲 forest exit marker
    "fq_grove_exit":   "\U00002728",  # ✨ hidden grove entrance
    # Forest Quest — shop & boss tiles
    "fq_shopkeeper":       "\U0001F9D9",  # 🧙 forest merchant
    "fq_warden_body":      "\U0001F33F",  # 🌿 Thornwarden briar body (impassable)
    "fq_warden_eye_nw":    "\U000026AB",  # ⚫ dormant NW eye (closed)
    "fq_warden_eye_ne":    "\U000026AB",  # ⚫ dormant NE eye (closed)
    "fq_warden_eye_sw":    "\U000026AB",  # ⚫ dormant SW eye (closed)
    "fq_warden_eye_se":    "\U000026AB",  # ⚫ dormant SE eye (closed)
    "fq_warden_eye_warn":  "\U0001F7E1",  # 🟡 eye about to open (warning flash)
    "fq_warden_eye_open":  "\U0001F441\U0000FE0F",  # 👁️ eye wide open (hit window)
    "fq_warden_dead":      "\U0001F7EB",  # 🟫 collapsed rubble (walkable)
    "fq_boss_door":        "\U0001F6A7",  # 🚧 locked exit from boss chamber
    "fq_boss_door_open":   "\U0001F6AA",  # 🚪 open exit door (walkable)
    "fq_boss_chest":       "\U0001F4E6",  # 📦 loot chest spawned after warden dies
    "fq_aim_cursor":       "\U0001F3AF",  # 🎯 slingshot aim cursor overlay
    # Forest Quest — Y-fork, canal puzzle, final room
    "fq_fork_chest":        "\U0001F381",  # 🎁 side-branch reward chest
    "fq_canal_floor":       "\U0001F4A7",  # 💧 wet canal floor (aesthetic)
    "fq_canal_target":      "\U00002B55",  # ⭕ canal block target slot
    "fq_canal_gate":        "\U0001F512",  # 🔒 locked canal gate
    "fq_canal_gate_open":   "\U0001F513",  # 🔓 opened canal gate (walkable)
    "fq_canal_reset":       "\U0001FAA8",  # 🪨 canal reset stone
    "fq_ancient_ent":       "\U0001F332",  # 🌲 ancient ent guardian (alive, darker tree)
    "fq_ancient_tree":      "\U0001F333",  # 🌳 the ancient heart tree (interactable)
    "fq_ancient_tree_done": "\U00002728",  # ✨ ancient tree — quest activated
    "fq_ancient_chest":     "\U0001F4E6",  # 📦 final room reward chest
    # Hermit zone tiles
    "fst_hermit_house": "\U0001F6D6",  # 🛖 hermit's hut
    "fst_fq_entrance":  "\U0001F333",  # 🌳 looks like a tree wall (FQ zone entrance marker)
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
    "forest_entrance":  "\U0001F332",        # 🌲 forest entrance (overridable with :forest_entrance:)
    "bandit_camp":      "⛺", # ⛺ tent — bandit camp
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
    # Surface
    "bandit": "\U0001F9B9",          # 🦹 villain/bandit
    # Forest Quest enemies
    "ent":             "\U0001F333",  # 🌳 ent (disguised as dense_forest until it moves)
    "snake":           "\U0001F40D",  # 🐍 forest snake
    # Forest enemies
    "forest_sprite":   "\U0001F9DA",  # 🧚 fairy-like mischievous spirit
    "vine_creeper":    "\U0001F40D",  # 🐍 snake-like vine monster
    "corrupted_dryad": "\U0001F9DF",  # 🧟 corrupted forest spirit
    "forest_troll":    "\U0001F479",  # 👹 mossy forest troll
    # Quest marker types (rendered on overworld as location indicators)
    "exploration":     "\U0001F332",  # 🌲 forest exploration quest marker
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
    "baked_potato": "\U0001F360",    # 🍠 roasted sweet potato
    "hoe":         "\U0001FAB0",     # 🪰  (overridable with :hoe:)
    "wood": "\U0001FAB5",            # 🪵
    "stone": "\U0001FAA8",           # 🪨
    "gem": "\U0001F48E",             # 💎
    "sword": "\U0001F5E1\uFE0F",    # 🗡️
    "shield": "\U0001F6E1\uFE0F",   # 🛡️
    "key": "\U0001F511",             # 🔑
    "cave_key":    "\U0001F5DD️",  # 🗝️ dungeon key (boss chamber)
    "warp_crystal": "\U0001F52E",        # 🔮 crystal of passage (warp item)
    "fish": "\U0001F41F",            # 🐟
    "map_fragment": "\U0001F5FA\uFE0F",  # 🗺️
    "knife": "\U0001F52A",    # 🗡️
    "hiking_boots":    "\U0001F97E",    # 🥾
    "climbing_boots":  "\U0001F97E",    # 🥾 hiking boot
    "torch": "\U0001F526",           # 🔦
    "axe": "\U0001FA93",             # 🪓
    "shovel": "\u26CF\uFE0F",       # ⛏️
    "watering_can": "\U0001FAA3",    # 🪣
    "pickaxe": "\u26CF\uFE0F",      # ⛏️
    "log": "\U0001FAB5",             # 🪵
    "stick": "\U0001F38B",           # 🎋
    "wayerwood":          "\U0001FA84",       # 🪄 magical divining rod (unattuned)
    "attuned_wayerwood":  "\U0001FA84",       # 🪄 attuned divining rod (crafted with rock)
    "resin": "\U0001F7E1",           # 🟡
    "plant_fiber": "\U0001F9F5",     # 🧵
    "dry_grass": "\U0001F33E",       # 🌾
    "seed": "\U0001F330",            # 🌰
    "pinecone": "\U0001F332",        # 🌲 pinecone (plantable, grows into sapling)
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
    "canoe":            "🛶",       # 🛶  canoe (legacy single-item)
    "canoe_left":       "🛶",       # left half of 2-piece canoe (overridden by custom emoji)
    "canoe_right":      "🛶",       # right half of 2-piece canoe (overridden by custom emoji)
    "canoe":            "🛶",       # canoe as a single item (used in equip row, tooltips); overridden with canoe_whole emoji
    "canoe_whole":      "🛶",       # player-on-water display (overridden by custom emoji)
    "hammer":           "🔨",       # 🔨  hammer (ship repair)
    "nail":             "📌",       # 📌  nail (ship repair)
    "breath_of_the_sea": "🫧",     # 🫧  breath of the sea (restores breath underwater)
    "gust_of_aevos":    "🌬️",     # 🌬️  rare ingredient for breath_of_the_sea
    "hawk_feather":     "🪶",       # 🪶  dropped by storm_hawk in sky biome
    "gold_coin":        "🪙",       # 🪙  loose gold coin (shipwreck loot)
    "small_gear": _ge("gear_small_still", "⚙️"),
    "large_gear": _ge("gear_small_still", "⚙️"),
    # Forest items
    "forest_nut":     "\U0001F330",           # 🌰 raw forest nut (+3 HP)
    "roasted_nut":    "\U0001F95C",           # 🥜 roasted forest nut (+6 HP)
    "living_root":    "\U0001FAB5",           # 🪵 crafting ingredient
    "bark_shield":    "\U0001F6E1️",     # 🛡️ woven bark shield
    "ancient_seed":   "\U0001F331",           # 🌱 grows into magical sapling
    "ancient_sapling":"\U0001F331",           # 🌱 planted ancient sapling (same as sapling)
    "ancient_log":    "\U0001FAB5",           # 🪵 dense timber from the forest ancient tree
    # Forest Quest boss drops
    "ent_core":              "\U0001F7E2",    # 🟢 compressed life-orb from a slain ent
    "forest_heart_amulet":   "\U0001F49A",    # 💚 amulet crafted from ent cores (+15 max HP)
    # Bomb system
    "bomb":           "\U0001F4A3",           # 💣 throwable explosive
}

# Maps seed item_id → crop progression for village farmland
FARM_CROPS: dict[str, dict] = {
    "wheat_seed":  {
        "planted": "vil_seeds_wheat",  "mature": "vil_crop_wheat",
        "yield": "wheat",  "yield_qty": 2,  "emoji": "🌾",
        "seed_drop": "wheat_seed",  "seed_drop_max": 2,   # harvest drops 1-2 extra seeds
    },
    "carrot_seed": {
        "planted": "vil_seeds_carrot", "mature": "vil_crop_carrot",
        "yield": "carrot", "yield_qty": 2,  "emoji": "🥕",
        "seed_drop": "carrot_seed",  "seed_drop_max": 2,   # harvest drops 1-2 extra seeds
    },
    # Potatoes are their own seed — plant a potato, harvest potatoes.
    "potato": {
        "planted": "vil_seeds_potato", "mature": "vil_crop_potato",
        "yield": "potato", "yield_qty": 3,  "emoji": "🥔",
    },
}

WALKABLE_TILES = {
    "sand", "plains", "grass", "forest", "hills", "path",
    "village", "ruins", "ruins_looted", "shrine", "cave", "bridge",
    "sapling", "pinecone_planted", "ancient_planted", "ancient_sapling", "short_grass", "seedling", "dirt",
    "farmland", "crop_planted", "crop_sprout", "crop_ripe",
    "player_house",  # player-built house — walkable (enter on interact)
    "harbor",        # harbor dock — walkable
    "drop_box",      # item drop box — walkable, interact to pick up
    "canoe_box",     # dropped canoe — walkable, interact to pick up
    "bomb_lit",      # placed lit bomb — walkable (blast imminent)
    "sundial",       # sundial ruins — walkable (interact with star_fragment to open rift)
    "sky_portal",    # sky portal on mountain — walkable (legacy; kept for any existing portals)
    "sky_temple_outer",  # outer puzzle temple — walkable overworld tile
    "sky_temple_main",   # main portal temple — walkable overworld tile
    "forest_entrance",   # forest entrance — walkable (triggers forest interior load)
    "bandit_camp",       # bandit camp — walkable overworld tile (triggers combat when adjacent)
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
STRUCTURE_TILES = {"village", "ruins", "ruins_looted", "shrine", "cave", "bridge", "player_house", "harbor", "shipwreck", "island", "volcano_island", "sundial", "sky_portal", "sky_temple_outer", "sky_temple_main", "forest_entrance", "bandit_camp"}

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
    # Cave dungeon boss (level-3 boss room)
    "stone_guardian": (150, 22, 12, 200, 100),  # high HP/DEF, slam+roar
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
    # Surface bandits
    "bandit":     (35, 12, 2, 20, 18),  # moderate HP/atk, carries more gold than wolves
    # Forest enemies
    "forest_sprite":   (18,  8,  0, 12,  6),   # fast, low HP, ranged
    "vine_creeper":    (28, 11,  0, 18, 10),   # melee, poisons
    "corrupted_dryad": (38, 13,  1, 30, 18),   # ranged, corrupted nature spirit
    "forest_troll":    (50, 16,  2, 45, 22),   # heavy melee, slam/roar
    # Mimic — disguises as a chest; a nasty nuisance, not a boss
    "chest_mimic":     (22, 10,  1, 20, 15),   # low HP, moderate attack
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
    "wind_wisp":  {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False, "ranged": False},
    "storm_hawk": {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False, "ranged": False},
    # Forest enemies
    "forest_sprite":   {"cobweb": False, "poison": False, "hit_run": True,  "roar": False, "slam": False, "ranged": True},
    "vine_creeper":    {"cobweb": True,  "poison": True,  "hit_run": False, "roar": False, "slam": False, "ranged": False},
    "corrupted_dryad": {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": False, "ranged": True},
    "forest_troll":    {"cobweb": False, "poison": False, "hit_run": False, "roar": True,  "slam": True,  "ranged": False},
    # Maze mimic
    "chest_mimic":     {"cobweb": False, "poison": False, "hit_run": False, "roar": False, "slam": True,  "ranged": False},
    # Cave dungeon boss
    "stone_guardian":  {"cobweb": False, "poison": False, "hit_run": False, "roar": True,  "slam": True,  "ranged": False},
}

ARENA_EMOJI = {
    "cobweb": "\U0001F578\uFE0F",   # 🕸️
}

FOOD_HP_RESTORE = {"fish": 5, "cooked_fish": 15, "bread": 10, "meat_stew": 20}

# ── Forest Quest Zone ──────────────────────────────────────────────────────────

# Zone layout constants
FQ_WIDTH  = 21
FQ_HEIGHT = 200   # expanded to accommodate shop, boss, Y-fork, puzzle, final room

FQ_CORRIDOR_X0 = 8    # corridor occupies x = 8..12 (5 wide)
FQ_CORRIDOR_X1 = 12
FQ_CORRIDOR_Y0 = 0
FQ_CORRIDOR_Y1 = 15   # corridor ends at y=15; chamber begins at y=16

FQ_CHAMBER_Y0  = 16
FQ_STREAM_Y    = 29   # near (shallow) stream row — log pushed here becomes a ford
FQ_STREAM_Y2   = 30   # far (deep) stream row — log slides here to complete bridge

FQ_PUZZLE_X0   = 5    # sunken Sokoban area x = 5..15 (11 wide)
FQ_PUZZLE_X1   = 15
FQ_PUZZLE_Y0   = 18   # sunken area y = 18..28 (11 tall)
FQ_PUZZLE_Y1   = 28

FQ_FORD_XA     = 9    # stream ford tiles (activated when both logs on targets)
FQ_FORD_XB     = 10

FQ_ENTRY_X     = 10   # player enters the zone here (top of corridor)
FQ_ENTRY_Y     = 0
FQ_RESET_X     = 3    # reset stone position (in chamber, left of puzzle)
FQ_RESET_Y     = 22
FQ_GROVE_EXIT_X = 10  # kept for backward compat; no longer used in tile gen
FQ_GROVE_EXIT_Y = 999  # moved beyond active zone

# Post-stream corridor (y 31-40): 3-wide, matching the shop corridor below
FQ_POST_STREAM_X0 = 9
FQ_POST_STREAM_X1 = 11

# Shop section (y 41-53): narrow 3-wide corridor + left side room
# Layout: corridor x=9-11; 2-wide wall x=7-8; room x=3-6; shopkeeper at (6,47)
# A 1-wide opening at y=FQ_SHOP_OPENING_Y cuts through the wall (x=7 and x=8 are floor)
FQ_SHOP_Y0          = 41
FQ_SHOP_Y1          = 53
FQ_SHOP_ROOM_Y0     = 44   # side room top
FQ_SHOP_ROOM_Y1     = 50   # side room bottom
FQ_SHOP_OPENING_Y   = 47   # y row where the 1-tile entrance cuts through the 2-wide wall
FQ_SHOPKEEPER_X     = 6    # shopkeeper at east edge of the room, facing the opening
FQ_SHOPKEEPER_Y     = 47

# Items sold by the Forest Quest shopkeeper
FQ_SHOP_CATALOG = [
    {"id": "forest_nut", "name": "Forest Nut", "emoji": "🌰",  "price": 8,
     "description": "Restores 3 HP. Gathered from the ancient canopy."},
    {"id": "roasted_nut","name": "Roasted Nut","emoji": "🥜",  "price": 12,
     "description": "Toasted over the campfire. Restores 6 HP."},
    {"id": "rock",       "name": "Rock",        "emoji": "🪨",  "price": 4,
     "description": "Smooth stone — loaded into a slingshot."},
    {"id": "slingshot",  "name": "Slingshot",   "emoji": "\U0001FA83", "price": 22,
     "description": "A carved-wood ranged weapon. Fires rocks at enemies."},
]

# Boss approach (y 54-57): corridor funnels to single-tile entrance
FQ_BOSS_APPROACH_Y0 = 54
FQ_BOSS_APPROACH_Y1 = 57

# Boss chamber (y 58-68): circular arena, radius 5, centre (10, 63)
FQ_BOSS_CHAMBER_Y0  = 58
FQ_BOSS_CHAMBER_Y1  = 68
FQ_BOSS_CHAMBER_CX  = 10   # circle centre x
FQ_BOSS_CHAMBER_CY  = 63   # circle centre y
FQ_BOSS_CHAMBER_R   = 5    # circle radius (tiles)

# Thornwarden body: 5-wide × 3-tall block at x 8-12, y 61-63
FQ_WARDEN_X0 = 8
FQ_WARDEN_X1 = 12
FQ_WARDEN_Y0 = 61
FQ_WARDEN_Y1 = 63

# Warden eye positions (zone-absolute coords)
FQ_WARDEN_EYE_NW = (FQ_WARDEN_X0, FQ_WARDEN_Y0)  # (8,  65)
FQ_WARDEN_EYE_NE = (FQ_WARDEN_X1, FQ_WARDEN_Y0)  # (12, 65)
FQ_WARDEN_EYE_SW = (FQ_WARDEN_X0, FQ_WARDEN_Y1)  # (8,  67)
FQ_WARDEN_EYE_SE = (FQ_WARDEN_X1, FQ_WARDEN_Y1)  # (12, 67)
FQ_WARDEN_EYE_POSITIONS: dict[str, tuple[int, int]] = {
    "NW": FQ_WARDEN_EYE_NW,
    "NE": FQ_WARDEN_EYE_NE,
    "SE": FQ_WARDEN_EYE_SE,
    "SW": FQ_WARDEN_EYE_SW,
}
FQ_WARDEN_EYE_CYCLE: tuple[str, ...] = ("NW", "NE", "SE", "SW")  # clockwise rotation
FQ_WARDEN_EYE_BY_POS: dict[tuple[int, int], str] = {
    v: k for k, v in FQ_WARDEN_EYE_POSITIONS.items()
}

# Boss door (locked exit at south end of chamber, opens on warden death)
FQ_BOSS_DOOR_X = 10
FQ_BOSS_DOOR_Y = FQ_BOSS_CHAMBER_Y1   # (10, 68)

# Warden loot chest (spawns at chamber centre after death)
FQ_BOSS_CHEST_X = 10
FQ_BOSS_CHEST_Y = 62

# Post-boss corridor to Y-fork (y 69-87)
FQ_POST_BOSS_Y0 = 69
FQ_POST_BOSS_Y1 = 87

# ── Y-fork gauntlet (y 88-108) ───────────────────────────────────────────────
FQ_FORK_Y0          = 88
FQ_FORK_LOBBY_Y     = 93    # wide 17-tile opening — all branches visible
FQ_FORK_BRANCH_Y0   = 94    # inner dividers appear; three distinct lanes
FQ_FORK_BRANCH_Y1   = 102   # side branches dead-end (chest at terminal tile)
FQ_FORK_Y1          = 108
FQ_FORK_LEFT_WALL_X  = 6    # wall col separating left branch from centre
FQ_FORK_RIGHT_WALL_X = 14   # wall col separating centre from right branch
FQ_FORK_CHEST_L = (4,  102)  # left branch dead-end reward chest
FQ_FORK_CHEST_R = (16, 102)  # right branch dead-end reward chest

# ── Canal puzzle (y 109-152) ─────────────────────────────────────────────────
FQ_CANAL_Y0          = 109
FQ_CANAL_ROOM_Y0     = 116   # wide puzzle room starts
FQ_CANAL_ROOM_Y1     = 143   # wide puzzle room ends
FQ_CANAL_TARGET_A    = (5,  121)  # left canal-block target (⭕)
FQ_CANAL_TARGET_B    = (15, 121)  # right canal-block target (⭕)
FQ_CANAL_BLOCK_A_START = (5,  135)  # canal block A initial position
FQ_CANAL_BLOCK_B_START = (15, 135)  # canal block B initial position
FQ_CANAL_GATE_X      = 10
FQ_CANAL_GATE_Y      = 144   # single-tile chokepoint gate (y=144 is x=10 only)
FQ_CANAL_RESET_X     = 10
FQ_CANAL_RESET_Y     = 116   # reset stone at canal room entrance
FQ_CANAL_Y1          = 152

# ── Final room (y 153-180) ───────────────────────────────────────────────────
FQ_FINAL_Y0             = 153
FQ_FINAL_ROOM_Y0        = 156   # wide final room starts (x=1-19)
FQ_ANCIENT_TREE_X       = 10
FQ_ANCIENT_TREE_Y       = 166
FQ_ANCIENT_TREE_CHEST_X = 10
FQ_ANCIENT_TREE_CHEST_Y = 169
FQ_ANCIENT_ENT_1        = (7,  161)
FQ_ANCIENT_ENT_2        = (13, 161)
FQ_ANCIENT_ENT_POSITIONS = [FQ_ANCIENT_ENT_1, FQ_ANCIENT_ENT_2]
FQ_FINAL_EXIT_X         = 10
FQ_FINAL_EXIT_Y         = 177
FQ_FINAL_Y1             = 180

# Puzzle log starting positions (zone-absolute coords)
FQ_LOG_A_START = (FQ_PUZZLE_X0 + 4, FQ_PUZZLE_Y0)        # zone (9,  18)
FQ_LOG_B_START = (FQ_PUZZLE_X0 + 6, FQ_PUZZLE_Y0)        # zone (11, 18)

# Logs are pushed directly into the stream — no orange target tiles in new design.
# Bridge requires one log in FQ_STREAM_Y (near) and one in FQ_STREAM_Y2 (far).

# ── Three-wall gate puzzle — v25 layout (30 obstacles, 62-push minimum solution) ──
#
#  Three complete horizontal walls, each with exactly ONE open gate column:
#    Wall 1  y=20  gate at col  5  (far left)
#    Wall 2  y=23  gate at col 15  (far right)
#    Wall 3  y=26  gate at col 10  (centre)
#
#  Both logs MUST zigzag: far-left → far-right → centre, then into the stream.
#  BFS-verified minimum solution: 62 pushes (either log can go first).
#
FQ_PUZZLE_OBSTACLES = frozenset({
    # ── Wall 1 (y=20): gate ONLY at col 5  (cols 6-15 blocked) ─────────────────
    (FQ_PUZZLE_X0 + 1, FQ_PUZZLE_Y0 + 2),   # (6,  20)
    (FQ_PUZZLE_X0 + 2, FQ_PUZZLE_Y0 + 2),   # (7,  20)
    (FQ_PUZZLE_X0 + 3, FQ_PUZZLE_Y0 + 2),   # (8,  20)
    (FQ_PUZZLE_X0 + 4, FQ_PUZZLE_Y0 + 2),   # (9,  20)
    (FQ_PUZZLE_X0 + 5, FQ_PUZZLE_Y0 + 2),   # (10, 20)
    (FQ_PUZZLE_X0 + 6, FQ_PUZZLE_Y0 + 2),   # (11, 20)
    (FQ_PUZZLE_X0 + 7, FQ_PUZZLE_Y0 + 2),   # (12, 20)
    (FQ_PUZZLE_X0 + 8, FQ_PUZZLE_Y0 + 2),   # (13, 20)
    (FQ_PUZZLE_X0 + 9, FQ_PUZZLE_Y0 + 2),   # (14, 20)
    (FQ_PUZZLE_X0 +10, FQ_PUZZLE_Y0 + 2),   # (15, 20)
    # ── Wall 2 (y=23): gate ONLY at col 15 (cols 5-14 blocked) ─────────────────
    (FQ_PUZZLE_X0 + 0, FQ_PUZZLE_Y0 + 5),   # (5,  23)
    (FQ_PUZZLE_X0 + 1, FQ_PUZZLE_Y0 + 5),   # (6,  23)
    (FQ_PUZZLE_X0 + 2, FQ_PUZZLE_Y0 + 5),   # (7,  23)
    (FQ_PUZZLE_X0 + 3, FQ_PUZZLE_Y0 + 5),   # (8,  23)
    (FQ_PUZZLE_X0 + 4, FQ_PUZZLE_Y0 + 5),   # (9,  23)
    (FQ_PUZZLE_X0 + 5, FQ_PUZZLE_Y0 + 5),   # (10, 23)
    (FQ_PUZZLE_X0 + 6, FQ_PUZZLE_Y0 + 5),   # (11, 23)
    (FQ_PUZZLE_X0 + 7, FQ_PUZZLE_Y0 + 5),   # (12, 23)
    (FQ_PUZZLE_X0 + 8, FQ_PUZZLE_Y0 + 5),   # (13, 23)
    (FQ_PUZZLE_X0 + 9, FQ_PUZZLE_Y0 + 5),   # (14, 23)
    # ── Wall 3 (y=26): gate ONLY at col 10 (cols 5-9 and 11-15 blocked) ────────
    (FQ_PUZZLE_X0 + 0, FQ_PUZZLE_Y0 + 8),   # (5,  26)
    (FQ_PUZZLE_X0 + 1, FQ_PUZZLE_Y0 + 8),   # (6,  26)
    (FQ_PUZZLE_X0 + 2, FQ_PUZZLE_Y0 + 8),   # (7,  26)
    (FQ_PUZZLE_X0 + 3, FQ_PUZZLE_Y0 + 8),   # (8,  26)
    (FQ_PUZZLE_X0 + 4, FQ_PUZZLE_Y0 + 8),   # (9,  26)
    (FQ_PUZZLE_X0 + 6, FQ_PUZZLE_Y0 + 8),   # (11, 26)
    (FQ_PUZZLE_X0 + 7, FQ_PUZZLE_Y0 + 8),   # (12, 26)
    (FQ_PUZZLE_X0 + 8, FQ_PUZZLE_Y0 + 8),   # (13, 26)
    (FQ_PUZZLE_X0 + 9, FQ_PUZZLE_Y0 + 8),   # (14, 26)
    (FQ_PUZZLE_X0 +10, FQ_PUZZLE_Y0 + 8),   # (15, 26)
})

# Ent starting positions in corridor (zone-absolute coords)
FQ_ENT_STARTS = [
    (9,  4),
    (11, 8),
    (8,  12),
    (12, 5),
]

# Walkable tile types inside the FQ zone
FQ_WALKABLE = frozenset({
    "fq_floor",
    "fq_puzzle_floor",
    "fq_stream_ford",
    "fq_log_target",        # Sokoban target marker
    "fq_reset",             # Sokoban reset stone
    "fq_grove_exit",
    "fq_exit",              # zone entry/exit
    "fq_warden_dead",       # collapsed warden rubble (walkable after boss death)
    "fq_boss_door_open",    # open exit door from boss chamber
    "fq_boss_chest",        # loot chest — walkable; interact opens it
    # Fork, canal, final room
    "fq_fork_chest",        # side-branch reward chest — walkable; interact loots it
    "fq_canal_floor",       # canal-aesthetic walkable floor
    "fq_canal_target",      # canal block target slot — walkable when no block on it
    "fq_canal_gate_open",   # opened canal gate
    "fq_canal_reset",       # canal reset stone
    "fq_ancient_tree",      # the ancient heart tree (interactable)
    "fq_ancient_tree_done", # post-activation state
    "fq_ancient_chest",     # final room reward chest
})

# Enemy stats — ent, snake, and ancient ent for the FQ zone
ENEMY_STATS.update({
    "ent":         (30, 10,  2, 40, 20),   # disguised as a tree; heavy, slow
    "snake":       (18,  9,  0, 12,  6),   # fast, low HP
    "ancient_ent": (90, 24, 10,  0,  0),   # ancient guardian; no gold, drops ent_core ×2
})
ENEMY_ABILITIES.update({
    "ent":         {"cobweb": False, "poison": False, "hit_run": False, "roar": True,  "slam": True,  "ranged": False},
    "snake":       {"cobweb": False, "poison": True,  "hit_run": True,  "roar": False, "slam": False, "ranged": False},
    "ancient_ent": {"cobweb": False, "poison": False, "hit_run": False, "roar": True,  "slam": True,  "ranged": False},
})

# Thornwarden miniboss — defeated via slingshot (eye mechanic), not standard combat
FQ_WARDEN_THORN_DAMAGE_MIN = 8   # damage if player fires outside open window
FQ_WARDEN_THORN_DAMAGE_MAX = 12
# Time-based eye rotation (replaces move-based turn system)
FQ_WARDEN_EYE_DURATION  = 1.0    # seconds each eye stays active before rotating
FQ_WARDEN_EYE_WARN_SEC  = 0.25   # opening 0.25 s shows 🟡 warning before 👁️ opens

# Ent Core drop quantities
FQ_ENT_CORE_DROP_ENT      = 1   # regular ent drops
FQ_ENT_CORE_DROP_WARDEN   = 4   # Thornwarden drops
FQ_ENT_CORE_DROP_ANCIENT  = 2   # ancient ents in the final room

# Consumable items: shown in combat food menu
# "escape": True  → guaranteed combat escape with no parting blow (e.g. Coward's Ale)
CONSUMABLE_ITEMS = {
    "fish":         {"hp": 5,   "desc": "+5 HP"},
    "cooked_fish":  {"hp": 15,  "desc": "+15 HP"},
    "bread":        {"hp": 10,  "desc": "+10 HP"},
    "meat_stew":    {"hp": 20,  "desc": "+20 HP"},
    "cowards_ale":  {"hp": 0,   "desc": "Guaranteed escape — no parting blow", "escape": True},
    "forest_nut":   {"hp": 3,   "desc": "+3 HP"},
    "roasted_nut":  {"hp": 6,   "desc": "+6 HP"},
    "baked_potato": {"hp": 5,   "desc": "+5 HP"},
    "carrot":       {"hp": 3,   "desc": "+3 HP"},
}

# Tavern food/drink menu (price in gold)
TAVERN_MENU = [
    {"id": "bread",       "name": "Bread",        "price": 4,  "hp": 10, "emoji": "\U0001F35E", "description": "A fresh loaf. Restores 10 HP."},
    {"id": "ale",         "name": "Ale",           "price": 6,  "hp": 0,  "emoji": "\U0001F37A", "description": "A cold pint. No HP, but it hits the spot."},
    {"id": "meat_stew",   "name": "Meat Stew",     "price": 10, "hp": 20, "emoji": "\U0001F372", "description": "Hearty bowl of stew. Restores 20 HP."},
    {"id": "cowards_ale", "name": "Coward's Ale",  "price": 10, "hp": 0,  "emoji": "\U0001F37A", "description": "Guaranteed escape from combat — no parting blow."},
]

# Farm animal types for farmhouse enclosures
FARM_ANIMALS = ["vil_cow", "vil_pig", "vil_chicken", "vil_goat", "vil_sheep"]

# Farmer shop catalog (price in gold)
FARMER_SHOP = [
    {"id": "wheat_seed",   "name": "Wheat Seeds",  "price": 3},
    {"id": "carrot_seed",  "name": "Carrot Seeds", "price": 3},
    {"id": "potato",       "name": "Potato (seed)", "price": 3},
    {"id": "hoe",          "name": "Hoe",          "price": 20},
    {"id": "watering_can", "name": "Watering Can", "price": 35},
    {"id": "dry_grass",    "name": "Hay",          "price": 1},
    {"id": "plant_fiber",  "name": "Fiber",        "price": 3},
    {"id": "healing_herb", "name": "Herb",         "price": 8},
]

# Armory shop catalog (price in gold)
ARMORY_CATALOG = [
    {"id": "bomb",          "name": "Bomb",           "price": 50,
     "description": "A lit fuse short. Explodes in a 5-tile cross pattern after a short delay."},
    {"id": "flint_and_steel","name": "Flint & Steel", "price": 30,
     "description": "Ignites bombs. Craft it yourself from flint + iron ingot, or buy one here."},
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
    # Wayerwood attunement — press a stone into the rod (cave chambers)
    frozenset({("wayerwood", 1), ("rock", 1)}):                  {"result": "attuned_wayerwood", "qty": 1, "label": "🪄 Attune (Cave)"},
    # Wayerwood forest attunement — bind a pinecone to the rod (forest chambers)
    frozenset({("wayerwood", 1), ("pinecone", 1)}):              {"result": "attuned_wayerwood", "qty": 1, "label": "🪄 Attune (Forest)"},
    frozenset({("attuned_wayerwood", 1), ("pinecone", 1)}):      {"result": "attuned_wayerwood", "qty": 1, "label": "🪄 Re-attune (Forest)"},
    # Forest Heart Amulet — compressed ent life-force woven into a charm
    frozenset({("ent_core", 4), ("living_root", 2)}):            {"result": "forest_heart_amulet", "qty": 1, "label": "💚 Forest Heart Amulet"},
    # Roasted Nut — torch-toast a forest nut for extra HP
    frozenset({("forest_nut", 1), ("torch", 1)}):                {"result": "roasted_nut",         "qty": 1, "label": "🥜 Roast Nut"},
}

# Terrain that blocks movement inside the combat arena
ARENA_IMPASSABLE = {
    "mountain", "snow", "dense_forest",
    "stone_wall", "b_wall", "void", "cave_rock",
    "river", "deep_water", "shallow_water",
    "fst_tree",   # forest tree-walls block movement in forest arenas
    # Note: ocean combat (high seas) spawns on water — separate arena type
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
    # Gear machine panel (interactable — opens the gear puzzle viewport)
    "gear_machine":           "⚙️",
    # ── Gear slot tiles — used inside the machine viewport ─────────────────────
    # Empty sockets — use gear_socket custom emoji if uploaded, else ⭕
    "gear_slot_s_empty":      _ge("gear_socket", "⭕"),
    "gear_slot_l_empty":      _ge("gear_socket", "⭕"),
    # Small gear — spinning (animated CW / CCW)
    "gear_slot_s_cw":         _ge("gear_small",         "⚙️"),
    "gear_slot_s_ccw":        _ge("gear_small_reverse", "⚙️"),
    # Small gear — still (not connected to power)
    "gear_slot_s_still":      _ge("gear_small_still",   "⚙️"),
    # Large gear — spinning clockwise (2×2)
    "gear_slot_l_cw_tl":      _ge("gear_top_left",            "🔩"),
    "gear_slot_l_cw_tr":      _ge("gear_top_right",           "🔩"),
    "gear_slot_l_cw_bl":      _ge("gear_bottom_left",         "🔩"),
    "gear_slot_l_cw_br":      _ge("gear_bottom_right",        "🔩"),
    # Large gear — spinning counter-clockwise (2×2)
    "gear_slot_l_ccw_tl":     _ge("gear_top_left_reverse",    "🔩"),
    "gear_slot_l_ccw_tr":     _ge("gear_top_right_reverse",   "🔩"),
    "gear_slot_l_ccw_bl":     _ge("gear_bottom_left_reverse", "🔩"),
    "gear_slot_l_ccw_br":     _ge("gear_bottom_right_reverse","🔩"),
    # Large gear — still / not connected to power (2×2)
    "gear_slot_l_still_tl":   _ge("gear_top_left_still",      "🔩"),
    "gear_slot_l_still_tr":   _ge("gear_top_right_still",     "🔩"),
    "gear_slot_l_still_bl":   _ge("gear_bottom_left_still",   "🔩"),
    "gear_slot_l_still_br":   _ge("gear_bottom_right_still",  "🔩"),
}

TEMPLE_WALKABLE: frozenset[str] = frozenset({
    "temple_floor", "temple_entrance",
    "temple_altar", "temple_portal_locked", "temple_portal_open",
    "temple_rune",
    "gear_machine",   # player steps onto the machine panel to open the puzzle UI
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
    "gear_machine": [
        "⚙️ A wall-mounted gear mechanism. Heavy iron brackets hold four sockets of varying size.",
        "⚙️ Faded engravings around each socket show small and large gear outlines. The machine awaits its gears.",
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

# --- Forest Interior System ---

FOREST_EMOJI: dict[str, str] = {
    # Interior floor / wall
    "fst_floor":        "\U0001F7E9",   # 🟩 forest floor (overridable with :fst_floor:)
    "fst_tree":         "\U0001F333",   # 🌳 impassable ancient tree wall
    # Special tiles
    "fst_exit":         "\U0001F6AA",   # 🚪 forest exit (returns to overworld)
    "fst_tree_city":    "\U0001F3E1",   # 🏡 tree city hub tile (shop)
    "fst_ancient_tree": "\U0001F332",   # 🌲 ancient watering tree (interact with can)
    "fst_maze_door":    "\U0001F300",   # 🌀 entrance to maze branch
    "fst_nut_tree":     "\U0001F330",   # 🌰 nut tree (interact to gather forest nuts)
    "fst_chest":        "\U0001F4E6",   # 📦 chest (overridable with :chest:)
    "fst_map_chest":    "\U0001F4E6",   # 📦 map chest — looks like a regular chest
    "fst_mimic":        "\U0001F4E6",   # 📦 mimic — identical look to fst_chest, by design
    # Hermit hut
    "fst_hermit_house":  "\U0001F6D6",  # 🛖 hermit's hut tile in the forest
    # Bomb (shared with cave / overworld)
    "bomb_lit":          "\U0001F4A3",  # 💣 lit bomb placed on the forest floor
    # Hidden chamber tiles
    "fst_secret_wall":   "\U0001F333",  # 🌳 looks identical to fst_tree (hidden passage)
    "fst_chamber_floor": "\U0001F7E9",  # 🟩 chamber interior floor
    "fst_chamber_chest": "\U0001F48E",  # 💎 hidden chamber treasure chest
    # Maze tiles
    "maze_wall":        "\U0001F333",   # 🌳 dense forest wall (impassable)
    "maze_floor":       "\U0001F7E9",   # 🟩 maze passage
    "maze_exit":        "\U0001F6AA",   # 🚪 maze exit (returns to forest)
    "maze_chest":       "\U0001F4B0",   # 💰 maze treasure chest
    "maze_mimic":       "\U0001F4B0",   # 💰 mimic — identical look to maze_chest, by design
    # Forest enemy icons (displayed in viewport encounters are handled by ENTITY_EMOJI,
    # but keep here so load_forest_viewport can render them as floor sub-tiles)
    "forest_sprite":   "\U0001F9DA",
    "vine_creeper":    "\U0001F40D",
    "corrupted_dryad": "\U0001F9DF",
    "forest_troll":    "\U0001F479",
}

FOREST_WALKABLE: frozenset[str] = frozenset({
    "fst_floor", "fst_exit", "fst_tree_city",
    "fst_maze_door", "fst_nut_tree", "fst_chest", "fst_mimic", "fst_map_chest",
    "fst_hermit_house",
    "fst_secret_wall", "fst_chamber_floor", "fst_chamber_chest",
    "bomb_lit",         # placed lit bomb — walkable (blast imminent)
})

MAZE_WALKABLE: frozenset[str] = frozenset({
    "maze_floor", "maze_exit", "maze_chest", "maze_mimic",
})

# Tree City interior tiles
TC_W  = 29    # floor width (was 15)
TC_H  = 25    # floor height (was 7)
TC_NUM_FLOORS = 4  # was 3

TC_EMOJI: dict[str, str] = {
    "tc_floor":      "\U0001F7EB",          # 🟫 wooden planks
    "tc_wall":       "\U0001FAB5",          # 🪵 log wall
    "tc_stair_up":   "\U0001F53C",          # 🔼 stairs up (overridable with :staircase:)
    "tc_stair_down": "\U0001F53D",          # 🔽 stairs down (overridable with :staircase:)
    "tc_door":       "\U0001F6AA",          # 🚪 exit door (ground floor only)
    "tc_shop":       "\U0001F9D1",          # 🧑 merchant NPC (approach from adjacent)
    "tc_villager":   "\U0001F9D4",          # 🧔 quest villager (approach from adjacent)
    "tc_elder":      "\U0001F9D9",          # 🧙 elder NPC (approach from adjacent)
    "tc_archivist":  "\U0001F4DC",          # 📜 The Archivist — recurring antagonist NPC
    "tc_bed":        "\U0001F6CF️",    # 🛏️ bed (walkable, rest/heal)
    "tc_counter":    "\U0001F9F1",          # 🧱 shop counter
    "tc_rug":        "\U0001F7E5",          # 🟥 decorative rug (walkable)
    "tc_table":      "\U0001FAB5",          # 🪵 wooden table
    "tc_lantern":    "\U0001F56F️",    # 🕯️ lantern
    "tc_plant":      "\U0001F33F",          # 🌿 plant
    "tc_barrel":     "\U0001F6E2️",    # 🛢️ barrel
    "tc_bookshelf":  "\U0001F4DA",          # 📚 bookshelf
    "tc_shrine":     "⛩️",        # ⛩️ shrine
}

# ── Grove biome tiles ──────────────────────────────────────────────────────────
GROVE_W = 19
GROVE_H = 19

GROVE_EMOJI: dict[str, str] = {
    "grove_floor":  "\U0001F7E9",   # 🟩 mossy ground
    "grove_wall":   "\U0001F333",   # 🌳 ancient tree
    "grove_statue": "\U0001F5FF",   # 🗿 statue
    "grove_exit":   "\U0001F6AA",   # 🚪 portal back
}

GROVE_WALKABLE: frozenset[str] = frozenset({"grove_floor", "grove_exit"})

# ── Bandit Camp Interior ──────────────────────────────────────────────────────
BANDIT_CAMP_SIZE = 11  # 11×11 interior grid

BANDIT_CAMP_EMOJI: dict[str, str] = {
    "bc_void":      "⬛",            # ⬛ empty outside
    "bc_dirt":      "\U0001F7EB",        # 🟫 walkable floor
    "bc_fence":     "\U0001F9F1",        # 🧱 wooden fence/wall
    "bc_tent":      "⛺",            # ⛺ tent (non-walkable)
    "bc_campfire":  "\U0001F525",        # 🔥 campfire (non-walkable)
    "bc_bandit":    "\U0001F9B9",        # 🦹 bandit NPC (walkable, proximity trigger)
    "bc_exit":      "\U0001F6AA",        # 🚪 camp exit (step to leave)
    "bc_crate":     "\U0001F4E6",        # 📦 loot crate (non-walkable)
    "bc_log":       "\U0001FAB5",        # 🪵 log pile (non-walkable)
}

BANDIT_CAMP_WALKABLE: frozenset[str] = frozenset({
    "bc_dirt",
    "bc_bandit",   # walkable — proximity check triggers combat
    "bc_exit",     # stepping on exit triggers leaving the camp
})

# ── Warp Crystal destinations ──────────────────────────────────────────────────
# Unlocked progressively; all initial three unlock when the crystal is first obtained.
WAYPOINTS: dict[str, dict] = {
    "spawn":  {"name": "The World's Navel",  "emoji": "🌍",
               "desc": "Where all journeys begin — the heart of the overworld."},
    "forest": {"name": "The Elder Bough",    "emoji": "🌲",
               "desc": "Gateway to the ancient forest, where the wayerwood grows."},
    "grove":  {"name": "The Still Grove",    "emoji": "✨",
               "desc": "The sacred clearing where the wayerwood rests."},
}

TC_WALKABLE: frozenset[str] = frozenset({
    "tc_floor", "tc_rug", "tc_door", "tc_stair_up", "tc_stair_down", "tc_bed",
    # Note: tc_shop and tc_elder are NOT walkable — player approaches from adjacent
})

# Random encounter rates inside forest (chance per step)
FOREST_ENCOUNTER_MOBS = {
    "forest_sprite":   0.08,
    "vine_creeper":    0.07,
    "corrupted_dryad": 0.05,
    "forest_troll":    0.03,
    "ent":             0.02,
}

# Tree city merchant shop (unique items, gold prices)
TREE_CITY_SHOP = [
    {"id": "forest_nut",   "name": "Forest Nut",   "price": 5,
     "description": "A sweet nut from the ancient canopy. Restores 8 HP."},
    {"id": "living_root",  "name": "Living Root",  "price": 20,
     "description": "A glowing root still warm with forest magic. Crafting ingredient."},
    {"id": "bark_shield",  "name": "Bark Shield",  "price": 80,
     "description": "Woven from enchanted bark. Sturdy and surprisingly light. +3 defense."},
]

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
    # Rift archivist NPC (approached from adjacent, not walkable)
    "rift_archivist":     "\U0001F4DC",            # 📜 The Archivist in the past
    # Boss room tiles
    "cave_boss_door":     "\U0001F512",            # 🔒 sealed stone door (requires cave key)
    "cave_boss_floor":    "\U0001F7E5",            # 🟥 red — boss chamber floor
    "cave_boss_trigger":  "\U0001F7E5",            # 🟥 same look as floor — triggers boss fight
    "cave_boss_chest":    "\U0001F4B0",            # 💰 boss treasure (gold bag)
    # Bombable walls system
    "cracked_stone":      "⬛",               # ⬛ looks identical to stone_wall — visually hidden!
    "bomb_lit":           "\U0001F4A3",            # 💣 placed lit bomb (walkable, about to explode)
    "hidden_chamber_entrance": "\U0001F7EB",       # 🟫 opened chamber floor (was cracked_stone)
    # Ground drops (mirrors TERRAIN_EMOJI so cave renderer can find it)
    "drop_box":           "\U0001F4E6",            # 📦 dropped item box in cave
}

CAVE_WALKABLE = {"stone_floor", "cave_entrance", "cave_chest", "cave_chest_medium", "cave_chest_large", "cave_stairdown", "cave_stairup", "player_house_cave",
                 "rift_floor", "rift_entrance", "rift_deposit",
                 # Lava cave tiles
                 "lava_floor", "lava_bridge",
                 # Boss room tiles (door is walkable so key-check logic runs inside the movement loop)
                 "cave_boss_door", "cave_boss_floor", "cave_boss_trigger", "cave_boss_chest",
                 # Bomb system (lit bomb tile is walkable; cracked_stone is NOT — it's a wall)
                 "bomb_lit", "hidden_chamber_entrance",
                 # Ground drops in cave (walk onto to pick up)
                 "drop_box"}
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

CAVE_CHEST_TYPES = {"cave_chest", "cave_chest_medium", "cave_chest_large", "cave_boss_chest"}

CAVE_ENEMY_TYPES = {"cave_bat", "cave_spider", "cave_golem", "cave_troll", "cave_wyvern"}

# Chest loot tiers: (weight, gold_min, gold_max, xp_min, xp_max, item_or_none)
CHEST_LOOT = [
    (50, 10,  40,  5,  20, None),
    (30, 30,  80,  15, 40, "cooked_fish"),
    (15, 60,  130, 30, 60, "gem"),
    (5,  100, 250, 50, 100, "sword"),
]

# Boss chest loot: (weight, item_or_none) — always 150-350 gold + one of these items
BOSS_CHEST_LOOT = [
    (40, "gem"),
    (30, "sword"),
    (15, "iron_helmet"),
    (15, "iron_chestplate"),
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
    "vil_lumber_mill":  "\U0001FA9A",  # 🪚  waterwheel lumber mill
    "vil_farmhouse":    "🏡",        # 🏡  farmhouse
    "vil_armory":       "\U0001F6E1️",  # 🛡️  armory
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
    "drop_box":         "\U0001F4E6",        # 📦  player-dropped items
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
    "b_saw":            "\U0001FA9A",  # 🪚  saw
    "b_log_moving":     "\U0001FAB5",  # 🪵  log in transit through conveyor (pre-saw)
    "b_plank_moving":   "\U0001FAB5",  # 🪵  plank in transit through conveyor (post-saw, overridden with :planks:)
    "b_lumber_npc":     "🧑",       # 🧑  lumber mill worker
    "b_farmer_npc":     "🧑",       # 🧑  farmer NPC
    "b_water":          "🌊",       # 🌊  water tile (lumber mill)
    # Large gear (2×2) — sits in water columns
    "b_gear_tl":        _ge("gear_top_left",    "⚙️"),   # large gear top-left
    "b_gear_tr":        _ge("gear_top_right",   "⚙️"),   # large gear top-right
    "b_gear_bl":        _ge("gear_bottom_left", "⚙️"),   # large gear bottom-left
    "b_gear_br":        _ge("gear_bottom_right","⚙️"),   # large gear bottom-right
    # Small gear — driven by large gear, drives conveyor
    "b_gear_small":     _ge("gear_small_reverse", "⚙️"),  # small gear (CCW)
    # Conveyor belt tiles
    "b_conveyor":       "🟫",       # 🟫  conveyor belt segment
    "b_log_input":      "📥",       # 📥  log insertion point (inbox)
    "b_plank_output":   "📤",       # 📤  plank pickup point (outbox)
    # Player-house chests
    # Player-house chests
    "ph_chest_small":     "\U0001F4E6",       # 📦
    "ph_chest_medium":    "\U0001F5C4\uFE0F", # 🗄️
    "ph_chest_large":     "\U0001F9F3",       # 🧳
    # Armory unique
    "b_armory_npc":       "🧑",              # 🧑  armorer NPC
    "b_weapons_rack":     "\U0001F5E1️", # 🗡️  weapons rack (decoration)
    "b_ammo_shelf":       "\U0001F4A3",       # 💣  ammo/bomb shelf (decoration)
    # Hermit Hut unique
    "hermit_npc":         "\U0001F9D9",       # 🧙  hermit / old wizard NPC
    "hut_stair_up":       "\U0001F53C",       # 🔼  staircase up
    "hut_stair_down":     "\U0001F53D",       # 🔽  staircase down
    "b_vines":            "\U0001F33F",       # 🌿  creeping vines (walkable decoration)
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
    "vil_pen_grass",       # pen interior ground (walkable)
    "vil_cow", "vil_pig", "vil_chicken", "vil_goat", "vil_sheep",  # animals are walkable
    "vil_puzzle_board",   # puzzle board — walkable, triggers puzzle UI
    "vil_armory",         # enterable armory building
    "drop_box",           # player-dropped items box — walkable, triggers pickup
    # Note: vil_fence is a solid obstacle (not walkable)
    # Note: "vil_water" is intentionally absent — impassable harbour water
}

BUILDING_WALKABLE = {
    "b_floor", "b_floor_wood", "b_door",
    "b_priest", "b_bank_npc", "b_shop_npc", "b_blacksmith_npc",
    "b_pew", "b_table", "b_bed",
    "b_barkeep", "b_tavern_npc", "b_healer", "b_barrel", "b_bar_counter", "b_medicine_shelf",
    "b_anvil", "b_chair", "b_bookshelf", "b_candle",
    "b_chest", "b_resident", "b_pet",
    "b_waterwheel", "b_lumber_npc", "b_farmer_npc",
    "b_crew_npc",   # harbour tavern recruit NPC — walkable
    # Note: b_water, b_saw, b_conveyor, b_log_input, b_plank_output are NOT walkable
    # (player interacts with conveyor line by standing adjacent to input/output boxes)
    # Note: b_gear_tl/tr/bl/br are NOT walkable (they sit in the water columns)
    "ph_chest_small", "ph_chest_medium", "ph_chest_large",
    "b_armory_npc",   # armorer NPC — walkable
}

# Walkable tiles inside the hermit hut (floor 1 and floor 2)
HERMIT_HUT_WALKABLE: frozenset[str] = frozenset({
    "b_floor_wood", "b_floor",
    "b_door",            # exit door — player can step on it (triggers exit)
    "b_bookshelf", "b_table", "b_bed", "b_chair", "b_candle",
    "hermit_npc",        # walkable NPC tile (interact via adjacent action)
    "hut_stair_up",      # staircase up to floor 2
    "hut_stair_down",    # staircase down to floor 1
    "b_vines",           # decorative vines — passable
})

VILLAGE_MIN_SIZE = 32
VILLAGE_MAX_SIZE = 32

# --- Items & Equipment ---

SHOP_CATALOG = [
    {
        "id": "knife",
        "name": "Knife",
        "emoji": "\U0001F52A",
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
        "emoji": "\U0001F97E",   # 🥾 hiking boot
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
    # "canoe" is intentionally NOT in this dict — canoe is a world item,
    # not equippable gear; it lives only in the inventory grid.
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
    "wayerwood":           "hand",
    "attuned_wayerwood":   "hand",
    "flint_and_steel":     "hand",
    "bomb":                "hand",
    "hoe":                 "hand",
    "hammer":              "hand",
    "bark_shield":         "hand",
    "forest_heart_amulet": "accessory",
}

# Items that occupy both hand slots
TWO_HANDED_ITEMS: set[str] = set()  # shovel is now 1-handed

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
    "bomb":                {},
    "arrow":               {},
    "hoe":                 {},
    "bark_shield":         {"defense": 3},
    "forest_heart_amulet": {"max_hp": 15},
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

# Surface encounters: terrain → [(enemy_type, weight), ...]  (1% chance per step)
# weights are relative (not %; they are normalised at runtime by random.choices)
SURFACE_ENCOUNTER_MOBS = {
    "plains":       [("wolf", 55), ("bandit", 45)],
    "grass":        [("wolf", 55), ("bandit", 45)],
    "sand":         [("wolf", 70), ("bandit", 30)],
    "hills":        [("bear", 65), ("wolf", 20), ("bandit", 15)],
    "forest":       [("wolf", 50), ("bandit", 30), ("bear", 20)],
    "dense_forest": [("bear", 60), ("wolf", 30), ("bandit", 10)],
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
    "wheat":             3,
    "carrot":            3,
    "potato":            3,
    "baked_potato":      4,
    "hoe":               12,
    "breath_of_the_sea": 30,
    "gust_of_aevos":     20,
    "gold_coin":         1,
    "seaweed":           3,
    # Forest items
    "forest_nut":             3,
    "roasted_nut":            6,
    "living_root":            10,
    "bark_shield":            48,
    "ancient_seed":           25,
    "ancient_log":            30,
    "ent_core":               28,
    "forest_heart_amulet":    380,
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
    "ancient_sapling": (60, 160, 60),
    "ancient_tree_top_left":     (30, 90, 30),
    "ancient_tree_top_right":    (30, 90, 30),
    "ancient_tree_bottom_left":  (30, 90, 30),
    "ancient_tree_bottom_right": (30, 90, 30),
    "dirt": (130, 90, 50),
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
    # Build separate caches for static and animated emojis
    cache = {}
    for e in guild_emojis:
        fmt = f"<a:{e.name}:{e.id}>" if getattr(e, "animated", False) else f"<:{e.name}:{e.id}>"
        cache[e.name] = fmt

    _replace = [
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
        (VILLAGE_EMOJI,  "vil_pen_grass",     "grass"),
        (VILLAGE_EMOJI,  "vil_fence",         "fence"),
        (VILLAGE_EMOJI,  "vil_fence_gate",    "fence_gate"),
        (VILLAGE_EMOJI,  "vil_farmland",      "farmland"),
        (VILLAGE_EMOJI,  "vil_seeds_wheat",   "farmland_seeds"),
        (VILLAGE_EMOJI,  "vil_seeds_carrot",  "farmland_seeds"),
        (VILLAGE_EMOJI,  "vil_seeds_potato",  "farmland_seeds"),
        # Forest entrance custom emoji
        (STRUCTURE_EMOJI, "forest_entrance",  "forest_entrance"),
        # Hills custom emoji
        (TERRAIN_EMOJI,   "hills",            "hills"),
        # Canoe drop box uses canoe_whole custom emoji
        (TERRAIN_EMOJI,   "canoe_box",        "canoe_whole"),
        # Village house chest uses custom chest emoji
        (BUILDING_EMOJI,  "b_chest",          "chest"),
        # Lumbermill large gear tiles
        (BUILDING_EMOJI,  "b_gear_tl",        "gear_top_left"),
        (BUILDING_EMOJI,  "b_gear_tr",        "gear_top_right"),
        (BUILDING_EMOJI,  "b_gear_bl",        "gear_bottom_left"),
        (BUILDING_EMOJI,  "b_gear_br",        "gear_bottom_right"),
        # Lumbermill small gear tile (CCW)
        (BUILDING_EMOJI,  "b_gear_small",     "gear_small_reverse"),
        # Lumbermill conveyor: plank-in-transit uses :planks: custom emoji
        (BUILDING_EMOJI,  "b_plank_moving",   "planks"),
        # Ancient 2×2 tree tiles
        (TERRAIN_EMOJI, "ancient_tree_top_left",     "ancient_tree_top_left"),
        (TERRAIN_EMOJI, "ancient_tree_top_right",    "ancient_tree_top_right"),
        (TERRAIN_EMOJI, "ancient_tree_bottom_left",  "ancient_tree_bottom_left"),
        (TERRAIN_EMOJI, "ancient_tree_bottom_right", "ancient_tree_bottom_right"),
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
        # Hoe
        ("hoe",          "hoe"),
        # Watering can
        ("watering_can", "watering_can"),
        # Plank (sawn lumber)
        ("plank",        "planks"),
        # Iron sword / cannonball / iron nails
        ("sword",        "sword_iron"),
        ("cannonball",   "cannonball"),
        ("nail",         "nails_iron"),
        # Wyvern armor pieces
        ("wyvern_helmet",     "helmet_wyvern"),
        ("wyvern_chestplate", "chestpiece_wyvern"),
        ("wyvern_leggings",   "leggings_wyvern"),
        ("wyvern_boots",      "boots_wyvern"),
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

    # ── Gear emojis — update TEMPLE_EMOJI and ITEM_EMOJI entries ──────────────
    # Maps TEMPLE_EMOJI tile key → emoji name on the server
    _gear_tile_map: list[tuple[str, str]] = [
        # Spinning variants
        ("gear_slot_s_cw",         "gear_small"),
        ("gear_slot_s_ccw",        "gear_small_reverse"),
        ("gear_slot_s_still",      "gear_small_still"),
        ("gear_slot_l_cw_tl",      "gear_top_left"),
        ("gear_slot_l_cw_tr",      "gear_top_right"),
        ("gear_slot_l_cw_bl",      "gear_bottom_left"),
        ("gear_slot_l_cw_br",      "gear_bottom_right"),
        ("gear_slot_l_ccw_tl",     "gear_top_left_reverse"),
        ("gear_slot_l_ccw_tr",     "gear_top_right_reverse"),
        ("gear_slot_l_ccw_bl",     "gear_bottom_left_reverse"),
        ("gear_slot_l_ccw_br",     "gear_bottom_right_reverse"),
        # Still variants — server may have gear_top_left_still etc.
        ("gear_slot_l_still_tl",   "gear_top_left_still"),
        ("gear_slot_l_still_tr",   "gear_top_right_still"),
        ("gear_slot_l_still_bl",   "gear_bottom_left_still"),
        ("gear_slot_l_still_br",   "gear_bottom_right_still"),
    ]
    for tile_key, emoji_name in _gear_tile_map:
        if emoji_name in cache:
            TEMPLE_EMOJI[tile_key] = cache[emoji_name]

    # Item icon for small_gear and large_gear both use the still (non-animated) variant
    if "gear_small_still" in cache:
        ITEM_EMOJI["small_gear"] = cache["gear_small_still"]
        ITEM_EMOJI["large_gear"] = cache["gear_small_still"]
        _renderer._ITEM_SLOT_EMOJI["small_gear"] = cache["gear_small_still"]
        _renderer._ITEM_SLOT_EMOJI["large_gear"] = cache["gear_small_still"]
    elif "gear_small" in cache:
        ITEM_EMOJI["small_gear"] = cache["gear_small"]
        ITEM_EMOJI["large_gear"] = cache["gear_small"]
        _renderer._ITEM_SLOT_EMOJI["small_gear"] = cache["gear_small"]
        _renderer._ITEM_SLOT_EMOJI["large_gear"] = cache["gear_small"]

    # Forest floor and chest overrides
    if "chest" in cache:
        FOREST_EMOJI["fst_chest"] = cache["chest"]
        FOREST_EMOJI["maze_chest"] = cache["chest"]
        FOREST_EMOJI["fst_mimic"] = cache["chest"]     # same look as fst_chest by design
        FOREST_EMOJI["fst_map_chest"] = cache["chest"] # map chest looks identical to regular chest
    if "fst_floor" in cache:
        FOREST_EMOJI["fst_floor"] = cache["fst_floor"]
    # Tree city staircase custom emoji
    if "staircase" in cache:
        TC_EMOJI["tc_stair_up"]   = cache["staircase"]
        TC_EMOJI["tc_stair_down"] = cache["staircase"]

    # Canoe 2-piece custom emojis — left half, right half, and whole (on-water player icon)
    for canoe_key in ("canoe_left", "canoe_right", "canoe_whole"):
        if canoe_key in cache:
            ITEM_EMOJI[canoe_key] = cache[canoe_key]
            _renderer._ITEM_SLOT_EMOJI[canoe_key] = cache[canoe_key]
    # The single 'canoe' item (used in the equipped row and other single-emoji
    # contexts) uses the canoe_whole custom emoji when available.
    if "canoe_whole" in cache:
        ITEM_EMOJI["canoe"] = cache["canoe_whole"]
        _renderer._ITEM_SLOT_EMOJI["canoe"] = cache["canoe_whole"]

    # Empty gear socket custom emoji
    if "gear_socket" in cache:
        TEMPLE_EMOJI["gear_slot_s_empty"] = cache["gear_socket"]
        TEMPLE_EMOJI["gear_slot_l_empty"] = cache["gear_socket"]

    # Iron armor custom emojis
    _iron_armor_map = [
        ("iron_boots",       "boots_iron"),
        ("iron_chestplate",  "chestpiece_iron"),
        ("iron_leggings",    "leggings_iron"),
        ("iron_helmet",      "helmet_iron"),
    ]
    for item_key, emoji_name in _iron_armor_map:
        if emoji_name in cache:
            ITEM_EMOJI[item_key] = cache[emoji_name]
            _renderer._ITEM_SLOT_EMOJI[item_key] = cache[emoji_name]



