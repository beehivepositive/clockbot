import sys

path = "/home/discord-bot/botc_logic.py"
with open(path, "r") as f:
    src = f.read()

r = []

r.append(("1_monk",
"""    if monk["ability_active"] and not ability_inactive(monk,g) and target_id:
        check_goon_targeting(monk,target_id,g)
        if is_drunk_or_poisoned(monk,g): return
        g.setdefault("_woke_tonight",set()).add(monk["id"])
        monk["tokens"]["monk_target"]=target_id""",
"""    if monk["ability_active"] and target_id:
        _was=ability_inactive(monk,g)
        check_goon_targeting(monk,target_id,g)
        if not _was and ability_inactive(monk,g): return
        if _was: return
        g.setdefault("_woke_tonight",set()).add(monk["id"])
        monk["tokens"]["monk_target"]=target_id"""))

r.append(("2_poisoner",
"""    if poisoner["ability_active"] and not ability_inactive(poisoner,g) and target_id:
        t=get_player(g,target_id)
        if t:
            check_goon_targeting(poisoner,target_id,g)
            if is_drunk_or_poisoned(poisoner,g): return
            g.setdefault("_woke_tonight",set()).add(poisoner["id"])
            try_impose_effect(poisoner,t,"poisoned_by_poisoner",True,g)
            poisoner["tokens"]["poisoner_last_target"]=target_id""",
"""    if poisoner["ability_active"] and target_id:
        t=get_player(g,target_id)
        if t:
            _was=ability_inactive(poisoner,g)
            check_goon_targeting(poisoner,target_id,g)
            if not _was and ability_inactive(poisoner,g): return
            if _was: return
            g.setdefault("_woke_tonight",set()).add(poisoner["id"])
            try_impose_effect(poisoner,t,"poisoned_by_poisoner",True,g)
            poisoner["tokens"]["poisoner_last_target"]=target_id"""))

r.append(("3_da",
"""    if da["ability_active"] and not ability_inactive(da,g) and target_id:
        check_goon_targeting(da,target_id,g)
        if is_drunk_or_poisoned(da,g): return
        g.setdefault("_woke_tonight",set()).add(da["id"])
        da["tokens"]["da_target"]=target_id""",
"""    if da["ability_active"] and target_id:
        _was=ability_inactive(da,g)
        check_goon_targeting(da,target_id,g)
        if not _was and ability_inactive(da,g): return
        if _was: return
        g.setdefault("_woke_tonight",set()).add(da["id"])
        da["tokens"]["da_target"]=target_id"""))

r.append(("4_exorcist",
"""    if ex["ability_active"] and not ability_inactive(ex,g) and target_id:
        if target_id==ex["tokens"].get("exorcist_last_target"): return
        check_goon_targeting(ex,target_id,g)
        if is_drunk_or_poisoned(ex,g): return
        g.setdefault("_woke_tonight",set()).add(ex["id"])
        ex["tokens"]["exorcist_target"]=target_id""",
"""    if ex["ability_active"] and target_id:
        if target_id==ex["tokens"].get("exorcist_last_target"): return
        _was=ability_inactive(ex,g)
        check_goon_targeting(ex,target_id,g)
        if not _was and ability_inactive(ex,g): return
        if _was: return
        g.setdefault("_woke_tonight",set()).add(ex["id"])
        ex["tokens"]["exorcist_target"]=target_id"""))

r.append(("5a_godfather_top",
"""def resolve_godfather_night(gf,target_id,g):
    if not gf["ability_active"] or ability_inactive(gf,g): return None
    if not g.get("_outsiders_died_last_day",0): return None""",
"""def resolve_godfather_night(gf,target_id,g):
    if not gf["ability_active"]: return None
    if not g.get("_outsiders_died_last_day",0): return None"""))

r.append(("5b_godfather_body",
"""    src={"type":ABILITY_KILL,"source_character":"Godfather","bypass_protection":True}
    check_goon_targeting(gf,target_id,g)
    if is_drunk_or_poisoned(gf,g): return None
    g.setdefault("_woke_tonight",set()).add(gf["id"])""",
"""    _was=ability_inactive(gf,g)
    check_goon_targeting(gf,target_id,g)
    if not _was and ability_inactive(gf,g): return None
    if _was: return None
    src={"type":ABILITY_KILL,"source_character":"Godfather","bypass_protection":True}
    g.setdefault("_woke_tonight",set()).add(gf["id"])"""))

