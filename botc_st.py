"""
botc_st.py
"""
import json, re, asyncio, datetime, pytz, traceback, discord
from botc_runner import get_game, set_game, format_game_state
import botc_logic as BL
from game_state import get_game_state, set_game_state, get_game_key, find_dest, is_excluded

CST = pytz.timezone('America/Chicago')
COMMON_NAMES_PATH = '/home/discord-bot/common_names.json'

CHAR_ACTIONS = {
    'Washerwoman': (True, False, None),
    'Librarian': (True, False, None),
    'Investigator': (True, False, None),
    'Chef': (True, False, None),
    'Empath': (True, False, None),
    'Fortune Teller': (True, True, 'Pick **2 players** to check (reply with two names):'),
    'Undertaker': (False, False, None),
    'Monk': (False, True, 'Pick **1 player** to protect tonight:'),
    'Ravenkeeper': (False, True, 'You died tonight - pick **1 player** to learn their character:'),
    'Virgin': (True, False, None),
    'Slayer': (True, False, None),
    'Soldier': (True, False, None),
    'Mayor': (True, False, None),
    'Butler': (True, True, 'Pick your **master** for tonight:'),
    'Drunk': (True, False, None),
    'Recluse': (True, False, None),
    'Saint': (True, False, None),
    'Poisoner': (True, True, 'Pick 1 player to poison tonight:'),
    'Spy': (True, False, None),
    'Widow': (True, True, 'Look at the Grimoire, then pick 1 player to poison (once/game, or `pass`):'),
    'Scarlet Woman': (True, False, None),
    'Baron': (True, False, None),
    'Imp': (False, True, 'Pick 1 player to kill tonight (or yourself to pass the Imp):'),
    'Grandmother': (True, True, 'Night 1 only - pick your grandchild:'),
    'Sailor': (True, True, 'Pick 1 alive player to drink with tonight:'),
    'Chambermaid': (True, True, 'Pick 2 players to observe:'),
    'Exorcist': (False, True, 'Pick 1 player for Demon not to wake:'),
    'Innkeeper': (False, True, 'Pick 2 players to protect:'),
    'Gambler': (False, True, 'Pick 1 player and 1 character to gamble on:'),
    'Gossip': (True, False, None),
    'Courtier': (True, True, 'Name a character to drunk (once/game) or pass:'),
    'Professor': (False, True, 'Pick 1 dead Townsfolk to resurrect (once/game) or pass:'),
    'Mathematician': (True, False, None),
    'Fool': (True, False, None),
    'Pacifist': (True, False, None),
    'Town Crier': (False, False, None),
    'Oracle': (False, False, None),
    'Savant': (True, False, None),
    'Seamstress': (True, True, 'Pick 2 players to check alignment (once/game) or pass:'),
    'Flowergirl': (False, False, None),
    'Juggler': (False, False, None),  # Juggles publicly day 1; result auto-DM in end_night
    'Acrobat': (False, True, 'Pick 1 alive neighbor to observe:'),
    'Balloonist': (True, False, None),
    'Dreamer': (True, False, None),
    'Snake Charmer': (True, True, 'Pick 1 player to attempt snake charming:'),
    'Preacher': (True, True, 'Pick 1 player to preach to tonight:'),
    'Godfather': (False, True, 'Outsider died - kill 1 or pass:'),
    'Witch': (True, True, 'Pick 1 player to curse:'),
    'Assassin': (False, True, 'Assassinate 1 (once/game) or pass:'),
    "Devil's Advocate": (True, True, 'Pick 1 alive player to protect from execution:'),
    'Po': (False, True, 'Kill 1 or pass to charge up:'),
    'Pukka': (True, True, 'Pick 1 player to begin poisoning:'),
    'Shabaloth': (False, True, 'Pick 2 players to kill:'),
    'Zombuul': (False, True, 'Kill 1 (nobody died today) or pass:'),
    'Clockmaker': (True, False, None),
    'Cult Leader': (True, True, 'Pick 1 alive neighbour whose alignment Cult Leader copies (or pass):'),
    'Shugenja': (True, False, None),
    'Philosopher': (True, True, 'Pick 1 Townsfolk to gain their ability:'),
    'Artist': (True, True, 'Ask the ST 1 yes/no question:'),
    'Sage': (False, False, None),
    'Mutant': (True, False, None),
    'Sweetheart': (True, False, None),
    'Cerenovus': (True, True, 'Pick player+character to act mad about:'),
    'Pit-Hag': (True, True, 'Pick player+character to transform into:'),
    'Evil Twin': (True, False, None),
    'Summoner': (True, True, 'Night 3 - pick player and Demon type:'),
    'Harpy': (True, True, 'Pick 2 to stay mad (once/game or pass):'),
    'Mezepheles': (True, True, 'Pick 1 player to whisper to:'),
    'No Dashii': (False, True, 'Pick 1 to kill tonight:'),
    'Vortox': (False, True, 'Pick 1 to kill tonight:'),
    'Vigormortis': (False, True, 'Pick 1 to kill:'),
    'Ojo': (False, True, 'Pick 1 character to kill:'),
    'Lycanthrope': (False, True, 'Pick 1 alive to kill:'),
    'Lleech': (True, True, 'Night 1: host. Later: pick 1 to kill:'),
    'Fang Gu': (False, True, 'Pick 1 to kill:'),
    'Al-Hadikhia': (False, True, 'Pick **3 players** (or `pass` to skip tonight):'),
    'Legion': (False, True, 'Pick 1 to kill:'),
    "Lil' Monsta": (True, True, 'Minions: who holds token+kills. Reply holder:Alice target:Bob:'),
    'Xaan': (True, False, None),
    'Boffin': (True, False, None),
    'Kazali': (True, True, 'Pick players to become Minions (e.g. Alice Poisoner, Bob Spy):'),
    'Lord of Typhon': (True, True, 'Pick 1 to kill tonight:'),
}

def load_common_names():
    try: return json.load(open(COMMON_NAMES_PATH))
    except Exception: return {}

def get_player_discord_id(player):
    return player.get('discord_id') or player.get('id')

def find_player_by_text(text, game):
    for mid in re.findall(r'<@!?(\d+)>', text):
        p = BL.get_player(game, mid)
        if p: return p
    players = game.get('players', [])
    matches = sorted([p for p in players if p.get('name','').lower() in text.lower()],
                     key=lambda p: len(p.get('name','')), reverse=True)
    return matches[0] if matches else None

def find_players_by_text(text, game, count=2):
    found, seen = [], set()
    for mid in re.findall(r'<@!?(\d+)>', text):
        p = BL.get_player(game, mid)
        if p and p['id'] not in seen:
            found.append(p); seen.add(p['id'])
    if len(found) < count:
        players = sorted(game.get('players',[]), key=lambda p: len(p.get('name','')), reverse=True)
        for p in players:
            if p['id'] in seen: continue
            if p.get('name','').lower() in text.lower():
                found.append(p); seen.add(p['id'])
    return found[:count]

