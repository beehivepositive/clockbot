"""Character data accessor for the ST-chats feature.

Maps a character name -> alignment / ability text / token icon, built on
botc_data.json (ability + type) and botc_assets (CDN-backed token images).
Kept small and side-effect-free so commands can import it cheaply.
"""

import os
import re
import json

import botc_assets

_DATA_PATH = ("/home/discord-bot/botc_data.json" if os.path.isdir("/home/discord-bot")
              else os.path.join(os.path.dirname(os.path.abspath(__file__)), "botc_data.json"))

_EVIL_TYPES = {"minion", "demon"}

_chars = None    # canonical name -> raw character dict
_by_key = None   # normalized key -> canonical name


def _key(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _load():
    global _chars, _by_key
    if _chars is None:
        with open(_DATA_PATH) as f:
            _chars = json.load(f).get("characters", {})
        _by_key = {_key(name): name for name in _chars}
    return _chars


def resolve_name(name):
    """Resolve a freeform character name/id to the canonical botc_data.json key,
    or None if it can't be matched unambiguously."""
    _load()
    k = _key(name)
    if not k:
        return None
    if k in _by_key:
        return _by_key[k]
    subs = [orig for kk, orig in _by_key.items() if k in kk]
    return subs[0] if len(subs) == 1 else None


def char_info(name, alignment=None):
    """Return a dict describing a character, or None if unknown:
        {name, type, alignment, is_traveler, ability, icon, icon_good, icon_evil}
    `alignment` ("Good"/"Evil") overrides the type-derived value — required for
    travelers, whose alignment the Storyteller assigns."""
    _load()
    canon = resolve_name(name)
    if canon is None:
        return None
    c = _chars[canon]
    typ = c.get("type", "townsfolk")
    align = (alignment or ("Evil" if typ in _EVIL_TYPES else "Good")).title()
    evil = align.lower() == "evil"
    return {
        "name": canon,
        "type": typ,
        "alignment": align,
        "is_traveler": typ == "traveler",
        "ability": c.get("ability", ""),
        "icon": botc_assets.get_token_path(canon, use_evil=evil),
        "icon_good": botc_assets.get_token_path(canon, use_evil=False),
        "icon_evil": botc_assets.get_token_path(canon, use_evil=True),
        "icon_url": botc_assets.get_token_url(canon, use_evil=evil),
    }
