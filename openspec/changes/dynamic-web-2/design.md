# Design: Dynamic Web App Push Updates

## Overview

The web app should behave as a live operations console. The backend owns source observation and exposes a browser-facing push channel. The frontend subscribes once, renders an initial snapshot, then applies typed events as they arrive. Browser-side interval refresh should not be the normal data path, and operator-facing refresh buttons should be removed from ordinary screens.

Server-sent events are sufficient for one-way operational updates. WebSocket is also acceptable if the chosen implementation benefits from bidirectional connection health or subscription management. The critical contract is that the browser receives updates from a live channel and does not poll snapshot endpoints on a timer as its primary mechanism.

## Event Flow

The backend should continue deriving state from Hub, MCP, Kubernetes, git, and existing normalized scion-ops helpers. It may combine multiple source mechanisms into one browser channel:

- MCP watch or round event cursor APIs when available.
- Hub messages, notifications, agent state, and runtime state read by cursor, source id, or timestamp.
- Kubernetes deployment, service, endpoint, and pod readiness watched directly or sampled server-side.
- Git and OpenSpec validation metadata read only when needed for displayed operational status.

The push channel should emit an initial snapshot event or require the frontend to load a snapshot and subscribe from the snapshot cursor. Subsequent events should be typed and mergeable. Expected event categories include round upserts, round removals, round timeline entries, inbox entries, runtime readiness changes, validation and final-review changes, heartbeat, source error, reconnect, stale, fallback, and fatal failure.

Each event must include stable identity for idempotent merge. Source ids from MCP, Hub, Kubernetes, git refs, or validation outputs are preferred. Deterministic fallback ids may be used only when the source lacks identifiers.

## UI Behavior

Live information should be optimized for an operator watching current state:

- New operational updates appear at the top of the relevant feed, inbox, and timeline surfaces.
- Existing visible entries are updated in place when their stable id reappears.
- Selected round detail, expanded rows, filters, and scroll context remain stable as new items arrive.
- Refresh buttons are removed from normal navigation and detail views.
- Any diagnostic resync behavior, if retained, is not presented as an ordinary refresh button and is secondary to live connection state.
- The live status indicator shows connected, reconnecting, stale, fallback, and failed states with the last successful update time.

Round detail may retain chronological historical grouping inside an expanded detail section if useful, but the current-operations surface should prioritize newest-first arrivals so the operator can watch status changes enter at the top.

## Fallback And Recovery

The preferred browser path is push. If a backing source cannot push directly, the backend may bridge server-side polling into the push channel and mark the affected source as fallback. If the browser live connection disconnects, the frontend should reconnect with the latest known cursor, event id, or snapshot version and accept replayed events idempotently.

Fallback must not hide degraded freshness. The UI should preserve last-known data and identify the affected source or view when the channel is stale or failed. A source-specific failure must not blank unrelated healthy data.

## Read-Only Boundary

All live update and recovery flows are read-only. Subscribing, reconnecting, cursor resume, replay, server-side source polling, and fallback snapshots must not start rounds, retry agents, archive changes, update Kubernetes resources, write git refs, or modify OpenSpec files.

## Verification Strategy

Implementation should include focused checks for:

- Initial snapshot followed by pushed round, inbox, runtime, validation, and final-review events.
- Newest-first insertion for live feed, inbox, and round detail updates.
- Removal of operator-facing refresh buttons from ordinary screens.
- Idempotent handling of duplicate or replayed events.
- Reconnect from a cursor or event id after interruption.
- Fallback source polling bridged through the push channel and shown as degraded live status.
- No-spend behavior proving loading, subscribing, reconnecting, replaying, and fallback recovery do not start model-backed rounds or mutate runtime state.
