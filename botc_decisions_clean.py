"""
botc_decisions.py

Every Storyteller decision point in structured form.
Consumed by the Discord renderer (buttons/dropdowns/modals in #ascension-chat)
and the LLM Storyteller (serialised to JSON, response parsed back to choices).

Input kinds:
  player_select       pick 1 player from a resolved list
  player_multiselect  pick N players (count specifies how many)
  character_select    pick 1 character from a resolved list
  choice              one of N labeled options (rendered as buttons)
  boolean             yes / no
  text                free-form string (modal input)
  player_char_pairs   list of {player_id, character} pairs (Kazali, LoT, etc.)
"""
import botc_logic as BL

# â”€â”€ Input kind constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
PLAYER_SELECT      = "player_select"
PLAYER_MULTISELECT = "player_multiselect"
CHARACTER_SELECT   = "character_select"
CHOICE             = "choice"
BOOLEAN            = "boolean"
TEXT               = "text"
PLAYER_CHAR_PAIRS  = "player_char_pairs"

# â”€â”€ Pool helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _pp(g, spec):
    """Resolve a player pool spec to a list of player dicts."""
    ps = g.get("players", [])
    alive = [p for p in ps if p["alive"]]
    pools = {
        "alive":       alive,
        "all":         ps,
        "dead":        [p for p in ps if not p["alive"]],
        "alive_good":  [p for p in alive if p["alignment"] == BL.GOOD],
        "alive_evil":  [p for p in alive if p["alignment"] == BL.EVIL],
        "alive_tf":    [p for p in alive if p["char_type"] == BL.TOWNSFOLK],
        "alive_out":   [p for p in alive if p["char_type"] == BL.OUTSIDER],
        "alive_min":   [p for p in alive if p["char_type"] == BL.MINION],
        "dead_tf":     [p for p in ps if not p["alive"] and p["char_type"] == BL.TOWNSFOLK],
    }
    return pools.get(spec, alive)

def _cp(g, spec):
    """Resolve a character pool spec to a list of character name strings."""
    script   = g.get("script", [])
    players  = g.get("players", [])
    in_play  = [p["character"] for p in players]
    ct       = BL._BOFFIN_CHAR_TYPE
    pools = {
        "script":         script,
        "in_play":        in_play,
        "tf_script":      [c for c in script if ct.get(c) == BL.TOWNSFOLK],
        "out_script":     [c for c in script if ct.get(c) == BL.OUTSIDER],
        "min_script":     [c for c in script if ct.get(c) == BL.MINION],
        "demon_script":   [c for c in script if ct.get(c) == BL.DEMON],
        "not_in_play":    [c for c in script if c not in in_play],
        "all_tf":         [c for c, t in ct.items() if t == BL.TOWNSFOLK],
        "all_min":        [c for c, t in ct.items() if t == BL.MINION],
        "all_demon":      [c for c, t in ct.items() if t == BL.DEMON],
    }
    return pools.get(spec, script)

# â”€â”€ Decision node factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def make_decision(dtype, g, **extra):
    """Instantiate a decision node with pools resolved from current game state."""
    defn = DECISION_DEFS.get(dtype)
    if not defn:
        raise KeyError(f"Unknown decision type: {dtype!r}")
    inputs = {}
    for key, spec in defn["inputs"].items():
        inp = dict(spec)
        if "pool" in inp and isinstance(inp["pool"], str):
            inp["players"] = _pp(g, inp["pool"])
        if "char_pool" in inp and isinstance(inp["char_pool"], str):
            inp["characters"] = _cp(g, inp["char_pool"])
        inputs[key] = inp
    return {"type": dtype, "prompt": defn["prompt"], "inputs": inputs, **extra}

def resolve_decision(dtype, choices, g):
    """Execute a resolved decision against game state. Returns resolver output."""
    fn = RESOLVERS.get(dtype)
    if not fn:
        raise KeyError(f"No resolver for: {dtype!r}")
    return fn(choices, g)

# â”€â”€ Shorthand builders (used in DECISION_DEFS) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _p1(prompt, pool="alive", optional=False):
    return {"prompt": prompt, "inputs": {
        "target": {"kind": PLAYER_SELECT, "pool": pool, "optional": optional},
    }}

def _p2(prompt, pool="alive", optional=False):
    return {"prompt": prompt, "inputs": {
        "t1": {"kind": PLAYER_SELECT, "pool": pool, "optional": optional},
        "t2": {"kind": PLAYER_SELECT, "pool": pool, "optional": optional},
    }}

def _p1c1(prompt, pool="alive", char_pool="script"):
    return {"prompt": prompt, "inputs": {
        "target":    {"kind": PLAYER_SELECT,    "pool": pool},
        "character": {"kind": CHARACTER_SELECT, "char_pool": char_pool},
    }}

# â”€â”€ Decision definitions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Keys match the resolver keys in RESOLVERS at the bottom of this file.

