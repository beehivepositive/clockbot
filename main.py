import discord
from typing import Optional
import anthropic
from personality import SYSTEM_PROMPT, PRIMING_HISTORY
from botc_knowledge import BOTC_KNOWLEDGE
from db_search import is_db_query, context_for
FULL_PROMPT = SYSTEM_PROMPT + chr(10)*2 + BOTC_KNOWLEDGE
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
CST = pytz.timezone('America/Chicago')

load_dotenv()
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
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
BOTC_TOOLS = [{'name': 'run_botc_scenario', 'description': 'Run a BotC logic scenario. botc_logic is imported. Use print().', 'input_schema': {'type': 'object', 'properties': {'code': {'type': 'string', 'description': 'Python code'}, 'description': {'type': 'string', 'description': 'What it tests'}}, 'required': ['code', 'description']}}, {'name': 'lookup_character', 'description': 'Look up a BotC character ability text from wiki data', 'input_schema': {'type': 'object', 'properties': {'character_name': {'type': 'string'}}, 'required': ['character_name']}}, {'name': 'get_game_state', 'description': 'Get the current tracked game state for a channel/game', 'input_schema': {'type': 'object', 'properties': {'game_key': {'type': 'string', 'description': 'The game identifier'}}, 'required': ['game_key']}}]

BOTC_SYSTEM_ADDITION = """
== BOTC LOGIC TOOLS ==
You have access to tools to run actual Blood on the Clocktower game logic code and look up character abilities.
Use run_botc_scenario when asked mechanical questions about how abilities work, interact, or what happens in specific situations.
Use lookup_character to get exact ability text.
Use get_game_state to see the current tracked game state for a channel.
Always run scenarios to verify mechanical rulings before answering -- don't guess at mechanics.
"""


def execute_botc_tool(name: str, params: dict, game_key: str = None) -> str:
    if name == "run_botc_scenario":
        return run_botc_code(params.get("code", ""))
    elif name == "lookup_character":
        return get_character_info(params.get("character_name", ""))
    elif name == "get_game_state":
        key = params.get("game_key") or game_key
        g = get_game(key) if key else None
        return format_game_state(g) if g else "No active game found for that key."
    return f"Unknown tool: {name}"


async def chat_with_botc_tools(messages: list, system: str, game_key: str = None) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    all_messages = list(messages)
    full_system = system + "\n\n" + BOTC_SYSTEM_ADDITION
    for _ in range(6):
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1200,
            system=full_system, tools=BOTC_TOOLS, messages=all_messages,
        )
        if resp.stop_reason == "end_turn":
            text = next((b.text for b in resp.content if hasattr(b, "text")), "")
            return text[:2000] or "(no response)"
        if resp.stop_reason == "tool_use":
            all_messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    res = execute_botc_tool(block.name, block.input, game_key)
                    results.append({"type":"tool_result","tool_use_id":block.id,"content":res[:3000]})
            if results:
                all_messages.append({"role": "user", "content": results})
        else:
            break
    return "(Could not generate response)"



@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

@bot.event
async def on_ready():
    global FULL_PROMPT
    guild = discord.Object(id=1339575347032621191)
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")
    try:
        import aiohttp as _ah, io as _io, pypdf as _pp
        rch = discord.utils.get(bot.get_all_channels(), name="resources")
        if rch:
            chunks = []
            async with _ah.ClientSession() as _s:
                async for m in rch.history(limit=None, oldest_first=True):
                    if m.content.strip():
                        chunks.append(m.content.strip())
                    for att in m.attachments:
                        nl = att.filename.lower()
                        try:
                            async with _s.get(att.url) as r:
                                data = await r.read()
                            if nl.endswith(".pdf"):
                                rd = _pp.PdfReader(_io.BytesIO(data))
                                txt = "\n".join(pg.extract_text() or "" for pg in rd.pages).strip()
                                if txt: chunks.append(f"[FILE: {att.filename}]\n{txt}")
                            elif nl.endswith((".txt",".md")):
                                chunks.append(f"[FILE: {att.filename}]\n{data.decode('utf-8','ignore').strip()}")
                        except Exception as fe:
                            print(f"Warn: {att.filename}: {fe}")
            if chunks:
                block = "== SERVER RESOURCES CHANNEL ==\n" + "\n\n".join(chunks)
                FULL_PROMPT = SYSTEM_PROMPT + chr(10)*2 + BOTC_KNOWLEDGE + chr(10)*2 + block
                chat_history.clear()
                print(f"Loaded {len(chunks)} items from #resources")
    except Exception as e:
        print(f"Warning: could not load #resources: {e}")

    # Inject player profiles
    _pp = '/home/discord-bot/player_profiles.json'
    if os.path.exists(_pp):
        try:
            import json as _j
            profs = _j.load(open(_pp))
            pb = "== PLAYER PROFILES ==\n" + "\n\n".join(f"[{n}]\n{t}" for n,t in profs.items())
            FULL_PROMPT = FULL_PROMPT + chr(10)*2 + pb
            print(f"Loaded {len(profs)} player profiles", flush=True)
        except Exception as e:
            print(f"Warning: profiles: {e}")
    if not game_clock.is_running():
        game_clock.start()


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



@bot.tree.command(name="archive-group", description="Archive all channels in a game group into the current channel")
@app_commands.describe(game="The game number or name (e.g. 197 or pridegame)")
@app_commands.check(lambda i: any(r.name.lower() == "pixie" for r in i.user.roles))
async def archive_group(interaction: discord.Interaction, game: str):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    dest = interaction.channel

    # Find all channels belonging to this game group
    all_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
    group_channels = [c for c in all_channels if get_game_key(c.name) == game.strip()]

    if not group_channels:
        await interaction.followup.send(f"No channels found for game **{game}**.")
        return

    to_archive = [c for c in group_channels if not is_excluded(c.name)]

    if not to_archive:
        await interaction.followup.send(f"No archivable channels found for game **{game}** (all are excluded).")
        return

    await interaction.followup.send(f"⏳ Archiving **{len(to_archive)}** channels for **game{game}** into {dest.mention}...")

    tmp_files = []
    avatar_cache = {}
    done = 0
    failed = []

    async with aiohttp.ClientSession() as session:
        for channel in sorted(to_archive, key=lambda c: c.name):
            # Check if already archived in this channel
            already_done = False
            async for m in dest.history(limit=200):
                if any(a.filename == f"{channel.name}.pdf" for a in m.attachments):
                    already_done = True
                    break
            if already_done:
                await dest.send(f"⏭ **#{channel.name}** already archived, skipping.")
                continue

            await dest.send(f"📥 Fetching **#{channel.name}**...")

            try:
                await archive_channel(session, dest, channel, guild, tmp_files, avatar_cache, progress_ch=None)
                done += 1
            except Exception as e:
                failed.append(f"#{channel.name} ({e})")

            # Clean up tmp files after each channel
            for tmp in tmp_files:
                try: os.unlink(tmp)
                except: pass
            tmp_files.clear()

    # Clean up avatar cache
    for av in avatar_cache.values():
        if av:
            try: os.unlink(av)
            except: pass

    summary = f"✅ Archived **{done}/{len(to_archive)}** channels for **game{game}**."
    if failed:
        summary += f"\n❌ Failed: {', '.join(failed[:10])}"
    await dest.send(summary)

