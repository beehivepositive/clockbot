"""BotC game-management commands (Storyteller-gated).

Commands:
  /newgame [number] [as_user]  Create game channels; archive the previous game first.
                         With as_user, build using that Storyteller's settings (they become the ST).
  /archivegame           Move the current Game Logs + Game Chat channels into an Archive category.
  /assignplayers         Strip player roles + assign Townsfolk to signups in #recruiting (grants talk if Explicit).
  /addtown <user>        Give a user the Townsfolk role + permission to talk in game chat.
  /endgame               Reveal the current game's ascension + ascension-chat to everyone.
  /ascend @user          Grant a user the Ascended role (or explicit per-user access).
  /addst <user>          Give a user the Storyteller role (+ explicit ST permissions if enabled).
  /setupsettings         Per-Storyteller settings that customize what /newgame builds (+ announcements).

Design notes / assumptions (flagged for iteration):
  * Roles/categories are resolved BY NAME (case-insensitive) so the bot can migrate servers.
  * Commands are registered globally (no hardcoded guild) and appear in every guild the bot is in.
  * The Storyteller allow-set below was reverse-engineered from the live server's bitmasks.
  * Ambiguous spec defaults resolved here (correct during iteration):
      - Game-chat threads/activities are DENIED to @everyone at the base, then granted per-role
        via the Townsfolk/Tulpa/Ascended toggles, so those toggles are meaningful.
      - Traveler gets NO overwrite by default (spec only named Townsfolk for game chat).
      - "images" toggle off  -> deny embed_links + attach_files to @everyone.
      - "bots" toggle off    -> deny use_embedded_activities + use_application_commands + use_external_apps.
      - Focused default slowmode = 30 min. Focused/ascension "ascended talk" default = on.
  * Per-user settings persist to st_game_settings.json (same JSON pattern as whisper_state.json).
"""

import os
import re
import json
import discord
from discord import app_commands
import votelock
import botc_pdf

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "st_game_settings.json")
# Fall back to the server's canonical location if running from /home/discord-bot
if os.path.isdir("/home/discord-bot"):
    SETTINGS_PATH = "/home/discord-bot/st_game_settings.json"

R_ST = "Storyteller"
R_TOWNSFOLK = "Townsfolk"
R_ASCENDED = "Ascended"
R_TRAVELER = "Traveler"
R_TULPA = "Tulpa"
R_RECLUSE = "Recluse"
R_CLOCKMAKER = "Clockmaker"

CAT_LOGS = "Game Logs"
CAT_CHAT = "Game Chat"
ARCHIVE_PREFIX = "Archive"
VOICE_CAT = "Voice Channels"
RECRUIT_CHANNEL = "recruiting"

MAX_CHANNELS_PER_CATEGORY = 50
REACTION_THRESHOLD = 5

# Storyteller allow-set (verified against live server bitmasks).
ST_PERMS = dict(
    view_channel=True, send_messages=True, manage_channels=True, manage_roles=True,
    manage_webhooks=True, manage_messages=True, manage_threads=True, embed_links=True,
    attach_files=True, use_application_commands=True, use_embedded_activities=True,
    use_external_apps=True,
)

# Slowmode presets (label -> seconds), mirroring Discord's native options.
SLOWMODE_OPTIONS = [
    ("Off", 0), ("5s", 5), ("10s", 10), ("15s", 15), ("30s", 30), ("1m", 60),
    ("2m", 120), ("5m", 300), ("10m", 600), ("15m", 900), ("30m", 1800),
    ("1h", 3600), ("2h", 7200), ("6h", 21600),
]

# The six channel kinds and their name suffixes, in creation order per category.
LOGS_KINDS = [("ascension", "ascension"), ("ascension_chat", "ascension-chat"), ("logs", "logs")]
CHAT_KINDS = [("chat", "chat"), ("focused", "focused"), ("whisper_logs", "whisper-logs")]

# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

def default_settings():
    return {
        "explicit_permission": False,
        "privacy": False,
        "channels": {
            "ascension":      {"create": True, "ascended_talk": True},
            "ascension_chat": {"create": True, "ascended_talk": True},
            "logs":           {"create": True},
            "chat":           {"create": True, "images": True, "bots": True},
            "focused":        {"create": True, "slowmode": True, "slowmode_secs": 1800,
                               "images": True, "bots": True},
            "whisper_logs":   {"create": True, "images": True, "bots": True},
        },
        "townsfolk": {"threads": True, "activities": True},
        "tulpa":     {"talk": False, "threads": True, "activities": True},
        "ascended":  {"talk": False, "threads": True, "activities": True},
        "announcements": {
            "votelock": {
                "enabled": False,
                "message": "@Townsfolk votes are locked.",
                "hour": None, "minute": None,
                "duration_min": 60,
                "tz": "America/Chicago",
                "track_votes": False,
            },
            "daynight": {
                "rules": [
                    {"trigger": "# Day {n}",   "output": "# Day {n}",   "kind": "day",    "enabled": False},
                    {"trigger": "# Night {n}", "output": "# Night {n}", "kind": "night",  "enabled": False},
                    {"trigger": "",            "output": "",            "kind": "custom", "enabled": False},
                ]
            },
        },
    }


