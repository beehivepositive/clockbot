"""One-off: delete Archive 1-7 categories and their channels on Blood on the
Mottetower 3 ONLY. Hard safety guards prevent running against any other guild.
Run once, then delete.
"""
import os
import re
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = "1530382515754242088"          # Blood on the Mottetower 3
PROD = "1339575347032621191"           # Blood on the Mottetower 2 — must NEVER be touched
EXPECTED_NAME = "Blood on the Mottetower 3"
API = "https://discord.com/api/v10"

assert GUILD != PROD, "ABORT: target equals the production guild id"


async def main():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        # Guard 1: verify the guild name matches exactly before doing anything.
        async with s.get(f"{API}/guilds/{GUILD}") as r:
            g = await r.json()
        if g.get("name") != EXPECTED_NAME:
            print(f"ABORT: guild {GUILD} is {g.get('name')!r}, expected {EXPECTED_NAME!r}")
            return
        print(f"verified target: {g['name']} ({GUILD})")

        async with s.get(f"{API}/guilds/{GUILD}/channels") as r:
            chans = await r.json()

        # Guard 2: only categories named exactly "Archive 1".."Archive 7".
        arch_ids = {c["id"] for c in chans
                    if c["type"] == 4 and re.fullmatch(r"archive [1-7]", c["name"].lower().strip())}
        children = [c for c in chans if c.get("parent_id") in arch_ids]
        # Guard 3: never touch the live categories.
        keep = {"game logs", "game chat", "text channels", "voice channels"}
        for c in children + [x for x in chans if x["id"] in arch_ids]:
            assert c["name"].lower() not in keep, f"ABORT: refusing to delete {c['name']!r}"

        targets = [c["id"] for c in children] + list(arch_ids)  # children first, then the categories
        print(f"will delete {len(children)} channels + {len(arch_ids)} categories = {len(targets)}")

        deleted, failed = 0, []
        for cid in targets:
            while True:
                async with s.delete(f"{API}/channels/{cid}") as r:
                    if r.status == 429:
                        j = await r.json()
                        await asyncio.sleep(float(j.get("retry_after", 1)) + 0.5)
                        continue
                    if r.status in (200, 204):
                        deleted += 1
                    else:
                        failed.append((cid, r.status, (await r.text())[:120]))
                    break
            await asyncio.sleep(0.4)
            if deleted % 25 == 0:
                print(f"  ...{deleted}/{len(targets)}")

        print(f"DONE. deleted {deleted}/{len(targets)}; failed {len(failed)}")
        for f in failed[:10]:
            print("  fail", f)


if __name__ == "__main__":
    asyncio.run(main())
