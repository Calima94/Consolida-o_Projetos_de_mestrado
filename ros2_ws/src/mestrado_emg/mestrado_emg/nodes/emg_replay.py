"""Replay a recorded Capture_EMG_Data CSV as if it were a live sensor.

Lets the whole chain (sEMG -> classifier -> Gazebo arm) run without any
hardware. Samples are published in batches on ``/emg/raw`` at real-time pace,
and the recorded category of the last sample of each batch goes to
``/emg/label`` (class index, sorted by label) for checking the classifier.

Replaying the same file a model was trained on only demonstrates the
plumbing; it is **not** an evaluation (see training.py for the splits).

Parameters
----------
csv_path : str
    Recording to replay (required).
fs_hz : float
    Sampling rate of the recording (200.0 for the thesis Myo data).
batch_size : int
    Samples per message.
loop : bool
    Restart from the beginning at the end of the file.
"""

from __future__ import annotations

import numpy as np
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, Int32

from mestrado_emg.nodes.common import EMG_TOPIC, LABEL_TOPIC, samples_to_msg, spin_node
from mestrado_emg.training import load_legacy_csv


class EmgReplayNode(Node):
    def __init__(self) -> None:
        super().__init__("emg_replay")
        self.declare_parameter("csv_path", "")
        self.declare_parameter("fs_hz", 200.0)
        self.declare_parameter("batch_size", 10)
        self.declare_parameter("loop", True)

        path = self.get_parameter("csv_path").value
        if not path:
            raise ValueError("parameter csv_path is required")
        self.samples, labels = load_legacy_csv(path)
        classes = sorted(np.unique(labels).tolist())
        self.label_idx = np.searchsorted(classes, labels)
        self.batch = int(self.get_parameter("batch_size").value)
        self.loop = bool(self.get_parameter("loop").value)
        self.pos = 0

        self.emg_pub = self.create_publisher(Float32MultiArray, EMG_TOPIC, 50)
        self.label_pub = self.create_publisher(Int32, LABEL_TOPIC, 10)
        period = self.batch / float(self.get_parameter("fs_hz").value)
        self.timer = self.create_timer(period, self._tick)
        self.get_logger().info(
            f"replaying {path}: {len(self.samples)} samples, {len(classes)} classes, "
            f"{self.batch} samples every {period * 1000:.0f} ms"
        )

    def _tick(self) -> None:
        if self.pos + self.batch > len(self.samples):
            if not self.loop:
                self.get_logger().info("end of recording")
                self.timer.cancel()
                return
            self.pos = 0
        chunk = self.samples[self.pos : self.pos + self.batch]
        self.emg_pub.publish(samples_to_msg(chunk))
        self.label_pub.publish(Int32(data=int(self.label_idx[self.pos + self.batch - 1])))
        self.pos += self.batch


def main(args: list[str] | None = None) -> None:
    spin_node(EmgReplayNode, args)


if __name__ == "__main__":
    main()
