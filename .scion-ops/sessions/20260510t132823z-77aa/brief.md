# Implementation Brief: autorefresh-web-app

## Approved Scope

Implement automatic, read-only browser updates for the Scion web app hub. The app must keep overview, rounds, round detail timelines, inbox, and runtime status current without relying on a primary refresh button. The update path may use server-sent events or an equivalent stream-like fallback, must preserve source-of-truth fields from Hub/MCP/Kubernetes, and must expose live/reconnecting/stale/fallback/failed status.

## Task Groups

### Group A: Backend live update contract and stream endpoint

- Branch: `round-20260510t132823z-77aa-impl-codex`
- Owned paths:
  - `scripts/web_app_hub.py`
  - `scripts/test-web-app-hub.py`
  - `openspec/changes/autorefresh-web-app/tasks.md`
- Tasks:
  - Identify current snapshot endpoints and source coverage for automatic updates.
  - Define typed browser-facing update events, cursors, stable ids, heartbeats, and error payloads in code/API contract.
  - Implement a read-only stream or stream-like endpoint for snapshot, overview, rounds, round detail, inbox, and runtime updates.
  - Add backend fixture/unit coverage for initial snapshot, incremental updates, duplicate/replayed event idempotency, timeline appends, inbox/runtime/final-review/status changes, reconnect/cursor or safe fallback behavior, and no-spend read-only behavior.
- Out of scope:
  - Frontend DOM/CSS behavior beyond the minimum needed to expose backend contract details.
  - Kind/kustomize manifests, smoke scripts, or runtime deployment changes.
  - Starting, aborting, retrying, archiving, or mutating rounds.

### Group B: Frontend autorefresh behavior and smoke/install coverage

- Branch: `round-20260510t132823z-77aa-impl-claude`
- Owned paths:
  - `scripts/web_app_hub.py`
  - `scripts/test-web-app-hub.py`
  - `deploy/kind/control-plane/web-app-deployment.yaml`
  - `deploy/kind/control-plane/web-app-service.yaml`
  - `deploy/kind/control-plane/kustomization.yaml`
  - `scripts/kind-control-plane-smoke.py`
  - `openspec/changes/autorefresh-web-app/tasks.md`
- Tasks:
  - Connect the browser UI to the automatic update path for overview, rounds, round detail, inbox, and runtime.
  - Preserve selected round, filters, scroll context, existing rows, and existing timeline entries while applying incremental updates.
  - Add compact live update indicators for connected, reconnecting, stale, fallback polling, and failed states.
  - Make any manual refresh controls secondary/troubleshooting-only.
  - Add or update focused fixture/smoke coverage for browser-facing automatic updates and read-only no-spend behavior.
- Out of scope:
  - Backend stream contract changes that conflict with Group A.
  - Hub/MCP/Kubernetes source mutation.
  - Unrelated design refreshes or deployment topology changes.

## Integration Notes

- Both branches may touch `scripts/web_app_hub.py` and `scripts/test-web-app-hub.py`; integration must reconcile Group A backend event helpers with Group B frontend use of those helpers.
- Implementers should update only the task checkboxes they complete in `openspec/changes/autorefresh-web-app/tasks.md`.
- The integration branch is `round-20260510t132823z-77aa-integration`.

## Verification Commands

- `python3 scripts/validate-openspec-change.py autorefresh-web-app`
- `uv run scripts/test-web-app-hub.py`
- `python3 -m pytest scripts/test-web-app-hub.py` if pytest is available in the environment
- `python3 -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(), filename=p) for p in ('mcp_servers/scion_ops.py', 'scripts/hub-managed-templates.py', 'scripts/steward-state.py', 'scripts/kind-control-plane-smoke.py', 'scripts/smoke-mcp-server.py', 'scripts/validate-openspec-change.py', 'scripts/validate-steward-session.py', 'scripts/finalize-steward-pr.py', 'scripts/archive-openspec-change.py', 'scripts/final_review_repair.py', 'scripts/web_app_hub.py', 'scripts/test-openspec-change-validator.py', 'scripts/test-steward-session-validator.py', 'scripts/test-steward-pr-finalizer.py', 'scripts/test-openspec-archive.py', 'scripts/test-mcp-openspec-cli.py', 'scripts/test-mcp-progress-lines.py', 'scripts/test-mcp-base-branch.py', 'scripts/test-mcp-implementation-base-branch.py', 'scripts/test-web-app-hub.py', 'scripts/test-verdict-schema.py', 'scripts/test-final-review-repair.py')]"`
- `bash -n scripts/build-images.sh scripts/kind-bootstrap.sh scripts/kind-round-preflight.sh scripts/release-smoke-round.sh scripts/scion-runtime-patches.sh scripts/storage-status.sh deploy/kind/control-plane/config/broker-entrypoint.sh orchestrator/lib/github-branches.sh orchestrator/run-round.sh orchestrator/round.sh orchestrator/spec-round.sh orchestrator/spec-steward.sh orchestrator/implementation-steward.sh orchestrator/abort.sh`
- If kind is available and already configured: `python3 scripts/kind-control-plane-smoke.py --help` and the relevant no-spend web-app smoke path added by implementers.