def find_character_in_text(text):
    text_lower = text.lower()
    for char in sorted(CHAR_ACTIONS.keys(), key=len, reverse=True):
        if char.lower() in text_lower: return char
    return None

async def dm_player(bot, player, msg):
    did = get_player_discord_id(player)
    if not did: return False
    try:
        user = await bot.fetch_user(int(did))
        dm = await user.create_dm()
        await dm.send(msg)
        return True
    except Exception as e:
        print(f"DM failed {player.get('name')}: {e}")
        return False

async def dm_player_grimoire(bot, player, snap, game_key):
    import discord
    did = get_player_discord_id(player)
    if not did: return False
    try:
        from botc_render import render_grimoire, build_grimoire_reminders
        build_grimoire_reminders(snap)
        path = '/tmp/grimoire_{}_{}.png'.format(game_key, player['id'])
        render_grimoire(snap, path)
        user = await bot.fetch_user(int(did))
        dm_ch = await user.create_dm()
        await dm_ch.send(content='Grimoire:', file=discord.File(path, 'grimoire.png'))
        return True
    except Exception as e:
        print('grimoire DM err: ' + str(e))
        return False

def get_guild(bot):
    return bot.guilds[0] if bot.guilds else None

def get_game_channels(guild, game_key):
    all_ch = list(guild.text_channels)
    game_ch = [c for c in all_ch if get_game_key(c.name)==game_key]
    logs = find_dest(game_ch)
    chat = [c for c in game_ch if not is_excluded(c.name) and c!=logs]
    return chat, logs

def _format_borrowed_result(char, result, g):
    if not result or not isinstance(result, dict): return None
    t=result.get("type","")
    sfx=" [may be false]" if result.get("accurate") is None else ""
    if t=="empath":
        n=result.get("result",0)
        return "Empath: "+str(n)+" evil."+sfx
    if t=="fortune_teller":
        return ("FT: Yes" if result.get("result") else "FT: No")+sfx
    if t=="seamstress":
        return ("same" if result.get("same_alignment") else "different")+sfx
    if t in ("town_crier","flowergirl"):
        return (char+("Yes" if result.get("result") else "No"))+sfx
    if t=="oracle":
        return "Oracle: "+str(result.get("result",0))+" dead evil."+sfx
    if t=="mathematician":
        return "Math: "+str(result.get("result",0))+"."+sfx
    if t=="undertaker":
        return "Undertaker: "+str(result.get("character","?"))+"."+sfx
    if t=="chef":
        return "Chef: "+str(result.get("count",0))+"."+sfx
    if t=="chambermaid":
        return "Chambermaid: "+str(result.get("count",0))+" woke."+sfx
    if t in ("washerwoman","librarian","investigator"):
        ps=result.get("players",[])
        pn=[p.get("name","?") for p in ps if isinstance(p,dict)]
        return char+": "+", ".join(pn)+" - "+str(result.get("character","?"))+"."+sfx
    if t=="juggler":
        return "Juggler: "+str(result.get("count",0))+" correct."+sfx
    return None

def compute_auto_info(player, game):
    char = player['character']
    night = game.get('night', 1)
    g = game
    try:
        if char == 'Empath':
            r = BL.resolve_empath_night(player, g)
            if r is not None:
                n=r['result']
                return f"Empath: {n} neighbour{'s are' if n!=1 else ' is'} evil."
        elif char=='Undertaker':
            r=BL.resolve_undertaker_night(player,g)
            if r and r.get('character'):
                return 'Undertaker: '+r['character']
        elif char=='Town Crier':
            r=BL.resolve_town_crier_night(player,g)
            if r is not None:
                return 'Town Crier: '+('Yes' if r['result'] else 'No')
        elif char=='Flowergirl':
            r=BL.resolve_flowergirl_night(player,g)
            if r is not None:
                return 'Flowergirl: '+('Yes' if r['result'] else 'No')
        elif char=='Oracle':
            r=BL.resolve_oracle_night(player,g)
            if r is not None: return 'Oracle: '+str(r['result'])+' dead evil'
        elif char=='Mathematician':
            r=BL.resolve_mathematician_night(player,g)
            if r is not None: return 'Math: '+str(r['result'])+' abnormal'
        elif char in ('Washerwoman','Librarian','Investigator',
                      'Chef','Clockmaker','Shugenja','Balloonist'):
            if night==1: return f'ST will provide {char} info.'
        elif char=='Dreamer': return 'ST will provide Dreamer info.'
    except Exception as e: print(f"auto_info err {char}: {e}")
    return None

