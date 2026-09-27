"""Figures and cross-validation for the thesis classifiers (the old "Results" tab).

``Train_Myo_Signals`` had a PyQt window whose "Results" page plotted the
classifier scores, a confusion matrix, a ROC curve (binary data only), the raw
signal of one channel and the processed features of two channels. This module
produces the same views as PNG files, so they work in Docker without a window,
plus what the GUI never showed:

* **cross-validation** in two flavours: ``temporal`` (contiguous blocks inside
  each class, with purge windows around the test block) and ``shuffled``
  (``StratifiedKFold`` over windows, like the thesis split). The gap between the
  two is the optimism of mixing neighbouring windows between train and test.
  The GUI had a ``cv`` field, but the calls that used it were commented out;
* **ROC from continuous scores** (``decision_function``/``predict_proba``). The
  GUI passed hard 0/1 predictions to ``roc_curve``, which yields a single point;
* a **sampling-rate check** from the ``time`` column: the pipeline assumes the
  configured rate (200 Hz for the Myo), and a file recorded in another mode is
  flagged instead of silently analysed with the wrong filters;
* an ``amplitude`` reference: LDA on a single number per window, the mean of
  the features over all channels. When it scores like the five classifiers,
  they are separating overall activation level, not a spatial muscle pattern.

Everything is fitted on training windows only; the hold-out split is the same
as in :func:`mestrado_emg.training.train_all`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer

from mestrado_emg.features import LegacyFeatureConfig, add_pipeline_args, config_from_args
from mestrado_emg.training import (
    SplitMode,
    WindowDataset,
    build_dataset,
    load_legacy_csv,
    make_classifiers,
    run_name,
    sha256_of,
    split_indices,
)

# Rate mismatch above this fraction of the configured rate is reported.
RATE_TOLERANCE = 0.25


def estimate_rate_hz(csv_path: str | Path) -> float | None:
    """Samples per second from the ``time`` column, or ``None`` without one.

    The Myo sends two EMG samples per BLE packet, so consecutive timestamps
    come in pairs; the overall count over the recording span is what matters
    (the thesis file ``6_10_20220.csv``: 3030 samples in 17.1 s, ~177 Hz).
    """
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip().str.lower()
    if "time" not in df.columns or len(df) < 2:
        return None
    # Sum of forward steps, so a clock restarted between segments still works.
    steps = np.diff(df["time"].to_numpy(dtype=float))
    span = float(steps[steps > 0].sum())
    return len(steps) / span if span > 0 else None


def rate_warning(rate_hz: float | None, config: LegacyFeatureConfig) -> str | None:
    """Portuguese warning when the measured rate is far from ``config.fs_hz``."""
    if rate_hz is None or abs(rate_hz - config.fs_hz) <= RATE_TOLERANCE * config.fs_hz:
        return None
    window_s = config.samples_per_window / rate_hz
    return (
        f"taxa medida ~{rate_hz:.0f} amostras/s, mas o pipeline supõe {config.fs_hz:.0f} Hz: "
        f"os filtros não correspondem a este arquivo e cada janela de "
        f"{config.samples_per_window} amostras dura ~{window_s:.2f} s, não "
        f"{config.window_ms:.0f} ms. Resultados deste arquivo não são comparáveis aos de 200 Hz."
    )


def _channel_mean(X: np.ndarray) -> np.ndarray:
    # -> [n_windows, 1]: overall activation level of each window
    return X.mean(axis=1, keepdims=True)


def analysis_classifiers(seed: int) -> dict:
    """The five thesis classifiers plus the ``amplitude`` reference."""
    clfs = make_classifiers(seed)
    clfs["amplitude"] = make_pipeline(
        FunctionTransformer(_channel_mean), LinearDiscriminantAnalysis()
    )
    return clfs


def blocked_cv_indices(
    ds: WindowDataset, n_folds: int, purge_windows: int = 1
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Temporal k-fold: fold ``f`` tests the ``f``-th contiguous block of each class.

    Windows within ``purge_windows`` of the test block (same class, recording
    order) are left out of training, as in the ``temporal`` hold-out.

    Returns
    -------
    list of (train_idx, test_idx)
        One pair per fold; indices into ``ds.X``.
    """
    per_class = []
    for cls in np.unique(ds.y):
        idx = np.flatnonzero(ds.y == cls)
        per_class.append(idx[np.argsort(ds.order[idx])])
    folds = []
    for f in range(n_folds):
        train_parts, test_parts = [], []
        for idx in per_class:
            bounds = np.linspace(0, len(idx), n_folds + 1).round().astype(int)
            lo, hi = bounds[f], bounds[f + 1]
            test_parts.append(idx[lo:hi])
            keep = np.ones(len(idx), dtype=bool)
            keep[max(0, lo - purge_windows) : hi + purge_windows] = False
            train_parts.append(idx[keep])
        folds.append((np.concatenate(train_parts), np.concatenate(test_parts)))
    return folds


