import discord
from typing import Optional
from discord.ext import commands, tasks
from discord import app_commands
import os, io, random, aiohttp, tempfile, re, asyncio, json
from datetime import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image, Table, TableStyle
from reportlab.lib import colors
from dotenv import load_dotenv
from botc_runner import run_botc_code, get_character_info, get_game, set_game, delete_game, format_game_state, make_player, infer_char_type, infer_alignment
import datetime, pytz
from botc_st import start_night, end_night, end_day, handle_dm_action, find_pending_game as find_pending_botc_game, resolve_execution as botc_resolve_execution
from game_state import load_whisper_state,save_whisper_state,get_game_state,set_game_state,get_game_key,is_excluded,find_dest
import botc_games
import botc_scripts
import reminders
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

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
DAY_PATTERN = re.compile(r"^#\s*Day\s+\d+", re.IGNORECASE)
COMMON_NAMES_PATH = "/home/discord-bot/common_names.json"
NOM_TRIGGER = re.compile(r"^(nom(?:inate)?)\s*(.*)", re.IGNORECASE)
JUGGLE_TRIGGER = re.compile(r"^juggl?e?\b(.*)", re.IGNORECASE)
MAX_IMG_W = 150*mm
MAX_IMG_H = 150*mm
AVATAR_SIZE = 10*mm
MAX_PDF_BYTES = 25 * 1024 * 1024



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
        # Register commands PER-GUILD only (fast updates, no duplicates).
        for gid in (GUILD_ID, TEST_GUILD_ID):
            try:
                g = discord.Object(id=gid)
                bot.tree.copy_global_to(guild=g)
                await bot.tree.sync(guild=g)
            except Exception as e:
                print(f"Guild sync failed for {gid}: {e}")
        # Clear any previously-registered GLOBAL commands so they stop
        # showing up as duplicates alongside the guild copies.
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        _commands_synced = True
    print(f"Logged in as {bot.user}")


async def download_image(session, url, suffix=".png"):
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(data)
                tmp.close()
                return tmp.name
    except Exception:
        pass
    return None

def esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def resolve_mentions(content, msg):
    import re
    for user in msg.mentions:
        content = content.replace(f'<@{user.id}>', f'@{user.display_name}')
        content = content.replace(f'<@!{user.id}>', f'@{user.display_name}')
    for role in msg.role_mentions:
        content = content.replace(f'<@&{role.id}>', f'@{role.name}')
    for ch in msg.channel_mentions:
        content = content.replace(f'<#{ch.id}>', f'#{ch.name}')
    content = re.sub(r'<@!?(\d+)>', '@DeletedUser', content)
    content = re.sub(r'<@&(\d+)>', '@DeletedRole', content)
    content = re.sub(r'<#(\d+)>', '#DeletedChannel', content)
    return content

def fit_image(path, max_w, max_h):
    from PIL import Image as PILImage
    try:
        with PILImage.open(path) as im:
            w, h = im.size
        scale = min(max_w / w, max_h / h, 1.0)
        return Image(path, w * scale, h * scale)
    except Exception:
        return Image(path, max_w, max_h)

def make_styles():
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("TT", parent=styles["Heading1"], fontSize=18,
        textColor=colors.HexColor("#5865F2"), spaceAfter=4)
    meta_s = ParagraphStyle("MT", parent=styles["Normal"], fontSize=9,
        textColor=colors.grey, spaceAfter=10)
    author_s = ParagraphStyle("AT", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor("#5865F2"), fontName="Helvetica-Bold", spaceAfter=0)
    ts_s = ParagraphStyle("TST", parent=styles["Normal"], fontSize=8,
        textColor=colors.grey, spaceAfter=2)
    msg_s = ParagraphStyle("MST", parent=styles["Normal"], fontSize=10,
        spaceAfter=4, leading=14)
    return title_s, meta_s, author_s, ts_s, msg_s



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

def build_pdf_to_file(story, outpath):
    doc = SimpleDocTemplate(outpath, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm)
    doc.build(story)
    return os.path.getsize(outpath)

