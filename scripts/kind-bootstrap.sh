#!/usr/bin/env bash
# Bootstrap kind Hub state needed for subscription-backed consensus rounds.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT_INPUT="${1:-${SCION_OPS_PROJECT_ROOT:-$REPO_ROOT}}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
if git -C "$PROJECT_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel)"
fi
CLUSTER_NAME="${KIND_CLUSTER_NAME:-scion-ops}"
CONTEXT="${KIND_CONTEXT:-kind-${CLUSTER_NAME}}"
NAMESPACE="${SCION_K8S_NAMESPACE:-scion-agents}"
BROKER="${SCION_KIND_CP_BROKER:-kind-control-plane}"
HUB_IN_CLUSTER="${SCION_OPS_KIND_IN_CLUSTER_HUB_URL:-http://127.0.0.1:8090}"
HUB_PUBLIC="${SCION_HUB_ENDPOINT:-${HUB_ENDPOINT:-${SCION_OPS_KIND_HUB_URL:-http://${SCION_OPS_KIND_LISTEN_ADDRESS:-192.168.122.103}:${SCION_OPS_KIND_HUB_PORT:-18090}}}}"
SCION_BIN="${SCION_BIN:-scion}"
HARNESS_CONFIG_ROOT="${SCION_OPS_HARNESS_CONFIG_ROOT:-${HOME}/.scion/harness-configs}"

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

kubectl_ctx() {
  kubectl --context "$CONTEXT" "$@"
}

sh_quote() {
  printf "'"
  printf '%s' "$1" | sed "s/'/'\\\\''/g"
  printf "'"
}

load_hub_auth() {
  local exports
  exports="$(task kind:hub:auth-export)"
  eval "$exports"
  HUB_PUBLIC="${SCION_HUB_ENDPOINT:-$HUB_PUBLIC}"
  export SCION_HUB_ENDPOINT="$HUB_PUBLIC"
  export HUB_ENDPOINT="$HUB_PUBLIC"
  [[ "${SCION_DEV_TOKEN:-}" == scion_dev_* ]] || die "could not read kind Hub dev token"
}

run_scion() {
  (cd "$PROJECT_ROOT" && SCION_HUB_ENDPOINT="$HUB_PUBLIC" SCION_DEV_TOKEN="$SCION_DEV_TOKEN" "$SCION_BIN" "$@")
}

hub_pod() {
  local pod
  pod="$(kubectl_ctx -n "$NAMESPACE" get pod \
    -l app.kubernetes.io/name=scion-hub \
    -o jsonpath='{.items[0].metadata.name}')"
  [[ -n "$pod" ]] || die "scion-hub pod not found in ${CONTEXT}/${NAMESPACE}; run task up"
  printf '%s\n' "$pod"
}

run_in_hub() {
  local pod="$1"
  local command="$2"
  kubectl_ctx -n "$NAMESPACE" exec "$pod" -c hub -- sh -lc "$command"
}

github_token() {
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    printf '%s' "$GITHUB_TOKEN"
    return
  fi
  if [[ -n "${GH_TOKEN:-}" ]]; then
    printf '%s' "$GH_TOKEN"
    return
  fi
  if command -v gh >/dev/null 2>&1; then
    gh auth token 2>/dev/null | tr -d '\r\n'
  fi
}

set_env_secret() {
  local key="$1"
  local value="$2"
  [[ -n "$value" ]] || die "${key} is empty"
  run_scion hub secret set --scope hub "$key" "$value" --non-interactive --yes >/dev/null
  log "set Hub environment secret ${key}"
}

set_file_secret() {
  local key="$1"
  local source="$2"
  local target="$3"
  [[ -f "$source" ]] || die "required credential file not found: $source"
  run_scion hub secret set --scope hub \
    --type file \
    --target "$target" \
    "$key" "@$source" \
    --non-interactive \
    --yes \
    >/dev/null
  log "set Hub file secret ${key} -> ${target}"
}

clear_secret_if_present() {
  local key="$1"
  if run_scion hub secret get --scope hub "$key" --json --non-interactive >/dev/null 2>&1; then
    run_scion hub secret clear --scope hub "$key" --non-interactive --yes >/dev/null
    log "cleared Hub secret ${key}"
  fi
}

truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

sync_harness_configs() {
  local pod="$1"
  local configs=(claude codex gemini)
  local existing=()

  if [[ -d "$HARNESS_CONFIG_ROOT" ]]; then
    for config in "${configs[@]}"; do
      [[ -d "${HARNESS_CONFIG_ROOT}/${config}" ]] && existing+=("$config")
    done
  fi

  if [[ "${#existing[@]}" -gt 0 ]]; then
    log "copy host harness configs into Hub pod: ${existing[*]}"
    tar -C "$HARNESS_CONFIG_ROOT" -cf - "${existing[@]}" |
      kubectl_ctx -n "$NAMESPACE" exec -i "$pod" -c hub -- \
        tar -C /home/scion/.scion/harness-configs -xf -
  else
    log "no host harness configs found; using Hub image defaults"
  fi

  log "sync harness configs from inside Hub pod"
  local hub_url
  hub_url="$(sh_quote "$HUB_IN_CLUSTER")"
  for config in "${configs[@]}"; do
    run_in_hub "$pod" "SCION_DEV_TOKEN=\$(cat /home/scion/.scion/dev-token) SCION_HUB_ENDPOINT=${hub_url} scion harness-config sync ${config} --hub ${hub_url} --non-interactive --yes"
  done
}

