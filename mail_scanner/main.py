"""
Mail Scanner — Point a camera at your mail and let AI sort it.

Usage:
    python main.py              Live camera mode (default)
    python main.py --test photo.jpg   Test with a single image file
    python main.py --backend claude   Use Claude API instead of Ollama

Controls (live mode):
    SPACE  — Force capture & classify the current frame
    Q/ESC  — Quit
"""
import argparse
import sys
import time
import cv2
import config
from camera import MotionDetector, is_clear_shot, open_camera
from classifier import classify
from storage import save_image, log_result


# colors
GREEN = (0, 200, 0)
RED = (0, 0, 220)
YELLOW = (0, 220, 220)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def draw_status(frame, text, color=GREEN):
    """Draw a status bar at the top of the frame."""
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), BLACK, -1)
    cv2.putText(frame, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


def draw_result(frame, result):
    """Draw the classification result on the frame."""
    y = frame.shape[0] - 120
    cv2.rectangle(frame, (0, y - 10), (frame.shape[1], frame.shape[0]), BLACK, -1)

    priority = result.get("priority", "unknown")
    color = GREEN if priority == "junk" else YELLOW if priority == "file_for_records" else RED

    lines = [
        f"Priority: {priority.upper().replace('_', ' ')}",
        f"Type: {result.get('type', '?')}",
        f"Sender: {result.get('sender', '?')}",
        f"Summary: {result.get('summary', '?')[:80]}",
    ]
    due = result.get("due_date", "none")
    if due and due.lower() != "none":
        lines.append(f"Due: {due}")

    for i, line in enumerate(lines):
        cv2.putText(frame, line, (10, y + 20 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color if i == 0 else WHITE, 1)


def process_frame(frame):
    """Validate, classify, save, and return the result."""
    clear, reason = is_clear_shot(frame)
    if not clear:
        return None, reason

    print("  Classifying with AI...")
    result = classify(frame)
    image_path = save_image(frame)
    log_result(image_path, result)

    priority = result.get("priority", "?")
    summary = result.get("summary", "")
    print(f"  -> {priority.upper()}: {summary}")
    print(f"  Saved to {image_path}")
    return result, "Classified"


def run_live():
    """Main loop: watch the camera for mail, classify when scene settles."""
    print("Starting mail scanner...")
    print(f"AI backend: {config.AI_BACKEND}")
    print(f"Press SPACE to force-capture, Q or ESC to quit.\n")

    cap = open_camera()
    detector = MotionDetector()
    last_result = None
    status = "Waiting for mail..."
    status_color = GREEN

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera read failed, retrying...")
            time.sleep(0.5)
            continue

        display = frame.copy()
        force_capture = False

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord(" "):
            force_capture = True

        settled = detector.update(frame)

        if settled or force_capture:
            status = "Motion settled — checking shot..." if settled else "Manual capture..."
            status_color = YELLOW
            draw_status(display, status, status_color)
            cv2.imshow("Mail Scanner", display)
            cv2.waitKey(1)

            result, reason = process_frame(frame)
            if result:
                last_result = result
                status = f"Done! {result.get('priority', '').upper().replace('_', ' ')} — waiting for next..."
                status_color = GREEN
            else:
                status = f"Bad shot: {reason} — waiting for retry..."
                status_color = RED
                detector.last_process_time = 0  # allow immediate retry

        elif detector.motion_detected:
            status = "Motion detected — hold still..."
            status_color = YELLOW
        else:
            if last_result:
                status = f"Last: {last_result.get('priority', '').upper().replace('_', ' ')} — waiting for mail..."
            else:
                status = "Waiting for mail..."
            status_color = GREEN

        draw_status(display, status, status_color)
        if last_result:
            draw_result(display, last_result)
        cv2.imshow("Mail Scanner", display)

    cap.release()
    cv2.destroyAllWindows()
    print("Scanner stopped.")


def run_test(image_path):
    """Test mode: classify a single image file."""
    print(f"Testing with image: {image_path}")
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"Error: Cannot read image '{image_path}'")
        sys.exit(1)

    result, reason = process_frame(frame)
    if result:
        print("\n=== Classification Result ===")
        for key, val in result.items():
            if key != "raw_response":
                print(f"  {key}: {val}")
    else:
        print(f"Could not process: {reason}")


def main():
    parser = argparse.ArgumentParser(description="AI-powered mail scanner")
    parser.add_argument("--test", metavar="IMAGE", help="Test with a single image file")
    parser.add_argument("--backend", choices=["ollama", "claude"], help="AI backend to use")
    parser.add_argument("--camera", type=int, help="Camera index (default 0)")
    args = parser.parse_args()

    if args.backend:
        config.AI_BACKEND = args.backend
    if args.camera is not None:
        config.CAMERA_INDEX = args.camera

    if args.test:
        run_test(args.test)
    else:
        run_live()


if __name__ == "__main__":
    main()
