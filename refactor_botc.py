#!/usr/bin/env python3
"""Full refactor script for botc_logic.py - Change 4: all resolver refactors."""

with open('/home/discord-bot/botc_logic.py', 'r') as f:
    c = f.read()

def rep(old, new, label):
    global c
    assert old in c, f"NOT FOUND: {label}"
    c = c.replace(old, new, 1)
    print(f"  OK: {label}")

# ---- resolve_monk_night ----
rep(
    'def resolve_monk_night(monk,target_id,g):\n'
    '    monk["tokens"].pop("monk_target",None)\n'
    '    if g.get("night",0)<=1: return\n'
    '    if monk["ability_active"] and target_id:\n'
    '        _was=ability_inactive(monk,g)\n'
    '        check_goon_targeting(monk,target_id,g)\n'
    '        if not _was and ability_inactive(monk,g): return\n'
    '        if _was: return\n'
    '        g.setdefault("_woke_tonight",set()).add(monk["id"])\n'
    '        monk["tokens"]["monk_target"]=target_id',
    'def resolve_monk_night(monk,target_id,g):\n'
    '    monk["tokens"].pop("monk_target",None)\n'
    '    if g.get("night",0)<=1: return\n'
    '    if not begin_ability(monk, target_id, g): return\n'
    '    monk["tokens"]["monk_target"] = target_id',
    'resolve_monk_night'
)

# ---- resolve_da_night ----
rep(
    'def resolve_da_night(da,target_id,g):\n'
    '    da["tokens"].pop("da_target",None)\n'
    '    if da["ability_active"] and target_id:\n'
    '        _was=ability_inactive(da,g)\n'
    '        check_goon_targeting(da,target_id,g)\n'
    '        if not _was and ability_inactive(da,g): return\n'
    '        if _was: return\n'
    '        g.setdefault("_woke_tonight",set()).add(da["id"])\n'
    '        da["tokens"]["da_target"]=target_id',
    'def resolve_da_night(da,target_id,g):\n'
    '    da["tokens"].pop("da_target",None)\n'
    '    if not begin_ability(da, target_id, g): return\n'
    '    da["tokens"]["da_target"] = target_id',
    'resolve_da_night'
)

# ---- resolve_poisoner_night ----
rep(
    'def resolve_poisoner_night(poisoner,target_id,g):\n'
    '    old=poisoner["tokens"].pop("poisoner_last_target",None)\n'
    '    if old:\n'
    '        p=get_player(g,old)\n'
    '        if p: p["tokens"].pop("poisoned_by_poisoner",None)\n'
    '    if poisoner["ability_active"] and target_id:\n'
    '        t=get_player(g,target_id)\n'
    '        if t:\n'
    '            _was=ability_inactive(poisoner,g)\n'
    '            check_goon_targeting(poisoner,target_id,g)\n'
    '            if not _was and ability_inactive(poisoner,g): return\n'
    '            if _was: return\n'
    '            g.setdefault("_woke_tonight",set()).add(poisoner["id"])\n'
    '            try_impose_effect(poisoner,t,"poisoned_by_poisoner",True,g)\n'
    '            poisoner["tokens"]["poisoner_last_target"]=target_id',
    'def resolve_poisoner_night(poisoner,target_id,g):\n'
    '    old=poisoner["tokens"].pop("poisoner_last_target",None)\n'
    '    if old:\n'
    '        p=get_player(g,old)\n'
    '        if p: p["tokens"].pop("poisoned_by_poisoner",None)\n'
    '    if not begin_ability(poisoner, target_id, g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if t:\n'
    '        try_impose_effect(poisoner,t,"poisoned_by_poisoner",True,g)\n'
    '        poisoner["tokens"]["poisoner_last_target"]=target_id',
    'resolve_poisoner_night'
)

# ---- resolve_exorcist_night ----
rep(
    'def resolve_exorcist_night(ex,target_id,g):\n'
    '    prev=ex["tokens"].pop("exorcist_target",None)\n'
    '    if prev: ex["tokens"]["exorcist_last_target"]=prev\n'
    '    if g.get("night",0)<=1: return\n'
    '    if ex["ability_active"] and target_id:\n'
    '        if target_id==ex["tokens"].get("exorcist_last_target"): return\n'
    '        _was=ability_inactive(ex,g)\n'
    '        check_goon_targeting(ex,target_id,g)\n'
    '        if not _was and ability_inactive(ex,g): return\n'
    '        if _was: return\n'
    '        g.setdefault("_woke_tonight",set()).add(ex["id"])\n'
    '        ex["tokens"]["exorcist_target"]=target_id',
    'def resolve_exorcist_night(ex,target_id,g):\n'
    '    prev=ex["tokens"].pop("exorcist_target",None)\n'
    '    if prev: ex["tokens"]["exorcist_last_target"]=prev\n'
    '    if g.get("night",0)<=1: return\n'
    '    if not begin_ability(ex, target_id, g): return\n'
    '    if target_id==ex["tokens"].get("exorcist_last_target"): return\n'
    '    ex["tokens"]["exorcist_target"]=target_id',
    'resolve_exorcist_night'
)

