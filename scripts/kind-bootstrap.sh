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
BROKER_CREDENTIAL_NAME="${SCION_KIND_CP_BROKER_CREDENTIAL_NAME:-in-cluster}"
BROKER_CREDENTIAL_SECRET="${SCION_KIND_CP_BROKER_CREDENTIAL_SECRET:-scion-broker-credentials}"
BROKER_BOOTSTRAP_HOME="${SCION_BROKER_BOOTSTRAP_HOME:-/tmp/scion-broker-bootstrap}"
GITHUB_TOKEN_SECRET="${SCION_GITHUB_TOKEN_SECRET:-scion-github-token}"
HUB_IN_CLUSTER="${SCION_OPS_KIND_IN_CLUSTER_HUB_URL:-http://127.0.0.1:8090}"
HUB_FOR_BROKER="${SCION_OPS_KIND_BROKER_HUB_URL:-http://scion-hub:8090}"
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

wait_for_public_hub() {
  local attempt
  log "wait for public Hub endpoint ${HUB_PUBLIC}"
  for attempt in $(seq 1 30); do
    if python3 - "$HUB_PUBLIC" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

endpoint = sys.argv[1].rstrip("/") + "/healthz"
with urllib.request.urlopen(endpoint, timeout=2) as response:
    if response.status != 200:
        raise SystemExit(1)
PY
    then
      return
    fi
    sleep 2
  done
  die "Hub at ${HUB_PUBLIC} did not become ready"
}

hub_pod() {
  local pod
  pod="$(kubectl_ctx -n "$NAMESPACE" get pod \
    -l app.kubernetes.io/name=scion-hub \
    -o jsonpath='{.items[0].metadata.name}')"
  [[ -n "$pod" ]] || die "scion-hub pod not found in ${CONTEXT}/${NAMESPACE}; run task up"
  printf '%s\n' "$pod"
}

broker_pod() {
  local pod
  pod="$(kubectl_ctx -n "$NAMESPACE" get pod \
    -l app.kubernetes.io/name=scion-broker \
    -o jsonpath='{.items[0].metadata.name}')"
  [[ -n "$pod" ]] || die "scion-broker pod not found in ${CONTEXT}/${NAMESPACE}; run task up"
  printf '%s\n' "$pod"
}

run_in_hub() {
  local pod="$1"
  local command="$2"
  kubectl_ctx -n "$NAMESPACE" exec "$pod" -c hub -- sh -lc "$command"
}

run_in_broker() {
  local pod="$1"
  local command="$2"
  kubectl_ctx -n "$NAMESPACE" exec "$pod" -c broker -- sh -lc "$command"
}

wait_for_control_plane_rollouts() {
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-hub --timeout=120s >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-broker --timeout=120s >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-ops-mcp --timeout=120s >/dev/null
}

restore_hub_dev_auth_secret() {
  local token="$1"
  local token_file
  [[ "$token" == scion_dev_* ]] || die "refusing to restore invalid Hub dev token"
  token_file="$(mktemp "${TMPDIR:-/tmp}/scion-hub-dev-token.XXXXXX")"
  chmod 0600 "$token_file"
  printf '%s\n' "$token" > "$token_file"
  if ! kubectl_ctx -n "$NAMESPACE" create secret generic scion-hub-dev-auth \
    --from-file=dev-token="$token_file" \
    --dry-run=client \
    -o yaml | kubectl_ctx -n "$NAMESPACE" apply -f - >/dev/null; then
    rm -f "$token_file"
    return 1
  fi
  rm -f "$token_file"
  log "restored Kubernetes Secret scion-hub-dev-auth"
}