DECISION_DEFS = {

    # â”€â”€ NIGHT META â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "minion_info": {
        "prompt": "Deliver minion info. Confirm minions have been shown their demon and each other.",
        "inputs": {"confirmed": {"kind": BOOLEAN}},
    },
    "demon_info": {
        "prompt": "Deliver demon info. Confirm demon has been shown their minions and 3 bluffs.",
        "inputs": {
            "bluff1": {"kind": CHARACTER_SELECT, "char_pool": "not_in_play"},
            "bluff2": {"kind": CHARACTER_SELECT, "char_pool": "not_in_play"},
            "bluff3": {"kind": CHARACTER_SELECT, "char_pool": "not_in_play"},
        },
    },

    # â”€â”€ BARISTA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "barista_nightly": {
        "prompt": "Barista: choose which player is affected and which ability applies tonight.",
        "inputs": {
            "target": {"kind": PLAYER_SELECT, "pool": "alive"},
            "ability_num": {"kind": CHOICE, "options": [
                {"value": 1, "label": "1 â€” Sober, healthy & guaranteed true info"},
                {"value": 2, "label": "2 â€” Use ability twice tonight"},
            ]},
        },
    },

    # â”€â”€ PROTECTION / EFFECT ROLES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "monk_night":        _p1("Monk wakes. Pick 1 player to protect from the Demon tonight."),
    "sailor_night":      _p1("Sailor wakes. Pick 1 player to drink with tonight."),
    "innkeeper_night": {
        "prompt": "Innkeeper wakes. Pick 2 players to protect; choose which one is drunk.",
        "inputs": {
            "t1":      {"kind": PLAYER_SELECT, "pool": "alive"},
            "t2":      {"kind": PLAYER_SELECT, "pool": "alive"},
            "drunk":   {"kind": CHOICE, "options": [
                {"value": "t1", "label": "First player is drunk"},
                {"value": "t2", "label": "Second player is drunk"},
            ]},
        },
    },
    "poisoner_night":    _p1("Poisoner wakes. Pick 1 player to poison tonight."),
    "witch_night":       _p1("Witch wakes. Pick 1 player to curse (dies if they nominate tomorrow)."),
    "devils_advocate_night": _p1("Devil's Advocate wakes. Pick 1 alive player to protect from execution today."),
    "butler_night":      _p1("Butler wakes. Pick your master for tonight (you may only vote if they vote)."),
    "preacher_night":    _p1("Preacher wakes. Pick 1 player to preach to (Minion loses ability if chosen)."),
    "exorcist_night":    _p1("Exorcist wakes. Pick 1 player â€” the Demon cannot act if they pick that player."),
    "courtier_night": {
        "prompt": "Courtier wakes. Name 1 character to make drunk for 3 nights (once per game), or pass.",
        "inputs": {
            "character": {"kind": CHARACTER_SELECT, "char_pool": "script"},
            "pass":      {"kind": BOOLEAN},
        },
    },
    "fearmonger_night":  _p1("Fearmonger wakes. Pick 1 player â€” if nominated and executed today, evil wins."),
    "harpy_night":       _p2("Harpy wakes. Pick 2 players â€” the second must stay mad or die (once per game)."),
    "mezepheles_night":  _p1("Mezepheles wakes. Pick 1 player to whisper the secret word to."),
    "cerenovus_night":   _p1c1("Cerenovus wakes. Pick 1 player and a character for them to claim madness about."),
    "godfather_night": {
        "prompt": "Godfather wakes (Outsider died today). Kill 1 player tonight, or pass.",
        "inputs": {
            "target":  {"kind": PLAYER_SELECT, "pool": "alive", "optional": True},
            "pass":    {"kind": BOOLEAN},
        },
    },
    "assassin_night": {
        "prompt": "Assassin wakes. Kill 1 player ignoring all protection (once per game), or pass.",
        "inputs": {
            "target":  {"kind": PLAYER_SELECT, "pool": "alive", "optional": True},
            "pass":    {"kind": BOOLEAN},
        },
    },
    "bone_collector_night": {
        "prompt": "Bone Collector wakes. Pick 1 dead player to regain their ability for one night (once per game), or pass.",
        "inputs": {
            "target":  {"kind": PLAYER_SELECT, "pool": "dead", "optional": True},
            "pass":    {"kind": BOOLEAN},
        },
    },
    "engineer_night": {
        "prompt": "Engineer wakes. Reassign Minions and/or the Demon type (once per game), or pass.",
        "inputs": {
            "assignments": {"kind": PLAYER_CHAR_PAIRS},
            "pass":        {"kind": BOOLEAN},
        },
    },
    "pit_hag_night":     _p1c1("Pit-Hag wakes. Pick 1 player and a character â€” they become it now."),
    "summoner_night":    _p1c1("Summoner (night 3). Pick 1 player to become the Demon and which Demon.", char_pool="demon_script"),
    "wizard_night":      _p1("Wizard wakes. Pick 1 player whose ability does not work tonight."),
    "wraith_night": {
        "prompt": "Wraith (Fabled). Kill 1 player as though a Demon killed them (once per game), or pass.",
        "inputs": {
            "target": {"kind": PLAYER_SELECT, "pool": "alive", "optional": True},
            "pass":   {"kind": BOOLEAN},
        },
    },

    # â”€â”€ INFORMATION ROLES â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "washerwoman_info": {
        "prompt": "Washerwoman: show 2 players, one of whom is a specific Townsfolk.",
        "inputs": {
            "t1":        {"kind": PLAYER_SELECT,    "pool": "all"},
            "t2":        {"kind": PLAYER_SELECT,    "pool": "all"},
            "character": {"kind": CHARACTER_SELECT, "char_pool": "tf_script"},
        },
    },
    "librarian_info": {
        "prompt": "Librarian: show 2 players, one of whom is a specific Outsider (or show no Outsiders).",
        "inputs": {
            "no_outsiders": {"kind": BOOLEAN},
            "t1":           {"kind": PLAYER_SELECT,    "pool": "all", "optional": True},
            "t2":           {"kind": PLAYER_SELECT,    "pool": "all", "optional": True},
            "character":    {"kind": CHARACTER_SELECT, "char_pool": "out_script", "optional": True},
        },
    },
    "investigator_info": {
        "prompt": "Investigator: show 2 players, one of whom is a specific Minion.",
        "inputs": {
            "t1":        {"kind": PLAYER_SELECT,    "pool": "all"},
            "t2":        {"kind": PLAYER_SELECT,    "pool": "all"},
            "character": {"kind": CHARACTER_SELECT, "char_pool": "min_script"},
        },
    },
    "chef_info": {
        "prompt": "Chef: how many pairs of neighbouring evil players are there?",
        "inputs": {"count": {"kind": CHOICE, "options": [{"value": i, "label": str(i)} for i in range(8)]}},
    },
    "fortune_teller_night": {
        "prompt": "Fortune Teller picks 2 players. Does the reading return Yes (one registers as Demon)?",
        "inputs": {
            "t1":    {"kind": PLAYER_SELECT, "pool": "alive"},
            "t2":    {"kind": PLAYER_SELECT, "pool": "alive"},
            "result":{"kind": BOOLEAN},
        },
    },
    "empath_night": {
        "prompt": "Empath: how many of their 2 alive neighbours are evil? (auto-computed â€” confirm or override)",
        "inputs": {"evil_count": {"kind": CHOICE, "options": [
            {"value": 0, "label": "0"}, {"value": 1, "label": "1"}, {"value": 2, "label": "2"},
        ]}},
    },
    "undertaker_night": {
        "prompt": "Undertaker: confirm which character the executed player registered as.",
        "inputs": {"character": {"kind": CHARACTER_SELECT, "char_pool": "script"}},
    },
    "seamstress_night": {
        "prompt": "Seamstress picks 2 players. Do they register as the same alignment?",
        "inputs": {
            "t1":            {"kind": PLAYER_SELECT, "pool": "alive"},
            "t2":            {"kind": PLAYER_SELECT, "pool": "alive"},
            "same_alignment":{"kind": BOOLEAN},
        },
    },
    "clockmaker_info": {
        "prompt": "Clockmaker: how many clockwise steps from the Demon to the nearest Minion?",
        "inputs": {"steps": {"kind": CHOICE, "options": [{"value": i, "label": str(i)} for i in range(1, 14)]}},
    },
    "dreamer_night":      _p1c1("Dreamer wakes. Pick 1 player and name their character (one of 2 offered options)."),
    "grandmother_night":  _p1("Grandmother: pick the grandchild (night 1 only)."),
    "noble_info": {
        "prompt": "Noble: show 3 players, exactly 1 of whom is evil.",
        "inputs": {
            "t1": {"kind": PLAYER_SELECT, "pool": "all"},
            "t2": {"kind": PLAYER_SELECT, "pool": "all"},
            "t3": {"kind": PLAYER_SELECT, "pool": "all"},
        },
    },
    "bounty_hunter_info":  _p1("Bounty Hunter: point to 1 evil Townsfolk."),
    "shugenja_info": {
        "prompt": "Shugenja: is the nearest evil player clockwise or counter-clockwise?",
        "inputs": {"direction": {"kind": CHOICE, "options": [
            {"value": "clockwise",        "label": "Clockwise"},
            {"value": "counterclockwise", "label": "Counter-clockwise"},
            {"value": "equal",            "label": "Equidistant"},
        ]}},
    },
    "steward_info":        _p1("Steward: point to 1 good player."),
    "knight_info": {
        "prompt": "Knight: show 2 players who are NOT the Demon.",
        "inputs": {
            "t1": {"kind": PLAYER_SELECT, "pool": "all"},
            "t2": {"kind": PLAYER_SELECT, "pool": "all"},
        },
    },
    "pixie_setup":         {"prompt": "Pixie: which Townsfolk character does the Pixie know is in play?",
                            "inputs": {"character": {"kind": CHARACTER_SELECT, "char_pool": "tf_script"}}},
    "ogre_night":          _p1("Ogre wakes. Pick 1 player â€” Ogre becomes their alignment."),
    "balloonist_night":    _p1("Balloonist: show 1 player of the next character type in rotation."),
    "village_idiot_night": _p1("Village Idiot wakes. Pick 1 player to learn their alignment (may be drunk and wrong)."),
    "flowergirl_night": {
        "prompt": "Flowergirl: did the Demon vote yesterday?",
        "inputs": {"demon_voted": {"kind": BOOLEAN}},
    },
    "town_crier_night": {
        "prompt": "Town Crier: did a Minion nominate today?",
        "inputs": {"minion_nominated": {"kind": BOOLEAN}},
    },
    "oracle_night": {
        "prompt": "Oracle: how many dead players are evil?",
        "inputs": {"count": {"kind": CHOICE, "options": [{"value": i, "label": str(i)} for i in range(10)]}},
    },
    "ravenkeeper_info":    _p1c1("Ravenkeeper died tonight. Pick the player they learn; confirm character shown."),
    "sage_info": {
        "prompt": "Sage was killed by the Demon. Show 2 players, one of whom is the Demon.",
        "inputs": {
            "t1": {"kind": PLAYER_SELECT, "pool": "all"},
            "t2": {"kind": PLAYER_SELECT, "pool": "all"},
        },
    },
    "juggler_day": {
        "prompt": "Juggler submits guesses (up to 5 player+character pairs).",
        "inputs": {"guesses": {"kind": PLAYER_CHAR_PAIRS}},
    },
    "juggler_night": {
        "prompt": "Juggler night: confirm how many of yesterday's guesses were correct.",
        "inputs": {"correct": {"kind": CHOICE, "options": [{"value": i, "label": str(i)} for i in range(6)]}},
    },
    "gambler_night":       _p1c1("Gambler wakes. Pick 1 player and guess their character (dies if wrong)."),
    "high_priestess_night":_p1("High Priestess: pick 1 player you think this player should talk to today."),
    "chambermaid_night": {
        "prompt": "Chambermaid wakes. Pick 2 players to observe â€” how many woke for an ability last night?",
        "inputs": {
            "t1":    {"kind": PLAYER_SELECT, "pool": "alive"},
            "t2":    {"kind": PLAYER_SELECT, "pool": "alive"},
            "count": {"kind": CHOICE, "options": [
                {"value": 0, "label": "0"}, {"value": 1, "label": "1"}, {"value": 2, "label": "2"},
            ]},
        },
    },
    "general_night": {
        "prompt": "General: which team is winning right now?",
        "inputs": {"result": {"kind": CHOICE, "options": [
            {"value": BL.GOOD, "label": "Good is winning"},
            {"value": BL.EVIL, "label": "Evil is winning"},
            {"value": None,    "label": "Neither / too close to call"},
        ]}},
    },
    "mathematician_night": {
        "prompt": "Mathematician: how many players received wrong info due to their own ability tonight/today?",
        "inputs": {"count": {"kind": CHOICE, "options": [{"value": i, "label": str(i)} for i in range(10)]}},
    },
    "huntsman_night":      _p1c1("Huntsman: pick the Damsel and which Townsfolk they become."),
    "night_watchman_night":_p1("Night Watchman wakes. Pick 1 player to learn you are the Night Watchman (once per game)."),
    "cult_leader_night":   _p1("Cult Leader wakes. Pick 1 alive neighbour to copy their alignment, or pass.", optional=True),
    "king_night": {
        "prompt": "King wakes. Confirm which player (if any) the Choirboy reveals as the Demon.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive", "optional": True}},
    },

    # â”€â”€ SNAKE CHARMER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "snake_charmer_night": {
        "prompt": "Snake Charmer wakes. Pick 1 player to attempt to charm.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive"}},
    },

    # â”€â”€ HARLOT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "harlot_night": {
        "prompt": "Harlot wakes. Pick 1 player to spend the night with (may learn their character; may die).",
        "inputs": {
            "target":    {"kind": PLAYER_SELECT, "pool": "alive"},
            "share_char":{"kind": BOOLEAN},
        },
    },

    # â”€â”€ ACROBAT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "acrobat_night": _p1("Acrobat wakes. Pick 1 player â€” if they are or become drunk/poisoned tonight, you die."),

    # â”€â”€ LYCANTHROPE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "lycanthrope_night": _p1("Lycanthrope wakes. Pick 1 alive player to kill tonight (only kill this night)."),

    # â”€â”€ DEMONS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "imp_night":       _p1("Imp wakes. Pick 1 player to kill tonight (pick yourself to pass Imp to a Minion)."),
    "no_dashii_night": _p1("No Dashii wakes. Pick 1 player to kill tonight."),
    "vortox_night":    _p1("Vortox wakes. Pick 1 player to kill tonight (all Townsfolk info is false)."),
    "vigormortis_night": _p1("Vigormortis wakes. Pick 1 player to kill tonight."),
    "fang_gu_night":   _p1("Fang Gu wakes. Pick 1 player to kill (may jump to a living Outsider)."),
    "legion_night":    _p1("Legion wakes. Pick 1 player to kill tonight."),
    "pukka_night":     _p1("Pukka wakes. Pick 1 player to begin poisoning (previous target dies now)."),
    "zombuul_night": {
        "prompt": "Zombuul wakes. Kill 1 player (only if nobody died during the day), or pass.",
        "inputs": {
            "target": {"kind": PLAYER_SELECT, "pool": "alive", "optional": True},
            "pass":   {"kind": BOOLEAN},
        },
    },
    "shabaloth_night": {
        "prompt": "Shabaloth wakes. Pick up to 2 players to kill tonight.",
        "inputs": {
            "t1": {"kind": PLAYER_SELECT, "pool": "alive"},
            "t2": {"kind": PLAYER_SELECT, "pool": "alive", "optional": True},
        },
    },
    "po_night": {
        "prompt": "Po wakes. Kill up to 3 players (charged), kill 1, or pass to charge up.",
        "inputs": {
            "targets": {"kind": PLAYER_MULTISELECT, "pool": "alive", "count": 3, "optional": True},
            "pass":    {"kind": BOOLEAN},
        },
    },
    "ojo_night": {
        "prompt": "Ojo wakes. Name a character â€” that player dies (or a random player if not in play).",
        "inputs": {"character": {"kind": CHARACTER_SELECT, "char_pool": "script"}},
    },
    "al_hadikhia_night": {
        "prompt": "Al-Hadikhia wakes. Pick 3 players â€” each secretly chooses to live or die.",
        "inputs": {
            "t1": {"kind": PLAYER_SELECT, "pool": "alive"},
            "t2": {"kind": PLAYER_SELECT, "pool": "alive"},
            "t3": {"kind": PLAYER_SELECT, "pool": "alive"},
        },
    },
    "lleech_night":        _p1("Lleech wakes. Pick 1 player to kill tonight."),
    "lleech_setup":        _p1("Lleech setup (night 1). Pick the host player."),
    "yaggababble_night": {
        "prompt": "Yaggababble: did the Yaggababble say their secret phrase aloud today? Kill players accordingly.",
        "inputs": {"kill_count": {"kind": CHOICE, "options": [{"value": i, "label": str(i)} for i in range(5)]}},
    },
    "lil_monsta_night": {
        "prompt": "Lil' Monsta: which Minion holds the baby token tonight, and who do they kill?",
        "inputs": {
            "holder": {"kind": PLAYER_SELECT, "pool": "alive_min"},
            "target": {"kind": PLAYER_SELECT, "pool": "alive"},
        },
    },
    "kazali_night":        _p1("Kazali wakes (non-setup nights). Pick 1 player to kill."),
    "kazali_setup": {
        "prompt": "Kazali setup (night 1). Assign Minion roles to players.",
        "inputs": {"assignments": {"kind": PLAYER_CHAR_PAIRS}},
    },
    "lot_setup": {
        "prompt": "Lord of Typhon setup (night 1). Assign roles to the in-line players.",
        "inputs": {"assignments": {"kind": PLAYER_CHAR_PAIRS}},
    },
    "lot_night":           _p1("Lord of Typhon wakes. Pick 1 player to kill tonight."),

    # â”€â”€ TRIGGER-BASED END-OF-NIGHT DECISIONS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "sweetheart_drunk": {
        "prompt": "Sweetheart died. Pick 1 player to be drunk for the rest of the game.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive"}},
    },
    "barber_swap": {
        "prompt": "Barber triggered. The Demon may swap 2 players' characters (including char_type/alignment). Confirm the swap or pass.",
        "inputs": {
            "t1":   {"kind": PLAYER_SELECT, "pool": "all", "optional": True},
            "t2":   {"kind": PLAYER_SELECT, "pool": "all", "optional": True},
            "pass": {"kind": BOOLEAN},
        },
    },
    "hatter_swap": {
        "prompt": "Hatter triggered. Minions/Demon may swap to a new character of the same type. Confirm swaps.",
        "inputs": {"assignments": {"kind": PLAYER_CHAR_PAIRS}},
    },
    "imp_starpass": {
        "prompt": "Imp killed themselves â€” choose which Minion becomes the new Imp.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive_min"}},
    },
    "mayor_bounce": {
        "prompt": "Mayor is the Demon's target and nobody has died tonight. Pick who the death bounces to, or nobody.",
        "inputs": {
            "target":  {"kind": PLAYER_SELECT, "pool": "alive", "optional": True},
            "nobody":  {"kind": BOOLEAN},
        },
    },
    "farmer_replacement": {
        "prompt": "Farmer died at night. Pick 1 alive Townsfolk to become the new Farmer.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive_tf"}},
    },
    "klutz_choice": {
        "prompt": "Klutz died and must immediately pick a player. Pick 1 player â€” if good, that player dies.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive"}},
    },
    "moonchild_kill": {
        "prompt": "Moonchild claimed a kill target. Did the target publicly accuse the Moonchild? Should they die?",
        "inputs": {
            "target": {"kind": PLAYER_SELECT, "pool": "alive"},
            "dies":   {"kind": BOOLEAN},
        },
    },
    "plague_doctor_ability": {
        "prompt": "Plague Doctor died. Pick which Minion ability the Storyteller gains.",
        "inputs": {"character": {"kind": CHARACTER_SELECT, "char_pool": "min_script"}},
    },
    "tinker_night": {
        "prompt": "Tinker: may die tonight. Should the Tinker die?",
        "inputs": {"dies": {"kind": BOOLEAN}},
    },

    # â”€â”€ DAY ACTIONS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    "slayer_claim":  _p1("Slayer claims to slay â€” pick the target (once per game)."),
    "gossip_night": {
        "prompt": "Gossip made a public statement today. Was it true? If so, pick 1 player to die tonight.",
        "inputs": {
            "statement_true": {"kind": BOOLEAN},
            "target":         {"kind": PLAYER_SELECT, "pool": "alive", "optional": True},
        },
    },
    "psychopath_day":  _p1("Psychopath may kill 1 player during the day if they lose Roshambo."),
    "damsel_guess": {
        "prompt": "A Minion is guessing the Damsel. Confirm target player and whether the guess is correct.",
        "inputs": {
            "minion":  {"kind": PLAYER_SELECT, "pool": "alive_min"},
            "target":  {"kind": PLAYER_SELECT, "pool": "alive"},
            "correct": {"kind": BOOLEAN},
        },
    },
    "golem_nominate": {
        "prompt": "Golem nominates â€” pick the target. The Golem cannot kill if drunk/poisoned.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive"}},
    },
    "vizier_execute": {
        "prompt": "Vizier uses instant execution ability. Pick 1 player to execute immediately.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive"}},
    },
    "puzzlemaster_guess": {
        "prompt": "Puzzlemaster guesses the Demon player. Pick the target.",
        "inputs": {"target": {"kind": PLAYER_SELECT, "pool": "alive"}},
    },
    "professor_night": {
        "prompt": "Professor wakes. Pick 1 dead Townsfolk to resurrect (once per game), or pass.",
        "inputs": {
            "target": {"kind": PLAYER_SELECT, "pool": "dead_tf", "optional": True},
            "pass":   {"kind": BOOLEAN},
        },
    },

}  # end DECISION_DEFS