# ---- resolve_witch_night ----
rep(
    'def resolve_witch_night(witch,target_id,g):\n'
    '    old=witch["tokens"].pop("witch_cursed",None)\n'
    '    if old:\n'
    '        p=get_player(g,old)\n'
    '        if p: p["tokens"].pop("witch_cursed",None)\n'
    '    if not witch["ability_active"] or ability_inactive(witch,g): return\n'
    '    if count_visible_alive(g)<=3: return\n'
    '    t=get_player(g,target_id)\n'
    '    if t and t["alive"]:\n'
    '        _was=ability_inactive(witch,g)\n'
    '        check_goon_targeting(witch,target_id,g)\n'
    '        if not _was and ability_inactive(witch,g): return\n'
    '        if _was: return\n'
    '        g.setdefault("_woke_tonight",set()).add(witch["id"])\n'
    '        if try_impose_effect(witch,t,"witch_cursed",True,g): witch["tokens"]["witch_cursed"]=target_id',
    'def resolve_witch_night(witch,target_id,g):\n'
    '    old=witch["tokens"].pop("witch_cursed",None)\n'
    '    if old:\n'
    '        p=get_player(g,old)\n'
    '        if p: p["tokens"].pop("witch_cursed",None)\n'
    '    if count_visible_alive(g)<=3: return\n'
    '    if not begin_ability(witch, target_id, g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if t and t["alive"]:\n'
    '        if try_impose_effect(witch,t,"witch_cursed",True,g): witch["tokens"]["witch_cursed"]=target_id',
    'resolve_witch_night'
)

# ---- resolve_preacher_night ----
rep(
    'def resolve_preacher_night(preacher,target_id,g):\n'
    '    if not preacher["ability_active"] or ability_inactive(preacher,g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return\n'
    '    _was=ability_inactive(preacher,g)\n'
    '    check_goon_targeting(preacher,target_id,g)\n'
    '    if not _was and ability_inactive(preacher,g): return\n'
    '    if _was: return\n'
    '    g.setdefault("_woke_tonight",set()).add(preacher["id"])\n'
    '    if (check_misregistration(t,"char_type",g))==MINION:\n'
    '        t["tokens"]["preacher_silenced"]=True\n'
    '        targets=preacher["tokens"].setdefault("preacher_targets",[])\n'
    '        if target_id not in targets: targets.append(target_id)',
    'def resolve_preacher_night(preacher,target_id,g):\n'
    '    if not begin_ability(preacher, target_id, g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return\n'
    '    if (check_misregistration(t,"char_type",g))==MINION:\n'
    '        t["tokens"]["preacher_silenced"]=True\n'
    '        targets=preacher["tokens"].setdefault("preacher_targets",[])\n'
    '        if target_id not in targets: targets.append(target_id)',
    'resolve_preacher_night'
)

# ---- resolve_godfather_night ----
rep(
    'def resolve_godfather_night(gf,target_id,g):\n'
    '    if not gf["ability_active"]: return None\n'
    '    if not g.get("_outsiders_died_last_day",0): return None\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return None\n'
    '    _was=ability_inactive(gf,g)\n'
    '    check_goon_targeting(gf,target_id,g)\n'
    '    if not _was and ability_inactive(gf,g): return None\n'
    '    if _was: return None\n'
    '    src={"type":ABILITY_KILL,"source_character":"Godfather","bypass_protection":True}\n'
    '    g.setdefault("_woke_tonight",set()).add(gf["id"])\n'
    '    if can_player_die(t,src,g)==DIES:\n'
    '        resolve_death(t,src,g); return t\n'
    '    return None',
    'def resolve_godfather_night(gf,target_id,g):\n'
    '    if not g.get("_outsiders_died_last_day",0): return None\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return None\n'
    '    if not begin_ability(gf, target_id, g): return None\n'
    '    src={"type":ABILITY_KILL,"source_character":"Godfather","bypass_protection":True}\n'
    '    if can_player_die(t,src,g)==DIES:\n'
    '        resolve_death(t,src,g); return t\n'
    '    return None',
    'resolve_godfather_night'
)

