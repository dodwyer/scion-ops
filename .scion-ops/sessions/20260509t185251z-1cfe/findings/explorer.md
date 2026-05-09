# Explorer Findings: update-web-app

## Scope

Goal: align the existing web app with the MCP service changes for Scion, and include the web app in the kustomize/kind install.

Artifact boundary honored: this explorer only writes this findings file.

## Current Web App State

- Existing app entry point: `scripts/web_app_hub.py`.
- Runtime shape: single-file Python `ThreadingHTTPServer`, read-only UI plus JSON endpoints.
- Local task: `task web:hub` runs `uv run scripts/web_app_hub.py`.
- Defaults: `SCION_OPS_WEB_HOST=127.0.0.1`, `SCION_OPS_WEB_PORT=8787`.
- Test coverage: `scripts/test-web-app-hub.py`, included in `task verify`.

The app already aligns with the newer Hub-backed MCP direction in several important places:

- `RuntimeProvider.hub_status()` delegates to `mcp_servers.scion_ops.scion_ops_hub_status()`.
- Messages and notifications are read through `scion_ops.HubClient`.
- Round detail delegates to `scion_ops_round_status()` and `scion_ops_round_events()`.
- Kubernetes status uses the same namespace/context helper path from `scion_ops`.
- The read-only boundary is enforced by rejecting POST/PUT/PATCH/DELETE with HTTP 405.

Key references:

- `scripts/web_app_hub.py:328` defines `RuntimeProvider`.
- `scripts/web_app_hub.py:647` builds the overview snapshot from Hub, messages, notifications, MCP, and Kubernetes.
- `scripts/web_app_hub.py:685` builds round detail from MCP-backed round status/events.
- `scripts/web_app_hub.py:933` rejects mutation methods.
- `scripts/web_app_hub.py:977` defines CLI/env defaults for host and port.

## Current MCP/Scion Alignment State

The MCP service is already Scion Hub API backed:

- Hub config resolves endpoint, grove id, and auth from env, settings, token files, and `.scion/grove-id`.
- `HubClient` reads Scion Hub health, grove, providers, brokers, agents, messages, and notifications.
- MCP tools expose Hub status, agents, round status, and round event cursors.
- Round status includes normalized outcome/final-review state and transcript fallback through `scion_ops_look`.

Key references:

- `mcp_servers/scion_ops.py:665` resolves Hub config.
- `mcp_servers/scion_ops.py:715` defines `HubClient`.
- `mcp_servers/scion_ops.py:1685` exposes `scion_ops_hub_status`.
- `mcp_servers/scion_ops.py:1776` exposes `scion_ops_round_status`.
- `mcp_servers/scion_ops.py:1827` exposes `scion_ops_round_events`.

Alignment gap: the web app still duplicates some normalization and branch/final-review parsing locally instead of using shared MCP helper output everywhere. This is functional today, but it can drift if Scion changes Hub payload field names again.

## Current Kind/Kustomize State

The kind install currently deploys Hub, broker, and MCP only.

- Top-level `deploy/kind/kustomization.yaml` includes only namespace and runtime RBAC.
- `deploy/kind/control-plane/kustomization.yaml` includes broker, hub, and MCP resources.
- `Taskfile.yml` applies `deploy/kind/control-plane` directly for control-plane resources.
- `Taskfile.yml` rollout/status/log tasks include `scion-hub`, `scion-broker`, and `scion-ops-mcp`.
- Kind native port mappings expose Hub and MCP only.
- The build script builds `localhost/scion-ops-mcp:latest` only for this repo-specific service image.

Key references:

- `deploy/kind/kustomization.yaml:4` includes only `namespace.yaml` and `rbac.yaml`.
- `deploy/kind/control-plane/kustomization.yaml:4` lists current control-plane resources.
- `deploy/kind/cluster.yaml.tpl:5` maps Hub and MCP ports only.
- `Taskfile.yml:67` `task up` loads images and applies/restarts/statuses current control plane.
- `Taskfile.yml:248` applies `deploy/kind/control-plane`.
- `Taskfile.yml:251` restarts only Hub, broker, and MCP.
- `Taskfile.yml:260` statuses only Hub, broker, and MCP.
- `scripts/build-images.sh:168` builds only the MCP repo-specific image.
- `image-build/scion-ops-mcp/Dockerfile:30` starts only the MCP server.

## Files Expected For Implementation

Likely product files to change:

- `scripts/web_app_hub.py`: reduce drift with MCP/Scion helpers if needed; ensure in-cluster defaults work without host-only assumptions.
- `scripts/test-web-app-hub.py`: add fixtures for any new Scion payload fields or in-cluster web runtime behavior.
- `image-build/...`: add a web app image or broaden the existing MCP image into a reusable scion-ops service image.
- `scripts/build-images.sh`: build/load the new web app image.
- `deploy/kind/control-plane/web-app-deployment.yaml`: new Deployment for the web app.
- `deploy/kind/control-plane/web-app-service.yaml`: new Service, probably NodePort if the app should be directly reachable like Hub/MCP.
- `deploy/kind/control-plane/kustomization.yaml`: include the new web resources.
- `deploy/kind/cluster.yaml.tpl`: add an extraPortMapping if normal web access should avoid port-forwarding.
- `scripts/kind-scion-runtime.sh`: add default host/node port variables, substrate validation, status output, and help text for the web app.
- `Taskfile.yml`: add web app URL var, include image loading, rollout restart/status/log tasks, and possibly `update:web`.
- `docs/kind-control-plane.md`: document the web app URL and lifecycle.
- `scripts/kind-control-plane-smoke.py` or a new smoke test: verify web app endpoint and `/api/snapshot` without starting rounds.

## Implementation Notes

- In cluster, the web app should use `SCION_OPS_HUB_ENDPOINT=http://scion-hub:8090`, `SCION_HUB_ENDPOINT=http://scion-hub:8090`, `SCION_DEV_TOKEN_FILE=/run/secrets/scion-hub-dev-auth/dev-token`, `SCION_K8S_NAMESPACE` from the pod namespace, and `SCION_OPS_MCP_URL=http://scion-ops-mcp:8765/mcp`.
- The Deployment should mount the workspace similarly to MCP if it imports repo code from `/workspace/scion-ops`, or the image should contain the repo scripts/modules directly.
- The web app probably needs the same Python deps as MCP: `mcp>=1.13,<2` and `PyYAML>=6,<7`.
- Use labels consistent with the control plane: `app.kubernetes.io/part-of=scion-control-plane`, with a distinct `app.kubernetes.io/name` such as `scion-ops-web`.
- Decide whether web app is part of required readiness. If yes, add it to rollout/status/smoke checks and possibly the app's own Kubernetes `CONTROL_PLANE_NAMES`; if no, keep it observable but avoid making web app health a prerequisite for round execution.

## Risks

- Port changes require kind cluster recreation. Adding a web app NodePort plus kind `extraPortMappings` will not retrofit an existing kind cluster.
- Reusing the MCP image for the web app can create a confusing entrypoint/port split unless tasks and manifests are explicit.
- Keeping branch/final-review normalization duplicated between MCP and web app raises drift risk as Scion payloads evolve.
- The web app currently checks MCP reachability through a host-default URL; in-cluster deployment must override it or readiness will report false degradation.
- If the web app pod shells out to `kubectl`, it needs appropriate RBAC and service account wiring. Reusing MCP helpers avoids some duplication but does not automatically grant Kubernetes permissions.
- Smoke tests should stay read-only/no-spend; avoid exercising round-starting MCP tools from web app checks.
