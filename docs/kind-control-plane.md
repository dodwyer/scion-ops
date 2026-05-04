# kind Control Plane Deployment

This is the proposed path for running the Scion control plane inside the local
kind cluster. The current default remains host-managed Hub, broker, and MCP
with kind used only for agent pods.

## Direction

Use native Kubernetes resources managed by Kustomize first. Do not introduce a
Helm chart until the resource model is proven and stable.

The target shape is:

```text
kind cluster:
  Scion Hub/API/Web
  Runtime Broker
  scion-ops HTTP MCP server
  Scion agent pods

host:
  repo checkout
  subscription credentials
  optional restore/bootstrap scripts
```

## Why Kustomize First

The repository already applies native Kubernetes resources from `deploy/kind`
with:

```bash
kubectl --context kind-scion-ops apply -k deploy/kind
```

Kustomize keeps the local deployment inspectable with `kubectl`, avoids
premature chart values/API design, and matches the existing project preference
for native deployable resources. Helm can package the result later if we need a
versioned install/upgrade interface.

## Persistence Model

Deleting and recreating the kind cluster deletes any state that lives only in
cluster storage. An all-in-kind deployment needs an explicit persistence and
restore model.

| State | Required persistence | Notes |
|---|---|---|
| Hub database/state | PersistentVolumeClaim or external DB | Contains groves, agents, messages, broker registrations, templates, and Hub state. |
| Hub signing/session material | Kubernetes Secret restored from host or sealed/external secret | Rotating this invalidates sessions/tokens. |
| Broker credentials | Kubernetes Secret or re-register on bootstrap | Broker must keep or reacquire trust with Hub. |
| Grove identity | Host repo `.scion/grove-id` plus Hub state | Recreating either side incorrectly can create duplicate grove identity. |
| Subscription credentials | Kubernetes Secret sourced from host files or external secret store | Claude, Codex, and Gemini auth should not be baked into images. |
| MCP workspace | HostPath mount for local kind or cloned persistent workspace | MCP tools need repo access for git/task/artifact inspection. |
| Agent artifacts | Git pushes, explicit sync, or persistent workspace volume | Do not rely on ephemeral agent pod storage for useful work. |

For local development, prefer restoring secrets/configuration from the host
rather than treating kind as the durable source of truth.

## Proposed Resource Layout

Keep resources under `deploy/kind` so the current `task kind:up` path remains
the single apply point:

```text
deploy/kind/
  namespace.yaml
  rbac.yaml
  control-plane/
    hub-deployment.yaml
    hub-service.yaml
    hub-pvc.yaml
    broker-deployment.yaml
    broker-rbac.yaml
    mcp-deployment.yaml
    mcp-service.yaml
    kustomization.yaml
  kustomization.yaml
```

The first implementation should add only resources that can be validated in the
local kind cluster. Avoid placeholder manifests that are not applied by tests.

## Networking

Local kind control-plane services should start with ClusterIP services plus
`kubectl port-forward` or a controlled localhost binding. Exposing Hub or MCP
directly outside the machine should require an explicit follow-up with TLS and
authentication.

The MCP server should keep using HTTP transport. Zed can then connect through a
port-forwarded localhost URL:

```bash
kubectl --context kind-scion-ops -n scion-agents port-forward svc/scion-ops-mcp 8765:8765
```

## Broker Constraints

Containerizing the broker is the riskiest part. The broker needs enough access
to create agent pods and manage their lifecycle, but should not receive host
Podman socket access for this path. The first all-in-kind broker should support
only the Kubernetes runtime.

Key requirements:

- in-cluster Kubernetes API access through a service account
- namespace/RBAC for agent pods, `pods/exec`, `pods/log`, and secrets
- mounted or restored broker credentials
- image registry access for Scion agent images
- stable workspace strategy for agents and MCP

## Phased Implementation

1. Add Kustomize resources for Hub and its persistent state.
2. Add MCP deployment with repo/workspace access and HTTP service.
3. Add broker deployment using in-cluster Kubernetes auth.
4. Add bootstrap/restore tasks for secrets, grove identity, templates, and
   broker provide.
5. Extend `task smoke:e2e` or add a sibling smoke task that validates the
   kind-hosted control plane.
6. Consider Helm packaging only after the manifests pass local kind smoke tests
   and the required values are clear.

## Open Questions

- Should local kind use hostPath volumes for Hub/MCP state, or PVCs with backup
  and restore tasks?
- Should the MCP workspace be a hostPath mount of this repo or a clone inside a
  persistent volume?
- Which Hub storage backend should be considered durable enough for local
  recreation?
- Should dev auth remain local-only, or should the in-kind path require a
  production-style session/JWT secret from the start?
