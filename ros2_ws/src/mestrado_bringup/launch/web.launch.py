"""Browser interface: rosbridge (ROS 2 over websocket + JSON) and the page in web/.

    ros2 launch mestrado_bringup web.launch.py            # page :8080, websocket :9090
    ros2 launch mestrado_bringup web.launch.py http_port:=8000 ws_port:=9000

Independent of the simulation: the same page drives Gazebo (sim.launch.py) or,
later, the physical arm, because both speak ROS 2. The page connects to the
websocket on the host it was loaded from, port 9090 (``?ws=`` overrides it).
The static files are served as they are on disk, so editing web/ needs no
rebuild -- only a reload in the browser.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    GroupAction,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    rosbridge = get_package_share_directory("rosbridge_server")
    return LaunchDescription(
        [
            DeclareLaunchArgument("http_port", default_value="8080", description="page"),
            DeclareLaunchArgument("ws_port", default_value="9090", description="rosbridge"),
            DeclareLaunchArgument(
                "web_dir", default_value="/web", description="directory with index.html"
            ),
            # Scoped: arguments given to an include otherwise leak into this
            # file (rosbridge's `port` overwrote ours; measured).
            GroupAction(
                [
                    IncludeLaunchDescription(
                        AnyLaunchDescriptionSource(
                            os.path.join(rosbridge, "launch", "rosbridge_websocket_launch.xml")
                        ),
                        launch_arguments={"port": LaunchConfiguration("ws_port")}.items(),
                    )
                ],
                scoped=True,
            ),
            ExecuteProcess(
                cmd=[
                    "python3",
                    "-m",
                    "http.server",
                    LaunchConfiguration("http_port"),
                    "--directory",
                    LaunchConfiguration("web_dir"),
                ],
                name="web_page",
                output="screen",
            ),
        ]
    )
