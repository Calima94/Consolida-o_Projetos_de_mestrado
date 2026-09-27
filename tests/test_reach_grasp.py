"""Reach&Grasp elbow replay: reading the Vicon files and building the target."""

import csv
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

from mestrado_emg.reach_grasp import (
    ELBOW_TASKS,
    TASKS,
    describe,
    elbow_target_rad,
    hold_last_valid,
    load_vicon,
    trial_paths,
)

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data" / "reach_grasp"
CHANNELS = ["LThorax_X", "LThorax_Y", "LThorax_Z", "RElbow_X", "RElbow_Y", "RElbow_Z"]


def _trial(root: Path, elbow, subject=1, task="ReaCyl", rate=100):
    paths = trial_paths(root, str(subject), task)
    paths["csv"].parent.mkdir(parents=True, exist_ok=True)
    with open(paths["tsv"], "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["name", "type", "units", "sampling_frequency"])
        for n in CHANNELS:
            w.writerow([n, "JNTANG", "DEG", rate])
    paths["json"].write_text(json.dumps({"SamplingFrequency": rate}))
    with open(paths["csv"], "w", newline="") as fh:
        w = csv.writer(fh)
        for i, x in enumerate(elbow):
            w.writerow([i / rate, 1, 2, 3, x, 0.0, 0.0])
    return paths


def test_paths_follow_the_dataset_layout(tmp_path):
    p = trial_paths(tmp_path, "4", "EatFruit")
    assert p["csv"] == tmp_path / "sub-04/motion/sub-04_task-EatFruit_acq-vicon_motion.csv"
    assert p["tsv"].name == "sub-04_task-EatFruit_acq-vicon_channels.tsv"
    with pytest.raises(ValueError, match="unknown task"):
        trial_paths(tmp_path, "1", "Reach")
    assert set(ELBOW_TASKS) <= set(TASKS) and len(TASKS) == 16


def test_missing_trial_says_how_to_download_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_reach_grasp.py --subjects 02 --tasks Pour"):
        load_vicon(tmp_path, "2", "Pour")


def test_elbow_goes_to_the_simulator_in_radians(tmp_path):
    _trial(tmp_path, [90.0, 60.0, float("nan"), 30.0])
    trial = load_vicon(tmp_path, "1", "ReaCyl")
    assert trial.rate_hz == 100 and trial.channels == CHANNELS
    assert trial.data.shape == (4, 6)  # [n_samples, n_channels]
    target, missing = elbow_target_rad(trial)
    assert missing == 1
    # 0 deg = extended on both sides: straight conversion, the gap holds 60 deg
    np.testing.assert_allclose(np.degrees(target), [90, 60, 60, 30])
    assert "RElbow_X 30.0 to 90.0 deg, 1 missing" in describe(trial)


def test_a_row_with_the_wrong_column_count_is_refused(tmp_path):
    paths = _trial(tmp_path, [90.0, 80.0])
    with open(paths["csv"], "a") as fh:
        fh.write("0.02,1,2\n")
    with pytest.raises(ValueError, match="line 3: 3 columns, expected 7"):
        load_vicon(tmp_path, "1", "ReaCyl")


def test_hold_last_valid():
    out, n = hold_last_valid(np.array([np.nan, 1.0, np.nan, np.nan, 4.0]))
    np.testing.assert_array_equal(out, [1, 1, 1, 1, 4])
    assert n == 3
    with pytest.raises(ValueError):
        hold_last_valid(np.array([np.nan, np.nan]))


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fetch_checks_md5_even_when_the_published_one_is_masked():
    fetch = _load_script("fetch_reach_grasp")
    good = "5326d9a49728e5b21c24908894039841"
    assert fetch.md5_ok(good, good)
    assert fetch.md5_ok(good, "5326d9a49728e5b21c2XXXXXXXXX9841")
    assert not fetch.md5_ok(good, "5326d9a49728e5b21c2XXXXXXXXX9842")
    assert not fetch.md5_ok(good, "0" * 32)


class _Resposta:
    def __init__(self, corpo: bytes):
        self.corpo = corpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.corpo


def _lista(versao="1.0"):
    maior, menor = versao.split(".")
    arquivos = [
        {"directoryLabel": "sub-01/motion",
         "dataFile": {"id": 7, "filename": "sub-01_task-ReaCyl_acq-vicon_motion.csv",
                      "filesize": 10, "checksum": {"value": "a" * 32}}},
        {"directoryLabel": "sub-01/emg",
         "dataFile": {"id": 8, "filename": "sub-01_task-ReaCyl_acq-bipolar_emg.edf",
                      "filesize": 99, "checksum": {"value": "b" * 32}}},
    ]  # fmt: skip
    dados = {"versionNumber": int(maior), "versionMinorNumber": int(menor), "files": arquivos}
    return json.dumps({"data": dados}).encode()


def test_listing_survives_a_timeout_like_the_ci_one(monkeypatch):
    """One timeout while listing the files used to end the download (CI, PR #9)."""
    fetch = _load_script("fetch_reach_grasp")
    respostas = iter([TimeoutError("timed out"), TimeoutError("timed out"), _lista()])

    def urlopen(url, timeout):
        r = next(respostas)
        if isinstance(r, Exception):
            raise r
        return _Resposta(r)

    esperas = []
    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fetch.time, "sleep", esperas.append)
    files = fetch.list_vicon_files()
    assert [f["path"] for f in files] == ["sub-01/motion/sub-01_task-ReaCyl_acq-vicon_motion.csv"]
    assert esperas == [2, 4]  # two retries, then it worked


