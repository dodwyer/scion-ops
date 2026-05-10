#!/usr/bin/env bash
# Validate that the kind Hub has the state needed for steward sessions.
set -euo pipefail

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

json_field() {
  local field="$1"
  python3 -c '
import json
import re
import sys

field = sys.argv[1]
raw = sys.stdin.read()
raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
start = raw.find("{")
if start < 0:
    raise SystemExit(1)
data = json.loads(raw[start:])
print(data.get(field) or "")
' "$field"
}

SCION_BIN="${SCION_BIN:-scion}"
HUB_ENDPOINT="${SCION_HUB_ENDPOINT:-${HUB_ENDPOINT:-}}"
SCION_OPS_ROOT="${SCION_OPS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
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
  impl-claude
  impl-codex
  reviewer-claude
  reviewer-codex
  final-reviewer-gemini
  final-reviewer-codex
  spec-goal-clarifier
  spec-goal-clarifier-claude
  spec-repo-explorer
  spec-author
  spec-ops-reviewer
  spec-ops-reviewer-claude
  spec-finalizer
  spec-steward
  implementation-steward
)

declare -A expected_template_harness=(
  [spec-goal-clarifier]=codex-exec
  [spec-goal-clarifier-claude]=claude
  [spec-repo-explorer]=codex-exec
  [spec-author]=codex-exec
  [spec-ops-reviewer]=codex-exec
  [spec-ops-reviewer-claude]=claude
  [spec-finalizer]=codex-exec
  [spec-steward]=codex-exec
  [implementation-steward]=codex-exec
  [impl-codex]=codex-exec
  [reviewer-codex]=codex-exec
  [final-reviewer-codex]=codex-exec
)

for template in "${required_templates[@]}"; do
  template_json="$(
    (
      cd "$PROJECT_ROOT" &&
        SCION_HUB_ENDPOINT="$HUB_ENDPOINT" "$SCION_BIN" --global templates show "$template" \
          --hub \
          --format json \
          --non-interactive
    ) 2>&1
  )" || die "Hub template ${template} is missing; run task bootstrap"

  expected="${expected_template_harness[$template]:-}"
  if [[ -n "$expected" && "${SCION_OPS_SKIP_TEMPLATE_HARNESS_PREFLIGHT:-0}" != "1" ]]; then
    actual="$(printf '%s' "$template_json" | json_field harness)" ||
      die "could not read Hub template harness for ${template}; run task bootstrap"
    if [[ "$actual" != "$expected" ]]; then
      die "Hub template ${template} uses harness ${actual:-<empty>}, expected ${expected}; run task bootstrap"
    fi
  fi
done

if [[ "${SCION_OPS_SKIP_TEMPLATE_HARNESS_PREFLIGHT:-0}" != "1" ]]; then
  SCION_HUB_ENDPOINT="$HUB_ENDPOINT" \
    python3 "${SCION_OPS_ROOT}/scripts/hub-managed-templates.py" verify \
    >/dev/null || die "Hub managed template records are not ready; run task bootstrap"
fi
