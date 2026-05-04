# kind Runtime Substrate

`kind` is the supported local Kubernetes substrate for scion-ops. It runs the
base namespace/RBAC, the Scion control plane, MCP, and Scion agent pods.

## Base Resources

`deploy/kind` contains the base namespace and RBAC needed by Scion's Kubernetes
runtime:

```bash
kubectl --context kind-scion-ops apply -k deploy/kind
```

`task up` applies these resources before applying `deploy/kind/control-plane`.
The helper script does not embed Kubernetes YAML; resources remain native and
directly deployable.

## Defaults

| Setting | Value |
|---|---|
| kind cluster | `scion-ops` |
| kubectl context | `kind-scion-ops` |
| namespace | `scion-agents` |
| runtime service account | `scion-agent-manager` |
| image registry | `localhost` |
| workspace host path | current repo checkout |
| workspace node path | `/workspace/scion-ops` |
| Hub host URL | `http://127.0.0.1:18090` |
| MCP host URL | `http://127.0.0.1:8765/mcp` |

Override the cluster name with:

```bash
KIND_CLUSTER_NAME=scion-dev task up
```

## Workspace Mount

The kind node is created with an `extraMount` from the host checkout to
`/workspace/scion-ops`. The MCP Deployment mounts that node path as a
Kubernetes `hostPath`.

Existing kind clusters cannot be mutated to add the mount. Check it with:

```bash
task kind:workspace:status
```

If the mount is missing, recreate the local cluster:

```bash
task down
task up
```

## Native Ports

The kind node is also created with `extraPortMappings`:

| Host | kind node | Kubernetes Service |
|---|---|---|
| `127.0.0.1:18090` | `30090` | `scion-hub` NodePort |
| `127.0.0.1:8765` | `30876` | `scion-ops-mcp` NodePort |

Existing kind clusters cannot be mutated to add these mappings. If
`task kind:status` reports missing kind native ports, recreate the cluster with
`task down` and `task up`.

## Images

Build all images:

```bash
task build
```

`task up` loads the expected local image tags into kind:

```text
localhost/scion-base:latest
localhost/scion-ops-mcp:latest
localhost/scion-claude:latest
localhost/scion-codex:latest
localhost/scion-gemini:latest
```

If your kind provider cannot read locally built images directly, `task up`
falls back to exporting matching Podman images as temporary archives. You can
still load a specific archive manually with the implementation helper:

```bash
podman save localhost/scion-claude:latest -o /tmp/scion-claude.tar
task kind:load-archive -- /tmp/scion-claude.tar
```

## Diagnostics

The top-level check is:

```bash
task test
```

Lower-level Kubernetes checks remain available for debugging:

```bash
task kind:status
task kind:control-plane:status
task kind:mcp:status
task kind:broker:status
```
