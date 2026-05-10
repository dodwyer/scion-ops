# Explorer Findings: dynamic-web-2

Session: `20260510t144423z-529c`
Change: `dynamic-web-2`
Base branch: `main`
Explorer branch: `round-20260510t144423z-529c-spec-explorer`

## Existing Web App

- The web app is implemented as a single Python script at `scripts/web_app_hub.py`.
- It uses `ThreadingHTTPServer` and embedded `INDEX_HTML` with plain browser JavaScript; there is no separate frontend package, build step, or framework.
- The backend is read-only. `GET` routes serve HTML and JSON; `POST`, `PUT`, `PATCH`, and `DELETE` return method-not-allowed.
- Main JSON routes:
  - `/api/snapshot`
  - `/api/live` and `/api/stream`
  - `/api/overview`
  - `/api/rounds`
  - `/api/rounds/{round_id}`
  - `/api/rounds/{round_id}/events`
  - `/api/inbox`
  - `/api/runtime`
  - `/api/contract`
- Runtime data is derived from existing sources through `RuntimeProvider`: Hub status/messages/notifications, MCP round status/events/artifacts/spec helpers, MCP reachability, and Kubernetes readiness.
- The app already has a modern push-style browser path:
  - `respond_sse()` serves `text/event-stream`.
  - Browser code uses `EventSource("/api/live")`.
  - `build_live_update_batch()` emits typed events such as `snapshot.initial`, `snapshot.updated`, `overview.updated`, `rounds.updated`, `round.detail.updated`, `timeline.appended`, `inbox.updated`, `runtime.updated`, `source.error`, and `heartbeat`.
  - Events carry ids/cursors and fixture tests cover idempotent replay, reconnect with current cursor, source-specific errors, and read-only live updates.
- The app still has manual and automatic refresh behavior that conflicts with the new operator goal:
  - A visible top-level button exists: `Refresh snapshot`.
  - Round detail includes a visible button: `Refresh timeline snapshot`.
  - Browser startup still calls `refresh()` after `startLiveUpdates()`.
  - Browser code always starts `setInterval(refresh, SNAPSHOT_POLL_MS)`.
  - Round detail starts `setInterval(pollSelectedRoundEvents, ROUND_EVENT_POLL_MS)`.
  - `markLiveOk()` labels successful snapshot/event polling as `fallback polling`, even when it is the default periodic path.
- Current timeline rendering sorts ascending by timestamp. New events are pushed into the detail model and then sorted oldest-first, so new operational information appears lower in the timeline, not at the top.
- Current inbox grouping sorts groups/items newest-first. Rounds list sorts newest-first through backend row construction.

## Kubernetes / kind / kustomize State

- The web app is already part of the kind control plane under `deploy/kind/control-plane`.
- `deploy/kind/control-plane/kustomization.yaml` includes:
  - `web-app-rbac.yaml`
  - `web-app-service.yaml`
  - `web-app-deployment.yaml`
- `deploy/kind/control-plane/web-app-deployment.yaml`:
  - Deployment name: `scion-ops-web-app`
  - Reuses image `localhost/scion-ops-mcp:latest`.
  - Runs `python "${SCION_OPS_ROOT}/scripts/web_app_hub.py"`.
  - Exposes container port `8787`.
  - Sets `SCION_OPS_WEB_HOST=0.0.0.0`, `SCION_OPS_WEB_PORT=8787`.
  - Points Hub to `http://scion-hub:8090`.
  - Points MCP to `http://scion-ops-mcp:8765/mcp`.
  - Mounts `/workspace`, Hub dev auth secret, and optional GitHub token secret.
  - Has HTTP readiness and liveness probes on `/healthz`.
- `deploy/kind/control-plane/web-app-service.yaml`:
  - Service name: `scion-ops-web-app`
  - Type: `NodePort`
  - Port: `8787`
  - NodePort: `30808`
- `deploy/kind/control-plane/web-app-rbac.yaml` grants read-only `get/list` access for deployments, services, pods, endpoints, and PVCs.
- `deploy/kind/cluster.yaml.tpl` already maps a web app node port to a host port using `__WEB_APP_NODE_PORT__` and `__WEB_APP_HOST_PORT__`.
- `Taskfile.yml` already has:
  - `SCION_OPS_WEB_APP_PORT` defaulting to `8808`
  - `SCION_OPS_WEB_APP_URL` defaulting to `http://192.168.122.103:8808`
  - `web:hub`
  - `update:web-app`
  - `kind:web-app:status`
  - `kind:web-app:logs`
  - `kind:control-plane:smoke` wiring `SCION_OPS_WEB_APP_URL`
- `scripts/kind-control-plane-smoke.py` already checks the web app by requesting `/api/overview`, unless `--skip-web-app` is used.
- README defaults currently list Hub URL and MCP URL, but not the web app URL.

## Existing OpenSpec State

