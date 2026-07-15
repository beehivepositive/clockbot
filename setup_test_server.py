"""One-off: scaffold the Clock Testing server to match production naming.

Creates any missing roles, the Game Logs / Game Chat / Voice / Archive categories,
and a #recruiting channel. Idempotent (skips anything that already exists).
REST-only (no gateway) so it won't conflict with the running bot.

Run once on the server:  ./venv/bin/python setup_test_server.py
Then delete it.
"""
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = "1291933524760199260"  # Clock Testing
API = "https://discord.com/api/v10"
HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

ROLES = ["Storyteller", "Ascended", "Traveler", "Tulpa", "Recluse", "Townsfolk"]
# Category order top->bottom (Archive 7 is most recent / highest in the stack).
CATEGORIES = ["Game Logs", "Game Chat", "Voice Channels",
              "Archive 7", "Archive 6", "Archive 5", "Archive 4",
              "Archive 3", "Archive 2", "Archive 1"]
TEXT_CHANNELS = ["recruiting"]


async def main():
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        async def get(path):
            async with s.get(API + path) as r:
                r.raise_for_status()
                return await r.json()

        async def post(path, body):
            async with s.post(API + path, json=body) as r:
                if r.status not in (200, 201):
                    print(f"  ! POST {path} -> {r.status}: {await r.text()}")
                    return None
                return await r.json()

        roles = await get(f"/guilds/{GUILD}/roles")
        have_roles = {r["name"].lower() for r in roles}
        for name in ROLES:
            if name.lower() in have_roles:
                print(f"role exists: {name}")
                continue
            await post(f"/guilds/{GUILD}/roles", {"name": name})
            print(f"created role: {name}")
            await asyncio.sleep(0.3)

        chans = await get(f"/guilds/{GUILD}/channels")
        cats_by_name = {c["name"].lower(): c for c in chans if c["type"] == 4}
        created_cats = {}
        for name in CATEGORIES:
            if name.lower() in cats_by_name:
                print(f"category exists: {name}")
                continue
            ctype = 4
            body = {"name": name, "type": ctype}
            res = await post(f"/guilds/{GUILD}/channels", body)
            if res:
                created_cats[name] = res
                print(f"created category: {name}")
            await asyncio.sleep(0.3)

        # Refresh and set category positions to match the intended order.
        chans = await get(f"/guilds/{GUILD}/channels")
        cats_by_name = {c["name"].lower(): c for c in chans if c["type"] == 4}
        positions = []
        base = 1  # leave position 0 for any existing "Text Channels"
        for i, name in enumerate(CATEGORIES):
            c = cats_by_name.get(name.lower())
            if c:
                positions.append({"id": c["id"], "position": base + i})
        if positions:
            async with s.patch(API + f"/guilds/{GUILD}/channels", json=positions) as r:
                print("set category positions:", r.status)

        # Recruiting text channel (no category needed).
        have_text = {c["name"].lower() for c in chans if c["type"] == 0}
        for name in TEXT_CHANNELS:
            if name.lower() in have_text:
                print(f"channel exists: #{name}")
                continue
            await post(f"/guilds/{GUILD}/channels", {"name": name, "type": 0})
            print(f"created channel: #{name}")
            await asyncio.sleep(0.3)

    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
