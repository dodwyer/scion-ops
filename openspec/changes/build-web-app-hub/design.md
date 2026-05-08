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

## Data Freshness

The MVP should support refresh without requiring the user to manually rerun terminal commands. Acceptable implementation options are:

- Browser polling of the facade for summaries plus round detail.
- Server-held long polling using `scion_ops_watch_round_events` semantics for drilldown updates.
- Server-sent events or WebSocket updates if the implementation environment already supports them cleanly.

Polling is acceptable for the MVP if intervals are bounded and visible stale-state indicators are provided. Direct browser polling of Kubernetes APIs or pod logs is not acceptable.

## Retention

Recent rounds should be displayed from canonical Hub/MCP-observable state first. If the existing sources cannot list enough history for the requested "active/recent" experience, implementation must either:

- explicitly scope the MVP to currently observable Hub state, or
- introduce a persistent event/read-model design as a separate approved decision.

The spec does not approve a separate database for round history yet.

## Authentication And Authorization

The MVP supports local operators and read-only reviewers, but the auth mechanism is unresolved. Implementation must decide how the browser authenticates to the facade and how reviewer read-only access is enforced.

Until that decision is made, the app must not expose mutating actions in the UI or browser API. Dev-auth tokens, Hub tokens, and MCP credentials must not be leaked to client-side JavaScript.

## Artifact Links

Artifacts should be rendered from structured references returned by the facade, including branch names, file paths, validation output, and PR-ready branch names. The implementation must define whether artifact links open local files, GitHub branches, Hub storage entries, or facade-served artifacts before rendering them as clickable links.

## Open Decisions

- App location: extend existing Hub web surface, add a separate scion-ops web service, or serve from the MCP service.
- Browser API boundary: direct Hub HTTP API facade, MCP-backed facade, or hybrid facade.
- Auth/session model for local operators and read-only reviewers.
- Live update mechanism and default refresh interval.
- Retention source for completed/recent rounds beyond current Hub-observable state.
- Artifact link contract.
- Whether mutating controls are included in a future change, and what confirmation model they require.

## Risks

- A UI-specific status model could diverge from MCP status semantics unless mappings are explicit and tested.
- A browser client that directly receives Hub/MCP credentials would broaden the local attack surface.
- A separate persistence layer could become a second source of truth for round state.
- Polling too aggressively could add load to Hub/MCP during active rounds.
- Artifact links can mislead reviewers if local workspace paths are not visible from their environment.
