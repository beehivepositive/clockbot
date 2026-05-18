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


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _match_char(word):
    """Return the canonical display name for a BotC character, or None."""
    n = _norm(word)
    if not n or len(n) < 3:
        return None
    if n in BOTC_NORM:
        return BOTC_NORM[n]
    close = difflib.get_close_matches(n, BOTC_NORM.keys(), n=1, cutoff=0.84)
    return BOTC_NORM[close[0]] if close else None


def _preprocess(img_bytes):
    """Open and preprocess an image for OCR. Returns (PIL.Image, width, height)."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size

    # Scale up small images — helps OCR on low-res screenshots
    if w < 1200:
        scale = 1200 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size

    # Detect dark-background images (grimoire screenshots)
    sample = list(img.crop((0, 0, min(300, w), min(300, h))).getdata())
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
    """
    Return 'script', 'grimoire', or 'unknown'.
    Script images contain many matching BotC character names.
    Grimoire images contain player names arranged in a circle.
    """
    items, _, _ = _ocr_boxes(img_bytes)
    texts = [t for t, *_ in items]

    matches = 0
    for i, t in enumerate(texts):
        if _match_char(t):
            matches += 1
        elif i + 1 < len(texts) and _match_char(t + texts[i + 1]):
            matches += 1

    if matches >= 4:
        return "script"
    # Grimoire: fewer char matches, lots of short proper-noun-ish words
    return "grimoire"


# ---------------------------------------------------------------------------
# Script image → character list
# ---------------------------------------------------------------------------

def extract_script_characters(img_bytes):
    """
    Return ordered list of BotC character display names found in a script image.
    Works by matching OCR words (and adjacent word pairs) against the known character list.
    """
    items, _, _ = _ocr_boxes(img_bytes)
    texts = [t for t, *_ in items]

    found = []
    i = 0
    while i < len(texts):
        # Try merging with next word first (handles "Town Crier", "Tea Lady", etc.)
        m = None
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
    Return player names from a grimoire/circle image, sorted clockwise from the top.

    Strategy:
    - Find the centre of the image.
    - All detected text is tagged with its radial distance and angle from centre.
    - Player name tokens live in a "ring" at 30–95% of the max radial distance.
    - BotC character names (role icons) are excluded; what remains are player names.
    - Sorted by angle (clockwise from 12 o'clock).
    """
    items, img_w, img_h = _ocr_boxes(img_bytes)
    cx, cy = img_w / 2, img_h / 2

    tagged = []
    for text, x, y, w, h in items:
        if len(text) < 2:
            continue
        tx = x + w / 2
        ty = y + h / 2
        dist = math.sqrt((tx - cx) ** 2 + (ty - cy) ** 2)
        angle = math.atan2(tx - cx, cy - ty) % (2 * math.pi)
        tagged.append((dist, angle, text))

    if not tagged:
        return []

    max_dist = max(d for d, *_ in tagged)
    # Keep only the outer ring where player names live
    ring = [(a, t) for d, a, t in tagged
            if max_dist * 0.30 <= d <= max_dist * 0.95]

    # Drop anything that fuzzy-matches a BotC character name
    players = [(a, t) for a, t in ring if not _match_char(t)]

    players.sort(key=lambda x: x[0])
    return [t for _, t in players]
