"""Self-contained channel -> PDF export (reportlab), reusable by the archive flow.

Mirrors the /channeltopdf command's rendering. Kept as its own module so
botc_games can import it without a circular import against main.py.
"""

import os
import re
import tempfile
from datetime import timezone

import aiohttp
import discord
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
                                Image, Table, TableStyle)
from reportlab.lib import colors

MAX_IMG_W = 150 * mm
MAX_IMG_H = 150 * mm
AVATAR_SIZE = 10 * mm
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


async def _download(session, url, suffix=".png"):
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


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _resolve_mentions(content, msg):
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


def _fit_image(path, max_w, max_h):
    from PIL import Image as PILImage
    try:
        with PILImage.open(path) as im:
            w, h = im.size
        scale = min(max_w / w, max_h / h, 1.0)
        return Image(path, w * scale, h * scale)
    except Exception:
        return Image(path, max_w, max_h)


def _styles():
    styles = getSampleStyleSheet()
    return (
        ParagraphStyle("TT", parent=styles["Heading1"], fontSize=18,
                       textColor=colors.HexColor("#5865F2"), spaceAfter=4),
        ParagraphStyle("MT", parent=styles["Normal"], fontSize=9,
                       textColor=colors.grey, spaceAfter=10),
        ParagraphStyle("AT", parent=styles["Normal"], fontSize=10,
                       textColor=colors.HexColor("#5865F2"), fontName="Helvetica-Bold", spaceAfter=0),
        ParagraphStyle("TST", parent=styles["Normal"], fontSize=8,
                       textColor=colors.grey, spaceAfter=2),
        ParagraphStyle("MST", parent=styles["Normal"], fontSize=10, spaceAfter=4, leading=14),
    )


CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:(\d+)>")


async def _prep_emojis(session, content, emoji_cache, tmp_files):
    """Download any custom emojis referenced in `content`; return {id: <img> tag}."""
    imgs = {}
    for eid in set(CUSTOM_EMOJI_RE.findall(content)):
        if eid not in emoji_cache:
            p = await _download(session, f"https://cdn.discordapp.com/emojis/{eid}.png", ".png")
            emoji_cache[eid] = p
            if p:
                tmp_files.append(p)
        if emoji_cache[eid]:
            imgs[eid] = f'<img src="{emoji_cache[eid]}" width="14" height="14" valign="middle"/>'
    return imgs


def _line_markup(line, emoji_imgs):
    """Escape a line's text but inline custom-emoji images where available."""
    out = []
    for part in re.split(r"(<a?:\w+:\d+>)", line):
        m = re.fullmatch(r"<a?:\w+:(\d+)>", part)
        if m and m.group(1) in emoji_imgs:
            out.append(emoji_imgs[m.group(1)])
        else:
            out.append(_esc(part))
    return "".join(out)


async def channel_to_pdf(channel, guild, outpath):
    """Render every message in `channel` to a PDF at `outpath`.
    Returns the message count, or None if the channel had no messages / was unreadable."""
    title_s, meta_s, author_s, ts_s, msg_s = _styles()
    messages = []
    try:
        async for msg in channel.history(limit=None, oldest_first=True):
            messages.append(msg)
    except discord.Forbidden:
        return None
    if not messages:
        return None

    tmp_files = []
    avatar_cache = {}
    emoji_cache = {}
    try:
        story = [
            Paragraph(f"#{_esc(channel.name)}", title_s),
            Paragraph(f"Server: {_esc(guild.name)} | Messages: {len(messages)}", meta_s),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor("#5865F2")),
            Spacer(1, 8),
        ]
        async with aiohttp.ClientSession() as session:
            for msg in messages:
                ts = msg.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                aid = msg.author.id
                if aid not in avatar_cache:
                    av_url = msg.author.display_avatar.with_format("png").with_size(64).url
                    avatar_cache[aid] = await _download(session, av_url, ".png")
                av_path = avatar_cache[aid]
                name_block = [Paragraph(_esc(msg.author.display_name), author_s), Paragraph(ts, ts_s)]
                if av_path:
                    try:
                        ht = Table([[Image(av_path, AVATAR_SIZE, AVATAR_SIZE), name_block]],
                                   colWidths=[12 * mm, None])
                        ht.setStyle(TableStyle([
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                        story.append(ht)
                    except Exception:
                        story.append(Paragraph(_esc(msg.author.display_name), author_s))
                        story.append(Paragraph(ts, ts_s))
                else:
                    story.append(Paragraph(_esc(msg.author.display_name), author_s))
                    story.append(Paragraph(ts, ts_s))
                content = _resolve_mentions(msg.content or "", msg)
                emoji_imgs = await _prep_emojis(session, content, emoji_cache, tmp_files)
                if content:
                    for line in content.split("\n"):
                        if line.strip():
                            story.append(Paragraph(_line_markup(line, emoji_imgs), msg_s))
                        else:
                            story.append(Spacer(1, 4))
                for att in msg.attachments:
                    ext = os.path.splitext(att.filename)[1].lower()
                    if ext in IMAGE_EXTS:
                        try:
                            ip = await _download(session, att.url, ext)
                            if ip:
                                tmp_files.append(ip)
                                img = _fit_image(ip, MAX_IMG_W, MAX_IMG_H)
                                img.hAlign = "LEFT"
                                story.append(img)
                                story.append(Spacer(1, 4))
                            else:
                                story.append(Paragraph("[Image failed]", msg_s))
                        except Exception:
                            story.append(Paragraph("[Image error]", msg_s))
                    else:
                        story.append(Paragraph(f"[Attachment: {_esc(att.filename)}]", msg_s))
                for st in getattr(msg, "stickers", []):
                    fmt = (getattr(getattr(st, "format", None), "name", "") or "").lower()
                    if fmt == "lottie":  # vector animation — can't embed, show name
                        story.append(Paragraph(f"[Sticker: {_esc(st.name)}]", msg_s))
                        continue
                    try:
                        sp = await _download(session, st.url, ".png")
                        if sp:
                            tmp_files.append(sp)
                            img = _fit_image(sp, 40 * mm, 40 * mm)
                            img.hAlign = "LEFT"
                            story.append(img)
                            story.append(Spacer(1, 4))
                        else:
                            story.append(Paragraph(f"[Sticker: {_esc(st.name)}]", msg_s))
                    except Exception:
                        story.append(Paragraph(f"[Sticker: {_esc(st.name)}]", msg_s))
                story.append(Spacer(1, 8))
        doc = SimpleDocTemplate(outpath, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
                                topMargin=20 * mm, bottomMargin=20 * mm)
        doc.build(story)
        return len(messages)
    finally:
        for p in tmp_files:
            try:
                os.unlink(p)
            except Exception:
                pass
        for p in avatar_cache.values():
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass
