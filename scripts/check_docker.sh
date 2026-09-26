#!/usr/bin/env bash
# Quick check, before the guide's commands, that Docker works from the Ubuntu
# terminal of WSL2 (Windows 11 + Docker Desktop). Read-only: it only inspects
# (command -v, docker info/version/ps, tasklist.exe, wsl.exe --list) and never
# starts, stops or changes anything.
#
# Usage (from the repository root, in the WSL Ubuntu terminal):
#   scripts/check_docker.sh
#
# Checks, in order:
#   a) running inside WSL (otherwise: this script is for the WSL Ubuntu terminal);
#   b) `docker` is the WSL-integrated CLI (/usr/bin/docker), not missing and not
#      the Windows binary reached through WSL interop (/mnt/c/...);
#   c) the Docker engine answers (`docker info`);
#   d) no container of this project is already running (two simulators on the
#      host network publish on the same topics and mix their readings).
#
# Exit codes: 0 all good (prints client/server versions); 1 docker CLI not
# integrated; 2 not WSL; 3 engine not answering; 4 project container running.
#
# Why (docs/COMO_RODAR.md, "Se algo der errado"): Docker Desktop prints
# "The command 'docker' could not be found in this WSL 2 distro. We recommend
# to activate the WSL integration in Docker Desktop settings." but the toggle
# is usually NOT the fix. The two real causes seen on Windows 11:
#   A) Docker Desktop is not running (e.g. after a reboot with "Start Docker
#      Desktop when you sign in" off);
#   B) the default WSL distro is not this one (usually "docker-desktop"), so
#      the integration with the *default* distro never reaches Ubuntu.
# When tasklist.exe / wsl.exe answer, the script says which cause is likely and
# which is ruled out; when they do not ("?"), it prints both.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"

ok() { echo "  ok    $*"; }
bad() { echo "  FALHA $*"; }

is_wsl() {
  [ "${CHECK_DOCKER_FORCE_WSL:-}" = 1 ] && return 0  # used by tests/test_check_docker.py
  [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null
}

# Best-effort Windows-side diagnostics through WSL interop; "?" if unavailable.
docker_desktop_running() {
  command -v tasklist.exe >/dev/null 2>&1 || { echo "?"; return; }
  if tasklist.exe /FI "IMAGENAME eq Docker Desktop.exe" /NH 2>/dev/null | grep -qi "Docker Desktop.exe"; then
    echo "sim"
  else
    echo "não"
  fi
}

default_wsl_distro() {
  command -v wsl.exe >/dev/null 2>&1 || { echo "?"; return; }
  # wsl.exe prints UTF-16; drop the NULs. The default distro has a leading "*".
  local line
  line="$(wsl.exe --list --verbose 2>/dev/null | tr -d '\000\r' | grep '^[[:space:]]*\*' | head -n1)"
  [ -n "$line" ] && echo "$line" | tr -s ' ' | cut -d' ' -f2 || echo "?"
}

cause_a() {
  cat <<EOF
  Causa A (a mais comum): o Docker Desktop não está rodando.
    Conserto: abra o Docker Desktop no Windows e espere o motor subir (~10 s),
    depois rode este script de novo. Se o "Start Docker Desktop when you sign in"
    estiver desligado, isso se repete a cada reinicialização do Windows.
EOF
}

cause_b() {
  cat <<EOF
  Causa B: a distro padrão do WSL não é esta (${here:-Ubuntu}); costuma ser a
    "docker-desktop" (a VM do próprio Docker), quando o Docker Desktop foi
    instalado antes do Ubuntu. A integração com a distro padrão nunca chega aqui.
    Confira no PowerShell:
      wsl --list --verbose        (o asterisco marca a distro padrão)
    Conserto, no PowerShell:
      wsl --set-default ${here:-Ubuntu}
    e reinicie o Docker Desktop.
EOF
}

# The Windows-side diagnosis decides which cause to show: "provável" (shown in
# full), "descartada" (one line) or unknown "?" (shown in full, as before).
print_causes() {
  local running default here a b
  running="$(docker_desktop_running)"
  default="$(default_wsl_distro)"
  here="${WSL_DISTRO_NAME:-}"

  case "$running" in
    não) a=provável ;;
    sim) a=descartada ;;
    *) a="?" ;;
  esac
  if [ "$default" = "?" ]; then
    b="?"
  elif [ -n "$here" ] && [ "$default" != "$here" ]; then
    b=provável
  elif [ -z "$here" ] && [[ "$default" == docker-desktop* ]]; then
    b=provável
  else
    b=descartada
  fi

  echo
  echo "  Diagnóstico (lado Windows): Docker Desktop rodando = ${running}; distro padrão do WSL = ${default}"

  if [ "$a" = descartada ] && [ "$b" = descartada ]; then
    cat <<EOF

  Nem a causa A nem a B: o Docker Desktop está rodando e a distro padrão já é
  esta. Se o Docker Desktop acabou de abrir, espere ~10 s e rode de novo. Se
  continuar, aqui sim confira no Docker Desktop: Settings > Resources >
  WSL integration, ligue a chave da distro ${here:-Ubuntu} e clique em
  "Apply & restart".
