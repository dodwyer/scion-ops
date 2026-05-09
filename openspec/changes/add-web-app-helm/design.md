# Design: Add Web App Hub to Kind Deployment

## Overview

The scion-ops web dashboard is already implemented and merged. This change wires it into the kind deployment as a 4th control-plane service. The approach mirrors the scion-ops-mcp pattern: dedicated image, Kubernetes Deployment + NodePort Service, kind cluster port mapping, and Taskfile integration. No changes to the web app itself are required.

## Open Questions — Resolved Decisions

### a. Image strategy

**Decision: new `image-build/scion-ops-web/` directory with a dedicated Dockerfile.**

Rationale: the MCP image carries MCP transport dependencies, the npm `@fission-ai/openspec` global, and MCP-specific entrypoint logic that the web app does not need. A dedicated image keeps the web service independently restartable, avoids coupling image rebuilds, and stays consistent with the single-responsibility principle already applied to `scion-ops-mcp`. The new image is a thin Python layer over `localhost/scion-base:latest` that installs only `mcp>=1.13,<2` and `PyYAML>=6,<7`.

### b. NodePort and host port

**Decision: NodePort 30787, host port 18787.**

The port number 8787 (default `SCION_OPS_WEB_PORT`) maps naturally to NodePort 30787 and host port 18787, following the same convention as hub (8090 → 30090 → 18090) and mcp (8765 → 30876 → 8765). The cluster template and Taskfile gain `__WEB_NODE_PORT__` / `__WEB_HOST_PORT__` variables.

### c. RBAC

**Decision: dedicated `ServiceAccount: scion-ops-web`.**

The web app reads Hub and Kubernetes state but has a different trust profile than the MCP server. A dedicated ServiceAccount allows independent RBAC scope now and avoids entanglement if the MCP account's permissions change later. Pattern matches the existing per-component accounts.

### d. Hub auth secret

**Decision: mount the `scion-hub-dev-auth` secret as an environment variable, same as scion-ops-mcp.**

The web app connects to the Hub API using the same dev-auth token. Sharing the secret mount pattern is consistent and avoids a second secret.

### e. Build and image-load integration

**Decision: add `build:web` as a new Taskfile task and include it in `kind:load-images`.**

This follows the same structure as `build:mcp`. The `build:web` task runs `docker build` targeting `image-build/scion-ops-web/`. The `kind:load-images` script (called via `scripts/kind-scion-runtime.sh load-images`) includes the new `localhost/scion-ops-web:latest` image alongside existing images.

### f. Smoke test

**Decision: extend `task test` to verify the web endpoint.**

The smoke test script (`scripts/kind-control-plane-smoke.py`) gains a step that sends an HTTP GET to `http://<KIND_LISTEN_ADDRESS>:<WEB_HOST_PORT>/` and asserts a 200 response. This matches the existing MCP reachability check pattern.

## Component Diagram

```
Host (port 18787)
    │  kind extraPortMappings
    ▼
kind node (NodePort 30787)
    │  scion-ops-web Service
    ▼
scion-ops-web Pod (port 8787)
    │  SCION_OPS_WEB_HOST=0.0.0.0
    │  SCION_OPS_WEB_PORT=8787
    │  SCION_OPS_HUB_ENDPOINT=http://scion-hub:8090
    │  scion-hub-dev-auth secret
    ▼
scripts/web_app_hub.py
    │  reads
    ├──► Hub API (scion-hub:8090)
    ├──► MCP (scion-ops-mcp:8765)
    └──► Kubernetes API (in-cluster)
```

## New Files

| Path | Purpose |
|------|---------|
| `image-build/scion-ops-web/Dockerfile` | Container image for web app hub |
| `deploy/kind/control-plane/web-rbac.yaml` | ServiceAccount for scion-ops-web |
| `deploy/kind/control-plane/web-deployment.yaml` | Deployment for web app |
| `deploy/kind/control-plane/web-service.yaml` | NodePort Service at 30787 |

## Modified Files

| Path | Change |
|------|--------|
| `deploy/kind/control-plane/kustomization.yaml` | Add web-rbac, web-deployment, web-service resources |
| `deploy/kind/cluster.yaml.tpl` | Add `__WEB_NODE_PORT__` / `__WEB_HOST_PORT__` extraPortMappings entry |
| `scripts/kind-scion-runtime.sh` | Render `__WEB_NODE_PORT__` and `__WEB_HOST_PORT__` template variables |
| `Taskfile.yml` | Add `SCION_OPS_KIND_WEB_PORT` var, `build:web` task, include web image in `kind:load-images`, extend smoke test |
| `scripts/kind-control-plane-smoke.py` | Add web endpoint HTTP 200 check |

## Deployment Environment Variables

The web app container receives:

```
SCION_OPS_WEB_HOST=0.0.0.0
SCION_OPS_WEB_PORT=8787
SCION_OPS_HUB_ENDPOINT=http://scion-hub:8090
SCION_HUB_ENDPOINT=http://scion-hub:8090
```

The auth token is injected from `scion-hub-dev-auth` secret using the same `valueFrom.secretKeyRef` pattern as scion-ops-mcp.

## Verification Strategy

- `task build:web` produces `localhost/scion-ops-web:latest`.
- `task up` loads the image, applies manifests, and the web pod reaches Running.
- `task test` passes the new web endpoint smoke check.
- `curl http://<KIND_LISTEN_ADDRESS>:18787/` returns HTTP 200 from the host.
- Existing hub, broker, and mcp services remain unaffected (existing smoke checks continue to pass).
