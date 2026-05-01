# shellcheck shell=bash
# State-file helpers. Sourced by round.sh.

state_init() {
  local file="$1" round_id="$2" prompt="$3"
  jq -n --arg id "$round_id" --arg p "$prompt" '{
    round_id: $id,
    prompt: $p,
    started_at: (now | todate),
    rounds: [],
    impl: {},
    integration: null,
    final_review: null,
    status: "running"
  }' > "$file"
}

state_merge() {
  local file="$1" jq_filter="$2"; shift 2
  local tmp; tmp=$(mktemp)
  jq "$@" "$jq_filter" "$file" > "$tmp" && mv "$tmp" "$file"
}

state_set_status() {
  local file="$1" status="$2"
  state_merge "$file" --arg s "$status" '.status = $s | .ended_at = (now | todate)'
}

state_record_impl() {
  local file="$1" agent="$2" status="$3" branch="$4"
  state_merge "$file" \
    --arg a "$agent" --arg s "$status" --arg b "$branch" \
    '.impl[$a] = {status: $s, branch: $b}'
}

state_append_round() {
  local file="$1" round_json="$2"
  state_merge "$file" --argjson r "$round_json" '.rounds += [$r]'
}

state_set_integration() {
  local file="$1" winner="$2" branch="$3" status="$4"
  state_merge "$file" \
    --arg w "$winner" --arg b "$branch" --arg s "$status" \
    '.integration = {winner: $w, branch: $b, status: $s}'
}

state_set_final() {
  local file="$1" verdict_json="$2"
  state_merge "$file" --argjson v "$verdict_json" '.final_review = $v'
}
