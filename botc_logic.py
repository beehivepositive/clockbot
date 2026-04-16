"""
Blood on the Clocktower - Game Logic
Structured rule processing for common game situations.
Each function takes a grimoire dict representing full game state.

Grimoire structure:
  players: list of player dicts:
    id, name, character, char_type, alignment, alive,
    ability_active, ability_used, tokens (dict), ghost_vote_available
  night: int (0 = day phase)
  day: int
  script: list of character names on the script
  _execution_occurred_today: bool
  _last_executed: player id or None
  _good_executions: int (running count)
  _day_ended: bool
"""

GOOD = 'good'
EVIL = 'evil'
TOWNSFOLK = 'townsfolk'
OUTSIDER = 'outsider'
MINION = 'minion'
DEMON = 'demon'
TRAVELER = 'traveler'

DEMON_KILL = 'demon_kill'
EXECUTION = 'execution'
ABILITY_KILL = 'ability_kill'
RIOT_KILL = 'riot_kill'

SURVIVES = 'survives'
DIES = 'dies'

# Canonical character-type registry
# Use canonical_char_type(name) for setup/script logic.
# Use player["char_type"] for in-game mechanics (Pit-Hag etc. mutate it).
try:
    import json as _j, os as _os
    _cd=_j.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),"botc_data.json")))
    _tm={"townsfolk":"townsfolk","outsider":"outsider","minion":"minion","demon":"demon","traveler":"traveler"}
    CHARACTER_TYPE={n:_tm.get(v.get("type","townsfolk"),"townsfolk") for n,v in _cd.get("characters",{}).items()}
    del _j,_os,_cd,_tm
except Exception:
    CHARACTER_TYPE={}

def canonical_char_type(character_name):
    """Canonical char_type for a character name (from botc_data.json)."""
    return CHARACTER_TYPE.get(character_name, TOWNSFOLK)



# Tokens that expire at the start of each new night.
# Add any new one-night token here — start_of_night clears them automatically.
ONE_NIGHT_TOKENS = frozenset({
    "monk_target",
    "da_target",
    "sailor_target",
    "sailor_protected",
    "sailor_self_drunk",
    "innkeeper_protected",
    "innkeeper_drunk",
    "poisoned_by_poisoner",
    "boffin_sailor_drunked",
    "boffin_sailor_protected",
    "boffin_sailor_target",
    "goon_triggered_night",
    "moonchild_target",
    "gossip_fired",
    "drunk_tonight",  # Organ Grinder
    "ysk_pending",
    "barista_sober_healthy",
    "barista_double_ability",
    "acrobat_target",
})

# --- PLAYER CLASS ---
class Player:
    """Wraps a player dict. New code uses attributes; old code uses dict interface."""
    __slots__ = ("_d",)
    def __init__(self, d): self._d = d
    @property
    def id(self): return self._d["id"]
    @property
    def name(self): return self._d.get("name", "")
    @property
    def character(self): return self._d["character"]
    @character.setter
    def character(self, v): self._d["character"] = v
    @property
    def char_type(self): return self._d["char_type"]
    @char_type.setter
    def char_type(self, v): self._d["char_type"] = v
    @property
    def alignment(self): return self._d["alignment"]
    @alignment.setter
    def alignment(self, v): self._d["alignment"] = v
    @property
    def alive(self): return self._d["alive"]
    @alive.setter
    def alive(self, v): self._d["alive"] = v
    @property
    def ability_active(self): return self._d["ability_active"]
    @ability_active.setter
    def ability_active(self, v): self._d["ability_active"] = v
    @property
    def tokens(self): return self._d["tokens"]
    @property
    def subinstance(self):
        t = self._d["tokens"]
        ci = t.get("cannibal_instance")
        if ci: return ci
        bi = t.get("boffin_instance")
        if bi: return bi
        cc = t.get("copied_character")
        if cc:
            return {"source":"Philosopher","character":cc,"tokens":t,"ability_active":True}
        return None
    def __getitem__(self, k): return self._d[k]
    def __setitem__(self, k, v): self._d[k] = v
    def __contains__(self, k): return k in self._d
    def get(self, k, default=None): return self._d.get(k, default)
    def setdefault(self, k, default=None): return self._d.setdefault(k, default)
    def pop(self, k, *args): return self._d.pop(k, *args)
    def __eq__(self, other):
        if isinstance(other, Player): return self._d is other._d
        if isinstance(other, dict): return self._d is other
        return NotImplemented
    def __hash__(self): return id(self._d)
    def __repr__(self): return f"Player({self._d.get('character','?')})"

class AbilityProxy(Player):
    """Proxy acting as borrowed character. Drunk checks use real player."""
    __slots__ = ("_d",)
    def __init__(self, real_player, inst_tokens, character,
                 override_id=None, override_alignment=None,
                 override_char_type=None):
        rp = real_player._d if isinstance(real_player, Player) else real_player
        d = {
            "id": override_id if override_id is not None else rp["id"],
            "name": rp.get("name", ""),
            "character": character,
            "char_type": (override_char_type
                          if override_char_type is not None else rp["char_type"]),
            "alignment": (override_alignment
                          if override_alignment is not None else rp["alignment"]),
            "alive": rp["alive"],
            "ability_active": True,
            "tokens": inst_tokens,
            "_real_player": rp,
        }
        super().__init__(d)

# --- GRIMOIRE HELPERS ---
def get_player(g, pid):
    d = next((p for p in g["players"] if p["id"] == pid), None)
    return Player(d) if d is not None else None

def make_ability_proxy(real_player, inst_tokens, character=None,
                       override_id=None, override_alignment=None,
                       override_char_type=None):
    """Legacy helper — delegates to AbilityProxy."""
    return AbilityProxy(real_player, inst_tokens,
                        character or real_player["character"],
                        override_id=override_id,
                        override_alignment=override_alignment,
                        override_char_type=override_char_type)

def effective_character(player, g):
    """The character a player effectively acts as (borrowed ability if any)."""
    t = player.tokens if isinstance(player, Player) else player.get("tokens", {})
    ci = t.get("cannibal_instance")
    if ci and ci.get("ability_active") and ci.get("character"):
        return ci["character"]
    bi = t.get("boffin_instance")
    if bi and bi.get("ability_active") and bi.get("character"):
        return bi["character"]
    cc = t.get("copied_character")
    if cc: return cc
    return player["character"]

def get_character(g, name):
    d = next((p for p in g["players"] if p["character"] == name), None)
    return Player(d) if d is not None else None

def get_alive_players(g): return [p for p in g["players"] if p["alive"]]
def count_alive(g): return sum(1 for p in g["players"] if p["alive"])
def count_alive_non_trav(g): return sum(1 for p in g["players"] if p["alive"] and p["char_type"]!=TRAVELER)
def count_visible_alive(g): return sum(1 for p in g["players"] if p["alive"] and not registers_as_dead(p))
def count_visible_alive_non_trav(g): return sum(1 for p in g["players"] if p["alive"] and not registers_as_dead(p) and p["char_type"]!=TRAVELER)
def demon_is_dead(g): return not any(p["char_type"]==DEMON and p["alive"] for p in g["players"])

def get_alignment(player,g):
    """Effective alignment — Ogre adopts alignment of their chosen player."""
    if player["character"]=="Ogre":
        t=get_player(g,player["tokens"].get("ogre_chosen"))
        if t: return t["alignment"]
    return player["alignment"]

def registers_as_dead(player):
    """Zombuul registers as dead to living-only abilities, but only after using their survival."""
    return player["character"]=="Zombuul" and player["tokens"].get("zombuul_registers_dead",False)

def get_alive_neighbors(player,g):
    """Return (left,right) alive neighbors; skips registered-dead (Zombuul)."""
    alive=[p for p in get_alive_players(g) if not registers_as_dead(p)]
    if player not in alive: return None,None
    i=alive.index(player)
    return alive[(i-1)%len(alive)],alive[(i+1)%len(alive)]

# --- MISREGISTRATION ---
def _has_spy_ability(player,g):
    char=player["character"]
    if char=="Spy": return True
    if char=="Alchemist" and player["tokens"].get("alchemist_ability")=="Spy":
        return not is_drunk_or_poisoned(player,g)
    inst=player["tokens"].get("boffin_instance")
    if inst and inst.get("character")=="Alchemist":
        if inst.get("tokens",{}).get("alchemist_ability")=="Spy":
            return not is_boffin_impaired(g)
    return False

# Checked first before any other modifier when an ability inspects alignment or type.
def check_misregistration(player,check_type,g):
    char=player["character"]
    _hermit_recluse=char=="Hermit" and player["tokens"].get("hermit_instances",{}).get("Recluse")
    if check_type=="alignment":
        if char in ("Spy","Recluse","Legion") or _has_spy_ability(player,g) or _hermit_recluse:
            return player["tokens"].get("registers_as_alignment",player["alignment"])
        if char=="Ogre": return get_alignment(player,g)
        lycan=get_character(g,"Lycanthrope")
        if (lycan and lycan["alive"] and not is_drunk_or_poisoned(lycan,g)
                and g.get("_lycan_faux_paw")==player["id"]
                and player["alignment"]==GOOD):
            return EVIL
        return player["alignment"]
    if check_type=="char_type":
        if char in ("Spy","Recluse","Legion") or _has_spy_ability(player,g) or _hermit_recluse:
            return player["tokens"].get("registers_as_type",player["char_type"])
        if player["id"]==g.get("_lil_monsta_holder"): return DEMON
        return player["char_type"]
    if check_type=="character":
        if char in ("Spy","Recluse") or _has_spy_ability(player,g) or _hermit_recluse:
            return player["tokens"].get("registers_as_character",player["character"])
        return player["character"]
    return None

# --- DRUNK / POISONED ---
def _no_dashii_targets(nd,g):
    """Find nearest Townsfolk in each direction by seat order."""
    players=g["players"]
    if nd not in players: return set()
    idx=players.index(nd); n=len(players); targets=set()
    for direction in (-1,1):
        for dist in range(1,n):
            p=players[(idx+direction*dist)%n]
            if check_misregistration(p,"char_type",g)==TOWNSFOLK:
                targets.add(p["id"]); break
    return targets


def is_demon_source(player,g):
    return player["char_type"]==DEMON or player["id"]==g.get("_lil_monsta_holder")
def is_safe_from_demon_effect(target,source,g):
    if not is_demon_source(source,g): return False
    return is_safe_from_demon(target,g)
def try_impose_effect(source,target,key,value,g):
    if is_safe_from_demon_effect(target,source,g): return False
    target["tokens"][key]=value
    return True
def is_safe_from_demon(player,g):
    monk=get_character(g,"Monk")
    if monk and monk["alive"] and not ability_inactive(monk,g):
        if monk["tokens"].get("monk_target")==player["id"]: return True
    pid=player["id"]
    for _p in g["players"]:
        if not _p["alive"]: continue
        for _key in ("cannibal_instance","boffin_instance"):
            _inst=_p["tokens"].get(_key)
            if (_inst and _inst.get("ability_active")
                    and _inst.get("character")=="Monk"
                    and _inst["tokens"].get("monk_target")==pid):
                return True
        if (_p["tokens"].get("copied_character")=="Monk"
                and _p["tokens"].get("monk_target")==pid):
            return True
    if player["character"]=="Soldier" and not is_drunk_or_poisoned(player,g): return True
    return False

def get_poison_sources(player,g):
    src=[]
    t=player["tokens"]
    if t.get("poisoned_by_poisoner"): src.append("Poisoner")
    if t.get("snake_charmer_poisoned") and player["character"]==t.get("snake_charmer_poisoned_char","Snake Charmer"): src.append("Snake Charmer")
    if t.get("widow_poisoned"): src.append("Widow")
    nd=get_character(g,"No Dashii")
    if nd and nd["alive"] and nd["id"]!=player["id"] and not is_drunk_or_poisoned(nd,g):
        if player["id"] in _no_dashii_targets(nd,g):
            _cmp=g.setdefault("_nd_poison_computing",set())
            if player["id"] in _cmp: src.append("No Dashii")
            else:
                _cmp.add(player["id"])
                try:
                    if not is_safe_from_demon_effect(player,nd,g): src.append("No Dashii")
                finally: _cmp.discard(player["id"])
    if t.get("pukka_poisoned"): src.append("Pukka")
    ll=get_character(g,"Lleech")
    if ll and ll["alive"] and ll["id"]!=player["id"] and not is_drunk_or_poisoned(ll,g):
        if player["id"]==ll["tokens"].get("lleech_host"): src.append("Lleech")
    vm=get_character(g,"Vigormortis")
    if t.get("vigormortis_poisoned") and vm and vm["alive"]: src.append("Vigormortis")
    can=get_character(g,"Cannibal")
    if can and can["alive"] and player["id"]==can["id"]:
        ci=can["tokens"].get("cannibal_instance")
        if ci is not None and not ci.get("ability_active",True):
            src.append("Cannibal")
        elif ci is not None:
            _bid=ci.get("bound_player_id")
            if _bid:
                _ex=get_player(g,_bid)
                if _ex and check_misregistration(_ex,"alignment",g)==EVIL: src.append("Cannibal")
        elif ci is None:
            ex=get_player(g,g.get("_cannibal_executee_id"))
            if ex and (check_misregistration(ex,"alignment",g))==EVIL:
                src.append("Cannibal")
    xaan=get_character(g,"Xaan")
    if g.get("_xaan_tf_poisoned") and player["char_type"]==TOWNSFOLK and xaan:
        if not is_safe_from_demon_effect(player,xaan,g): src.append("Xaan")
    if player["character"] == "Damsel":
        from botc_jinxes import call_jinx_hook
        if call_jinx_hook("spy_damsel_poisoned", g): src.append("Spy")
        if call_jinx_hook("widow_damsel_poisoned", g): src.append("Widow")
    return src

def get_drunk_sources(player,g):
    src=[]; t=player["tokens"]
    char=player["character"]
    if t.get("courtier_drunk_remaining",0)>0: src.append("Courtier")
    if g.get("_minstrel_drunk") and player["char_type"]!=TRAVELER: src.append("Minstrel")
    if t.get("goon_drunk"): src.append("Goon")
    for _sp in g.get("players",[]):
        if _sp.get("alive") and _sp["tokens"].get("sailor_target")==player["id"]: src.append("Sailor"); break
    og=get_character(g,"Organ Grinder")
    if og and og["alive"] and og["tokens"].get("drunk_tonight") and player["id"]==og["id"]: src.append("Organ Grinder")
    phil=get_character(g,"Philosopher")
    _phil_char = (player.get("_real_player") or {}).get("character", char)
    if phil and phil["tokens"].get("copied_character")==_phil_char:
        if phil["alive"] and not ability_inactive(phil,g): src.append("Philosopher")
    if player["tokens"].get("sailor_self_drunk"): src.append("Sailor")
    if player["tokens"].get("boffin_sailor_drunked"): src.append("Sailor")
    if player["tokens"].get("sweetheart_drunk"): src.append("Sweetheart")
    if player["tokens"].get("innkeeper_drunk"): src.append("Innkeeper")
    if player["tokens"].get("puzzlemaster_drunk"):src.append("Puzzlemaster")
    if t.get("vi_drunk") and player["character"]=="Village Idiot": src.append("Village Idiot")
    return src

def is_drunk_or_poisoned(player,g):
    rp=player.get("_real_player",player)
    if rp["tokens"].get("barista_sober_healthy"): return False
    return bool(get_drunk_sources(player,g) or get_poison_sources(player,g))
def is_silenced(player,g):
    rp=player.get("_real_player",player)
    return bool(rp["tokens"].get("preacher_silenced"))
def ability_inactive(player,g):
    rp=player.get("_real_player",player)
    return is_drunk_or_poisoned(rp,g) or is_silenced(rp,g)


def begin_ability(player, target_id, g, used_token=None):
    if not player.get("ability_active"): return False
    if used_token:
        if player["tokens"].get(used_token): return False
        player["tokens"][used_token] = True
    g.setdefault("_woke_tonight", set()).add(player["id"])
    _was = ability_inactive(player, g)
    if target_id:
        check_goon_targeting(player, target_id, g)
        if not _was and ability_inactive(player, g): return False
    if _was: return False
    return True

def begin_ability_multi(player, target_ids, g, used_token=None):
    if not player.get("ability_active"): return False
    if used_token:
        if player["tokens"].get(used_token): return False
        player["tokens"][used_token] = True
    g.setdefault("_woke_tonight", set()).add(player["id"])
    _was = ability_inactive(player, g)
    for tid in (target_ids or []):
        if tid: check_goon_targeting(player, tid, g)
    if not _was and ability_inactive(player, g): return False
    if _was: return False
    return True

# --- INFORMATION DELIVERY ---
# Order: misregistration -> Vortox -> drunk/poisoned
def resolve_information(receiver,raw_info,g):
    """Returns (info, accurate) where accurate: True=info is correct, False=info is definitely false (Vortox), None=ST discretion (drunk/poisoned — may be true or false, ability cannot affect game state)."""
    info=dict(raw_info)
    if "players" in info:
        for ref in info["players"]:
            rp=get_player(g,ref.get("id"))
            if rp:
                ref["effective_alignment"]=check_misregistration(rp,"alignment",g)
                ref["effective_char_type"]=check_misregistration(rp,"char_type",g)
    rp_recv=receiver.get("_real_player",receiver)
    vortox=get_character(g,"Vortox")
    if vortox and vortox["alive"] and not is_drunk_or_poisoned(vortox,g):
        if not rp_recv["tokens"].get("barista_sober_healthy"):
            if check_misregistration(receiver,"char_type",g)==TOWNSFOLK and not is_safe_from_demon_effect(receiver,vortox,g):
                return info,False
    if receiver["character"] in ("Drunk","Marionette","Lunatic") or is_drunk_or_poisoned(receiver,g):
        return info,None
    return info,True