# â”€â”€ Resolver functions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Each takes (choices: dict, g: dict) and calls into botc_logic.

def _gp(g, pid): return BL.get_player(g, pid)
def _gc(g, char): return BL.get_character(g, char)

def _res_demon_info(ch, g):
    bluffs = [ch.get("bluff1"), ch.get("bluff2"), ch.get("bluff3")]
    g["_demon_bluffs"] = [b for b in bluffs if b]

def _res_barista(ch, g):
    b = _gc(g, "Barista")
    if b: BL.resolve_barista_night(b, ch["target"], ch.get("ability_num", 1), g)

def _res_monk(ch, g):
    p = _gc(g, "Monk")
    if p: BL.resolve_monk_night(p, ch["target"], g)

def _res_sailor(ch, g):
    p = _gc(g, "Sailor")
    if p: BL.resolve_sailor_night(p, ch["target"], g)

def _res_innkeeper(ch, g):
    p = _gc(g, "Innkeeper")
    drunk_key = ch.get("drunk", "t1")
    drunk_id = ch[drunk_key]
    if p: BL.resolve_innkeeper_night(p, ch["t1"], ch["t2"], drunk_id, g)

def _res_poisoner(ch, g):
    p = _gc(g, "Poisoner")
    if p: BL.resolve_poisoner_night(p, ch["target"], g)

