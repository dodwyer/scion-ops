#!/usr/bin/env bash
# Dueling-agents consensus round runner.
#
# Usage:  round.sh "<task prompt>"
#
# Produces:
#   - Two implementer branches: round-<id>-impl-claude, round-<id>-impl-codex
#   - Up to MAX_ROUNDS review iterations, each producing two verdict.json files
#   - One integrated branch: round-<id>-integration  (winner-of-impl branch + agreed feedback)
#   - One final-review verdict
#   - Audit trail at scion-ops/state/<id>.json
set -eo pipefail

# ---- Inputs & locations ---------------------------------------------------
PROMPT="${1:?Usage: $(basename "$0") \"<task prompt>\"}"

SCION_OPS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$SCION_OPS_ROOT/orchestrator/lib"
# shellcheck source=lib/state.sh
source "$LIB/state.sh"
# shellcheck source=lib/scion-helpers.sh
source "$LIB/scion-helpers.sh"

ROUND_ID="$(date +%Y%m%dT%H%M%S)-$(printf '%04x' $RANDOM)"
STATE_DIR="$SCION_OPS_ROOT/state"; mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/$ROUND_ID.json"

MAX_ROUNDS="${MAX_ROUNDS:-3}"
IMPL_TIMEOUT="${IMPL_TIMEOUT:-1800}"   # 30 min
REVIEW_TIMEOUT="${REVIEW_TIMEOUT:-900}" # 15 min

CLAUDE_IMPL="round-${ROUND_ID}-impl-claude"
CODEX_IMPL="round-${ROUND_ID}-impl-codex"
INTEGRATION_BRANCH="round-${ROUND_ID}-integration"

