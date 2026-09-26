#!/usr/bin/env bash
# Headless end-to-end test inside the image (used by CI):
#   docker run --rm --init -v $PWD/data:/data -v $PWD/scripts:/scripts \
#     mestrado-ros:lyrical /scripts/integration_test.sh
# Trains the k-NN, starts the full chain with replayed sEMG, checks that the
# elbow follows the classifier, then checks that everything exits cleanly.
set -euo pipefail
# Job control: without it bash starts background jobs with SIGINT ignored,
# and `ros2 launch` would never see the stop signal.
set -m
HERE="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR=/tmp/models

ros2 run mestrado_emg train_legacy /data/6_10_20220.csv --out "$MODEL_DIR" \
  --feature mav --split temporal --seed 42
ros2 launch mestrado_bringup mestrado.launch.py source:=replay gui:=false \
  csv_path:=/data/6_10_20220.csv \
  model_path:="$MODEL_DIR/knn_6-10-20220_mav_temporal_latest.joblib" > /tmp/launch.log 2>&1 &
sleep 8

status=0
python3 "$HERE/check_integration.py" --duration 25 || status=1

start=$(date +%s.%N)
"$HERE/stop.sh" | tee /tmp/stop.log
elapsed=$(python3 -c "import time; print(f'{time.time() - $start:.1f}')")
echo "shutdown took ${elapsed}s"
grep -q "encerrado limpo" /tmp/stop.log || { echo "FAIL: shutdown needed escalation"; status=1; }
[ "$status" -eq 0 ] || tail -40 /tmp/launch.log
exit "$status"
