"""The ported feature pipeline must match the thesis code bit-for-bit (up to fp)."""

import numpy as np
import pytest

from legacy_reference import train_myo_signals_mod_sig_emg as legacy
from mestrado_emg.features import (
    LegacyFeatureConfig,
    extract_features,
    legacy_wavelet_filter,
    segment_windows,
)

CFG = LegacyFeatureConfig()


def _legacy_pipeline(classes, feature):
    """Run the verbatim thesis functions exactly as train_signals_emg.py did."""
    ts, win_ms, nch = 5.0, 250.0, 8
    classes = [c[: int((len(c) // 50) * 50)] for c in classes]
    cm = legacy.sample_classes_(np.array(classes, dtype=object), ts, win_ms, nch)
    cm = legacy.filter_signal(cm, np.array(CFG.sos_highpass), nch)
    cm = legacy.filter_signal(cm, np.array(CFG.sos_bandstop), nch)
    cm = legacy.select_wavelet_layer_x(cm, "db7", 4, [1, 2], nch)
    return [np.asarray(m, dtype=float) for m in legacy.matrix_m(feature, cm, ts, win_ms, nch)]


@pytest.mark.parametrize("feature", ["mav", "rms"])
def test_matches_verbatim_legacy_code(feature):
    rng = np.random.default_rng(0)
    # Different lengths per class, as in the real data (the legacy code relies
    # on ragged object arrays).
    classes = [rng.normal(scale=20, size=(523, 8)), rng.normal(scale=35, size=(311, 8))]
    expected = _legacy_pipeline(classes, feature)
    cfg = LegacyFeatureConfig(feature=feature)
    for raw, ref in zip(classes, expected, strict=True):
        np.testing.assert_allclose(extract_features(raw, cfg), ref, rtol=1e-10, atol=1e-9)


def test_defaults_are_the_live_thesis_parameters():
    assert CFG.fs_hz == 200.0
    assert CFG.samples_per_window == 50  # 250 ms at 200 Hz
    assert CFG.n_channels == 8
    assert (CFG.wavelet, CFG.wavelet_levels) == ("db7", 4)
    assert CFG.feature == "mav"  # what my_arm_def computed live


def test_segment_windows_drops_the_incomplete_tail():
    x = np.arange(130 * 8, dtype=float).reshape(130, 8)
    w = segment_windows(x, CFG)
    assert w.shape == (2, 50, 8)
    np.testing.assert_array_equal(w[1, 0], x[50])


def test_segment_windows_rejects_wrong_channel_count():
    with pytest.raises(ValueError, match="n_samples, 8"):
        segment_windows(np.zeros((100, 4)), CFG)


def test_too_short_input_gives_empty_matrix():
    assert extract_features(np.zeros((49, 8)), CFG).shape == (0, 8)


def test_wavelet_layers_setting_is_effectively_ignored():
    """Pins the reproduced legacy quirk: only cD4 is zeroed, whatever the layers."""
    rng = np.random.default_rng(1)
    w = rng.normal(size=(3, 50, 8))
    a = legacy_wavelet_filter(w, LegacyFeatureConfig(wavelet_layers=(1, 2)))
    b = legacy_wavelet_filter(w, LegacyFeatureConfig(wavelet_layers=(3,)))
    np.testing.assert_array_equal(a, b)
    assert a.shape == w.shape


def test_config_roundtrip():
    cfg = LegacyFeatureConfig(feature="rms", window_ms=200.0)
    assert LegacyFeatureConfig.from_dict(cfg.to_dict()) == cfg


def test_invalid_feature_rejected():
    with pytest.raises(ValueError, match="mav"):
        LegacyFeatureConfig(feature="wl")


def test_for_sensor_redesigns_filters():
    cfg = LegacyFeatureConfig.for_sensor(fs_hz=1000.0, n_channels=4)
    assert cfg.samples_per_window == 250
    assert cfg.sos_highpass != CFG.sos_highpass
    # A pure 60 Hz tone is attenuated by the band-stop, a 150 Hz one is not.
    t = np.arange(2000) / 1000.0
    tone60 = np.tile(np.sin(2 * np.pi * 60 * t)[:, None], (1, 4))
    tone150 = np.tile(np.sin(2 * np.pi * 150 * t)[:, None], (1, 4))
    cfg_rms = LegacyFeatureConfig.for_sensor(fs_hz=1000.0, n_channels=4, feature="rms")
    f60 = extract_features(tone60, cfg_rms)[1:].mean()
    f150 = extract_features(tone150, cfg_rms)[1:].mean()
    assert f60 < 0.2 * f150


def test_for_sensor_without_mains_band_below_nyquist():
    cfg = LegacyFeatureConfig.for_sensor(fs_hz=100.0, n_channels=2)
    assert cfg.sos_bandstop == ((1.0, 0.0, 0.0, 1.0, 0.0, 0.0),)
