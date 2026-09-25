"""Gazebo Jetty with the thesis arm + ROS <-> Gazebo bridge.

    ros2 launch mestrado_bringup sim.launch.py            # with GUI
    ros2 launch mestrado_bringup sim.launch.py gui:=false # headless

Gazebo is started through ``gz_sim_group`` instead of
``ros_gz_sim/gz_sim.launch.py``. That launch file runs ``gz sim`` via
``/bin/sh -c`` (dash on Ubuntu), which does not forward SIGINT, and with the
GUI ``gz sim`` itself does not forward it to the server and GUI processes:
on shutdown they were left orphaned -- the "Gazebo keeps running after Stop"
problem the thesis worked around with ``killall gzserver gzclient``.
``gz_sim_group`` sends every stop signal to the whole Gazebo process group.
The model path comes from the mestrado_description environment hook.
"""

import os

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _gazebo(context):
    world = LaunchConfiguration("world").perform(context)
    gui = LaunchConfiguration("gui").perform(context).lower() in ("1", "true", "yes")
    mode = ["-r"] if gui else ["-r", "-s", "--headless-rendering"]
    wrapper = os.path.join(
        get_package_prefix("mestrado_bringup"), "lib", "mestrado_bringup", "gz_sim_group"
    )
    return [
        ExecuteProcess(
            cmd=[wrapper, "gz", "sim", *mode, world],
            name="gazebo",
            output="screen",
            shell=False,
            on_exit=Shutdown(reason="Gazebo exited"),
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