def _res_witch(ch, g):
    p = _gc(g, "Witch")
    if p: BL.resolve_witch_night(p, ch["target"], g)

def _res_da(ch, g):
    p = _gc(g, "Devil's Advocate")
    if p: BL.resolve_da_night(p, ch["target"], g)

def _res_butler(ch, g):
    p = _gc(g, "Butler")
    if p: BL.resolve_butler_night(p, ch["target"], g)

def _res_preacher(ch, g):
    p = _gc(g, "Preacher")
    if p: BL.resolve_preacher_night(p, ch["target"], g)

def _res_exorcist(ch, g):
    p = _gc(g, "Exorcist")
    if p: BL.resolve_exorcist_night(p, ch["target"], g)

def _res_courtier(ch, g):
    p = _gc(g, "Courtier")
    if p and not ch.get("pass"): BL.resolve_courtier_night(p, ch.get("character"), g)

def _res_fearmonger(ch, g):
    p = _gc(g, "Fearmonger")
    if p: BL.resolve_fearmonger_night(p, ch["target"], g)

def _res_harpy(ch, g):
    p = _gc(g, "Harpy")
    if p: BL.resolve_harpy_night(p, ch["t1"], ch["t2"], g)

def _res_mezepheles(ch, g):
    p = _gc(g, "Mezepheles")
    if p: BL.resolve_mezepheles_night(p, ch["target"], ch.get("word", ""), g)

