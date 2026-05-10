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
if ! scion_ops_resolve_base_ref "$PROJECT_ROOT" "$BASE_BRANCH" >/dev/null; then
  die "base branch does not resolve locally or on origin: $BASE_BRANCH"
fi

VALIDATION_PROJECT_ROOT="$PROJECT_ROOT"
VALIDATION_TMP_DIR=""
STATE_INIT_TMP_DIR=""
cleanup_tmp_dirs() {
  if [[ -n "$VALIDATION_TMP_DIR" ]]; then
    rm -rf "$VALIDATION_TMP_DIR"
  fi
  if [[ -n "$STATE_INIT_TMP_DIR" ]]; then
    rm -rf "$STATE_INIT_TMP_DIR"
  fi
}
trap cleanup_tmp_dirs EXIT

if [[ "$BASE_BRANCH_EXPLICIT" == "1" ]]; then
  VALIDATION_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/scion-openspec-validation.XXXXXX")"
  if ! scion_ops_export_base_branch_to_temp_root "$PROJECT_ROOT" "$BASE_BRANCH" "$VALIDATION_TMP_DIR"; then
    die "base branch does not resolve locally or on origin: $BASE_BRANCH"
  fi
  VALIDATION_PROJECT_ROOT="$VALIDATION_TMP_DIR"
fi

VALIDATION_JSON="$(python3 "$SCION_OPS_ROOT/scripts/validate-openspec-change.py" \
  --project-root "$VALIDATION_PROJECT_ROOT" \
  --change "$CHANGE" \
  --json)" || {
  printf '%s\n' "$VALIDATION_JSON"
  die "OpenSpec change is missing or invalid: $CHANGE"
}

STEWARD_NAME="round-${SESSION_ID}-implementation-steward"
STEWARD_BRANCH="$STEWARD_NAME"
IMPLEMENTER_NAME="round-${SESSION_ID}-impl-codex"
SECOND_IMPLEMENTER_NAME="round-${SESSION_ID}-impl-claude"
FINAL_REVIEW_NAME="round-${SESSION_ID}-final-review"
FINAL_BRANCH="round-${SESSION_ID}-integration"
SESSION_STATE_ROOT=".scion-ops/sessions/${SESSION_ID}"
IMPLEMENTER_HANDOFF="$SESSION_STATE_ROOT/findings/$IMPLEMENTER_NAME.json"
SECOND_IMPLEMENTER_HANDOFF="$SESSION_STATE_ROOT/findings/$SECOND_IMPLEMENTER_NAME.json"

precreate_session_branches() {
  local suffix
  for suffix in implementation-steward impl-codex impl-claude integration; do
    scion_ops_ensure_remote_branch "$PROJECT_ROOT" "round-${SESSION_ID}-${suffix}" "$BASE_BRANCH"
  done
}

