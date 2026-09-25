"""Retrain the master's thesis classifiers from the raw Myo CSV recordings.

Why retrain instead of reusing the ``*_teste.joblib`` files: the historical
models were pickled with scikit-learn 1.1 and two of them (k-NN, which was the
one used live, and the decision tree) no longer unpickle on current
scikit-learn. See ``docs/INVENTARIO_MESTRADO.md``.

Each trained model is saved as a *bundle* that carries the feature
configuration, the class-to-angle map and provenance (seed, split, source file
hash), so training and inference can no longer disagree on the feature type --
a mismatch that existed in the legacy code (``rms`` in ``parameters.csv`` vs
``mav`` in the live node).

Two evaluation splits are available:

``legacy``
    ``StratifiedShuffleSplit`` over windows (test_size=0.3, random_state=42),
    exactly as in the thesis code. Kept **only** to reproduce the historical
    numbers: adjacent 250 ms windows of the same recording land in both train
    and test, so the score is optimistic.
``temporal``
    Blocked hold-out inside each class: the first ``1 - test_size`` of the
    windows (in recording order) train, the rest test, with ``purge_windows``
    windows discarded at the boundary. This is the honest within-subject
    estimate. The recordings are single-subject, so no inter-subject claim can
    be made from either split.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn import svm
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier

from mestrado_emg.features import LegacyFeatureConfig, extract_features

BUNDLE_FORMAT = "mestrado-emg-bundle/1"

# Elbow targets (degrees, simulator convention: 0 = extended) indexed by the
# predicted class, from my_arm_def/.../myo_raw.py (POSITIONS_TO_USE). The
# capture tool labelled category 1 at ~170 deg and category 2 at ~90 deg of
# anatomical elbow angle, so class 0 -> 0 deg and class 1 -> 90 deg here.
LEGACY_CLASS_ANGLES_DEG = (0.0, 90.0, 120.0, 135.0, 150.0)

SplitMode = Literal["legacy", "temporal"]


@dataclass
class WindowDataset:
    """Feature matrix plus the bookkeeping needed for splitting.

    Attributes
    ----------
    X : np.ndarray
        Features, ``[n_windows, n_channels]``.
    y : np.ndarray
        Class index per window (0..K-1, sorted by original label).
    order : np.ndarray
        Position of each window inside its class, in recording order.
    class_labels : list
        Original label value for each class index.
    """

    X: np.ndarray
    y: np.ndarray
    order: np.ndarray
    class_labels: list


def load_legacy_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read a Capture_EMG_Data CSV the same way ``read_data`` did.

    Column names are stripped and lower-cased; channel columns are those
    starting with ``chanel``/``channel`` (both spellings exist in the data) and
    the label is the last column.

    Returns
    -------
    tuple of np.ndarray
        ``samples`` with shape ``[n_samples, n_channels]`` and ``labels`` with
        shape ``[n_samples]``.
    """
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    channel_cols = [c for c in df.columns if re.match(r"^(chanel|channel)", c)]
    if not channel_cols:
        raise ValueError(f"no channel columns found in {path}")
    return df[channel_cols].to_numpy(dtype=float), df[df.columns[-1]].to_numpy()


def build_dataset(
    samples: np.ndarray, labels: np.ndarray, config: LegacyFeatureConfig
) -> WindowDataset:
    """Group samples by label and extract windowed features per class.

    As in the legacy ``spare_classes_``, every class is the concatenation of
    its rows in file order; windows never mix two classes.
    """
    class_labels = sorted(pd.unique(labels).tolist())
    xs, ys, orders = [], [], []
    for idx, label in enumerate(class_labels):
        feats = extract_features(samples[labels == label], config)
        xs.append(feats)
        ys.append(np.full(len(feats), idx))
        orders.append(np.arange(len(feats)))
    return WindowDataset(
        X=np.vstack(xs),
        y=np.concatenate(ys),
        order=np.concatenate(orders),
        class_labels=class_labels,
    )


