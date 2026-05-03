#!/usr/bin/env bash
# Stop and delete every agent in the current grove (optionally filtered to a round).
#   bash orchestrator/abort.sh             # everything in this grove
#   bash orchestrator/abort.sh <round_id>  # only agents whose name contains this
set -eo pipefail

ROUND_FILTER="${1:-}"
SCION_BIN="${SCION_BIN:-scion}"

names=$("$SCION_BIN" list --format json 2>/dev/null \
  | sed -n '/^\[/,/^\]/p' \
  | jq -r --arg f "$ROUND_FILTER" '.[] | select($f == "" or (.name | contains($f))) | .name' \
  || true)

if [[ -z "$names" ]]; then
  echo "no agents matching '${ROUND_FILTER:-*}'"
  exit 0
fi

while IFS= read -r n; do
  [[ -n "$n" ]] || continue
  echo "stopping  $n"
  "$SCION_BIN" stop   "$n" --non-interactive --yes 2>/dev/null | tail -1 || true
done <<<"$names"

sleep 2

while IFS= read -r n; do
  [[ -n "$n" ]] || continue
  echo "deleting  $n"
  "$SCION_BIN" delete "$n" --non-interactive --yes 2>/dev/null | tail -1 || true
done <<<"$names"

echo "done."
