#!/usr/bin/env bash
# Wire the local Scion Runtime Broker to the kind-backed Kubernetes profile.
set -euo pipefail

SCION_BIN="${SCION_BIN:-scion}"
PROFILE_NAME="${SCION_K8S_PROFILE:-kind}"
RUNTIME_NAME="${SCION_K8S_RUNTIME:-kubernetes}"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-scion-ops}"
NAMESPACE="${SCION_K8S_NAMESPACE:-scion-agents}"
HUB_ENDPOINT="${HUB_ENDPOINT:-${SCION_HUB_ENDPOINT:-http://127.0.0.1:8090}}"
HUB_BIND_HOST="${HUB_BIND_HOST:-127.0.0.1}"
HUB_WEB_PORT="${HUB_WEB_PORT:-8090}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS_FILE="${SCION_SETTINGS_FILE:-${HOME}/.scion/settings.yaml}"
SMOKE_AGENT="${SCION_KIND_SMOKE_AGENT:-kind-smoke-$(date +%Y%m%d%H%M%S)}"
SMOKE_TEMPLATE="${SCION_KIND_SMOKE_TEMPLATE:-reviewer-claude}"
SMOKE_PROMPT="${SCION_KIND_SMOKE_PROMPT:-Report the current working directory and then stop.}"
SMOKE_WAIT_SECONDS="${SCION_KIND_SMOKE_WAIT_SECONDS:-60}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  configure   Configure Scion profile "${PROFILE_NAME}" for the kind Kubernetes runtime.
  provide     Refresh broker registration, provide this grove, and make broker default.
  status      Show profile, broker, and Hub broker profile status.
  smoke       Dispatch a minimal Hub agent with --profile ${PROFILE_NAME} and verify a kind pod appears.

