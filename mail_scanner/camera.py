"""Camera capture, motion detection, and clear-shot validation."""
import time
import cv2
import numpy as np
import config


class MotionDetector:
    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=50, detectShadows=True
        )
        self.still_count = 0
        self.motion_detected = False
        self.last_process_time = 0

    def update(self, frame):
        """Returns True when scene has settled after motion (mail placed and hand removed)."""
        if time.time() - self.last_process_time < config.COOLDOWN_SECONDS:
            return False

        fg_mask = self.bg_subtractor.apply(frame)
        # remove shadows and noise
        fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)[1]
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        total_area = sum(cv2.contourArea(c) for c in contours)

        has_motion = total_area > config.MOTION_THRESHOLD

        if has_motion:
            self.motion_detected = True
            self.still_count = 0
        elif self.motion_detected:
            self.still_count += 1
            if self.still_count >= config.STILL_FRAMES_REQUIRED:
                self.motion_detected = False
                self.still_count = 0
                self.last_process_time = time.time()
                return True

        return False


def is_clear_shot(frame):
    """Check if the frame is sharp enough and properly exposed."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < config.BLUR_THRESHOLD:
        return False, f"Too blurry (sharpness: {laplacian_var:.0f}, need {config.BLUR_THRESHOLD})"

    brightness = np.mean(gray)
    if brightness < config.MIN_BRIGHTNESS:
        return False, f"Too dark (brightness: {brightness:.0f})"
    if brightness > config.MAX_BRIGHTNESS:
        return False, f"Too bright (brightness: {brightness:.0f})"

    return True, "Clear"


def open_camera():
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError(
            f"Cannot open camera {config.CAMERA_INDEX}. "
            "Check that a webcam is connected and not in use by another app."
        )
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap
