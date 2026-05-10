# Design: Web App 2

## Overview

Web App 2 should present Scion operations as a live console. The browser receives an initial snapshot and then applies pushed updates from a server-sent events stream, WebSocket, MCP watch bridge, cursor-based long poll, or another implementation-compatible transport. The chosen implementation stack is flexible, but the browser contract is fixed: routine monitoring updates automatically, and refreshed content appears in place without resetting the operator's current context.

## Update Model

The backend should expose a browser-facing update contract with typed events and stable identities. Events should cover at least:

- Feed item inserted, updated, removed, or acknowledged by source state.
- Round created, changed, blocked, completed, or updated with final-review and validation state.
- Round timeline event inserted or amended.
- Inbox message or notification inserted, updated, grouped, or marked source-stale.
- Runtime dependency health and source error changes.
- Heartbeat, reconnect, stale, fallback, and fatal update states.

Each event should include a source id, timestamp, cursor or version when available, source category, and enough structured fields for the frontend to merge updates idempotently. When a source lacks stable identifiers, deterministic fallback ids may be derived from source category, timestamp, round id, and content hash.

## Feed Ordering

Feed-style views should be newest-first by default. New pushed content should be inserted at the top of the relevant feed without clearing existing entries. The UI should preserve the selected round, active filters, sort controls, and scroll position. If the operator is scrolled away from the top, the app may show a compact pending-new-items affordance instead of forcing the viewport to jump.

Round detail timelines may keep chronological order when that better supports reading a sequence, but any feed or inbox summary of new operational content should place newly arrived items first. Duplicate or replayed events should update the existing row or item rather than creating a second visible entry.

## Operator UI

The interface should be restrained, dense, and work-focused:

- Persistent navigation for Overview, Feeds, Rounds, Round Detail, Inbox, and Runtime.
- Compact source-health and live-update indicators visible across views.
- Tables, split panes, timelines, and feed rows optimized for scanning round id, status, source, severity, branch, validation, final-review, and timestamp fields.
- Clear visual distinction between running, waiting, blocked, failed, accepted, stale, and unknown states.
- Empty, degraded, and failed states that explain the affected source without blanking unrelated data.
- No landing page, decorative hero, or marketing-style presentation as the first screen.

The visual system should use stable spacing, modest border radii, accessible contrast, predictable controls, and responsive layouts that remain usable on laptop-sized and narrow screens. Operator-critical text must not overlap or truncate in a way that hides status, branch, source, or timestamp values.

## Source Of Truth

Hub, MCP, Kubernetes, git, and OpenSpec state remain authoritative. The web app may keep temporary transport caches, replay buffers, or client-side stores, but those stores must be refreshable from source snapshots. Structured fields from source responses, including branch references, validation status, blockers, warnings, final-review verdicts, terminal state, and timestamps, take precedence over any text-derived fallback.

## Transport And Recovery

Server-sent events are sufficient for one-way updates, but WebSocket, long polling, or another framework-native mechanism is acceptable. Reconnect should resume from the latest known cursor or safe snapshot when available. If push transport is unavailable, bounded automatic polling may be used as a fallback and must be labeled as fallback mode in the UI.

Source-specific failures should degrade only the affected view or data source where possible. The app should retain last known data while marking it stale or failed, and it must avoid implying that a round has completed simply because updates stopped.

## Verification Strategy

Verification should cover:

- Initial snapshot followed by pushed updates without page refresh.
- New feed and inbox content appearing at the top.
- Idempotent duplicate and replay handling.
- Reconnect from cursor or snapshot with missed updates merged correctly.
- Live, reconnecting, stale, fallback, and failed indicators.
- Professional operator UI behavior across desktop and narrow viewports.
- No-spend, read-only behavior for load, subscribe, reconnect, and fallback polling paths.
