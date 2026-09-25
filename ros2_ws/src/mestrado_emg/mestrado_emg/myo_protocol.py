"""Myo armband protocol over the BLED112 USB dongle (no ROS dependency).

Ported from the ``MyoRaw``/``BT`` classes used in the master's thesis
(``my_arm_def/.../capture_braco_pos.py`` and
``Capture_EMG_Data/capture_myo_not_filtered_signal_200hz.py``), which in turn
come from:

- dzhu, myo-raw: https://github.com/dzhu/myo-raw
- Fernando Cosentino, PyoConnect: http://www.fernandocosentino.net/pyoconnect
- Alvaro Villoslada (Alvipe), myo-raw fork: https://github.com/Alvipe/myo-raw

Changes relative to the thesis code:

- dropped the ``multichr``/``multiord`` helpers that branched on
  ``sys.version_info`` (a Python 2 shim inherited from myo-raw; the thesis ran
  on Python 3.8);
- packet framing and attribute decoding are pure functions/classes so they can
  be unit-tested without the dongle;
- ``pyserial`` is imported lazily, so importing this module never requires it.

The EMG mode written by :meth:`MyoRaw.start_raw` is ``0x02`` by default, the
same byte the thesis used when recording the training data. In the Myo BLE
header (``myohw.h``, https://github.com/thalmiclabs/myo-bluetooth) ``0x02`` is
``myohw_emg_mode_send_emg`` (filtered, 200 Hz) and ``0x03`` is
``myohw_emg_mode_send_emg_raw`` (unfiltered). The thesis comment calling
``0x02`` "50 Hz filtered" was inaccurate: 50 Hz was the separate
rectified/smoothed mode on handle ``0x28``.
"""

from __future__ import annotations

import enum
import math
import re
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

# Myo IMU fixed-point scales (myohw.h).
QUATERNION_SCALE = 16384.0
ACCELEROMETER_SCALE = 2048.0  # -> g
GYROSCOPE_SCALE = 16.0  # -> deg/s

# Tail of the advertisement payload that identifies a Myo during the BLE scan.
_MYO_ADV_SUFFIX = b"\x06\x42\x48\x12\x4a\x7f\x2c\x48\x47\xb9\xde\x04\xa9\x01\x00\x06\xd5"

# GATT handles for the four EMG notification characteristics.
EMG_DATA_HANDLES = (0x2B, 0x2E, 0x31, 0x34)


def pack(fmt: str, *args) -> bytes:
    """Little-endian ``struct.pack``."""
    return struct.pack("<" + fmt, *args)


def unpack(fmt: str, data: bytes) -> tuple:
    """Little-endian ``struct.unpack``."""
    return struct.unpack("<" + fmt, data)


class Arm(enum.Enum):
    UNKNOWN = 0
    RIGHT = 1
    LEFT = 2


class XDirection(enum.Enum):
    UNKNOWN = 0
    X_TOWARD_WRIST = 1
    X_TOWARD_ELBOW = 2


class Pose(enum.Enum):
    REST = 0
    FIST = 1
    WAVE_IN = 2
    WAVE_OUT = 3
    FINGERS_SPREAD = 4
    THUMB_TO_PINKY = 5
    UNKNOWN = 255


@dataclass
class Packet:
    """One BLED112 packet (header byte, class, command, payload)."""

    typ: int
    cls: int
    cmd: int
    payload: bytes

    @classmethod
    def from_bytes(cls, ords: list[int]) -> Packet:
        return cls(typ=ords[0], cls=ords[2], cmd=ords[3], payload=bytes(ords[4:]))

    def __repr__(self) -> str:
        body = " ".join(f"{b:02X}" for b in self.payload)
        return f"Packet({self.typ:02X}, {self.cls:02X}, {self.cmd:02X}, [{body}])"


class PacketParser:
    """Byte-by-byte BLED112 framing, identical to the thesis ``proc_byte``."""

    def __init__(self) -> None:
        self.buf: list[int] = []
        self.packet_len = 0

    def feed(self, c: int) -> Packet | None:
        """Consume one byte; return a :class:`Packet` when one is complete."""
        if not self.buf:
            # BLE response, BLE event, wifi response, wifi event
            if c in (0x00, 0x80, 0x08, 0x88):
                self.buf.append(c)
            return None
        if len(self.buf) == 1:
            self.buf.append(c)
            self.packet_len = 4 + (self.buf[0] & 0x07) + self.buf[1]
            return None
        self.buf.append(c)
        if self.packet_len and len(self.buf) == self.packet_len:
            p = Packet.from_bytes(self.buf)
            self.buf = []
            return p
        return None


@dataclass
class EmgEvent:
    samples: list[tuple[int, ...]]  # each tuple has 8 channels
    moving: int = 0


@dataclass
class ImuEvent:
    quat: tuple[int, int, int, int]  # w, x, y, z (raw fixed point)
    acc: tuple[int, int, int]
    gyro: tuple[int, int, int]