initialize_steward_state_branch() {
  [[ "${SCION_OPS_INITIALIZE_STEWARD_STATE:-1}" != "0" ]] || return 0

  local remote push_remote state_file
  remote="$(git -C "$PROJECT_ROOT" remote get-url origin 2>/dev/null || true)"
  [[ -n "$remote" ]] || die "origin remote is required to initialize steward state"
  push_remote="$(scion_ops_github_authenticated_remote "$remote")"

  scion_ops_ensure_remote_branch "$PROJECT_ROOT" "$STEWARD_BRANCH" "$BASE_BRANCH"

  STATE_INIT_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/scion-implementation-state.XXXXXX")"
  if ! GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch --branch "$STEWARD_BRANCH" "$push_remote" "$STATE_INIT_TMP_DIR"; then
    die "failed to clone steward branch for state initialization: $STEWARD_BRANCH"
  fi

  state_file="$STATE_INIT_TMP_DIR/$SESSION_STATE_ROOT/state.json"
  if [[ -f "$state_file" ]]; then
    printf 'Steward state already exists on branch: %s\n' "$STEWARD_BRANCH"
    return 0
  fi

  git -C "$STATE_INIT_TMP_DIR" config user.email "${GIT_AUTHOR_EMAIL:-scion-ops@example.invalid}"
  git -C "$STATE_INIT_TMP_DIR" config user.name "${GIT_AUTHOR_NAME:-scion-ops}"

  python3 "$SCION_OPS_ROOT/scripts/steward-state.py" implementation-init \
    --project-root "$STATE_INIT_TMP_DIR" \
    --session-id "$SESSION_ID" \
    --change "$CHANGE" \
    --base-branch "$BASE_BRANCH" \
    --integration-branch "$FINAL_BRANCH"

  cat >"$STATE_INIT_TMP_DIR/$SESSION_STATE_ROOT/brief.md" <<EOF
# Implementation Steward Session $SESSION_ID

Change: $CHANGE
Base branch: $BASE_BRANCH
Final branch: $FINAL_BRANCH

Goal:
$GOAL
EOF

  git -C "$STATE_INIT_TMP_DIR" add "$SESSION_STATE_ROOT/state.json" "$SESSION_STATE_ROOT/brief.md"
  if git -C "$STATE_INIT_TMP_DIR" diff --cached --quiet; then
    return 0
  fi
  git -C "$STATE_INIT_TMP_DIR" commit --quiet -m "Initialize implementation steward state for $SESSION_ID"
  if ! GIT_TERMINAL_PROMPT=0 git -C "$STATE_INIT_TMP_DIR" push "$push_remote" "HEAD:refs/heads/$STEWARD_BRANCH" >/dev/null; then
    die "failed to push initial steward state to $STEWARD_BRANCH"
  fi
  printf 'Initialized steward state on branch: %s\n' "$STEWARD_BRANCH"
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
scion_ops_root: $AGENT_SCION_OPS_ROOT
collection_recipient: $COLLECTION_RECIPIENT
session_state_root: $SESSION_STATE_ROOT
final_branch: $FINAL_BRANCH
steward_agent: $STEWARD_NAME
implementer_agent: $IMPLEMENTER_NAME
secondary_implementer_agent: $SECOND_IMPLEMENTER_NAME
final_review_agent: $FINAL_REVIEW_NAME
implementer_handoff: $IMPLEMENTER_HANDOFF
secondary_implementer_handoff: $SECOND_IMPLEMENTER_HANDOFF

approved_spec_artifacts:
- openspec/changes/$CHANGE/proposal.md
- openspec/changes/$CHANGE/design.md
- openspec/changes/$CHANGE/tasks.md
- openspec/changes/$CHANGE/specs/

validation:
$VALIDATION_JSON

implementation_goal:
$GOAL

required_first_actions:
1. Confirm $SESSION_STATE_ROOT/state.json already exists on the steward branch.
   The launcher pre-initialized it before starting you. If it is missing, create
   it immediately, commit it to $STEWARD_BRANCH, push it, and do no product work.
2. Read the approved artifacts, then write a concise implementation brief under
   $SESSION_STATE_ROOT/brief.md on the steward branch. The brief must list
   task groups, owned paths, verification commands, and which implementer branch
   owns each group. Commit and push the brief before starting product work.
3. Start implementer agents before any implementation edits. Do not hand a broad
   multi-area change to a single implementer. If the approved tasks span more
   than one area, split them into bounded implementer prompts with explicit
   owned paths and out-of-scope paths. For changes that touch both application
   code and kind/kustomize install or smoke coverage, use at least two
   implementer branches.
4. Before every implementer start, including replacement branches you invent,
   pre-create and verify the remote child branch from the accepted base. Scion
   may fall back to the repository default branch when a requested branch is
   missing; that is invalid. Use the checked-in helper instead of open-coded
   shell so quoting, refspecs, and shallow checkouts are handled consistently:

   python3 "$AGENT_SCION_OPS_ROOT/scripts/precreate-agent-branch.py" --project-root "$AGENT_PROJECT_ROOT" --branch "<child branch>" --base-branch "$BASE_BRANCH" --output "$SESSION_STATE_ROOT/validation/<child branch>-branch.json"

   If the guard fails, record the blocker in state and do not start that child.
5. Use $IMPLEMENTER_NAME for the first bounded implementation branch. Substitute
   the actual bounded scope, owned paths, and out-of-scope paths in the prompt:

   scion --profile "$SCION_PROFILE" start "$IMPLEMENTER_NAME" --type impl-codex --branch "$IMPLEMENTER_NAME" --broker "$BROKER" --harness-config codex-exec --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
change: $CHANGE
base_branch: $BASE_BRANCH
collection_recipient: $COLLECTION_RECIPIENT
steward_agent: $STEWARD_NAME
expected_branch: $IMPLEMENTER_NAME
handoff_file: $IMPLEMENTER_HANDOFF
scope: <bounded task group from $SESSION_STATE_ROOT/brief.md>
owned_paths: <paths this branch may edit>
out_of_scope: <paths this branch must not edit>
artifact_boundary: implement only the assigned slice of the approved OpenSpec change under openspec/changes/$CHANGE
expected_summary: branch pushed, changed files, tasks updated, tests run, blockers
completion_contract: before final response or task_completed, write $IMPLEMENTER_HANDOFF as JSON with status, changed_files, tasks_completed, tests_run, blockers, and summary, then run bash scripts/impl-publish-handoff.sh --project-root . --session-id $SESSION_ID --agent $IMPLEMENTER_NAME --branch $IMPLEMENTER_NAME --handoff $IMPLEMENTER_HANDOFF

Read proposal.md, design.md, tasks.md, and all delta specs under openspec/changes/$CHANGE/specs/. Implement only your assigned slice, update only task checkboxes you complete, publish the handoff with the helper, then send a concise completion summary to $STEWARD_NAME and copy $COLLECTION_RECIPIENT."

6. After every implementer start, wait for the durable handoff artifact before
   accepting the branch. For the default implementer:

   python3 "$AGENT_SCION_OPS_ROOT/scripts/wait-for-review-artifact.py" --project-root "$AGENT_PROJECT_ROOT" --branch "$IMPLEMENTER_NAME" --artifact "$IMPLEMENTER_HANDOFF" --agent "$IMPLEMENTER_NAME" --scion-profile "$SCION_PROFILE" --timeout-seconds "900" --poll-interval-seconds "20" --output "$SESSION_STATE_ROOT/validation/$IMPLEMENTER_NAME-handoff-wait.json" --require-head-sha-ancestor --require-json-fields agent status branch head_sha changed_files tasks_completed tests_run blockers summary

   Use the same command shape for the secondary implementer and replacements,
   substituting their branch, agent, and handoff file. If an implementer cannot
   be started, times out without a valid handoff, reports status "blocked", or
   exits without branch movement, record a structured blocker cause such as
   agent_start_failed, artifact_timeout, branch_guard_failed, pod_missing,
   hub_stale_state, or no_branch_movement. The wait output already captures
   scion look, pod JSON, and Kubernetes logs on timeout; commit that diagnostic
   file before stopping idle workers. Start a replacement only with a narrower
   prompt. If no implementer can produce a non-empty branch and completed
   handoff, finish blocked. Do not implement the approved change in the steward
   checkout.
7. After implementation branches are accepted and integrated into $FINAL_BRANCH,
   create or update the final-review branch from the pushed integration commit,
   not from the accepted spec base. If $FINAL_REVIEW_NAME already exists at the
   accepted base and has no review commits, advance it to the integration SHA.
   If it has review commits or cannot be advanced safely, choose a fresh review
   branch name and record it in state before starting the reviewer.

   Use this guard before final review:

   INTEGRATION_SHA="\$(git ls-remote --heads origin "$FINAL_BRANCH" | awk '{print \$1}')"
   test -n "\$INTEGRATION_SHA" || { echo "integration branch does not exist on origin: $FINAL_BRANCH" >&2; exit 1; }
   REVIEW_SHA="\$(git ls-remote --heads origin "$FINAL_REVIEW_NAME" | awk '{print \$1}')"
   if test -z "\$REVIEW_SHA"; then
     git push origin "\$INTEGRATION_SHA:refs/heads/$FINAL_REVIEW_NAME"
   elif test "\$REVIEW_SHA" != "\$INTEGRATION_SHA"; then
     git fetch origin "$FINAL_BRANCH" "$FINAL_REVIEW_NAME" "$BASE_BRANCH"
     if git merge-base --is-ancestor "\$REVIEW_SHA" "\$INTEGRATION_SHA"; then
       git push --force-with-lease=refs/heads/$FINAL_REVIEW_NAME:"\$REVIEW_SHA" origin "\$INTEGRATION_SHA:refs/heads/$FINAL_REVIEW_NAME"
     else
       echo "final-review branch has unique commits; choose a fresh review branch" >&2
       exit 1
     fi
   fi

   Then start final review with:

   scion --profile "$SCION_PROFILE" start "$FINAL_REVIEW_NAME" --type final-reviewer-codex --branch "$FINAL_REVIEW_NAME" --broker "$BROKER" --harness-config codex-exec --harness-auth auth-file --no-upload --non-interactive --notify "session_id: $SESSION_ID
change: $CHANGE
base_branch: $BASE_BRANCH
review_branch: $FINAL_BRANCH
collection_recipient: $COLLECTION_RECIPIENT
steward_agent: $STEWARD_NAME
verdict_file: $SESSION_STATE_ROOT/reviews/final-review.json
expected_summary: verdict accept/reject/blocked, blocking issues, verification gaps, PR readiness

Review only $FINAL_BRANCH against the approved OpenSpec artifacts. Do not edit product files. Write, commit, and push $SESSION_STATE_ROOT/reviews/final-review.json on your review branch, then send a concise verdict summary to $STEWARD_NAME and copy $COLLECTION_RECIPIENT."

   After starting final review, wait for the durable verdict artifact before
   deciding readiness. Final-review verdicts are review records, not
   implementation handoffs, so do not require head_sha or use
   --require-head-sha-ancestor for this wait. Use verdict-specific fields:

   python3 "$AGENT_SCION_OPS_ROOT/scripts/wait-for-review-artifact.py" --project-root "$AGENT_PROJECT_ROOT" --branch "$FINAL_REVIEW_NAME" --artifact "$SESSION_STATE_ROOT/reviews/final-review.json" --agent "$FINAL_REVIEW_NAME" --scion-profile "$SCION_PROFILE" --timeout-seconds "900" --poll-interval-seconds "20" --output "$SESSION_STATE_ROOT/validation/$FINAL_REVIEW_NAME-wait.json" --require-json-fields verdict summary blocking_issues

   If the wait times out, record a structured blocker with cause
   artifact_timeout and commit the wait diagnostics. If the verdict is not
   accept, record the final-review verdict, blocking issues, classification,
   and evidence in state.json, then either route a bounded repair when policy
   allows it or finish blocked. Do not leave the steward waiting on a durable
   request_changes or blocked verdict.

8. After verification passes and final review accepts, update
   $SESSION_STATE_ROOT/state.json on the steward branch with status ready,
   phase complete, the final integration branch, passing verification evidence,
   the accepting final-review verdict, and no blockers. Then create or return
   the GitHub pull request for the ready integration branch before reporting
   task_completed:

   python3 "$AGENT_SCION_OPS_ROOT/scripts/finalize-steward-pr.py" \
     --project-root "$AGENT_PROJECT_ROOT" \
     --session-id "$SESSION_ID" \
     --kind implementation \
     --change "$CHANGE" \
     --branch "$FINAL_BRANCH" \
     --state-branch "$STEWARD_BRANCH" \
     --base-branch "$BASE_BRANCH" \
     --record-state \
     --json > "$SESSION_STATE_ROOT/pr.json"

   git add "$SESSION_STATE_ROOT/state.json" "$SESSION_STATE_ROOT/pr.json"
   if ! git diff --cached --quiet; then
     git commit -m "Record implementation steward PR for $SESSION_ID"
     git push origin HEAD:refs/heads/$STEWARD_BRANCH
   fi

   If PR finalization fails, update $SESSION_STATE_ROOT/state.json as blocked
   with the finalizer error and do not report the session as ready. A successful
   implementation session must end with a PR URL recorded in
   state.pull_request.pr_url. After recording the PR, run the readiness
   validator with both --require-ready and --require-pr; do not report
   task_completed unless it passes.

Start the implementation steward playbook. Coordinate specialist implementers
and reviewers, keep durable state under $SESSION_STATE_ROOT, use implementer
agents for product changes, and finish ready only when $FINAL_BRANCH exists and
is pushed with passing verification, an accepting final-review verdict, and a
pull request for the integration branch.
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
printf 'Agent scion-ops root: %s\n' "$AGENT_SCION_OPS_ROOT"

if [[ "${SCION_OPS_DRY_RUN:-0}" == "1" ]]; then
  cat <<EOF

Dry run command:
  $SCION_BIN --profile "$SCION_PROFILE" --grove "$PROJECT_ROOT" start "$STEWARD_NAME" --type implementation-steward --branch "$STEWARD_BRANCH" --broker "$BROKER" --harness-config codex-exec --harness-auth auth-file --no-upload --non-interactive --yes --notify "<prompt>"

Rendered prompt:
$TASK_PROMPT
EOF
  exit 0
fi

if [[ "${SCION_OPS_PRECREATE_SESSION_BRANCHES:-1}" != "0" ]]; then
  scion_ops_load_github_token_for_branch_precreate
  precreate_session_branches
fi
initialize_steward_state_branch

"$SCION_BIN" --profile "$SCION_PROFILE" --grove "$PROJECT_ROOT" start "$STEWARD_NAME" \
  --type implementation-steward \
  --branch "$STEWARD_BRANCH" \
  --broker "$BROKER" \
  --harness-config codex-exec \
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
printf '  task steward:validate -- --project-root %q --session-id %q --kind implementation --change %q --branch %q --require-ready --require-pr\n' "$PROJECT_ROOT" "$SESSION_ID" "$CHANGE" "$FINAL_BRANCH"
