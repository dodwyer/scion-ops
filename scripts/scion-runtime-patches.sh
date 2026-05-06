#!/usr/bin/env bash
# Apply or verify the Scion runtime patches required by scion-ops.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCION_SRC="${SCION_SRC:-${HOME}/workspace/github/GoogleCloudPlatform/scion}"
PATCH_DIR="${SCION_OPS_SCION_PATCH_DIR:-$REPO_ROOT/patches/scion}"
COMMAND="${1:-status}"

if [[ "$COMMAND" == "-h" || "$COMMAND" == "--help" ]]; then
  COMMAND="help"
else
  shift || true
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src)
      SCION_SRC="$2"
      shift 2
      ;;
    --patch-dir)
      PATCH_DIR="$2"
      shift 2
      ;;
    -h|--help)
      COMMAND="help"
      shift
      ;;
    *)
      printf 'unknown option: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

usage() {
  cat <<EOF
Usage: $(basename "$0") <status|check|apply|ensure> [--src PATH] [--patch-dir PATH]

Commands:
  status   Print whether each scion-ops patch is applied, pending, or blocked.
  check    Exit successfully only when every patch is already applied.
  apply    Apply pending patches and leave already-applied patches unchanged.
  ensure   Alias for apply; used by build entry points.

Environment:
  SCION_SRC                 Scion source checkout
                            (default: ${SCION_SRC})
  SCION_OPS_SCION_PATCH_DIR Patch directory
                            (default: ${PATCH_DIR})
EOF
}

log() {
  printf '\033[36m==> %s\033[0m\n' "$*"
}

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

require_source() {
  command -v git >/dev/null 2>&1 || die "git is required on PATH"
  [[ -d "$SCION_SRC/.git" ]] || die "SCION_SRC is not a git checkout: $SCION_SRC"
  [[ -f "$SCION_SRC/go.mod" ]] || die "SCION_SRC is not the Scion Go module: $SCION_SRC"
}

load_patches() {
  shopt -s nullglob
  PATCHES=("$PATCH_DIR"/*.patch)
  shopt -u nullglob
  [[ "${#PATCHES[@]}" -gt 0 ]] || die "no Scion patches found in $PATCH_DIR"
}

patch_state() {
  local patch="$1"
  if git -C "$SCION_SRC" apply --reverse --check "$patch" >/dev/null 2>&1; then
    printf 'applied'
    return 0
  fi
  if git -C "$SCION_SRC" apply --check "$patch" >/dev/null 2>&1; then
    printf 'pending'
    return 0
  fi
  printf 'blocked'
  return 1
}

run_status() {
  local patch state failed=0
  for patch in "${PATCHES[@]}"; do
    state="$(patch_state "$patch")" || failed=1
    printf '%-8s %s\n' "$state" "$(basename "$patch")"
  done
  return "$failed"
}

run_check() {
  local patch state failed=0
  for patch in "${PATCHES[@]}"; do
    state="$(patch_state "$patch")" || state="blocked"
    case "$state" in
      applied)
        printf 'applied %s\n' "$(basename "$patch")"
        ;;
      pending)
        printf 'pending %s; run task scion:patch:apply or let task build apply it\n' "$(basename "$patch")" >&2
        failed=1
        ;;
      *)
        printf 'blocked %s; patch does not apply cleanly to %s\n' "$(basename "$patch")" "$SCION_SRC" >&2
        git -C "$SCION_SRC" apply --check "$patch" >&2 || true
        failed=1
        ;;
    esac
  done
  return "$failed"
}

run_apply() {
  local patch state
  for patch in "${PATCHES[@]}"; do
    state="$(patch_state "$patch")" || state="blocked"
    case "$state" in
      applied)
        printf 'already applied %s\n' "$(basename "$patch")"
        ;;
      pending)
        log "apply $(basename "$patch")"
        git -C "$SCION_SRC" apply "$patch"
        ;;
      *)
        printf 'blocked %s; patch does not apply cleanly to %s\n' "$(basename "$patch")" "$SCION_SRC" >&2
        git -C "$SCION_SRC" apply --check "$patch" >&2 || true
        exit 1
        ;;
    esac
  done
}

case "$COMMAND" in
  help)
    usage
    exit 0
    ;;
  status|check|apply|ensure)
    require_source
    load_patches
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac

case "$COMMAND" in
  status) run_status ;;
  check) run_check ;;
  apply|ensure) run_apply ;;
esac
