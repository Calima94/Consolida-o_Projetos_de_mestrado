"""Labelling sEMG with elbow-angle categories, ported from Capture_EMG_Data.

Thesis behaviour (capture_myo_not_filtered_signal_200hz.py + pose_module.py):

- categories are angles, by default ``[170, 90, 60, 45]`` deg, of which the
  first ``n_categories`` (2 to 4) are used;
- an sEMG sample is recorded only while the measured angle lies strictly
  inside ``angle +- tolerance`` of a category that is not yet complete; it is
  labelled with that category (1-based, "position" column);
- a category is complete once it has ``samples_per_category`` samples;
  the capture ends when all categories are complete.

Fixed here (see docs/INVENTARIO_MESTRADO.md, finding 17): the thesis decided
completion from ``Counter(labels).values()`` enumerated in order, so if a later
category had samples before an earlier one, the *earlier* one was marked
complete. Completion is now counted per category.

New, optional (``continuous=True``): every sample is recorded with the
measured angle, labelled 0 outside categories. This is the ground truth needed
for continuous angle regression. ``train_legacy`` ignores label 0.

Output CSV keeps the thesis columns (``time, channel1..N, position``) with an
extra ``angle_deg`` column before ``position``, so the files still load with
``mestrado_emg.training.load_legacy_csv``.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

LEGACY_CATEGORY_ANGLES_DEG = (170.0, 90.0, 60.0, 45.0)


@dataclass
class CategoryRecorder:
    """Accumulates labelled sEMG samples following the thesis protocol.

    Examples
    --------
    >>> rec = CategoryRecorder(n_categories=2, tolerance_deg=10, samples_per_category=2)
    >>> rec.add(np.ones((2, 8)), angle_deg=172.0, t_end=0.01)
    True
    >>> rec.complete
    [True, False]
    >>> rec.add(np.ones((2, 8)), angle_deg=172.0, t_end=0.02)  # category 1 is full
    False
    """

    n_categories: int = 2
    tolerance_deg: float = 10.0
    samples_per_category: int = 1000
    category_angles_deg: tuple[float, ...] = LEGACY_CATEGORY_ANGLES_DEG
    n_channels: int = 8
    fs_hz: float = 200.0
    continuous: bool = False
    counts: list[int] = field(init=False)
    _rows: list[np.ndarray] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 1 <= self.n_categories <= len(self.category_angles_deg):
            raise ValueError(f"n_categories must be between 1 and {len(self.category_angles_deg)}")
        self.category_angles_deg = tuple(self.category_angles_deg[: self.n_categories])
        self.counts = [0] * self.n_categories
        self._rows = []

    @property
    def complete(self) -> list[bool]:
        return [c >= self.samples_per_category for c in self.counts]

    @property
    def done(self) -> bool:
        return all(self.complete)

    @property
    def n_rows(self) -> int:
        return sum(len(r) for r in self._rows)

    def category_for(self, angle_deg: float | None) -> int | None:
        """First incomplete category whose open interval contains the angle."""
        if angle_deg is None:
            return None
        for i, target in enumerate(self.category_angles_deg):
            if not self.complete[i] and target - self.tolerance_deg < angle_deg < (
                target + self.tolerance_deg
            ):
                return i
        return None

    def add(self, samples: np.ndarray, angle_deg: float | None, t_end: float) -> bool:
        """Offer a batch of samples measured at ``angle_deg``; return True if labelled.

        ``t_end`` is the time (s) of the last sample; earlier samples of the
        batch are spaced by ``1 / fs_hz``.
        """
        samples = np.asarray(samples, dtype=float)
        if samples.ndim != 2 or samples.shape[1] != self.n_channels:
            raise ValueError(f"expected [n, {self.n_channels}] samples, got {samples.shape}")
        cat = self.category_for(angle_deg)
        if cat is None and not self.continuous:
            return False
        n = len(samples)
        times = t_end - (n - 1 - np.arange(n)) / self.fs_hz
        angle = np.nan if angle_deg is None else angle_deg
        label = 0 if cat is None else cat + 1
        # -> [n, 1 + n_channels + 2]: time, channels..., angle_deg, position
        self._rows.append(np.column_stack([times, samples, np.full(n, angle), np.full(n, label)]))
        if cat is not None:
            self.counts[cat] += n
        return cat is not None

    def status_text(self) -> str:
        """One-line progress, e.g. ``170°: 400/1000 | 90°: ok``."""
        parts = []
        for target, count, ok in zip(
            self.category_angles_deg, self.counts, self.complete, strict=True
        ):
            parts.append(
                f"{target:g} graus: {'ok' if ok else f'{count}/{self.samples_per_category}'}"
            )
        return " | ".join(parts)

    def to_dataframe(self) -> pd.DataFrame:
        columns = (
            ["time"]
            + [f"channel{i}" for i in range(1, self.n_channels + 1)]
            + ["angle_deg", "position"]
        )
        data = np.vstack(self._rows) if self._rows else np.empty((0, len(columns)))
        df = pd.DataFrame(data, columns=columns)
        df["position"] = df["position"].astype(int)
        return df

    def save(self, out_dir: str | os.PathLike, prefix: str = "captura") -> Path:
        """Write ``<prefix>_<date><n>.csv`` without overwriting, as the thesis did."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{prefix}_{dt.date.today().isoformat()}"
        u = 0
        while (out_dir / f"{stem}{u}.csv").exists():
            u += 1
        path = out_dir / f"{stem}{u}.csv"
        self.to_dataframe().to_csv(path, index=False)
        return path