def _res_cerenovus(ch, g):
    p = _gc(g, "Cerenovus")
    if p: BL.resolve_cerenovus_night(p, ch["target"], ch.get("character"), g)

def _res_godfather(ch, g):
    p = _gc(g, "Godfather")
    if p and not ch.get("pass") and ch.get("target"):
        BL.resolve_godfather_night(p, ch["target"], g)

def _res_assassin(ch, g):
    p = _gc(g, "Assassin")
    if p and not ch.get("pass") and ch.get("target"):
        BL.resolve_assassin_night(p, ch["target"], g)

def _res_bone_collector(ch, g):
    p = _gc(g, "Bone Collector")
    if p and not ch.get("pass") and ch.get("target"):
        BL.resolve_bone_collector_night(p, ch["target"], g)

def _res_engineer(ch, g):
    p = _gc(g, "Engineer")
    if p and not ch.get("pass") and ch.get("assignments"):
        BL.resolve_engineer_night(p, ch["assignments"], g)

def _res_pit_hag(ch, g):
    p = _gc(g, "Pit-Hag")
    if p and ch.get("target") and ch.get("character"):
        char = ch["character"]
        ct = BL._BOFFIN_CHAR_TYPE.get(char, BL.TOWNSFOLK)
        aln = BL.EVIL if ct in (BL.MINION, BL.DEMON) else BL.GOOD
        BL.resolve_pit_hag_night(p, ch["target"], char, ct, aln, g)

def _res_summoner(ch, g):
    p = _gc(g, "Summoner")
    if p: BL.resolve_summoner_night(p, ch["target"], ch.get("character"), g)

