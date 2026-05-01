# shellcheck shell=bash
# Scion CLI helpers. Sourced by round.sh.

# Spawn an agent detached. Args: agent-name template-name branch-name task...
scion_spawn() {
  local name="$1" template="$2" branch="$3"; shift 3
  scion start "$name" \
    --type "$template" \
    --branch "$branch" \
    --non-interactive \
    --yes \
    "$@"
}

# Get the status of a single agent (running|completed|errored|stopped|missing).
scion_status() {
  local name="$1"
  scion list --format json 2>/dev/null \
    | jq -r --arg n "$name" '.[] | select(.name==$n) | .status // "unknown"' \
    | head -1
}

# Resolve the host-side path to an agent's /workspace.
# Try `scion cdw --print`, fall back to known layouts.
scion_workspace_path() {
  local name="$1"
  # First try the CLI
  local p
  p=$(scion cdw "$name" --print 2>/dev/null) || true
  if [[ -n "$p" && -d "$p" ]]; then echo "$p"; return 0; fi
  # Hub layout
  if [[ -d "$HOME/.scion/agents/$name/workspace" ]]; then
    echo "$HOME/.scion/agents/$name/workspace"; return 0
  fi
  # Solo / git-worktree layout
  local grove_basename; grove_basename="$(basename "$PWD")"
  if [[ -d "../.scion_worktrees/$grove_basename/$name" ]]; then
    (cd "../.scion_worktrees/$grove_basename/$name" && pwd); return 0
  fi
  return 1
}

# Wait for a named agent to reach a terminal state. Returns the status.
# Args: agent-name [timeout-seconds]
scion_wait_for() {
  local name="$1" timeout="${2:-1800}"
  local start=$SECONDS
  while [[ $((SECONDS - start)) -lt $timeout ]]; do
    local s; s=$(scion_status "$name")
    case "$s" in
      completed|stopped|errored) echo "$s"; return 0 ;;
      ""|unknown|missing)        echo "missing"; return 1 ;;
    esac
    sleep 10
  done
  echo "timeout"; return 2
}

# Send a follow-up message to an agent (e.g. review feedback).
scion_message() {
  local name="$1" msg="$2"
  scion message "$name" "$msg"
}

# Read verdict.json from an agent's workspace and emit it on stdout.
# Returns nonzero if missing or malformed.
scion_read_verdict() {
  local name="$1"
  local ws; ws=$(scion_workspace_path "$name") || { echo "{}"; return 1; }
  local f="$ws/verdict.json"
  [[ -f "$f" ]] || { echo "{}"; return 1; }
  jq -e . "$f" 2>/dev/null || { echo "{}"; return 1; }
}
