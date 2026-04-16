import json,sqlite3,re,os
SRC="/home/discord-bot/archive_messages.json"
DEST="/home/discord-bot/archive.db"
def gg(ch):
    if "pridegame" in ch: return "pridegame"
    m=re.search(r"game-?([a-z0-9]+(?:-rerack)?)",ch)
    return m.group(1) if m else None
data=json.load(open(SRC))
print(f"{len(data)} channels, {sum(len(v) for v in data.values()):,} msgs")
if os.path.exists(DEST): os.remove(DEST)
con=sqlite3.connect(DEST)
cur=con.cursor()
cur.executescript("""
CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,channel TEXT NOT NULL,game TEXT,author TEXT NOT NULL,content TEXT NOT NULL,timestamp TEXT);
CREATE INDEX idx_author ON messages(author);
CREATE INDEX idx_game ON messages(game);
CREATE INDEX idx_channel ON messages(channel);
CREATE INDEX idx_ts ON messages(timestamp);
CREATE VIRTUAL TABLE messages_fts USING fts5(content,author,channel,game,content="messages",content_rowid="id");
""")
rows=[(ch,gg(ch),m.get("a",""),m.get("c",""),m.get("t","")) for ch,msgs in data.items() for m in msgs if m.get("a") and m.get("c")]
cur.executemany("INSERT INTO messages(channel,game,author,content,timestamp)VALUES(?,?,?,?,?)",rows)
print(f"Inserted {len(rows):,} rows")
print("Building FTS index...")
cur.execute("INSERT INTO messages_fts(rowid,content,author,channel,game) SELECT id,content,author,channel,game FROM messages")
con.commit()
con.close()
print(f"Done. {os.path.getsize(DEST)/1024/1024:.1f} MB")
