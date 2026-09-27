#!/usr/bin/env python3
"""Painel do projeto: scripts/menu.sh as a page in the browser.

Runs on the host (the WSL Ubuntu on Windows, or Linux), not in Docker, because
it is what starts and stops the project's containers. Standard library only.

    python3 scripts/painel.py            # http://localhost:8000
    python3 scripts/painel.py --abrir    # ... and opens the browser
    python3 scripts/painel.py --porta 8001

Every button runs one entry of a fixed list of actions: the same docker compose
commands as scripts/menu.sh, with the same defaults. Nothing else can be run
through it, and every parameter is checked against the files that exist and
the values the menu offers. Simulations start detached (`up -d`), so closing
the panel leaves them running; "Parar" and "Parar tudo" stop them. One-off
tasks (capture, training, tests) belong to the panel and stop with it.

Only one simulation (or capture) at a time: two of them publish on the same
topics and mix their readings without any error (docs/COMO_RODAR.md).

The server listens on 127.0.0.1 only. Against other sites open in the same
browser: every POST needs the X-Painel header, which a page from another origin
cannot send without a CORS preflight that this server never approves, and the
Host header must be this machine (no DNS rebinding).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[1]
PAGINA = Path(__file__).with_name("painel.html")

BASE = "docker/compose.yaml"
DESKTOP = "docker/compose.desktop.yaml"
MYO = "docker/compose.myo.yaml"
CAMERA = "docker/compose.camera.yaml"

# Services that run Gazebo or publish sEMG: only one of them at a time.
PRINCIPAIS = {"braco", "sim", "espelho", "captura", "shell"}
NOMES = {
    "braco": "o braço",
    "sim": "o sistema completo",
    "espelho": "o modo espelho",
    "captura": "a captura",
    "shell": "um terminal do projeto (talvez o Gazebo do menu)",
}
NAO_BRUTOS = {"scores_of_classifiers.csv", "training_matrix_csv_m_class.csv"}
VIDEOS = {".avi", ".mp4", ".mkv", ".mov"}
CSV_PADRAO = "6_10_20220.csv"
MODELO_PADRAO = "knn_6-10-20220_mav_temporal_latest.joblib"
VIDEO_PADRAO = "test_2_05.avi"  # saved already mirrored by the thesis tool
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
MAX_LINHAS = 5000


class Recusado(Exception):
    """A request the panel will not run; the message is shown on the page."""


@dataclass
class Comando:
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        """As it would be typed in a terminal (shown at the top of the output)."""
        return " ".join([*(f"{k}={v}" for k, v in self.env.items()), *self.argv])


@dataclass
class Plano:
    titulo: str
    passos: list[Comando]
    alvo: str | None = None  # the main service it starts, for the one-at-a-time rule


@dataclass
class Ambiente:
    wsl: bool
    janela: str | None  # compose file that opens windows; None = no display
    desktop: bool  # Docker Desktop: the web page needs compose.desktop.yaml

    @classmethod
    def detectar(cls, desktop: bool) -> Ambiente:
        try:
            release = Path("/proc/sys/kernel/osrelease").read_text().lower()
        except OSError:
            release = ""
        wsl = bool(os.environ.get("WSL_DISTRO_NAME")) or "microsoft" in release
        if wsl:
            janela = "docker/compose.wsl.yaml"
        elif os.environ.get("DISPLAY"):
            janela = "docker/compose.gui.yaml"
        else:
            janela = None
        return cls(wsl, janela, desktop)


# --------------------------------------------------------------------- docker


class Docker:
    """The two questions the page asks every couple of seconds."""

    def __init__(self, repo: Path = REPO) -> None:
        self.repo = repo

    def info(self) -> dict:
        try:
            r = subprocess.run(
                ["docker", "info", "--format", "{{.OperatingSystem}}|{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):  # no CLI: Docker Desktop closed
            return {"ok": False, "desktop": False, "versao": ""}
        if r.returncode != 0:
            return {"ok": False, "desktop": False, "versao": ""}
        so, _, versao = r.stdout.strip().partition("|")
        return {"ok": True, "desktop": "Docker Desktop" in so, "versao": versao}

    def rodando(self) -> list[dict]:
        """Running containers of this compose project, `run` ones included."""
        try:
            r = subprocess.run(
                ["docker", "compose", "-f", BASE, "ps", "-a", "--format", "json"],
                cwd=self.repo,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        saida = r.stdout.strip()
        if r.returncode != 0 or not saida:
            return []
        itens = (
            json.loads(saida)
            if saida.startswith("[")
            else [json.loads(linha) for linha in saida.splitlines() if linha.strip()]
        )
        return [
            {
                "servico": c.get("Service", ""),
                "nome": c.get("Name", ""),
                "status": c.get("Status", ""),
            }
            for c in itens
            if c.get("State") == "running"
        ]


# ------------------------------------------------------------------ catalogue


FILTROS = {".csv", ".txt", ".json", ".npy"}  # formats mestrado_emg.features.load_sos reads
_info_cache: dict[Path, tuple[tuple[float, int], dict]] = {}


def info_gravacao(path: Path) -> dict:
    """Channels in the header and the rate the ``time`` column suggests (cached by mtime).

    The rate is a hint for the page only: the Myo files of the thesis timestamp
    irregularly, and the training uses the rate the user sets.
    """
    try:
        st = path.stat()
    except OSError:
        return {"canais": 0, "taxa": None}
    chave = (st.st_mtime, st.st_size)
    guardado = _info_cache.get(path)
    if guardado and guardado[0] == chave:
        return guardado[1]
    canais, taxa = 0, None
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            leitor = csv.reader(f)
            cabecalho = [c.strip().lower() for c in next(leitor)]
            canais = sum(bool(re.match(r"(chanel|channel)", c)) for c in cabecalho)
            if "time" in cabecalho:
                i, tempos = cabecalho.index("time"), []
                for linha in itertools.islice(leitor, 5000):
                    try:
                        tempos.append(float(linha[i]))
                    except (ValueError, IndexError):
                        pass
                # Samples over the forward span, as analysis.estimate_rate_hz: the Myo
                # stamps its samples in pairs, so a median step would double-count.
                passos = [b - a for a, b in itertools.pairwise(tempos)]
                vao = sum(p for p in passos if p > 0)
                if vao > 0:
                    taxa = round(len(passos) / vao)
    except (OSError, StopIteration, UnicodeDecodeError, csv.Error):
        pass
    info = {"canais": canais, "taxa": taxa}
    _info_cache[path] = (chave, info)
    return info


def opcoes(repo: Path) -> dict:
    """What exists on disk to choose from (the menu's lists)."""
    data, models = repo / "data", repo / "models"
    csvs = sorted(p.name for p in data.glob("*.csv") if p.name not in NAO_BRUTOS)
    videos = sorted(p.name for p in data.glob("*") if p.suffix.lower() in VIDEOS)
    modelos = sorted(p.name for p in models.glob("*_latest.joblib"))
    analises = sorted(p.name for p in (models / "analise").glob("*") if p.is_dir())
    filtros = sorted(p.name for p in (data / "filtros").glob("*") if p.suffix.lower() in FILTROS)
    return {
        "csvs": csvs,
        "videos": videos,
        "modelos": modelos,
        "analises": analises,
        "filtros": filtros,
        "gravacoes": {nome: info_gravacao(data / nome) for nome in csvs},
    }


def _escolha(p: dict, nome: str, validos: list[str], padrao: str) -> str:
    v = p.get(nome, padrao)
    if v not in validos:
        raise Recusado(f"Valor inválido para {nome}: {v!r}.")
    return v


def _bool(p: dict, nome: str, padrao: bool) -> bool:
    v = p.get(nome, padrao)
    if not isinstance(v, bool):
        raise Recusado(f"Valor inválido para {nome}: {v!r}.")
    return v


def _int(p: dict, nome: str, padrao: int, lo: int, hi: int) -> int:
    v = str(p.get(nome, padrao)).strip()
    if not re.fullmatch(r"-?\d+", v) or not lo <= int(v) <= hi:
        raise Recusado(f"{nome} deve ser um número inteiro entre {lo} e {hi}.")
    return int(v)


def _num(p: dict, nome: str, padrao: float, lo: float, hi: float) -> str:
    v = str(p.get(nome, padrao)).strip().replace(",", ".")
    try:
        x = float(v)
    except ValueError:
        x = float("nan")
    if not lo <= x <= hi:
        raise Recusado(f"{nome} deve ser um número entre {lo:g} e {hi:g}.")
    return f"{x:g}"


def _tf(b: bool) -> str:
    return "true" if b else "false"


def _compose(*arquivos: str | None) -> list[str]:
    argv = ["docker", "compose"]
    for a in arquivos:
        if a:
            argv += ["-f", a]
    return argv


def _csv(p: dict, opc: dict) -> str:
    if not opc["csvs"]:
        raise Recusado("Não há gravações em data/: use Manutenção → Baixar os dados do mestrado.")
    padrao = CSV_PADRAO if CSV_PADRAO in opc["csvs"] else opc["csvs"][0]
    return _escolha(p, "csv", opc["csvs"], padrao)


def _camera(p: dict, amb: Ambiente, opc: dict) -> tuple[str, bool, list[str | None]]:
    """Video in data/ or, on Linux, the webcam -> CAMERA, FLIP and extra files."""
    validos = opc["videos"] + ([] if amb.wsl else ["webcam"])
    if not validos:
        raise Recusado("Não há vídeo em data/: use Manutenção → Baixar os dados do mestrado.")
    video = _escolha(p, "video", validos, VIDEO_PADRAO if VIDEO_PADRAO in validos else validos[0])
    espelhar = _bool(p, "espelhar", video != VIDEO_PADRAO)
    if video == "webcam":
        return "0", espelhar, [CAMERA]
    return f"/data/{video}", espelhar, []


def _janela(p: dict, amb: Ambiente, padrao: bool) -> bool:
    return amb.janela is not None and _bool(p, "janela", padrao)


def _seguir(argv_compose: list[str], servicos: list[str], ultimas: int = 40) -> Comando:
    """Follow the logs of what was started; ends when the services stop."""
    return Comando([*argv_compose, "logs", "-f", "--no-color", "--tail", str(ultimas), *servicos])


# -------------------------------------------------------------------- actions


def plano_braco(p: dict, amb: Ambiente, opc: dict) -> Plano:
    janela = _janela(p, amb, False)
    c = _compose(BASE, amb.janela if janela else None, DESKTOP if amb.desktop else None)
    return Plano(
        "Braço pelo navegador",
        [Comando([*c, "up", "-d", "braco", "web"], {"GUI": _tf(janela)}), _seguir(c, ["braco"])],
        alvo="braco",
    )


def plano_sistema(p: dict, amb: Ambiente, opc: dict) -> Plano:
    fonte = _escolha(p, "fonte", ["gravacao", "myo"], "gravacao")
    csv = _csv(p, opc) if fonte == "gravacao" else CSV_PADRAO
    if not opc["modelos"]:
        raise Recusado("Não há classificadores em models/: treine antes (Dados e resultados).")
    padrao = MODELO_PADRAO if MODELO_PADRAO in opc["modelos"] else opc["modelos"][0]
    modelo = _escolha(p, "modelo", opc["modelos"], padrao)
    janela = _janela(p, amb, False)
    pagina = _bool(p, "pagina", True)
    c = _compose(
        BASE,
        amb.janela if janela else None,
        MYO if fonte == "myo" else None,
        DESKTOP if pagina and amb.desktop else None,
    )
    env = {
        "GUI": _tf(janela),
        "SOURCE": "replay" if fonte == "gravacao" else "myo",
        "CSV": csv,
        "MODEL": modelo,
    }
    servicos = ["sim", "web"] if pagina else ["sim"]
    return Plano(
        "Sistema completo",
        [Comando([*c, "up", "-d", *servicos], env), _seguir(c, ["sim"])],
        alvo="sim",
    )


def plano_espelho(p: dict, amb: Ambiente, opc: dict) -> Plano:
    camera, espelhar, extra = _camera(p, amb, opc)
    lado = _escolha(p, "lado", ["right", "left"], "right")
    janela = _janela(p, amb, True)
    pagina = _bool(p, "pagina", False)
    c = _compose(
        BASE, amb.janela if janela else None, *extra, DESKTOP if pagina and amb.desktop else None
    )
    env = {
        "CAMERA": camera,
        "FLIP": _tf(espelhar),
        "ARM": lado,
        "GUI": _tf(janela),
        "SHOW_WINDOW": _tf(janela),
    }
    servicos = ["espelho", "web"] if pagina else ["espelho"]
    return Plano(
        "Modo espelho",
        [Comando([*c, "up", "-d", *servicos], env), _seguir(c, ["espelho"])],
        alvo="espelho",
    )


def plano_captura(p: dict, amb: Ambiente, opc: dict) -> Plano:
    fonte = _escolha(p, "fonte", ["gravacao", "myo"], "gravacao")
    csv = _csv(p, opc) if fonte == "gravacao" else CSV_PADRAO
    camera, espelhar, extra = _camera(p, amb, opc)
    janela = _janela(p, amb, True)
    c = _compose(BASE, amb.janela if janela else None, *extra, MYO if fonte == "myo" else None)
    env = {
        "EMG": "replay" if fonte == "gravacao" else "myo",
        "CSV": csv,
        "CAMERA": camera,
        "FLIP": _tf(espelhar),
        "ARM": _escolha(p, "lado", ["right", "left"], "right"),
        "SHOW_WINDOW": _tf(janela),
        "N_CATEGORIES": str(_int(p, "categorias", 2, 2, 4)),
        "TOLERANCE": _num(p, "tolerancia", 10, 1, 45),
        "SAMPLES": str(_int(p, "amostras", 1000, 10, 100000)),
        "CONTINUOUS": _tf(_bool(p, "continuo", False)),
    }
    return Plano("Captura de dados", [Comando([*c, "run", "--rm", "captura"], env)], alvo="captura")


def _treino_args(p: dict, opc: dict) -> tuple[str, str, str, int]:
    return (
        _csv(p, opc),
        _escolha(p, "feature", ["mav", "rms"], "mav"),
        _escolha(p, "divisao", ["temporal", "legacy"], "temporal"),
        _int(p, "semente", 42, 0, 2**31 - 1),
    )


def _teste(p: dict) -> list[str]:
    """--test-size, only when the hold-out is not the thesis's 30 % (the course used 20 %)."""
    pct = _int(p, "teste", 30, 5, 50)
    return [] if pct == 30 else ["--test-size", f"{pct / 100:g}"]


# The wavelets PyWavelets knows by these names (the page offers haar, db, sym, coif).
WAVELET = re.compile(
    r"haar|dmey|db([1-9]|[1-3]\d)|sym([2-9]|1\d|20)|coif([1-9]|1[0-7])"
    r"|(bior|rbio)(1\.[135]|2\.[2468]|3\.[13579]|4\.4|5\.5|6\.8)"
)


def _filtros(p: dict, opc: dict | None, fs: float) -> tuple[list[str], str]:
    """The IIR choice: the thesis coefficients, designed for fs, or files in data/filtros."""
    modo = _escolha(p, "filtros", ["mestrado", "projetados", "arquivos"], "mestrado")
    if modo == "projetados":
        hp = _num(p, "passa_altas_hz", 20, 0.1, fs / 2 - 0.1)
        rede = _escolha(p, "rede_hz", ["60", "50", "0"], "60")
        tag = f"hp{hp}" + (f"-rf{rede}" if rede != "0" else "-srf")
        return ["--filters", "design", "--highpass-hz", hp, "--mains-hz", rede], tag
    if modo == "arquivos":
        validos = ["", *(opc or {}).get("filtros", [])]
        a = _escolha(p, "arquivo_passa_altas", validos, "")
        b = _escolha(p, "arquivo_rejeita_faixa", validos, "")
        if not a and not b:
            raise Recusado("Escolha ao menos um arquivo de filtro (eles ficam em data/filtros/).")
        args = ["--filters", "files"]
        args += ["--highpass-file", f"/data/filtros/{a}"] if a else []
        args += ["--bandstop-file", f"/data/filtros/{b}"] if b else []
        nomes = [re.sub(r"[^A-Za-z0-9]+", "", Path(x).stem)[:12] or "nenhum" for x in (a, b)]
        return args, "iir-" + "-".join(nomes)
    return [], ""


def _sinal(p: dict, opc: dict | None = None, canais: int = 8) -> tuple[list[str], str]:
    """Rate, filters, window and wavelet choices of the thesis training screen.

    Returns the extra command-line options (only those that differ from the
    thesis, so the default command stays the menu's) and the tag that
    mestrado_emg.features.LegacyFeatureConfig.tag() gives the same choices.
    ``canais`` is the recording's channel count, which the training reads from
    the file itself; it only enters the tag.
    """
    fs = _num(p, "fs", 200, 20, 20000)
    filtros, tag_filtros = _filtros(p, opc, float(fs))
    janela = _num(p, "janela", 250, 20, 2000)
    wavelet = str(p.get("wavelet", "db7"))
    if not WAVELET.fullmatch(wavelet):
        raise Recusado(f"Wavelet desconhecida: {wavelet!r} (ex.: db7, sym4, coif2, haar).")
    niveis = _int(p, "niveis", 4, 1, 10)
    modo = _escolha(p, "modo", ["mestrado", "faixas"], "mestrado")
    args, partes = [], []  # args in the menu's order, tag in LegacyFeatureConfig.tag()'s
    if fs != "200":
        args += ["--fs", fs]
        partes.append(f"fs{fs}")
    if canais != 8:
        partes.append(f"c{canais}")
    args += filtros
    if tag_filtros:
        partes.append(tag_filtros)
    if janela != "250":
        args += ["--window-ms", janela]
    if (wavelet, niveis) != ("db7", 4):
        args += ["--wavelet", wavelet, "--levels", str(niveis)]
        partes.append(f"{wavelet}-n{niveis}")
    if modo == "faixas":
        camadas = p.get("camadas", [1, 2])
        if not isinstance(camadas, list) or not all(
            isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= niveis for n in camadas
        ):
            raise Recusado(f"Camadas: números de 1 a {niveis} (1 = a faixa mais aguda).")
        camadas = sorted(set(camadas))
        aproximacao = _bool(p, "aproximacao", False)
        if not camadas and not aproximacao:
            raise Recusado("Nenhuma faixa marcada: escolha ao menos uma camada ou a aproximação.")
        args += ["--wavelet-mode", "bands", "--layers", *map(str, camadas)]  # may be empty
        if aproximacao:
            args.append("--approx")
        partes.append("D" + "".join(map(str, camadas)) + ("A" if aproximacao else ""))
    if janela != "250":
        partes.append(f"w{janela}")
    return args, "-".join(partes)


def _canais(opc: dict, gravacao: str) -> int:
    return opc.get("gravacoes", {}).get(gravacao, {}).get("canais") or 8


def plano_treino(p: dict, amb: Ambiente, opc: dict) -> Plano:
    csv, feature, divisao, semente = _treino_args(p, opc)
    extra, _ = _sinal(p, opc, _canais(opc, csv))
    argv = [
        *_compose(BASE), "run", "--rm", "train",
        "ros2", "run", "mestrado_emg", "train_legacy", f"/data/{csv}", "--out", "/models",
        "--feature", feature, "--split", divisao, "--seed", str(semente), *_teste(p), *extra,
    ]  # fmt: skip
    return Plano("Treinar os classificadores", [Comando(argv)])


def pasta_analise(csv: str, feature: str, divisao: str, tag: str = "") -> str:
    """Folder name analyze_legacy writes to (mestrado_emg.training.run_name)."""
    stem = re.sub(r"[^A-Za-z0-9]+", "-", csv.removesuffix(".csv")).strip("-")
    return f"{stem}_{feature}_{divisao}" + (f"_{tag}" if tag else "")


def plano_analise(p: dict, amb: Ambiente, opc: dict) -> Plano:
    csv, feature, divisao, semente = _treino_args(p, opc)
    extra, tag = _sinal(p, opc, _canais(opc, csv))
    particoes = _int(p, "particoes", 5, 2, 20)
    canais = str(p.get("canais", "1 2")).split()
    if len(canais) != 2 or not all(re.fullmatch(r"[1-8]", c) for c in canais):
        raise Recusado("Canais: dois números de 1 a 8, separados por espaço (ex.: 1 2).")
    argv = [
        *_compose(BASE), "run", "--rm", "train",
        "ros2", "run", "mestrado_emg", "analyze_legacy", f"/data/{csv}", "--out", "/models/analise",
        "--feature", feature, "--split", divisao, "--seed", str(semente), *_teste(p),
        "--cv", str(particoes), "--pair", *canais, *extra,
    ]  # fmt: skip
    return Plano(
        f"Analisar os resultados → {pasta_analise(csv, feature, divisao, tag)}", [Comando(argv)]
    )


GESTOS_CSV = "gestos_1khz.csv"  # scripts/fetch_gesture_data.sh


def plano_lstm(p: dict, amb: Ambiente, opc: dict) -> Plano:
    """The course project's LSTM again, split three ways (mestrado_emg.lstm_gestos).

    Its own image (PyTorch), built on the first run and a cache hit after that.
    """
    if GESTOS_CSV not in opc["csvs"]:
        raise Recusado(
            f"Falta data/{GESTOS_CSV}: baixe em Manutenção → Dados → Gestos da disciplina."
        )
    epocas = _int(p, "epocas", 200, 1, 1000)
    sementes = _int(p, "repeticoes", 3, 1, 10)
    extra = [] if epocas == 200 else ["--epocas", str(epocas)]
    extra += [] if sementes == 3 else ["--repeticoes", str(sementes)]
    c = [*_compose(BASE), "--profile", "lstm"]
    argv = [
        *c, "run", "--rm", "lstm", "python3", "-m", "mestrado_emg.lstm_gestos",
        f"/data/{GESTOS_CSV}", "--out", "/models/analise", *extra,
    ]  # fmt: skip
    pasta = pasta_analise(GESTOS_CSV, "lstm", "").rstrip("_")
    pasta += "" if epocas == 200 else f"-e{epocas}"
    return Plano(
        f"Refazer a LSTM da disciplina → {pasta}", [Comando([*c, "build", "lstm"]), Comando(argv)]
    )


def plano_abrir_figuras(p: dict, amb: Ambiente, opc: dict) -> Plano:
    if not opc["analises"]:
        raise Recusado("Ainda não há análises em models/analise: rode Analisar antes.")
    pasta = _escolha(p, "pasta", opc["analises"], opc["analises"][-1])
    caminho = f"models/analise/{pasta}"
    if amb.wsl:  # Explorer, through WSL interop
        argv = ["sh", "-c", 'explorer.exe "$(wslpath -w "$1")"; true', "sh", caminho]
    else:
        argv = ["xdg-open", caminho]
    return Plano(f"Abrir as figuras de {pasta}", [Comando(argv)])


def plano_abrir_docker(p: dict, amb: Ambiente, opc: dict) -> Plano:
    if not amb.wsl:
        raise Recusado("Abrir o Docker Desktop daqui só funciona no Windows (WSL).")
    exe = r"$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    argv = ["powershell.exe", "-NoProfile", "-Command", f'Start-Process "{exe}"']
    return Plano("Abrir o Docker Desktop", [Comando(argv)])


Construtor = Callable[[dict, Ambiente, dict], Plano]


def _parar(titulo: str, servicos: list[str]) -> Construtor:
    def plano(p: dict, amb: Ambiente, opc: dict) -> Plano:
        c = _compose(BASE, DESKTOP if amb.desktop else None)
        return Plano(titulo, [Comando([*c, "stop", *servicos])])

    return plano


def _ver(titulo: str, servico: str) -> Construtor:
    """Logs of a simulation started before the panel (or whose output was closed)."""

    def plano(p: dict, amb: Ambiente, opc: dict) -> Plano:
        return Plano(titulo, [_seguir(_compose(BASE), [servico], ultimas=200)])

    return plano


def _script(titulo: str, *argv: str) -> Construtor:
    def plano(p: dict, amb: Ambiente, opc: dict) -> Plano:
        return Plano(titulo, [Comando(list(argv))])

    return plano


# action -> (build the plan, needs the Docker engine)
ACOES: dict[str, tuple[Construtor, bool]] = {
    "braco": (plano_braco, True),
    "sistema": (plano_sistema, True),
    "espelho": (plano_espelho, True),
    "parar_braco": (_parar("Parar o braço", ["braco", "web", "web-portas"]), True),
    "parar_sistema": (_parar("Parar o sistema completo", ["sim", "web", "web-portas"]), True),
    "parar_espelho": (_parar("Parar o modo espelho", ["espelho", "web", "web-portas"]), True),
    "ver_braco": (_ver("Saída do braço", "braco"), True),
    "ver_sistema": (_ver("Saída do sistema completo", "sim"), True),
    "ver_espelho": (_ver("Saída do modo espelho", "espelho"), True),
    "captura": (plano_captura, True),
    "treino": (plano_treino, True),
    "analise": (plano_analise, True),
    "lstm": (plano_lstm, True),
    "abrir_figuras": (plano_abrir_figuras, False),
    "testes_rapido": (_script("Testes (rápido)", "scripts/ci_local.sh", "--rapido"), True),
    "testes_completo": (_script("Testes (completo)", "scripts/ci_local.sh"), True),
    "verificar": (_script("Verificar o Docker", "scripts/check_docker.sh"), False),
    "dados": (_script("Baixar os dados do mestrado", "scripts/fetch_legacy_data.sh"), False),
    "dados_gestos": (
        _script("Baixar os dados de gestos da disciplina", "scripts/fetch_gesture_data.sh"),
        False,
    ),
    "imagem": (_script("Construir a imagem", "docker", "compose", "-f", BASE, "build"), True),
    "parar_tudo": (_script("Parar tudo", "scripts/stop.sh"), True),
    "abrir_docker": (plano_abrir_docker, False),
}


def conflito(alvo: str | None, rodando: set[str]) -> str | None:
    """Why `alvo` cannot start now, or None."""
    if alvo is None:
        return None
    if alvo in rodando:
        return f"{NOMES[alvo].capitalize()} já está rodando."
    outros = sorted((rodando & PRINCIPAIS) - {alvo})
    if outros:
        return (
            f"Já está rodando {NOMES[outros[0]]}. Pare antes de começar outro: dois ao mesmo "
            "tempo publicam nos mesmos tópicos e as leituras se misturam sem erro."
        )
    return None


# ---------------------------------------------------------------------- tasks


class Tarefa:
    """One plan being run: its commands in order, output kept for the page."""

    def __init__(self, id_: int, acao: str, plano: Plano, repo: Path) -> None:
        self.id, self.acao, self.titulo = id_, acao, plano.titulo
        self.passos, self.repo = plano.passos, repo
        self.linhas: list[str] = []
        self.base = 0  # index of linhas[0] since the start (old lines are dropped)
        self.inicio, self.fim = time.time(), None
        self.codigo: int | None = None
        self.proc: subprocess.Popen | None = None
        self.parando = False
        self.lock = threading.Lock()
        threading.Thread(target=self._rodar, daemon=True).start()

    @property
    def rodando(self) -> bool:
        return self.fim is None

    def _anotar(self, linha: str) -> None:
        with self.lock:
            self.linhas.append(ANSI.sub("", linha.rstrip("\n")))
            excesso = len(self.linhas) - MAX_LINHAS
            if excesso > 0:
                del self.linhas[:excesso]
                self.base += excesso

    def _rodar(self) -> None:
        codigo = 0
        for cmd in self.passos:
            if self.parando:
                break
            self._anotar(f"$ {cmd}")
            try:
                self.proc = subprocess.Popen(
                    cmd.argv,
                    cwd=self.repo,
                    env={**os.environ, **cmd.env},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    bufsize=1,
                    start_new_session=True,  # its own group: stopped as a whole
                )
            except OSError as e:
                self._anotar(f"não foi possível executar: {e}")
                codigo = 127
                break
            for linha in self.proc.stdout:
                self._anotar(linha)
            codigo = self.proc.wait()
            if codigo != 0:
                break
        self.codigo = codigo
        self.fim = time.time()
        print(f"  ■ {self.titulo}: terminou com código {codigo}", flush=True)

    def parar(self) -> None:
        """Like Ctrl+C in a terminal: SIGINT to the whole process group."""
        self.parando = True
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGINT)
            except ProcessLookupError:
                pass

    def ler(self, desde: int) -> dict:
        with self.lock:
            inicio = max(desde, self.base)
            linhas = self.linhas[inicio - self.base :]
            return {
                "linhas": linhas,
                "proximo": self.base + len(self.linhas),
                "rodando": self.rodando,
                "codigo": self.codigo,
            }

    def resumo(self) -> dict:
        return {
            "id": self.id,
            "acao": self.acao,
            "titulo": self.titulo,
            "rodando": self.rodando,
            "codigo": self.codigo,
            "inicio": self.inicio,
            "fim": self.fim,
        }