Environment:
  SCION_BIN                    Scion CLI binary (default: scion)
  SCION_K8S_PROFILE            Scion profile name (default: kind)
  SCION_K8S_RUNTIME            Scion runtime name (default: kubernetes)
  KIND_CLUSTER_NAME            kind cluster name (default: scion-ops)
  SCION_K8S_NAMESPACE          Agent namespace (default: scion-agents)
  HUB_ENDPOINT                 Hub endpoint (default: http://127.0.0.1:8090)
  HUB_BIND_HOST                Server bind host when restart is needed (default: 127.0.0.1)
  HUB_WEB_PORT                 Server web port when restart is needed (default: 8090)
  SCION_KIND_SMOKE_TEMPLATE    Smoke template (default: reviewer-claude)
  SCION_KIND_SMOKE_AGENT       Smoke agent name (default: timestamped)
  SCION_KIND_SMOKE_WAIT_SECONDS  Pod observation timeout (default: 60)
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

broker_id() {
  "$SCION_BIN" broker status --json 2>/dev/null | jq -r '.brokerId // empty'
}

broker_name() {
  "$SCION_BIN" broker status --json 2>/dev/null | jq -r '.brokerName // empty'
}

cmd_configure() {
  require "$SCION_BIN"
  require yq

  log "configure Scion profile ${PROFILE_NAME} for kind cluster ${CLUSTER_NAME}"
  "$SCRIPT_DIR/kind-scion-runtime.sh" configure-scion

  log "verify Kubernetes runtime profile ${PROFILE_NAME}"
  "$SCION_BIN" doctor --profile "$PROFILE_NAME"
}

cmd_provide() {
  require "$SCION_BIN"
  require jq

  cmd_configure

  log "refresh broker registration so Hub sees profile ${PROFILE_NAME}"
  "$SCION_BIN" broker register --force --hub "$HUB_ENDPOINT" --non-interactive --yes

  if [[ "${SCION_BROKER_RESTART_AFTER_REGISTER:-1}" == "1" ]]; then
    log "restart workstation server so embedded broker reloads refreshed credentials"
    "$SCION_BIN" server stop || true
    SCION_BIN="$SCION_BIN" \
      HUB_BIND_HOST="$HUB_BIND_HOST" \
      HUB_WEB_PORT="$HUB_WEB_PORT" \
      HUB_ENDPOINT="$HUB_ENDPOINT" \
      "$SCRIPT_DIR/hub-mode.sh" up
  fi

  log "provide this grove from the local broker and make it default"
  "$SCION_BIN" broker provide --make-default --non-interactive --yes
}

cmd_status() {
  require "$SCION_BIN"
  require jq
  require yq

  printf 'settings:  %s\n' "$SETTINGS_FILE"
  printf 'profile:   %s\n' "$PROFILE_NAME"
  printf 'runtime:   %s\n\n' "$RUNTIME_NAME"

  if [[ -f "$SETTINGS_FILE" ]]; then
    SCION_K8S_PROFILE="$PROFILE_NAME" SCION_K8S_RUNTIME="$RUNTIME_NAME" yq eval '
      {
        "runtime": .runtimes[strenv(SCION_K8S_RUNTIME)],
        "profile": .profiles[strenv(SCION_K8S_PROFILE)],
        "image_registry": .image_registry
      }
    ' "$SETTINGS_FILE"
  else
    die "settings file not found: $SETTINGS_FILE"
  fi

  printf '\n'
  "$SCION_BIN" broker status --json | jq '{registered, brokerId, brokerName, brokerStatus, hubConnected, groves}'

  local id
  id="$(broker_id)"
  if [[ -n "$id" ]]; then
    printf '\n'
    "$SCION_BIN" hub brokers info "$id" --hub "$HUB_ENDPOINT" --non-interactive --json | jq '{id, name, status, profiles}'
  fi
}

cmd_smoke() {
  require "$SCION_BIN"
  require jq
  require kubectl

  local id name context
  id="$(broker_id)"
  name="$(broker_name)"
  [[ -n "$id" ]] || die "broker is not registered; run: task broker:kind-provide"
  [[ -n "$name" ]] || name="$id"
  context="kind-${CLUSTER_NAME}"

  log "dispatch ${SMOKE_AGENT} through Hub to broker ${name} with profile ${PROFILE_NAME}"
  "$SCION_BIN" --profile "$PROFILE_NAME" start "$SMOKE_AGENT" \
    --broker "$name" \
    --type "$SMOKE_TEMPLATE" \
    --no-auth \
    --hub "$HUB_ENDPOINT" \
    --non-interactive \
    --yes \
    "$SMOKE_PROMPT"

  log "wait for kind pod scion.name=${SMOKE_AGENT}"
  local deadline
  deadline=$((SECONDS + SMOKE_WAIT_SECONDS))
  while (( SECONDS <= deadline )); do
    if kubectl --context "$context" get pods -n "$NAMESPACE" -l "scion.name=${SMOKE_AGENT}" --no-headers 2>/dev/null | grep -q .; then
      kubectl --context "$context" get pods -n "$NAMESPACE" -l "scion.name=${SMOKE_AGENT}" -o wide
      if [[ "${SCION_KIND_SMOKE_KEEP:-0}" != "1" ]]; then
        log "delete smoke agent ${SMOKE_AGENT}"
        "$SCION_BIN" delete "$SMOKE_AGENT" --hub "$HUB_ENDPOINT" --non-interactive --yes || true
      fi
      return 0
    fi
    sleep 1
  done

  "$SCION_BIN" list --hub "$HUB_ENDPOINT" --non-interactive || true
  die "no kind pod appeared for ${SMOKE_AGENT} within ${SMOKE_WAIT_SECONDS}s"
}

case "${1:-}" in
  configure)
    cmd_configure
    ;;
  provide)
    cmd_provide
    ;;
  status)
    cmd_status
    ;;
  smoke)
    cmd_smoke
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    usage >&2
    die "unknown command: $1"
    ;;
esac
