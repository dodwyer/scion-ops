# Tasks

- [ ] 1.1 Identify browser-visible refresh controls, client-side interval refresh paths, snapshot endpoints, and existing live update code that affect overview, rounds, round detail, inbox, and runtime views.
- [ ] 1.2 Define the push-first browser event contract, including initial snapshot behavior, event types, stable ids, cursors or event ids, heartbeats, fallback markers, and source-specific error payloads.
- [ ] 1.3 Implement or update the backend live channel using WebSocket, server-sent events, MCP watch streams, or an equivalent push-capable mechanism while keeping all data access read-only.
- [ ] 1.4 Bridge any non-push backing source through the server-side live channel and mark it as fallback or degraded instead of relying on browser-side auto-refresh.
- [ ] 1.5 Connect frontend views to the live channel so new operational updates are inserted at the top of feeds, inbox groups, round lists, and round detail status surfaces.
- [ ] 1.6 Preserve selected round detail state, filters, expanded rows, scroll context, and existing visible entries while pushed events are merged.
- [ ] 1.7 Remove operator-facing refresh buttons and refresh-button-dependent workflows from normal overview, rounds, round detail, inbox, and runtime screens.
- [ ] 1.8 Add compact live connection indicators for connected, reconnecting, stale, fallback, and failed states, including last successful update time where available.
- [ ] 1.9 Add fixture or unit tests for pushed round status updates, timeline updates, inbox updates, runtime readiness changes, validation/final-review changes, duplicate event replay, newest-first insertion, and refresh button removal.
- [ ] 1.10 Add reconnect and fallback tests covering cursor or event-id resume, source-specific stale states, and server-side polling bridged through the live channel.
- [ ] 1.11 Run OpenSpec validation for this change.
- [ ] 1.12 Run relevant static checks, web app tests, and no-spend smoke checks for the live update path.
