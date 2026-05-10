# Kubernetes Operations

scion-ops runs Scion Hub, Runtime Broker, MCP, and agent pods in Kubernetes.
The supported operator path is Kubernetes through local `kind`.

## Lifecycle

```bash
task x          # build, deploy/update, bootstrap, smoke test
task build      # build images
task up         # create/update kind and apply control-plane resources
task bootstrap  # restore Hub credentials, templates, harness configs, target grove
task test       # no-spend smoke test
task down       # destroy kind and cluster-local state
```

`task up` is the deploy and update operation. It:

- creates or reuses the kind cluster
- applies namespace and runtime RBAC
- verifies the workspace mount
- loads local images
- applies `deploy/kind/control-plane`
- restarts Hub, broker, MCP, and web app deployments
- waits for rollouts

## Resources

Kubernetes resources are native Kustomize manifests:

```text
deploy/kind/
  cluster.yaml.tpl
  namespace.yaml
  rbac.yaml
  control-plane/
    hub-*.yaml
    broker-*.yaml
    mcp-*.yaml
    web-app-*.yaml
    config/
```

Direct inspection:

```bash
kubectl --context kind-scion-ops -n scion-agents get deploy,svc,pvc,cm
kubectl --context kind-scion-ops -n scion-agents get pods
kubectl --context kind-scion-ops -n scion-agents logs deploy/scion-hub
kubectl --context kind-scion-ops -n scion-agents logs deploy/scion-broker -c broker
kubectl --context kind-scion-ops -n scion-agents logs deploy/scion-ops-mcp
kubectl --context kind-scion-ops -n scion-agents logs deploy/scion-ops-web-app
```

## Defaults

| Setting | Default |
| --- | --- |
| kind cluster | `scion-ops` |
| kind provider | `docker` |
| context | `kind-scion-ops` |
| namespace | `scion-agents` |
| Hub URL | `http://192.168.122.103:18090` |
| MCP URL | `http://192.168.122.103:8765/mcp` |
| Web app URL | `http://192.168.122.103:8808` |
| workspace host path | `~/workspace` when possible |
| workspace pod path | `/workspace` |

Changing the listen address, ports, or workspace mount requires recreating kind:

```bash
task down
task up
```

## Access

Kind exposes Hub, MCP, and the web app through native port mappings and NodePort
Services. Do not use `kubectl port-forward` for normal operation.

```bash
eval "$(task kind:hub:auth-export)"
task kind:mcp:smoke
```

Open the NiceGUI operator console at the configured web app URL (default
`http://192.168.122.103:8808`). The console reads operational state from Hub and
MCP using the same in-cluster credentials as the MCP server.

The MCP pod reads Hub through the in-cluster `scion-hub` Service and uses the
`scion-hub-dev-auth` Secret restored by `task bootstrap`.

## Bootstrap

Bootstrap must run after `task up` and before subscription-backed rounds:

```bash
task bootstrap -- /path/to/target/project
```

It restores:

- Hub dev auth Secret
- Hub web session Secret
- target grove link
- broker registration
- GitHub token Secret
- Claude, Codex, and Gemini Hub secrets
- Hub and broker harness configs
- Hub and broker templates

Codex-backed personas use the repo-managed `codex-exec` harness config.
Claude templates use `--print` for non-interactive execution.
Broker runtime state is backed by a PVC so synced templates and harness configs
survive normal broker pod restarts.

## Project Targeting

The target repo must be visible to the MCP server. In local kind, repos under
the mounted workspace are mapped into `/workspace`. For GitHub URLs not already
checked out locally, use `scion_ops_prepare_github_repo` and use the returned
`project_root`.

Agents clone from Git, work in pod-local storage, and push result branches.
They do not share the MCP checkout as a mutable workspace.

## Smoke And Release Checks

```bash
task verify          # static, no cluster
task test            # no-spend control-plane smoke
task spec:steward    # steward-based OpenSpec change
task spec:implement  # steward-based implementation from an approved change
```

`task test` verifies kind, Hub health, broker registration, MCP tool surface,
web app endpoint readiness, and no-auth Kubernetes agent dispatch.

Use the steward tasks before a release, after credential changes, or when
diagnosing model-backed dispatch.

## Narrow Updates

```bash
task dev:mcp:restart
task build:base
task update:hub
task build:mcp
task update:mcp
task update:web-app
task build:harness -- codex
task load:image -- localhost/scion-codex:latest
task dev:test
```

The NiceGUI web app reuses the `scion-ops-mcp` image. `task update:web-app`
reloads that image and restarts the web app deployment.

Use `task storage:status` before full image rebuilds. If Docker is using `vfs`,
switch to `overlay2` storage before large rebuild cycles.

## Web App Troubleshooting

```bash
task kind:web-app:status    # rollout status and service info
task kind:web-app:logs      # streaming logs
```

The NiceGUI operator console reads Hub dev auth from the `scion-hub-dev-auth`
Secret. If Hub credentials have changed, run `task bootstrap` to restore the
Secret, then `task update:web-app` to pick it up.

The console entry point is `scripts/web_app.py`. Health and JSON snapshot
endpoints (`/healthz`, `/api/overview`) remain available for probes and smoke
checks; they do not require a browser connection to be active.

If the web app port is unreachable, verify the kind cluster has the web app port
mapping active:

```bash
task kind:status
```

An old cluster without the web app port mapping must be recreated:

```bash
task down
task up
```

## NiceGUI Local Development

Run the operator console locally against a live kind control plane:

```bash
SCION_OPS_HUB_ENDPOINT=http://192.168.122.103:18090 \
SCION_OPS_MCP_URL=http://192.168.122.103:8765/mcp \
SCION_OPS_WEB_HOST=127.0.0.1 \
SCION_OPS_WEB_PORT=8787 \
uv run scripts/web_app.py
```

The console opens at `http://127.0.0.1:8787`. It uses the same environment
variables and Hub dev auth conventions as the kind deployment.

## Destroy

```bash
task down
```

This deletes the kind cluster and all cluster-local PVCs and Secrets. Host
checkouts and pushed Git branches are not deleted.
