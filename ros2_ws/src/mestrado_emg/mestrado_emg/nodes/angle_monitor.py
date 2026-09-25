"""Print target vs. actual shoulder/elbow angles in degrees.

Text replacement for the thesis PyQt panel (``show_angles.ui``). For plots use
``rqt`` or ``ros2 topic echo /joint_states``.
"""

from __future__ import annotations

import math

from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64

from mestrado_emg.nodes.common import (
    ELBOW_CMD_TOPIC,
    JOINT_STATES_TOPIC,
    SHOULDER_CMD_TOPIC,
    spin_node,
)


class AngleMonitorNode(Node):
    def __init__(self) -> None:
        super().__init__("angle_monitor")
        self.declare_parameter("period_s", 1.0)
        self.target = {"shoulder_joint": 0.0, "elbow_joint": 0.0}
        self.actual = {"shoulder_joint": math.nan, "elbow_joint": math.nan}
        self.create_subscription(JointState, JOINT_STATES_TOPIC, self._on_js, 10)
        self.create_subscription(Float64, SHOULDER_CMD_TOPIC, self._target("shoulder_joint"), 10)
        self.create_subscription(Float64, ELBOW_CMD_TOPIC, self._target("elbow_joint"), 10)
        self.create_timer(float(self.get_parameter("period_s").value), self._report)

    def _target(self, joint: str):
        def cb(msg: Float64) -> None:
            self.target[joint] = msg.data

        return cb

    def _on_js(self, msg: JointState) -> None:
        for name, pos in zip(msg.name, msg.position, strict=False):
            if name in self.actual:
                self.actual[name] = pos

    def _report(self) -> None:
        d = math.degrees
        t, a = self.target, self.actual
        self.get_logger().info(
            f"ombro alvo {d(t['shoulder_joint']):6.1f} / atual {d(a['shoulder_joint']):6.1f} deg | "
            f"cotovelo alvo {d(t['elbow_joint']):6.1f} / atual {d(a['elbow_joint']):6.1f} deg"
        )


def main(args: list[str] | None = None) -> None:
    spin_node(AngleMonitorNode, args)


if __name__ == "__main__":
    main()