async def archive_channel(session, dest, channel, guild, tmp_files, avatar_cache, progress_ch=None):
    title_s, meta_s, author_s, ts_s, msg_s = make_styles()

    messages = []
    try:
        async for msg in channel.history(limit=None, oldest_first=True):
            messages.append(msg)
    except discord.Forbidden:
        if progress_ch:
            await progress_ch.send(f"  ⚠️ No permission to read **#{channel.name}**, skipping.")
        return
    except Exception as e:
        if progress_ch:
            await progress_ch.send(f"  ❌ Error reading **#{channel.name}**: {e}")
        return

    if not messages:
        if progress_ch:
            await progress_ch.send(f"  ⚠️ **#{channel.name}** is empty, skipping.")
        return

    part = 1
    story = []

    def start_story():
        s = []
        s.append(Paragraph(f"#{esc(channel.name)}" + (f" (Part {part})" if part > 1 else ""), title_s))
        s.append(Paragraph(f"Server: {esc(guild.name)} | Messages: {len(messages)}", meta_s))
        s.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#5865F2")))
        s.append(Spacer(1, 8))
        return s

    story = start_story()

    for msg in messages:
        ts = msg.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        author_id = msg.author.id
        if author_id not in avatar_cache:
            av_url = msg.author.display_avatar.with_format("png").with_size(64).url
            av_path = await download_image(session, av_url, ".png")
            avatar_cache[author_id] = av_path
        av_path = avatar_cache[author_id]
        name_block = [Paragraph(esc(msg.author.display_name), author_s),
                      Paragraph(ts, ts_s)]
        if av_path:
            try:
                av_img = Image(av_path, AVATAR_SIZE, AVATAR_SIZE)
                ht = Table([[av_img, name_block]], colWidths=[12*mm, None])
                ht.setStyle(TableStyle([
                    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ("LEFTPADDING",(0,0),(-1,-1),0),
                    ("RIGHTPADDING",(0,0),(-1,-1),4),
                    ("TOPPADDKNG",(0,0),(-1,-1),0),
                    ("BOTTOMPADDING",(0,0),(-1,-1),0),
                ]))
                story.append(ht)
            except Exception:
                story.append(Paragraph(esc(msg.author.display_name), author_s))
                story.append(Paragraph(ts, ts_s))
        else:
            story.append(Paragraph(esc(msg.author.display_name), author_s))
            story.append(Paragraph(ts, ts_s))

        content = resolve_mentions(msg.content or "", msg)
        if content:
            for line in content.split("\n"):
                if line.strip():
                    story.append(Paragraph(esc(line), msg_s))
                else:
                    story.append(Spacer(1, 4))

        for att in msg.attachments:
            ext = os.path.splitext(att.filename)[1].lower()
            if ext in IMAGE_EXTS:
                try:
                    ip = await download_image(session, att.url, ext)
                    if ip:
                        tmp_files.append(ip)
                        img = fit_image(ip, MAX_IMG_W, MAX_IMG_H)
                        img.hAlign = "LEFT"
                        story.append(img)
                        story.append(Spacer(1, 4))
                    else:
                        story.append(Paragraph(f"[Image failed: {esc(att.filename)}]", msg_s))
                except Exception:
                       story.append(Paragraph(f"[Image error: {esc(att.filename)}]", msg_s))
            else:
                story.append(Paragraph(f"[Attachment: {esc(att.filename)}]", msg_s))

        story.append(Spacer(1, 8))

    async def send_pdf(msgs, part_num=None):
        suffix = f"-part{part_num}" if part_num else ""
        fname = f"{channel.name}{suffix}.pdf"
        label = f"📄 **#{channel.name}**" + (f" part {part_num}" if part_num else "")
        s = []
        header = f"#{esc(channel.name)}" + (f" (Part {part_num})" if part_num else "")
        s.append(Paragraph(header, title_s))
        s.append(Paragraph(f"Server: {esc(guild.name)} | Messages: {len(messages)}", meta_s))
        s.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#5865F2")))
        s.append(Spacer(1, 8))
        for m in msgs:
            ts2 = m.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            av = avatar_cache.get(m.author.id)
            nb = [Paragraph(esc(m.author.display_name), author_s), Paragraph(ts2, ts_s)]
            if av:
                try:
                    ai = Image(av, AVATAR_SIZE, AVATAR_SIZE)
                    ht2 = Table([[ai, nb]], colWidths=[12*mm, None])
                    ht2.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
                    s.append(ht2)
                except Exception:
                    s.append(Paragraph(esc(m.author.display_name), author_s))
                    s.append(Paragraph(ts2, ts_s))
            else:
                s.append(Paragraph(esc(m.author.display_name), author_s))
                s.append(Paragraph(ts2, ts_s))
            c2 = resolve_mentions(m.content or "", m)
            if c2:
                for line in c2.split("\n"):
                    if line.strip(): s.append(Paragraph(esc(line), msg_s))
                    else: s.append(Spacer(1, 4))
            for att in m.attachments:
                ext2 = os.path.splitext(att.filename)[1].lower()
                if ext2 in IMAGE_EXTS:
                    try:
                        ip2 = await download_image(session, att.url, ext2)
                        if ip2:
                            tmp_files.append(ip2)
                            s.append(fit_image(ip2, MAX_IMG_W, MAX_IMG_H))
                            s.append(Spacer(1, 4))
                        else: s.append(Paragraph(f"[Image failed: {esc(att.filename)}]", msg_s))
                    except Exception: s.append(Paragraph(f"[Image error: {esc(att.filename)}]", msg_s))
                else: s.append(Paragraph(f"[Attachment: {esc(att.filename)}]", msg_s))
            s.append(Spacer(1, 8))
        outpath = f"/tmp/{channel.name}{suffix}.pdf"
        build_pdf_to_file(s, outpath)
        tmp_files.append(outpath)
        await dest.send(content=label, file=discord.File(outpath, filename=fname))

    try:
        await send_pdf(messages)
    except discord.HTTPException as e:
        if e.code == 40005:
            if progress_ch: await progress_ch.send(f"  ⚠️ **#{channel.name}** too large, splitting into 2 parts...")
            mid = len(messages) // 2
            await send_pdf(messages[:mid], 1)
            await send_pdf(messages[mid:], 2)
        else:
            if progress_ch: await progress_ch.send(f"  ❌ Failed **#{channel.name}**: {e}")
    except Exception as e:
        if progress_ch: await progress_ch.send(f"  ❌ Failed **#{channel.name}**: {e}")


