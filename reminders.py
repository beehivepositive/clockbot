"""/remindme — set a reminder that replies to your command when it's due.

Two ways to set the time:
  * relative: amount + unit (seconds/minutes/hours/days/months/years)
  * absolute: `at` as a typed date/time (Discord has no calendar-picker option type)

A slash command doesn't post a user message, so the bot's public confirmation of
the command is the thing the reminder replies to. Its reference is saved at
creation; if it's later deleted the reminder still fires (reply is dropped).
Extra users can be pinged via `also_ping`. Reminders persist to reminders.json
and are delivered by a background loop, so they survive restarts. Times are
interpreted in US Central; messages use Discord timestamps so each viewer sees
their own local time.
"""

import os
import re
import json
import calendar
import datetime
import discord
import pytz
from discord import app_commands
from discord.ext import tasks

CST = pytz.timezone("America/Chicago")
PATH = "/home/discord-bot/reminders.json" if os.path.isdir("/home/discord-bot") else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "reminders.json")

DATE_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                "%m/%d/%Y %H:%M", "%m/%d/%Y"]


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def _load():
    if os.path.exists(PATH):
        try:
            with open(PATH) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save(items):
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, PATH)


# --------------------------------------------------------------------------
# Time math
# --------------------------------------------------------------------------

def _add_months(dt, months):
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    day = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)


def add_relative(dt, amount, unit):
    if unit in ("seconds", "minutes", "hours", "days"):
        return dt + datetime.timedelta(**{unit: amount})
    if unit == "months":
        return _add_months(dt, amount)
    if unit == "years":
        return _add_months(dt, amount * 12)
    raise ValueError(f"unknown unit {unit}")


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

def register(bot):

    @tasks.loop(seconds=15)
    async def reminder_loop():
        now = datetime.datetime.now(CST).timestamp()
        items = _load()
        due = [r for r in items if r.get("due_ts", 0) <= now]
        if not due:
            return
        _save([r for r in items if r.get("due_ts", 0) > now])
        for r in due:
            try:
                ch = bot.get_channel(r["channel_id"]) or await bot.fetch_channel(r["channel_id"])
                pings = " ".join(f"<@{uid}>" for uid in r.get("ping_ids", []))
                content = (pings + " " if pings else "") + f"⏰ **Reminder:** {r['message']}"
                ref = None
                if r.get("reply_message_id"):
                    # fail_if_not_exists=False → if the original was deleted, still send (no reply).
                    ref = discord.MessageReference(
                        message_id=r["reply_message_id"],
                        channel_id=r["channel_id"],
                        fail_if_not_exists=False)
                await ch.send(content, reference=ref,
                              allowed_mentions=discord.AllowedMentions(users=True, replied_user=False))
            except Exception as e:
                print(f"reminder send failed ({r.get('id')}): {e}")

    @reminder_loop.before_loop
    async def _before():
        await bot.wait_until_ready()

    async def _start_loop():
        if not reminder_loop.is_running():
            reminder_loop.start()

    bot.add_listener(_start_loop, "on_ready")

    @bot.tree.command(name="remindme", description="Set a reminder; the bot replies to your command when it's due.")
    @app_commands.describe(
        message="What you want to be reminded about.",
        amount="How many <unit> from now (use together with unit).",
        unit="Time unit (use together with amount).",
        at="Or an exact date/time, e.g. 2026-08-15 14:30 (US Central). Overrides amount/unit.",
        also_ping="Extra users to ping when it's due — mention them here.",
    )
    @app_commands.choices(unit=[
        app_commands.Choice(name="seconds", value="seconds"),
        app_commands.Choice(name="minutes", value="minutes"),
        app_commands.Choice(name="hours", value="hours"),
        app_commands.Choice(name="days", value="days"),
        app_commands.Choice(name="months", value="months"),
        app_commands.Choice(name="years", value="years"),
    ])
    async def remindme(interaction: discord.Interaction, message: str,
                       amount: int | None = None,
                       unit: app_commands.Choice[str] | None = None,
                       at: str | None = None,
                       also_ping: str | None = None):
        now = datetime.datetime.now(CST)

        # Resolve the due time.
        if at:
            due_dt = None
            for fmt in DATE_FORMATS:
                try:
                    due_dt = CST.localize(datetime.datetime.strptime(at.strip(), fmt))
                    break
                except ValueError:
                    continue
            if due_dt is None:
                await interaction.response.send_message(
                    "Couldn't read that date. Try `YYYY-MM-DD HH:MM` (e.g. `2026-08-15 14:30`).",
                    ephemeral=True)
                return
        elif amount is not None and unit is not None:
            if amount <= 0:
                await interaction.response.send_message("Amount must be a positive number.", ephemeral=True)
                return
            due_dt = add_relative(now, amount, unit.value)
        elif amount is not None or unit is not None:
            await interaction.response.send_message(
                "Provide **both** `amount` and `unit`, or use `at` for an exact date.", ephemeral=True)
            return
        else:
            await interaction.response.send_message(
                "Tell me when: either `amount` + `unit`, or an `at` date/time.", ephemeral=True)
            return

        due_ts = int(due_dt.timestamp())
        if due_ts <= int(now.timestamp()):
            await interaction.response.send_message("That time is in the past.", ephemeral=True)
            return

        # Extra users to ping (the initiator is NOT pinged — the reminder replies to their command).
        ping_ids = []
        if also_ping:
            for uid in re.findall(r"<@!?(\d+)>", also_ping):
                if int(uid) not in ping_ids:
                    ping_ids.append(int(uid))

        # Public confirmation — this is the message the reminder will reply to.
        extra = (" and ping " + " ".join(f"<@{u}>" for u in ping_ids)) if ping_ids else ""
        await interaction.response.send_message(
            f"Reminder set for <t:{due_ts}:F> (<t:{due_ts}:R>). I'll reply here when it's due{extra}:\n> {message}",
            allowed_mentions=discord.AllowedMentions(users=bool(ping_ids)))
        try:
            conf = await interaction.original_response()
            reply_mid, jump = conf.id, conf.jump_url
        except Exception:
            reply_mid, jump = None, None

        items = _load()
        rid = (max((r.get("id", 0) for r in items), default=0) + 1)
        items.append({
            "id": rid,
            "guild_id": interaction.guild_id,
            "channel_id": interaction.channel_id,
            "user_id": interaction.user.id,
            "ping_ids": ping_ids,
            "message": message,
            "due_ts": due_ts,
            "created_ts": int(now.timestamp()),
            "reply_message_id": reply_mid,
            "jump_url": jump,
        })
        _save(items)
