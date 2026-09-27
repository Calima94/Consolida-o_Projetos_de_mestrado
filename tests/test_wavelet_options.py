"""The choices of the thesis training screen: mother wavelet, levels, layers, window.

The legacy mode (default) is pinned against the original code in
test_features_equivalence.py; these tests cover the options and the corrected
"bands" mode.
"""

import argparse

import numpy as np
import pytest
import pywt
from test_training import _synthetic_csv

from mestrado_emg.features import (
    LegacyFeatureConfig,
    add_pipeline_args,
    config_from_args,
    legacy_wavelet_filter,
)
from mestrado_emg.training import run_name, train_all

RNG = np.random.default_rng(7)
W = RNG.normal(size=(4, 50, 8))  # [windows, samples, channels]


def bands(**kw):
    return LegacyFeatureConfig(wavelet_mode="bands", **kw)


def test_keeping_every_band_gives_the_signal_back():
    cfg = bands(wavelet_layers=(1, 2, 3, 4), wavelet_keep_approx=True)
    np.testing.assert_allclose(legacy_wavelet_filter(W, cfg), W, atol=1e-9)


def test_bands_mode_keeps_exactly_the_chosen_levels():
    cfg = bands(wavelet="db4", wavelet_levels=2, wavelet_layers=(1,))
    coeffs = pywt.wavedec(W, "db4", level=2, axis=1)  # [A2, D2, D1]
    esperado = pywt.waverec(
        [np.zeros_like(coeffs[0]), np.zeros_like(coeffs[1]), coeffs[2]], "db4", axis=1
    )[:, :50, :]
    np.testing.assert_allclose(legacy_wavelet_filter(W, cfg), esperado, atol=1e-12)


def test_in_bands_mode_the_layers_matter():
    a = legacy_wavelet_filter(W, bands(wavelet_layers=(1, 2)))
    b = legacy_wavelet_filter(W, bands(wavelet_layers=(3,)))
    assert not np.allclose(a, b)


@pytest.mark.parametrize(
    "kw, erro",
    [
        ({"wavelet": "db99"}, "unknown discrete wavelet"),
        ({"wavelet_levels": 0}, "wavelet_levels"),
        ({"wavelet_mode": "tudo"}, "wavelet_mode"),
        ({"wavelet_mode": "bands", "wavelet_layers": (5,)}, "outside 1..4"),
        ({"wavelet_mode": "bands", "wavelet_layers": ()}, "keeps nothing"),
    ],
)
def test_invalid_choices_are_refused(kw, erro):
    with pytest.raises(ValueError, match=erro):
        LegacyFeatureConfig(**kw)


def test_frequency_of_each_band_at_200_hz():
    assert LegacyFeatureConfig().bands() == [
        ("D1", 50.0, 100.0),
        ("D2", 25.0, 50.0),
        ("D3", 12.5, 25.0),
        ("D4", 6.25, 12.5),
        ("A4", 0.0, 6.25),
    ]


@pytest.mark.parametrize("wavelet, niveis", [("db7", 1), ("db4", 2), ("sym4", 2), ("haar", 5)])
def test_useful_levels_on_the_thesis_window(wavelet, niveis):
    assert LegacyFeatureConfig(wavelet=wavelet, wavelet_levels=1).max_useful_level == niveis


def test_tag_and_names_only_change_for_new_choices():
    assert LegacyFeatureConfig().tag() == ""
    assert LegacyFeatureConfig(wavelet_layers=(3,)).tag() == ""  # no effect in legacy mode
    assert bands(wavelet_layers=(2, 1), wavelet_keep_approx=True).tag() == "D12A"
    cfg = bands(wavelet="sym4", wavelet_levels=2, wavelet_layers=(1, 2), window_ms=300)
    assert run_name("6_10_20220.csv", cfg, "temporal") == "6-10-20220_mav_temporal_sym4-n2-D12-w300"
    assert run_name("6_10_20220.csv", LegacyFeatureConfig(), "temporal") == (
        "6-10-20220_mav_temporal"
    )


def test_old_bundles_load_as_the_legacy_pipeline():
    antigo = LegacyFeatureConfig().to_dict()
    del antigo["wavelet_mode"], antigo["wavelet_keep_approx"]
    assert LegacyFeatureConfig.from_dict(antigo) == LegacyFeatureConfig()


def _args(*argv):
    p = argparse.ArgumentParser()
    add_pipeline_args(p)
    return p.parse_args(list(argv))


def test_command_line_builds_the_config():
    cfg = config_from_args(
        _args("--wavelet", "sym4", "--levels", "2", "--wavelet-mode", "bands", "--layers", "1",
              "--approx", "--window-ms", "300", "--feature", "rms")
    )  # fmt: skip
    assert (cfg.wavelet, cfg.wavelet_levels, cfg.wavelet_mode) == ("sym4", 2, "bands")
    assert (cfg.wavelet_layers, cfg.wavelet_keep_approx) == ((1,), True)
    assert (cfg.window_ms, cfg.feature) == (300.0, "rms")
    assert config_from_args(_args()) == LegacyFeatureConfig()


def test_command_line_explains_a_bad_choice_and_warns_about_boundary_effects(capsys):
    with pytest.raises(SystemExit, match="unknown discrete wavelet"):
        config_from_args(_args("--wavelet", "db99"))
    config_from_args(_args())
    assert "1 nível(is) útil(eis)" in capsys.readouterr().out


def test_models_of_another_setup_do_not_overwrite_the_thesis_ones(tmp_path):
    csv = _synthetic_csv(tmp_path / "gravacao.csv")
    train_all(csv, tmp_path, LegacyFeatureConfig(), date="2026-01-01")
    train_all(csv, tmp_path, bands(wavelet="db4", wavelet_levels=2), date="2026-01-01")
    nomes = sorted(p.name for p in tmp_path.glob("knn_*_latest.joblib"))
    assert nomes == [
        "knn_gravacao_mav_temporal_db4-n2-D12_latest.joblib",
        "knn_gravacao_mav_temporal_latest.joblib",
    ]


def test_the_choices_are_described_in_logs_and_summaries():
    assert (
        LegacyFeatureConfig()
        .describe()
        .endswith("janela 250 ms, db7 com 4 níveis, como no mestrado (só D4 removido)")
    )
    cfg = bands(wavelet="sym4", wavelet_levels=2, wavelet_layers=(2, 1), wavelet_keep_approx=True)
    assert cfg.describe().endswith(
        "janela 250 ms, sym4 com 2 níveis, faixas mantidas: D1 + D2 + A2"
    )
