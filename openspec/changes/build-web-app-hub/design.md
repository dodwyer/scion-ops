# Build Web App Hub Design

## Context

The repository is currently a Kubernetes-hosted scion-ops control plane rather than a frontend application. The existing runtime includes:

- Scion Hub started with Hub and web support.
- A dedicated Runtime Broker.
- A streamable HTTP MCP server.
- Kubernetes agent pods.
- MCP tools such as `scion_ops_hub_status`, `scion_ops_list_agents`, `scion_ops_round_status`, `scion_ops_round_events`, `scion_ops_watch_round_events`, `scion_ops_project_status`, `scion_ops_spec_status`, `scion_ops_validate_spec_change`, and `scion_ops_run_spec_round`.

The app should be a thin operational surface over those sources. The single source of truth for round state remains Hub/MCP-derived data.

## Proposed Architecture

Introduce a web app served as part of the scion-ops control-plane experience. The implementation should expose a browser-safe HTTP API/facade that normalizes existing Hub/MCP responses into UI view models:

- `ControlPlaneSummary`: Hub reachability, grove, providers, brokers, agent counts, phase/activity counts, auth/source metadata redacted for display.
- `RoundSummary`: round ID, project root/repo label, change ID, base branch, expected/PR-ready branch, status, health, validation status, agent counts, blocker count, warning count, terminal state, updated time, and copyable identifiers.
- `RoundDetail`: summary plus progress lines, agent state table, latest events/messages/notifications, blockers, warnings, artifacts, validation details, protocol/finalizer state, final verdict, and next action.
- `FilterState`: project, change, round ID substring, status, health, validation status, and updated-time range.

The facade should call canonical sources instead of requiring browser clients to understand MCP protocol details or Kubernetes internals. If implementation chooses to colocate the facade inside the existing MCP service, the browser API must remain ordinary HTTP/JSON and must not expose raw mutating MCP tools by default.

### Placement Decision Required

Implementation must choose one concrete placement before code work:

- Extend the existing Hub web surface.
- Add a separate scion-ops web service in the local kind control plane.
- Serve a browser-safe HTTP facade from the MCP service.

The accepted decision must name the Kubernetes object ownership model, local kind access path, port/service exposure, build artifact ownership, and how the app reaches Hub/MCP without manual patches. Until this decision is accepted, no implementation task should create frontend code, manifests, runtime scripts, or service wiring.

### Browser API And Schema Ownership Required

Implementation must choose the canonical browser API boundary before code work:

- Hub HTTP facade owned by Hub/web.
- MCP-backed facade owned by MCP/server code.
- Hybrid facade with explicit endpoint and schema ownership.

The accepted decision must define endpoint ownership, versioning expectations, source-to-view-model field ownership, read-only endpoint allowlist, error envelope, partial-source behavior, and whether raw Hub/MCP fields are exposed only in drilldown diagnostics. Browser clients must not call mutating MCP tools or query Kubernetes APIs directly.

## UX Model

The first screen should be the working operator hub, not a landing page. It should contain:

- A compact control-plane health strip.
- Active/recent rounds as a dense table or list optimized for scanning.
- Status and health indicators with clear labels, not color-only meaning.
- Quick filters and search by round/change/project.
- Copy buttons for common identifiers.
- A persistent "next action" area for selected or focused rounds.

Round drilldown should show:

- Round headline with status, health, validation, elapsed/updated time, branch, and final verdict.
- Progress lines in newest-relevant order while preserving the canonical text emitted by MCP helpers.
- Agent table grouped by active, unhealthy, and completed agents.
- Event/message timeline with cursor-aware refresh state.
- Blockers and warnings with actionable wording.
- Artifacts and PR-ready branch when available.

## Status Model

The UI should normalize canonical round state into a small display vocabulary:

- `starting`: no complete agent picture yet.
- `running`: active agents and no warnings/blockers.
- `degraded`: running with unhealthy agents, warnings, or partial data.
- `blocked`: terminal or operational blocker requires intervention.
- `timed_out`: monitoring timeout or round timeout condition.
- `completed`: protocol completed and artifacts/validation are ready.
- `unknown`: source unavailable or fields insufficient for classification.

