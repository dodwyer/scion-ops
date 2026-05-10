# Design: Autorefresh Web App

## Overview

The web app should move from operator-triggered refresh to an automatic update model. The browser-facing adapter should expose a stream or stream-like endpoint that emits typed updates for the views already defined by the web app hub: overview, rounds, round detail timelines, inbox, and runtime.

The implementation can choose the transport that fits the existing server stack. Server-sent events are likely sufficient for one-way operational updates, while WebSocket or cursor-based long polling are acceptable if they better match the existing MCP client or deployment constraints. The user-facing behavior is the contract: data changes arrive automatically, and the refresh button is not the normal way to keep the app current.

## Update Sources

The backend should continue to treat Hub, MCP, and Kubernetes as authoritative. Automatic updates may be produced from:

- MCP watch/event tools such as round event watches when available.
- Hub message, notification, and agent state queried by cursor, timestamp, or source id.
- Kubernetes readiness checks sampled by the backend and emitted only when status changes or staleness thresholds are crossed.
- Existing normalized scion-ops helpers that already combine round status, artifacts, validation, and final-review fields.

Structured fields remain authoritative over text fallbacks. The streaming path must preserve the same source identifiers, timestamps, branch references, validation states, blockers, warnings, and final-review verdicts that ordinary snapshot endpoints expose.

## Browser Contract

The browser should receive an initial snapshot followed by incremental updates, or it should load an initial snapshot and then subscribe from a cursor tied to that snapshot. Updates should be typed so the frontend can apply them without a full reload. Expected update categories include:

- Control-plane readiness and source error changes.
- Round created, updated, completed, blocked, or removed from the active set.
- Round timeline entries appended or amended.
- Inbox message or notification inserted, updated, or grouped.
- Runtime dependency health changed.
- Stream heartbeat, reconnect, stale, and fatal error states.

Each update should carry enough identity to merge it idempotently. Timeline and inbox entries should use stable source ids when present, with deterministic fallback ids only when the source lacks identifiers.

## UI Behavior

The UI should treat live updates as the default data path:

- A visible refresh button should not be required for normal operation.
- If a manual refresh control remains for troubleshooting, it must be secondary to the live status indicator.
- The app should show live, reconnecting, stale, and failed states in a compact operator-readable way.
- Existing rows, selected round detail context, scroll position, and filters should remain stable while updates arrive.
- New timeline entries should appear without duplicating old entries or clearing earlier context.
- Stale-state warnings should be based on the stream heartbeat or last successful update time, not only on the page load time.

## Failure Handling

The automatic update path should degrade gracefully. If the stream disconnects, the frontend should reconnect with the latest known cursor or snapshot version when available. If streaming is unavailable, the backend or frontend may fall back to bounded polling that still updates automatically.

Source-specific failures should not blank unrelated data. For example, an MCP stream failure may mark round timeline data stale while preserving Hub and Kubernetes readiness that remains available. Reconnect attempts must not start rounds, retry agents, mutate runtime resources, or write local repository state.

## Verification Strategy

Implementation should include focused checks for:

- Initial snapshot plus subsequent automatic round status and timeline updates.
- Idempotent handling of duplicate or replayed events.
- Reconnect from a cursor or safe fallback snapshot after stream interruption.
- Visible live, reconnecting, stale, and failed states.
- Automatic runtime and inbox updates without page reload.
- No-spend behavior proving app loading, streaming, reconnecting, and fallback polling do not start model-backed rounds or perform state-changing operations.
