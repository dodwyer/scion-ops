# Local kind Runtime

This project uses `kind` as the local Kubernetes target for Scion runtime
testing. This is the substrate for later Hub/Broker work: issue #1 only creates
the cluster, namespace, RBAC, and image-loading path.

## Responsibility Split

Scion does not bootstrap the local Kubernetes substrate for us. Once configured
with a Kubernetes runtime, Scion creates and manages agent runtime objects such
as pods and secrets in the configured namespace. This project is responsible for
the local setup around that runtime: the kind cluster, namespace, and minimum
RBAC needed by Scion.

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
runtimes:
  kind:
    type: kubernetes
    context: kind-scion-ops
    namespace: scion-agents
profiles:
  kind:
    runtime: kind
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

For repeated local development, a local registry can replace `kind load`, but
that should be introduced with the broker/runtime issue if we need it.

## Cleanup

```bash
task kind:down
```

This deletes the kind cluster named by `KIND_CLUSTER_NAME`.