def _res_wraith(ch, g):
    p = _gc(g, "Wraith")
    if p and not ch.get("pass") and ch.get("target"):
        BL.resolve_wraith_night(p, ch["target"], g)

def _res_washerwoman(ch, g):
    p = _gc(g, "Washerwoman")
    if p: BL.resolve_washerwoman_info(p, ch["t1"], ch["t2"], ch.get("character"), g)

def _res_librarian(ch, g):
    p = _gc(g, "Librarian")
    if p: BL.resolve_librarian_info(p, ch.get("t1"), ch.get("t2"), ch.get("character"), g)

def _res_investigator(ch, g):
    p = _gc(g, "Investigator")
    if p: BL.resolve_investigator_info(p, ch["t1"], ch["t2"], ch.get("character"), g)

def _res_chef(ch, g):
    p = _gc(g, "Chef")
    if p: BL.resolve_chef_info(p, g)

def _res_ft(ch, g):
    p = _gc(g, "Fortune Teller")
    if p: return BL.resolve_fortune_teller_night(p, ch["t1"], ch["t2"], g)

def _res_empath(ch, g):
    p = _gc(g, "Empath")
    if p: return BL.resolve_empath_night(p, g)

def _res_undertaker(ch, g):
    p = _gc(g, "Undertaker")
    if p: return BL.resolve_undertaker_night(p, g)

def _res_seamstress(ch, g):
    p = _gc(g, "Seamstress")
    if p: return BL.resolve_seamstress_night(p, ch["t1"], ch["t2"], g)

def _res_clockmaker(ch, g):
    p = _gc(g, "Clockmaker")
    if p: return BL.resolve_clockmaker_info(p, g)

def _res_dreamer(ch, g):
    p = _gc(g, "Dreamer")
    if p: return BL.resolve_dreamer_night(p, ch["target"], g)

def _res_grandmother(ch, g):
    p = _gc(g, "Grandmother")
    if p: return BL.resolve_grandmother_night(p, ch["target"], g)

def _res_noble(ch, g):
    p = _gc(g, "Noble")
    if p: return BL.resolve_noble_info(p, ch["t1"], ch["t2"], ch["t3"], g)

def _res_bounty_hunter(ch, g):
    p = _gc(g, "Bounty Hunter")
    if p: return BL.resolve_bounty_hunter_info(p, ch["target"], g)

def _res_shugenja(ch, g):
    p = _gc(g, "Shugenja")
    if p: return BL.resolve_shugenja_info(p, g)

def _res_ogre(ch, g):
    p = _gc(g, "Ogre")
    if p: return BL.resolve_ogre_night(p, ch["target"], g)

def _res_balloonist(ch, g):
    p = _gc(g, "Balloonist")
    if p: return BL.resolve_balloonist_night(p, ch["target"], g)

def _res_vi(ch, g):
    p = _gc(g, "Village Idiot")
    if p: return BL.resolve_village_idiot_night(p, ch["target"], g)

def _res_flowergirl(ch, g):
    p = _gc(g, "Flowergirl")
    if p: return BL.resolve_flowergirl_night(p, g)

def _res_town_crier(ch, g):
    p = _gc(g, "Town Crier")
    if p: return BL.resolve_town_crier_night(p, g)

def _res_oracle(ch, g):
    p = _gc(g, "Oracle")
    if p: return BL.resolve_oracle_night(p, g)

def _res_ravenkeeper(ch, g):
    p = next((x for x in g.get("players", []) if x["tokens"].get("ravenkeeper_triggered")), None)
    if p: return BL.resolve_ravenkeeper_info(p, ch["target"], g)

def _res_sage(ch, g):
    p = next((x for x in g.get("players", []) if x["tokens"].get("sage_triggered")), None)
    if p: return BL.resolve_sage_info(p, ch["t1"], ch["t2"], g)

def _res_juggler_day(ch, g):
    p = _gc(g, "Juggler")
    if p: BL.resolve_juggler_day(p, ch.get("guesses", []), g)

def _res_juggler_night(ch, g):
    p = _gc(g, "Juggler")
    if p: return BL.resolve_juggler_night(p, g)

def _res_gambler(ch, g):
    p = _gc(g, "Gambler")
    if p: BL.resolve_gambler_night(p, ch["target"], ch.get("character"), g)

def _res_high_priestess(ch, g):
    p = _gc(g, "High Priestess")
    if p: return BL.resolve_high_priestess_night(p, ch["target"], g)

def _res_chambermaid(ch, g):
    p = _gc(g, "Chambermaid")
    if p: return BL.resolve_chambermaid_night(p, ch["t1"], ch["t2"], g)

def _res_general(ch, g):
    p = _gc(g, "General")
    if p: return BL.resolve_general_night(p, ch.get("result"), g)

def _res_mathematician(ch, g):
    p = _gc(g, "Mathematician")
    if p: return BL.resolve_mathematician_night(p, g)

def _res_huntsman(ch, g):
    p = _gc(g, "Huntsman")
    if p: return BL.resolve_huntsman_night(p, ch["target"], ch.get("character"), g)

def _res_nw(ch, g):
    p = _gc(g, "Night Watchman")
    if p: BL.resolve_nightwatchman_night(p, ch["target"], g)

def _res_cult_leader(ch, g):
    p = _gc(g, "Cult Leader")
    if p: BL.resolve_cult_leader_night(p, ch.get("target"), g)

def _res_king(ch, g):
    p = _gc(g, "King")
    if p: return BL.resolve_king_night(p, g)

def _res_snake_charmer(ch, g):
    p = _gc(g, "Snake Charmer")
    if p: BL.resolve_snake_charmer_night(p, ch["target"], g)

def _res_harlot(ch, g):
    p = _gc(g, "Harlot")
    if p: return BL.resolve_harlot_night(p, ch["target"], g)

def _res_acrobat(ch, g):
    p = _gc(g, "Acrobat")
    if p: BL.resolve_acrobat_night(p, ch["target"], g)

def _res_lycanthrope(ch, g):
    p = _gc(g, "Lycanthrope")
    if p: return BL.resolve_lycanthrope_night(p, ch["target"], g)

def _res_imp(ch, g):
    demon = BL.get_character(g, "Imp")
    if demon: return BL.resolve_demon_kill(demon, _gp(g, ch["target"]), g)

