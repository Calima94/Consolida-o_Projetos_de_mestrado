"""Gazebo Jetty with the thesis arm + ROS <-> Gazebo bridge.

    ros2 launch mestrado_bringup sim.launch.py            # with GUI
    ros2 launch mestrado_bringup sim.launch.py gui:=false # headless
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _gazebo(context):
    world = LaunchConfiguration("world").perform(context)
    gui = LaunchConfiguration("gui").perform(context).lower() in ("1", "true", "yes")
    gz_args = f"-r {world}" if gui else f"-r -s --headless-rendering {world}"
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(get_package_share_directory("ros_gz_sim"), "launch", "gz_sim.launch.py")
            ),
            launch_arguments={"gz_args": gz_args, "on_exit_shutdown": "true"}.items(),
        )
    ]


def generate_launch_description():
    description = get_package_share_directory("mestrado_description")
    bringup = get_package_share_directory("mestrado_bringup")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "world", default_value=os.path.join(description, "worlds", "braco.sdf")
            ),
            DeclareLaunchArgument("gui", default_value="true", description="open the Gazebo GUI"),
            OpaqueFunction(function=_gazebo),
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="ros_gz_bridge",
                parameters=[{"config_file": os.path.join(bringup, "config", "bridge.yaml")}],
                output="screen",
            ),
        ]
    )