@dataclass
class ArmEvent:
    arm: Arm
    xdir: XDirection


@dataclass
class PoseEvent:
    pose: Pose


@dataclass
class BatteryEvent:
    level: int


def decode_attribute(attr: int, pay: bytes):
    """Decode a GATT notification payload into an event object.

    Returns ``None`` for attributes the thesis code did not handle.
    """
    if attr == 0x27:
        # Legacy firmware: 8 unsigned shorts + a movement bitmask byte.
        vals = unpack("8HB", pay)
        return EmgEvent(samples=[vals[:8]], moving=vals[8])
    if attr in EMG_DATA_HANDLES:
        # Each notification carries two consecutive int8 samples.
        return EmgEvent(samples=[unpack("8b", pay[:8]), unpack("8b", pay[8:16])])
    if attr == 0x1C:
        vals = unpack("10h", pay)
        return ImuEvent(quat=vals[:4], acc=vals[4:7], gyro=vals[7:10])
    if attr == 0x23:
        typ, val, xdir, _, _, _ = unpack("6B", pay)
        if typ == 1:
            return ArmEvent(Arm(val), XDirection(xdir))
        if typ == 2:
            return ArmEvent(Arm.UNKNOWN, XDirection.UNKNOWN)
        if typ == 3:
            return PoseEvent(Pose(val))
        return None
    if attr == 0x11:
        return BatteryEvent(level=pay[0])
    return None


def quat_to_pitch(w: float, x: float, y: float, z: float) -> float:
    """Pitch (rad) as computed by the thesis ``calc_quat`` (inputs normalised).

    Examples
    --------
    >>> quat_to_pitch(1.0, 0.0, 0.0, 0.0)
    -0.0
    """
    return -math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))


class BT:
    """Non-Myo-specific details of the BLED112 serial protocol."""

    def __init__(self, tty: str) -> None:
        import serial  # lazy: only needed with real hardware

        self.ser = serial.Serial(port=tty, baudrate=9600, dsrdtr=1)
        self.parser = PacketParser()
        self.lock = threading.Lock()
        self.handlers: list[Callable[[Packet], None]] = []

    def recv_packet(self, timeout: float | None = None) -> Packet | None:
        t0 = time.time()
        self.ser.timeout = None
        while timeout is None or time.time() < t0 + timeout:
            if timeout is not None:
                self.ser.timeout = t0 + timeout - time.time()
            c = self.ser.read()
            if not c:
                return None
            ret = self.parser.feed(ord(c))
            if ret:
                if ret.typ == 0x80:
                    self.handle_event(ret)
                return ret
        return None

    def handle_event(self, p: Packet) -> None:
        for h in self.handlers:
            h(p)

    def add_handler(self, h: Callable[[Packet], None]) -> None:
        self.handlers.append(h)

    def remove_handler(self, h: Callable[[Packet], None]) -> None:
        if h in self.handlers:
            self.handlers.remove(h)

    def wait_event(self, cls: int, cmd: int) -> Packet:
        res: list[Packet | None] = [None]

        def h(p: Packet) -> None:
            if p.cls == cls and p.cmd == cmd:
                res[0] = p

        self.add_handler(h)
        while res[0] is None:
            self.recv_packet()
        self.remove_handler(h)
        return res[0]

    def connect(self, addr: list[int]) -> Packet:
        return self.send_command(6, 3, pack("6sBHHHH", bytes(addr), 0, 6, 6, 64, 0))

    def discover(self) -> Packet:
        return self.send_command(6, 2, b"\x01")

    def end_scan(self) -> Packet:
        return self.send_command(6, 4)

    def disconnect(self, h: int) -> Packet:
        return self.send_command(3, 0, pack("B", h))

    def read_attr(self, con: int, attr: int) -> Packet:
        self.send_command(4, 4, pack("BH", con, attr))
        return self.wait_event(4, 5)

    def write_attr(self, con: int, attr: int, val: bytes) -> Packet:
        self.send_command(4, 5, pack("BHB", con, attr, len(val)) + val)
        return self.wait_event(4, 1)

    def send_command(self, cls: int, cmd: int, payload: bytes = b"") -> Packet:
        self.ser.write(pack("4B", 0, len(payload), cls, cmd) + payload)
        while True:
            p = self.recv_packet()
            if p.typ == 0:  # response; anything else is an event
                return p
            self.handle_event(p)