def cross_validate(
    ds: WindowDataset, n_folds: int, seed: int, purge_windows: int = 1
) -> dict[str, dict[str, list[float]]]:
    """Accuracy per fold for every classifier, temporal and shuffled.

    Returns
    -------
    dict
        ``{"temporal": {name: [acc, ...]}, "shuffled": {name: [acc, ...]}}``.
    """
    schemes = {
        "temporal": blocked_cv_indices(ds, n_folds, purge_windows),
        "shuffled": list(
            StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed).split(ds.X, ds.y)
        ),
    }
    out: dict[str, dict[str, list[float]]] = {}
    for scheme, folds in schemes.items():
        out[scheme] = {}
        for name, proto in analysis_classifiers(seed).items():
            accs = []
            for train_idx, test_idx in folds:
                clf = clone(proto).fit(ds.X[train_idx], ds.y[train_idx])
                accs.append(float(accuracy_score(ds.y[test_idx], clf.predict(ds.X[test_idx]))))
            out[scheme][name] = accs
    return out


def positive_class_score(clf, X: np.ndarray) -> np.ndarray:
    """Continuous score for class 1 of a fitted binary classifier."""
    if hasattr(clf, "decision_function"):
        return np.asarray(clf.decision_function(X))
    return clf.predict_proba(X)[:, 1]


def _runs(labels: np.ndarray) -> list[tuple[int, int, object]]:
    """Contiguous ``(start, stop, label)`` runs, in file order."""
    runs, start = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            runs.append((start, i, labels[start]))
            start = i
    return runs


