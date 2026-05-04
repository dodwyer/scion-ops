#!/usr/bin/env bash
# Manage the local kind cluster used for Scion Kubernetes runtime testing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-scion-ops}"
NAMESPACE="${SCION_K8S_NAMESPACE:-scion-agents}"
SERVICE_ACCOUNT="${SCION_K8S_SERVICE_ACCOUNT:-scion-agent-manager}"
PROFILE_NAME="${SCION_K8S_PROFILE:-kind}"
RUNTIME_NAME="${SCION_K8S_RUNTIME:-kubernetes}"
IMAGE_REGISTRY="${SCION_IMAGE_REGISTRY:-localhost}"
MANIFEST_DIR="${SCION_K8S_MANIFEST_DIR:-${REPO_ROOT}/deploy/kind}"
WORKSPACE_HOST_PATH="${SCION_OPS_WORKSPACE_HOST_PATH:-$REPO_ROOT}"
WORKSPACE_NODE_PATH="${SCION_OPS_WORKSPACE_NODE_PATH:-/workspace/scion-ops}"
CONTEXT="kind-${CLUSTER_NAME}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  up                  Create/reuse the kind cluster and apply deploy/kind.
  down                Delete the kind cluster.
  status              Show cluster, namespace, RBAC, and node status.
  workspace-status    Verify the kind node can see the scion-ops workspace.
  load-images IMAGE   Load one or more local images into the kind nodes.
  load-archive FILE   Load one or more image archives into the kind nodes.
  configure-scion     Configure global Scion profile "kind" for this cluster.

Environment:
  KIND_CLUSTER_NAME          Cluster name (default: scion-ops)
  SCION_K8S_MANIFEST_DIR     Kustomize manifest directory (default: deploy/kind)
  SCION_K8S_NAMESPACE        Agent namespace (default: scion-agents)
  SCION_K8S_SERVICE_ACCOUNT  Runtime service account (default: scion-agent-manager)
  SCION_K8S_PROFILE          Scion profile name (default: kind)
  SCION_K8S_RUNTIME          Scion runtime name (default: kubernetes)
  SCION_IMAGE_REGISTRY       Agent image registry/prefix (default: localhost)
  SCION_OPS_WORKSPACE_HOST_PATH  Host scion-ops checkout mounted into kind
                                 (default: this repo)
  SCION_OPS_WORKSPACE_NODE_PATH  Node path used by future MCP hostPath mounts
                                 (default: /workspace/scion-ops)
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

