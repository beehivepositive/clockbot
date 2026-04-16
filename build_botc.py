import json
d={}
d["character_types"]={}
ct=d["character_types"]
ct["townsfolk"]={"alignment":"good","description":"Core good team. Abilities designed to find and eliminate evil."}
ct["outsider"]={"alignment":"good","description":"Good players whose abilities often hinder the good team."}
ct["minion"]={"alignment":"evil","description":"Evil support. Know the Demon and each other on night 1."}
ct["demon"]={"alignment":"evil","description":"Primary evil. Good wins by executing the Demon.","notes":"One Demon per game. Exceptions: Pit-Hag, Fang Gu."}
ct["traveler"]={"alignment":"storyteller_assigned","description":"Optional external characters. ST assigns alignment. Character known to all, alignment unknown.","notes":["Removed via exile not execution (normally).","Can be executed by abilities e.g. Cerenovus.","Exile does not count as the day execution."]}
d["phases"]={}
ph=d["phases"]
ph["night"]={"description":"Players close eyes. ST wakes players in canonical night order.","notes":["Canonical night order determines sequence of ability triggers.","Night order matters mechanically — earlier abilities can affect later ones.","First night has separate order for night-1-only roles.","Demon kills one player per night unless prevented."]}
ph["day"]={"description":"Players discuss, whisper, nominate, vote, execute.","notes":["Some abilities trigger during the day e.g. Savant.","Some trigger during nomination phase e.g. Witch, Golem, Psychopath.","One execution per day max (Butcher traveler exception).","Execution ends day and moves to night."]}
d["mechanics"]={}
m=d["mechanics"]
m["nominations"]={"rules":["Any number of nominations per day.","Each living player may nominate once per day.","Each player may only be nominated once per day.","Dead players generally cannot nominate.","Exile is NOT a nomination — does not trigger Witch etc."],"exceptions":["Banshee: if killed by Demon, can nominate twice and vote twice as a dead player."]}
m["voting"]={"rules":["Votes needed = ceil(living_players / 2).","E.g. 12 alive = 6 votes, 11 alive = 6 votes (rounds up).","Dead players retain one ghost vote — single use, consumed on use.","Ghost votes cannot be used in exile votes.","Player with most votes at day end is executed if threshold met.","Tie unresolved by day end = no execution."],"exceptions":["Banshee: votes twice as dead player if killed by Demon.","Butler: can only vote if Master voted first that nomination."]}
m["execution"]={"rules":["One execution per day maximum.","Execution ends the day and triggers night.","Normally occurs at end of day after voting.","Can occur at night via abilities e.g. Cerenovus.","Travelers cannot be executed via normal nomination — they are exiled.","Travelers CAN be executed by abilities, bypassing exile."],"exceptions":["Butcher (traveler): allows a second execution after the first."]}
m["exile"]={"rules":["Exile is the mechanic to remove travelers.","Requires votes >= 50% of ALL players (living and dead).","Ghost votes count toward exile threshold but are NOT consumed.","Exile is NOT a nomination — does not trigger Witch etc.","Exile does not count as the day execution.","Exiled traveler is removed from the game."]}
m["death"]={"living":{"can_nominate":True,"can_vote":True},"dead":{"can_nominate":False,"can_vote":True,"ghost_vote":"one use, consumed on use, cannot be used for exile","ability_active":False,"notes":"Dead players generally lose their ability on death."},"exceptions":["Banshee: killed by Demon = nominate twice, vote twice as dead player.","Vigormortis: dead Minions retain their abilities.","Sweetheart: when dead, one player becomes permanently drunk.","Moonchild: when dead, can curse a player publicly to die.","Klutz: when dead, must pick a player publicly — if evil, good team loses."]}
m["drunk_and_poisoned"]={"effect":"Affected character ability malfunctions. May receive false info or active ability fails.","st_discretion":"ST decides false info given. Can be true, but intent is to harm the affected player team.","drunk_source":"Passive state or own role (e.g. Drunk outsider, Sailor target, Philosopher).","poisoned_source":"Another character actively targeting them (e.g. Poisoner, No Dashii, Vigormortis).","mechanical_difference":"None — effect is identical regardless of source.","notes":["Drunk/poisoned player usually does not know they are affected.","Does not carry over between nights unless source persists."]}
m["win_conditions"]={"good_default":"Good team wins by successfully executing the Demon.","evil_default":"Evil wins when only 2 players remain alive with the Demon among them.","notes":["Many characters create alternate or modified win conditions.","Examples: Evil Twin, Klutz, Saint, Vortox, Mayor, Mastermind, Mutant — covered per character."]}
d["characters"]={}
open("/home/discord-bot/botc_data.json","w").write(__import__("json").dumps(d,indent=2))
print("done")
