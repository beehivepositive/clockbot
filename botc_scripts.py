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
import re
import json
import random
import sqlite3
import difflib
import datetime
import aiohttp
import discord
import pytz
from discord import app_commands

CST = pytz.timezone("America/Chicago")


def _today():
    """Today's date (YYYY-MM-DD) in US Central."""
    return datetime.datetime.now(CST).strftime("%Y-%m-%d")

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
        # Migrate older DBs: add updated_at if it's missing.
        cols = [r[1] for r in c.execute("PRAGMA table_info(scripts)")]
        if "updated_at" not in cols:
            c.execute("ALTER TABLE scripts ADD COLUMN updated_at TEXT")


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


def _row_updated(r):
    try:
        return bool(r["updated_at"])
    except (KeyError, IndexError):
        return False


def _entry_text(r):
    rating = _rating_str(r["id"])
    rtxt = "unrated" if rating.startswith("unrated") else f"⭐ {rating}"
    upd = f" · updated {r['updated_at']}" if _row_updated(r) else ""
    return f"**`{r['id']}` {r['name']}**\n{r['uploader_name']} · {r['created_at']}{upd} · {rtxt}"


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

    def embed(self):
        s = self.page * self.per
        page_rows = self.rows[s:s + self.per]
        e = discord.Embed(
            title=self.title,
            description="\n\n".join(_entry_text(r) for r in page_rows),
            color=discord.Color.blurple(),
        )
        e.set_footer(text=f"Page {self.page + 1}/{self.pages} · {len(self.rows)} total")
        return e

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
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction, button):
        self.page = min(self.pages - 1, self.page + 1)
        self._sync()
        await interaction.response.edit_message(embed=self.embed(), view=self)


def has_clockmaker(member):
    return any(r.name.lower() == CLOCKMAKER_ROLE.lower() for r in getattr(member, "roles", []))


def _ext(filename, default=".png"):
    e = os.path.splitext(filename or "")[1].lower()
    return e if e in (".png", ".jpg", ".jpeg", ".webp", ".gif") else default


def _split_script_pdf(pdf_bytes, sid, dpi=150):
    """Render a botcscripts PDF into (char_path, night_path) PNGs. botcscripts
    lays the script out with the character sheet first and the night-order fold
    sheet as the LAST page — so the night order is the last page and the character
    sheet is every page before it (stacked vertically if there's more than one).
    night_path is None if the PDF is a single page."""
    try:
        import pymupdf
    except ImportError:  # older PyMuPDF only exposes the `fitz` name
        import fitz as pymupdf
    from PIL import Image

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        n = doc.page_count

        def render(i):
            pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        char_idxs = list(range(0, n - 1)) if n >= 2 else [0]
        char_imgs = [render(i) for i in char_idxs]
        if len(char_imgs) == 1:
            char_img = char_imgs[0]
        else:  # multi-page character sheet: stack the pages vertically
            w = max(im.width for im in char_imgs)
            char_img = Image.new("RGB", (w, sum(im.height for im in char_imgs)), "white")
            y = 0
            for im in char_imgs:
                char_img.paste(im, (0, y))
                y += im.height
        char_path = os.path.join(IMG_DIR, f"{sid}_character.png")
        char_img.save(char_path)

        night_path = None
        if n >= 2:
            night_path = os.path.join(IMG_DIR, f"{sid}_night.png")
            render(n - 1).save(night_path)
        return char_path, night_path
    finally:
        doc.close()


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
# Fuzzy name resolution — "did you mean …?"
# --------------------------------------------------------------------------

def suggest_scripts(query, n=5):
    """Return up to n script rows whose name is a close/substring match for query."""
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM scripts").fetchall()]
    q = query.lower().strip()
    out, seen = [], set()
    # Substring matches first (most intuitive), then difflib fuzzy matches.
    for r in rows:
        nl = r["name"].lower()
        if q and (q in nl or nl in q) and r["id"] not in seen:
            out.append(r)
            seen.add(r["id"])
    lower_map = {}
    for r in rows:
        lower_map.setdefault(r["name"].lower(), r)
    for cl in difflib.get_close_matches(q, list(lower_map.keys()), n=n, cutoff=0.5):
        r = lower_map[cl]
        if r["id"] not in seen:
            out.append(r)
            seen.add(r["id"])
    return out[:n]


