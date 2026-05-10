# Implementation Brief: autorefresh-web-app

Session: 20260510t085414z-4e4f
Base branch: main
Integration branch: round-20260510t085414z-4e4f-integration

## Task Groups

### Group A: Web App Live Update Implementation

Owner branch: round-20260510t085414z-4e4f-impl-codex

Scope:
- Identify existing snapshot endpoints and source reads in `scripts/web_app_hub.py`.
- Define and expose the browser-facing live update contract for initial snapshot, typed updates, stable ids, cursor/version handling, heartbeats, and source-specific errors.
- Implement a read-only automatic update path for overview, rounds, selected round detail timelines, inbox, and runtime state.
- Connect the embedded browser UI to the automatic update path, preserve selected round/detail/filter/scroll context where applicable, keep timeline merges idempotent, show live/reconnecting/stale/fallback/failed states, and make manual refresh secondary.

Owned paths:
- `scripts/web_app_hub.py`
- `openspec/changes/autorefresh-web-app/tasks.md`

Out of scope:
- Test-only fixture assertions and smoke scripts owned by Group B.
- Kubernetes manifests unless required to expose an already implemented read-only endpoint.
- Any write operation that starts, retries, aborts, archives, deletes, or mutates rounds, Kubernetes resources, Hub records, git refs, or OpenSpec files.

Tasks targeted:
- 1.1 through 1.7, plus the implementation portion needed for 1.8 and 1.9.

### Group B: Fixture, Reconnect, Smoke, and No-Spend Verification

Owner branch: round-20260510t085414z-4e4f-impl-claude

Scope:
- Add fixture/unit tests for initial snapshot plus incremental updates, duplicate/replayed event handling, timeline appends, inbox updates, runtime changes, final-review/status changes, reconnect/stale behavior, and read-only/no-spend behavior.
- Add or update no-spend smoke coverage for automatic update endpoints if an existing smoke harness is suitable.
- Run OpenSpec validation and the relevant web app/static/smoke checks.

Owned paths:
- `scripts/test-web-app-hub.py`
- `scripts/kind-control-plane-smoke.py`
- `scripts/smoke-mcp-server.py`
- `openspec/changes/autorefresh-web-app/tasks.md`

Out of scope:
- Product implementation in `scripts/web_app_hub.py` except for proposing required changes in the completion summary if tests reveal a blocker.
- Kubernetes manifests and runtime deployment behavior unless a smoke-only adjustment is needed.
- Any model-backed smoke round or state-changing operation.

Tasks targeted:
- 1.8 through 1.11.

## Verification Commands

Run on the integration branch after implementation branches are merged:

- `python3 scripts/validate-openspec-change.py autorefresh-web-app`
- `uv run scripts/test-web-app-hub.py`
- `python3 scripts/kind-control-plane-smoke.py --help`
- `python3 scripts/smoke-mcp-server.py --help`

If a local kind control plane is available without spend, also run the existing no-spend control-plane smoke command documented by the changed smoke scripts.

## Integration Notes

- Merge Group A first so Group B tests can validate the concrete live update contract.
- Preserve source-of-truth behavior: Hub, MCP, Kubernetes, and existing normalized helper output remain authoritative.
- Integration must push `round-20260510t085414z-4e4f-integration`, then final review must be started from that pushed integration SHA.
