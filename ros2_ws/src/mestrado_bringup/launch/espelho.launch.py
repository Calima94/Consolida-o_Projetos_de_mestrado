"""Mirror mode: the Gazebo arm copies your elbow, seen by the webcam.

No sEMG needed. The camera node publishes the simulator elbow target
directly (180 deg - measured angle, clipped to [0, 180] deg).

    ros2 launch mestrado_bringup espelho.launch.py                 # webcam 0
    ros2 launch mestrado_bringup espelho.launch.py camera:=/data/test_2_05.avi flip:=false
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
            DeclareLaunchArgument("camera", default_value="0"),
            DeclareLaunchArgument("arm", default_value="right"),
            DeclareLaunchArgument(
                "flip",
                default_value="true",
                description="mirror the image (true for a webcam; false for videos saved "
                "by the thesis tool, which are already mirrored)",
            ),
            DeclareLaunchArgument("gui", default_value="true", description="Gazebo window"),
            DeclareLaunchArgument("show_window", default_value="true", description="camera window"),
            DeclareLaunchArgument("loop", default_value="true", description="loop a video file"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(os.path.join(bringup, "launch", "sim.launch.py")),
                launch_arguments={"gui": cfg("gui")}.items(),
            ),
            Node(
                package="mestrado_capture",
                executable="elbow_angle_camera",
                parameters=[
                    {
                        "source": ParameterValue(cfg("camera"), value_type=str),
                        "arm": cfg("arm"),
                        "flip": ParameterValue(cfg("flip"), value_type=bool),
                        "show_window": ParameterValue(cfg("show_window"), value_type=bool),
                        "loop": ParameterValue(cfg("loop"), value_type=bool),
                        "mirror_to_sim": True,
                    }
                ],
                output="screen",
            ),
            Node(package="mestrado_emg", executable="angle_monitor", output="screen"),
        ]
    )