@bot.tree.command(name="archive-all", description="Archive all game channel groups to their logs channels")
@app_commands.check(lambda i: any(r.name.lower() == "pixie" for r in i.user.roles))
async def archive_all(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    progress_ch = discord.utils.get(guild.text_channels, name="off-topic")
    all_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
    groups = {}
    for ch in all_channels:
        key = get_game_key(ch.name)
        if key: groups.setdefault(key, []).append(ch)
    total = len(groups)
    done = 0
    skipped = []
    await interaction.followup.send(f"Starting {total} groups.")
    tmp_files=[]
    avatar_cache={}
    async with aiohttp.ClientSession() as session:
        for i,(key,channels) in enumerate(sorted(groups.items()),1):
            dest=find_dest(channels)
            to_archive=[c for c in channels if not is_excluded(c.name)]
            if not dest:
                skipped.append(f"game{key}(no logs)")
                continue
            if not to_archive:
                skipped.append(f"game{key}(nothing)")
                continue
            if progress_ch: await progress_ch.send(f"[{i}/{total}] game{key}...")
            group_ok=True
            try:
                for ch_idx,channel in enumerate(sorted(to_archive,key=lambda c:c.name),1):
                    already_done = False
                    async for m in dest.history(limit=200):
                        if any(a.filename == f"{channel.name}.pdf" for a in m.attachments):
                            already_done = True
                            break
                    if already_done:
                        if progress_ch: await progress_ch.send(f"  ⏭ #{channel.name} already archived, skipping.")
                        continue
                    if progress_ch: await progress_ch.send(f"  [{ch_idx}/{len(to_archive)}] #{channel.name}...")
                    try:
                        await archive_channel(session,dest,channel,guild,tmp_files,avatar_cache,progress_ch)
                    except Exception as e:
                        if progress_ch: await progress_ch.send(f"  X #{channel.name} failed: {e}")
                        group_ok=False
                    for tmp in tmp_files:
                        try: os.unlink(tmp)
                        except: pass
                    tmp_files.clear()
                    await asyncio.sleep(1)
            except Exception as e:
                skipped.append(f"game{key}(err)")
                if progress_ch: await progress_ch.send(f"FAIL game{key}: {e}")
                continue
            done+=1
            ok="OK" if group_ok else "PARTIAL"
            if progress_ch: await progress_ch.send(f"{ok} [{i}/{total}] game{key} done.")
            await asyncio.sleep(2)
    for tmp in tmp_files:
        try: os.unlink(tmp)
        except: pass
    for av in avatar_cache.values():
        if av:
            try: os.unlink(av)
            except: pass
    summary=f"Archived {done}/{total} groups."
    if skipped: summary+="\nSkipped: "+str(len(skipped))+" groups."
    if progress_ch: await progress_ch.send("DONE! "+summary)
    await interaction.followup.send(summary)



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

class WhisperView(discord.ui.View):
    def __init__(self,initiator,targets,game_key,cost,is_st=False):
        super().__init__(timeout=None)
        self.initiator=initiator
        self.targets=targets
        self.game_key=game_key
        self.cost=cost
        self.is_st=is_st
        self.accepted=set()
        self.declined=set()
        self.creating=False
        self.message=None
        self.multi=(len(targets)>=2)

    async def on_timeout(self):
        try:
            await self.message.edit(content="Whisper request expired.", view=None)
        except Exception:
            pass

    def status_text(self):
        lines=[]
        for t in self.targets:
            if t.id in self.accepted: lines.append(f"✅ {t.display_name}")
            elif t.id in self.declined: lines.append(f"❌ {t.display_name}")
            else: lines.append(f"⏳ {t.display_name}")
        return chr(10).join(lines)

    @discord.ui.button(label="Accept",style=discord.ButtonStyle.green)
    async def accept_btn(self,interaction,button):
        tids={t.id for t in self.targets}
        if interaction.user.id not in tids:
            await interaction.response.send_message("Not for you.",ephemeral=True); return
        self.accepted.add(interaction.user.id)
        await interaction.response.defer()
        if self.accepted>=tids and not self.creating:
            self.creating=True
            await self._create_thread(interaction)
        elif self.multi and not self.creating:
            await self.message.edit(content="Whisper request to "+" ".join(t.mention for t in self.targets)+":"+chr(10)+self.status_text())

    @discord.ui.button(label="Decline",style=discord.ButtonStyle.red)
    async def decline_btn(self,interaction,button):
        if interaction.user.id not in {t.id for t in self.targets}:
            await interaction.response.send_message("Not for you.",ephemeral=True); return
        self.declined.add(interaction.user.id)
        await interaction.response.defer()
        await self.message.edit(content="Whisper declined by "+interaction.user.display_name+".",view=None)
        self.stop()

    @discord.ui.button(label="Cancel",style=discord.ButtonStyle.grey)
    async def cancel_btn(self,interaction,button):
        if interaction.user.id!=self.initiator.id:
            await interaction.response.send_message("Only the initiator can cancel.",ephemeral=True); return
        await interaction.response.defer()
        await self.message.edit(content="Whisper cancelled by "+self.initiator.display_name+".",view=None)
        self.stop()

    async def _create_thread(self,interaction):
        ch=self.message.channel
        guild=ch.guild
        gd=get_game_state(self.game_key)
        all_ids=sorted([self.initiator.id]+[t.id for t in self.targets])
        existing=next((t for t in gd["threads"] if t["participants"]==all_ids),None)
        day=gd.get("day",1)
        if existing:
            try:
                thread=await guild.fetch_channel(existing["thread_id"])
                names=", ".join(t.display_name for t in self.targets)
                nn="[Day "+str(day)+"] Whisper: "+self.initiator.display_name+" to "+names
                await thread.edit(archived=False,locked=False,name=nn)
                if not self.is_st:
                    gd["used"]+=self.cost
                    inc=len(self.targets); pc=gd["player_counts"]
                    for t in self.targets: pc[str(t.id)]=pc.get(str(t.id),0)+inc
                    pc[str(self.initiator.id)]=pc.get(str(self.initiator.id),0)+inc
                    set_game_state(self.game_key,gd)
                await self.message.edit(content="Whisper created!",view=None)
                all_p=[self.initiator]+list(self.targets)
                lim=str(gd["limit"])
                pcs=[m.display_name+": "+str(gd["player_counts"].get(str(m.id),0))+"/"+lim for m in all_p]
                await ch.send(chr(10).join(pcs))
                self.stop(); return
            except Exception: pass

        if not self.is_st:
            gd["used"]+=self.cost
            pc=gd["player_counts"]
            inc=len(self.targets)
            for t in self.targets:
                pc[str(t.id)]=pc.get(str(t.id),0)+inc
            pc[str(self.initiator.id)]=pc.get(str(self.initiator.id),0)+inc
        new_set=set(all_ids)
        for prev in gd["threads"]:
            prev_set=set(prev["participants"])
            if prev_set!=new_set and prev_set&new_set:
                try:
                    pt=await guild.fetch_channel(prev["thread_id"])
                    await pt.edit(locked=True)
                except Exception: pass
        names=", ".join(t.display_name for t in self.targets)
        tname="[Day "+str(day)+"] Whisper: "+self.initiator.display_name+" to "+names
        thread=await ch.create_thread(
            name=tname,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=1440,
            invitable=False)
        await thread.add_user(self.initiator)
        for t in self.targets: await thread.add_user(t)
        for m in guild.members:
            if any(r.name.lower() in ("storyteller","ascended") for r in m.roles):
                try: await thread.add_user(m)
                except Exception: pass
        gd["threads"].append({"thread_id":thread.id,"participants":all_ids})
        set_game_state(self.game_key,gd)
        used=gd["used"]; limit=gd["limit"]
        ctr="("+str(used)+"/"+str(limit)+")" if not self.is_st else "(ST whisper)"
        pings=" ".join(t.mention for t in self.targets)
        await self.message.edit(content="Whisper created!",view=None)
        await thread.send("Whisper: "+self.initiator.mention+" with "+pings)
        all_p=[self.initiator]+list(self.targets)
        lim=str(gd["limit"])
        pcs=[m.display_name+": "+str(gd["player_counts"].get(str(m.id),0))+"/"+lim for m in all_p]
        await ch.send(chr(10).join(pcs))
        self.stop()


@bot.tree.command(name="whisper",description="Start a private whisper")
@app_commands.describe(targets="Mention players to whisper")
async def whisper_cmd(interaction:discord.Interaction,targets:str):
    if not is_whisper_channel(interaction):
        await interaction.response.send_message("Whisper channels only.",ephemeral=True); return
    gk=get_game_key(interaction.channel.name)
    if not gk:
        await interaction.response.send_message("Cannot determine game.",ephemeral=True); return
    tgts=[m for m in interaction.guild.members if f"<@{m.id}>" in targets or f"<@!{m.id}>" in targets]
    if not tgts:
        await interaction.response.send_message("Mention at least one player.",ephemeral=True); return
    cost=len(tgts); gd=get_game_state(gk)
    lim=gd["limit"]; pc=gd["player_counts"]; inc=len(tgts)
    over=[]
    all_p=[interaction.user]+tgts
    for p in all_p:
        cur=pc.get(str(p.id),0)
        if cur+inc>lim:
            over.append(p.display_name+": "+str(cur)+"/"+str(lim))
    if over:
        msg="Cannot create whisper. The following players are over limit:"+chr(10)+chr(10).join(over)
        await interaction.response.send_message(msg,ephemeral=True); return
    view=WhisperView(interaction.user,tgts,gk,cost)
    pings=" ".join(t.mention for t in tgts)
    await interaction.response.send_message(f"{interaction.user.mention} wants to whisper with {pings}. Accept?",view=view)
    view.message=await interaction.original_response()

@bot.tree.command(name="st-whisper",description="ST whisper")
@app_commands.describe(targets="Players")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def st_whisper_cmd(i2:discord.Interaction,targets:str):
    if not is_whisper_channel(i2): await i2.response.send_message("Whisper only.",ephemeral=True); return
    gk=get_game_key(i2.channel.name)
    t2=[m for m in i2.guild.members if f"<@{m.id}>" in targets]
    if not t2: await i2.response.send_message("No players.",ephemeral=True); return
    v=WhisperView(i2.user,t2,gk,0,True)
    p=" ".join(t.mention for t in t2)
    await i2.response.send_message(f"[ST] Whisper to {p}. Accept?",view=v)
    v.message=await i2.original_response()

@bot.tree.command(name="set-whisper-limit",description="Set whisper limit")
@app_commands.describe(limit="Max whisper points")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def set_whisper_limit(i3:discord.Interaction,limit:int):
    gk=get_game_key(i3.channel.name)
    if not gk: await i3.response.send_message("Cannot determine game.",ephemeral=True); return
    d=get_game_state(gk); d["limit"]=limit; set_game_state(gk,d)
    await i3.response.send_message(f"Limit set to {limit}.",ephemeral=True)

@bot.tree.command(name="reset-whispers",description="Reset whisper counter")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def reset_whispers(i4:discord.Interaction):
    gk=get_game_key(i4.channel.name)
    if not gk: await i4.response.send_message("Cannot determine game.",ephemeral=True); return
    d=get_game_state(gk); d["used"]=0; set_game_state(gk,d)
    lim=d["limit"]
    await i4.response.send_message(f"Counter reset (0/{lim}).",ephemeral=True)



@bot.tree.command(name="delete-whisper-threads",description="Delete all threads in this whisper channel")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def delete_whisper_threads(i5:discord.Interaction):
    if not is_whisper_channel(i5):
        await i5.response.send_message("Whisper channels only.",ephemeral=True); return
    await i5.response.defer(ephemeral=True)
    ch=i5.channel; deleted=0
    for thread in ch.threads:
        try: await thread.delete(); deleted+=1
        except Exception: pass
    async for thread in ch.archived_threads(private=True,limit=100):
        try: await thread.delete(); deleted+=1
        except Exception: pass
    gk=get_game_key(ch.name)
    if gk:
        d=get_game_state(gk); d["threads"]=[]; set_game_state(gk,d)
    await i5.followup.send("Deleted "+str(deleted)+" thread(s).",ephemeral=True)

@bot.tree.command(name="setneighborwhispers",description="Create neighbor whispers for an ordered list")
@app_commands.describe(targets="Ordered list of mentions e.g. @Alice @Bob @Charlie")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def set_neighbor_whispers(interaction:discord.Interaction,targets:str):
    if not is_whisper_channel(interaction):
        await interaction.response.send_message("Whisper channels only.",ephemeral=True); return
    gk=get_game_key(interaction.channel.name)
    if not gk:
        await interaction.response.send_message("Cannot determine game.",ephemeral=True); return
    players=[]
    for tok in re.finditer('<@!?(\\d+)>|\\S+',targets):
        mid=re.match('<@!?(\\d+)>',tok.group())
        if mid:
            mb=interaction.guild.get_member(int(mid.group(1)))
            players.append((mb,mb.display_name if mb else "Unknown"))
        else:
            players.append((None,tok.group()))
    if len(players)<2:
        await interaction.response.send_message("Need at least 2 players.",ephemeral=True); return
    await interaction.response.defer()
    ch=interaction.channel; guild=interaction.guild
    sts=[mb for mb in guild.members if any(r.name.lower()in("storyteller","ascended")for r in mb.roles)]
    created=[]
    for i in range(len(players)):
        m1,n1=players[i]; m2,n2=players[(i+1)%len(players)]
        tname="🏘️ "+n1+" & "+n2
        mentionables=[mb for mb in[m1,m2]if mb is not None]
        try:
            thread=await ch.create_thread(name=tname,type=discord.ChannelType.private_thread,invitable=False)
            for mb in mentionables:
                try: await thread.add_user(mb)
                except Exception: pass
            for st in sts:
                try: await thread.add_user(st)
                except Exception: pass
            created.append(tname)
        except Exception as e:
            created.append("Failed: "+n1+" & "+n2)
    summary="Neighbor whispers created:"+chr(10)+chr(10).join(created)
    await interaction.followup.send(summary)


async def _post_vote_message(channel, game_key, vote_type, subject, extra=""):
    """Post a public reaction vote message and record it in game state."""
    if vote_type == "nomination":
        text = f"⚖️ **{subject}** has been nominated by **{extra}**\nReact ⬆️ to vote for execution."
    elif vote_type == "exile":
        text = f"🚪 Exile vote for **{subject}**\nReact ⬆️ to exile."
    else:
        text = f"🕯️ **{subject}** is calling for a cult vote!\nReact ⬆️ to join their cult."
    msg = await channel.send(text)
    await msg.add_reaction("⬆️")
    gd = get_game_state(game_key)
    gd["active_vote"] = {
        "type": vote_type,
        "message_id": msg.id,
        "channel_id": channel.id,
        "subject": subject,
        "extra": extra,
    }
    set_game_state(game_key, gd)
    return msg

# ── Chat handler ──────────────────────────────────────────────────────────
async def _check_mez_word(message):
    """Fire when a player says their Mezepheles word in public chat.
    Requires: target is Good, Mez alive+sober, no prior conversion.
    """
    from botc_runner import get_game,set_game,load_games
    import botc_logic as _BL
    words=set(message.content.lower().split())
    for gk,_g in list(load_games().items()):
        if not _g.get("active"): continue
        mez=_BL.get_character(_g,"Mezepheles")
        if not mez or not mez["alive"]: continue
        if _BL.is_drunk_or_poisoned(mez,_g): continue
        if mez["tokens"].get("mez_converted"): continue
        for _p in _g.get("players",[]):
            mw=_p.get("tokens",{}).get("mez_word","")
            if not mw or mw.lower() not in words: continue
            if _p.get("alignment")!=_BL.GOOD: continue
            _BL.resolve_mezepheles_word_said(_p["id"],_g)
            set_game(gk,_g)
            await message.add_reaction("🌑")
            return

async def _check_yagg_phrase(message):
    from botc_runner import get_game,set_game,load_games
    import botc_logic as _BL
    text=message.content.lower()
    for gk,g in list(load_games().items()):
        if not g.get("active"): continue
        yagg=_BL.get_character(g,"Yaggababble")
        if not yagg or not yagg["alive"]: continue
        phrase=g.get("_yaggababble_phrase","").lower()
        if not phrase: continue
        c=text.count(phrase)
        if c: g["_yaggababble_day_count"]=g.get("_yaggababble_day_count",0)+c; set_game(gk,g)

async def _handle_juggle(message):
    """Parse juggle claims from day chat and store results.
    Format: juggle PlayerA:CharA, PlayerB:CharB
    """
    import re as _re, botc_logic as _BL
    from botc_runner import get_game,set_game
    gk=get_game_key(message.channel.name)
    if not gk: return
    _g=get_game(gk)
    if not _g or _g.get("phase")!="day": return
    jug_p=_BL.get_character(_g,"Juggler")
    if not jug_p or not jug_p["alive"]: return
    sid=str(message.author.id)
    cn=load_common_names()
    def _match(did,dname):
        if jug_p["id"]==str(did): return True
        for k,v in cn.items():
            if int(v)==did and k==jug_p.get("name","").lower(): return True
        return jug_p.get("name","").lower()==dname.lower()
    if not _match(message.author.id,message.author.display_name): return
    body=JUGGLE_TRIGGER.match(message.content.strip()).group(1).strip()
    pairs={}
    import re as _re2
    for part in _re2.split(r"[,;]+",body):
        part=part.strip()
        if ":" in part:
            pname,cname=part.split(":",1)
            pname=pname.strip(); cname=cname.strip()
            for _p in _g.get("players",[]):
                if _p.get("name","").lower()==pname.lower():
                    pairs[_p["id"]]=cname; break
    if not pairs: return
    _BL.resolve_juggler_day(jug_p,pairs,_g)
    set_game(gk,_g)
    count=len(pairs)
    await message.add_reaction("⚖️")

async def handle_nomination(message):
    gk = get_game_key(message.channel.name)
    if not gk: return
    gd = get_game_state(gk)
    if not gd.get("nominations_enabled"): return
    tf_role = discord.utils.get(message.guild.roles, name="Townsfolk")
    def is_townsfolk(member):
        return tf_role is not None and tf_role in member.roles
    if not is_townsfolk(message.author):
        await message.channel.send(f"{message.author.mention}, only Townsfolk players can nominate.", delete_after=15)
        return
    content = message.content
    for u in message.mentions:
        content = content.replace(f"<@{u.id}>","").replace(f"<@!{u.id}>","")
    for r in message.role_mentions:
        content = content.replace(f"<@&{r.id}>","")
    content = content.strip()
    m = NOM_TRIGGER.match(content)
    if not m: return
    target_text = m.group(2).strip()
    nominator = message.author
    nominator_id = str(nominator.id)
    if nominator_id in gd.get("dead_players",[]):
        # Allow Riot-killed players to make their forced nomination
        _riot_g = get_game(gk)
        if not (_riot_g and _riot_g.get("_riot_must_nominate") == nominator_id):
            await message.channel.send(f"{nominator.mention}, dead players cannot nominate.", delete_after=15)
            return
    if nominator_id in gd.get("nominators",[]):
        await message.channel.send(f"{nominator.mention}, you have already nominated today.", delete_after=15)
        return
    nominee = None
    for u in message.mentions:
        if u.id != bot.user.id:
            nominee = message.guild.get_member(u.id)
            break
    if not nominee and target_text:
        cn = load_common_names()
        tl = target_text.lower()
        if tl in cn:
            nominee = message.guild.get_member(int(cn[tl]))
        if not nominee:
            for mb in message.guild.members:
                if mb.display_name.lower()==tl or mb.name.lower()==tl:
                    nominee = mb; break
    if not nominee:
        await message.channel.send(f"Could not find player. Try mentioning them directly.", delete_after=15)
        return
    if not is_townsfolk(nominee):
        await message.channel.send(f"{nominee.mention} is not a Townsfolk player and cannot be nominated.", delete_after=15)
        return
    nominee_id = str(nominee.id)
    if nominee_id in gd.get("nominees",[]):
        await message.channel.send(f"{nominee.mention} has already been nominated today.", delete_after=15)
        return
    gd["nominees"].append(nominee_id); gd["nominators"].append(nominator_id)
    set_game_state(gk, gd)
    from botc_runner import get_game, set_game
    import botc_logic as _BL
    _g=get_game(gk); _nom_pid=_nee_pid=None
    if _g:
        def _fp(did,dname):
            sid=str(did)
            for _p in _g.get("players",[]):
                if _p["id"]==sid or _p.get("discord_id")==sid: return _p
            dl=dname.lower()
            for _p in _g.get("players",[]):
                if _p.get("name","").lower()==dl: return _p
            _cn=load_common_names()
            for _cnk,_cnv in _cn.items():
                if str(_cnv)==sid:
                    for _p in _g.get("players",[]):
                        if _p.get("name","").lower()==_cnk.lower(): return _p
        _nm=_fp(nominator.id,nominator.display_name)
        _ne=_fp(nominee.id,nominee.display_name)
        if _nm and _ne:
            _nom_pid=_nm["id"]; _nee_pid=_ne["id"]
            _BL.resolve_nomination(_nom_pid,_nee_pid,[],_g)
            # Clear riot_must_nominate now that the forced nomination has been made
            if _g.get("_riot_must_nominate") == _nom_pid:
                _g.pop("_riot_must_nominate", None)
                _nm.get("tokens",{}).pop("riot_must_nominate", None)
            set_game(gk,_g)
            if not _nm["alive"]:
                if _ne and _ne.get("character")=="Virgin":
                    await message.channel.send(f"🗡️ **{nominator.display_name}** was executed by the **Virgin**!")
                else:
                    await message.channel.send(f"🪄 **{nominator.display_name}** was struck down by the **Witch's** curse!")
    # Riot: nominated player dies immediately (not an execution)
    if _g and _nom_pid and _nee_pid and _BL.is_riot_active(_g):
        _ne2=_BL.get_player(_g,_nee_pid)
        if _ne2 and _ne2["alive"]:
            _BL.resolve_riot_kill(_nee_pid,_g)
            _win=_BL.check_win_conditions(_g)
            set_game(gk,_g)
            await message.channel.send(f"💀 **{nominee.display_name}** killed by Riot! Must nominate.")
            if _win: await message.channel.send(f"{_win} wins!")
            _did=_ne2.get("discord_id") or _ne2.get("id")
            try:
                _u=await bot.fetch_user(int(_did))
                _dm=await _u.create_dm()
                await _dm.send("Riot killed you. Nominate in game channel within 30s.")
            except Exception: pass
            asyncio.create_task(_riot_nominate_timeout(gk,_nee_pid,message.channel,30))
            return
    await _post_vote_message(message.channel,gk,"nomination",
                             nominee.display_name,nominator.display_name)
    if _nom_pid and _nee_pid:
        _gd2=get_game_state(gk)
        if _gd2.get("nomination_votes"):
            _gd2["nomination_votes"][-1]["nom_id"]=_nom_pid
            _gd2["nomination_votes"][-1]["nee_id"]=_nee_pid
            set_game_state(gk,_gd2)

@bot.tree.command(name="enable-nominations",description="Enable nominations for this game")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
async def enable_nominations(i:discord.Interaction):
    if not is_game_category_channel(i.channel):
        await i.response.send_message("This command only works in game channels.",ephemeral=True); return
    gk=get_game_key(i.channel.name)
    if not gk:
        await i.response.send_message("Cannot determine game.",ephemeral=True); return
    d=get_game_state(gk); d["nominations_enabled"]=True; set_game_state(gk,d)
    await i.response.send_message("Nominations enabled for this game.",ephemeral=True)

@bot.tree.command(name="disable-nominations",description="Disable nominations for this game")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
async def disable_nominations(i:discord.Interaction):
    if not is_game_category_channel(i.channel):
        await i.response.send_message("This command only works in game channels.",ephemeral=True); return
    gk=get_game_key(i.channel.name)
    if not gk:
        await i.response.send_message("Cannot determine game.",ephemeral=True); return
    d=get_game_state(gk); d["nominations_enabled"]=False; set_game_state(gk,d)
    await i.response.send_message("Nominations disabled for this game.",ephemeral=True)

@bot.tree.command(name="set-dead",description="Mark a player as dead")
@app_commands.describe(player="Player")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
async def set_dead(i:discord.Interaction,player:discord.Member):
    if not is_game_category_channel(i.channel):
        await i.response.send_message("Game channels only.",ephemeral=True); return
    gk=get_game_key(i.channel.name)
    if not gk: await i.response.send_message("No game.",ephemeral=True); return
    d=get_game_state(gk); pid=str(player.id)
    if pid not in d["dead_players"]: d["dead_players"].append(pid)
    set_game_state(gk,d)
    await i.response.send_message(f"{player.display_name} marked as dead.",ephemeral=True)

@bot.tree.command(name="set-alive",description="Restore a player to alive")
@app_commands.describe(player="Player")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
async def set_alive(i:discord.Interaction,player:discord.Member):
    if not is_game_category_channel(i.channel):
        await i.response.send_message("Game channels only.",ephemeral=True); return
    gk=get_game_key(i.channel.name)
    if not gk: await i.response.send_message("No game.",ephemeral=True); return
    d=get_game_state(gk); pid=str(player.id)
    if pid in d["dead_players"]: d["dead_players"].remove(pid)
    set_game_state(gk,d)
    await i.response.send_message(f"{player.display_name} marked as alive.",ephemeral=True)

@bot.tree.command(name="add-common-name",description="Map a common name to a player")
@app_commands.describe(common_name="Common name",player="The player")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
async def add_common_name(i:discord.Interaction,common_name:str,player:discord.Member):
    cn=load_common_names(); cn[common_name.lower()]=player.id; save_common_names(cn)
    await i.response.send_message(f"{common_name} -> {player.display_name} saved.",ephemeral=True)

@bot.tree.command(name="remove-common-name",description="Remove a common name alias")
@app_commands.describe(common_name="Common name to remove")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
async def remove_common_name(i:discord.Interaction,common_name:str):
    cn=load_common_names(); key=common_name.lower()
    if key in cn:
        del cn[key]; save_common_names(cn)
        await i.response.send_message(f"{common_name} removed.",ephemeral=True)
    else: await i.response.send_message(f"{common_name} not found.",ephemeral=True)

chat_history = {}  # channel_id -> list of {role, content}
MAX_HISTORY = 20

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
    if (ch_name.endswith('-logs') or ch_name.endswith('-log'))             and 'whisper' not in ch_name             and DAY_PATTERN.match(message.content or ''):
        await mirror_day_announcement(message)
        return
    cat = getattr(message.channel,"category",None)
    cat_name = cat.name.lower() if cat else ""
    if "game chat" in cat_name or "game logs" in cat_name:
        is_bot = bot.user in message.mentions
        st_role = discord.utils.get(message.guild.roles,name="Storyteller") or discord.utils.get(message.guild.roles,name="storyteller")
        is_st_role = st_role is not None and st_role in message.role_mentions
        if is_bot or is_st_role:
            stripped = message.content
            for u in message.mentions:
                stripped = stripped.replace(f"<@{u.id}>","").replace(f"<@!{u.id}>","")
            for r in message.role_mentions:
                stripped = stripped.replace(f"<@&{r.id}>","")
            clean = stripped.strip()
            if NOM_TRIGGER.match(clean):
                await handle_nomination(message)
                return
            # Juggler: "juggle PlayerA:CharA, PlayerB:CharB"
            _jm=JUGGLE_TRIGGER.match(message.content.strip())
            if _jm and not is_bot and not is_st_role:
                await _handle_juggle(message)
                return
            # Yaggababble phrase tracking
            await _check_yagg_phrase(message)
            # Mezepheles word detection (any player)
            await _check_mez_word(message)
            if is_bot and clean and ANTHROPIC_KEY:
                gk = get_game_key(message.channel.name)
                ch_id = message.channel.id
                if ch_id not in chat_history:
                    chat_history[ch_id] = list(PRIMING_HISTORY)
                history = chat_history[ch_id]
                game_ctx = ""
                if gk:
                    g = get_game(gk)
                    if g:
                        game_ctx = f"\n\n== CURRENT GAME STATE ({gk}) ==\n{format_game_state(g)}"
                history.append({"role": "user", "content": f"{message.author.display_name}: {clean or 'hey'}"})
                if len(history) > MAX_HISTORY:
                    chat_history[ch_id] = history[-MAX_HISTORY:]
                async with message.channel.typing():
                    try:
                        reply_text = await chat_with_botc_tools(
                            chat_history[ch_id], FULL_PROMPT + game_ctx, game_key=gk)
                    except Exception as e:
                        reply_text = f"broke: {e}"
                chat_history[ch_id].append({"role": "assistant", "content": reply_text})
                if len(reply_text) > 2000:
                    reply_text = reply_text[:1997] + "..."
                await message.reply(reply_text, mention_author=False)
        return
    is_mentioned = bot.user in message.mentions
    is_reply = (message.reference is not None
        and getattr(message.reference.resolved, "author", None) == bot.user)
    if not (is_mentioned or is_reply):
        return
    if ch_name == "general":
        return

    if not ANTHROPIC_KEY:
        await message.reply("Set ANTHROPIC_API_KEY in .env to enable chat.", mention_author=False)
        return
    content = message.content
    for u in message.mentions:
        content = content.replace(f"<@{u.id}>", "").replace(f"<@!{u.id}>", "")
    content = content.strip() or "hey"
    ch_id = message.channel.id
    if ch_id not in chat_history:
        chat_history[ch_id] = list(PRIMING_HISTORY)
    history = chat_history[ch_id]
    history.append({"role": "user", "content": f"{message.author.display_name}: {content}"})
    if len(history) > MAX_HISTORY:
        chat_history[ch_id] = history[-MAX_HISTORY:]
    db_ctx=context_for(content) if is_db_query(content) else ""
    sys_prompt=FULL_PROMPT+(chr(10)*2+db_ctx if db_ctx else "")
    BOTC_KEYWORDS = {"monk","imp","demon","townsfolk","outsider","minion","poisoner","empath",
                     "fortune teller","scarlet woman","ability","protect","night","kill","drunk","poison",
                     "vortox","assassin","exorcist","undertaker","washerwoman","librarian","chef",
                     "clocktower","botc","blood on"}
    content_lower = content.lower()
    use_tools = any(kw in content_lower for kw in BOTC_KEYWORDS)
    async with message.channel.typing():
        try:
            if use_tools:
                reply_text = await chat_with_botc_tools(chat_history[ch_id], sys_prompt)
            else:
                client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
                resp = client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=400,
                    system=sys_prompt,
                    messages=chat_history[ch_id],
                )
                reply_text = resp.content[0].text
        except Exception as e:
            reply_text = f"broke: {e}"

    chat_history[ch_id].append({"role": "assistant", "content": reply_text})
    if len(reply_text) > 2000:
        reply_text = reply_text[:1997] + "..."
    await message.reply(reply_text, mention_author=False)





