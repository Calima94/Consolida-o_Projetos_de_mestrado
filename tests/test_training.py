"""Training: split logic, bundles, and reproduction of the historical results."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from mestrado_emg.features import LegacyFeatureConfig
from mestrado_emg.training import (
    BUNDLE_FORMAT,
    build_dataset,
    load_bundle,
    load_legacy_csv,
    split_indices,
    train_all,
)

DATA = Path(__file__).resolve().parents[1] / "data"
RAW = DATA / "6_10_20220.csv"
needs_data = pytest.mark.skipif(
    not RAW.exists(), reason="run scripts/fetch_legacy_data.sh to get the thesis data"
)


def _synthetic_csv(path: Path, n_per_class=(620, 480), seed=0) -> Path:
    """Two classes with clearly different amplitude, legacy column names."""
    rng = np.random.default_rng(seed)
    rows = []
    for label, (n, scale) in zip((1, 2), zip(n_per_class, (5.0, 40.0), strict=True), strict=True):
        emg = rng.normal(scale=scale, size=(n, 8)).round()
        rows.append(np.column_stack([np.arange(n) / 200.0, emg, np.full(n, label)]))
    df = pd.DataFrame(
        np.vstack(rows), columns=["time"] + [f"channel{i}" for i in range(1, 9)] + ["position"]
    )
    df.to_csv(path, index=False)
    return path


def test_load_legacy_csv_accepts_both_spellings(tmp_path):
    p = tmp_path / "a.csv"
    pd.DataFrame(
        {"Unnamed": [0, 1], " Chanel1 ": [1, 2], "chanel2": [3, 4], "position": [1, 2]}
    ).to_csv(p, index=False)
    samples, labels = load_legacy_csv(p)
    assert samples.shape == (2, 2)
    assert labels.tolist() == [1, 2]


def test_temporal_split_is_blocked_and_purged(tmp_path):
    s, lab = load_legacy_csv(_synthetic_csv(tmp_path / "s.csv"))
    ds = build_dataset(s, lab, LegacyFeatureConfig())
    train, test = split_indices(ds, "temporal", test_size=0.3, purge_windows=1)
    assert not set(train) & set(test)
    for cls in np.unique(ds.y):
        tr = ds.order[train][ds.y[train] == cls]
        te = ds.order[test][ds.y[test] == cls]
        # every test window comes after every train window, with a 1-window gap
        assert te.min() - tr.max() == 2


def test_legacy_split_is_reproducible(tmp_path):
    s, lab = load_legacy_csv(_synthetic_csv(tmp_path / "s.csv"))
    ds = build_dataset(s, lab, LegacyFeatureConfig())
    a = split_indices(ds, "legacy", seed=42)
    b = split_indices(ds, "legacy", seed=42)
    np.testing.assert_array_equal(a[1], b[1])


def test_train_all_writes_bundles_report_and_latest_links(tmp_path):
    csv = _synthetic_csv(tmp_path / "rec 1.csv")
    report = train_all(csv, tmp_path / "m", LegacyFeatureConfig(), date="2026-01-01")
    assert report["seed"] == 42
    assert set(report["results"]) == {"lda", "gnb", "lin_svm", "knn", "tree"}
    # amplitude classes are trivially separable
    assert all(r["accuracy"] == 1.0 for r in report["results"].values())

    latest = tmp_path / "m" / "knn_rec-1_mav_temporal_latest.joblib"
    assert latest.is_symlink()
    bundle = load_bundle(latest)
    assert bundle["format"] == BUNDLE_FORMAT
    assert bundle["class_angles_deg"] == [0.0, 90.0]
    assert LegacyFeatureConfig.from_dict(bundle["feature_config"]) == LegacyFeatureConfig()
    assert len(bundle["source"]["sha256"]) == 64
    saved = json.loads((tmp_path / "m" / "report_rec-1_mav_temporal_2026-01-01.json").read_text())
    assert saved["results"] == report["results"]


def test_load_bundle_rejects_legacy_pickles(tmp_path):
    p = tmp_path / "neigh_teste.joblib"
    joblib.dump(object(), p)
    with pytest.raises(ValueError, match="retrained"):
        load_bundle(p)


@needs_data
def test_rms_features_reproduce_the_thesis_training_matrix():
    """Settles which feature the thesis models were trained on: RMS, not MAV."""
    ref = pd.read_csv(DATA / "training_matrix_csv_m_class.csv")
    s, lab = load_legacy_csv(RAW)
    rms = build_dataset(s, lab, LegacyFeatureConfig(feature="rms"))
    np.testing.assert_allclose(rms.X, ref.iloc[:, :8].to_numpy(), rtol=1e-12, atol=1e-9)
    np.testing.assert_array_equal(rms.y, ref["Category"].to_numpy())
    mav = build_dataset(s, lab, LegacyFeatureConfig(feature="mav"))
    assert not np.allclose(mav.X, ref.iloc[:, :8].to_numpy())


@needs_data
def test_historical_scores_are_reproduced(tmp_path):
    hist = pd.read_csv(DATA / "scores_of_classifiers.csv").set_index("Classifiers")["Scores"]
    report = train_all(RAW, tmp_path, LegacyFeatureConfig(feature="rms"), split="legacy", seed=42)
    for name, score in hist.items():
        assert report["results"][name]["accuracy"] == pytest.approx(score)
