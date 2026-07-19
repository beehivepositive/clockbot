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
import random
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
COMMON_NAMES_PATH = os.path.join(_BASE, "common_names.json")
PLAYER_NAMES_PATH = os.path.join(_BASE, "player_common_names.json")
os.makedirs(IMG_DIR, exist_ok=True)


def load_id_to_common():
    """Build a user_id -> common name map from two sources:
      1. common_names.json (name -> id): inverted; first alias per id wins.
      2. player_common_names.json (id -> name): explicit, and authoritative
         (overrides the inverted map). Handles several accounts sharing a name."""
    out = {}
    try:
        with open(COMMON_NAMES_PATH) as f:
            cn = json.load(f)
        for name, uid in cn.items():
            try:
                uid = int(uid)
            except (TypeError, ValueError):
                continue
            if uid not in out:
                out[uid] = name
    except Exception:
        pass
    try:
        with open(PLAYER_NAMES_PATH) as f:
            for uid, name in json.load(f).items():
                try:
                    out[int(uid)] = name
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass
    return out

CLOCKMAKER_ROLE = "Clockmaker"
TOWNSFOLK_ROLE = "Townsfolk"
STORYTELLER_ROLE = "Storyteller"
ASCENDED_ROLE = "Ascended"


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


def name_taken(name, exclude_id=None):
    with _conn() as c:
        row = c.execute("SELECT id FROM scripts WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    return row is not None and row["id"] != exclude_id


def unique_name(base, exclude_id=None):
    """Return `base`, or `base-1`, `base-2`, ... — the first name not already taken."""
    if not name_taken(base, exclude_id):
        return base
    n = 1
    while name_taken(f"{base}-{n}", exclude_id):
        n += 1
    return f"{base}-{n}"


def next_free_id():
    """Lowest positive integer not currently used as a script id (fills deletion gaps)."""
    with _conn() as c:
        ids = set(r[0] for r in c.execute("SELECT id FROM scripts"))
    n = 1
    while n in ids:
        n += 1
    return n


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

SCRIPTS_PER_PAGE = 15


def _format_rows(rows):
    header = f"{'ID':>3}  {'Name':<24} {'Uploaded by':<16} {'Date':<10} Rating"
    out = [header, "-" * len(header)]
    for r in rows:
        out.append(f"{r['id']:>3}  {r['name'][:24]:<24} {r['uploader_name'][:16]:<16} {r['created_at']:<10} {_rating_str(r['id'])}")
    return out


class ScriptListView(discord.ui.View):
    """Button-paginated table of scripts, restricted to the invoker."""

    def __init__(self, rows, title, owner_id, per_page=SCRIPTS_PER_PAGE):
        super().__init__(timeout=180)
        self.rows = rows
        self.title = title
        self.owner_id = owner_id
        self.per = per_page
        self.page = 0
        self.pages = max(1, (len(rows) + per_page - 1) // per_page)
        self._sync()

    def content(self):
        s = self.page * self.per
        body = "\n".join(_format_rows(self.rows[s:s + self.per]))
        return (f"**{self.title}** — page {self.page + 1}/{self.pages}, {len(self.rows)} total\n"
                f"```\n{body}\n```")

    def _sync(self):
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self.pages - 1

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This list isn't yours to page — run the command yourself.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction, button):
        self.page = max(0, self.page - 1)
        self._sync()
        await interaction.response.edit_message(content=self.content(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction, button):
        self.page = min(self.pages - 1, self.page + 1)
        self._sync()
        await interaction.response.edit_message(content=self.content(), view=self)


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
        script_file="The script JSON file.",
    )
    async def addscript(interaction: discord.Interaction, name: str,
                        character_sheet: discord.Attachment,
                        night_order: discord.Attachment,
                        script_file: discord.Attachment):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            raw = (await script_file.read()).decode("utf-8")
        except Exception as e:
            await interaction.followup.send(f"Couldn't read the script file: {e}", ephemeral=True)
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            await interaction.followup.send(f"That isn't valid JSON: {e}", ephemeral=True)
            return

        # Auto-suffix duplicate names: "Foo", then "Foo-1", "Foo-2", ...
        final_name = unique_name(name)

        # Store the uploader's common name as the author when we have one.
        author_name = load_id_to_common().get(interaction.user.id) or interaction.user.display_name
        created = datetime.datetime.now().strftime("%Y-%m-%d")
        sid = next_free_id()  # reuse the lowest free id so deletions get backfilled
        with _conn() as c:
            c.execute(
                "INSERT INTO scripts (id, name, json, uploader_id, uploader_name, created_at) VALUES (?,?,?,?,?,?)",
                (sid, final_name, json.dumps(parsed), interaction.user.id, author_name, created))

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

        note = f" (a script named **{name}** already existed)" if final_name != name else ""
        await interaction.followup.send(
            f"Added script **{final_name}** (ID `{sid}`) with character sheet + night order.{note}",
            ephemeral=True)

    @bot.tree.command(name="myscripts", description="List the scripts you've uploaded.")
    async def myscripts(interaction: discord.Interaction):
        with _conn() as c:
            rows = c.execute("SELECT * FROM scripts WHERE uploader_id=? ORDER BY id", (interaction.user.id,)).fetchall()
        if not rows:
            await interaction.response.send_message("You haven't uploaded any scripts yet.", ephemeral=True)
            return
        view = ScriptListView(rows, "Your scripts", interaction.user.id)
        await interaction.response.send_message(
            view.content(), view=view if view.pages > 1 else None, ephemeral=True)

    @bot.tree.command(name="scripts", description="List all scripts, optionally sorted.")
    @app_commands.describe(sort="How to sort the list (default: by ID).")
    @app_commands.choices(sort=[
        app_commands.Choice(name="Rating (best first)", value="rating"),
        app_commands.Choice(name="Uploader (A-Z)", value="uploader"),
        app_commands.Choice(name="Newest first", value="new"),
        app_commands.Choice(name="Oldest first", value="old"),
    ])
    async def scripts_cmd(interaction: discord.Interaction,
                          sort: app_commands.Choice[str] | None = None):
        with _conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM scripts").fetchall()]
        if not rows:
            await interaction.response.send_message("No scripts have been uploaded yet.", ephemeral=True)
            return
        mode = sort.value if sort else None
        if mode == "rating":
            # Best average first; unrated scripts sort below the worst rating.
            def rk(r):
                avg, n = script_avg_rating(r["id"])
                return avg if n else -1.0
            rows.sort(key=rk, reverse=True)
        elif mode == "uploader":
            rows.sort(key=lambda r: r["uploader_name"].lower())
        elif mode == "new":
            rows.sort(key=lambda r: r["id"], reverse=True)
        else:  # "old" or default
            rows.sort(key=lambda r: r["id"])
        title = "All scripts" + (f" — {sort.name}" if sort else "")
        view = ScriptListView(rows, title, interaction.user.id)
        await interaction.response.send_message(
            view.content(), view=view if view.pages > 1 else None)

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

    @bot.tree.command(name="getscript", description="Get a script's images and JSON.")
    @app_commands.describe(script="Script name or ID.")
    async def getscript_cmd(interaction: discord.Interaction, script: str):
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

    @bot.tree.command(name="updatescript", description="Update a script's name/images/JSON (yours, or any with Clockmaker).")
    @app_commands.describe(
        script="Script name or ID to update.",
        name="New name (optional).",
        character_sheet="New character sheet image (optional).",
        night_order="New night order image (optional).",
        script_file="New script JSON file (optional).",
    )
    async def updatescript(interaction: discord.Interaction, script: str,
                           name: str | None = None,
                           character_sheet: discord.Attachment | None = None,
                           night_order: discord.Attachment | None = None,
                           script_file: discord.Attachment | None = None):
        s = get_script(script)
        if not s:
            await interaction.response.send_message(f"No script found matching **{script}**.", ephemeral=True)
            return
        if s["uploader_id"] != interaction.user.id and not has_clockmaker(interaction.user):
            await interaction.response.send_message(
                "That isn't your script — you need the **Clockmaker** role to update others' scripts.", ephemeral=True)
            return
        if not any((name, character_sheet, night_order, script_file)):
            await interaction.response.send_message("Provide at least one field to update.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        sets, changed = {}, []

        if script_file is not None:
            try:
                parsed = json.loads((await script_file.read()).decode("utf-8"))
            except Exception as e:
                await interaction.followup.send(f"Couldn't read/parse the script JSON: {e}", ephemeral=True)
                return
            sets["json"] = json.dumps(parsed)
            changed.append("JSON")

        if character_sheet is not None:
            new_path = os.path.join(IMG_DIR, f"{s['id']}_character{_ext(character_sheet.filename)}")
            try:
                await character_sheet.save(new_path)
            except Exception as e:
                await interaction.followup.send(f"Couldn't save the character sheet: {e}", ephemeral=True)
                return
            if s["char_path"] and s["char_path"] != new_path and os.path.exists(s["char_path"]):
                try: os.remove(s["char_path"])
                except Exception: pass
            sets["char_path"] = new_path
            changed.append("character sheet")

        if night_order is not None:
            new_path = os.path.join(IMG_DIR, f"{s['id']}_night{_ext(night_order.filename)}")
            try:
                await night_order.save(new_path)
            except Exception as e:
                await interaction.followup.send(f"Couldn't save the night order: {e}", ephemeral=True)
                return
            if s["night_path"] and s["night_path"] != new_path and os.path.exists(s["night_path"]):
                try: os.remove(s["night_path"])
                except Exception: pass
            sets["night_path"] = new_path
            changed.append("night order")

        rename_note = ""
        if name is not None:
            final_name = unique_name(name, exclude_id=s["id"])
            sets["name"] = final_name
            changed.append(f"name → **{final_name}**")
            if final_name != name:
                rename_note = f" (a script named **{name}** already existed)"

        with _conn() as c:
            assignments = ", ".join(f"{k}=?" for k in sets)
            c.execute(f"UPDATE scripts SET {assignments} WHERE id=?", (*sets.values(), s["id"]))

        await interaction.followup.send(
            f"Updated **{s['name']}** (ID `{s['id']}`): {', '.join(changed)}.{rename_note}", ephemeral=True)

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
        asc = discord.utils.find(lambda r: r.name.lower() == ASCENDED_ROLE.lower(), guild.roles)
        if tf is None:
            await interaction.response.send_message("No **Townsfolk** role found in this server.", ephemeral=True)
            return
        excluded = {r for r in (st, asc) if r is not None}
        players = [m for m in guild.members
                   if tf in m.roles and not (excluded & set(m.roles)) and not m.bot]
        random.shuffle(players)

        # Prefer each player's common name (falling back to display name).
        id_to_common = load_id_to_common()
        def pname(m):
            n = id_to_common.get(m.id)
            return (n[:1].upper() + n[1:]) if n else m.display_name

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
            "players": [player_entry(pname(m)) for m in players],
        }
        buf = io.BytesIO(json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8"))
        names = ", ".join(pname(m) for m in players) if players else "none"
        await interaction.response.send_message(
            f"Seating JSON for **{s['name']}** — {len(players)} player(s): {names}",
            file=discord.File(buf, f"{s['name']}_seating.json"))
