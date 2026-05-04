#!/usr/bin/env bash
# Detached round launcher with watchdog.
#
# Spawns the consensus-runner in the background, logs to LOG_FILE, and a
# separate watchdog kills the runner (and all its children) after MAX_MINUTES.
# Returns immediately with the round id and PID file path.
#
#   bash orchestrator/run-round.sh "<task prompt>"
#   MAX_MINUTES=20 bash orchestrator/run-round.sh "<task prompt>"
set -eo pipefail

PROMPT="${*:-}"
[[ -n "$PROMPT" ]] || { echo "Usage: $(basename "$0") \"<task prompt>\"" >&2; exit 1; }

MAX_MINUTES="${MAX_MINUTES:-30}"
MAX_REVIEW_ROUNDS="${MAX_REVIEW_ROUNDS:-${MAX_ROUNDS:-3}}"
FINAL_REVIEWER="${FINAL_REVIEWER:-gemini}"
BASE_BRANCH="${BASE_BRANCH:-}"
LOG_FILE="${LOG_FILE:-/tmp/scion-round.log}"
PID_FILE="${PID_FILE:-/tmp/scion-round.pid}"
WATCHDOG_PID_FILE="${WATCHDOG_PID_FILE:-/tmp/scion-round-watchdog.pid}"

ROUND_ID="${ROUND_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$(printf '%04x' "$RANDOM")}"
RUNNER_NAME="round-${ROUND_ID,,}-consensus"   # scion lowercases agent slugs

SCION_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT_INPUT="${SCION_OPS_PROJECT_ROOT:-$SCION_OPS_ROOT}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
if git -C "$PROJECT_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel)"
fi
export SCION_OPS_PROJECT_ROOT="$PROJECT_ROOT"

if [[ -z "${SCION_HUB_ENDPOINT:-}" ]]; then
  SCION_HUB_ENDPOINT="${SCION_OPS_KIND_HUB_URL:-http://${SCION_OPS_KIND_LISTEN_ADDRESS:-192.168.122.103}:${SCION_OPS_KIND_HUB_PORT:-18090}}"
  export SCION_HUB_ENDPOINT
fi
export HUB_ENDPOINT="${HUB_ENDPOINT:-$SCION_HUB_ENDPOINT}"

if [[ -z "${SCION_DEV_TOKEN:-}" && -z "${SCION_DEV_TOKEN_FILE:-}" ]] && command -v task >/dev/null 2>&1; then
  if hub_auth="$(task kind:hub:auth-export 2>/dev/null)"; then
    eval "$hub_auth"
  fi
fi

if [[ "${SCION_OPS_ROUND_PREFLIGHT:-1}" != "0" ]]; then
  bash "$SCION_OPS_ROOT/scripts/kind-round-preflight.sh"
fi

# 1. Truncate log, launch round.sh detached.
: > "$LOG_FILE"
round_env=(
  "ROUND_ID=$ROUND_ID"
  "MAX_REVIEW_ROUNDS=$MAX_REVIEW_ROUNDS"
  "FINAL_REVIEWER=$FINAL_REVIEWER"
  "SCION_OPS_PROJECT_ROOT=$PROJECT_ROOT"
)
if [[ -n "$BASE_BRANCH" ]]; then
  round_env+=("BASE_BRANCH=$BASE_BRANCH")
fi
env "${round_env[@]}" setsid nohup bash "$SCION_OPS_ROOT/orchestrator/round.sh" "$PROMPT" \
  >> "$LOG_FILE" 2>&1 &
ROUND_PID=$!
disown "$ROUND_PID" 2>/dev/null || true
echo "$ROUND_PID" > "$PID_FILE"

# 2. Watchdog: after MAX_MINUTES, kill everything related to this round.
(
  sleep $((MAX_MINUTES * 60))
  if "$SCION_OPS_ROOT/orchestrator/abort.sh" "$ROUND_ID" >/dev/null 2>&1; then
    printf '\n[watchdog %s] aborted round %s after %s minutes\n' \
      "$(date +%H:%M:%S)" "$ROUND_ID" "$MAX_MINUTES" >> "$LOG_FILE"
  fi
  kill "$ROUND_PID" 2>/dev/null || true
) >> "$LOG_FILE" 2>&1 &
WATCHDOG_PID=$!
disown "$WATCHDOG_PID" 2>/dev/null || true
echo "$WATCHDOG_PID" > "$WATCHDOG_PID_FILE"

cat <<EOF
round_id    : $ROUND_ID
runner      : $RUNNER_NAME
log         : $LOG_FILE
final review: $FINAL_REVIEWER
round pid   : $ROUND_PID
watchdog    : $WATCHDOG_PID  (kill after ${MAX_MINUTES} min)

watch:
  task watch                     # status board, refreshes every 5s
  task watch -- $ROUND_ID        # filter to this round
  scion look $RUNNER_NAME

abort early:
  task abort -- $ROUND_ID
EOF
