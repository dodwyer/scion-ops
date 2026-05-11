#!/usr/bin/env bash
# Build Scion container images natively with Docker, single-arch.
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
BUILD_CORE=1
BUILD_BASE=1
BUILD_HARNESSES=1
BUILD_NEW_UI_EVAL=1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_IMG_BUILD="$REPO_ROOT/image-build"
TASK_VERSION="${TASK_VERSION:-v3.44.0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src)       SCION_SRC="$2"; shift 2 ;;
    --tag)       TAG="$2"; shift 2 ;;
    --registry)  REGISTRY="$2"; shift 2 ;;
    --harness)   HARNESSES=("$2"); shift 2 ;;
    --all-harnesses) HARNESSES=(claude codex gemini opencode); shift ;;
    --skip-mcp)  BUILD_MCP=0; shift ;;
    --skip-new-ui-eval) BUILD_NEW_UI_EVAL=0; shift ;;
    --skip-core) BUILD_CORE=0; shift ;;
    --skip-base) BUILD_BASE=0; shift ;;
    --skip-harnesses) BUILD_HARNESSES=0; shift ;;
    --only)
      BUILD_CORE=0
      BUILD_BASE=0
      BUILD_HARNESSES=0
      BUILD_MCP=0
      BUILD_NEW_UI_EVAL=0
      case "$2" in
        core) BUILD_CORE=1 ;;
        base) BUILD_CORE=1; BUILD_BASE=1 ;;
        harnesses) BUILD_HARNESSES=1 ;;
        mcp) BUILD_MCP=1 ;;
        new-ui-eval) BUILD_NEW_UI_EVAL=1 ;;
        claude|codex|gemini|opencode)
          BUILD_HARNESSES=1
          HARNESSES=("$2")
          ;;
        all)
          BUILD_CORE=1
          BUILD_BASE=1
          BUILD_HARNESSES=1
          BUILD_MCP=1
          BUILD_NEW_UI_EVAL=1
          ;;
        *) red "Unknown --only target: $2"; exit 1 ;;
      esac
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Usage: $(basename "$0") [options]
  --src <path>       Path to scion source (default: $SCION_SRC)
  --tag <tag>        Image tag (default: $TAG)
  --registry <name>  Image prefix (default: $REGISTRY)
  --harness <name>   Build only this harness (repeatable)
  --all-harnesses    Build claude codex gemini opencode (default: claude codex gemini)
  --skip-mcp         Do not build the scion-ops MCP image
  --skip-new-ui-eval Do not build the new UI evaluation image
  --skip-core        Do not build core-base
  --skip-base        Do not build scion-base
  --skip-harnesses   Do not build harness images
  --only <target>    Build only core, base, mcp, harnesses, all, or one harness
EOF
      exit 0
      ;;
    *) red "Unknown option: $1"; exit 1 ;;
  esac
done

[[ -d "$SCION_SRC/image-build" ]] || { red "scion source not found at $SCION_SRC"; exit 1; }
command -v docker >/dev/null || { red "docker not on PATH"; exit 1; }
docker info >/dev/null 2>&1 || { red "docker daemon is not available"; exit 1; }

"$REPO_ROOT/scripts/scion-runtime-patches.sh" ensure --src "$SCION_SRC"

IMG_BUILD="$SCION_SRC/image-build"

storage_preflight() {
  [[ "${SCION_OPS_SKIP_STORAGE_CHECK:-}" == "1" ]] && return

  local driver graph_root available_kb
  driver="$(docker info --format '{{.Driver}}' 2>/dev/null || true)"
  graph_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"

  if [[ "$driver" == "vfs" ]]; then
    printf '\033[33m%s\033[0m\n' "Warning: Docker is using the vfs storage driver; image rebuilds will consume much more disk than overlay-backed storage."
    printf '\033[33m%s\033[0m\n' "         Use targeted build tasks, or run 'task storage:status' and 'task storage:prune' before a full build."
  fi

  if [[ -n "$graph_root" && -d "$graph_root" ]]; then
    available_kb="$(df -Pk "$graph_root" | awk 'NR == 2 {print $4}')"
    if [[ -n "$available_kb" && "$available_kb" -lt 41943040 ]]; then
      red "Docker storage has less than 40GiB available at $graph_root."
      red "Run 'task storage:status' and prune old images before building."
      exit 1
    fi
  fi
}

build() {
  local name="$1" dockerfile="$2" context="$3"; shift 3
  local tag="${REGISTRY}/${name}:${TAG}"
  log "build $tag"
  docker build \
    --tag "$tag" \
    --file "$dockerfile" \
    "$@" \
    "$context"
  green "    ok  $tag"
}

storage_preflight

# 1. core-base
if [[ "$BUILD_CORE" == "1" ]]; then
  build "core-base" \
        "$IMG_BUILD/core-base/Dockerfile" \
        "$IMG_BUILD/core-base"
fi

# 2. scion-base (needs scion source root as context to copy go.mod, cmd/, pkg/, web/)
if [[ "$BUILD_BASE" == "1" ]]; then
  build "scion-base" \
        "$IMG_BUILD/scion-base/Dockerfile" \
        "$SCION_SRC" \
        --build-arg "BASE_IMAGE=${REGISTRY}/core-base:${TAG}" \
        --build-arg "GIT_COMMIT=$(git -C "$SCION_SRC" rev-parse HEAD 2>/dev/null || echo unknown)"
  build "scion-base" \
        "$LOCAL_IMG_BUILD/task-runtime/Dockerfile" \
        "$LOCAL_IMG_BUILD/task-runtime" \
        --build-arg "BASE_IMAGE=${REGISTRY}/scion-base:${TAG}" \
        --build-arg "TASK_VERSION=${TASK_VERSION}"
fi

# 3. harness images
if [[ "$BUILD_HARNESSES" == "1" ]]; then
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
fi

if [[ "$BUILD_MCP" == "1" ]]; then
  build "scion-ops-mcp" \
        "$LOCAL_IMG_BUILD/scion-ops-mcp/Dockerfile" \
        "$LOCAL_IMG_BUILD/scion-ops-mcp" \
        --build-arg "BASE_IMAGE=${REGISTRY}/scion-base:${TAG}"
fi

if [[ "$BUILD_NEW_UI_EVAL" == "1" ]]; then
  NEW_UI_EVAL_CONTEXT="$REPO_ROOT/new-ui-evaluation"
  if [[ ! -d "$NEW_UI_EVAL_CONTEXT" ]]; then
    red "new-ui-evaluation directory not found at $NEW_UI_EVAL_CONTEXT; skipping scion-ops-new-ui-eval build"
    red "Run the frontend scaffold (Group A) before building this image."
  else
    build "scion-ops-new-ui-eval" \
          "$LOCAL_IMG_BUILD/new-ui-eval/Dockerfile" \
          "$NEW_UI_EVAL_CONTEXT"
  fi
fi

green ""
green "All images built."
echo  "Configure scion:  scion config set --global image_registry ${REGISTRY}"
docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | awk 'NR==1 || /scion|core-base/' | head -10
