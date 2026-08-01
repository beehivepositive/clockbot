"""Votelock: a daily "votes are locked" announcement plus nomination/vote tracking.

Flow (Storyteller-only):
  /setupsettings -> Announcements -> Votelock  -> configure (enabled, message, time, duration, tz)
  /startgame                                   -> snapshot the ST's votelock settings + activate the cycle
  /skiplock                                    -> skip today's lock (resumes tomorrow)
  /endgame (in botc_games)                     -> deactivate

Each day at the lock time (while active) the bot posts the configured votelock message
in the current game's game-logs channel, then for `duration_minutes` it:
  * collects nomination messages (containing "nominates") posted in game-logs,
  * watches the up-arrow (:arrow_up:) reacts on them,
  * if a react is REMOVED during the window it alerts the Storyteller in
    ascension-chat with who removed it and which nomination — unless the react was
    added <3s earlier (misclick grace).
Settings persist across restarts; the live tracking window is in-memory.
"""

import os
import re
import time
import json
import datetime
import discord
import pytz
from discord import app_commands
from discord.ext import tasks

PATH = "/home/discord-bot/votelock.json" if os.path.isdir("/home/discord-bot") else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "votelock.json")

GRACE = 3.0                      # seconds: add-then-remove within this is ignored
UP_CODE = "⬆"               # :arrow_up: (U+2B06), with/without the U+FE0F variation selector

TZ_CHOICES = {
    "Central": "America/Chicago",
    "Eastern": "America/New_York",
    "Mountain": "America/Denver",
    "Pacific": "America/Los_Angeles",
    "UTC": "UTC",
}

# In-memory live tracking windows: guild_id(str) -> window dict
_windows = {}


# --------------------------------------------------------------------------
# Persistence + helpers
# --------------------------------------------------------------------------

def _load():
    if os.path.exists(PATH):
        try:
            with open(PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save(d):
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, PATH)


def deactivate(guild_id):
    """Stop the votelock cycle for a guild (called by /endgame)."""
    d = _load()
    g = d.get(str(guild_id))
    if g and g.get("active"):
        g["active"] = False
        _save(d)
    _windows.pop(str(guild_id), None)


def _is_up(emoji):
    s = getattr(emoji, "name", None) or str(emoji)
    return s.replace("️", "") == "⬆"


