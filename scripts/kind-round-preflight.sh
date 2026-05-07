#!/usr/bin/env bash
# Validate that the kind Hub has the state needed for a consensus round.
set -euo pipefail

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

assert_template_absent() {
  local file="$1"
  local forbidden="$2"
  [[ -f "$file" ]] || die "template prompt is missing: $file"
  if grep -Fq "$forbidden" "$file"; then
    die "template prompt contains forbidden placeholder status text: $forbidden"
  fi
}

SCION_BIN="${SCION_BIN:-scion}"
HUB_ENDPOINT="${SCION_HUB_ENDPOINT:-${HUB_ENDPOINT:-}}"
PROJECT_ROOT_INPUT="${1:-${SCION_OPS_PROJECT_ROOT:-$(pwd -P)}}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
if git -C "$PROJECT_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel)"
fi

command -v "$SCION_BIN" >/dev/null 2>&1 || die "scion not on PATH"
[[ -n "$HUB_ENDPOINT" ]] || die "SCION_HUB_ENDPOINT is not set; run task up or task bootstrap first"
[[ -d "$PROJECT_ROOT" ]] || die "target project is not visible: $PROJECT_ROOT"
git -C "$PROJECT_ROOT" rev-parse --show-toplevel >/dev/null 2>&1 || die "target project is not a git repo: $PROJECT_ROOT"
[[ -f "${PROJECT_ROOT}/.scion/grove-id" ]] || die "target project is not linked to the Hub; run task bootstrap -- ${PROJECT_ROOT}"

if [[ -z "${SCION_DEV_TOKEN:-}" && -z "${SCION_DEV_TOKEN_FILE:-}" && ! -f "${HOME}/.scion/dev-token" ]]; then
  die "Hub dev auth is unavailable; run task bootstrap from the host or expose SCION_DEV_TOKEN_FILE"
fi

required_secrets=(
  GITHUB_TOKEN
  CLAUDE_AUTH
  CLAUDE_CONFIG
  CODEX_AUTH
  GEMINI_OAUTH_CREDS
)

for secret in "${required_secrets[@]}"; do
  (cd "$PROJECT_ROOT" && "$SCION_BIN" hub secret get --scope hub "$secret" \
    --hub "$HUB_ENDPOINT" \
    --json \
    --non-interactive) \
    >/dev/null || die "Hub secret ${secret} is missing; run task bootstrap"
done

required_templates=(
  consensus-runner
  impl-claude
  impl-codex
  reviewer-claude
  reviewer-codex
  final-reviewer-gemini
  final-reviewer-codex
  spec-consensus-runner
  spec-goal-clarifier
  spec-repo-explorer
  spec-author
  spec-ops-reviewer
  spec-finalizer
)

for template in "${required_templates[@]}"; do
  (cd "$PROJECT_ROOT" && SCION_HUB_ENDPOINT="$HUB_ENDPOINT" "$SCION_BIN" --global templates show "$template" \
    --hub \
    --non-interactive) \
    >/dev/null || die "Hub template ${template} is missing; run task bootstrap"
done

spec_consensus_prompt="${SCION_OPS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/.scion/templates/spec-consensus-runner/system-prompt.md"
assert_template_absent "$spec_consensus_prompt" 'sciontool status blocked "Waiting for <agent names>"'
assert_template_absent "$spec_consensus_prompt" 'sciontool status blocked "<question or blocker>"'
assert_template_absent "$spec_consensus_prompt" 'sciontool status task_completed "round <round_id> spec complete: <branch>"'
