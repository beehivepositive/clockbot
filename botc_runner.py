# botc_runner.py
import json, os, traceback, io, sys
from contextlib import redirect_stdout

sys.path.insert(0, '/home/discord-bot')
import botc_logic as BL

GAMES_PATH = "/home/discord-bot/botc_games.json"
DATA_PATH = "/home/discord-bot/botc_data.json"
CHAR_TYPES = {
    "townsfolk": BL.TOWNSFOLK, "outsider": BL.OUTSIDER,
    "minion": BL.MINION, "demon": BL.DEMON, "traveler": BL.TRAVELER
}
ALIGNMENTS = {"good": BL.GOOD, "evil": BL.EVIL}

def load_games():
    if os.path.exists(GAMES_PATH):
        try: return json.load(open(GAMES_PATH))
        except: pass
    return {}

def save_games(games):
    def serial(o):
        if isinstance(o, (set, frozenset)): return list(o)
        raise TypeError(f"Not serializable: {type(o)}")
    with open(GAMES_PATH, "w") as f:
        json.dump(games, f, indent=2, default=serial)

def get_game(key):
    return load_games().get(key)

def set_game(key, state):
    g = load_games()
    g[key] = state
    save_games(g)

def delete_game(key):
    g = load_games()
    g.pop(key, None)
    save_games(g)

def run_botc_code(code: str) -> str:
    """Execute code with botc_logic in scope. Returns printed output or error."""
    ns = {k: getattr(BL, k) for k in dir(BL) if not k.startswith("_")}
    ns.update({"json": json, "BL": BL})
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            exec(compile(code, "<botc>", "exec"), ns)
        out = buf.getvalue().strip()
        if "result" in ns and ns["result"] is not None:
            r = str(ns["result"])
            out = (out + "\n" + r).strip() if out else r
        return (out or "(no output)")[:2000]
    except Exception:
        return "Error:\n" + traceback.format_exc()[-600:]

def get_character_info(name: str) -> str:
    try:
        data = json.load(open(DATA_PATH))
        chars = data.get("characters", {})
        for k, v in chars.items():
            if k.lower() == name.lower():
                return f"**{k}**: {v.get('ability', 'No ability text.')}"
        return f"Character '{name}' not found."
    except Exception as e:
        return f"Error: {e}"

def make_player(pid: str, name: str, character: str, char_type: str, alignment: str) -> dict:
    ct = CHAR_TYPES.get(char_type.lower(), BL.TOWNSFOLK)
    al = ALIGNMENTS.get(alignment.lower(), BL.GOOD)
    return {
        "id": pid, "name": name, "character": character,
        "char_type": ct, "alignment": al,
        "alive": True, "ability_active": True, "tokens": {}
    }

def format_game_state(g: dict) -> str:
    if not g:
        return "No active game."
    night = g.get("night", 0)
    players = g.get("players", [])
    alive_count = sum(1 for p in players if p["alive"])
    phase = "Night" if night > 0 else "Setup"
    lines = [f"**{phase} {night}** | {alive_count}/{len(players)} alive"]
    for p in players:
        status = "\u2713" if p["alive"] else "\u2717"
        name = p.get("name", p["id"])
        char = p["character"]
        al = p["alignment"]
        ct = p["char_type"]
        toks = [k for k, v in p.get("tokens", {}).items() if v and not k.startswith("_")]
        tok_str = f" [{', '.join(toks[:3])}]" if toks else ""
        lines.append(f"{status} **{name}**: {char} ({ct}/{al}){tok_str}")
    return "\n".join(lines)

def game_state_to_logic(g: dict) -> dict:
    """Prepare game state dict for use with botc_logic functions (convert lists to sets etc)."""
    import copy
    state = copy.deepcopy(g)
    for k, v in state.items():
        if isinstance(v, list) and k.startswith("_woke"):
            state[k] = set(v)
    return state

def infer_char_type(character: str) -> str:
    """Infer char_type from botc_data.json."""
    try:
        data = json.load(open(DATA_PATH))
        chars = data.get("characters", {})
        for k, v in chars.items():
            if k.lower() == character.lower():
                return v.get("type", "townsfolk").lower()
    except: pass
    return "townsfolk"

def infer_alignment(char_type: str) -> str:
    if char_type in ("minion", "demon"):
        return "evil"
    return "good"

def build_player(id,name,character,char_type,alignment=None,tokens=None):
    if alignment is None: alignment=infer_alignment(char_type)
    return {"id":str(id),"name":name,"character":character,"char_type":char_type,
            "alignment":alignment,"alive":True,"ability_active":True,
            "tokens":tokens.copy() if tokens else {}}

def build_grim(players,script=None,boffin_char=None,lycan_faux_paw=None):
    import botc_logic as BL
    g={"active":True,"phase":"day","night":0,"day_num":1,
       "game_channel_ids":[],"log_channel_id":None,"script":script or [],
       "players":players,"_execution_occurred_today":False,
       "_last_executed":None,"_good_executions":0,"_day_ended":False}
    if boffin_char: g["_boffin_char"]=boffin_char
    if lycan_faux_paw: g["_lycan_faux_paw"]=str(lycan_faux_paw)
    BL.setup_boffin(g); BL.setup_vi_drunk(g); BL.setup_lycan_faux_paw(g)
    from botc_jinxes import build_active_jinxes
    build_active_jinxes(g)
    BL.resolve_xaan_setup(g)
    return g

def grim_json(players,script=None,**kw):
    import json
    return json.dumps(build_grim(players,script,**kw),indent=2)

# --- GRIMOIRE IMPORT ---
import re as _re

def _norm_role_id(s):
    if isinstance(s, dict): s=s.get("id","")
    if not isinstance(s, str): s=str(s) if s else ""
    return _re.sub(r"[^a-z0-9]","",s.lower())

def _build_role_lookup():
    try:
        from botc_knowledge import BOTC
        return {_norm_role_id(k):k for k in BOTC.get("characters",{})}
    except: return {}

_ROLE_LOOKUP=_build_role_lookup()

def _role_to_display(role_id):
    key=_norm_role_id(role_id)
    return _ROLE_LOOKUP.get(key, key)

def _role_char_type(display):
    try:
        from botc_knowledge import BOTC
        t=BOTC.get("characters",{}).get(display,{}).get("type","townsfolk")
        return {"townsfolk":"townsfolk","outsider":"outsider","minion":"minion","demon":"demon","traveler":"traveler"}.get(t,"townsfolk")
    except: return "townsfolk"

def parse_grim_json(data):
    import json as _j
    if isinstance(data,str): data=_j.loads(data)
    raw=data.get("players",[])
    script=[_role_to_display(r["id"]) for r in data.get("roles",[])]
    players=[]; rh_target=None; fp_target=None
    for pd in raw:
        disp=_role_to_display(pd.get("role",""))
        ctype=_role_char_type(disp)
        aln=infer_alignment(ctype)
        pid=pd.get("id") or pd["name"]
        p={"id":str(pid),"name":pd["name"],"character":disp,"char_type":ctype,
           "alignment":aln,"alive":not pd.get("isDead",False),
           "ability_active":True,"tokens":{}}
        if pd.get("isDead") and not pd.get("isVoteless"):
            p["tokens"]["ghost_vote_available"]=True
        for rem in pd.get("reminders",[]):
            if isinstance(rem,str): rem={"name":rem}
            rn=rem.get("name","")
            if rn=="Faux Paw": fp_target=str(pid)
            elif rn=="Red Herring": rh_target=str(pid)
            elif rn=="Poisoned":
                _role_raw=(rem.get("role","") or "").lower().replace(" ","")
                if not _role_raw or "poison" in _role_raw: p["tokens"]["poisoned_by_poisoner"]=True
                else: p.setdefault("_raw_reminders",[]).append(rem)
            elif rn in ("Is The Drunk","Is the Drunk"):
                p["tokens"]["drunk_display_as"]=disp
                p["character"]="Drunk"; p["char_type"]="outsider"
            else:
                p.setdefault("_raw_reminders",[]).append(rem)
        players.append(p)
    # second pass: wire red herring onto FT player
    if rh_target:
        ft=next((p for p in players if p["character"]=="Fortune Teller"),None)
        if ft: ft["tokens"]["red_herring"]=rh_target
    import botc_logic as BL
    g={"active":True,"phase":"day","night":0,"day_num":1,
       "game_channel_ids":[],"log_channel_id":None,"script":script,
       "players":players,"_execution_occurred_today":False,
       "_last_executed":None,"_good_executions":0,"_day_ended":False}
    if fp_target: g["_lycan_faux_paw"]=fp_target
    raw_bluffs=data.get("bluffs") or []
    g["_demon_bluffs"]=[_role_to_display(b["id"] if isinstance(b,dict) else b) for b in raw_bluffs if b]
    BL.setup_boffin(g); BL.setup_vi_drunk(g); BL.setup_lycan_faux_paw(g)
    return g

