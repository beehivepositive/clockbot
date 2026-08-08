import discord
from typing import Optional
from discord.ext import commands, tasks
from discord import app_commands
import os, io, random, aiohttp, tempfile, re, asyncio, json
from datetime import timezone
from dotenv import load_dotenv
from botc_runner import run_botc_code, get_character_info, get_game, set_game, delete_game, format_game_state, make_player, infer_char_type, infer_alignment
import datetime, pytz
from botc_st import start_night, end_night, end_day, handle_dm_action, find_pending_game as find_pending_botc_game, resolve_execution as botc_resolve_execution
from game_state import load_whisper_state,save_whisper_state,get_game_state,set_game_state,get_game_key,is_excluded,find_dest
import botc_games
import botc_stchats
import botc_scripts
import botc_html
import reminders
import votelock
import ghost
CST = pytz.timezone('America/Chicago')

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def setup_hook():
    await bot.load_extension("dwarf_explorer.cog")

bot.setup_hook = setup_hook

DAY_PATTERN = re.compile(r"^#\s*Day\s+\d+", re.IGNORECASE)
COMMON_NAMES_PATH = "/home/discord-bot/common_names.json"
NOM_TRIGGER = re.compile(r"^(nom(?:inate)?)\s*(.*)", re.IGNORECASE)
JUGGLE_TRIGGER = re.compile(r"^juggl?e?\b(.*)", re.IGNORECASE)



@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

GUILD_ID = 1339575347032621191
TEST_GUILD_ID = 1291933524760199260

_commands_synced = False

@bot.event
async def on_ready():
    global _commands_synced
    if not _commands_synced:
        # User-installable commands (e.g. /assignrole) must live in the GLOBAL scope
        # so they work in DMs where the app is user-installed. Pull them out before
        # the per-guild copy, then restore them globally afterward.
        USER_INSTALL = {"assignrole"}
        pulled = [c for c in (bot.tree.remove_command(n) for n in USER_INSTALL) if c is not None]
        # Register the remaining commands PER-GUILD (fast updates, no duplicates).
        for g in bot.guilds:
            try:
                bot.tree.copy_global_to(guild=g)
                await bot.tree.sync(guild=g)
            except Exception as e:
                print(f"Guild sync failed for {g.id}: {e}")
        # Global scope keeps ONLY the user-install commands (clear the guild-copied
        # ones from global first so they aren't duplicated).
        bot.tree.clear_commands(guild=None)
        for c in pulled:
            bot.tree.add_command(c)
        await bot.tree.sync()
        _commands_synced = True
    print(f"Logged in as {bot.user}")


def load_common_names():
    if os.path.exists(COMMON_NAMES_PATH):
        with open(COMMON_NAMES_PATH) as f: return json.load(f)
    return {}

def save_common_names(data):
    with open(COMMON_NAMES_PATH,"w") as f: json.dump(data,f,indent=2)

def is_game_category_channel(channel):
    cat = channel.category
    if not cat: return False
    n = cat.name.lower()
    return "game chat" in n or "game logs" in n

def is_whisper_channel(i):
    ch=i.channel
    return ch.category and "game chat" in ch.category.name.lower() and "whisper" in ch.name.lower()



