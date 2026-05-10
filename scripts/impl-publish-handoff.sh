#!/usr/bin/env bash
# Commit, push, and verify an implementation handoff artifact.
set -euo pipefail

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

PROJECT_ROOT="."
SESSION_ID=""
AGENT=""
BRANCH=""
HANDOFF=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      [[ $# -ge 2 ]] || die "--project-root requires a value"
      PROJECT_ROOT="$2"
      shift 2
      ;;
    --session-id)
      [[ $# -ge 2 ]] || die "--session-id requires a value"
      SESSION_ID="$2"
      shift 2
      ;;
    --agent)
      [[ $# -ge 2 ]] || die "--agent requires a value"
      AGENT="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "--branch requires a value"
      BRANCH="$2"
      shift 2
      ;;
    --handoff)
      [[ $# -ge 2 ]] || die "--handoff requires a value"
      HANDOFF="$2"
      shift 2
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$SESSION_ID" ]] || die "--session-id is required"
[[ -n "$AGENT" ]] || die "--agent is required"
[[ -n "$BRANCH" ]] || die "--branch is required"

PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd -P)"
HANDOFF="${HANDOFF:-.scion-ops/sessions/${SESSION_ID}/findings/${AGENT}.json}"
[[ -f "$PROJECT_ROOT/$HANDOFF" ]] || die "handoff artifact is missing: $HANDOFF"

cd "$PROJECT_ROOT"

CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
if [[ -n "$CURRENT_BRANCH" && "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  die "current branch $CURRENT_BRANCH does not match expected branch $BRANCH"
fi

git config user.email "${GIT_AUTHOR_EMAIL:-scion-ops@example.invalid}"
git config user.name "${GIT_AUTHOR_NAME:-scion-ops}"

python3 - "$HANDOFF" "$AGENT" "$BRANCH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
agent = sys.argv[2]
branch = sys.argv[3]
required = ["status", "changed_files", "tasks_completed", "tests_run", "blockers", "summary"]

try:
    payload = json.loads(path.read_text())
except json.JSONDecodeError as exc:
    raise SystemExit(f"{path}: invalid JSON: {exc}") from exc

if not isinstance(payload, dict):
    raise SystemExit(f"{path}: handoff must be a JSON object")

missing = [key for key in required if key not in payload]
if missing:
    raise SystemExit(f"{path}: missing required fields: {', '.join(missing)}")

for key in ("changed_files", "tasks_completed", "tests_run", "blockers"):
    if not isinstance(payload.get(key), list):
        raise SystemExit(f"{path}: {key} must be a list")

payload["agent"] = agent
payload["branch"] = branch
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

git add -A
git reset -- "$HANDOFF" >/dev/null 2>&1 || true
if ! git diff --cached --quiet; then
  git commit -m "Implement ${SESSION_ID} ${AGENT} changes"
fi

PRODUCT_HEAD="$(git rev-parse HEAD)"
python3 - "$HANDOFF" "$PRODUCT_HEAD" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text())
payload["head_sha"] = sys.argv[2]
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

git add "$HANDOFF"
if ! git diff --cached --quiet; then
  git commit -m "Record implementation handoff for ${SESSION_ID} ${AGENT}"
fi

git push origin "HEAD:refs/heads/${BRANCH}"
git fetch origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}"
git show "origin/${BRANCH}:${HANDOFF}"