class MyoRaw:
    """Myo-specific protocol: connection, streaming setup and event dispatch."""

    def __init__(self, tty: str | None = None, emg_mode: int = 0x02) -> None:
        tty = tty or self.detect_tty()
        if tty is None:
            raise ValueError("Myo dongle not found!")
        self.bt = BT(tty)
        self.conn: int | None = None
        self.emg_mode = emg_mode
        self.emg_handlers: list[Callable] = []
        self.imu_handlers: list[Callable] = []
        self.arm_handlers: list[Callable] = []
        self.pose_handlers: list[Callable] = []
        self.battery_handlers: list[Callable] = []

    @staticmethod
    def detect_tty() -> str | None:
        """Find the BLED112 dongle (USB PID 2458:0001) among serial ports."""
        from serial.tools.list_ports import comports

        for p in comports():
            if re.search(r"PID=2458:0*1", p[2]):
                return p[0]
        return None

    def run(self, timeout: float | None = None) -> None:
        self.bt.recv_packet(timeout)

    def connect(self) -> None:
        """Scan, connect, configure streaming and register the data handler."""
        self.bt.end_scan()
        for h in (0, 1, 2):
            self.bt.disconnect(h)

        self.bt.discover()
        while True:
            p = self.bt.recv_packet()
            if p.payload.endswith(_MYO_ADV_SUFFIX):
                addr = list(p.payload[2:8])
                break
        self.bt.end_scan()

        conn_pkt = self.bt.connect(addr)
        self.conn = conn_pkt.payload[-1]
        self.bt.wait_event(3, 0)

        fw = self.read_attr(0x17)
        _, _, _, _, v0, _v1, _v2, _v3 = unpack("BHBBHHHH", fw.payload)
        if v0 == 0:
            # Old firmware (v0.x): sequence copied from Myo Connect.
            self.write_attr(0x19, b"\x01\x02\x00\x00")
            for handle in (0x2F, 0x2C, 0x32, 0x35):
                self.write_attr(handle, b"\x01\x00")
            self.write_attr(0x28, b"\x01\x00")
            self.write_attr(0x1D, b"\x01\x00")
            c, emg_hz, emg_smooth, imu_hz = 1000, 50, 100, 50
            self.write_attr(0x19, pack("BBBBHBBBBB", 2, 9, 2, 1, c, emg_smooth, c // emg_hz, imu_hz, 0, 0))
        else:
            self.write_attr(0x1D, b"\x01\x00")  # IMU notifications
            self.write_attr(0x24, b"\x02\x00")  # on/off-arm indications
            self.start_raw()
            self.write_attr(0x12, b"\x01\x10")  # battery notifications

        self.bt.add_handler(self._handle_data)

    def _handle_data(self, p: Packet) -> None:
        if (p.cls, p.cmd) != (4, 5):
            return
        _c, attr, _typ = unpack("BHB", p.payload[:4])
        event = decode_attribute(attr, p.payload[5:])
        if isinstance(event, EmgEvent):
            for sample in event.samples:
                for h in self.emg_handlers:
                    h(sample, event.moving)
        elif isinstance(event, ImuEvent):
            for h in self.imu_handlers:
                h(event.quat, event.acc, event.gyro)
        elif isinstance(event, ArmEvent):
            for h in self.arm_handlers:
                h(event.arm, event.xdir)
        elif isinstance(event, PoseEvent):
            for h in self.pose_handlers:
                h(event.pose)
        elif isinstance(event, BatteryEvent):
            for h in self.battery_handlers:
                h(event.level)

    def write_attr(self, attr: int, val: bytes) -> None:
        if self.conn is not None:
            self.bt.write_attr(self.conn, attr, val)

    def read_attr(self, attr: int) -> Packet | None:
        if self.conn is not None:
            return self.bt.read_attr(self.conn, attr)
        return None

    def disconnect(self) -> None:
        if self.conn is not None:
            self.bt.disconnect(self.conn)

    def start_raw(self) -> None:
        """Subscribe to the four EMG characteristics and enable streaming.

        Command on handle 0x19: [0x01 set mode, 0x03 payload size,
        EMG mode, IMU mode 0x01 (data), classifier mode 0x01 (events)].
        """
        for handle in (0x2C, 0x2F, 0x32, 0x35):
            self.write_attr(handle, b"\x01\x00")
        self.write_attr(0x19, bytes([0x01, 0x03, self.emg_mode, 0x01, 0x01]))

    def sleep_mode(self, mode: int) -> None:
        self.write_attr(0x19, pack("3B", 9, 1, mode))

    def power_off(self) -> None:
        self.write_attr(0x19, b"\x04\x00")

    def vibrate(self, length: int) -> None:
        if length in range(1, 4):
            self.write_attr(0x19, pack("3B", 3, 1, length))

    def set_leds(self, logo: list[int], line: list[int]) -> None:
        self.write_attr(0x19, pack("8B", 6, 6, *(logo + line)))

    def add_emg_handler(self, h: Callable) -> None:
        self.emg_handlers.append(h)

    def add_imu_handler(self, h: Callable) -> None:
        self.imu_handlers.append(h)

    def add_pose_handler(self, h: Callable) -> None:
        self.pose_handlers.append(h)

    def add_arm_handler(self, h: Callable) -> None:
        self.arm_handlers.append(h)

    def add_battery_handler(self, h: Callable) -> None:
        self.battery_handlers.append(h)