# --- DEATH PROTECTION ---
def can_player_die(player,kill_source,g):
    """Returns SURVIVES or DIES. kill_source: {type, source_character}"""
    if kill_source.get("bypass_protection"): return DIES
    if kill_source.get("type")==RIOT_KILL: return DIES
    t=player["tokens"]
    if player["character"]=="Fool" and not t.get("fool_used") and not is_drunk_or_poisoned(player,g):
        t["fool_used"]=True; return SURVIVES
    if player["character"]=="Zombuul" and kill_source["type"]==EXECUTION and not t.get("zombuul_used") and not is_drunk_or_poisoned(player,g):
        t["zombuul_used"]=True; t["zombuul_registers_dead"]=True; return SURVIVES
    if player["character"]=="Psychopath" and kill_source["type"]==EXECUTION:
        if not player["tokens"].get("psychopath_lost_roshambo"): return SURVIVES
    if player["character"]=="Vizier" and kill_source["type"]==EXECUTION: return SURVIVES
    if player["tokens"].get("sailor_protected") and kill_source["type"]!=EXECUTION and not is_drunk_or_poisoned(player,g):
        return SURVIVES
    if player["tokens"].get("boffin_sailor_protected") and player["tokens"].get("boffin_instance") and kill_source["type"]!=EXECUTION and not is_boffin_impaired(g):
        return SURVIVES
    ik=get_character(g,"Innkeeper")
    if ik and ik["alive"] and not ability_inactive(ik,g) and kill_source["type"]!=EXECUTION:
        if player["tokens"].get("innkeeper_protected"): return SURVIVES
    if player["character"]=="Soldier" and kill_source["type"]==DEMON_KILL and not is_drunk_or_poisoned(player,g):
        return SURVIVES
    monk=get_character(g,"Monk")
    if monk and monk["alive"] and not ability_inactive(monk,g):
        if monk["tokens"].get("monk_target")==player["id"] and kill_source["type"]==DEMON_KILL:
            return SURVIVES
    tl=get_character(g,"Tea Lady")
    if tl and tl["alive"] and not ability_inactive(tl,g):
        l,r=get_alive_neighbors(tl,g)
        if l and r:
            la=check_misregistration(l,"alignment",g)
            ra=check_misregistration(r,"alignment",g)
            if la==GOOD and ra==GOOD and player["id"] in (l["id"],r["id"]):
                return SURVIVES

    da=get_character(g,"Devil's Advocate")
    if da and da["alive"] and not ability_inactive(da,g):
        if da["tokens"].get("da_target")==player["id"] and kill_source["type"]==EXECUTION:
            return SURVIVES
    if player["character"]=="Lleech":
        host=get_player(g,t.get("lleech_host"))
        if host and host["alive"]: return SURVIVES
    pac=get_character(g,"Pacifist")
    if pac and pac["alive"] and not ability_inactive(pac,g):
        if kill_source["type"]==EXECUTION and check_misregistration(player,"alignment",g)==GOOD:
            if player["tokens"].get("pacifist_saved"): return SURVIVES
    ma=get_character(g,"Mayor")
    if ma and ma["alive"] and not ability_inactive(ma,g) and player["id"]==ma["id"]:
        if kill_source["type"]==DEMON_KILL:
            g["_mayor_protect_pending"]=True
            return SURVIVES
    return DIES

def has_active_subinstance(player):
    """True if the player has a live subinstance that should survive their death."""
    tok=player.get("tokens",{})
    if tok.get("copied_character"): return True
    ci=tok.get("cannibal_instance")
    if ci and ci.get("ability_active"): return True
    bi=tok.get("boffin_instance")
    if bi and bi.get("ability_active"): return True
    return False

# --- DEATH RESOLUTION ---
def resolve_death(player,kill_source,g):
    player["alive"]=False
    player["ability_active"]=False
    g["_someone_died_today"]=True
    if player["character"]=="Boffin":
        _bd=next((p for p in g["players"] if "boffin_instance" in p.get("tokens",{})),None)
        if _bd:
            _binst=_bd["tokens"]["boffin_instance"]
            if _binst.get("character")=="Poisoner":
                _old=_binst.get("tokens",{}).get("poisoner_last_target")
                if _old:
                    _pt=get_player(g,_old)
                    if _pt: _pt["tokens"].pop("poisoned_by_poisoner",None)
            _binst["ability_active"]=False
    t=player["tokens"]
    t["ghost_vote_available"]=True
    vm=get_character(g,"Vigormortis")
    if vm and vm["alive"] and not ability_inactive(vm,g):
        if check_misregistration(player,"char_type",g)==MINION and kill_source.get("source_character")=="Vigormortis":
            player["ability_active"]=True
            g.setdefault("_pending_vigormortis_poison",[]).append(player["id"])
    if player["character"]=="Banshee" and kill_source["type"]==DEMON_KILL:
        player["ability_active"]=True
        t["banshee_killed_by_demon"]=True

    if g.get("_lil_monsta_holder")==player["id"]:
        g["_lil_monsta_holder"]=None
        from botc_jinxes import call_jinx_hook
        call_jinx_hook("lm_sw_transfer",g)
    if player["character"]=="Vigormortis":
        from botc_jinxes import jinx_pair_active
        other_demon=any(p["alive"] and p["char_type"]==DEMON and p["id"]!=player["id"] for p in g["players"])
        if not other_demon:
            mm=get_character(g,"Mastermind")
            mm_jinx=(mm and not mm["alive"] and mm.get("ability_active") and jinx_pair_active("Mastermind","Vigormortis",g))
            if mm_jinx:
                mm["tokens"]["mastermind_vm_jinx"]=True
            for p in g["players"]:
                if not p["alive"] and p["tokens"].get("vigormortis_poisoned"):
                    if mm_jinx and p["id"]==mm["id"]:
                        pass
                    else:
                        p["ability_active"]=False
    if player["char_type"]==DEMON:
        sw=get_character(g,"Scarlet Woman")
        if sw and sw["alive"] and not ability_inactive(sw,g) and count_visible_alive_non_trav(g)>=4:
            keep={"ghost_vote_available","nominations_today","nominated_today"}
            sw["tokens"]={k:v for k,v in sw["tokens"].items() if k in keep}
            sw["char_type"]=DEMON; sw["character"]=player["character"]; sw["ability_active"]=True
            transfer_boffin_to(sw["id"],g)
        elif player["character"]=="Imp" and kill_source.get("source_character")=="Imp":
            alive_minions=[p for p in g["players"] if p["char_type"]==MINION and p["alive"]]
            if alive_minions: g["_pending_imp_transfer"]=[m["id"] for m in alive_minions]

    if (check_misregistration(player,"char_type",g))==OUTSIDER:
        g["_outsiders_died_today"]=g.get("_outsiders_died_today",0)+1
    if player["char_type"]==MINION and kill_source["type"]==EXECUTION:
        mn=get_character(g,"Minstrel")
        if mn and mn["alive"] and not ability_inactive(mn,g): g["_minstrel_drunk"]=True
    if player["character"]=="Sage" and kill_source["type"]==DEMON_KILL:
        if not is_drunk_or_poisoned(player,g): player["tokens"]["sage_triggered"]=True
    if player["character"]=="Ravenkeeper" and g.get("night",0)>0:
        if not is_drunk_or_poisoned(player,g): player["tokens"]["ravenkeeper_triggered"]=True
    if player["character"]=="Farmer" and g.get("night",0)>0 and not is_drunk_or_poisoned(player,g):
        g["_pending_farmer_replacement"]=True
    if player["character"]=="Klutz" and not is_drunk_or_poisoned(player,g): player["tokens"]["klutz_triggered"]=True
    if player["character"]=="Poisoner":
        old_t=player["tokens"].get("poisoner_last_target")
        if old_t:
            pt=get_player(g,old_t)
            if pt: pt["tokens"].pop("poisoned_by_poisoner",None)
    if player["character"]=="Sweetheart" and not is_drunk_or_poisoned(player,g):
        g["_sweetheart_pending"]=True
    if player["character"]=="Barber" and not is_drunk_or_poisoned(player,g):
        g["_barber_triggered"]=True
    if player["character"]=="Hatter" and not is_drunk_or_poisoned(player,g):
        g["_hatter_triggered"]=True
    if player["character"]=="Poppy Grower" and not is_drunk_or_poisoned(player,g):
        g["_poppy_grower_dead"]=True
    px=get_character(g,"Pixie")
    if px and px["alive"] and px["tokens"].get("pixie_character")==player["character"]:
        g.setdefault("_pixie_gain_pending",[]).append(px["id"])
    ll=get_character(g,"Lleech")
    if ll and ll["alive"] and ll["tokens"].get("lleech_host")==player["id"]:
        g.setdefault("_pending_deaths",[]).append({"player":ll,"source":{"type":ABILITY_KILL,"source_character":"Lleech"}})
    gm=get_character(g,"Grandmother")
    if gm and gm["alive"] and not ability_inactive(gm,g) and gm["tokens"].get("grandchild")==player["id"]:
        if kill_source["type"]==DEMON_KILL:
            g.setdefault("_pending_deaths",[]).append({"player":gm,"source":{"type":ABILITY_KILL,"source_character":"Grandmother"}})
    _pc=player["tokens"].get("copied_character")
    if _pc and not is_drunk_or_poisoned(player,g):
        _apply_death_triggers(player,
            {"character":_pc,"tokens":player["tokens"]},kill_source,g)
    _apply_boffin_death_triggers(player,kill_source,g)
    _apply_cannibal_instance_death_triggers(player,kill_source,g)
    return check_win_conditions(g)

# --- WIN CONDITIONS ---
def _heretic_flip(g):
    """Returns True if the win result should be flipped (odd number of active Heretic abilities).
    Counts actual Heretic players, Philosopher-as-Heretic, and Cannibal-as-Heretic."""
    count = 0
    for p in g["players"]:
        if p["character"] == "Heretic" and not is_drunk_or_poisoned(p, g):
            count += 1
        elif (p["character"] == "Philosopher" and p["alive"]
              and not is_drunk_or_poisoned(p, g)
              and p["tokens"].get("copied_character") == "Heretic"):
            count += 1
    can = get_character(g, "Cannibal")
    if (can and can["alive"] and not is_drunk_or_poisoned(can, g)
            and g.get("_cannibal_told_character") == "Heretic"):
        count += 1
    return count % 2 == 1

def check_win_conditions(g):
    good_t,evil_t=[],[]
    et=get_character(g,"Evil Twin")
    if et:
        opp=get_player(g,et["tokens"].get("opposing_player"))
        if opp:
            gp=et if et["alignment"]==GOOD else opp
            if not gp["alive"] and g.get("_last_executed")==gp["id"]:
                evil_t.append("Evil Twin")
    s=get_character(g,"Saint")
    if s and not s["alive"] and g.get("_last_executed")==s["id"] and s["tokens"].get("was_sober_at_execution",True): evil_t.append("Saint")
    gob=get_character(g,"Goblin")
    if gob and not gob["alive"] and g.get("_last_executed")==gob["id"] and gob["tokens"].get("goblin_claimed"): evil_t.append("Goblin")
    kl=get_character(g,"Klutz")
    if kl and kl["tokens"].get("klutz_chose_evil"): evil_t.append("Klutz")
    ma=get_character(g,"Mayor")
    if ma and ma["alive"] and not is_drunk_or_poisoned(ma,g):
        if count_visible_alive(g)==3 and not g.get("_execution_occurred_today"): good_t.append("Mayor")

    vx=get_character(g,"Vortox")
    if vx and vx["alive"] and not is_drunk_or_poisoned(vx,g) and g.get("_day_ended") and not g.get("_execution_occurred_today"):
        evil_t.append("Vortox")
    lv=get_character(g,"Leviathan")
    if lv and lv["alive"] and not is_drunk_or_poisoned(lv,g):
        if g.get("_good_executions",0)>1: evil_t.append("Leviathan")
        if g.get("night",0)>=5 and g.get("_day_ended"): evil_t.append("Leviathan day5")
    if good_t or evil_t:
        res=GOOD if good_t else EVIL
        if _heretic_flip(g): res=EVIL if res==GOOD else GOOD
        return res
    if et and et["alive"]:
        opp=get_player(g,et["tokens"].get("opposing_player"))
        if opp and opp["alive"]:
            return EVIL if count_alive_non_trav(g)<=2 else None
    if "_lil_monsta_holder" in g:
        holder=get_player(g,g.get("_lil_monsta_holder")) if g.get("_lil_monsta_holder") else None
        if not holder or not holder["alive"]:
            return EVIL if _heretic_flip(g) else GOOD
        if count_alive_non_trav(g)<=2:
            return GOOD if _heretic_flip(g) else EVIL
        return None
    if demon_is_dead(g) and not g.get("_pending_imp_transfer"):
        mm=get_character(g,"Mastermind")
        if g.get("_demon_executed_died") and mm and mm["alive"] and not ability_inactive(mm,g) and not mm["tokens"].get("mm_used"):
            mm["tokens"]["mm_used"]=True
            g["_mastermind_grace"]=True
            return None
        if g.get("_mastermind_grace"):
            return None
        _h=get_character(g,"Heretic")
        return EVIL if _h and not is_drunk_or_poisoned(_h,g) else GOOD
    if count_alive_non_trav(g)<=2:
        _h=get_character(g,"Heretic")
        return GOOD if _h and not is_drunk_or_poisoned(_h,g) else EVIL
    cl=get_character(g,"Cult Leader")
    if cl and cl["alive"] and not is_drunk_or_poisoned(cl,g):
        alive_pl=[p for p in g["players"] if p["alive"]]
        if alive_pl and all(p["alignment"]==cl["alignment"] for p in alive_pl):
            res=cl["alignment"]
            if _heretic_flip(g): res=EVIL if res==GOOD else GOOD
            return res
    return None

# --- FANG GU JUMP ---
def resolve_fang_gu_jump(fg,target,g):
    if fg["tokens"].get("fang_gu_jumped"): return False
    src={"type":DEMON_KILL,"source_character":"Fang Gu"}
    if can_player_die(target,src,g)!=DIES: return False
    if can_player_die(fg,src,g)!=DIES: return False
    target["character"]="Fang Gu"; target["char_type"]=DEMON
    target["alignment"]=EVIL; target["ability_active"]=True
    fg["tokens"]["fang_gu_jumped"]=True
    fg["char_type"]=OUTSIDER
    resolve_death(fg,src,g)
    return True

def is_demon_suppressed(demon,g):
    """True if demon ability is blocked by drunk/poison or Exorcist."""
    if not demon["ability_active"] or ability_inactive(demon,g): return True
    ex=get_character(g,"Exorcist")
    if ex and ex["alive"] and not ability_inactive(ex,g):
        if ex["tokens"].get("exorcist_target")==demon["id"]: return True
    if g.get("_cannibal_killed_princess"): return True
    return False

# --- DEMON NIGHT KILL ---
def resolve_demon_kill(demon,target,g):
    src={"type":DEMON_KILL,"source_character":demon["character"]}
    if g.get("night",0)<=1: return SURVIVES
    if registers_as_dead(demon): return SURVIVES
    if is_demon_suppressed(demon,g): return SURVIVES
    g.setdefault("_woke_tonight",set()).add(demon["id"])
    if g.get("_lycanthrope_killed_tonight"): return SURVIVES
    if demon["character"]=="Zombuul" and g.get("_someone_died_last_day"): return SURVIVES
    check_goon_targeting(demon,target["id"],g)
    if is_drunk_or_poisoned(demon,g): return SURVIVES  # Goon may have just drunk the demon
    if demon["character"]=="Fang Gu" and not demon["tokens"].get("fang_gu_jumped"):
        if (check_misregistration(target,"char_type",g))==OUTSIDER:
            if resolve_fang_gu_jump(demon,target,g): return DIES
    if can_player_die(target,src,g)==SURVIVES: return SURVIVES
    resolve_death(target,src,g)
    return DIES

# --- EXECUTION ---
def vote_threshold(g): return (count_visible_alive(g)+1)//2
def can_cast_vote(v,g):
    if not v["alive"]:return v["tokens"].get("ghost_vote_available",False)
    return True
    mid=b["tokens"].get("butler_master");return bool(mid and mid in vids)
