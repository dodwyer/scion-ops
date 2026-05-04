# kind Control Plane Deployment

Status: Hub, co-located Runtime Broker, and MCP slices implemented for local
kind. A separate broker Deployment remains a future bootstrap task.

This is the path for running the Scion control plane inside the local kind
cluster. The current default remains host-managed Hub, broker, and MCP with kind
used only for agent pods.

## Direction

Use native Kubernetes resources managed by Kustomize first. Do not introduce a
Helm chart until the resource model is proven and stable.

The target shape is:

```text
kind cluster:
  Scion Hub/API/Web with co-located Runtime Broker
  scion-ops HTTP MCP server
  Scion agent pods

host:
  repo checkout
  subscription credentials
  optional restore/bootstrap scripts
```

## Implemented Control-Plane Slices

The control-plane slices add a separate Kustomize target under
`deploy/kind/control-plane` for Hub/Web, a co-located Runtime Broker, and the
scion-ops HTTP MCP server. It is not included by `task kind:up`, so the
existing host-managed Hub workflow stays the default.

Resources:

- `deploy/kind/control-plane/hub-deployment.yaml`
- `deploy/kind/control-plane/hub-config.yaml`
- `deploy/kind/control-plane/hub-service.yaml`
- `deploy/kind/control-plane/hub-pvc.yaml`
- `deploy/kind/control-plane/broker-rbac.yaml`
- `deploy/kind/control-plane/broker-kubeconfig.yaml`
- `deploy/kind/control-plane/mcp-deployment.yaml`
- `deploy/kind/control-plane/mcp-service.yaml`

Apply and verify:

```bash
task kind:up
task kind:workspace:status
task kind:load-images -- localhost/scion-base:latest localhost/scion-ops-mcp:latest
task kind:control-plane:apply
task kind:control-plane:status
task kind:broker:status
```

If the images have not been built locally, build them first with
`task images:build` and then load them into kind.

The Hub/broker-specific task names remain available as narrow aliases:

```bash
task kind:hub:apply
task kind:hub:status
task kind:hub:logs
task kind:hub:port-forward
eval "$(task kind:hub:auth-export)"
task kind:broker:status
task kind:broker:logs
```

MCP-specific status, logs, and port-forward helpers are also available:

```bash
task kind:mcp:status
task kind:mcp:logs
task kind:mcp:port-forward
task kind:mcp:smoke
```

Run the end-to-end kind control-plane smoke with:

```bash
task kind:control-plane:smoke
```

The smoke creates or reuses the kind runtime substrate, applies the
control-plane Kustomize target, reads the dev-auth token from the Hub pod,
starts temporary local port-forwards for Hub and MCP if needed, links the
current grove to the kind Hub, makes the co-located broker the current grove's
default provider, checks the kind-hosted MCP Hub status, dispatches a no-auth
generic smoke agent, verifies that a pod appears in kind, and deletes the smoke
agent after a successful run.

The bootstrap is intentionally one-off. It passes `--hub` or
`SCION_HUB_ENDPOINT` to Scion commands and does not run `task hub:link` or
`scion config set hub.endpoint`, so the host's global Scion Hub endpoint is not
rewritten. It does create or update current-grove state inside the kind Hub PVC.
By default it uses Scion's inline config support with the `generic` harness and
does not upload templates or harness configs. Pass `--template` to use an
existing Hub template, `--sync-template` to upload that template first, and
`--sync-harness-config` only when you explicitly want to test Hub
harness-config upload as well. Template and harness uploads require a Hub
storage backend that supports remote uploads; local kind Hub state uses local
storage and is not a reliable target for host-side upload sync.

Useful overrides:

| Variable | Default |
|---|---|
| `SCION_KIND_CP_SMOKE_TEMPLATE` | unset, uses inline generic config |
| `SCION_KIND_CP_SMOKE_AGENT` | generated `kind-cp-smoke-*` name |
| `SCION_KIND_CP_SMOKE_KEEP_AGENT` | unset, deletes on success |
| `SCION_KIND_CP_SMOKE_SKIP_SETUP` | unset, applies kind resources |
| `SCION_KIND_CP_SMOKE_SYNC_TEMPLATE` | unset, no template upload |
| `SCION_KIND_CP_SMOKE_SYNC_HARNESS_CONFIG` | unset, no harness-config upload |
| `SCION_KIND_CP_SMOKE_TIMEOUT` | `90` |
| `SCION_OPS_KIND_HUB_PORT` | `18090` |
| `SCION_OPS_MCP_URL` | `http://127.0.0.1:8765/mcp` |

Pass `--skip-setup` when the kind cluster and control plane are already applied,
`--no-port-forward` when you want to manage the Hub and MCP port-forwards in
separate terminals, or `--skip-bootstrap` when the current grove and broker
provider already exist in the kind Hub. Pass `--skip-mcp` to verify only the Hub
and co-located broker dispatch path; in that mode the script uses the Hub-only
apply/status tasks and does not require the kind workspace mount.

To inspect the Hub HTTP endpoint from the host, use a local-only port-forward:

```bash
task kind:hub:port-forward
```

In another terminal, export the matching endpoint and dev-auth token:

