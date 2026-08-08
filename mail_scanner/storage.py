"""Save scanned mail images and log results to CSV."""
import csv
from datetime import datetime
from pathlib import Path
import cv2
import config


def _ensure_dirs():
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_image(frame):
    """Save the mail image and return the file path."""
    _ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.OUTPUT_DIR / f"mail_{timestamp}.png"
    cv2.imwrite(str(path), frame)
    return path


def log_result(image_path: Path, result: dict):
    """Append a classification result to the CSV log."""
    _ensure_dirs()
    file_exists = config.CSV_FILE.exists()

    with open(config.CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "image", "type", "priority",
                "summary", "sender", "due_date",
            ])
        writer.writerow([
            datetime.now().isoformat(),
            str(image_path),
            result.get("type", ""),
            result.get("priority", ""),
            result.get("summary", ""),
            result.get("sender", ""),
            result.get("due_date", ""),
        ])
