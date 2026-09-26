"""gz_sim_group must take down the whole process group on SIGINT/SIGTERM."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "ros2_ws/src/mestrado_bringup/scripts/gz_sim_group"

# Mimics `gz sim` with GUI: the parent exits on the stop signal without
# forwarding it, and its two children (server + GUI) are stubborn -- they
# ignore SIGINT and SIGTERM -- so only the wrapper's final sweep can end them.
FAKE_GZ = r"""
import signal, subprocess, sys, time
child = (
    "import signal, time; "
    "signal.signal(signal.SIGINT, signal.SIG_IGN); "
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "time.sleep(60)"
)
kids = [subprocess.Popen([sys.executable, "-c", child]) for _ in range(2)]
print(" ".join(str(k.pid) for k in kids), flush=True)
time.sleep(60)
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # Zombies still answer kill(0); check /proc when available.
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().split()[2] == "Z")


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX process groups")
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_stop_signal_reaches_every_process(sig):
    proc = subprocess.Popen(
        [sys.executable, str(WRAPPER), sys.executable, "-c", FAKE_GZ],
        stdout=subprocess.PIPE,
        text=True,
    )
    kids = [int(p) for p in proc.stdout.readline().split()]
    assert len(kids) == 2 and all(_alive(k) for k in kids)

    proc.send_signal(sig)
    assert proc.wait(timeout=10) != 0
    deadline = time.monotonic() + 5
    while any(_alive(k) for k in kids) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(_alive(k) for k in kids)


def test_wrapper_passes_exit_code_through():
    rc = subprocess.run(
        [sys.executable, str(WRAPPER), sys.executable, "-c", "raise SystemExit(3)"]
    ).returncode
    assert rc == 3