def _deep_merge(base, override):
    """Fill any keys missing from override using base (recursively)."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = _deep_merge(base[k], v)
        else:
            out[k] = v
    # Ensure keys present in base but absent from override are kept
    for k, v in base.items():
        if k not in out:
            out[k] = v
    return out


def _load_all():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def load_settings(user_id):
    raw = _load_all().get(str(user_id), {})
    return _deep_merge(default_settings(), raw)


def save_settings(user_id, data):
    alld = _load_all()
    alld[str(user_id)] = data
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(alld, f, indent=2)
    os.replace(tmp, SETTINGS_PATH)


# ---------------------------------------------------------------------------
# Per-game Storyteller record (who /newgame was run as, keyed by game number)
# ---------------------------------------------------------------------------

GAME_ST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_st.json")
if os.path.isdir("/home/discord-bot"):
    GAME_ST_PATH = "/home/discord-bot/game_st.json"


def _load_game_st():
    if os.path.exists(GAME_ST_PATH):
        try:
            with open(GAME_ST_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def set_game_st(guild_id, number, user_id):
    data = _load_game_st()
    data.setdefault(str(guild_id), {})[str(number)] = str(user_id)
    tmp = GAME_ST_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, GAME_ST_PATH)


def get_game_st(guild_id, number):
    """The recorded Storyteller user-id (int) for a game number, or None."""
    v = _load_game_st().get(str(guild_id), {}).get(str(number))
    return int(v) if v else None


# Shared common-name aliases (name -> discord id), same file /add-common-name writes.
COMMON_NAMES_PATH = ("/home/discord-bot/common_names.json" if os.path.isdir("/home/discord-bot")
                     else os.path.join(os.path.dirname(os.path.abspath(__file__)), "common_names.json"))


def _load_common_names():
    try:
        with open(COMMON_NAMES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Resolution helpers (by name, case-insensitive)
# ---------------------------------------------------------------------------

def resolve_role(guild, name):
    return discord.utils.find(lambda r: r.name.lower() == name.lower(), guild.roles)


def resolve_category(guild, name):
    return discord.utils.find(lambda c: c.name.lower() == name.lower(), guild.categories)


def resolve_member(guild, text):
    """Resolve a guild member from free text: an @mention, a raw ID, or a common
    name (nickname / display name / username), case-insensitive. Returns
    (member, None) on success or (None, error_message) on failure."""
    text = (text or "").strip()
    if not text:
        return None, "No user given."
    m = re.match(r"<@!?(\d+)>$", text) or re.match(r"(\d{15,25})$", text)
    if m:
        member = guild.get_member(int(m.group(1)))
        return (member, None) if member else (None, "That user isn't in this server.")
    low = text.lower()

    # Common-name aliases (name -> discord id), shared with /add-common-name.
    cn = _load_common_names()
    if low in cn:
        member = guild.get_member(int(cn[low]))
        if member is not None:
            return member, None

    def gname(mem):
        return (getattr(mem, "global_name", None) or "").lower()

    # Exact match on nickname / display name / username wins over a partial one.
    exact = [mem for mem in guild.members
             if low in (mem.display_name.lower(), mem.name.lower(), gname(mem))]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, _ambiguous(exact)
    partial = [mem for mem in guild.members
               if low in mem.display_name.lower() or low in mem.name.lower()]
    if len(partial) == 1:
        return partial[0], None
    if len(partial) > 1:
        return None, _ambiguous(partial)
    return None, f"No member matching “{text}” found."


def _ambiguous(members):
    names = ", ".join(sorted(m.display_name for m in members)[:8])
    return ("Multiple members match that name — narrow it down or @mention them.\n"
            f"Matches: {names}")


def pick_member(guild, user, name):
    """Resolve a target member from an optional Member-picker arg and/or an
    optional free-text common-name arg. The picker wins if both are supplied."""
    if user is not None:
        return user, None
    if name:
        return resolve_member(guild, name)
    return None, "Give a user (from the picker) or type a name."


def is_storyteller(interaction):
    return any(r.name.lower() == R_ST.lower() for r in getattr(interaction.user, "roles", []))


def has_clockmaker(member):
    return any(r.name.lower() == R_CLOCKMAKER.lower() for r in getattr(member, "roles", []))


def st_check():
    return app_commands.check(lambda i: is_storyteller(i))


def is_current_game_st(interaction):
    """True if the caller is the Storyteller recorded for the current game. The
    'current game' is the one named by the channel this was run in, else the
    latest game. If no ST was recorded for that game (e.g. it predates ST
    tracking), fall back to the plain Storyteller-role check so nothing breaks."""
    guild = interaction.guild
    if guild is None:
        return False
    num = game_number_from_name(getattr(interaction.channel, "name", "") or "")
    if num is None:
        num = latest_game_number(guild)
    recorded = get_game_st(guild.id, num) if num is not None else None
    if recorded is not None:
        return interaction.user.id == recorded
    return is_storyteller(interaction)


def current_game_st_check():
    return app_commands.check(lambda i: is_current_game_st(i))


def game_number_from_name(name):
    m = re.match(r"game0*(\d+)", name.lower())
    return int(m.group(1)) if m else None


def archive_index(cat_name):
    m = re.match(rf"{ARCHIVE_PREFIX.lower()}\s*(\d+)", cat_name.lower())
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Permission builder — the single source of truth for channel overwrites
# ---------------------------------------------------------------------------

def build_overwrites(guild, kind, s, initiator):
    """Return {role_or_member: PermissionOverwrite} for a channel of `kind`
    given Storyteller settings `s` and the `initiator` member."""
    ev = guild.default_role
    ow = {}

    st = resolve_role(guild, R_ST)
    tf = resolve_role(guild, R_TOWNSFOLK)
    asc = resolve_role(guild, R_ASCENDED)
    tul = resolve_role(guild, R_TULPA)
    rec = resolve_role(guild, R_RECLUSE)

    explicit = s.get("explicit_permission", False)
    privacy = s.get("privacy", False)
    cset = s.get("channels", {}).get(kind, {})

    is_ascension = kind in ("ascension", "ascension_chat")
    is_gamechat = kind in ("chat", "focused", "whisper_logs")
    is_logs = kind == "logs"

    # Storyteller powers -> the ST role, or the initiator member under Explicit Permission.
    st_target = initiator if explicit else st
    if st_target is not None:
        ow[st_target] = discord.PermissionOverwrite(**ST_PERMS)

    # Recluse denied view everywhere.
    if rec is not None:
        ow[rec] = discord.PermissionOverwrite(view_channel=False)

    # @everyone base.
    ev_ow = discord.PermissionOverwrite(send_messages=False)
    if is_ascension:
        ev_ow.view_channel = False
    if is_logs:
        ev_ow.create_public_threads = False
        ev_ow.create_private_threads = False
        ev_ow.send_messages_in_threads = False
    if is_gamechat:
        # Threads denied at base so per-role toggles are meaningful.
        ev_ow.create_public_threads = False
        ev_ow.create_private_threads = False
        if not cset.get("images", True):
            ev_ow.embed_links = False
            ev_ow.attach_files = False
        if not cset.get("bots", True):
            ev_ow.use_embedded_activities = False
            ev_ow.use_application_commands = False
            ev_ow.use_external_apps = False
    # Privacy: hide game-chat + logs from @everyone (ascension stays hidden regardless).
    if privacy and (is_gamechat or is_logs):
        ev_ow.view_channel = False
    ow[ev] = ev_ow

    def grant(role, **perms):
        if role is None:
            return
        cur = ow.get(role, discord.PermissionOverwrite())
        for k, v in perms.items():
            setattr(cur, k, v)
        ow[role] = cur

    # Privacy grants view to the player audience in game-chat + logs (not ascension).
    if privacy and (is_gamechat or is_logs):
        grant(tf, view_channel=True)
        if asc is not None and not explicit:
            grant(asc, view_channel=True)

    if is_ascension:
        # Townsfolk keep send so that after /endgame reveal they can talk.
        grant(tf, send_messages=True)
        if not explicit:
            if cset.get("ascended_talk", True):
                grant(asc, view_channel=True, send_messages=True)
            else:
                grant(asc, view_channel=True, send_messages=False)

    if is_gamechat:
        ts = s.get("townsfolk", {})
        # Under Explicit Permission the Townsfolk role does NOT auto-grant talk;
        # players are added individually via /addtown or /assignplayers.
        if not explicit:
            grant(tf, send_messages=True)
        if ts.get("threads", True):
            grant(tf, create_public_threads=True, send_messages_in_threads=True)
        if ts.get("activities", True):
            grant(tf, use_embedded_activities=True)

        tu = s.get("tulpa", {})
        if tu.get("talk", False):
            grant(tul, send_messages=True)
        if tu.get("threads", True):
            grant(tul, create_public_threads=True, send_messages_in_threads=True)
        if tu.get("activities", True):
            grant(tul, use_embedded_activities=True)

        au = s.get("ascended", {})
        if au.get("talk", False) and not explicit:
            grant(asc, send_messages=True)
        if au.get("threads", True) and not explicit:
            grant(asc, create_public_threads=True, send_messages_in_threads=True)
        if au.get("activities", True) and not explicit:
            grant(asc, use_embedded_activities=True)

    return ow


def archived_overwrites(guild):
    """Read-only overwrites for an archived channel: everyone may view but not
    post/react; Recluse cannot view."""
    ev = guild.default_role
    rec = resolve_role(guild, R_RECLUSE)
    ow = {
        ev: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False, add_reactions=False,
            create_public_threads=False, create_private_threads=False,
            send_messages_in_threads=False, use_embedded_activities=False,
            use_application_commands=False,
        )
    }
    if rec is not None:
        ow[rec] = discord.PermissionOverwrite(view_channel=False)
    return ow


# ---------------------------------------------------------------------------
# Game / channel discovery
# ---------------------------------------------------------------------------

def current_game_channels(guild):
    """All text channels currently in the Game Logs / Game Chat categories."""
    out = []
    for cat_name in (CAT_LOGS, CAT_CHAT):
        cat = resolve_category(guild, cat_name)
        if cat:
            out.extend([c for c in cat.channels if isinstance(c, discord.TextChannel)])
    return out


def latest_game_number(guild):
    """Highest game number seen across every text channel in the guild."""
    nums = []
    for c in guild.text_channels:
        n = game_number_from_name(c.name)
        if n is not None:
            nums.append(n)
    return max(nums) if nums else None


def archive_categories(guild):
    """Archive categories sorted by their numeric index (ascending)."""
    cats = []
    for c in guild.categories:
        idx = archive_index(c.name)
        if idx is not None:
            cats.append((idx, c))
    cats.sort(key=lambda t: t[0])
    return cats


async def ensure_archive_target(guild, needed):
    """Return an Archive category with room for `needed` channels, creating a new
    top-of-stack Archive (N+1) if the most-recent one can't hold them together."""
    cats = archive_categories(guild)
    if cats:
        top_idx, top_cat = cats[-1]  # highest number = most recent
        if len(top_cat.channels) + needed <= MAX_CHANNELS_PER_CATEGORY:
            return top_cat
        new_idx = top_idx + 1
        insert_pos = min(c.position for _, c in cats)  # top of the archive block
    else:
        new_idx = 1
        voice = resolve_category(guild, VOICE_CAT)
        insert_pos = (voice.position + 1) if voice else None

    new_cat = await guild.create_category(f"{ARCHIVE_PREFIX} {new_idx}")
    if insert_pos is not None:
        try:
            await new_cat.edit(position=insert_pos)
        except Exception:
            pass
    return new_cat


