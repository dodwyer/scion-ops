# Design: Update Web App

## Overview

This change has two concerns: aligning `scripts/web_app_hub.py` with the
updated `mcp_servers/scion_ops.py` module, and adding the web app to the
kind control-plane kustomize deployment so it is managed alongside hub, broker,
and MCP.

## MCP Alignment

### Port env-var workaround removal

`scion_ops.py` now defines `_env_port(name, default)` which accepts both a
plain integer string and a full URL string (extracting the port). Before this
helper existed, `web_app_hub.py` cleared `SCION_OPS_MCP_PORT` from the
environment at import time if it was not a plain digit string, to prevent
`FastMCP` from crashing during module initialisation.

Now that `scion_ops.py` handles this internally before constructing the
`FastMCP` instance, the workaround in `web_app_hub.py` must be removed. The
two lines that read and conditionally delete the env var are the only removal
needed.

### Final failure fields in round detail

`_final_review_outcome` in `scion_ops.py` now includes
`final_failure_classification` and `final_failure_evidence` in its return
dict. `web_app_hub.py` receives this data through
`scion_ops.scion_ops_round_status` and passes it into the round detail view.
The HTML template and JSON response for the round detail view must surface
these two fields when non-empty, alongside the existing `blocking_issues`
display.

### CONTROL_PLANE_NAMES

The set `CONTROL_PLANE_NAMES = {"scion-hub", "scion-broker", "scion-ops-mcp"}`
determines which Kubernetes deployments the runtime readiness view tracks. The
web app deployment (`scion-ops-web`) must be added so the overview correctly
shows degraded state when the web app itself is not ready.

## Kubernetes Deployment

### Image and entrypoint

The web app uses `localhost/scion-ops-mcp:latest` — the same image used by the
MCP deployment. No new image is required because both services import from the
same workspace hostPath mount and share the same Python dependency set. The
entrypoint for the web deployment sets `SCION_OPS_WEB_HOST=0.0.0.0` and runs
`scripts/web_app_hub.py`.

### Service and port mapping

Pattern follows the existing hub and MCP services:

| Component     | Container port | NodePort | Default host port | Env var                    |
|---------------|---------------|----------|-------------------|----------------------------|
| scion-hub     | 8090          | 30090    | 18090             | SCION_OPS_KIND_HUB_PORT    |
| scion-ops-mcp | 8765          | 30876    | 8765 (MCP_PORT)   | SCION_OPS_MCP_PORT         |
| scion-ops-web | 8787          | 30787    | 8787              | SCION_OPS_KIND_WEB_PORT    |

The Service is NodePort type. The kind cluster template gains a third
`extraPortMappings` entry: `containerPort: 30787`, `hostPort: __WEB_HOST_PORT__`.

### kustomization.yaml

`deploy/kind/control-plane/kustomization.yaml` gains two new resources:

```
- web-service.yaml
- web-deployment.yaml
```

No new configMapGenerator entry is needed; the web app reads configuration
solely from environment variables.

### kind-scion-runtime.sh and Taskfile.yml

`scripts/kind-scion-runtime.sh` adds:

```sh
WEB_HOST_PORT="${SCION_OPS_KIND_WEB_PORT:-8787}"
WEB_NODE_PORT="30787"
```

The sed substitutions for the cluster template and the port-binding validation
logic gain `__WEB_HOST_PORT__` and `__WEB_NODE_PORT__` counterparts.

`Taskfile.yml` adds a `SCION_OPS_KIND_WEB_PORT` variable in the `vars` block
following the existing `SCION_OPS_KIND_HUB_PORT` pattern.

## Verification Strategy

- Run `task lint` (or equivalent static check) to confirm Python parse passes
  for the modified `web_app_hub.py`.
- Run `uv run scripts/test-web-app-hub.py` to confirm the web app unit tests
  pass with the workaround removed.
- Confirm `CONTROL_PLANE_NAMES` includes `scion-ops-web` by reading the set
  in the modified file.
- Inspect `deploy/kind/control-plane/kustomization.yaml` to confirm web
  resources are listed.
- Inspect `deploy/kind/cluster.yaml.tpl` to confirm the web port mapping
  placeholder is present.
- A smoke check of `task kind:control-plane:apply` on a running kind cluster
  confirms the web deployment rolls out and the NodePort is reachable.