class SuggestView(discord.ui.View):
    """Offers close-name matches; picking one runs the held command with that script."""

    def __init__(self, candidates, owner_id, run):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.run = run
        self._by_id = {str(r["id"]): r for r in candidates}
        options = [discord.SelectOption(label=f"{r['name']} (ID {r['id']})"[:100], value=str(r["id"]))
                   for r in candidates[:25]]
        self.sel = discord.ui.Select(placeholder="Did you mean…", options=options)
        self.sel.callback = self._pick
        self.add_item(self.sel)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This prompt isn't yours.", ephemeral=True)
            return False
        return True

    async def _pick(self, interaction):
        row = self._by_id.get(self.sel.values[0])
        self.stop()
        if row:
            await self.run(interaction, row)


async def resolve_or_suggest(interaction, script, run):
    """Resolve `script` (name or id) and call run(interaction, row). With no exact
    match, offer close-name suggestions — the original command inputs are held in
    the `run` closure, so picking a suggestion completes the action."""
    s = get_script(script)
    if s:
        await run(interaction, s)
        return
    if str(script).strip().isdigit():
        await interaction.response.send_message(f"No script with ID **{script}**.", ephemeral=True)
        return
    cands = suggest_scripts(script)
    if not cands:
        await interaction.response.send_message(f"No script found matching **{script}**.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"No exact match for **{script}** — did you mean one of these?",
        view=SuggestView(cands, interaction.user.id, run), ephemeral=True)


# --------------------------------------------------------------------------
# Command registration
# --------------------------------------------------------------------------

