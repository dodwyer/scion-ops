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
AGENT_SCION_OPS_ROOT="${SCION_OPS_AGENT_SCION_OPS_ROOT:-$AGENT_PROJECT_ROOT}"

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
SPEC_STEWARD_TEMPLATE="${SCION_OPS_SPEC_STEWARD_TEMPLATE:-spec-steward}"
SPEC_STEWARD_HARNESS="${SCION_OPS_SPEC_STEWARD_HARNESS:-codex-exec}"
SPEC_CLARIFIER_TEMPLATE="${SCION_OPS_SPEC_CLARIFIER_TEMPLATE:-spec-goal-clarifier-claude}"
SPEC_CLARIFIER_HARNESS="${SCION_OPS_SPEC_CLARIFIER_HARNESS:-claude}"
SPEC_EXPLORER_TEMPLATE="${SCION_OPS_SPEC_EXPLORER_TEMPLATE:-spec-repo-explorer}"
SPEC_EXPLORER_HARNESS="${SCION_OPS_SPEC_EXPLORER_HARNESS:-codex-exec}"
SPEC_AUTHOR_TEMPLATE="${SCION_OPS_SPEC_AUTHOR_TEMPLATE:-spec-author}"
SPEC_AUTHOR_HARNESS="${SCION_OPS_SPEC_AUTHOR_HARNESS:-codex-exec}"
SPEC_OPS_REVIEW_TEMPLATE="${SCION_OPS_SPEC_OPS_REVIEW_TEMPLATE:-spec-ops-reviewer-claude}"
SPEC_OPS_REVIEW_HARNESS="${SCION_OPS_SPEC_OPS_REVIEW_HARNESS:-claude}"
SPEC_OPS_REVIEW_WAIT_SECONDS="${SCION_OPS_SPEC_OPS_REVIEW_WAIT_SECONDS:-420}"
SPEC_OPS_REVIEW_POLL_SECONDS="${SCION_OPS_SPEC_OPS_REVIEW_POLL_SECONDS:-15}"
SPEC_REQUIRE_MULTI_HARNESS="${SCION_OPS_SPEC_REQUIRE_MULTI_HARNESS:-1}"
SPEC_REQUIRE_MULTI_HARNESS_ENABLED=1
case "${SPEC_REQUIRE_MULTI_HARNESS,,}" in
  0|false|no)
    SPEC_REQUIRE_MULTI_HARNESS_ENABLED=0
    ;;
esac
SPEC_REQUIRE_MULTI_HARNESS_FLAG=""
if [[ "$SPEC_REQUIRE_MULTI_HARNESS_ENABLED" == "1" ]]; then
  SPEC_REQUIRE_MULTI_HARNESS_FLAG=" --require-multi-harness"
fi

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
specialist_templates:
  clarifier: $SPEC_CLARIFIER_TEMPLATE
  explorer: $SPEC_EXPLORER_TEMPLATE
  author: $SPEC_AUTHOR_TEMPLATE
  ops_review: $SPEC_OPS_REVIEW_TEMPLATE
specialist_harnesses:
  clarifier: $SPEC_CLARIFIER_HARNESS
  explorer: $SPEC_EXPLORER_HARNESS
  author: $SPEC_AUTHOR_HARNESS
  ops_review: $SPEC_OPS_REVIEW_HARNESS
required_multi_harness: $SPEC_REQUIRE_MULTI_HARNESS_ENABLED

original_goal:
$GOAL

branch_names:
  steward: $STEWARD_BRANCH
  clarifier: $CLARIFIER_NAME
  explorer: $EXPLORER_NAME
  author: $AUTHOR_NAME
  review: $OPS_REVIEW_NAME
  integration: $FINAL_BRANCH

required_commands:
  init_state: python3 "$AGENT_SCION_OPS_ROOT/scripts/steward-state.py" spec-init --project-root "$AGENT_PROJECT_ROOT" --session-id "$SESSION_ID" --change "$CHANGE" --base-branch "$BASE_BRANCH"
  spec_validate: python3 "$AGENT_SCION_OPS_ROOT/scripts/validate-openspec-change.py" --project-root "$AGENT_PROJECT_ROOT" --change "$CHANGE"
  wait_review: python3 "$AGENT_SCION_OPS_ROOT/scripts/wait-for-review-artifact.py" --project-root "$AGENT_PROJECT_ROOT" --branch "$OPS_REVIEW_NAME" --artifact "$SESSION_STATE_ROOT/findings/ops-review.json" --agent "$OPS_REVIEW_NAME" --scion-profile "$SCION_PROFILE" --timeout-seconds "$SPEC_OPS_REVIEW_WAIT_SECONDS" --poll-interval-seconds "$SPEC_OPS_REVIEW_POLL_SECONDS" --output "$SESSION_STATE_ROOT/validation/ops-review-wait.json"
  ready_state: python3 "$AGENT_SCION_OPS_ROOT/scripts/steward-state.py" spec-ready --project-root "$AGENT_PROJECT_ROOT" --session-id "$SESSION_ID" --change "$CHANGE" --base-branch "$BASE_BRANCH" --integration-branch "$FINAL_BRANCH" --validation-command "python3 scripts/validate-openspec-change.py --project-root . --change $CHANGE" --review-summary "<accepted ops review summary>"
  blocked_state: python3 "$AGENT_SCION_OPS_ROOT/scripts/steward-state.py" spec-blocked --project-root "$AGENT_PROJECT_ROOT" --session-id "$SESSION_ID" --change "$CHANGE" --base-branch "$BASE_BRANCH" --phase review --blocker "<blocker summary>" --next-action "<next action>"
  finalize_pr: python3 "$AGENT_SCION_OPS_ROOT/scripts/finalize-steward-pr.py" --project-root "$AGENT_PROJECT_ROOT" --session-id "$SESSION_ID" --kind spec --change "$CHANGE" --branch "$FINAL_BRANCH" --state-branch "$STEWARD_BRANCH" --base-branch "$BASE_BRANCH" --record-state --json > "$SESSION_STATE_ROOT/pr.json"
  validate_ready: python3 "$AGENT_SCION_OPS_ROOT/scripts/validate-steward-session.py" --project-root "$AGENT_PROJECT_ROOT" --session-id "$SESSION_ID" --kind spec --change "$CHANGE" --base-branch "$BASE_BRANCH" --branch "$FINAL_BRANCH" --state-branch "$STEWARD_BRANCH" --require-ready --require-pr$SPEC_REQUIRE_MULTI_HARNESS_FLAG

