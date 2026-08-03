"""ST-chats feature — player->character assignment parsing + per-game storage.

The Storyteller supplies a JSON (via /createstchats) mapping players to their
characters; /assignrole later looks a player up to reveal their role. Character
canonicalization + alignment come from botc_chardata.

Accepted JSON shapes (all normalize the same):
  1. {"players": [ {"name": "...", "character": "...", "alignment": "Good"|"Evil"?}, ... ]}
  2. [ {"name": "...", "character": "...", "alignment": ...?}, ... ]
  3. {"PlayerName": "Character", ...}                (alignment derived from type)
  4. {"PlayerName": {"character": "...", "alignment": ...?}, ...}
`alignment` is optional and only needed to pin a traveler's side.
"""

import os
import re
import json

import botc_chardata

_PATH = ("/home/discord-bot/st_assignments.json" if os.path.isdir("/home/discord-bot")
         else os.path.join(os.path.dirname(os.path.abspath(__file__)), "st_assignments.json"))


def _key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def parse_assignments(raw):
    """Parse a game JSON (str or decoded) into
        { player_key: {"player": name, "character": canonical, "alignment": "Good"/"Evil"} }
    Returns (assignments, errors)."""
    errors = []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        return {}, [f"Invalid JSON: {e}"]

    rows = None
    if isinstance(data, dict) and isinstance(data.get("players"), list):
        rows = data["players"]
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = []
        for name, val in data.items():
            if isinstance(val, str):
                rows.append({"name": name, "character": val})
            elif isinstance(val, dict):
                rows.append({"name": name, **val})
    if rows is None:
        return {}, ["Unrecognized JSON shape — expected a players list or a name->character map."]

    assignments = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("player") or "").strip()
        char = str(row.get("character") or row.get("role") or "").strip()
        if not name or not char:
            errors.append(f"Skipped entry missing name/character: {row}")
            continue
        info = botc_chardata.char_info(char, row.get("alignment"))
        if info is None:
            errors.append(f"Unknown character '{char}' (player '{name}').")
            continue
        assignments[_key(name)] = {
            "player": name,
            "character": info["name"],
            "alignment": info["alignment"],
        }
    return assignments, errors


def _load():
    try:
        with open(_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def set_assignments(guild_id, game_number, assignments):
    d = _load()
    d.setdefault(str(guild_id), {})[str(game_number)] = assignments
    tmp = _PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _PATH)


def get_assignments(guild_id, game_number):
    return _load().get(str(guild_id), {}).get(str(game_number), {})


def get_player(guild_id, game_number, name):
    """Look up a player's assignment by (freeform) name for a game, or None."""
    a = get_assignments(guild_id, game_number)
    k = _key(name)
    if k in a:
        return a[k]
    subs = [v for kk, v in a.items() if k and k in kk]
    return subs[0] if len(subs) == 1 else None
