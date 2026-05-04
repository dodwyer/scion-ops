#!/usr/bin/env bash
# Build Scion container images natively with podman, single-arch.
#
# Requires the upstream scion source checked out (we read its image-build/
# Dockerfiles). By default it expects the source at
# $HOME/workspace/github/GoogleCloudPlatform/scion. Override with --src.
#
# Outputs images tagged as:
#   localhost/core-base:latest
#   localhost/scion-base:latest
#   localhost/scion-<harness>:latest    (for each in HARNESSES)
#
# After running, configure scion with:
#   scion config set --global image_registry localhost
set -eo pipefail

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
log()   { printf '\033[36m==> %s\033[0m\n' "$*"; }

SCION_SRC="${HOME}/workspace/github/GoogleCloudPlatform/scion"
TAG="latest"
REGISTRY="localhost"
HARNESSES=(claude codex gemini)   # skip opencode by default to save time/disk
BUILD_MCP=1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_IMG_BUILD="$REPO_ROOT/image-build"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src)       SCION_SRC="$2"; shift 2 ;;
    --tag)       TAG="$2"; shift 2 ;;
    --registry)  REGISTRY="$2"; shift 2 ;;
    --harness)   HARNESSES=("$2"); shift 2 ;;
    --all-harnesses) HARNESSES=(claude codex gemini opencode); shift ;;
    --skip-mcp)  BUILD_MCP=0; shift ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [options]
  --src <path>       Path to scion source (default: $SCION_SRC)
  --tag <tag>        Image tag (default: $TAG)
  --registry <name>  Image prefix (default: $REGISTRY)
  --harness <name>   Build only this harness (repeatable)
  --all-harnesses    Build claude codex gemini opencode (default: claude codex gemini)
  --skip-mcp         Do not build the scion-ops MCP image
EOF
      exit 0
      ;;
    *) red "Unknown option: $1"; exit 1 ;;
  esac
done

[[ -d "$SCION_SRC/image-build" ]] || { red "scion source not found at $SCION_SRC"; exit 1; }
command -v podman >/dev/null || { red "podman not on PATH"; exit 1; }

IMG_BUILD="$SCION_SRC/image-build"

build() {
  local name="$1" dockerfile="$2" context="$3"; shift 3
  local tag="${REGISTRY}/${name}:${TAG}"
  log "build $tag"
  podman build \
    --tag "$tag" \
    --file "$dockerfile" \
    "$@" \
    "$context"
  green "    ok  $tag"
}

# 1. core-base
build "core-base" \
      "$IMG_BUILD/core-base/Dockerfile" \
      "$IMG_BUILD/core-base"

# 2. scion-base (needs scion source root as context to copy go.mod, cmd/, pkg/, web/)
build "scion-base" \
      "$IMG_BUILD/scion-base/Dockerfile" \
      "$SCION_SRC" \
      --build-arg "BASE_IMAGE=${REGISTRY}/core-base:${TAG}" \
      --build-arg "GIT_COMMIT=$(git -C "$SCION_SRC" rev-parse HEAD 2>/dev/null || echo unknown)"

# 3. harness images
for h in "${HARNESSES[@]}"; do
  harness_dir="$IMG_BUILD/${h}"
  if [[ -d "$LOCAL_IMG_BUILD/${h}" ]]; then
    harness_dir="$LOCAL_IMG_BUILD/${h}"
  fi
  build "scion-${h}" \
        "$harness_dir/Dockerfile" \
        "$harness_dir" \
        --build-arg "BASE_IMAGE=${REGISTRY}/scion-base:${TAG}"
done

if [[ "$BUILD_MCP" == "1" ]]; then
  build "scion-ops-mcp" \
        "$LOCAL_IMG_BUILD/scion-ops-mcp/Dockerfile" \
        "$LOCAL_IMG_BUILD/scion-ops-mcp" \
        --build-arg "BASE_IMAGE=${REGISTRY}/scion-base:${TAG}"
fi

green ""
green "All images built."
echo  "Configure scion:  scion config set --global image_registry ${REGISTRY}"
podman images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | awk 'NR==1 || /scion|core-base/' | head -10
