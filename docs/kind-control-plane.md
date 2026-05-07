# Kubernetes Control Plane

This is the supported deployment path for scion-ops. Hub, Web/API, Runtime
Broker, MCP, and Scion agent pods run in Kubernetes. For local development the
cluster is `kind`; other Kubernetes clusters need an explicit persistence and
workspace bootstrap implementation before they are supported. The accepted
workspace design is documented in `docs/workspace-persistence.md`.

## Operating Contract

Use the top-level lifecycle tasks:

```bash
task x
task build
task up
task bootstrap
task test
task down
```

`task x` is the day-zero path: build images, create/update the deployment, and
run the bootstrap and smoke test. `task up` is both deploy and update. It
creates or reuses the kind cluster, applies base runtime resources, verifies the
workspace mount, loads local images, applies the control-plane Kustomize target,
restarts the control-plane deployments so mutable local image tags are picked
up, and waits for rollout.

Use focused tasks for iteration:

```bash
task dev:mcp:restart
task build:base
task update:hub
task build:mcp
task update:mcp
task build:harness -- claude
task load:image -- localhost/scion-claude:latest
task dev:test
task storage:status
```

These tasks keep the lifecycle defaults intact while avoiding unnecessary image
builds, kind image loads, and control-plane restarts.

## Kubernetes Resources

Resources are native manifests managed by Kustomize:

```text
deploy/kind/
  cluster.yaml.tpl
  namespace.yaml
  rbac.yaml
  scion-settings.base.yaml
  kustomization.yaml
  smoke/
    generic-smoke-agent.yaml
  control-plane/
    broker-deployment.yaml
    broker-rbac.yaml
    config/
      broker-bootstrap-server.yaml
      broker-bootstrap-settings.yaml
      broker-entrypoint.sh
      broker-kubeconfig.yaml
      hub-settings.yaml
    hub-deployment.yaml
    hub-pvc.yaml
    hub-service.yaml
    mcp-deployment.yaml
    mcp-service.yaml
    kustomization.yaml
```

The direct apply form remains valid after the kind cluster has been created
with the required native port mappings:

```bash
kubectl --context kind-scion-ops apply -k deploy/kind/control-plane
```

Kustomize is intentional for the current resource size. Do not introduce Helm
until the values model and upgrade behavior are worth packaging. The packaging
decision and Helm review triggers are documented in
`docs/kubernetes-packaging.md`.

Config payloads remain source files under `deploy/kind/control-plane/config`
and are included with Kustomize `configMapGenerator`; scripts do not carry
literal Kubernetes YAML bodies.

## Control-Plane Shape

The Kubernetes control plane includes:

- a Hub Deployment for Scion Hub/API/Web and PVC-backed Hub state
- a dedicated Runtime Broker Deployment
- an in-cluster Kubernetes runtime profile

The MCP Deployment runs the scion-ops streamable HTTP MCP server and reads Hub
state through the `scion-hub` ClusterIP service. In local kind, MCP mounts the
host workspace tree via a kind node `extraMount` and Kubernetes `hostPath`, so
tools operate on the mounted git checkout selected by `project_root`.
Cluster deployments should use MCP-managed Git checkouts on persistent storage
instead of workstation bind mounts.

The broker creates agent pods in `scion-agents` using in-cluster Kubernetes API
access. It restores Hub HMAC credentials from the `scion-broker-credentials`
Secret and connects back to the Hub over Scion's control channel. It does not
use host Podman or Docker sockets.

## Development Loop

Before building Scion images, scion-ops ensures the configured Scion checkout
has the required runtime patch set from `patches/scion/`. The default source is
`~/workspace/github/GoogleCloudPlatform/scion`; override it with `SCION_SRC` or
`task build -- --src <path>`.

```bash
task scion:patch:status
task scion:patch:apply
task scion:patch:check
```

`task build` and `task build:base` run the same patch ensure step, so a clean
checkout fails or converges before Hub images are built.

MCP source changes are mounted from the workspace, so they usually need only:

```bash
task dev:mcp:restart
task kind:mcp:smoke
```

Image-level changes stay explicit:

```bash
task build:base
task update:hub
task build:mcp
task update:mcp
task build:harness -- codex
task load:image -- localhost/scion-codex:latest
```

Before full image work, check storage:

```bash
task storage:status
```

The build helper warns when Podman uses `vfs` and fails early when available
space in the Podman graph root is under 40 GiB. Set
`SCION_OPS_SKIP_STORAGE_CHECK=1` only when the storage state has been checked
another way. Normal full rebuilds should use rootless Podman with the `overlay`
storage driver so base layers are shared across `core-base`, `scion-base`, MCP,
and harness images.

## Local Access

Local kind exposes Hub and MCP through kind `extraPortMappings` and fixed
Kubernetes `NodePort` services. No `kubectl port-forward` process is part of
the supported workflow.

After `task up`, use:

```bash
eval "$(task kind:hub:auth-export)"
task bootstrap
task kind:mcp:smoke
```

Hub is available at `http://192.168.122.103:18090`; MCP is available at
`http://192.168.122.103:8765/mcp`.

The kind Hub sets `SCION_SERVER_HUB_HUBID` to `scion-ops-kind`. Scion
namespaces Hub-scoped secrets by Hub ID, so this value must stay stable across
Hub pod rollouts or bootstrap credentials will become invisible after restart.
`task bootstrap` also mirrors the active Hub dev-auth token into the
`scion-hub-dev-auth` Kubernetes Secret. MCP reads that Secret and no longer
mounts the Hub state PVC for auth.
Bootstrap restores `scion-hub-web-session` as the Hub web session signing
Secret and sets Hub `TMPDIR` to the Hub PVC, so filesystem-backed browser
session records and the signing key survive Hub pod restarts after bootstrap.

