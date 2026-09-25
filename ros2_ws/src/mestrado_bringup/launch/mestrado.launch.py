"""Full thesis chain: sEMG source -> classifier -> Gazebo arm.

Replaces my_arm_definitive.launch.py + the PyQt launcher (main.py).

    # no hardware: replay a recorded CSV
    ros2 launch mestrado_bringup mestrado.launch.py source:=replay \\
        csv_path:=/data/6_10_20220.csv model_path:=/models/<bundle>.joblib

    # with the Myo dongle
    ros2 launch mestrado_bringup mestrado.launch.py source:=myo model_path:=...
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def _source_is(name):
    return IfCondition(PythonExpression(["'", LaunchConfiguration("source"), f"' == '{name}'"]))


def generate_launch_description():
    bringup = get_package_share_directory("mestrado_bringup")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "source", default_value="replay", description="replay | myo | none"
            ),
            DeclareLaunchArgument(
                "csv_path", default_value="", description="CSV for source:=replay"
            ),
            DeclareLaunchArgument("model_path", description="bundle from train_legacy"),
            DeclareLaunchArgument(
                "tty", default_value="", description="Myo dongle (empty = autodetect)"
            ),
            DeclareLaunchArgument("gui", default_value="true"),
            DeclareLaunchArgument("loop", default_value="true", description="loop the replay"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(os.path.join(bringup, "launch", "sim.launch.py")),
                launch_arguments={"gui": LaunchConfiguration("gui")}.items(),
            ),
            Node(
                package="mestrado_emg",
                executable="emg_replay",
                parameters=[
                    {
                        "csv_path": LaunchConfiguration("csv_path"),
                        "loop": LaunchConfiguration("loop"),
                    }
                ],
                condition=_source_is("replay"),
                output="screen",
            ),
            Node(
                package="mestrado_emg",
                executable="myo_driver",
                parameters=[{"tty": LaunchConfiguration("tty")}],
                condition=_source_is("myo"),
                output="screen",
            ),
            Node(
                package="mestrado_emg",
                executable="emg_classifier",
                parameters=[{"model_path": LaunchConfiguration("model_path")}],
                output="screen",
            ),
            Node(package="mestrado_emg", executable="angle_monitor", output="screen"),
        ]
    )