```bash
eval "$(task kind:hub:auth-export)"
curl http://127.0.0.1:18090/healthz
```

The Service is ClusterIP-only. There is no host port binding unless the
port-forward is running. Override the local port with
`SCION_OPS_KIND_HUB_PORT`.

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

The Hub slice intentionally runs `scion --global server start` in explicit
component mode with `--production --enable-hub --enable-web
--enable-runtime-broker --dev-auth`. Production mode avoids workstation
defaults, while the explicit Runtime Broker flag uses Scion's built-in
co-located Hub+broker path. That path creates the broker record and HMAC secret
inside Hub state, so the local kind deployment does not need a custom broker
registration sidecar.

The broker binds to `127.0.0.1` inside the Hub pod and is not exposed as a
Service. It uses the `kind` profile from `scion-hub-settings`, an in-cluster
kubeconfig ConfigMap, and the `scion-control-plane` service account to create
agent pods in `scion-agents`. The Deployment overrides the `scion-base` agent
entrypoint and runs the Hub process directly as UID/GID 1000 because
`sciontool init` is for agent containers. The web session secret is still
auto-generated per pod start and is not production-ready.

## MCP Workspace Mount Substrate

The MCP server needs a live `scion-ops` workspace for git, task, Scion, and
artifact inspection. In kind, a pod `hostPath` volume sees the kind node
filesystem, not the developer workstation filesystem directly. For local kind
clusters, `task kind:up` now creates the cluster with a kind `extraMount`:

| Side | Default path |
|---|---|
| Host checkout | repo root |
| kind node | `/workspace/scion-ops` |

The MCP Deployment mounts the node path as a Kubernetes `hostPath`. This is
intentionally limited to local kind. For non-kind clusters, use a cloned
workspace or persistent workspace volume instead of a workstation bind mount.

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

The MCP image is `localhost/scion-ops-mcp:latest`. It is built from
`image-build/scion-ops-mcp/Dockerfile` on top of `scion-base`, adding `task`
and the Python MCP dependencies while running the server from the mounted
workspace. The Deployment reads Hub state through the `scion-hub` ClusterIP
service and reads the local dev-auth token from the Hub PVC mounted read-only at
`/hub-state`.

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
| Broker credentials | Co-located broker secret in Hub state for the current kind slice; Kubernetes Secret or registration bootstrap for a future separate broker | Broker must keep or reacquire trust with Hub. |
| Grove identity | Host repo `.scion/grove-id` plus Hub state | Recreating either side incorrectly can create duplicate grove identity. |
| Subscription credentials | Kubernetes Secret sourced from host files or external secret store | Claude, Codex, and Gemini auth should not be baked into images. |
| MCP workspace | HostPath mount through the kind node for local kind, or cloned persistent workspace outside kind | MCP tools need repo access for git/task/artifact inspection. The local kind MCP mount is read-write. |
| MCP Hub auth | Read-only view of Hub PVC dev token for local kind, restored Secret outside kind | The current local slice depends on Hub dev auth and is not production-ready. |
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
    broker-kubeconfig.yaml
    broker-rbac.yaml
    hub-config.yaml
    hub-deployment.yaml
    hub-service.yaml
    hub-pvc.yaml
    mcp-deployment.yaml
    mcp-service.yaml
    kustomization.yaml
  kustomization.yaml
```

Implemented resources are Hub, co-located broker RBAC/kubeconfig, and MCP. The
workspace mount substrate is part of kind cluster creation, not a Kubernetes
manifest. Avoid placeholder manifests that are not applied by tests.

## Networking

Local kind control-plane services should start with ClusterIP services plus
`kubectl port-forward` or a controlled localhost binding. Exposing Hub or MCP
directly outside the machine should require an explicit follow-up with TLS and
authentication.

The MCP server should keep using HTTP transport. Zed can then connect through a
port-forwarded localhost URL:

```bash
task kind:mcp:port-forward
```

In another terminal, smoke test the forwarded service:

```bash
task kind:mcp:smoke
```

## Broker Constraints

Containerizing the broker is the riskiest part. The broker needs enough access
to create agent pods and manage their lifecycle, but should not receive host
Podman socket access for this path. The first all-in-kind broker runs
co-located in the Hub pod and supports only the Kubernetes runtime.

Key requirements:

- in-cluster Kubernetes API access through a service account
- namespace/RBAC for agent pods, `pods/exec`, `pods/log`, and secrets
- co-located broker HMAC secret in Hub state
- image registry access for Scion agent images
- stable workspace strategy for agents and MCP

A separate broker Deployment remains out of scope until there is an explicit
broker credential restore or registration bootstrap flow.

## Phased Implementation

1. Add Kustomize resources for Hub and its persistent state. Done.
2. Add local kind workspace mount substrate for MCP repo access. Done.
3. Add MCP deployment with repo/workspace access and HTTP service. Done for the
   local kind slice.
4. Add co-located broker support using in-cluster Kubernetes auth. Done for the
   local kind slice.
5. Add bootstrap/restore tasks for secrets, grove identity, templates, and
   future separate broker provide.
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
- Should a future separate Runtime Broker be bootstrapped from a restored
  Kubernetes Secret or from a registration job once Scion supports that flow?
