"""The course project's LSTM (hand gestures at 1 kHz), trained again with honest splits.

The course project that followed the thesis ("Hand Gesture Classification via
LSTM Neural Networks", PPGINF/UFABC) reported 97 % with the PyTorch notebook
``Deep_Learning_EMG_Pytorch_Modificado.ipynb`` (github.com/Calima94/
DEEP_LEARNING_MYO_SIGNALS, commit f7d28a4, folder "Colab Notebooks"). This
module repeats that notebook and changes only how the windows are split, so a
difference between the numbers comes from the split:

* ``notebook``: as its ``EMGDataset`` does it. The training set and the test
  set are built by two independent shuffles, so about 80 % of the test windows
  are training windows too (finding 27 in docs/INVENTARIO_MESTRADO.md);
* ``sorteio``: one shuffle, 80/20, no window in both sets (the same people in
  both, like the classifiers' hold-out in the course);
* ``participante``: train on seven participants, test on the eighth, each in
  turn: someone who recorded no training data.

Kept from the notebook on purpose:

* windows of 200 samples without overlap, per recording; absolute value and a
  20-sample moving average (``np.convolve(..., mode="same")``) on every channel
  but the last one (its ``range(d.shape[1] - 1)``); divided by the largest
  value;
* Gaussian noise of 5 % of the standard deviation, added once to the training
  windows;
* ``EMGModel``: the 200 x 4 window is flattened to 800 numbers and handed to
  ``nn.LSTM`` as a 2-D tensor, which PyTorch reads as one unbatched sequence
  whose steps are the windows of the batch. The recurrence runs across the
  windows of a batch, not along the time inside a window (finding 28);
* the hyper-parameters Optuna chose there (learning rate 0.0098, batch 256,
  dropout 0.4, 32 hidden units), Adam and 200 epochs. The dropout acts only in
  the first epoch: the notebook's ``validate`` puts the model in eval mode after
  every epoch and nothing puts it back in train mode;
* the test windows read in a random order, 256 at a time, like its
  ``test_loader``.

The same test set is also read in recording order (neighbours share the
gesture) and one window at a time. Since the recurrence crosses windows, these
show how much of the accuracy depends on which windows come before.

One change in the two new splits: the largest value used to scale comes from
the training windows only (the notebook takes it from all of them).

PyTorch is not in the ROS image: this runs in docker/Dockerfile.lstm
(``docker compose -f docker/compose.yaml --profile lstm run --rm lstm``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DIVISOES = ("notebook", "sorteio", "participante")
# how the test windows are read: random order in batches (the notebook's
# test_loader), recording order in batches, one window at a time
ORDENS = ("sorteada", "gravacao", "isolada")
NOME_DIVISAO = {
    "notebook": "como no notebook (treino e teste se sobrepõem)",
    "sorteio": "sorteio sem sobreposição (mesmas pessoas)",
    "participante": "participante novo (treina com os outros)",
}


@dataclass(frozen=True)
class Hiper:
    """The notebook's choices: Optuna's best trial (cell 12) and its data set-up."""

    lr: float = 0.009816285218013608
    lote: int = 256
    dropout: float = 0.4
    ocultas: int = 32
    epocas: int = 200
    ruido: float = 0.05
    parte_treino: float = 0.8
    janela: int = 200
    media: int = 20


def janelas(
    csv_path: str | Path, janela: int = 200, media: int = 20
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cut the windows as the notebook's ``EMGDataset.load_and_label``, before scaling.

    ``csv_path`` is the file of scripts/fetch_gesture_data.sh: one block of rows
    per (participante, position) recording, labels ``gesto_<n>``.

    Returns
    -------
    tuple of np.ndarray
        ``X`` [n, janela, canais], ``y`` [n] (the gesture number, as the
        notebook's file name) and ``grupo`` [n] (the participant).
    """
    df = pd.read_csv(csv_path)
    canais = [c for c in df.columns if c.strip().lower().startswith("channel")]
    kernel = np.ones(media) / media
    X, y, grupo = [], [], []
    for (pessoa, gesto), bloco in df.groupby(["participante", "position"], sort=False):
        emg = bloco[canais].to_numpy(dtype=float)
        rotulo = int(str(gesto).rsplit("_", 1)[-1])
        for k in range(0, len(emg) - janela + 1, janela):
            d = np.abs(emg[k : k + janela])
            for n in range(d.shape[1] - 1):  # the notebook leaves the last channel raw
                d[:, n] = np.convolve(d[:, n], kernel, mode="same")
            X.append(d)
            y.append(rotulo)
            grupo.append(pessoa)
    return np.array(X), np.array(y), np.array(grupo)


