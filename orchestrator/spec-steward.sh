#!/usr/bin/env bash
# Start a Scion-native OpenSpec steward session.
set -euo pipefail

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

GOAL="${*:-}"
[[ -n "$GOAL" ]] || die "Usage: $(basename "$0") \"<spec goal>\""

SCION_BIN="${SCION_BIN:-scion}"
command -v "$SCION_BIN" >/dev/null || die "scion not on PATH"

SCION_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCION_OPS_ROOT/orchestrator/lib/github-branches.sh"

PROJECT_ROOT_INPUT="${SCION_OPS_PROJECT_ROOT:-$SCION_OPS_ROOT}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel 2>/dev/null)" || die "target project is not a git repo: $PROJECT_ROOT"

agent_path_for() {
  local path="$1"
  local host_root="${SCION_OPS_HOST_WORKSPACE_ROOT:-/home/david/workspace}"
  local container_root="${SCION_OPS_CONTAINER_WORKSPACE_ROOT:-/workspace}"
  case "$path" in
    "$container_root"|"$container_root"/*)
      printf '%s\n' "$path"
      ;;
    "$host_root")
      printf '%s\n' "$container_root"
      ;;
    "$host_root"/*)
      printf '%s/%s\n' "$container_root" "${path#"$host_root"/}"
      ;;
    *)
      printf '%s\n' "$path"
      ;;
  esac
}

AGENT_PROJECT_ROOT="${SCION_OPS_AGENT_PROJECT_ROOT:-.}"
AGENT_SCION_OPS_ROOT="${SCION_OPS_AGENT_SCION_OPS_ROOT:-$(agent_path_for "$SCION_OPS_ROOT")}"

SESSION_ID="${SCION_OPS_SESSION_ID:-${ROUND_ID:-$(date -u +%Y%m%dt%H%M%Sz)-$(printf '%04x' "$RANDOM")}}"
SESSION_ID="$(printf '%s' "$SESSION_ID" | tr '[:upper:]' '[:lower:]')"
ROUND_ID="$SESSION_ID"
CHANGE="${SCION_OPS_SPEC_CHANGE:-}"
BASE_BRANCH_EXPLICIT=0
if [[ -n "${BASE_BRANCH:-}" ]]; then
  BASE_BRANCH_EXPLICIT=1
else
  BASE_BRANCH=""
fi
BROKER="${SCION_KIND_CP_BROKER:-kind-control-plane}"
SCION_PROFILE="${SCION_K8S_PROFILE:-kind}"
COLLECTION_RECIPIENT="${SCION_OPS_COLLECTION_RECIPIENT:-user:dev@localhost}"

default_base_branch() {
  local remote_head current candidate
  remote_head="$(git -C "$PROJECT_ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
  if [[ -n "$remote_head" ]]; then
    printf '%s\n' "$remote_head"
    return
  fi
  for candidate in main master; do
    if git -C "$PROJECT_ROOT" rev-parse --verify --quiet "origin/${candidate}^{commit}" >/dev/null ||
      git -C "$PROJECT_ROOT" rev-parse --verify --quiet "${candidate}^{commit}" >/dev/null; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  current="$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || true)"
  printf '%s\n' "${current:-main}"
}

BASE_BRANCH="${BASE_BRANCH:-$(default_base_branch)}"
if [[ "$BASE_BRANCH_EXPLICIT" == "0" && "$BASE_BRANCH" == round-* && "${SCION_OPS_ALLOW_IMPLICIT_ROUND_BASE:-0}" != "1" ]]; then
  die "implicit base branch resolved to a round branch ($BASE_BRANCH); set BASE_BRANCH explicitly, usually BASE_BRANCH=main"
fi
if ! git -C "$PROJECT_ROOT" rev-parse --verify --quiet "${BASE_BRANCH}^{commit}" >/dev/null &&
  ! git -C "$PROJECT_ROOT" rev-parse --verify --quiet "origin/${BASE_BRANCH}^{commit}" >/dev/null; then
  die "base branch does not resolve locally or on origin: $BASE_BRANCH"
fi

STEWARD_NAME="round-${SESSION_ID}-spec-steward"
STEWARD_BRANCH="$STEWARD_NAME"
CLARIFIER_NAME="round-${SESSION_ID}-spec-clarifier"
EXPLORER_NAME="round-${SESSION_ID}-spec-explorer"
AUTHOR_NAME="round-${SESSION_ID}-spec-author"
OPS_REVIEW_NAME="round-${SESSION_ID}-spec-ops-review"
FINAL_BRANCH="round-${SESSION_ID}-spec-integration"
SESSION_STATE_ROOT=".scion-ops/sessions/${SESSION_ID}"

precreate_session_branches() {
  local suffix
  for suffix in spec-steward spec-clarifier spec-explorer spec-author spec-ops-review spec-integration; do
    scion_ops_ensure_remote_branch "$PROJECT_ROOT" "round-${SESSION_ID}-${suffix}" "$BASE_BRANCH"
  done
}

if [[ "${SCION_OPS_ROUND_PREFLIGHT:-1}" != "0" && "${SCION_OPS_DRY_RUN:-0}" != "1" ]]; then
  bash "$SCION_OPS_ROOT/scripts/kind-round-preflight.sh"
fi

TASK_PROMPT=$(cat <<EOF
session_id: $SESSION_ID
round_id: $ROUND_ID
session_type: spec
base_branch: $BASE_BRANCH
base_branch_explicit: $BASE_BRANCH_EXPLICIT
change: $CHANGE
scion_profile: $SCION_PROFILE
project_root: $AGENT_PROJECT_ROOT
scion_ops_root: $AGENT_SCION_OPS_ROOT
collection_recipient: $COLLECTION_RECIPIENT
session_state_root: $SESSION_STATE_ROOT
final_branch: $FINAL_BRANCH

original_goal:
$GOAL

required_first_actions:
1. Before detailed repository inspection or any OpenSpec authoring, create
   $SESSION_STATE_ROOT/state.json on the steward branch with status "running",
   phase "clarifying", branches for steward/clarifier/explorer/author/review/
   integration, validation.status "pending", blockers [], and next_actions.
   Commit and push that state to $STEWARD_BRANCH.
2. Start both required discovery agents with these exact commands from the
   current Scion checkout:

   scion --profile "$SCION_PROFILE" start "$CLARIFIER_NAME" --type spec-goal-clarifier --branch "$CLARIFIER_NAME" --broker "$BROKER" --harness-config codex-exec --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
change: $CHANGE
base_branch: $BASE_BRANCH
collection_recipient: $COLLECTION_RECIPIENT
expected_branch: $CLARIFIER_NAME
artifact_boundary: no file changes; clarify scope only
expected_summary: goal clarification, assumptions, unresolved questions, and recommended change name

Clarify the requested OpenSpec change. Do not edit files. Send a concise completion summary to $COLLECTION_RECIPIENT."

   scion --profile "$SCION_PROFILE" start "$EXPLORER_NAME" --type spec-repo-explorer --branch "$EXPLORER_NAME" --broker "$BROKER" --harness-config codex-exec --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
change: $CHANGE
base_branch: $BASE_BRANCH
collection_recipient: $COLLECTION_RECIPIENT
expected_branch: $EXPLORER_NAME
artifact_boundary: no file changes; inspect repo only
expected_summary: existing web app, Kubernetes deploy/kind/kustomize state, expected files to spec, and risks

Explore the repository for this OpenSpec change. Do not edit files. Send a concise completion summary to $COLLECTION_RECIPIENT."

3. If either command fails, update state as blocked and call
   sciontool status task_completed with the blocker. Do not author the spec
   yourself.
4. Only after both discovery summaries are available, start the author with:

   scion --profile "$SCION_PROFILE" start "$AUTHOR_NAME" --type spec-author --branch "$AUTHOR_NAME" --broker "$BROKER" --harness-config codex-exec --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
change: $CHANGE
base_branch: $BASE_BRANCH
collection_recipient: $COLLECTION_RECIPIENT
expected_branch: $AUTHOR_NAME
artifact_boundary: openspec/changes/$CHANGE only
expected_summary: files changed, requirements added/modified, validation notes

Write only OpenSpec artifacts for $CHANGE. Use the clarifier and explorer summaries. Send a concise completion summary to $COLLECTION_RECIPIENT."

5. Review only the integration branch with:

   scion --profile "$SCION_PROFILE" start "$OPS_REVIEW_NAME" --type spec-ops-reviewer --branch "$OPS_REVIEW_NAME" --broker "$BROKER" --harness-config codex-exec --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
change: $CHANGE
base_branch: $BASE_BRANCH
collection_recipient: $COLLECTION_RECIPIENT
review_branch: $FINAL_BRANCH
expected_summary: verdict accept/reject/blocked, blocking issues, recommendations, and test gaps

Review the OpenSpec artifacts on $FINAL_BRANCH. Do not review the author branch. Send a concise verdict summary to $COLLECTION_RECIPIENT."

Start the OpenSpec steward playbook. Coordinate specialist agents, keep durable
state under $SESSION_STATE_ROOT, validate the resulting OpenSpec artifacts, and
finish ready only when $FINAL_BRANCH exists and is pushed with a valid
openspec/changes/<change>/ artifact set. Do not implement product code.
EOF
)

printf 'Starting OpenSpec steward: %s\n' "$STEWARD_NAME"
printf 'session_id: %s\n' "$SESSION_ID"
printf 'round_id: %s\n' "$ROUND_ID"
printf 'Base branch: %s\n' "$BASE_BRANCH"
printf 'Change: %s\n' "${CHANGE:-<derive in session>}"
printf 'Final branch: %s\n' "$FINAL_BRANCH"
printf 'Scion profile: %s\n' "$SCION_PROFILE"
printf 'Broker: %s\n' "$BROKER"
printf 'Collection recipient: %s\n' "$COLLECTION_RECIPIENT"
printf 'Grove root: %s\n' "$PROJECT_ROOT"
printf 'Agent project root: %s\n' "$AGENT_PROJECT_ROOT"
printf 'Agent scion-ops root: %s\n' "$AGENT_SCION_OPS_ROOT"

if [[ "${SCION_OPS_DRY_RUN:-0}" == "1" ]]; then
  cat <<EOF

Dry run command:
  $SCION_BIN --profile "$SCION_PROFILE" --grove "$PROJECT_ROOT" start "$STEWARD_NAME" --type spec-steward --branch "$STEWARD_BRANCH" --broker "$BROKER" --harness-auth auth-file --no-upload --non-interactive --yes --notify "<prompt>"

Rendered prompt:
$TASK_PROMPT
EOF
  exit 0
fi

if [[ "${SCION_OPS_PRECREATE_SESSION_BRANCHES:-1}" != "0" ]]; then
  scion_ops_load_github_token_for_branch_precreate
  precreate_session_branches
fi

"$SCION_BIN" --profile "$SCION_PROFILE" --grove "$PROJECT_ROOT" start "$STEWARD_NAME" \
  --type spec-steward \
  --branch "$STEWARD_BRANCH" \
  --broker "$BROKER" \
  --harness-auth auth-file \
  --no-upload \
  --non-interactive \
  --yes \
  --notify \
  "$TASK_PROMPT"

printf '\nWatch progress:\n'
printf '  scion look %s\n' "$STEWARD_NAME"
printf '  scion messages --agent %s\n' "$STEWARD_NAME"
printf '\nValidate session:\n'
printf '  task steward:validate -- --project-root %q --session-id %q --kind spec --change %q --branch %q --require-ready\n' "$PROJECT_ROOT" "$SESSION_ID" "$CHANGE" "$FINAL_BRANCH"
