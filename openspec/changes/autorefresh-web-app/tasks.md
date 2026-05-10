# Tasks

- [x] 1.1 Identify the current web app snapshot endpoints, MCP watch/event sources, Hub message/notification sources, and Kubernetes readiness checks that need automatic update coverage.
- [x] 1.2 Define the browser-facing live update contract, including initial snapshot handling, update event types, stable ids, cursors, heartbeats, and source-specific error payloads.
- [x] 1.3 Implement a backend streaming or stream-like endpoint for overview, rounds, round detail timelines, inbox, and runtime updates without adding write operations.
- [ ] 1.4 Connect the frontend views to the automatic update path so new data appears without pressing a refresh button or reloading the page.
- [ ] 1.5 Preserve selected round detail state, filters, scroll context, and existing timeline entries while incremental updates are applied.
- [ ] 1.6 Add live connection indicators for connected, reconnecting, stale, fallback polling, and failed states.
- [ ] 1.7 Make any remaining manual refresh control secondary and ensure it is not required for ordinary monitoring.
- [x] 1.8 Add fixture or unit tests for initial snapshot plus incremental updates, duplicate event handling, timeline appends, inbox updates, runtime status changes, and final-review/status changes.
- [x] 1.9 Add reconnect and stale-state tests covering cursor resume or safe fallback snapshot behavior.
- [x] 1.10 Run OpenSpec validation for this change.
- [ ] 1.11 Run the repo's relevant static checks, web app tests, and no-spend smoke checks for the automatic update path.
