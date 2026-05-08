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

SCION_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCION_OPS_ROOT/orchestrator/lib/github-branches.sh"
PROJECT_ROOT_INPUT="${SCION_OPS_PROJECT_ROOT:-$SCION_OPS_ROOT}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel 2>/dev/null)" || die "target project is not a git repo: $PROJECT_ROOT"
AGENT_PROJECT_ROOT="${SCION_OPS_AGENT_PROJECT_ROOT:-/workspace}"

ROUND_ID="${ROUND_ID:-$(date -u +%Y%m%dt%H%M%Sz)-$(printf '%04x' "$RANDOM")}"
ROUND_ID="$(printf '%s' "$ROUND_ID" | tr '[:upper:]' '[:lower:]')"
MAX_REVIEW_ROUNDS="${MAX_REVIEW_ROUNDS:-${MAX_ROUNDS:-3}}"
MAX_MINUTES="${MAX_MINUTES:-90}"
AGENT_MAX_DURATION="${SCION_OPS_AGENT_MAX_DURATION:-${MAX_MINUTES}m}"
FINAL_REVIEWER="${FINAL_REVIEWER:-codex}"
BASE_BRANCH="${BASE_BRANCH:-$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || true)}"
BROKER="${SCION_KIND_CP_BROKER:-kind-control-plane}"
SCION_PROFILE="${SCION_K8S_PROFILE:-kind}"
if [[ -z "$BASE_BRANCH" ]]; then
  BASE_BRANCH="$(git -C "$PROJECT_ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
fi
BASE_BRANCH="${BASE_BRANCH:-main}"
RUNNER_NAME="round-${ROUND_ID}-consensus"
RUNNER_BRANCH="$RUNNER_NAME"

precreate_round_branches() {
  local suffix
  for suffix in consensus impl-claude impl-codex; do
    scion_ops_ensure_remote_branch "$PROJECT_ROOT" "round-${ROUND_ID}-${suffix}" "$BASE_BRANCH"
  done
}

TASK_PROMPT=$(cat <<EOF
round_id: $ROUND_ID
max_review_rounds: $MAX_REVIEW_ROUNDS
agent_max_duration: $AGENT_MAX_DURATION
base_branch: $BASE_BRANCH
final_reviewer: $FINAL_REVIEWER
scion_profile: $SCION_PROFILE
project_root: $AGENT_PROJECT_ROOT

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
printf 'Scion profile: %s\n' "$SCION_PROFILE"
printf 'Broker: %s\n' "$BROKER"
printf 'Grove root: %s\n' "$PROJECT_ROOT"
printf 'Agent project root: %s\n' "$AGENT_PROJECT_ROOT"

if [[ "${SCION_OPS_PRECREATE_ROUND_BRANCHES:-1}" != "0" ]]; then
  scion_ops_load_github_token_for_branch_precreate
  precreate_round_branches
fi

"$SCION_BIN" --profile "$SCION_PROFILE" --grove "$PROJECT_ROOT" start "$RUNNER_NAME" \
  --type consensus-runner \
  --branch "$RUNNER_BRANCH" \
  --broker "$BROKER" \
  --harness-auth auth-file \
  --no-upload \
  --non-interactive \
  --yes \
  --notify \
  "$TASK_PROMPT"

printf '\nWatch progress:\n'
printf '  scion look %s\n' "$RUNNER_NAME"
printf '  scion messages --agent %s\n' "$RUNNER_NAME"
