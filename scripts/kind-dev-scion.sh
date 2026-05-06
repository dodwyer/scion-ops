#!/usr/bin/env bash
# Fast Scion binary iteration for the kind-hosted Hub/Broker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCION_SRC="${SCION_SRC:-${HOME}/workspace/github/GoogleCloudPlatform/scion}"
BIN_DIR="${SCION_DEV_BIN_DIR:-${SCION_SRC}/.scion-dev/bin}"
KIND_CONTEXT="${KIND_CONTEXT:-kind-${KIND_CLUSTER_NAME:-scion-ops}}"
NAMESPACE="${SCION_K8S_NAMESPACE:-scion-agents}"
DEV_BIN_TARGET="/home/scion/.scion/dev-bin"

log() {
  printf '\033[36m==> %s\033[0m\n' "$*"
}

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <build|deploy|status|clear>

Commands:
  build    Build scion and sciontool into ${BIN_DIR}
  deploy   Build, copy binaries into the Hub PVC dev-bin path, and restart Hub
  status   Show whether Hub is using dev binaries
  clear    Remove dev binaries from the Hub PVC and restart Hub

Environment:
  SCION_SRC          Upstream Scion source checkout
                     (default: ${SCION_SRC})
  SCION_DEV_BIN_DIR  Local output directory
                     (default: ${BIN_DIR})
  KIND_CONTEXT       Kubernetes context
                     (default: ${KIND_CONTEXT})
  SCION_K8S_NAMESPACE Namespace
                     (default: ${NAMESPACE})
EOF
}

require() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required on PATH"
}

hub_pod() {
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" get pod \
    -l app.kubernetes.io/name=scion-hub,app.kubernetes.io/component=hub \
    -o jsonpath='{.items[0].metadata.name}'
}

cmd_build() {
  require go
  [[ -d "$SCION_SRC" ]] || die "SCION_SRC does not exist: $SCION_SRC"
  [[ -f "$SCION_SRC/go.mod" ]] || die "SCION_SRC is not a Go module: $SCION_SRC"

  log "build Scion binaries from $SCION_SRC"
  mkdir -p "$BIN_DIR"
  (
    cd "$SCION_SRC"
    go build -buildvcs=false -tags no_embed_web -o "$BIN_DIR/scion" ./cmd/scion/
    go build -buildvcs=false -tags no_embed_web -o "$BIN_DIR/sciontool" ./cmd/sciontool/
  )
  chmod +x "$BIN_DIR/scion" "$BIN_DIR/sciontool"
  ls -lh "$BIN_DIR/scion" "$BIN_DIR/sciontool"
}

cmd_deploy() {
  require kubectl
  cmd_build

  local pod
  pod="$(hub_pod)"
  [[ -n "$pod" ]] || die "scion-hub pod not found in $KIND_CONTEXT/$NAMESPACE"

  log "copy dev binaries into Hub PVC"
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" exec "$pod" -c hub -- mkdir -p "$DEV_BIN_TARGET"
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" cp "$BIN_DIR/scion" "$pod:${DEV_BIN_TARGET}/scion" -c hub
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" cp "$BIN_DIR/sciontool" "$pod:${DEV_BIN_TARGET}/sciontool" -c hub
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" exec "$pod" -c hub -- chmod +x "${DEV_BIN_TARGET}/scion" "${DEV_BIN_TARGET}/sciontool"

  log "restart Hub to run dev scion binary"
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" rollout restart deploy/scion-hub
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" rollout status deploy/scion-hub --timeout=120s
}

cmd_status() {
  require kubectl
  local pod
  pod="$(hub_pod)"
  [[ -n "$pod" ]] || die "scion-hub pod not found in $KIND_CONTEXT/$NAMESPACE"

  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" exec "$pod" -c hub -- sh -lc "
    set -e
    printf 'dev-bin: %s\n' '${DEV_BIN_TARGET}'
    ls -lh '${DEV_BIN_TARGET}' 2>/dev/null || true
    printf '\nselected scion: '
    if [ -x '${DEV_BIN_TARGET}/scion' ]; then
      printf '%s\n' '${DEV_BIN_TARGET}/scion'
    else
      command -v scion
    fi
  "
}

cmd_clear() {
  require kubectl
  local pod
  pod="$(hub_pod)"
  [[ -n "$pod" ]] || die "scion-hub pod not found in $KIND_CONTEXT/$NAMESPACE"

  log "remove dev binaries from Hub PVC"
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" exec "$pod" -c hub -- rm -f "${DEV_BIN_TARGET}/scion" "${DEV_BIN_TARGET}/sciontool"
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" rollout restart deploy/scion-hub
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" rollout status deploy/scion-hub --timeout=120s
}

case "${1:-}" in
  build)
    cmd_build
    ;;
  deploy)
    cmd_deploy
    ;;
  status)
    cmd_status
    ;;
  clear)
    cmd_clear
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
