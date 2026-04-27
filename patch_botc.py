with open("/home/discord-bot/botc_logic.py","r") as fh:
    src=fh.read()

# CHANGE 1: insert _heretic_flip before check_win_conditions
new1 = (
    "def _heretic_flip(g):\n"
    "    \"\"\"Returns True if the win result should be flipped (odd number of active Heretic abilities).\n"
    "    Counts actual Heretic players, Philosopher-as-Heretic, and Cannibal-as-Heretic.\"\"\"\n"
    "    count = 0\n"
    "    for p in g[\"players\"]:\n"
    "        if p[\"character\"] == \"Heretic\" and not is_drunk_or_poisoned(p, g):\n"
    "            count += 1\n"
    "        elif (p[\"character\"] == \"Philosopher\" and p[\"alive\"]\n"
    "              and not is_drunk_or_poisoned(p, g)\n"
    "              and p[\"tokens\"].get(\"copied_character\") == \"Heretic\"):\n"
    "            count += 1\n"
    "    can = get_character(g, \"Cannibal\")\n"
    "    if (can and can[\"alive\"] and not is_drunk_or_poisoned(can, g)\n"
    "            and g.get(\"_cannibal_told_character\") == \"Heretic\"):\n"
    "        count += 1\n"
    "    return count % 2 == 1\n"
    "\n"
    "def check_win_conditions(g):"
)
assert "def check_win_conditions(g):" in src, "C1: anchor not found"
src=src.replace("def check_win_conditions(g):",new1,1)
assert "def _heretic_flip(g):" in src, "C1 fail"
print("C1 OK")

# CHANGE 2a: fix Leviathan + good_t/evil_t block
old2a=(
    "    lv=get_character(g,\"Leviathan\")\n"
    "    if lv and lv[\"alive\"]:\n"
    "        if g.get(\"_good_executions\",0)>1: evil_t.append(\"Leviathan\")\n"
    "        if g.get(\"night\",0)>=5 and g.get(\"_day_ended\"): evil_t.append(\"Leviathan day5\")\n"
    "    if good_t or evil_t:\n"
    "        res=GOOD if good_t else EVIL\n"
    "        h=get_character(g,\"Heretic\")\n"
    "        if h and not is_drunk_or_poisoned(h,g):res=EVIL if res==GOOD else GOOD\n"
    "        return res"
)
new2a=(
    "    lv=get_character(g,\"Leviathan\")\n"
    "    if lv and lv[\"alive\"] and not is_drunk_or_poisoned(lv,g):\n"
    "        if g.get(\"_good_executions\",0)>1: evil_t.append(\"Leviathan\")\n"
    "        if g.get(\"night\",0)>=5 and g.get(\"_day_ended\"): evil_t.append(\"Leviathan day5\")\n"
    "    if good_t or evil_t:\n"
    "        res=GOOD if good_t else EVIL\n"
    "        if _heretic_flip(g): res=EVIL if res==GOOD else GOOD\n"
    "        return res"
)
assert old2a in src, "C2a old not found"
src=src.replace(old2a,new2a,1)
assert new2a in src, "C2a fail"
print("C2a OK")

# CHANGE 2b: inline Heretic EVIL pattern
old2b="_h=get_character(g,\"Heretic\");return EVIL if _h and not is_drunk_or_poisoned(_h,g) else GOOD"
new2b="return EVIL if _heretic_flip(g) else GOOD"
cnt=src.count(old2b)
assert cnt>0, "C2b not found"
src=src.replace(old2b,new2b)
print("C2b OK replaced",cnt)

# CHANGE 2c: inline Heretic GOOD pattern
old2c="_h=get_character(g,\"Heretic\");return GOOD if _h and not is_drunk_or_poisoned(_h,g) else EVIL"
new2c="return GOOD if _heretic_flip(g) else EVIL"
cnt=src.count(old2c)
assert cnt>0, "C2c not found"
src=src.replace(old2c,new2c)
print("C2c OK replaced",cnt)

# CHANGE 2d: Cult Leader block in check_win_conditions
old2d=(
    "            _h=get_character(g,\"Heretic\")\n"
    "            res=cl[\"alignment\"]\n"
    "            return (EVIL if res==GOOD else GOOD) if _h and not is_drunk_or_poisoned(_h,g) else res"
)
new2d=(
    "            res=cl[\"alignment\"]\n"
    "            if _heretic_flip(g): res=EVIL if res==GOOD else GOOD\n"
    "            return res"
)
assert old2d in src, "C2d not found"
src=src.replace(old2d,new2d,1)
assert new2d in src, "C2d fail"
print("C2d OK")

# CHANGE 2e: resolve_cult_vote
old2e=(
    "    h = get_character(g, \"Heretic\")\n"
    "    if h and not is_drunk_or_poisoned(h, g): res = EVIL if res == GOOD else GOOD"
)
new2e="    if _heretic_flip(g): res = EVIL if res == GOOD else GOOD"
assert old2e in src, "C2e not found"
src=src.replace(old2e,new2e,1)
assert new2e in src, "C2e fail"
print("C2e OK")

with open("/home/discord-bot/botc_logic.py","w") as fh:
    fh.write(src)
print("File written, len=",len(src))
