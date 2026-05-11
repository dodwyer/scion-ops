# Implementation Brief: wire-new-ui-1

## Scope

Implement the approved OpenSpec change `wire-new-ui-1` by wiring the separate `new-ui-evaluation` React/Vite UI to live, read-only operational data with an initial snapshot plus push-based browser updates. Fixture data remains available only through explicit development/test fallback. Existing `web-app-hub` UI paths, deployment, service, port, routes, and smoke behavior must remain unchanged.

## Task Groups

### Group A: live adapter, contracts, and read-only source aggregation

- Branch: `round-20260511t154050z-44ce-impl-codex`
- Owned paths:
  - `new-ui-evaluation/adapter.py`
  - `new-ui-evaluation/tests/`
  - `new-ui-evaluation/fixtures/preview-fixtures.json`
  - `new-ui-evaluation/src/types.ts`
  - `docs/new-ui-evaluation.md`
  - `openspec/changes/wire-new-ui-1/tasks.md`
  - `.scion-ops/sessions/20260511t154050z-44ce/findings/round-20260511t154050z-44ce-impl-codex.json`
- Out of scope:
  - React view/component implementation in `new-ui-evaluation/src/App.tsx`, `new-ui-evaluation/src/api.ts`, and `new-ui-evaluation/src/styles.css`
  - Kind/kustomize deployment manifests and smoke scripts
  - Existing UI files under `scripts/web_app_hub.py` and `deploy/kind/control-plane/web-app-*`
- Tasks:
  - Define the versioned live snapshot schema for overview, rounds, round detail, inbox, runtime, diagnostics, and raw source views.
  - Define the incremental event schema with stable ids, entity ids, source names, timestamps, version/cursor, payload, and source error/staleness metadata.
  - Add a read-only live data layer for Hub, MCP, Kubernetes, git, and OpenSpec sources, with explicit fixture fallback.
  - Add the backend push path, preferably SSE, including heartbeat, source freshness/staleness, replay/idempotency, and safe snapshot fallback.
  - Add adapter contract and read-only safety tests for snapshot/event payloads and mutation rejection.

### Group B: browser live merge, health states, deployment coexistence, and smoke coverage

- Branch: `round-20260511t154050z-44ce-impl-claude`
- Owned paths:
  - `new-ui-evaluation/src/App.tsx`
  - `new-ui-evaluation/src/api.ts`
  - `new-ui-evaluation/src/styles.css`
  - `new-ui-evaluation/src/__tests__/`
  - `new-ui-evaluation/src/types.ts`
  - `deploy/kind/control-plane/new-ui-evaluation-deployment.yaml`
  - `deploy/kind/control-plane/new-ui-evaluation-service.yaml`
  - `deploy/kind/control-plane/kustomization.yaml`
  - `scripts/kind-control-plane-smoke.py`
  - `docs/kind-control-plane.md`
  - `openspec/changes/wire-new-ui-1/tasks.md`
  - `.scion-ops/sessions/20260511t154050z-44ce/findings/round-20260511t154050z-44ce-impl-claude.json`
- Out of scope:
  - Existing UI implementation and manifests: `scripts/web_app_hub.py`, `deploy/kind/control-plane/web-app-deployment.yaml`, `deploy/kind/control-plane/web-app-service.yaml`
  - Adapter internals beyond shared TypeScript types needed to consume the contract
  - Orchestrator/steward scripts
- Tasks:
  - Implement initial snapshot loading plus incremental event handling in the React/Vite UI.
  - Preserve selected view, filters, grouping, scroll/expanded diagnostic context while events merge.
  - Add global and per-source connection health, freshness, stale, reconnecting, fallback, failed, and fixture labels.
  - Implement bounded reconnect/backoff, cursor or event-id resume, safe snapshot recovery, and stale-data preservation.
  - Add frontend tests for idempotent merges, duplicate/replayed events, reconnect behavior, stale indicators, source-specific failures, and fixture fallback labeling.
  - Add coexistence checks proving existing UI deployment/service/port/routes/health/lifecycle/operator path remain unchanged.

## Integration Plan

1. Pre-create and verify both implementer branches from `main` using `scripts/precreate-agent-branch.py`.
2. Start both implementers with bounded prompts and explicit owned/out-of-scope paths.
3. Wait for durable JSON handoff artifacts with `scripts/wait-for-review-artifact.py`; accept only non-blocked branches with branch movement.
4. Create `round-20260511t154050z-44ce-integration` from `main`, merge accepted implementation branches, resolve conflicts without changing unrelated areas, then push.
5. Run verification on the integration branch.
6. Create/advance final-review branch from the pushed integration SHA and wait for accepting final-review verdict.
7. Record ready state and PR metadata on steward branch.

## Verification Commands

- `python3 scripts/validate-openspec-change.py openspec/changes/wire-new-ui-1`
- `python3 -m pytest new-ui-evaluation/tests`
- `cd new-ui-evaluation && npm test -- --runInBand`
- `cd new-ui-evaluation && npm run build`
- `python3 scripts/kind-control-plane-smoke.py --help`
- If a kind control plane is available: `task kind:control-plane:smoke`
- Steward readiness after PR recording: `python3 scripts/validate-steward-session.py --project-root . --session-id 20260511t154050z-44ce --require-ready --require-pr`

## Branch Ownership

- `round-20260511t154050z-44ce-impl-codex` owns Group A.
- `round-20260511t154050z-44ce-impl-claude` owns Group B.
- `round-20260511t154050z-44ce-integration` is steward-managed integration only after handoffs are accepted.
- `round-20260511t154050z-44ce-final-review` is review-only and must be based on the pushed integration commit.