def dividir(divisao: str, grupo: np.ndarray, rng: np.random.Generator, parte_treino: float = 0.8):
    """Yield ``(nome, treino, teste)`` index arrays, ``teste`` in the order it is read.

    The test order is random in all three, as in the notebook's test set.
    """
    n = len(grupo)
    corte = int(parte_treino * n)
    if divisao == "notebook":  # EMGDataset(is_training=True) and (is_training=False)
        treino = rng.permutation(n)[:corte]
        yield "notebook", treino, rng.permutation(n)[corte:]
    elif divisao == "sorteio":
        p = rng.permutation(n)
        yield "sorteio", p[:corte], p[corte:]
    elif divisao == "participante":
        for pessoa in sorted(pd.unique(grupo).tolist()):
            teste = np.flatnonzero(grupo == pessoa)
            yield str(pessoa), np.flatnonzero(grupo != pessoa), rng.permutation(teste)
    else:
        raise ValueError(f"divisão desconhecida: {divisao}")


# ------------------------------------------------------------------ training (PyTorch)

_DADOS: dict = {}


def _iniciar(X: np.ndarray, y: np.ndarray, threads: int) -> None:
    """Worker set-up: the windows once per process, and its share of the cores."""
    import torch

    torch.set_num_threads(threads)
    _DADOS.update(X=X, y=y)


def _modelo(entradas: int, classes: int, hiper: Hiper):
    """The notebook's ``EMGModel`` (cell 7), with the sizes as arguments."""
    from torch import nn

    class EMGModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(entradas, hiper.ocultas, batch_first=True)
            self.dropout = nn.Dropout(p=hiper.dropout)
            self.relu2 = nn.ReLU()
            self.fc3 = nn.Linear(hiper.ocultas, classes)

        def forward(self, x):
            x = x.view(x.shape[0], -1)  # 2-D: nn.LSTM takes it as ONE sequence of windows
            x, _ = self.lstm(x)
            return self.fc3(self.relu2(self.dropout(x)))

    return EMGModel()


