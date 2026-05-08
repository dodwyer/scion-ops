# Tasks

- [ ] 1.1 Implement a dedicated read-only web API facade backed by Hub/MCP state and document its dashboard, round detail, watch/events, artifact, freshness, and error response contract.
- [ ] 1.2 Build the dashboard view showing Hub connectivity, active/recent rounds, key counts, latest update time, and stale/unavailable states.
- [ ] 1.3 Build the round detail view showing progress lines, lifecycle status, terminal outcome, blockers, validation status, and per-agent state.
- [ ] 1.4 Build the event feed using message, notification, and agent-state updates with duplicate-safe cursor handling.
- [ ] 1.5 Build the artifacts panel from facade-provided link objects for branches, OpenSpec paths, Hub records, PR-ready branch status, validation output, and transcript/log links, with metadata-only rendering for local or unstable paths.
- [ ] 1.6 Add endpoint/auth/single-project configuration handling that reflects existing scion-ops Hub/MCP configuration without introducing a second source of truth or a project selector.
- [ ] 1.7 Add read-only guardrails so start, abort, and resume controls are absent or disabled unless explicitly enabled by a future approved scope.
- [ ] 1.8 Apply the dashboard completed-round display limit of active rounds plus the most recent 50 completed rounds or 14 days, whichever is smaller, and show when additional history is hidden.
- [ ] 1.9 Package the web hub for the repo Kubernetes deployment model, including image build integration, in-cluster Hub/MCP connectivity configuration, Secret/ConfigMap usage, and health/readiness behavior.
- [ ] 1.10 Add focused tests or fixtures for empty, active, blocked, completed, failed, partial-data, auth-error, project-configuration-error, artifact-link, retention-limit, and Hub-unavailable states.
- [ ] 1.11 Verify the implemented UI at desktop and mobile widths, including live update retry behavior and non-duplicated event rendering.