async def start_night(game_key, bot):
    g = get_game(game_key)
    if not g: return
    guild = get_guild(bot)
    if not guild: return
    night = g.get('night', 0) + 1
    g['night'] = night
    g['phase'] = 'night'
    g['night_start_time'] = datetime.datetime.now(pytz.utc).isoformat()
    g['pending_actions'] = {}
    g['collected_actions'] = {}
    g['_someone_died_last_day'] = g.pop('_someone_died_today', False)
    BL.start_of_night(g)
    _, logs_ch = get_game_channels(guild, game_key)
    night_msg = f'Night {night} has begun. Players will receive action DMs shortly.'
    for ch_id in (g.get('game_channel_ids') or []):
        ch = guild.get_channel(ch_id)
        if ch:
            try: await ch.send(night_msg)
            except: pass
    if logs_ch:
        try: await logs_ch.send(night_msg)
        except: pass
    player_list = '\n'.join(
        ('alive' if p['alive'] else 'dead')+' '+p.get('name',p['id'])+': '+p['character']
        for p in g.get('players', []))
    dm_tasks=[]
    for p in g.get('players',[]):
        if not p['alive']: continue
        char=p['character']
        borrowed_source=None; borrowed_char=None
        if char=='Philosopher' and night>1:
            cc=p['tokens'].get('copied_character')
            if cc: borrowed_source='philosopher'; borrowed_char=cc
            else: continue
        elif char=='Cannibal' and night>1:
            _ctold,_=BL.get_cannibal_effective_character(g)
            if _ctold: borrowed_source='cannibal'; borrowed_char=_ctold
            else: continue
        elif char=='Cannibal':
            continue
        lookup=borrowed_char if borrowed_source else char
        spec=CHAR_ACTIONS.get(lookup)
        if not spec: continue
        n1,ni,prompt=spec
        if night==1 and not n1: continue
        if char=='Widow' and p['tokens'].get('widow_used'): continue
        if char in ('Kazali','Lord of Typhon') and night==1:
            prompt='Assign minions (e.g. Alice Baron, Bob Spy):'
        if char=='Wizard' and p['tokens'].get('wizard_wish_used'): continue
        if borrowed_source=='philosopher':
            pkey=p['id']+'_phil'; atype='philosopher_borrowed'
            ameta={'phil_char':borrowed_char,'player_id':p['id']}
        elif borrowed_source=='cannibal':
            pkey=p['id']+'_cannibal'; atype='cannibal'
            ameta={'cannibal_char':borrowed_char,'player_id':p['id']}
        else:
            pkey=p['id']
            atype='wizard_wish' if char=='Wizard' else char
            ameta={}
        if ni and prompt:
            if borrowed_source:
                fp=f'Night {night} (as {borrowed_char}): {prompt}\n\nPlayers:\n{player_list}'
            else:
                fp=f'Night {night}-{char}\n{prompt}\n\nPlayers:\n{player_list}'
            g['pending_actions'][pkey]={'action_type':atype,'resolved':False,**ameta}
            dm_tasks.append(dm_player(bot,p,fp))
        else:
            if borrowed_source=='cannibal':
                ctok=p['tokens'].get('cannibal_instance',{}).get('tokens',{})
                info=compute_auto_info({'character':borrowed_char,'id':p['id'],'tokens':ctok},g)
                if info: dm_tasks.append(dm_player(bot,p,f'Cannibal ({borrowed_char}): {info}'))
            elif borrowed_source=='philosopher':
                info=compute_auto_info({'character':borrowed_char,'id':p['id'],'tokens':p['tokens']},g)
                if info: dm_tasks.append(dm_player(bot,p,f'Phil ({borrowed_char}): {info}'))
            else:
                info=compute_auto_info(p,g)
                if info: dm_tasks.append(dm_player(bot,p,info))
    # Hermit: one DM per script Outsider with an active night action
    _herm=next((p for p in g.get('players',[]) if p['alive'] and p['character']=='Hermit'),None)
    if _herm:
        _hinsts=_herm['tokens'].get('hermit_instances',{})
        for _hchar,_hinst in _hinsts.items():
            if not _hinst.get('ability_active',True): continue
            _hspec=CHAR_ACTIONS.get(_hchar)
            if not _hspec: continue
            _hn1,_hni,_hprompt=_hspec
            if night==1 and not _hn1: continue
            _hkey=_herm['id']+'_hermit_'+_hchar
            if _hni and _hprompt:
                _hfp=f'Night {night} (Hermit - {_hchar}): {_hprompt}\n\nPlayers:\n{player_list}'
                g['pending_actions'][_hkey]={'action_type':'hermit_outsider','outsider_char':_hchar,'player_id':_herm['id'],'resolved':False}
                dm_tasks.append(dm_player(bot,_herm,_hfp))
            else:
                _htok=_hinst.get('tokens',{})
                _hinfo=compute_auto_info({'character':_hchar,'id':_herm['id'],'tokens':_htok},g)
                if _hinfo: dm_tasks.append(dm_player(bot,_herm,f'Hermit ({_hchar}): {_hinfo}'))
    # Boffin: demon needs kill DM + separate borrowed-ability DM
    dem=next((p for p in g.get('players',[]) if p['alive'] and 'boffin_instance' in p.get('tokens',{})),None)
    if dem:
        binst=dem['tokens']['boffin_instance']
        bchar=binst.get('character','')
        bspec=CHAR_ACTIONS.get(bchar)
        if bspec and binst.get('ability_active',True):
            bn1,bni,bprompt=bspec
            if not (night==1 and not bn1):
                bkey=dem['id']+'_boffin'
                if bni and bprompt:
                    bp=f'Night {night} - Boffin: {bchar}\n{bprompt}\n\nPlayers:\n{player_list}'
                    g['pending_actions'][bkey]={'action_type':'boffin','boffin_char':bchar,'player_id':dem['id'],'resolved':False}
                    dm_tasks.append(dm_player(bot,dem,bp))
                else:
                    binfo=compute_auto_info({'character':bchar,'id':dem['id'],'tokens':binst.get('tokens',{})},g)
                    if binfo: dm_tasks.append(dm_player(bot,dem,f'Boffin ({bchar}): {binfo}'))
    grimoire_tasks=[]
    for _gwp in g.get("players",[]):
        if not _gwp["alive"]: continue
        if _gwp["character"]=="Widow" and not _gwp["tokens"].get("widow_used"):
            _snap=BL.resolve_widow_grimoire_view(_gwp,g)
            if _snap: grimoire_tasks.append(dm_player_grimoire(bot,_gwp,_snap,game_key))
    if grimoire_tasks: await asyncio.gather(*grimoire_tasks,return_exceptions=True)
    set_game(game_key,g)
    if dm_tasks: await asyncio.gather(*dm_tasks,return_exceptions=True)

async def _alh_announce_and_prompt(bot,game_key,g,idx):
    seq=g.get("_alh_seq",{})
    tids=seq.get("targets",[])
    if idx>=len(tids): return
    tid=tids[idx]
    p=BL.get_player(g,tid)
    if not p: return
    guild=get_guild(bot)
    _,logs_ch=get_game_channels(guild,game_key) if guild else (None,None)
    pub=f"Al-Hadikhia chose **{p.get('name',p['id'])}**."
    for ch_id in (g.get("game_channel_ids") or []):
        ch=guild.get_channel(ch_id) if guild else None
        if ch:
            try: await ch.send(pub)
            except: pass
    if logs_ch:
        try: await logs_ch.send(pub)
        except: pass
    if not p.get("alive",True): return
    others=[BL.get_player(g,t).get("name",t) for t in tids if t!=tid and BL.get_player(g,t)]
    oth=', '.join(others) if others else 'none'
    msg=(f"You have been chosen by Al-Hadikhia. Others chosen: {oth}.\n\n"
         "Reply `live` or `die`.\n"
         "If all survive phase 1, all die in phase 2 (in selection order).")
    g["pending_actions"][tid]={"action_type":"alh_choice","resolved":False}
    set_game(game_key,g)
    await dm_player(bot,p,msg)

async def _alh_start_sequence(bot,game_key,g,target_ids):
    demon=BL.get_character(g,"Al-Hadikhia")
    g["_alh_seq"]={"targets":target_ids,"choices":{},"idx":0,"resolved":False,"demon_id":demon["id"] if demon else None}
    set_game(game_key,g)
    await _alh_announce_and_prompt(bot,game_key,g,0)