def test_listing_gives_up_and_a_wrong_version_is_not_retried(monkeypatch):
    fetch = _load_script("fetch_reach_grasp")
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)

    def sempre_cai(url, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", sempre_cai)
    with pytest.raises(TimeoutError):
        fetch.list_vicon_files(retries=2)
    chamadas = []

    def versao_nova(url, timeout):
        chamadas.append(url)
        return _Resposta(_lista("2.0"))

    monkeypatch.setattr(fetch.urllib.request, "urlopen", versao_nova)
    with pytest.raises(RuntimeError, match="version 2.0, expected 1.0"):
        fetch.list_vicon_files()
    assert len(chamadas) == 1


def test_checker_finds_the_lag_of_a_delayed_copy():
    check = _load_script("check_movement") if importlib.util.find_spec("rclpy") else None
    if check is None:
        pytest.skip("rclpy only in the Docker image")
    t = np.arange(0, 30, 0.01)
    rec = [(ti, 60 + 40 * math.sin(ti)) for ti in t]
    sim = [(ti, 60 + 40 * math.sin(ti - 1.0)) for ti in t]  # 1 s behind
    m = check.compare(rec, sim)
    assert m["lag_s"] == pytest.approx(1.0, abs=0.05)
    assert m["corr"] > 0.99


needs_trial = pytest.mark.skipif(
    not trial_paths(DATA, "1", "ReaCyl")["csv"].exists(),
    reason="scripts/fetch_reach_grasp.py --subjects 1 --tasks ReaCyl",
)


@needs_trial
def test_real_trial_matches_the_data_contract():
    """Numbers of the semg-digital-twins data contract, sub-01 ReaCyl."""
    trial = load_vicon(DATA, "1", "ReaCyl")
    assert trial.rate_hz == 100 and len(trial.channels) == 31
    x = trial.channel("RElbow_X")
    assert np.isfinite(x).all()
    assert np.abs(trial.channel("RElbow_Y")).max() < 1e-11  # 1 degree of freedom
    assert np.abs(trial.channel("RElbow_Z")).max() < 1e-11
    assert x.max() - x.min() == pytest.approx(55.6, abs=0.1)
    rest = np.median(x[:100])
    assert rest - x.min() > 30  # reaching extends the elbow: the angle drops
