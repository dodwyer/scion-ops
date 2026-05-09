#!/usr/bin/env bash
# Start a Scion-native implementation steward session from an approved OpenSpec change.
set -euo pipefail

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

CHANGE=""
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --change)
      [[ $# -ge 2 ]] || die "--change requires a value"
      CHANGE="$2"
      shift 2
      ;;
    --change=*)
      CHANGE="${1#--change=}"
      shift
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

[[ -n "$CHANGE" ]] || die "Usage: $(basename "$0") --change <change> \"<optional implementation goal>\""
GOAL="${ARGS[*]:-Implement the approved OpenSpec change.}"

SCION_BIN="${SCION_BIN:-scion}"
command -v "$SCION_BIN" >/dev/null || die "scion not on PATH"

SCION_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCION_OPS_ROOT/orchestrator/lib/github-branches.sh"

PROJECT_ROOT_INPUT="${SCION_OPS_PROJECT_ROOT:-$SCION_OPS_ROOT}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel 2>/dev/null)" || die "target project is not a git repo: $PROJECT_ROOT"
AGENT_PROJECT_ROOT="${SCION_OPS_AGENT_PROJECT_ROOT:-/workspace}"

SESSION_ID="${SCION_OPS_SESSION_ID:-${ROUND_ID:-$(date -u +%Y%m%dt%H%M%Sz)-$(printf '%04x' "$RANDOM")}}"
SESSION_ID="$(printf '%s' "$SESSION_ID" | tr '[:upper:]' '[:lower:]')"
ROUND_ID="$SESSION_ID"
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

VALIDATION_JSON="$(python3 "$SCION_OPS_ROOT/scripts/validate-openspec-change.py" \
  --project-root "$PROJECT_ROOT" \
  --change "$CHANGE" \
  --json)" || {
  printf '%s\n' "$VALIDATION_JSON"
  die "OpenSpec change is missing or invalid: $CHANGE"
}

STEWARD_NAME="round-${SESSION_ID}-implementation-steward"
STEWARD_BRANCH="$STEWARD_NAME"
FINAL_BRANCH="round-${SESSION_ID}-integration"
SESSION_STATE_ROOT=".scion-ops/sessions/${SESSION_ID}"

precreate_session_branches() {
  local suffix
  for suffix in implementation-steward impl-codex impl-claude final-review integration; do
    scion_ops_ensure_remote_branch "$PROJECT_ROOT" "round-${SESSION_ID}-${suffix}" "$BASE_BRANCH"
  done
}

if [[ "${SCION_OPS_ROUND_PREFLIGHT:-1}" != "0" && "${SCION_OPS_DRY_RUN:-0}" != "1" ]]; then
  bash "$SCION_OPS_ROOT/scripts/kind-round-preflight.sh"
fi

TASK_PROMPT=$(cat <<EOF
session_id: $SESSION_ID
round_id: $ROUND_ID
session_type: implementation
change: $CHANGE
spec_artifact_root: openspec/changes/$CHANGE
base_branch: $BASE_BRANCH
base_branch_explicit: $BASE_BRANCH_EXPLICIT
scion_profile: $SCION_PROFILE
project_root: $AGENT_PROJECT_ROOT
collection_recipient: $COLLECTION_RECIPIENT
session_state_root: $SESSION_STATE_ROOT
final_branch: $FINAL_BRANCH

approved_spec_artifacts:
- openspec/changes/$CHANGE/proposal.md
- openspec/changes/$CHANGE/design.md
- openspec/changes/$CHANGE/tasks.md
- openspec/changes/$CHANGE/specs/

validation:
$VALIDATION_JSON

implementation_goal:
$GOAL

Start the implementation steward playbook. Coordinate specialist implementers
and reviewers, keep durable state under $SESSION_STATE_ROOT, implement only the
approved OpenSpec change, and finish ready only when $FINAL_BRANCH exists and is
pushed with passing verification and an accepting final-review verdict.
EOF
)

printf 'Starting implementation steward: %s\n' "$STEWARD_NAME"
printf 'session_id: %s\n' "$SESSION_ID"
printf 'round_id: %s\n' "$ROUND_ID"
printf 'Base branch: %s\n' "$BASE_BRANCH"
printf 'Change: %s\n' "$CHANGE"
printf 'Final branch: %s\n' "$FINAL_BRANCH"
printf 'Scion profile: %s\n' "$SCION_PROFILE"
printf 'Broker: %s\n' "$BROKER"
printf 'Collection recipient: %s\n' "$COLLECTION_RECIPIENT"
printf 'Grove root: %s\n' "$PROJECT_ROOT"
printf 'Agent project root: %s\n' "$AGENT_PROJECT_ROOT"

if [[ "${SCION_OPS_DRY_RUN:-0}" == "1" ]]; then
  cat <<EOF

Dry run command:
  $SCION_BIN --profile "$SCION_PROFILE" --grove "$PROJECT_ROOT" start "$STEWARD_NAME" --type implementation-steward --branch "$STEWARD_BRANCH" --broker "$BROKER" --harness-auth auth-file --no-upload --non-interactive --yes --notify "<prompt>"

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
  --type implementation-steward \
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
printf '  task steward:validate -- --project-root %q --session-id %q --kind implementation --change %q --branch %q --require-ready\n' "$PROJECT_ROOT" "$SESSION_ID" "$CHANGE" "$FINAL_BRANCH"
