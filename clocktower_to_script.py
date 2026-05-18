"""
Convert a clocktower.live game state JSON into the script.bloodontheclocktower.com upload format.

Usage:
    python clocktower_to_script.py '<json string>'
    python clocktower_to_script.py game_state.json
    python clocktower_to_script.py game_state.json --name "My Script" --author "Me"

The script tool format is an array:
    [{"id":"_meta","name":"...","author":"..."}, "characterid1", "characterid2", ...]

Character IDs are the character name lowercased with all non-alphanumeric chars stripped.
"""

import json
import re
import sys

# Full character lists for the three base editions, in canonical script order.
# IDs match the script tool's format: lowercase, alphanumeric only.
BASE_EDITIONS = {
    "tb": [
        # Townsfolk
        "washerwoman", "librarian", "investigator", "chef", "empath",
        "fortuneteller", "undertaker", "monk", "ravenkeeper", "virgin",
        "slayer", "soldier", "mayor",
        # Outsiders
        "butler", "drunk", "recluse", "saint",
        # Minions
        "poisoner", "spy", "scarletwoman", "baron",
        # Demon
        "imp",
    ],
    "bmr": [
        # Townsfolk
        "grandmother", "sailor", "chambermaid", "exorcist", "innkeeper",
        "gambler", "gossip", "courtier", "professor", "minstrel",
        "tealady", "pacifist", "fool",
        # Outsiders
        "tinker", "moonchild", "goon", "lunatic",
        # Minions
        "godfather", "devilsadvocate", "assassin", "mastermind",
        # Demons
        "zombuul", "pukka", "shabaloth", "po",
    ],
    "snv": [
        # Townsfolk
        "clockmaker", "dreamer", "snakecharmer", "mathematician", "flowergirl",
        "towncrier", "oracle", "savant", "seamstress", "philosopher",
        "artist", "juggler", "sage",
        # Outsiders
        "mutant", "sweetheart", "barber", "klutz",
        # Minions
        "eviltwin", "witch", "cerenovus", "pithag",
        # Demons
        "fanggu", "vigormortis", "nodashii", "vortox",
    ],
}

EDITION_NAMES = {
    "tb": "Trouble Brewing",
    "bmr": "Bad Moon Rising",
    "snv": "Sects & Violets",
}


def norm_id(s):
    """Strip to lowercase alphanumeric — matches clocktower.live's internal ID format."""
    if s is None:
        return ""
    if isinstance(s, dict):
        s = s.get("id", "")
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def convert(game_state, name=None, author=None):
    """
    Convert a clocktower.live game state dict (or JSON string) to script tool format.
    Returns a list ready for json.dumps().
    """
    if isinstance(game_state, str):
        game_state = json.loads(game_state)

    edition_id = norm_id(game_state.get("edition", {}).get("id", ""))
    roles_raw = game_state.get("roles", "")

    # roles is sometimes a JSON string rather than already-parsed
    if isinstance(roles_raw, str) and roles_raw.strip().startswith("["):
        try:
            roles_raw = json.loads(roles_raw)
        except json.JSONDecodeError:
            roles_raw = ""

    # Determine character list
    if roles_raw and isinstance(roles_raw, list) and len(roles_raw) > 0:
        # Custom script: roles is a list of {"id": "..."} objects or strings
        # norm_id returns "" for None/empty entries; filter those out
        characters = [norm_id(r) for r in roles_raw if norm_id(r)]
        default_name = game_state.get("edition", {}).get("name", "") or "Custom Script"
        default_author = game_state.get("edition", {}).get("author", "") or ""
    elif edition_id in BASE_EDITIONS:
        # Base edition: use hardcoded full character list
        characters = BASE_EDITIONS[edition_id]
        default_name = EDITION_NAMES[edition_id]
        default_author = ""
    else:
        # Unknown / empty — return empty script
        characters = []
        default_name = "Unknown Script"
        default_author = ""

    meta = {
        "id": "_meta",
        "name": name if name is not None else default_name,
        "author": author if author is not None else default_author,
    }

    return [meta] + characters


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Convert clocktower.live JSON to script tool format")
    parser.add_argument("input", help="JSON string or path to .json file")
    parser.add_argument("--name", default=None, help="Override script name")
    parser.add_argument("--author", default=None, help="Override author")
    args = parser.parse_args()

    src = args.input.strip()
    if src.startswith("{") or src.startswith("["):
        data = src
    else:
        with open(src, encoding="utf-8") as f:
            data = f.read()

    result = convert(data, name=args.name, author=args.author)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
