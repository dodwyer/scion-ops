# Design: Update Web App

## Overview

This change promotes the scion-ops web app hub from a local development script to a properly deployed Kubernetes workload aligned with the MCP service conventions already in place. The scope is: deploy the web app in the kind control plane and fix the two environment configuration gaps that prevent it from working in-cluster.

## Configuration Gaps

Two specific gaps must be closed before the web app can operate in-cluster:

1. **MCP URL default**: `scripts/web_app_hub.py` defaults `SCION_OPS_MCP_URL` to a hardcoded development IP (`http://192.168.122.103:8765/mcp`). In-cluster this must resolve to the MCP service by DNS name: `http://scion-ops-mcp:8765/mcp`.
2. **Web host default**: `scripts/web_app_hub.py` defaults `SCION_OPS_WEB_HOST` to `127.0.0.1`. The in-cluster Deployment must bind to `0.0.0.0`.

Both of these should be corrected by providing the appropriate environment variables in the Deployment manifest rather than changing code defaults, which preserves the existing local development behaviour.

## Image Strategy

The web app script imports `mcp_servers.scion_ops` from the repository root and uses only the Python standard library plus the same `mcp` and `PyYAML` dependencies already installed in the `scion-ops-mcp` image. No separate Dockerfile is required. The `scion-ops-mcp` image should be reused as the container image for the web app Deployment, with the entrypoint overridden to run `scripts/web_app_hub.py` instead of `mcp_servers/scion_ops.py`.

This avoids adding a new image build target and keeps the dependency surface identical to the MCP service.

## Kubernetes Manifests

The following new manifests are required under `deploy/kind/control-plane/`:

### web-deployment.yaml

A `Deployment` named `scion-ops-web` in the `scion-agents` namespace. Key characteristics:

- Uses image `localhost/scion-ops-mcp:latest` with `imagePullPolicy: IfNotPresent`.
- Overrides the entrypoint to `python /workspace/scion-ops/scripts/web_app_hub.py`.
- Sets the same security context as the MCP deployment (UID/GID 1000, non-root, no privilege escalation).
- Mounts the workspace volume (hostPath `/workspace`) so the script can import `mcp_servers.scion_ops`.
- Mounts the `hub-dev-auth` secret to `/run/secrets/scion-hub-dev-auth` to provide `SCION_DEV_TOKEN_FILE`.
- Sets environment variables: `HOME`, `USER`, `LOGNAME`, `SHELL`, `SCION_OPS_ROOT`, `SCION_OPS_HUB_ENDPOINT`, `SCION_HUB_ENDPOINT`, `SCION_DEV_TOKEN_FILE`, `SCION_OPS_MCP_URL` (in-cluster value), `SCION_OPS_WEB_HOST` (`0.0.0.0`), `SCION_OPS_WEB_PORT`, `SCION_K8S_NAMESPACE`, `DO_NOT_TRACK`, `OPENSPEC_TELEMETRY`.
- Exposes containerPort 8787 named `http`.
- Readiness and liveness probes on HTTP GET `/` at port `http`.
- Same resource requests/limits shape as the MCP service.

### web-service.yaml

A `Service` named `scion-ops-web` with `type: NodePort`, exposing port 8787 to targetPort `http` and nodePort 30787.

### web-rbac.yaml

A `ServiceAccount`, `Role`, and `RoleBinding` named `scion-ops-web`. The Role grants the same read-only pod permissions as the MCP RBAC (get/list pods, get pod logs) plus get/list on deployments, services, and persistent volume claims, since the web app calls `kubectl get deploy,pod,svc,pvc`.

## Kind Cluster Template

`deploy/kind/cluster.yaml.tpl` must gain a third port mapping entry:

```yaml
- containerPort: __WEB_NODE_PORT__
  hostPort: __WEB_HOST_PORT__
  listenAddress: "__KIND_LISTEN_ADDRESS__"
  protocol: TCP
```

`scripts/kind-scion-runtime.sh` must introduce `WEB_NODE_PORT=30787` and `WEB_HOST_PORT` (defaulting to `SCION_OPS_WEB_PORT` or `8787`), and apply the new substitutions. The port-binding verification and status output should include the web app port alongside hub and MCP.

## Kustomization

`deploy/kind/control-plane/kustomization.yaml` must list the three new manifests:

```yaml
- web-rbac.yaml
- web-service.yaml
- web-deployment.yaml
```

The `configMapGenerator` section does not require changes.

## Verification Strategy

- `kubectl apply -k deploy/kind/control-plane` succeeds without manual manifest additions.
- The web app pod reaches Ready state and the readiness probe succeeds.
- A request to `http://<kind-host>:8787/` returns an HTTP 200 response.
- The web app correctly shows the in-cluster hub and MCP status (no DNS or auth errors in the overview page).
- The kind cluster creation template substitution includes web port bindings and the smoke checks verify they are present.