# ---- resolve_acrobat_night ----
rep(
    'def resolve_acrobat_night(acrobat,target_id,g):\n'
    '    acrobat["tokens"].pop("acrobat_target",None)\n'
    '    if g.get("night",0)<=1: return False\n'
    '    if not acrobat["ability_active"] or ability_inactive(acrobat,g): return False\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return False\n'
    '    _was=ability_inactive(acrobat,g)\n'
    '    check_goon_targeting(acrobat,target_id,g)\n'
    '    if not _was and ability_inactive(acrobat,g): return False\n'
    '    if _was: return False\n'
    '    acrobat["tokens"]["acrobat_target"]=target_id\n'
    '    g.setdefault("_woke_tonight",set()).add(acrobat["id"])\n'
    '    if is_drunk_or_poisoned(t,g):\n'
    '        src={"type":ABILITY_KILL,"source_character":"Acrobat"}\n'
    '        if can_player_die(acrobat,src,g)==DIES:\n'
    '            resolve_death(acrobat,src,g); return True\n'
    '    return False',
    'def resolve_acrobat_night(acrobat,target_id,g):\n'
    '    acrobat["tokens"].pop("acrobat_target",None)\n'
    '    if g.get("night",0)<=1: return False\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return False\n'
    '    if not begin_ability(acrobat, target_id, g): return False\n'
    '    acrobat["tokens"]["acrobat_target"]=target_id\n'
    '    if is_drunk_or_poisoned(t,g):\n'
    '        src={"type":ABILITY_KILL,"source_character":"Acrobat"}\n'
    '        if can_player_die(acrobat,src,g)==DIES:\n'
    '            resolve_death(acrobat,src,g); return True\n'
    '    return False',
    'resolve_acrobat_night'
)

# ---- resolve_lleech_night ----
rep(
    'def resolve_lleech_night(ll,target_id,g):\n'
    '    """Subsequent nights: Lleech kills a chosen player. Host always poisoned (passive) via get_poison_sources."""\n'
    '    if g.get("night",0)<=1: return\n'
    '    if is_demon_suppressed(ll,g) or not target_id: return\n'
    '    g.setdefault("_woke_tonight",set()).add(ll["id"])\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return\n'
    '    src={"type":DEMON_KILL,"source_character":"Lleech"}\n'
    '    _was=ability_inactive(ll,g)\n'
    '    check_goon_targeting(ll,target_id,g)\n'
    '    if not _was and ability_inactive(ll,g): return\n'
    '    if _was: return\n'
    '    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)',
    'def resolve_lleech_night(ll,target_id,g):\n'
    '    """Subsequent nights: Lleech kills a chosen player. Host always poisoned (passive) via get_poison_sources."""\n'
    '    if g.get("night",0)<=1: return\n'
    '    if is_demon_suppressed(ll,g) or not target_id: return\n'
    '    if not begin_ability(ll, target_id, g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return\n'
    '    src={"type":DEMON_KILL,"source_character":"Lleech"}\n'
    '    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)',
    'resolve_lleech_night'
)

# ---- resolve_slayer_claim ----
rep(
    'def resolve_slayer_claim(slayer,target_id,g):\n'
    '    if slayer["tokens"].get("slayer_used"): return False\n'
    '    if not slayer["ability_active"]: return False\n'
    '    slayer["tokens"]["slayer_used"]=True\n'
    '    if ability_inactive(slayer,g): return False\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return False\n'
    '    if check_misregistration(t,"char_type",g)==DEMON:\n'
    '        src={"type":ABILITY_KILL,"source_character":"Slayer"}\n'
    '        if can_player_die(t,src,g)==DIES:\n'
    '            resolve_death(t,src,g); return True\n'
    '    return False',
    'def resolve_slayer_claim(slayer,target_id,g):\n'
    '    if not begin_ability(slayer, target_id, g, used_token="slayer_used"): return False\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return False\n'
    '    if check_misregistration(t,"char_type",g)==DEMON:\n'
    '        src={"type":ABILITY_KILL,"source_character":"Slayer"}\n'
    '        if can_player_die(t,src,g)==DIES:\n'
    '            resolve_death(t,src,g); return True\n'
    '    return False',
    'resolve_slayer_claim'
)

# ---- resolve_widow_night ----
rep(
    'def resolve_widow_night(widow,target_id,g):\n'
    '    if widow["tokens"].get("widow_used"): return\n'
    '    if not widow["ability_active"]: return\n'
    '    widow["tokens"]["widow_used"]=True\n'
    '    g.setdefault("_woke_tonight",set()).add(widow["id"])\n'
    '    if ability_inactive(widow,g): return\n'
    '    apply_widow_poison(target_id,g)\n'
    '    g["_widow_knows_pending"]=True',
    'def resolve_widow_night(widow,target_id,g):\n'
    '    if not begin_ability(widow, target_id, g, used_token="widow_used"): return\n'
    '    apply_widow_poison(target_id,g)\n'
    '    g["_widow_knows_pending"]=True',
    'resolve_widow_night'
)