sync_templates() {
  local pod="$1"

  [[ -d "${REPO_ROOT}/.scion/templates" ]] || die "template directory not found: ${REPO_ROOT}/.scion/templates"

  log "copy checked-in templates into Hub pod global template directory"
  run_in_hub "$pod" "mkdir -p /home/scion/.scion/templates"
  tar -C "${REPO_ROOT}/.scion/templates" -cf - . |
    kubectl_ctx -n "$NAMESPACE" exec -i "$pod" -c hub -- \
      tar -C /home/scion/.scion/templates -xf -

  log "sync templates from inside Hub pod"
  local hub_url
  hub_url="$(sh_quote "$HUB_IN_CLUSTER")"
  run_in_hub "$pod" "SCION_DEV_TOKEN=\$(cat /home/scion/.scion/dev-token) SCION_HUB_ENDPOINT=${hub_url} scion --global templates sync --all --hub ${hub_url} --non-interactive --yes"
}

main() {
  require task
  require kubectl
  require tar
  require "$SCION_BIN"
  [[ -d "$PROJECT_ROOT/.git" ]] || git -C "$PROJECT_ROOT" rev-parse --show-toplevel >/dev/null 2>&1 || die "target project is not a git repo: $PROJECT_ROOT"

  log "read kind Hub auth"
  load_hub_auth

  log "wait for Hub and MCP rollouts"
  task kind:control-plane:status >/dev/null

  log "link target grove and provide broker ${BROKER}"
  log "target project: ${PROJECT_ROOT}"
  run_scion hub link --non-interactive --yes >/dev/null
  run_scion broker provide --broker "$BROKER" --make-default --non-interactive --yes >/dev/null

  local token pod
  token="$(github_token)"
  [[ -n "$token" ]] || die "GITHUB_TOKEN, GH_TOKEN, or a usable gh auth token is required"
  set_env_secret GITHUB_TOKEN "$token"
  unset token

  set_file_secret CLAUDE_AUTH "${CLAUDE_AUTH_FILE:-${HOME}/.claude/.credentials.json}" "~/.claude/.credentials.json"
  set_file_secret CLAUDE_CONFIG "${CLAUDE_CONFIG_FILE:-${HOME}/.claude.json}" "~/.claude.json"
  set_file_secret CODEX_AUTH "${CODEX_AUTH_FILE:-${HOME}/.codex/auth.json}" "~/.codex/auth.json"
  set_file_secret GEMINI_OAUTH_CREDS "${GEMINI_OAUTH_CREDS_FILE:-${HOME}/.gemini/oauth_creds.json}" "~/.gemini/oauth_creds.json"
  if truthy "${SCION_OPS_BOOTSTRAP_VERTEX_ADC:-}"; then
    [[ -n "${GOOGLE_CLOUD_PROJECT:-}" ]] || die "GOOGLE_CLOUD_PROJECT is required when SCION_OPS_BOOTSTRAP_VERTEX_ADC is enabled"
    [[ -n "${GOOGLE_CLOUD_REGION:-${CLOUD_ML_REGION:-${GOOGLE_CLOUD_LOCATION:-}}}" ]] || die "GOOGLE_CLOUD_REGION, CLOUD_ML_REGION, or GOOGLE_CLOUD_LOCATION is required when SCION_OPS_BOOTSTRAP_VERTEX_ADC is enabled"
    set_file_secret gcloud-adc "${GOOGLE_APPLICATION_CREDENTIALS:-${HOME}/.config/gcloud/application_default_credentials.json}" "~/.config/gcloud/application_default_credentials.json"
    set_env_secret GOOGLE_CLOUD_PROJECT "$GOOGLE_CLOUD_PROJECT"
    set_env_secret GOOGLE_CLOUD_REGION "${GOOGLE_CLOUD_REGION:-${CLOUD_ML_REGION:-${GOOGLE_CLOUD_LOCATION:-}}}"
  else
    clear_secret_if_present gcloud-adc
    clear_secret_if_present GOOGLE_CLOUD_PROJECT
    clear_secret_if_present GOOGLE_CLOUD_REGION
    clear_secret_if_present CLOUD_ML_REGION
    clear_secret_if_present GOOGLE_CLOUD_LOCATION
    log "skip Vertex ADC restore; set SCION_OPS_BOOTSTRAP_VERTEX_ADC=1 to enable"
  fi

  pod="$(hub_pod)"
  sync_harness_configs "$pod"
  sync_templates "$pod"

  log "preflight round state"
  SCION_HUB_ENDPOINT="$HUB_PUBLIC" SCION_DEV_TOKEN="$SCION_DEV_TOKEN" SCION_OPS_PROJECT_ROOT="$PROJECT_ROOT" \
    "${REPO_ROOT}/scripts/kind-round-preflight.sh"

  log "bootstrap complete"
}

main "$@"