def register(bot):
    init_db()

    @bot.tree.command(name="addscript", description="Add a script to the library.")
    @app_commands.rename(script_file="json")
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
        created = _today()
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

    @bot.tree.command(name="importscript",
                      description="Import a script from a botcscripts.com link into the library.")
    @app_commands.describe(link="A botcscripts.com script link, e.g. https://www.botcscripts.com/script/42/5.1.0")
    async def importscript(interaction: discord.Interaction, link: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        # Only botcscripts.com for now — build the download URLs from the id/version
        # in the link (never fetch the raw user string, so this can't be pointed elsewhere).
        m = re.search(r"botcscripts\.com/script/(\d+)(?:/([\w.]+))?", link.strip(), re.I)
        if not m:
            await interaction.followup.send(
                "Give me a **botcscripts.com** script link, like "
                "`https://www.botcscripts.com/script/42/5.1.0`.", ephemeral=True)
            return
        num, ver = m.group(1), m.group(2)
        base = f"https://www.botcscripts.com/script/{num}" + (f"/{ver}" if ver else "")
        headers = {"User-Agent": "Mozilla/5.0 (Clockbot script importer)"}
        try:
            async with aiohttp.ClientSession(headers=headers) as sess:
                async with sess.get(base + "/download") as r:
                    if r.status != 200:
                        await interaction.followup.send(
                            f"Couldn't download the script JSON (HTTP {r.status}). Double-check the link.",
                            ephemeral=True)
                        return
                    raw = await r.text()
                async with sess.get(base + "/download_pdf") as r:
                    if r.status != 200:
                        await interaction.followup.send(
                            f"Couldn't download the script PDF (HTTP {r.status}).", ephemeral=True)
                        return
                    pdf_bytes = await r.read()
        except Exception as e:
            await interaction.followup.send(f"Download failed: {e}", ephemeral=True)
            return

        try:
            parsed = json.loads(raw)
        except Exception as e:
            await interaction.followup.send(f"The downloaded JSON was invalid: {e}", ephemeral=True)
            return
        meta = {}
        if isinstance(parsed, list):
            meta = next((e for e in parsed if isinstance(e, dict) and e.get("id") == "_meta"), None) or {}
        title = (meta.get("name") or f"Script {num}").strip()
        author = (meta.get("author") or "").strip()

        final_name = unique_name(title)
        uploader_name = author or load_id_to_common().get(interaction.user.id) or interaction.user.display_name
        sid = next_free_id()
        with _conn() as c:
            c.execute(
                "INSERT INTO scripts (id, name, json, uploader_id, uploader_name, created_at) VALUES (?,?,?,?,?,?)",
                (sid, final_name, json.dumps(parsed), interaction.user.id, uploader_name, _today()))

        try:
            char_path, night_path = _split_script_pdf(pdf_bytes, sid)
        except Exception as e:
            with _conn() as c:
                c.execute("DELETE FROM scripts WHERE id=?", (sid,))
            await interaction.followup.send(f"Couldn't render/split the PDF: {e}", ephemeral=True)
            return
        with _conn() as c:
            c.execute("UPDATE scripts SET char_path=?, night_path=? WHERE id=?", (char_path, night_path, sid))

        files = [discord.File(char_path, f"{final_name}_character.png")]
        if night_path:
            files.append(discord.File(night_path, f"{final_name}_night_order.png"))
        note = (f" (a script named **{title}** already existed, saved as **{final_name}**)"
                if final_name != title else "")
        byline = f" by **{author}**" if author else ""
        await interaction.followup.send(
            f"Imported **{final_name}**{byline} (ID `{sid}`) from botcscripts.{note}\n"
            "Split the PDF into character sheet + night order — check they look right:",
            files=files, ephemeral=True)

    @bot.tree.command(name="myscripts", description="List the scripts you've uploaded.")
    async def myscripts(interaction: discord.Interaction):
        with _conn() as c:
            rows = c.execute("SELECT * FROM scripts WHERE uploader_id=? ORDER BY id", (interaction.user.id,)).fetchall()
        if not rows:
            await interaction.response.send_message("You haven't uploaded any scripts yet.", ephemeral=True)
            return
        view = ScriptListView(rows, "Your scripts", interaction.user.id)
        await interaction.response.send_message(
            embed=view.embed(), view=view if view.pages > 1 else None, ephemeral=True)

    @bot.tree.command(name="scripts", description="List scripts, optionally filtered by uploader and sorted.")
    @app_commands.describe(
        sort="How to sort the list (default: by ID).",
        uploader="Show only this uploader's scripts — a common name or an @mention/ID.",
    )
    @app_commands.choices(sort=[
        app_commands.Choice(name="Rating (best first)", value="rating"),
        app_commands.Choice(name="Newest first", value="new"),
        app_commands.Choice(name="Oldest first", value="old"),
    ])
    async def scripts_cmd(interaction: discord.Interaction,
                          sort: app_commands.Choice[str] | None = None,
                          uploader: str | None = None):
        with _conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM scripts").fetchall()]
        if not rows:
            await interaction.response.send_message("No scripts have been uploaded yet.", ephemeral=True)
            return

        filt = ""
        if uploader:
            q = uploader.strip()
            m = re.match(r"^<@!?(\d+)>$|^(\d+)$", q)
            if m:
                uid = int(m.group(1) or m.group(2))
                rows = [r for r in rows if r["uploader_id"] == uid]
                filt = f" by <@{uid}>"
            else:
                ql = q.lower()
                id2c = load_id_to_common()
                rows = [r for r in rows
                        if r["uploader_name"].lower() == ql
                        or id2c.get(r["uploader_id"], "").lower() == ql]
                filt = f" by {q}"
            if not rows:
                await interaction.response.send_message(f"No scripts uploaded{filt}.", ephemeral=True)
                return

        mode = sort.value if sort else None
        if mode == "rating":
            # Best average first; unrated scripts sort below the worst rating.
            def rk(r):
                avg, n = script_avg_rating(r["id"])
                return avg if n else -1.0
            rows.sort(key=rk, reverse=True)
        elif mode == "new":
            rows.sort(key=lambda r: r["id"], reverse=True)
        else:  # "old" or default
            rows.sort(key=lambda r: r["id"])

        title = "Scripts" + filt + (f" — {sort.name}" if sort else "")
        view = ScriptListView(rows, title, interaction.user.id)
        await interaction.response.send_message(
            embed=view.embed(), view=view if view.pages > 1 else None)

    @bot.tree.command(name="ratescript", description="Rate a script from 1 to 10.")
    @app_commands.describe(script="Script name or ID.", rating="A rating from 1 to 10.")
    async def ratescript(interaction: discord.Interaction, script: str,
                         rating: app_commands.Range[int, 1, 10]):
        async def run(inter, s):
            with _conn() as c:
                c.execute(
                    "INSERT INTO ratings (script_id, user_id, rating) VALUES (?,?,?) "
                    "ON CONFLICT(script_id, user_id) DO UPDATE SET rating=excluded.rating",
                    (s["id"], inter.user.id, int(rating)))
            await inter.response.send_message(
                f"You rated **{s['name']}** {int(rating)}/10. New average: {_rating_str(s['id'])}.", ephemeral=True)
        await resolve_or_suggest(interaction, script, run)

    @bot.tree.command(name="getscript", description="Get a script's images and JSON.")
    @app_commands.describe(script="Script name or ID.")
    async def getscript_cmd(interaction: discord.Interaction, script: str):
        async def run(inter, s):
            await inter.response.defer(thinking=True)
            files = []
            for path, label in ((s["char_path"], "character"), (s["night_path"], "night_order")):
                if path and os.path.exists(path):
                    files.append(discord.File(path, f"{s['name']}_{label}{os.path.splitext(path)[1]}"))
            files.append(discord.File(io.BytesIO(s["json"].encode("utf-8")), f"{s['name']}.json"))
            upd = f" · updated {s['updated_at']}" if s.get("updated_at") else ""
            await inter.followup.send(
                f"**{s['name']}** (ID `{s['id']}`) — uploaded by {s['uploader_name']} on {s['created_at']}{upd} — {_rating_str(s['id'])}",
                files=files)
        await resolve_or_suggest(interaction, script, run)

    @bot.tree.command(name="deletescript", description="Delete a script (yours, or any with the Clockmaker role).")
    @app_commands.describe(script="Script name or ID.")
    async def deletescript(interaction: discord.Interaction, script: str):
        async def run(inter, s):
            if s["uploader_id"] != inter.user.id and not has_clockmaker(inter.user):
                await inter.response.send_message(
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
            await inter.response.send_message(f"Deleted script **{s['name']}** (ID `{s['id']}`).", ephemeral=True)
        await resolve_or_suggest(interaction, script, run)

    @bot.tree.command(name="updatescript", description="Update a script's name/images/JSON (yours, or any with Clockmaker).")
    @app_commands.rename(script_file="json")
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
        async def run(inter, s):
            if s["uploader_id"] != inter.user.id and not has_clockmaker(inter.user):
                await inter.response.send_message(
                    "That isn't your script — you need the **Clockmaker** role to update others' scripts.", ephemeral=True)
                return
            if not any((name, character_sheet, night_order, script_file)):
                await inter.response.send_message("Provide at least one field to update.", ephemeral=True)
                return
            await inter.response.defer(ephemeral=True, thinking=True)

            sets, changed = {}, []

            if script_file is not None:
                try:
                    parsed = json.loads((await script_file.read()).decode("utf-8"))
                except Exception as e:
                    await inter.followup.send(f"Couldn't read/parse the script JSON: {e}", ephemeral=True)
                    return
                sets["json"] = json.dumps(parsed)
                changed.append("JSON")

            if character_sheet is not None:
                new_path = os.path.join(IMG_DIR, f"{s['id']}_character{_ext(character_sheet.filename)}")
                try:
                    await character_sheet.save(new_path)
                except Exception as e:
                    await inter.followup.send(f"Couldn't save the character sheet: {e}", ephemeral=True)
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
                    await inter.followup.send(f"Couldn't save the night order: {e}", ephemeral=True)
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

            sets["updated_at"] = _today()
            with _conn() as c:
                assignments = ", ".join(f"{k}=?" for k in sets)
                c.execute(f"UPDATE scripts SET {assignments} WHERE id=?", (*sets.values(), s["id"]))

            await inter.followup.send(
                f"Updated **{s['name']}** (ID `{s['id']}`): {', '.join(changed)}.{rename_note}", ephemeral=True)
        await resolve_or_suggest(interaction, script, run)

    @bot.tree.command(name="seatingjson", description="Build a game-state JSON seating the current players for a script.")
    @app_commands.describe(script="Script name or ID.")
    async def seatingjson(interaction: discord.Interaction, script: str):
        async def run(inter, s):
            guild = inter.guild
            tf = discord.utils.find(lambda r: r.name.lower() == TOWNSFOLK_ROLE.lower(), guild.roles)
            st = discord.utils.find(lambda r: r.name.lower() == STORYTELLER_ROLE.lower(), guild.roles)
            asc = discord.utils.find(lambda r: r.name.lower() == ASCENDED_ROLE.lower(), guild.roles)
            if tf is None:
                await inter.response.send_message("No **Townsfolk** role found in this server.", ephemeral=True)
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
            await inter.response.send_message(
                f"Seating JSON for **{s['name']}** — {len(players)} player(s): {names}",
                file=discord.File(buf, f"{s['name']}_seating.json"))
        await resolve_or_suggest(interaction, script, run)
