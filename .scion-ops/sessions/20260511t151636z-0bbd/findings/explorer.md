# Explorer Findings: wire-new-ui-1

## Existing Framework

The repo uses OpenSpec change folders under `openspec/changes/<change>/` with:

- `proposal.md`
- `design.md`
- `tasks.md`
- `specs/**/spec.md`

Validation is implemented by `scripts/validate-openspec-change.py`. The validator requires the three top-level files, checkbox tasks in `tasks.md`, at least one `specs/**/spec.md`, and delta spec headings using `## ADDED Requirements`, `## MODIFIED Requirements`, or `## REMOVED Requirements` with `### Requirement:` and `#### Scenario:` entries.

The most relevant existing change is `openspec/changes/base-framework-1`, which introduced the separate `new-ui-evaluation` React/Vite preview. Its delta spec lives at `openspec/changes/base-framework-1/specs/new-ui-evaluation/spec.md`.

The second relevant change is `openspec/changes/autorefresh-web-app`, which already captures live-update semantics for the existing `web-app-hub`: initial snapshot plus incremental updates, live/reconnecting/stale/failed status, reconnect/fallback behavior, idempotent event merging, and read-only automatic updates.

## Lowest-Risk OpenSpec Files

For `wire-new-ui-1`, the lowest-risk artifact set is:

- `openspec/changes/wire-new-ui-1/proposal.md`
- `openspec/changes/wire-new-ui-1/design.md`
- `openspec/changes/wire-new-ui-1/tasks.md`
- `openspec/changes/wire-new-ui-1/specs/new-ui-evaluation/spec.md`

Use the existing `new-ui-evaluation` spec area rather than `web-app-hub`. The goal is to wire the new React/Vite evaluation UI to live operational data while preserving separation from the existing UI, so modifying `web-app-hub` would blur ownership and increase risk.

The new delta should mostly use `MODIFIED Requirements` against these `base-framework-1` requirements:

- `Mocked Operator Data Contract`
- `Core Mocked Operator Views`
- `Read Only Preview Safety`
- `Evaluation Verification`

It should add new requirements for the live data contract and delivery path, for example:

- `Live Operational Data Contract`
- `Push Based Update Delivery`
- `Connection Health And Staleness`
- `Graceful Reconnect And Fallback`
- `Read Only Live Wiring Safety`
- `Existing UI Separation`

## Key Constraint Conflict

`base-framework-1` intentionally says the preview must not read live Hub, MCP, Kubernetes, git, OpenSpec, or model-backed state. `wire-new-ui-1` must explicitly narrow or supersede that prior fixture-only rule for this evaluation UI, while keeping mutation prohibitions intact.

Recommended wording: live reads are now in scope only through defined read-only adapters/watchers for Hub, MCP, Kubernetes, git, and OpenSpec operational state. Writes remain out of scope unless a later change explicitly scopes them.

## Requirements To Capture

The change should specify:

- Live Hub, MCP, Kubernetes, git, and OpenSpec source flow into the new React/Vite UI.
- Browser updates are push-based by default, using SSE, WebSocket, MCP watch bridging, Kubernetes watch bridging, git/OpenSpec event publication, or an equivalent stream-like mechanism.
- The browser receives an initial snapshot and then incremental typed updates.
- Incremental events carry stable ids, source names, timestamps, versions, cursors, or event ids so the frontend can merge updates idempotently.
- Duplicate or replayed update events do not create duplicate visible rows, timeline entries, messages, or diagnostics.
- The UI shows connection health such as live, reconnecting, stale, fallback, and failed states.
- Stale data is preserved for inspection and marked as stale rather than being silently cleared.
- Source-specific failures degrade only affected views or fields when other sources remain healthy.
- Reconnect uses exponential or bounded backoff and resumes from the latest cursor/event id when available.
- Fallback polling, if allowed, is bounded and secondary to the push path; it must not become polling-heavy page reload behavior.
- The preview remains read-only: no starting, retrying, aborting, deleting, archiving, git mutation, OpenSpec mutation, Kubernetes mutation, Hub mutation, or model/provider work.
- Existing UI and new UI remain separate in code, deployment, service, routes, port, lifecycle, and operator access path.
- Fixture-only mocked data moves to a local development/test fallback rather than the primary runtime data source.

## Existing Implementation Shape

Current `new-ui-evaluation` code is fixture-oriented:

- `new-ui-evaluation/adapter.py` serves static assets plus `/api/fixtures`, `/api/overview`, `/api/rounds`, `/api/inbox`, `/api/runtime`, `/api/diagnostics`, and `/api/rounds/<id>`.
- `new-ui-evaluation/src/api.ts` performs snapshot fetches for those endpoints.
- `new-ui-evaluation/src/types.ts` defines the current view payload shapes.
- `new-ui-evaluation/fixtures/preview-fixtures.json` is the current data source.

The OpenSpec should avoid prescribing exact implementation files beyond the contract, but should make clear that these snapshot APIs may become the initial snapshot source and that a new stream endpoint/event contract should provide incremental updates.

## Suggested Verification

Require validation for:

- OpenSpec validation for `wire-new-ui-1`.
- Contract tests for initial snapshot payloads and incremental event payloads.
- Frontend merge tests for idempotent updates, stale-state display, source-specific failure handling, and preserving selected view/filter context.
- Reconnect tests for cursor resume, heartbeat loss, bounded backoff, and fallback mode.
- Read-only safety tests proving subscription, reconnect, fallback, and snapshot loading do not mutate Hub, MCP, Kubernetes, git, OpenSpec, or model/provider state.
- Coexistence checks proving the existing UI deployment, service, port, health checks, routes, and lifecycle remain unchanged.

## Risk Notes

The main risk is underspecifying the boundary between live reads and mutations. The spec should say exactly which live sources can be read and should keep all writes out of scope.

The second risk is implementing "live" behavior as repeated page-level snapshot reloads. The OpenSpec should require push-based delivery or stream-like updates as the primary path and allow bounded polling only as a degraded fallback.

The third risk is mixing the existing UI and new UI contracts. Keep the delta under `specs/new-ui-evaluation/spec.md` and repeat the separation requirement so implementation work does not alter the current `web-app-hub` surface unless a later change says so.
