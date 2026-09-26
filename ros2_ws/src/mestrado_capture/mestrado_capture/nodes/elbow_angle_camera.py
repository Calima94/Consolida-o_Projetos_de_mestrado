"""Measure the elbow angle from a webcam or a video file (MediaPipe).

Replaces the ``write_image`` loop of the thesis capture tool. Publishes the
angle on ``/capture/elbow_angle_deg`` (thesis convention, ~170 deg extended)
and, with ``mirror_to_sim``, also drives the simulated elbow directly: the
Gazebo arm copies your arm, no sEMG needed.

Parameters
----------
source : str
    Camera index (``"0"``), video file path, or stream URL.
model_path : str
    MediaPipe ``pose_landmarker_*.task`` file.
arm : str
    ``right`` or ``left`` (thesis convention on the mirrored image).
flip : bool
    Mirror the image horizontally before detection, as the thesis did.
min_visibility : float
    Reject detections with less visible shoulder/elbow/wrist.
show_window : bool
    Show the annotated image (ESC stops the capture, as in the thesis).
video_out : str
    If set, save the annotated video there (the thesis saved Videos/*.avi).
mirror_to_sim : bool
    Also publish ``/arm/elbow/cmd_pos`` from the measured angle.
loop : bool
    Restart a video file at its end.
"""

from __future__ import annotations

import time

import cv2
from rclpy.node import Node
from std_msgs.msg import Bool, Float64, String

from mestrado_capture.pose import (
    DEFAULT_MODEL_PATH,
    ElbowAngleEstimator,
    anatomical_to_sim_rad,
    draw_overlay,
)
from mestrado_emg.nodes.common import ELBOW_CMD_TOPIC, spin_node

ANGLE_TOPIC = "/capture/elbow_angle_deg"
RECORDING_TOPIC = "/capture/recording"
STATUS_TOPIC = "/capture/status"


class StopRequested(KeyboardInterrupt):
    """Raised from a callback to end the node through the normal shutdown path."""


class ElbowAngleCameraNode(Node):
    def __init__(self) -> None:
        super().__init__("elbow_angle_camera")
        p = {
            "source": "0",
            "model_path": DEFAULT_MODEL_PATH,
            "arm": "right",
            "flip": True,
            "min_visibility": 0.5,
            "show_window": True,
            "video_out": "",
            "mirror_to_sim": False,
            "loop": False,
        }
        for name, default in p.items():
            self.declare_parameter(name, default)
        g = lambda name: self.get_parameter(name).value  # noqa: E731

        source = str(g("source"))
        self.is_file = not source.isdigit()
        self.cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
        if not self.cap.isOpened():
            raise RuntimeError(f"could not open video source {source!r}")
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.fps = fps if 1.0 <= fps <= 120.0 else 30.0
        self.flip = bool(g("flip"))
        self.loop = bool(g("loop"))
        self.show = bool(g("show_window"))
        self.mirror = bool(g("mirror_to_sim"))
        self.estimator = ElbowAngleEstimator(
            g("model_path"), arm=g("arm"), min_visibility=float(g("min_visibility"))
        )
        self.writer = None
        if g("video_out"):
            w, h = int(self.cap.get(3)), int(self.cap.get(4))
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            self.writer = cv2.VideoWriter(g("video_out"), fourcc, self.fps, (w, h))

        self.frame_idx = 0
        self.t0 = time.monotonic()
        self.recording = False
        self.status = ""
        self.angle_pub = self.create_publisher(Float64, ANGLE_TOPIC, 10)
        self.elbow_pub = (
            self.create_publisher(Float64, ELBOW_CMD_TOPIC, 10) if self.mirror else None
        )
        self.create_subscription(Bool, RECORDING_TOPIC, self._on_recording, 10)
        self.create_subscription(String, STATUS_TOPIC, self._on_status, 10)
        self.timer = self.create_timer(1.0 / self.fps, self._tick)
        self.get_logger().info(
            f"source {source!r} at {self.fps:.0f} fps, arm {g('arm')}, "
            f"mirror_to_sim={self.mirror}, window={self.show}"
        )

    def _on_recording(self, msg: Bool) -> None:
        self.recording = msg.data

    def _on_status(self, msg: String) -> None:
        self.status = msg.data

    def _tick(self) -> None:
        ok, img = self.cap.read()
        if not ok:
            if self.is_file and self.loop:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return
            self.get_logger().info("end of video" if self.is_file else "camera stopped")
            raise StopRequested
        if self.flip:
            img = cv2.flip(img, 1)
        # Video files use their own clock so detection is independent of CPU speed.
        ts_ms = (
            self.frame_idx * 1000.0 / self.fps
            if self.is_file
            else (time.monotonic() - self.t0) * 1000.0
        )
        self.frame_idx += 1
        det = self.estimator.process(img, int(ts_ms))
        if det is not None:
            self.angle_pub.publish(Float64(data=det.angle_deg))
            if self.elbow_pub is not None:
                self.elbow_pub.publish(Float64(data=anatomical_to_sim_rad(det.angle_deg)))
        if self.show or self.writer is not None:
            draw_overlay(img, det, self.recording, self.status)
            if self.writer is not None:
                self.writer.write(img)
            if self.show:
                cv2.imshow("Captura - cotovelo (ESC para sair)", img)
                if cv2.waitKey(1) & 0xFF == 27:
                    raise StopRequested

    def shutdown(self) -> None:
        self.cap.release()
        if self.writer is not None:
            self.writer.release()
        self.estimator.close()
        if self.show:
            cv2.destroyAllWindows()


def main(args: list[str] | None = None) -> None:
    spin_node(ElbowAngleCameraNode, args)


if __name__ == "__main__":
    main()