Implementation must document the exact mapping from Hub/MCP fields to these statuses before code changes begin. Existing MCP statuses such as `running_degraded` may map to `degraded` for display while preserving raw status in drilldown.

The mapping decision must include, at minimum, source fields for raw round status, terminal state, validation result, agent health, blocker/warning counts, timeout conditions, source reachability, updated time, and missing/partial data. It must also define precedence when fields conflict, for example when validation succeeds but an agent is unhealthy or when the source is stale.

## Data Freshness

The MVP should support refresh without requiring the user to manually rerun terminal commands. Acceptable implementation options are:

- Browser polling of the facade for summaries plus round detail.
- Server-held long polling using `scion_ops_watch_round_events` semantics for drilldown updates.
- Server-sent events or WebSocket updates if the implementation environment already supports them cleanly.

Polling is acceptable for the MVP if intervals are bounded and visible stale-state indicators are provided. Direct browser polling of Kubernetes APIs or pod logs is not acceptable.

The accepted freshness decision must select one live update transport for list and drilldown views, default refresh interval or event heartbeat, stale threshold, failed-refresh display behavior, cursor/resume semantics for event streams when applicable, and any backoff limits needed to avoid adding load during active rounds.

## Retention

Recent rounds should be displayed from canonical Hub/MCP-observable state first. If the existing sources cannot list enough history for the requested "active/recent" experience, implementation must either:

- explicitly scope the MVP to currently observable Hub state, or
- introduce a persistent event/read-model design as a separate approved decision.

The spec does not approve a separate database for round history yet.

The accepted retention decision must state whether completed/recent rounds are limited to currently observable Hub state, Hub/MCP event history, Git/worktree artifacts, or a separately approved persistent read model. It must also define how many rounds or what time window the MVP promises, and what the UI shows when older completed rounds are unavailable.

## Authentication And Authorization

The MVP supports local operators and read-only reviewers, but the auth mechanism is unresolved. Implementation must decide how the browser authenticates to the facade and how reviewer read-only access is enforced.

Until that decision is made, the app must not expose mutating actions in the UI or browser API. Dev-auth tokens, Hub tokens, and MCP credentials must not be leaked to client-side JavaScript.

The accepted auth decision must define session establishment, local kind access assumptions, reviewer identity or token handling, read-only enforcement location, CSRF/CORS posture where relevant, and secret redaction rules. Read-only enforcement must be server-side, not only hidden UI controls.

## Artifact Links

Artifacts should be rendered from structured references returned by the facade, including branch names, file paths, validation output, and PR-ready branch names. The implementation must define whether artifact links open local files, GitHub branches, Hub storage entries, or facade-served artifacts before rendering them as clickable links.

The accepted artifact decision must define each supported artifact reference type, display label, copy value, click target, authorization behavior, missing-target behavior, and whether local workspace paths are shown as plain text or converted to links. The UI must not create clickable links whose target semantics are unknown or environment-specific.

## Open Decisions

- App location/local kind hosting: extend existing Hub web surface, add a separate scion-ops web service, or serve from the MCP service.
- Auth/session model for local operators and read-only reviewers, including server-side read-only enforcement.
- Browser API boundary and schema ownership: direct Hub HTTP API facade, MCP-backed facade, or hybrid facade.
- Exact Hub/MCP field mapping to canonical UI lifecycle statuses and conflict precedence.
- Live update mechanism, default refresh interval or heartbeat, stale threshold, and event cursor semantics.
- Retention/history source for completed/recent rounds beyond current Hub-observable state.
- Artifact link contract for local paths, branches, validation output, PR-ready branches, and facade-served artifacts.
- Whether mutating controls are included in a future change, and what confirmation and authorization model they require.

## Implementation Gate

Implementation is blocked until every open decision above is resolved by accepted OpenSpec artifacts. The future implementation tasks may start only after those artifacts name the selected options and define the required contracts. This spec-finalization pass must not infer those choices from current repository layout or reviewer comments.

## Risks

- A UI-specific status model could diverge from MCP status semantics unless mappings are explicit and tested.
- A browser client that directly receives Hub/MCP credentials would broaden the local attack surface.
- A separate persistence layer could become a second source of truth for round state.
- Polling too aggressively could add load to Hub/MCP during active rounds.
- Artifact links can mislead reviewers if local workspace paths are not visible from their environment.