log() { printf '\033[36m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*" >&2; }
die() { printf '\033[31m[%s] %s\033[0m\n' "$(date +%H:%M:%S)" "$*" >&2; state_set_status "$STATE_FILE" "error"; exit 1; }

# ---- Preflight ------------------------------------------------------------
command -v scion >/dev/null || die "scion not on PATH"
command -v jq    >/dev/null || die "jq not on PATH"

state_init "$STATE_FILE" "$ROUND_ID" "$PROMPT"
log "round_id=$ROUND_ID  state_file=$STATE_FILE"

# ---- Phase A: spawn implementers in parallel -----------------------------
log "spawn $CLAUDE_IMPL + $CODEX_IMPL"
scion_spawn "$CLAUDE_IMPL" impl-claude "$CLAUDE_IMPL" "$PROMPT" >/dev/null &
scion_spawn "$CODEX_IMPL"  impl-codex  "$CODEX_IMPL"  "$PROMPT" >/dev/null &
wait

CL_STATUS=$(scion_wait_for "$CLAUDE_IMPL" "$IMPL_TIMEOUT" || true)
CO_STATUS=$(scion_wait_for "$CODEX_IMPL"  "$IMPL_TIMEOUT" || true)
state_record_impl "$STATE_FILE" claude "$CL_STATUS" "$CLAUDE_IMPL"
state_record_impl "$STATE_FILE" codex  "$CO_STATUS" "$CODEX_IMPL"
log "impl status: claude=$CL_STATUS codex=$CO_STATUS"

[[ "$CL_STATUS" == "completed" && "$CO_STATUS" == "completed" ]] || die "implementer(s) did not complete cleanly"

# ---- Phase B: review loop -------------------------------------------------
final_round_json="{}"
consensus="false"

for r in $(seq 1 "$MAX_ROUNDS"); do
  log "review round $r/$MAX_ROUNDS"
  RC_NAME="round-${ROUND_ID}-rev-claude-r${r}"
  RX_NAME="round-${ROUND_ID}-rev-codex-r${r}"

  # claude reviews codex's branch; codex reviews claude's branch.
  scion_spawn "$RC_NAME" reviewer-claude "$CODEX_IMPL"  "Review branch $CODEX_IMPL against base 'main'. Original task: $PROMPT" >/dev/null &
  scion_spawn "$RX_NAME" reviewer-codex  "$CLAUDE_IMPL" "Review branch $CLAUDE_IMPL against base 'main'. Original task: $PROMPT" >/dev/null &
  wait

  RC_STATUS=$(scion_wait_for "$RC_NAME" "$REVIEW_TIMEOUT" || true)
  RX_STATUS=$(scion_wait_for "$RX_NAME" "$REVIEW_TIMEOUT" || true)

  RC_VERDICT=$(scion_read_verdict "$RC_NAME" || echo '{}')
  RX_VERDICT=$(scion_read_verdict "$RX_NAME" || echo '{}')

  round_json=$(jq -n \
    --arg n "$r" \
    --arg cs "$RC_STATUS" --argjson cv "$RC_VERDICT" \
    --arg xs "$RX_STATUS" --argjson xv "$RX_VERDICT" \
    '{round: ($n|tonumber), reviewer_claude: {status: $cs, verdict: $cv}, reviewer_codex: {status: $xs, verdict: $xv}}')
  state_append_round "$STATE_FILE" "$round_json"
  final_round_json="$round_json"

  CL_CORR=$(jq -r '.reviewer_claude.verdict.scores.correctness // 0' <<<"$round_json")
  CX_CORR=$(jq -r '.reviewer_codex.verdict.scores.correctness  // 0' <<<"$round_json")
  log "  scores: claude_on_codex=$CL_CORR  codex_on_claude=$CX_CORR"

  if [[ "$CL_CORR" -ge 4 && "$CX_CORR" -ge 4 ]]; then
    log "  consensus reached"
    consensus="true"
    break
  fi

  # Feed blocking issues back to the original implementers for another swing.
  CL_ISSUES=$(jq -r '.reviewer_codex.verdict.blocking_issues // [] | map("- " + .) | join("\n")' <<<"$round_json")
  CX_ISSUES=$(jq -r '.reviewer_claude.verdict.blocking_issues // [] | map("- " + .) | join("\n")' <<<"$round_json")

  if [[ -n "$CL_ISSUES" ]]; then
    scion_message "$CLAUDE_IMPL" "Reviewer raised blocking issues. Address them and re-run tests:\n$CL_ISSUES"
    scion_wait_for "$CLAUDE_IMPL" "$IMPL_TIMEOUT" >/dev/null || true
  fi
  if [[ -n "$CX_ISSUES" ]]; then
    scion_message "$CODEX_IMPL"  "Reviewer raised blocking issues. Address them and re-run tests:\n$CX_ISSUES"
    scion_wait_for "$CODEX_IMPL" "$IMPL_TIMEOUT" >/dev/null || true
  fi
done

if [[ "$consensus" != "true" ]]; then
  log "no consensus after $MAX_ROUNDS rounds — escalating"
  state_set_status "$STATE_FILE" "escalate"
  exit 2
fi

# ---- Phase C: pick winner & integrate ------------------------------------
# Highest sum of (correctness + completeness) on the FINAL round.
CL_SUM=$(jq -r '.reviewer_codex.verdict.scores | (.correctness // 0) + (.completeness // 0)' <<<"$final_round_json")
CX_SUM=$(jq -r '.reviewer_claude.verdict.scores | (.correctness // 0) + (.completeness // 0)' <<<"$final_round_json")
log "winner sums: claude_impl=$CL_SUM  codex_impl=$CX_SUM"

if   [[ "$CL_SUM" -gt "$CX_SUM" ]]; then WINNER=claude
elif [[ "$CX_SUM" -gt "$CL_SUM" ]]; then WINNER=codex
else
  # Tie-break: prefer a passing test gate; fall back to claude.
  log "tie — running test gate to break"
  if (cd "$(scion_workspace_path "$CLAUDE_IMPL")" && bash "$LIB/verify.sh" >/dev/null 2>&1); then
    WINNER=claude
  elif (cd "$(scion_workspace_path "$CODEX_IMPL")" && bash "$LIB/verify.sh" >/dev/null 2>&1); then
    WINNER=codex
  else
    WINNER=claude
  fi
fi
log "winner: $WINNER"

INT_NAME="round-${ROUND_ID}-integrator"
INT_TEMPLATE="impl-${WINNER}"
WINNER_BRANCH=$([[ "$WINNER" == "claude" ]] && echo "$CLAUDE_IMPL" || echo "$CODEX_IMPL")
LOSER_BRANCH=$([[ "$WINNER" == "claude" ]] && echo "$CODEX_IMPL"  || echo "$CLAUDE_IMPL")

INT_PROMPT="You are the integrator. Both peer drafts have been reviewed and scored.

Your branch starts from '$WINNER_BRANCH'. Read the loser's branch '$LOSER_BRANCH' for any insights worth merging in. Apply the accumulated reviewer feedback (see below). Produce a single coherent diff on this integration branch.

Reviewer feedback to address (final round):
$(jq -r '
  [
    (.reviewer_claude.verdict.nits             // [] | map("- nit: " + .)),
    (.reviewer_claude.verdict.blocking_issues  // [] | map("- BLOCKING: " + .)),
    (.reviewer_codex.verdict.nits              // [] | map("- nit: " + .)),
    (.reviewer_codex.verdict.blocking_issues   // [] | map("- BLOCKING: " + .))
  ] | flatten | join("\n")
' <<<"$final_round_json")

Tests must pass before you signal completion."

scion_spawn "$INT_NAME" "$INT_TEMPLATE" "$INTEGRATION_BRANCH" "$INT_PROMPT" >/dev/null
INT_STATUS=$(scion_wait_for "$INT_NAME" "$IMPL_TIMEOUT" || true)
state_set_integration "$STATE_FILE" "$WINNER" "$INTEGRATION_BRANCH" "$INT_STATUS"
log "integration: status=$INT_STATUS"
[[ "$INT_STATUS" == "completed" ]] || die "integrator did not complete"

# ---- Phase D: final review ------------------------------------------------
FINAL_NAME="round-${ROUND_ID}-final-review"
scion_spawn "$FINAL_NAME" final-reviewer-codex "$INTEGRATION_BRANCH" \
  "Final smoke-test review of the integrated branch '$INTEGRATION_BRANCH'. Original task: $PROMPT" >/dev/null
FINAL_STATUS=$(scion_wait_for "$FINAL_NAME" "$REVIEW_TIMEOUT" || true)
FINAL_VERDICT=$(scion_read_verdict "$FINAL_NAME" || echo '{}')
state_set_final "$STATE_FILE" "$(jq -n --arg s "$FINAL_STATUS" --argjson v "$FINAL_VERDICT" '{status: $s, verdict: $v}')"

FINAL_RESULT=$(jq -r '.verdict // "unknown"' <<<"$FINAL_VERDICT")
log "final review verdict: $FINAL_RESULT"

if [[ "$FINAL_STATUS" == "completed" && "$FINAL_RESULT" == "accept" ]]; then
  state_set_status "$STATE_FILE" "success"
  log "✓ round complete — branch: $INTEGRATION_BRANCH"
  exit 0
else
  state_set_status "$STATE_FILE" "final_blocked"
  log "✗ final review blocked. See $STATE_FILE"
  exit 3
fi
