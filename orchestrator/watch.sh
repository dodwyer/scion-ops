#!/usr/bin/env bash
# Live status board for an in-flight Scion steward session.
# Refreshes every INTERVAL seconds. Stop with Ctrl-C.
#
#   bash orchestrator/watch.sh                 # all agents in current grove
#   bash orchestrator/watch.sh <round_id>      # filter to one round
#   INTERVAL=10 bash orchestrator/watch.sh
set -eo pipefail

ROUND_FILTER="${1:-}"
INTERVAL="${INTERVAL:-5}"

SCION_BIN="${SCION_BIN:-scion}"
command -v "$SCION_BIN" >/dev/null || { echo "scion not on PATH" >&2; exit 1; }
command -v jq >/dev/null         || { echo "jq not on PATH" >&2; exit 1; }

while true; do
  clear
  printf '== scion session watch  ==  %s  ==  refresh %ss\n' "$(date +%H:%M:%S)" "$INTERVAL"
  printf '   filter: %s\n\n' "${ROUND_FILTER:-(none)}"

  agents_json=$("$SCION_BIN" list --format json 2>/dev/null \
    | sed -n '/^\[/,/^\]/p' \
    | jq -c "[ .[] | select(${ROUND_FILTER:+.name | contains(\"$ROUND_FILTER\")}${ROUND_FILTER:-true}) ]" 2>/dev/null \
    || echo '[]')

  if [[ "$agents_json" == "[]" ]]; then
    printf '   no agents.\n'
  else
    printf '%-58s %-10s %-12s %s\n' "AGENT" "PHASE" "HARNESS" "STATUS"
    printf '%-58s %-10s %-12s %s\n' "-----" "-----" "-------" "------"
    jq -r '.[] | [.name, .phase, .harnessConfig // "-", .containerStatus // "-"] | @tsv' <<<"$agents_json" \
      | while IFS=$'\t' read -r name phase harness status; do
          printf '%-58s %-10s %-12s %s\n' "${name:0:58}" "$phase" "$harness" "$status"
        done
  fi

  printf '\n-- recent steward / coordinator output --\n'
  runner=$(jq -r '.[] | select((.name | contains("steward")) or (.name | contains("consensus"))) | .name' <<<"$agents_json" | head -1)
  if [[ -n "$runner" ]]; then
    "$SCION_BIN" look "$runner" 2>/dev/null \
      | sed 's/\x1b\[[0-9;]*m//g' \
      | tail -10
  else
    echo "  (no steward active)"
  fi

  printf '\n-- workspace artefacts --\n'
  for d in /tmp/scion-sandbox/.scion/agents/*/workspace \
           "$PWD/.scion/agents"/*/workspace; do
    [[ -d "$d" ]] || continue
    [[ -n "$ROUND_FILTER" ]] && [[ "$d" != *"$ROUND_FILTER"* ]] && continue
    agent=$(basename "$(dirname "$d")")
    flags=""
    [[ -f "$d/.scion-done"  ]] && flags+="DONE "
    [[ -f "$d/verdict.json" ]] && flags+="VERDICT "
    [[ -n "$flags" ]] && printf '  %-50s %s\n' "$agent" "$flags"
  done | head -20

  sleep "$INTERVAL"
done
