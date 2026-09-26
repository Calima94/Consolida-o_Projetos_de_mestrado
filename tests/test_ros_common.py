"""Message packing shared by all sEMG sources (runs where ROS 2 is installed)."""

import numpy as np
import pytest

pytest.importorskip("std_msgs", reason="ROS 2 not available; runs inside the Docker image")

from mestrado_emg.nodes.common import msg_to_samples, samples_to_msg  # noqa: E402


def test_roundtrip_keeps_sample_and_channel_order():
    x = np.arange(24, dtype=np.float32).reshape(3, 8)
    msg = samples_to_msg(x)
    assert [d.label for d in msg.layout.dim] == ["samples", "channels"]
    np.testing.assert_array_equal(msg_to_samples(msg), x)


def test_inconsistent_layout_is_rejected():
    msg = samples_to_msg(np.zeros((2, 8)))
    msg.data = msg.data[:-1]
    with pytest.raises(ValueError, match="layout says 2x8"):
        msg_to_samples(msg)


def test_one_dimensional_input_is_rejected():
    with pytest.raises(ValueError, match="n_samples, n_channels"):
        samples_to_msg(np.zeros(8))
