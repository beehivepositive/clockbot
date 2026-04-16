"""botc_jinxes.py - BotC jinx registry."""

def _alive_count(g):
    return sum(1 for p in g["players"] if p.get("alive"))

def _hook_lm_sw_transfer(g):
    from botc_logic import get_character,ability_inactive,MINION
    sw=get_character(g,"Scarlet Woman")
    if(sw and sw["alive"] and not ability_inactive(sw,g)
            and sw["char_type"]==MINION and _alive_count(g)>=4):  # holder already dead; +1 = 5 at moment of death
        g["_lil_monsta_holder"]=sw["id"]
        sw["tokens"]["sw_must_hold_lm"]=True
        return sw["id"]
    return None

def _hook_spy_sees_grimoire(g):
    from botc_logic import is_poppy_grower_alive
    return not is_poppy_grower_alive(g)

def _hook_widow_sees_grimoire(g):
    from botc_logic import is_poppy_grower_alive
    return not is_poppy_grower_alive(g)

def _hook_spy_damsel_poisoned(g):
    from botc_logic import get_character
    return bool(get_character(g,"Spy") or g.get("_spy_was_in_play"))

def _hook_widow_damsel_poisoned(g):
    from botc_logic import get_character
    return bool(get_character(g,"Widow") or g.get("_widow_was_in_play"))

