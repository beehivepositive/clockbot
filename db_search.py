import sqlite3, re
DB = "/home/discord-bot/archive.db"
def get_con(): return sqlite3.connect(DB)
def is_db_query(text):
    t=text.lower()
    if re.search(r"game[ -]?[0-9]+",t): return True
    triggers=["what did","remember when","that time","quote","who said","said that","in game","look up","check the"]
    return any(x in t for x in triggers)
def search(query, max_results=10, game_num=None):
    con=get_con()
    cur=con.cursor()
    fts=re.sub(r"[^a-z0-9 ]","",query.lower()).strip()
    if not fts: return []
    if game_num:
        cur.execute("SELECT m.timestamp,m.channel,COALESCE(u.username,m.author),m.content FROM messages_fts f JOIN messages m ON f.rowid=m.id LEFT JOIN users u ON m.author=u.user_id WHERE messages_fts MATCH ? AND m.game=? ORDER BY rank LIMIT ?",(fts,str(game_num),max_results))
    else:
        cur.execute("SELECT m.timestamp,m.channel,COALESCE(u.username,m.author),m.content FROM messages_fts f JOIN messages m ON f.rowid=m.id LEFT JOIN users u ON m.author=u.user_id WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",(fts,max_results))
    rows=cur.fetchall()
    con.close()
    return rows
def context_for(query):
    gm=re.search(r"game[ -]?([0-9]+)",query.lower())
    gnum=gm.group(1) if gm else None
    rows=search(query,max_results=10,game_num=gnum)
    if not rows: return ""
    lines=["== RELEVANT SERVER HISTORY =="]
    for t,ch,a,c in rows: lines.append(f"[{str(t)[:10]}] #{ch} | {a}: {c[:300]}")
    return "\n".join(lines)+"\n\n"
