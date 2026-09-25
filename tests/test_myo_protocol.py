"""Myo protocol: framing and decoding, tested without the dongle."""

import math
import struct

import pytest

from mestrado_emg.myo_protocol import (
    Arm,
    ArmEvent,
    BatteryEvent,
    EmgEvent,
    ImuEvent,
    MyoRaw,
    Packet,
    PacketParser,
    Pose,
    PoseEvent,
    XDirection,
    decode_attribute,
    quat_to_pitch,
)


def _notification(attr: int, payload: bytes) -> list[int]:
    """BLED112 event packet: attclient attribute_value (class 4, command 5)."""
    body = struct.pack("<BHB", 0, attr, 1) + bytes([len(payload)]) + payload
    return [0x80, len(body), 4, 5, *body]


def _feed(parser: PacketParser, data: list[int]):
    out = [parser.feed(b) for b in data]
    return [p for p in out if p is not None]


def test_parser_frames_a_packet_and_skips_leading_garbage():
    pkt = _notification(0x2B, bytes(16))
    packets = _feed(PacketParser(), [0x55, 0x13, *pkt])
    assert len(packets) == 1
    p = packets[0]
    assert (p.typ, p.cls, p.cmd) == (0x80, 4, 5)
    assert len(p.payload) == len(pkt) - 4


def test_parser_handles_back_to_back_packets():
    data = _notification(0x2B, bytes(16)) + _notification(0x11, bytes([77]))
    assert len(_feed(PacketParser(), data)) == 2


def test_emg_notification_carries_two_int8_samples():
    s1, s2 = tuple(range(-4, 4)), tuple(range(10, 18))
    ev = decode_attribute(0x31, struct.pack("<8b8b", *s1, *s2))
    assert isinstance(ev, EmgEvent)
    assert ev.samples == [s1, s2]


def test_legacy_firmware_emg():
    ev = decode_attribute(0x27, struct.pack("<8HB", *range(8), 3))
    assert ev.samples == [tuple(range(8))] and ev.moving == 3


def test_imu_decoding():
    vals = (16384, 0, 0, 0, 1, 2, 3, 4, 5, 6)
    ev = decode_attribute(0x1C, struct.pack("<10h", *vals))
    assert isinstance(ev, ImuEvent)
    assert ev.quat == (16384, 0, 0, 0) and ev.acc == (1, 2, 3) and ev.gyro == (4, 5, 6)


@pytest.mark.parametrize(
    "payload, expected",
    [
        (bytes([1, 1, 1, 0, 0, 0]), ArmEvent(Arm.RIGHT, XDirection.X_TOWARD_WRIST)),
        (bytes([2, 0, 0, 0, 0, 0]), ArmEvent(Arm.UNKNOWN, XDirection.UNKNOWN)),
        (bytes([3, 1, 0, 0, 0, 0]), PoseEvent(Pose.FIST)),
    ],
)
def test_classifier_events(payload, expected):
    assert decode_attribute(0x23, payload) == expected


def test_battery_and_unknown_attributes():
    assert decode_attribute(0x11, bytes([42])) == BatteryEvent(42)
    assert decode_attribute(0x99, b"") is None


def test_quat_to_pitch_matches_thesis_formula():
    # 30 deg rotation about y: w = cos(15), y = sin(15) -> thesis pitch = -30 deg
    h = math.radians(15)
    assert math.degrees(quat_to_pitch(math.cos(h), 0.0, math.sin(h), 0.0)) == pytest.approx(-30)
    assert quat_to_pitch(1.0, 0.0, 1.0, 0.0) == pytest.approx(-math.pi / 2)  # 2(wy) = 2, clamped


def test_handle_data_dispatches_each_emg_sample():
    myo = MyoRaw.__new__(MyoRaw)  # skip __init__: no dongle
    myo.emg_handlers, myo.imu_handlers = [], []
    myo.arm_handlers, myo.pose_handlers, myo.battery_handlers = [], [], []
    got = []
    myo.add_emg_handler(lambda s, moving: got.append(s))
    raw = _notification(0x2E, struct.pack("<8b8b", *([1] * 8), *([2] * 8)))
    myo._handle_data(Packet.from_bytes(raw))
    assert got == [(1,) * 8, (2,) * 8]


def test_start_raw_uses_thesis_emg_mode():
    myo = MyoRaw.__new__(MyoRaw)
    myo.emg_mode = 0x02
    writes = []
    myo.write_attr = lambda attr, val: writes.append((attr, val))
    myo.start_raw()
    assert writes[-1] == (0x19, b"\x01\x03\x02\x01\x01")  # same bytes as the thesis
    assert [a for a, _ in writes[:4]] == [0x2C, 0x2F, 0x32, 0x35]
