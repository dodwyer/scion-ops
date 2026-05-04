# Kubernetes Control Plane

This is the supported deployment path for scion-ops. Hub, Web/API, Runtime
Broker, MCP, and Scion agent pods run in Kubernetes. For local development the
cluster is `kind`; other Kubernetes clusters need an explicit persistence and
workspace bootstrap model before they are supported.

## Operating Contract

Use the top-level lifecycle tasks:

```bash
task x
task build
task up
task test
task down
```

`task x` is the day-zero path: build images, create/update the deployment, and
run the smoke test. `task up` is both deploy and update. It creates or reuses
the kind cluster, applies base runtime resources, verifies the workspace mount,
loads local images, applies the control-plane Kustomize target, and waits for
rollout.

## Kubernetes Resources

Resources are native manifests managed by Kustomize:

```text
deploy/kind/
  namespace.yaml
  rbac.yaml
  kustomization.yaml
  control-plane/
    broker-kubeconfig.yaml
    broker-rbac.yaml
    hub-config.yaml
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
until the values model and upgrade behavior are worth packaging.

## Control-Plane Shape

The Hub Deployment runs:

- Scion Hub/API/Web
- Scion's co-located Runtime Broker
- PVC-backed mutable Scion state
- an in-cluster Kubernetes runtime profile

The MCP Deployment runs the scion-ops streamable HTTP MCP server and reads Hub
state through the `scion-hub` ClusterIP service. In local kind, MCP mounts this
repo via a kind node `extraMount` and Kubernetes `hostPath`.

The broker creates agent pods in `scion-agents` using in-cluster Kubernetes API
access. It does not use host Podman or Docker sockets.

## Local Access

Local kind exposes Hub and MCP through kind `extraPortMappings` and fixed
Kubernetes `NodePort` services. No `kubectl port-forward` process is part of
the supported workflow.

After `task up`, use:

```bash
eval "$(task kind:hub:auth-export)"
task kind:mcp:smoke
```

Hub is available at `http://127.0.0.1:18090`; MCP is available at
`http://127.0.0.1:8765/mcp`.

## Smoke Test

Run:

```bash
task test
```

This dispatches an inline no-auth generic agent through the Kubernetes-hosted
Hub and co-located broker, verifies that an agent pod appears in kind, checks
MCP Hub status through HTTP, and deletes the smoke agent after success.

Useful overrides:

| Variable | Default |
|---|---|
| `KIND_CLUSTER_NAME` | `scion-ops` |
| `SCION_K8S_NAMESPACE` | `scion-agents` |
| `SCION_OPS_KIND_HUB_PORT` | `18090` |
| `SCION_OPS_MCP_URL` | `http://127.0.0.1:8765/mcp` |
| `SCION_KIND_CP_SMOKE_KEEP_AGENT` | unset, deletes on success |
| `SCION_KIND_CP_SMOKE_SKIP_SETUP` | unset, applies kind resources |
| `SCION_KIND_CP_SMOKE_TIMEOUT` | `90` |

## Persistence

Deleting the kind cluster deletes cluster-local Scion state.

| State | Current local-kind source | Lost on cluster deletion |
|---|---|---|
| Hub database/state | `scion-hub-state` PVC | yes |
| Hub dev token | `scion-hub-state` PVC | yes |
| Broker registration | Hub state for co-located broker | yes |
| MCP workspace | host checkout mounted into kind node | no |
| Agent artifacts | agent workspaces and pushed git branches | pod-local state is ephemeral |
| Subscription credentials | not yet restored into kind Hub | issue #29 |
| Templates/harness configs | inline generic smoke only by default | issue #29 |

Issue #29 is the required follow-up for remote-safe credential, template, and
harness bootstrap. Until that lands, do not claim full Claude/Codex/Gemini
consensus rounds as a complete Kubernetes operation.
