# Explorer Findings: update-web-app

Session: `20260509t184354z-48de`
Branch: `round-20260509t184354z-48de-spec-explorer`
Goal: align the web app with recent Scion-oriented MCP service changes and include the web app in the kustomize/kind install.

## Current Web App State

- Existing app entry point is `scripts/web_app_hub.py`. It is a read-only stdlib HTTP server, not a separate frontend build, and serves both HTML and JSON endpoints.
- The app imports `mcp_servers.scion_ops` directly and delegates runtime data through `RuntimeProvider`:
  - Hub status: `scion_ops.scion_ops_hub_status()`.
  - Hub messages/notifications: `scion_ops.HubClient("").messages(...)` and `.notifications()`.
  - Round detail/events: `scion_ops.scion_ops_round_status(...)` and `scion_ops.scion_ops_round_events(...)`.
  - MCP reachability: HTTP probe of `SCION_OPS_MCP_URL`, defaulting to `http://192.168.122.103:8765/mcp`.
  - Kubernetes state: `kubectl get deploy,pod,svc,pvc -o json`.
- The app already has alignment work for newer normalized Scion/MCP payloads:
  - Structured branch fields are preferred over fallback parsing.
  - Final review verdicts are normalized and surfaced in list/detail views.
  - Degraded source handling preserves partial data.
- Current default web bind is local only: `SCION_OPS_WEB_HOST` defaults to `127.0.0.1`; `SCION_OPS_WEB_PORT` defaults to `8787`. A Kubernetes deployment will need `0.0.0.0`.
- Current control-plane deployment detection hard-codes `CONTROL_PLANE_NAMES = {"scion-hub", "scion-broker", "scion-ops-mcp"}`. If the web app becomes part of the installed control plane, this set and the tests should include the web deployment so Runtime view/readiness do not ignore it.
- The web app has a `task web:hub` local runner but no image, Kubernetes Deployment, Service, NodePort, update task, status task, or smoke coverage in the kind install path.

## MCP / Scion Alignment Notes

- `mcp_servers/scion_ops.py` now uses Scion Hub HTTP APIs as the source of truth for Hub-mode control and monitoring, with config/auth discovery through `HubClient` and `HubConfig`.
- The web app currently reuses those internals rather than going through MCP tools over HTTP. This keeps behavior closely aligned but creates coupling to internal Python symbols such as `HubClient`, `_hub_error_payload`, and `_kubectl_context_args`.
- For this change, prefer preserving that shared-code model unless the spec explicitly wants browser backend calls to the MCP HTTP transport. If the MCP service API changes again, the lowest-risk web update is usually in `RuntimeProvider`, not the frontend template.
- The web app should use the same in-cluster Hub auth and endpoint settings as the MCP deployment:
  - `SCION_OPS_HUB_ENDPOINT=http://scion-hub:8090`
  - `SCION_HUB_ENDPOINT=http://scion-hub:8090`
  - `SCION_DEV_TOKEN_FILE=/run/secrets/scion-hub-dev-auth/dev-token`
  - namespace from the pod field ref via `SCION_K8S_NAMESPACE`
- If deployed in-cluster, MCP status should probe the service URL (`http://scion-ops-mcp:8765/mcp`) unless the desired check is explicitly host NodePort reachability.

## Kind / Kustomize State

- Top-level `deploy/kind/kustomization.yaml` only includes:
  - `namespace.yaml`
  - `rbac.yaml`
- The control plane kustomization is separate at `deploy/kind/control-plane/kustomization.yaml` and includes Hub, broker, and MCP resources only.
- `task kind:control-plane:apply` applies `deploy/kind/namespace.yaml` and then `deploy/kind/control-plane`; it does not apply the top-level `deploy/kind` kustomization.
- Kind cluster template `deploy/kind/cluster.yaml.tpl` exposes only Hub and MCP NodePorts via host mappings:
  - Hub node port `30090` -> host port `SCION_OPS_KIND_HUB_PORT` default `18090`
  - MCP node port `30876` -> host port `SCION_OPS_MCP_PORT` default `8765`
- `scripts/kind-scion-runtime.sh` validates only Hub and MCP native port mappings. Adding normal host access for the web app requires adding a web NodePort and validating/rendering a third extraPortMapping.
- `Taskfile.yml` build/up/update/status tasks know about `localhost/scion-base:latest`, `localhost/scion-ops-mcp:latest`, and harness images. There is no web image target or `task update:web`.

## Expected Files To Spec / Implement

Likely product files:

- `scripts/web_app_hub.py`
  - Update runtime provider defaults for in-cluster deployment.
  - Include `scion-ops-web` in control-plane Kubernetes normalization if the web app is installed as a Deployment.
  - Keep alignment with `mcp_servers.scion_ops` current Hub auth/config behavior.
- `scripts/test-web-app-hub.py`
  - Add/adjust fixtures for the web deployment appearing in Kubernetes readiness.
  - Add tests for in-cluster MCP URL/env behavior if RuntimeProvider defaults change.
