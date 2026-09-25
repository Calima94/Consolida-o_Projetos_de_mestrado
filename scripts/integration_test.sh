#!/usr/bin/env bash
# Headless end-to-end test inside the image (used by CI):
#   docker run --rm -v $PWD/data:/data -v $PWD/scripts:/scripts mestrado-ros:lyrical \
#     /scripts/integration_test.sh
set -euo pipefail
MODEL_DIR=/tmp/models
ros2 run mestrado_emg train_legacy /data/6_10_20220.csv --out "$MODEL_DIR" \
  --feature mav --split temporal --seed 42
ros2 launch mestrado_bringup mestrado.launch.py source:=replay gui:=false \
  csv_path:=/data/6_10_20220.csv \
  model_path:="$MODEL_DIR/knn_6-10-20220_mav_temporal_latest.joblib" > /tmp/launch.log 2>&1 &
LAUNCH_PID=$!
trap 'kill -INT $LAUNCH_PID 2>/dev/null || true; wait $LAUNCH_PID 2>/dev/null || true' EXIT
sleep 8
python3 "$(dirname "$0")/check_integration.py" --duration 25 || { tail -40 /tmp/launch.log; exit 1; }
grep -m3 "angle_monitor" /tmp/launch.log || true
