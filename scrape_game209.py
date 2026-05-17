import discord, json, asyncio, os
from datetime import datetime

try:
    TOKEN = open("/home/discord-bot/.env").read().split("DISCORD_TOKEN=")[1].split("\n")[0].strip()
except FileNotFoundError:
    from dotenv import load_dotenv
    load_dotenv()
    TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1339575347032621191
TARGET_CHANNELS = ["game209-logs", "game209-chat", "game209-focused", "game209-whisper-log"]

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
client = discord.Client(intents=intents)

def log(msg):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def serialize_message(msg):
    return {
        "id": str(msg.id),
        "author_name": msg.author.display_name,
        "author_id": str(msg.author.id),
        "timestamp": msg.created_at.isoformat(),
        "content": msg.content or "",
        "attachments": [
            {"filename": a.filename, "url": a.url, "content_type": a.content_type, "size": a.size}
            for a in msg.attachments
        ],
        "embeds": [e.to_dict() for e in msg.embeds],
        "type": str(msg.type),
    }

async def fetch_channel(ch):
    for attempt in range(5):
        try:
            messages = []
            async for msg in ch.history(limit=None, oldest_first=True):
                messages.append(serialize_message(msg))
                if len(messages) % 500 == 0:
                    log(f"  ... {len(messages)} messages")
            return messages
        except discord.HTTPException as e:
            log(f"RETRY {ch.name}: {e}")
            await asyncio.sleep(10 * (attempt + 1))
    return []

@client.event
async def on_ready():
    log(f"Logged in as {client.user}")
    guild = client.get_guild(GUILD_ID)
    if not guild:
        log("ERROR: Guild not found"); await client.close(); return

    for name in TARGET_CHANNELS:
        ch = discord.utils.get(guild.text_channels, name=name)
        if not ch:
            log(f"WARN: '{name}' not found — skipping"); continue
        log(f"Fetching '{name}'...")
        messages = await fetch_channel(ch)
        out = f"{name}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2, ensure_ascii=False)
        log(f"DONE '{name}': {len(messages)} messages -> {out}")

    log("COMPLETE"); await client.close()

client.run(TOKEN)
