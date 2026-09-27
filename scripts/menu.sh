#!/usr/bin/env bash
# Terminal menu for the whole project: the three PyQt windows of the thesis
# (capture, training/results and the Gazebo launcher) as one text menu.
# Each option asks its fields with defaults (Enter keeps the default), shows
# the exact docker compose command and runs it, so the command can also be
# copied and run by hand later.
#
# Usage (from anywhere; WSL Ubuntu terminal on Windows):
#   scripts/menu.sh
#
# MENU_DRY_RUN=1 only prints the commands (used by tests/test_menu.py).
# MENU_JANELA overrides the window file (default: compose.wsl.yaml on WSL,
# compose.gui.yaml with $DISPLAY on Linux, none otherwise).
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1
BASE=(-f docker/compose.yaml)

is_wsl() {
  [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null
}

if [ -n "${MENU_JANELA+x}" ]; then
  JANELA="$MENU_JANELA"
elif is_wsl; then
  JANELA=docker/compose.wsl.yaml
elif [ -n "${DISPLAY:-}" ]; then
  JANELA=docker/compose.gui.yaml
else
  JANELA=""
fi

# ask VAR "question" default -> VAR holds the answer (default on Enter/EOF)
ask() {
  local __var="$1" __q="$2" __def="$3" __ans=""
  read -r -p "  $__q [$__def]: " __ans || true
  printf -v "$__var" '%s' "${__ans:-$__def}"
}

# choose VAR "question" default opt1 opt2 ... -> option text or its number, Enter = default
choose() {
  local __var="$1" __q="$2" __def="$3" __ans="" i=1
  shift 3
  local opts=("$@")
  echo "  $__q"
  for o in "${opts[@]}"; do
    printf '    %d) %s\n' "$i" "$o"
    i=$((i + 1))
  done
  read -r -p "  escolha [$__def]: " __ans || true
  __ans="${__ans:-$__def}"
  # An answer equal to an option is taken as is (e.g. "3" categories);
  # otherwise a number picks the option by position.
  for o in "${opts[@]}"; do
    if [ "$o" = "$__ans" ]; then
      printf -v "$__var" '%s' "$__ans"
      return
    fi
  done
  if [[ "$__ans" =~ ^[0-9]+$ ]] && [ "$__ans" -ge 1 ] && [ "$__ans" -le "${#opts[@]}" ]; then
    __ans="${opts[$((__ans - 1))]}"
  fi
  printf -v "$__var" '%s' "$__ans"
}

# Raw sEMG recordings in data/ (the thesis matrix and scores are not raw data).
raw_csvs() {
  local f
  for f in data/*.csv; do
    [ -e "$f" ] || continue
    case "$(basename "$f")" in
      scores_of_classifiers.csv | training_matrix_csv_m_class.csv) continue ;;
    esac
    basename "$f"
  done
}

pick_csv() {
  local list
  mapfile -t list < <(raw_csvs)
  if [ "${#list[@]}" -eq 0 ]; then
    echo "  (nenhum CSV em data/: rode a opção 2 para baixar os dados do mestrado)"
    ask "$1" "arquivo em data/" "6_10_20220.csv"
  else
    choose "$1" "arquivo de sEMG (em data/):" "6_10_20220.csv" "${list[@]}"
  fi
}

window_files() {
  # Echo "-f <file>" for the window overlay, or warn when there is none.
  if [ -n "$JANELA" ]; then
    echo "-f $JANELA"
  else
    echo "  (sem janela: nem WSL nem \$DISPLAY; o comando roda sem interface)" >&2
  fi
}

run() {
  echo
  printf '  $'
  printf ' %q' "$@"
  echo
  [ "${MENU_DRY_RUN:-}" = 1 ] && return 0
  local ok=""
  read -r -p "  Executar? [S/n]: " ok || true
  case "$ok" in n | N) return 0 ;; esac
  # A handler (not "ignore") so Ctrl+C reaches the command and not this menu;
  # handlers are reset in child processes, ignored signals are inherited.
  trap ':' INT
  "$@"
  local rc=$?
  trap - INT
  echo "  (terminou com código $rc)"
}

# The rate, filter, window and wavelet fields of the thesis training screen,
# behind one question so that Enter keeps the thesis setup. Fills SIGNAL_ARGS
# with the options that differ from it (train_legacy/analyze_legacy --help),
# in the same order as scripts/painel.py. The channels come from the file.
ask_signal() {
  SIGNAL_ARGS=()
  local adv fs filters hp mains fhp fbs janela wavelet levels mode layers approx
  ask adv "ajustar frequência, filtros, janela e wavelet? (s/N)" "n"
  case "$adv" in s | S) ;; *) return ;; esac
  ask fs "frequência de amostragem (Hz)" "200"
  echo "  filtros: 'mestrado' usa os coeficientes do mestrado (feitos para 200 Hz);"
  echo "           'projetados' calcula para a frequência acima; 'arquivos' lê de data/filtros/"
  choose filters "filtros:" "mestrado" mestrado projetados arquivos
  [ "$fs" = 200 ] || SIGNAL_ARGS+=(--fs "$fs")
  case "$filters" in
    projetados)
      ask hp "passa-altas (Hz)" "20"
      choose mains "rede elétrica (Hz; 0 = sem rejeita-faixa):" "60" 60 50 0
      SIGNAL_ARGS+=(--filters design --highpass-hz "$hp" --mains-hz "$mains")
      ;;
    arquivos)
      ls data/filtros 2>/dev/null | sed 's/^/    /'
      ask fhp "arquivo do passa-altas em data/filtros (Enter = nenhum)" ""
      ask fbs "arquivo do rejeita-faixa em data/filtros (Enter = nenhum)" ""
      SIGNAL_ARGS+=(--filters files)
      [ -z "$fhp" ] || SIGNAL_ARGS+=(--highpass-file "/data/filtros/$fhp")
      [ -z "$fbs" ] || SIGNAL_ARGS+=(--bandstop-file "/data/filtros/$fbs")
      ;;
  esac
  ask janela "janela em ms" "250"
  ask wavelet "wavelet-mãe (db7, sym4, coif2, haar...)" "db7"
  choose levels "níveis da decomposição:" "4" 1 2 3 4 5 6
  echo "  camadas: 'mestrado' repete o código original (a escolha de camadas não faz efeito);"
  echo "           'faixas' mantém só as camadas escolhidas (1 = a mais fina, fs/4 a fs/2)"
  choose mode "modo:" "mestrado" mestrado faixas
  [ "$janela" = 250 ] || SIGNAL_ARGS+=(--window-ms "$janela")
  if [ "$wavelet" != db7 ] || [ "$levels" != 4 ]; then
    SIGNAL_ARGS+=(--wavelet "$wavelet" --levels "$levels")
  fi
  if [ "$mode" = faixas ]; then
    ask layers "camadas a manter" "1 2"
    ask approx "manter também a aproximação? (s/N)" "n"
    # shellcheck disable=SC2206  # the layers are words on purpose
    SIGNAL_ARGS+=(--wavelet-mode bands --layers $layers)
    case "$approx" in s | S) SIGNAL_ARGS+=(--approx) ;; esac
  fi
}

# Share of the windows kept for the hold-out test, in percent. Fills TEST_ARGS
# only when it is not the thesis's 30 % (the course project used 20 %).
ask_test_size() {
  local pct
  ask pct "parte de teste (%)" "30"
  TEST_ARGS=()
  [ "$pct" = 30 ] || TEST_ARGS=(--test-size "$(awk -v p="$pct" 'BEGIN { print p / 100 }')")
}

opt_train() {
  local csv feature split seed
  pick_csv csv
  choose feature "feature:" "mav" mav rms
  choose split "divisão treino/teste:" "temporal" temporal legacy
  ask seed "semente" "42"
  ask_test_size
  ask_signal
  run docker compose "${BASE[@]}" run --rm train \
    ros2 run mestrado_emg train_legacy "/data/$csv" --out /models \
    --feature "$feature" --split "$split" --seed "$seed" "${TEST_ARGS[@]}" "${SIGNAL_ARGS[@]}"
  echo "  Modelos em models/, com o nome <classificador>_<arquivo>_${feature}_${split}[_<ajustes>]_latest.joblib"
}

opt_analyze() {
  local csv feature split seed folds pair
  pick_csv csv
  choose feature "feature:" "mav" mav rms
  choose split "divisão treino/teste:" "temporal" temporal legacy
  ask seed "semente" "42"
  ask_test_size
  ask folds "partições da validação cruzada" "5"
  ask pair "dois canais para o gráfico de dispersão" "1 2"
  ask_signal
  # shellcheck disable=SC2086  # the pair is two words on purpose
  run docker compose "${BASE[@]}" run --rm train \
    ros2 run mestrado_emg analyze_legacy "/data/$csv" --out /models/analise \
    --feature "$feature" --split "$split" --seed "$seed" "${TEST_ARGS[@]}" --cv "$folds" \
    --pair $pair "${SIGNAL_ARGS[@]}"
  echo "  Figuras e resumo em models/analise/ (a última linha da análise diz a pasta)"
  if is_wsl; then
    echo "  Para abrir no Windows: cd models/analise && explorer.exe ."
  fi
}

opt_arm() {
  local -a win
  read -r -a win <<<"$(window_files)"
  run docker compose "${BASE[@]}" "${win[@]}" run --rm shell \
    ros2 launch mestrado_bringup sim.launch.py
  echo "  Para mover o cotovelo, em outro terminal:"
  echo "    docker compose -f docker/compose.yaml run --rm shell ros2 topic pub --once -w 1 /arm/elbow/cmd_pos std_msgs/msg/Float64 \"{data: 1.57}\""
}

opt_system() {
  local source csv model gui f models extra=()
  local -a win
  choose source "fonte do sEMG:" "replay" replay myo
  if [ "$source" = replay ]; then
    pick_csv csv
  else
    csv=6_10_20220.csv
    extra=(-f docker/compose.myo.yaml)
  fi
  models=()
  for f in models/*_latest.joblib; do
    [ -e "$f" ] && models+=("$(basename "$f")")
  done
  if [ "${#models[@]}" -gt 0 ]; then
    choose model "classificador (em models/):" "knn_6-10-20220_mav_temporal_latest.joblib" "${models[@]}"
  else
    echo "  (nenhum modelo em models/: rode a opção 4 antes)"
    model=knn_6-10-20220_mav_temporal_latest.joblib
  fi
  read -r -a win <<<"$(window_files)"
  gui=false
  [ "${#win[@]}" -gt 0 ] && gui=true
  run env "GUI=$gui" "SOURCE=$source" "CSV=$csv" "MODEL=$model" \
    docker compose "${BASE[@]}" "${win[@]}" "${extra[@]}" up sim
}

camera_extra() {
  # A number is a camera device (Linux webcam); a path is a video file.
  if [[ "$1" =~ ^[0-9]+$ ]]; then
    echo "-f docker/compose.camera.yaml"
  fi
}

opt_mirror() {
  local camera flip arm fdef
  local -a win cam
  ask camera "câmera (número do dispositivo) ou vídeo em /data" "/data/test_2_05.avi"
  fdef=true
  [ "$camera" = /data/test_2_05.avi ] && fdef=false
  choose flip "espelhar a imagem (FLIP)? o vídeo do mestrado já está espelhado" "$fdef" true false
  choose arm "braço:" "right" right left
  read -r -a win <<<"$(window_files)"
  read -r -a cam <<<"$(camera_extra "$camera")"
  local show=true
  [ "${#win[@]}" -gt 0 ] || show=false
  run env "CAMERA=$camera" "FLIP=$flip" "ARM=$arm" "GUI=$show" "SHOW_WINDOW=$show" \
    docker compose "${BASE[@]}" "${win[@]}" "${cam[@]}" up espelho
}

opt_capture() {
  local emg camera flip arm n tol samples cont csv="6_10_20220.csv" fdef
  local -a win cam extra=()
  choose emg "fonte do sEMG:" "myo" myo replay
  if [ "$emg" = replay ]; then
    pick_csv csv
  else
    extra=(-f docker/compose.myo.yaml)
  fi
  ask camera "câmera (número do dispositivo) ou vídeo em /data" "/data/test_2_05.avi"
  fdef=true
  [ "$camera" = /data/test_2_05.avi ] && fdef=false
  choose flip "espelhar a imagem (FLIP)?" "$fdef" true false
  choose arm "braço:" "right" right left
  choose n "quantidade de categorias (170/90/60/45°):" "2" 2 3 4
  ask tol "tolerância em graus (a \"variância\" do mestrado)" "10"
  ask samples "amostras por categoria" "1000"
  choose cont "gravar também fora das categorias (regressão contínua)?" "false" false true
  read -r -a win <<<"$(window_files)"
  read -r -a cam <<<"$(camera_extra "$camera")"
  local show=true
  [ "${#win[@]}" -gt 0 ] || show=false
  run env "EMG=$emg" "CSV=$csv" "CAMERA=$camera" "FLIP=$flip" "ARM=$arm" "SHOW_WINDOW=$show" \
    "N_CATEGORIES=$n" "TOLERANCE=$tol" "SAMPLES=$samples" "CONTINUOUS=$cont" \
    docker compose "${BASE[@]}" "${win[@]}" "${cam[@]}" "${extra[@]}" run --rm captura
  echo "  O CSV gravado fica em data/captura_<data><n>.csv"
}

menu() {
  cat <<EOF

=== Projeto do mestrado: menu ===
  janela: ${JANELA:-nenhuma}
   1) Verificar o Docker
   2) Baixar os dados do mestrado
   3) Construir/atualizar a imagem
   4) Treinar os classificadores
   5) Analisar os resultados (figuras e validação cruzada)
   6) Ver o braço no Gazebo
   7) Sistema completo: sEMG -> classificador -> braço
   8) Modo espelho: o braço copia o vídeo/câmera
   9) Captura de dados (sEMG + ângulo do cotovelo)
  10) Encerrar tudo que estiver rodando
  11) Baixar os dados de gestos da disciplina (1 kHz, 8 participantes)
   0) Sair
EOF
}

while true; do
  menu
  choice=""
  read -r -p "Opção: " choice || exit 0
  case "$choice" in
    1) run scripts/check_docker.sh ;;
    2) run scripts/fetch_legacy_data.sh ;;
    3) run docker compose "${BASE[@]}" build ;;
    4) opt_train ;;
    5) opt_analyze ;;
    6) opt_arm ;;
    7) opt_system ;;
    8) opt_mirror ;;
    9) opt_capture ;;
    10) run scripts/stop.sh ;;
    11) run scripts/fetch_gesture_data.sh ;;
    0 | q | sair) exit 0 ;;
    "") ;;
    *) echo "  opção inválida: $choice" ;;
  esac
done