def resolve_nomination(nom_id,nee_id,vids,g):
    nom=get_player(g,nom_id)
    if nom:
        nom["tokens"]["nominations_today"]=nom["tokens"].get("nominations_today",0)+1
        if nom["tokens"].get("witch_cursed") and nom["alive"]:
            src={"type":ABILITY_KILL,"source_character":"Witch"}
            if can_player_die(nom,src,g)==DIES: resolve_death(nom,src,g)
    nee=get_player(g,nee_id)
    if not nee:return
    nee["tokens"]["nominated_today"]=True
    if check_misregistration(nom,"char_type",g)==MINION: g["_minion_nominated_today"]=True
    resolve_harpy_nomination(nom_id,nee_id,g)
    if nee["character"]=="Goblin" and not is_drunk_or_poisoned(nee,g):
        g["_goblin_nominated"]=nee["id"]
    if (nom and nom["character"]=="Princess" and not is_drunk_or_poisoned(nom,g)
            and g.get("day",g.get("day_num",1))==1):
        g["_princess_nominated_day1"]=True
    if nee["character"]=="Virgin" and not nee["tokens"].get("virgin_used"):
        nee["tokens"]["virgin_used"]=True
        if not is_drunk_or_poisoned(nee,g):
            nom_aln=check_misregistration(nom,"char_type",g)
            if nom_aln==TOWNSFOLK and nom["alive"]:
                resolve_execution(nom["id"],g)
                return
    eff=[]
    for vid in vids:
        v=get_player(g,vid)
        if not v:continue
        if v["character"]=="Butler" and not is_drunk_or_poisoned(v,g):
            if not butler_vote_ok(v,vids,g):continue
        eff.append(vid)
    for vid in eff:
        v=get_player(g,vid)
        if v and not v["alive"] and not v["tokens"].get("banshee_killed_by_demon"):
            v["tokens"]["ghost_vote_available"]=False
        if v and check_misregistration(v,"char_type",g)==DEMON: g["_demon_voted_today"]=True
    bur=get_character(g,"Bureaucrat")
    bur_t=bur["tokens"].get("bureaucrat_target") if bur and bur["alive"] and not ability_inactive(bur,g) else None
    thf=get_character(g,"Thief")
    thf_t=thf["tokens"].get("thief_target") if thf and thf["alive"] and not ability_inactive(thf,g) else None
    ct=0
    for v in eff:
        p=get_player(g,v)
        if not p: continue
        base=2 if p["tokens"].get("banshee_killed_by_demon") else 1
        if v==bur_t: base*=3
        if v==thf_t: base=-base
        ct+=base
    # Legion: execution fails if all effective voters are evil
    leg=get_character(g,"Legion")
    if leg and leg["alive"] and not ability_inactive(leg,g) and eff:
        if all(check_misregistration(get_player(g,v),"alignment",g)==EVIL for v in eff if get_player(g,v)):
            return
    th=vote_threshold(g);cc=g.get("_on_the_block_votes",0)
    if ct<th:return
    if ct>cc:g["_on_the_block"]=nee_id;g["_on_the_block_votes"]=ct;g["_on_the_block_nominator"]=nom_id
    elif ct==cc:g["_on_the_block"]=None;g["_on_the_block_votes"]=0

def tally_vote(nee_id,nom_id,vids,g):
    """Count votes separately from nomination immediate effects."""
    eff=[]
    for vid in vids:
        v=get_player(g,vid)
        if not v: continue
        if v["character"]=="Butler" and not is_drunk_or_poisoned(v,g):
            if not butler_vote_ok(v,vids,g): continue
        eff.append(vid)
    for vid in eff:
        v=get_player(g,vid)
        if v and not v["alive"] and not v["tokens"].get("banshee_killed_by_demon"):
            v["tokens"]["ghost_vote_available"]=False
        if v and check_misregistration(v,"char_type",g)==DEMON:
            g["_demon_voted_today"]=True
    bur=get_character(g,"Bureaucrat")
    bur_t=bur["tokens"].get("bureaucrat_target") if bur and bur["alive"] and not ability_inactive(bur,g) else None
    thf=get_character(g,"Thief")
    thf_t=thf["tokens"].get("thief_target") if thf and thf["alive"] and not ability_inactive(thf,g) else None
    ct=0
    for v in eff:
        p=get_player(g,v)
        if not p: continue
        base=2 if p["tokens"].get("banshee_killed_by_demon") else 1
        if v==bur_t: base*=3
        if v==thf_t: base=-base
        ct+=base
    leg=get_character(g,"Legion")
    if leg and leg["alive"] and not ability_inactive(leg,g) and eff:
        if all(check_misregistration(get_player(g,v),"alignment",g)==EVIL
               for v in eff if get_player(g,v)): return
    th=vote_threshold(g); cc=g.get("_on_the_block_votes",0)
    if ct<th: return
    if ct>cc:
        g["_on_the_block"]=nee_id; g["_on_the_block_votes"]=ct
        g["_on_the_block_nominator"]=nom_id
    elif ct==cc: g["_on_the_block"]=None; g["_on_the_block_votes"]=0

def resolve_execution(tid,g):
    t=get_player(g,tid)
    if not t:return SURVIVES
    src={"type":EXECUTION,"source_character":None}
    g["_execution_occurred_today"]=True;g["_last_executed"]=tid
    aln=check_misregistration(t,"alignment",g)
    if aln==GOOD:g["_good_executions"]=g.get("_good_executions",0)+1
    # Jinxes: LM holder Psychopath/Vizier die on execution
    from botc_jinxes import jinx_pair_active
    if g.get("_lil_monsta_holder") == t["id"]:
        if t["character"] == "Psychopath" and jinx_pair_active("Lil' Monsta", "Psychopath", g):
            src = dict(src, bypass_protection=True)
        elif t["character"] == "Vizier" and jinx_pair_active("Lil' Monsta", "Vizier", g):
            src = dict(src, bypass_protection=True)
    if can_player_die(t,src,g)==SURVIVES:
        if t["character"]=="Zombuul" and t["tokens"].get("zombuul_registers_dead"):
            g["_someone_died_today"]=True
        return SURVIVES
    t["tokens"]["was_sober_at_execution"]=not is_drunk_or_poisoned(t,g)
    if t["char_type"]==DEMON:g["_demon_executed_died"]=True
    resolve_death(t,src,g)
    from botc_jinxes import jinx_pair_active as _jpa
    if (g.get("_princess_nominated_day1") and _jpa("Al-Hadikhia","Princess",g)):
        g["_alh_princess_no_kill"]=True
    if (t["character"]=="Princess" and _jpa("Cannibal","Princess",g)):
        nom_id=g.get("_on_the_block_nominator")
        can=get_character(g,"Cannibal")
        if can and can["id"]==nom_id and not is_drunk_or_poisoned(can,g):
            g["_cannibal_killed_princess"]=True
    g["_cannibal_executee_id"]=t["id"]
    g["_last_executed_dying_id"]=t["id"]
    g["_executed_character"]=t["character"]
    g["_someone_died_today"]=True
    told_char=check_misregistration(t,"character",g) if aln==GOOD else None
    g["_cannibal_told_character"]=told_char
    can=get_character(g,"Cannibal")
    if can and can["alive"]:
        can["tokens"]["cannibal_instance"]={"character":told_char,"tokens":{},"ability_active":bool(told_char),"bound_player_id":t["id"],"source":"Cannibal"}
    return DIES
def end_of_day(g):
    tid=g.get("_on_the_block")
    if tid:resolve_execution(tid,g)
    g["_day_ended"]=True
    if g.get("_mastermind_grace"):
        g.pop("_mastermind_grace",None)
        if not g.get("_execution_occurred_today"):
            result=GOOD
        else:
            ex=get_player(g,g.get("_last_executed"))
            result=EVIL if (ex and check_misregistration(ex,"alignment",g)==GOOD) else GOOD
    else:
        result=check_win_conditions(g)
    g["_outsiders_died_last_day"]=g.get("_outsiders_died_today",0)
    g["_undertaker_last_executed"]=g.get("_executed_character")
    g["_someone_died_last_day"]=g.get("_someone_died_today",False)
    g["_minion_nominated_last_day"]=g.get("_minion_nominated_today",False)
    g["_demon_voted_last_day"]=g.get("_demon_voted_today",False)
    g.update({"_on_the_block":None,"_on_the_block_votes":0,"_last_executed":None,"_demon_executed_died":False,"_day_ended":False,"_outsiders_died_today":0,"_executed_character":None,"_minstrel_drunk":False,"_someone_died_today":False,"_minion_nominated_today":False,"_demon_voted_today":False})
    g["_yaggababble_day_count"]=0
    g.pop("_riot_must_nominate",None)
    for p in g["players"]:
        p["tokens"]["nominations_today"]=0
        p["tokens"].pop("nominated_today",None)
        p["tokens"].pop("goon_drunk",None)
        p["tokens"].pop("mez_word",None)
        p["tokens"].pop("riot_must_nominate",None)
    return result
def can_nominate(player,g):
    if not player["alive"]:
        if player["tokens"].get("banshee_killed_by_demon"):
            return player["tokens"].get("nominations_today",0)<2
        if player["tokens"].get("riot_must_nominate"):
            return player["tokens"].get("nominations_today",0)<1
        return False
    return player["tokens"].get("nominations_today",0)<1
def can_be_nominated(player,g):
    if player["tokens"].get("nominated_today"):return False
    return True

# --- RIOT ---
def is_riot_active(g):
    return any(p["alive"] and p["character"]=="Riot" and p["char_type"]==DEMON
               for p in g.get("players",[]))

def setup_riot(g):
    """Transform all alive non-drunk Minions into Riot at start of day 3."""
    changed=[]
    for p in g.get("players",[]):
        if p["alive"] and p["char_type"]==MINION and not is_drunk_or_poisoned(p,g):
            changed.append(p["character"])
            p["character"]="Riot"; p["char_type"]=DEMON; p["ability_active"]=True
    return changed

def resolve_riot_kill(nominated_id,g):
    """Riot: nominated player dies (not an execution). Returns DIES/SURVIVES."""
    t=get_player(g,nominated_id)
    if not t or not t["alive"]: return SURVIVES
    src={"type":RIOT_KILL,"source_character":"Riot"}
    if can_player_die(t,src,g)!=DIES: return SURVIVES
    resolve_death(t,src,g)
    g["_someone_died_today"]=True
    t["tokens"]["riot_must_nominate"]=True
    g["_riot_must_nominate"]=nominated_id
    return DIES

# --- WIZARD ---
def resolve_wizard_wish(wizard,wish_text,g):
    """Once per game: Wizard makes a wish. Returns wish text for ST."""
    if wizard["tokens"].get("wizard_wish_used"): return None
    if not wizard["ability_active"] or ability_inactive(wizard,g): return None
    wizard["tokens"]["wizard_wish_used"]=True
    return wish_text

# --- YAGGABABBLE ---
def resolve_yaggababble_kills(target_ids,g):
    """ST-chosen kills from Yaggababble phrase utterances."""
    killed=[]
    src={"type":ABILITY_KILL,"source_character":"Yaggababble"}
    for tid in (target_ids or []):
        t=get_player(g,tid)
        if t and t["alive"] and can_player_die(t,src,g)==DIES:
            resolve_death(t,src,g); g["_someone_died_today"]=True; killed.append(tid)
    return killed

# --- EXILE ---
def resolve_exile(traveller_id,vids,g):
    t=get_player(g,traveller_id)
    if not t:return SURVIVES
    eff=[]
    for vid in vids:
        v=get_player(g,vid)
        if not v:continue
        if v["character"]=="Butler" and not is_drunk_or_poisoned(v,g):
            if not butler_vote_ok(v,vids,g):continue
        eff.append(vid)
    ct=sum(2 if get_player(g,v) and get_player(g,v)["tokens"].get("banshee_killed_by_demon") else 1 for v in eff)
    if ct<vote_threshold(g):return SURVIVES
    src={"type":"exile","source_character":None}
    if can_player_die(t,src,g)==SURVIVES:return SURVIVES
    resolve_death(t,src,g)
    return DIES

# --- PENDING STATE PROCESSING ---
def flush_pending(g):
    actions = []
    win = None
    while g.get("_pending_deaths"):
        batch = g.pop("_pending_deaths")
        for item in batch:
            p,src=item["player"],item["source"]
            if p["alive"] and can_player_die(p,src,g)==DIES:
                result=resolve_death(p,src,g)
                if result is not None and win is None: win=result
    for mid in g.pop("_pending_vigormortis_poison",[]):
        g.setdefault("_vigormortis_poison_needed",[]).append(mid)
        actions.append(("VIGORMORTIS_POISON_NEEDED",mid))
    if g.pop("_pending_farmer_replacement",False):
        cands=[p["id"] for p in g["players"] if p["alive"] and p["alignment"]==GOOD]
        actions.append(("FARMER_REPLACEMENT_NEEDED",cands))
    if g.get("_pending_imp_transfer"):
        actions.append(("IMP_TRANSFER_NEEDED",g.pop("_pending_imp_transfer")))
    if g.pop("_sweetheart_pending",False):
        actions.append(("SWEETHEART_DRUNK_NEEDED",None))
    if g.pop("_widow_knows_pending",False):
        good=[p["id"] for p in g["players"] if p["alive"] and p["alignment"]==GOOD]
        actions.append(("WIDOW_GOOD_PLAYER_KNOWS_NEEDED",good))
    if g.pop("_mayor_protect_pending",False):
        ma2=get_character(g,"Mayor"); cands=[p["id"] for p in g["players"] if p["alive"] and (not ma2 or p["id"]!=ma2["id"])]
        actions.append(("MAYOR_PROTECT_NEEDED",cands))
    if g.pop("_barber_triggered",False):
        demons=[p["id"] for p in g["players"] if p["alive"] and p["char_type"]==DEMON]
        actions.append(("BARBER_SWAP_NEEDED",demons))
    if g.pop("_hatter_triggered",False):
        minions=[p["id"] for p in g["players"] if p["alive"] and p["char_type"]==MINION]
        demons2=[p["id"] for p in g["players"] if p["alive"] and p["char_type"]==DEMON]
        actions.append(("HATTER_SWAP_NEEDED",{"minions":minions,"demons":demons2,"optional_rule":g.get("hatter_optional_rule",False)}))
    for px_id in g.pop("_pixie_gain_pending",[]):
        actions.append(("PIXIE_GAIN_CHECK",px_id))
    if g.pop("_ojo_no_target_pending",False):
        alive=[p["id"] for p in g["players"] if p["alive"]]
        actions.append(("OJO_NO_TARGET_KILL_NEEDED",alive))
    if g.pop("_poppy_grower_dead",False):
        if not is_poppy_grower_alive(g):
            evil=[p["id"] for p in g["players"] if p["alignment"]==EVIL]
            actions.append(("EVIL_LEARNS_EACH_OTHER",evil))
    if g.get("_fearmonger_execute"):
        actions.append(("FEARMONGER_EXECUTE",g.pop("_fearmonger_execute")))
    transfer_pending=any(a[0]=="IMP_TRANSFER_NEEDED" for a in actions)
    if not transfer_pending:
        final_win=check_win_conditions(g)
        if final_win is not None: win=final_win
    update_lycan_faux_paw(g)
    return win,actions

def apply_imp_transfer(minion_id,g):
    m=get_player(g,minion_id)
    if m and m["char_type"]==MINION and m["alive"]:
        m["character"]="Imp";m["char_type"]=DEMON;m["ability_active"]=True
        _dead_bd=next((p for p in g["players"] if not p["alive"] and "boffin_instance" in p.get("tokens",{})),None)
        if _dead_bd and _dead_bd["tokens"]["boffin_instance"].get("character") not in BOFFIN_ONGOING_AFTER_DEATH:
            transfer_boffin_to(m["id"],g)

def apply_farmer_replacement(player_id,g):
    p=get_player(g,player_id)
    if p and p["alive"] and p["alignment"]==GOOD:
        p["character"]="Farmer";p["char_type"]=TOWNSFOLK;p["ability_active"]=True

def resolve_klutz_choice(klutz_id,chosen_id,g):
    kl=get_player(g,klutz_id)
    if not kl or not kl["tokens"].get("klutz_triggered"): return
    chosen=get_player(g,chosen_id)
    if chosen:
        aln=check_misregistration(chosen,"alignment",g)
        if aln==EVIL: kl["tokens"]["klutz_chose_evil"]=True

def apply_sweetheart_drunk(player_id,g):
    p=get_player(g,player_id)
    if p: p["tokens"]["sweetheart_drunk"]=True

def apply_mayor_redirect(victim_id,g):
    """ST chose this player to die instead of Mayor."""
    v=get_player(g,victim_id)
    if v and v["alive"]:
        src={"type":DEMON_KILL,"source_character":"Mayor"}
        if can_player_die(v,src,g)==DIES: resolve_death(v,src,g)

# --- NIGHT ACTION HELPERS ---
def apply_widow_poison(player_id,g):
    p=get_player(g,player_id)
    if p: p["tokens"]["widow_poisoned"]=True

def resolve_pukka_night(pukka,new_target_id,g):
    prev_killed=None
    for p in g["players"]:
        if p["tokens"].pop("pukka_poisoned",None):
            if p["alive"] and not registers_as_dead(p):
                src={"type":DEMON_KILL,"source_character":"Pukka"}
                if can_player_die(p,src,g)==DIES:
                    resolve_death(p,src,g); prev_killed=p
    if not is_demon_suppressed(pukka,g) and new_target_id:
        g.setdefault("_woke_tonight",set()).add(pukka["id"])
        t=get_player(g,new_target_id)
        if t:
            _was=ability_inactive(pukka,g)
            check_goon_targeting(pukka,new_target_id,g)
            if not _was and not ability_inactive(pukka,g):
                pk=get_character(g,"Pukka")
                if pk: try_impose_effect(pk,t,"pukka_poisoned",True,g)
    return prev_killed
