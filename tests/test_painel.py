"""scripts/painel.py: the actions build the menu's commands, refuse bad input and
unsafe requests, and run tasks. Standard library only; no Docker needed."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location("painel", SCRIPTS / "painel.py")
painel = importlib.util.module_from_spec(_spec)
sys.modules["painel"] = painel
_spec.loader.exec_module(painel)

WSL = painel.Ambiente(wsl=True, janela="docker/compose.wsl.yaml", desktop=True)
LINUX = painel.Ambiente(wsl=False, janela="docker/compose.gui.yaml", desktop=False)
OPC = {
    "csvs": ["6_10_20220.csv", "captura_2026-09-260.csv"],
    "videos": ["meu_braco.mp4", "test_2_05.avi"],
    "modelos": [
        "knn_6-10-20220_mav_temporal_latest.joblib",
        "lda_6-10-20220_mav_temporal_latest.joblib",
    ],
    "analises": ["6-10-20220_mav_temporal"],
}


def files(cmd):
    """The -f arguments of a docker compose command."""
    return [cmd.argv[i + 1] for i, a in enumerate(cmd.argv) if a == "-f"]


# ------------------------------------------------------------------ commands


def test_arm_on_docker_desktop_brings_the_relay_and_no_window_by_default():
    up, logs = painel.plano_braco({}, WSL, OPC).passos
    assert files(up) == ["docker/compose.yaml", "docker/compose.desktop.yaml"]
    assert up.argv[-4:] == ["up", "-d", "braco", "web"]
    assert up.env == {"GUI": "false"}
    assert logs.argv[-6:] == ["logs", "-f", "--no-color", "--tail", "40", "braco"]


def test_arm_with_the_gazebo_window():
    (up, _) = painel.plano_braco({"janela": True}, WSL, OPC).passos
    assert files(up) == [
        "docker/compose.yaml",
        "docker/compose.wsl.yaml",
        "docker/compose.desktop.yaml",
    ]
    assert up.env == {"GUI": "true"}


def test_without_a_display_the_window_option_is_ignored():
    headless = painel.Ambiente(wsl=False, janela=None, desktop=False)
    (up, _) = painel.plano_braco({"janela": True}, headless, OPC).passos
    assert files(up) == ["docker/compose.yaml"] and up.env == {"GUI": "false"}


def test_full_system_defaults_and_myo():
    (up, _) = painel.plano_sistema({}, WSL, OPC).passos
    assert up.env == {
        "GUI": "false",
        "SOURCE": "replay",
        "CSV": "6_10_20220.csv",
        "MODEL": "knn_6-10-20220_mav_temporal_latest.joblib",
    }
    assert up.argv[-4:] == ["up", "-d", "sim", "web"]
    (up, _) = painel.plano_sistema({"fonte": "myo", "pagina": False}, LINUX, OPC).passos
    assert up.env["SOURCE"] == "myo" and "docker/compose.myo.yaml" in files(up)
    assert up.argv[-3:] == ["up", "-d", "sim"]


def test_mirror_flips_every_video_but_the_thesis_one():
    (up, _) = painel.plano_espelho({}, WSL, OPC).passos
    assert up.env["CAMERA"] == "/data/test_2_05.avi" and up.env["FLIP"] == "false"
    assert up.env["GUI"] == up.env["SHOW_WINDOW"] == "true"
    (up, _) = painel.plano_espelho({"video": "meu_braco.mp4"}, WSL, OPC).passos
    assert up.env["FLIP"] == "true"


def test_webcam_only_on_linux():
    with pytest.raises(painel.Recusado):
        painel.plano_espelho({"video": "webcam"}, WSL, OPC)
    (up, _) = painel.plano_espelho({"video": "webcam"}, LINUX, OPC).passos
    assert up.env["CAMERA"] == "0" and "docker/compose.camera.yaml" in files(up)


def test_capture_passes_every_field():
    p = {"categorias": "3", "tolerancia": "7,5", "amostras": 200, "continuo": True, "lado": "left"}
    (run,) = painel.plano_captura(p, WSL, OPC).passos
    assert run.argv[-3:] == ["run", "--rm", "captura"]
    assert run.env == {
        "EMG": "replay",
        "CSV": "6_10_20220.csv",
        "CAMERA": "/data/test_2_05.avi",
        "FLIP": "false",
        "ARM": "left",
        "SHOW_WINDOW": "true",
        "N_CATEGORIES": "3",
        "TOLERANCE": "7.5",
        "SAMPLES": "200",
        "CONTINUOUS": "true",
    }


def test_analysis_folder_name_is_the_one_analyze_legacy_writes():
    assert painel.pasta_analise("6_10_20220.csv", "mav", "temporal") == "6-10-20220_mav_temporal"
    assert painel.pasta_analise("captura_2026-09-260.csv", "rms", "legacy") == (
        "captura-2026-09-260_rms_legacy"
    )


# ------------------------------------------------------- same as scripts/menu.sh


def _menu_commands(answers: str) -> list[str]:
    env = {**os.environ, "MENU_DRY_RUN": "1", "MENU_JANELA": "docker/compose.wsl.yaml"}
    r = subprocess.run(
        ["bash", str(SCRIPTS / "menu.sh")],
        input=answers,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [x.strip()[2:] for x in r.stdout.splitlines() if x.strip().startswith("$ ")]


def _menu_command(answers: str) -> str:
    (line,) = _menu_commands(answers)
    return line


@pytest.mark.skipif(sys.platform != "linux", reason="bash script for WSL/Linux")
def test_training_is_the_menu_command():
    (cmd,) = painel.plano_treino({}, WSL, OPC).passos
    assert " ".join(cmd.argv) == _menu_command("4\n\n\n\n\n\n0\n")


@pytest.mark.skipif(sys.platform != "linux", reason="bash script for WSL/Linux")
def test_analysis_is_the_menu_command():
    p = {"feature": "rms", "divisao": "legacy", "semente": "7", "particoes": "3", "canais": "3 4"}
    (cmd,) = painel.plano_analise(p, WSL, OPC).passos
    assert " ".join(cmd.argv) == _menu_command("5\n\nrms\nlegacy\n7\n\n3\n3 4\n0\n")


@pytest.mark.skipif(sys.platform != "linux", reason="bash script for WSL/Linux")
def test_the_course_hold_out_is_the_menu_command():
    """20 % of test windows, as the course project ran the thesis app."""
    p = {"feature": "rms", "divisao": "legacy", "semente": "5", "teste": "20"}
    (treino,) = painel.plano_treino(p, WSL, OPC).passos
    assert "--seed 5 --test-size 0.2" in " ".join(treino.argv)
    assert " ".join(treino.argv) == _menu_command("4\n\nrms\nlegacy\n5\n20\n0\n")
    (analise,) = painel.plano_analise(p, WSL, OPC).passos
    assert " ".join(analise.argv) == _menu_command("5\n\nrms\nlegacy\n5\n20\n\n\n0\n")


# ------------------------------------------------------------------ refusals


@pytest.mark.parametrize(
    "plano, params",
    [
        (painel.plano_treino, {"csv": "../../etc/passwd"}),
        (painel.plano_treino, {"csv": "nao_existe.csv"}),
        (painel.plano_treino, {"semente": "42; rm -rf /"}),
        (painel.plano_treino, {"teste": "80"}),
        (painel.plano_analise, {"canais": "1 9"}),
        (painel.plano_captura, {"tolerancia": "muito"}),
        (painel.plano_captura, {"categorias": "5"}),
        (painel.plano_sistema, {"modelo": "/models/../x.joblib"}),
        (painel.plano_braco, {"janela": "sim"}),
    ],
)
def test_bad_parameters_are_refused(plano, params):
    with pytest.raises(painel.Recusado):
        plano(params, WSL, OPC)


@pytest.mark.skipif(sys.platform != "linux", reason="bash script for WSL/Linux")
def test_the_course_lstm_is_the_menu_command():
    opc = {**OPC, "csvs": [*OPC["csvs"], "gestos_1khz.csv"]}
    plano = painel.plano_lstm({}, WSL, opc)
    assert plano.titulo.endswith("gestos-1khz_lstm")
    assert [" ".join(c.argv) for c in plano.passos] == _menu_commands("12\n\n\n0\n")
    rapido = painel.plano_lstm({"epocas": "20", "repeticoes": "1"}, WSL, opc)
    assert rapido.passos[1].argv[-4:] == ["--epocas", "20", "--repeticoes", "1"]
    assert rapido.titulo.endswith("gestos-1khz_lstm-e20")
    assert [" ".join(c.argv) for c in rapido.passos] == _menu_commands("12\n20\n1\n0\n")


def test_the_course_lstm_needs_the_gesture_data():
    with pytest.raises(painel.Recusado, match="Gestos da disciplina"):
        painel.plano_lstm({}, WSL, OPC)
    with pytest.raises(painel.Recusado):
        painel.plano_lstm({"epocas": "0"}, WSL, {**OPC, "csvs": ["gestos_1khz.csv"]})


def test_the_gesture_data_download_pins_every_file():
    construir, precisa_docker = painel.ACOES["dados_gestos"]
    (cmd,) = construir({}, WSL, OPC).passos
    assert cmd.argv == ["scripts/fetch_gesture_data.sh"] and not precisa_docker
    texto = (SCRIPTS / "fetch_gesture_data.sh").read_text()
    linhas = re.findall(r'^  "(\d) (\d) (\S+) ([0-9a-f]{64})"$', texto, re.M)
    assert sorted((p, g) for p, g, *_ in linhas) == [
        (str(p), str(g)) for p in range(1, 9) for g in range(5)
    ]
    assert len({drive_id for _, _, drive_id, _ in linhas}) == 40


def test_missing_data_says_what_to_do():
    vazio = {"csvs": [], "videos": [], "modelos": [], "analises": []}
    with pytest.raises(painel.Recusado, match="Baixar os dados"):
        painel.plano_treino({}, WSL, vazio)
    with pytest.raises(painel.Recusado, match="treine antes"):
        painel.plano_sistema({}, WSL, {**OPC, "modelos": []})


def test_one_simulation_at_a_time():
    assert painel.conflito("braco", {"web", "web-portas"}) is None
    assert "já está rodando" in painel.conflito("braco", {"braco", "web"})
    assert "o braço" in painel.conflito("sim", {"braco", "web"})
    assert "o sistema completo" in painel.conflito("captura", {"sim"})
    assert painel.conflito(None, {"sim"}) is None


def test_catalogue_lists_what_exists(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "models" / "analise" / "x_mav_temporal").mkdir(parents=True)
    for nome in ("scores_of_classifiers.csv", "test_2_05.avi", "notas.txt"):
        (tmp_path / "data" / nome).write_text("")
    (tmp_path / "data" / "gestos.csv").write_text(
        "time,chanel1,chanel2,chanel3,chanel4,position\n"
        + "".join(f"{i / 1000:.3f},1,2,3,4,0\n" for i in range(50))
    )
    (tmp_path / "data" / "filtros").mkdir()
    for nome in ("passa_altas.csv", "leia-me.md"):
        (tmp_path / "data" / "filtros" / nome).write_text("")
    for nome in ("knn_a_latest.joblib", "knn_a_2026-09-26.joblib"):
        (tmp_path / "models" / nome).write_text("")
    assert painel.opcoes(tmp_path) == {
        "csvs": ["gestos.csv"],
        "videos": ["test_2_05.avi"],
        "modelos": ["knn_a_latest.joblib"],
        "analises": ["x_mav_temporal"],
        "filtros": ["passa_altas.csv"],
        "gravacoes": {"gestos.csv": {"canais": 4, "taxa": 1000}},
    }


# --------------------------------------------------------------- tasks + http


class FakeDocker:
    def __init__(self, rodando=()):
        self._rodando = [{"servico": s, "nome": f"mestrado-{s}-1", "status": "Up"} for s in rodando]

    def info(self):
        return {"ok": True, "desktop": False, "versao": "0"}

    def rodando(self):
        return self._rodando


def _esperar(tarefa, limite=10):
    fim = time.time() + limite
    while tarefa.rodando and time.time() < fim:
        time.sleep(0.05)
    assert not tarefa.rodando


def python(codigo, env=None):
    return painel.Comando([sys.executable, "-c", codigo], env or {})


def acao_de_teste(monkeypatch, nome, *passos):
    plano = painel.Plano(nome.capitalize(), list(passos))
    monkeypatch.setitem(painel.ACOES, nome, (lambda p, a, o: plano, False))


def test_task_runs_its_steps_in_order_and_stops_at_the_first_failure(tmp_path, monkeypatch):
    acao_de_teste(
        monkeypatch,
        "teste",
        python("print('um')"),
        python("import os; print(os.environ['X']); raise SystemExit(3)", {"X": "dois"}),
        python("print('nunca')"),
    )
    t = painel.Painel(tmp_path, FakeDocker()).iniciar("teste", {})
    _esperar(t)
    saida = t.ler(0)
    assert [x for x in saida["linhas"] if not x.startswith("$ ")] == ["um", "dois"]
    assert saida["linhas"][2].startswith("$ X=dois ")
    assert t.codigo == 3


def test_stopping_a_task_is_like_ctrl_c(tmp_path, monkeypatch):
    dorme = "import time\ntry:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n    print('salvo')"
    acao_de_teste(monkeypatch, "dorme", python(dorme))
    t = painel.Painel(tmp_path, FakeDocker()).iniciar("dorme", {})
    time.sleep(0.5)
    t.parar()
    _esperar(t)
    assert "salvo" in t.ler(0)["linhas"]


def test_a_second_simulation_is_refused(tmp_path):
    p = painel.Painel(tmp_path, FakeDocker(rodando=["braco", "web"]))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "test_2_05.avi").write_text("")
    with pytest.raises(painel.Recusado, match="o braço"):
        p.iniciar("espelho", {})


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    acao_de_teste(monkeypatch, "oi", python("print('oi')"))
    srv = painel.Servidor(("127.0.0.1", 0), painel.Painel(tmp_path, FakeDocker()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _pedir(endereco, caminho, corpo=None, cabecalhos=None, host=None):
    req = urllib.request.Request(
        f"http://{endereco}{caminho}",
        data=None if corpo is None else json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json", **(cabecalhos or {})},
        method="GET" if corpo is None else "POST",
    )
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_status_and_a_task_through_http(servidor):
    status, estado = _pedir(servidor, "/api/estado")
    assert status == 200 and estado["docker"]["ok"] is True
    status, r = _pedir(servidor, "/api/acao", {"acao": "oi"}, {"X-Painel": "1"})
    assert status == 200
    for _ in range(100):
        _, saida = _pedir(servidor, f"/api/saida?tarefa={r['tarefa']}&desde=0")
        if not saida["rodando"]:
            break
        time.sleep(0.05)
    assert saida["codigo"] == 0 and saida["linhas"][-1] == "oi"


def test_post_without_the_panel_header_is_refused(servidor):
    assert _pedir(servidor, "/api/acao", {"acao": "oi"})[0] == 403


def test_other_host_names_are_refused(servidor):
    """DNS rebinding: a page on evil.example resolving to 127.0.0.1."""
    porta = servidor.split(":")[1]
    status, _ = _pedir(
        servidor, "/api/acao", {"acao": "oi"}, {"X-Painel": "1"}, host=f"evil.example:{porta}"
    )
    assert status == 403
    assert _pedir(servidor, "/api/estado", host=f"evil.example:{porta}")[0] == 403


def test_unknown_action_is_a_conflict_with_a_message(servidor):
    status, r = _pedir(servidor, "/api/acao", {"acao": "rm"}, {"X-Painel": "1"})
    assert status == 409 and "desconhecida" in r["erro"]


# ------------------------------------------------ signal parameters (wavelet)

NOVO = {"janela": "300", "wavelet": "sym4", "niveis": "2", "modo": "faixas", "camadas": [1],
        "aproximacao": True}  # fmt: skip
NOVO_ARGS = ["--window-ms", "300", "--wavelet", "sym4", "--levels", "2", "--wavelet-mode", "bands",
             "--layers", "1", "--approx"]  # fmt: skip


def test_thesis_signal_adds_nothing_to_the_command():
    assert painel._sinal({}) == ([], "")
    assert painel._sinal({"modo": "mestrado", "camadas": [3]}) == ([], "")  # no effect there


def test_new_signal_choices_reach_training_and_analysis():
    (treino,) = painel.plano_treino(NOVO, WSL, OPC).passos
    assert treino.argv[-len(NOVO_ARGS) :] == NOVO_ARGS
    plano = painel.plano_analise(NOVO, WSL, OPC)
    assert plano.passos[0].argv[-len(NOVO_ARGS) :] == NOVO_ARGS
    assert plano.titulo.endswith("6-10-20220_mav_temporal_sym4-n2-D1A-w300")


def test_only_the_approximation():
    args, tag = painel._sinal({"modo": "faixas", "camadas": [], "aproximacao": True})
    assert args == ["--wavelet-mode", "bands", "--layers", "--approx"] and tag == "DA"


@pytest.mark.parametrize(
    "p",
    [
        {"wavelet": "db7; rm -rf /"},
        {"wavelet": "morl"},  # continuous: no decomposition
        {"niveis": "0"},
        {"modo": "faixas", "camadas": [5]},
        {"modo": "faixas", "camadas": ["1"]},
        {"modo": "faixas", "camadas": [], "aproximacao": False},
        {"janela": "5"},
    ],
)
def test_bad_signal_choices_are_refused(p):
    with pytest.raises(painel.Recusado):
        painel._sinal(p)


GESTOS = {"fs": "1000", "janela": "200", "filtros": "projetados", "passa_altas_hz": "20",
          "rede_hz": "60"}  # fmt: skip


@pytest.mark.parametrize(
    "p, canais",
    [
        ({}, 8),
        (NOVO, 8),
        ({"wavelet": "db4", "niveis": "2"}, 8),
        ({"modo": "faixas", "camadas": [2, 1]}, 8),
        ({"modo": "faixas", "camadas": [], "aproximacao": True}, 8),
        ({"janela": "500"}, 8),
        (GESTOS, 4),
        ({"fs": "1000"}, 4),
        ({"filtros": "projetados", "rede_hz": "0", "passa_altas_hz": "10.5"}, 8),
        ({"filtros": "arquivos", "arquivo_passa_altas": "hp.json"}, 8),
        (
            {
                "filtros": "arquivos",
                "arquivo_passa_altas": "hp.json",
                "arquivo_rejeita_faixa": "rejeita_60.json",
            },
            2,
        ),  # fmt: skip
    ],
)
def test_the_panel_names_the_folder_the_training_code_will_write(p, canais, tmp_path):
    """The panel's tag and the one train_legacy computes from the panel's own arguments."""
    pytest.importorskip("pywt", reason="needs the pipeline (host CI job or the image)")
    import argparse
    import json

    from mestrado_emg.features import LEGACY_SOS_HIGHPASS, add_pipeline_args, config_from_args

    for nome in ("hp.json", "rejeita_60.json"):  # stand-ins for data/filtros
        (tmp_path / nome).write_text(json.dumps(LEGACY_SOS_HIGHPASS.tolist()))
    args, tag = painel._sinal(p, {"filtros": ["hp.json", "rejeita_60.json"]}, canais)
    args = [a.replace("/data/filtros", str(tmp_path)) for a in args]
    parser = argparse.ArgumentParser()
    add_pipeline_args(parser)
    assert config_from_args(parser.parse_args(args), canais).tag() == tag


def test_gesture_recordings_at_1khz_with_designed_filters():
    args, tag = painel._sinal(GESTOS, None, 4)
    assert args == ["--fs", "1000", "--filters", "design", "--highpass-hz", "20", "--mains-hz",
                    "60", "--window-ms", "200"]  # fmt: skip
    assert tag == "fs1000-c4-hp20-rf60-w200"


@pytest.mark.parametrize(
    "p",
    [
        {"fs": "5"},
        {"filtros": "projetados", "passa_altas_hz": "150"},  # above Nyquist at 200 Hz
        {"filtros": "projetados", "rede_hz": "55"},
        {"filtros": "arquivos"},  # no file chosen
        {"filtros": "arquivos", "arquivo_passa_altas": "../../etc/passwd"},
    ],
)
def test_bad_rate_or_filter_choices_are_refused(p):
    with pytest.raises(painel.Recusado):
        painel._sinal(p, {"filtros": ["hp.json"]})


@pytest.mark.skipif(sys.platform != "linux", reason="bash script for WSL/Linux")
def test_the_menu_asks_the_same_signal_choices():
    menu = _menu_command("4\n\n\n\n\n\ns\n\n\n300\nsym4\n2\nfaixas\n1\ns\n0\n")
    assert menu.endswith("--seed 42 " + " ".join(NOVO_ARGS))
    gestos = _menu_command("4\n\n\n\n\n\ns\n1000\nprojetados\n20\n60\n200\n\n\n\n0\n")
    assert gestos.endswith("--seed 42 " + " ".join(painel._sinal(GESTOS)[0]))


def test_a_panel_older_than_its_file_only_stops_things(tmp_path, monkeypatch):
    """The page is read from disk each visit; the server only at start."""
    p = painel.Painel(tmp_path, FakeDocker())
    acao_de_teste(monkeypatch, "oi", python("print('oi')"))
    acao_de_teste(monkeypatch, "parar_oi", python("print('parado')"))
    assert p.estado()["desatualizado"] is False
    monkeypatch.setattr(painel, "_impressao", lambda: "outra versão")
    assert p.estado()["desatualizado"] is True
    with pytest.raises(painel.Recusado, match="atualizado depois de aberto"):
        p.iniciar("oi", {})
    _esperar(p.iniciar("parar_oi", {}))