async def _alh_advance_sequence(bot,game_key,pid,choice):
    g=get_game(game_key)
    if not g: return
    seq=g.setdefault("_alh_seq",{})
    seq.setdefault("choices",{})[pid]=choice
    tids=seq.get("targets",[])
    demon_id=seq.get("demon_id")
    src={"type":BL.DEMON_KILL,"source_character":"Al-Hadikhia"}
    guild=get_guild(bot)
    ch_ids=list(g.get("game_channel_ids") or [])
    _,logs_ch=get_game_channels(guild,game_key) if guild else (None,None)
    async def broadcast(text):
        for ch_id in ch_ids:
            ch=guild.get_channel(ch_id) if guild else None
            if ch:
                try: await ch.send(text)
                except: pass
        if logs_ch:
            try: await logs_ch.send(text)
            except: pass
    # Phase 1: resolve this choice immediately
    if choice=="die":
        orig=BL.get_player(g,demon_id) if demon_id else None
        t=BL.get_player(g,pid)
        if t and t["alive"] and orig and orig["alive"]:
            if BL.can_player_die(t,src,g)==BL.DIES:
                BL.resolve_death(t,src,g)
                set_game(game_key,g); g=get_game(game_key); seq=g.get("_alh_seq",{})
                await broadcast(f"**{t.get('name',pid)}** died.")
    set_game(game_key,g); g=get_game(game_key); seq=g.setdefault("_alh_seq",{})
    orig=BL.get_player(g,demon_id) if demon_id else None
    if not orig or not orig["alive"]:
        seq["resolved"]=True; set_game(game_key,g); return
    nxt=seq.get("idx",0)+1
    seq["idx"]=nxt; set_game(game_key,g)
    if nxt<len(tids):
        g=get_game(game_key)
        await _alh_announce_and_prompt(bot,game_key,g,nxt)
    else:
        g=get_game(game_key); seq=g.get("_alh_seq",{})
        all_alive=all((lambda p:p and p["alive"])(BL.get_player(g,t)) for t in tids)
        if all_alive:
            for kill_tid in tids:
                orig=BL.get_player(g,demon_id) if demon_id else None
                if not orig or not orig["alive"]: break
                t=BL.get_player(g,kill_tid)
                if not t or not t["alive"]: continue
                if BL.can_player_die(t,src,g)==BL.DIES:
                    BL.resolve_death(t,src,g)
                    set_game(game_key,g); g=get_game(game_key)
                    await broadcast(f"**{t.get('name',kill_tid)}** died.")
        seq=g.get("_alh_seq",{}); seq["resolved"]=True; set_game(game_key,g)

def find_pending_game(discord_id):
    from botc_runner import load_games
    for gk,g in load_games().items():
        if g.get('phase')!='night': continue
        pending=g.get('pending_actions',{})
        for key,entry in pending.items():
            if entry.get('resolved'): continue
            pid=entry.get('player_id') or key
            p=next((x for x in g.get('players',[])
                if x['id']==pid and get_player_discord_id(x)==discord_id),None)
            if p: return gk,p,key
    return None,None,None

async def handle_dm_action(bot, discord_id, text):
    game_key,player,action_key=find_pending_game(discord_id)
    if not game_key: return 'No pending action right now.'
    g=get_game(game_key)
    if not g: return 'Game not found.'
    pid=player['id']
    text=text.strip()
    pe=g.get('pending_actions',{}).get(action_key,{})
    if pe.get('action_type')=='alh_choice':
        c=text.lower()
        if c not in ('live','die','l','d'): return "Reply `live` or `die`."
        c='die' if c in ('die','d') else 'live'
        g['pending_actions'][action_key]['resolved']=True
        g.setdefault('collected_actions',{})[action_key]={'char':'alh_choice','choice':c}
        set_game(game_key,g)
        await _alh_advance_sequence(bot,game_key,pid,c)
        return f'You chose to **{c}** tonight.'
    if pe.get('action_type')=='wizard_wish':
        if player['tokens'].get('wizard_wish_used'):
            return 'You have already made your wish.'
        BL.resolve_wizard_wish(player, text, g)
        g['pending_actions'][action_key]['resolved']=True
        g.setdefault('collected_actions',{})[action_key]={'char':'Wizard','wish':text}
        set_game(game_key,g)
        return 'Your wish has been relayed to the Storyteller.'
    is_boffin=pe.get('action_type')=='boffin'
    is_phil=pe.get('action_type')=='philosopher_borrowed'
    is_cannibal=pe.get('action_type')=='cannibal'
    is_hermit=pe.get('action_type')=='hermit_outsider'
    if is_phil:
        char=pe.get('phil_char','')
        ckey=player['id']+'_phil'
    elif is_boffin:
        char=pe.get('boffin_char','')
        ckey='_boffin'
    elif is_cannibal:
        char=pe.get('cannibal_char','')
        ckey=player['id']+'_cannibal'
    elif is_hermit:
        char=pe.get('outsider_char','')
        ckey=player['id']+'_hermit_'+char
    else:
        char=player['character']
        ckey=char
    action_data={'char':ckey,'raw':text}
    spec=CHAR_ACTIONS.get(char)
    if not spec: return 'Unknown character.'
    _,needs_input,_=spec
    if not needs_input: return 'No input needed.'
    two={'Fortune Teller','Innkeeper','Shabaloth','Chambermaid','Seamstress','Harpy'}
    three={'Al-Hadikhia'}; combo={'Gambler','Cerenovus','Summoner','Pit-Hag'}
    kazali_lot={'Kazali','Lord of Typhon'}
    if text.lower()=='pass': action_data['targets']=[]
    elif char in kazali_lot:
        if g.get('night',1)==1:
            parts=[p.strip() for p in re.split(r',|\n',text) if p.strip()]
            asgn=[]
            for part in parts:
                tp2=find_player_by_text(part,g); mc=find_character_in_text(part)
                if tp2 and mc: asgn.append({'player_id':tp2['id'],'minion_character':mc})
            if not asgn: return 'Format: Alice Baron, Bob Spy'
            action_data['assignments']=asgn
        else:
            tp=find_player_by_text(text,g)
            if not tp: return 'Could not find player.'
            action_data['targets']=[tp['id']]
    elif char in three:
        tgts=find_players_by_text(text,g,count=3)
        if len(tgts)<3: return f'Need 3 players, found {len(tgts)}.'
        action_data['targets']=[t['id'] for t in tgts]
    elif char in two:
        tgts=find_players_by_text(text,g,count=2)
        if len(tgts)<2: return f'Need 2 players, found {len(tgts)}.'
        action_data['targets']=[t['id'] for t in tgts]
    elif char in combo:
        tp=find_player_by_text(text,g); c=find_character_in_text(text)
        if not tp: return 'Could not find player.'
        action_data['targets']=[tp['id']]; action_data['character']=c
    elif char=='Ojo':
        c=find_character_in_text(text)
        if not c: return 'Could not find character name.'
        action_data['character']=c
    elif char=="Lil' Monsta":
        holder=find_player_by_text(text,g)
        tm=re.search(r'target[:\s]+(.+)',text,re.IGNORECASE)
        tgt=find_player_by_text(tm.group(1) if tm else text,g)
        if not holder: return 'Format: holder:Alice target:Bob'
        action_data['holder']=holder['id']
        action_data['targets']=[tgt['id']] if tgt else []
    else:
        tp=find_player_by_text(text,g)
        if not tp: return 'Could not find player.'
        action_data['targets']=[tp['id']]
    g['pending_actions'][action_key]['resolved']=True
    g.setdefault('collected_actions',{})[action_key]=action_data
    set_game(game_key,g)
    names=[]
    for tid in action_data.get('targets',[]):
        tp=BL.get_player(g,tid)
        if tp: names.append(tp.get('name',tid))
    if action_data.get('character'): names.append(action_data['character'])
    s=', '.join(names) if names else 'pass'
    if char=='Al-Hadikhia' and action_data.get('targets'):
        await _alh_start_sequence(bot,game_key,g,action_data['targets'])
    label=(f'Boffin ({char})' if is_boffin else f'Cannibal ({char})' if is_cannibal else f'Phil ({char})' if is_phil else f'Hermit ({char})' if is_hermit else char)
    return f'Got it - {label}: {s}'


