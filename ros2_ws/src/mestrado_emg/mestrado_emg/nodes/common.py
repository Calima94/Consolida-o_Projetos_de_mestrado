"""Topic conventions shared by every sEMG source and consumer.

Any sEMG source (Myo, CSV replay, a future armband) publishes:

``/emg/raw`` : ``std_msgs/Float32MultiArray``
    A batch of consecutive samples, row-major, with
    ``layout.dim[0] = ("samples", n)`` and ``layout.dim[1] = ("channels", c)``.
``/emg/imu`` : ``sensor_msgs/Imu`` (optional)
    Orientation of the sensor; used for the shoulder angle, as in the thesis.

Swapping the sensor therefore means writing one new driver node; the
classifier and the simulator stay untouched.
"""

from __future__ import annotations

import numpy as np
from std_msgs.msg import Float32MultiArray, MultiArrayDimension

EMG_TOPIC = "/emg/raw"
IMU_TOPIC = "/emg/imu"
LABEL_TOPIC = "/emg/label"
CLASS_TOPIC = "/emg/predicted_class"
SHOULDER_CMD_TOPIC = "/arm/shoulder/cmd_pos"
ELBOW_CMD_TOPIC = "/arm/elbow/cmd_pos"
JOINT_STATES_TOPIC = "/joint_states"


def samples_to_msg(samples: np.ndarray) -> Float32MultiArray:
    """Pack ``[n_samples, n_channels]`` into a ``Float32MultiArray``."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 2:
        raise ValueError(f"expected [n_samples, n_channels], got shape {samples.shape}")
    n, c = samples.shape
    msg = Float32MultiArray()
    msg.layout.dim = [
        MultiArrayDimension(label="samples", size=n, stride=n * c),
        MultiArrayDimension(label="channels", size=c, stride=c),
    ]
    # -> [n_samples * n_channels] (row-major)
    msg.data = samples.reshape(-1).tolist()
    return msg


def msg_to_samples(msg: Float32MultiArray) -> np.ndarray:
    """Inverse of :func:`samples_to_msg`; returns ``[n_samples, n_channels]``."""
    if len(msg.layout.dim) != 2:
        raise ValueError("expected a 2-D layout (samples x channels)")
    n, c = msg.layout.dim[0].size, msg.layout.dim[1].size
    data = np.asarray(msg.data, dtype=float)
    if data.size != n * c:
        raise ValueError(f"layout says {n}x{c} but data has {data.size} values")
    # -> [n_samples, n_channels]
    return data.reshape(n, c)


def spin_node(node_factory, args: list[str] | None = None) -> None:
    """Run a node until Ctrl+C / SIGINT / SIGTERM and clean up exactly once.

    SIGINT and SIGTERM only *request* the stop; the node leaves between two
    callbacks, never in the middle of one (a KeyboardInterrupt raised at an
    arbitrary point can cut a Myo disconnection or a file write in half).
    On ``docker compose stop`` or Ctrl+C the signal can arrive twice (terminal
    or tini process group, then ``ros2 launch``); repeats are ignored.
    A callback may raise ``KeyboardInterrupt`` (or a subclass) to end the node
    itself. If the node defines ``shutdown()``, it is called before
    ``destroy_node()``.
    """
    import signal
    import threading

    import rclpy
    from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = None
    try:
        node = node_factory()
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        while rclpy.ok() and not stop.is_set():
            executor.spin_once(timeout_sec=0.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            if hasattr(node, "shutdown"):
                node.shutdown()
            node.destroy_node()
        rclpy.try_shutdown()
