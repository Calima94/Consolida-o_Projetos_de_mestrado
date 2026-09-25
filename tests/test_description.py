"""Consistency between the SDF model, the bridge config and the node topics."""

import ast
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

SRC = Path(__file__).resolve().parents[1] / "ros2_ws" / "src"
MODEL = SRC / "mestrado_description" / "models" / "braco_antebraco_garra" / "model.sdf"
BRIDGE = SRC / "mestrado_bringup" / "config" / "bridge.yaml"
COMMON = SRC / "mestrado_emg" / "mestrado_emg" / "nodes" / "common.py"

# Values from my_arm_def/src/my_arm_def_cpp_pkg/models/braco_antebraco_garra.sdf
LEGACY_MASSES = {
    "shoulder_link": 0.175,  # link_0
    "upper_arm_link": 1.924,  # link_1
    "elbow_link": 0.175,  # link_2
    "forearm_link": 1.184,  # link_3
    "gripper_base_link": 0.15,  # link_4
    "finger_left_base_link": 0.05,  # link_5
    "finger_right_base_link": 0.05,  # link_6
    "finger_left_link": 0.125,  # link_7
    "finger_right_link": 0.125,  # link_8
}


@pytest.fixture(scope="module")
def model():
    return ET.parse(MODEL).getroot().find("model")


@pytest.fixture(scope="module")
def bridge():
    return yaml.safe_load(BRIDGE.read_text())


def _common_constants():
    tree = ast.parse(COMMON.read_text())
    return {
        t.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        for t in node.targets
    }


def test_masses_are_the_thesis_ones(model):
    masses = {ln.get("name"): float(ln.findtext("inertial/mass")) for ln in model.findall("link")}
    assert masses == LEGACY_MASSES


def test_joints_match_thesis_kinematics(model):
    joints = {j.get("name"): j for j in model.findall("joint")}
    assert joints["shoulder_joint"].findtext("parent") == "world"
    for name in ("shoulder_joint", "elbow_joint"):
        assert joints[name].get("type") == "revolute"
        assert joints[name].findtext("axis/xyz") == "1 0 0"
        assert float(joints[name].findtext("axis/limit/upper")) == 3.15
    for name in ("gripper_left_joint", "gripper_right_joint"):
        assert joints[name].get("type") == "prismatic"
        assert float(joints[name].findtext("axis/limit/upper")) == 0.04


def test_velocity_controlled_joints_have_effort_limits(model):
    """Gazebo only enforces position limits under velocity control with an effort limit."""
    for j in model.findall("joint"):
        if j.get("type") != "fixed":
            assert float(j.findtext("axis/limit/effort")) > 0


def test_controller_topics_are_bridged(model, bridge):
    plugin_topics = {
        p.findtext("topic")
        for p in model.findall("plugin")
        if p.get("name") == "gz::sim::systems::JointPositionController"
    }
    ros_to_gz = {b["gz_topic_name"] for b in bridge if b["direction"] == "ROS_TO_GZ"}
    assert plugin_topics == ros_to_gz


def test_joint_state_topic_is_bridged(model, bridge):
    (jsp,) = [p for p in model.findall("plugin") if p.get("name").endswith("JointStatePublisher")]
    gz_to_ros = {b["gz_topic_name"]: b["ros_topic_name"] for b in bridge}
    assert gz_to_ros[jsp.findtext("topic")] == _common_constants()["JOINT_STATES_TOPIC"]


def test_classifier_publishes_on_bridged_topics(bridge):
    ros_topics = {b["ros_topic_name"] for b in bridge}
    consts = _common_constants()
    assert consts["SHOULDER_CMD_TOPIC"] in ros_topics
    assert consts["ELBOW_CMD_TOPIC"] in ros_topics
