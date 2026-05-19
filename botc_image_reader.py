"""
OCR-based reader for BotC script and grimoire images.
Requires: pip install pytesseract  &&  apt-get install -y tesseract-ocr
"""
import io
import math
import re
import json
import difflib

from PIL import Image, ImageOps, ImageEnhance

try:
    import pytesseract
    TESSERACT_OK = True
except ImportError:
    TESSERACT_OK = False


def _load_chars():
    for path in ["/home/discord-bot/botc_data.json", "botc_data.json"]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            chars = list(data.get("characters", {}).keys())
            norm = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in chars}
            return chars, norm
        except Exception:
            pass
    return [], {}


BOTC_CHARS, BOTC_NORM = _load_chars()

_UI_WORDS = {
    "day", "night", "vote", "votes", "chat", "dawn", "dusk",
    "alive", "dead", "the", "and", "for", "you", "are", "not", "can",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _match_char(word):
    """Return canonical BotC character display name, or None."""
    n = _norm(word)
    if not n or len(n) < 2:
        return None
    if n in BOTC_NORM:
        return BOTC_NORM[n]
    close = difflib.get_close_matches(n, BOTC_NORM.keys(), n=1, cutoff=0.88)
    if close and close[0][0] == n[0]:
        return BOTC_NORM[close[0]]
    return None


# ---------------------------------------------------------------------------
# Color-based mask (script images only)
# ---------------------------------------------------------------------------

def _apply_color_mask(img_rgb):
    """
    Return a copy of img_rgb with non-colored pixels replaced by white.

    Script images use color for character names (blue for good, red for evil)
    and gray/black for ability text and headers. Masking non-colored pixels
    leaves only the character name text visible for OCR.

    A pixel is 'colored' if its saturation > 0.30 and it isn't nearly black.
    """
    pixels = list(img_rgb.getdata())
    out = []
    for r, g, b in pixels:
        mx = max(r, g, b)
        mn = min(r, g, b)
        sat = (mx - mn) / mx if mx > 0 else 0.0
        # Keep if clearly colored (not gray/black/white)
        if sat > 0.30 and mx > 50:
            out.append((r, g, b))
        else:
            out.append((255, 255, 255))
    masked = img_rgb.copy()
    masked.putdata(out)
    return masked


# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------

def _run_ocr(pil_img, min_conf=20, config=""):
    """Run Tesseract on a preprocessed PIL image. Returns list of (text, x, y, w, h)."""
    data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT, config=config)
    items = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if t and int(data["conf"][i]) > min_conf:
            items.append((t, data["left"][i], data["top"][i],
                          data["width"][i], data["height"][i]))
    return items


def _scale_up(img, min_width=1400):
    w, h = img.size
    if w < min_width:
        scale = min_width / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def _ocr_script(img_bytes):
    """
    OCR a script image using the color mask.
    Only colored text (character names) survives the mask — ability text is gone.
    Returns (items, img_w, img_h).
    """
    if not TESSERACT_OK:
        raise RuntimeError("pytesseract not installed")

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = _scale_up(img)
    masked = _apply_color_mask(img)
    gray = ImageEnhance.Contrast(masked.convert("L")).enhance(2.5)
    w, h = img.size
    # Low confidence floor — color masking already eliminates false positives,
    # so short names like "Po" that Tesseract reads with low confidence still count.
    # --psm 11: sparse text, suits character names scattered down a script page.
    return _run_ocr(gray, min_conf=5, config="--psm 11"), w, h


