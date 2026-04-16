import sqlite3,re
from collections import defaultdict
DB="/home/discord-bot/archive.db"
WORDS=["fuck","shit","ass","damn","bitch","crap","hell","bastard","cunt","dick","piss","retard"]
con=sqlite3.connect(DB)
cur=con.cursor()
cur.execute("SELECT author,content FROM messages")
counts=defaultdict(lambda:defaultdict(int))
totals=defaultdict(int)
msgc=defaultdict(int)
for author,content in cur:
    msgc[author]+=1
    low=content.lower()
    for w in WORDS:
        n=len(re.findall(r"\b"+w+r"\w*",low))
        if n: counts[author][w]+=n; totals[author]+=n
con.close()
all_players=set(msgc.keys())|set(totals.keys())
rows=[]
for p in all_players:
    t=totals[p]; m=msgc[p]
    ratio=t/m if m else 0
    rows.append((p,t,m,ratio))
MIN_MSGS=200
rows=[(p,t,m,r) for p,t,m,r in rows if m>=MIN_MSGS]
rows.sort(key=lambda x:-counts[x[0]].get("fuck",0))
print(f"{"Player":<26} {"Total":>7} {"Msgs":>7} {"Per Msg":>8}  "+"  ".join(f"{w[:5]:>5}" for w in WORDS))
print("-"*115)
for p,t,m,r in rows:
    wc="  ".join(f"{counts[p].get(w,0):>5}" for w in WORDS)
    print(f"{p:<26} {t:>7} {m:>7} {r:>8.3f}  {wc}")