def _res_demon_kill_generic(char):
    def _fn(ch, g):
        demon = BL.get_character(g, char)
        t = _gp(g, ch.get("target"))
        if demon and t: return BL.resolve_demon_kill(demon, t, g)
    return _fn

def _res_pukka(ch, g):
    p = _gc(g, "Pukka")
    if p: return BL.resolve_pukka_night(p, ch.get("target"), g)

def _res_zombuul(ch, g):
    p = _gc(g, "Zombuul")
    if p and not ch.get("pass") and ch.get("target"):
        t = _gp(g, ch["target"])
        if t: return BL.resolve_demon_kill(p, t, g)

def _res_shabaloth(ch, g):
    p = _gc(g, "Shabaloth")
    if p:
        targets = [t for t in [ch.get("t1"), ch.get("t2")] if t]
        return BL.resolve_shabaloth_night(p, targets, g)

def _res_po(ch, g):
    p = _gc(g, "Po")
    if p:
        targets = ch.get("targets") or []
        return BL.resolve_po_night(p, targets or None, g)

def _res_ojo(ch, g):
    p = _gc(g, "Ojo")
    if p: return BL.resolve_ojo_night(p, ch.get("character"), g)

def _res_alh(ch, g):
    p = _gc(g, "Al-Hadikhia")
    if p:
        tids = [ch.get("t1"), ch.get("t2"), ch.get("t3")]
        tids = [t for t in tids if t]
        return BL.resolve_al_hadikhia_night(p, tids, [], g)

def _res_lleech(ch, g):
    p = _gc(g, "Lleech")
    if p: BL.resolve_lleech_night(p, ch["target"], g)

def _res_lleech_setup(ch, g):
    p = _gc(g, "Lleech")
    if p: BL.resolve_lleech_setup(p, ch["target"], g)

def _res_lil_monsta(ch, g):
    BL.resolve_lil_monsta_vote(ch.get("holder"), g)
    if ch.get("target"): BL.resolve_lil_monsta_kill(ch["target"], g)

def _res_kazali(ch, g):
    p = _gc(g, "Kazali")
    if p: return BL.resolve_demon_kill(p, _gp(g, ch["target"]), g)

def _res_kazali_setup(ch, g):
    p = _gc(g, "Kazali")
    if p:
        changed = BL.resolve_kazali_night(p, ch.get("assignments", []), g)
        BL.post_kazali_lot_setup(g)
        return changed

def _res_lot_setup(ch, g):
    p = _gc(g, "Lord of Typhon")
    if p:
        changed = BL.resolve_lot_setup(p, ch.get("assignments", []), g)
        BL.post_kazali_lot_setup(g)
        return changed

def _res_sweetheart(ch, g):
    t = _gp(g, ch["target"])
    if t: t["tokens"]["sweetheart_drunk"] = True
    g.pop("_sweetheart_pending", None)

def _res_barber_swap(ch, g):
    if not ch.get("pass") and ch.get("t1") and ch.get("t2"):
        demon = next((p for p in g.get("players", []) if p["char_type"] == BL.DEMON and p["alive"]), None)
        if demon: BL.resolve_barber_swap(demon["id"], ch["t1"], ch["t2"], g)
    g.pop("_barber_triggered", None)

def _res_hatter_swap(ch, g):
    if ch.get("assignments"): BL.resolve_hatter_swap(ch["assignments"], g)
    g.pop("_hatter_triggered", None)

def _res_imp_starpass(ch, g):
    t = _gp(g, ch["target"])
    if t:
        t["character"] = "Imp"
        t["char_type"] = BL.DEMON

def _res_mayor_bounce(ch, g):
    if not ch.get("nobody") and ch.get("target"):
        t = _gp(g, ch["target"])
        src = {"type": BL.DEMON_KILL, "source_character": "Mayor bounce"}
        if t and BL.can_player_die(t, src, g) == BL.DIES: BL.resolve_death(t, src, g)
    g.pop("_mayor_protect_pending", None)

def _res_farmer(ch, g):
    t = _gp(g, ch["target"])
    if t:
        t["character"] = "Farmer"
        t["char_type"] = BL.TOWNSFOLK
        t["ability_active"] = True
    g.pop("_pending_farmer_replacement", None)

def _res_klutz(ch, g):
    BL.resolve_klutz_choice(
        next((p["id"] for p in g.get("players", []) if p["tokens"].get("klutz_triggered")), None),
        ch["target"], g
    )

def _res_moonchild(ch, g):
    if ch.get("dies"): BL.resolve_moonchild_night(g)

def _res_slayer(ch, g):
    p = _gc(g, "Slayer")
    if p: return BL.resolve_slayer_claim(p, ch["target"], g)

def _res_gossip(ch, g):
    p = _gc(g, "Gossip")
    if p: BL.resolve_gossip_night(p, None, None, ch.get("statement_true", False), ch.get("target"), g)

def _res_psychopath(ch, g):
    p = _gc(g, "Psychopath")
    if p: BL.resolve_psychopath_day(p, ch["target"], g)

def _res_damsel(ch, g):
    BL.resolve_damsel_guess(ch.get("minion"), ch.get("target"), g)

def _res_golem(ch, g):
    p = _gc(g, "Golem")
    if p: BL.resolve_golem_nominate(p["id"], ch["target"], g)

def _res_vizier(ch, g):
    BL.resolve_vizier_execute(
        next((p["id"] for p in g.get("players", []) if p["character"] == "Vizier"), None),
        ch["target"], g
    )

def _res_puzzlemaster(ch, g):
    BL.resolve_puzzlemaster_guess(
        next((p["id"] for p in g.get("players", []) if p["character"] == "Puzzlemaster"), None),
        ch["target"], g
    )

def _res_professor(ch, g):
    p = _gc(g, "Professor")
    if p and not ch.get("pass") and ch.get("target"):
        BL.resolve_professor_night(p, ch["target"], g)

def _res_pixie(ch, g):
    p = _gc(g, "Pixie")
    if p: BL.resolve_pixie_setup(p, ch.get("character"), g)

# â”€â”€ RESOLVERS dispatch table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

