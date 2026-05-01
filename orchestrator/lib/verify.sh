#!/usr/bin/env bash
# Generic test/static-analysis gate. Run inside an agent's workspace (CWD).
# Detects language by manifest files; runs the project's own test command.
# Exit 0 on green; non-zero on any failure.
set -eo pipefail

run() { echo "+ $*"; "$@"; }

if [[ -f Taskfile.yml ]] && grep -qE '^\s+test:' Taskfile.yml; then
  run task test
elif [[ -f package.json ]]; then
  if jq -e '.scripts.test' package.json >/dev/null 2>&1; then
    run npm test --silent
  else
    echo "no test script in package.json — passing trivially"
  fi
elif [[ -f go.mod ]]; then
  run go test ./...
elif [[ -f pyproject.toml ]]; then
  if command -v uv >/dev/null;        then run uv run pytest -q
  elif command -v poetry >/dev/null;   then run poetry run pytest -q
  else                                       run python -m pytest -q
  fi
elif [[ -f Cargo.toml ]]; then
  run cargo test --quiet
else
  echo "no recognised manifest — verify is a no-op"
  exit 0
fi
