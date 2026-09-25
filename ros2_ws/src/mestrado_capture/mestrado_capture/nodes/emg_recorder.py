"""Record sEMG labelled with elbow-angle categories (the thesis capture tool).

Replaces ``write_file`` + the PyQt form of Capture_EMG_Data. Listens to any
sEMG source on ``/emg/raw`` and to the measured angle on
``/capture/elbow_angle_deg``; the labelling rules are in
:mod:`mestrado_capture.categories`. When every category is complete the file
is saved and the node exits (the launch file then stops the whole capture, as
the thesis closed its window). Ctrl+C saves whatever was recorded so far.

Parameters (thesis GUI field in brackets)
----------
n_categories : int
    2 to 4 [comboBox: number of categories].
tolerance_deg : float
    Accepted +- deviation around each category [variation field].
samples_per_category : int
    Samples to collect per category [samples field].
category_angles_deg : list[float]
    Defaults to the thesis list [170, 90, 60, 45].
continuous : bool
    Also record samples outside the categories (label 0) with their angle.
max_angle_age_s : float
    An angle older than this is treated as unknown (the thesis reused the last
    one indefinitely).
fs_hz : float
    Sampling rate of the sEMG source, used to time-stamp each sample.
out_dir, prefix : str
    Output file ``<out_dir>/<prefix>_<date><n>.csv``.
"""

from __future__ import annotations

import time

from rclpy.node import Node
from std_msgs.msg import Bool, Float32MultiArray, Float64, String

from mestrado_capture.categories import LEGACY_CATEGORY_ANGLES_DEG, CategoryRecorder
from mestrado_capture.nodes.elbow_angle_camera import (
    ANGLE_TOPIC,
    RECORDING_TOPIC,
    STATUS_TOPIC,
    StopRequested,
)
from mestrado_emg.nodes.common import EMG_TOPIC, msg_to_samples, spin_node


class EmgRecorderNode(Node):
    def __init__(self) -> None:
        super().__init__("emg_recorder")
        p = {
            "n_categories": 2,
            "tolerance_deg": 10.0,
            "samples_per_category": 1000,
            "category_angles_deg": list(LEGACY_CATEGORY_ANGLES_DEG),
            "continuous": False,
            "max_angle_age_s": 0.5,
            "fs_hz": 200.0,
            "n_channels": 8,
            "out_dir": "/data",
            "prefix": "captura",
        }
        for name, default in p.items():
            self.declare_parameter(name, default)
        g = lambda name: self.get_parameter(name).value  # noqa: E731

        self.rec = CategoryRecorder(
            n_categories=int(g("n_categories")),
            tolerance_deg=float(g("tolerance_deg")),
            samples_per_category=int(g("samples_per_category")),
            category_angles_deg=tuple(float(a) for a in g("category_angles_deg")),
            n_channels=int(g("n_channels")),
            fs_hz=float(g("fs_hz")),
            continuous=bool(g("continuous")),
        )
        self.max_age = float(g("max_angle_age_s"))
        self.out_dir, self.prefix = g("out_dir"), g("prefix")
        self.saved = None
        self.t0 = time.monotonic()
        self.angle: float | None = None
        self.angle_t = -1e9
        self.was_recording = False

        self.recording_pub = self.create_publisher(Bool, RECORDING_TOPIC, 10)
        self.status_pub = self.create_publisher(String, STATUS_TOPIC, 10)
        self.create_subscription(Float64, ANGLE_TOPIC, self._on_angle, 10)
        self.create_subscription(Float32MultiArray, EMG_TOPIC, self._on_emg, 50)
        self.create_timer(1.0, self._report)
        self.get_logger().info(
            f"categorias {self.rec.category_angles_deg} graus +- {self.rec.tolerance_deg:g}, "
            f"{self.rec.samples_per_category} amostras cada, contínuo={self.rec.continuous}"
        )

    def _on_angle(self, msg: Float64) -> None:
        self.angle, self.angle_t = msg.data, time.monotonic()

    def _on_emg(self, msg: Float32MultiArray) -> None:
        now = time.monotonic()
        angle = self.angle if now - self.angle_t <= self.max_age else None
        recording = self.rec.add(msg_to_samples(msg), angle, t_end=now - self.t0)
        if recording != self.was_recording:
            self.recording_pub.publish(Bool(data=recording))
            self.was_recording = recording
        if self.rec.done:
            self._save()
            self.get_logger().info("todas as categorias completas")
            raise StopRequested

    def _report(self) -> None:
        text = self.rec.status_text()
        self.status_pub.publish(String(data=text))
        self.get_logger().info(text)

    def _save(self) -> None:
        if self.saved is None and self.rec.n_rows:
            self.saved = self.rec.save(self.out_dir, self.prefix)
            self.get_logger().info(f"salvo {self.saved} ({self.rec.n_rows} amostras)")

    def shutdown(self) -> None:
        self._save()


def main(args: list[str] | None = None) -> None:
    spin_node(EmgRecorderNode, args)


if __name__ == "__main__":
    main()