def _ocr_grimoire(img_bytes):
    """
    OCR a grimoire screenshot (dark background).
    Inverts the image so white player-name text becomes dark-on-light.
    Returns (items, img_w, img_h).
    """
    if not TESSERACT_OK:
        raise RuntimeError("pytesseract not installed")

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = _scale_up(img)
    w, h = img.size

    # Detect dark background by sampling the four corners — NOT the centre.
    # The grimoire centre has bright coloured icons (character tokens, votes, etc.)
    # which inflate the average and can fool a centre-based check.
    # Corners are pure background: dark for grimoire screenshots, light for other images.
    cs = min(150, w // 6, h // 6)
    corner_pixels = (
        list(img.crop((0,     0,     cs,     cs)).getdata()) +
        list(img.crop((w-cs,  0,     w,      cs)).getdata()) +
        list(img.crop((0,     h-cs,  cs,     h )).getdata()) +
        list(img.crop((w-cs,  h-cs,  w,      h )).getdata())
    )
    avg = sum(r + g + b for r, g, b in corner_pixels) / (3 * len(corner_pixels))
    if avg < 130:
        img = ImageOps.invert(img)

    gray = ImageEnhance.Contrast(img.convert("L")).enhance(3.0)
    # --psm 11: sparse text — find text scattered in any order (suits the circle layout)
    return _run_ocr(gray, config="--psm 11"), w, h


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def debug_grimoire(img_bytes):
    """
    Return (preprocessed_png_bytes, ocr_lines) for debugging.
    preprocessed_png_bytes: what Tesseract actually sees (post-inversion, post-contrast).
    ocr_lines: list of strings "conf=XX  '{text}'  at ({x},{y}) size {w}x{h}"
    """
    if not TESSERACT_OK:
        raise RuntimeError("pytesseract not installed")

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = _scale_up(img)
    w, h = img.size

    cs = min(150, w // 6, h // 6)
    corner_pixels = (
        list(img.crop((0,     0,     cs,     cs)).getdata()) +
        list(img.crop((w-cs,  0,     w,      cs)).getdata()) +
        list(img.crop((0,     h-cs,  cs,     h )).getdata()) +
        list(img.crop((w-cs,  h-cs,  w,      h )).getdata())
    )
    avg = sum(r + g + b for r, g, b in corner_pixels) / (3 * len(corner_pixels))
    inverted = avg < 130
    if inverted:
        img = ImageOps.invert(img)

    gray = ImageEnhance.Contrast(img.convert("L")).enhance(3.0)

    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config="--psm 11")
    lines = [f"corner_avg={avg:.1f}  inverted={inverted}  size={w}x{h}  psm=11"]
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if not t:
            continue
        conf = int(data["conf"][i])
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        lines.append(f"conf={conf:3d}  '{t}'  at ({x},{y}) size {bw}x{bh}")

    buf = io.BytesIO()
    gray.save(buf, format="PNG")
    return buf.getvalue(), lines


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_image(img_bytes):
    """
    Return 'script' or 'grimoire'.
    Tries script OCR (color-masked); if it finds 4+ BotC character names → script.
    """
    try:
        items, _, _ = _ocr_script(img_bytes)
    except Exception:
        return "grimoire"

    texts = [t for t, *_ in items]
    matches = 0
    for i, t in enumerate(texts):
        if _match_char(t):
            matches += 1
        elif i + 1 < len(texts) and _match_char(t + texts[i + 1]):
            matches += 1

    return "script" if matches >= 3 else "grimoire"


# ---------------------------------------------------------------------------
# Script image → character list
# ---------------------------------------------------------------------------

def extract_script_characters(img_bytes):
    """
    Return ordered list of BotC character display names found in a script image.

    Uses color-masked OCR so only the colored character-name text is visible.
    No ability text survives the mask, eliminating false positives entirely.
    """
    items, _, _ = _ocr_script(img_bytes)
    texts = [t for t, *_ in items]

    found = []
    i = 0
    while i < len(texts):
        m = None
        # Try two-word match first ("Town Crier", "Tea Lady", "Snake Charmer", etc.)
        if i + 1 < len(texts):
            m = (_match_char(texts[i] + texts[i + 1]) or
                 _match_char(texts[i] + " " + texts[i + 1]))
        if m:
            if m not in found:
                found.append(m)
            i += 2
            continue

        m = _match_char(texts[i])
        if m and m not in found:
            found.append(m)
        i += 1

    return found


# ---------------------------------------------------------------------------
# Grimoire image → player name list (clockwise order)
# ---------------------------------------------------------------------------

def extract_player_names(img_bytes):
    """
    Return player names from a grimoire circle image, sorted clockwise from the top.

    Player names sit on the outer ring (never the centre).
    Filters: BotC character names, known UI words, text inside the inner exclusion zone.
    """
    items, img_w, img_h = _ocr_grimoire(img_bytes)
    cx, cy = img_w / 2, img_h / 2

    # Exclude text whose centre is within ~15 % of the shorter image dimension
    # from the image centre — that zone has coloured game icons, not player names.
    inner_r = min(img_w, img_h) * 0.15

    candidates = []
    seen = set()
    for text, x, y, w, h in items:
        if len(text) < 2:
            continue
        if _norm(text) in _UI_WORDS:
            continue
        if _match_char(text):
            continue

        tx = x + w / 2
        ty = y + h / 2

        if math.hypot(tx - cx, ty - cy) < inner_r:
            continue

        key = _norm(text)
        if key in seen:
            continue
        seen.add(key)

        angle = math.atan2(tx - cx, cy - ty) % (2 * math.pi)
        candidates.append((angle, text))

    candidates.sort(key=lambda c: c[0])
    return [t for _, t in candidates]
