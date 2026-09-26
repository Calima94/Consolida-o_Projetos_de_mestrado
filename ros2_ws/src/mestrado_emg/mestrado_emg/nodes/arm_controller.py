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

Added for the browser interface (not in the thesis):

- ``/arm/joint_targets`` (``sensor_msgs/JointState``): the targets the loop is
  actually tracking, so that command and reality can be compared from one
  topic against ``/joint_states``;
- ``/arm/estop`` (``std_srvs/SetBool``): emergency stop. ``true`` sends zero
  velocity to every joint and ignores ``cmd_pos`` until ``false``. Both hold
  the arm where it is: on release the targets are the current positions, so
  the arm does not resume a target sent before the stop. The state goes out on
  ``/arm/estop_active`` (``std_msgs/Bool``, transient local) on every change
  and once a second, so a page opened later sees it and can tell that the
  controller is alive. The stop lives here, on the always-on side, and not in
  the page.

The control law itself (no ROS) is :func:`mestrado_emg.control.p_velocity`.
"""

from __future__ import annotations

from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float64
from std_srvs.srv import SetBool

from mestrado_emg.control import p_velocity
from mestrado_emg.nodes.common import JOINT_STATES_TOPIC, spin_node

# joint name -> (topic prefix, thesis kp)
JOINTS = {
    "shoulder_joint": ("/arm/shoulder", 1.0),
    "elbow_joint": ("/arm/elbow", 1.0),
    "gripper_left_joint": ("/arm/gripper_left", 10.0),
    "gripper_right_joint": ("/arm/gripper_right", 10.0),
}
TARGETS_TOPIC = "/arm/joint_targets"
ESTOP_SERVICE = "/arm/estop"
ESTOP_STATE_TOPIC = "/arm/estop_active"


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
        self.target_pub = self.create_publisher(JointState, TARGETS_TOPIC, 10)
        self.stopped = False
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.estop_pub = self.create_publisher(Bool, ESTOP_STATE_TOPIC, latched)
        self._publish_estop()
        self.create_service(SetBool, ESTOP_SERVICE, self._on_estop)
        self.create_timer(1.0, self._publish_estop)
        self.create_timer(1.0 / float(self.get_parameter("rate_hz").value), self._step)
        self.get_logger().info(f"kp {self.kp}")

    def _on_target(self, joint: str):
        def cb(msg: Float64) -> None:
            if self.stopped:
                self.get_logger().warning(
                    "parada de emergência ativa: cmd_pos ignorado", throttle_duration_sec=2.0
                )
                return
            self.target[joint] = msg.data

        return cb

    def _on_joint_states(self, msg: JointState) -> None:
        for name, pos in zip(msg.name, msg.position, strict=False):
            if name in self.kp:
                self.position[name] = pos
                self.target.setdefault(name, pos)  # hold the initial pose

    def _on_estop(self, request: SetBool.Request, response: SetBool.Response):
        self.stopped = bool(request.data)
        self.target.update(self.position)  # engage or release: hold where it is
        self._publish_estop()
        response.success = True
        response.message = "parado" if self.stopped else "liberado"
        self.get_logger().warning(f"parada de emergência: {response.message}")
        return response

    def _publish_estop(self) -> None:
        self.estop_pub.publish(Bool(data=self.stopped))

    def _step(self) -> None:
        for joint, pos in self.position.items():
            v = p_velocity(self.target[joint], pos, self.kp[joint], self.v_max)
            self.vel_pub[joint].publish(Float64(data=0.0 if self.stopped else v))
        if self.target:
            msg = JointState(name=list(self.target), position=list(self.target.values()))
            msg.header.stamp = self.get_clock().now().to_msg()
            self.target_pub.publish(msg)


def main(args: list[str] | None = None) -> None:
    spin_node(ArmControllerNode, args)


if __name__ == "__main__":
    main()