@bot.tree.command(name="channeltohtml", description="Export all messages in a channel to an HTML transcript")
@app_commands.describe(channel="The channel to archive")
@app_commands.check(lambda i: any(r.name.lower() == "pixie" for r in i.user.roles))
async def channeltohtml(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(thinking=True)
    outpath = f"/tmp/{channel.name}-archive.html"
    try:
        cnt = await botc_html.channel_to_html(channel, interaction.guild, outpath, bot=bot)
        if not cnt:
            await interaction.followup.send("No messages found.")
            return
        await interaction.followup.send(
            content=f"📄 Archive of **#{channel.name}** ({cnt} messages)",
            file=discord.File(outpath, filename=f"{channel.name}-archive.html"))
    except discord.Forbidden:
        await interaction.followup.send("No permission to read that channel.")
    except discord.HTTPException as e:
        if e.code == 40005:
            await interaction.followup.send(
                "That transcript is over this server's Discord upload limit. Ping me to add splitting.")
        else:
            await interaction.followup.send(f"Error: {e}")
    except Exception as e:
        await interaction.followup.send(f"Error: {e}")
    finally:
        try:
            os.unlink(outpath)
        except Exception:
            pass



def render_echo(tpl, n, d):
    """Substitute echo variables into an output template."""
    return (tpl.replace("{n}", str(n))
               .replace("{day}", str(d.get("day", 0)))
               .replace("{night}", str(d.get("night", 0))))


# @everyone may appear as literal TEXT but must never actually ping the server.
_SAFE_MENTIONS = discord.AllowedMentions(everyone=False)


def _compile_trigger(trig):
    """Build a match regex for a trigger. If it contains {n}, a number is REQUIRED
    there (e.g. '# Day {n}' fires only on '# Day 3'). Without {n}, a trailing number
    is optional and enables auto-increment (e.g. 'dusk' fires on 'dusk' or 'dusk 3')."""
    trig = re.sub(r"\s+", " ", trig).strip()
    if "{n}" in trig:
        pat = r"(\d+)".join(re.escape(p) for p in trig.split("{n}"))
        return re.compile(rf"^{pat}$", re.IGNORECASE)
    return re.compile(rf"^{re.escape(trig)}(?:\s*(\d+))?$", re.IGNORECASE)


async def handle_announcement_echo(message):
    """Configurable Day/Night/custom echo. The Storyteller types a rule's trigger
    (optionally followed by a number) in the -logs channel; the rendered output is
    mirrored to the game's chat channels only (never re-posted into -logs). Rules +
    templates come from the poster's /setupsettings; {n} is the number typed, else an
    auto-incrementing per-game counter. {day}/{night} expose the shared counters."""
    game_key = get_game_key(message.channel.name)
    if not game_key:
        return
    content = re.sub(r"\s+", " ", (message.content or "")).strip()
    if not content:
        return
    # Use the game's recorded Storyteller's settings (not the poster's), so the
    # echo config is consistent no matter who posts in logs. Fall back to the
    # poster if the game has no recorded ST (e.g. it predates ST tracking).
    owner = message.author.id
    try:
        num = botc_games.game_number_from_name(message.channel.name)
        if num is not None and message.guild is not None:
            st_id = botc_games.get_game_st(message.guild.id, num)
            if st_id:
                owner = st_id
    except Exception:
        pass
    try:
        rules = botc_games.load_settings(owner)["announcements"]["daynight"]["rules"]
    except Exception:
        rules = []
    for rule in rules:
        if not rule.get("enabled", False):
            continue
        trig = (rule.get("trigger") or "").strip()
        out_tpl = rule.get("output") or ""
        if not trig or not out_tpl:
            continue
        m = _compile_trigger(trig).match(content)
        if not m:
            continue
        kind = rule.get("kind", "custom")
        d = get_game_state(game_key)
        ckey = kind if kind in ("day", "night") else "echo_" + trig.lower()
        typed = m.group(1)
        n = int(typed) if typed is not None else int(d.get(ckey, 0)) + 1
        d[ckey] = n
        # Day rolls over the in-memory per-day nomination counters (no deletions).
        if kind == "day":
            d["used"] = 0; d["player_counts"] = {}; d["nominees"] = []; d["nominators"] = []
        set_game_state(game_key, d)
        out = render_echo(out_tpl, n, d)
        for ch in message.guild.text_channels:
            if get_game_key(ch.name) != game_key or ch.id == message.channel.id:
                continue
            cat = ch.category
            if cat and "game chat" in cat.name.lower():
                try:
                    await ch.send(out, allowed_mentions=_SAFE_MENTIONS)
                except Exception as e:
                    print(f"Echo mirror failed -> #{ch.name}: {e}")
        # Mirrored to the game-chat channels only — intentionally NOT re-posted
        # back into the -logs channel (the trigger message already lives there).
        return  # first matching rule wins

@bot.tree.command(name="add-common-name",description="Map a common name to a player")
@app_commands.describe(common_name="Common name",player="The player")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
async def add_common_name(i:discord.Interaction,common_name:str,player:discord.Member):
    cn=load_common_names(); cn[common_name.lower()]=player.id; save_common_names(cn)
    await i.response.send_message(f"{common_name} -> {player.display_name} saved.",ephemeral=True)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if isinstance(message.channel, discord.DMChannel):
        reply = await handle_dm_action(bot, str(message.author.id), message.content)
        await message.channel.send(reply)
        return
    await bot.process_commands(message)
    ch_name = message.channel.name
    if (ch_name.endswith('-logs') or ch_name.endswith('-log')) \
            and 'whisper' not in ch_name:
        await handle_announcement_echo(message)
        return
@bot.tree.command(name="syncchannels", description="Sync every channel in this category to the category's permissions", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(manage_channels=True)
async def syncchannels_cmd(interaction: discord.Interaction):
    category = interaction.channel.category
    if category is None:
        await interaction.response.send_message("This channel isn't inside a category.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    synced, failed = [], []
    for ch in category.channels:
        try:
            await ch.edit(sync_permissions=True)
            synced.append(ch.mention)
        except discord.Forbidden:
            failed.append(f"`{ch.name}` (missing permissions)")
        except Exception as e:
            failed.append(f"`{ch.name}` ({e})")

    lines = [f"Synced **{len(synced)}** channel(s) in **{category.name}** to category permissions."]
    if failed:
        lines.append("Failed: " + ", ".join(failed))
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@syncchannels_cmd.error
async def syncchannels_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("You need the **Manage Channels** permission to use this.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Error: {error}", ephemeral=True)


botc_games.register(bot)
botc_stchats.register(bot)
botc_scripts.register(bot)
reminders.register(bot)
votelock.register(bot)
ghost.register(bot)
bot.run(TOKEN)
