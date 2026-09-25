"""Joint position controller of the thesis arm (port of arm_controller.py).

The thesis node received target positions (services ``pos_reach*``), read the
joint positions published by its Gazebo plugin and sent back a velocity,
``v = kp * (target - position)``, which the plugin applied with
``joint->SetVelocity()``. Same loop here: targets on ``/arm/<joint>/cmd_pos``
(radians), measured positions on ``/joint_states``, velocities on
``/arm/<joint>/cmd_vel`` for the Gazebo ``JointController`` systems.

The thesis gains are the defaults (params.yaml: kp 1 for shoulder and elbow,
10 for the gripper fingers). Dropped: the extra term
``vel_atual * kd * error`` (a velocity-times-error product, not a derivative
term) and the special case in which the shoulder published the raw error.
Until a target arrives each joint is held where it is.

The control law itself (no ROS) is :func:`mestrado_emg.control.p_velocity`.
"""

from __future__ import annotations

from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64

from mestrado_emg.control import p_velocity
from mestrado_emg.nodes.common import JOINT_STATES_TOPIC, spin_node

# joint name -> (topic prefix, thesis kp)
JOINTS = {
    "shoulder_joint": ("/arm/shoulder", 1.0),
    "elbow_joint": ("/arm/elbow", 1.0),
    "gripper_left_joint": ("/arm/gripper_left", 10.0),
    "gripper_right_joint": ("/arm/gripper_right", 10.0),
}


class ArmControllerNode(Node):
    def __init__(self) -> None:
        super().__init__("arm_controller")
        self.declare_parameter("rate_hz", 100.0)
        self.declare_parameter("max_velocity", 0.0)  # rad/s (m/s for the gripper); 0 = no clip
        self.kp, self.target, self.position, self.vel_pub = {}, {}, {}, {}
        for joint, (prefix, kp) in JOINTS.items():
            self.declare_parameter(f"kp.{joint}", kp)
            self.kp[joint] = float(self.get_parameter(f"kp.{joint}").value)
            self.vel_pub[joint] = self.create_publisher(Float64, f"{prefix}/cmd_vel", 10)
            self.create_subscription(Float64, f"{prefix}/cmd_pos", self._on_target(joint), 10)
        self.v_max = float(self.get_parameter("max_velocity").value)
        self.create_subscription(JointState, JOINT_STATES_TOPIC, self._on_joint_states, 10)
        self.create_timer(1.0 / float(self.get_parameter("rate_hz").value), self._step)
        self.get_logger().info(f"kp {self.kp}")

    def _on_target(self, joint: str):
        def cb(msg: Float64) -> None:
            self.target[joint] = msg.data

        return cb

    def _on_joint_states(self, msg: JointState) -> None:
        for name, pos in zip(msg.name, msg.position, strict=False):
            if name in self.kp:
                self.position[name] = pos
                self.target.setdefault(name, pos)  # hold the initial pose

    def _step(self) -> None:
        for joint, pos in self.position.items():
            v = p_velocity(self.target[joint], pos, self.kp[joint], self.v_max)
            self.vel_pub[joint].publish(Float64(data=v))


def main(args: list[str] | None = None) -> None:
    spin_node(ArmControllerNode, args)


if __name__ == "__main__":
    main()
