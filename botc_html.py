"""HTML transcript converter for channel archiving (replaces the PDF path).

Uses chat_exporter for a Discord-faithful transcript, then makes it a single
self-contained file: every referenced asset is downloaded, downscaled, and
embedded as a data URI (so it survives Discord CDN-link expiry), and a small
CSS override is appended to fix chat_exporter's embed layout (its embeds use a
one-column grid but place the thumbnail in an implicit column 2, which crams
the text sideways).

`channel_to_html(channel, guild, outpath, bot)` mirrors the old
`botc_pdf.channel_to_pdf` signature and returns the message count.
"""

import io
import re
import base64
import asyncio

import aiohttp
import chat_exporter
from PIL import Image

_SRC_RE = re.compile(r'src="(https?://[^"]+)"')
_MSG_RE = re.compile(r'id="chatlog__message-container-\d+"')

# Appended last so it wins the cascade: give the embed a flexible text column and
# a constrained thumbnail column, and force embeds to sit below the message text.
_CSS_FIX = (
    "<style>"
    ".chatlog__embed{grid-template-columns:minmax(0,1fr) auto !important;"
    "max-width:520px !important;}"
    ".chatlog__embed-text{min-width:0 !important;grid-column:1 !important;}"
    ".chatlog__embed-thumbnail,.chatlog__embed-thumbnail img{max-width:80px !important;"
    "max-height:80px !important;}"
    ".chatlog__content{min-width:0 !important;}"
    "</style>"
)


def _target_max(url):
    """Max pixel dimension by asset type — small for avatars/emojis, large for
    attachments and embed images."""
    if any(seg in url for seg in ("/avatars/", "/embed/avatars/", "/icons/", "/guilds/", "/banners/")):
        return 96
    if "/emojis/" in url:
        return 48
    return 1280


def _b64(data, ct):
    return "data:" + ct + ";base64," + base64.b64encode(data).decode()


def _encode_asset(data, url, content_type):
    """Downscale + re-encode an image asset to a data URI. Keeps small animated
    GIFs whole; embeds other non-images raw when small, else returns None so the
    original URL is left in place (e.g. large videos)."""
    try:
        img = Image.open(io.BytesIO(data))
        if getattr(img, "is_animated", False):
            if len(data) <= 1_500_000:
                return _b64(data, content_type)  # keep the animation
            img.seek(0)                          # too big — fall back to first frame
        mx = _target_max(url)
        if max(img.size) > mx:
            img.thumbnail((mx, mx))
        buf = io.BytesIO()
        if img.mode in ("RGBA", "LA", "P") and max(img.size) <= 160:
            img.convert("RGBA").save(buf, "PNG")
            return _b64(buf.getvalue(), "image/png")
        img.convert("RGB").save(buf, "JPEG", quality=80)
        return _b64(buf.getvalue(), "image/jpeg")
    except Exception:
        pass
    if len(data) <= 2_000_000:  # JS/CSS/fonts referenced by the template
        return _b64(data, content_type)
    return None


async def _inline_assets(html):
    """Replace every external src= URL with an embedded (downscaled) data URI.
    Downloads run concurrently; substitution is a single pass so a big transcript
    doesn't thrash memory."""
    urls = list(set(_SRC_RE.findall(html)))
    results = {}
    sem = asyncio.Semaphore(12)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sess:
        async def fetch(u):
            async with sem:
                try:
                    async with sess.get(u) as r:
                        if r.status != 200:
                            return
                        data = await r.read()
                        ct = r.headers.get("Content-Type", "image/png").split(";")[0]
                except Exception:
                    return
                enc = _encode_asset(data, u, ct)
                if enc:
                    results[u] = enc
        await asyncio.gather(*(fetch(u) for u in urls))

    return _SRC_RE.sub(lambda m: 'src="' + results.get(m.group(1), m.group(1)) + '"', html)


async def channel_to_html(channel, guild=None, outpath=None, bot=None):
    """Export `channel` to a self-contained HTML transcript at `outpath`.
    Returns the message count (0 if there was nothing to export)."""
    html = await chat_exporter.export(channel, tz_info="America/Chicago", bot=bot)
    if not html:
        return 0
    count = len(_MSG_RE.findall(html))
    if "</body>" in html:
        html = html.replace("</body>", _CSS_FIX + "</body>", 1)
    else:
        html += _CSS_FIX
    html = await _inline_assets(html)
    if outpath:
        with open(outpath, "w", encoding="utf-8") as f:
            f.write(html)
    return count