# --- CLOCKTOWER.LIVE EXPORT ---

def _edition_for_char(display):
    try:
        from botc_knowledge import BOTC
        s=BOTC.get("characters",{}).get(display,{}).get("script","")
        if isinstance(s,list): s=s[0] if s else ""
    except: s=""
    m={"tb":"tb","trouble brewing":"tb","bad moon rising":"bmr",
       "sects and violets":"snv","sects_and_villains":"snv"}
    return m.get(s.lower(),"custom")

def _reminder_obj(src_char,src_ctype,name):
    return {"role":_norm_role_id(src_char),"team":src_ctype,
            "edition":_edition_for_char(src_char),"name":name}
def to_clocktower_json(g,bluffs=None):
    import json as _j
    extra={p["id"]:[] for p in g["players"]}
    ft=next((p for p in g["players"] if p.get("character")=="Fortune Teller"),None)
    if ft:
        rh=ft.get("tokens",{}).get("red_herring")
        if rh and rh in extra: extra[rh].append(_reminder_obj("Fortune Teller","townsfolk","Red Herring"))
    fp=g.get("_lycan_faux_paw")
    if fp and fp in extra: extra[fp].append(_reminder_obj("Lycanthrope","townsfolk","Faux Paw"))
    players_out=[]
    for p in g["players"]:
        pid=p["id"]; reminders=list(extra.get(pid,[]))
        if p.get("tokens",{}).get("poisoned_by_poisoner"):
            reminders.append(_reminder_obj("Poisoner","minion","Poisoned"))
        char=p.get("character",""); display_role=_norm_role_id(char)
        if char=="Drunk":
            fake=p.get("tokens",{}).get("drunk_display_as","")
            if fake:
                display_role=_norm_role_id(fake)
                reminders.append(_reminder_obj("Drunk","outsider","Is The Drunk"))
        is_dead=not p.get("alive",True)
        ghost=p.get("tokens",{}).get("ghost_vote_available",False)
        players_out.append({"name":p["name"],"id":p.get("id",""),
            "connected":False,"role":display_role,"alignmentIndex":0,
            "reminders":reminders,"isVoteless":is_dead and not ghost,
            "hasTwoVotes":False,"hasResponded":{},"isDead":is_dead,
            "handRaised":False,"pronouns":p.get("pronouns","")})
    script_roles=[{"id":_norm_role_id(r)} for r in g.get("script",[])]
    bl=[]
    for b in (bluffs or g.get("_demon_bluffs") or [None,None,None]):
        bl.append({"id":_norm_role_id(b)} if b else None)
    return _j.dumps({"bluffs":bl,"edition":{"id":"custom","author":"","name":""},
        "roles":script_roles,"npcs":[],"players":players_out},indent=2)