JINXES=[
    {"chars":frozenset({'Alchemist','Boffin'}),"text":'If the Alchemist has the Boffin ability, the Alchemist does not learn what ability the Demon has.'},
    {"chars":frozenset({'Alchemist','Marionette'}),"text":'An Alchemist-Marionette has no Marionette ability & the Marionette is in play.'},
    {"chars":frozenset({'Alchemist','Mastermind'}),"text":'An Alchemist-Mastermind has no Mastermind ability & the Mastermind is not-in-play.'},
    {"chars":frozenset({'Alchemist','Organ Grinder'}),"text":'If the Alchemist has the Organ Grinder ability, the Organ Grinder is in play. If both are sober, both are drunk.'},
    {"chars":frozenset({'Bounty Hunter','Kazali'}),"text":'If the Kazali turns the Bounty Hunter into a Minion, an evil Townsfolk is not created.'},
    {"chars":frozenset({'Bounty Hunter','Philosopher'}),"text":'If the Philosopher gains the Bounty Hunter ability, a Townsfolk might turn evil.'},
    {"chars":frozenset({'Butler','Cannibal'}),"text":'If the Cannibal gains the Butler ability, the Cannibal learns this.'},
    {"chars":frozenset({'Cannibal','Juggler'}),"text":'If the Juggler guesses on their first day and dies by execution, tonight the living Cannibal learns how many guesses the Juggler got correct.'},
    {"chars":frozenset({'Cannibal','Princess'}),"text":"If the Cannibal nominated, executed, & killed the Princess today, the Demon doesn't kill tonight."},
    {"chars":frozenset({'Cannibal','Zealot'}),"text":'If the Cannibal gains the Zealot ability, the Cannibal learns this.'},
    {"chars":frozenset({'Chambermaid','Mathematician'}),"text":'The Chambermaid can detect if the Mathematician will wake tonight.'},
    {"chars":frozenset({'Drunk','Mathematician'}),"text":"The Mathematician might learn if the Drunk's ability yielded false info or failed to work properly."},
    {"chars":frozenset({'Legion','Magician'}),"text":'Legion knows if a Magician is in play, but not which player it is.'},
    {"chars":frozenset({'Magician','Marionette'}),"text":"If the Magician is alive, the Demon doesn't know which neighbor is the Marionette."},
    {"chars":frozenset({'Magician','Spy'}),"text":"When the Spy sees the Grimoire, the Demon and Magician's character tokens are removed."},
    {"chars":frozenset({'Magician','Vizier'}),"text":"If the Vizier is in play, the Magician has no ability but is immune to the Vizier's ability."},
    {"chars":frozenset({'Magician','Widow'}),"text":"When the Widow sees the Grimoire, the Demon and Magician's character tokens are removed."},
    {"chars":frozenset({'Magician','Wraith'}),"text":'After each execution, the living Magician may publicly guess a living player as the Wraith. If correct, the Demon must choose the Wraith tonight.'},
    {"chars":frozenset({'Butler','Organ Grinder'}),"text":'If the Organ Grinder is causing eyes closed voting, the Butler may raise their hand to vote but their vote is only counted if their master voted too.'},
    {"chars":frozenset({'Baron','Heretic'}),"text":'Only 1 jinxed character can be in play.',"type":'restriction'},
    {"chars":frozenset({'Godfather','Heretic'}),"text":'Only 1 jinxed character can be in play.',"type":'restriction'},
    {"chars":frozenset({'Heretic','Lleech'}),"text":'Only 1 jinxed character can be in play.',"type":'restriction'},
    {"chars":frozenset({'Heretic','Pit-Hag'}),"text":'Only 1 jinxed character can be in play.',"type":'restriction'},
    {"chars":frozenset({'Heretic','Spy'}),"text":'Only 1 jinxed character can be in play.',"type":'restriction'},
    {"chars":frozenset({'Heretic','Widow'}),"text":'Only 1 jinxed character can be in play.',"type":'restriction'},
    {"chars":frozenset({'Baron','Plague Doctor'}),"text":'If the Storyteller would gain the Baron ability, up to two players become Outsiders.'},
    {"chars":frozenset({'Boomdandy','Plague Doctor'}),"text":'If the Storyteller would gain the Boomdandy ability, a player becomes the Boomdandy.'},
    {"chars":frozenset({'Evil Twin','Plague Doctor'}),"text":'If the Storyteller would gain the Evil Twin ability, a player becomes the Evil Twin.'},
    {"chars":frozenset({'Fearmonger','Plague Doctor'}),"text":'If the Storyteller would gain the Fearmonger ability, a Minion gains it, and learns this.'},
    {"chars":frozenset({'Goblin','Plague Doctor'}),"text":'If the Storyteller would gain the Goblin ability, a Minion gains it, and learns this.'},
    {"chars":frozenset({'Marionette','Plague Doctor'}),"text":"If the Storyteller would gain the Marionette ability, one of the Demon's good neighbors becomes the Marionette."},
    {"chars":frozenset({'Plague Doctor','Scarlet Woman'}),"text":'If the Storyteller would gain the Scarlet Woman ability, a Minion gains it, and learns this.'},
    {"chars":frozenset({'Plague Doctor','Spy'}),"text":'If the Storyteller would gain the Spy ability, a Minion gains it, and learns this.'},
    {"chars":frozenset({'Plague Doctor','Wraith'}),"text":'If the Storyteller would gain the Wraith ability, a Minion gains it, and learns this.'},
    {"chars":frozenset({'Ogre','Recluse'}),"text":'If the Recluse registers as evil to the Ogre, the Ogre learns that they are evil.'},
    {"chars":frozenset({'Recluse','Sage'}),"text":'The Recluse might register as the Demon to the Sage.'},
    {"chars":frozenset({'Boffin','Cult Leader'}),"text":"If the Demon has the Cult Leader ability, they can't turn good due to this ability."},
    {"chars":frozenset({'Boffin','Drunk'}),"text":'The Demon cannot have the Drunk ability.',"type":'restriction'},
    {"chars":frozenset({'Boffin','Goon'}),"text":"If the Demon has the Goon ability, they can't turn good due to this ability."},
    {"chars":frozenset({'Boffin','Heretic'}),"text":'The Demon cannot have the Heretic ability.',"type":'restriction'},
    {"chars":frozenset({'Boffin','Ogre'}),"text":'The Demon cannot have the Ogre ability.',"type":'restriction'},
    {"chars":frozenset({'Boffin','Politician'}),"text":'The Demon cannot have the Politician ability.',"type":'restriction'},
    {"chars":frozenset({'Boffin','Village Idiot'}),"text":'If there is a spare token, the Boffin can give the Demon the Village Idiot ability.'},
    {"chars":frozenset({'Cerenovus','Goblin'}),"text":'The Cerenovus may choose to make a player mad that they are the Goblin.'},
    {"chars":frozenset({'Balloonist','Marionette'}),"text":'If the Marionette thinks that they are the Balloonist, an Outsider might have been added during setup.'},
    {"chars":frozenset({'Huntsman','Marionette'}),"text":'If the Marionette thinks that they are the Huntsman, the Damsel was added during setup.'},
    {"chars":frozenset({'Kazali','Marionette'}),"text":'If there would be a Marionette in play, they enter play after the Demon & must start as their neighbor.'},
    {"chars":frozenset({"Lil' Monsta",'Marionette'}),"text":'If there would be a Marionette in play, they enter play after the Demon & must start as their neighbor.'},
    {"chars":frozenset({'Marionette','Summoner'}),"text":'If there would be a Marionette in play, they enter play after the Demon & must start as their neighbor.'},
    {"chars":frozenset({'Mastermind','Vigormortis'}),"text":'A Mastermind that has their ability keeps it if the Vigormortis dies.'},
    {"chars":frozenset({'Cult Leader','Pit-Hag'}),"text":"If the Pit-Hag turns an evil player into the Cult Leader, they can't turn good due to their own ability."},
    {"chars":frozenset({'Damsel','Pit-Hag'}),"text":'If a Pit-Hag creates a Damsel, the Storyteller chooses which player it is.'},
    {"chars":frozenset({'Goon','Pit-Hag'}),"text":"If the Pit-Hag turns an evil player into the Goon, they can't turn good due to their own ability."},
    {"chars":frozenset({'Ogre','Pit-Hag'}),"text":"If the Pit-Hag turns an evil player into the Ogre, they can't turn good due to their own ability."},
    {"chars":frozenset({'Pit-Hag','Politician'}),"text":"If the Pit-Hag turns an evil player into the Politician, they can't turn good due to their own ability."},
    {"chars":frozenset({'Pit-Hag','Village Idiot'}),"text":'If there is a spare token, the Pit-Hag can create an extra Village Idiot. If so, the drunk Village Idiot might change.'},
    {"chars":frozenset({'Al-Hadikhia','Scarlet Woman'}),"text":'If there would be two Demons, one of which was the Scarlet Woman, the Scarlet Woman becomes the Scarlet Woman again.'},
    {"chars":frozenset({'Fang Gu','Scarlet Woman'}),"text":'If there would be two Demons, one of which was the Scarlet Woman, the Scarlet Woman remains the Scarlet Woman.'},
    {"chars":frozenset({'Damsel','Spy'}),"text":'If the Spy is (or has been) in play, the Damsel is poisoned.',"hook_id":'spy_damsel_poisoned'},
    {"chars":frozenset({'Ogre','Spy'}),"text":'The Spy registers as evil to the Ogre.'},
    {"chars":frozenset({'Poppy Grower','Spy'}),"text":'If the Poppy Grower has their ability, the Spy does not see the Grimoire.',"hook_id":'spy_sees_grimoire'},
    {"chars":frozenset({'Clockmaker','Summoner'}),"text":'The Summoner registers as the Demon to the Clockmaker.'},
    {"chars":frozenset({'Courtier','Summoner'}),"text":'If the living Summoner has no ability, the Storyteller has the Summoner ability.'},
    {"chars":frozenset({'Engineer','Summoner'}),"text":'If the living Summoner is removed from play, the Storyteller has the Summoner ability.'},
    {"chars":frozenset({'Hatter','Summoner'}),"text":'If the Summoner creates a second living Demon, deaths tonight are arbitrary.'},
    {"chars":frozenset({'Kazali','Summoner'}),"text":'If the Summoner creates a second living Demon, deaths tonight are arbitrary.'},
    {"chars":frozenset({'Lord of Typhon','Summoner'}),"text":'If a Lord of Typhon is summoned, they must neighbor a Minion & their other neighbor becomes an evil Minion.'},
    {"chars":frozenset({'Pit-Hag','Summoner'}),"text":'If the Summoner creates a second living Demon, deaths tonight are arbitrary.'},
    {"chars":frozenset({'Poppy Grower','Summoner'}),"text":'If the Poppy Grower is alive on the 3rd night, the Summoner chooses which Demon but not which player.'},
    {"chars":frozenset({'Preacher','Summoner'}),"text":'If the living Summoner has no ability, the Storyteller has the Summoner ability.'},
    {"chars":frozenset({'Pukka','Summoner'}),"text":'The Summoner may summon a Pukka on the 2nd night instead of the 3rd.'},
    {"chars":frozenset({'Summoner','Zombuul'}),"text":'If the Summoner summons a dead player into the Zombuul, the Zombuul has already died once.'},
    {"chars":frozenset({'Alsaahir','Vizier'}),"text":"The Storyteller doesn't declare the Vizier is in play."},
    {"chars":frozenset({'Courtier','Vizier'}),"text":'If the Vizier loses their ability, they learn this, and cannot die during the day.'},
    {"chars":frozenset({'Fearmonger','Vizier'}),"text":'The Vizier wakes with the Fearmonger, learns who they choose and cannot choose to immediately execute that player.'},
    {"chars":frozenset({'Investigator','Vizier'}),"text":"The Storyteller doesn't declare the Vizier is in play."},
    {"chars":frozenset({'Politician','Vizier'}),"text":'The Politician might register as evil to the Vizier.'},
    {"chars":frozenset({'Preacher','Vizier'}),"text":'If the Vizier loses their ability, they learn this, and cannot die during the day.'},
    {"chars":frozenset({'Vizier','Zealot'}),"text":'The Zealot might register as evil to the Vizier.'},
    {"chars":frozenset({'Damsel','Widow'}),"text":'If the Widow is (or has been) in play, the Damsel is poisoned.',"hook_id":'widow_damsel_poisoned'},
    {"chars":frozenset({'Poppy Grower','Widow'}),"text":'If the Poppy Grower has their ability, the Widow does not see the Grimoire.',"hook_id":'widow_sees_grimoire'},
    {"chars":frozenset({'Al-Hadikhia','Princess'}),"text":'If the Princess nominated & executed a player on their 1st day, no one dies to the Al-Hadikhia tonight.'},
    {"chars":frozenset({'Al-Hadikhia','Mastermind'}),"text":'If the Al-Hadikhia dies by execution, and the Mastermind is alive, the Al-Hadikhia chooses 3 good players tonight: if all 3 choose to live, evil wins. Otherwise, good wins.'},
    {"chars":frozenset({'Engineer','Legion'}),"text":'If Legion is created, all evil players become Legion. If Legion is in play, the Engineer starts knowing this but has no ability.'},
    {"chars":frozenset({'Hatter','Legion'}),"text":'If Legion is created, all evil players become Legion. If Legion is in play, the Hatter has no ability.'},
    {"chars":frozenset({'Legion','Minstrel'}),"text":'If Legion died by execution today, Legion keeps their ability, but the Minstrel might learn they are Legion.'},
    {"chars":frozenset({'Legion','Politician'}),"text":'The Politician might register as evil to Legion.'},
    {"chars":frozenset({'Legion','Preacher'}),"text":'If the Preacher chooses Legion, Legion keeps their ability, but the Preacher might learn they are Legion.'},
    {"chars":frozenset({'Legion','Summoner'}),"text":'If Legion is summoned, all evil players become Legion.'},
    {"chars":frozenset({'Legion','Zealot'}),"text":'The Zealot might register as evil to Legion.'},
    {"chars":frozenset({'Banshee','Leviathan'}),"text":'Each night*, the Leviathan chooses an alive good player (different to previous nights): a chosen Banshee dies & gains their ability.'},
    {"chars":frozenset({'Exorcist','Leviathan'}),"text":'If the Leviathan nominates and executes the Exorcist-chosen player, good wins.'},
    {"chars":frozenset({'Farmer','Leviathan'}),"text":'Each night*, the Leviathan chooses an alive good player (different to previous nights): a chosen Farmer uses their ability but does not die.'},
    {"chars":frozenset({'Grandmother','Leviathan'}),"text":'If the Leviathan is in play and the Grandchild dies by execution, evil wins.'},
    {"chars":frozenset({'Hatter','Leviathan'}),"text":'The Leviathan cannot enter play after day 5.',"type":'restriction'},
    {"chars":frozenset({'Innkeeper','Leviathan'}),"text":'If the Leviathan nominates and executes an Innkeeper-protected player, good wins.'},
    {"chars":frozenset({'King','Leviathan'}),"text":'If the Leviathan is in play, and at least 1 player is dead, the King learns an alive character each night.'},
    {"chars":frozenset({'Leviathan','Mayor'}),"text":'If the Leviathan and the Mayor are alive on day 5 & no execution occurs, good wins.'},
    {"chars":frozenset({'Leviathan','Monk'}),"text":'If the Leviathan nominates and executes the Monk-protected player, good wins.'},
    {"chars":frozenset({'Leviathan','Pit-Hag'}),"text":'The Leviathan cannot enter play after day 5.',"type":'restriction'},
    {"chars":frozenset({'Leviathan','Ravenkeeper'}),"text":'Each night*, the Leviathan chooses an alive player (different to previous nights): a chosen Ravenkeeper uses their ability but does not die.'},
    {"chars":frozenset({'Leviathan','Sage'}),"text":'Each night*, the Leviathan chooses an alive good player (different to previous nights): a chosen Sage uses their ability but does not die.'},
    {"chars":frozenset({'Leviathan','Soldier'}),"text":'If the Leviathan nominates and executes the Soldier, good wins.'},
    {"chars":frozenset({'Hatter',"Lil' Monsta"}),"text":"If the Hatter dies & the Demon chooses Lil' Monsta, they also choose a Minion to become."},
    {"chars":frozenset({"Lil' Monsta",'Poppy Grower'}),"text":"If Lil' Monsta & the Poppy Grower are alive, Minions wake one by one, until one of them chooses to take the Lil' Monsta token."},
    {"chars":frozenset({"Lil' Monsta",'Psychopath'}),"text":"If the Psychopath is babysitting Lil' Monsta, they die when executed."},
    {"chars":frozenset({"Lil' Monsta",'Magician'}),"text":"If the Magician is alive, the Storyteller chooses which Minion babysits Lil' Monsta."},
    {"chars":frozenset({"Lil' Monsta",'Scarlet Woman'}),"text":"If Lil' Monsta dies with 5 or more players alive, the Scarlet Woman babysits Lil' Monsta for the rest of the game.","hook_id":'lm_sw_transfer'},
    {"chars":frozenset({"Lil' Monsta",'Vizier'}),"text":"If the Vizier is babysitting Lil' Monsta, they die when executed."},
    {"chars":frozenset({'Lleech','Mastermind'}),"text":'If the Mastermind is alive and the Lleech host dies by execution, the Lleech lives but loses their ability.'},
    {"chars":frozenset({'Lleech','Slayer'}),"text":'If the Slayer slays the Lleech host, the host dies.'},
    {"chars":frozenset({'Atheist','Riot'}),"text":'During a riot, if the Storyteller is nominated, players vote. If they are about to die, the game ends. If not, they nominate again.'},
    {"chars":frozenset({'Banshee','Riot'}),"text":'Each night*, Riot chooses an alive good player (different to previous nights): a chosen Banshee dies & gains their ability.'},
    {"chars":frozenset({'Exorcist','Riot'}),"text":'If Riot nominates and executes the Exorcist-chosen player, good wins.'},
    {"chars":frozenset({'Farmer','Riot'}),"text":'Each night*, Riot chooses an alive good player (different to previous nights): a chosen Farmer uses their ability but does not die.'},
    {"chars":frozenset({'Grandmother','Riot'}),"text":'If Riot is in play and the Grandchild dies by execution, evil wins.'},
    {"chars":frozenset({'Innkeeper','Riot'}),"text":'If Riot nominates and executes an Innkeeper-protected player, good wins.'},
    {"chars":frozenset({'King','Riot'}),"text":'If Riot is in play, and at least 1 player is dead, the King learns an alive character each night.'},
    {"chars":frozenset({'Mayor','Riot'}),"text":'The Mayor may choose to stop the riot. If they do so when only 1 Riot is alive, good wins. Otherwise, evil wins.'},
    {"chars":frozenset({'Monk','Riot'}),"text":'If Riot nominates and executes the Monk-protected player, good wins.'},
    {"chars":frozenset({'Ravenkeeper','Riot'}),"text":'Each night*, Riot chooses an alive good player (different to previous nights): a chosen Ravenkeeper uses their ability but does not die.'},
    {"chars":frozenset({'Riot','Sage'}),"text":'Each night*, Riot chooses an alive good player (different to previous nights): a chosen Sage uses their ability but does not die.'},
    {"chars":frozenset({'Riot','Soldier'}),"text":'If Riot nominates and executes the Soldier, good wins.'},
    {"chars":frozenset({'Banshee','Vortox'}),"text":'If the Vortox kills the Banshee, all players learn that the Banshee has died.'},
    {"chars":frozenset({'Exorcist','Yaggababble'}),"text":'If the Exorcist chooses the Yaggababble, the Yaggababble does not kill tonight.'},
]
JINX_HOOKS={
    "lm_sw_transfer":_hook_lm_sw_transfer,
    "spy_sees_grimoire":_hook_spy_sees_grimoire,
    "widow_sees_grimoire":_hook_widow_sees_grimoire,
    "spy_damsel_poisoned":_hook_spy_damsel_poisoned,
    "widow_damsel_poisoned":_hook_widow_damsel_poisoned,
}