r.append(("6_witch",
"""    if t and t["alive"]:
        check_goon_targeting(witch,target_id,g)
        if is_drunk_or_poisoned(witch,g): return
        g.setdefault("_woke_tonight",set()).add(witch["id"])
        if try_impose_effect(witch,t,"witch_cursed",True,g): witch["tokens"]["witch_cursed"]=target_id""",
"""    if t and t["alive"]:
        _was=ability_inactive(witch,g)
        check_goon_targeting(witch,target_id,g)
        if not _was and ability_inactive(witch,g): return
        if _was: return
        g.setdefault("_woke_tonight",set()).add(witch["id"])
        if try_impose_effect(witch,t,"witch_cursed",True,g): witch["tokens"]["witch_cursed"]=target_id"""))

r.append(("7_preacher",
"""    g.setdefault("_woke_tonight",set()).add(preacher["id"])
    check_goon_targeting(preacher,target_id,g)
    if is_drunk_or_poisoned(preacher,g): return
    if (check_misregistration(t,"char_type",g))==MINION:""",
"""    _was=ability_inactive(preacher,g)
    check_goon_targeting(preacher,target_id,g)
    if not _was and ability_inactive(preacher,g): return
    if _was: return
    g.setdefault("_woke_tonight",set()).add(preacher["id"])
    if (check_misregistration(t,"char_type",g))==MINION:"""))

r.append(("8_innkeeper",
"""        if p:
            check_goon_targeting(ik,tid,g)
            if is_drunk_or_poisoned(ik,g): break
            p["tokens"]["innkeeper_protected"]=True""",
"""        if p:
            _was=ability_inactive(ik,g)
            check_goon_targeting(ik,tid,g)
            if not _was and ability_inactive(ik,g): break
            if _was: break
            p["tokens"]["innkeeper_protected"]=True"""))

r.append(("9_acrobat",
"""    check_goon_targeting(acrobat,target_id,g)
    if is_drunk_or_poisoned(acrobat,g): return False
    acrobat["tokens"]["acrobat_target"]=target_id
    g.setdefault("_woke_tonight",set()).add(acrobat["id"])
    if is_drunk_or_poisoned(t,g):""",
"""    _was=ability_inactive(acrobat,g)
    check_goon_targeting(acrobat,target_id,g)
    if not _was and ability_inactive(acrobat,g): return False
    if _was: return False
    acrobat["tokens"]["acrobat_target"]=target_id
    g.setdefault("_woke_tonight",set()).add(acrobat["id"])
    if is_drunk_or_poisoned(t,g):"""))

r.append(("10_lleech",
"""    check_goon_targeting(ll,target_id,g)
    if is_drunk_or_poisoned(ll,g): return
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)""",
"""    _was=ability_inactive(ll,g)
    check_goon_targeting(ll,target_id,g)
    if not _was and ability_inactive(ll,g): return
    if _was: return
    if can_player_die(t,src,g)==DIES: resolve_death(t,src,g)"""))

r.append(("11_lil_monsta",
"""    check_goon_targeting(holder,target_id,g)
    if is_drunk_or_poisoned(holder,g): return
    src={"type":DEMON_KILL,"source_character":"Lil Monsta"}""",
"""    _was=ability_inactive(holder,g)
    check_goon_targeting(holder,target_id,g)
    if not _was and ability_inactive(holder,g): return
    if _was: return
    src={"type":DEMON_KILL,"source_character":"Lil Monsta"}"""))

r.append(("12_legion",
"""    check_goon_targeting(killer,target_id,g)
    if is_drunk_or_poisoned(killer,g): return
    src={"type":DEMON_KILL,"source_character":"Legion"}""",
"""    _was=ability_inactive(killer,g)
    check_goon_targeting(killer,target_id,g)
    if not _was and ability_inactive(killer,g): return
    if _was: return
    src={"type":DEMON_KILL,"source_character":"Legion"}"""))

r.append(("13_cerenovus",
"""    check_goon_targeting(cer,target_id,g)
    if is_drunk_or_poisoned(cer,g): return
    cer["tokens"]["cer_target"]=target_id
    try_impose_effect(cer,t,"cerenovus_mad_as",character_name,g)""",
"""    _was=ability_inactive(cer,g)
    check_goon_targeting(cer,target_id,g)
    if not _was and ability_inactive(cer,g): return
    if _was: return
    cer["tokens"]["cer_target"]=target_id
    try_impose_effect(cer,t,"cerenovus_mad_as",character_name,g)"""))

r.append(("14_lycanthrope",
"""    check_goon_targeting(lycan,target_id,g)
    if is_drunk_or_poisoned(lycan,g): return None
    src={"type":ABILITY_KILL,"source_character":"Lycanthrope"}""",
"""    _was=ability_inactive(lycan,g)
    check_goon_targeting(lycan,target_id,g)
    if not _was and ability_inactive(lycan,g): return None
    if _was: return None
    src={"type":ABILITY_KILL,"source_character":"Lycanthrope"}"""))

