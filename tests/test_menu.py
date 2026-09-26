"""scripts/menu.sh: each option builds the documented docker compose command.

Runs the menu with MENU_DRY_RUN=1 (commands are printed, not run) and answers
piped on stdin; Enter keeps each default.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

MENU = Path(__file__).resolve().parents[1] / "scripts" / "menu.sh"

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="bash script for WSL/Linux")


def _menu(answers: str, janela: str = "docker/compose.wsl.yaml") -> str:
    env = {**os.environ, "MENU_DRY_RUN": "1", "MENU_JANELA": janela}
    env.pop("WSL_DISTRO_NAME", None)
    r = subprocess.run(
        ["bash", str(MENU)], input=answers, env=env, capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 0, r.stderr
    return r.stdout + r.stderr


def _commands(out: str) -> list[str]:
    return [line.strip()[2:] for line in out.splitlines() if line.strip().startswith("$ ")]


def test_defaults_train_the_thesis_file_like_the_compose_service():
    (cmd,) = _commands(_menu("4\n\n\n\n\n0\n"))
    assert cmd == (
        "docker compose -f docker/compose.yaml run --rm train ros2 run mestrado_emg "
        "train_legacy /data/6_10_20220.csv --out /models --feature mav --split temporal --seed 42"
    )


def test_analysis_passes_every_field():
    (cmd,) = _commands(_menu("5\n\nrms\nlegacy\n7\n3\n3 4\n0\n"))
    assert "analyze_legacy /data/6_10_20220.csv --out /models/analise" in cmd
    assert "--feature rms --split legacy --seed 7 --cv 3 --pair 3 4" in cmd


def test_full_system_uses_the_window_file_and_gui():
    (cmd,) = _commands(_menu("7\n\n\n\n0\n"))
    assert cmd.startswith("env GUI=true SOURCE=replay CSV=6_10_20220.csv MODEL=")
    assert cmd.endswith("docker compose -f docker/compose.yaml -f docker/compose.wsl.yaml up sim")


def test_myo_adds_the_dongle_file():
    (cmd,) = _commands(_menu("7\nmyo\n\n0\n"))
    assert "SOURCE=myo" in cmd and "-f docker/compose.myo.yaml" in cmd


def test_without_a_display_the_windows_are_turned_off():
    out = _menu("8\n\n\n\n0\n", janela="")
    (cmd,) = _commands(out)
    assert "GUI=false SHOW_WINDOW=false" in cmd
    assert "compose.wsl.yaml" not in cmd and "compose.gui.yaml" not in cmd
    assert "sem janela" in out


def test_mirror_with_the_thesis_video_does_not_flip():
    (cmd,) = _commands(_menu("8\n\n\n\n0\n"))
    assert "CAMERA=/data/test_2_05.avi FLIP=false ARM=right" in cmd
    assert "compose.camera.yaml" not in cmd


def test_capture_with_a_webcam_number_adds_the_camera_file():
    answers = "9\nreplay\n\n0\n\n\n3\n12\n500\ntrue\n0\n"
    (cmd,) = _commands(_menu(answers))
    assert "EMG=replay" in cmd and "CAMERA=0 FLIP=true" in cmd
    assert "N_CATEGORIES=3 TOLERANCE=12 SAMPLES=500 CONTINUOUS=true" in cmd
    assert "-f docker/compose.camera.yaml" in cmd and "compose.myo.yaml" not in cmd
    assert cmd.endswith("run --rm captura")


def test_stop_and_check_options_call_the_scripts():
    cmds = _commands(_menu("10\n1\n0\n"))
    assert cmds == ["scripts/stop.sh", "scripts/check_docker.sh"]


def test_invalid_option_and_eof_do_not_hang():
    out = _menu("99\n")
    assert "opção inválida: 99" in out
