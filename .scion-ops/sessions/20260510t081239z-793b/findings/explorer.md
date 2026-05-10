# Explorer Findings: autorefresh-web-app

## Scope

- Session: `20260510t081239z-793b`
- Change: `autorefresh-web-app`
- Goal: replace the visible/manual refresh interaction in the web app with automatic incoming data that behaves like a stream.
- Branch inspected: `round-20260510t081239z-793b-spec-explorer`
- Artifact boundary honored: this file only.

## Current Web App State

- The web app is implemented as a single Python HTTP server in `scripts/web_app_hub.py`.
- The UI is embedded in `INDEX_HTML` and renders Overview, Rounds, Inbox, Runtime, and Round Detail views from browser-side JavaScript.
- The app is read-only. `do_POST`, `do_PUT`, `do_PATCH`, and `do_DELETE` all return method-not-allowed responses.
- Current browser update behavior:
  - `/api/snapshot` is fetched by `refresh()`.
  - A visible top-level `Refresh` button calls `refresh()`.
  - `setInterval(refresh, 15000)` already auto-polls every 15 seconds.
  - Round detail has a separate visible `Refresh timeline` button that re-fetches `/api/rounds/<round_id>`.
- Existing event-related backend surface:
  - `/api/rounds/<round_id>/events` calls `provider.round_events(round_id, cursor=..., include_existing=False)`.
  - `build_round_detail()` already returns a cursor from `provider.round_events(..., include_existing=True)`.
  - The browser state has `cursors: {}` but currently does not use cursors to incrementally update the timeline.
- There is no browser `EventSource`, WebSocket, chunked event stream, or long-poll loop today. The only automatic behavior is fixed-interval snapshot polling.

## Backing Runtime/MCP State

- `RuntimeProvider.round_events()` delegates to `scion_ops.scion_ops_round_events()`.
- `mcp_servers/scion_ops.py` exposes:
  - `scion_ops_round_events(round_id, cursor="", include_existing=False, project_root="")`
  - `scion_ops_watch_round_events(round_id, cursor="", timeout_seconds=90, poll_interval_seconds=2, include_existing=False, project_root="")`
- `scion_ops_watch_round_events()` is the closest existing primitive for stream-like behavior. It long-polls inside the MCP server until Hub messages, notifications, agent fingerprints, or terminal status change, then returns events plus a new cursor.
- The current web app backend does not expose `scion_ops_watch_round_events()` through an HTTP endpoint.

## Kubernetes / Kind / Kustomize State

- The web app is already deployed as a kind control-plane component:
  - `deploy/kind/control-plane/web-app-deployment.yaml`
  - `deploy/kind/control-plane/web-app-service.yaml`
  - `deploy/kind/control-plane/web-app-rbac.yaml`
- `deploy/kind/control-plane/kustomization.yaml` includes the web app Deployment, Service, and RBAC resources.
- The web app container reuses `localhost/scion-ops-mcp:latest` and runs `python "${SCION_OPS_ROOT}/scripts/web_app_hub.py"`.
- In-cluster config is wired through env:
  - `SCION_OPS_WEB_HOST=0.0.0.0`
  - `SCION_OPS_WEB_PORT=8787`
  - `SCION_OPS_HUB_ENDPOINT=http://scion-hub:8090`
  - `SCION_HUB_ENDPOINT=http://scion-hub:8090`
  - `SCION_OPS_MCP_URL=http://scion-ops-mcp:8765/mcp`
  - `SCION_DEV_TOKEN_FILE=/run/secrets/scion-hub-dev-auth/dev-token`
- The Service is `NodePort` with service port `8787` and nodePort `30808`.
- `deploy/kind/cluster.yaml.tpl` maps the web app node port through the kind host port.
- `Taskfile.yml` already includes web-app lifecycle integration:
  - `task up` applies and restarts the web app.
  - `task update:web-app` reloads the MCP image and restarts `deploy/scion-ops-web-app`.
  - `task kind:web-app:status` and `task kind:web-app:logs` exist.
  - `task kind:control-plane:smoke` passes `SCION_OPS_WEB_APP_URL` into the smoke script.
