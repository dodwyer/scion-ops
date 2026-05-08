# Design: Web App Hub

## Product Shape

The web app is an operational dashboard for scion-ops. The first screen should be the working hub itself, not a landing page. It should favor dense, scannable status over decorative presentation because the target users are maintainers, operators, and reviewers who need to answer operational questions quickly.

The initial product is read-focused. It can display backend-discovered controls as disabled or unavailable, but it must not start, abort, or resume rounds unless a later approved scope explicitly enables those actions and defines permission checks.

## Information Architecture

The app should provide these primary views:

- Dashboard: active and recent rounds, Hub/MCP connectivity, active agent count, blocked/terminal counts, and latest update time.
- Round detail: progress summary, terminal result, blockers, validation state, per-agent status, event feed, and artifacts.
- Agent detail or panel: agent role/name, state, status fingerprint, last activity, recent messages, and transcript/log link if exposed by the backend.
- Artifacts panel: branch names, validation output, OpenSpec change paths, PR-ready branch status, and related links.
- Settings/status panel: selected endpoint, grove/project identity, auth state category, and refresh mode.

## Data Sources

The UI should consume a stable web-facing API backed by existing scion-ops Hub/MCP state. The initial implementation SHALL use a dedicated read-only web API facade between browser code and Hub/MCP. The facade may call Hub HTTP directly or use MCP internally, but it must expose a browser-oriented contract that preserves these concepts:

- Hub health and identity from the hub status affordance.
- Agents from `scion_ops_list_agents` or equivalent Hub agent state.
- Round summaries from `scion_ops_round_status`.
- Messages, notifications, agent changes, cursors, and progress lines from `scion_ops_round_events` and `scion_ops_watch_round_events`.
- Artifacts from `scion_ops_round_artifacts`.
- Spec validation/project status from `scion_ops_spec_status` where applicable.

The UI must not infer round truth from Kubernetes pods, local terminal files, or ad hoc log scraping when Hub/MCP state is available.

The facade contract should provide dashboard, round detail, round events/watch, and artifact endpoints or equivalent grouped responses. Returned objects should include stable identifiers, lifecycle state, server time, freshness/staleness metadata, and link objects with explicit labels and URL/path types. Unknown backend fields should be passed through only when they are safe to display as metadata; they should not become implicit UI behavior.

## Project Scope And Retention

The first release is scoped to one configured project/grove identity. The app should show that identity in status surfaces and treat missing or mismatched identity as a configuration error. It should not provide a project selector, cross-project aggregation, or multi-tenant switching until a later approved change defines discovery, authorization, and UX rules.

The dashboard should show all active rounds returned by the facade plus a bounded completed-round window. The default UI limit is the most recent 50 completed rounds or completed rounds from the last 14 days, whichever is smaller. Implementations may expose configuration to narrow that window, but must not silently expand beyond the default without an explicit later decision. When more completed rounds exist than are displayed, the UI should show that the list is limited.

## Artifact Link Contract

Artifact links must be explicit backend/facade data, not guessed client-side routes. Each artifact destination should include a human label, type, and target supplied by the facade. Supported first-release artifact types are:

- Branch or pull request links when a remote URL is known.
- OpenSpec change paths when the facade can provide a repository-relative path or hosted URL.
- Hub record links when the facade exposes a stable route or identifier.
- Transcript or log links when the facade exposes a stable endpoint.
- Local-only paths only as non-clickable text unless the facade marks them as openable in the current deployment context.

If the backend returns an artifact without a stable destination, the UI should render the artifact as unavailable or metadata-only rather than constructing a URL from naming conventions.

## Live Update Model

The round detail view should initialize from a status/events snapshot, then follow changes with a cursor-based watch operation, long-poll, server-sent events, or polling interval. Each update should be idempotent from the UI perspective: duplicate messages, notifications, or agent-state changes should not create duplicate timeline items.

When live watching fails, the UI should retain the last known state, surface the connectivity problem, and offer retry behavior. The dashboard should continue to make clear whether data is current, stale, or unavailable.

## Round Status Model

The app should normalize each round into a small display model:

- Round identity: round id, type if known, project/change if known, branch if known.
- Lifecycle: pending, running, blocked, completed, failed, aborted, or unknown.
- Progress: active/completed/stalled agent counts and progress lines.
- Terminal state: final summary, result, task summary, validation state, and completion time if available.
- Blockers: explicit blocker text reported by the backend or derived from failed validation/watch responses.
- Updates: ordered messages, notifications, and agent-state changes.
- Artifacts: branches, logs/transcripts, OpenSpec paths, PR links, and validation output links when available.

Unknown fields should render as unavailable rather than causing blank or misleading UI.

## Controls And Permissions

Read-only observation is the default requirement. Start, abort, and resume workflows are high-risk because they change operational state. If they are added later, the implementation must require explicit configuration, confirmation for destructive actions, and clear permission boundaries. Abort must require a confirmation step equivalent to the existing backend confirm flag.

## Deployment And Operations

The implementation should fit the repository's Kubernetes-only operating model. The web hub should be packageable as an image and deployable through the same Kubernetes deployment flow as the existing Hub/MCP services. Runtime configuration should come from Kubernetes environment, service discovery, ConfigMaps, and Secrets as appropriate; local-only scripts may be useful for development, but they are not the operational packaging model.

The web app deployment should define how the facade reaches Hub/MCP inside the cluster, how authentication material is provided without duplicating secrets, and how health/readiness checks distinguish UI availability from backend connectivity. The deployment should not require direct pod log access or host-local filesystem mounts to provide the specified UI.

## Error Handling

The app should distinguish these error classes:

- Hub unavailable or endpoint misconfigured.
- Authentication missing or rejected.
- Project/grove identity missing.
- Round not found.
- Watch cursor invalid or expired.
- Artifact unavailable.
- Backend returned partial data.

Partial data should be displayed with inline warnings rather than replacing the whole page with a generic failure whenever enough state exists to be useful.

## UX Notes

The UI should use compact tables, timelines, tabs, status chips, icon buttons, and panels consistent with an operations tool. It should avoid marketing content, large hero sections, and decorative cards that reduce information density.

The round detail page should make terminal outcomes and blockers visible without scrolling on common desktop viewports. Event and agent lists should remain usable on mobile through responsive stacking or horizontal overflow where appropriate.

## Verification Expectations

Implementation should be verified against mocked or fixture-backed API responses for empty, active, blocked, completed, failed, stale, and unavailable states. Browser-level checks should confirm that the dashboard and round detail remain readable at desktop and mobile widths and that live update retry behavior does not duplicate events.
