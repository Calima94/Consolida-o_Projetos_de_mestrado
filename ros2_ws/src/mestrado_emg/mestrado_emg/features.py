"""Faithful re-implementation of the master's thesis sEMG feature pipeline.

The original code lives in two places that were kept in sync by hand:

- ``Train_Myo_Signals/mod_sig_emg.py`` (training), and
- ``my_arm_def/src/my_arm_def_py_pkg/my_arm_def_py_pkg/mod_sig_emg.py`` +
  ``capture_simple_sample.py`` (live inference).

Pipeline, per non-overlapping window of ``window_ms`` at ``fs_hz``::

    high-pass IIR (SOS) -> band-stop IIR (SOS) -> wavelet reconstruction -> MAV or RMS

Each filter starts from a zero state **per window** (``scipy.signal.sosfilt``
without ``zi``), exactly as in the original code. Because both IIR stages are
linear and time-invariant with zero initial state, their order does not change
the result; the training code applied them in the opposite order to the live
code, and that is harmless.

Known legacy quirk reproduced on purpose (see ``docs/INVENTARIO_MESTRADO.md``):
the wavelet loop ``for i in range(1, -1, -(levels + 1))`` visits only ``i = 1``,
so only the coarsest detail band (``cD<levels>``) can ever be zeroed and the
``wavelet_layers`` setting is effectively ignored beyond that single check.
Changing this would change the features the historical classifiers saw, so the
behaviour is kept and pinned by a golden test against the original code.
"""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
import pywt
from scipy import signal

# Named ``sos_low_pass_`` in capture_simple_sample.py, but the numerator
# sections are [1, -2, 1] (double zero at DC): it is a high-pass filter.
# The original comment reads "10 Hz stop / 15 Hz pass, 60 dB".
LEGACY_SOS_HIGHPASS = np.array(
    [
        [
            1,
            -2,
            1,
            1,
            -1.740367670683557577149258577264845371246,
            0.93092862335376458382540931779658421874,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.629360431136253506423372527933679521084,
            0.80776668472892854122591188570368103683,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.535449319165865356140443509502802044153,
            0.703572808222718393267314240802079439163,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.457344522530261921033911676204297691584,
            0.616915954050245685102993320469977334142,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.393730553043875275420759862754493951797,
            0.546336595104689237700767989736050367355,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.343402365227919670331857560086064040661,
            0.490497739871769145025837133289314806461,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.305336827562876278463477319746743887663,
            0.448264229402160208071137503793579526246,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.278726258361997381030050746630877256393,
            0.418739945183796424821309756225673481822,
        ],
        [
            1,
            -2,
            1,
            1,
            -1.262991469218308848709853009495418518782,
            0.401282280776567523705722351223812438548,
        ],
        [1, -1, 0, 1, -0.628892547371665888711333991523133590817, 0.0],
    ]
)

# Band-stop around the mains frequency ("55 Hz stop / 65 Hz pass" in the
# original parameters.csv description).
LEGACY_SOS_BANDSTOP = np.array(
    [
        [1, 0.622946104851632931342919619055464863777, 1, 1, 0.409261284246611789505720935267163440585, 0.944930685706123152378665963624371215701],
        [1, 0.622946104851632931342919619055464863777, 1, 1, 0.790937366004399455832185594772454351187, 0.948426893239073809382944091339595615864],
        [1, 0.622946104851632931342919619055464863777, 1, 1, 0.711063241242363974770057666319189593196, 0.863346362516600351888484965456882491708],
        [1, 0.622946104851632931342919619055464863777, 1, 1, 0.441523156151951257086807345331180840731, 0.856895681601938186133793351473286747932],
        [1, 0.622946104851632931342919619055464863777, 1, 1, 0.612695780882883012097295249986927956343, 0.814392565084377184625452628097264096141],
        [1, 0.622946104851632931342919619055464863777, 1, 1, 0.515815447012487493516630365775199607015, 0.811296756704375288116182218800531700253],
    ]
)  # fmt: skip

FeatureType = Literal["mav", "rms"]