- `scripts/kind-control-plane-smoke.py` verifies the deployed web app by requesting `/api/overview`.

## Existing OpenSpec Context

- There is no `openspec/changes/autorefresh-web-app` directory yet.
- Relevant existing web app changes:
  - `openspec/changes/build-web-app-hub/`
  - `openspec/changes/update-web-app/`
- `build-web-app-hub` already requires refresh behavior that keeps the interface current without manual CLI polling and includes a "Timeline refreshes" scenario.
- `update-web-app` is marked complete and broadened the web app contract around MCP-aligned structured state, kind deployment, lifecycle tasks, and smoke checks.
- The new spec should likely be a MODIFIED delta against `web-app-hub`, not a new product area.

## Expected Files To Spec

Likely OpenSpec artifact files:

- `openspec/changes/autorefresh-web-app/proposal.md`
- `openspec/changes/autorefresh-web-app/design.md`
- `openspec/changes/autorefresh-web-app/tasks.md`
- `openspec/changes/autorefresh-web-app/specs/web-app-hub/spec.md`

Likely product files for a later implementation round:

- `scripts/web_app_hub.py`
- `scripts/test-web-app-hub.py`
- Possibly `scripts/kind-control-plane-smoke.py` if the smoke should verify stream/event behavior rather than only `/api/overview`.
- Possibly `docs/kind-control-plane.md` if operator-facing behavior or troubleshooting changes are documented.

Kubernetes files probably do not need structural changes unless the spec chooses true long-lived browser connections and wants probe/resource guidance:

- `deploy/kind/control-plane/web-app-deployment.yaml`
- `deploy/kind/control-plane/web-app-service.yaml`

## Suggested Spec Shape

Recommended requirement deltas for `web-app-hub`:

- Modify Round Detail Timeline: new events should appear automatically while a round detail view is open, without clicking `Refresh timeline` and without losing existing entries.
- Modify Operator Overview / Round Progress Visibility / Inbox: visible lists should stay current automatically without a manual `Refresh` button.
- Add or modify browser update transport semantics:
  - The backend should provide a browser-facing event update mechanism, either Server-Sent Events or long-polling over existing JSON endpoints.
  - The browser should track cursors or versions to avoid duplicating timeline entries.
  - The UI should surface connection/update errors without blanking already-rendered data.
- Preserve read-only behavior: streaming or long-poll endpoints must not start rounds or mutate Hub, MCP, Kubernetes, or local git state.

## Implementation Risks

- Naming risk: the user asked for "like a stream"; current stack has MCP streamable HTTP, but the browser app does not currently stream. The spec should decide whether "stream" means true SSE/WebSocket or automatic long-polling. Long-polling fits the existing MCP `watch_round_events` primitive with less new infrastructure.
- Thread exhaustion risk: `ThreadingHTTPServer` can hold one thread per long-poll/SSE connection. A true always-open stream or many open round-detail tabs could consume threads. If using long-polling, keep timeouts bounded and reconnect from the browser.
- Snapshot cost risk: `build_snapshot()` calls Hub, MCP, Kubernetes, round status, and artifacts. Rebuilding it too frequently for all users may increase latency/load. Stream/detail updates should use narrower event endpoints where possible.
- Consistency risk: top-level snapshot updates and per-round event updates may diverge unless the browser has clear rules for when to refresh the snapshot versus append timeline events.
- Cursor risk: `/api/rounds/<id>/events` exists but the browser does not currently store or pass cursors. The spec should require dedupe/stable ordering so reconnects do not duplicate events.
- Error handling risk: current `refresh()` shows snapshot failure in the refresh-state area. Automatic updates need equivalent stale/disconnected/degraded status while preserving last good data.
- Test gap risk: existing fixture tests cover backend snapshot semantics, MCP fields, final-review outcomes, and Kubernetes normalization, but not browser auto-refresh/stream behavior. At minimum, tests should cover new backend event endpoint behavior and that manual refresh controls are absent or no longer primary.
- Smoke risk: current kind smoke only checks `/api/overview`. If stream behavior is part of the operator contract, add a no-spend smoke path that can validate the update endpoint responds without requiring live model-backed rounds.
