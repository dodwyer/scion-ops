# Explorer Findings: web-app-2

Session: `20260510t154643z-459d`
Change: `web-app-2`
Base branch: `main`
Explorer branch: `round-20260510t154643z-459d-spec-explorer`

## Existing Web App

The repository already has a read-only operator web app implemented as a single Python HTTP server in `scripts/web_app_hub.py`. It serves an embedded HTML/CSS/JavaScript interface and browser-facing JSON endpoints over the existing scion-ops runtime sources.

Current backend endpoints include:

- `/` for the operator UI.
- `/healthz` and `/api/healthz` for service health.
- `/api/snapshot`, `/api/overview`, `/api/rounds`, `/api/inbox`, and `/api/runtime` for snapshot views.
- `/api/rounds/{round_id}` for selected round detail.
- `/api/rounds/{round_id}/events` for cursor-based round event polling.
- `/api/live` and `/api/stream` for live updates.
- `/api/contract` for the browser JSON contract.

The live update contract is already present in `BROWSER_JSON_CONTRACT["live_updates"]`. It defines `/api/live?cursor=<last_cursor>&round_id=<optional-round>`, typed events, cursors, heartbeats, source-specific errors, idempotency expectations, and read-only behavior. The implementation supports both SSE (`text/event-stream`) and JSON batch responses for clients that do not request an event stream.

The current frontend is operator-focused rather than decorative: compact header navigation, overview cards, rounds table, selected round detail, inbox, runtime source checks, status dots, metadata pills, and monospace runner output. It subscribes with `EventSource("/api/live")`, falls back to automatic snapshot polling when streaming is unavailable, tracks live states (`connected`, `reconnecting`, `stale`, `fallback`, `failed`), and preserves selected round detail state while applying updates. Manual refresh controls are intentionally absent from the rendered UI markers in the current tests.

For the explicit goal, important existing behavior is already in place:

- New snapshot data is applied automatically through live events rather than requiring a page refresh.
- Round detail timelines append incoming `timeline.appended` entries and sort newest-first.
- Inbox groups and items are sorted newest-first by latest update/time.
- Duplicate timeline events are suppressed by stable IDs or deterministic fallback keys.
- Source failures preserve prior rounds, inbox items, or timelines where possible instead of blanking unrelated data.

## Data Sources And Semantics

The server reads existing operational state and does not maintain a competing persistent model.

Primary sources:

- Scion Hub via `scion_ops.scion_ops_hub_status()`.
- Hub messages and notifications through `HubClient.messages()` and `HubClient.notifications()`.
- MCP round helpers: `scion_ops_round_status`, `scion_ops_round_events`, `scion_ops_round_artifacts`, `scion_ops_spec_status`, and `scion_ops_validate_spec_change` where appropriate.
- Kubernetes readiness via `kubectl get deploy,pod,svc,endpoints,pvc -o json`.
- Local git/artifact data exposed through the existing MCP helper layer.

The adapter normalizes Hub, MCP, Kubernetes, messages, notifications, web app, and broker health into explicit source records. It prefers structured branch, artifact, validation, blocker, warning, final-review, and steward progress fields before using text-derived fallbacks. Final-review states such as accepted, changes requested, and blocked are kept visible instead of being collapsed into generic completed state.

## Kubernetes, Kind, And Kustomize State

The web app is already part of the kind control plane.

Expected deployed files:

- `deploy/kind/control-plane/web-app-rbac.yaml`
- `deploy/kind/control-plane/web-app-service.yaml`
- `deploy/kind/control-plane/web-app-deployment.yaml`
- `deploy/kind/control-plane/kustomization.yaml`
- `deploy/kind/cluster.yaml.tpl`
- `Taskfile.yml`
- `scripts/kind-control-plane-smoke.py`
- `docs/kind-control-plane.md`

Current manifest shape:

- Deployment: `scion-ops-web-app`
- ServiceAccount/RBAC: `scion-ops-web-app`, read-only access to deployments, services, pods, endpoints, and PVCs.
- Image: `localhost/scion-ops-mcp:latest`
- Container command: runs `scripts/web_app_hub.py` from the mounted checkout.
- Container port: `8787`
- Service: `scion-ops-web-app`
- Service type: `NodePort`
- NodePort: `30808`
- Taskfile default URL: `http://192.168.122.103:8808`
- In-cluster Hub endpoint: `http://scion-hub:8090`
- In-cluster MCP URL: `http://scion-ops-mcp:8765/mcp`
- Workspace mount: host `/workspace` mounted at `/workspace`
- Dev auth secret: `/run/secrets/scion-hub-dev-auth/dev-token`
- Optional GitHub token secret mounted read-only.

`deploy/kind/control-plane/kustomization.yaml` includes the web app RBAC, Service, and Deployment alongside Hub, broker, and MCP resources. `deploy/kind/cluster.yaml.tpl` includes a web app port mapping placeholder in addition to Hub and MCP mappings.

Taskfile coverage:

