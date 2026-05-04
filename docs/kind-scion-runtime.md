# Local kind Runtime

This project uses `kind` as the local Kubernetes target for Scion agent runtime
testing. In the current default workflow, kind runs agent pods while Hub,
broker, and MCP stay on the host. The proposed all-in-kind control-plane path
is documented separately in `docs/kind-control-plane.md`.

## Responsibility Split

Scion does not bootstrap the local Kubernetes substrate for us. Once configured
with a Kubernetes runtime, Scion creates and manages agent runtime objects such
as pods and secrets in the configured namespace. This project is responsible for
the local setup around that runtime: the kind cluster, namespace, and minimum
RBAC needed by Scion.

These manifests are intentionally native Kustomize resources. Do not move this
path to Helm unless the kind control-plane resource model has stabilized and we
need packaged install/upgrade behavior.

Those Kubernetes resources live in `deploy/kind` and are directly deployable:

```bash
kubectl --context kind-scion-ops apply -k deploy/kind
```

`task kind:up` creates or reuses the kind cluster, then applies that
kustomization. The helper script should not contain embedded Kubernetes YAML.

## Defaults

| Setting | Value |
|---|---|
| kind cluster | `scion-ops` |
| kubectl context | `kind-scion-ops` |
| agent namespace | `scion-agents` |
| RBAC service account | `scion-agent-manager` |
| Scion profile | `kind` |
| Scion runtime | `kubernetes` |
| image registry | `localhost` |

Override the cluster name with an environment variable:

```bash
KIND_CLUSTER_NAME=scion-dev task kind:up
```

For a different namespace or service account, create a kustomize overlay and
run with matching `SCION_K8S_MANIFEST_DIR`, `SCION_K8S_NAMESPACE`, and
`SCION_K8S_SERVICE_ACCOUNT` values.

## Create the Cluster

Prerequisites:

- `kind`
- `kubectl`
- `yq` for `task kind:configure-scion`

```bash
task kind:up
```

The task is idempotent. It creates the cluster if missing, reuses it if present,
applies the `deploy/kind` Kubernetes resources, and sets the kind context
namespace.

Check the result:

```bash
task kind:status
kubectl --context kind-scion-ops get pods -n scion-agents
```

## Configure Scion Diagnostics

Configure a global Scion profile named `kind`. This step uses `yq` because the
current `scion config set` command does not support nested runtime/profile
keys:

```bash
task kind:configure-scion
```

This writes:

```yaml
image_registry: localhost
runtimes:
  kubernetes:
    type: kubernetes
    context: kind-scion-ops
    namespace: scion-agents
profiles:
  kind:
    runtime: kubernetes
```

Run Scion's Kubernetes diagnostics:

```bash
task kind:doctor
```

This validates cluster connectivity, namespace access, pod permissions,
`pods/exec`, pod logs, and secret permissions.

## Load Agent Images

Build the Scion images locally:

```bash
task images:build
```

Load the images into kind:

```bash
task kind:load-images -- \
  localhost/scion-base:latest \
  localhost/scion-claude:latest \
  localhost/scion-codex:latest \
  localhost/scion-gemini:latest
```

If the images were built with Podman but your kind provider cannot see them as
Docker images, export archives and load those instead:

```bash
podman save localhost/scion-claude:latest -o /tmp/scion-claude.tar
task kind:load-archive -- /tmp/scion-claude.tar
```

For repeated local development, a local registry can replace `kind load`. If
the all-in-kind control plane adopts a registry, document it in
`docs/kind-control-plane.md` as part of the persistence/bootstrap model.

## Cleanup

```bash
task kind:down
```

This deletes the kind cluster named by `KIND_CLUSTER_NAME`.
