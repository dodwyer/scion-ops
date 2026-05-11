# Tasks: Wire New UI 1

- [x] Define the live snapshot schema for overview, rounds, round detail, inbox, runtime, diagnostics, and raw source views.
- [x] Define the incremental event schema, including event type, stable id, entity id, source name, timestamp, version or cursor, payload, and source error or staleness metadata.
- [x] Add a read-only live data layer for Hub, MCP, Kubernetes, git, and OpenSpec sources, with fixture mode retained only as an explicit development or test fallback.
- [x] Add a push-based browser update path using SSE, WebSocket, source-native watch bridging, or an equivalent stream-like mechanism.
- [ ] Implement initial snapshot plus incremental update handling in the React/Vite UI while preserving selected view, filters, grouping, scroll context, and expanded diagnostics.
- [ ] Add global and per-source connection health, freshness, stale, reconnecting, fallback, and failed indicators.
- [ ] Implement graceful reconnect with bounded backoff, cursor or event-id resume when available, safe snapshot recovery when resume is unavailable, and stale-data preservation.
- [ ] Add tests for snapshot contracts, event contracts, idempotent frontend merging, duplicate or replayed events, reconnect behavior, stale-data handling, source-specific failures, and fixture fallback labeling.
- [x] Add read-only safety tests proving live loading, streaming, reconnect, resume, and fallback polling do not mutate Hub, MCP, Kubernetes, git, OpenSpec, runtime broker, secrets, PVCs, rounds, or model/provider state.
- [ ] Add coexistence checks proving the existing UI deployment, service, port, routes, health checks, lifecycle, and operator access path remain unchanged.
