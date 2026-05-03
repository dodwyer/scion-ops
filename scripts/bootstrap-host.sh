#!/usr/bin/env bash
# Preflight check for scion-ops host. Verifies tooling, paths, auth.
set -euo pipefail

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

fail=0
require() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    green "  ok  $label"
  else
    red   "  FAIL $label"
    fail=1
  fi
}

echo "scion-ops bootstrap preflight"

# Go >= 1.23
if command -v go >/dev/null 2>&1; then
  ver=$(go env GOVERSION | sed 's/go//')
  major=${ver%%.*}; rest=${ver#*.}; minor=${rest%%.*}
  if [[ "$major" -gt 1 || ( "$major" -eq 1 && "$minor" -ge 23 ) ]]; then
    green "  ok  go $ver"
  else
    red   "  FAIL go >= 1.23 required, found $ver"; fail=1
  fi
else
  red "  FAIL go not on PATH"; fail=1
fi

# Podman >= 4
if command -v podman >/dev/null 2>&1; then
  pver=$(podman --version | awk '{print $3}')
  pmajor=${pver%%.*}
  if [[ "$pmajor" -ge 4 ]]; then
    green "  ok  podman $pver"
  else
    red   "  FAIL podman >= 4 required, found $pver"; fail=1
  fi
  # rootless check
  if podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null | grep -q true; then
    green "  ok  podman rootless"
  else
    yellow "  warn podman not rootless — Scion will still work but auth mounts are looser"
  fi
else
  red "  FAIL podman not installed"; fail=1
fi

require "tmux"        command -v tmux
require "git"         command -v git
require "claude CLI"  command -v claude
require "codex CLI"   command -v codex
require "gemini CLI"  bash -lc 'command -v gemini >/dev/null 2>&1 || test -x "$HOME/.npm-global/bin/gemini"'
require "task"        command -v task

# GOPATH/bin must be on PATH so `scion` is findable after install
gobin="$(go env GOPATH 2>/dev/null)/bin"
case ":$PATH:" in
  *":$gobin:"*) green "  ok  $gobin on PATH" ;;
  *) yellow "  warn $gobin not on PATH — add to shell rc:  export PATH=\"$gobin:\$PATH\"" ;;
esac

# Auth presence (don't print values). Prefer subscription credential files so
# agents can run through Claude Code / Codex subscriptions rather than API keys.
if [[ -f "$HOME/.claude/.credentials.json" ]]; then
  green "  ok  ~/.claude/.credentials.json present"
elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  yellow "  warn using ANTHROPIC_API_KEY; subscription agents need ~/.claude/.credentials.json"
else
  red   "  FAIL ~/.claude/.credentials.json missing — run: claude login"; fail=1
fi
if [[ -f "$HOME/.codex/auth.json" ]]; then
  green "  ok  ~/.codex/auth.json present"
else
  red   "  FAIL ~/.codex/auth.json missing — run: codex login"; fail=1
fi
if [[ -f "$HOME/.gemini/oauth_creds.json" ]]; then
  green "  ok  ~/.gemini/oauth_creds.json present"
else
  red   "  FAIL ~/.gemini/oauth_creds.json missing - run: gemini"; fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  red "preflight FAILED"
  exit 1
fi
green "preflight OK"
