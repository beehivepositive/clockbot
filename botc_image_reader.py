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

def _run_ocr(pil_img):
    """Run Tesseract on a preprocessed PIL image. Returns list of (text, x, y, w, h)."""
    data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
    items = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if t and int(data["conf"][i]) > 20:
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
    return _run_ocr(gray), w, h


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

    # Detect dark background by sampling the image centre
    cx, cy = w // 2, h // 2
    sample = list(img.crop((cx - 100, cy - 100, cx + 100, cy + 100)).getdata())
    avg = sum(r + g + b for r, g, b in sample) / (3 * len(sample))
    if avg < 110:
        img = ImageOps.invert(img)

    gray = ImageEnhance.Contrast(img.convert("L")).enhance(2.0)
    return _run_ocr(gray), w, h


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

    Player names are always:
      - The largest text in the image
      - On the outer ring (never in the centre)
      - Always contain at least one letter (no pure numbers/punctuation)
    """
    items, img_w, img_h = _ocr_grimoire(img_bytes)
    cx, cy = img_w / 2, img_h / 2

    # Exclude text within ~20 % of the shorter dimension from centre
    # (the centre has coloured game icons, not player names)
    inner_r = min(img_w, img_h) * 0.20

    # Player names are always the largest text in the image.
    # Compute the 65th-percentile height across all OCR items and use 65 % of
    # that as the minimum — filters vote counts, labels, and other small text.
    all_heights = sorted(h for _, _, _, _, h in items if h > 0)
    min_h = (all_heights[int(len(all_heights) * 0.65)] * 0.65) if all_heights else 1

    candidates = []
    seen = set()
    for text, x, y, w, h in items:
        if len(text) < 2:
            continue
        # Skip anything without a letter (numbers, punctuation, vote counts, "14", etc.)
        if not re.search(r'[a-zA-Z]', text):
            continue
        if _norm(text) in _UI_WORDS:
            continue
        if _match_char(text):
            continue

        tx = x + w / 2
        ty = y + h / 2

        # Exclude centre zone where game icons live
        if math.hypot(tx - cx, ty - cy) < inner_r:
            continue

        # Only keep large text (player names are the biggest text on screen)
        if h < min_h:
            continue

        key = _norm(text)
        if key in seen:
            continue
        seen.add(key)

        angle = math.atan2(tx - cx, cy - ty) % (2 * math.pi)
        candidates.append((angle, text))

    candidates.sort(key=lambda c: c[0])
    return [t for _, t in candidates]