# ---- resolve_butler_night ----
rep(
    "def resolve_butler_night(butler,master_id,g):\n"
    "    butler['tokens'].pop('butler_master',None)\n"
    "    if not butler['ability_active'] or ability_inactive(butler,g): return\n"
    "    if master_id and master_id!=butler['id']:\n"
    "        _was=ability_inactive(butler,g)\n"
    "        check_goon_targeting(butler,master_id,g)\n"
    "        if not _was and ability_inactive(butler,g): return\n"
    "        if _was: return\n"
    "        g.setdefault('_woke_tonight',set()).add(butler['id'])\n"
    "        butler['tokens']['butler_master']=master_id",
    "def resolve_butler_night(butler,master_id,g):\n"
    "    butler['tokens'].pop('butler_master',None)\n"
    "    if not master_id or master_id==butler['id']: return\n"
    "    if not begin_ability(butler, master_id, g): return\n"
    "    butler['tokens']['butler_master']=master_id",
    'resolve_butler_night'
)

# ---- resolve_bureaucrat_night ----
rep(
    "def resolve_bureaucrat_night(bur,target_id,g):\n"
    "    bur['tokens'].pop('bureaucrat_target',None)\n"
    "    if not bur['ability_active'] or ability_inactive(bur,g): return\n"
    "    t=get_player(g,target_id)\n"
    "    if t and t['alive']:\n"
    "        _was=ability_inactive(bur,g)\n"
    "        check_goon_targeting(bur,target_id,g)\n"
    "        if not _was and ability_inactive(bur,g): return\n"
    "        if _was: return\n"
    "        g.setdefault('_woke_tonight',set()).add(bur['id'])\n"
    "        bur['tokens']['bureaucrat_target']=target_id",
    "def resolve_bureaucrat_night(bur,target_id,g):\n"
    "    bur['tokens'].pop('bureaucrat_target',None)\n"
    "    if not begin_ability(bur, target_id, g): return\n"
    "    t=get_player(g,target_id)\n"
    "    if t and t['alive']:\n"
    "        bur['tokens']['bureaucrat_target']=target_id",
    'resolve_bureaucrat_night'
)

# ---- resolve_thief_night ----
rep(
    "def resolve_thief_night(thief,target_id,g):\n"
    "    thief['tokens'].pop('thief_target',None)\n"
    "    if not thief['ability_active'] or ability_inactive(thief,g): return\n"
    "    t=get_player(g,target_id)\n"
    "    if t and t['alive']:\n"
    "        _was=ability_inactive(thief,g)\n"
    "        check_goon_targeting(thief,target_id,g)\n"
    "        if not _was and ability_inactive(thief,g): return\n"
    "        if _was: return\n"
    "        g.setdefault('_woke_tonight',set()).add(thief['id'])\n"
    "        thief['tokens']['thief_target']=target_id",
    "def resolve_thief_night(thief,target_id,g):\n"
    "    thief['tokens'].pop('thief_target',None)\n"
    "    if not begin_ability(thief, target_id, g): return\n"
    "    t=get_player(g,target_id)\n"
    "    if t and t['alive']:\n"
    "        thief['tokens']['thief_target']=target_id",
    'resolve_thief_night'
)

# ---- resolve_dreamer_night ----
rep(
    "def resolve_dreamer_night(dreamer,target_id,g):\n"
    "    if not dreamer['ability_active'] or ability_inactive(dreamer,g): return None\n"
    "    t=get_player(g,target_id)\n"
    "    if not t: return None\n"
    "    g.setdefault('_woke_tonight',set()).add(dreamer['id'])\n"
    "    raw={'type':'dreamer','player_id':target_id,'true_character':t['character'],'false_character':None}\n"
    "    return resolve_information(dreamer,raw,g)",
    "def resolve_dreamer_night(dreamer,target_id,g):\n"
    "    if not begin_ability(dreamer, target_id, g): return None\n"
    "    t=get_player(g,target_id)\n"
    "    if not t: return None\n"
    "    raw={'type':'dreamer','player_id':target_id,'true_character':t['character'],'false_character':None}\n"
    "    return resolve_information(dreamer,raw,g)",
    'resolve_dreamer_night'
)

