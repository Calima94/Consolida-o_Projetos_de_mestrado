#!/usr/bin/env bash
# End-to-end test of the capture tool port, without webcam or sEMG hardware
# (used by CI):
#   docker run --rm --init -v $PWD/data:/data -v $PWD/scripts:/scripts \
#     mestrado-ros:lyrical /scripts/capture_test.sh
# 1. capture: thesis video as the camera + replayed sEMG -> must finish by
#    itself and write 200 samples per category with angles inside the ranges;
# 2. mirror mode: the Gazebo elbow must follow the elbow in the video.
set -euo pipefail
set -m  # background jobs must receive SIGINT (see integration_test.sh)
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT=/tmp/capture_test
rm -rf "$OUT"

echo "== 1. captura (vídeo do mestrado + sEMG reproduzido)"
timeout 120 ros2 launch mestrado_bringup captura.launch.py emg:=replay \
  camera:=/data/test_2_05.avi flip:=false csv_path:=/data/6_10_20220.csv \
  show_window:=false n_categories:=2 tolerance_deg:=10 samples_per_category:=200 \
  out_dir:="$OUT" > /tmp/capture.log 2>&1 || { tail -30 /tmp/capture.log; exit 1; }
python3 - "$OUT" <<'PY'
import glob, sys
import pandas as pd
files = glob.glob(f"{sys.argv[1]}/*.csv")
assert len(files) == 1, files
df = pd.read_csv(files[0])
counts = df["position"].value_counts().to_dict()
print("amostras por categoria:", counts)
assert counts == {1: 200, 2: 200}, counts
a1 = df.loc[df.position == 1, "angle_deg"]
a2 = df.loc[df.position == 2, "angle_deg"]
assert a1.between(160, 180).all() and a2.between(80, 100).all()
print(f"ângulos: cat 1 {a1.min():.1f}-{a1.max():.1f}, cat 2 {a2.min():.1f}-{a2.max():.1f}")
PY

echo "== 2. modo espelho (braço do Gazebo segue o vídeo)"
ros2 launch mestrado_bringup espelho.launch.py gui:=false show_window:=false \
  camera:=/data/test_2_05.avi flip:=false > /tmp/mirror.log 2>&1 &
sleep 6
status=0
python3 "$HERE/check_mirror.py" --duration 30 || status=1
"$HERE/stop.sh" | tee /tmp/stop.log
grep -q "encerrado limpo" /tmp/stop.log || { echo "FAIL: shutdown needed escalation"; status=1; }
[ "$status" -eq 0 ] || tail -30 /tmp/mirror.log
exit "$status"
