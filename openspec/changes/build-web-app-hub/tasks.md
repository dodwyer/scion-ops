# Tasks

- [ ] 1.1 Decide the initial web API boundary: direct Hub, MCP adapter, or dedicated facade, and document the selected request/response contract in implementation notes.
- [ ] 1.2 Build the dashboard view showing Hub connectivity, active/recent rounds, key counts, latest update time, and stale/unavailable states.
- [ ] 1.3 Build the round detail view showing progress lines, lifecycle status, terminal outcome, blockers, validation status, and per-agent state.
- [ ] 1.4 Build the event feed using message, notification, and agent-state updates with duplicate-safe cursor handling.
- [ ] 1.5 Build the artifacts panel for branches, OpenSpec paths, PR-ready branch status, validation output, and transcript/log links when available.
- [ ] 1.6 Add endpoint/auth/project configuration handling that reflects existing scion-ops Hub/MCP configuration without introducing a second source of truth.
- [ ] 1.7 Add read-only guardrails so start, abort, and resume controls are absent or disabled unless explicitly enabled by a future approved scope.
- [ ] 1.8 Add focused tests or fixtures for empty, active, blocked, completed, failed, partial-data, auth-error, and Hub-unavailable states.
- [ ] 1.9 Verify the implemented UI at desktop and mobile widths, including live update retry behavior and non-duplicated event rendering.