from botc_runner import load_games

@tasks.loop(minutes=1)
async def game_clock():
    try:
        now = datetime.datetime.now(CST)
        for gk,g in list(load_games().items()):
            if not g.get("active"): continue
            if g.get("phase")=="day":
                _det=g.get('day_end_time',{'hour':13,'minute':0})
                t=now.replace(hour=_det['hour'],minute=_det['minute'],second=0,microsecond=0)
                in_window=abs((now-t).total_seconds())<=90
                if in_window and not g.get('day_ended_today'):
                    g['day_ended_today']=True; set_game(gk,g)
                    asyncio.create_task(end_day(gk,bot))
            elif g.get("phase")=="night":
                ns=g.get("night_start_time")
                if ns:
                    s=datetime.datetime.fromisoformat(ns)
                    if s.tzinfo is None: s=s.replace(tzinfo=pytz.utc)
                    if (now.astimezone(pytz.utc)-s).total_seconds()>=3600:
                        asyncio.create_task(end_night(gk,bot))
    except Exception as e: print(f"game_clock err: {e}")

@bot.tree.command(name="botc-grim",description="Show grimoire")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def botc_grim(ii:discord.Interaction):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    g=get_game(gk)
    if not g: await ii.response.send_message("No grimoire.",ephemeral=True);return
    t=format_game_state(g)[:1900]
    await ii.response.send_message(f"```\n{t}\n```",ephemeral=True)

