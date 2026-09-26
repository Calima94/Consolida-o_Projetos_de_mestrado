"""Elbow angle from a camera image, ported from Capture_EMG_Data/pose_module.py.

The thesis tool was built on a base version by Alan Mendes
(https://github.com/alans96/arm_robotics); see THIRD_PARTY_NOTICES.md.

The thesis used the legacy MediaPipe "Solutions" API (``mp.solutions.pose``),
which no longer exists in MediaPipe 1.x. This module uses the Tasks API
(``PoseLandmarker``) with the same 33-landmark BlazePose topology, so the
landmark indices and the angle formula are unchanged:

- right arm (as the thesis selected it on the mirrored image): 11-13-15,
- left arm: 12-14-16,
- angle = atan2(wrist - elbow) - atan2(shoulder - elbow), in degrees, mapped
  to [0, 360). About 170 deg is the arm extended, 90 deg is a right angle.

New relative to the thesis: detections whose shoulder, elbow or wrist
visibility is below ``min_visibility`` are rejected. On the thesis video
(Capture_EMG_Data/Videos/test_2_05.avi), frames with visible landmarks agree
with the angle the thesis printed on screen within about 2 deg; low-visibility
frames were the ones that disagreed.

MediaPipe is imported lazily, so the geometry helpers work without it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

ARM_LANDMARKS = {"right": (11, 13, 15), "left": (12, 14, 16)}

# Pinned model (versioned URL + SHA-256), downloaded into the Docker image.
DEFAULT_MODEL_PATH = "/opt/mediapipe/models/pose_landmarker_full.task"


def elbow_angle_deg(
    shoulder: tuple[float, float], elbow: tuple[float, float], wrist: tuple[float, float]
) -> float:
    """Angle at the elbow in image coordinates, exactly as the thesis computed it.

    Examples
    --------
    >>> round(elbow_angle_deg((0, 0), (1, 0), (2, 0)))
    180
    >>> round(elbow_angle_deg((0, 0), (1, 0), (1, -1)))
    90
    """
    (x1, y1), (x2, y2), (x3, y3) = shoulder, elbow, wrist
    angle = math.degrees(math.atan2(y3 - y2, x3 - x2) - math.atan2(y1 - y2, x1 - x2))
    return angle + 360.0 if angle < 0 else angle


def anatomical_to_sim_rad(angle_deg: float) -> float:
    """Map the measured elbow angle to the simulator elbow joint (radians).

    The simulated elbow is 0 when extended, like the thesis class mapping
    (170 deg -> 0, 90 deg -> 90 deg). Values are clipped to [0, 180] deg;
    angles above 180 deg (bending the "wrong" way in the image) map to 0.

    Examples
    --------
    >>> round(math.degrees(anatomical_to_sim_rad(90.0)))
    90
    >>> anatomical_to_sim_rad(200.0)
    0.0
    """
    return math.radians(float(np.clip(180.0 - angle_deg, 0.0, 180.0)))


@dataclass
class ArmDetection:
    """Result for one frame: pixel coordinates, angle and worst visibility."""

    points_px: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    angle_deg: float
    visibility: float


class ElbowAngleEstimator:
    """MediaPipe PoseLandmarker (video mode) returning the elbow angle.

    Parameters
    ----------
    model_path : str
        ``pose_landmarker_*.task`` file.
    arm : str
        ``"right"`` or ``"left"`` (thesis convention on the mirrored image).
    min_visibility : float
        Minimum visibility of the three landmarks to accept a detection.
    """

    def __init__(
        self, model_path: str = DEFAULT_MODEL_PATH, arm: str = "right", min_visibility: float = 0.5
    ) -> None:
        if arm not in ARM_LANDMARKS:
            raise ValueError(f"arm must be 'right' or 'left', got {arm!r}")
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            PoseLandmarker,
            PoseLandmarkerOptions,
            RunningMode,
        )

        self._mp = mp
        self.indices = ARM_LANDMARKS[arm]
        self.min_visibility = min_visibility
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
        )
        self._landmarker = PoseLandmarker.create_from_options(options)
        self._last_ts = -1

    def process(self, bgr: np.ndarray, timestamp_ms: int) -> ArmDetection | None:
        """Detect the arm in a BGR frame; ``None`` if absent or not visible enough."""
        import cv2

        timestamp_ms = max(int(timestamp_ms), self._last_ts + 1)  # must increase
        self._last_ts = timestamp_ms
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.pose_landmarks:
            return None
        landmarks = result.pose_landmarks[0]
        h, w = bgr.shape[:2]
        picked = [landmarks[i] for i in self.indices]
        visibility = min(float(p.visibility or 0.0) for p in picked)
        points = tuple((int(p.x * w), int(p.y * h)) for p in picked)
        angle = elbow_angle_deg(*[(p.x * w, p.y * h) for p in picked])
        detection = ArmDetection(points_px=points, angle_deg=angle, visibility=visibility)
        return detection if visibility >= self.min_visibility else None

    def close(self) -> None:
        self._landmarker.close()


def draw_overlay(
    img: np.ndarray, det: ArmDetection | None, recording: bool, status: str = ""
) -> np.ndarray:
    """Thesis-style overlay: arm in orange/red while recording, green otherwise.

    Also draws the thesis 40-171 deg progress bar and the angle value.
    """
    import cv2

    if det is not None:
        (x1, y1), (x2, y2), (x3, y3) = det.points_px
        line, dot = ((0, 0, 255), (50, 200, 255)) if recording else ((0, 255, 0), (255, 0, 0))
        cv2.line(img, (x1, y1), (x2, y2), line, 3)
        cv2.line(img, (x3, y3), (x2, y2), line, 3)
        for x, y in det.points_px:
            cv2.circle(img, (x, y), 4, dot, cv2.FILLED)
            cv2.circle(img, (x, y), 8, dot, 2)
        cv2.putText(
            img, str(int(det.angle_deg)), (500, 100), cv2.FONT_HERSHEY_PLAIN, 4, (0, 0, 255), 2
        )
        per = float(np.interp(det.angle_deg, (40, 171), (0, 100)))
        bar = int(np.interp(det.angle_deg, (40, 171), (400, 100)))
        cv2.rectangle(img, (50, bar), (60, 400), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, f"{int(per)}%", (55, 300), cv2.FONT_HERSHEY_PLAIN, 5, (255, 0, 0), 4)
    for i, text in enumerate(status.split(" | ") if status else []):
        cv2.putText(img, text, (10, 440 - 22 * i), cv2.FONT_HERSHEY_PLAIN, 1.3, (255, 255, 255), 2)
    return img
