#!/usr/bin/env bash
# Start an opt-in subscription-backed Scion round for release confidence.
set -euo pipefail

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT_INPUT="${1:-${SCION_OPS_PROJECT_ROOT:-$REPO_ROOT}}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel 2>/dev/null)" || die "target project is not a git repo: $PROJECT_ROOT"

ROUND_ID="${ROUND_ID:-release-smoke-$(date -u +%Y%m%dT%H%M%SZ)}"
MAX_MINUTES="${SCION_OPS_RELEASE_SMOKE_MAX_MINUTES:-8}"
MAX_REVIEW_ROUNDS="${SCION_OPS_RELEASE_SMOKE_MAX_REVIEW_ROUNDS:-1}"
FINAL_REVIEWER="${SCION_OPS_RELEASE_SMOKE_FINAL_REVIEWER:-gemini}"
PROMPT="${SCION_OPS_RELEASE_SMOKE_PROMPT:-}"

case "$FINAL_REVIEWER" in
  gemini|codex) ;;
  *) die "SCION_OPS_RELEASE_SMOKE_FINAL_REVIEWER must be gemini or codex" ;;
esac

if [[ -z "$PROMPT" ]]; then
  PROMPT=$(cat <<'EOF'
Release smoke: make the smallest safe README wording improvement, verify it,
push the resulting branch, and report the PR-ready branch name. Keep the change
minimal; this run exists to prove subscription-backed Claude, Codex, and final
reviewer credentials in Kubernetes.
EOF
)
fi

if [[ "${SCION_OPS_RELEASE_SMOKE_BOOTSTRAP:-1}" != "0" ]]; then
  task bootstrap -- "$PROJECT_ROOT"
fi

cat <<EOF
release smoke
  project_root:       $PROJECT_ROOT
  round_id:           $ROUND_ID
  max_minutes:        $MAX_MINUTES
  max_review_rounds:  $MAX_REVIEW_ROUNDS
  final_reviewer:     $FINAL_REVIEWER

This is an opt-in model-backed test. It starts Claude/Codex round agents and
uses the selected final reviewer. Use task test for frequent no-spend checks.
EOF

SCION_OPS_PROJECT_ROOT="$PROJECT_ROOT" \
ROUND_ID="$ROUND_ID" \
MAX_MINUTES="$MAX_MINUTES" \
MAX_REVIEW_ROUNDS="$MAX_REVIEW_ROUNDS" \
FINAL_REVIEWER="$FINAL_REVIEWER" \
task round -- "$PROMPT"