def analyze(
    csv_path: str | Path,
    out_dir: str | Path,
    config: LegacyFeatureConfig,
    split: SplitMode = "temporal",
    seed: int = 42,
    test_size: float = 0.3,
    purge_windows: int = 1,
    n_folds: int = 5,
    pair: tuple[int, int] = (1, 2),
) -> dict:
    """Write the figures, ``analise.json`` and ``resumo.md`` for one CSV.

    Parameters
    ----------
    pair : tuple of int
        Channels (1-based, like the GUI) for the feature scatter plot.

    Returns
    -------
    dict
        The content of ``analise.json``.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay

    csv_path = Path(csv_path)
    samples, labels = load_legacy_csv(csv_path)
    if samples.shape[1] != config.n_channels:
        raise ValueError(
            f"{csv_path} has {samples.shape[1]} channels, config expects {config.n_channels}"
        )
    for ch in pair:
        if not 1 <= ch <= config.n_channels:
            raise ValueError(f"channel {ch} outside 1..{config.n_channels}")
    out = Path(out_dir) / run_name(csv_path, config, split)
    out.mkdir(parents=True, exist_ok=True)

    rate = estimate_rate_hz(csv_path)
    warning = rate_warning(rate, config)
    ds = build_dataset(samples, labels, config)
    train_idx, test_idx = split_indices(ds, split, test_size, seed, purge_windows)
    names = [str(c) for c in ds.class_labels]
    binary = len(names) == 2

    fitted, results = {}, {}
    for name, clf in analysis_classifiers(seed).items():
        clf.fit(ds.X[train_idx], ds.y[train_idx])
        pred = clf.predict(ds.X[test_idx])
        fitted[name] = clf
        results[name] = {
            "accuracy": float(accuracy_score(ds.y[test_idx], pred)),
            "balanced_accuracy": float(balanced_accuracy_score(ds.y[test_idx], pred)),
            "confusion_matrix": confusion_matrix(
                ds.y[test_idx], pred, labels=range(len(names))
            ).tolist(),
        }
        if binary:
            results[name]["roc_auc"] = float(
                roc_auc_score(ds.y[test_idx], positive_class_score(clf, ds.X[test_idx]))
            )

    # Every class needs at least one window per fold.
    min_class = int(np.bincount(ds.y).min())
    folds = min(n_folds, min_class)
    cv = cross_validate(ds, folds, seed, purge_windows) if folds >= 2 else {}

    # 1. scores (the GUI's Home page bar chart)
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(results))
    accs = [r["accuracy"] * 100 for r in results.values()]
    ax.bar(x - 0.2, accs, 0.4, label=f"hold-out {split}")
    if cv:
        m = [np.mean(v) * 100 for v in cv["temporal"].values()]
        s = [np.std(v) * 100 for v in cv["temporal"].values()]
        ax.bar(x + 0.2, m, 0.4, yerr=s, capsize=3, label=f"CV temporal ({folds} blocos)")
    ax.set_xticks(x, list(results))
    ax.set_ylim(0, 105)
    ax.set_ylabel("acurácia (%)")
    ax.set_title(f"{csv_path.name}: {len(test_idx)} janelas de teste")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out / "scores.png", dpi=120)
    plt.close(fig)

    # 2. confusion matrices, one per classifier
    fig, axes = plt.subplots(1, len(fitted), figsize=(3.2 * len(fitted), 3.9))
    for ax, (name, res) in zip(axes, results.items(), strict=True):
        ConfusionMatrixDisplay(np.array(res["confusion_matrix"]), display_labels=names).plot(
            ax=ax, colorbar=False
        )
        ax.set_title(f"{name}  acc={res['accuracy']:.2f}")
        ax.set_xlabel("previsto")
        ax.set_ylabel("verdadeiro")
    fig.suptitle(f"Matriz de confusão (categorias; teste {split})")
    fig.tight_layout()
    fig.savefig(out / "confusao.png", dpi=120)
    plt.close(fig)

    # 3. ROC (binary only, as in the GUI)
    if binary:
        fig, ax = plt.subplots(figsize=(5, 5))
        for name, clf in fitted.items():
            fpr, tpr, _ = roc_curve(ds.y[test_idx], positive_class_score(clf, ds.X[test_idx]))
            ax.plot(fpr, tpr, lw=2, label=f"{name}  AUC={results[name]['roc_auc']:.2f}")
        ax.plot([0, 1], [0, 1], "k--", label="acaso")
        ax.set_xlabel("taxa de falsos positivos")
        ax.set_ylabel("taxa de verdadeiros positivos")
        ax.set_title(f"ROC (categoria {names[1]} como positiva)")
        ax.legend(loc="lower right")
        fig.tight_layout()
        fig.savefig(out / "roc.png", dpi=120)
        plt.close(fig)

    # 4. raw signal, all channels, shaded by category
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    fig, axes = plt.subplots(
        config.n_channels, 1, figsize=(10, 1.2 * config.n_channels), sharex=True
    )
    for ch, ax in enumerate(np.atleast_1d(axes)):
        ax.plot(samples[:, ch], lw=0.5, color="k")
        for start, stop, lab in _runs(labels):
            ax.axvspan(start, stop, color=colors[names.index(str(lab)) % len(colors)], alpha=0.15)
        ax.set_ylabel(f"c{ch + 1}", rotation=0, labelpad=12)
    np.atleast_1d(axes)[-1].set_xlabel("amostra (cor de fundo = categoria)")
    fig.suptitle(f"Sinal bruto: {csv_path.name}")
    fig.tight_layout()
    fig.savefig(out / "sinal_bruto.png", dpi=110)
    plt.close(fig)

    # 5. processed features per channel and category (all windows)
    fig, axes = plt.subplots(2, (config.n_channels + 1) // 2, figsize=(12, 5.5))
    for ch, ax in enumerate(axes.ravel()[: config.n_channels]):
        data = [ds.X[ds.y == k, ch] for k in range(len(names))]
        ax.boxplot(data)
        ax.set_xticks(range(1, len(names) + 1), names)
        ax.set_title(f"canal {ch + 1}")
    for ax in axes.ravel()[config.n_channels :]:
        ax.set_visible(False)
    fig.suptitle(f"{config.feature.upper()} por janela, por categoria")
    fig.tight_layout()
    fig.savefig(out / "features_por_canal.png", dpi=110)
    plt.close(fig)

    # 6. feature scatter of two channels (the GUI's "Plot Processed Signals")
    a, b = pair[0] - 1, pair[1] - 1
    is_test = np.zeros(len(ds.y), dtype=bool)
    is_test[test_idx] = True
    fig, ax = plt.subplots(figsize=(6, 5))
    for k, lab in enumerate(names):
        for mask, marker, suffix in ((~is_test, "o", "treino"), (is_test, "x", "teste")):
            sel = (ds.y == k) & mask
            ax.scatter(
                ds.X[sel, a],
                ds.X[sel, b],
                marker=marker,
                color=colors[k % len(colors)],
                label=f"categoria {lab} ({suffix})",
            )
    ax.set_xlabel(f"{config.feature.upper()} canal {pair[0]}")
    ax.set_ylabel(f"{config.feature.upper()} canal {pair[1]}")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / f"features_c{pair[0]}_c{pair[1]}.png", dpi=120)
    plt.close(fig)

    report = {
        "source": {"path": csv_path.name, "sha256": sha256_of(csv_path)},
        "measured_rate_hz": rate,
        "warning": warning,
        "feature_config": {k: v for k, v in config.to_dict().items() if not k.startswith("sos_")},
        "seed": seed,
        "split": split,
        "test_size": test_size,
        "purge_windows": purge_windows,
        "class_labels": names,
        "n_windows": {
            "total": int(len(ds.y)),
            "per_class": np.bincount(ds.y).tolist(),
            "train": int(len(train_idx)),
            "test": int(len(test_idx)),
        },
        "holdout": results,
        "cv_folds": folds if cv else 0,
        "cv": cv,
        "sklearn_version": sklearn.__version__,
    }
    (out / "analise.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (out / "resumo.md").write_text(_summary_md(report, split))
    return report


def _summary_md(r: dict, split: str) -> str:
    """Short Portuguese table of the analysis, for the terminal and for notes."""
    lines = [
        f"# Análise: {r['source']['path']}",
        "",
        f"- feature: {r['feature_config']['feature']}; split do hold-out: {split}; "
        f"semente: {r['seed']}; scikit-learn {r['sklearn_version']}",
        f"- janelas: {r['n_windows']['total']} (por categoria {r['n_windows']['per_class']}); "
        f"treino {r['n_windows']['train']}, teste {r['n_windows']['test']}",
        f"- sinal: {LegacyFeatureConfig.from_dict(r['feature_config']).describe()}",
    ]
    if r["measured_rate_hz"]:
        lines.append(f"- taxa medida: ~{r['measured_rate_hz']:.0f} amostras/s")
    if r["warning"]:
        lines.append(f"- **AVISO:** {r['warning']}")
    lines += [
        "",
        "| classificador | hold-out | bal. | AUC | CV temporal | CV embaralhada |",
        "|---|---|---|---|---|---|",
    ]
    for name, res in r["holdout"].items():
        auc = f"{res['roc_auc']:.2f}" if "roc_auc" in res else "-"
        cvt = cvs = "-"
        if r["cv"]:
            t, s = r["cv"]["temporal"][name], r["cv"]["shuffled"][name]
            cvt = f"{np.mean(t):.2f} ± {np.std(t):.2f}"
            cvs = f"{np.mean(s):.2f} ± {np.std(s):.2f}"
        lines.append(
            f"| {name} | {res['accuracy']:.2f} | {res['balanced_accuracy']:.2f} | {auc} "
            f"| {cvt} | {cvs} |"
        )
    lines += [
        "",
        f'CV com {r["cv_folds"]} partições. "Temporal" testa blocos contíguos de cada categoria '
        '(com janelas de purga); "embaralhada" mistura janelas vizinhas entre treino e teste, '
        "como o split do mestrado, e por isso tende a ser otimista. "
        '"amplitude" é a referência de um número só por janela (média dos canais): se ela '
        "empata com os classificadores, eles estão separando o nível geral de ativação.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point (``analyze_legacy``)."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("csv", help="raw CSV from Capture_EMG_Data (e.g. 6_10_20220.csv)")
    p.add_argument("--out", default="models/analise", help="output directory")
    p.add_argument("--split", choices=["legacy", "temporal"], default="temporal")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--test-size", type=float, default=0.3)
    p.add_argument("--purge-windows", type=int, default=1)
    p.add_argument("--cv", type=int, default=5, help="number of cross-validation folds")
    p.add_argument(
        "--pair",
        type=int,
        nargs=2,
        default=(1, 2),
        metavar=("CH_X", "CH_Y"),
        help="channels (1-based) for the feature scatter plot",
    )
    add_pipeline_args(p)
    args = p.parse_args(argv)
    config = config_from_args(args)

    report = analyze(
        args.csv,
        args.out,
        config,
        split=args.split,
        seed=args.seed,
        test_size=args.test_size,
        purge_windows=args.purge_windows,
        n_folds=args.cv,
        pair=tuple(args.pair),
    )
    print(_summary_md(report, args.split))
    print(f"figuras em {Path(args.out) / run_name(args.csv, config, args.split)}")


if __name__ == "__main__":
    main()