def _impressao() -> str:
    """Fingerprint of this file, taken again on every status request."""
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return ""


class Painel:
    def __init__(self, repo: Path = REPO, docker: Docker | None = None) -> None:
        self.repo = repo
        self.docker = docker or Docker(repo)
        self.tarefas: dict[int, Tarefa] = {}
        self.ids = itertools.count(1)
        self.lock = threading.Lock()
        # The page is read from disk on every visit, the server only at start:
        # after an update, an old server would silently ignore new options.
        self.impressao = _impressao()

    @property
    def desatualizado(self) -> bool:
        return _impressao() != self.impressao

    def estado(self) -> dict:
        info = self.docker.info()
        amb = Ambiente.detectar(info["desktop"])
        rodando = self.docker.rodando() if info["ok"] else []
        with self.lock:
            tarefas = [t.resumo() for t in self.tarefas.values()]
        return {
            "docker": info,
            "ambiente": {"wsl": amb.wsl, "janela": amb.janela is not None, "desktop": amb.desktop},
            "rodando": rodando,
            "tarefas": tarefas,
            "opcoes": opcoes(self.repo),
            "pagina_braco": _porta_aberta(8080),
            "desatualizado": self.desatualizado,
        }

    def iniciar(self, acao: str, params: dict) -> Tarefa:
        if acao not in ACOES:
            raise Recusado(f"Ação desconhecida: {acao!r}.")
        if self.desatualizado and not acao.startswith(("parar", "ver_")):
            raise Recusado(
                "O painel foi atualizado depois de aberto. Feche a janela do painel e abra "
                "de novo (Parar continua funcionando)."
            )
        construir, precisa_docker = ACOES[acao]
        with self.lock:
            if any(t.acao == acao and t.rodando for t in self.tarefas.values()):
                raise Recusado("Isso já está em andamento: veja a saída ao lado.")
            info = self.docker.info()
            if precisa_docker and not info["ok"]:
                raise Recusado(
                    "O Docker não responde. Abra o Docker Desktop (ou use Verificar o Docker)."
                )
            plano = construir(params, Ambiente.detectar(info["desktop"]), opcoes(self.repo))
            if plano.alvo:
                motivo = conflito(plano.alvo, {c["servico"] for c in self.docker.rodando()})
                if motivo:
                    raise Recusado(motivo)
            tarefa = Tarefa(next(self.ids), acao, plano, self.repo)
            self.tarefas[tarefa.id] = tarefa
            for velho in list(self.tarefas)[:-30]:  # keep the last 30
                if not self.tarefas[velho].rodando:
                    del self.tarefas[velho]
        print(f"  ▶ {plano.titulo}", flush=True)
        return tarefa

    def encerrar(self, espera: float = 8.0) -> None:
        """Stop what the panel itself is running; detached simulations keep going."""
        vivas = [t for t in self.tarefas.values() if t.rodando]
        for t in vivas:
            t.parar()
        limite = time.time() + espera
        while any(t.rodando for t in vivas) and time.time() < limite:
            time.sleep(0.1)
        for t in vivas:
            if t.rodando and t.proc is not None:
                try:
                    os.killpg(t.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass


def _porta_aberta(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.2):
            return True
    except OSError:
        return False


# ----------------------------------------------------------------------- http


class Manipulador(BaseHTTPRequestHandler):
    server: Servidor

    def log_message(self, formato: str, *args) -> None:  # quiet: the panel prints its own lines
        pass

    def _host_ok(self) -> bool:
        porta = self.server.server_address[1]
        validos = {f"{h}:{porta}" for h in ("localhost", "127.0.0.1", "[::1]")}
        return self.headers.get("Host", "") in validos

    def _responder(self, status: int, corpo: bytes, tipo: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, status: int, dados: dict) -> None:
        self._responder(status, json.dumps(dados, ensure_ascii=False).encode(), "application/json")

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._json(HTTPStatus.FORBIDDEN, {"erro": "Host não permitido"})
        url = urlparse(self.path)
        painel = self.server.painel
        if url.path in ("/", "/index.html"):
            return self._responder(HTTPStatus.OK, PAGINA.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/estado":
            return self._json(HTTPStatus.OK, painel.estado())
        if url.path == "/api/saida":
            q = parse_qs(url.query)
            try:
                tarefa = painel.tarefas[int(q["tarefa"][0])]
                desde = int(q.get("desde", ["0"])[0])
            except (KeyError, ValueError):
                return self._json(HTTPStatus.NOT_FOUND, {"erro": "tarefa desconhecida"})
            return self._json(HTTPStatus.OK, tarefa.ler(desde))
        self._json(HTTPStatus.NOT_FOUND, {"erro": "não encontrado"})

    def do_POST(self) -> None:
        if not self._host_ok() or self.headers.get("X-Painel") != "1":
            return self._json(HTTPStatus.FORBIDDEN, {"erro": "pedido recusado"})
        tamanho = int(self.headers.get("Content-Length", "0") or 0)
        if tamanho > 65536:
            return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"erro": "pedido grande demais"})
        try:
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
            if not isinstance(corpo, dict):
                raise ValueError
        except ValueError:
            return self._json(HTTPStatus.BAD_REQUEST, {"erro": "JSON inválido"})
        painel = self.server.painel
        url = urlparse(self.path)
        if url.path == "/api/acao":
            params = corpo.get("params") or {}
            if not isinstance(params, dict):
                return self._json(HTTPStatus.BAD_REQUEST, {"erro": "params deve ser um objeto"})
            try:
                tarefa = painel.iniciar(str(corpo.get("acao", "")), params)
            except Recusado as e:
                return self._json(HTTPStatus.CONFLICT, {"erro": str(e)})
            return self._json(HTTPStatus.OK, {"tarefa": tarefa.id})
        if url.path == "/api/parar_tarefa":
            tarefa = painel.tarefas.get(corpo.get("tarefa"))
            if tarefa is None:
                return self._json(HTTPStatus.NOT_FOUND, {"erro": "tarefa desconhecida"})
            tarefa.parar()
            return self._json(HTTPStatus.OK, {"ok": True})
        self._json(HTTPStatus.NOT_FOUND, {"erro": "não encontrado"})


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, endereco: tuple[str, int], painel: Painel) -> None:
        self.painel = painel
        super().__init__(endereco, Manipulador)


def _abrir_navegador(url: str) -> None:
    if Ambiente.detectar(False).wsl and shutil.which("explorer.exe"):
        subprocess.Popen(
            ["explorer.exe", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    elif shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Painel do projeto no navegador.")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--abrir", action="store_true", help="abre o navegador")
    args = ap.parse_args(argv)

    painel = Painel()
    try:
        servidor = Servidor(("127.0.0.1", args.porta), painel)
    except OSError as e:
        print(f"Não consegui usar a porta {args.porta} ({e}). O painel já está aberto?")
        print(f"Tente http://localhost:{args.porta} ou outra porta: --porta {args.porta + 1}")
        return 1
    url = f"http://localhost:{args.porta}"
    print(f"\nPainel do projeto em {url}")
    print("Deixe esta janela aberta enquanto usa o painel. Para encerrar: Ctrl+C.")
    print("As simulações continuam depois disso; pare-as no painel ou com scripts/stop.sh.\n")

    def sair(*_):
        raise KeyboardInterrupt

    for sinal in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sinal, sair)
    if args.abrir:
        threading.Timer(0.5, _abrir_navegador, args=(url,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print("\nEncerrando o painel...")
        servidor.server_close()
        painel.encerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