async def archive_channels(guild, channels, log=None):
    """Move `channels` (grouped by game) into archive categories, keeping each
    game's channels together, and apply read-only archive permissions."""
    moved = 0
    groups = {}
    for ch in channels:
        key = game_number_from_name(ch.name)
        groups.setdefault(key, []).append(ch)

    async def _pdf_into(ch, dest, prefix):
        """PDF `ch` and post the file into `dest`; log on failure."""
        outpath = f"/tmp/{ch.name}.pdf"
        try:
            cnt = await botc_pdf.channel_to_pdf(ch, guild, outpath)
            if cnt:
                await dest.send(f"{prefix} **#{ch.name}** ({cnt} messages)",
                                file=discord.File(outpath, filename=f"{ch.name}.pdf"))
        except Exception as e:
            if log:
                log.append(f"PDF failed for #{ch.name}: {e}")
        finally:
            try:
                os.unlink(outpath)
            except Exception:
                pass

    for key, chans in groups.items():
        target = await ensure_archive_target(guild, len(chans))
        ow = archived_overwrites(guild)
        logs_ch = next((c for c in chans
                        if (c.name.endswith("-logs") or c.name.endswith("-log"))
                        and "whisper" not in c.name.lower()), None)
        whisper_chans = [c for c in chans if "whisper" in c.name.lower()]

        # PDF pass: the -logs channel FIRST (so its PDF is pristine), then the other
        # non-whisper channels, each PDF posted into itself. Nothing is deleted here.
        pdf_order = ([logs_ch] if logs_ch is not None else []) + \
                    [c for c in chans if c not in whisper_chans and c is not logs_ch]
        for ch in pdf_order:
            await _pdf_into(ch, ch, "📄 Archive of")

        # whisper-logs: PDF into the game's -logs channel, then DELETE the channel.
        for ch in whisper_chans:
            if logs_ch is not None:
                await _pdf_into(ch, logs_ch, "📄 Archived (deleted)")
            try:
                await ch.delete(reason="archive: whisper-logs removed after PDF")
            except Exception as e:
                if log:
                    log.append(f"Failed to delete #{ch.name}: {e}")

        # Move + lock the survivors (everything except deleted whispers), reversed so
        # the group stacks at the TOP of the archive category in original order.
        survivors = [c for c in chans if c not in whisper_chans]
        for ch in reversed(survivors):
            try:
                await ch.move(beginning=True, category=target, sync_permissions=False)
                for tgt in list(ch.overwrites.keys()):
                    await ch.set_permissions(tgt, overwrite=None)
                for tgt, perm in ow.items():
                    await ch.set_permissions(tgt, overwrite=perm)
                if ch.slowmode_delay:
                    await ch.edit(slowmode_delay=0)
                moved += 1
            except Exception as e:
                if log:
                    log.append(f"Failed to archive #{ch.name}: {e}")
    return moved


# ---------------------------------------------------------------------------
# Channel creation
# ---------------------------------------------------------------------------

async def create_game_channels(guild, number, s, initiator, log=None):
    """Create the (up to) six channels for a game number per settings `s`."""
    logs_cat = resolve_category(guild, CAT_LOGS)
    chat_cat = resolve_category(guild, CAT_CHAT)
    created = []
    if logs_cat is None or chat_cat is None:
        if log is not None:
            log.append(f"Missing category: {'Game Logs' if not logs_cat else ''} "
                       f"{'Game Chat' if not chat_cat else ''}".strip())
        return created

    async def make(cat, kind, suffix):
        cset = s.get("channels", {}).get(kind, {})
        if not cset.get("create", True):
            return
        name = f"game{number}-{suffix}"
        overwrites = build_overwrites(guild, kind, s, initiator)
        kwargs = {"overwrites": overwrites}
        if kind == "focused" and cset.get("slowmode", True):
            kwargs["slowmode_delay"] = int(cset.get("slowmode_secs", 1800))
        ch = await cat.create_text_channel(name, **kwargs)
        created.append(ch)

    for kind, suffix in LOGS_KINDS:
        await make(logs_cat, kind, suffix)
    for kind, suffix in CHAT_KINDS:
        await make(chat_cat, kind, suffix)
    return created


