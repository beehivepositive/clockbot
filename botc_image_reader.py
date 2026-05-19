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
    img = _scale_up(img, min_width=2000)
    masked = _apply_color_mask(img)
    gray = ImageEnhance.Contrast(masked.convert("L")).enhance(2.5)
    w, h = img.size
    # Disable word-frequency and system dictionaries — they silently reject short
    # real words like "Po" as statistically implausible. Color masking already
    # eliminates false positives so we don't need the language-model gate.
    # Note: --oem 1 and tessedit_char_whitelist are intentionally omitted —
    # whitelist is unreliable in LSTM mode, and oem 1 fails if LSTM data is missing.
    _SCRIPT_CFG = "--psm 11 -c load_system_dawg=0 -c load_freq_dawg=0"
    return _run_ocr(gray, min_conf=-1, config=_SCRIPT_CFG), w, h


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

    base = img.convert("L")
    # PSM 3 (full-page) at lower contrast — catches names like Jeff that over-saturate
    # at high contrast and disappear. PSM 11 (sparse text) at higher contrast catches
    # names scattered around the ring that PSM 3 misses.
    gray_lo = ImageEnhance.Contrast(base).enhance(2.0)
    gray_hi = ImageEnhance.Contrast(base).enhance(3.0)
    items_a = _run_ocr(gray_lo, config="--psm 3")
    items_b = _run_ocr(gray_hi, config="--psm 11")
    seen_n = set()
    merged = []
    for item in items_a + items_b:
        n = re.sub(r"[^a-z0-9]", "", item[0].lower())
        if n and n not in seen_n:
            seen_n.add(n)
            merged.append(item)
    return merged, w, h


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

    base = img.convert("L")
    gray_lo = ImageEnhance.Contrast(base).enhance(2.0)
    gray_hi = ImageEnhance.Contrast(base).enhance(3.0)

    lines = [f"corner_avg={avg:.1f}  inverted={inverted}  size={w}x{h}"]
    for label, gray, psm in (
        ("psm3 contrast=2.0", gray_lo, "--psm 3"),
        ("psm11 contrast=3.0", gray_hi, "--psm 11"),
    ):
        lines.append(f"\n=== {label} ===")
        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config=psm)
        for i in range(len(data["text"])):
            t = data["text"][i].strip()
            if not t:
                continue
            conf = int(data["conf"][i])
            x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            lines.append(f"conf={conf:3d}  '{t}'  at ({x},{y}) size {bw}x{bh}")

    buf = io.BytesIO()
    gray_lo.save(buf, format="PNG")
    return buf.getvalue(), lines


def debug_script(img_bytes):
    """
    Return (masked_png_bytes, ocr_lines) for debugging script OCR.
    masked_png_bytes: the color-masked grayscale image Tesseract sees.
    ocr_lines: every word Tesseract found, with conf and position, NO filtering.
    """
    if not TESSERACT_OK:
        raise RuntimeError("pytesseract not installed")

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = _scale_up(img, min_width=2000)
    w, h = img.size
    masked = _apply_color_mask(img)
    gray = ImageEnhance.Contrast(masked.convert("L")).enhance(2.5)

    cfg = "--psm 11 -c load_system_dawg=0 -c load_freq_dawg=0"
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT, config=cfg)
    lines = [f"size={w}x{h}  config={cfg!r}"]
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

def _has_grimoire_center(img_rgb):
    """
    Return True if the image has a cluster of distinctly-coloured pixels near
    its centre — the grimoire always renders coloured token icons there
    (green for Townsfolk, red for Demons, orange for reminders, etc.).
    Script images have only grey/black ability text in the centre, so they fail.
    """
    w, h = img_rgb.size
    cx, cy = w // 2, h // 2
    r = min(w, h) // 6          # sample the central ~16 % × 16 % region
    region = img_rgb.crop((max(0, cx - r), max(0, cy - r),
                           min(w, cx + r), min(h, cy + r)))
    pixels = list(region.getdata())
    if not pixels:
        return False
    colored = 0
    for rv, gv, bv in pixels:
        mx = max(rv, gv, bv)
        mn = min(rv, gv, bv)
        sat = (mx - mn) / mx if mx > 0 else 0.0
        if sat > 0.35 and 40 < mx < 230:
            colored += 1
    return (colored / len(pixels)) > 0.05


def classify_image(img_bytes):
    """
    Return 'script' or 'grimoire'.

    Grimoire detection uses a positive signal — coloured token icons always
    clustered in the centre — so random images and custom-background shots
    that happen to look dark don't get misclassified.
    Script detection falls back to colour-masked OCR finding BotC names.
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    if _has_grimoire_center(img):
        return "grimoire"

    try:
        items, _, _ = _ocr_script(img_bytes)
    except Exception:
        return "unknown"

    texts = [t for t, *_ in items]
    matches = 0
    for i, t in enumerate(texts):
        if _match_char(t):
            matches += 1
        elif i + 1 < len(texts) and _match_char(t + texts[i + 1]):
            matches += 1

    return "script" if matches >= 3 else "unknown"


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
        # Only accept the two-word result if it differs from the single-word result —
        # i.e. it genuinely needed both tokens. Without this guard, e.g. 'ShabalothPo'
        # fuzzy-matches 'Shabaloth' (ratio 0.9 > cutoff), consuming 'Po' silently.
        if i + 1 < len(texts):
            m2 = (_match_char(texts[i] + texts[i + 1]) or
                  _match_char(texts[i] + " " + texts[i + 1]))
            m1 = _match_char(texts[i])
            if m2 and m2 != m1:
                m = m2
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

    # Cluster radius: if two OCR items are this close, they're the same label.
    # Keeps e.g. "(bal..." from splitting Butti into two entries.
    cluster_r = 150

    candidates = []
    seen_norm = set()
    placed = []   # (tx, ty) of accepted items, for position-based dedup
    for text, x, y, w, h in items:
        if len(text) < 3:
            continue
        if _norm(text) in _UI_WORDS:
            continue
        if _match_char(text):
            continue

        tx = x + w / 2
        ty = y + h / 2

        if math.hypot(tx - cx, ty - cy) < inner_r:
            continue

        # Skip if a nearby item was already accepted (same label, different OCR fragment)
        if any(math.hypot(tx - px, ty - py) < cluster_r for px, py in placed):
            continue

        key = _norm(text)
        if key in seen_norm:
            continue
        seen_norm.add(key)
        placed.append((tx, ty))

        angle = math.atan2(tx - cx, cy - ty) % (2 * math.pi)
        candidates.append((angle, text))

    candidates.sort(key=lambda c: c[0])
    return [t for _, t in candidates]
