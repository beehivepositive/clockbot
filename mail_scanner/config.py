"""Configuration for the mail scanner."""
from pathlib import Path

# --- Camera ---
CAMERA_INDEX = 0  # 0 = default webcam, change if you have multiple cameras

# --- Motion Detection ---
MOTION_THRESHOLD = 5000       # minimum contour area to count as motion
STILL_FRAMES_REQUIRED = 15    # frames with no motion before we consider the scene "settled"
COOLDOWN_SECONDS = 5          # wait this long after processing before looking for new mail

# --- Clear Shot Detection ---
BLUR_THRESHOLD = 100.0   # Laplacian variance below this = too blurry
MIN_BRIGHTNESS = 40      # average brightness below this = too dark
MAX_BRIGHTNESS = 240     # average brightness above this = overexposed

# --- AI Backend ---
# "ollama" (free, local) or "claude" (paid API)
AI_BACKEND = "ollama"
OLLAMA_MODEL = "llava"           # or "llama3.2-vision", "bakllava", etc.
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# --- Output ---
OUTPUT_DIR = Path("./scanned_mail")
CSV_FILE = Path("./scanned_mail/mail_log.csv")

# --- Classification Prompt ---
CLASSIFY_PROMPT = """You are a mail sorting assistant. Look at this image of a piece of mail and provide:

1. **Type**: bill, personal letter, advertisement/junk, government/legal, medical, financial statement, package slip, other
2. **Priority**: action_required, file_for_records, junk
3. **Summary**: One sentence describing what this mail is about.
4. **Sender**: Who sent it (if visible).
5. **Due Date**: Any deadlines or due dates visible (or "none").

Respond in this exact format:
TYPE: <type>
PRIORITY: <priority>
SUMMARY: <summary>
SENDER: <sender>
DUE_DATE: <due_date>
"""