# ---- resolve_fearmonger_night ----
rep(
    "def resolve_fearmonger_night(fm,target_id,g):\n"
    "    if fm['tokens'].get('fm_used'): return\n"
    "    if not fm['ability_active']: return\n"
    "    prev=fm['tokens'].get('fm_target')\n"
    "    fm['tokens']['fm_target']=target_id\n"
    "    g.setdefault('_woke_tonight',set()).add(fm['id'])\n"
    "    if ability_inactive(fm,g): return\n"
    "    if prev and prev==target_id:\n"
    "        fm['tokens']['fm_used']=True; g['_fearmonger_execute']=target_id",
    "def resolve_fearmonger_night(fm,target_id,g):\n"
    "    prev=fm['tokens'].get('fm_target')\n"
    "    fm['tokens']['fm_target']=target_id\n"
    "    if not begin_ability(fm, target_id, g, used_token=None): return\n"
    "    if fm['tokens'].get('fm_used'): return\n"
    "    if prev and prev==target_id:\n"
    "        fm['tokens']['fm_used']=True; g['_fearmonger_execute']=target_id",
    'resolve_fearmonger_night'
)

# ---- resolve_wraith_night ----
rep(
    "def resolve_wraith_night(wraith,target_id,g):\n"
    "    if wraith['tokens'].get('wraith_used'): return\n"
    "    if not wraith['ability_active']: return\n"
    "    t=get_player(g,target_id)\n"
    "    if not t or not t['alive']: return\n"
    "    wraith['tokens']['wraith_used']=True\n"
    "    if ability_inactive(wraith,g): return\n"
    "    g.setdefault('_woke_tonight',set()).add(wraith['id'])\n"
    "    src={'type':ABILITY_KILL,'source_character':'Wraith','bypass_protection':True}\n"
    "    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)",
    "def resolve_wraith_night(wraith,target_id,g):\n"
    "    t=get_player(g,target_id)\n"
    "    if not t or not t['alive']: return\n"
    "    if not begin_ability(wraith, target_id, g, used_token='wraith_used'): return\n"
    "    src={'type':ABILITY_KILL,'source_character':'Wraith','bypass_protection':True}\n"
    "    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)",
    'resolve_wraith_night'
)

# ---- resolve_organ_grinder_night ----
rep(
    "def resolve_organ_grinder_night(og,abstain,g):\n"
    "    if not og['ability_active'] or ability_inactive(og,g): return\n"
    "    g.setdefault('_woke_tonight',set()).add(og['id'])\n"
    "    og['tokens']['drunk_tonight']=bool(abstain)",
    "def resolve_organ_grinder_night(og,abstain,g):\n"
    "    if not begin_ability(og, None, g): return\n"
    "    og['tokens']['drunk_tonight']=bool(abstain)",
    'resolve_organ_grinder_night'
)

# ---- resolve_harlot_night ----
rep(
    'def resolve_harlot_night(harlot,target_id,g):\n'
    '    """Die if chosen player woke tonight for their own ability. Call after target resolver."""\n'
    '    if not harlot["ability_active"] or ability_inactive(harlot,g): return None\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return None\n'
    '    g.setdefault("_woke_tonight",set()).add(harlot["id"])\n'
    '    info,acc=resolve_information(harlot,{"type":"harlot","player_id":target_id,"character":t["character"]},g)\n'
    '    if acc is not None and target_id in g.get("_woke_tonight",set()):\n'
    '        src={"type":ABILITY_KILL,"source_character":"Harlot"}\n'
    '        if can_player_die(harlot,src,g)==DIES: resolve_death(harlot,src,g)\n'
    '    return info,acc',
    'def resolve_harlot_night(harlot,target_id,g):\n'
    '    """Die if chosen player woke tonight for their own ability. Call after target resolver."""\n'
    '    if not begin_ability(harlot, target_id, g): return None\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return None\n'
    '    info,acc=resolve_information(harlot,{"type":"harlot","player_id":target_id,"character":t["character"]},g)\n'
    '    if acc is not None and target_id in g.get("_woke_tonight",set()):\n'
    '        src={"type":ABILITY_KILL,"source_character":"Harlot"}\n'
    '        if can_player_die(harlot,src,g)==DIES: resolve_death(harlot,src,g)\n'
    '    return info,acc',
    'resolve_harlot_night'
)

