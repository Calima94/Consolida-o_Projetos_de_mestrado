#!/usr/bin/env bash
# Download the raw Myo recordings of the master's thesis into ./data, pinned to
# a fixed commit of https://github.com/Calima94/Train_Myo_Signals so every run
# uses exactly the same bytes. SHA-256 sums are checked after download.
set -euo pipefail

COMMIT="20fca8ad610ea631fc0a992e652dbc06f7081070"
BASE="https://raw.githubusercontent.com/Calima94/Train_Myo_Signals/${COMMIT}/Raw_EMG_Data"
DEST="$(cd "$(dirname "$0")/.." && pwd)/data"
mkdir -p "$DEST"

FILES=(
  "6_10_20220.csv"
  "train_with_openCV_list_16_05.csv"
  "train_with_openCV_list_16_051.csv"
)

for f in "${FILES[@]}"; do
  curl -fsSL "${BASE}/${f}" -o "${DEST}/${f}"
  echo "ok ${f}"
done

cd "$DEST"
sha256sum -c <<'SUMS'
662982f2cfea591dc9e120bc1caa514b25fd834d52ced50f986eb0be8376a6a8  6_10_20220.csv
6e0fc3ad04ac64e40751d739d9c3128e789d821a0d33b1aaec4f8986ed9b2a7c  train_with_openCV_list_16_05.csv
f6a81bb10319197e6553539c3062b2bd6efe2ccf32a12dd89b9493084786b686  train_with_openCV_list_16_051.csv
SUMS
