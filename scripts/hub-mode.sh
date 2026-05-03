#!/usr/bin/env bash
# Manage the local Scion workstation server used as Hub + Broker + Web.
set -euo pipefail

SCION_BIN="${SCION_BIN:-scion}"
HUB_BIND_HOST="${HUB_BIND_HOST:-127.0.0.1}"
HUB_WEB_PORT="${HUB_WEB_PORT:-8090}"
HUB_ENDPOINT="${HUB_ENDPOINT:-${SCION_HUB_ENDPOINT:-http://127.0.0.1:${HUB_WEB_PORT}}}"
SCION_SERVER_LOG="${SCION_SERVER_LOG:-${HOME}/.scion/server.log}"
READY_TIMEOUT_SECONDS="${SCION_HUB_READY_TIMEOUT_SECONDS:-30}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  up           Start/reuse the local Scion workstation server.
  down         Stop the local Scion server daemon.
  status       Show server, Hub, and current agent status.
  auth-export  Print the SCION_DEV_TOKEN export line from the server log.
  link         Configure endpoint, enable Hub mode, and link this grove.
  disable      Disable Hub integration for this grove.
  logs         Tail the Scion server log.

Environment:
  SCION_BIN                         Scion CLI binary (default: scion)
  HUB_BIND_HOST                     Server bind host (default: 127.0.0.1)
  HUB_WEB_PORT                      Web/combined Hub port (default: 8090)
  HUB_ENDPOINT                      Client endpoint (default: http://127.0.0.1:8090)
  SCION_HUB_READY_TIMEOUT_SECONDS   Startup readiness timeout (default: 30)
EOF
}

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

log() {
  printf '\033[36m==> %s\033[0m\n' "$*"
}

require() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required on PATH"
}

server_status() {
  "$SCION_BIN" server status 2>&1
}

server_ready() {
  local status
  status="$(server_status || true)"
  grep -Eq 'Hub API:[[:space:]]+running' <<<"$status" \
    && grep -Eq 'Runtime Broker:[[:space:]]+running' <<<"$status" \
    && grep -Eq 'Web Frontend:[[:space:]]+running' <<<"$status"
}

wait_until_ready() {
  local deadline
  deadline=$((SECONDS + READY_TIMEOUT_SECONDS))

  while (( SECONDS <= deadline )); do
    if server_ready; then
      return 0
    fi
    sleep 1
  done

  server_status >&2 || true
  if [[ -f "$SCION_SERVER_LOG" ]]; then
    printf '\nRecent server log:\n' >&2
    tail -n 40 "$SCION_SERVER_LOG" >&2
  fi
  die "Scion server did not become ready within ${READY_TIMEOUT_SECONDS}s"
}

cmd_up() {
  require "$SCION_BIN"

  if server_ready; then
    log "reuse running Scion workstation server"
  else
    log "start Scion workstation server on ${HUB_BIND_HOST}:${HUB_WEB_PORT}"
    "$SCION_BIN" server start --host "$HUB_BIND_HOST" --web-port "$HUB_WEB_PORT"
    wait_until_ready
  fi

  cat <<EOF

Scion Hub mode ready
  Web UI:      ${HUB_ENDPOINT}
  Bind host:   ${HUB_BIND_HOST}
  Web port:    ${HUB_WEB_PORT}
  Server log:  ${SCION_SERVER_LOG}

Next:
  eval "\$(task hub:auth-export)"
  task hub:link
  task hub:status
EOF
}

cmd_down() {
  require "$SCION_BIN"
  "$SCION_BIN" server stop || true
}

cmd_auth_export() {
  [[ -f "$SCION_SERVER_LOG" ]] || die "server log not found: $SCION_SERVER_LOG; run task hub:up first"
  local token_line
  token_line="$(grep -oE 'export SCION_DEV_TOKEN=scion_dev_[[:alnum:]]+' "$SCION_SERVER_LOG" | tail -1 || true)"
  [[ -n "$token_line" ]] || die "SCION_DEV_TOKEN not found in $SCION_SERVER_LOG; restart the server or inspect the log"
  printf '%s\n' "$token_line"
}

cmd_link() {
  require "$SCION_BIN"
  [[ -n "${SCION_DEV_TOKEN:-}" ]] || die "SCION_DEV_TOKEN not set. Run: eval \"\$(task hub:auth-export)\""

  log "configure Hub endpoint ${HUB_ENDPOINT}"
  "$SCION_BIN" config set hub.endpoint "$HUB_ENDPOINT"
  "$SCION_BIN" hub enable --hub "$HUB_ENDPOINT"
  "$SCION_BIN" hub link --hub "$HUB_ENDPOINT" --non-interactive --yes
}

cmd_status() {
  require "$SCION_BIN"
  "$SCION_BIN" server status
  printf '\n'
  "$SCION_BIN" hub status --hub "$HUB_ENDPOINT" --non-interactive
  printf '\n'
  "$SCION_BIN" list --hub "$HUB_ENDPOINT" --non-interactive
}

cmd_disable() {
  require "$SCION_BIN"
  "$SCION_BIN" hub disable
  cat <<EOF

Hub integration disabled for this grove.
For a one-off local-only command, prefer the global flag:
  scion start --no-hub scratch "echo local"
EOF
}

cmd_logs() {
  [[ -f "$SCION_SERVER_LOG" ]] || die "server log not found: $SCION_SERVER_LOG"
  tail -F "$SCION_SERVER_LOG"
}

case "${1:-}" in
  up)
    cmd_up
    ;;
  down)
    cmd_down
    ;;
  status)
    cmd_status
    ;;
  auth-export)
    cmd_auth_export
    ;;
  link)
    cmd_link
    ;;
  disable)
    cmd_disable
    ;;
  logs)
    cmd_logs
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    usage >&2
    die "unknown command: $1"
    ;;
esac