EOF
    return
  fi

  echo "  Não mexa primeiro no \"WSL integration\" das configurações: costuma não ser isso."
  local cause state
  for cause in A B; do
    if [ "$cause" = A ]; then state="$a"; else state="$b"; fi
    echo
    case "$state" in
      provável)
        echo "  >> Causa provável: $cause"
        if [ "$cause" = A ]; then cause_a; else cause_b; fi
        ;;
      descartada)
        if [ "$cause" = A ]; then
          echo "  Causa A descartada: o Docker Desktop está rodando."
        else
          echo "  Causa B descartada: a distro padrão do WSL já é ${default}."
        fi
        ;;
      *)
        if [ "$cause" = A ]; then cause_a; else cause_b; fi
        ;;
    esac
  done
}

echo "Verificando o Docker para este projeto..."

# a) WSL
if ! is_wsl; then
  echo "  Este script é para o terminal do Ubuntu no WSL2 (Windows)."
  echo "  No Linux, confira com: docker version  (deve mostrar Client e Server)."
  exit 2
fi
ok "rodando dentro do WSL${WSL_DISTRO_NAME:+ ($WSL_DISTRO_NAME)}"

# b) docker CLI integrated into this distro
docker_path="$(command -v docker || true)"
if [ -z "$docker_path" ]; then
  bad "comando 'docker' não encontrado nesta distro"
  print_causes
  exit 1
fi
# Windows drives are mounted under /mnt/ (prefix overridable only for tests).
case "$docker_path" in
  "${CHECK_DOCKER_WINDOWS_PREFIX:-/mnt/}"*)
    bad "'docker' aponta para o binário do Windows ($docker_path),"
    echo "        alcançado por interop do WSL: isso NÃO é a integração funcionando."
    print_causes
    exit 1
    ;;
esac
ok "cliente docker integrado ($docker_path)"

# c) engine answers
if ! timeout 20 docker info >/dev/null 2>&1; then
  bad "o motor do Docker não respondeu (docker info)"
  echo
  echo "  O Docker Desktop está fechado ou ainda subindo. Abra o Docker Desktop no"
  echo "  Windows, espere o motor ficar pronto (~10 s) e rode este script de novo."
  exit 3
fi
ok "motor do Docker respondendo"

# d) project containers already running (up and run containers alike)
running_ids="$(docker compose -f "$COMPOSE" ps -a -q --status running 2>/dev/null)"
if [ -n "$running_ids" ]; then
  bad "já há container(s) deste projeto rodando:"
  for id in $running_ids; do
    docker ps --filter "id=$id" --format '{{.Names}}  ({{.Status}})' 2>/dev/null | sed 's/^/        /'
  done
  echo
  echo "  Dois simuladores ao mesmo tempo publicam nos mesmos tópicos e as leituras"
  echo "  se misturam, sem erro nenhum. Pare tudo antes: ./scripts/stop.sh"
  exit 4
fi
ok "nenhum container do projeto rodando"

# e) versions
echo
docker version --format '  cliente {{.Client.Version}}, servidor {{.Server.Version}}' 2>/dev/null ||
  echo "  (não foi possível ler as versões)"
echo "Tudo certo: pode seguir o guia (docs/COMO_RODAR.md)."
exit 0