@dataclass(frozen=True)
class LegacyFeatureConfig:
    """Parameters of the master's thesis feature pipeline.

    Defaults are the values used by the live classifier in ``my_arm_def``
    (``capture_simple_sample.py``): Myo raw mode at 200 Hz, 250 ms windows,
    8 channels, Daubechies-7 wavelet with 4 levels, MAV features.

    Examples
    --------
    >>> LegacyFeatureConfig().samples_per_window
    50
    """

    fs_hz: float = 200.0
    window_ms: float = 250.0
    n_channels: int = 8
    wavelet: str = "db7"
    wavelet_levels: int = 4
    wavelet_layers: tuple[int, ...] = (1, 2)
    feature: FeatureType = "mav"
    sos_highpass: tuple[tuple[float, ...], ...] = field(
        default=tuple(map(tuple, LEGACY_SOS_HIGHPASS.tolist())), repr=False
    )
    sos_bandstop: tuple[tuple[float, ...], ...] = field(
        default=tuple(map(tuple, LEGACY_SOS_BANDSTOP.tolist())), repr=False
    )

    def __post_init__(self) -> None:
        if self.feature not in ("mav", "rms"):
            raise ValueError(f"feature must be 'mav' or 'rms', got {self.feature!r}")
        if self.samples_per_window < 1:
            raise ValueError("window_ms is shorter than one sample period")

    @classmethod
    def for_sensor(
        cls,
        fs_hz: float,
        n_channels: int,
        highpass_hz: float = 20.0,
        mains_hz: float = 60.0,
        **kwargs,
    ) -> LegacyFeatureConfig:
        """Same pipeline with IIR stages redesigned for another sensor.

        The legacy SOS coefficients only make sense at 200 Hz (Myo). For any
        other sampling rate this builds a 4th-order Butterworth high-pass at
        ``highpass_hz`` and a 2nd-order Butterworth band-stop at
        ``mains_hz +- 5 Hz`` (skipped when the mains frequency is above
        Nyquist). This is a **new design**, not the thesis one, so models must
        be retrained.

        Examples
        --------
        >>> cfg = LegacyFeatureConfig.for_sensor(fs_hz=1000.0, n_channels=4)
        >>> cfg.samples_per_window
        250
        """
        hp = signal.butter(4, highpass_hz, btype="highpass", fs=fs_hz, output="sos")
        if mains_hz + 5.0 < fs_hz / 2.0:
            bs = signal.butter(
                2,
                [mains_hz - 5.0, mains_hz + 5.0],
                btype="bandstop",
                fs=fs_hz,
                output="sos",
            )
        else:
            bs = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]])  # identity section
        return cls(
            fs_hz=fs_hz,
            n_channels=n_channels,
            sos_highpass=tuple(map(tuple, hp.tolist())),
            sos_bandstop=tuple(map(tuple, bs.tolist())),
            **kwargs,
        )

    @property
    def samples_per_window(self) -> int:
        """Number of samples per window, computed as in the legacy code."""
        time_between_samples_ms = (1.0 / self.fs_hz) * 1000.0
        return int(self.window_ms / time_between_samples_ms)

    def to_dict(self) -> dict:
        """Serialisable representation (stored next to trained models)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> LegacyFeatureConfig:
        """Inverse of :meth:`to_dict`."""
        data = dict(data)
        for key in ("wavelet_layers",):
            if key in data:
                data[key] = tuple(data[key])
        for key in ("sos_highpass", "sos_bandstop"):
            if key in data:
                data[key] = tuple(tuple(row) for row in data[key])
        return cls(**data)


def segment_windows(samples: np.ndarray, config: LegacyFeatureConfig) -> np.ndarray:
    """Cut a continuous recording into non-overlapping windows.

    Trailing samples that do not fill a whole window are dropped, as in the
    legacy ``standardize_classes`` + ``sample_classes_`` pair.

    Parameters
    ----------
    samples : np.ndarray
        Array of shape ``[n_samples, n_channels]``.
    config : LegacyFeatureConfig
        Pipeline parameters.

    Returns
    -------
    np.ndarray
        Array of shape ``[n_windows, samples_per_window, n_channels]``.
    """
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 2 or samples.shape[1] != config.n_channels:
        raise ValueError(
            f"expected samples with shape [n_samples, {config.n_channels}], got {samples.shape}"
        )
    win = config.samples_per_window
    n_windows = samples.shape[0] // win
    # -> [n_windows, samples_per_window, n_channels]
    return samples[: n_windows * win].reshape(n_windows, win, config.n_channels)


def legacy_wavelet_filter(x: np.ndarray, config: LegacyFeatureConfig) -> np.ndarray:
    """Wavelet decomposition/reconstruction exactly as in the legacy code.

    Operates along axis 1 of a ``[n_windows, samples_per_window, n_channels]``
    array. See the module docstring for the reproduced loop quirk.
    """
    with warnings.catch_warnings():
        # 4 levels of db7 on 50 samples exceeds pywt's maximum useful level and
        # warns about boundary effects; that is the thesis configuration.
        warnings.filterwarnings("ignore", message="Level value of .* is too high")
        coeffs = pywt.wavedec(x, config.wavelet, level=config.wavelet_levels, axis=1)
    # Verbatim loop bounds from the original wav_filter(); visits only i = 1.
    for i in range(1, -1, -(config.wavelet_levels + 1)):
        if -i not in config.wavelet_layers:
            coeffs[i] = np.zeros_like(coeffs[i])
    rec = pywt.waverec(coeffs, config.wavelet, axis=1)
    # -> [n_windows, samples_per_window, n_channels] (waverec may pad by one)
    return rec[:, : x.shape[1], :]


def filter_windows(windows: np.ndarray, config: LegacyFeatureConfig) -> np.ndarray:
    """Apply high-pass, band-stop and wavelet stages to each window independently."""
    out = signal.sosfilt(np.asarray(config.sos_highpass), windows, axis=1)
    out = signal.sosfilt(np.asarray(config.sos_bandstop), out, axis=1)
    return legacy_wavelet_filter(out, config)


def window_features(filtered: np.ndarray, feature: FeatureType) -> np.ndarray:
    """Reduce each window to one value per channel (MAV or RMS).

    Returns an array of shape ``[n_windows, n_channels]``.
    """
    if feature == "mav":
        return np.mean(np.abs(filtered), axis=1)
    if feature == "rms":
        return np.sqrt(np.mean(filtered**2, axis=1))
    raise ValueError(f"unknown feature {feature!r}")


def extract_features(samples: np.ndarray, config: LegacyFeatureConfig) -> np.ndarray:
    """Full pipeline: continuous samples -> 2D feature matrix.

    Parameters
    ----------
    samples : np.ndarray
        Raw sEMG, shape ``[n_samples, n_channels]``.
    config : LegacyFeatureConfig
        Pipeline parameters.

    Returns
    -------
    np.ndarray
        Features, shape ``[n_windows, n_channels]``, ready for scikit-learn.

    Examples
    --------
    >>> cfg = LegacyFeatureConfig()
    >>> extract_features(np.zeros((100, 8)), cfg).shape
    (2, 8)
    """
    windows = segment_windows(samples, config)
    if windows.shape[0] == 0:
        return np.empty((0, config.n_channels))
    return window_features(filter_windows(windows, config), config.feature)