# ===========================================================================
# Settings UI  (/stgamesettings)
# ===========================================================================

def _mark(v):
    return "🟢" if v else "🔴"


class BaseSettingsView(discord.ui.View):
    """Common plumbing: owns a user, persists on every change, guards clicks."""

    def __init__(self, owner_id):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.settings = load_settings(owner_id)

    async def interaction_check(self, interaction):
        # The owner may edit their own settings; a Clockmaker may edit anyone's.
        if interaction.user.id == self.owner_id or has_clockmaker(interaction.user):
            return True
        await interaction.response.send_message(
            "These settings aren't yours to change.", ephemeral=True)
        return False

    def persist(self):
        save_settings(self.owner_id, self.settings)

    async def show(self, interaction, view, content):
        await interaction.response.edit_message(content=content, view=view)


def toggle_button(label, getter, setter, row=0):
    """Build a green/red toggle button bound to getter/setter closures."""
    btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=row)

    async def cb(interaction):
        view = btn.view
        setter(view.settings, not getter(view.settings))
        view.persist()
        view.refresh()
        await interaction.response.edit_message(view=view)

    btn.callback = cb
    btn._getter = getter
    return btn


def _cget(s, kind, key, default=None):
    return s.get("channels", {}).get(kind, {}).get(key, default)


def _cset(s, kind, key, val):
    s.setdefault("channels", {}).setdefault(kind, {})[key] = val


# ---- Main menu ------------------------------------------------------------

class MainMenu(BaseSettingsView):
    def __init__(self, owner_id):
        super().__init__(owner_id)
        for label, target in [
            ("Channels", ChannelsMenu), ("Security", SecurityMenu),
            ("Townsfolk", lambda oid: RoleMenu(oid, "townsfolk", "Townsfolk", talk=False)),
            ("Tulpa", lambda oid: RoleMenu(oid, "tulpa", "Tulpa", talk=True)),
            ("Ascended", lambda oid: RoleMenu(oid, "ascended", "Ascended", talk=True)),
            ("Announcements", AnnouncementsMenu),
        ]:
            self.add_item(self._nav(label, target))

    def _nav(self, label, target):
        btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)

        async def cb(interaction):
            v = target(self.owner_id)
            await interaction.response.edit_message(content=v.title(), view=v)

        btn.callback = cb
        return btn

    def title(self):
        return "**Storyteller game settings** — pick a category:"


class BackButton(discord.ui.Button):
    def __init__(self, target=None):
        super().__init__(label="◀ Back", style=discord.ButtonStyle.danger, row=4)
        self._target = target

    async def callback(self, interaction):
        target = self._target or MainMenu
        v = target(self.view.owner_id)
        await interaction.response.edit_message(content=v.title(), view=v)


# ---- Security -------------------------------------------------------------

class SecurityMenu(BaseSettingsView):
    def __init__(self, owner_id):
        super().__init__(owner_id)
        self._build()

    def _build(self):
        self.clear_items()
        self.add_item(toggle_button(
            f"{_mark(self.settings['explicit_permission'])} Explicit permission",
            lambda s: s["explicit_permission"],
            lambda s, v: s.__setitem__("explicit_permission", v)))
        self.add_item(toggle_button(
            f"{_mark(self.settings['privacy'])} Privacy",
            lambda s: s["privacy"],
            lambda s, v: s.__setitem__("privacy", v)))
        self.add_item(BackButton())

    def refresh(self):
        self._build()

    def title(self):
        return ("**Security** — Explicit permission gives ST powers to *you* instead of the "
                "Storyteller role (and gates Ascension behind /ascend). Privacy hides the game "
                "from non-players.")


# ---- Role menus (Townsfolk / Tulpa / Ascended) ----------------------------

class RoleMenu(BaseSettingsView):
    def __init__(self, owner_id, key, label, talk):
        super().__init__(owner_id)
        self.key = key
        self.label = label
        self.talk = talk
        self._build()

    def _build(self):
        self.clear_items()
        d = self.settings[self.key]
        if self.talk:
            self.add_item(toggle_button(
                f"{_mark(d['talk'])} Talk in game chat",
                lambda s: s[self.key]["talk"],
                lambda s, v: s[self.key].__setitem__("talk", v)))
        self.add_item(toggle_button(
            f"{_mark(d['threads'])} Create threads",
            lambda s: s[self.key]["threads"],
            lambda s, v: s[self.key].__setitem__("threads", v)))
        self.add_item(toggle_button(
            f"{_mark(d['activities'])} Start activities",
            lambda s: s[self.key]["activities"],
            lambda s, v: s[self.key].__setitem__("activities", v)))
        self.add_item(BackButton())

    def refresh(self):
        self._build()

    def title(self):
        return f"**{self.label}** — permissions in the Game Chat channels."


# ---- Everyone (placeholder; spec undefined) -------------------------------

class EveryoneMenu(BaseSettingsView):
    def __init__(self, owner_id):
        super().__init__(owner_id)
        self.add_item(BackButton())

    def refresh(self):
        pass

    def title(self):
        return "**Everyone** — no configurable toggles yet (reserved)."


# ---- Channels menu --------------------------------------------------------

class ChannelsMenu(BaseSettingsView):
    def __init__(self, owner_id):
        super().__init__(owner_id)
        specs = [
            ("Ascension", lambda oid: ChannelToggleMenu(oid, "ascension", "Ascension", ascended_talk=True)),
            ("Ascension Chat", lambda oid: ChannelToggleMenu(oid, "ascension_chat", "Ascension Chat", ascended_talk=True)),
            ("Logs", lambda oid: ChannelToggleMenu(oid, "logs", "Logs")),
            ("Chat", lambda oid: ChannelToggleMenu(oid, "chat", "Chat", images=True, bots=True)),
            ("Focused", lambda oid: FocusedMenu(oid)),
            ("Whisper Logs", lambda oid: ChannelToggleMenu(oid, "whisper_logs", "Whisper Logs", images=True, bots=True)),
        ]
        for label, target in specs:
            self.add_item(self._nav(label, target))
        self.add_item(BackButton())

    def _nav(self, label, target):
        btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)

        async def cb(interaction):
            v = target(self.owner_id)
            await interaction.response.edit_message(content=v.title(), view=v)

        btn.callback = cb
        return btn

    def refresh(self):
        pass

    def title(self):
        return "**Channels** — configure each channel that /newgame creates:"


