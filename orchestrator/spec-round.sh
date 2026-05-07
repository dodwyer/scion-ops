#!/usr/bin/env bash
# Start a Scion-native spec-building round.
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
PROJECT_ROOT_INPUT="${SCION_OPS_PROJECT_ROOT:-$SCION_OPS_ROOT}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT_INPUT" && pwd -P)"
PROJECT_ROOT="$(git -C "$PROJECT_ROOT" rev-parse --show-toplevel 2>/dev/null)" || die "target project is not a git repo: $PROJECT_ROOT"
AGENT_PROJECT_ROOT="${SCION_OPS_AGENT_PROJECT_ROOT:-/workspace}"

ROUND_ID="${ROUND_ID:-$(date -u +%Y%m%dt%H%M%Sz)-$(printf '%04x' "$RANDOM")}"
ROUND_ID="$(printf '%s' "$ROUND_ID" | tr '[:upper:]' '[:lower:]')"
CHANGE="${SCION_OPS_SPEC_CHANGE:-}"
BASE_BRANCH="${BASE_BRANCH:-$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || true)}"
BROKER="${SCION_KIND_CP_BROKER:-kind-control-plane}"
COLLECTION_RECIPIENT="${SCION_OPS_COLLECTION_RECIPIENT:-user:dev@localhost}"
if [[ -z "$BASE_BRANCH" ]]; then
  BASE_BRANCH="$(git -C "$PROJECT_ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
fi
BASE_BRANCH="${BASE_BRANCH:-main}"
RUNNER_NAME="round-${ROUND_ID}-spec-consensus"
RUNNER_BRANCH="$RUNNER_NAME"
COORDINATOR_PROTOCOL_FILE="$SCION_OPS_ROOT/.scion/templates/spec-consensus-runner/system-prompt.md"
COORDINATOR_PROTOCOL=""
if [[ -f "$COORDINATOR_PROTOCOL_FILE" ]]; then
  COORDINATOR_PROTOCOL="$(cat "$COORDINATOR_PROTOCOL_FILE")"
fi

github_authenticated_remote() {
  local remote="$1"
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    case "$remote" in
      https://github.com/*)
        printf 'https://x-access-token:%s@github.com/%s' "$GITHUB_TOKEN" "${remote#https://github.com/}"
        return
        ;;
      git@github.com:*)
        printf 'https://x-access-token:%s@github.com/%s' "$GITHUB_TOKEN" "${remote#git@github.com:}"
        return
        ;;
      ssh://git@github.com/*)
        printf 'https://x-access-token:%s@github.com/%s' "$GITHUB_TOKEN" "${remote#ssh://git@github.com/}"
        return
        ;;
    esac
  fi
  printf '%s' "$remote"
}

ensure_remote_branch() {
  local branch="$1"
  local remote push_remote base_ref

  remote="$(git -C "$PROJECT_ROOT" remote get-url origin 2>/dev/null || true)"
  [[ -n "$remote" ]] || {
    printf 'Warning: origin remote is missing; cannot pre-create %s\n' "$branch" >&2
    return 0
  }
  push_remote="$(github_authenticated_remote "$remote")"

  if GIT_TERMINAL_PROMPT=0 git -C "$PROJECT_ROOT" ls-remote --exit-code --heads "$push_remote" "$branch" >/dev/null 2>&1; then
    return 0
  fi

  base_ref="$BASE_BRANCH"
  if ! git -C "$PROJECT_ROOT" rev-parse --verify --quiet "${base_ref}^{commit}" >/dev/null; then
    base_ref="origin/$BASE_BRANCH"
  fi
  if ! git -C "$PROJECT_ROOT" rev-parse --verify --quiet "${base_ref}^{commit}" >/dev/null; then
    base_ref="HEAD"
  fi

  printf 'Pre-creating round branch: %s\n' "$branch"
  if ! GIT_TERMINAL_PROMPT=0 git -C "$PROJECT_ROOT" push "$push_remote" "${base_ref}:refs/heads/${branch}" >/dev/null; then
    printf 'Warning: failed to pre-create %s; Scion will try to create it during agent start\n' "$branch" >&2
  fi
}

precreate_round_branches() {
  local suffix
  for suffix in spec-consensus spec-clarifier spec-explorer spec-author spec-ops-review spec-finalizer spec-integration; do
    ensure_remote_branch "round-${ROUND_ID}-${suffix}"
  done
}

load_github_token_for_branch_precreate() {
  local token_file="/run/secrets/scion-github-token/GITHUB_TOKEN"
  if [[ -z "${GITHUB_TOKEN:-}" && -r "$token_file" ]]; then
    GITHUB_TOKEN="$(cat "$token_file")"
    export GITHUB_TOKEN
  fi
}

if [[ "${SCION_OPS_ROUND_PREFLIGHT:-1}" != "0" && "${SCION_OPS_DRY_RUN:-0}" != "1" ]]; then
  bash "$SCION_OPS_ROOT/scripts/kind-round-preflight.sh"
fi

TASK_PROMPT=$(cat <<EOF
round_id: $ROUND_ID
base_branch: $BASE_BRANCH
change: $CHANGE
project_root: $AGENT_PROJECT_ROOT
collection_recipient: $COLLECTION_RECIPIENT

original_goal:
$GOAL

Coordinator protocol:
$COORDINATOR_PROTOCOL

Start the spec-building protocol above. Produce only OpenSpec artifacts under
openspec/changes/<change>/ in the target project. Do not implement code, tests,
manifests, product docs, or runtime changes during this round. Do not exit until
the final branch round-${ROUND_ID}-spec-integration exists on origin and contains
the committed OpenSpec artifacts.
EOF
)

printf 'Starting spec consensus runner: %s\n' "$RUNNER_NAME"
printf 'Round id: %s\n' "$ROUND_ID"
printf 'Base branch: %s\n' "$BASE_BRANCH"
printf 'Change: %s\n' "${CHANGE:-<derive in round>}"
printf 'Broker: %s\n' "$BROKER"
printf 'Collection recipient: %s\n' "$COLLECTION_RECIPIENT"
printf 'Grove root: %s\n' "$PROJECT_ROOT"
printf 'Agent project root: %s\n' "$AGENT_PROJECT_ROOT"

if [[ "${SCION_OPS_DRY_RUN:-0}" == "1" ]]; then
  cat <<EOF

Dry run command:
  $SCION_BIN --grove "$PROJECT_ROOT" start "$RUNNER_NAME" --type spec-consensus-runner --branch "$RUNNER_BRANCH" --broker "$BROKER" --harness-auth auth-file --no-upload --non-interactive --yes --notify "<prompt>"

Rendered prompt:
$TASK_PROMPT
EOF
  exit 0
fi

if [[ "${SCION_OPS_PRECREATE_ROUND_BRANCHES:-1}" != "0" ]]; then
  load_github_token_for_branch_precreate
  precreate_round_branches
fi

"$SCION_BIN" --grove "$PROJECT_ROOT" start "$RUNNER_NAME" \
  --type spec-consensus-runner \
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
