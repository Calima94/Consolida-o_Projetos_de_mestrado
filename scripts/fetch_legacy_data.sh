#!/usr/bin/env bash
# Download the master's thesis data into ./data, pinned to a fixed commit of
# https://github.com/Calima94/Train_Myo_Signals so every run uses exactly the
# same bytes. SHA-256 sums are checked after download.
#
# - Raw_EMG_Data/*.csv: raw Myo recordings (200 Hz, 8 channels + category)
# - training_matrix_csv_m_class.csv: the feature matrix the thesis trained on
# - scores_of_classifiers.csv: the historical test scores
# The last two are the golden references of tests/test_training.py.
set -euo pipefail

COMMIT="20fca8ad610ea631fc0a992e652dbc06f7081070"
BASE="https://raw.githubusercontent.com/Calima94/Train_Myo_Signals/${COMMIT}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/data"
mkdir -p "$DEST"

FILES=(
  "Raw_EMG_Data/6_10_20220.csv"
  "Raw_EMG_Data/train_with_openCV_list_16_05.csv"
  "Raw_EMG_Data/train_with_openCV_list_16_051.csv"
  "M_Class_Data/training_matrix_csv_m_class.csv"
  "scores_of_classifiers.csv"
)

for f in "${FILES[@]}"; do
  curl -fsSL --retry 3 "${BASE}/${f}" -o "${DEST}/$(basename "${f}")"
  echo "ok ${f}"
done

cd "$DEST"
sha256sum -c <<'SUMS'
662982f2cfea591dc9e120bc1caa514b25fd834d52ced50f986eb0be8376a6a8  6_10_20220.csv
6e0fc3ad04ac64e40751d739d9c3128e789d821a0d33b1aaec4f8986ed9b2a7c  train_with_openCV_list_16_05.csv
f6a81bb10319197e6553539c3062b2bd6efe2ccf32a12dd89b9493084786b686  train_with_openCV_list_16_051.csv
94ec06863d112079480051ffca5e79652bd4e1ab07bdd9c6c7070de2cfcec5f8  training_matrix_csv_m_class.csv
4646c49a89365d2f68ccdb8936c5e213e61b305e1bcb34c58d3a8c450a848e6c  scores_of_classifiers.csv
SUMS