def _parse_time(s):
    s = s.strip().upper().replace(".", "")
    for fmt in ("%H:%M", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p", "%H"):
        try:
            t = datetime.datetime.strptime(s, fmt)
            return t.hour, t.minute
        except ValueError:
            continue
    return None


def _role(guild, name):
    return discord.utils.find(lambda r: r.name.lower() == name.lower(), guild.roles)


def _game_channels(guild):
    out = []
    for cat_name in ("Game Logs", "Game Chat"):
        cat = discord.utils.find(lambda c: c.name.lower() == cat_name.lower(), guild.categories)
        if cat:
            out.extend([c for c in cat.channels if isinstance(c, discord.TextChannel)])
    return out


def _find_logs(guild):
    for ch in _game_channels(guild):
        if ch.name.endswith("-logs") and "whisper" not in ch.name:
            return ch
    return None


def _find_ascension_chat(guild):
    for ch in _game_channels(guild):
        if ch.name.endswith("-ascension-chat"):
            return ch
    return None


def _is_st(i):
    return any(r.name.lower() == "storyteller" for r in getattr(i.user, "roles", []))


def _render_message(guild, text):
    """Turn '@RoleName' tokens into real role pings (except @everyone), and return
    AllowedMentions that permit those role pings but NEVER @everyone/@here."""
    roles = []
    out = text or "@Townsfolk votes are locked."
    for role in guild.roles:
        if role.is_default():
            continue
        tok = "@" + role.name
        if tok in out:
            out = out.replace(tok, role.mention)
            roles.append(role)
    return out, discord.AllowedMentions(everyone=False, roles=roles, users=False)


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

def register(bot):

    async def _fire(gid, cfg):
        guild = bot.get_guild(int(gid))
        if not guild:
            return
        logs = _find_logs(guild)
        if not logs:
            return
        text, am = _render_message(guild, cfg.get("message"))
        try:
            await logs.send(text, allowed_mentions=am)
        except Exception as e:
            print(f"votelock post failed: {e}")
            return
        asc = _find_ascension_chat(guild)
        _windows[gid] = {
            "end_ts": time.time() + cfg["duration_min"] * 60,
            "logs_id": logs.id,
            "asc_id": asc.id if asc else None,
            "noms": set(),
            "nom_text": {},
            "react_times": {},
        }

    @tasks.loop(seconds=20)
    async def votelock_loop():
        d = _load()
        changed = False
        for gid, cfg in list(d.items()):
            if not cfg.get("active") or "hour" not in cfg:
                continue
            try:
                now = datetime.datetime.now(pytz.timezone(cfg["tz"]))
                target = now.replace(hour=cfg["hour"], minute=cfg["minute"], second=0, microsecond=0)
                today = now.strftime("%Y-%m-%d")
                if 0 <= (now - target).total_seconds() < 60 and cfg.get("last_fired") != today:
                    cfg["last_fired"] = today
                    changed = True
                    await _fire(gid, cfg)
            except Exception as e:
                print(f"votelock loop err ({gid}): {e}")
        if changed:
            _save(d)
        # purge expired windows
        for gid in list(_windows):
            if time.time() > _windows[gid]["end_ts"]:
                del _windows[gid]

    @votelock_loop.before_loop
    async def _before():
        await bot.wait_until_ready()

    async def _start_loop():
        if not votelock_loop.is_running():
            votelock_loop.start()

    bot.add_listener(_start_loop, "on_ready")

    # ---- live tracking listeners ------------------------------------------

    async def _on_message(message):
        if message.guild is None:
            return
        w = _windows.get(str(message.guild.id))
        if not w or time.time() > w["end_ts"]:
            return
        if message.channel.id != w["logs_id"]:
            return
        if "nominates" in (message.content or "").lower():
            w["noms"].add(message.id)
            w["nom_text"][message.id] = (message.content or "").strip()[:120]

    async def _on_add(payload):
        if payload.guild_id is None or payload.user_id == bot.user.id:
            return
        w = _windows.get(str(payload.guild_id))
        if not w or time.time() > w["end_ts"] or payload.message_id not in w["noms"]:
            return
        if _is_up(payload.emoji):
            w["react_times"][(payload.message_id, payload.user_id)] = time.time()

    async def _on_remove(payload):
        if payload.guild_id is None or payload.user_id == bot.user.id:
            return
        w = _windows.get(str(payload.guild_id))
        if not w or time.time() > w["end_ts"] or payload.message_id not in w["noms"]:
            return
        if not _is_up(payload.emoji):
            return
        added = w["react_times"].pop((payload.message_id, payload.user_id), None)
        if added is not None and (time.time() - added) < GRACE:
            return  # add-then-remove misclick grace
        guild = bot.get_guild(payload.guild_id)
        if not guild or not w.get("asc_id"):
            return
        ch = guild.get_channel(w["asc_id"])
        if not ch:
            return
        member = guild.get_member(payload.user_id)
        who = member.display_name if member else f"User {payload.user_id}"
        st = _role(guild, "Storyteller")
        st_ping = (st.mention + " ") if st else ""
        jump = f"https://discord.com/channels/{payload.guild_id}/{w['logs_id']}/{payload.message_id}"
        txt = w["nom_text"].get(payload.message_id, "a nomination")
        try:
            await ch.send(
                f"{st_ping}⚠️ **{who}** removed their ⬆ vote from a locked nomination:\n> {txt}\n{jump}",
                allowed_mentions=discord.AllowedMentions(roles=[st] if st else False))
        except Exception as e:
            print(f"votelock alert failed: {e}")

    bot.add_listener(_on_message, "on_message")
    bot.add_listener(_on_add, "on_raw_reaction_add")
    bot.add_listener(_on_remove, "on_raw_reaction_remove")

    # ---- commands ---------------------------------------------------------

    @bot.tree.command(name="startgame", description="Start the daily votelock cycle using your /setupsettings.")
    @app_commands.check(lambda i: _is_st(i))
    async def startgame(interaction: discord.Interaction):
        import botc_games  # lazy import: avoids a circular import at module load
        vl = botc_games.load_settings(interaction.user.id).get("announcements", {}).get("votelock", {})
        if not vl.get("enabled"):
            await interaction.response.send_message(
                "Votelock is **off**. Turn it on in **/setupsettings → Announcements → Votelock**.", ephemeral=True)
            return
        if vl.get("hour") is None:
            await interaction.response.send_message(
                "Set a votelock **time** in /setupsettings first.", ephemeral=True)
            return
        d = _load()
        gid = str(interaction.guild_id)
        d[gid] = {
            "hour": vl["hour"], "minute": vl["minute"],
            "tz": vl.get("tz", "America/Chicago"),
            "duration_min": int(vl.get("duration_min", 60)),
            "message": vl.get("message", "@Townsfolk votes are locked."),
            "active": True, "last_fired": None,
        }
        _save(d)
        await interaction.response.send_message(
            f"Votelock started: daily at **{vl['hour']:02d}:{vl['minute']:02d}** ({d[gid]['tz']}), "
            f"watching nominations for **{d[gid]['duration_min']} min**. Stop with **/endgame**; skip a day with **/skiplock**.",
            ephemeral=True)

    @bot.tree.command(name="skiplock", description="Skip today's votelock; it resumes tomorrow.")
    @app_commands.check(lambda i: _is_st(i))
    async def skiplock(interaction: discord.Interaction):
        d = _load()
        gid = str(interaction.guild_id)
        cfg = d.get(gid)
        if not cfg or not cfg.get("active"):
            await interaction.response.send_message("No active votelock to skip.", ephemeral=True)
            return
        try:
            today = datetime.datetime.now(pytz.timezone(cfg.get("tz", "America/Chicago"))).strftime("%Y-%m-%d")
        except Exception:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
        cfg["last_fired"] = today  # mark as already handled today so the loop skips it
        _save(d)
        await interaction.response.send_message(
            "Today's votelock is **skipped** — it resumes tomorrow.", ephemeral=True)

    @startgame.error
    @skiplock.error
    async def _err(interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = ("You need the **Storyteller** role to use this."
               if isinstance(error, app_commands.CheckFailure) else f"Error: {error}")
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
