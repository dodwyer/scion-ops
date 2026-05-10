# Implementation Brief: autorefresh-web-app

Session: 20260510t084647z-0b23
Base branch: main
Integration branch: round-20260510t084647z-0b23-integration

## Accepted Scope

Implement automatic browser updates for the read-only scion-ops web app hub. The approved change requires a live stream, watch, cursor long-poll, or equivalent automatic update path for overview, rounds, round detail timelines, inbox, and runtime status; visible live/reconnecting/stale/fallback/failed states; idempotent merge behavior; and no write operations during subscribe, reconnect, polling, or recovery.

## Task Groups

### Group A: Backend Live Delivery Contract

Branch: round-20260510t084647z-0b23-impl-codex

Owned paths:
- scripts/web_app_hub.py
- scripts/test-web-app-hub.py
- openspec/changes/autorefresh-web-app/tasks.md

Tasks:
- Identify current snapshot endpoints and backing sources covered by automatic updates.
- Define and implement a browser-facing live update contract, preferably using server-sent events because the current app is a small Python HTTP server and needs one-way operational updates.
- Emit an initial snapshot, typed snapshot/round-detail/heartbeat/error events, stable event ids or cursor fields, source-specific errors, and a safe fallback signal when streaming cannot continue.
- Preserve read-only behavior for all live endpoints.
- Add focused fixture/unit tests for the backend contract, initial snapshot, incremental/update events, duplicate/idempotent ids where practical, source errors, and read-only HTTP behavior.

Out of scope:
- Frontend rendering changes except minimal server-provided data needed by the contract.
- Kubernetes manifests, Taskfile lifecycle, or smoke script changes unless tests prove a backend issue requires a narrow adjustment.

### Group B: Frontend Auto-Refresh Experience And Verification

Branch: round-20260510t084647z-0b23-impl-claude

Owned paths:
- scripts/web_app_hub.py
- scripts/test-web-app-hub.py
- scripts/kind-control-plane-smoke.py
- openspec/changes/autorefresh-web-app/tasks.md

Tasks:
- Connect overview, rounds, round detail, inbox, and runtime views to the live update path.
- Keep selected round detail, current view, existing timeline entries, filters/view state, and scroll context stable while updates arrive.
- Add compact live status indicators for connected/live, reconnecting, stale, fallback polling, and failed states.
- Make the manual refresh button a secondary troubleshooting action rather than the normal monitoring path.
- Add tests for frontend-visible HTML/JS contract where feasible and extend no-spend smoke coverage only if needed to verify the automatic update path without starting model-backed rounds.

Out of scope:
- New mutating controls or state-changing backend endpoints.
- Broad deployment/kustomize changes unless the web app endpoint contract requires a narrow health/smoke adjustment.

## Integration Notes

Both implementation branches touch `scripts/web_app_hub.py` and `scripts/test-web-app-hub.py`; integrate Group A first, then replay/adapt Group B onto the integration branch while preserving the backend event contract. Only update checked tasks that are fully completed by the branch. Do not mark validation/smoke tasks complete until they have actually run.

## Verification Commands

Run after integration:

```sh
python3 scripts/validate-openspec-change.py autorefresh-web-app
uv run scripts/test-web-app-hub.py
python3 -m py_compile scripts/web_app_hub.py scripts/kind-control-plane-smoke.py
```

Run no-spend smoke if the kind control plane is available:

```sh
python3 scripts/kind-control-plane-smoke.py --skip-round
```

If kind or required auth is unavailable, record the exact blocker and keep the fixture/static verification evidence.
