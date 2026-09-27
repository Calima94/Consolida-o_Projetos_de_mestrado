"""Replay a real elbow movement (Reach&Grasp, Vicon) on the simulated arm.

Reads one trial with :mod:`mestrado_emg.reach_grasp` and publishes the elbow
angle as the simulator target on ``/arm/elbow/cmd_pos`` (radians), at the pace
of the recording. The ``arm_controller`` then drives the Gazebo elbow as it
does for the classifier and the camera. No model is involved: this checks the
digital twin end to end with the target a regression model would have to
predict (``docs/DECISOES.md``, D27).

The recorded angle in degrees also goes to ``/reach_grasp/elbow_deg``, so a
checker or the browser page can compare it with ``/joint_states``.

Parameters
----------
root : str
    Folder written by ``scripts/fetch_reach_grasp.py`` (``/data/reach_grasp``).
subject : str
    Subject number, ``"1"`` to ``"10"`` (``"01"`` also accepted).
task : str
    Task abbreviation, e.g. ``ReaCyl`` (see ``reach_grasp.TASKS``).
speed : float
    Playback speed (1.0 = real time).
loop : bool
    Start over at the end of the recording.
"""

from __future__ import annotations

import time

from rclpy.node import Node
from std_msgs.msg import Float64

from mestrado_emg.nodes.common import ELBOW_CMD_TOPIC, spin_node
from mestrado_emg.reach_grasp import (
    ELBOW_TASKS,
    describe,
    elbow_target_rad,
    is_elbow_task,
    load_vicon,
)

RECORDED_ELBOW_TOPIC = "/reach_grasp/elbow_deg"


class MovementReplayNode(Node):
    def __init__(self) -> None:
        super().__init__("movement_replay")
        self.declare_parameter("root", "/data/reach_grasp")
        self.declare_parameter("subject", "1")
        self.declare_parameter("task", "ReaCyl")
        self.declare_parameter("speed", 1.0)
        self.declare_parameter("loop", True)

        subject = str(self.get_parameter("subject").value)
        task = str(self.get_parameter("task").value)
        self.speed = float(self.get_parameter("speed").value)
        if self.speed <= 0:
            raise ValueError("speed must be positive")
        self.loop = bool(self.get_parameter("loop").value)
        trial = load_vicon(self.get_parameter("root").value, subject, task)
        self.target_rad, n_missing = elbow_target_rad(trial)
        self.times = trial.times - trial.times[0]
        self.recorded_deg = trial.channel("RElbow_X")

        self.cmd_pub = self.create_publisher(Float64, ELBOW_CMD_TOPIC, 10)
        self.rec_pub = self.create_publisher(Float64, RECORDED_ELBOW_TOPIC, 10)
        log = self.get_logger()
        log.info(f"Reach&Grasp sub-{int(subject):02d} {task}: {describe(trial)}")
        if n_missing:
            log.info(f"{n_missing} missing Vicon samples: the previous target is held")
        if not is_elbow_task(task):
            log.info(f"{task} barely moves the elbow; these do: {', '.join(ELBOW_TASKS)}")
        self.start = time.monotonic()
        self.index = -1
        self.timer = self.create_timer(1.0 / (trial.rate_hz * self.speed), self._tick)

    def _tick(self) -> None:
        elapsed = (time.monotonic() - self.start) * self.speed
        if elapsed > self.times[-1]:
            if not self.loop:
                self.get_logger().info("end of the recording; the last target is held")
                self.timer.cancel()
                return
            self.start = time.monotonic()
            self.index = -1
            elapsed = 0.0
        # Latest sample not after `elapsed` (the times are increasing).
        i = int(self.times.searchsorted(elapsed, side="right")) - 1
        if i == self.index:
            return
        self.index = i
        self.cmd_pub.publish(Float64(data=float(self.target_rad[i])))
        deg = float(self.recorded_deg[i])
        if deg == deg:  # not NaN: only recorded samples go to the comparison topic
            self.rec_pub.publish(Float64(data=deg))


def main(args: list[str] | None = None) -> None:
    spin_node(MovementReplayNode, args)


if __name__ == "__main__":
    main()
