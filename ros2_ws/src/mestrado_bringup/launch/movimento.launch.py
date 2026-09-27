"""A real elbow movement on the simulated arm (Reach&Grasp, Vicon).

The Gazebo arm follows the elbow angle recorded in a Reach&Grasp trial. No
sEMG and no model: it shows the digital twin with the target that a regression
model would have to predict (docs/DECISOES.md, D27). Download the trials first
with scripts/fetch_reach_grasp.py.

    ros2 launch mestrado_bringup movimento.launch.py                     # sub 1, ReaCyl
    ros2 launch mestrado_bringup movimento.launch.py subject:=4 task:=EatFruit speed:=0.5
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    bringup = get_package_share_directory("mestrado_bringup")
    cfg = LaunchConfiguration
    return LaunchDescription(
        [
            DeclareLaunchArgument("root", default_value="/data/reach_grasp"),
            DeclareLaunchArgument("subject", default_value="1", description="1 to 10"),
            DeclareLaunchArgument(
                "task",
                default_value="ReaCyl",
                description="FroRea, ReaCyl, ReaSph, Pour, Screw or EatFruit move the elbow",
            ),
            DeclareLaunchArgument("speed", default_value="1.0", description="1.0 = real time"),
            DeclareLaunchArgument("loop", default_value="true"),
            DeclareLaunchArgument("gui", default_value="true", description="Gazebo window"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(os.path.join(bringup, "launch", "sim.launch.py")),
                launch_arguments={"gui": cfg("gui")}.items(),
            ),
            Node(
                package="mestrado_emg",
                executable="movement_replay",
                parameters=[
                    {
                        "root": ParameterValue(cfg("root"), value_type=str),
                        "subject": ParameterValue(cfg("subject"), value_type=str),
                        "task": ParameterValue(cfg("task"), value_type=str),
                        "speed": ParameterValue(cfg("speed"), value_type=float),
                        "loop": ParameterValue(cfg("loop"), value_type=bool),
                    }
                ],
                output="screen",
            ),
            Node(package="mestrado_emg", executable="angle_monitor", output="screen"),
        ]
    )
