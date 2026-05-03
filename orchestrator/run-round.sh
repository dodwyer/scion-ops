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

# 1. Truncate log, launch round.sh detached.
: > "$LOG_FILE"
round_env=(
  "ROUND_ID=$ROUND_ID"
  "MAX_REVIEW_ROUNDS=$MAX_REVIEW_ROUNDS"
  "FINAL_REVIEWER=$FINAL_REVIEWER"
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
