"""Myo driver node without a dongle (runs where ROS 2 is installed)."""

import threading
import time

import pytest

pytest.importorskip("rclpy", reason="ROS 2 not available; runs inside the Docker image")

import rclpy  # noqa: E402

from mestrado_emg.nodes import myo_driver  # noqa: E402


class UnpluggedDongle:
    """Stands in for MyoRaw when the dongle is pulled out: disconnect() fails."""

    def __init__(self, tty, emg_mode):
        self.running = threading.Event()

    def add_emg_handler(self, handler):
        pass

    def add_imu_handler(self, handler):
        pass

    def connect(self):
        pass

    def run(self, timeout):
        self.running.set()
        time.sleep(0.01)

    def disconnect(self):
        raise OSError("device disconnected")


def test_shutdown_survives_a_dongle_that_is_already_gone(monkeypatch):
    monkeypatch.setattr(myo_driver, "MyoRaw", UnpluggedDongle)
    rclpy.init()
    try:
        node = myo_driver.MyoDriverNode()
        assert node.myo.running.wait(timeout=2)
        node.shutdown()  # logs the failure instead of raising
        node._thread.join(timeout=2)
        assert not node._thread.is_alive()
        node.destroy_node()
    finally:
        rclpy.shutdown()
