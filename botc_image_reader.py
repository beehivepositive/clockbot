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

# Words that appear constantly in ability text and would false-match character names
_ABILITY_NOISE = {
    "drunk", "dead", "alive", "kill", "die", "dies", "good", "evil",
    "night", "day", "vote", "player", "town", "game", "fool", "recluse",
    "spy", "baron", "imp", "slayer", "virgin", "monk", "soldier", "mayor",
}


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

# Common non-name words to exclude from player list
_UI_WORDS = {
    "day", "night", "vote", "votes", "chat", "dawn", "dusk", "alive",
    "dead", "the", "and", "for", "you", "are", "not", "can",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _match_char(word):
    """
    Return the canonical BotC character display name for a word, or None.

    Uses exact match first, then fuzzy with a high cutoff.
    Requires the first letter to match — prevents 'night' → 'Knight' etc.
    Skips words that are common ability-text noise.
    """
    n = _norm(word)
    if not n or len(n) < 3:
        return None
    # Skip words that are almost always from ability text, not character names
    if n in _ABILITY_NOISE:
        return None
    if n in BOTC_NORM:
        return BOTC_NORM[n]
    # Fuzzy match: require high ratio AND same first letter
    close = difflib.get_close_matches(n, BOTC_NORM.keys(), n=1, cutoff=0.88)
    if close and close[0][0] == n[0]:
        return BOTC_NORM[close[0]]
    return None


def _preprocess(img_bytes):
    """Open and preprocess an image for OCR. Returns (PIL.Image, width, height)."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size

    # Scale up small images — helps OCR on low-res screenshots
    if w < 1400:
        scale = 1400 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size

    # Detect dark-background images (grimoire screenshots) by sampling the centre
    cx, cy = w // 2, h // 2
    sample = list(img.crop((cx - 100, cy - 100, cx + 100, cy + 100)).getdata())
    avg = sum(r + g + b for r, g, b in sample) / (3 * len(sample))
    if avg < 110:
        img = ImageOps.invert(img)

    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.0)
    return img, w, h


def _ocr_boxes(img_bytes):
    """
    Run Tesseract on img_bytes.
    Returns (items, img_w, img_h) where items = list of (text, x, y, w, h).
    """
    if not TESSERACT_OK:
        raise RuntimeError("pytesseract not installed — run: pip install pytesseract")

    proc, img_w, img_h = _preprocess(img_bytes)
    data = pytesseract.image_to_data(proc, output_type=pytesseract.Output.DICT)

    items = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        conf = int(data["conf"][i])
        if t and conf > 30:
            items.append((t, data["left"][i], data["top"][i],
                          data["width"][i], data["height"][i]))
    return items, img_w, img_h


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_image(img_bytes):
    """Return 'script' or 'grimoire'. Script images contain many BotC character names."""
    items, _, _ = _ocr_boxes(img_bytes)
    texts = [t for t, *_ in items]

    matches = 0
    for i, t in enumerate(texts):
        if _match_char(t):
            matches += 1
        elif i + 1 < len(texts) and _match_char(t + texts[i + 1]):
            matches += 1

    return "script" if matches >= 4 else "grimoire"


# ---------------------------------------------------------------------------
# Script image → character list
# ---------------------------------------------------------------------------

def extract_script_characters(img_bytes):
    """
    Return ordered list of BotC character display names found in a script image.

    Scans OCR words (and adjacent pairs for two-word names) against the known
    character list. Uses strict matching to avoid ability-text false positives.
    Deduplicates: each character counted once regardless of how many times the
    name appears in ability text.
    """
    items, _, _ = _ocr_boxes(img_bytes)
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

    Strategy:
    - Get all OCR text with positions.
    - Discard: BotC character names, pure numbers, UI words, single chars.
    - Compute angle of each remaining item from the image centre.
    - Sort clockwise (angle 0 = 12 o'clock).

    The ring-distance filter is intentionally removed — UI panels in screenshots
    can shift the circle off-centre, making distance-based filtering unreliable.
    """
    items, img_w, img_h = _ocr_boxes(img_bytes)
    cx, cy = img_w / 2, img_h / 2

    candidates = []
    for text, x, y, w, h in items:
        # Skip short tokens, pure numbers, known UI words, BotC character names
        if len(text) < 2:
            continue
        if text.isdigit():
            continue
        if _norm(text) in _UI_WORDS:
            continue
        if _match_char(text):
            continue
        # Skip two-word combos that match a character (e.g. "Town Crier")
        tx = x + w / 2
        ty = y + h / 2
        angle = math.atan2(tx - cx, cy - ty) % (2 * math.pi)
        candidates.append((angle, text))

    candidates.sort(key=lambda c: c[0])
    return [t for _, t in candidates]
