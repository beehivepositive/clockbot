"""One-off: write player_common_names.json (user_id -> common name) from the
numbered list of un-named members. Reproduces the same sorted ordering that was
presented, then applies the number -> name map below. Run once, then delete.

    ./venv/bin/python apply_common_names.py
"""
import os
import json
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = "1339575347032621191"
API = "https://discord.com/api/v10"
BASE = "/home/discord-bot" if os.path.isdir("/home/discord-bot") else "."
COMMON_NAMES_PATH = os.path.join(BASE, "common_names.json")
OUT_PATH = os.path.join(BASE, "player_common_names.json")

# Number (from the presented list, 1-indexed) -> common name.
NAME_BY_INDEX = {
    2: "4o4", 3: "Dulla", 4: "Jeff", 5: "89", 6: "Baastard", 7: "Aquota",
    8: "Train", 9: "Autism", 10: "89", 11: "Dunce", 12: "Cindery", 13: "Cindery",
    14: "Cuz", 16: "Demy", 17: "Disheveled", 18: "DonationBox", 19: "Holler",
    20: "Coop", 21: "Cynka", 22: "Mith", 23: "Gdow", 24: "Diddy", 25: "Hash",
    26: "HBTZ", 27: "Carp", 28: "Bozo", 29: "Null", 30: "Bunny", 31: "Indigo",
    32: "Prolly", 33: "Cox", 34: "Bot", 35: "JC", 36: "Klenny", 37: "Klenny",
    38: "Lash", 39: "Rabbit", 40: "89", 41: "Cox", 42: "Nayshun",
    43: "Techi", 44: "Pumblechook", 45: "Pride", 46: "Pojom", 47: "Russy",
    48: "Russy", 49: "Rwkasten", 50: "Elli", 52: "Vape", 53: "Techi",
    54: "Trace", 55: "Song", 56: "Techi", 57: "Wuz", 58: "Elizabeth",
}


async def main():
    async with aiohttp.ClientSession(headers={"Authorization": f"Bot {TOKEN}"}) as s:
        async with s.get(f"{API}/guilds/{GUILD}/members?limit=1000") as r:
            members = await r.json()

    cn = json.load(open(COMMON_NAMES_PATH)) if os.path.exists(COMMON_NAMES_PATH) else {}
    covered = set(int(v) for v in cn.values())

    rows = []
    for m in members:
        u = m.get("user", {})
        if u.get("bot"):
            continue
        uid = int(u["id"])
        if uid in covered:
            continue
        rows.append((u.get("username", "?"), uid))
    rows.sort(key=lambda r: r[0].lower())

    out = json.load(open(OUT_PATH)) if os.path.exists(OUT_PATH) else {}
    added = []
    for idx, (uname, uid) in enumerate(rows, 1):
        if idx in NAME_BY_INDEX:
            out[str(uid)] = NAME_BY_INDEX[idx]
            added.append(f"  {idx:>2}  {uname:<24} -> {NAME_BY_INDEX[idx]}")

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {OUT_PATH} ({len(out)} total entries); added {len(added)}:")
    print("\n".join(added))


if __name__ == "__main__":
    asyncio.run(main())