mandatory_first_actions:
- Run init_state now, then commit and push "$SESSION_STATE_ROOT/state.json" on "$STEWARD_BRANCH".
- Start the clarifier and explorer with the exact scion commands below before
  detailed repo inspection. If either command fails, write blocked_state with
  the command output as the blocker and push it on "$STEWARD_BRANCH".

start_clarifier:
  scion --profile "$SCION_PROFILE" start "$CLARIFIER_NAME" --type "$SPEC_CLARIFIER_TEMPLATE" --branch "$CLARIFIER_NAME" --broker "$BROKER" --harness-config "$SPEC_CLARIFIER_HARNESS" --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
  change: $CHANGE
  base_branch: $BASE_BRANCH
  steward_agent: $STEWARD_NAME
  collection_recipient: $COLLECTION_RECIPIENT
  expected_branch: $CLARIFIER_NAME
  artifact: $SESSION_STATE_ROOT/findings/clarifier.md
  role: clarify the requested OpenSpec outcome, scope boundaries, and operator-facing acceptance questions.
  goal: $GOAL"

start_explorer:
  scion --profile "$SCION_PROFILE" start "$EXPLORER_NAME" --type "$SPEC_EXPLORER_TEMPLATE" --branch "$EXPLORER_NAME" --broker "$BROKER" --harness-config "$SPEC_EXPLORER_HARNESS" --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
  change: $CHANGE
  base_branch: $BASE_BRANCH
  steward_agent: $STEWARD_NAME
  collection_recipient: $COLLECTION_RECIPIENT
  expected_branch: $EXPLORER_NAME
  artifact: $SESSION_STATE_ROOT/findings/explorer.md
  role: inspect existing framework and identify the lowest-risk OpenSpec files and constraints.
  goal: $GOAL"

execution_notes:
- Follow the spec-steward system prompt as the authoritative protocol.
- Do not pause for confirmation. Execute the mandatory first actions before
  detailed repo inspection or authoring.
- Child prompts must include the original goal, expected branch, artifact path,
  steward agent, and collection recipient.
- Create the integration branch from the author branch before review.
- Run wait_review after starting ops review. Do not stop or restart the reviewer
  early only because Hub reports idle activity or the branch has not moved after
  a short poll.
- Finish ready only after validation passes, ops review accepts, and finalize_pr
  records a pull request. Otherwise write blocked state with diagnostics.
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
printf 'Spec steward template/harness: %s / %s\n' "$SPEC_STEWARD_TEMPLATE" "$SPEC_STEWARD_HARNESS"
printf 'Spec specialist harnesses: clarifier=%s/%s explorer=%s/%s author=%s/%s ops_review=%s/%s\n' \
  "$SPEC_CLARIFIER_TEMPLATE" "$SPEC_CLARIFIER_HARNESS" \
  "$SPEC_EXPLORER_TEMPLATE" "$SPEC_EXPLORER_HARNESS" \
  "$SPEC_AUTHOR_TEMPLATE" "$SPEC_AUTHOR_HARNESS" \
  "$SPEC_OPS_REVIEW_TEMPLATE" "$SPEC_OPS_REVIEW_HARNESS"
printf 'Grove root: %s\n' "$PROJECT_ROOT"
printf 'Agent project root: %s\n' "$AGENT_PROJECT_ROOT"
printf 'Agent scion-ops root: %s\n' "$AGENT_SCION_OPS_ROOT"

if [[ "${SCION_OPS_DRY_RUN:-0}" == "1" ]]; then
  cat <<EOF

Dry run command:
  $SCION_BIN --profile "$SCION_PROFILE" --grove "$PROJECT_ROOT" start "$STEWARD_NAME" --type "$SPEC_STEWARD_TEMPLATE" --branch "$STEWARD_BRANCH" --broker "$BROKER" --harness-config "$SPEC_STEWARD_HARNESS" --harness-auth auth-file --no-upload --non-interactive --yes --notify "<prompt>"

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
  --type "$SPEC_STEWARD_TEMPLATE" \
  --branch "$STEWARD_BRANCH" \
  --broker "$BROKER" \
  --harness-config "$SPEC_STEWARD_HARNESS" \
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
printf '  task steward:validate -- --project-root %q --session-id %q --kind spec --change %q --base-branch %q --branch %q --require-ready --require-pr%s\n' "$PROJECT_ROOT" "$SESSION_ID" "$CHANGE" "$BASE_BRANCH" "$FINAL_BRANCH" "$SPEC_REQUIRE_MULTI_HARNESS_FLAG"
