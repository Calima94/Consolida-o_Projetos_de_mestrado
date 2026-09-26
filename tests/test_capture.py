"""Capture tool port: angle geometry, category labelling, output format."""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from legacy_reference import capture_pose_module as legacy
from mestrado_capture.categories import CategoryRecorder
from mestrado_capture.pose import ARM_LANDMARKS, anatomical_to_sim_rad, elbow_angle_deg
from mestrado_emg.training import load_legacy_csv

VIDEO = Path(__file__).resolve().parents[1] / "data" / "test_2_05.avi"


# --- geometry -----------------------------------------------------------------


@pytest.mark.parametrize(
    "wrist, expected",
    [((2, 0), 180.0), ((1, -1), 90.0), ((1, 1), 270.0), ((0.5, -0.8660254), 60.0)],
)
def test_elbow_angle_uses_thesis_formula(wrist, expected):
    # shoulder at (0, 0), elbow at (1, 0); image y grows downwards
    assert elbow_angle_deg((0, 0), (1, 0), wrist) == pytest.approx(expected, abs=1e-6)


def test_landmarks_are_the_thesis_ones():
    assert ARM_LANDMARKS == {"right": (11, 13, 15), "left": (12, 14, 16)}


@pytest.mark.parametrize(
    "angle, sim_deg", [(170.0, 10.0), (90.0, 90.0), (45.0, 135.0), (200.0, 0.0), (-5.0, 180.0)]
)
def test_anatomical_to_sim(angle, sim_deg):
    assert math.degrees(anatomical_to_sim_rad(angle)) == pytest.approx(sim_deg)


# --- categories ---------------------------------------------------------------


def _batch(n=2):
    return np.ones((n, 8))


def test_category_membership_matches_thesis():
    """Same decision as the verbatim thesis function for many angles."""
    rec = CategoryRecorder(n_categories=4, tolerance_deg=10.0)
    for angle in np.linspace(30, 190, 321):
        write, cat = legacy.test_cases_to_use(4, angle, 10.0, [170, 90, 60, 45], [])
        mine = rec.category_for(angle)
        assert write == (mine is not None)
        assert cat == (0 if mine is None else mine + 1)


def test_thesis_completion_bug_is_fixed():
    """Finding 17: the thesis marked the wrong category complete."""
    # 3 samples of category 2 (90 deg) and none of category 1 (170 deg).
    table = [[0.0] * 9 + [2]] * 3
    _, done = legacy.check_if_num_samples_is_complete(table, [170, 90], 3, 2, [])
    assert done == [0]  # thesis: category 1 (170 deg) flagged complete -- wrong

    rec = CategoryRecorder(n_categories=2, samples_per_category=3)
    rec.add(np.ones((3, 8)), angle_deg=90.0, t_end=1.0)
    assert rec.complete == [False, True]  # port: the category that was filled


def test_recording_flow_and_output_format(tmp_path):
    rec = CategoryRecorder(n_categories=2, tolerance_deg=10, samples_per_category=4, fs_hz=200.0)
    assert not rec.add(_batch(), angle_deg=130.0, t_end=0.01)  # between categories
    assert not rec.add(_batch(), angle_deg=None, t_end=0.02)  # no angle
    assert rec.add(_batch(), angle_deg=168.0, t_end=0.03)
    assert rec.add(_batch(), angle_deg=172.0, t_end=0.04)  # category 1 complete
    assert not rec.add(_batch(), angle_deg=170.0, t_end=0.05)  # full, ignored
    assert rec.add(_batch(), angle_deg=92.0, t_end=0.06)
    assert not rec.done
    assert rec.add(_batch(), angle_deg=88.0, t_end=0.07)
    assert rec.done
    assert rec.status_text() == "170 graus: ok | 90 graus: ok"

    path = rec.save(tmp_path, prefix="t")
    assert rec.save(tmp_path, prefix="t") != path  # never overwrites (thesis numbering)
    df = pd.read_csv(path)
    assert list(df.columns) == ["time"] + [f"channel{i}" for i in range(1, 9)] + [
        "angle_deg",
        "position",
    ]
    assert df["position"].tolist() == [1, 1, 1, 1, 2, 2, 2, 2]
    # two samples per batch, 5 ms apart, ending at t_end
    np.testing.assert_allclose(df["time"][:2], [0.025, 0.03])
    samples, labels = load_legacy_csv(path)  # still readable by the training code
    assert samples.shape == (8, 8) and set(labels) == {1, 2}


def test_continuous_mode_keeps_everything_but_training_ignores_label_0(tmp_path):
    rec = CategoryRecorder(n_categories=2, samples_per_category=100, continuous=True)
    rec.add(_batch(), angle_deg=130.0, t_end=0.01)
    rec.add(_batch(), angle_deg=None, t_end=0.02)
    rec.add(_batch(), angle_deg=171.0, t_end=0.03)
    df = rec.to_dataframe()
    assert df["position"].tolist() == [0, 0, 0, 0, 1, 1]
    assert df["angle_deg"].isna().sum() == 2
    _, labels = load_legacy_csv(rec.save(tmp_path))
    assert set(labels) == {1}


def test_invalid_configuration():
    with pytest.raises(ValueError, match="n_categories"):
        CategoryRecorder(n_categories=5)
    with pytest.raises(ValueError, match="samples"):
        CategoryRecorder().add(np.ones((2, 4)), 170.0, 0.0)


# --- MediaPipe on the thesis video (inside the Docker image) -------------------

# Angle the thesis tool printed on these frames of Videos/test_2_05.avi.
THESIS_PRINTED = {180: 94, 195: 93, 210: 94, 225: 94, 240: 95}


@pytest.mark.skipif(not VIDEO.exists(), reason="run scripts/fetch_legacy_data.sh")
def test_mediapipe_matches_thesis_angles_on_thesis_video():
    pytest.importorskip("mediapipe", reason="MediaPipe is installed in the Docker image")
    cv2 = pytest.importorskip("cv2")
    from mestrado_capture.pose import DEFAULT_MODEL_PATH, ElbowAngleEstimator

    if not Path(DEFAULT_MODEL_PATH).exists():
        pytest.skip("pose model not present (it is downloaded in the Docker image)")
    est = ElbowAngleEstimator(DEFAULT_MODEL_PATH, arm="right", min_visibility=0.5)
    cap = cv2.VideoCapture(str(VIDEO))
    got, i = {}, 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        det = est.process(img, i * 50)  # 20 fps; the video is already mirrored
        if i in THESIS_PRINTED and det is not None:
            got[i] = det.angle_deg
        i += 1
    est.close()
    assert set(got) == set(THESIS_PRINTED)
    for frame, thesis in THESIS_PRINTED.items():
        assert got[frame] == pytest.approx(thesis, abs=3.0), frame
