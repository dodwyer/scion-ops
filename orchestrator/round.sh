#!/usr/bin/env bash
# Start a Scion-native consensus round.
#
# The round logic lives in the consensus-runner template. This launcher keeps
# host-side code limited to naming the round and starting the coordinator.
set -euo pipefail

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

PROMPT="${*:-}"
[[ -n "$PROMPT" ]] || die "Usage: $(basename "$0") \"<task prompt>\""

SCION_BIN="${SCION_BIN:-scion}"
command -v "$SCION_BIN" >/dev/null || die "scion not on PATH"

ROUND_ID="${ROUND_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$(printf '%04x' "$RANDOM")}"
MAX_REVIEW_ROUNDS="${MAX_REVIEW_ROUNDS:-${MAX_ROUNDS:-3}}"
FINAL_REVIEWER="${FINAL_REVIEWER:-gemini}"
BASE_BRANCH="${BASE_BRANCH:-$(git branch --show-current 2>/dev/null || true)}"
if [[ -z "$BASE_BRANCH" ]]; then
  BASE_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
fi
BASE_BRANCH="${BASE_BRANCH:-main}"
RUNNER_NAME="round-${ROUND_ID}-consensus"
RUNNER_BRANCH="$RUNNER_NAME"

TASK_PROMPT=$(cat <<EOF
round_id: $ROUND_ID
max_review_rounds: $MAX_REVIEW_ROUNDS
base_branch: $BASE_BRANCH
final_reviewer: $FINAL_REVIEWER

original_task:
$PROMPT

Start the consensus protocol described in your system prompt. Keep the user
updated through Scion status and messages. Do not implement the task yourself.
EOF
)

printf 'Starting consensus runner: %s\n' "$RUNNER_NAME"
printf 'Round id: %s\n' "$ROUND_ID"
printf 'Base branch: %s\n' "$BASE_BRANCH"
printf 'Final reviewer: %s\n' "$FINAL_REVIEWER"

"$SCION_BIN" start "$RUNNER_NAME" \
  --type consensus-runner \
  --branch "$RUNNER_BRANCH" \
  --harness-auth auth-file \
  --upload-template \
  --non-interactive \
  --yes \
  --notify \
  "$TASK_PROMPT"

printf '\nWatch progress:\n'
printf '  scion look %s\n' "$RUNNER_NAME"
printf '  scion messages --agent %s\n' "$RUNNER_NAME"
