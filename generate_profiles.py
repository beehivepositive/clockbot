import json, random, anthropic, sqlite3
from collections import defaultdict

DB = "/home/discord-bot/archive.db"
OUT = '/home/discord-bot/player_profiles.json'
MIN_MSGS = 200
SAMPLE_SIZE = 600

key = open('/home/discord-bot/.env').read()
for line in key.split('\n'):
    if 'ANTHROPIC' in line: key = line.split('=',1)[1].strip(); break

client = anthropic.Anthropic(api_key=key)
con=sqlite3.connect(DB)
cur=con.cursor()
cur.execute("SELECT author,channel,content FROM messages")
by_player=defaultdict(list)
for a,ch,c in cur.fetchall(): by_player[a].append(f"[{ch}] {c}")
con.close()

