# kind Control Plane Deployment

Status: first Hub-only slice implemented. The local kind workspace mount
substrate for a future MCP Deployment is in place. Broker and MCP Kubernetes
resources are still pending.

This is the path for running the Scion control plane inside the local kind
cluster. The current default remains host-managed Hub, broker, and MCP with kind
used only for agent pods.

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

## Implemented Hub Slice

The first slice adds a separate Kustomize target under
`deploy/kind/control-plane` for a Hub/Web process only. It is not included by
`task kind:up`, so the existing host-managed Hub workflow stays the default.

Resources:

- `deploy/kind/control-plane/hub-deployment.yaml`
- `deploy/kind/control-plane/hub-config.yaml`
- `deploy/kind/control-plane/hub-service.yaml`
- `deploy/kind/control-plane/hub-pvc.yaml`

Apply and verify:

```bash
task kind:up
task kind:workspace:status
task kind:load-images -- localhost/scion-base:latest
task kind:control-plane:apply
task kind:control-plane:status
```

If `localhost/scion-base:latest` has not been built locally, build it first
with `task images:build` and then load it into kind.

The Hub-specific task names remain available as narrow aliases:

```bash
task kind:hub:apply
task kind:hub:status
task kind:hub:logs
```

To inspect the Hub HTTP endpoint from the host, use a local-only port-forward:

```bash
kubectl --context kind-scion-ops -n scion-agents port-forward svc/scion-hub 18090:8090
curl http://127.0.0.1:18090/healthz
```

The Service is ClusterIP-only. There is no host port binding unless the
port-forward is running.

Remove the experimental control-plane resources with:

```bash
task kind:control-plane:delete
```

This deletes resources from `deploy/kind/control-plane`. It does not delete the
kind cluster or the base agent-runtime resources from `deploy/kind`.

The Hub stores its mutable global Scion directory, SQLite database, dev token,
templates, and local storage directory on the `scion-hub-state` PVC. The
minimal `settings.yaml` comes from the `scion-hub-settings` ConfigMap so the
required `image_registry: localhost` setting is reproducible from this repo.
Deleting the kind cluster deletes the PVC-backed state.

This first slice intentionally runs `scion --global server start` in explicit
component mode with `--production --enable-hub --enable-web --dev-auth`:
production mode prevents workstation defaults from starting the broker
automatically, while dev auth keeps the local kind deployment usable without
OAuth setup. The Deployment overrides the `scion-base` agent entrypoint and
runs the Hub process directly as UID/GID 1000 because `sciontool init` is for
agent containers. The web session secret is still auto-generated per pod start
and is not production-ready.

## MCP Workspace Mount Substrate

The MCP server needs a live `scion-ops` workspace for git, task, Scion, and
artifact inspection. In kind, a pod `hostPath` volume sees the kind node
filesystem, not the developer workstation filesystem directly. For local kind
clusters, `task kind:up` now creates the cluster with a kind `extraMount`:

| Side | Default path |
|---|---|
| Host checkout | repo root |
| kind node | `/workspace/scion-ops` |

The future MCP Deployment can mount the node path as a Kubernetes `hostPath`.
This is intentionally limited to local kind. For non-kind clusters, use a
cloned workspace or persistent workspace volume instead of a workstation bind
mount.

Existing kind clusters cannot be updated with new `extraMounts`. Verify the
substrate before deploying MCP resources:

```bash
task kind:workspace:status
```

If the mount is missing, recreate only the local kind cluster:

```bash
task kind:down
task kind:up
```

## Relationship To Existing Docs

- `docs/kind-scion-runtime.md` documents the current kind substrate and agent
  runtime resources.
- `docs/local-hub-mode.md` documents the current host-managed Hub/Web/Broker
  workflow.
- `docs/kind-broker-runtime.md` documents the current host-managed broker
  providing the `kind` Kubernetes profile.
- `docs/zed-mcp.md` documents the current host/remote HTTP MCP registration
  path; a kind-hosted MCP service should expose the same HTTP URL shape through
  port-forwarding or controlled ingress.
- `docs/testing-plan.md` documents the current end-to-end smoke; the all-in-kind
  deployment should add a sibling smoke rather than overloading that default
  until it is stable.

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

This is an intentional exception to the general project standard that
Kubernetes resources are typically packaged with Helm. It is documented in
`KNOWNISSUES.md` and remains valid only while the local kind control-plane
configuration stays small, native, and reproducible from this repo.

If the deployment needs a chart, console-applied Helm releases should be
managed through a helmfile.

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
| MCP workspace | HostPath mount through the kind node for local kind, or cloned persistent workspace outside kind | MCP tools need repo access for git/task/artifact inspection. |
| Agent artifacts | Git pushes, explicit sync, or persistent workspace volume | Do not rely on ephemeral agent pod storage for useful work. |

For local development, prefer restoring secrets/configuration from the host
rather than treating kind as the durable source of truth.

## Resource Layout

Keep resources under `deploy/kind`. The experimental control-plane target is
separate from the current `task kind:up` target until the full all-in-kind path
has passed smoke tests:

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

The first resource implementation adds only the Hub resources. The workspace
mount substrate is part of kind cluster creation, not a Kubernetes manifest.
Avoid placeholder manifests that are not applied by tests.

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

1. Add Kustomize resources for Hub and its persistent state. Done for the
   Hub-only slice.
2. Add local kind workspace mount substrate for MCP repo access. Done.
3. Add MCP deployment with repo/workspace access and HTTP service.
4. Add broker deployment using in-cluster Kubernetes auth.
5. Add bootstrap/restore tasks for secrets, grove identity, templates, and
   broker provide.
6. Extend `task smoke:e2e` or add a sibling smoke task that validates the
   kind-hosted control plane.
7. Consider Helm packaging only after the manifests pass local kind smoke tests
   and the required values are clear.

## Open Questions

- Should local kind use hostPath volumes for Hub/MCP state, or PVCs with backup
  and restore tasks?
- Outside local kind, should the MCP workspace be a clone inside a persistent
  volume or restored through another workspace bootstrap path?
- Which Hub storage backend should be considered durable enough for local
  recreation?
- How should the in-kind path restore a stable session/JWT secret before it is
  used beyond local development?
