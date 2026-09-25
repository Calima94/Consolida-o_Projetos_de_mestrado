"""The thesis P control law used by the arm controller."""

import pytest

from mestrado_emg.control import p_velocity


def test_velocity_is_kp_times_error():
    assert p_velocity(1.0, 0.25, kp=1.0, v_max=0.0) == pytest.approx(0.75)
    assert p_velocity(0.0, 0.02, kp=10.0, v_max=0.0) == pytest.approx(-0.2)


def test_clip():
    assert p_velocity(3.0, 0.0, kp=10.0, v_max=2.0) == 2.0
    assert p_velocity(-3.0, 0.0, kp=10.0, v_max=2.0) == -2.0


def test_first_order_response_time_constant():
    """kp = 1 gives a 1 s time constant: 63 % of the step after 1 s (as in Gazebo)."""
    pos, dt = 0.0, 0.01
    for _ in range(100):
        pos += p_velocity(1.0, pos, kp=1.0, v_max=0.0) * dt
    assert pos == pytest.approx(0.634, abs=0.01)
