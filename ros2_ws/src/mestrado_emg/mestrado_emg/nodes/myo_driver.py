"""ROS 2 driver for the Myo armband (BLED112 dongle).

Replaces the ``myo_thread`` of the thesis ``capture_braco_pos.py``: instead of
collecting 50 samples into a global list, it streams every notification to
``/emg/raw`` (2 samples x 8 channels) and the IMU to ``/emg/imu``.

Parameters
----------
tty : str
    Serial device of the dongle; ``auto`` (or empty) auto-detects (USB 2458:0001).
emg_mode : int
    0x02 (filtered 200 Hz, used in the thesis) or 0x03 (unfiltered 200 Hz).
frame_id : str
    Frame for the IMU message.

Run with the dongle passed into the container (see docker/compose.myo.yaml)::

    ros2 run mestrado_emg myo_driver --ros-args -p tty:=/dev/ttyACM0
"""

from __future__ import annotations

import math
import threading

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32MultiArray

from mestrado_emg.myo_protocol import (
    ACCELEROMETER_SCALE,
    GYROSCOPE_SCALE,
    QUATERNION_SCALE,
    MyoRaw,
)
from mestrado_emg.nodes.common import EMG_TOPIC, IMU_TOPIC, samples_to_msg, spin_node

G = 9.80665


class MyoDriverNode(Node):
    def __init__(self) -> None:
        super().__init__("myo_driver")
        self.declare_parameter("tty", "auto")
        self.declare_parameter("emg_mode", 0x02)
        self.declare_parameter("frame_id", "myo")
        self.frame_id = self.get_parameter("frame_id").value

        self.emg_pub = self.create_publisher(Float32MultiArray, EMG_TOPIC, 50)
        self.imu_pub = self.create_publisher(Imu, IMU_TOPIC, 10)
        self._pending: list[tuple[int, ...]] = []
        self._stop = threading.Event()

        tty = self.get_parameter("tty").value
        tty = None if tty in ("", "auto") else tty
        self.myo = MyoRaw(tty, emg_mode=int(self.get_parameter("emg_mode").value))
        self.myo.add_emg_handler(self._on_emg)
        self.myo.add_imu_handler(self._on_imu)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self.get_logger().info("scanning for Myo...")
        self.myo.connect()
        self.get_logger().info("Myo connected, streaming")
        while not self._stop.is_set() and rclpy.ok():
            self.myo.run(1)

    def _on_emg(self, sample: tuple[int, ...], _moving: int) -> None:
        # Notifications carry 2 samples; publish them together.
        self._pending.append(sample)
        if len(self._pending) == 2:
            self.emg_pub.publish(samples_to_msg(np.array(self._pending)))
            self._pending = []

    def _on_imu(self, quat, acc, gyro) -> None:
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        w, x, y, z = (q / QUATERNION_SCALE for q in quat)
        msg.orientation.w, msg.orientation.x = w, x
        msg.orientation.y, msg.orientation.z = y, z
        ax, ay, az = (a / ACCELEROMETER_SCALE * G for a in acc)
        msg.linear_acceleration.x, msg.linear_acceleration.y = ax, ay
        msg.linear_acceleration.z = az
        gx, gy, gz = (math.radians(g / GYROSCOPE_SCALE) for g in gyro)
        msg.angular_velocity.x, msg.angular_velocity.y = gx, gy
        msg.angular_velocity.z = gz
        self.imu_pub.publish(msg)

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self.myo.disconnect()
        except Exception as exc:  # the dongle may already be gone
            self.get_logger().warn(f"disconnect failed: {exc}")


def main(args: list[str] | None = None) -> None:
    spin_node(MyoDriverNode, args)


if __name__ == "__main__":
    main()
