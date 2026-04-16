"""Shared state helpers — avoids circular imports between main.py and botc_st.py."""
import os, json, re

WHISPER_STATE_PATH = "/home/discord-bot/whisper_state.json"

def load_whisper_state():
    if os.path.exists(WHISPER_STATE_PATH):
        with open(WHISPER_STATE_PATH) as f: return json.load(f)
    return {}

def save_whisper_state(state):
    with open(WHISPER_STATE_PATH, "w") as f: json.dump(state, f)

def get_game_state(k):
    d = load_whisper_state().get(k, {})
    d.setdefault("limit", 5); d.setdefault("used", 0)
    d.setdefault("player_counts", {}); d.setdefault("threads", [])
    d.setdefault("day", 1); d.setdefault("nominations_enabled", False)
    d.setdefault("nominees", []); d.setdefault("nominators", [])
    d.setdefault("dead_players", [])
    return d

def set_game_state(k, data):
    s = load_whisper_state(); s[k] = data; save_whisper_state(s)

def get_game_key(name):
    if "robot-playground" in name: return "robot-playground"
    if "pridegame" in name: return "pridegame"
    if "game185-rerack" in name: return "185-rerack"
    m = re.search(r"game-?([a-z0-9]+)", name)
    return m.group(1) if m else None

def is_excluded(name):
    if "focused" in name or name.endswith("-focus"): return True
    if name.endswith("-chat") and "ascension" not in name: return True
    if "whisper" in name: return False
    return (name.endswith("-logs") or name.endswith("-log") or
            bool(re.search(r"-logs-", name)))

def find_dest(channels):
    for ch in channels:
        n = ch.name
        if (n.endswith("-logs") or n.endswith("-log")) and "whisper" not in n:
            return ch
    return None