@bot.tree.command(name="botc-load-grim",description="Load grimoire JSON or upload a file")
@app_commands.describe(json_data="JSON string",json_file="Upload a .json or .txt file")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def botc_load_grim(ii:discord.Interaction,json_data:Optional[str]=None,json_file:Optional[discord.Attachment]=None):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    if json_file is not None:
        try:
            d=await json_file.read();raw=json.loads(d.decode("utf-8"))
        except Exception as e: await ii.response.send_message(f"file err:{e}",ephemeral=True);return
    elif json_data:
        try: raw=json.loads(json_data)
        except Exception as e: await ii.response.send_message(f"err:{e}",ephemeral=True);return
    else:
        await ii.response.send_message("Provide json_data or upload a json_file.",ephemeral=True);return
    try:
        from botc_runner import parse_grim_json
        players=raw.get("players",[])
        is_ctlive=players and "role" in players[0] and "character" not in players[0]
        if is_ctlive:
            g=parse_grim_json(raw)
        else:
            g=raw
            g.setdefault("active",True);g.setdefault("phase","day")
            g.setdefault("night",0);g.setdefault("day_num",1)
            from botc_logic import setup_boffin,setup_vi_drunk,setup_lycan_faux_paw,setup_hermit
            setup_boffin(g);setup_vi_drunk(g);setup_lycan_faux_paw(g)
            _herm=next((p for p in g.get("players",[]) if p["character"]=="Hermit"),None)
            if _herm: setup_hermit(_herm,g)
            from botc_jinxes import build_active_jinxes
            build_active_jinxes(g)
        from botc_jinxes import build_active_jinxes
        from botc_logic import resolve_xaan_setup
        build_active_jinxes(g)
        resolve_xaan_setup(g)
        set_game(gk,g)
        n=len(g.get("players",[]))
        await ii.response.send_message(f"Loaded {gk}: {n} players",ephemeral=True)
    except Exception as e: await ii.response.send_message(f"load err: {e}",ephemeral=True)

