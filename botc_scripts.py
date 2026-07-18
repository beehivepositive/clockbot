"""Script library commands for the BotC bot.

Commands (all names except /addscript also accept a numeric script ID):
  /addscript      Add a script: name + character sheet + night order (+ JSON file or text).
  /myscripts      List the scripts you uploaded.
  /allscripts     List every script: ID, name, uploader, date, average rating /10.
  /ratescript     Rate a script 1-10 (once per person per script; re-rating updates).
  /script         Return a script's two images and its JSON.
  /deletescript   Delete a script (own only, unless you have the Clockmaker role).
  /renamescript   Rename a script (own only, unless you have the Clockmaker role).
  /seatingjson    Build a clocktower.live game-state JSON seating the current players
                  (Townsfolk role, minus Storyteller).

Storage: SQLite (botc_scripts.db) for metadata + ratings; image bytes on disk under
script_data/. Discord attachment URLs expire, so images are downloaded and stored.
"""

import os
import io
import json
import sqlite3
import datetime
import discord
from discord import app_commands

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

_BASE = "/home/discord-bot" if os.path.isdir("/home/discord-bot") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE, "botc_scripts.db")
IMG_DIR = os.path.join(_BASE, "script_data")
os.makedirs(IMG_DIR, exist_ok=True)

CLOCKMAKER_ROLE = "Clockmaker"
TOWNSFOLK_ROLE = "Townsfolk"
STORYTELLER_ROLE = "Storyteller"


