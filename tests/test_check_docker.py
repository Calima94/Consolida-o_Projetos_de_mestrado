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


def _fake_windows(bindir, desktop_running, default_distro):
    """Stand-ins for tasklist.exe and wsl.exe reached through WSL interop."""
    task = (
        "Docker Desktop.exe  4242 Console  1  150.000 K"
        if desktop_running
        else "INFO: No tasks are running which match the specified criteria."
    )
    tasklist = bindir / "tasklist.exe"
    tasklist.write_text(f"#!/bin/bash\necho '{task}'\n")
    # wsl.exe prints UTF-16LE with CRLF; the default distro is marked with "*".
    rows = ["  NAME              STATE           VERSION"]
    for name in ("Ubuntu", "docker-desktop"):
        mark = "*" if name == default_distro else " "
        rows.append(f"{mark} {name:<17} Running         2")
    listing = bindir / "wsl-list.txt"
    listing.write_bytes("\r\n".join(rows + [""]).encode("utf-16-le"))
    wsl = bindir / "wsl.exe"
    wsl.write_text(f"#!/bin/bash\ncat '{listing}'\n")
    for exe in (tasklist, wsl):
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path, docker=None, wsl=True, docker_dir_name="bin", windows=None, distro=None):
    bindir = tmp_path / "tools"
    bindir.mkdir(exist_ok=True)
    for tool in TOOLS:
        src = shutil.which(tool)
        assert src, tool
        dst = bindir / tool
        if not dst.exists():
            dst.symlink_to(src)
    if windows is not None:
        _fake_windows(bindir, *windows)
    path = [str(bindir)]
    if docker is not None:
        ddir = tmp_path / docker_dir_name
        ddir.mkdir(parents=True, exist_ok=True)
        exe = ddir / "docker"
        exe.write_text(docker)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        path.insert(0, str(ddir))
    env = {"PATH": os.pathsep.join(path), "HOME": str(tmp_path)}
    # Forced both ways, so the tests also pass inside a Docker Desktop container,
    # whose kernel is WSL's.
    env["CHECK_DOCKER_FORCE_WSL"] = "1" if wsl else "0"
    if distro:
        env["WSL_DISTRO_NAME"] = distro
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


def test_docker_desktop_closed_points_to_a_and_rules_out_b(tmp_path):
    # The state measured on Windows 11 with Docker Desktop closed.
    r = _run(tmp_path, docker=None, windows=(False, "Ubuntu"), distro="Ubuntu")
    assert r.returncode == 1
    out = r.stdout
    assert "rodando = não; distro padrão do WSL = Ubuntu" in out
    assert "Causa provável: A" in out
    assert "Causa B descartada: a distro padrão do WSL já é Ubuntu" in out
    assert "wsl --set-default" not in out


def test_default_distro_docker_desktop_points_to_b(tmp_path):
    r = _run(tmp_path, docker=None, windows=(True, "docker-desktop"), distro="Ubuntu")
    assert r.returncode == 1
    out = r.stdout
    assert "Causa A descartada: o Docker Desktop está rodando" in out
    assert "Causa provável: B" in out
    assert "wsl --set-default Ubuntu" in out
    assert "costuma não ser isso" in out


def test_both_causes_likely_are_shown_a_first(tmp_path):
    r = _run(tmp_path, docker=None, windows=(False, "docker-desktop"), distro="Ubuntu")
    assert r.returncode == 1
    out = r.stdout
    assert out.index("Causa provável: A") < out.index("Causa provável: B")
    assert "descartada" not in out


def test_neither_cause_then_the_integration_toggle_is_the_suspect(tmp_path):
    r = _run(tmp_path, docker=None, windows=(True, "Ubuntu"), distro="Ubuntu")
    assert r.returncode == 1
    out = r.stdout
    assert "Nem a causa A nem a B" in out
    assert "WSL integration, ligue a chave da distro Ubuntu" in out
    assert "costuma não ser isso" not in out


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
    assert "rodando = ?" in r.stdout
    assert "fechado ou ainda subindo" in r.stdout  # no diagnosis: both, as before


def test_engine_down_with_docker_desktop_closed(tmp_path):
    # Rare race: seen once on Windows right after `docker desktop stop`, while
    # /usr/bin/docker was still there; normally a closed Docker Desktop ends in b).
    r = _run(tmp_path, docker=_fake_docker(info_ok=False), windows=(False, "Ubuntu"))
    assert r.returncode == 3
    out = r.stdout
    assert "rodando = não" in out
    assert "O Docker Desktop está fechado (ou acabou de fechar)" in out
    assert "abra o Docker Desktop" in out
    assert "ainda subindo" not in out


def test_engine_down_with_docker_desktop_starting(tmp_path):
    r = _run(tmp_path, docker=_fake_docker(info_ok=False), windows=(True, "Ubuntu"))
    assert r.returncode == 3
    out = r.stdout
    assert "rodando = sim" in out
    assert "aberto, mas o motor ainda não respondeu" in out
    assert "Quit Docker Desktop" in out


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
