# Explorer Findings: web-ui-theme

## Repository Shape

- The web UI is implemented as a small read-only Python HTTP server in `scripts/web_app_hub.py`.
- The browser document is embedded in `INDEX_HTML` in the same file. The theme, layout CSS, nav buttons, view containers, and frontend rendering functions all live there.
- Fixture coverage for backend normalization and frontend template markers is in `scripts/test-web-app-hub.py`.
- The UI is deployed as a kind control-plane component, not just a local script. It reuses the `localhost/scion-ops-mcp:latest` image and runs `scripts/web_app_hub.py`.
- Operator documentation for kind access, defaults, and troubleshooting is in `docs/kind-control-plane.md`.

## Existing Web App

- Current primary views are `Overview`, `Rounds`, `Inbox`, `Runtime`, plus a selected round detail view.
- `scripts/web_app_hub.py` already presents operator state from Hub, MCP, Kubernetes, messages, notifications, round artifacts, final review, and live updates.
- CSS starts at `scripts/web_app_hub.py` near `INDEX_HTML`. Current tokens are already restrained but basic:
  - `--bg:#f7f7f5`
  - `--panel:#ffffff`
  - `--text:#202225`
  - `--muted:#676b73`
  - `--line:#d8d9dc`
  - status colors for good/warn/bad/info
- Current components include `header`, nav `button`, `.grid`, `.card`, `.table-wrap`, `.detail`, `.pill`, `.agent-card`, table rows, `.mono`, `.flow-stage`, `.stage-pill`, `.reason-box`, and `.error-box`.
- The UI is already function-first and not marketing-oriented. The likely spec work is to formalize a more consistent operational theme: denser spacing, clearer visual hierarchy, consistent surfaces, stronger table/readability treatment, and status colors tuned for monitoring.

## Kubernetes / Kind / Kustomize State

- Web app deployment: `deploy/kind/control-plane/web-app-deployment.yaml`
  - Deployment name: `scion-ops-web-app`
  - Service account: `scion-ops-web-app`
  - Image: `localhost/scion-ops-mcp:latest`
  - Server env: `SCION_OPS_WEB_HOST=0.0.0.0`, `SCION_OPS_WEB_PORT=8787`
  - Hub/MCP env: in-cluster `http://scion-hub:8090` and `http://scion-ops-mcp:8765/mcp`
  - Readiness/liveness probe: `/healthz`
  - Workspace mounted from host `/workspace`
- Web app service: `deploy/kind/control-plane/web-app-service.yaml`
  - Service name: `scion-ops-web-app`
  - Port: `8787`
  - NodePort: `30808`
- Web app RBAC: `deploy/kind/control-plane/web-app-rbac.yaml`
  - Read-only list/get for deployments, services, pods, endpoints, and PVCs.
- Kustomize includes `web-app-rbac.yaml`, `web-app-service.yaml`, and `web-app-deployment.yaml` in `deploy/kind/control-plane/kustomization.yaml`.
- Taskfile includes full lifecycle and narrow web app tasks:
  - `task up` applies control-plane resources, restarts Hub/broker/MCP/web app, and checks web app status.
  - `task update:web-app` reloads the MCP image and restarts only `scion-ops-web-app`.
  - `task kind:web-app:status` and `task kind:web-app:logs` support operator troubleshooting.
- Docs expose default web app URL as `http://192.168.122.103:8808`.

## OpenSpec Context

- Existing relevant OpenSpec changes:
  - `openspec/changes/build-web-app-hub/`
  - `openspec/changes/update-web-app/`
  - `openspec/changes/autorefresh-web-app/`
- `build-web-app-hub/design.md` explicitly says the app should be an operator-facing read model and should favor direct, inspectable status over decorative presentation.
- `update-web-app/design.md` treats the app as a deployed read-only control-plane component aligned with MCP semantics.
- `autorefresh-web-app/design.md` adds automatic update behavior and compact live/reconnecting/stale/failed state display.
- There is no existing `openspec/changes/web-ui-theme` directory in this checkout at exploration time.

## Files Expected To Spec

- `openspec/changes/web-ui-theme/proposal.md`: describe a basic operational theme for the existing web UI, explicitly scoped to readability and monitoring of live Scion state.
- `openspec/changes/web-ui-theme/design.md`: likely define visual principles and implementation constraints:
  - restrained neutral palette, not decorative;
  - status colors reserved for operational semantics;
  - compact layout suitable for repeated scanning;
  - clear table hierarchy for rounds and runtime data;
  - consistent cards/panels without marketing/dashboard ornamentation;
  - responsive behavior that preserves readability.
- `openspec/changes/web-ui-theme/tasks.md`: likely include CSS/token update, view checks across Overview/Rounds/Round Detail/Inbox/Runtime, fixture/static test updates if needed, and no-spend verification.
- `openspec/changes/web-ui-theme/specs/web-app-hub/spec.md`: likely modify or add requirements under the existing web-app-hub area for an operational visual theme.

## Implementation Surface For Later

- Most product implementation should be limited to the CSS and small markup/class adjustments inside `scripts/web_app_hub.py`.
- Useful target area: `INDEX_HTML` CSS block and render functions for cards/tables/detail panels around `renderOverview`, `renderRounds`, `renderRoundDetail`, `renderInbox`, and `renderRuntime`.
- Existing tests can cheaply assert theme markers in `INDEX_HTML`; browser-level or screenshot verification would be more valuable if this repo has a working kind/web app environment during implementation.

## Risks

- `INDEX_HTML` is embedded in Python, so broad CSS/markup edits can make diffs noisy and can break JS template strings if quoting is careless.
- The current UI uses `.card`, `.detail`, and `.table-wrap` broadly. A theme spec should avoid requiring structural refactors unless the goal is only visual polish.
- Status colors are operational signals. Decorative use of green/yellow/red/blue would reduce scan clarity.
- Existing OpenSpec language already rejects decorative presentation; the new change should not redefine the app as a generic dashboard or marketing page.
- Running full kind verification may be environment-dependent. No-spend static/fixture checks are available through `uv run scripts/test-web-app-hub.py` and `task verify`, while deployed visual checks require the local kind path.