async def end_night(game_key, bot):
    g=get_game(game_key)
    if not g or g.get('phase')!='night': return
    guild=get_guild(bot)
    if not guild: return
    night=g.get('night',1)
    collected=g.get('collected_actions',{})
    def ga(cn):
        for pid,act in collected.items():
            if act.get('char')==cn: return pid,act
        return None,None
    def gp(pid): return BL.get_player(g,pid)
    announcements=[]
    dm_infos=[]
    # --- BARISTA (ST-set nightly action) ---
    _ba=g.get("_barista_action",{})
    if _ba.get("target_id"):
        _barista_p=BL.get_character(g,"Barista")
        if _barista_p:
            BL.resolve_barista_night(_barista_p,_ba["target_id"],_ba.get("ability_num",1),g)
            _btgt=gp(_ba["target_id"])
            if _btgt:
                _ab_label="sober+healthy" if _ba.get("ability_num",1)==1 else "double ability"
                dm_infos.append((_barista_p["id"],"Barista: you affected "+_btgt.get("name","?")+" ("+_ab_label+")."))
    pid,act=ga('Poisoner')
    if pid and act.get('targets'):
        BL.resolve_poisoner_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Sailor')
    if pid and act.get('targets'):
        BL.resolve_sailor_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Innkeeper')
    if pid and act.get('targets') and len(act['targets'])>=2:
        BL.resolve_innkeeper_night(gp(pid),act['targets'][0],act['targets'][1],act['targets'][-1],g)
    pid,act=ga('Witch')
    if pid and act.get('targets'): BL.resolve_witch_night(gp(pid),act['targets'][0],g)
    pid,act=ga("Devil's Advocate")
    if pid and act.get('targets'): BL.resolve_devils_advocate_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Monk')
    if pid and act.get('targets'): BL.resolve_monk_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Cult Leader')
    if pid: BL.resolve_cult_leader_night(gp(pid),act['targets'][0] if act and act.get('targets') else None,g)
    pid,act=ga('Butler')
    if pid and act.get('targets'): BL.resolve_butler_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Preacher')
    if pid and act.get('targets'): BL.resolve_preacher_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Exorcist')
    if pid and act.get('targets'): BL.resolve_exorcist_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Widow')
    if pid and act.get('targets'): BL.resolve_widow_night(gp(pid),act['targets'][0],g)
    pid,act=ga('Fortune Teller')
    if pid and act.get('targets') and len(act['targets'])>=2:
        ft=gp(pid)
        if ft:
            r=BL.resolve_fortune_teller_night(ft,act['targets'][0],act['targets'][1],g)
            if r is not None:
                yn='Yes' if r.get('result') else 'No'
                dm_infos.append((pid,'FT: '+yn+', one is Demon.'))
    pid,act=ga('Seamstress')
    if pid and act.get('targets') and len(act['targets'])>=2:
        sm=gp(pid)
        if sm:
            r=BL.resolve_seamstress_night(sm,act['targets'][0],act['targets'][1],g)
            if r is not None:
                a='same' if r.get('same_alignment') else 'different'
                dm_infos.append((pid,'Seamstress: '+a+' alignment.'))
    pid,act=ga('Gambler')
    if pid and act.get('targets') and act.get('character'):
        gbl=gp(pid)
        if gbl: BL.resolve_gambler_night(gbl,act['targets'][0],act['character'],g)
    if night==1:
        pid,act=ga('Grandmother')
        if pid and act.get('targets'):
            gm=gp(pid)
            if gm:
                r=BL.resolve_grandmother_night(gm,act['targets'][0],g)
                if r:
                    tc=gp(act['targets'][0])
                    if tc: dm_infos.append((pid,'Grandmother: grandchild is '+tc.get('name','')+' the '+tc['character']))
    # --- PHILOSOPHER ---
    pid,act=ga('Philosopher')
    if pid and act.get('character'):
        BL.resolve_philosopher_night(gp(pid),act['character'],g)
    # --- PHILOSOPHER borrowed (night 2+) ---
    for _pp in g.get('players',[]):
        if not _pp['alive'] or _pp['character']!='Philosopher': continue
        _pkey=_pp['id']+'_phil'
        _,_pact=ga(_pkey)
        if _pact:
            _pr=BL.resolve_philosopher_borrowed_night(gp(_pp['id']),_pact,g)
            _pmsg=_format_borrowed_result(_pact.get('phil_char','?'),_pr,g)
            if _pmsg: dm_infos.append((_pp['id'],'Phil: '+_pmsg))
    # --- CANNIBAL borrowed (night 2+) ---
    _can2=BL.get_character(g,'Cannibal')
    if _can2 and _can2['alive']:
        _,_cact=ga(_can2['id']+'_cannibal')
        if _cact:
            _cr=BL.resolve_cannibal_night(_can2,_cact,g)
            _cmsg=_format_borrowed_result(_cact.get('cannibal_char','?'),_cr,g)
            if _cmsg: dm_infos.append((_can2['id'],'Cannibal: '+_cmsg))
    # --- HERMIT outsider actions ---
    _herm2=BL.get_character(g,'Hermit')
    if _herm2 and _herm2['alive']:
        _hinsts2=_herm2['tokens'].get('hermit_instances',{})
        for _hchar2,_hinst2 in _hinsts2.items():
            _hkey2=_herm2['id']+'_hermit_'+_hchar2
            _hact2=collected.get(_hkey2)
            if _hact2:
                _hr=BL.resolve_hermit_outsider_night(_herm2,_hchar2,_hact2,g)
                _hmsg=_format_borrowed_result(_hchar2,_hr,g)
                if _hmsg: dm_infos.append((_herm2['id'],f'Hermit ({_hchar2}): {_hmsg}'))
    # --- SNAKE CHARMER ---
    pid,act=ga('Snake Charmer')
    if pid and act.get('targets'):
        BL.resolve_snake_charmer_night(gp(pid),act['targets'][0],g)
    # --- COURTIER ---
    pid,act=ga('Courtier')
    if pid and act.get('character'):
        BL.resolve_courtier_night(gp(pid),act['character'],g)
    # --- CERENOVUS ---
    pid,act=ga('Cerenovus')
    if pid and act.get('targets') and act.get('character'):
        BL.resolve_cerenovus_night(gp(pid),act['targets'][0],act['character'],g)
    # --- HARPY ---
    pid,act=ga('Harpy')
    if pid and act.get('targets') and len(act['targets'])>=2:
        BL.resolve_harpy_night(gp(pid),act['targets'][0],act['targets'][1],g)
    # --- PIT-HAG ---
    pid,act=ga('Pit-Hag')
    if pid and act.get('targets') and act.get('character'):
        try: _cdata=__import__('json').load(open('/home/discord-bot/botc_data.json')).get('characters',{})
        except: _cdata={}
        _tmap={'townsfolk':BL.TOWNSFOLK,'outsider':BL.OUTSIDER,'minion':BL.MINION,'demon':BL.DEMON}
        _nchar=act['character']
        _ntype=_tmap.get(_cdata.get(_nchar,{}).get('type','').lower(),BL.TOWNSFOLK)
        _naln=BL.EVIL if _ntype in(BL.MINION,BL.DEMON) else BL.GOOD
        BL.resolve_pit_hag_night(gp(pid),act['targets'][0],_nchar,_ntype,_naln,g)
    # --- SUMMONER ---
    pid,act=ga('Summoner')
    if pid and act.get('targets') and act.get('character'):
        BL.resolve_summoner_night(gp(pid),act['targets'][0],act['character'],g)
    # --- MEZEPHELES ---
    pid,act=ga('Mezepheles')
    if pid and act.get('targets'):
        _mez=gp(pid)
        if _mez:
            _mword=g.setdefault('_mezepheles_word',BL.generate_mezepheles_word())
            BL.resolve_mezepheles_night(_mez,act['targets'][0],_mword,g)
            dm_infos.append((pid,'Mezepheles word: **'+_mword+'**'))
    # --- ASSASSIN ---
    pid,act=ga('Assassin')
    if pid and act.get('targets'):
        _atgt=gp(act['targets'][0])
        if _atgt:
            _was=_atgt['alive']
            BL.resolve_assassin_night(gp(pid),act['targets'][0],g)
            if _was and not _atgt['alive']:
                announcements.append(_atgt.get('name','')+' died in the night.')
    # --- GODFATHER ---
    pid,act=ga('Godfather')
    if pid and act.get('targets'):
        _gtgt=gp(act['targets'][0])
        if _gtgt:
            _was=_gtgt['alive']
            BL.resolve_godfather_night(gp(pid),act['targets'][0],g)
            if _was and not _gtgt['alive']:
                announcements.append(_gtgt.get('name','')+' died in the night.')
    # --- ACROBAT ---
    pid,act=ga('Acrobat')
    if pid and act.get('targets'):
        _acro=gp(pid)
        if _acro:
            _acro_was=_acro['alive']
            BL.resolve_acrobat_night(_acro,act['targets'][0],g)
            if _acro_was and not _acro['alive']:
                announcements.append(f'💀 **{_acro.get("name","?")}** died in the night.')
    # --- CHAMBERMAID ---
    pid,act=ga('Chambermaid')
    if pid and act.get('targets') and len(act['targets'])>=2:
        _cm=gp(pid)
        if _cm:
            r=BL.resolve_chambermaid_night(_cm,act['targets'][0],act['targets'][1],g)
            if r is not None:
                _p1=gp(act['targets'][0]); _p2=gp(act['targets'][1])
                _n1=_p1.get('name','?') if _p1 else '?'
                _n2=_p2.get('name','?') if _p2 else '?'
                dm_infos.append((pid,f'Chambermaid: {_n1} {"woke" if r.get("p1_woke") else "slept"}, {_n2} {"woke" if r.get("p2_woke") else "slept"}.'))
    # --- PROFESSOR ---
    pid,act=ga('Professor')
    if pid and act.get('targets'):
        _ptgt=gp(act['targets'][0])
        if _ptgt:
            _was=_ptgt['alive']
            BL.resolve_professor_night(gp(pid),act['targets'][0],g)
            if not _was and _ptgt['alive']:
                announcements.append(_ptgt.get('name','')+' was resurrected by the Professor!')
    # --- JUGGLER (night 2+: DM count) ---
    if night>1:
        _jug_p=BL.get_character(g,'Juggler')
        if _jug_p and _jug_p['alive']:
            r=BL.resolve_juggler_night(_jug_p,g)
            if r is not None:
                dm_infos.append((_jug_p['id'],'Juggler: **'+str(r.get('count',r.get('result',0)))+'** correct.'))
    lycan_p=BL.get_character(g,"Lycanthrope")
    if lycan_p and lycan_p["alive"]:
        _,lact=ga("Lycanthrope")
        if lact and lact.get("targets"):
            lk=BL.resolve_lycanthrope_night(lycan_p,lact["targets"][0],g)
            if lk: announcements.append(lk.get("name","")+' died in the night.')
    demon=next((p for p in g.get('players',[]) if p['char_type']==BL.DEMON and p['alive']),None)
    if demon:
        boffin_key=demon['id']+'_boffin'
        _,bact=ga(boffin_key)
        if bact:
            bc,br=BL.resolve_boffin_ability(
                demon,bact.get('targets',[]),g,bact.get('character'))
            if bc and br:
                if bc=='Fortune Teller':
                    dm_infos.append((demon['id'],
                        'Boffin FT: '+('Yes' if br.get('result') else 'No')))
                elif bc=='Seamstress':
                    a='same' if br.get('same_alignment') else 'different'
                    dm_infos.append((demon['id'],'Boffin Seamstress: '+a))
        char=demon['character']
        pid,act=ga(char)
        def died(t): announcements.append(t.get('name','')+' died in the night.')
        if char=='Imp':
            if pid and act.get('targets'):
                t=gp(act['targets'][0])
                if t and BL.resolve_demon_kill(demon,t,g)==BL.DIES: died(t)
        elif char in ('No Dashii','Vortox','Vigormortis','Fang Gu','Legion','Zombuul'):
            if pid and act.get('targets'):
                t=gp(act['targets'][0])
                if t and BL.resolve_demon_kill(demon,t,g)==BL.DIES: died(t)
        elif char=='Kazali':
            if night==1:
                _,kact=ga('Kazali')
                if kact and kact.get('assignments'):
                    changed=BL.resolve_kazali_night(demon,kact['assignments'],g)
                    BL.post_kazali_lot_setup(g)
                    for cp in changed: dm_infos.append((cp['id'],'You are now a '+cp['character']+'.'))
            elif pid and act.get('targets'):
                t2=gp(act['targets'][0])
                if t2 and BL.resolve_demon_kill(demon,t2,g)==BL.DIES: died(t2)
        elif char=='Lord of Typhon':
            if night==1:
                _,lact=ga('Lord of Typhon')
                if lact and lact.get('assignments'):
                    changed=BL.resolve_lot_setup(demon,lact['assignments'],g)
                    BL.post_kazali_lot_setup(g)
                    for cp in changed: dm_infos.append((cp['id'],'You are now a '+cp['character']+'.'))
            elif pid and act.get('targets'):
                t2=gp(act['targets'][0])
                if t2 and BL.resolve_demon_kill(demon,t2,g)==BL.DIES: died(t2)
        elif char=='Ojo':
            if pid and act.get('character'):
                tc=BL.get_character(g,act['character'])
                if tc:
                    t=gp(tc["id"])
                    if t and BL.resolve_demon_kill(demon,t,g)==BL.DIES: died(t)
        elif char=='Po':
            if pid:
                if not act.get('targets'):
                    BL.resolve_po_night(demon,None,g)
                else:
                    for tid in act['targets'][:3]:
                        t=gp(tid)
                        if t and BL.resolve_demon_kill(demon,t,g)==BL.DIES: died(t)
        elif char=='Shabaloth':
            if pid and act.get('targets'):
                killed,revived=BL.resolve_shabaloth_night(demon,act['targets'],g)
                for t in killed: died(t)
                for t in revived: announcements.append(t.get('name','')+' was revived.')
        elif char=='Pukka':
            t2=act['targets'][0] if act and act.get('targets') else None
            pk=BL.resolve_pukka_night(demon,t2,g)
            if pk: died(pk)
        elif char=='Lleech':
            if pid and act.get('targets'):
                if night==1: BL.resolve_lleech_setup(demon,act["targets"][0],g)
                else: BL.resolve_lleech_night(demon,act["targets"][0],g)
        elif char=='Al-Hadikhia':
            if pid and act.get('targets'):
                seq=g.get('_alh_seq',{})
                if not seq.get('resolved'):
                    tids=seq.get('targets',act['targets'])
                    choices=seq.get('choices',{})
                    die_ids=[t for t in tids if choices.get(t)=='die']
                    deaths,alh_win=BL.resolve_al_hadikhia_night(demon,tids,die_ids,g)
                    for t in deaths: died(t)
                    if alh_win:
                        announcements.append(alh_win+' wins!')
                        g['phase']='day'; set_game(game_key,g); return
    lm_pid,lm_act=ga("Lil' Monsta")
    if lm_pid and lm_act and lm_act.get('holder'):
        BL.resolve_lil_monsta_vote(lm_act['holder'],g)
        if lm_act.get('targets'): BL.resolve_lil_monsta_kill(lm_act['targets'][0],g)
    for p in g.get('players',[]):
        if not p['alive']: continue
        char=p['character']
        spec=CHAR_ACTIONS.get(char)
        if not spec: continue
        n1,ni,prompt=spec
        if not ni and prompt is None:
            info=compute_auto_info(p,g)
            if info: dm_infos.append((p['id'],info))
    # --- BARISTA DOUBLE ABILITY ---
    _barista_chr=BL.get_character(g,'Barista')
    if _barista_chr and _barista_chr.get('alive'):
        for _bp in g.get('players',[]):
            if not _bp.get('alive') or not _bp['tokens'].get('barista_double_ability'): continue
            BL.barista_reset_for_double(_bp)
            _bc=_bp['character']; _bpid,_bact=ga(_bc)
            _btgts=_bact.get('targets',[]) if _bact else []
            if _bc=='Poisoner' and _btgts: BL.resolve_poisoner_night(_bp,_btgts[0],g)
            elif _bc=='Sailor' and _btgts: BL.resolve_sailor_night(_bp,_btgts[0],g)
            elif _bc=='Monk' and _btgts: BL.resolve_monk_night(_bp,_btgts[0],g)
            elif _bc=='Witch' and _btgts: BL.resolve_witch_night(_bp,_btgts[0],g)
            elif _bc=='Butler' and _btgts: BL.resolve_butler_night(_bp,_btgts[0],g)
            elif _bc=='Preacher' and _btgts: BL.resolve_preacher_night(_bp,_btgts[0],g)
            elif _bc=='Exorcist' and _btgts: BL.resolve_exorcist_night(_bp,_btgts[0],g)
            elif _bc=="Devil's Advocate" and _btgts: BL.resolve_devils_advocate_night(_bp,_btgts[0],g)
            elif _bc=='Cult Leader': BL.resolve_cult_leader_night(_bp,_btgts[0] if _btgts else None,g)
            elif _bc=='Innkeeper' and len(_btgts)>=2: BL.resolve_innkeeper_night(_bp,_btgts[0],_btgts[1],_btgts[-1],g)
            elif _bc=='Fortune Teller' and len(_btgts)>=2:
                _r=BL.resolve_fortune_teller_night(_bp,_btgts[0],_btgts[1],g)
                if _r is not None: dm_infos.append((_bp['id'],'[x2] FT: '+('Yes' if _r.get('result') else 'No')))
            elif _bc=='Seamstress' and len(_btgts)>=2:
                _r=BL.resolve_seamstress_night(_bp,_btgts[0],_btgts[1],g)
                if _r is not None: dm_infos.append((_bp['id'],'[x2] Seamstress: '+('same' if _r.get('same_alignment') else 'different')))
            elif _bc=='Gambler' and _btgts and _bact.get('character'):
                BL.resolve_gambler_night(_bp,_btgts[0],_bact['character'],g)
            elif _bc=='Grandmother' and _btgts:
                _r=BL.resolve_grandmother_night(_bp,_btgts[0],g)
                if _r:
                    _tc=gp(_btgts[0])
                    if _tc: dm_infos.append((_bp['id'],'[x2] Grandchild: '+_tc.get('name','')+' the '+_tc['character']))
            elif _bc=='Night Watchman' and _btgts:
                BL.resolve_nightwatchman_night(_bp,_btgts[0],g)
            else:
                _info=compute_auto_info(_bp,g)
                if _info: dm_infos.append((_bp['id'],'[x2] '+_info))
    if night>1:
        _acrobat=BL.get_character(g,"Acrobat")
        if _acrobat and _acrobat["alive"]:
            BL.resolve_acrobat_eot(_acrobat,g)
            if not _acrobat["alive"]:
                announcements.append(f'💀 **{_acrobat.get("name","?")}** died in the night.')
    if night==2 and any(p["alive"] and p["character"]=="Riot" for p in g.get("players",[])):
        _riot_changed=BL.setup_riot(g)
        _st_notes_pre=[f"RIOT: {c} became Riot" for c in _riot_changed]
    else:
        _st_notes_pre=[]
    win,_pending_actions=BL.flush_pending(g)
    if not win: win=BL.check_win_conditions(g)
    _st_notes=list(_st_notes_pre)
    for _atype,_adata in _pending_actions:
        if _atype=='PIXIE_GAIN_CHECK':
            _pxp=BL.get_player(g,_adata)
            if _pxp:
                _pxchar=_pxp.get('tokens',{}).get('pixie_shown_character','?')
                _st_notes.append(f'PIXIE: Did {_pxp.get("name","?")} act mad as {_pxchar}? Run /botc-pixie-confirm {_adata} to grant ability.')
        elif _atype=='EVIL_LEARNS_EACH_OTHER':
            _eps=[BL.get_player(g,e) for e in (_adata or [])]
            _en=', '.join(p.get('name','?')+'('+p['character']+')' for p in _eps if p)
            for p in _eps:
                if p: dm_infos.append((p['id'],'Poppy Grower died. Evil: '+_en))
        elif _atype=='VIGORMORTIS_POISON_NEEDED':
            _mp=BL.get_player(g,_adata)
            _mn=_mp.get('name','?') if _mp else str(_adata)
            _st_notes.append(f'VIGORMORTIS: {_mn} (Minion) died. Use /botc-vigormortis-poison {_adata} left|right to poison adjacent Townsfolk.')
        elif _atype in ('IMP_TRANSFER_NEEDED','FARMER_REPLACEMENT_NEEDED',
                        'SWEETHEART_DRUNK_NEEDED','WIDOW_GOOD_PLAYER_KNOWS_NEEDED',
                        'MAYOR_PROTECT_NEEDED','BARBER_SWAP_NEEDED','HATTER_SWAP_NEEDED',
                        'OJO_NO_TARGET_KILL_NEEDED','FEARMONGER_EXECUTE'):
            _st_notes.append('ST action needed: '+_atype+' data='+str(_adata))

    for _wact in g.get('collected_actions',{}).values():
        if _wact.get('char')=='Wizard' and _wact.get('wish'):
            _wp=BL.get_character(g,'Wizard')
            _wname=_wp.get('name','Wizard') if _wp else 'Wizard'
            _st_notes.append('WIZARD WISH from '+_wname+': '+_wact['wish'])
    if win: announcements.append(win+' wins the game!')
    day_num=g.get('day_num',1)
    g['phase']='day'
    g['day_num']=day_num
    g['day_ended_today']=False
    g['night_start_time']=None
    BL.end_of_day(g)
    set_game(game_key,g)
    dm_tasks=[]
    for (tpid,msg) in dm_infos:
        tp=BL.get_player(g,tpid)
        if tp: dm_tasks.append(dm_player(bot,tp,msg))
    if dm_tasks: await asyncio.gather(*dm_tasks,return_exceptions=True)
    _,logs_ch=get_game_channels(guild,game_key)
    if _st_notes and logs_ch:
        try: await logs_ch.send('**ST actions needed:**\n'+chr(10).join(_st_notes))
        except: pass
    spy_p=BL.get_character(g,'Spy')
    if spy_p and spy_p['alive']:
        _spy_snap=BL.resolve_spy_grimoire_view(spy_p,g)
        if _spy_snap:
            try: await dm_player_grimoire(bot,spy_p,_spy_snap,game_key)
            except Exception as _e: print('Spy grimoire err:',_e)
    if not announcements: announcements=['No deaths.']
    hdr='Day '+str(day_num)+'\n\n'+'\n'.join(announcements)
    for ch_id in (g.get('game_channel_ids') or []):
        ch=guild.get_channel(ch_id)
        if ch:
            try: await ch.send(hdr)
            except: pass
    if logs_ch:
        try: await logs_ch.send(hdr); await logs_ch.send("# Day "+str(day_num))
        except: pass
    if win: return
    gd=get_game_state(game_key)
    gd['nominations_enabled']=True
    gd['nominees']=[]; gd['nominators']=[]
    gd['dead_players']=[p['id'] for p in g.get('players',[]) if not p['alive']]
    set_game_state(game_key,gd)