def treinar_e_testar(tarefa: dict) -> dict:
    """Train on ``tarefa["treino"]``, test on ``tarefa["teste"]``; runs in a worker."""
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    inicio = time.monotonic()
    X, y = _DADOS["X"], _DADOS["y"]
    hiper = Hiper(**tarefa["hiper"])
    treino, teste, semente = tarefa["treino"], tarefa["teste"], tarefa["semente"]
    torch.manual_seed(semente)
    rng = np.random.default_rng(semente)

    escala = X.max() if tarefa["divisao"] == "notebook" else X[treino].max()
    x_treino = X[treino] / escala
    x_treino = x_treino + rng.normal(0, x_treino.std() * hiper.ruido, x_treino.shape)
    x_teste = torch.tensor(X[teste] / escala, dtype=torch.float32)
    classes = int(y.max()) + 1

    dados = TensorDataset(
        torch.tensor(x_treino, dtype=torch.float32), torch.tensor(y[treino], dtype=torch.long)
    )
    lotes = DataLoader(
        dados, batch_size=hiper.lote, shuffle=True, generator=torch.Generator().manual_seed(semente)
    )
    modelo = _modelo(x_treino[0].size, classes, hiper)
    otimizador = torch.optim.Adam(modelo.parameters(), lr=hiper.lr)
    perda = nn.CrossEntropyLoss()
    for epoca in range(hiper.epocas):
        modelo.train(epoca == 0)  # the notebook's validate() leaves eval mode on from then on
        for xb, yb in lotes:
            otimizador.zero_grad()
            perda(modelo(xb), yb).backward()
            otimizador.step()

    modelo.eval()

    def prever(ordem: np.ndarray, lote: int) -> np.ndarray:
        with torch.no_grad():
            partes = [
                modelo(x_teste[ordem[i : i + lote]]).argmax(dim=1).numpy()
                for i in range(0, len(ordem), lote)
            ]
        pred = np.empty(len(ordem), dtype=int)
        pred[ordem] = np.concatenate(partes)
        return pred

    verdade = y[teste]
    sorteada = prever(np.arange(len(teste)), hiper.lote)  # teste is already shuffled
    acc = {
        "sorteada": float(np.mean(sorteada == verdade)),
        "gravacao": float(np.mean(prever(np.argsort(teste), hiper.lote) == verdade)),
        "isolada": float(np.mean(prever(np.arange(len(teste)), 1) == verdade)),
    }
    confusao = np.zeros((classes, classes), dtype=int)
    np.add.at(confusao, (verdade, sorteada), 1)
    return {
        "divisao": tarefa["divisao"],
        "nome": tarefa["nome"],
        "semente": semente,
        "n_treino": len(treino),
        "n_teste": len(teste),
        "sobreposicao": float(np.isin(teste, treino).mean()),
        "acc": acc,
        "confusao": confusao.tolist(),
        "segundos": round(time.monotonic() - inicio, 1),
    }