- `image-build/scion-ops-web/Dockerfile` or reuse `image-build/scion-ops-mcp/Dockerfile`
  - If creating a separate image, install the same Python deps as MCP (`mcp`, `PyYAML`) because the web app imports `mcp_servers.scion_ops`.
  - If reusing the MCP image, the Deployment command can run `scripts/web_app_hub.py` from the mounted checkout.
- `scripts/build-images.sh`
  - Add a build target for web if using a separate image, including `--only web`.
- `deploy/kind/control-plane/web-deployment.yaml`
  - Run `python ${SCION_OPS_ROOT}/scripts/web_app_hub.py --host 0.0.0.0 --port 8787` or equivalent env-driven command.
  - Mount the workspace like the MCP deployment so the script and shared MCP module are available.
  - Mount `scion-hub-dev-auth` for Hub auth.
  - Set `SCION_OPS_MCP_URL=http://scion-ops-mcp:8765/mcp`.
  - Set Hub endpoint env vars to `http://scion-hub:8090`.
  - Use a service account with enough RBAC for `kubectl get deploy,pod,svc,pvc`; either reuse `scion-ops-mcp` if acceptable or define a narrow `scion-ops-web` service account/role/binding.
- `deploy/kind/control-plane/web-service.yaml`
  - Expose port `8787`; use NodePort only if the app should be reachable via the normal kind host mapping.
- `deploy/kind/control-plane/kustomization.yaml`
  - Add web deployment/service and any web RBAC/config resources.
- `deploy/kind/cluster.yaml.tpl`
  - Add a third extraPortMapping if web host access is part of the kind install.
- `scripts/kind-scion-runtime.sh`
  - Add web host/node port variables, render substitutions, native port validation, status output, and usage text.
- `Taskfile.yml`
  - Add web port/URL vars, load the web image in `task up` if separate, and add `update:web`, `kind:web:status`, and possibly `kind:web:smoke`.
  - Include web rollout in `kind:control-plane:restart` and `kind:control-plane:status` if web is required for a complete control-plane install.
- `scripts/kind-control-plane-smoke.py`
  - Add a no-spend HTTP check for the web app and `/api/snapshot`, ideally verifying partial JSON shape and readiness source names.
- `docs/kind-control-plane.md` and possibly `README.md`
  - Document the web URL/port and the new install/update path.

Likely OpenSpec files for this change:

- `openspec/changes/update-web-app/proposal.md`
- `openspec/changes/update-web-app/design.md`
- `openspec/changes/update-web-app/tasks.md`
- `openspec/changes/update-web-app/specs/web-app-hub/spec.md`
- Possibly a deployment/control-plane spec delta if the repo has or adds a dedicated spec area for kind control-plane installation.

## Spec Points To Capture

- Web app SHALL derive Hub/grove/auth config through the same Scion-aligned code path as MCP.
- Web app SHALL run inside kind as part of the control-plane install.
- Web app SHALL be reachable from the host through the standard kind install, without requiring a manual port-forward.
- Web app SHALL expose read-only status and SHALL NOT start/abort/mutate rounds.
- Web app readiness SHALL include Hub, broker, MCP, Kubernetes, and the web app's own Kubernetes deployment/service state once installed.
- Kind install/update/status/smoke commands SHALL include the web app.
- Smoke coverage SHALL remain no-spend and should only call HTTP/status endpoints.

## Risks / Watch Items

- Internal coupling risk: `scripts/web_app_hub.py` imports non-public helpers from `mcp_servers.scion_ops`. This is workable inside one repo but should be acknowledged in the spec if "aligned with MCP" means shared behavior rather than MCP-over-HTTP.
- Service account risk: a web pod that shells out to `kubectl` needs RBAC. Reusing MCP RBAC is fastest; a separate web service account is cleaner but adds manifests.
- Port mapping risk: kind extraPortMappings are immutable for existing clusters. Adding a web host port requires cluster recreation for existing users, same as prior Hub/MCP mapping changes.
- Image/build risk: a separate web image increases build/load/update tasks. Reusing `localhost/scion-ops-mcp:latest` avoids a new image target but may be semantically confusing.
- Readiness recursion risk: once the web app is counted as a required deployment, ensure fixtures and normalization do not report degraded merely because older clusters lack the new deployment before migration.
- Host-vs-cluster URL risk: in-cluster web probes should use Kubernetes service DNS for MCP; operator-facing docs should use the host URL.
- Existing `deploy/kind/kustomization.yaml` does not include `control-plane/`; clarify whether "include web app into kustomize / kind install" means the control-plane kustomization only or also the top-level kustomization.

## Verification Suggestions

- `python3 -m py_compile mcp_servers/scion_ops.py scripts/web_app_hub.py scripts/kind-control-plane-smoke.py`
- `uv run scripts/test-web-app-hub.py`
- `bash -n scripts/build-images.sh scripts/kind-scion-runtime.sh`
- If manifests are changed: `kubectl kustomize deploy/kind/control-plane`
- No-spend kind verification after deployment:
  - `task build:mcp` or new `task build:web` if applicable
  - `task up`
  - `task kind:web:status`
  - `task test -- --skip-setup`
