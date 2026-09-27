#!/usr/bin/env bash
# Run locally, in Docker, what CI runs (.github/workflows/ci.yml), so that no
# Python or ROS is needed on the host. Every step runs even if an earlier one
# failed; a summary comes at the end, and the exit code is 0 only if all passed.
#
# Usage (WSL Ubuntu terminal on Windows, or Linux):
#   scripts/ci_local.sh            # everything, as in CI (a few minutes)
#   scripts/ci_local.sh --rapido   # compose, ruff and tests only (~1 min): no build, no end-to-end
#
# Differences from CI, on purpose:
# - ruff and the host-Python test job run inside the image; the tests there are
#   a superset (they also run the ones that need ROS);
# - the repository is mounted read-only and ruff runs without a cache, so
#   nothing owned by root is left in the clone;
# - the end-to-end containers use their own ROS_DOMAIN_ID, so they never mix
#   with a simulator left running (docs/COMO_RODAR.md: two simulators publish
#   on the same topics without any error);
# - the thesis data is only downloaded when it is missing.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1
IMAGE=mestrado-ros:lyrical
DOMAIN=97  # anything but the default 0 of compose.yaml
RUFF="$(grep -o 'ruff==[0-9.]*' .github/workflows/ci.yml | head -1)"  # the same pin as CI
LOGS="${TMPDIR:-/tmp}/ci_local"
QUICK=0
[ "${1:-}" = --rapido ] && QUICK=1

names=()
codes=()

# step <log name> <description> <command...>
step() {
  local log="$LOGS/$(printf '%02d' "${#names[@]}")_$1.log" desc="$2" start rc secs
  shift 2
  printf '  %s ... ' "$desc"
  start=$(date +%s)
  "$@" >"$log" 2>&1
  rc=$?
  secs=$(($(date +%s) - start))
  names+=("$desc")
  codes+=("$rc")
  if [ "$rc" -eq 0 ]; then
    echo "ok (${secs} s)"
  else
    echo "FALHOU (código $rc, ${secs} s)"
    tail -15 "$log" | sed 's/^/      | /'
  fi
}

compose_config() {
  local f
  docker compose -f docker/compose.yaml config -q || return 1
  for f in docker/compose.*.yaml; do
    echo "$f"
    docker compose -f docker/compose.yaml -f "$f" config -q || return 1
  done
}

in_image() {  # the repository read-only in /repo
  docker run --rm -v "$REPO:/repo:ro" -w /repo -e PYTHONDONTWRITEBYTECODE=1 "$@"
}

ruff_checks() {
  in_image --entrypoint bash "$IMAGE" -c \
    "pip install -q --break-system-packages $RUFF && ruff check --no-cache . && ruff format --check --no-cache ."
}

end_to_end() {  # <script in scripts/>
  docker run --rm --init -e "ROS_DOMAIN_ID=$DOMAIN" \
    -v "$REPO/data:/data:ro" -v "$REPO/scripts:/scripts:ro" "$IMAGE" "/scripts/$1"
}

echo
echo "=== Testes do projeto, como no CI$([ "$QUICK" = 1 ] && echo " (rápido)") ==="
if ! docker info >/dev/null 2>&1; then
  echo "  O Docker não responde. Rode scripts/check_docker.sh para ver o motivo."
  exit 3
fi
rm -rf "$LOGS" && mkdir -p "$LOGS"

if [ ! -f data/6_10_20220.csv ] || [ ! -f data/test_2_05.avi ]; then
  step dados "baixar os dados do mestrado" ./scripts/fetch_legacy_data.sh
fi
step compose "arquivos do compose" compose_config
if [ "$QUICK" = 0 ]; then
  step imagem "construir a imagem" docker compose -f docker/compose.yaml build
elif ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "  A imagem $IMAGE não existe: rode sem --rapido, que ela é construída."
  exit 1
fi
step ruff "ruff (lint e formatação, $RUFF)" ruff_checks
step pytest "testes unitários (pytest, na imagem)" in_image "$IMAGE" python3 -m pytest -q -p no:cacheprovider
# The course LSTM needs PyTorch, which only its own image has (docker/Dockerfile.lstm).
# That image is not built here (~1 GB): the step runs once the panel or the menu built it.
if docker image inspect mestrado-lstm:cpu >/dev/null 2>&1; then
  step lstm "LSTM da disciplina (pytest, na imagem da LSTM)" \
    in_image mestrado-lstm:cpu python3 -m pytest -q -p no:cacheprovider tests/test_lstm_gestos.py
fi
if [ "$QUICK" = 0 ]; then
  step analise "análise dos resultados (analyze_legacy)" \
    docker run --rm -v "$REPO/data:/data:ro" "$IMAGE" \
    ros2 run mestrado_emg analyze_legacy /data/6_10_20220.csv --out /tmp/analise
  step ponta_a_ponta "ponta a ponta: sEMG -> classificador -> braço" end_to_end integration_test.sh
  step captura "ponta a ponta: captura e modo espelho" end_to_end capture_test.sh
fi

failed=0
for rc in "${codes[@]}"; do [ "$rc" -eq 0 ] || failed=$((failed + 1)); done
echo
if [ "$failed" -eq 0 ]; then
  echo "Tudo certo: ${#codes[@]} de ${#codes[@]} passos passaram."
else
  echo "$failed de ${#codes[@]} passos falharam. Logs completos em $LOGS"
  if [ -n "${WSL_DISTRO_NAME:-}" ]; then
    echo "  (no Windows: \\\\wsl\$\\$WSL_DISTRO_NAME${LOGS//\//\\})"
  fi
fi
[ "$failed" -eq 0 ]
