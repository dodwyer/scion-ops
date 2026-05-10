# Tasks: Web App 2

- [ ] Define the browser-facing snapshot and push-event schema for feeds, rounds, round detail, inbox, runtime, and update health.
- [ ] Implement or select a push-capable backend transport such as server-sent events, WebSocket, MCP watch bridge, or cursor-based long polling.
- [ ] Implement frontend state merging with stable ids, newest-first feed insertion, replay protection, and preservation of selection, filters, and scroll context.
- [ ] Build the professional operator UI shell with compact navigation, status hierarchy, source health, timestamps, and degraded-state handling.
- [ ] Add reconnect, stale, fallback, and failed update states that retain last known data and identify affected sources.
- [ ] Verify pushed feed, round, inbox, timeline, and runtime updates using fixtures or local no-spend state.
- [ ] Verify duplicate/replayed events, reconnect recovery, and fallback polling behavior.
- [ ] Verify the app remains read-only and does not start model-backed work or mutate Hub, MCP, Kubernetes, git, or OpenSpec state.