@bot.tree.command(name="botc-grim-image",description="Show grimoire as image")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def botc_grim_image(ii:discord.Interaction):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    g=get_game(gk)
    if not g: await ii.response.send_message("No grimoire.",ephemeral=True);return
    await ii.response.defer()
    try:
        from botc_render import render_grimoire,build_grimoire_reminders
        build_grimoire_reminders(g)
        out='/tmp/grim_{}.png'.format(gk)
        render_grimoire(g,out)
        await ii.followup.send(file=discord.File(out,'grimoire.png'))
    except Exception as e:
        import traceback
        await ii.followup.send(f"render err: {e}\n```{traceback.format_exc()[-800:]}```",ephemeral=True)

@bot.tree.command(name="botc-set-day-end",description="ST: set day end time (CST 24h)")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
@app_commands.describe(hour="Hour 0-23 CST (default 13 = 1 PM)",minute="Minute 0-59")
async def botc_set_day_end(ii:discord.Interaction,hour:int=13,minute:int=0):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    from botc_runner import get_game,set_game
    g=get_game(gk)
    if not g: await ii.response.send_message("No grimoire.",ephemeral=True);return
    hour=max(0,min(23,hour)); minute=max(0,min(59,minute))
    g['day_end_time']={'hour':hour,'minute':minute}
    set_game(gk,g)
    await ii.response.send_message(f"Day ends at {hour:02d}:{minute:02d} CST.",ephemeral=True)