async def initiate_cult_vote(game_key,caller_name,bot,game_channel_id=None):
    """Legacy stub — cult votes now use reaction messages via _post_vote_message."""
    return "Use /botc-cult-vote instead."


async def end_day(game_key, bot):
    g=get_game(game_key)
    if not g or g.get("phase")!="day": return
    guild=get_guild(bot)
    if not guild: return
    gd=get_game_state(game_key)
    nom_votes=gd.get("nomination_votes",[])
    def _fpid(discord_id,dname=""):
        sid=str(discord_id)
        for p in g.get("players",[]):
            if p["id"]==sid or p.get("discord_id")==sid: return p
        dl=dname.lower()
        for p in g.get("players",[]):
            if dl and p.get("name","").lower()==dl: return p
    tf_role=discord.utils.get(guild.roles,name="Townsfolk")
    for nv in nom_votes:
        nee_id=nv.get("nee_id"); nom_id=nv.get("nom_id")
        if not nee_id or not nom_id: continue
        voter_dids=list(nv.get("voter_ids",[]))
        try:
            _ch=guild.get_channel(nv["channel_id"])
            if _ch:
                _msg=await _ch.fetch_message(nv["message_id"])
                for _rxn in _msg.reactions:
                    if str(_rxn.emoji)=="⬆️":
                        async for _u in _rxn.users():
                            if not _u.bot and _u.id not in voter_dids:
                                voter_dids.append(_u.id)
                        break
        except: pass
        voter_pids=[]
        for did in voter_dids:
            _m=guild.get_member(did)
            if _m and tf_role and tf_role not in _m.roles: continue
            _p=_fpid(did,_m.display_name if _m else "")
            if _p: voter_pids.append(_p["id"])
        BL.tally_vote(nee_id,nom_id,voter_pids,g)
    # Execute whoever is on the block
    exec_msg=""
    game_over=False
    if g.get("_on_the_block"):
        exec_pid=g["_on_the_block"]
        exec_p=BL.get_player(g,exec_pid)
        if exec_p:
            BL.resolve_execution(exec_pid,g)
            win=BL.check_win_conditions(g)
            exec_msg=f"\n⚖️ {exec_p.get(chr(110)+chr(97)+chr(109)+chr(101),chr(63))} was executed."
            if not exec_p["alive"]: exec_msg+=" They are dead."
            else: exec_msg+=" They survived!"
            if win: exec_msg+=f"\n\U0001f3c6 {win} wins!"; game_over=True
    gd=get_game_state(game_key)
    gd["nominations_enabled"]=False; gd["nomination_votes"]=[]
    set_game_state(game_key,gd)
    _,logs_ch=get_game_channels(guild,game_key)
    msg="Day has ended."+exec_msg+"\nNight begins - watch for your DMs."
    for ch_id in (g.get("game_channel_ids") or []):
        ch=guild.get_channel(ch_id)
        if ch:
            try: await ch.send(msg)
            except: pass
    if logs_ch:
        try: await logs_ch.send(msg)
        except: pass
    g["day_ended_today"]=True; set_game(game_key,g)
    if not game_over: await start_night(game_key,bot)
async def resolve_execution(game_key, player_id, bot):
    g=get_game(game_key)
    if not g: return ""
    p=BL.get_player(g,player_id)
    if not p: return ""
    BL.resolve_execution(player_id,g)
    win=BL.check_win_conditions(g)
    set_game(game_key,g)
    msg=p.get('name','')+' ('+p['character']+') was executed.'
    if not p['alive']: msg+=' They are dead.'
    else: msg+=' They survived!'
    if win: msg+='\n'+win+' wins!'
    return msg
