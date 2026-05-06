#!/usr/bin/env bash
# Start an implementation round from an approved OpenSpec change.
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

SCION_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT_INPUT="${SCION_OPS_PROJECT_ROOT:-$SCION_OPS_ROOT}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel 2>/dev/null)" || die "target project is not a git repo: $PROJECT_ROOT"
AGENT_PROJECT_ROOT="${SCION_OPS_AGENT_PROJECT_ROOT:-/workspace}"
BASE_BRANCH="${BASE_BRANCH:-$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || true)}"
if [[ -z "$BASE_BRANCH" ]]; then
  BASE_BRANCH="$(git -C "$PROJECT_ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
fi
BASE_BRANCH="${BASE_BRANCH:-main}"

VALIDATION_JSON="$(python3 "$SCION_OPS_ROOT/scripts/validate-openspec-change.py" \
  --project-root "$PROJECT_ROOT" \
  --change "$CHANGE" \
  --json)" || {
  printf '%s\n' "$VALIDATION_JSON"
  die "OpenSpec change is missing or invalid: $CHANGE"
}

IMPLEMENTATION_PROMPT=$(cat <<EOF
spec_change: $CHANGE
spec_artifact_root: openspec/changes/$CHANGE
base_branch: $BASE_BRANCH
project_root: $AGENT_PROJECT_ROOT

approved_spec_artifacts:
- openspec/changes/$CHANGE/proposal.md
- openspec/changes/$CHANGE/design.md
- openspec/changes/$CHANGE/tasks.md
- openspec/changes/$CHANGE/specs/

validation:
$VALIDATION_JSON

implementation_goal:
$GOAL

Implement the approved OpenSpec change. Before editing, read proposal.md,
design.md, tasks.md, and all delta specs under specs/. Treat those artifacts as
the implementation contract. Do not expand scope beyond the approved artifacts.
Update tasks.md checkboxes for tasks you complete. If implementation reveals a
real spec conflict, update the artifact text and report why in your completion
summary.

Reviewers must distinguish implementation quality from spec conformance. Spec
drift is a blocking issue even when the code works.
EOF
)

if [[ "${SCION_OPS_DRY_RUN:-0}" == "1" ]]; then
  cat <<EOF
Spec implementation dry run:
project_root: $PROJECT_ROOT
change: $CHANGE
base_branch: $BASE_BRANCH

Rendered prompt:
$IMPLEMENTATION_PROMPT
EOF
  exit 0
fi

env \
  "SCION_OPS_PROJECT_ROOT=$PROJECT_ROOT" \
  "BASE_BRANCH=$BASE_BRANCH" \
  bash "$SCION_OPS_ROOT/orchestrator/run-round.sh" "$IMPLEMENTATION_PROMPT"
