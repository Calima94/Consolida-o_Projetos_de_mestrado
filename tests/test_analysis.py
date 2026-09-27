"""Analysis: temporal CV folds, rate check, figures, and the documented numbers."""

import json

import numpy as np
import pandas as pd
import pytest
from test_training import RAW, _synthetic_csv, needs_data

from mestrado_emg.analysis import (
    analyze,
    blocked_cv_indices,
    estimate_rate_hz,
    rate_warning,
)
from mestrado_emg.features import LegacyFeatureConfig
from mestrado_emg.training import WindowDataset

FIGURES = {
    "scores.png",
    "confusao.png",
    "roc.png",
    "sinal_bruto.png",
    "features_por_canal.png",
    "features_c1_c2.png",
    "analise.json",
    "resumo.md",
}


def _dataset(n_per_class=(12, 10)) -> WindowDataset:
    y = np.concatenate([np.full(n, k) for k, n in enumerate(n_per_class)])
    order = np.concatenate([np.arange(n) for n in n_per_class])
    return WindowDataset(X=np.zeros((len(y), 8)), y=y, order=order, class_labels=[1, 2])


def test_blocked_folds_are_disjoint_contiguous_and_purged():
    ds = _dataset()
    folds = blocked_cv_indices(ds, n_folds=4, purge_windows=1)
    assert len(folds) == 4
    tested = np.concatenate([te for _, te in folds])
    assert sorted(tested) == list(range(len(ds.y)))  # every window tested once
    for train, test in folds:
        assert not set(train) & set(test)
        for cls in (0, 1):
            pos = np.sort(ds.order[test[ds.y[test] == cls]])
            assert len(pos) > 0  # every class in every fold
            assert np.all(np.diff(pos) == 1)  # contiguous block
            train_pos = ds.order[train[ds.y[train] == cls]]
            # purge: no training window right next to the test block
            assert not set(train_pos) & {pos[0] - 1, pos[-1] + 1}


def test_rate_warning_flags_the_50hz_recordings(tmp_path):
    cfg = LegacyFeatureConfig()
    assert rate_warning(200.0, cfg) is None
    assert rate_warning(177.0, cfg) is None  # thesis file: 200 Hz with packet loss
    msg = rate_warning(40.0, cfg)
    assert "~40 amostras/s" in msg and "200 Hz" in msg

    csv = _synthetic_csv(tmp_path / "s.csv")
    assert estimate_rate_hz(csv) == pytest.approx(200.0, rel=0.01)
    pd.DataFrame({"channel1": [1, 2, 3], "position": [1, 1, 2]}).to_csv(tmp_path / "n.csv")
    assert estimate_rate_hz(tmp_path / "n.csv") is None


def test_analyze_writes_every_figure_and_the_amplitude_reference(tmp_path):
    csv = _synthetic_csv(tmp_path / "synthetic.csv")
    report = analyze(csv, tmp_path / "out", LegacyFeatureConfig(), n_folds=3)
    out = tmp_path / "out" / "synthetic_mav_temporal"
    assert FIGURES <= {p.name for p in out.iterdir()}
    assert report["warning"] is None
    assert set(report["holdout"]) == {"lda", "gnb", "lin_svm", "knn", "tree", "amplitude"}
    assert all("roc_auc" in r for r in report["holdout"].values())
    assert report["cv_folds"] == 3
    assert set(report["cv"]) == {"temporal", "shuffled"}
    assert json.loads((out / "analise.json").read_text())["seed"] == 42
    assert "| amplitude |" in (out / "resumo.md").read_text()
    assert report["cv_participante"] is None  # the thesis files are one person's


def test_participant_validation_when_the_file_says_who_recorded(tmp_path):
    """The gesture set of scripts/fetch_gesture_data.sh: a participante column."""
    frames = []
    for pessoa in (1, 2, 3):
        df = pd.read_csv(_synthetic_csv(tmp_path / f"p{pessoa}.csv", (300, 300), seed=pessoa))
        df.insert(len(df.columns) - 1, "participante", pessoa)
        frames.append(df)
    csv = tmp_path / "gestos.csv"
    pd.concat(frames).to_csv(csv, index=False)
    report = analyze(csv, tmp_path / "out", LegacyFeatureConfig(), n_folds=3)
    grupos = report["cv_participante"]
    assert grupos["participantes"] == ["1", "2", "3"]
    assert set(grupos["acc"]) == set(report["holdout"])
    assert all(len(v) == 3 for v in grupos["acc"].values())
    assert min(grupos["acc"]["lda"]) > 0.9  # amplitude separates the classes for everybody
    resumo = (tmp_path / "out" / "gestos_mav_temporal" / "resumo.md").read_text()
    assert "participante novo" in resumo and "(1, 2, 3)" in resumo


def test_analyze_rejects_a_channel_out_of_range(tmp_path):
    csv = _synthetic_csv(tmp_path / "s.csv")
    with pytest.raises(ValueError, match="channel 9"):
        analyze(csv, tmp_path, LegacyFeatureConfig(), pair=(1, 9))


@needs_data
def test_documented_numbers_of_the_thesis_file(tmp_path):
    """The figures quoted in docs/ANALISE_RESULTADOS.md."""
    legacy = analyze(RAW, tmp_path, LegacyFeatureConfig(feature="rms"), split="legacy")
    for name in ("lda", "gnb", "lin_svm", "knn", "tree"):
        assert legacy["holdout"][name]["accuracy"] == pytest.approx(0.9444, abs=1e-4)

    r = analyze(RAW, tmp_path, LegacyFeatureConfig())
    assert r["warning"] is None
    assert r["n_windows"]["per_class"] == [30, 30]
    assert r["holdout"]["amplitude"]["accuracy"] == 1.0
    assert np.mean(r["cv"]["temporal"]["amplitude"]) == pytest.approx(0.983, abs=1e-3)
    assert r["holdout"]["lda"]["accuracy"] == 0.875
    assert r["holdout"]["lda"]["roc_auc"] == 1.0  # separable, threshold shifted


@needs_data
def test_the_50hz_recordings_are_flagged():
    csv = RAW.parent / "train_with_openCV_list_16_05.csv"
    rate = estimate_rate_hz(csv)
    assert 35 < rate < 45
    assert rate_warning(rate, LegacyFeatureConfig()) is not None
