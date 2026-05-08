#!/usr/bin/env bash
# Show the local container storage state used by kind and image builds.
set -euo pipefail

warn() {
  printf '\033[33m%s\033[0m\n' "$*"
}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not on PATH"
  exit 1
fi

driver="$(docker info --format '{{.Driver}}' 2>/dev/null || true)"
graph_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"

printf 'Docker storage\n'
printf '  driver:   %s\n' "${driver:-unknown}"
printf '  root:     %s\n\n' "${graph_root:-unknown}"

if [[ "$driver" == "vfs" ]]; then
  warn "Warning: vfs copies layers instead of sharing them efficiently."
  warn "         Full Scion image rebuilds can consume hundreds of GiB."
  warn "         Docker should use overlay2 storage for normal work."
  warn "         Prefer task dev:* or targeted task build:* commands for iteration."
  printf '\n'
fi

if [[ -n "$graph_root" && -d "$graph_root" ]]; then
  df -h "$graph_root"
  physical_usage="$( { du -sh "$graph_root" 2>/dev/null || true; } | awk 'NR == 1 {print $1}')"
  if [[ -n "$physical_usage" ]]; then
    printf 'Physical graph usage: %s\n' "$physical_usage"
  fi
  printf '\n'
fi

docker system df

printf '\nLargest scion images\n'
docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}' |
  awk 'NR == 1 || /localhost\/(core-base|scion-)/'
