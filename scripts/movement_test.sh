#!/usr/bin/env bash
# End-to-end test of the movement replay (used by CI): a Reach&Grasp elbow
# recording drives the Gazebo arm, which must follow its shape.
#   scripts/fetch_reach_grasp.py --subjects 1 --tasks ReaCyl
#   docker run --rm --init -v $PWD/data:/data -v $PWD/scripts:/scripts \
#     mestrado-ros:lyrical /scripts/movement_test.sh
set -euo pipefail
set -m  # background jobs must receive SIGINT (see integration_test.sh)
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== movimento real (Reach&Grasp sub-01 ReaCyl) no braço do Gazebo"
ros2 launch mestrado_bringup movimento.launch.py gui:=false subject:=1 task:=ReaCyl \
  > /tmp/movement.log 2>&1 &
sleep 6
status=0
python3 "$HERE/check_movement.py" --duration 60 --settle 5 || status=1
"$HERE/stop.sh" | tee /tmp/stop.log
grep -q "encerrado limpo" /tmp/stop.log || { echo "FAIL: shutdown needed escalation"; status=1; }
[ "$status" -eq 0 ] || tail -30 /tmp/movement.log
exit "$status"
