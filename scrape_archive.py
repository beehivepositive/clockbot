import discord,sqlite3,asyncio,re,os
from datetime import datetime
TOKEN=open("/home/discord-bot/.env").read().split("DISCORD_TOKEN=")[1].split("\n")[0].strip()
DB="/home/discord-bot/archive.db"
GUILD_ID=1339575347032621191
intents=discord.Intents.default()
intents.message_content=True
intents.guilds=True
client=discord.Client(intents=intents)
def log(msg):
    ts=datetime.utcnow().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}",flush=True)
def gg(ch):
    if "pridegame" in ch: return "pridegame"
    m=re.search(r"game-?([a-z0-9]+(?:-rerack)?)",ch)
    return m.group(1) if m else None
def get_done_channels():
    con=sqlite3.connect(DB); cur=con.cursor()
    cur.execute("SELECT DISTINCT channel FROM messages")
    done={r[0] for r in cur.fetchall()}; con.close(); return done
async def fetch_and_save(ch):
    for attempt in range(5):
        try:
            rows=[]
            users=[]
            async for m in ch.history(limit=None,oldest_first=True):
                if m.author.bot or not m.content.strip(): continue
                rows.append((ch.name,gg(ch.name),str(m.author.id),m.content.strip(),m.created_at.isoformat()))
                users.append((str(m.author.id),m.author.name))
            con=sqlite3.connect(DB); cur=con.cursor()
            cur.executemany("INSERT OR IGNORE INTO users(user_id,username)VALUES(?,?)",users)
            cur.executemany("INSERT INTO messages(channel,game,author,content,timestamp)VALUES(?,?,?,?,?)",rows)
            if rows:
                cur.execute("INSERT INTO messages_fts(rowid,content,author,channel,game) SELECT id,content,author,channel,game FROM messages WHERE channel=?",(ch.name,))
            con.commit(); con.close(); return len(rows)
        except discord.HTTPException as e:
            log(f"RETRY {ch.name}: {e}"); await asyncio.sleep(10*(attempt+1))
    return 0
@client.event
async def on_ready():
    guild=client.get_guild(GUILD_ID)
    done=get_done_channels()
    chs=sorted([c for c in guild.text_channels if c.category and "archive" in c.category.name.lower()],key=lambda c:(c.category.name,c.position))
    log(f"Found {len(chs)} channels, {len(done)} done")
    for i,ch in enumerate(chs):
        if ch.name in done: log(f"SKIP {ch.name}"); continue
        log(f"[{i+1}/{len(chs)}] {ch.name}")
        n=await fetch_and_save(ch)
        log(f"DONE {ch.name}: {n}")
    log("COMPLETE"); await client.close()
client.run(TOKEN)
