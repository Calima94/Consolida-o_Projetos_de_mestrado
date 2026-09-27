"""Emergency stop and published targets of the arm controller (runs where ROS 2 is installed)."""

import pytest

pytest.importorskip("std_srvs", reason="ROS 2 not available; runs inside the Docker image")

import rclpy  # noqa: E402
from sensor_msgs.msg import JointState  # noqa: E402
from std_msgs.msg import Float64  # noqa: E402
from std_srvs.srv import SetBool  # noqa: E402

from mestrado_emg.nodes.arm_controller import ArmControllerNode  # noqa: E402


@pytest.fixture
def node():
    rclpy.init()
    n = ArmControllerNode()
    n.sent, n.targets = {}, []
    for joint, pub in n.vel_pub.items():
        pub.publish = lambda msg, j=joint: n.sent.__setitem__(j, msg.data)
    n.target_pub.publish = n.targets.append
    yield n
    n.destroy_node()
    rclpy.shutdown()


def arm_at(node, elbow):
    node._on_joint_states(JointState(name=["shoulder_joint", "elbow_joint"], position=[0.0, elbow]))


def command(node, elbow):
    node._on_target("elbow_joint")(Float64(data=elbow))


def estop(node, on):
    return node._on_estop(SetBool.Request(data=on), SetBool.Response())


def test_targets_are_published_with_the_measured_joints(node):
    arm_at(node, 0.2)
    command(node, 1.5)
    node._step()
    assert node.sent["elbow_joint"] == pytest.approx(1.3)  # kp 1 * (1.5 - 0.2)
    msg = node.targets[-1]
    assert dict(zip(msg.name, msg.position, strict=True)) == {
        "shoulder_joint": 0.0,
        "elbow_joint": 1.5,
    }


def test_stop_zeroes_velocity_and_ignores_new_targets(node):
    arm_at(node, 0.2)
    command(node, 1.5)
    assert estop(node, True).success
    command(node, -1.0)
    node._step()
    assert node.sent["elbow_joint"] == 0.0
    assert node.target["elbow_joint"] == pytest.approx(0.2)


def test_release_holds_where_the_arm_is(node):
    arm_at(node, 0.2)
    command(node, 1.5)
    estop(node, True)
    arm_at(node, 0.3)  # still coasting when the stop arrived
    estop(node, False)
    node._step()
    assert node.sent["elbow_joint"] == pytest.approx(0.0)  # the old 1.5 is not resumed
    command(node, 1.0)
    node._step()
    assert node.sent["elbow_joint"] == pytest.approx(0.7)