@bot.tree.command(name="botc-start-night",description="ST: begin night now")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def botc_sn(ii:discord.Interaction):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    await ii.response.send_message("Starting night...",ephemeral=True)
    await end_day(gk,bot)

@bot.tree.command(name="botc-end-night",description="ST: process night actions")
@app_commands.check(lambda i:any(r.name.lower()in("storyteller","pixie")for r in i.user.roles))
async def botc_en(ii:discord.Interaction):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    await ii.response.send_message("Processing night...",ephemeral=True)
    await end_night(gk,bot)



@bot.tree.command(name="botc-cult-vote",description="ST: initiate a cult vote for a player")
@app_commands.check(lambda i:any(r.name.lower() in ("storyteller","pixie") for r in i.user.roles))
@app_commands.describe(player="Name of the player calling for the cult vote")
async def botc_cult_vote(ii:discord.Interaction,player:str):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    gd=get_game_state(gk)
    if gd.get("active_vote"): await ii.response.send_message("A vote is already in progress.",ephemeral=True);return
    from botc_runner import get_game,find_player_by_text
    g=get_game(gk)
    caller_game_id=None
    if g:
        caller=find_player_by_text(player,g)
        if caller: caller_game_id=caller["id"]
    await ii.response.defer(ephemeral=True)
    msg=await _post_vote_message(ii.channel,gk,"cult",player)
    if caller_game_id:
        gd2=get_game_state(gk)
        if gd2.get("active_vote"): gd2["active_vote"]["caller_game_id"]=caller_game_id
        set_game_state(gk,gd2)
    await ii.followup.send(f"Cult vote started for {player}.",ephemeral=True)