# ---- resolve_lycanthrope_night ----
rep(
    'def resolve_lycanthrope_night(lycan,target_id,g):\n'
    '    if g.get("night",0)<=1: return\n'
    '    if not lycan["ability_active"] or ability_inactive(lycan,g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return\n'
    '    g.setdefault("_woke_tonight",set()).add(lycan["id"])\n'
    '    _was=ability_inactive(lycan,g)\n'
    '    check_goon_targeting(lycan,target_id,g)\n'
    '    if not _was and ability_inactive(lycan,g): return None\n'
    '    if _was: return None\n'
    '    src={"type":ABILITY_KILL,"source_character":"Lycanthrope"}\n'
    '    if check_misregistration(t,"alignment",g)==GOOD:\n'
    '        if can_player_die(t,src,g)==DIES:\n'
    '            resolve_death(t,src,g)\n'
    '            g["_lycanthrope_killed_tonight"]=True\n'
    '            return t\n'
    '    return None',
    'def resolve_lycanthrope_night(lycan,target_id,g):\n'
    '    if g.get("night",0)<=1: return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return\n'
    '    if not begin_ability(lycan, target_id, g): return None\n'
    '    src={"type":ABILITY_KILL,"source_character":"Lycanthrope"}\n'
    '    if check_misregistration(t,"alignment",g)==GOOD:\n'
    '        if can_player_die(t,src,g)==DIES:\n'
    '            resolve_death(t,src,g)\n'
    '            g["_lycanthrope_killed_tonight"]=True\n'
    '            return t\n'
    '    return None',
    'resolve_lycanthrope_night'
)

# ---- resolve_ojo_night ----
# ojo targets character name, not player id — use None for goon check
rep(
    'def resolve_ojo_night(ojo,character_name,g):\n'
    '    if g.get("night",0)<=1 or is_demon_suppressed(ojo,g): return\n'
    '    g.setdefault("_woke_tonight",set()).add(ojo["id"])\n'
    '    src={"type":DEMON_KILL,"source_character":"Ojo"}\n'
    '    t=get_character(g,character_name)\n'
    '    if t and t["alive"]:\n'
    '        if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)\n'
    '    else:\n'
    '        g["_ojo_no_target_pending"]=True',
    'def resolve_ojo_night(ojo,character_name,g):\n'
    '    if g.get("night",0)<=1 or is_demon_suppressed(ojo,g): return\n'
    '    if not begin_ability(ojo, None, g): return\n'
    '    src={"type":DEMON_KILL,"source_character":"Ojo"}\n'
    '    t=get_character(g,character_name)\n'
    '    if t and t["alive"]:\n'
    '        if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)\n'
    '    else:\n'
    '        g["_ojo_no_target_pending"]=True',
    'resolve_ojo_night'
)

# ---- resolve_cerenovus_night ----
rep(
    'def resolve_cerenovus_night(cer,target_id,character_name,g):\n'
    '    cer["tokens"].pop("cer_target",None)\n'
    '    if not cer["ability_active"] or ability_inactive(cer,g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return\n'
    '    g.setdefault("_woke_tonight",set()).add(cer["id"])\n'
    '    _was=ability_inactive(cer,g)\n'
    '    check_goon_targeting(cer,target_id,g)\n'
    '    if not _was and ability_inactive(cer,g): return\n'
    '    if _was: return\n'
    '    cer["tokens"]["cer_target"]=target_id\n'
    '    try_impose_effect(cer,t,"cerenovus_mad_as",character_name,g)',
    'def resolve_cerenovus_night(cer,target_id,character_name,g):\n'
    '    cer["tokens"].pop("cer_target",None)\n'
    '    if not begin_ability(cer, target_id, g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t or not t["alive"]: return\n'
    '    cer["tokens"]["cer_target"]=target_id\n'
    '    try_impose_effect(cer,t,"cerenovus_mad_as",character_name,g)',
    'resolve_cerenovus_night'
)

# ---- resolve_mezepheles_night ----
rep(
    'def resolve_mezepheles_night(mez,target_id,secret_word,g):\n'
    '    mez["tokens"].pop("mez_target",None)\n'
    '    if not mez["ability_active"] or ability_inactive(mez,g): return\n'
    '    if mez["tokens"].get("mez_converted"): return\n'
    '    t=get_player(g,target_id)\n'
    '    if t and t["alive"]:\n'
    '        g.setdefault("_woke_tonight",set()).add(mez["id"])\n'
    '        mez["tokens"]["mez_target"]=target_id\n'
    '        t["tokens"]["mez_word"]=secret_word',
    'def resolve_mezepheles_night(mez,target_id,secret_word,g):\n'
    '    mez["tokens"].pop("mez_target",None)\n'
    '    if mez["tokens"].get("mez_converted"): return\n'
    '    if not begin_ability(mez, target_id, g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if t and t["alive"]:\n'
    '        mez["tokens"]["mez_target"]=target_id\n'
    '        t["tokens"]["mez_word"]=secret_word',
    'resolve_mezepheles_night'
)