restore_hub_web_session_secret() {
  local existing
  local session_secret
  local secret_file
  existing="$(kubectl_ctx -n "$NAMESPACE" get secret scion-hub-web-session -o jsonpath='{.data.session-secret}' 2>/dev/null || true)"
  if [[ -n "$existing" ]]; then
    log "preserved Kubernetes Secret scion-hub-web-session"
    return
  fi

  session_secret="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  secret_file="$(mktemp "${TMPDIR:-/tmp}/scion-hub-session.XXXXXX")"
  chmod 0600 "$secret_file"
  printf '%s\n' "$session_secret" > "$secret_file"
  if ! kubectl_ctx -n "$NAMESPACE" create secret generic scion-hub-web-session \
    --from-file=session-secret="$secret_file" \
    --dry-run=client \
    -o yaml | kubectl_ctx -n "$NAMESPACE" apply -f - >/dev/null; then
    rm -f "$secret_file"
    return 1
  fi
  rm -f "$secret_file"
  log "restored Kubernetes Secret scion-hub-web-session"
}

restart_control_plane_for_restored_auth_state() {
  kubectl_ctx -n "$NAMESPACE" rollout restart deploy/scion-hub >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-hub --timeout=120s >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout restart deploy/scion-broker >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-broker --timeout=120s >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout restart deploy/scion-ops-mcp >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-ops-mcp --timeout=120s >/dev/null
  log "restarted Hub, broker, and MCP after auth/session Secret restore"
}

restore_broker_credentials_secret() {
  local pod="$1"
  local credential_file
  credential_file="$(mktemp "${TMPDIR:-/tmp}/scion-broker-credentials.XXXXXX.json")"
  chmod 0600 "$credential_file"

  if ! kubectl_ctx -n "$NAMESPACE" exec "$pod" -c broker -- \
    cat "${BROKER_BOOTSTRAP_HOME}/.scion/hub-credentials/${BROKER_CREDENTIAL_NAME}.json" >"$credential_file"; then
    rm -f "$credential_file"
    return 1
  fi

  python3 - "$credential_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
missing = [key for key in ("brokerId", "secretKey", "hubEndpoint") if not data.get(key)]
if missing:
    raise SystemExit(f"broker credential file is missing: {', '.join(missing)}")
PY

  if ! kubectl_ctx -n "$NAMESPACE" create secret generic "$BROKER_CREDENTIAL_SECRET" \
    --from-file="${BROKER_CREDENTIAL_NAME}.json=${credential_file}" \
    --dry-run=client \
    -o yaml | kubectl_ctx -n "$NAMESPACE" apply -f - >/dev/null; then
    rm -f "$credential_file"
    return 1
  fi
  rm -f "$credential_file"
  kubectl_ctx -n "$NAMESPACE" label secret "$BROKER_CREDENTIAL_SECRET" \
    app.kubernetes.io/name=scion-broker \
    app.kubernetes.io/component=broker \
    app.kubernetes.io/part-of=scion-control-plane \
    --overwrite >/dev/null
  log "restored Kubernetes Secret ${BROKER_CREDENTIAL_SECRET}"
}

broker_credentials_secret_exists() {
  kubectl_ctx -n "$NAMESPACE" get secret "$BROKER_CREDENTIAL_SECRET" >/dev/null 2>&1
}

broker_control_channel_ready() {
  local pod
  pod="$(broker_pod)"
  kubectl_ctx -n "$NAMESPACE" logs "$pod" -c broker 2>/dev/null |
    grep -q "Connected to Hub control channel"
}

hub_control_channel_ready() {
  local pod
  pod="$(hub_pod)"
  kubectl_ctx -n "$NAMESPACE" logs "$pod" -c hub 2>/dev/null |
    grep -q "Broker control channel connected"
}

broker_connection_ready() {
  local info
  broker_credentials_secret_exists || return 1
  broker_control_channel_ready || return 1
  hub_control_channel_ready || return 1

  if ! info="$(run_scion hub brokers info "$BROKER" --json --non-interactive 2>/dev/null)"; then
    return 1
  fi

  BROKER_INFO="$info" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["BROKER_INFO"])
if isinstance(data, dict) and isinstance(data.get("broker"), dict):
    data = data["broker"]

status = str(data.get("status") or data.get("brokerStatus") or "").lower()
connection = str(data.get("connectionState") or data.get("connection_state") or "").lower()

