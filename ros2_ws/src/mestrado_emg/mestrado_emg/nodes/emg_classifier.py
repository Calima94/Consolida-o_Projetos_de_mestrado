"""Classify sEMG windows into elbow positions and command the simulated arm.

Merges the roles of three thesis nodes:

- ``capture_braco_pos`` (window of 50 samples -> feature pipeline -> class),
- ``myo_raw`` (class -> elbow angle via POSITIONS_TO_USE; IMU pitch relative to
  the first reading -> shoulder angle),
- ``arm_controller`` (P controller). The controller now lives inside Gazebo
  (JointPositionController with velocity commands), so this node only
  publishes position targets in radians.

Difference from the thesis: windows are consecutive and no samples are
dropped while a window is being classified (the thesis discarded samples that
arrived during classification).

Parameters
----------
model_path : str
    Bundle produced by ``train_legacy`` (required). Legacy ``*_teste.joblib``
    files are rejected: they must be retrained.
use_imu : bool
    Drive the shoulder from ``/emg/imu`` pitch, as in the thesis.
"""

from __future__ import annotations

import math

import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32MultiArray, Float64, Int32

from mestrado_emg.features import LegacyFeatureConfig, extract_features
from mestrado_emg.myo_protocol import quat_to_pitch
from mestrado_emg.nodes.common import (
    CLASS_TOPIC,
    ELBOW_CMD_TOPIC,
    EMG_TOPIC,
    IMU_TOPIC,
    SHOULDER_CMD_TOPIC,
    msg_to_samples,
    spin_node,
)
from mestrado_emg.training import load_bundle


class EmgClassifierNode(Node):
    def __init__(self) -> None:
        super().__init__("emg_classifier")
        self.declare_parameter("model_path", "")
        self.declare_parameter("use_imu", True)

        path = self.get_parameter("model_path").value
        if not path:
            raise ValueError("parameter model_path is required")
        bundle = load_bundle(path)
        self.model = bundle["model"]
        self.config = LegacyFeatureConfig.from_dict(bundle["feature_config"])
        self.angles_rad = [math.radians(a) for a in bundle["class_angles_deg"]]
        self.win = self.config.samples_per_window
        self.buffer = np.empty((0, self.config.n_channels))
        self.pitch_ref: float | None = None

        self.elbow_pub = self.create_publisher(Float64, ELBOW_CMD_TOPIC, 10)
        self.shoulder_pub = self.create_publisher(Float64, SHOULDER_CMD_TOPIC, 10)
        self.class_pub = self.create_publisher(Int32, CLASS_TOPIC, 10)
        self.create_subscription(Float32MultiArray, EMG_TOPIC, self._on_emg, 50)
        if self.get_parameter("use_imu").value:
            self.create_subscription(Imu, IMU_TOPIC, self._on_imu, 10)

        self.get_logger().info(
            f"model {bundle['classifier']} ({self.config.feature}, "
            f"{self.config.fs_hz:g} Hz, {self.win}-sample windows), "
            f"class angles {bundle['class_angles_deg']} deg"
        )

    def _on_emg(self, msg: Float32MultiArray) -> None:
        try:
            chunk = msg_to_samples(msg)
        except ValueError as exc:
            self.get_logger().error(f"bad /emg/raw message: {exc}")
            return
        if chunk.shape[1] != self.config.n_channels:
            self.get_logger().error(
                f"got {chunk.shape[1]} channels, model expects {self.config.n_channels}"
            )
            return
        # -> [n_buffered, n_channels]
        self.buffer = np.concatenate([self.buffer, chunk], axis=0)
        while len(self.buffer) >= self.win:
            window, self.buffer = self.buffer[: self.win], self.buffer[self.win :]
            feats = extract_features(window, self.config)  # -> [1, n_channels]
            cls = int(self.model.predict(feats)[0])
            self.class_pub.publish(Int32(data=cls))
            self.elbow_pub.publish(Float64(data=self.angles_rad[cls]))

    def _on_imu(self, msg: Imu) -> None:
        q = msg.orientation
        pitch = quat_to_pitch(q.w, q.x, q.y, q.z)
        if self.pitch_ref is None:
            self.pitch_ref = pitch
            self.get_logger().info(f"shoulder reference pitch {math.degrees(pitch):.1f} deg")
            return
        self.shoulder_pub.publish(Float64(data=pitch - self.pitch_ref))


def main(args: list[str] | None = None) -> None:
    spin_node(EmgClassifierNode, args)


if __name__ == "__main__":
    main()