async def _resolve_vote(game_key, guild):
    """Fetch reactions on the active vote message and return a result dict.
    Does NOT modify game state — callers decide what to do with the result."""
    gd = get_game_state(game_key)
    vote = gd.get("active_vote")
    if not vote:
        return None
    ch = guild.get_channel(vote["channel_id"])
    if not ch:
        return None
    try:
        msg = await ch.fetch_message(vote["message_id"])
    except Exception:
        return None
    voter_names = []
    voter_ids = []
    for reaction in msg.reactions:
        if str(reaction.emoji) == "⬆️":
            async for user in reaction.users():
                if not user.bot:
                    voter_names.append(user.display_name)
                    voter_ids.append(user.id)
            break
    result = {
        "type": vote["type"],
        "subject": vote["subject"],
        "extra": vote.get("extra", ""),
        "caller_game_id": vote.get("caller_game_id"),
        "voter_names": voter_names,
        "voter_ids": voter_ids,
        "message_id": vote["message_id"],
        "channel_id": vote["channel_id"],
    }
    # For cult votes: annotate with good-player match info
    if vote["type"] == "cult":
        from botc_runner import get_game
        import botc_logic as BL
        g = get_game(game_key)
        if g:
            good_names = [p["name"] for p in g["players"]
                          if p["alive"] and p.get("alignment") == BL.GOOD]
            result["good_player_names"] = good_names
            all_good_joined = all(
                any(gn.lower() in vn.lower() or vn.lower() in gn.lower()
                    for vn in voter_names)
                for gn in good_names
            )
            result["all_good_joined"] = all_good_joined
            caller_game_id = vote.get("caller_game_id")
            if caller_game_id and all_good_joined:
                win = BL.resolve_cult_vote(caller_game_id, g)
                result["win"] = win
    return result

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) != "⬆️" or payload.user_id == bot.user.id:
        return
    ch = bot.get_channel(payload.channel_id)
    if not ch or not hasattr(ch, "name"):
        return
    gk = get_game_key(ch.name)
    if not gk:
        return
    gd = get_game_state(gk)
    vote = gd.get("active_vote")
    if not vote or vote["message_id"] != payload.message_id:
        return
    _tracked=False
    for _nv in gd.get("nomination_votes",[]):
        if _nv.get("message_id")==payload.message_id:
            _nv.setdefault("voter_ids",[])
            if payload.user_id not in _nv["voter_ids"]:
                _nv["voter_ids"].append(payload.user_id)
            _tracked=True; break
    if not _tracked:
        vote=gd.get("active_vote")
        if vote and vote.get("message_id")==payload.message_id:
            vote.setdefault("voter_ids",[])
            if payload.user_id not in vote["voter_ids"]:
                vote["voter_ids"].append(payload.user_id)
    set_game_state(gk, gd)