if status == "online" and connection in ("", "connected"):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_broker_connection() {
  local attempt
  log "wait for dedicated broker ${BROKER} to connect to Hub"
  for attempt in $(seq 1 30); do
    if broker_connection_ready; then
      return
    fi
    sleep 2
  done
  die "broker ${BROKER} did not become connected"
}

ensure_broker_registration() {
  local pod
  local hub_url
  local token
  local credential_name
  local bootstrap_home

  if broker_connection_ready; then
    log "dedicated broker ${BROKER} is already connected"
    return
  fi

  pod="$(broker_pod)"
  hub_url="$(sh_quote "$HUB_FOR_BROKER")"
  token="$(sh_quote "$SCION_DEV_TOKEN")"
  credential_name="$(sh_quote "$BROKER_CREDENTIAL_NAME")"
  bootstrap_home="$(sh_quote "$BROKER_BOOTSTRAP_HOME")"

  log "register dedicated broker ${BROKER} with Hub"
  run_in_broker "$pod" "HOME=${bootstrap_home} SCION_HUB_ENDPOINT=${hub_url} HUB_ENDPOINT=${hub_url} SCION_DEV_TOKEN=${token} scion --global broker register --hub ${hub_url} --name ${credential_name} --force --auto-provide --non-interactive --yes >/tmp/scion-broker-register.log 2>&1 || { cat /tmp/scion-broker-register.log >&2; exit 1; }"
  restore_broker_credentials_secret "$pod"

  kubectl_ctx -n "$NAMESPACE" rollout restart deploy/scion-broker >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-broker --timeout=120s >/dev/null
  wait_for_broker_connection
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

restore_github_token_kubernetes_secret() {
  local token="$1"
  [[ -n "$token" ]] || die "GITHUB_TOKEN is empty"
  kubectl_ctx -n "$NAMESPACE" create secret generic "$GITHUB_TOKEN_SECRET" \
    --from-literal=GITHUB_TOKEN="$token" \
    --dry-run=client \
    -o yaml |
    kubectl_ctx -n "$NAMESPACE" apply -f - >/dev/null
  log "restored Kubernetes Secret ${GITHUB_TOKEN_SECRET} for MCP git branch preparation"
}

restart_mcp_for_github_token() {
  if [[ -n "${SCION_OPS_MCP_PORT:-}" && -n "${KUBERNETES_SERVICE_HOST:-}" ]]; then
    log "skip MCP restart from inside MCP pod; restart MCP from the host to reload ${GITHUB_TOKEN_SECRET}"
    return 0
  fi
  kubectl_ctx -n "$NAMESPACE" rollout restart deploy/scion-ops-mcp >/dev/null
  kubectl_ctx -n "$NAMESPACE" rollout status deploy/scion-ops-mcp --timeout=120s >/dev/null
  log "restarted MCP to load ${GITHUB_TOKEN_SECRET}"
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

set_claude_config_secret() {
  local source="$1"
  local target="$2"
  local prepared
  [[ -f "$source" ]] || die "required credential file not found: $source"
  prepared="$(mktemp "${TMPDIR:-/tmp}/scion-claude-config.XXXXXX.json")"

  python3 - "$source" "$prepared" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
dest = Path(sys.argv[2])
config = json.loads(source.read_text())
projects = config.setdefault("projects", {})
workspace = projects.setdefault("/workspace", {})
workspace.setdefault("allowedTools", [])
workspace.setdefault("mcpContextUris", [])
workspace.setdefault("mcpServers", {})
workspace.setdefault("enabledMcpjsonServers", [])
workspace.setdefault("disabledMcpjsonServers", [])
workspace["hasTrustDialogAccepted"] = True
workspace.setdefault("projectOnboardingSeenCount", 1)
workspace.setdefault("hasClaudeMdExternalIncludesApproved", False)
workspace.setdefault("hasClaudeMdExternalIncludesWarningShown", False)
workspace.setdefault("exampleFiles", [])
config["hasCompletedOnboarding"] = True
config["bypassPermissionsModeAccepted"] = True
config["skipDangerousModePermissionPrompt"] = True
config["mcpServers"] = {}
config["enabledMcpjsonServers"] = []
config["disabledMcpjsonServers"] = []
config["mcpContextUris"] = []
dest.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
PY

  if set_file_secret CLAUDE_CONFIG "$prepared" "$target"; then
    rm -f "$prepared"
  else
    rm -f "$prepared"
    return 1
  fi
  log "prepared Claude config for Scion agent startup"
}

claude_auth_seconds_until_expiry() {
  local source="$1"
  python3 - "$source" <<'PY'
import json
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
expires_at = data.get("claudeAiOauth", {}).get("expiresAt")
if not isinstance(expires_at, (int, float)):
    raise SystemExit("missing claudeAiOauth.expiresAt")
print(int((expires_at / 1000) - time.time()))
PY
}

ensure_claude_auth_fresh() {
  local source="$1"
  local min_seconds="${SCION_OPS_CLAUDE_AUTH_MIN_SECONDS:-3600}"
  local refresh_timeout="${SCION_OPS_CLAUDE_REFRESH_TIMEOUT:-180}"
  local seconds
  local err_file

  [[ -f "$source" ]] || die "required credential file not found: $source"
  seconds="$(claude_auth_seconds_until_expiry "$source")" || \
    die "Claude auth file is not a recognized subscription credential: $source"

  if (( seconds > min_seconds )); then
    log "Claude auth access token is valid for ${seconds}s"
    return 0
  fi

  if truthy "${SCION_OPS_SKIP_CLAUDE_AUTH_REFRESH:-}"; then
    die "Claude auth access token expires too soon (${seconds}s); run claude /login, then task bootstrap"
  fi

  command -v claude >/dev/null 2>&1 || \
    die "Claude CLI is required to refresh subscription auth; install/login with claude, then task bootstrap"

  log "refresh Claude subscription auth before uploading Hub secret"
  err_file="$(mktemp "${TMPDIR:-/tmp}/scion-claude-refresh.XXXXXX.err")"
  if ! timeout "$refresh_timeout" claude --no-chrome --print 'Return exactly: ok' >/dev/null 2>"$err_file"; then
    local detail
    detail="$(sed -n '1,3p' "$err_file" | tr '\n' ' ')"
    rm -f "$err_file"
    die "Claude auth refresh failed: ${detail:-unknown error}. Run claude /login, then task bootstrap"
  fi
  rm -f "$err_file"

  seconds="$(claude_auth_seconds_until_expiry "$source")" || \
    die "Claude auth file is not readable after refresh: $source"
  if (( seconds <= min_seconds )); then
    die "Claude auth refresh did not produce a long-lived access token (${seconds}s remaining); run claude /login, then task bootstrap"
  fi
  log "Claude auth refresh complete; access token is valid for ${seconds}s"
}

prepare_hub_harness_configs() {
  local pod="$1"
  run_in_hub "$pod" "python3 - <<'PY'
import json
from pathlib import Path

settings = Path('/home/scion/.scion/harness-configs/claude/home/.claude/settings.json')
settings.parent.mkdir(parents=True, exist_ok=True)
try:
    data = json.loads(settings.read_text()) if settings.exists() else {}
except json.JSONDecodeError:
    data = {}
data['skipDangerousModePermissionPrompt'] = True
settings.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
PY"
  log "prepared Claude harness settings for non-interactive startup"
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
  local configs=(claude codex-exec gemini)
  local existing=()
  local repo_existing=()

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

  if [[ -d "${REPO_ROOT}/deploy/kind/harness-configs" ]]; then
    for config in "${configs[@]}"; do
      [[ -d "${REPO_ROOT}/deploy/kind/harness-configs/${config}" ]] && repo_existing+=("$config")
    done
  fi

  if [[ "${#repo_existing[@]}" -gt 0 ]]; then
    log "copy repo-managed harness configs into Hub pod: ${repo_existing[*]}"
    tar -C "${REPO_ROOT}/deploy/kind/harness-configs" -cf - "${repo_existing[@]}" |
      kubectl_ctx -n "$NAMESPACE" exec -i "$pod" -c hub -- \
        tar -C /home/scion/.scion/harness-configs -xf -
  fi

  prepare_hub_harness_configs "$pod"

  log "sync harness configs from inside Hub pod"
  local hub_url
  local token
  hub_url="$(sh_quote "$HUB_IN_CLUSTER")"
  token="$(sh_quote "$SCION_DEV_TOKEN")"
  for config in "${configs[@]}"; do
    run_in_hub "$pod" "SCION_DEV_TOKEN=${token} SCION_HUB_ENDPOINT=${hub_url} scion harness-config sync ${config} --hub ${hub_url} --non-interactive --yes"
  done

  log "copy prepared harness configs into broker pod"
  local broker
  broker="$(broker_pod)"
  run_in_broker "$broker" "mkdir -p /home/scion/.scion/harness-configs"
  kubectl_ctx -n "$NAMESPACE" exec "$pod" -c hub -- \
    tar -C /home/scion/.scion/harness-configs -cf - "${configs[@]}" |
    kubectl_ctx -n "$NAMESPACE" exec -i "$broker" -c broker -- \
      tar -C /home/scion/.scion/harness-configs -xf -
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
  local token
  hub_url="$(sh_quote "$HUB_IN_CLUSTER")"
  token="$(sh_quote "$SCION_DEV_TOKEN")"
  run_in_hub "$pod" "SCION_DEV_TOKEN=${token} SCION_HUB_ENDPOINT=${hub_url} scion --global templates sync --all --hub ${hub_url} --non-interactive --yes"

  log "copy synced template storage into broker pod"
  local broker
  broker="$(broker_pod)"
  run_in_broker "$broker" "mkdir -p /home/scion/.scion/storage/templates"
  kubectl_ctx -n "$NAMESPACE" exec "$pod" -c hub -- \
    tar -C /home/scion/.scion/storage/templates -cf - . |
    kubectl_ctx -n "$NAMESPACE" exec -i "$broker" -c broker -- \
      tar -C /home/scion/.scion/storage/templates -xf -
}

main() {
  require task
  require kubectl
  require python3
  require tar
  require "$SCION_BIN"
  [[ -d "$PROJECT_ROOT/.git" ]] || git -C "$PROJECT_ROOT" rev-parse --show-toplevel >/dev/null 2>&1 || die "target project is not a git repo: $PROJECT_ROOT"

  log "read kind Hub auth"
  load_hub_auth
  restore_hub_dev_auth_secret "$SCION_DEV_TOKEN"
  restore_hub_web_session_secret

  log "wait for control-plane rollouts"
  wait_for_control_plane_rollouts
  restart_control_plane_for_restored_auth_state
  wait_for_public_hub
  ensure_broker_registration

  log "link target grove and provide broker ${BROKER}"
  log "target project: ${PROJECT_ROOT}"
  run_scion hub link --non-interactive --yes >/dev/null
  run_scion broker provide --broker "$BROKER" --make-default --non-interactive --yes >/dev/null

  local token pod
  token="$(github_token)"
  [[ -n "$token" ]] || die "GITHUB_TOKEN, GH_TOKEN, or a usable gh auth token is required"
  set_env_secret GITHUB_TOKEN "$token"
  restore_github_token_kubernetes_secret "$token"
  restart_mcp_for_github_token
  unset token

  local claude_auth_file claude_config_file
  claude_auth_file="${CLAUDE_AUTH_FILE:-${HOME}/.claude/.credentials.json}"
  claude_config_file="${CLAUDE_CONFIG_FILE:-${HOME}/.claude.json}"
  ensure_claude_auth_fresh "$claude_auth_file"
  set_file_secret CLAUDE_AUTH "$claude_auth_file" "~/.claude/.credentials.json"
  set_claude_config_secret "$claude_config_file" "~/.claude.json"
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
