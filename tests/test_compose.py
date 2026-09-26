"""Static checks of the Docker Compose files."""

import re
from pathlib import Path

import pytest
import yaml

DOCKER = Path(__file__).resolve().parents[1] / "docker"
COMPOSE_FILES = sorted(DOCKER.glob("compose*.yaml"))


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda p: p.name)
def test_launch_arguments_never_expand_to_empty(path):
    """`ros2 launch` rejects `name:=` with an empty value (bug found in `sim`)."""
    empty_default = re.findall(r"\w+:=\$\{\w+:-\}", path.read_text())
    assert not empty_default, f"{path.name}: {empty_default}"


def test_services_stop_cleanly():
    base = yaml.safe_load((DOCKER / "compose.yaml").read_text())
    anchor = base["x-ros"]
    assert anchor["init"] is True
    assert anchor["stop_signal"] == "SIGINT"
    assert "TINI_KILL_PROCESS_GROUP=1" in anchor["environment"]
    for name in ("sim", "captura", "espelho", "train", "shell"):
        assert name in base["services"]


@pytest.mark.parametrize("override", ["compose.gui.yaml", "compose.wsl.yaml"])
def test_gui_overrides_cover_every_windowed_service(override):
    services = yaml.safe_load((DOCKER / override).read_text())["services"]
    assert {"sim", "captura", "espelho"} <= set(services)
