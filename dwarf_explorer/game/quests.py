"""Quest generation, pool management, and progress tracking.

Quest sources:
  village_npc — 3 quests per village, 24-hour pool refresh.
  bounty      — 3 overworld kill-bounties with map markers, 24-hour refresh.
  merchant    — 1 delivery quest offered during travelling-merchant encounter.

Quest subtypes:
  kill          — defeat N of enemy_type; progress auto-tracks on combat win.
  fetch         — bring N of item_id to village NPC; checked at turn-in.
  investigation — visit a structure at location_x/y; auto-completes on arrival.
  delivery      — carry merchant_parcel to destination village; auto-completes on entry.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, UTC

from dwarf_explorer.config import WORLD_SIZE


# ── Pool refresh interval ──────────────────────────────────────────────────────
POOL_TTL_HOURS = 24
MAX_PLAYER_QUESTS = 5

# ── Enemy display names ────────────────────────────────────────────────────────
_ENEMY_NAMES = {
    "wolf":        "Wolves",
    "bear":        "Bears",
    "cave_spider": "Cave Spiders",
    "spider":      "Spiders",
    "shark":       "Sharks",
    "crab":        "Crabs",
    "sea_serpent": "Sea Serpents",
    "temporal_echo": "Temporal Echoes",
}

# ── Item display names ─────────────────────────────────────────────────────────
_ITEM_NAMES = {
    "log":        "Logs",
    "stone":      "Stones",
    "fish":       "Fish",
    "cooked_fish": "Cooked Fish",
    "iron_ore":   "Iron Ore",
    "dry_grass":  "Dry Grass",
    "plant_fiber": "Plant Fiber",
    "resin":      "Tree Resin",
    "gold_ore":   "Gold Ore",
    "wheat":      "Wheat",
    "carrot":     "Carrots",
    "potato":     "Potatoes",
}

# ── Quest templates ────────────────────────────────────────────────────────────

_VILLAGE_KILL_TEMPLATES = [
    {
        "target_id": "wolf",
        "count_range": (4, 8),
        "title": "Wolf Culling",
        "descriptions": [
            "Wolves have been preying on livestock near the village. Cull the pack.",
            "The eastern farms are under threat from a wolf pack. Thin their numbers.",
        ],
        "reward_gold_base": 30,
        "reward_xp_base": 180,
    },
    {
        "target_id": "bear",
        "count_range": (2, 4),
        "title": "Bear Threat",
        "descriptions": [
            "A bear has been raiding our food stores. Put it down before winter.",
            "The forest trail is blocked by an aggressive bear. Clear the path.",
        ],
        "reward_gold_base": 55,
        "reward_xp_base": 300,
    },
    {
        "target_id": "spider",
        "count_range": (5, 10),
        "title": "Spider Infestation",
        "descriptions": [
            "Giant spiders have nested near the village. We need an exterminator.",
            "Spiders have been plaguing our woodcutters. Deal with the nest.",
        ],
        "reward_gold_base": 25,
        "reward_xp_base": 150,
    },
]

_VILLAGE_FETCH_TEMPLATES = [
    {
        "target_id": "log",
        "count_range": (10, 20),
        "title": "Woodcutter's Request",
        "descriptions": [
            "We're running low on lumber for winter. Chop some trees and bring the logs.",
            "The carpenter needs logs to repair the mill. Can you gather some?",
        ],
        "reward_gold_base": 3,   # per item
        "reward_xp_base": 15,
        "reward_item": None,
    },
    {
        "target_id": "stone",
        "count_range": (12, 24),
        "title": "Mason's Commission",
        "descriptions": [
            "We're rebuilding the well wall. Bring us stones from the hills.",
            "The elder wants to reinforce the village walls. Bring stones.",
        ],
        "reward_gold_base": 2,
        "reward_xp_base": 10,
        "reward_item": None,
    },
    {
        "target_id": "fish",
        "count_range": (6, 12),
        "title": "Fisher's Bounty",
        "descriptions": [
            "The village feast is coming up and we're short on fish. Fill the pantry.",
            "A merchant is visiting — help us impress them with a proper fish supper.",
        ],
        "reward_gold_base": 6,
        "reward_xp_base": 30,
        "reward_item": None,
    },
    {
        "target_id": "iron_ore",
        "count_range": (4, 8),
        "title": "Ore Delivery",
        "descriptions": [
            "The blacksmith is out of iron. Venture into the hills and bring back ore.",
            "We need iron ore to repair our tools. Mine some and bring it here.",
        ],
        "reward_gold_base": 12,
        "reward_xp_base": 60,
        "reward_item": "iron_ingot",
    },
    {
        "target_id": "cooked_fish",
        "count_range": (5, 10),
        "title": "The Hungry Miners",
        "descriptions": [
            "The miners need packed meals. Bring cooked fish to feed them.",
            "Long shifts in the caves — the workers need cooked meals. Help out.",
        ],
        "reward_gold_base": 8,
        "reward_xp_base": 35,
        "reward_item": None,
    },
]

_VILLAGE_INVESTIGATION_TEMPLATES = [
    {
        "target_id": "ruins",
        "title": "Voices in the Ruins",
        "descriptions": [
            "Travellers report strange sounds from the old ruins. Investigate and report back.",
            "Something stirs in the ancient ruins to the east. We need to know what.",
        ],
        "reward_gold": 70,
        "reward_xp": 350,
        "reward_item": "gem",
    },
    {
        "target_id": "shrine",
        "title": "Forgotten Shrine",
        "descriptions": [
            "An old shrine has been rediscovered. Visit it and see if the old magic still holds.",
            "Pilgrims once walked to a shrine nearby. Find it and offer a prayer.",
        ],
        "reward_gold": 60,
        "reward_xp": 300,
        "reward_item": "enchanted_gem_luck",
    },
]

_BOUNTY_TEMPLATES = [
    {
        "target_id": "wolf",
        "count_range": (5, 10),
        "title_fmt": "Bounty: Wolf Pack",
        "descriptions": [
            "Wanted — wolf pelts. A dangerous pack has been spotted in the region.",
            "The hunting guild puts out a standing bounty on wolves. Take them down.",
        ],
        "reward_gold_base": 45,
        "reward_xp_base": 250,
    },
    {
        "target_id": "bear",
        "count_range": (3, 5),
        "title_fmt": "Bounty: Bear Menace",
        "descriptions": [
            "Wanted — large bears. A bounty is offered for each confirmed kill.",
            "Three bears have been terrorising the northern road. Bring proof of the kill.",
        ],
        "reward_gold_base": 70,
        "reward_xp_base": 380,
    },
    {
        "target_id": "cave_spider",
        "count_range": (6, 12),
        "title_fmt": "Bounty: Cave Spiders",
        "descriptions": [
            "The miners refuse to work until the cave spiders are cleared out.",
            "A guild contract is open for cave spider extermination. High pay, high risk.",
        ],
        "reward_gold_base": 35,
        "reward_xp_base": 200,
    },
    {
        "target_id": "shark",
        "count_range": (3, 6),
        "title_fmt": "Bounty: Shark Cull",
        "descriptions": [
            "Shark attacks have crippled trade routes. The maritime guild will pay for kills.",
            "Fishermen can't work safely with these sharks in the water. Clear them out.",
        ],
        "reward_gold_base": 60,
        "reward_xp_base": 320,
        "location_type": "ocean",
    },
    {
        "target_id": "sea_serpent",
        "count_range": (2, 4),
        "title_fmt": "Bounty: Sea Serpent",
        "descriptions": [
            "A sea serpent has capsized two ships this season. The guild wants it dead.",
            "Wanted: sea serpent, dead or gone. The reward is substantial.",
        ],
        "reward_gold_base": 90,
        "reward_xp_base": 450,
        "location_type": "ocean",
    },
]

# ── Village errand templates (no tools required; complete by visiting a tile) ──
_VILLAGE_ERRAND_TEMPLATES = [
    {
        "target_id": "vil_well",
        "title": "Fresh Water Run",
        "descriptions": [
            "The well in the village square needs checking after last night's storm. Head over and take a look.",
            "An elder asked someone to inspect the well. A small gesture of goodwill goes a long way.",
        ],
        "reward_gold": 8,
        "reward_xp": 30,
    },
    {
        "target_id": "vil_guard",
        "title": "Guard Patrol Report",
        "descriptions": [
            "The village guard wants to brief any willing adventurers about recent disturbances. Find the guard.",
            "A posted notice asks travellers to check in with the village guard for a quick debrief.",
        ],
        "reward_gold": 10,
        "reward_xp": 35,
    },
    {
        "target_id": "vil_farmhouse",
        "title": "Helping the Farmer",
        "descriptions": [
            "The farmer is overwhelmed with chores. Stop by the farmhouse and lend a hand for a few minutes.",
            "Someone's needed at the farmhouse to help move some grain sacks. Shouldn't take long.",
        ],
        "reward_gold": 8,
        "reward_xp": 30,
    },
    {
        "target_id": "vil_tavern",
        "title": "A Message for the Innkeeper",
        "descriptions": [
            "Deliver a quick verbal message to the innkeeper at the tavern. Shouldn't take long.",
            "The village elder wants the innkeeper to know about the upcoming festival. Pass the word along.",
        ],
        "reward_gold": 7,
        "reward_xp": 25,
    },
    {
        "target_id": "vil_market",
        "title": "Market Errand",
        "descriptions": [
            "Pop over to the market and let the stall holders know about the upcoming inspection.",
            "The village needs someone to check the market prices are still in order. Quick job.",
        ],
        "reward_gold": 7,
        "reward_xp": 25,
    },
]

# ── Easy village fetch templates (no tools; items obtainable in the village) ───
_VILLAGE_EASY_FETCH_TEMPLATES = [
    {
        "target_id": "wheat",
        "count_range": (2, 3),
        "title": "Grain for the Baker",
        "descriptions": [
            "The baker has run out of wheat. Harvest a little from the village fields.",
            "A small amount of wheat is needed for tonight's bread. The farm fields should have some.",
        ],
        "reward_gold_base": 5,
        "reward_xp_base": 20,
        "reward_item": None,
    },
    {
        "target_id": "carrot",
        "count_range": (2, 3),
        "title": "Carrots for the Cook",
        "descriptions": [
            "The village cook needs a few carrots for tonight's stew. See what you can pull from the garden.",
            "Carrots are needed in the kitchen. Grow a couple from the farmland and bring them over.",
        ],
        "reward_gold_base": 5,
        "reward_xp_base": 20,
        "reward_item": None,
    },
    {
        "target_id": "potato",
        "count_range": (2, 3),
        "title": "Potatoes for the Cellar",
        "descriptions": [
            "The village needs a few potatoes stored before the cold sets in. Bring some from the farm.",
            "The innkeeper wants to stock up on potatoes. Harvest a small batch from the farmland.",
        ],
        "reward_gold_base": 5,
        "reward_xp_base": 20,
        "reward_item": None,
    },
    {
        "target_id": "plant_fiber",
        "count_range": (3, 5),
        "title": "Fiber for the Weaver",
        "descriptions": [
            "The local weaver needs plant fiber for a new batch of cloth. Gather a handful.",
            "A quick job: collect some plant fiber from the surrounding area for the village weaver.",
        ],
        "reward_gold_base": 3,
        "reward_xp_base": 12,
        "reward_item": None,
    },
    {
        "target_id": "dry_grass",
        "count_range": (4, 6),
        "title": "Thatching Material",
        "descriptions": [
            "A roof needs patching. Collect some dry grass from the fields.",
            "The carpenter needs dry grass for thatching repairs. Easy work for willing hands.",
        ],
        "reward_gold_base": 2,
        "reward_xp_base": 10,
        "reward_item": None,
    },
]

_MERCHANT_DELIVERY_TEMPLATES = [
    {
        "title": "Urgent Parcel",
        "descriptions": [
            "I need this parcel delivered to the next village — quickly. I'll pay well.",
            "A package for the village elder at {dest}. Handle it with care.",
        ],
        "reward_gold_base": 80,
        "reward_xp_base": 400,
    },
    {
        "title": "Trade Goods",
        "descriptions": [
            "These trade goods need to reach {dest} before sundown. Make haste.",
            "Deliver this crate to the traders at {dest}. There's a good tip in it for you.",
        ],
        "reward_gold_base": 70,
        "reward_xp_base": 350,
    },
    {
        "title": "Secret Letter",
        "descriptions": [
            "This letter must reach {dest}. Tell no one what you carry.",
            "An urgent message for the village at {dest}. Speed is essential.",
        ],
        "reward_gold_base": 60,
        "reward_xp_base": 300,
        "reward_item": "map_fragment",
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _expires_str(hours: int = POOL_TTL_HOURS) -> str:
    return (_now_utc() + timedelta(hours=hours)).isoformat()


def _pool_expired(expires_at_str: str) -> bool:
    try:
        return _now_utc() > datetime.fromisoformat(expires_at_str)
    except (ValueError, TypeError):
        return True


def _pick(rng: random.Random, lst: list):
    return lst[rng.randrange(len(lst))]


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _bounty_location(rng: random.Random, location_type: str) -> tuple[int, int]:
    """Pick a plausible location for a bounty marker."""
    from dwarf_explorer.config import OCEAN_SIZE
    if location_type == "ocean":
        ox = rng.randint(10, OCEAN_SIZE - 10)
        oy = rng.randint(10, OCEAN_SIZE - 10)
        return ox, oy
    # Overworld: scatter around a random area (not spawn centre)
    margin = 40
    wx = rng.randint(margin, WORLD_SIZE - margin)
    wy = rng.randint(margin, WORLD_SIZE - margin)
    return wx, wy


def _direction_from_point(wx: int, wy: int, ref_x: int, ref_y: int) -> str:
    """Return a compass-direction adjective for (wx, wy) relative to reference point (ref_x, ref_y)."""
    dx = wx - ref_x   # positive = east
    dy = wy - ref_y   # positive = south (y grows downward)
    adx, ady = abs(dx), abs(dy)
    if adx == 0 and ady == 0:
        return "nearby"
    # Pure cardinal if one axis dominates by 2:1
    if ady > adx * 2:
        return "southern" if dy > 0 else "northern"
    if adx > ady * 2:
        return "eastern" if dx > 0 else "western"
    # Diagonal
    ns = "south" if dy > 0 else "north"
    ew = "east" if dx > 0 else "west"
    return f"{ns}{ew}ern"


# Words we may need to swap out; ordered longest-first so sub-words don't match first
_DIRECTIONAL_WORDS = [
    "northeastern", "northwestern", "southeastern", "southwestern",
    "northern", "southern", "eastern", "western",
    "north", "south", "east", "west",
]


def _patch_direction(desc: str, wx: int, wy: int, ref_x: int, ref_y: int) -> str:
    """Replace the first directional word in *desc* with the actual direction from ref_x/ref_y."""
    actual = _direction_from_point(wx, wy, ref_x, ref_y)
    for word in _DIRECTIONAL_WORDS:
        if word in desc:
            return desc.replace(word, actual, 1)
    return desc


# ── Quest record constructors ──────────────────────────────────────────────────

def _build_village_kill(rng: random.Random, tmpl: dict) -> dict:
    count = rng.randint(*tmpl["count_range"])
    desc = _pick(rng, tmpl["descriptions"])
    gold = tmpl["reward_gold_base"] + count * 5
    xp   = tmpl["reward_xp_base"] + count * 20
    return {
        "quest_type": f"Kill {count} {_ENEMY_NAMES.get(tmpl['target_id'], tmpl['target_id'])}",
        "title": tmpl["title"],
        "description": desc,
        "target_id": tmpl["target_id"],
        "target_count": count,
        "reward_gold": gold,
        "reward_xp": xp,
        "reward_item": None,
        "location_x": None,
        "location_y": None,
        "source_type": "village_npc",
        "quest_subtype": "kill",
        "location_type": "overworld",
    }


def _build_village_fetch(rng: random.Random, tmpl: dict) -> dict:
    count = rng.randint(*tmpl["count_range"])
    desc  = _pick(rng, tmpl["descriptions"])
    gold  = tmpl["reward_gold_base"] * count
    xp    = tmpl["reward_xp_base"] * count
    return {
        "quest_type": f"Gather {count} {_ITEM_NAMES.get(tmpl['target_id'], tmpl['target_id'])}",
        "title": tmpl["title"],
        "description": desc,
        "target_id": tmpl["target_id"],
        "target_count": count,
        "reward_gold": gold,
        "reward_xp": xp,
        "reward_item": tmpl.get("reward_item"),
        "location_x": None,
        "location_y": None,
        "source_type": "village_npc",
        "quest_subtype": "fetch",
        "location_type": "overworld",
    }


def _build_village_errand(rng: random.Random, tmpl: dict, village_id: int) -> dict:
    """Build an errand quest that completes by visiting a specific tile in this village."""
    desc = _pick(rng, tmpl["descriptions"])
    return {
        "quest_type": f"Errand: {tmpl['title']}",
        "title": tmpl["title"],
        "description": desc,
        "target_id": tmpl["target_id"],   # village tile type to visit
        "target_count": 1,
        "reward_gold": tmpl["reward_gold"],
        "reward_xp": tmpl["reward_xp"],
        "reward_item": tmpl.get("reward_item"),
        "location_x": village_id,          # overloaded: stores village_id
        "location_y": None,
        "source_type": "village_npc",
        "quest_subtype": "errand",
        "location_type": "village",
    }


def _build_village_investigation(rng: random.Random, tmpl: dict, loc_x: int | None, loc_y: int | None) -> dict:
    desc = _pick(rng, tmpl["descriptions"])
    return {
        "quest_type": f"Investigate {tmpl['target_id'].capitalize()}",
        "title": tmpl["title"],
        "description": desc,
        "target_id": tmpl["target_id"],
        "target_count": 1,
        "reward_gold": tmpl["reward_gold"],
        "reward_xp": tmpl["reward_xp"],
        "reward_item": tmpl.get("reward_item"),
        "location_x": loc_x,
        "location_y": loc_y,
        "source_type": "village_npc",
        "quest_subtype": "investigation",
        "location_type": "overworld",
    }


def _build_bounty(
    rng: random.Random, tmpl: dict,
    ref_x: int | None = None, ref_y: int | None = None,
) -> dict:
    count = rng.randint(*tmpl["count_range"])
    desc  = _pick(rng, tmpl["descriptions"])
    gold  = tmpl["reward_gold_base"] + count * 8
    xp    = tmpl["reward_xp_base"] + count * 30
    loc_type = tmpl.get("location_type", "overworld")
    lx, ly   = _bounty_location(rng, loc_type)
    # Patch any directional word in the description to match the actual location.
    # Use the village as the reference point so the direction makes sense from
    # the player's perspective.  Fall back to world centre if not provided.
    if loc_type == "overworld":
        rx = ref_x if ref_x is not None else WORLD_SIZE // 2
        ry = ref_y if ref_y is not None else WORLD_SIZE // 2
        desc = _patch_direction(desc, lx, ly, rx, ry)
    return {
        "quest_type": f"Bounty: {count} {_ENEMY_NAMES.get(tmpl['target_id'], tmpl['target_id'])}",
        "title": tmpl["title_fmt"],
        "description": desc,
        "target_id": tmpl["target_id"],
        "target_count": count,
        "reward_gold": gold,
        "reward_xp": xp,
        "reward_item": None,
        "location_x": lx,
        "location_y": ly,
        "source_type": "bounty",
        "quest_subtype": "kill",
        "location_type": loc_type,
    }


def _build_merchant_delivery(rng: random.Random, tmpl: dict, dest_x: int, dest_y: int) -> dict:
    desc = _pick(rng, tmpl["descriptions"]).format(dest=f"({dest_x},{dest_y})")
    reward_item = tmpl.get("reward_item")
    return {
        "quest_type": "Delivery Quest",
        "title": tmpl["title"],
        "description": desc,
        "target_id": "merchant_parcel",
        "target_count": 1,
        "reward_gold": tmpl["reward_gold_base"],
        "reward_xp": tmpl["reward_xp_base"],
        "reward_item": reward_item,
        "location_x": dest_x,
        "location_y": dest_y,
        "source_type": "merchant",
        "quest_subtype": "delivery",
        "location_type": "overworld",
    }


# ── DB insertion helper ────────────────────────────────────────────────────────

async def _insert_quest(db, q: dict) -> int:
    """Insert a quest record and return its new id."""
    cur = await db.execute(
        "INSERT INTO quests (quest_type, title, description, target_id, target_count, "
        "reward_gold, reward_xp, reward_item, location_x, location_y, "
        "source_type, quest_subtype, location_type) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (q["quest_type"], q["title"], q["description"], q["target_id"], q["target_count"],
         q["reward_gold"], q["reward_xp"], q["reward_item"],
         q["location_x"], q["location_y"],
         q["source_type"], q["quest_subtype"], q["location_type"]),
    )
    return cur.lastrowid


# ── Pool management ────────────────────────────────────────────────────────────

async def get_or_refresh_village_pool(db, village_id: int, seed: int) -> list[dict]:
    """Return the current quest pool for a village, refreshing if expired.

    Returns a list of quest dicts (from the quests table) for up to 3 quests.
    If an existing active player_quest references a pool quest, that quest is
    excluded from the refreshed pool for the returning player — callers must
    filter by user.
    """
    source_key = str(village_id)
    pool = await _load_pool(db, "village_npc", source_key)
    if pool is not None:
        return pool
    # Expired or missing — generate fresh quests
    rng = random.Random(seed ^ village_id ^ int(_now_utc().timestamp() // (POOL_TTL_HOURS * 3600)))
    quests_out: list[dict] = []

    # Guaranteed: 1 errand + 1 easy fetch (no tools required, completable in the village)
    all_errands     = _VILLAGE_ERRAND_TEMPLATES[:]
    all_easy_fetch  = _VILLAGE_EASY_FETCH_TEMPLATES[:]
    rng.shuffle(all_errands)
    rng.shuffle(all_easy_fetch)

    records: list[dict] = []
    records.append(_build_village_errand(rng, all_errands[0], village_id))
    records.append(_build_village_fetch(rng, all_easy_fetch[0]))

    # Pick 1 kill or harder fetch quest to round out the pool
    all_kill   = _VILLAGE_KILL_TEMPLATES[:]
    all_fetch  = _VILLAGE_FETCH_TEMPLATES[:]
    rng.shuffle(all_kill)
    rng.shuffle(all_fetch)
    inv_chance = rng.random()

    if inv_chance < 0.4:
        # Investigation quest if a matching structure exists
        inv_tmpl = _pick(rng, _VILLAGE_INVESTIGATION_TEMPLATES)
        loc = await db.fetch_one(
            "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = ? LIMIT 1",
            (inv_tmpl["target_id"],),
        )
        if loc:
            records.append(_build_village_investigation(rng, inv_tmpl, loc["world_x"], loc["world_y"]))
        else:
            records.append(_build_village_kill(rng, all_kill[0]))
    elif inv_chance < 0.7:
        records.append(_build_village_kill(rng, all_kill[0]))
    else:
        records.append(_build_village_fetch(rng, all_fetch[0]))

    # Limit to 3
    rng.shuffle(records)
    for q in records[:3]:
        qid = await _insert_quest(db, q)
        q["id"] = qid
        quests_out.append(q)

    # Store pool with expiry
    expires = _expires_str()
    for q in quests_out:
        await db.execute(
            "INSERT INTO quest_pool (source_type, source_key, quest_id, expires_at) VALUES (?,?,?,?)",
            ("village_npc", source_key, q["id"], expires),
        )
    return quests_out


async def get_or_refresh_bounty_pool(
    db, seed: int,
    village_id: int | None = None,
    village_wx: int | None = None,
    village_wy: int | None = None,
) -> list[dict]:
    """Return the bounty pool for a specific village, refreshing if expired.

    When village_id is provided the pool is stored per-village so that
    directional descriptions ("northern road") are computed relative to that
    village's world position rather than the world centre.

    Falls back to a global pool when called without a village_id (e.g. from
    the world map bounty board).
    """
    source_key = f"bounty_v{village_id}" if village_id is not None else "overworld"
    pool = await _load_pool(db, "bounty", source_key)
    if pool is not None:
        return pool

    # Mix village coords into RNG so each village gets a different set of quests
    rng_seed = seed ^ 0xB0BBBBBB ^ int(_now_utc().timestamp() // (POOL_TTL_HOURS * 3600))
    if village_id is not None:
        rng_seed ^= village_id * 0x1337
    rng = random.Random(rng_seed)
    all_bounties = _BOUNTY_TEMPLATES[:]
    rng.shuffle(all_bounties)

    quests_out: list[dict] = []
    expires = _expires_str()
    for tmpl in all_bounties[:3]:
        q = _build_bounty(rng, tmpl, ref_x=village_wx, ref_y=village_wy)
        qid = await _insert_quest(db, q)
        q["id"] = qid
        quests_out.append(q)
        await db.execute(
            "INSERT INTO quest_pool (source_type, source_key, quest_id, expires_at) VALUES (?,?,?,?)",
            ("bounty", source_key, qid, expires),
        )
    return quests_out


async def generate_merchant_quest(db, seed: int, player_wx: int, player_wy: int) -> dict | None:
    """Generate a one-off delivery quest for the travelling merchant.

    Picks a destination village from tile_overrides that isn't too close to the
    player.  Returns None if no suitable destination village exists.
    """
    villages = await db.fetch_all(
        "SELECT world_x, world_y FROM tile_overrides WHERE tile_type = 'village'"
    )
    # Filter to villages at least 50 tiles away
    far = [(r["world_x"], r["world_y"]) for r in villages
           if abs(r["world_x"] - player_wx) + abs(r["world_y"] - player_wy) > 50]
    if not far:
        far = [(r["world_x"], r["world_y"]) for r in villages] or None
    if not far:
        return None

    rng = random.Random(seed ^ player_wx ^ player_wy ^ 0xDEADBEEF)
    dest_x, dest_y = rng.choice(far)
    tmpl = _pick(rng, _MERCHANT_DELIVERY_TEMPLATES)
    q    = _build_merchant_delivery(rng, tmpl, dest_x, dest_y)
    qid  = await _insert_quest(db, q)
    q["id"] = qid
    return q


async def _load_pool(db, source_type: str, source_key: str) -> list[dict] | None:
    """Return quest rows if a valid (unexpired) pool exists, else None."""
    rows = await db.fetch_all(
        "SELECT qp.quest_id, qp.expires_at, "
        "q.quest_type, q.title, q.description, q.target_id, q.target_count, "
        "q.reward_gold, q.reward_xp, q.reward_item, q.location_x, q.location_y, "
        "q.source_type, q.quest_subtype, q.location_type "
        "FROM quest_pool qp JOIN quests q ON qp.quest_id = q.id "
        "WHERE qp.source_type = ? AND qp.source_key = ?",
        (source_type, source_key),
    )
    if not rows:
        return None
    # All rows share the same expires_at — check the first
    if _pool_expired(rows[0]["expires_at"]):
        # Expire — delete pool entries (keep quest rows in case players have them)
        await db.execute(
            "DELETE FROM quest_pool WHERE source_type = ? AND source_key = ?",
            (source_type, source_key),
        )
        return None
    return [dict(r) for r in rows]


# ── Player quest operations ────────────────────────────────────────────────────

async def get_active_quest_count(db, user_id: int) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM player_quests WHERE user_id = ? AND status = 'active'",
        (user_id,),
    )
    return row["cnt"] if row else 0


async def get_active_quests(db, user_id: int) -> list[dict]:
    """Return active player_quests joined with quest definitions."""
    rows = await db.fetch_all(
        "SELECT pq.id AS pq_id, pq.progress, pq.accepted_at, pq.bounty_wx, pq.bounty_wy, "
        "q.id AS quest_id, q.quest_type, q.title, q.description, q.target_id, q.target_count, "
        "q.reward_gold, q.reward_xp, q.reward_item, q.location_x, q.location_y, "
        "q.source_type, q.quest_subtype, q.location_type "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' "
        "ORDER BY pq.accepted_at",
        (user_id,),
    )
    return [dict(r) for r in rows]


async def accept_quest(
    db, user_id: int, quest_id: int,
    source_type: str = "village_npc",
    bounty_wx: int | None = None,
    bounty_wy: int | None = None,
) -> bool:
    """Accept a quest. Returns False if player already has MAX_PLAYER_QUESTS active."""
    count = await get_active_quest_count(db, user_id)
    if count >= MAX_PLAYER_QUESTS:
        return False
    # Check not already accepted
    existing = await db.fetch_one(
        "SELECT id FROM player_quests WHERE user_id = ? AND quest_id = ? AND status = 'active'",
        (user_id, quest_id),
    )
    if existing:
        return False
    await db.execute(
        "INSERT OR REPLACE INTO player_quests "
        "(user_id, quest_id, progress, status, accepted_at, bounty_wx, bounty_wy, source_type) "
        "VALUES (?, ?, 0, 'active', datetime('now'), ?, ?, ?)",
        (user_id, quest_id, bounty_wx, bounty_wy, source_type),
    )
    return True


async def cancel_quest(db, user_id: int, pq_id: int) -> bool:
    """Cancel an active quest. Returns False if not found."""
    row = await db.fetch_one(
        "SELECT id FROM player_quests WHERE id = ? AND user_id = ? AND status = 'active'",
        (pq_id, user_id),
    )
    if not row:
        return False
    await db.execute(
        "UPDATE player_quests SET status = 'cancelled' WHERE id = ?", (pq_id,)
    )
    # Remove any merchant_parcel that was added for a delivery quest
    # (handled separately by caller if needed)
    return True


async def complete_quest(db, user_id: int, pq_id: int) -> dict | None:
    """Mark a quest completed; return reward dict or None on error."""
    row = await db.fetch_one(
        "SELECT pq.id, pq.quest_id, pq.progress, "
        "q.target_count, q.reward_gold, q.reward_xp, q.reward_item, q.quest_subtype, q.target_id "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.id = ? AND pq.user_id = ? AND pq.status = 'active'",
        (pq_id, user_id),
    )
    if not row:
        return None
    await db.execute(
        "UPDATE player_quests SET status = 'completed', completed_at = datetime('now') WHERE id = ?",
        (pq_id,),
    )
    return {
        "gold": row["reward_gold"],
        "xp": row["reward_xp"],
        "item": row["reward_item"],
        "quest_subtype": row["quest_subtype"],
        "target_id": row["target_id"],
    }


async def increment_kill_progress(db, user_id: int, enemy_type: str) -> list[str]:
    """Called on combat win. Increments progress for matching active kill quests.

    Returns list of quest titles that just completed.
    """
    rows = await db.fetch_all(
        "SELECT pq.id, pq.progress, q.target_count, q.title "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' "
        "AND q.quest_subtype = 'kill' AND q.target_id = ?",
        (user_id, enemy_type),
    )
    completed: list[str] = []
    for r in rows:
        new_progress = r["progress"] + 1
        await db.execute(
            "UPDATE player_quests SET progress = ? WHERE id = ?",
            (new_progress, r["id"]),
        )
        if new_progress >= r["target_count"]:
            completed.append(r["title"])
    return completed


async def get_completable_fetch_quests(db, user_id: int) -> list[dict]:
    """Return fetch quests the player can turn in based on current inventory."""
    from dwarf_explorer.database.repositories import get_inventory
    inv = await get_inventory(db, user_id)
    # Tally totals
    totals: dict[str, int] = {}
    for slot in inv:
        totals[slot["item_id"]] = totals.get(slot["item_id"], 0) + slot["quantity"]

    rows = await db.fetch_all(
        "SELECT pq.id AS pq_id, pq.progress, q.target_id, q.target_count, "
        "q.title, q.reward_gold, q.reward_xp, q.reward_item "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' AND q.quest_subtype = 'fetch'",
        (user_id,),
    )
    completable = []
    for r in rows:
        if totals.get(r["target_id"], 0) >= r["target_count"]:
            completable.append(dict(r))
    return completable


async def get_completable_delivery_quests(db, user_id: int, village_wx: int, village_wy: int) -> list[dict]:
    """Return delivery quests that can be completed at this village (player has parcel + at dest)."""
    from dwarf_explorer.database.repositories import get_inventory
    inv = await get_inventory(db, user_id)
    has_parcel = any(s["item_id"] == "merchant_parcel" for s in inv)
    if not has_parcel:
        return []

    rows = await db.fetch_all(
        "SELECT pq.id AS pq_id, q.title, q.reward_gold, q.reward_xp, q.reward_item, "
        "q.location_x, q.location_y "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' AND q.quest_subtype = 'delivery'",
        (user_id,),
    )
    completable = []
    for r in rows:
        # Destination matches if within 5 tiles of this village's world tile
        if (r["location_x"] is not None and r["location_y"] is not None
                and abs(r["location_x"] - village_wx) <= 5
                and abs(r["location_y"] - village_wy) <= 5):
            completable.append(dict(r))
    return completable


async def get_completable_investigation_quests(
    db, user_id: int, structure_type: str, world_x: int, world_y: int
) -> list[dict]:
    """Return investigation quests completable at this structure tile."""
    rows = await db.fetch_all(
        "SELECT pq.id AS pq_id, q.title, q.reward_gold, q.reward_xp, q.reward_item, "
        "q.location_x, q.location_y, q.target_id "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' AND q.quest_subtype = 'investigation'"
        " AND q.target_id = ?",
        (user_id, structure_type),
    )
    completable = []
    for r in rows:
        if (r["location_x"] is not None and r["location_y"] is not None
                and abs(r["location_x"] - world_x) <= 3
                and abs(r["location_y"] - world_y) <= 3):
            completable.append(dict(r))
    return completable


async def get_completable_errand_quests(
    db, user_id: int, tile_type: str, village_id: int
) -> list[dict]:
    """Return errand quests completable by standing on *tile_type* in *village_id*."""
    rows = await db.fetch_all(
        "SELECT pq.id AS pq_id, q.title, q.reward_gold, q.reward_xp, q.reward_item, "
        "q.location_x, q.target_id "
        "FROM player_quests pq JOIN quests q ON pq.quest_id = q.id "
        "WHERE pq.user_id = ? AND pq.status = 'active' "
        "AND q.quest_subtype = 'errand' AND q.target_id = ?",
        (user_id, tile_type),
    )
    return [dict(r) for r in rows if r["location_x"] == village_id]


def render_quest_progress_bar(progress: int, total: int, width: int = 5) -> str:
    """Return a filled/empty bar like ██░░░ 3/5."""
    filled = min(width, round(progress / max(1, total) * width))
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {progress}/{total}"


def render_quest_summary(q: dict) -> str:
    """One-line quest summary for the quest list view."""
    subtype = q.get("quest_subtype", "kill")
    if subtype == "kill":
        bar = render_quest_progress_bar(q.get("progress", 0), q["target_count"])
        return (f"**{q['title']}** [{q.get('source_type', '?').replace('_', ' ').title()}]\n"
                f"{q['description']}\n"
                f"Progress: {bar}\n"
                f"Reward: {q['reward_gold']}🪙 +{q['reward_xp']}xp"
                + (f" +{q['reward_item']}" if q.get("reward_item") else ""))
    elif subtype == "fetch":
        from dwarf_explorer.config import ITEM_EMOJI
        item_emoji = ITEM_EMOJI.get(q["target_id"], "📦")
        return (f"**{q['title']}** [Village]\n"
                f"{q['description']}\n"
                f"Need: {item_emoji} ×{q['target_count']} {_ITEM_NAMES.get(q['target_id'], q['target_id'])}\n"
                f"Reward: {q['reward_gold']}🪙 +{q['reward_xp']}xp"
                + (f" +{q['reward_item']}" if q.get("reward_item") else ""))
    elif subtype == "investigation":
        loc_str = ""
        if q.get("location_x") and q.get("location_y"):
            loc_str = f"\nDestination: ({q['location_x']}, {q['location_y']})"
        return (f"**{q['title']}** [Investigation]\n"
                f"{q['description']}{loc_str}\n"
                f"Reward: {q['reward_gold']}🪙 +{q['reward_xp']}xp"
                + (f" +{q['reward_item']}" if q.get("reward_item") else ""))
    elif subtype == "errand":
        _tile_labels = {
            "vil_well":      "the village well ⛲",
            "vil_guard":     "the village guard 🛡️",
            "vil_farmhouse": "the farmhouse 🏡",
            "vil_tavern":    "the tavern 🍺",
            "vil_market":    "the market 🛒",
        }
        dest_label = _tile_labels.get(q.get("target_id", ""), q.get("target_id", "the destination"))
        return (f"**{q['title']}** [Errand]\n"
                f"{q['description']}\n"
                f"Go to: {dest_label}\n"
                f"Reward: {q['reward_gold']}🪙 +{q['reward_xp']}xp"
                + (f" +{q['reward_item']}" if q.get("reward_item") else ""))
    elif subtype == "delivery":
        loc_str = ""
        if q.get("location_x") and q.get("location_y"):
            loc_str = f"\nDeliver to: ({q['location_x']}, {q['location_y']})"
        return (f"**{q['title']}** [Delivery]\n"
                f"{q['description']}{loc_str}\n"
                f"Reward: {q['reward_gold']}🪙 +{q['reward_xp']}xp"
                + (f" +{q['reward_item']}" if q.get("reward_item") else ""))
    return f"**{q['title']}**\n{q['description']}"
