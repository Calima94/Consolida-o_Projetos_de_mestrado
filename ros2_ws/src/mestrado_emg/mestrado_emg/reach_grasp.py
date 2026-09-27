"""Read the elbow angle of a Reach&Grasp trial (Vicon) for the simulator.

Reach&Grasp (Di Domenico et al., Scientific Data 12, 233, 2025; IIT Dataverse
DOI 10.48557/L6OWMM, version 1.0, CC BY 4.0) records the elbow of healthy
subjects with a Vicon system at 100 Hz while they reach, grasp and manipulate
objects. The data contract of ``semg-digital-twins``
(``docs/DATA_CONTRACT_REACH_GRASP.md``) describes the files; the points used
here are:

* ``sub-XX/motion/sub-XX_task-YY_acq-vicon_motion.csv`` has no header: time in
  seconds, then one column per channel, in the order of the ``_channels.tsv``;
* the elbow has one degree of freedom, ``RElbow_X`` (``RElbow_Y``/``Z`` are
  numerically zero), in degrees; reaching lowers it and bringing the hand to
  the mouth raises it, which fits 0 deg = extended;
* a few trials have missing samples (``NaN``) in the elbow.

The simulator elbow (``mestrado_description``) is also 0 when extended, so the
Vicon angle goes straight to ``/arm/elbow/cmd_pos`` in radians, without the
180 deg - angle used for the camera. That convention is **not confirmed** in
the Plug-in-Gait documentation; replaying a real movement is how it is checked
by eye (``docs/DECISOES.md``, D27).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DATASET_DOI = "10.48557/L6OWMM"
ELBOW_CHANNEL = "RElbow_X"
TASKS = (
    "HO",
    "HC",
    "WF",
    "WE",
    "WP",
    "WS",
    "Thumb",
    "Cyl",
    "Sph",
    "Trid",
    "FroRea",
    "ReaCyl",
    "ReaSph",
    "Pour",
    "Screw",
    "EatFruit",
)
# Tasks whose elbow excursion is large (median over subjects 31 to 96 deg,
# measured in the data contract); in the others the elbow barely moves.
ELBOW_TASKS = ("FroRea", "ReaCyl", "ReaSph", "Pour", "Screw", "EatFruit")


@dataclass
class ViconTrial:
    """One Vicon recording.

    Attributes
    ----------
    times : np.ndarray
        Seconds, ``[n_samples]``.
    channels : list of str
        Channel names, in file order.
    data : np.ndarray
        Angles in degrees, ``[n_samples, n_channels]`` (may contain NaN).
    rate_hz : float
        Sampling rate declared in the ``.json`` sidecar.
    """

    times: np.ndarray
    channels: list[str]
    data: np.ndarray
    rate_hz: float

    def channel(self, name: str) -> np.ndarray:
        """Column ``name`` as a 1-D array (raises if absent)."""
        if name not in self.channels:
            raise KeyError(f"channel {name} not in {self.channels}")
        return self.data[:, self.channels.index(name)]


def trial_paths(root: str | Path, subject: str, task: str) -> dict[str, Path]:
    """Paths of the Vicon CSV, channels TSV and JSON sidecar of one trial."""
    sub = f"sub-{int(subject):02d}"
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; one of {', '.join(TASKS)}")
    stem = Path(root) / sub / "motion" / f"{sub}_task-{task}_acq-vicon"
    return {
        "csv": stem.with_name(stem.name + "_motion.csv"),
        "tsv": stem.with_name(stem.name + "_channels.tsv"),
        "json": stem.with_name(stem.name + "_motion.json"),
    }


def load_vicon(root: str | Path, subject: str, task: str) -> ViconTrial:
    """Load one trial and check it against its sidecars.

    Raises
    ------
    FileNotFoundError
        With the command that downloads the data, if a file is missing.
    ValueError
        If a row does not have one column per channel plus time.
    """
    paths = trial_paths(root, subject, task)
    for p in paths.values():
        if not p.exists():
            raise FileNotFoundError(
                f"{p} not found; download it with scripts/fetch_reach_grasp.py "
                f"--subjects {int(subject):02d} --tasks {task}"
            )
    with open(paths["tsv"], newline="") as fh:
        channels = [row["name"] for row in csv.DictReader(fh, delimiter="\t")]
    rate = float(json.loads(paths["json"].read_text())["SamplingFrequency"])
    rows = []
    with open(paths["csv"], newline="") as fh:
        for i, rec in enumerate(csv.reader(fh)):
            if len(rec) != len(channels) + 1:
                raise ValueError(
                    f"{paths['csv']} line {i + 1}: {len(rec)} columns, "
                    f"expected {len(channels) + 1} (time + {len(channels)} channels)"
                )
            rows.append([float(v) for v in rec])
    table = np.asarray(rows, dtype=float)  # -> [n_samples, 1 + n_channels]
    return ViconTrial(times=table[:, 0], channels=channels, data=table[:, 1:], rate_hz=rate)


def hold_last_valid(values: np.ndarray) -> tuple[np.ndarray, int]:
    """Replace NaN by the last valid value (leading NaN: the first valid one).

    For replaying a target, a missing Vicon sample means "keep the last
    target"; nothing is interpolated. Returns the filled copy and how many
    samples were missing.

    Examples
    --------
    >>> hold_last_valid(np.array([np.nan, 1.0, np.nan, 3.0]))
    (array([1., 1., 1., 3.]), 2)
    """
    out = np.array(values, dtype=float)
    missing = ~np.isfinite(out)
    n_missing = int(missing.sum())
    if n_missing == len(out):
        raise ValueError("no valid sample")
    if n_missing:
        idx = np.where(~missing, np.arange(len(out)), 0)
        np.maximum.accumulate(idx, out=idx)
        first = int(np.argmax(~missing))
        idx[:first] = first
        out = out[idx]
    return out, n_missing


def elbow_target_rad(trial: ViconTrial) -> tuple[np.ndarray, int]:
    """Simulator elbow target (rad) from ``RElbow_X`` (deg), gaps held.

    Returns the targets and the number of missing Vicon samples that were
    held at the previous value.
    """
    deg, n_missing = hold_last_valid(trial.channel(ELBOW_CHANNEL))
    return np.radians(deg), n_missing


def describe(trial: ViconTrial) -> str:
    """One line for the log: duration, rate and elbow range."""
    x = trial.channel(ELBOW_CHANNEL)
    ok = x[np.isfinite(x)]
    dur = float(trial.times[-1] - trial.times[0]) if len(trial.times) > 1 else 0.0
    text = f"{len(trial.times)} samples, {dur:.1f} s at {trial.rate_hz:g} Hz, "
    if not len(ok):
        return text + "no valid elbow sample"
    text += f"{ELBOW_CHANNEL} {ok.min():.1f} to {ok.max():.1f} deg"
    if len(ok) < len(x):
        text += f", {len(x) - len(ok)} missing"
    return text


def is_elbow_task(task: str) -> bool:
    """True for the tasks that move the elbow (``ELBOW_TASKS``)."""
    return task in ELBOW_TASKS


__all__ = [
    "DATASET_DOI",
    "ELBOW_CHANNEL",
    "ELBOW_TASKS",
    "TASKS",
    "ViconTrial",
    "describe",
    "elbow_target_rad",
    "hold_last_valid",
    "is_elbow_task",
    "load_vicon",
    "trial_paths",
]