RESOLVERS = {
    "minion_info":           lambda ch, g: None,  # info delivery only, no state change
    "demon_info":            _res_demon_info,
    "barista_nightly":       _res_barista,
    "monk_night":            _res_monk,
    "sailor_night":          _res_sailor,
    "innkeeper_night":       _res_innkeeper,
    "poisoner_night":        _res_poisoner,
    "witch_night":           _res_witch,
    "devils_advocate_night": _res_da,
    "butler_night":          _res_butler,
    "preacher_night":        _res_preacher,
    "exorcist_night":        _res_exorcist,
    "courtier_night":        _res_courtier,
    "fearmonger_night":      _res_fearmonger,
    "harpy_night":           _res_harpy,
    "mezepheles_night":      _res_mezepheles,
    "cerenovus_night":       _res_cerenovus,
    "godfather_night":       _res_godfather,
    "assassin_night":        _res_assassin,
    "bone_collector_night":  _res_bone_collector,
    "engineer_night":        _res_engineer,
    "pit_hag_night":         _res_pit_hag,
    "summoner_night":        _res_summoner,
    "wraith_night":          _res_wraith,
    "washerwoman_info":      _res_washerwoman,
    "librarian_info":        _res_librarian,
    "investigator_info":     _res_investigator,
    "chef_info":             _res_chef,
    "fortune_teller_night":  _res_ft,
    "empath_night":          _res_empath,
    "undertaker_night":      _res_undertaker,
    "seamstress_night":      _res_seamstress,
    "clockmaker_info":       _res_clockmaker,
    "dreamer_night":         _res_dreamer,
    "grandmother_night":     _res_grandmother,
    "noble_info":            _res_noble,
    "bounty_hunter_info":    _res_bounty_hunter,
    "shugenja_info":         _res_shugenja,
    "ogre_night":            _res_ogre,
    "balloonist_night":      _res_balloonist,
    "village_idiot_night":   _res_vi,
    "flowergirl_night":      _res_flowergirl,
    "town_crier_night":      _res_town_crier,
    "oracle_night":          _res_oracle,
    "ravenkeeper_info":      _res_ravenkeeper,
    "sage_info":             _res_sage,
    "juggler_day":           _res_juggler_day,
    "juggler_night":         _res_juggler_night,
    "gambler_night":         _res_gambler,
    "high_priestess_night":  _res_high_priestess,
    "chambermaid_night":     _res_chambermaid,
    "general_night":         _res_general,
    "mathematician_night":   _res_mathematician,
    "huntsman_night":        _res_huntsman,
    "night_watchman_night":  _res_nw,
    "cult_leader_night":     _res_cult_leader,
    "king_night":            _res_king,
    "snake_charmer_night":   _res_snake_charmer,
    "harlot_night":          _res_harlot,
    "acrobat_night":         _res_acrobat,
    "lycanthrope_night":     _res_lycanthrope,
    "imp_night":             _res_imp,
    "no_dashii_night":       _res_demon_kill_generic("No Dashii"),
    "vortox_night":          _res_demon_kill_generic("Vortox"),
    "vigormortis_night":     _res_demon_kill_generic("Vigormortis"),
    "fang_gu_night":         _res_demon_kill_generic("Fang Gu"),
    "legion_night":          _res_demon_kill_generic("Legion"),
    "pukka_night":           _res_pukka,
    "zombuul_night":         _res_zombuul,
    "shabaloth_night":       _res_shabaloth,
    "po_night":              _res_po,
    "ojo_night":             _res_ojo,
    "al_hadikhia_night":     _res_alh,
    "lleech_night":          _res_lleech,
    "lleech_setup":          _res_lleech_setup,
    "lil_monsta_night":      _res_lil_monsta,
    "kazali_night":          _res_kazali,
    "kazali_setup":          _res_kazali_setup,
    "lot_setup":             _res_lot_setup,
    "lot_night":             _res_demon_kill_generic("Lord of Typhon"),
    "sweetheart_drunk":      _res_sweetheart,
    "barber_swap":           _res_barber_swap,
    "hatter_swap":           _res_hatter_swap,
    "imp_starpass":          _res_imp_starpass,
    "mayor_bounce":          _res_mayor_bounce,
    "farmer_replacement":    _res_farmer,
    "klutz_choice":          _res_klutz,
    "moonchild_kill":        _res_moonchild,
    "pixie_setup":           _res_pixie,
    "tinker_night":          lambda ch, g: (
        BL.resolve_death(_gp(g, next((p["id"] for p in g.get("players",[]) if p["character"]=="Tinker"),"")),
                         {"type": BL.ABILITY_KILL, "source_character": "Tinker"}, g)
        if ch.get("dies") else None
    ),
    "plague_doctor_ability": lambda ch, g: g.update({"_plague_doctor_ability": ch.get("character")}),
    "slayer_claim":          _res_slayer,
    "gossip_night":          _res_gossip,
    "psychopath_day":        _res_psychopath,
    "damsel_guess":          _res_damsel,
    "golem_nominate":        _res_golem,
    "vizier_execute":        _res_vizier,
    "puzzlemaster_guess":    _res_puzzlemaster,
    "professor_night":       _res_professor,
    "yaggababble_night":     lambda ch, g: None,  # ST handles kills manually
    "wizard_night":          lambda ch, g: None,  # TODO: add resolve_wizard_night to BL
    "steward_info":          lambda ch, g: None,  # info only
    "knight_info":           lambda ch, g: None,  # info only
    "pixie_setup":           _res_pixie,
}

# â”€â”€ Pending decision detector â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_pending_decisions(g):
    """
    Inspect game state flags and return a list of decision type strings
    that are currently waiting to be resolved. The caller (Discord renderer
    or LLM ST) should call make_decision(dtype, g) for each.
    """
    pending = []
    if g.get("_sweetheart_pending"):   pending.append("sweetheart_drunk")
    if g.get("_barber_triggered"):     pending.append("barber_swap")
    if g.get("_hatter_triggered"):     pending.append("hatter_swap")
    if g.get("_mayor_protect_pending"):pending.append("mayor_bounce")
    if g.get("_pending_farmer_replacement"): pending.append("farmer_replacement")
    if any(p["tokens"].get("klutz_triggered") for p in g.get("players", [])):
        pending.append("klutz_choice")
    if any(p["tokens"].get("ravenkeeper_triggered") for p in g.get("players", [])):
        pending.append("ravenkeeper_info")
    if any(p["tokens"].get("sage_triggered") for p in g.get("players", [])):
        pending.append("sage_info")
    if g.get("_pending_imp_transfer"):
        pending.append("imp_starpass")
    return pending
