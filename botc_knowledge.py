import json, os
_path = os.path.join(os.path.dirname(__file__), "botc_data.json")
BOTC = json.load(open(_path))
def get_knowledge(): return BOTC
def get_section(key): return BOTC.get(key,{})
def get_mechanic(key): return BOTC.get("mechanics",{}).get(key,{})
def get_character(name): return BOTC.get("characters",{}).get(name,{})
BOTC_KNOWLEDGE=""