# ---- resolve_innkeeper_night ----
rep(
    'def resolve_innkeeper_night(ik,target1_id,target2_id,drunk_id,g):\n'
    '    for old in ik["tokens"].pop("ik_targets",[]):\n'
    '        p=get_player(g,old)\n'
    '        if p: p["tokens"].pop("innkeeper_protected",None); p["tokens"].pop("innkeeper_drunk",None)\n'
    '    ik["tokens"]["ik_targets"]=[t for t in [target1_id,target2_id] if t]\n'
    '    if g.get("night",0)<=1: return\n'
    '    if not ik["ability_active"] or ability_inactive(ik,g): return\n'
    '    g.setdefault("_woke_tonight",set()).add(ik["id"])\n'
    '    for tid in ik["tokens"]["ik_targets"]:\n'
    '        p=get_player(g,tid)\n'
    '        if p:\n'
    '            _was=ability_inactive(ik,g)\n'
    '            check_goon_targeting(ik,tid,g)\n'
    '            if not _was and ability_inactive(ik,g): break\n'
    '            if _was: break\n'
    '            p["tokens"]["innkeeper_protected"]=True\n'
    '    if drunk_id:\n'
    '        p=get_player(g,drunk_id)\n'
    '        ik2=get_character(g,"Innkeeper")\n'
    '        if p and ik2: try_impose_effect(ik2,p,"innkeeper_drunk",True,g)',
    'def resolve_innkeeper_night(ik,target1_id,target2_id,drunk_id,g):\n'
    '    for old in ik["tokens"].pop("ik_targets",[]):\n'
    '        p=get_player(g,old)\n'
    '        if p: p["tokens"].pop("innkeeper_protected",None); p["tokens"].pop("innkeeper_drunk",None)\n'
    '    ik["tokens"]["ik_targets"]=[t for t in [target1_id,target2_id] if t]\n'
    '    if g.get("night",0)<=1: return\n'
    '    if not begin_ability_multi(ik, [target1_id, target2_id], g): return\n'
    '    for tid in ik["tokens"]["ik_targets"]:\n'
    '        p=get_player(g,tid)\n'
    '        if p: p["tokens"]["innkeeper_protected"]=True\n'
    '    if drunk_id:\n'
    '        p=get_player(g,drunk_id)\n'
    '        ik2=get_character(g,"Innkeeper")\n'
    '        if p and ik2: try_impose_effect(ik2,p,"innkeeper_drunk",True,g)',
    'resolve_innkeeper_night'
)

# ---- resolve_harpy_night ----
rep(
    'def resolve_harpy_night(harpy,p1_id,p2_id,g):\n'
    '    harpy["tokens"].pop("harpy_pair",None)\n'
    '    if not harpy["ability_active"] or ability_inactive(harpy,g): return\n'
    '    p1=get_player(g,p1_id); p2=get_player(g,p2_id)\n'
    '    if p1 and p2 and p1["alive"] and p2["alive"]:\n'
    '        g.setdefault("_woke_tonight",set()).add(harpy["id"])\n'
    '        harpy["tokens"]["harpy_pair"]=(p1_id,p2_id)',
    'def resolve_harpy_night(harpy,p1_id,p2_id,g):\n'
    '    harpy["tokens"].pop("harpy_pair",None)\n'
    '    if not begin_ability_multi(harpy, [p1_id, p2_id], g): return\n'
    '    p1=get_player(g,p1_id); p2=get_player(g,p2_id)\n'
    '    if p1 and p2 and p1["alive"] and p2["alive"]:\n'
    '        harpy["tokens"]["harpy_pair"]=(p1_id,p2_id)',
    'resolve_harpy_night'
)

# ---- resolve_engineer_night ----
rep(
    'def resolve_engineer_night(eng,assignments,g):\n'
    '    """Once per game: reassign evil characters in play."""\n'
    '    if not eng["ability_active"]: return False\n'
    '    if eng["tokens"].get("engineer_used"): return False\n'
    '    eng["tokens"]["engineer_used"]=True\n'
    '    if ability_inactive(eng,g): return False\n'
    '    g.setdefault("_woke_tonight",set()).add(eng["id"])\n'
    '    keep={"ghost_vote_available","nominations_today","nominated_today"}\n'
    '    for a in (assignments or []):\n'
    '        t=get_player(g,a["player_id"])\n'
    '        if not t: continue\n'
    '        t["tokens"]={k:v for k,v in t["tokens"].items() if k in keep}\n'
    '        t["character"]=a["character"]; t["char_type"]=a["char_type"]\n'
    '        t["alignment"]=EVIL; t["ability_active"]=True\n'
    '    return True',
    'def resolve_engineer_night(eng,assignments,g):\n'
    '    """Once per game: reassign evil characters in play."""\n'
    '    if not begin_ability(eng, None, g, used_token="engineer_used"): return False\n'
    '    keep={"ghost_vote_available","nominations_today","nominated_today"}\n'
    '    for a in (assignments or []):\n'
    '        t=get_player(g,a["player_id"])\n'
    '        if not t: continue\n'
    '        t["tokens"]={k:v for k,v in t["tokens"].items() if k in keep}\n'
    '        t["character"]=a["character"]; t["char_type"]=a["char_type"]\n'
    '        t["alignment"]=EVIL; t["ability_active"]=True\n'
    '    return True',
    'resolve_engineer_night'
)