# --------------------------------------------------------------------------
# DB helpers
# --------------------------------------------------------------------------

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS scripts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT COLLATE NOCASE UNIQUE NOT NULL,
                json        TEXT NOT NULL,
                uploader_id   INTEGER NOT NULL,
                uploader_name TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                char_path   TEXT,
                night_path  TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                script_id INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                rating    INTEGER NOT NULL,
                PRIMARY KEY (script_id, user_id)
            )
        """)


def get_script(name_or_id):
    """Resolve by numeric ID (if all digits) or by name (case-insensitive)."""
    with _conn() as c:
        key = str(name_or_id).strip()
        if key.isdigit():
            row = c.execute("SELECT * FROM scripts WHERE id=?", (int(key),)).fetchone()
            if row:
                return dict(row)
        row = c.execute("SELECT * FROM scripts WHERE name=? COLLATE NOCASE", (key,)).fetchone()
        return dict(row) if row else None


def script_avg_rating(script_id):
    with _conn() as c:
        row = c.execute("SELECT AVG(rating) a, COUNT(*) n FROM ratings WHERE script_id=?",
                        (script_id,)).fetchone()
        return (row["a"], row["n"])


def _rating_str(script_id):
    avg, n = script_avg_rating(script_id)
    return f"{avg:.1f}/10 ({n})" if n else "unrated"


# --------------------------------------------------------------------------
# Misc helpers
# --------------------------------------------------------------------------

def has_clockmaker(member):
    return any(r.name.lower() == CLOCKMAKER_ROLE.lower() for r in getattr(member, "roles", []))


def _ext(filename, default=".png"):
    e = os.path.splitext(filename or "")[1].lower()
    return e if e in (".png", ".jpg", ".jpeg", ".webp", ".gif") else default


def _extract_role_ids(script_json):
    """Pull character ids out of a clocktower script JSON (list form).
    Accepts entries that are plain strings or dicts with an 'id'; skips _meta."""
    ids = []
    if isinstance(script_json, list):
        for entry in script_json:
            if isinstance(entry, str):
                ids.append(entry)
            elif isinstance(entry, dict):
                cid = entry.get("id")
                if cid and cid != "_meta":
                    ids.append(cid)
    return ids


def _norm_id(cid):
    try:
        from botc_runner import _norm_role_id
        return _norm_role_id(cid)
    except Exception:
        return str(cid).lower().replace(" ", "").replace("_", "").replace("-", "").replace("'", "")


# --------------------------------------------------------------------------
# Command registration
# --------------------------------------------------------------------------

def register(bot):
    init_db()

    @bot.tree.command(name="addscript", description="Add a script to the library.")
    @app_commands.describe(
        name="Unique name for the script.",
        character_sheet="The character sheet image.",
        night_order="The night order sheet image.",
        script_file="The script JSON as a file (or use script_text).",
        script_text="The script JSON pasted as text (or use script_file).",
    )
    async def addscript(interaction: discord.Interaction, name: str,
                        character_sheet: discord.Attachment,
                        night_order: discord.Attachment,
                        script_file: discord.Attachment | None = None,
                        script_text: str | None = None):
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Resolve the JSON from either a file or pasted text.
        if script_file is not None:
            try:
                raw = (await script_file.read()).decode("utf-8")
            except Exception as e:
                await interaction.followup.send(f"Couldn't read the script file: {e}", ephemeral=True)
                return
        elif script_text is not None:
            raw = script_text
        else:
            await interaction.followup.send("Provide the script JSON as either `script_file` or `script_text`.", ephemeral=True)
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            await interaction.followup.send(f"That isn't valid JSON: {e}", ephemeral=True)
            return

        if get_script(name):
            await interaction.followup.send(f"A script named **{name}** already exists. Pick another name or /renamescript it.", ephemeral=True)
            return

        created = datetime.datetime.now().strftime("%Y-%m-%d")
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO scripts (name, json, uploader_id, uploader_name, created_at) VALUES (?,?,?,?,?)",
                (name, json.dumps(parsed), interaction.user.id, interaction.user.display_name, created))
            sid = cur.lastrowid

        # Download + store the two images now (Discord URLs expire).
        char_path = os.path.join(IMG_DIR, f"{sid}_character{_ext(character_sheet.filename)}")
        night_path = os.path.join(IMG_DIR, f"{sid}_night{_ext(night_order.filename)}")
        try:
            await character_sheet.save(char_path)
            await night_order.save(night_path)
        except Exception as e:
            with _conn() as c:
                c.execute("DELETE FROM scripts WHERE id=?", (sid,))
            await interaction.followup.send(f"Couldn't save the images: {e}", ephemeral=True)
            return
        with _conn() as c:
            c.execute("UPDATE scripts SET char_path=?, night_path=? WHERE id=?", (char_path, night_path, sid))

        await interaction.followup.send(
            f"Added script **{name}** (ID `{sid}`) with character sheet + night order.", ephemeral=True)

    @bot.tree.command(name="myscripts", description="List the scripts you've uploaded.")
    async def myscripts(interaction: discord.Interaction):
        with _conn() as c:
            rows = c.execute("SELECT * FROM scripts WHERE uploader_id=? ORDER BY id", (interaction.user.id,)).fetchall()
        if not rows:
            await interaction.response.send_message("You haven't uploaded any scripts yet.", ephemeral=True)
            return
        lines = [f"`{r['id']:>3}`  {r['name']}  —  {_rating_str(r['id'])}" for r in rows]
        await interaction.response.send_message(
            "**Your scripts:**\n" + "\n".join(lines), ephemeral=True)

    @bot.tree.command(name="allscripts", description="List every uploaded script.")
    async def allscripts(interaction: discord.Interaction):
        with _conn() as c:
            rows = c.execute("SELECT * FROM scripts ORDER BY id").fetchall()
        if not rows:
            await interaction.response.send_message("No scripts have been uploaded yet.", ephemeral=True)
            return
        header = f"{'ID':>3}  {'Name':<24} {'Uploaded by':<16} {'Date':<10} Rating"
        out = [header, "-" * len(header)]
        for r in rows:
            out.append(f"{r['id']:>3}  {r['name'][:24]:<24} {r['uploader_name'][:16]:<16} {r['created_at']:<10} {_rating_str(r['id'])}")
        text = "```\n" + "\n".join(out) + "\n```"
        if len(text) > 1990:
            buf = io.BytesIO(("\n".join(out)).encode("utf-8"))
            await interaction.response.send_message("All scripts:", file=discord.File(buf, "scripts.txt"))
        else:
            await interaction.response.send_message(text)

    @bot.tree.command(name="ratescript", description="Rate a script from 1 to 10.")
    @app_commands.describe(script="Script name or ID.", rating="A rating from 1 to 10.")
    async def ratescript(interaction: discord.Interaction, script: str,
                         rating: app_commands.Range[int, 1, 10]):
        s = get_script(script)
        if not s:
            await interaction.response.send_message(f"No script found matching **{script}**.", ephemeral=True)
            return
        with _conn() as c:
            c.execute(
                "INSERT INTO ratings (script_id, user_id, rating) VALUES (?,?,?) "
                "ON CONFLICT(script_id, user_id) DO UPDATE SET rating=excluded.rating",
                (s["id"], interaction.user.id, int(rating)))
        await interaction.response.send_message(
            f"You rated **{s['name']}** {int(rating)}/10. New average: {_rating_str(s['id'])}.", ephemeral=True)

    @bot.tree.command(name="script", description="Get a script's images and JSON.")
    @app_commands.describe(script="Script name or ID.")
    async def script_cmd(interaction: discord.Interaction, script: str):
        s = get_script(script)
        if not s:
            await interaction.response.send_message(f"No script found matching **{script}**.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        files = []
        for path, label in ((s["char_path"], "character"), (s["night_path"], "night_order")):
            if path and os.path.exists(path):
                files.append(discord.File(path, f"{s['name']}_{label}{os.path.splitext(path)[1]}"))
        files.append(discord.File(io.BytesIO(s["json"].encode("utf-8")), f"{s['name']}.json"))
        await interaction.followup.send(
            f"**{s['name']}** (ID `{s['id']}`) — uploaded by {s['uploader_name']} on {s['created_at']} — {_rating_str(s['id'])}",
            files=files)

    @bot.tree.command(name="deletescript", description="Delete a script (yours, or any with the Clockmaker role).")
    @app_commands.describe(script="Script name or ID.")
    async def deletescript(interaction: discord.Interaction, script: str):
        s = get_script(script)
        if not s:
            await interaction.response.send_message(f"No script found matching **{script}**.", ephemeral=True)
            return
        if s["uploader_id"] != interaction.user.id and not has_clockmaker(interaction.user):
            await interaction.response.send_message(
                "That isn't your script — you need the **Clockmaker** role to delete others' scripts.", ephemeral=True)
            return
        for path in (s["char_path"], s["night_path"]):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        with _conn() as c:
            c.execute("DELETE FROM ratings WHERE script_id=?", (s["id"],))
            c.execute("DELETE FROM scripts WHERE id=?", (s["id"],))
        await interaction.response.send_message(f"Deleted script **{s['name']}** (ID `{s['id']}`).", ephemeral=True)

    @bot.tree.command(name="renamescript", description="Rename a script (yours, or any with the Clockmaker role).")
    @app_commands.describe(script="Current script name or ID.", new_name="The new name.")
    async def renamescript(interaction: discord.Interaction, script: str, new_name: str):
        s = get_script(script)
        if not s:
            await interaction.response.send_message(f"No script found matching **{script}**.", ephemeral=True)
            return
        if s["uploader_id"] != interaction.user.id and not has_clockmaker(interaction.user):
            await interaction.response.send_message(
                "That isn't your script — you need the **Clockmaker** role to rename others' scripts.", ephemeral=True)
            return
        existing = get_script(new_name)
        if existing and existing["id"] != s["id"]:
            await interaction.response.send_message(f"A script named **{new_name}** already exists.", ephemeral=True)
            return
        with _conn() as c:
            c.execute("UPDATE scripts SET name=? WHERE id=?", (new_name, s["id"]))
        await interaction.response.send_message(f"Renamed **{s['name']}** → **{new_name}**.", ephemeral=True)

    @bot.tree.command(name="seatingjson", description="Build a game-state JSON seating the current players for a script.")
    @app_commands.describe(script="Script name or ID.")
    async def seatingjson(interaction: discord.Interaction, script: str):
        s = get_script(script)
        if not s:
            await interaction.response.send_message(f"No script found matching **{script}**.", ephemeral=True)
            return
        guild = interaction.guild
        tf = discord.utils.find(lambda r: r.name.lower() == TOWNSFOLK_ROLE.lower(), guild.roles)
        st = discord.utils.find(lambda r: r.name.lower() == STORYTELLER_ROLE.lower(), guild.roles)
        if tf is None:
            await interaction.response.send_message("No **Townsfolk** role found in this server.", ephemeral=True)
            return
        players = [m for m in guild.members
                   if tf in m.roles and (st is None or st not in m.roles) and not m.bot]
        players.sort(key=lambda m: m.display_name.lower())

        try:
            script_json = json.loads(s["json"])
        except Exception:
            script_json = []
        role_ids = [_norm_id(cid) for cid in _extract_role_ids(script_json)]

        def player_entry(name):
            return {"name": name, "id": "", "connected": False, "role": {},
                    "alignmentIndex": 0, "reminders": [], "isVoteless": False,
                    "hasTwoVotes": False, "hasResponded": {}, "isDead": False,
                    "handRaised": False, "pronouns": ""}

        state = {
            "bluffs": [None, None, None],
            "edition": {"id": "custom", "name": s["name"], "author": s["uploader_name"]},
            "roles": [{"id": rid} for rid in role_ids],
            "npcs": [],
            "players": [player_entry(m.display_name) for m in players],
        }
        buf = io.BytesIO(json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8"))
        names = ", ".join(m.display_name for m in players) if players else "none"
        await interaction.response.send_message(
            f"Seating JSON for **{s['name']}** — {len(players)} player(s): {names}",
            file=discord.File(buf, f"{s['name']}_seating.json"))
