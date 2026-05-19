"""Force-register all slash commands to a specific guild via Discord REST API."""
import asyncio, aiohttp, base64, json

TOKEN = "YOUR_BOT_TOKEN_HERE"  # set via environment variable or config
GUILD_ID = 1339575347032621191

# Decode application ID from token (first segment is base64-encoded bot user ID)
APP_ID = int(base64.b64decode(TOKEN.split(".")[0] + "==").decode())

# Full list of commands to register on the guild
COMMANDS = [
    {
        "name": "convertscript",
        "description": "Convert a clocktower.live game state JSON into script tool format",
        "options": [
            {"name": "game_state", "description": "The clocktower.live JSON (paste the full object)", "type": 3, "required": True},
            {"name": "name", "description": "Override the script name", "type": 3, "required": False},
            {"name": "author", "description": "Override the author", "type": 3, "required": False},
        ],
    },
]

async def main():
    url = f"https://discord.com/api/v10/applications/{APP_ID}/guilds/{GUILD_ID}/commands"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        # PUT replaces the entire guild command list atomically
        async with session.put(url, headers=headers, json=COMMANDS) as r:
            data = await r.json()
            if r.status in (200, 201):
                print(f"Registered {len(data)} commands to guild {GUILD_ID}:")
                for cmd in data:
                    print(f"  /{cmd['name']} — {cmd['description']}")
            else:
                print(f"Error {r.status}:", json.dumps(data, indent=2))

asyncio.run(main())
