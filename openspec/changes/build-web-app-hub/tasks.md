# Tasks

- [x] 1.1 Confirm the implementation entry point and web framework fit the existing repository tooling.
- [x] 1.2 Add a read-only backend adapter for Hub, Runtime Broker, MCP, Kubernetes readiness, rounds, messages, and notifications.
- [x] 1.3 Build the overview view for control-plane readiness and stale/degraded status visibility.
- [x] 1.4 Build the rounds list and round detail views for agent progress, branches, messages, notifications, runner output, and outcome.
- [x] 1.4.1 Ensure branch references are sourced from structured Hub/MCP/normalized round fields when present, with text/taskSummary/name/slug parsing used only as fallback.
- [x] 1.4.2 Ensure final-review verdicts are visibly rendered in rounds and round detail views, including changes-requested or blocked verdicts without collapsing them to generic completed state.
- [x] 1.5 Build the inbox/notifications view with round grouping and source-aware empty/error states.
- [x] 1.6 Add refresh behavior for current status and round timelines without starting or mutating rounds.
- [x] 1.7 Add focused tests or fixtures for healthy, empty, blocked, stale, and unavailable runtime states.
- [x] 1.7.1 Add tests proving structured branch fields take precedence over fallback text or agent-name-derived branch references.
- [x] 1.7.2 Add tests proving final-review verdicts are exposed by the backend and visibly rendered by the frontend for accepted and changes-requested outcomes.
- [x] 1.8 Verify the app through the repo's standard static checks and no-spend control-plane checks.
- [x] 1.9 Normalize approved final-review verdicts to accepted MCP outcome state.