@bot.event
async def on_raw_reaction_remove(payload):
    if str(payload.emoji) != "⬆️":
        return
    ch = bot.get_channel(payload.channel_id)
    if not ch or not hasattr(ch, "name"):
        return
    gk = get_game_key(ch.name)
    if not gk:
        return
    gd = get_game_state(gk)
    vote = gd.get("active_vote")
    if not vote or vote["message_id"] != payload.message_id:
        return
    _tracked=False
    for _nv in gd.get('nomination_votes',[]):
        if _nv.get('message_id')==payload.message_id:
            vids=_nv.setdefault('voter_ids',[])
            if payload.user_id in vids: vids.remove(payload.user_id)
            _tracked=True; break
    if not _tracked:
        vote=gd.get('active_vote')
        if vote and vote.get('message_id')==payload.message_id:
            vids=vote.get('voter_ids',[])
            if payload.user_id in vids: vids.remove(payload.user_id)
    set_game_state(gk, gd)

async def _riot_nominate_timeout(gk,dead_pid,channel,seconds):
    await asyncio.sleep(seconds)
    import botc_logic as _BL
    from botc_runner import get_game,set_game
    g=get_game(gk)
    if not g: return
    dp=_BL.get_player(g,dead_pid)
    if not dp or not dp["tokens"].get("riot_must_nominate"): return
    if dp["tokens"].get("nominations_today",0)>0: return
    _dn=dp.get("name","?")
    await channel.send(f"Time up! **{_dn}** did not nominate. ST must force via /botc-riot-nominate.")

@bot.tree.command(name="botc-riot-nominate",description="ST: force Riot nomination")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
@app_commands.describe(nominator="Dead Riot player",nominee="Their nominee")
async def botc_riot_nominate(ii:discord.Interaction,nominator:str,nominee:str):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    import botc_logic as _BL; from botc_runner import get_game,set_game
    g=get_game(gk)
    if not g or not _BL.is_riot_active(g): await ii.response.send_message("No Riot.",ephemeral=True);return
    from botc_st import find_player_by_text
    ne=find_player_by_text(nominee,g)
    if not ne: await ii.response.send_message("Could not find nominee.",ephemeral=True);return
    _BL.resolve_riot_kill(ne["id"],g)
    win=_BL.check_win_conditions(g); set_game(gk,g)
    msg=f"💀 {ne.get("name",ne["id"])} killed by Riot."
    if win: msg+=f" {win} wins!"
    await ii.response.send_message(msg)

@bot.tree.command(name="botc-yagg-kill",description="ST: apply Yaggababble kills")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
@app_commands.describe(targets="Comma-separated player names to kill")
async def botc_yagg_kill(ii:discord.Interaction,targets:str):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    import botc_logic as _BL; from botc_runner import get_game,set_game
    g=get_game(gk)
    if not g: await ii.response.send_message("No game state.",ephemeral=True);return
    from botc_st import find_player_by_text
    tids=[]
    for name in targets.split(","):
        p=find_player_by_text(name.strip(),g)
        if p: tids.append(p["id"])
    if not tids: await ii.response.send_message("No valid targets.",ephemeral=True);return
    count_before=g.get("_yaggababble_day_count",0)
    killed=_BL.resolve_yaggababble_kills(tids,g)
    set_game(gk,g)
    names=[", ".join(_BL.get_player(g,t).get("name",t) for t in killed)] if killed else ["none"]
    await ii.response.send_message(f"Yaggababble killed: {names[0]}. Day phrase count was {count_before}.")

@bot.tree.command(name="botc-set-yagg-phrase",description="ST: set Yaggababble phrase")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
@app_commands.describe(phrase="The exact phrase")
async def botc_set_yagg_phrase(ii:discord.Interaction,phrase:str):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    from botc_runner import get_game,set_game; g=get_game(gk)
    if not g: await ii.response.send_message("No state.",ephemeral=True);return
    g["_yaggababble_phrase"]=phrase; g["_yaggababble_day_count"]=0; set_game(gk,g)
    await ii.response.send_message(f"Phrase set.",ephemeral=True)

@bot.tree.command(name="botc-vigormortis-poison",description="ST: apply Vigormortis minion poison")
@app_commands.check(lambda i:any(r.name.lower()=="storyteller" for r in i.user.roles))
@app_commands.describe(minion_name="Minion killed by Vigormortis",direction="left or right")
async def botc_vigormortis_poison(ii:discord.Interaction,minion_name:str,direction:str):
    gk=get_game_key(ii.channel.name)
    if not gk: await ii.response.send_message("No game.",ephemeral=True);return
    import botc_logic as _BL; from botc_runner import get_game,set_game
    g=get_game(gk)
    if not g: await ii.response.send_message("No state.",ephemeral=True);return
    from botc_st import find_player_by_text
    mn=find_player_by_text(minion_name,g)
    if not mn: await ii.response.send_message("Minion not found.",ephemeral=True);return
    d=direction.lower().strip()
    if d not in ("left","right"): await ii.response.send_message("direction must be left or right",ephemeral=True);return
    _BL.apply_vigormortis_poison(mn["id"],d,g); set_game(gk,g)
    await ii.response.send_message(f"Vigormortis: poisoned {d} neighbour of {mn.get("name",mn["id"])}.")

bot.run(TOKEN)