## Smoke Test

Run:

```bash
task test
```

This dispatches the checked-in no-auth generic smoke config through the Kubernetes-hosted
Hub and dedicated broker, verifies that an agent pod appears in kind, checks
MCP Hub status through HTTP, and deletes the smoke agent after success.

`task test` is deliberately no-auth and no-spend. For release confidence, run
the opt-in model-backed tier:

```bash
task release:smoke
```

That command bootstraps the selected target, starts a short Claude/Codex round,
and defaults to Gemini final review. It is intended for release checks or model
credential changes, not every local edit.

Useful overrides:

| Variable | Default |
|---|---|
| `KIND_CLUSTER_NAME` | `scion-ops` |
| `SCION_K8S_NAMESPACE` | `scion-agents` |
| `SCION_OPS_KIND_HUB_PORT` | `18090` |
| `SCION_OPS_KIND_LISTEN_ADDRESS` | `192.168.122.103` |
| `SCION_OPS_MCP_URL` | `http://192.168.122.103:8765/mcp` |
| `SCION_OPS_WORKSPACE_HOST_PATH` | `~/workspace` when it contains the scion-ops checkout, otherwise the checkout's parent |
| `SCION_OPS_WORKSPACE_NODE_PATH` | `/workspace` |
| `SCION_KIND_CP_SMOKE_KEEP_AGENT` | unset, deletes on success |
| `SCION_KIND_CP_SMOKE_SKIP_SETUP` | unset, applies kind resources |
| `SCION_KIND_CP_SMOKE_TIMEOUT` | `90` |
| `SCION_OPS_WATCHDOG_DELETE` | unset, timeout stops agents and keeps Hub records |

## Project Targeting

The codebase being changed is always the target project. `task bootstrap --
<project-root>` links that target as a Hub grove and provides the kind broker.
Shared credentials are stored as Hub-scoped secrets, and scion-ops templates are
synced as Hub global templates.

Default model authentication uses subscription credential files restored by
`task bootstrap`: `CLAUDE_AUTH`, `CLAUDE_CONFIG`, `CODEX_AUTH`, and
`GEMINI_OAUTH_CREDS`.
The restored Claude config keeps subscription state and adds `/workspace` as a
trusted project path for Scion-managed agent pods. Bootstrap also prepares the
Claude harness settings to skip the bypass-permissions warning in the
Kubernetes agent sandbox. Codex-backed personas use repo-managed Codex harness
configs in `deploy/kind/harness-configs/`: both `codex` and `codex-exec` run
`codex exec` as a single non-interactive task while still using the restored
Codex subscription auth file.
Host-local Claude MCP server registrations are stripped from the agent config
so startup depends on Scion's explicit harness and template configuration.
Claude templates pass `--print` through native Scion `command_args` so
multiline prompts are submitted non-interactively. Coordinators collect child
outputs through the Hub user inbox with `scion messages --json` instead of
depending on interactive tmux prompt delivery.
The default round personas use Scion's `--harness-auth auth-file` path for
Claude, Codex, and optional Gemini final review. Codex is the reliable default
final reviewer; Gemini can be requested explicitly and falls back to Codex when
capacity or auth prevents a verdict. Vertex ADC is deliberately opt-in. To use
it, set `SCION_OPS_BOOTSTRAP_VERTEX_ADC=1` and provide `GOOGLE_CLOUD_PROJECT`
plus `GOOGLE_CLOUD_REGION`, `CLOUD_ML_REGION`, or `GOOGLE_CLOUD_LOCATION`.

The MCP tool contract mirrors that shape: pass `project_root` to
`scion_ops_project_status`, `scion_ops_start_round`, `scion_ops_round_status`,
`scion_ops_watch_round_events`, and git diff/status tools when operating on a
target project. If the target is only known by GitHub URL, call
`scion_ops_prepare_github_repo` first and use the returned MCP-visible
`project_root`. In local kind that path may resolve through the host workspace
mount or the MCP checkout PVC. In cluster deployments it should resolve through
the MCP checkout PVC.

## Persistence

Deleting the kind cluster deletes cluster-local Scion state.

| State | Current local-kind source | Lost on cluster deletion |
|---|---|---|
| Hub database/state | `scion-hub-state` PVC | yes |
| Hub ID | `SCION_SERVER_HUB_HUBID=scion-ops-kind` in `deploy/kind/control-plane/hub-deployment.yaml` | no |
| Hub dev token | `scion-hub-state` PVC, mirrored to `scion-hub-dev-auth` by `task bootstrap` | yes |
| Hub web sessions | `scion-hub-web-session` Secret plus session files under `scion-hub-state` PVC | yes |
| Broker registration | Hub state plus `scion-broker-credentials` Secret restored by `task bootstrap` | yes |
| MCP workspace | host checkout mounted into kind node; local-kind only | no |
| MCP-prepared GitHub checkouts | `scion-ops-mcp-checkouts` PVC; cluster design treats this as the target checkout root | yes |
| Agent artifacts | Hub agent records and pushed git branches | pod-local state is ephemeral |
| Subscription credentials | Hub-scoped Claude, Codex, and Gemini secrets restored by `task bootstrap` | yes |
| Vertex ADC credentials | optional Hub-scoped secrets restored only when `SCION_OPS_BOOTSTRAP_VERTEX_ADC=1`; cleared by default bootstrap | yes |
| Templates/harness configs | Hub global templates plus Hub and broker harness configs restored by `task bootstrap` | yes |