- Relevant completed changes already exist:
  - `openspec/changes/build-web-app-hub`
  - `openspec/changes/update-web-app`
  - `openspec/changes/autorefresh-web-app`
- `autorefresh-web-app` already specifies automatic data delivery with stream/watch/cursor long poll or equivalent, live status, read-only automatic updates, source-specific failures, and automatic updates for rounds/runtime/inbox/timelines.
- Its design allows SSE, WebSocket, or cursor-based long polling. SSE is the closest fit to the current implementation because operator data appears one-way from server to browser.
- The new user goal is stricter than the existing autorefresh spec in two areas:
  - Refresh buttons should be removed, not merely secondary.
  - Operational data should be added to the top of the page/timeline so the operator can watch new information arrive.

## Expected Files To Spec / Implement

Likely OpenSpec files for `dynamic-web-2`:

- `openspec/changes/dynamic-web-2/proposal.md`
- `openspec/changes/dynamic-web-2/design.md`
- `openspec/changes/dynamic-web-2/tasks.md`
- `openspec/changes/dynamic-web-2/specs/web-app-hub/spec.md`

Likely product files for implementation:

- `scripts/web_app_hub.py`
  - Remove visible refresh controls from `INDEX_HTML`.
  - Stop treating periodic snapshot polling as the ordinary path.
  - Make SSE/EventSource the primary update mechanism.
  - Keep bounded polling only as an explicit fallback after stream failure or when `EventSource` is unavailable.
  - Add cursor-aware SSE reconnect behavior if needed; current `EventSource("/api/live")` does not pass the current cursor in the URL, though the server can read `Last-Event-ID`.
  - Render timeline and inbox updates newest-first where operator watch behavior requires top insertion.
  - Ensure new live events can update the current visible DOM/model without page reload and without moving selected view/scroll context unexpectedly.
- `scripts/test-web-app-hub.py`
  - Update tests that currently assert `SNAPSHOT_POLL_MS`, `ROUND_EVENT_POLL_MS`, and refresh markers exist.
  - Add tests proving refresh buttons are absent.
  - Add tests proving live updates are the default path and polling is fallback-only.
  - Add tests proving timeline entries are ordered newest-first / inserted at the top.
  - Preserve existing tests for source-specific errors, idempotency, cursor resume, and read-only behavior.
- `README.md`
  - Add web app URL to the defaults table if this change is expected to expose the operator screen as a first-class default endpoint.
- Possibly `scripts/kind-control-plane-smoke.py`
  - Existing smoke only checks `/api/overview`. A stronger smoke could check `/api/live` JSON or SSE response without starting model-backed work.

## Risks And Design Notes

- The current backend does not receive native pushed events from Hub/Kubernetes. Its SSE endpoint produces events by rebuilding snapshots and comparing cursors inside the HTTP request loop. This is server-to-browser push, but source acquisition remains sampled/polled. If the spec demands true upstream push all the way from source-of-truth to web app, Hub/MCP/Kubernetes watch APIs need deeper integration.
- `respond_sse()` keeps each SSE response open for up to 60 seconds and then returns. Browser `EventSource` will reconnect, but cursor continuity depends on `Last-Event-ID` and current server framing. Verify this in-browser because the current frame sets `id:` to the event cursor rather than the event id.
- The app currently starts snapshot polling unconditionally even when SSE is connected. That may mask stream bugs and make the screen appear dynamic because of polling. The implementation should make tests distinguish stream delivery from fallback polling.
- Removing refresh buttons is straightforward, but fallback recovery still needs a non-button operator status indicator so stale/failed states are clear.
- Newest-first timeline ordering may change existing operator expectations and tests because the backend currently sorts timeline detail ascending by time. Decide whether to change only rendering order or also backend JSON order. Rendering-only is lower blast radius; backend order change is easier to test for API contract.
- The single-file Python/embedded JS shape is simple and already tested. Migrating frameworks would add rigor only if the team wants a larger frontend surface. For this change, SSE-first cleanup inside `scripts/web_app_hub.py` is likely lower risk than moving to another language/framework.
- Because `scripts/web_app_hub.py` imports MCP internals directly, any framework migration should preserve the existing `RuntimeProvider` behavior and no-spend/read-only guarantees before changing presentation.

## Suggested Acceptance Focus

- No visible refresh buttons in overview, rounds, round detail, inbox, or runtime views.
- Initial page load opens a live update connection and displays connected/reconnecting/stale/fallback/failed state.
- With SSE available, routine updates arrive through `/api/live` and not through unconditional `setInterval(refresh, ...)`.
- If SSE is unavailable, bounded automatic fallback polling starts and is visibly labeled as fallback.
- New round timeline/inbox/operator updates appear at the top of the visible list.
- Replayed live events do not duplicate timeline or inbox rows.
- Live update, reconnect, fallback, and smoke paths remain read-only and no-spend.
