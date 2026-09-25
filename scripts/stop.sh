#!/usr/bin/env bash
# Stop the simulation and every node it started -- the modern equivalent of
# the thesis "Stop" button (my_arm_def/main.py, stop_myo_and_gazebo(): SIGINT
# to `ros2 launch`, then `killall gzserver gzclient gazebo`).
#
# Usage:
#   scripts/stop.sh            # on the host: stops this project's containers (up and run)
#   scripts/stop.sh            # inside the container / native ROS: see below
#   GRACE=20 scripts/stop.sh   # seconds to wait before escalating (default 10)
#
# Inside a container (or a native ROS install) it
#   1. sends SIGINT to `ros2 launch mestrado_bringup ...` and to Gazebo (like Ctrl+C);
#   2. waits up to GRACE s for launch, Gazebo, the bridge and our nodes to exit;
#   3. escalates to SIGTERM and then SIGKILL for anything still alive.
# The Myo driver disconnects the dongle on SIGINT; if it had to be killed,
# the next connect() clears the stale connection (it disconnects handles 0-2
# before scanning), so no manual reset is needed.
set -u

GRACE="${GRACE:-10}"
LAUNCH_PAT='bin/ros2 launch mestrado_bringup'  # the ros2 CLI process, not shells whose command line mentions it
PROC_PAT="${LAUNCH_PAT}|gz-sim-main|gz-sim-gui-client|ruby .*gz sim|parameter_bridge|mestrado_emg/(myo_driver|emg_replay|emg_classifier|angle_monitor|arm_controller)|mestrado_capture/(elbow_angle_camera|emg_recorder)"

# Host side: stop every running container of this compose project, including
# one-off `docker compose run` containers (the guide's step 4 uses them).
# `docker compose ps -q` and `docker compose stop` ignore those, so list with
# -a and stop by id; they carry init + stop_signal SIGINT from compose.yaml.
if [ ! -f /.dockerenv ] && command -v docker >/dev/null 2>&1; then
  compose_dir="$(cd "$(dirname "$0")/../docker" && pwd)"
  ids="$(docker compose -f "$compose_dir/compose.yaml" ps -a -q --status running 2>/dev/null)"
  if [ -n "$ids" ]; then
    echo "parando $(echo "$ids" | wc -l) container(s) do projeto..."
    # shellcheck disable=SC2086  # one id per word
    docker stop -t "$GRACE" $ids >/dev/null && echo "encerrado"
    exit $?
  fi
fi

wait_gone() {  # $1 = seconds
  local i
  for ((i = 0; i < $1 * 2; i++)); do
    pgrep -f "$PROC_PAT" >/dev/null || return 0
    sleep 0.5
  done
  return 1
}

if ! pgrep -f "$PROC_PAT" >/dev/null; then
  echo "nada rodando"
  exit 0
fi

# Like Ctrl+C in a terminal: SIGINT to launch *and* straight to Gazebo, in
# case something (e.g. a shell wrapper) sits between them and eats the signal.
pkill -INT -f "$LAUNCH_PAT" && echo "SIGINT enviado ao ros2 launch"
pkill -INT -f "gz-sim-main|gz-sim-gui-client" && echo "SIGINT enviado ao Gazebo"
if wait_gone "$GRACE"; then
  echo "encerrado limpo"
  exit 0
fi

echo "ainda há processos após ${GRACE}s; enviando SIGTERM:"
pgrep -af "$PROC_PAT" | cut -c1-120
pkill -TERM -f "$PROC_PAT"
if wait_gone 5; then
  echo "encerrado com SIGTERM"
  exit 0
fi

echo "forçando SIGKILL:"
pgrep -af "$PROC_PAT" | cut -c1-120
pkill -KILL -f "$PROC_PAT"
wait_gone 2 && echo "encerrado com SIGKILL" || { echo "falhou"; exit 1; }