r.append(("15_butler",
"""        check_goon_targeting(butler,master_id,g)
        if is_drunk_or_poisoned(butler,g): return
        g.setdefault('_woke_tonight',set()).add(butler['id'])
        butler['tokens']['butler_master']=master_id""",
"""        _was=ability_inactive(butler,g)
        check_goon_targeting(butler,master_id,g)
        if not _was and ability_inactive(butler,g): return
        if _was: return
        g.setdefault('_woke_tonight',set()).add(butler['id'])
        butler['tokens']['butler_master']=master_id"""))

r.append(("16_bureaucrat",
"""        check_goon_targeting(bur,target_id,g)
        if is_drunk_or_poisoned(bur,g): return
        g.setdefault('_woke_tonight',set()).add(bur['id'])
        bur['tokens']['bureaucrat_target']=target_id""",
"""        _was=ability_inactive(bur,g)
        check_goon_targeting(bur,target_id,g)
        if not _was and ability_inactive(bur,g): return
        if _was: return
        g.setdefault('_woke_tonight',set()).add(bur['id'])
        bur['tokens']['bureaucrat_target']=target_id"""))

r.append(("17_thief",
"""        check_goon_targeting(thief,target_id,g)
        if is_drunk_or_poisoned(thief,g): return
        g.setdefault('_woke_tonight',set()).add(thief['id'])
        thief['tokens']['thief_target']=target_id""",
"""        _was=ability_inactive(thief,g)
        check_goon_targeting(thief,target_id,g)
        if not _was and ability_inactive(thief,g): return
        if _was: return
        g.setdefault('_woke_tonight',set()).add(thief['id'])
        thief['tokens']['thief_target']=target_id"""))

r.append(("18_nightwatchman",
"""def resolve_nightwatchman_night(nw,target_id,g):
    if nw['tokens'].get('nw_used'): return
    if not nw['ability_active'] or ability_inactive(nw,g): return
    t=get_player(g,target_id)
    if not t or not t['alive']: return
    nw['tokens']['nw_used']=True
    g.setdefault('_woke_tonight',set()).add(nw['id'])
    t['tokens']['nightwatchman_learned']=nw['id']""",
"""def resolve_nightwatchman_night(nw,target_id,g):
    if nw['tokens'].get('nw_used'): return
    if not nw['ability_active']: return
    t=get_player(g,target_id)
    if not t or not t['alive']: return
    _was=ability_inactive(nw,g)
    check_goon_targeting(nw,target_id,g)
    if not _was and ability_inactive(nw,g): return
    nw['tokens']['nw_used']=True
    g.setdefault('_woke_tonight',set()).add(nw['id'])
    t['tokens']['nightwatchman_learned']=nw['id']"""))

r.append(("19_pukka",
"""        t=get_player(g,new_target_id)
        if t:
            check_goon_targeting(pukka,new_target_id,g)
            if not is_drunk_or_poisoned(pukka,g):
                pk=get_character(g,"Pukka")
                if pk: try_impose_effect(pk,t,"pukka_poisoned",True,g)""",
"""        t=get_player(g,new_target_id)
        if t:
            _was=ability_inactive(pukka,g)
            check_goon_targeting(pukka,new_target_id,g)
            if not _was and not ability_inactive(pukka,g):
                pk=get_character(g,"Pukka")
                if pk: try_impose_effect(pk,t,"pukka_poisoned",True,g)"""))

r.append(("20_shabaloth",
"""        for t in tgts:
            check_goon_targeting(shabaloth,t["id"],g)
            if is_drunk_or_poisoned(shabaloth,g): break
            src={"type":DEMON_KILL,"source_character":"Shabaloth"}""",
"""        for t in tgts:
            _was=ability_inactive(shabaloth,g)
            check_goon_targeting(shabaloth,t["id"],g)
            if not _was and ability_inactive(shabaloth,g): break
            if _was: break
            src={"type":DEMON_KILL,"source_character":"Shabaloth"}"""))

r.append(("21_po",
"""        t=get_player(g,tid)
        if t and t["alive"]:
            check_goon_targeting(po,t["id"],g)
            if is_drunk_or_poisoned(po,g): break
            src={"type":DEMON_KILL,"source_character":"Po"}""",
"""        t=get_player(g,tid)
        if t and t["alive"]:
            _was=ability_inactive(po,g)
            check_goon_targeting(po,t["id"],g)
            if not _was and ability_inactive(po,g): break
            if _was: break
            src={"type":DEMON_KILL,"source_character":"Po"}"""))

# Assert all old strings exist
failed = False
for (name, old, new) in r:
    if old not in src:
        print(f"ASSERTION FAILED: [{name}]")
        failed = True

if failed:
    sys.exit(1)

for (name, old, new) in r:
    src = src.replace(old, new, 1)
    print(f"Applied: {name}")

with open(path, "w") as f:
    f.write(src)

print("All replacements applied successfully.")
