"""Control law of the thesis arm controller (no ROS dependency)."""


def p_velocity(target: float, position: float, kp: float, v_max: float) -> float:
    """Thesis control law ``kp * error``, clipped to ``+- v_max`` (0 = no clip).

    Examples
    --------
    >>> p_velocity(1.0, 0.25, kp=1.0, v_max=0.0)
    0.75
    >>> p_velocity(3.0, 0.0, kp=10.0, v_max=2.0)
    2.0
    """
    v = kp * (target - position)
    if v_max > 0.0:
        v = max(-v_max, min(v_max, v))
    return v