def resolve_shabaloth_night(shabaloth,target_ids,g):
    last=shabaloth["tokens"].pop("shabaloth_last_targets",[])
    rv=[p for p in [get_player(g,t) for t in last] if p and not p["alive"]]
    if g.get("night",0)<=1: return [],rv
    killed=[]
    if not is_demon_suppressed(shabaloth,g):
        g.setdefault("_woke_tonight",set()).add(shabaloth["id"])
        tgts=[t for t in [get_player(g,i) for i in (target_ids or [])] if t]
        shabaloth["tokens"]["shabaloth_last_targets"]=[t["id"] for t in tgts]
        for t in tgts:
            _was=ability_inactive(shabaloth,g)
            check_goon_targeting(shabaloth,t["id"],g)
            if not _was and ability_inactive(shabaloth,g): break
            if _was: break
            src={"type":DEMON_KILL,"source_character":"Shabaloth"}
            if can_player_die(t,src,g)==DIES:
                resolve_death(t,src,g); killed.append(t)
    else:
        shabaloth["tokens"]["shabaloth_last_targets"]=[]
    return killed,rv

def apply_shabaloth_revival(player,g):
    if not player["alive"]:
        player["alive"]=True; player["ability_active"]=True
        player["tokens"].pop("ghost_vote_available",None)

def resolve_po_night(po,target_ids,g):
    if g.get("night",0)<=1: return []
    if is_demon_suppressed(po,g): return []
    if target_ids is None:
        g["_po_charged"]=True; return []
    expected=3 if g.pop("_po_charged",False) else 1
    g.setdefault("_woke_tonight",set()).add(po["id"])
    if ability_inactive(po,g): return []
    killed=[]
    for tid in (target_ids or [])[:expected]:
        t=get_player(g,tid)
        if t and t["alive"]:
            _was=ability_inactive(po,g)
            check_goon_targeting(po,t["id"],g)
            if not _was and ability_inactive(po,g): break
            if _was: break
            src={"type":DEMON_KILL,"source_character":"Po"}
            resolve_death(t,src,g); killed.append(t)
    return killed


# --- NIGHT TRANSITION ---
def start_of_night(g):
    g["_prev_night_dead"]=set(p["id"] for p in g["players"] if not p["alive"])
    g["night"]=g.get("night",0)+1

    g["_execution_occurred_today"]=False
    g["_woke_tonight"]=set()
    g.pop("_xaan_tf_poisoned",None)
    g.pop("_lycanthrope_killed_tonight",None)
    g.pop("_cannibal_killed_princess",None)
    g.pop("_princess_nominated_day1",None)
    g.pop("_alh_princess_no_kill",None)
    bc=get_character(g,"Bone Collector")
    if bc:
        old_t=bc["tokens"].get("bc_target")
        if old_t:
            dead=get_player(g,old_t)
            if dead and not dead["alive"]: dead["ability_active"]=False
    for p in g["players"]:
        p["tokens"].pop("zombuul_registers_dead", None)
        if p["tokens"].get("courtier_drunk_remaining", 0) > 0:
            p["tokens"]["courtier_drunk_remaining"] -= 1
        for _tok in ONE_NIGHT_TOKENS:
            p["tokens"].pop(_tok, None)
        for _inst in p["tokens"].get("hermit_instances", {}).values():
            _inst["tokens"].pop("goon_triggered_night", None)
        ci=p["tokens"].get("cannibal_instance")
        if ci:
            for _tok in ONE_NIGHT_TOKENS: ci["tokens"].pop(_tok,None)
        bi=p["tokens"].get("boffin_instance")
        if bi:
            for _tok in ONE_NIGHT_TOKENS: bi["tokens"].pop(_tok,None)
    # Freshly-created Cannibal retroactive binding
    can=get_character(g,"Cannibal")
    if can and can["alive"] and not can["tokens"].get("cannibal_instance"):
        lid=g.get("_last_executed_dying_id")
        if lid:
            ex=get_player(g,lid)
            if ex:
                aln=check_misregistration(ex,"alignment",g)
                told=check_misregistration(ex,"character",g) if aln!=EVIL else None
                can["tokens"]["cannibal_instance"]={
                    "character":told,"tokens":{},"ability_active":bool(told),
                    "bound_player_id":lid,"source":"Cannibal"}
    return g["night"]

# --- NIGHT ACTION RESOLVERS ---
def resolve_monk_night(monk,target_id,g):
    monk["tokens"].pop("monk_target",None)
    if g.get("night",0)<=1: return
    if not begin_ability(monk, target_id, g): return
    monk["tokens"]["monk_target"] = target_id

def resolve_sailor_night(sailor,target_id,g,self_drunk=True):
    sailor["tokens"].pop("sailor_target",None)
    sailor["tokens"].pop("sailor_protected",None)
    sailor["tokens"].pop("sailor_self_drunk",None)
    if sailor["ability_active"] and target_id:
        _was=ability_inactive(sailor,g)
        check_goon_targeting(sailor,target_id,g)
        if not _was and ability_inactive(sailor,g): return
        if _was: return
        g.setdefault("_woke_tonight",set()).add(sailor["id"])
        t=get_player(g,target_id)
        is_tf=t and check_misregistration(t,"char_type",g)==TOWNSFOLK
        if is_tf or not self_drunk:
            sailor["tokens"]["sailor_target"]=target_id
            sailor["tokens"]["sailor_protected"]=True
        else:
            sailor["tokens"]["sailor_self_drunk"]=True

def resolve_poisoner_night(poisoner,target_id,g):
    old=poisoner["tokens"].pop("poisoner_last_target",None)
    if old:
        p=get_player(g,old)
        if p: p["tokens"].pop("poisoned_by_poisoner",None)
    if not begin_ability(poisoner, target_id, g): return
    t=get_player(g,target_id)
    if t:
        try_impose_effect(poisoner,t,"poisoned_by_poisoner",True,g)
        poisoner["tokens"]["poisoner_last_target"]=target_id

def resolve_da_night(da,target_id,g):
    da["tokens"].pop("da_target",None)
    if not begin_ability(da, target_id, g): return
    da["tokens"]["da_target"] = target_id

def resolve_exorcist_night(ex,target_id,g):
    prev=ex["tokens"].pop("exorcist_target",None)
    if prev: ex["tokens"]["exorcist_last_target"]=prev
    if g.get("night",0)<=1: return
    if not begin_ability(ex, target_id, g): return
    if target_id==ex["tokens"].get("exorcist_last_target"): return
    ex["tokens"]["exorcist_target"]=target_id

def apply_vigormortis_poison(minion_id,direction,g):
    """direction: -1 for left, 1 for right in seat order."""
    players=g["players"]
    mn=get_player(g,minion_id)
    if not mn or mn not in players: return
    idx=players.index(mn); n=len(players)
    for dist in range(1,n):
        p=players[(idx+direction*dist)%n]
        if p["alive"] and (check_misregistration(p,"char_type",g))==TOWNSFOLK:
            vm2=get_character(g,"Vigormortis")
            if vm2: try_impose_effect(vm2,p,"vigormortis_poisoned",True,g); return

def resolve_philosopher_night(phil,character_name,g):
    if phil["tokens"].get("phil_used"): return
    if not phil["ability_active"] or not character_name: return
    phil["tokens"]["phil_used"]=True
    g.setdefault("_woke_tonight",set()).add(phil["id"])
    if ability_inactive(phil,g): return
    phil["tokens"]["copied_character"]=character_name

def resolve_philosopher_borrowed_night(phil, choices, g):
    """Night 2+ Philosopher acts as their copied character."""
    cc = phil["tokens"].get("copied_character")
    if not cc or not phil.get("ability_active"): return None
    inst = {"source":"Philosopher","character":cc,"tokens":phil["tokens"],"ability_active":True}
    if ability_inactive(phil, g): return None
    return dispatch_borrowed_night(phil, inst, choices, g)

def resolve_snake_charmer_night(sc,target_id,g):
    if not sc["ability_active"]: return False
    g.setdefault("_woke_tonight",set()).add(sc["id"])
    if ability_inactive(sc,g): return False
    t=get_player(g,target_id)
    if not t or not t["alive"]: return False
    actual_type=check_misregistration(t,"char_type",g)
    if actual_type!=DEMON: return False
    demon_char=t["character"]; demon_type=t["char_type"]
    keep={"ghost_vote_available","nominations_today","nominated_today"}
    t["tokens"]={k:v for k,v in t["tokens"].items() if k in keep}
    new_char=sc["character"]; t["character"]=new_char; t["char_type"]=TOWNSFOLK
    t["alignment"]=GOOD; t["tokens"]["snake_charmer_poisoned"]=True
    t["tokens"]["snake_charmer_poisoned_char"]=new_char
    sc["character"]=demon_char; sc["char_type"]=demon_type
    sc["alignment"]=EVIL; sc["ability_active"]=True
    t["ability_active"]=True
    update_lycan_faux_paw(g)
    return True

def resolve_slayer_claim(slayer,target_id,g):
    if not begin_ability(slayer, target_id, g, used_token="slayer_used"): return False
    t=get_player(g,target_id)
    if not t: return False
    from botc_jinxes import jinx_pair_active
    if jinx_pair_active("Lleech","Slayer",g):
        ll=get_character(g,"Lleech")
        if ll and ll["tokens"].get("lleech_host")==t["id"]:
            src={"type":ABILITY_KILL,"source_character":"Slayer"}
            if can_player_die(t,src,g)==DIES:
                resolve_death(t,src,g); return True
            return False
    if check_misregistration(t,"char_type",g)==DEMON:
        src={"type":ABILITY_KILL,"source_character":"Slayer"}
        if can_player_die(t,src,g)==DIES:
            resolve_death(t,src,g); return True
    return False

def resolve_widow_night(widow,target_id,g):
    if not begin_ability(widow, target_id, g, used_token="widow_used"): return
    apply_widow_poison(target_id,g)
    g["_widow_knows_pending"]=True

def resolve_grandmother_night(gm,grandchild_id,g):
    if gm["tokens"].get("grandchild"): return
    if not gm["ability_active"]: return
    gm["tokens"]["grandchild"]=grandchild_id
    g.setdefault("_woke_tonight",set()).add(gm["id"])
    if ability_inactive(gm,g): return
    t=get_player(g,grandchild_id)
    if not t: return None
    return resolve_information(gm,{"type":"grandmother","player_id":grandchild_id,"character":t["character"]},g)

def resolve_ogre_night(ogre,target_id,g):
    if ogre["tokens"].get("ogre_chosen"): return
    if not ogre["ability_active"]: return
    g.setdefault("_woke_tonight",set()).add(ogre["id"])
    t=get_player(g,target_id)
    if t and t["id"]!=ogre["id"]: ogre["tokens"]["ogre_chosen"]=target_id

def resolve_ravenkeeper_info(rk,target_id,g):
    if not rk["tokens"].get("ravenkeeper_triggered"): return None
    t=get_player(g,target_id)
    if not t: return None
    g.setdefault("_woke_tonight",set()).add(rk["id"])
    raw={"type":"ravenkeeper","player_id":target_id,"character":t["character"]}
    return resolve_information(rk,raw,g)

def resolve_sage_info(sage,player1_id,player2_id,g):
    if not sage["tokens"].get("sage_triggered"): return None
    g.setdefault("_woke_tonight",set()).add(sage["id"])
    raw={"type":"sage","players":[{"id":player1_id},{"id":player2_id}]}
    return resolve_information(sage,raw,g)

def resolve_godfather_night(gf,target_id,g):
    if not g.get("_outsiders_died_last_day",0): return None
    t=get_player(g,target_id)
    if not t or not t["alive"]: return None
    if not begin_ability(gf, target_id, g): return None
    src={"type":ABILITY_KILL,"source_character":"Godfather","bypass_protection":True}
    if can_player_die(t,src,g)==DIES:
        resolve_death(t,src,g); return t
    return None

def resolve_witch_night(witch,target_id,g):
    old=witch["tokens"].pop("witch_cursed",None)
    if old:
        p=get_player(g,old)
        if p: p["tokens"].pop("witch_cursed",None)
    if count_visible_alive(g)<=3: return
    if not begin_ability(witch, target_id, g): return
    t=get_player(g,target_id)
    if t and t["alive"]:
        if try_impose_effect(witch,t,"witch_cursed",True,g): witch["tokens"]["witch_cursed"]=target_id

def resolve_preacher_night(preacher,target_id,g):
    if not begin_ability(preacher, target_id, g): return
    t=get_player(g,target_id)
    if not t: return
    if (check_misregistration(t,"char_type",g))==MINION:
        t["tokens"]["preacher_silenced"]=True
        targets=preacher["tokens"].setdefault("preacher_targets",[])
        if target_id not in targets: targets.append(target_id)

def resolve_innkeeper_night(ik,target1_id,target2_id,drunk_id,g):
    for old in ik["tokens"].pop("ik_targets",[]):
        p=get_player(g,old)
        if p: p["tokens"].pop("innkeeper_protected",None); p["tokens"].pop("innkeeper_drunk",None)
    ik["tokens"]["ik_targets"]=[t for t in [target1_id,target2_id] if t]
    if g.get("night",0)<=1: return
    if not begin_ability_multi(ik, [target1_id, target2_id], g): return
    for tid in ik["tokens"]["ik_targets"]:
        p=get_player(g,tid)
        if p: p["tokens"]["innkeeper_protected"]=True
    if drunk_id:
        p=get_player(g,drunk_id)
        ik2=get_character(g,"Innkeeper")
        if p and ik2: try_impose_effect(ik2,p,"innkeeper_drunk",True,g)

def resolve_acrobat_night(acrobat,target_id,g):
    if g.get("night",0)<=1: return False
    if not begin_ability(acrobat,target_id,g): return False
    t=get_player(g,target_id)
    if not t: return False
    acrobat["tokens"]["acrobat_target"]=target_id
    if is_drunk_or_poisoned(t,g):
        src={"type":ABILITY_KILL,"source_character":"Acrobat"}
        if can_player_die(acrobat,src,g)==DIES: resolve_death(acrobat,src,g)
    return True

def resolve_acrobat_eot(acrobat,g):
    if not acrobat["alive"]: return False
    tid=acrobat["tokens"].get("acrobat_target")
    if not tid: return False
    t=get_player(g,tid)
    if not t or not t["alive"]: return False
    if is_drunk_or_poisoned(t,g):
        src={"type":ABILITY_KILL,"source_character":"Acrobat"}
        if can_player_die(acrobat,src,g)==DIES: resolve_death(acrobat,src,g)
        return True
    return False

def resolve_lleech_setup(ll,host_id,g):
    """First-night: Lleech picks host who is dynamically poisoned while Lleech is alive/sober."""
    if host_id: ll["tokens"]["lleech_host"]=host_id

def resolve_lleech_night(ll,target_id,g):
    """Subsequent nights: Lleech kills a chosen player. Host always poisoned (passive) via get_poison_sources."""
    if g.get("night",0)<=1: return
    if is_demon_suppressed(ll,g) or not target_id: return
    if not begin_ability(ll, target_id, g): return
    t=get_player(g,target_id)
    if not t: return
    src={"type":DEMON_KILL,"source_character":"Lleech"}
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)
# --- TROUBLE BREWING: INFORMATION TOWNSFOLK ---
def resolve_washerwoman_info(ww,p1_id,p2_id,character_name,g):
    g.setdefault("_woke_tonight",set()).add(ww["id"])
    t1=get_player(g,p1_id); t2=get_player(g,p2_id)
    players=[{"id":t["id"]} for t in [t1,t2] if t]
    return resolve_information(ww,{"type":"washerwoman","players":players,"character":character_name},g)

def resolve_librarian_info(lib,p1_id,p2_id,character_name,g):
    g.setdefault("_woke_tonight",set()).add(lib["id"])
    t1=get_player(g,p1_id); t2=get_player(g,p2_id)
    players=[{"id":t["id"]} for t in [t1,t2] if t]
    return resolve_information(lib,{"type":"librarian","players":players,"character":character_name},g)

def resolve_investigator_info(inv,p1_id,p2_id,character_name,g):
    g.setdefault("_woke_tonight",set()).add(inv["id"])
    t1=get_player(g,p1_id); t2=get_player(g,p2_id)
    players=[{"id":t["id"]} for t in [t1,t2] if t]
    return resolve_information(inv,{"type":"investigator","players":players,"character":character_name},g)

def resolve_chef_info(chef,g):
    g.setdefault("_woke_tonight",set()).add(chef["id"])
    players=g["players"]; n=len(players); count=0
    for i in range(n):
        p1=players[i]; p2=players[(i+1)%n]
        if check_misregistration(p1,"alignment",g)==EVIL and check_misregistration(p2,"alignment",g)==EVIL: count+=1
    return resolve_information(chef,{"type":"chef","count":count},g)

