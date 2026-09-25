"""Thesis capture tool: webcam elbow angle + sEMG recorded by angle category.

Replaces Capture_EMG_Data (PyQt form + OpenCV window). The GUI fields are
launch arguments; the OpenCV window shows the arm in orange while recording.
The capture ends by itself when every category is complete (or with ESC /
Ctrl+C, which save what was recorded so far).

    # with the Myo
    ros2 launch mestrado_bringup captura.launch.py emg:=myo n_categories:=2 \\
        tolerance_deg:=10 samples_per_category:=1500

    # dry run without hardware: thesis video + replayed sEMG
    ros2 launch mestrado_bringup captura.launch.py emg:=replay \\
        camera:=/data/test_2_05.avi flip:=false csv_path:=/data/6_10_20220.csv
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _emg_is(name):
    return IfCondition(PythonExpression(["'", LaunchConfiguration("emg"), f"' == '{name}'"]))


def _arg(name):
    return LaunchConfiguration(name)


def generate_launch_description():
    args = [
        ("emg", "myo", "sEMG source: myo | replay | none (another driver already running)"),
        ("camera", "0", "camera index, video file or stream URL"),
        ("arm", "right", "right | left"),
        ("flip", "true", "mirror the image (false for videos saved by the thesis tool)"),
        ("n_categories", "2", "2 to 4 (thesis: 170, 90, 60, 45 deg)"),
        ("tolerance_deg", "10.0", "accepted +- deviation per category"),
        ("samples_per_category", "1000", "samples per category"),
        ("continuous", "false", "also record samples outside the categories (label 0)"),
        ("out_dir", "/data", "where the CSV is written"),
        ("csv_path", "", "sEMG recording for emg:=replay"),
        ("tty", "auto", "Myo dongle (auto = autodetect)"),
        ("show_window", "true", "show the OpenCV window"),
        ("video_out", "", "save the annotated video (like the thesis Videos/*.avi)"),
    ]
    return LaunchDescription(
        [DeclareLaunchArgument(n, default_value=d, description=h) for n, d, h in args]
        + [
            Node(
                package="mestrado_emg",
                executable="myo_driver",
                parameters=[{"tty": _arg("tty")}],
                condition=_emg_is("myo"),
                output="screen",
            ),
            Node(
                package="mestrado_emg",
                executable="emg_replay",
                parameters=[{"csv_path": _arg("csv_path"), "loop": True}],
                condition=_emg_is("replay"),
                output="screen",
            ),
            Node(
                package="mestrado_capture",
                executable="elbow_angle_camera",
                parameters=[
                    {
                        "source": ParameterValue(_arg("camera"), value_type=str),
                        "arm": _arg("arm"),
                        "flip": ParameterValue(_arg("flip"), value_type=bool),
                        "show_window": ParameterValue(_arg("show_window"), value_type=bool),
                        "video_out": ParameterValue(_arg("video_out"), value_type=str),
                        "loop": True,
                    }
                ],
                output="screen",
                on_exit=Shutdown(reason="camera closed"),
            ),
            Node(
                package="mestrado_capture",
                executable="emg_recorder",
                parameters=[
                    {
                        "n_categories": ParameterValue(_arg("n_categories"), value_type=int),
                        "tolerance_deg": ParameterValue(_arg("tolerance_deg"), value_type=float),
                        "samples_per_category": ParameterValue(
                            _arg("samples_per_category"), value_type=int
                        ),
                        "continuous": ParameterValue(_arg("continuous"), value_type=bool),
                        "out_dir": _arg("out_dir"),
                    }
                ],
                output="screen",
                on_exit=Shutdown(reason="capture finished"),
            ),
        ]
    )