# ---- resolve_vigormortis_night ----
rep(
    'def resolve_vigormortis_night(vm,target_id,g):\n'
    '    """Each night*: kill a player. If a Minion, they keep their ability; ST then calls apply_vigormortis_poison."""\n'
    '    if g.get("night",0)<=1 or is_demon_suppressed(vm,g) or not target_id: return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return\n'
    '    g.setdefault("_woke_tonight",set()).add(vm["id"])\n'
    '    src={"type":DEMON_KILL,"source_character":"Vigormortis"}\n'
    '    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)',
    'def resolve_vigormortis_night(vm,target_id,g):\n'
    '    """Each night*: kill a player. If a Minion, they keep their ability; ST then calls apply_vigormortis_poison."""\n'
    '    if g.get("night",0)<=1 or is_demon_suppressed(vm,g) or not target_id: return\n'
    '    if not begin_ability(vm, target_id, g): return\n'
    '    t=get_player(g,target_id)\n'
    '    if not t: return\n'
    '    src={"type":DEMON_KILL,"source_character":"Vigormortis"}\n'
    '    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)',
    'resolve_vigormortis_night'
)

# ---- resolve_gossip_night ----
rep(
    'def resolve_gossip_night(gossip,target1_id,target2_id,statement_true,victim_id,g):\n'
    '    """ST provides victim_id; dies if both targets alive and statement was true."""\n'
    '    if g.get("night",0)<=1: return\n'
    '    if not gossip["ability_active"] or ability_inactive(gossip,g): return\n'
    '    if not statement_true: return\n'
    '    t1=get_player(g,target1_id); t2=get_player(g,target2_id)\n'
    '    if not (t1 and t1["alive"] and t2 and t2["alive"]): return\n'
    '    victim=get_player(g,victim_id)\n'
    '    if not victim or not victim["alive"]: return\n'
    '    g.setdefault("_woke_tonight",set()).add(gossip["id"])\n'
    '    src={"type":ABILITY_KILL,"source_character":"Gossip"}\n'
    '    if can_player_die(victim,src,g)==DIES: resolve_death(victim,src,g)',
    'def resolve_gossip_night(gossip,target1_id,target2_id,statement_true,victim_id,g):\n'
    '    """ST provides victim_id; dies if both targets alive and statement was true."""\n'
    '    if g.get("night",0)<=1: return\n'
    '    if not statement_true: return\n'
    '    if not begin_ability_multi(gossip, [target1_id, target2_id], g): return\n'
    '    t1=get_player(g,target1_id); t2=get_player(g,target2_id)\n'
    '    if not (t1 and t1["alive"] and t2 and t2["alive"]): return\n'
    '    victim=get_player(g,victim_id)\n'
    '    if not victim or not victim["alive"]: return\n'
    '    src={"type":ABILITY_KILL,"source_character":"Gossip"}\n'
    '    if can_player_die(victim,src,g)==DIES: resolve_death(victim,src,g)',
    'resolve_gossip_night'
)

# ---- resolve_golem_nominate ----
rep(
    'def resolve_golem_nominate(golem_id,nee_id,g):\n'
    '    golem=get_player(g,golem_id)\n'
    '    if not golem or golem["tokens"].get("golem_used"): return False\n'
    '    golem["tokens"]["golem_used"]=True  # consumed even when drunk\n'
    '    if ability_inactive(golem,g): return False\n'
    '    nee=get_player(g,nee_id)\n'
    '    # Returns True if nominee is a non-demon (game runner should issue ability kill).\n'
    '    # Execution/death are independent — no protection from execution granted.\n'
    '    return check_misregistration(nee,"char_type",g)!=DEMON if nee else False',
    'def resolve_golem_nominate(golem_id,nee_id,g):\n'
    '    golem=get_player(g,golem_id)\n'
    '    if not golem: return False\n'
    '    if not begin_ability(golem, nee_id, g, used_token="golem_used"): return False\n'
    '    nee=get_player(g,nee_id)\n'
    '    # Returns True if nominee is a non-demon (game runner should issue ability kill).\n'
    '    # Execution/death are independent — no protection from execution granted.\n'
    '    return check_misregistration(nee,"char_type",g)!=DEMON if nee else False',
    'resolve_golem_nominate'
)

with open('/home/discord-bot/botc_logic.py', 'w') as f:
    f.write(c)
print("ALL CHANGES DONE")