def resolve_empath_night(empath,g):
    if not empath["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(empath["id"])
    players=g["players"]; idx=players.index(empath); n=len(players); evil=0
    for d in (-1,1):
        for dist in range(1,n):
            p=players[(idx+d*dist)%n]
            if p["alive"] and not registers_as_dead(p):
                if check_misregistration(p,"alignment",g)==EVIL: evil+=1
                break
    return resolve_information(empath,{"type":"empath","count":evil},g)

def resolve_fortune_teller_night(ft,t1_id,t2_id,g):
    if not ft["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(ft["id"])
    result=False
    for tid in [t1_id,t2_id]:
        t=get_player(g,tid)
        if t:
            if check_misregistration(t,"char_type",g)==DEMON: result=True
            if t["id"]==ft["tokens"].get("red_herring"): result=True
    return resolve_information(ft,{"type":"fortune_teller","result":result},g)

def resolve_undertaker_night(ut,g):
    if g.get("night",0)<=1: return None
    if not ut["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(ut["id"])
    return resolve_information(ut,{"type":"undertaker","character":g.get("_undertaker_last_executed")},g)

# Baron: setup only (+2 Outsiders). No active ability to resolve.

# --- BMR: ASSASSIN ---
def resolve_assassin_night(assassin,target_id,g):
    """Once per game, night*: kill a player bypassing all protections."""
    if g.get("night",0)<=1: return
    if not assassin["ability_active"]: return
    if assassin["tokens"].get("assassin_used"): return
    assassin["tokens"]["assassin_used"]=True
    if ability_inactive(assassin,g): return
    g.setdefault("_woke_tonight",set()).add(assassin["id"])
    t=get_player(g,target_id)
    if not t: return
    src={"type":ABILITY_KILL,"source_character":"Assassin","bypass_protection":True}
    check_goon_targeting(assassin,target_id,g)
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)

# --- BMR: PSYCHOPATH ---
def resolve_psychopath_day(psycho,target_id,g):
    """Each day before nominations: publicly choose a player, they die."""
    if not psycho["ability_active"] or ability_inactive(psycho,g): return
    t=get_player(g,target_id)
    if not t or not t["alive"]: return
    src={"type":ABILITY_KILL,"source_character":"Psychopath"}
    if can_player_die(t,src,g)==DIES:
        resolve_death(t,src,g); g["_someone_died_today"]=True

# --- BMR: GAMBLER ---
def resolve_gambler_night(gambler,target_id,guessed_character,g):
    """Each night*: guess a player's character; die if wrong."""
    if g.get("night",0)<=1: return
    if not gambler["ability_active"] or ability_inactive(gambler,g): return
    g.setdefault("_woke_tonight",set()).add(gambler["id"])
    t=get_player(g,target_id)
    if not t: return
    if check_misregistration(t,"character",g)!=guessed_character:
        src={"type":ABILITY_KILL,"source_character":"Gambler"}
        if can_player_die(gambler,src,g)==DIES: resolve_death(gambler,src,g)

# --- BMR: COURTIER ---
def resolve_courtier_night(courtier,character_name,g):
    """Once per game, night: choose a character; that player is drunk for 3 nights."""
    if not courtier["ability_active"]: return
    if courtier["tokens"].get("courtier_used"): return
    courtier["tokens"]["courtier_used"]=True
    if ability_inactive(courtier,g): return
    g.setdefault("_woke_tonight",set()).add(courtier["id"])
    t=get_character(g,character_name)
    if t: t["tokens"]["courtier_drunk_remaining"]=3  # drunk for 3 nights

# --- BMR: PROFESSOR ---
def resolve_professor_night(prof,target_id,g):
    """Once per game, night*: choose a dead player; if Townsfolk, resurrect them."""
    if g.get("night",0)<=1: return
    if not prof["ability_active"]: return
    if prof["tokens"].get("professor_used"): return
    prof["tokens"]["professor_used"]=True
    if ability_inactive(prof,g): return
    g.setdefault("_woke_tonight",set()).add(prof["id"])
    t=get_player(g,target_id)
    if not t or t["alive"]: return
    if check_misregistration(t,"char_type",g)!=TOWNSFOLK: return
    t["alive"]=True; t["ability_active"]=True
    t["tokens"]["ghost_vote_available"]=False

# --- BMR: MOONCHILD ---
def resolve_moonchild_claim(moonchild,target_id,g):
    """After dying, choose a player: if good, they die tonight (deferred)."""
    if moonchild["alive"]: return
    t=get_player(g,target_id)
    if not t or not t["alive"]: return
    g["_moonchild_target"]=target_id

def resolve_moonchild_night(g):
    tid=g.pop("_moonchild_target",None)
    if not tid: return
    t=get_player(g,tid)
    if not t or not t["alive"]: return
    if check_misregistration(t,"alignment",g)==GOOD:
        src={"type":ABILITY_KILL,"source_character":"Moonchild"}
        if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)

# --- BMR: GOON ---
# Goon: first player to target Goon each night becomes drunk until dusk; Goon takes their alignment.
def _on_targeted_goon(target, source, context, g):
    inst_tokens = target.tokens
    hi = target.tokens.get("hermit_instances", {}).get("Goon")
    if hi and hi.get("ability_active") and not ability_inactive(target, g):
        inst_tokens = hi["tokens"]
    elif ability_inactive(target, g):
        return
    if inst_tokens.get("goon_triggered_night"): return
    inst_tokens["goon_triggered_night"] = True
    source["tokens"]["goon_drunk"] = True
    target["alignment"] = source["alignment"]

def _on_targeted_barber(target, source, context, g):
    if not context.get("killed"): return
    if not is_demon_source(source, g): return
    if ability_inactive(target, g): return
    g["_barber_triggered"] = True

CHARACTER_ON_TARGETED = {
    "Goon":   _on_targeted_goon,
    "Barber": _on_targeted_barber,
}

def notify_targeted(target, source, context, g):
    """Call when source targets target. context dict: chosen, killed, source_character."""
    if not target or not target["alive"]: return
    eff = effective_character(target, g)
    hook = CHARACTER_ON_TARGETED.get(eff)
    if hook: hook(target, source, context, g)

def check_goon_targeting(targeter, target_id, g):
    """Shim — delegates to notify_targeted."""
    t = get_player(g, target_id)
    if not t: return
    notify_targeted(t, targeter,
        {"chosen": True, "source_character": targeter["character"]}, g)


# --- BMR: CHAMBERMAID ---
# Any resolver that wakes a player should call: g.setdefault("_woke_tonight",set()).add(player_id)
def resolve_chambermaid_night(cm,p1_id,p2_id,g):
    """Each night: choose 2 alive players, learn how many woke due to their ability."""
    if not cm["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(cm["id"])
    woke=g.get("_woke_tonight",set())
    count=sum(1 for tid in [p1_id,p2_id] if tid and tid in woke and tid!=cm["id"])
    return resolve_information(cm,{"type":"chambermaid","count":count},g)

# --- BMR: LUNATIC ---
# Lunatic thinks they are the Demon but are not. Setup: ST tells them false Demon info.
# No active resolver needed — Lunatic picks "kill targets" each night but those do nothing.
# The Demon wakes separately and kills normally.
def resolve_lunatic_night(lunatic,target_ids,g):
    """Lunatic picks targets (no effect). Record for ST reference only."""
    lunatic["tokens"]["lunatic_targets"]=target_ids

# --- BMR: GOSSIP ---
# Gossip: each night*, one true public statement they made today becomes lethal if both named players are alive.
# The ST validates truth and decides if the statement fires.
def resolve_gossip_night(gossip,target1_id,target2_id,statement_true,victim_id,g):
    """ST provides victim_id; dies if both targets alive and statement was true."""
    if g.get("night",0)<=1: return
    if not statement_true: return
    if not begin_ability_multi(gossip, [target1_id, target2_id], g): return
    t1=get_player(g,target1_id); t2=get_player(g,target2_id)
    if not (t1 and t1["alive"] and t2 and t2["alive"]): return
    victim=get_player(g,victim_id)
    if not victim or not victim["alive"]: return
    src={"type":ABILITY_KILL,"source_character":"Gossip"}
    if can_player_die(victim,src,g)==DIES: resolve_death(victim,src,g)
def resolve_vigormortis_night(vm,target_id,g):
    """Each night*: kill a player. If a Minion, they keep their ability; ST then calls apply_vigormortis_poison."""
    if g.get("night",0)<=1 or is_demon_suppressed(vm,g) or not target_id: return
    if not begin_ability(vm, target_id, g): return
    t=get_player(g,target_id)
    if not t: return
    src={"type":DEMON_KILL,"source_character":"Vigormortis"}
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)

# --- SECTS & CITIES ---
def resolve_al_hadikhia_night(alh,target_ids,die_ids,g):
    """Al-Hadikhia: 3 targets choose live/die. Goon/Barber react via notify_targeted."""
    if g.get("night",0)<=1: return [],None
    if is_demon_suppressed(alh,g): return [],None
    src={"type":DEMON_KILL,"source_character":"Al-Hadikhia"}
    g.setdefault("_woke_tonight",set()).add(alh["id"])
    ctx_c={"chosen":True,"killed":False,"source_character":"Al-Hadikhia"}
    for tid in (target_ids or []):
        t=get_player(g,tid)
        if t: notify_targeted(t,alh,ctx_c,g)
    if is_drunk_or_poisoned(alh,g): return [],None
    if g.get("_alh_princess_no_kill"): g["_alh_no_kill_active"]=True
    die_set=set(die_ids or []); deaths=[]

    def _ceased():
        return (alh.get("character")!="Al-Hadikhia"
                or alh.get("char_type")!=DEMON or not alh["alive"])

    def _kill_notify(t):
        if can_player_die(t,src,g)==DIES:
            resolve_death(t,src,g)
            notify_targeted(t,alh,
                {"chosen":True,"killed":True,"source_character":"Al-Hadikhia"},g)
            if g.pop("_barber_triggered",False):
                resolve_barber_swap(
                    alh["id"],g.get("_barber_swap_p1"),g.get("_barber_swap_p2"),g)
            return True
        return False

    for tid in (target_ids or []):
        if not alh["alive"]: break
        if tid not in die_set: continue
        t=get_player(g,tid)
        if not t or not t["alive"]: continue
        if g.get("_alh_no_kill_active"): continue
        if _kill_notify(t): deaths.append(t)
        if _ceased(): return deaths,None
        win=check_win_conditions(g)
        if win: return deaths,win

    if alh["alive"] and alh.get("character")=="Al-Hadikhia" and target_ids and all(
        (lambda p: p and p["alive"])(get_player(g,tid)) for tid in target_ids
    ):
        for tid in target_ids:
            if not alh["alive"]: break
            t=get_player(g,tid)
            if not t or not t["alive"]: continue
            if g.get("_alh_no_kill_active"): continue
            if _kill_notify(t): deaths.append(t)
            if _ceased(): return deaths,None
            win=check_win_conditions(g)
            if win: return deaths,win
    g.pop("_alh_no_kill_active",None)
    return deaths,None


def resolve_kazali_night(kazali,assignments,g):
    if not kazali["ability_active"]: return []
    if kazali["tokens"].get("kazali_used"): return []
    kazali["tokens"]["kazali_used"]=True
    if ability_inactive(kazali,g): return []
    g.setdefault("_woke_tonight",set()).add(kazali["id"])
    keep={"ghost_vote_available","nominations_today","nominated_today"}
    changed=[]
    for a in (assignments or []):
        t=get_player(g,a["player_id"])
        if not t: continue
        t["tokens"]={k:v for k,v in t["tokens"].items() if k in keep}
        t["character"]=a["minion_character"]; t["char_type"]=MINION
        t["alignment"]=EVIL; t["ability_active"]=True; changed.append(t)
    return changed

def resolve_lot_setup(lot,assignments,g):
    if not lot["ability_active"]: return []
    if lot["tokens"].get("lot_setup_used"): return []
    lot["tokens"]["lot_setup_used"]=True
    if ability_inactive(lot,g): return []
    g.setdefault("_woke_tonight",set()).add(lot["id"])
    keep={"ghost_vote_available","nominations_today","nominated_today"}
    changed=[]
    for a in (assignments or []):
        t=get_player(g,a["player_id"])
        if not t: continue
        t["tokens"]={k:v for k,v in t["tokens"].items() if k in keep}
        t["character"]=a["minion_character"]; t["char_type"]=MINION
        t["alignment"]=EVIL; t["ability_active"]=True; changed.append(t)
    return changed

def post_kazali_lot_setup(g):
    _bd=next((p for p in g["players"] if "boffin_instance" in p.get("tokens",{})),None)
    if _bd and _bd["tokens"]["boffin_instance"].get("character")=="Bounty Hunter": g["_bh_setup_pending"]=True
    update_lycan_faux_paw(g)

# --- LIL MONSTA ---
def resolve_lil_monsta_vote(winner_id,g):
    """Minions vote each night on who babysits. Winner holds token and is responsible for the kill."""
    sw=get_character(g,"Scarlet Woman")
    if sw and sw["tokens"].get("sw_must_hold_lm"): return
    g["_lil_monsta_holder"]=winner_id

def resolve_lil_monsta_kill(target_id,g):
    """Babysitting Minion kills each night."""
    holder_id=g.get("_lil_monsta_holder")
    if not holder_id: return
    holder=get_player(g,holder_id)
    if g.get("night",0)<=1: return
    if not holder or not holder["alive"] or ability_inactive(holder,g): return
    t=get_player(g,target_id)
    if not t: return
    _was=ability_inactive(holder,g)
    check_goon_targeting(holder,target_id,g)
    if not _was and ability_inactive(holder,g): return
    if _was: return
    src={"type":DEMON_KILL,"source_character":"Lil Monsta"}
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)

# --- LEGION ---
def resolve_legion_night(killer_id,target_id,g):
    """ST picks one Legion player to kill each night."""
    killer=get_player(g,killer_id)
    if g.get("night",0)<=1: return
    if not killer or is_demon_suppressed(killer,g): return
    t=get_player(g,target_id)
    if not t: return
    g.setdefault("_woke_tonight",set()).add(killer["id"])
    _was=ability_inactive(killer,g)
    check_goon_targeting(killer,target_id,g)
    if not _was and ability_inactive(killer,g): return
    if _was: return
    src={"type":DEMON_KILL,"source_character":"Legion"}
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)


def character_is_in_play(character_name,g):
    return any(check_misregistration(p,"character",g)==character_name for p in g["players"])

# --- CERENOVUS ---
def resolve_cerenovus_night(cer,target_id,character_name,g):
    cer["tokens"].pop("cer_target",None)
    if not begin_ability(cer, target_id, g): return
    t=get_player(g,target_id)
    if not t or not t["alive"]: return
    cer["tokens"]["cer_target"]=target_id
    try_impose_effect(cer,t,"cerenovus_mad_as",character_name,g)

def resolve_cerenovus_day(target_id,acted_mad,g):
    """ST confirms if target acted mad. If not, they may die."""
    t=get_player(g,target_id)
    if not t or not t["alive"]: return
    t["tokens"].pop("cerenovus_mad_as",None)
    if not acted_mad:
        src={"type":ABILITY_KILL,"source_character":"Cerenovus"}
        if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)

# --- PIT-HAG ---
def resolve_pit_hag_night(ph,target_id,new_character,new_char_type,g):
    """Each night: choose a player and a character; they become it."""
    if not ph["ability_active"] or ability_inactive(ph,g): return False
    g.setdefault("_woke_tonight",set()).add(ph["id"])
    t=get_player(g,target_id)
    if not t: return False
    t["character"]=new_character
    t["char_type"]=new_char_type
    t["ability_active"]=True
    # Jinx tracking: Spy/Widow entering play via Pit-Hag
    from botc_jinxes import jinx_pair_active
    if new_character == "Spy" and not g.get("_spy_was_in_play"):
        if jinx_pair_active("Spy", "Damsel", g):
            g["_spy_was_in_play"] = True
    if new_character == "Widow" and not g.get("_widow_was_in_play"):
        if jinx_pair_active("Widow", "Damsel", g):
            g["_widow_was_in_play"] = True
    update_lycan_faux_paw(g)
    mark_ysk_pending(t,g)
    if t["id"]==g.get("_cannibal_executee_id"):
        g["_cannibal_told_character"]=new_character if t["alignment"]==GOOD else None
    return True

# --- INFORMATION RESOLVERS ---