def split_indices(
    ds: WindowDataset,
    mode: SplitMode,
    test_size: float = 0.3,
    seed: int = 42,
    purge_windows: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Return train and test window indices for the requested split mode."""
    if mode == "legacy":
        sss = StratifiedShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train_idx, test_idx = next(sss.split(ds.X, ds.y))
        return np.sort(train_idx), np.sort(test_idx)
    if mode == "temporal":
        train_parts, test_parts = [], []
        for cls in np.unique(ds.y):
            idx = np.flatnonzero(ds.y == cls)
            idx = idx[np.argsort(ds.order[idx])]
            n_train = int(round(len(idx) * (1.0 - test_size)))
            train_parts.append(idx[:n_train])
            test_parts.append(idx[n_train + purge_windows :])
        return np.concatenate(train_parts), np.concatenate(test_parts)
    raise ValueError(f"unknown split mode {mode!r}")


def make_classifiers(seed: int) -> dict:
    """The five thesis classifiers with their original hyper-parameters.

    ``lin_svm`` keeps its historical name, but the original code built
    ``svm.SVC(decision_function_shape='ovo')``, i.e. an **RBF** kernel.
    The decision tree gets ``random_state=seed`` (the original had none, which
    made it non-reproducible).
    """
    return {
        "lda": LinearDiscriminantAnalysis(),
        "gnb": GaussianNB(),
        "lin_svm": svm.SVC(decision_function_shape="ovo"),
        "knn": KNeighborsClassifier(n_neighbors=5),
        "tree": DecisionTreeClassifier(random_state=seed),
    }


def sha256_of(path: str | Path) -> str:
    """Hex SHA-256 of a file, used to pin the training data version."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def train_all(
    csv_path: str | Path,
    out_dir: str | Path,
    config: LegacyFeatureConfig,
    split: SplitMode = "temporal",
    seed: int = 42,
    test_size: float = 0.3,
    purge_windows: int = 1,
    class_angles_deg: tuple[float, ...] = LEGACY_CLASS_ANGLES_DEG,
    date: str | None = None,
) -> dict:
    """Train the five classifiers, save bundles and a JSON report.

    Returns
    -------
    dict
        The report that is also written to ``<out_dir>/report_<...>.json``.
    """
    csv_path = Path(csv_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = date or dt.date.today().isoformat()

    samples, labels = load_legacy_csv(csv_path)
    if samples.shape[1] != config.n_channels:
        raise ValueError(f"{csv_path} has {samples.shape[1]} channels, config expects {config.n_channels}")
    ds = build_dataset(samples, labels, config)
    if len(ds.class_labels) > len(class_angles_deg):
        raise ValueError("more classes than entries in class_angles_deg")
    train_idx, test_idx = split_indices(ds, split, test_size, seed, purge_windows)

    source = {"path": csv_path.name, "sha256": sha256_of(csv_path)}
    report = {
        "seed": seed,
        "split": split,
        "test_size": test_size,
        "purge_windows": purge_windows if split == "temporal" else None,
        "feature_config": {k: v for k, v in config.to_dict().items() if not k.startswith("sos_")},
        "source": source,
        "class_labels": [str(c) for c in ds.class_labels],
        "n_windows": {"train": int(len(train_idx)), "test": int(len(test_idx))},
        "sklearn_version": sklearn.__version__,
        "results": {},
    }
    stem = re.sub(r"[^A-Za-z0-9]+", "-", csv_path.stem).strip("-")
    for name, clf in make_classifiers(seed).items():
        clf.fit(ds.X[train_idx], ds.y[train_idx])
        pred = clf.predict(ds.X[test_idx])
        report["results"][name] = {
            "accuracy": float(accuracy_score(ds.y[test_idx], pred)),
            "balanced_accuracy": float(balanced_accuracy_score(ds.y[test_idx], pred)),
            "confusion_matrix": confusion_matrix(ds.y[test_idx], pred).tolist(),
        }
        bundle = {
            "format": BUNDLE_FORMAT,
            "classifier": name,
            "model": clf,
            "feature_config": config.to_dict(),
            "class_labels": ds.class_labels,
            "class_angles_deg": list(class_angles_deg[: len(ds.class_labels)]),
            "seed": seed,
            "split": split,
            "source": source,
            "sklearn_version": sklearn.__version__,
            "created": date,
        }
        joblib.dump(bundle, out_dir / f"{name}_{stem}_{config.feature}_{split}_{date}.joblib")

    report_path = out_dir / f"report_{stem}_{config.feature}_{split}_{date}.json"
    report_path.write_text(json.dumps(report, indent=2))
    return report


def load_bundle(path: str | Path) -> dict:
    """Load a bundle saved by :func:`train_all` and check its format tag."""
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT:
        raise ValueError(
            f"{path} is not a {BUNDLE_FORMAT} bundle (legacy *_teste.joblib files "
            "must be retrained with `ros2 run mestrado_emg train_legacy`)"
        )
    return bundle


def main(argv: list[str] | None = None) -> None:
    """CLI entry point (``train_legacy``)."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("csv", help="raw CSV from Capture_EMG_Data (e.g. 6_10_20220.csv)")
    p.add_argument("--out", default="models", help="output directory")
    p.add_argument("--feature", choices=["mav", "rms"], default="mav")
    p.add_argument("--split", choices=["legacy", "temporal"], default="temporal")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--test-size", type=float, default=0.3)
    p.add_argument("--purge-windows", type=int, default=1)
    args = p.parse_args(argv)

    report = train_all(
        args.csv,
        args.out,
        LegacyFeatureConfig(feature=args.feature),
        split=args.split,
        seed=args.seed,
        test_size=args.test_size,
        purge_windows=args.purge_windows,
    )
    print(f"seed={report['seed']} split={report['split']} windows={report['n_windows']}")
    for name, res in report["results"].items():
        print(f"  {name:8s} acc={res['accuracy']:.4f} bal_acc={res['balanced_accuracy']:.4f}")


if __name__ == "__main__":
    main()