class ChannelToggleMenu(BaseSettingsView):
    def __init__(self, owner_id, kind, label, ascended_talk=False, images=False, bots=False):
        super().__init__(owner_id)
        self.kind = kind
        self.label = label
        self.has_ascended_talk = ascended_talk
        self.has_images = images
        self.has_bots = bots
        self._build()

    def _build(self):
        self.clear_items()
        k = self.kind
        self.add_item(toggle_button(
            f"{_mark(_cget(self.settings, k, 'create', True))} Create channel",
            lambda s: _cget(s, k, "create", True),
            lambda s, v: _cset(s, k, "create", v)))
        if self.has_ascended_talk:
            self.add_item(toggle_button(
                f"{_mark(_cget(self.settings, k, 'ascended_talk', True))} Ascended can talk",
                lambda s: _cget(s, k, "ascended_talk", True),
                lambda s, v: _cset(s, k, "ascended_talk", v)))
        if self.has_images:
            self.add_item(toggle_button(
                f"{_mark(_cget(self.settings, k, 'images', True))} Allow images",
                lambda s: _cget(s, k, "images", True),
                lambda s, v: _cset(s, k, "images", v)))
        if self.has_bots:
            self.add_item(toggle_button(
                f"{_mark(_cget(self.settings, k, 'bots', True))} Allow bots/activities",
                lambda s: _cget(s, k, "bots", True),
                lambda s, v: _cset(s, k, "bots", v)))
        self.add_item(BackButton(ChannelsMenu))

    def refresh(self):
        self._build()

    def title(self):
        return f"**{self.label}** channel settings:"


class FocusedMenu(BaseSettingsView):
    def __init__(self, owner_id):
        super().__init__(owner_id)
        self._build()

    def _build(self):
        self.clear_items()
        k = "focused"
        self.add_item(toggle_button(
            f"{_mark(_cget(self.settings, k, 'create', True))} Create channel",
            lambda s: _cget(s, k, "create", True),
            lambda s, v: _cset(s, k, "create", v)))
        self.add_item(toggle_button(
            f"{_mark(_cget(self.settings, k, 'slowmode', True))} Slowmode",
            lambda s: _cget(s, k, "slowmode", True),
            lambda s, v: _cset(s, k, "slowmode", v)))
        self.add_item(toggle_button(
            f"{_mark(_cget(self.settings, k, 'images', True))} Allow images",
            lambda s: _cget(s, k, "images", True),
            lambda s, v: _cset(s, k, "images", v)))
        self.add_item(toggle_button(
            f"{_mark(_cget(self.settings, k, 'bots', True))} Allow bots/activities",
            lambda s: _cget(s, k, "bots", True),
            lambda s, v: _cset(s, k, "bots", v)))
        self.add_item(self._slow_select())
        self.add_item(BackButton(ChannelsMenu))

    def _slow_select(self):
        cur = _cget(self.settings, "focused", "slowmode_secs", 1800)
        options = [
            discord.SelectOption(label=lbl, value=str(sec), default=(sec == cur))
            for lbl, sec in SLOWMODE_OPTIONS if sec != 0
        ]
        sel = discord.ui.Select(placeholder="Slowmode interval", options=options, row=3)

        async def cb(interaction):
            _cset(self.settings, "focused", "slowmode_secs", int(sel.values[0]))
            self.persist()
            self._build()
            await interaction.response.edit_message(view=self)

        sel.callback = cb
        return sel

    def refresh(self):
        self._build()

    def title(self):
        return "**Focused** channel settings:"


# ---- Announcements (Votelock + Day/Night) ---------------------------------

def _parse_hhmm(s):
    m = re.match(r"^(\d{1,2}):(\d{2})$", (s or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return (h, mi) if 0 <= h <= 23 and 0 <= mi <= 59 else None


def _ann(s):
    return s.setdefault("announcements", {})


def _vl(s):
    return _ann(s).setdefault("votelock", {})


def _dn(s):
    return _ann(s).setdefault("daynight", {})


class _TextModal(discord.ui.Modal):
    """Generic 1-2 field text modal that writes back into a settings view.
    `fields` = list of (label, default, style, required); `apply(settings, values)`
    mutates settings and returns an error string (or None on success)."""

    def __init__(self, title, fields, parent, apply):
        super().__init__(title=title)
        self._parent = parent
        self._apply = apply
        self._inputs = []
        for label, default, style, required in fields:
            ti = discord.ui.TextInput(label=label, default=(default or ""), style=style,
                                      required=required, max_length=300)
            self.add_item(ti)
            self._inputs.append(ti)

    async def on_submit(self, interaction):
        err = self._apply(self._parent.settings, [ti.value for ti in self._inputs])
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        self._parent.persist()
        self._parent.refresh()
        await interaction.response.edit_message(content=self._parent.title(), view=self._parent)


class AnnouncementsMenu(BaseSettingsView):
    def __init__(self, owner_id):
        super().__init__(owner_id)
        self.add_item(self._nav("Votelock", VotelockMenu))
        self.add_item(self._nav("Day / Night", DayNightMenu))
        self.add_item(BackButton())

    def _nav(self, label, target):
        btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)

        async def cb(interaction):
            v = target(self.owner_id)
            await interaction.response.edit_message(content=v.title(), view=v)

        btn.callback = cb
        return btn

    def title(self):
        return "**Announcements** — pick one:"


class VotelockMenu(BaseSettingsView):
    def __init__(self, owner_id):
        super().__init__(owner_id)
        self._build()

    def _build(self):
        self.clear_items()
        v = _vl(self.settings)
        self.add_item(toggle_button(
            f"{_mark(v.get('enabled', False))} Enabled",
            lambda s: _vl(s).get('enabled', False),
            lambda s, val: _vl(s).__setitem__('enabled', val)))
        self.add_item(toggle_button(
            f"{_mark(v.get('track_votes', False))} Track votes",
            lambda s: _vl(s).get('track_votes', False),
            lambda s, val: _vl(s).__setitem__('track_votes', val)))
        self.add_item(self._opener("✏ Message", self._edit_message, row=1))
        self.add_item(self._opener("🕐 Time", self._edit_time, row=1))
        self.add_item(self._opener("⏱ Duration", self._edit_duration, row=1))
        self.add_item(self._tz_select())
        self.add_item(BackButton(AnnouncementsMenu))

    def _opener(self, label, cb, row):
        b = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=row)
        b.callback = cb
        return b

    async def _edit_message(self, interaction):
        def apply(s, vals):
            _vl(s)["message"] = vals[0].strip() or "@Townsfolk votes are locked."
            return None
        await interaction.response.send_modal(_TextModal(
            "Votelock message",
            [("Message (@everyone shows as text, never pings)",
              _vl(self.settings).get("message", ""), discord.TextStyle.paragraph, False)],
            self, apply))

    async def _edit_time(self, interaction):
        v = _vl(self.settings)
        cur = "" if v.get("hour") is None else f"{v['hour']:02d}:{v['minute']:02d}"

        def apply(s, vals):
            hm = _parse_hhmm(vals[0])
            if hm is None:
                return "Couldn't read that time. Use 24-hour HH:MM, e.g. 12:30 or 23:21."
            _vl(s)["hour"], _vl(s)["minute"] = hm
            return None
        await interaction.response.send_modal(_TextModal(
            "Votelock start time", [("Time (24h HH:MM)", cur, discord.TextStyle.short, True)], self, apply))

    async def _edit_duration(self, interaction):
        def apply(s, vals):
            try:
                n = int(vals[0].strip())
                if n <= 0:
                    raise ValueError
            except ValueError:
                return "Duration must be a positive whole number of minutes."
            _vl(s)["duration_min"] = n
            return None
        await interaction.response.send_modal(_TextModal(
            "Votelock duration",
            [("Minutes to watch after lock", str(_vl(self.settings).get("duration_min", 60)),
              discord.TextStyle.short, True)], self, apply))

    def _tz_select(self):
        cur = _vl(self.settings).get("tz", "America/Chicago")
        opts = [discord.SelectOption(label=name, value=val, default=(val == cur))
                for name, val in votelock.TZ_CHOICES.items()]
        sel = discord.ui.Select(placeholder="Timezone", options=opts, row=2)

        async def cb(interaction):
            _vl(self.settings)["tz"] = sel.values[0]
            self.persist()
            self._build()
            await interaction.response.edit_message(content=self.title(), view=self)

        sel.callback = cb
        return sel

    def refresh(self):
        self._build()

    def title(self):
        v = _vl(self.settings)
        t = "not set" if v.get("hour") is None else f"{v['hour']:02d}:{v['minute']:02d}"
        tzname = next((n for n, val in votelock.TZ_CHOICES.items() if val == v.get('tz')), v.get('tz', '—'))
        return ("**Votelock** — automated daily 'votes are locked' post.\n"
                f"{_mark(v.get('enabled', False))} enabled · **{t}** {tzname} · watch **{v.get('duration_min', 60)}m**\n"
                f"{_mark(v.get('track_votes', False))} **track votes** — at lock, posts who's voting on what in "
                "ascension chat, then alerts on any vote added/removed during the window (no grace period).\n"
                f"message: `{v.get('message', '')}`\n"
                "Start for a game with **/startgame**; skip a day with **/skiplock**.")