# --- GENERAL ---
def resolve_general_night(general,result,g):
    """Each night: ST provides result (GOOD/EVIL/None-for-neither)."""
    if not general["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(general["id"])
    return resolve_information(general,{"type":"general","result":result},g)
def resolve_oracle_night(oracle,g):
    if g.get("night",0)<=1: return None
    if not oracle["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(oracle["id"])
    count=sum(1 for p in g["players"] if not p["alive"] and check_misregistration(p,"alignment",g)==EVIL)
    return resolve_information(oracle,{"type":"oracle","count":count},g)

def resolve_mathematician_night(math,g):
    """Each night: learn how many alive players have a malfunctioning ability."""
    if not math["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(math["id"])
    counted=set()
    for p in g["players"]:
        if not p["alive"]: continue
        if p["character"] in ("Drunk","Marionette","Lunatic"): counted.add(p["id"])
        elif is_drunk_or_poisoned(p,g): counted.add(p["id"])
    vortox=get_character(g,"Vortox")
    if vortox and vortox["alive"] and not is_drunk_or_poisoned(vortox,g):
        woke=g.get("_woke_tonight",set())
        for p in g["players"]:
            if not p["alive"] or p["id"] in counted or p["id"] not in woke: continue
            if (check_misregistration(p,"char_type",g)==TOWNSFOLK
                    and not is_safe_from_demon_effect(p,vortox,g)):
                counted.add(p["id"])
    return resolve_information(math,{"type":"mathematician","count":len(counted)},g)

def resolve_flowergirl_night(fg,g):
    if g.get("night",0)<=1: return None
    if not fg["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(fg["id"])
    return resolve_information(fg,{"type":"flowergirl","result":bool(g.get("_demon_voted_last_day"))},g)

def resolve_town_crier_night(tc,g):
    if g.get("night",0)<=1: return None
    if not tc["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(tc["id"])
    return resolve_information(tc,{"type":"town_crier","result":bool(g.get("_minion_nominated_last_day"))},g)

def resolve_seamstress_night(sm,p1_id,p2_id,g):
    if sm["tokens"].get("seamstress_used"): return None
    if not sm["ability_active"]: return None
    sm["tokens"]["seamstress_used"]=True
    if ability_inactive(sm,g): return None
    g.setdefault("_woke_tonight",set()).add(sm["id"])
    t1=get_player(g,p1_id); t2=get_player(g,p2_id)
    if not t1 or not t2: return None
    same=check_misregistration(t1,"alignment",g)==check_misregistration(t2,"alignment",g)
    raw={"type":"seamstress","players":[{"id":p1_id},{"id":p2_id}],"same_alignment":same}
    return resolve_information(sm,raw,g)

def resolve_clockmaker_info(cm,g):
    """Start knowing: steps from Demon to nearest Minion in seat order."""
    g.setdefault("_woke_tonight",set()).add(cm["id"])
    demon=next((p for p in g["players"] if p["char_type"]==DEMON),None)
    if not demon: return resolve_information(cm,{"type":"clockmaker","steps":0},g)
    players=g["players"]; n=len(players); idx=players.index(demon); best=n
    for dist in range(1,n):
        for d in (1,-1):
            p=players[(idx+d*dist)%n]
            if p["char_type"]==MINION: best=min(best,dist); break
    return resolve_information(cm,{"type":"clockmaker","steps":best if best<n else 0},g)

def resolve_cult_leader_night(cl,neighbor_id,g):
    """Cult Leader: each night become the alignment of an alive neighbour."""
    if not cl["alive"] or is_drunk_or_poisoned(cl,g): return
    g.setdefault("_woke_tonight",set()).add(cl["id"])
    if not neighbor_id: return
    nbr=get_player(g,neighbor_id)
    if not nbr or not nbr["alive"]: return
    left,right=get_alive_neighbors(cl,g)
    if not left or not right: return
    if nbr["id"] not in (left["id"],right["id"]): return
    cl["alignment"]=check_misregistration(nbr,"alignment",g)

def resolve_cult_vote(caller_id, g):
    """Return winning alignment if caller is the sober Cult Leader, else None."""
    cl = get_character(g, "Cult Leader")
    if not cl or cl["id"] != caller_id: return None
    if not cl["alive"] or is_drunk_or_poisoned(cl, g): return None
    res = cl["alignment"]
    if _heretic_flip(g): res = EVIL if res == GOOD else GOOD
    return res

def resolve_shugenja_info(sh,g):
    """Start knowing: closest evil player is clockwise or counterclockwise."""
    players=g["players"]; n=len(players); idx=players.index(sh)
    for dist in range(1,n):
        cw=players[(idx+dist)%n]; ccw=players[(idx-dist)%n]
        cw_evil=check_misregistration(cw,"alignment",g)==EVIL
        ccw_evil=check_misregistration(ccw,"alignment",g)==EVIL
        if cw_evil or ccw_evil:
            if cw_evil and ccw_evil: direction="arbitrary"
            elif cw_evil: direction="clockwise"
            else: direction="counterclockwise"
            g.setdefault("_woke_tonight",set()).add(sh["id"])
            return resolve_information(sh,{"type":"shugenja","direction":direction},g)
    return resolve_information(sh,{"type":"shugenja","direction":None},g)

def resolve_noble_info(noble,p1_id,p2_id,p3_id,g):
    """Start knowing 3 players, exactly 1 is evil."""
    g.setdefault("_woke_tonight",set()).add(noble["id"])
    players=[{"id":i} for i in [p1_id,p2_id,p3_id] if i]
    return resolve_information(noble,{"type":"noble","players":players},g)

def resolve_bounty_hunter_info(bh,target_id,g):
    """Start knowing 1 evil player. If known player dies, learn another tonight."""
    g.setdefault("_woke_tonight",set()).add(bh["id"])
    t=get_player(g,target_id)
    if not t: return None
    raw={"type":"bounty_hunter","players":[{"id":t["id"]}]}
    return resolve_information(bh,raw,g)

def resolve_juggler_day(juggler,guesses,g):
    """Day 1: publicly guess up to 5 player+character pairs. Store for night resolution."""
    if juggler["tokens"].get("juggler_used"): return
    juggler["tokens"]["juggler_used"]=True
    juggler["tokens"]["juggler_guesses"]=guesses

def resolve_juggler_night(juggler,g):
    """Night after juggler day: learn how many guesses were correct."""
    if g.get("night",0)<=1: return None
    if not juggler["ability_active"] or ability_inactive(juggler,g):
        return resolve_information(juggler,{"type":"juggler","count":0},g)
    guesses=juggler["tokens"].get("juggler_guesses",{})
    count=sum(1 for pid,char in guesses.items()
              if (p:=get_player(g,pid)) and check_misregistration(p,"character",g)==char)
    g.setdefault("_woke_tonight",set()).add(juggler["id"])
    return resolve_information(juggler,{"type":"juggler","count":count},g)

# --- LYCANTHROPE ---
def resolve_lycanthrope_night(lycan,target_id,g):
    if g.get("night",0)<=1: return
    t=get_player(g,target_id)
    if not t or not t["alive"]: return
    if not begin_ability(lycan, target_id, g): return None
    src={"type":ABILITY_KILL,"source_character":"Lycanthrope"}
    if check_misregistration(t,"alignment",g)==GOOD:
        if can_player_die(t,src,g)==DIES:
            resolve_death(t,src,g)
            g["_lycanthrope_killed_tonight"]=True
            return t
    return None

# --- OJO ---
def resolve_ojo_night(ojo,character_name,g):
    if g.get("night",0)<=1 or is_demon_suppressed(ojo,g): return
    if not begin_ability(ojo, None, g): return
    src={"type":DEMON_KILL,"source_character":"Ojo"}
    t=get_character(g,character_name)
    if t and t["alive"]:
        if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)
    else:
        g["_ojo_no_target_pending"]=True

def apply_ojo_kill(victim_id,g):
    v=get_player(g,victim_id)
    if v and v["alive"]:
        src={"type":DEMON_KILL,"source_character":"Ojo"}
        if can_player_die(v,src,g)==DIES: resolve_death(v,src,g)

# --- ENGINEER ---
def resolve_engineer_night(eng,assignments,g):
    """Once per game: reassign evil characters in play."""
    if not begin_ability(eng, None, g, used_token="engineer_used"): return False
    keep={"ghost_vote_available","nominations_today","nominated_today"}
    for a in (assignments or []):
        t=get_player(g,a["player_id"])
        if not t: continue
        t["tokens"]={k:v for k,v in t["tokens"].items() if k in keep}
        t["character"]=a["character"]; t["char_type"]=a["char_type"]
        t["alignment"]=EVIL; t["ability_active"]=True
    return True

# --- HARPY ---
def resolve_harpy_night(harpy,p1_id,p2_id,g):
    harpy["tokens"].pop("harpy_pair",None)
    if not begin_ability_multi(harpy, [p1_id, p2_id], g): return
    p1=get_player(g,p1_id); p2=get_player(g,p2_id)
    if p1 and p2 and p1["alive"] and p2["alive"]:
        harpy["tokens"]["harpy_pair"]=(p1_id,p2_id)

def resolve_harpy_nomination(nom_id,nee_id,g):
    harpy=get_character(g,"Harpy")
    if not harpy or not harpy["alive"] or ability_inactive(harpy,g): return
    pair=harpy["tokens"].get("harpy_pair")
    if not pair: return
    p1_id,p2_id=pair
    if nom_id==p1_id and nee_id==p2_id:
        other=get_player(g,p2_id)
        if other and other["alive"]:
            src={"type":ABILITY_KILL,"source_character":"Harpy"}
            if can_player_die(other,src,g)==DIES: resolve_death(other,src,g)

def resolve_harpy_madness_kill(target_id,g):
    """ST-callable: kill one player in the Harpy pair for failing madness independently."""
    harpy=get_character(g,"Harpy")
    if not harpy or not harpy["alive"] or ability_inactive(harpy,g): return False
    pair=harpy["tokens"].get("harpy_pair")
    if not pair or target_id not in pair: return False
    t=get_player(g,target_id)
    if t and t["alive"]:
        src={"type":ABILITY_KILL,"source_character":"Harpy"}
        if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)
    return True

# --- MEZEPHELES ---

_MEZ_WORDS=[
    "cobalt","vellichor","sonder","petrichor","somnolent","hiraeth","ephemeral",
    "susurrus","quixotic","nocturnal","lambent","lachrymose","mellifluous","sempiternal",
    "phosphene","crepuscular","umbra","stelliferous","noctiluca","viridian",
    "abyssal","gossamer","tenebrous","limerence","serendipity","pyrexia",
    "labyrinthine","iridescent","halcyon","sibilant","ossify","pluvial",
]
def generate_mezepheles_word():
    import random as _r, os as _os
    wf=_os.path.join(_os.path.dirname(__file__),"mezepheles_words.txt")
    try:
        with open(wf) as _f: pool=[w.strip() for w in _f if w.strip()]
    except: pool=_MEZ_WORDS
    return _r.choice(pool)

def resolve_mezepheles_night(mez,target_id,secret_word,g):
    mez["tokens"].pop("mez_target",None)
    if mez["tokens"].get("mez_converted"): return
    if not begin_ability(mez, target_id, g): return
    t=get_player(g,target_id)
    if t and t["alive"]:
        mez["tokens"]["mez_target"]=target_id
        t["tokens"]["mez_word"]=secret_word

def resolve_mezepheles_word_said(player_id,g):
    p=get_player(g,player_id)
    if not p or not p["tokens"].get("mez_word"): return False
    p["alignment"]=EVIL; p["tokens"].pop("mez_word",None)
    mez=get_character(g,"Mezepheles")
    if mez: mez["tokens"].pop("mez_target",None); mez["tokens"]["mez_converted"]=True
    return True

# --- SUMMONER ---
def resolve_summoner_night(summoner,target_id,demon_character,g):
    if not summoner["ability_active"]: return
    if g.get("night",0)<3: return
    if summoner["tokens"].get("summoner_used"): return
    summoner["tokens"]["summoner_used"]=True
    if ability_inactive(summoner,g): return
    g.setdefault("_woke_tonight",set()).add(summoner["id"])
    t=get_player(g,target_id)
    if not t: return
    keep={"ghost_vote_available","nominations_today","nominated_today"}
    t["tokens"]={k:v for k,v in t["tokens"].items() if k in keep}
    t["character"]=demon_character; t["char_type"]=DEMON
    t["alignment"]=EVIL; t["ability_active"]=True

# --- XAAN ---
def resolve_xaan_setup(g):
    g["_xaan_x"]=sum(1 for p in g["players"] if p["char_type"]==OUTSIDER)

def resolve_xaan_night(xaan,g):
    g.pop("_xaan_tf_poisoned",None)
    if not xaan["ability_active"] or ability_inactive(xaan,g): return
    g.setdefault("_woke_tonight",set()).add(xaan["id"])
    if g.get("night")==g.get("_xaan_x") and g.get("_xaan_x",0)>0:
        g["_xaan_tf_poisoned"]=True

# --- BARBER ---
def resolve_barber_swap(demon_id,p1_id,p2_id,g,context=None):
    d=get_player(g,demon_id)
    if not d or not d["alive"]: return False
    p1=get_player(g,p1_id); p2=get_player(g,p2_id)
    if not p1 or not p2: return False
    keep={"ghost_vote_available","nominations_today","nominated_today"}
    p1["tokens"]={k:v for k,v in p1["tokens"].items() if k in keep}
    p2["tokens"]={k:v for k,v in p2["tokens"].items() if k in keep}
    p1["character"],p2["character"]=p2["character"],p1["character"]
    p1["char_type"],p2["char_type"]=p2["char_type"],p1["char_type"]
    return True


def get_hatter_player_options(player_id,g,optional_rule=False,already_claimed=None):
    import json as _j
    player=get_player(g,player_id)
    if not player:return{"must_change":False,"options":[]}
    ptype=player["char_type"]; current=player["character"]
    claimed=set(already_claimed or [])
    must_change=current in claimed
    try: cdata=__import__("json").load(open("/home/discord-bot/botc_data.json")).get("characters",{})
    except: cdata={}
    script=set(g.get("script",[]))
    tmap={"townsfolk":TOWNSFOLK,"outsider":OUTSIDER,"minion":MINION,"demon":DEMON}
    if optional_rule and ptype==MINION: valid={MINION,DEMON}
    elif optional_rule and ptype==DEMON: valid={DEMON,MINION}
    else: valid={ptype}
    opts=[ch for ch in script if ch!=current and ch not in claimed
          and tmap.get(cdata.get(ch,{}).get("type","").lower()) in valid]
    return{"must_change":must_change,"options":opts}

def resolve_hatter_swap(swaps,g):
    try: cdata=__import__("json").load(open("/home/discord-bot/botc_data.json")).get("characters",{})
    except: cdata={}
    tmap={"townsfolk":TOWNSFOLK,"outsider":OUTSIDER,"minion":MINION,"demon":DEMON}
    keep={"ghost_vote_available","nominations_today","nominated_today"}
    changes=[]
    for pid,new_char in swaps:
        if new_char is None: continue
        p=get_player(g,pid)
        if not p or not p["alive"]: continue
        old=p["character"]
        if new_char==old: continue
        nt=tmap.get(cdata.get(new_char,{}).get("type","").lower(),p["char_type"])
        p["character"]=new_char; p["char_type"]=nt
        if nt in(MINION,DEMON): p["alignment"]=EVIL
        p["tokens"]={k:v for k,v in p["tokens"].items() if k in keep}
        p["ability_active"]=True
        changes.append((pid,old,new_char))
    return changes


# Butler
def resolve_butler_night(butler,master_id,g):
    butler['tokens'].pop('butler_master',None)
    if not master_id or master_id==butler['id']: return
    if not begin_ability(butler, master_id, g): return
    butler['tokens']['butler_master']=master_id

def butler_vote_ok(butler,voters,g):
    master_id=butler['tokens'].get('butler_master')
    if not master_id: return True
    if is_drunk_or_poisoned(butler,g): return True
    return master_id in voters
# Bureaucrat
def resolve_bureaucrat_night(bur,target_id,g):
    bur['tokens'].pop('bureaucrat_target',None)
    if not begin_ability(bur, target_id, g): return
    t=get_player(g,target_id)
    if t and t['alive']:
        bur['tokens']['bureaucrat_target']=target_id

# Thief
def resolve_thief_night(thief,target_id,g):
    thief['tokens'].pop('thief_target',None)
    if not begin_ability(thief, target_id, g): return
    t=get_player(g,target_id)
    if t and t['alive']:
        thief['tokens']['thief_target']=target_id
# Dreamer
def resolve_dreamer_night(dreamer,target_id,g):
    if not begin_ability(dreamer, target_id, g): return None
    t=get_player(g,target_id)
    if not t: return None
    raw={'type':'dreamer','player_id':target_id,'true_character':t['character'],'false_character':None}
    return resolve_information(dreamer,raw,g)
# Huntsman
def resolve_huntsman_night(hs,target_id,new_character,g):
    if hs['tokens'].get('huntsman_used'): return False
    if not hs['ability_active']: return False
    t=get_player(g,target_id)
    if not t or not t['alive']: return False
    g.setdefault('_woke_tonight',set()).add(hs['id'])
    if check_misregistration(t,'character',g)=='Damsel':
        hs['tokens']['huntsman_used']=True
        if ability_inactive(hs,g): return False
        keep={'ghost_vote_available','nominations_today','nominated_today'}
        t['tokens']={k:v for k,v in t['tokens'].items() if k in keep}
        t['character']=new_character; t['char_type']=TOWNSFOLK; t['ability_active']=True
        return True
    return False
# Village Idiot
def resolve_village_idiot_night(vi,target_id,g):
    if not vi['ability_active'] or ability_inactive(vi,g): return None
    t=get_player(g,target_id)
    if not t: return None
    g.setdefault('_woke_tonight',set()).add(vi['id'])
    aln=check_misregistration(t,'alignment',g)
    return resolve_information(vi,{'type':'village_idiot','player_id':target_id,'alignment':aln},g)
# King
def resolve_king_night(king,g):
    if g.get('night',0)<=1: return None
    if not king['ability_active'] or ability_inactive(king,g): return None
    evil_ct=sum(1 for p in g['players'] if p['alive'] and check_misregistration(p,'alignment',g)==EVIL)
    good_ct=sum(1 for p in g['players'] if p['alive'] and check_misregistration(p,'alignment',g)==GOOD)
    if evil_ct<=good_ct: return None
    demon=next((p for p in g['players'] if p['char_type']==DEMON and p['alive']),None)
    if not demon: return None
    g.setdefault('_woke_tonight',set()).add(king['id'])
    return resolve_information(king,{'type':'king','demon_id':demon['id']},g)
# Nightwatchman
def resolve_nightwatchman_night(nw,target_id,g):
    if nw['tokens'].get('nw_used'): return
    if not nw['ability_active']: return
    t=get_player(g,target_id)
    if not t or not t['alive']: return
    _was=ability_inactive(nw,g)
    check_goon_targeting(nw,target_id,g)
    if not _was and ability_inactive(nw,g): return
    nw['tokens']['nw_used']=True
    g.setdefault('_woke_tonight',set()).add(nw['id'])
    t['tokens']['nightwatchman_learned']=nw['id']

# Bone Collector
def resolve_bone_collector_night(bc,target_id,g):
    if bc['tokens'].get('bc_used'): return False
    if not bc['ability_active']: return False
    t=get_player(g,target_id)
    if not t or t['alive']: return False
    bc['tokens']['bc_used']=True
    if ability_inactive(bc,g): return False
    g.setdefault('_woke_tonight',set()).add(bc['id'])
    bc['tokens']['bc_target']=target_id
    t['ability_active']=True
    return True
# Fearmonger
def resolve_fearmonger_night(fm,target_id,g):
    prev=fm['tokens'].get('fm_target')
    fm['tokens']['fm_target']=target_id
    if not begin_ability(fm, target_id, g): return
    if fm['tokens'].get('fm_used'): return
    if prev and prev==target_id:
        fm['tokens']['fm_used']=True; g['_fearmonger_execute']=target_id
# Wraith
def resolve_wraith_night(wraith,target_id,g):
    t=get_player(g,target_id)
    if not t or not t['alive']: return
    if not begin_ability(wraith, target_id, g, used_token='wraith_used'): return
    src={'type':ABILITY_KILL,'source_character':'Wraith','bypass_protection':True}
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)
# High Priestess
def resolve_high_priestess_night(hp,target_id,g):
    """ST picks a player for the HP to talk to. Pure info delivery."""
    if not begin_ability(hp,target_id,g): return None
    t=get_player(g,target_id)
    if not t: return None
    return resolve_information(hp,{"type":"high_priestess","player_id":target_id},g)

# Virgin
# Organ Grinder
# --- BARISTA ---
def resolve_barista_night(barista,target_id,ability_num,g):
    """ST chooses target+ability; Barista does not learn either. Target is told.
    1: target sober/healthy/true-info tonight, immune to drunk/poison until dusk.
       Overrides Vortox. 2: target uses ability twice (once-per-game resets)."""
    if not begin_ability(barista,target_id,g): return
    t=get_player(g,target_id)
    if not t: return
    if ability_num==1:
        t["tokens"]["barista_sober_healthy"]=True
    else:
        t["tokens"]["barista_double_ability"]=True

def resolve_organ_grinder_night(og,abstain,g):
    if not begin_ability(og, None, g): return
    og['tokens']['drunk_tonight']=bool(abstain)

# Harlot
def resolve_harlot_night(harlot,target_id,g):
    """Die if chosen player woke tonight for their own ability. Call after target resolver."""
    if not begin_ability(harlot, target_id, g): return None
    t=get_player(g,target_id)
    if not t or not t["alive"]: return None
    info,acc=resolve_information(harlot,{"type":"harlot","player_id":target_id,"character":t["character"]},g)
    if acc is not None and target_id in g.get("_woke_tonight",set()):
        src={"type":ABILITY_KILL,"source_character":"Harlot"}
        if can_player_die(harlot,src,g)==DIES: resolve_death(harlot,src,g)
    return info,acc
# --- DAMSEL ---
def resolve_damsel_guess(minion_id,target_id,g):
    minion=get_player(g,minion_id)
    if not minion or not minion["alive"]: return None
    if check_misregistration(minion,"char_type",g)!=MINION: return None
    damsel=get_character(g,"Damsel")
    if not damsel or damsel["tokens"].get("damsel_guessed"): return None
    damsel["tokens"]["damsel_guessed"]=True
    target=get_player(g,target_id)
    if target and target["id"]==damsel["id"] and not is_drunk_or_poisoned(damsel,g):
        h=get_character(g,"Heretic")
        return GOOD if h and not is_drunk_or_poisoned(h,g) else EVIL
    return None

# --- GOLEM ---
def resolve_golem_nominate(golem_id,nee_id,g):
    golem=get_player(g,golem_id)
    if not golem: return False
    if not begin_ability(golem, nee_id, g, used_token="golem_used"): return False
    nee=get_player(g,nee_id)
    # Returns True if nominee is a non-demon (game runner should issue ability kill).
    # Execution/death are independent — no protection from execution granted.
    return check_misregistration(nee,"char_type",g)!=DEMON if nee else False

# --- VIZIER ---
def resolve_vizier_execute(vizier_id,target_id,g):
    vizier=get_player(g,vizier_id)
    if not vizier or not vizier["alive"]: return
    if vizier["tokens"].get("vizier_used"): return
    vizier["tokens"]["vizier_used"]=True
    if ability_inactive(vizier,g): return
    resolve_execution(target_id,g)

# --- PUZZLEMASTER ---
def resolve_puzzlemaster_guess(pm_id,target_id,g):
    pm=get_player(g,pm_id)
    if not pm or pm["tokens"].get("pm_used"): return None
    pm["tokens"]["pm_used"]=True
    t=get_player(g,target_id)
    if not t: return None
    if t["char_type"]==DEMON and not is_drunk_or_poisoned(pm,g):
        h=get_character(g,"Heretic")
        return EVIL if h and not is_drunk_or_poisoned(h,g) else GOOD
    return None

# --- BALLOONIST ---
_BALLOON_TYPES=[TOWNSFOLK,OUTSIDER,MINION,DEMON]
def resolve_balloonist_night(balloon,shown_player_id,g):
    if not balloon["ability_active"]: return None
    g.setdefault("_woke_tonight",set()).add(balloon["id"])
    idx=balloon["tokens"].get("balloonist_type_idx",0)%len(_BALLOON_TYPES)
    balloon["tokens"]["balloonist_type_idx"]=idx+1
    return resolve_information(balloon,{"type":"balloonist","player_id":shown_player_id,"char_type":_BALLOON_TYPES[idx]},g)

# --- POPPY GROWER ---
def is_poppy_grower_alive(g):
    pg=get_character(g,"Poppy Grower")
    if pg and pg["alive"] and not is_drunk_or_poisoned(pg,g): return True
    can=get_character(g,"Cannibal")
    if (can and can["alive"] and not is_drunk_or_poisoned(can,g)
            and g.get("_cannibal_told_character")=="Poppy Grower"): return True
    return False

# --- ALCHEMIST ---
def resolve_alchemist_setup(alch,minion_ability_name,g):
    alch["tokens"]["alchemist_ability"]=minion_ability_name

# --- PIXIE ---
def resolve_pixie_setup(pixie,character_name,g):
    if not pixie["ability_active"] or ability_inactive(pixie,g): return None
    pixie["tokens"]["pixie_character"]=character_name
    return resolve_information(pixie,{"type":"pixie","character":character_name},g)

def resolve_pixie_gain(pixie_id,g):
    """Called when Pixie's character dies and ST confirms Pixie was mad."""
    pixie=get_player(g,pixie_id)
    if not pixie or not pixie["alive"] or ability_inactive(pixie,g): return False
    if not pixie["tokens"].get("pixie_was_mad"): return False
    if pixie["tokens"].get("pixie_gained"): return False
    pixie["tokens"]["pixie_gained"]=pixie["tokens"].get("pixie_character")
    return True

# --- VILLAGE IDIOT ---
def setup_vi_drunk(g):
    import random
    vis=[p for p in g.get("players",[]) if p.get("character")=="Village Idiot"]
    for p in vis: p["tokens"].pop("vi_drunk",None)
    extras=[p for p in vis if not p["tokens"].get("vi_original")]
    if extras: random.choice(extras)["tokens"]["vi_drunk"]=True

def assign_vi_drunk_if_needed(g):
    """Call after any mid-game VI creation to assign drunk if none exists yet."""
    import random
    vis=[p for p in g.get("players",[]) if p.get("character")=="Village Idiot"]
    extras=[p for p in vis if not p["tokens"].get("vi_original")]
    if extras and not any(p["tokens"].get("vi_drunk") for p in extras):
        random.choice(extras)["tokens"]["vi_drunk"]=True

# --- BOFFIN ---
def setup_boffin(g):
    bchar=g.get("_boffin_char")
    if not bchar: return
    boffin=get_character(g,"Boffin")
    if not boffin or not boffin["alive"]: return
    demon=next((p for p in g["players"] if p["char_type"]==DEMON and p["alive"]),None)
    if not demon: return
    demon["tokens"]["boffin_instance"]={"character":bchar,"tokens":{},"ability_active":True}

def is_boffin_impaired(g):
    boffin=get_character(g,"Boffin")
    if not boffin or not boffin["alive"]: return True
    if not any("boffin_instance" in p.get("tokens",{}) for p in g["players"]): return True
    return is_drunk_or_poisoned(boffin,g)

def get_boffin_fake_player(demon,g):
    inst=demon["tokens"].get("boffin_instance",{})
    char=inst.get("character","")
    return make_ability_proxy(
        demon, inst.get("tokens",{}), character=char,
        override_id=demon["id"]+"_boffin",
        override_alignment=GOOD,
        override_char_type=_BOFFIN_CHAR_TYPE.get(char,TOWNSFOLK)
    )

def _boffin_sailor_pre(demon, g):
    demon["tokens"].pop("boffin_sailor_protected", None)
    old = demon["tokens"].pop("boffin_sailor_target", None)
    if old:
        op = get_player(g, old)
        if op: op["tokens"].pop("boffin_sailor_drunked", None)

def _boffin_sailor_post(demon, fake, g):
    if fake["tokens"].get("sailor_target"):
        demon["tokens"]["boffin_sailor_target"] = fake["tokens"]["sailor_target"]
        tp = get_player(g, fake["tokens"]["sailor_target"])
        if tp: tp["tokens"]["boffin_sailor_drunked"] = True
    if fake["tokens"].get("sailor_protected"):
        demon["tokens"]["boffin_sailor_protected"] = True

def resolve_boffin_ability(demon, target_ids, g, extra=None):
    inst = demon["tokens"].get("boffin_instance")
    if not inst: return None, None
    if is_boffin_impaired(g): return None, None
    if not inst.get("ability_active", True): return None, None
    char = inst.get("character", "")
    choices = {"targets": target_ids or [], "character": extra}
    pre  = _boffin_sailor_pre  if char == "Sailor" else None
    post = _boffin_sailor_post if char == "Sailor" else None
    result = dispatch_borrowed_night(
        demon, inst, choices, g,
        override_id=demon["id"]+"_boffin",
        override_alignment=GOOD,
        override_char_type=_BOFFIN_CHAR_TYPE.get(char, TOWNSFOLK),
        pre_hook=pre, post_hook=post)
    return char, result

BOFFIN_ONGOING_AFTER_DEATH={"Sweetheart"}
def transfer_boffin_to(new_demon_id,g):
    new=get_player(g,new_demon_id)
    if not new: return
    old=next((p for p in g["players"] if p["id"]!=new_demon_id and "boffin_instance" in p.get("tokens",{})),None)
    if old:
        inst=old["tokens"].pop("boffin_instance")
        inst["ability_active"]=True
        new["tokens"]["boffin_instance"]=inst

_BOFFIN_CHAR_TYPE={
 'Washerwoman':TOWNSFOLK,'Librarian':TOWNSFOLK,'Investigator':TOWNSFOLK,
 'Chef':TOWNSFOLK,'Empath':TOWNSFOLK,'Fortune Teller':TOWNSFOLK,
 'Undertaker':TOWNSFOLK,'Monk':TOWNSFOLK,'Ravenkeeper':TOWNSFOLK,
 'Virgin':TOWNSFOLK,'Slayer':TOWNSFOLK,'Soldier':TOWNSFOLK,'Mayor':TOWNSFOLK,
 'Butler':OUTSIDER,'Drunk':OUTSIDER,'Recluse':OUTSIDER,'Saint':OUTSIDER,
 'Grandmother':TOWNSFOLK,'Sailor':TOWNSFOLK,'Chambermaid':TOWNSFOLK,
 'Exorcist':TOWNSFOLK,'Innkeeper':TOWNSFOLK,'Gambler':TOWNSFOLK,
 'Gossip':TOWNSFOLK,'Courtier':TOWNSFOLK,'Professor':TOWNSFOLK,
 'Mathematician':TOWNSFOLK,'Fool':TOWNSFOLK,'Pacifist':TOWNSFOLK,
 'Town Crier':TOWNSFOLK,'Oracle':TOWNSFOLK,'Savant':TOWNSFOLK,
 'Seamstress':TOWNSFOLK,'Flowergirl':TOWNSFOLK,'Juggler':TOWNSFOLK,
 'Acrobat':TOWNSFOLK,'Clockmaker':TOWNSFOLK,'Dreamer':TOWNSFOLK,
 'Snake Charmer':TOWNSFOLK,'Philosopher':TOWNSFOLK,'Artist':TOWNSFOLK,
 'Sage':TOWNSFOLK,'Shugenja':TOWNSFOLK,'Balloonist':TOWNSFOLK,
 'Preacher':TOWNSFOLK,'Lunatic':OUTSIDER,'Tinker':OUTSIDER,
 'Moonchild':OUTSIDER,'Goon':OUTSIDER,'Mutant':OUTSIDER,
 'Hatter':OUTSIDER,
}

_IS_NIGHT = lambda ks,g: g.get("night",0) > 0
_IS_DEMON_KILL = lambda ks,g: ks["type"] == DEMON_KILL

CHARACTER_DEATH_TRIGGERS = {
    "Farmer":       (("_pending_farmer_replacement",True), None, _IS_NIGHT),
    "Sweetheart":   (("_sweetheart_pending",True), None, None),
    "Barber":       (("_barber_triggered",True), None, None),
    "Hatter":       (("_hatter_triggered",True), None, None),
    "Poppy Grower": (("_poppy_grower_dead",True), None, None),
    "Ravenkeeper":  (None, "ravenkeeper_triggered", _IS_NIGHT),
    "Klutz":        (None, "klutz_triggered", None),
    "Sage":         (None, "sage_triggered", _IS_DEMON_KILL),
    "Banshee":      (None, "banshee_killed_by_demon", _IS_DEMON_KILL),
}

def _apply_death_triggers(player, inst, kill_source, g):
    bc = inst.get("character","")
    entry = CHARACTER_DEATH_TRIGGERS.get(bc)
    if entry:
        gflag, tok_key, cond = entry
        if cond is None or cond(kill_source, g):
            if gflag: g[gflag[0]] = gflag[1]
            if tok_key: inst["tokens"][tok_key] = True
            if bc == "Banshee": player["ability_active"] = True
    if bc == "Poisoner":
        old = inst["tokens"].get("poisoner_last_target")
        if old:
            pt = get_player(g, old)
            if pt: pt["tokens"].pop("poisoned_by_poisoner", None)

def _apply_boffin_death_triggers(player, kill_source, g):
    inst = player["tokens"].get("boffin_instance")
    if not inst: return
    if is_boffin_impaired(g): return
    inst["ability_active"] = False
    _apply_death_triggers(player, inst, kill_source, g)

def _apply_cannibal_instance_death_triggers(player, kill_source, g):
    inst = player["tokens"].get("cannibal_instance")
    if not inst or not inst.get("ability_active"): return
    if is_drunk_or_poisoned(player, g): return
    inst["ability_active"] = False
    _apply_death_triggers(player, inst, kill_source, g)


def setup_lycan_faux_paw(g):
    import random
    lycan=get_character(g,"Lycanthrope")
    if not lycan: return
    if "_lycan_faux_paw" in g: return
    cands=[p for p in g["players"] if _eligible_for_faux_paw(p,g)]
    g["_lycan_faux_paw"]=random.choice(cands)["id"] if cands else None

def update_lycan_faux_paw(g):
    import random
    lycan=get_character(g,"Lycanthrope")
    if not lycan: return
    cur=g.get("_lycan_faux_paw")
    if cur:
        p=get_player(g,cur)
        if p and _eligible_for_faux_paw(p,g): return
    cands=[p for p in g["players"] if _eligible_for_faux_paw(p,g)]
    g["_lycan_faux_paw"]=random.choice(cands)["id"] if cands else None

def _registers_as_good_base(p,g):
    """Alignment registration ignoring faux paw — used for faux paw eligibility."""
    char=p["character"]
    if char in ("Spy","Recluse","Legion"):
        return p["tokens"].get("registers_as_alignment",p["alignment"])==GOOD
    if char=="Ogre": return get_alignment(p,g)==GOOD
    return p["alignment"]==GOOD

def _eligible_for_faux_paw(p,g):
    if p["tokens"].get("lycan_registers_as")==EVIL: return False
    return _registers_as_good_base(p,g)

# --- HERMIT ---
def resolve_hermit_outsider_night(hermit, outsider_char, choices, g):
    """Hermit acts as a script Outsider — routes through dispatch_borrowed_night."""
    inst = hermit["tokens"].get("hermit_instances", {}).get(outsider_char)
    if not inst or not inst.get("ability_active", True): return None
    if not hermit["ability_active"] or ability_inactive(hermit, g): return None
    return dispatch_borrowed_night(hermit, inst, choices, g)

def setup_hermit(hermit,g):
    """Set up hermit_instances from script Outsiders."""
    outsiders=[c for c in g.get("script",[]) if canonical_char_type(c)==OUTSIDER and c!="Hermit"]
    instances={n:{"tokens":{},"ability_active":True,"character":n} for n in outsiders}
    hermit["tokens"]["hermit_instances"]=instances
    if "Lunatic" in instances:
        hermit["tokens"]["hermit_told_demon"]=True


# --- NIGHT ORDER ---
TRIGGER_ONLY_NIGHT = frozenset({
    "Barber","Hatter","Tinker","Sweetheart","Plague Doctor",
})

# Characters only in FIRST_NIGHT_ORDER (You Start Knowing).
# If they enter play after night 1, they wake after killing roles.
YSK_ROLES = frozenset({
    "Washerwoman","Librarian","Investigator","Chef","Clockmaker",
    "Steward","Knight","Noble","Shugenja","Pixie","Ogre",
    "Alchemist","Apprentice","Boffin","Widow",
})
# Position after Moonchild (720) and before Grandmother (730)
DEFAULT_YSK_NIGHT_POSITION = 725
NIGHT_META_FIRST = {"MINION_INFO": 210, "DEMON_INFO": 250}
def get_living_neighbours(player,g):
    players=g["players"]
    if player not in players: return []
    idx=players.index(player); n=len(players); result=[]
    for d in (-1,1):
        for dist in range(1,n):
            p=players[(idx+d*dist)%n]
            if p["alive"]: result.append(p); break
    return result

def get_first_night_demon_info(demon,g):
    pg=get_character(g,"Poppy Grower")
    sup=bool(pg and pg["alive"] and not is_drunk_or_poisoned(pg,g))
    minions=[p for p in g["players"] if p["char_type"]==MINION and p["alive"]]
    mag=get_character(g,"Magician")
    if mag and mag["alive"] and not is_drunk_or_poisoned(mag,g):
        minions=minions+[mag]
    return {"minions":[] if sup else minions,"bluffs":g.get("_demon_bluffs",[]),"suppressed":sup}

def get_first_night_minion_info(minion,g):
    pg=get_character(g,"Poppy Grower")
    sup=bool(pg and pg["alive"] and not is_drunk_or_poisoned(pg,g))
    demons=[p for p in g["players"] if p["char_type"]==DEMON and p["alive"]]
    mag=get_character(g,"Magician")
    if mag and mag["alive"] and not is_drunk_or_poisoned(mag,g):
        demons=demons+[mag]
    fellows=[p for p in g["players"] if p["char_type"]==MINION and p["alive"] and p["id"]!=minion["id"]]
    return {"demons":[] if sup else demons,"fellows":[] if sup else fellows,"suppressed":sup}

FIRST_NIGHT_ORDER = {
    "Angel":40,"Buddhist":50,"Toymaker":60,
    "Wraith":80,"Lord of Typhon":90,"Kazali":100,
    "Apprentice":110,"Barista":120,"Bureaucrat":130,"Thief":140,
    "Boffin":150,"Philosopher":160,"Alchemist":170,"Poppy Grower":180,
    "Yaggababble":190,"Magician":200,
    "Snitch":220,"Lunatic":230,"Summoner":240,
    "King":260,"Sailor":270,"Marionette":280,
    "Engineer":290,"Preacher":300,
}
FIRST_NIGHT_ORDER.update({
    "Lil' Monsta":310,"Lleech":320,"Xaan":330,
    "Poisoner":340,"Widow":350,"Courtier":360,"Wizard":370,
    "Snake Charmer":380,"Godfather":390,"Organ Grinder":400,
    "Devil's Advocate":410,"Evil Twin":420,"Witch":430,
    "Cerenovus":440,"Fearmonger":450,"Harpy":460,"Mezepheles":470,
    "Pukka":480,"Pixie":490,"Huntsman":500,"Damsel":510,
    "Washerwoman":530,"Librarian":540,"Investigator":550,"Chef":560,
    "Empath":570,"Fortune Teller":580,"Butler":590,"Grandmother":600,
    "Clockmaker":610,"Dreamer":620,"Seamstress":630,
    "Steward":640,"Knight":650,"Noble":660,"Balloonist":670,
    "Shugenja":680,"Village Idiot":690,"Bounty Hunter":700,
    "Night Watchman":710,"Cult Leader":720,
    "Spy":730,"Ogre":740,"High Priestess":750,
    "General":760,"Chambermaid":770,"Mathematician":780,
    "Leviathan":9000,"Vizier":9010,
})
OTHER_NIGHT_ORDER = {
    "Duchess":40,"Toymaker":50,
    "Wraith":60,"Barista":70,"Bone Collector":80,"Bureaucrat":90,
    "Harlot":100,"Thief":110,
    "Philosopher":120,"Poppy Grower":130,"Sailor":140,
    "Engineer":150,"Preacher":160,"Xaan":170,"Poisoner":180,
    "Courtier":190,"Innkeeper":200,"Wizard":210,"Gambler":220,
    "Acrobat":230,"Snake Charmer":240,"Monk":250,
    "Organ Grinder":260,"Devil's Advocate":270,"Witch":280,
    "Cerenovus":290,"Pit-Hag":300,"Fearmonger":310,
    "Harpy":320,"Mezepheles":330,"Scarlet Woman":340,
    "Summoner":350,"Lunatic":360,"Exorcist":370,"Lycanthrope":380,
}
OTHER_NIGHT_ORDER.update({
    "Legion":390,"Imp":400,"Zombuul":410,"Pukka":420,
    "Shabaloth":430,"Po":440,"Fang Gu":450,"No Dashii":460,
    "Vortox":470,"Lord of Typhon":480,"Vigormortis":490,
    "Ojo":500,"Al-Hadikhia":510,"Lleech":520,
    "Lil' Monsta":530,"Yaggababble":540,"Kazali":550,
    "Assassin":560,"Godfather":570,"Gossip":580,
})
OTHER_NIGHT_ORDER.update({
    "Hatter":590,"Barber":600,"Sweetheart":610,"Plague Doctor":620,
    "Sage":630,"Banshee":640,"Professor":650,"Choirboy":660,
    "Huntsman":670,"Damsel":680,"Farmer":700,
    "Tinker":710,"Moonchild":720,"Grandmother":730,
    "Ravenkeeper":750,"Empath":760,"Fortune Teller":770,
    "Undertaker":780,"Dreamer":790,"Flowergirl":800,
    "Town Crier":810,"Oracle":820,"Seamstress":830,
    "Juggler":840,"Balloonist":850,"Village Idiot":860,
    "King":870,"Bounty Hunter":880,"Night Watchman":890,
    "Cult Leader":900,"Butler":910,"Spy":920,
    "High Priestess":930,"General":940,"Chambermaid":950,
    "Mathematician":960,"Leviathan":9000,
})

def set_amnesiac_position(amnesiac,night_position,g):
    """ST sets where Amnesiac wakes in the night order to match their ability.
    Pass None to remove them from the wake order entirely."""
    if night_position is None:
        amnesiac["tokens"].pop("amnesiac_night_position",None)
    else:
        amnesiac["tokens"]["amnesiac_night_position"]=night_position

# Characters with once-per-game used tokens that Barista double-ability resets
BARISTA_RESETTABLE_TOKENS = {
    "Widow": "widow_used",
    "Engineer": "engineer_used",
    "Wraith": "wraith_used",
    "Assassin": "assassin_used",
    "Night Watchman": "nw_used",
    "Bone Collector": "bc_used",
}

def barista_reset_for_double(player):
    """Clear once-per-game used token so a Barista-doubled player can act again."""
    tok=BARISTA_RESETTABLE_TOKENS.get(player["character"])
    if tok: player["tokens"].pop(tok,None)

def mark_ysk_pending(player, g):
    """Call when a YSK character enters play after night 1 so they
    receive their start-of-game info at the right point in the night order
    (after killing roles). Token clears automatically via ONE_NIGHT_TOKENS."""
    if g.get("night", 1) > 1 and player.get("character", "") in YSK_ROLES:
        player["tokens"]["ysk_pending"] = True

def get_wake_order(g, include_trigger_only=False, include_dawn=False):
    """Return alive players sorted by their night wake position.
    is_first_night determined from g['night'].
    Skips characters not in the night order (no night ability).
    Skips trigger-only characters unless include_trigger_only=True.
    Skips Dawn characters (pos>=9000) unless include_dawn=True."""
    is_first = g.get("night", 1) == 1
    order = FIRST_NIGHT_ORDER if is_first else OTHER_NIGHT_ORDER
    result = []
    for p in g.get("players", []):
        if not p.get("alive"):
            if not p.get("ability_active"): continue
        char = p.get("character", "")
        pos = order.get(char)
        if pos is None:
            if char=="Amnesiac" and p["tokens"].get("amnesiac_night_position"):
                pos=p["tokens"]["amnesiac_night_position"]
            elif not is_first and char in YSK_ROLES and p["tokens"].get("ysk_pending"):
                pos=DEFAULT_YSK_NIGHT_POSITION
            elif char=="Cannibal":
                pos=get_cannibal_night_position(g)
                if pos is None: continue
            elif char=="Philosopher" and not is_first:
                cc=p["tokens"].get("copied_character")
                pos=OTHER_NIGHT_ORDER.get(cc) if cc else None
                if pos is None: continue
            elif p["tokens"].get("boffin_instance",{}).get("ability_active"):
                bi=p["tokens"]["boffin_instance"]
                bpos=OTHER_NIGHT_ORDER.get(bi.get("character",""))
                if bpos is not None:
                    result.append((bpos,bi["character"],p))
                if pos is None: continue
            else:
                continue

        if not include_trigger_only and char in TRIGGER_ONLY_NIGHT: continue
        if not include_dawn and pos >= 9000: continue
        result.append((pos, char, p))
    result.sort(key=lambda x: x[0])
    return [p for _, _, p in result]


# -- CANNIBAL --

def get_cannibal_effective_character(g):
    can=get_character(g,"Cannibal")
    if not can or not can["alive"]: return None,False
    inst=can["tokens"].get("cannibal_instance")
    if not inst or not inst.get("ability_active"): return None,False
    bid=inst.get("bound_player_id")
    if bid:
        ex=get_player(g,bid)
        if ex:
            told=check_misregistration(ex,"character",g)
            is_evil=check_misregistration(ex,"alignment",g)==EVIL
            inst["character"]=told
            return told,is_evil
    told=inst.get("character")
    eid=g.get("_cannibal_executee_id")
    ex=get_player(g,eid) if eid else None
    is_evil=bool(ex and check_misregistration(ex,"alignment",g)==EVIL)
    return told,is_evil

def get_cannibal_night_position(g):
    told, _ = get_cannibal_effective_character(g)
    if not told: return None
    if told in YSK_ROLES: return DEFAULT_YSK_NIGHT_POSITION
    return OTHER_NIGHT_ORDER.get(told)

def _dispatch_grandmother(fake, choices, g):
    inst = fake.tokens
    if not inst.get("grandchild"):
        return resolve_grandmother_night(fake, choices["target"], g)
    t = get_player(g, inst["grandchild"])
    return resolve_information(fake, {
        "type": "grandmother",
        "player_id": inst["grandchild"],
        "character": t["character"] if t else None
    }, g)

_NR = None  # no-op sentinel

CHARACTER_NIGHT_RESOLVERS = {
    "Chef":          lambda f,c,g: resolve_chef_info(f,g),
    "Empath":        lambda f,c,g: resolve_empath_night(f,g),
    "Undertaker":    lambda f,c,g: resolve_undertaker_night(f,g),
    "Flowergirl":    lambda f,c,g: resolve_flowergirl_night(f,g),
    "Town Crier":    lambda f,c,g: resolve_town_crier_night(f,g),
    "Oracle":        lambda f,c,g: resolve_oracle_night(f,g),
    "Mathematician": lambda f,c,g: resolve_mathematician_night(f,g),
    "Juggler":       lambda f,c,g: resolve_juggler_night(f,g),
    "Clockmaker":    lambda f,c,g: resolve_clockmaker_info(f,g),
    "Shugenja":      lambda f,c,g: resolve_shugenja_info(f,g),
    "King":          lambda f,c,g: resolve_king_night(f,g),
}
CHARACTER_NIGHT_RESOLVERS.update({
    "Monk":          lambda f,c,g: resolve_monk_night(f,c["target"],g),
    "Poisoner":      lambda f,c,g: resolve_poisoner_night(f,c["target"],g),
    "Witch":         lambda f,c,g: resolve_witch_night(f,c["target"],g),
    "Dreamer":       lambda f,c,g: resolve_dreamer_night(f,c["target"],g),
    "Butler":        lambda f,c,g: resolve_butler_night(f,c["target"],g),
    "Bounty Hunter": lambda f,c,g: resolve_bounty_hunter_info(f,c.get("target"),g),
    "Balloonist":    lambda f,c,g: resolve_balloonist_night(f,c.get("target"),g),
    "Cult Leader":   lambda f,c,g: resolve_cult_leader_night(f,c.get("target"),g),
    "High Priestess":lambda f,c,g: resolve_high_priestess_night(f,c["target"],g),
    "Night Watchman":lambda f,c,g: resolve_nightwatchman_night(f,c["target"],g),
    "Steward": lambda f,c,g: resolve_information(
        f,{"type":"steward","player_id":c.get("target")},g),
})
CHARACTER_NIGHT_RESOLVERS.update({
    "Fortune Teller":lambda f,c,g: resolve_fortune_teller_night(f,c["t1"],c["t2"],g),
    "Chambermaid":   lambda f,c,g: resolve_chambermaid_night(f,c["t1"],c["t2"],g),
    "Seamstress":    lambda f,c,g: resolve_seamstress_night(f,c["t1"],c["t2"],g),
    "Noble":         lambda f,c,g: resolve_noble_info(f,c["t1"],c["t2"],c["t3"],g),
    "Gambler": lambda f,c,g: resolve_gambler_night(f,c["target"],c["character"],g),
    "General":       lambda f,c,g: resolve_general_night(f,c["result"],g),
    "Grandmother":   _dispatch_grandmother,
    "Ravenkeeper": lambda f,c,g: None,
})
CHARACTER_NIGHT_RESOLVERS.update({
    "Washerwoman": lambda f,c,g: resolve_washerwoman_info(
        f,c["t1"],c["t2"],c["character"],g),
    "Librarian": lambda f,c,g: resolve_librarian_info(
        f,c["t1"],c["t2"],c["character"],g),
    "Investigator": lambda f,c,g: resolve_investigator_info(
        f,c["t1"],c["t2"],c["character"],g),
    "Knight": lambda f,c,g: resolve_information(f,{
        "type":"knight",
        "players":[{"id":tid} for tid in c.get("targets",[])]},g),
    "Ogre":lambda f,c,g:None,"Alchemist":lambda f,c,g:None,
    "Apprentice":lambda f,c,g:None,"Boffin":lambda f,c,g:None,
    "Widow":lambda f,c,g:None,"Pixie":lambda f,c,g:None,
})

CHARACTER_NIGHT_RESOLVERS.update({
    "Exorcist":lambda f,c,g: resolve_exorcist_night(f,c["target"],g),
    "Preacher": lambda f,c,g: resolve_preacher_night(f,c["target"],g),
    "Snake Charmer":lambda f,c,g: resolve_snake_charmer_night(f,c["target"],g),
    "Sailor":   lambda f,c,g: resolve_sailor_night(f,c["target"],g),
    "Courtier": lambda f,c,g: resolve_courtier_night(f,c["character"],g),
    "Innkeeper":lambda f,c,g: resolve_innkeeper_night(
        f,c["t1"],c["t2"],c.get("drunk_id",c["t2"]),g),
})


def dispatch_borrowed_night(actor, inst, choices, g,
                             override_id=None, override_alignment=None,
                             override_char_type=None,
                             pre_hook=None, post_hook=None):
    """Dispatch borrowed-ability through CHARACTER_NIGHT_RESOLVERS."""
    c = inst.get("character")
    if not c: return None
    resolver = CHARACTER_NIGHT_RESOLVERS.get(c)
    if resolver is None: return None
    rp = actor._d if isinstance(actor, Player) else actor
    fake = AbilityProxy(actor, inst["tokens"], c,
                        override_id=override_id,
                        override_alignment=override_alignment,
                        override_char_type=override_char_type)
    g.setdefault("_woke_tonight", set()).add(rp["id"])
    ch = dict(choices or {})
    tids = ch.get("targets", [])
    if tids and "target" not in ch:
        ch["target"] = tids[0] if tids else None
        ch["t1"] = tids[0] if len(tids)>0 else None
        ch["t2"] = tids[1] if len(tids)>1 else None
        ch["t3"] = tids[2] if len(tids)>2 else None
        ch["drunk_id"] = tids[-1] if tids else None
    if pre_hook: pre_hook(actor, g)
    result = resolver(fake, ch, g)
    if post_hook: post_hook(actor, fake, g)
    return result

def resolve_cannibal_night(cannibal, choices, g):
    inst = cannibal["tokens"].get("cannibal_instance") if cannibal else None
    if not inst or not inst.get("ability_active"): return None
    if not cannibal.get("ability_active"): return None
    return dispatch_borrowed_night(cannibal, inst, choices, g)


# --- SPY / WIDOW GRIMOIRE VIEW ---

def _build_grimoire_snapshot(viewer, g, viewer_char):
    import copy
    from botc_jinxes import jinx_pair_active
    snap = copy.deepcopy(g)
    if jinx_pair_active("Magician", viewer_char, snap):
        for p in snap["players"]:
            if p.get("char_type")==DEMON or p.get("character")=="Magician":
                p["tokens"]["_grimoire_char_hidden"] = True
    return snap
def resolve_spy_grimoire_view(spy, g):
    g.setdefault("_woke_tonight", set()).add(spy["id"])
    from botc_jinxes import call_jinx_hook
    result = call_jinx_hook("spy_sees_grimoire", g)
    if result is False: return None
    return _build_grimoire_snapshot(spy, g, "Spy")

def resolve_widow_grimoire_view(widow, g):
    from botc_jinxes import call_jinx_hook
    result = call_jinx_hook("widow_sees_grimoire", g)
    if result is False: return None
    return _build_grimoire_snapshot(widow, g, "Widow")
