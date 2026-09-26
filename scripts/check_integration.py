#!/usr/bin/env python3
"""End-to-end check: replayed sEMG -> classifier -> Gazebo arm.

Run inside the container while ``mestrado.launch.py source:=replay`` is up.
Listens for ``--duration`` seconds and verifies that

1. the classifier publishes predictions and they mostly agree with the
   recorded labels (plumbing check, not an evaluation: the replayed file is
   the training file);
2. the simulated elbow actually moves between the class targets
   (0 deg and 90 deg for the thesis data).

Exit code 0 on success.
"""

import argparse
import math
import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Int32


class Checker(Node):
    def __init__(self):
        super().__init__("integration_checker")
        self.label = None
        self.pairs = []
        self.elbow = []
        self.create_subscription(Int32, "/emg/label", self._label, 10)
        self.create_subscription(Int32, "/emg/predicted_class", self._pred, 10)
        self.create_subscription(JointState, "/joint_states", self._js, 10)

    def _label(self, msg):
        self.label = msg.data

    def _pred(self, msg):
        if self.label is not None:
            self.pairs.append((msg.data, self.label))

    def _js(self, msg):
        if "elbow_joint" in msg.name:
            self.elbow.append(msg.position[msg.name.index("elbow_joint")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=25.0)
    ap.add_argument("--min-agreement", type=float, default=0.8)
    args = ap.parse_args()

    rclpy.init()
    node = Checker()
    end = time.monotonic() + args.duration
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)

    n = len(node.pairs)
    agree = sum(p == lbl for p, lbl in node.pairs) / n if n else 0.0
    lo = math.degrees(min(node.elbow)) if node.elbow else math.nan
    hi = math.degrees(max(node.elbow)) if node.elbow else math.nan
    print(
        f"predictions={n} agreement={agree:.3f} elbow_range_deg=[{lo:.1f}, {hi:.1f}] "
        f"joint_state_msgs={len(node.elbow)}"
    )
    ok = n > 0 and agree >= args.min_agreement and lo < 10.0 and hi > 70.0
    print("PASS" if ok else "FAIL")
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
