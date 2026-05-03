#!/usr/bin/env bash
# Manage the local kind cluster used for Scion Kubernetes runtime testing.
set -euo pipefail

CLUSTER_NAME="${KIND_CLUSTER_NAME:-scion-ops}"
NAMESPACE="${SCION_K8S_NAMESPACE:-scion-agents}"
SERVICE_ACCOUNT="${SCION_K8S_SERVICE_ACCOUNT:-scion-agent-manager}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST_DIR="${SCION_K8S_MANIFEST_DIR:-${REPO_ROOT}/deploy/kind}"
CONTEXT="kind-${CLUSTER_NAME}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  up                  Create/reuse the kind cluster and apply deploy/kind.
  down                Delete the kind cluster.
  status              Show cluster, namespace, RBAC, and node status.
  load-images IMAGE   Load one or more local images into the kind nodes.
  load-archive FILE   Load one or more image archives into the kind nodes.
  configure-scion     Configure global Scion profile "kind" for this cluster.

Environment:
  KIND_CLUSTER_NAME          Cluster name (default: scion-ops)
  SCION_K8S_MANIFEST_DIR     Kustomize manifest directory (default: deploy/kind)
  SCION_K8S_NAMESPACE        Agent namespace (default: scion-agents)
  SCION_K8S_SERVICE_ACCOUNT  Runtime service account (default: scion-agent-manager)
EOF
}

die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}

log() {
  printf '\033[36m==> %s\033[0m\n' "$*"
}

require() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required on PATH"
}

cluster_exists() {
  kind get clusters 2>/dev/null | grep -Fxq "$CLUSTER_NAME"
}

kubectl_ctx() {
  kubectl --context "$CONTEXT" "$@"
}

ensure_cluster() {
  require kind
  if cluster_exists; then
    log "reuse kind cluster $CLUSTER_NAME"
    return
  fi

  log "create kind cluster $CLUSTER_NAME"
  kind create cluster --name "$CLUSTER_NAME"
}

apply_manifests() {
  require kubectl
  [[ -d "$MANIFEST_DIR" ]] || die "manifest directory not found: $MANIFEST_DIR"
  log "apply Kubernetes resources from $MANIFEST_DIR"
  kubectl_ctx apply -k "$MANIFEST_DIR"
  if ! kubectl_ctx get namespace "$NAMESPACE" >/dev/null 2>&1; then
    die "namespace $NAMESPACE was not created by $MANIFEST_DIR; set SCION_K8S_NAMESPACE to match the applied manifests"
  fi
  # Make ad-hoc kubectl commands predictable after setup.
  kubectl config set-context "$CONTEXT" --namespace "$NAMESPACE" >/dev/null
}

cmd_up() {
  ensure_cluster
  apply_manifests

  cat <<EOF

kind cluster ready
  cluster:   ${CLUSTER_NAME}
  context:   ${CONTEXT}
  namespace: ${NAMESPACE}
  manifests: ${MANIFEST_DIR}

Next:
  task kind:configure-scion
  task kind:doctor
EOF
}

cmd_down() {
  require kind
  if cluster_exists; then
    log "delete kind cluster $CLUSTER_NAME"
    kind delete cluster --name "$CLUSTER_NAME"
  else
    log "cluster $CLUSTER_NAME does not exist"
  fi
}

cmd_status() {
  require kind
  require kubectl

  printf 'cluster:   %s\n' "$CLUSTER_NAME"
  printf 'context:   %s\n' "$CONTEXT"
  printf 'namespace: %s\n\n' "$NAMESPACE"

  if ! cluster_exists; then
    die "kind cluster $CLUSTER_NAME does not exist"
  fi

  kubectl_ctx get nodes -o wide
  printf '\n'
  kubectl_ctx get namespace "$NAMESPACE"
  printf '\n'
  kubectl_ctx get serviceaccount,role,rolebinding -n "$NAMESPACE" | grep -E "NAME|${SERVICE_ACCOUNT}|scion-agent-manager"
}

cmd_load_images() {
  require kind
  [[ "$#" -gt 0 ]] || die "provide at least one image tag, e.g. localhost/scion-claude:latest"
  cluster_exists || die "kind cluster $CLUSTER_NAME does not exist; run: task kind:up"

  for image in "$@"; do
    log "load image $image into $CLUSTER_NAME"
    kind load docker-image --name "$CLUSTER_NAME" "$image"
  done
}

cmd_load_archive() {
  require kind
  [[ "$#" -gt 0 ]] || die "provide at least one image archive"
  cluster_exists || die "kind cluster $CLUSTER_NAME does not exist; run: task kind:up"

  for archive in "$@"; do
    [[ -f "$archive" ]] || die "image archive not found: $archive"
    log "load image archive $archive into $CLUSTER_NAME"
    kind load image-archive --name "$CLUSTER_NAME" "$archive"
  done
}

cmd_configure_scion() {
  require yq

  local settings_file="${SCION_SETTINGS_FILE:-${HOME}/.scion/settings.yaml}"
  local settings_dir
  settings_dir="$(dirname "$settings_file")"
  mkdir -p "$settings_dir"
  if [[ ! -f "$settings_file" ]]; then
    printf 'schema_version: "1"\n' > "$settings_file"
  fi

  local tmp
  tmp="$(mktemp)"
  KIND_CONTEXT="$CONTEXT" SCION_K8S_NAMESPACE="$NAMESPACE" yq eval '
    .schema_version = (.schema_version // "1") |
    .runtimes.kind.type = "kubernetes" |
    .runtimes.kind.context = strenv(KIND_CONTEXT) |
    .runtimes.kind.namespace = strenv(SCION_K8S_NAMESPACE) |
    .profiles.kind.runtime = "kind"
  ' "$settings_file" > "$tmp"
  mv "$tmp" "$settings_file"

  cat <<EOF
Configured Scion profile:
  file:      ${settings_file}
  profile:   kind
  context:   ${CONTEXT}
  namespace: ${NAMESPACE}
EOF
}

case "${1:-}" in
  up)
    shift
    cmd_up "$@"
    ;;
  down)
    shift
    cmd_down "$@"
    ;;
  status)
    shift
    cmd_status "$@"
    ;;
  load-images)
    shift
    cmd_load_images "$@"
    ;;
  load-archive)
    shift
    cmd_load_archive "$@"
    ;;
  configure-scion)
    shift
    cmd_configure_scion "$@"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    usage >&2
    die "unknown command: $1"
    ;;
esac
