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
DEFAULT_WORKSPACE_HOST_PATH="${HOME}/workspace"
case "$REPO_ROOT" in
  "$DEFAULT_WORKSPACE_HOST_PATH"|"$DEFAULT_WORKSPACE_HOST_PATH"/*) ;;
  *) DEFAULT_WORKSPACE_HOST_PATH="$(dirname "$REPO_ROOT")" ;;
esac
if [[ ! -d "$DEFAULT_WORKSPACE_HOST_PATH" ]]; then
  DEFAULT_WORKSPACE_HOST_PATH="$(dirname "$REPO_ROOT")"
fi
WORKSPACE_HOST_PATH="${SCION_OPS_WORKSPACE_HOST_PATH:-$DEFAULT_WORKSPACE_HOST_PATH}"
WORKSPACE_NODE_PATH="${SCION_OPS_WORKSPACE_NODE_PATH:-/workspace}"
case "$REPO_ROOT" in
  "$WORKSPACE_HOST_PATH")
    SCION_OPS_REPO_NODE_PATH="${SCION_OPS_REPO_NODE_PATH:-$WORKSPACE_NODE_PATH}"
    ;;
  "$WORKSPACE_HOST_PATH"/*)
    SCION_OPS_REPO_NODE_PATH="${SCION_OPS_REPO_NODE_PATH:-${WORKSPACE_NODE_PATH}/${REPO_ROOT#"$WORKSPACE_HOST_PATH"/}}"
    ;;
  *)
    SCION_OPS_REPO_NODE_PATH="${SCION_OPS_REPO_NODE_PATH:-${WORKSPACE_NODE_PATH}/scion-ops}"
    ;;
esac
KIND_PROVIDER="docker"
KIND_CLUSTER_CONFIG_TEMPLATE="${SCION_OPS_KIND_CLUSTER_CONFIG_TEMPLATE:-${REPO_ROOT}/deploy/kind/cluster.yaml.tpl}"
KIND_LISTEN_ADDRESS="${SCION_OPS_KIND_LISTEN_ADDRESS:-192.168.122.103}"
HUB_HOST_PORT="${SCION_OPS_KIND_HUB_PORT:-18090}"
MCP_HOST_PORT="${SCION_OPS_MCP_PORT:-8765}"
WEB_APP_HOST_PORT="${SCION_OPS_WEB_APP_PORT:-8808}"
HUB_NODE_PORT="30090"
MCP_NODE_PORT="30876"
WEB_APP_NODE_PORT="30808"
CONTEXT="kind-${CLUSTER_NAME}"
SCION_SETTINGS_TEMPLATE="${SCION_SETTINGS_TEMPLATE:-${REPO_ROOT}/deploy/kind/scion-settings.base.yaml}"
KIND_IMAGE_PLATFORM="${SCION_OPS_KIND_IMAGE_PLATFORM:-linux/amd64}"
export KIND_EXPERIMENTAL_PROVIDER="$KIND_PROVIDER"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  up                  Create/reuse the kind cluster and apply deploy/kind.
  down                Delete the kind cluster.
  status              Show cluster, namespace, RBAC, and node status.
  workspace-status    Verify the kind node can see the scion-ops workspace.
  configure-mcp-root  Point the MCP deployment at this scion-ops checkout.
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
  SCION_OPS_WORKSPACE_HOST_PATH  Host workspace tree mounted into kind
                                 (default: ~/workspace when it contains the
                                 scion-ops checkout, otherwise the checkout's
                                 parent)
  SCION_OPS_WORKSPACE_NODE_PATH  Node path for the mounted workspace tree
                                 (default: /workspace)
  SCION_OPS_REPO_NODE_PATH       scion-ops repo path inside the kind node
                                 (default: derived from host/node paths)
  SCION_OPS_KIND_CLUSTER_CONFIG_TEMPLATE
                                 kind cluster template (default: deploy/kind/cluster.yaml.tpl)
  SCION_OPS_KIND_LISTEN_ADDRESS  Host listen address for kind port mappings
                                 (default: 192.168.122.103)
  SCION_OPS_KIND_HUB_PORT        Host port for the Hub service (default: 18090)
  SCION_OPS_MCP_PORT             Host port for the MCP service (default: 8765)
  SCION_OPS_KIND_IMAGE_PLATFORM  Platform for direct kind image imports
                                 (default: linux/amd64)
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
  [[ "$SCION_OPS_REPO_NODE_PATH" = /* ]] || die "SCION_OPS_REPO_NODE_PATH must be an absolute path: $SCION_OPS_REPO_NODE_PATH"
  [[ -d "$WORKSPACE_HOST_PATH" ]] || die "workspace host path not found: $WORKSPACE_HOST_PATH"
  case "$REPO_ROOT" in
    "$WORKSPACE_HOST_PATH"|"$WORKSPACE_HOST_PATH"/*) ;;
    *) die "SCION_OPS_WORKSPACE_HOST_PATH must contain the scion-ops checkout: $WORKSPACE_HOST_PATH" ;;
  esac
}

yaml_dq_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

sed_replacement_escape() {
  printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

render_cluster_config() {
  [[ -f "$KIND_CLUSTER_CONFIG_TEMPLATE" ]] || die "kind cluster template not found: $KIND_CLUSTER_CONFIG_TEMPLATE"

  local config
  config="$(mktemp)"
  sed \
    -e "s|__HUB_NODE_PORT__|$(sed_replacement_escape "$HUB_NODE_PORT")|g" \
    -e "s|__HUB_HOST_PORT__|$(sed_replacement_escape "$HUB_HOST_PORT")|g" \
    -e "s|__MCP_NODE_PORT__|$(sed_replacement_escape "$MCP_NODE_PORT")|g" \
    -e "s|__MCP_HOST_PORT__|$(sed_replacement_escape "$MCP_HOST_PORT")|g" \
    -e "s|__WEB_APP_NODE_PORT__|$(sed_replacement_escape "$WEB_APP_NODE_PORT")|g" \
    -e "s|__WEB_APP_HOST_PORT__|$(sed_replacement_escape "$WEB_APP_HOST_PORT")|g" \
    -e "s|__KIND_LISTEN_ADDRESS__|$(sed_replacement_escape "$(yaml_dq_escape "$KIND_LISTEN_ADDRESS")")|g" \
    -e "s|__WORKSPACE_HOST_PATH__|$(sed_replacement_escape "$(yaml_dq_escape "$WORKSPACE_HOST_PATH")")|g" \
    -e "s|__WORKSPACE_NODE_PATH__|$(sed_replacement_escape "$(yaml_dq_escape "$WORKSPACE_NODE_PATH")")|g" \
    "$KIND_CLUSTER_CONFIG_TEMPLATE" > "$config"
  printf '%s\n' "$config"
}

kind_node_name() {
  kind get nodes --name "$CLUSTER_NAME" 2>/dev/null | head -n 1
}

container_runtime_for_node() {
  local node="$1"
  if command -v docker >/dev/null 2>&1 && docker container inspect "$node" >/dev/null 2>&1; then
    printf 'docker\n'
    return 0
  fi
  return 1
}

workspace_mount_present() {
  local node
  local runtime

  node="$(kind_node_name)"
  [[ -n "$node" ]] || return 1
  runtime="$(container_runtime_for_node "$node")" || return 1

  "$runtime" exec "$node" test -f "${SCION_OPS_REPO_NODE_PATH}/Taskfile.yml" &&
    "$runtime" exec "$node" test -d "${SCION_OPS_REPO_NODE_PATH}/.git"
}

kind_native_ports_present() {
  local node
  local runtime
  local bindings

  node="$(kind_node_name)"
  [[ -n "$node" ]] || return 1
  runtime="$(container_runtime_for_node "$node")" || return 1
  bindings="$("$runtime" container inspect --format '{{json .HostConfig.PortBindings}}' "$node" 2>/dev/null || true)"

  [[ "$bindings" == *"\"${HUB_NODE_PORT}/tcp\""* ]] &&
    [[ "$bindings" == *"\"${MCP_NODE_PORT}/tcp\""* ]] &&
    [[ "$bindings" == *"\"${WEB_APP_NODE_PORT}/tcp\""* ]] &&
    [[ "$bindings" == *"\"HostPort\":\"${HUB_HOST_PORT}\""* ]] &&
    [[ "$bindings" == *"\"HostPort\":\"${MCP_HOST_PORT}\""* ]] &&
    [[ "$bindings" == *"\"HostPort\":\"${WEB_APP_HOST_PORT}\""* ]] &&
    [[ "$bindings" == *"\"HostIp\":\"${KIND_LISTEN_ADDRESS}\""* ]]
}

warn_missing_workspace_mount() {
  cat >&2 <<EOF
Warning: workspace mount is not available inside kind node ${WORKSPACE_NODE_PATH}.
Existing kind clusters cannot be updated with new extraMounts. Recreate this
cluster with 'task down' and then 'task up' before deploying scion-ops.

Expected:
  host workspace path: ${WORKSPACE_HOST_PATH}
  node workspace path: ${WORKSPACE_NODE_PATH}
  scion-ops node path: ${SCION_OPS_REPO_NODE_PATH}
EOF
}

warn_missing_kind_native_ports() {
  cat >&2 <<EOF
Warning: kind native port mappings are not available on cluster ${CLUSTER_NAME}.
Existing kind clusters cannot be updated with new extraPortMappings. Recreate
this cluster with 'task down' and then 'task up'.

Required mappings:
  ${KIND_LISTEN_ADDRESS}:${HUB_HOST_PORT} -> kind node ${HUB_NODE_PORT} -> scion-hub
  ${KIND_LISTEN_ADDRESS}:${MCP_HOST_PORT} -> kind node ${MCP_NODE_PORT} -> scion-ops-mcp
  ${KIND_LISTEN_ADDRESS}:${WEB_APP_HOST_PORT} -> kind node ${WEB_APP_NODE_PORT} -> scion-ops-web-app
EOF
}

validate_cluster_substrate() {
  local missing=0
  if ! workspace_mount_present; then
    warn_missing_workspace_mount
    missing=1
  fi
  if ! kind_native_ports_present; then
    warn_missing_kind_native_ports
    missing=1
  fi
  [[ "$missing" -eq 0 ]] || die "existing kind cluster $CLUSTER_NAME is missing required scion-ops substrate; recreate it with task down and task up"
}

ensure_cluster() {
  require kind
  if cluster_exists; then
    log "reuse kind cluster $CLUSTER_NAME"
    validate_cluster_substrate
    return
  fi

  ensure_workspace_host_path
  log "create kind cluster $CLUSTER_NAME"
  local config
  config="$(render_cluster_config)"
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
  configure_mcp_root
}

configure_mcp_root() {
  require kubectl
  log "configure MCP repo root ${SCION_OPS_REPO_NODE_PATH}"
  kubectl_ctx -n "$NAMESPACE" set env deploy/scion-ops-mcp \
    "SCION_OPS_ROOT=${SCION_OPS_REPO_NODE_PATH}" \
    "SCION_OPS_HOST_WORKSPACE_ROOT=${WORKSPACE_HOST_PATH}" \
    "SCION_OPS_CONTAINER_WORKSPACE_ROOT=${WORKSPACE_NODE_PATH}" \
    >/dev/null
  kubectl_ctx -n "$NAMESPACE" set env deploy/scion-ops-web-app \
    "SCION_OPS_ROOT=${SCION_OPS_REPO_NODE_PATH}" \
    >/dev/null
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
  printf 'provider:  %s\n' "$KIND_PROVIDER"
  printf 'workspace host: %s\n' "$WORKSPACE_HOST_PATH"
  printf 'workspace node: %s\n' "$WORKSPACE_NODE_PATH"
  printf 'scion-ops node: %s\n\n' "$SCION_OPS_REPO_NODE_PATH"
  printf 'Hub host URL:     http://%s:%s\n' "$KIND_LISTEN_ADDRESS" "$HUB_HOST_PORT"
  printf 'MCP host URL:     http://%s:%s/mcp\n' "$KIND_LISTEN_ADDRESS" "$MCP_HOST_PORT"
  printf 'Web app host URL: http://%s:%s\n\n' "$KIND_LISTEN_ADDRESS" "$WEB_APP_HOST_PORT"

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
  if kind_native_ports_present; then
    printf 'kind native ports: ok\n'
  else
    printf 'kind native ports: unavailable; recreate the cluster with task down and task up\n'
  fi
}

cmd_workspace_status() {
  require kind

  printf 'cluster:        %s\n' "$CLUSTER_NAME"
  printf 'workspace host: %s\n' "$WORKSPACE_HOST_PATH"
  printf 'workspace node: %s\n' "$WORKSPACE_NODE_PATH"
  printf 'scion-ops node: %s\n\n' "$SCION_OPS_REPO_NODE_PATH"

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

cmd_configure_mcp_root() {
  require kubectl
  configure_mcp_root
}

cmd_load_images() {
  require kind
  [[ "$#" -gt 0 ]] || die "provide at least one image tag, e.g. localhost/scion-claude:latest"
  cluster_exists || die "kind cluster $CLUSTER_NAME does not exist; run: task kind:up"

  for image in "$@"; do
    log "load image $image into $CLUSTER_NAME"
    if command -v docker >/dev/null 2>&1 && docker image inspect "$image" >/dev/null 2>&1 && image_loaded_in_kind "$image"; then
      log "image $image already loaded in $CLUSTER_NAME"
      continue
    fi

    local load_output
    if load_output="$(kind load docker-image --name "$CLUSTER_NAME" "$image" 2>&1)"; then
      [[ -n "$load_output" ]] && printf '%s\n' "$load_output"
      continue
    fi

    printf '%s\n' "$load_output" >&2
    die "image $image is not available to Docker or failed to load into kind; run: task build"
  done
}

image_loaded_in_kind() {
  local image="$1"
  local image_id node runtime
  local nodes=()

  image_id="$(docker image inspect "$image" --format '{{.Id}}' 2>/dev/null || true)"
  image_id="${image_id#sha256:}"
  [[ -n "$image_id" ]] || return 1

  mapfile -t nodes < <(kind get nodes --name "$CLUSTER_NAME" 2>/dev/null)
  [[ "${#nodes[@]}" -gt 0 ]] || return 1

  for node in "${nodes[@]}"; do
    [[ -n "$node" ]] || continue
    runtime="$(container_runtime_for_node "$node")" || return 1
    "$runtime" exec "$node" ctr --namespace=k8s.io images inspect "$image" 2>/dev/null \
      | grep -Fq "@sha256:${image_id}" || return 1
  done
}

import_image_archive() {
  local archive="$1"
  local node runtime snapshotter
  local nodes=()
  local import_cmd

  mapfile -t nodes < <(kind get nodes --name "$CLUSTER_NAME" 2>/dev/null)
  [[ "${#nodes[@]}" -gt 0 ]] || return 1

  for node in "${nodes[@]}"; do
    [[ -n "$node" ]] || continue
    runtime="$(container_runtime_for_node "$node")" || return 1
    snapshotter="${SCION_OPS_KIND_IMAGE_SNAPSHOTTER:-}"

    import_cmd=(ctr --namespace=k8s.io images import --local --digests --platform "$KIND_IMAGE_PLATFORM")
    if [[ -n "$snapshotter" ]]; then
      import_cmd+=(--snapshotter "$snapshotter")
    fi
    import_cmd+=(-)

    log "import image archive into $node for $KIND_IMAGE_PLATFORM"
    "$runtime" exec --privileged -i "$node" "${import_cmd[@]}" < "$archive"
  done
}

cmd_load_archive() {
  require kind
  [[ "$#" -gt 0 ]] || die "provide at least one image archive"
  cluster_exists || die "kind cluster $CLUSTER_NAME does not exist; run: task kind:up"

  for archive in "$@"; do
    [[ -f "$archive" ]] || die "image archive not found: $archive"
    log "load image archive $archive into $CLUSTER_NAME"
    import_image_archive "$archive"
  done
}

cmd_configure_scion() {
  require yq

  local settings_file="${SCION_SETTINGS_FILE:-${HOME}/.scion/settings.yaml}"
  local settings_dir
  settings_dir="$(dirname "$settings_file")"
  mkdir -p "$settings_dir"
  if [[ ! -f "$settings_file" ]]; then
    [[ -f "$SCION_SETTINGS_TEMPLATE" ]] || die "Scion settings template not found: $SCION_SETTINGS_TEMPLATE"
    cp "$SCION_SETTINGS_TEMPLATE" "$settings_file"
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
  configure-mcp-root)
    shift
    cmd_configure_mcp_root "$@"
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