class DayNightMenu(BaseSettingsView):
    _LABELS = {"day": "Day", "night": "Night", "custom": "Custom"}

    def __init__(self, owner_id):
        super().__init__(owner_id)
        self._build()

    def _build(self):
        self.clear_items()
        rules = _dn(self.settings).get("rules", [])
        for idx, rule in enumerate(rules):
            label = self._LABELS.get(rule.get("kind"), f"Rule {idx + 1}")
            self.add_item(self._toggle_btn(idx, label, idx))
            self.add_item(self._edit_btn(idx, label, idx))
        self.add_item(BackButton(AnnouncementsMenu))

    def _toggle_btn(self, idx, label, row):
        on = _dn(self.settings)["rules"][idx].get("enabled", False)
        b = discord.ui.Button(label=f"{_mark(on)} {label}", style=discord.ButtonStyle.secondary, row=row)

        async def cb(interaction):
            r = _dn(self.settings)["rules"][idx]
            r["enabled"] = not r.get("enabled", False)
            self.persist()
            self._build()
            await interaction.response.edit_message(content=self.title(), view=self)

        b.callback = cb
        return b

    def _edit_btn(self, idx, label, row):
        b = discord.ui.Button(label=f"✏ {label}", style=discord.ButtonStyle.secondary, row=row)

        async def cb(interaction):
            rule = _dn(self.settings)["rules"][idx]

            def apply(s, vals):
                r = _dn(s)["rules"][idx]
                r["trigger"], r["output"] = vals[0].strip(), vals[1].strip()
                return None
            await interaction.response.send_modal(_TextModal(
                f"{label} echo",
                [("Trigger ({n} = require a number there)", rule.get("trigger", ""), discord.TextStyle.short, False),
                 ("Output (vars: {n}, {day}, {night})", rule.get("output", ""), discord.TextStyle.paragraph, False)],
                self, apply))

        b.callback = cb
        return b

    def refresh(self):
        self._build()

    def title(self):
        lines = ["**Day / Night echoes** — type a trigger in the logs channel; the output posts to game chat.",
                 "Toggle each on/off; ✏ edits its trigger/output. All are **off** by default."]
        for rule in _dn(self.settings).get("rules", []):
            lines.append(f"{_mark(rule.get('enabled', False))} **{rule.get('kind', 'custom').title()}**: "
                         f"`{rule.get('trigger', '') or '—'}` → `{rule.get('output', '') or '—'}`")
        lines.append("`{n}` = this echo's number (typed, or auto-increments if the trigger has no `{n}`). "
                     "`{day}`/`{night}` = the latest Day/Night number, for referencing in another echo.")
        return "\n".join(lines)


# ===========================================================================
# Command registration
# ===========================================================================