def get_jinx(char_a,char_b):
    key=frozenset({char_a,char_b})
    for j in JINXES:
        if j["chars"]==key: return j
    return None

def get_jinxes_for_character(char):
    return [j for j in JINXES if char in j["chars"]]

def build_active_jinxes(g):
    """Called at game start. Scans g['script'] and stores which jinx hook_ids
    and char pairs are applicable. Also sets _spy_was_in_play / _widow_was_in_play
    if the relevant characters are already present at setup.
    """
    script = set(g.get("script", []))
    active_pairs = set()
    active_hook_ids = set()
    for j in JINXES:
        if j["chars"] <= script:
            active_pairs.add(j["chars"])
            if "hook_id" in j:
                active_hook_ids.add(j["hook_id"])
    g["_active_jinx_pairs"] = active_pairs
    g["_active_jinx_hook_ids"] = active_hook_ids
    # Initialise in-play tracking for Spy/Widow+Damsel jinxes
    if frozenset({"Spy", "Damsel"}) in active_pairs:
        if any(p["character"] == "Spy" for p in g["players"]):
            g["_spy_was_in_play"] = True
    if frozenset({"Widow", "Damsel"}) in active_pairs:
        if any(p["character"] == "Widow" for p in g["players"]):
            g["_widow_was_in_play"] = True

def jinx_hook_active(hook_id, g):
    """True if both characters for this hook are on the script."""
    return hook_id in g.get("_active_jinx_hook_ids", set())

def jinx_pair_active(char_a, char_b, g):
    """True if both characters are on the script."""
    return frozenset({char_a, char_b}) in g.get("_active_jinx_pairs", set())

def call_jinx_hook(hook_id, g, **kw):
    """Dispatch to hook only if both characters are on the script."""
    if not jinx_hook_active(hook_id, g):
        return None
    fn = JINX_HOOKS.get(hook_id)
    return fn(g, **kw) if fn is not None else None

def get_restriction_jinxes():
    return [j for j in JINXES if j.get("type") == "restriction"]

def get_active_restriction_jinxes(g):
    """Return restriction jinxes where both chars are on the script."""
    return [j for j in JINXES
            if j.get("type") == "restriction" and j["chars"] <= set(g.get("script", []))]