@bot.tree.command(name="archive", description="Export all messages in a channel to a PDF")
@app_commands.describe(channel="The channel to archive")
@app_commands.check(lambda i: any(r.name.lower() == "pixie" for r in i.user.roles))
async def archive(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(thinking=True)
    tmp_files = []
    try:
        title_s, meta_s, author_s, ts_s, msg_s = make_styles()
        messages = []
        async for msg in channel.history(limit=None, oldest_first=True):
            messages.append(msg)
        if not messages:
            await interaction.followup.send("No messages found.")
            return
        story = []
        story.append(Paragraph(f"#{esc(channel.name)}", title_s))
        story.append(Paragraph(f"Server: {esc(interaction.guild.name)} | Messages: {len(messages)}", meta_s))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#5865F2")))
        story.append(Spacer(1, 8))
        avatar_cache = {}
        async with aiohttp.ClientSession() as session:
            for msg in messages:
                ts = msg.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                author_id = msg.author.id
                if author_id not in avatar_cache:
                    av_url = msg.author.display_avatar.with_format("png").with_size(64).url
                    av_path = await download_image(session, av_url, ".png")
                    avatar_cache[author_id] = av_path
                av_path = avatar_cache[author_id]
                name_block = [Paragraph(esc(msg.author.display_name), author_s), Paragraph(ts, ts_s)]
                if av_path:
                    try:
                        av_img = Image(av_path, AVATAR_SIZE, AVATAR_SIZE)
                        ht = Table([[av_img, name_block]], colWidths=[12*mm, None])
                        ht.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
                        story.append(ht)
                    except Exception:
                        story.append(Paragraph(esc(msg.author.display_name), author_s))
                        story.append(Paragraph(ts, ts_s))
                else:
                    story.append(Paragraph(esc(msg.author.display_name), author_s))
                    story.append(Paragraph(ts, ts_s))
                content = resolve_mentions(msg.content or "", msg)
                if content:
                    for line in content.split("\n"):
                        if line.strip(): story.append(Paragraph(esc(line), msg_s))
                        else: story.append(Spacer(1, 4))
                for att in msg.attachments:
                    ext = os.path.splitext(att.filename)[1].lower()
                    if ext in IMAGE_EXTS:
                        try:
                            ip = await download_image(session, att.url, ext)
                            if ip:
                                tmp_files.append(ip)
                                img = fit_image(ip, MAX_IMG_W, MAX_IMG_H)
                                img.hAlign = "LEFT"
                                story.append(img)
                                story.append(Spacer(1, 4))
                            else: story.append(Paragraph(f"[Image failed]", msg_s))
                        except Exception: story.append(Paragraph(f"[Image error]", msg_s))
                    else: story.append(Paragraph(f"[Attachment: {esc(att.filename)}]", msg_s))
                story.append(Spacer(1, 8))
        outpath = f"/tmp/{channel.name}-archive.pdf"
        build_pdf_to_file(story, outpath)
        tmp_files.append(outpath)
        await interaction.followup.send(content=f"📄 Archive of **#{channel.name}**", file=discord.File(outpath, filename=f"{channel.name}-archive.pdf"))
    except discord.Forbidden: await interaction.followup.send("No permission.")
    except Exception as e: await interaction.followup.send(f"Error: {e}")
    finally:
        for tmp in tmp_files:
            try: os.unlink(tmp)
            except: pass
        for av in avatar_cache.values():
            if av:
                try: os.unlink(av)
                except: pass



async def mirror_day_announcement(message):
    game_key = get_game_key(message.channel.name)
    if not game_key:
        return
    for ch in message.guild.text_channels:
        if get_game_key(ch.name) != game_key or ch.id == message.channel.id:
            continue
        cat = ch.category
        if cat and "game chat" in cat.name.lower():
            try:
                await ch.send(message.content)
            except Exception as e:
                print(f"Mirror failed -> #{ch.name}: {e}")
    dm=re.search(r"[0-9]+",message.content); d=get_game_state(game_key)
    if dm: d["day"]=int(dm.group())
    d["used"]=0; d["player_counts"]={} ; d["nominees"]=[]; d["nominators"]=[]
    for th in d.get("threads",[]):
        try:
            t=await message.guild.fetch_channel(th["thread_id"])
            await t.edit(locked=True,archived=True)
        except Exception: pass
    set_game_state(game_key,d)

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
            and 'whisper' not in ch_name \
            and DAY_PATTERN.match(message.content or ''):
        await mirror_day_announcement(message)
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
botc_scripts.register(bot)
reminders.register(bot)
bot.run(TOKEN)