def rodar(
    csv_path: str | Path,
    hiper: Hiper,
    divisoes: tuple[str, ...] = DIVISOES,
    repeticoes: int = 3,
    semente: int = 0,
    processos: int = 0,
) -> dict:
    """Every (split, fold, seed) training, in parallel; one line per finished training."""
    X, y, grupo = janelas(csv_path, hiper.janela, hiper.media)
    tarefas = []
    for r in range(repeticoes):
        rng = np.random.default_rng(semente + r)
        for divisao in divisoes:
            for nome, treino, teste in dividir(divisao, grupo, rng, hiper.parte_treino):
                tarefas.append(
                    dict(divisao=divisao, nome=nome, treino=treino, teste=teste,
                         semente=semente + r, hiper=asdict(hiper))
                )  # fmt: skip
    nucleos = os.cpu_count() or 1
    processos = processos or min(len(tarefas), nucleos)
    threads = max(1, nucleos // processos)
    print(
        f"{len(X)} janelas ({len(np.unique(y))} gestos, {len(np.unique(grupo))} participantes); "
        f"{len(tarefas)} treinos de {hiper.epocas} épocas, {processos} de cada vez",
        flush=True,
    )
    resultados = []
    with ProcessPoolExecutor(processos, initializer=_iniciar, initargs=(X, y, threads)) as pool:
        futuros = [pool.submit(treinar_e_testar, t) for t in tarefas]
        for f in as_completed(futuros):
            r = f.result()
            resultados.append(r)
            print(
                f"  [{len(resultados)}/{len(tarefas)}] {r['divisao']} {r['nome']} "
                f"(semente {r['semente']}): {r['acc']['sorteada']:.1%} em {r['segundos']:.0f} s",
                flush=True,
            )
    ordem = {d: i for i, d in enumerate(DIVISOES)}
    resultados.sort(key=lambda r: (ordem[r["divisao"]], r["nome"], r["semente"]))
    import torch

    return {
        "fonte": Path(csv_path).name,
        "n_janelas": len(X),
        "participantes": sorted(str(p) for p in np.unique(grupo)),
        "hiper": asdict(hiper),
        "repeticoes": repeticoes,
        "semente": semente,
        "torch": torch.__version__,
        "treinos": resultados,
        "resumo": resumir(resultados),
    }


def resumir(resultados: list[dict]) -> dict:
    """Mean ± std per split and reading order.

    For ``participante`` the spread is across participants (each one averaged
    over the seeds first), like the "participante novo" column of analyze_legacy.
    """
    resumo = {}
    for divisao in DIVISOES:
        rs = [r for r in resultados if r["divisao"] == divisao]
        if not rs:
            continue
        item = {"n_teste": int(np.mean([r["n_teste"] for r in rs])),
                "sobreposicao": float(np.mean([r["sobreposicao"] for r in rs]))}  # fmt: skip
        for ordem in ORDENS:
            if divisao == "participante":
                por = {}
                for r in rs:
                    por.setdefault(r["nome"], []).append(r["acc"][ordem])
                valores = [float(np.mean(v)) for v in por.values()]
                if ordem == "sorteada":
                    item["por_participante"] = {k: float(np.mean(v)) for k, v in por.items()}
            else:
                valores = [r["acc"][ordem] for r in rs]
            item[ordem] = {"media": float(np.mean(valores)), "desvio": float(np.std(valores))}
        resumo[divisao] = item
    return resumo


def pasta(csv_path: str | Path, epocas: int = 200) -> str:
    """Output folder name, next to analyze_legacy's (…/models/analise/<pasta>)."""
    stem = re.sub(r"[^A-Za-z0-9]+", "-", Path(csv_path).stem).strip("-")
    return f"{stem}_lstm" + ("" if epocas == 200 else f"-e{epocas}")


def _pct(m: dict) -> str:
    return f"{m['media']:.1%} ± {m['desvio']:.1%}".replace(".", ",")


def resumo_md(rel: dict) -> str:
    """Portuguese summary, for the terminal and resumo.md."""
    h = rel["hiper"]
    linhas = [
        f"# LSTM da disciplina: {rel['fonte']}",
        "",
        "- a rede, o pré-processamento e os hiperparâmetros do notebook da disciplina; "
        "só a divisão treino/teste muda",
        f"- {rel['n_janelas']} janelas de {h['janela']} amostras; {h['epocas']} épocas; "
        f"lr {h['lr']:.4f}, lote {h['lote']}, dropout {h['dropout']}, {h['ocultas']} unidades; "
        f"{rel['repeticoes']} semente(s) a partir de {rel['semente']}; PyTorch {rel['torch']}",
        "",
        "| divisão | janelas de teste | teste também no treino | acurácia "
        "| em ordem de gravação | janela isolada |",
        "|---|---|---|---|---|---|",
    ]
    for divisao, item in rel["resumo"].items():
        linhas.append(
            f"| {NOME_DIVISAO[divisao]} | {item['n_teste']} | {item['sobreposicao']:.0%} "
            f"| {_pct(item['sorteada'])} | {_pct(item['gravacao'])} | {_pct(item['isolada'])} |"
        )
    part = rel["resumo"].get("participante")
    if part:
        nomes = list(part["por_participante"])
        linhas += [
            "",
            "| participante | " + " | ".join(nomes) + " |",
            "|---|" + "---|" * len(nomes),
            "| acurácia | "
            + " | ".join(f"{v:.0%}" for v in part["por_participante"].values())
            + " |",
        ]
    linhas += [
        "",
        '"Acurácia" lê o teste em ordem sorteada, de 256 em 256 janelas, como o notebook. '
        "Como a recorrência da rede passa de uma janela para a seguinte dentro do lote, "
        '"em ordem de gravação" (vizinhas do mesmo gesto) e "janela isolada" (uma por vez) '
        "mostram quanto o resultado depende das janelas vizinhas. Na divisão por participante, "
        "o desvio é entre participantes.",
        "",
    ]
    return "\n".join(linhas)


def figuras(rel: dict, out: Path) -> None:
    """acuracia.png (per split, and per participant) and confusao.png."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    resumo = rel["resumo"]
    part = resumo.get("participante")
    fig, eixos = plt.subplots(1, 2 if part else 1, figsize=(11 if part else 6, 4), squeeze=False)
    ax = eixos[0][0]
    nomes = list(resumo)
    x = np.arange(len(nomes))
    for i, (ordem, rotulo) in enumerate(
        (("sorteada", "ordem sorteada (notebook)"), ("gravacao", "ordem de gravação"),
         ("isolada", "janela isolada"))
    ):  # fmt: skip
        m = [resumo[d][ordem]["media"] * 100 for d in nomes]
        s = [resumo[d][ordem]["desvio"] * 100 for d in nomes]
        ax.bar(x + (i - 1) * 0.27, m, 0.27, yerr=s, capsize=3, label=rotulo)
    rotulos = {"notebook": "notebook\n(sobreposição)", "sorteio": "sorteio",
               "participante": "participante\nnovo"}  # fmt: skip
    ax.set_xticks(x, [rotulos[d] for d in nomes])
    ax.set_ylim(0, 105)
    ax.set_ylabel("acurácia (%)")
    ax.set_title("LSTM do notebook, por divisão")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, frameon=False, fontsize=8)
    if part:
        ax = eixos[0][1]
        pessoas = list(part["por_participante"])
        ax.bar(pessoas, [v * 100 for v in part["por_participante"].values()], color="C2")
        ax.axhline(part["sorteada"]["media"] * 100, color="k", ls="--", lw=1, label="média")
        ax.set_ylim(0, 105)
        ax.set_xlabel("participante testado")
        ax.set_title("Participante novo")
        ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out / "acuracia.png", dpi=120)
    plt.close(fig)

    presentes = [d for d in DIVISOES if d in resumo]
    fig, eixos = plt.subplots(1, len(presentes), figsize=(3.6 * len(presentes), 3.6), squeeze=False)
    for ax, divisao in zip(eixos[0], presentes, strict=True):
        soma = sum(np.array(r["confusao"]) for r in rel["treinos"] if r["divisao"] == divisao)
        taxa = soma / np.maximum(soma.sum(axis=1, keepdims=True), 1)  # a gesture may miss the test
        ax.imshow(taxa, vmin=0, vmax=1, cmap="Blues")
        for (i, j), v in np.ndenumerate(taxa):
            ax.text(j, i, f"{v:.0%}", ha="center", va="center",
                    color="white" if v > 0.6 else "black", fontsize=8)  # fmt: skip
        ax.set_title(divisao, fontsize=10)
        ax.set_xlabel("previsto (gesto)")
        ax.set_ylabel("verdadeiro (gesto)")
    fig.suptitle("Matriz de confusão da LSTM (linhas somam 100 %)")
    fig.tight_layout()
    fig.savefig(out / "confusao.png", dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point (``python3 -m mestrado_emg.lstm_gestos``)."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("csv", help="data/gestos_1khz.csv (scripts/fetch_gesture_data.sh)")
    p.add_argument("--out", default="models/analise", help="parent of the output folder")
    p.add_argument("--epocas", type=int, default=Hiper.epocas)
    p.add_argument("--repeticoes", type=int, default=3, help="seeds per split")
    p.add_argument("--semente", type=int, default=0)
    p.add_argument("--divisoes", nargs="+", choices=DIVISOES, default=list(DIVISOES))
    p.add_argument("--processos", type=int, default=0, help="parallel trainings (0 = cores)")
    args = p.parse_args(argv)
    if args.epocas < 1 or args.repeticoes < 1:
        p.error("--epocas e --repeticoes precisam ser >= 1")
    if not Path(args.csv).is_file():
        p.error(
            f"{args.csv} não existe: baixe com scripts/fetch_gesture_data.sh "
            "(no painel, Manutenção → Dados → Gestos da disciplina)"
        )

    hiper = Hiper(epocas=args.epocas)
    rel = rodar(args.csv, hiper, tuple(args.divisoes), args.repeticoes, args.semente,
                args.processos)  # fmt: skip
    out = Path(args.out) / pasta(args.csv, args.epocas)
    out.mkdir(parents=True, exist_ok=True)
    (out / "resultado.json").write_text(json.dumps(rel, indent=2, ensure_ascii=False))
    (out / "resumo.md").write_text(resumo_md(rel))
    figuras(rel, out)
    print()
    print(resumo_md(rel))
    print(f"figuras em {out}")


if __name__ == "__main__":
    main()
