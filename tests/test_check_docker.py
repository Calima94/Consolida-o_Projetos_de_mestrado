"""scripts/check_docker.sh: each failure mode maps to its exit code and advice.

The script runs with a PATH that holds only the tools it needs plus a fake
`docker`, so every state (no CLI, Windows CLI via interop, engine down,
project container running, all good) can be simulated without Docker Desktop.
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_docker.sh"
TOOLS = ["bash", "grep", "timeout", "tr", "head", "cut", "cat", "dirname", "sed"]

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="bash script for WSL/Linux")


def _fake_docker(info_ok=True, running_ids=""):
    info = "exit 0" if info_ok else "exit 1"
    return f"""#!/bin/bash
case "$1" in
  info) {info} ;;
  compose) printf '%s' "{running_ids}" ;;
  ps) echo "mestrado-sim-1  (Up 5 minutes)" ;;
  version) echo "  cliente 29.8.0, servidor 29.8.0" ;;
esac
"""


def _run(tmp_path, docker=None, wsl=True, docker_dir_name="bin"):
    bindir = tmp_path / "tools"
    bindir.mkdir(exist_ok=True)
    for tool in TOOLS:
        src = shutil.which(tool)
        assert src, tool
        dst = bindir / tool
        if not dst.exists():
            dst.symlink_to(src)
    path = [str(bindir)]
    if docker is not None:
        ddir = tmp_path / docker_dir_name
        ddir.mkdir(parents=True, exist_ok=True)
        exe = ddir / "docker"
        exe.write_text(docker)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        path.insert(0, str(ddir))
    env = {"PATH": os.pathsep.join(path), "HOME": str(tmp_path)}
    if wsl:
        env["CHECK_DOCKER_FORCE_WSL"] = "1"
    # Stand-in for /mnt/: a docker found under it is the Windows binary via interop.
    env["CHECK_DOCKER_WINDOWS_PREFIX"] = str(tmp_path / "mnt") + "/"
    return subprocess.run(
        [str(bindir / "bash"), str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30
    )


def test_outside_wsl_says_it_is_for_the_ubuntu_terminal(tmp_path):
    r = _run(tmp_path, docker=_fake_docker(), wsl=False)
    assert r.returncode == 2
    assert "terminal do Ubuntu no WSL2" in r.stdout


def test_missing_cli_explains_causes_a_and_b_in_order(tmp_path):
    r = _run(tmp_path, docker=None)
    assert r.returncode == 1
    out = r.stdout
    assert "não encontrado" in out
    assert out.index("Causa A") < out.index("Causa B")
    assert "wsl --set-default Ubuntu" in out
    assert "costuma não ser isso" in out  # the WSL-integration toggle warning
    assert "rodando = ?" in out  # no interop in the test: unknown, not a guess


def test_windows_cli_through_interop_is_not_integration(tmp_path):
    r = _run(tmp_path, docker=_fake_docker(), docker_dir_name="mnt/c/Users/x/DockerDesktop/bin")
    assert r.returncode == 1
    assert "binário do Windows" in r.stdout
    assert "NÃO é a integração funcionando" in r.stdout
    assert "Causa A" in r.stdout


def test_engine_down(tmp_path):
    r = _run(tmp_path, docker=_fake_docker(info_ok=False))
    assert r.returncode == 3
    assert "motor do Docker não respondeu" in r.stdout


def test_project_container_running_blocks_with_two_sim_warning(tmp_path):
    r = _run(tmp_path, docker=_fake_docker(running_ids="abc123"))
    assert r.returncode == 4
    assert "        mestrado-sim-1" in r.stdout  # indented under the message
    assert "./scripts/stop.sh" in r.stdout


def test_all_good_prints_versions(tmp_path):
    r = _run(tmp_path, docker=_fake_docker())
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cliente 29.8.0, servidor 29.8.0" in r.stdout
    assert "Tudo certo" in r.stdout