def register(bot):
    """Attach all game-management commands to the bot's command tree."""

    @bot.tree.command(name="newgame", description="Create a fresh set of game channels (archives the previous game).")
    @app_commands.describe(number="Game number (defaults to last game + 1).",
                           as_user="Build using this Storyteller's settings (they become the ST under Explicit Permission).",
                           as_name="…or type that Storyteller's name / nickname instead.")
    @st_check()
    async def newgame(interaction: discord.Interaction, number: int | None = None,
                      as_user: discord.Member = None, as_name: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild

        # Optionally run "as" another Storyteller: use their settings, and make
        # them the initiator (the ST who gets powers under Explicit Permission).
        initiator = interaction.user
        if as_user is not None or as_name:
            initiator, err = pick_member(guild, as_user, as_name)
            if initiator is None:
                await interaction.followup.send(err, ephemeral=True)
                return
        s = load_settings(initiator.id)

        if number is None:
            last = latest_game_number(guild)
            number = (last + 1) if last is not None else 1

        log = []
        prev = current_game_channels(guild)
        moved = 0
        if prev:
            moved = await archive_channels(guild, prev, log)

        created = await create_game_channels(guild, number, s, initiator, log)
        set_game_st(guild.id, number, initiator.id)

        msg = [f"**Game {number}** created — {len(created)} channel(s)."]
        if initiator.id != interaction.user.id:
            msg.append(f"Using **{initiator.display_name}**'s settings.")
        if moved:
            msg.append(f"Archived {moved} channel(s) from the previous game.")
        if created:
            msg.append("Created: " + ", ".join(c.mention for c in created))
        if log:
            msg.append("⚠️ " + "; ".join(log))
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @bot.tree.command(name="archivegame", description="Move the current game's channels into an Archive category.")
    @st_check()
    async def archivegame(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        chans = current_game_channels(guild)
        if not chans:
            await interaction.followup.send("No channels in Game Logs / Game Chat to archive.", ephemeral=True)
            return
        log = []
        moved = await archive_channels(guild, chans, log)
        msg = [f"Archived **{moved}** channel(s)."]
        if log:
            msg.append("⚠️ " + "; ".join(log))
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @bot.tree.command(name="endgame", description="Reveal the current game's ascension channels to everyone.")
    @current_game_st_check()
    async def endgame(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        votelock.deactivate(guild.id)  # stop the daily votelock cycle
        ev = guild.default_role
        # Prefer the game of the channel this was run in; else the latest game.
        target_num = game_number_from_name(getattr(interaction.channel, "name", "") or "")
        if target_num is None:
            target_num = latest_game_number(guild)
        revealed = []
        for c in current_game_channels(guild):
            if game_number_from_name(c.name) != target_num:
                continue
            if c.name.endswith("-ascension") or c.name.endswith("-ascension-chat"):
                try:
                    # Merge into the existing @everyone overwrite so the
                    # send_messages=False deny is preserved (view only).
                    ow = c.overwrites_for(ev)
                    ow.view_channel = True
                    await c.set_permissions(ev, overwrite=ow)
                    revealed.append(c.mention)
                except Exception:
                    pass
        note = "\nVotelock cycle stopped."
        if revealed:
            await interaction.followup.send("Revealed: " + ", ".join(revealed) + note, ephemeral=True)
        else:
            await interaction.followup.send("No ascension channels found for that game." + note, ephemeral=True)

    @bot.tree.command(name="ascend", description="Grant a user the Ascended role (or explicit ascension access).")
    @app_commands.describe(user="Pick the player to ascend.",
                           name="…or type a name / nickname instead.")
    @current_game_st_check()
    async def ascend(interaction: discord.Interaction,
                     user: discord.Member = None, name: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        member, err = pick_member(guild, user, name)
        if member is None:
            await interaction.followup.send(err, ephemeral=True)
            return
        s = load_settings(interaction.user.id)
        if not s.get("explicit_permission", False):
            role = resolve_role(guild, R_ASCENDED)
            if role is None:
                await interaction.followup.send("No **Ascended** role found.", ephemeral=True)
                return
            await member.add_roles(role, reason=f"/ascend by {interaction.user}")
            await interaction.followup.send(f"Gave **Ascended** to {member.mention}.", ephemeral=True)
            return
        # Explicit permission: grant per-user access to this game's ascension channels.
        target_num = game_number_from_name(getattr(interaction.channel, "name", "") or "")
        if target_num is None:
            target_num = latest_game_number(guild)
        granted = []
        for c in current_game_channels(guild):
            if game_number_from_name(c.name) != target_num:
                continue
            if c.name.endswith("-ascension") or c.name.endswith("-ascension-chat"):
                await c.set_permissions(member, view_channel=True, send_messages=True)
                granted.append(c.mention)
        if granted:
            await interaction.followup.send(
                f"Granted {member.mention} access to " + ", ".join(granted), ephemeral=True)
        else:
            await interaction.followup.send("No ascension channels found for that game.", ephemeral=True)

    @bot.tree.command(name="addst", description="Give a user the Storyteller role (plus explicit ST permissions if enabled).")
    @app_commands.describe(user="Pick the member to make a Storyteller.",
                           name="…or type a name / nickname instead.")
    @current_game_st_check()
    async def addst(interaction: discord.Interaction,
                    user: discord.Member = None, name: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        member, err = pick_member(guild, user, name)
        if member is None:
            await interaction.followup.send(err, ephemeral=True)
            return
        st_role = resolve_role(guild, R_ST)
        if st_role is None:
            await interaction.followup.send("No **Storyteller** role found.", ephemeral=True)
            return
        await member.add_roles(st_role, reason=f"/addst by {interaction.user}")
        msg = [f"Gave **Storyteller** to {member.mention}."]

        # Under Explicit Permission the ST role carries no channel access — the
        # Storyteller's powers live as per-member overwrites (see build_overwrites,
        # st_target = initiator). So a newly-added ST needs those same explicit
        # overwrites on this game's channels to actually have ST powers.
        s = load_settings(interaction.user.id)
        if s.get("explicit_permission", False):
            target_num = game_number_from_name(getattr(interaction.channel, "name", "") or "")
            if target_num is None:
                target_num = latest_game_number(guild)
            granted = []
            for c in current_game_channels(guild):
                if game_number_from_name(c.name) != target_num:
                    continue
                try:
                    await c.set_permissions(
                        member, overwrite=discord.PermissionOverwrite(**ST_PERMS),
                        reason=f"/addst explicit by {interaction.user}")
                    granted.append(c.mention)
                except Exception:
                    pass
            if granted:
                msg.append("Explicit permission is on — granted ST access to "
                           + ", ".join(granted) + ".")
            else:
                msg.append("Explicit permission is on, but no channels for that game were found.")
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @bot.tree.command(name="addtown", description="Give a user the Townsfolk role and permission to talk in game chat.")
    @app_commands.describe(user="Pick the player.",
                           name="…or type a name / nickname instead.")
    @current_game_st_check()
    async def addtown(interaction: discord.Interaction,
                      user: discord.Member = None, name: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        member, err = pick_member(guild, user, name)
        if member is None:
            await interaction.followup.send(err, ephemeral=True)
            return
        tf = resolve_role(guild, R_TOWNSFOLK)
        if tf is None:
            await interaction.followup.send("No **Townsfolk** role found.", ephemeral=True)
            return
        try:
            await member.add_roles(tf, reason=f"/addtown by {interaction.user}")
        except discord.Forbidden:
            me = guild.me
            hint = ("my role isn't high enough — drag **{my}** above **{tf}**"
                    if me.top_role <= tf else "I'm missing the **Manage Roles** permission")
            await interaction.followup.send(
                f"I couldn't assign **{tf.name}** (Discord said *Missing Permissions*). "
                f"In **{guild.name}**, {hint.format(my=me.top_role.name, tf=tf.name)} "
                f"in **Server Settings → Roles**, then try again.", ephemeral=True)
            return
        # Give a per-member talk overwrite on this game's Game Chat channels. This
        # is what actually enables talking under Explicit Permission (where the
        # Townsfolk role no longer auto-grants it); harmless otherwise.
        target_num = game_number_from_name(getattr(interaction.channel, "name", "") or "")
        if target_num is None:
            target_num = latest_game_number(guild)
        granted = []
        for c in current_game_channels(guild):
            if game_number_from_name(c.name) != target_num:
                continue
            if c.category and c.category.name.lower() == CAT_CHAT.lower():
                try:
                    await c.set_permissions(member, send_messages=True,
                                            reason=f"/addtown by {interaction.user}")
                    granted.append(c.mention)
                except Exception:
                    pass
        msg = [f"Gave **Townsfolk** to {member.mention}."]
        if granted:
            msg.append("Can talk in " + ", ".join(granted) + ".")
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @bot.tree.command(name="addtulpa", description="Give a user the Tulpa role and access to this game's chat.")
    @app_commands.describe(user="Pick the player.",
                           name="…or type a name / nickname instead.")
    @current_game_st_check()
    async def addtulpa(interaction: discord.Interaction,
                       user: discord.Member = None, name: str = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        member, err = pick_member(guild, user, name)
        if member is None:
            await interaction.followup.send(err, ephemeral=True)
            return
        tul = resolve_role(guild, R_TULPA)
        if tul is None:
            await interaction.followup.send("No **Tulpa** role found.", ephemeral=True)
            return
        try:
            await member.add_roles(tul, reason=f"/addtulpa by {interaction.user}")
        except discord.Forbidden:
            me = guild.me
            hint = ("my role isn't high enough — drag **{my}** above **{tf}**"
                    if me.top_role <= tul else "I'm missing the **Manage Roles** permission")
            await interaction.followup.send(
                f"I couldn't assign **{tul.name}** (Discord said *Missing Permissions*). "
                f"In **{guild.name}**, {hint.format(my=me.top_role.name, tf=tul.name)} "
                f"in **Server Settings → Roles**, then try again.", ephemeral=True)
            return
        # Per-member overwrite on this game's Game Chat channels: always grant view
        # (so the Tulpa can follow the game even under Privacy), and grant talk only
        # when the game Storyteller's Tulpa 'talk' setting is on.
        target_num = game_number_from_name(getattr(interaction.channel, "name", "") or "")
        if target_num is None:
            target_num = latest_game_number(guild)
        st_id = get_game_st(guild.id, target_num) if target_num is not None else None
        can_talk = load_settings(st_id or interaction.user.id).get("tulpa", {}).get("talk", False)
        granted = []
        for c in current_game_channels(guild):
            if game_number_from_name(c.name) != target_num:
                continue
            if c.category and c.category.name.lower() == CAT_CHAT.lower():
                kwargs = {"view_channel": True}
                if can_talk:
                    kwargs["send_messages"] = True
                try:
                    await c.set_permissions(member, reason=f"/addtulpa by {interaction.user}", **kwargs)
                    granted.append(c.mention)
                except Exception:
                    pass
        msg = [f"Gave **Tulpa** to {member.mention}."]
        if granted:
            msg.append(f"Can {'see and talk in' if can_talk else 'see'} " + ", ".join(granted) + ".")
            if not can_talk:
                msg.append("*(Tulpa **talk** is off in setupsettings — view only. Turn it on to let them post.)*")
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @bot.tree.command(name="assignplayers", description="Assign Townsfolk to signups in #recruiting (grants talk under Explicit Permission).")
    @st_check()
    async def assignplayers(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        recruiting = discord.utils.find(
            lambda c: c.name.lower() == RECRUIT_CHANNEL and isinstance(c, discord.TextChannel),
            guild.channels)
        if recruiting is None:
            await interaction.followup.send("No #recruiting channel found.", ephemeral=True)
            return

        # Find the most recent message with a reaction of >= threshold.
        signup = None
        async for m in recruiting.history(limit=100):
            if any(r.count >= REACTION_THRESHOLD for r in m.reactions):
                signup = m
                break
        if signup is None:
            await interaction.followup.send(
                f"No recent signup post with {REACTION_THRESHOLD}+ reactions found.", ephemeral=True)
            return

        # Pick the emoji with the most reactions and gather its reactors.
        top = max(signup.reactions, key=lambda r: r.count)
        signups = [u async for u in top.users() if not u.bot]

        strip_names = [R_ST, R_ASCENDED, R_TRAVELER, R_TULPA, R_TOWNSFOLK]
        strip_roles = [r for r in (resolve_role(guild, n) for n in strip_names) if r]
        tf = resolve_role(guild, R_TOWNSFOLK)
        if tf is None:
            await interaction.followup.send("No **Townsfolk** role found.", ephemeral=True)
            return

        stripped = 0
        for member in guild.members:
            if member.id == interaction.user.id or member.bot:
                continue
            to_remove = [r for r in strip_roles if r in member.roles]
            if to_remove:
                try:
                    await member.remove_roles(*to_remove, reason="/assignplayers reset")
                    stripped += 1
                except Exception:
                    pass

        assigned_members = []
        for u in signups:
            member = guild.get_member(u.id)
            if member is None:
                continue
            try:
                await member.add_roles(tf, reason="/assignplayers signup")
                assigned_members.append(member)
            except Exception:
                pass
        assigned = len(assigned_members)

        # Under Explicit Permission the Townsfolk role doesn't grant talk, so give
        # each assigned player a per-member talk overwrite on the latest game's chat.
        note = ""
        s = load_settings(interaction.user.id)
        if s.get("explicit_permission", False) and assigned_members:
            num = latest_game_number(guild)
            chat_chans = [c for c in current_game_channels(guild)
                          if game_number_from_name(c.name) == num
                          and c.category and c.category.name.lower() == CAT_CHAT.lower()]
            for member in assigned_members:
                for c in chat_chans:
                    try:
                        await c.set_permissions(member, send_messages=True, reason="/assignplayers talk")
                    except Exception:
                        pass
            if chat_chans:
                note = f"\nExplicit permission on — granted talk in {len(chat_chans)} chat channel(s)."

        await interaction.followup.send(
            f"Signup post by {signup.author.display_name} using {top.emoji}.\n"
            f"Stripped roles from **{stripped}** member(s); assigned **Townsfolk** to **{assigned}** signup(s)." + note,
            ephemeral=True)

    @bot.tree.command(name="setupsettings", description="Customize the permissions and announcements /newgame applies.")
    @app_commands.describe(user="(Clockmaker only) edit this player's settings instead of your own.",
                           name="(Clockmaker only) …or by name / nickname.")
    async def setupsettings(interaction: discord.Interaction,
                            user: discord.Member = None, name: str = None):
        owner_id = interaction.user.id
        prefix = ""
        if user is not None or name:
            if not has_clockmaker(interaction.user):
                await interaction.response.send_message(
                    "Only the **Clockmaker** role can edit another user's settings.", ephemeral=True)
                return
            member, err = pick_member(interaction.guild, user, name)
            if member is None:
                await interaction.response.send_message(err, ephemeral=True)
                return
            owner_id = member.id
            if owner_id != interaction.user.id:
                prefix = f"⚙️ Editing **{member.display_name}**'s settings.\n"
        view = MainMenu(owner_id)
        await interaction.response.send_message(prefix + view.title(), view=view, ephemeral=True)

    @newgame.error
    @archivegame.error
    @assignplayers.error
    @setupsettings.error
    async def _err(interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = ("You need the **Storyteller** role to use this."
               if isinstance(error, app_commands.CheckFailure)
               else f"Error: {error}")
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    @ascend.error
    @addst.error
    @addtown.error
    @addtulpa.error
    @endgame.error
    async def _err_game_st(interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = ("Only the **current game's Storyteller** can use this."
               if isinstance(error, app_commands.CheckFailure)
               else f"Error: {error}")
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