ensure_workspace_host_path() {
  [[ "$WORKSPACE_HOST_PATH" = /* ]] || die "SCION_OPS_WORKSPACE_HOST_PATH must be an absolute path: $WORKSPACE_HOST_PATH"
  [[ "$WORKSPACE_NODE_PATH" = /* ]] || die "SCION_OPS_WORKSPACE_NODE_PATH must be an absolute path: $WORKSPACE_NODE_PATH"
  [[ -d "$WORKSPACE_HOST_PATH" ]] || die "workspace host path not found: $WORKSPACE_HOST_PATH"
  [[ -f "${WORKSPACE_HOST_PATH}/Taskfile.yml" ]] || die "workspace host path does not look like scion-ops: $WORKSPACE_HOST_PATH"
}

create_cluster_config() {
  local config
  config="$(mktemp)"
  cat > "$config" <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraMounts:
  - hostPath: ${WORKSPACE_HOST_PATH}
    containerPath: ${WORKSPACE_NODE_PATH}
EOF
  printf '%s\n' "$config"
}

kind_node_name() {
  kind get nodes --name "$CLUSTER_NAME" 2>/dev/null | head -n 1
}

container_runtime_for_node() {
  local node="$1"
  local runtime

  for runtime in docker podman; do
    if command -v "$runtime" >/dev/null 2>&1 && "$runtime" container inspect "$node" >/dev/null 2>&1; then
      printf '%s\n' "$runtime"
      return 0
    fi
  done

  return 1
}

workspace_mount_present() {
  local node
  local runtime

  node="$(kind_node_name)"
  [[ -n "$node" ]] || return 1
  runtime="$(container_runtime_for_node "$node")" || return 1

  "$runtime" exec "$node" test -f "${WORKSPACE_NODE_PATH}/Taskfile.yml" &&
    "$runtime" exec "$node" test -d "${WORKSPACE_NODE_PATH}/.git"
}

warn_missing_workspace_mount() {
  cat >&2 <<EOF
Warning: workspace mount is not available inside kind node ${WORKSPACE_NODE_PATH}.
Existing kind clusters cannot be updated with new extraMounts. Recreate this
cluster with 'task kind:down && task kind:up' before deploying a kind-hosted MCP.
EOF
}

ensure_cluster() {
  require kind
  if cluster_exists; then
    log "reuse kind cluster $CLUSTER_NAME"
    if ! workspace_mount_present; then
      warn_missing_workspace_mount
    fi
    return
  fi

  ensure_workspace_host_path
  log "create kind cluster $CLUSTER_NAME"
  local config
  config="$(create_cluster_config)"
  if ! kind create cluster --name "$CLUSTER_NAME" --config "$config"; then
    rm -f "$config"
    return 1
  fi
  rm -f "$config"
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
  task kind:workspace:status
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
  printf 'namespace: %s\n' "$NAMESPACE"
  printf 'workspace host: %s\n' "$WORKSPACE_HOST_PATH"
  printf 'workspace node: %s\n\n' "$WORKSPACE_NODE_PATH"

  if ! cluster_exists; then
    die "kind cluster $CLUSTER_NAME does not exist"
  fi

  kubectl_ctx get nodes -o wide
  printf '\n'
  kubectl_ctx get namespace "$NAMESPACE"
  printf '\n'
  kubectl_ctx get serviceaccount,role,rolebinding -n "$NAMESPACE" | grep -E "NAME|${SERVICE_ACCOUNT}|scion-agent-manager"
  printf '\n\n'
  if workspace_mount_present; then
    printf 'workspace mount: ok\n'
  else
    printf 'workspace mount: unavailable; run task kind:workspace:status for details\n'
  fi
}

cmd_workspace_status() {
  require kind

  printf 'cluster:        %s\n' "$CLUSTER_NAME"
  printf 'workspace host: %s\n' "$WORKSPACE_HOST_PATH"
  printf 'workspace node: %s\n\n' "$WORKSPACE_NODE_PATH"

  if ! cluster_exists; then
    die "kind cluster $CLUSTER_NAME does not exist; run: task kind:up"
  fi

  if workspace_mount_present; then
    printf 'workspace mount: ok\n'
    return
  fi

  warn_missing_workspace_mount
  return 1
}

cmd_load_images() {
  require kind
  [[ "$#" -gt 0 ]] || die "provide at least one image tag, e.g. localhost/scion-claude:latest"
  cluster_exists || die "kind cluster $CLUSTER_NAME does not exist; run: task kind:up"

  for image in "$@"; do
    log "load image $image into $CLUSTER_NAME"
    local load_output
    if load_output="$(kind load docker-image --name "$CLUSTER_NAME" "$image" 2>&1)"; then
      [[ -n "$load_output" ]] && printf '%s\n' "$load_output"
      continue
    fi

    if ! command -v podman >/dev/null 2>&1 || ! podman image exists "$image"; then
      printf '%s\n' "$load_output" >&2
      die "image $image is not available to kind or podman; run: task build"
    fi

    local archive
    archive="$(mktemp "${TMPDIR:-/tmp}/scion-kind-image.XXXXXX.tar")"
    log "export podman image $image for kind"
    if ! podman save "$image" -o "$archive"; then
      rm -f "$archive"
      die "failed to export podman image $image"
    fi
    if ! kind load image-archive --name "$CLUSTER_NAME" "$archive"; then
      rm -f "$archive"
      die "failed to load podman archive for $image into $CLUSTER_NAME"
    fi
    rm -f "$archive"
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
  KIND_CONTEXT="$CONTEXT" \
    SCION_K8S_NAMESPACE="$NAMESPACE" \
    SCION_K8S_PROFILE="$PROFILE_NAME" \
    SCION_K8S_RUNTIME="$RUNTIME_NAME" \
    SCION_IMAGE_REGISTRY="$IMAGE_REGISTRY" \
    yq eval '
    .schema_version = (.schema_version // "1") |
    .runtimes[strenv(SCION_K8S_RUNTIME)].type = "kubernetes" |
    .runtimes[strenv(SCION_K8S_RUNTIME)].context = strenv(KIND_CONTEXT) |
    .runtimes[strenv(SCION_K8S_RUNTIME)].namespace = strenv(SCION_K8S_NAMESPACE) |
    .profiles[strenv(SCION_K8S_PROFILE)].runtime = strenv(SCION_K8S_RUNTIME) |
    .image_registry = strenv(SCION_IMAGE_REGISTRY)
  ' "$settings_file" > "$tmp"
  mv "$tmp" "$settings_file"

  cat <<EOF
Configured Scion profile:
  file:      ${settings_file}
  profile:   ${PROFILE_NAME}
  runtime:   ${RUNTIME_NAME}
  context:   ${CONTEXT}
  namespace: ${NAMESPACE}
  registry:  ${IMAGE_REGISTRY}
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
  workspace-status)
    shift
    cmd_workspace_status "$@"
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
