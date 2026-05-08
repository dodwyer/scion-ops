# scion-ops

Kubernetes-hosted Scion operations for running agent rounds through a Scion Hub,
dedicated Runtime Broker, HTTP MCP server, and Kubernetes agent pods.

The supported deployment target is Kubernetes through local `kind`. The
operator-facing contract is:

```bash
task x          # build, deploy/update, bootstrap, and smoke test
task build      # build all required images
task up         # create/update the kind control plane
task bootstrap  # restore credentials, harness configs, templates, and target grove
task test       # no-spend control-plane smoke test
task down       # destroy the kind cluster and cluster-local state
```

## Prerequisites

- `task`
- `podman`
- `kind`
- `kubectl`
- `uv`
- `scion`
- upstream Scion checkout at `~/workspace/github/GoogleCloudPlatform/scion`, or
  pass `task build -- --src <path>`

## Default Operation

Bring up the product from a fresh checkout:

```bash
task x
```

Run individual lifecycle steps:

```bash
task build
task up
task bootstrap
task test
task down
```

`task up` is both deploy and update. It reconciles the kind cluster, loads local
images, applies Kubernetes resources, restarts mutable deployments, and waits for
rollout health.

Use narrow update commands while iterating:

```bash
task dev:mcp:restart
task build:base
task update:hub
task build:mcp
task update:mcp
task build:harness -- codex
task load:image -- localhost/scion-codex:latest
task dev:test
task storage:status
```

## Defaults

| Setting | Default |
| --- | --- |
| kind cluster | `scion-ops` |
| kind context | `kind-scion-ops` |
| namespace | `scion-agents` |
| Hub URL | `http://192.168.122.103:18090` |
| MCP URL | `http://192.168.122.103:8765/mcp` |
| workspace host path | `~/workspace` when it contains this checkout, otherwise this checkout's parent |
| workspace path in pods | `/workspace` |

Override defaults only when needed:

```bash
KIND_CLUSTER_NAME=scion-dev task up
SCION_OPS_KIND_LISTEN_ADDRESS=192.168.122.103 task up
SCION_OPS_WORKSPACE_HOST_PATH=/home/david/workspace task up
```

Existing kind clusters cannot be mutated to add different workspace mounts or
port mappings. Recreate the cluster after changing those settings:

```bash
task down
task up
```

## Target Projects

The target project is the repo the round should modify. Bootstrap it before
starting rounds:

```bash
task bootstrap -- /home/david/workspace/github/example/project
```

From shell tasks:

```bash
SCION_OPS_PROJECT_ROOT=/home/david/workspace/github/example/project \
task round -- "Make the requested change, verify it, push the branch, and report the branch name."
```

From MCP/Zed, pass the same path as `project_root`. If the repo is not already
checked out under the mounted workspace, call `scion_ops_prepare_github_repo`
with the GitHub URL and use the returned `project_root`.

Uncommitted editor buffers are not part of a round. Commit or push important
work before starting a round. Agent outputs are durable through pushed git
branches and Hub records; pod-local agent workspaces are ephemeral.

## MCP And Zed

`task up` exposes the HTTP MCP service through kind-native host port mappings.
No `kubectl port-forward` process is required.

Zed context server:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://192.168.122.103:8765/mcp"
    }
  }
}
```

Smoke test the MCP service:

```bash
task kind:mcp:smoke
```

Operational MCP examples are in [docs/zed-mcp.md](docs/zed-mcp.md).

## Spec-Driven Rounds

Spec rounds create only OpenSpec artifacts under
`openspec/changes/<change>/`. Implementation rounds consume an approved change
folder.

```bash
SCION_OPS_PROJECT_ROOT=/home/david/workspace/github/example/project \
SCION_OPS_SPEC_CHANGE=add-widget \
task spec:round -- "Specify the widget behavior."

task spec:validate -- --project-root /home/david/workspace/github/example/project --change add-widget

SCION_OPS_PROJECT_ROOT=/home/david/workspace/github/example/project \
task spec:implement -- --change add-widget "Implement the approved change."
```

MCP callers should prefer `scion_ops_run_spec_round` for spec rounds because it
starts, monitors, validates, and returns the PR-ready branch in one repeatable
tool loop.

OpenSpec operations are documented in
[docs/openspec-round-workflow.md](docs/openspec-round-workflow.md).

## Verification

Use `task verify` for static checks and repo-local validators. It does not
create a cluster.

Use `task test` for the regular no-spend control-plane smoke. It checks kind,
Hub, broker, MCP, and Kubernetes no-auth agent dispatch.

Use `task release:smoke` only for release confidence or credential changes. It
uses subscription-backed model credentials and starts a bounded Claude/Codex
round. The default final reviewer is Gemini; set
`SCION_OPS_RELEASE_SMOKE_FINAL_REVIEWER=codex` when Gemini is not part of the
check.

## State And Destruction

`task down` deletes the kind cluster and all cluster-local PVCs and Secrets.
Host workspace checkouts survive because they are outside the cluster.

Cluster-local state includes Hub DB/storage, dev auth, broker credentials,
synced templates, harness configs, MCP-prepared GitHub checkouts, and restored
model credentials. Recreate it with:

```bash
task up
task bootstrap -- /path/to/project
```

## Layout

- `.scion/templates/` - Scion agent templates and prompts
- `deploy/kind/` - native Kubernetes manifests for kind, Hub, broker, MCP, and runtime RBAC
- `docs/kind-control-plane.md` - Kubernetes operations runbook
- `docs/zed-mcp.md` - Zed and MCP operations
- `docs/openspec-round-workflow.md` - OpenSpec operations
- `image-build/` - image additions for task runtime, MCP, and optional harnesses
- `mcp_servers/scion_ops.py` - streamable HTTP MCP server
- `orchestrator/` - round launcher scripts
- `patches/scion/` - required upstream Scion runtime patches
- `scripts/` - build, bootstrap, smoke, storage, and OpenSpec utility scripts
