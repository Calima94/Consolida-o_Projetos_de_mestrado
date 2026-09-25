#!/usr/bin/env python3
"""Mirror-mode check: the Gazebo elbow must follow the elbow seen by the camera.

With the thesis video (arm extended ~169 deg, then bent ~93 deg) the
simulated elbow has to visit both ~10 deg and ~87 deg. Exit code 0 on success.
"""

import argparse
import math
import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=30.0)
    args = ap.parse_args()
    rclpy.init()
    node = Node("mirror_checker")
    angles, elbow = [], []
    node.create_subscription(
        Float64, "/capture/elbow_angle_deg", lambda m: angles.append(m.data), 10
    )

    def on_js(msg):
        if "elbow_joint" in msg.name:
            elbow.append(math.degrees(msg.position[msg.name.index("elbow_joint")]))

    node.create_subscription(JointState, "/joint_states", on_js, 10)
    end = time.monotonic() + args.duration
    while time.monotonic() < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    lo = min(elbow) if elbow else math.nan
    hi = max(elbow) if elbow else math.nan
    print(f"camera_angles={len(angles)} elbow_range_deg=[{lo:.1f}, {hi:.1f}]")
    ok = len(angles) > 20 and hi > 70.0 and lo < 25.0
    print("PASS" if ok else "FAIL")
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