- `task web:hub` runs the local read-only app.
- `task up` applies/restarts/status-checks the web app as part of the control plane.
- `task update:web-app` reloads the MCP image, restarts the web app deployment, and checks rollout status.
- `task kind:web-app:status` and `task kind:web-app:logs` provide focused operations.
- `task kind:control-plane:smoke` passes `SCION_OPS_WEB_APP_URL` into `scripts/kind-control-plane-smoke.py`.

The smoke script checks the deployed web app by requesting `/api/overview` and validating that it is reachable and not returning an explicit error payload.

## Relevant Tests And Verification

Focused web app tests live in `scripts/test-web-app-hub.py`.

Coverage found:

- Healthy, empty, blocked, stale, and unavailable snapshot states.
- Kubernetes control-plane normalization, including web app deployment/service/endpoint readiness.
- Structured branch precedence over text, task summary, name, and slug fallback data.
- Final-review accept, changes-requested, blocked, and outcome-only verdict rendering semantics.
- MCP/steward progress fields: expected branch, PR-ready branch, remote branch SHA, validation status, blockers, warnings, PR URL, artifacts, and spec status.
- Live contract shape, typed initial snapshot events, heartbeat, cursor generation, source coverage, final-review/status changes, runtime changes, inbox updates, duplicate replay idempotency, cursor resume, source-specific errors, preservation of last-known data on source failures, and read-only behavior.
- Frontend contract markers for `/api/live`, `EventSource`, automatic fallback polling, stale handling, timeline dedupe keys, and absence of primary manual refresh controls.

Verification run during exploration:

- `uv run scripts/test-web-app-hub.py` passed.
- `git diff --check` passed.
- `kubectl kustomize deploy/kind/control-plane` rendered successfully and included the web app Service/Deployment with NodePort `30808` and container port `8787`.

## Expected Files To Spec

If the new OpenSpec change needs to document or tighten the dynamic push/operator UI behavior, the expected spec surface is likely under:

- `openspec/changes/web-app-2/proposal.md`
- `openspec/changes/web-app-2/design.md`
- `openspec/changes/web-app-2/tasks.md`
- `openspec/changes/web-app-2/specs/web-app-hub/spec.md`

The closest existing accepted or in-progress precedent is:

- `openspec/changes/build-web-app-hub/*`
- `openspec/changes/update-web-app/*`
- `openspec/changes/autorefresh-web-app/*`

Those existing change artifacts already describe most of the requested behavior: read-only operator hub, MCP-aligned fields, kind deployment, live/automatic updates, incremental timeline appends, connected/reconnecting/stale/failed states, and no-spend verification.

## Risks And Gaps

- The current live endpoint is server-produced SSE over repeated snapshots. It is push-like from the browser's perspective, but the server still polls/normalizes Hub, MCP, and Kubernetes state rather than subscribing to all backing systems with true source-native push streams.
- `/api/live` emits snapshot-level updates plus detail events when `round_id` is provided. The frontend opens `/api/live` without a round id for the main stream and separately polls selected round events. This satisfies automatic updates, but selected round timeline behavior is a hybrid of SSE snapshot updates and cursor polling rather than one unified push channel.
- SSE formatting uses typed event names and JSON data, but browser reconnection currently opens `/api/live` without visibly passing the last cursor in the EventSource URL. Cursor resume behavior is tested at the backend batch level, but the frontend's EventSource reconnect path may replay snapshots instead of resuming precisely from the last cursor.
- No Playwright or browser-level screenshot/interaction test was found for the professional operator UI. Existing frontend checks are string/contract markers inside `INDEX_HTML`, not rendered layout verification.
- The kind smoke checks `/api/overview`, not `/api/live` streaming behavior. A runtime smoke that verifies SSE headers and at least one heartbeat would reduce deployment risk.
- The UI is embedded in a Python raw string. That keeps deployment simple, but larger professional UI changes may become hard to maintain without extracting frontend assets or adding a small frontend build step.
- Newest-first feed ordering exists for rounds, inbox, and timelines, but there is no explicit visual "new item inserted" affordance. If operators need attention management during high-volume updates, the spec should call out highlighting, unread markers, or stable scroll anchoring.
- Current RBAC is read-only and appropriately narrow for control-plane inspection, but any future UI write operation would need a separate authorization and audit model. This should remain out of scope for `web-app-2` unless explicitly requested.

## Implementation Guidance

The least disruptive path is to extend the existing `scripts/web_app_hub.py` implementation and tests rather than introduce another framework. Alternative frameworks are allowed by the goal, but the repo already has a working no-build Python server, kind deployment, smoke wiring, and focused fixture tests. A framework migration would increase blast radius unless the change requires substantially richer client-side interaction than the current embedded UI can support.

For a professional operator-focused iteration, prioritize:

- Tighten the live stream contract between selected round detail and `/api/live?round_id=...`.
- Pass the last cursor on reconnect where possible.
- Add a smoke or fixture test for SSE heartbeat delivery.
- Add rendered UI verification for desktop/mobile layout and non-overlap if visual changes are substantial.
- Keep the app read-only and preserve structured MCP/Hub fields as authoritative.
