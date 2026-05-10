# Proposal: Dynamic Web App Push Updates

## Summary

Update the web app hub specification so operational information reaches the browser through a push-first live mechanism, such as WebSocket or server-sent events, instead of timer-driven snapshot refresh. New operational updates should be inserted at the top of visible feeds and timelines so an operator can watch the latest status arrive without reloading the page or using refresh buttons.

## Motivation

The web app is an operations surface, not a report page. Operators need current round, inbox, runtime, validation, and final-review information to arrive as events when the control plane changes. Periodic auto-refresh and visible refresh buttons still frame the UI as a polling tool and can hide whether data is genuinely live. The interface should communicate current status through a modern live data channel and make newly arrived information immediately visible at the top of the screen.

## Scope

In scope:

- Push-first browser delivery for overview, rounds, round detail, inbox, and runtime status.
- A backend live update channel using WebSocket, server-sent events, MCP watch streams bridged to the browser, or an equivalent push-capable mechanism.
- Removal of operator-facing refresh buttons and refresh-button-dependent workflows.
- Newest-first insertion for live feeds, inbox items, status events, and round detail updates where operators monitor arrival order.
- Compact live, reconnecting, stale, and failed indicators based on the push channel and source-specific freshness.
- Read-only behavior for subscribing, reconnecting, replaying missed events, and recovering from disconnects.
- Verification with fixtures or local control-plane state, without starting model-backed work.

Out of scope:

- Adding round start, abort, retry, archive, delete, or other mutation controls.
- Replacing Hub, MCP, Kubernetes, git, or OpenSpec as the source of truth.
- Hosted production deployment, authentication, or multi-user collaboration.
- Requiring model-backed rounds for routine validation.

## Assumptions

- Hub, MCP, or normalized scion-ops helpers expose enough source ids, timestamps, cursors, or event ids for idempotent live updates.
- If a backing source only supports polling, the server may bridge that polling into the browser-facing push channel, but the browser contract remains push-first and does not rely on a visible refresh button or client-side snapshot timer.
- Newest-first visual ordering is the preferred operator view for monitoring current status; historical context may remain available through stable expanded detail sections or filters.

## Success Criteria

- Operators can see new operational data arrive without page reloads, refresh buttons, or client-side auto-refresh timers as the primary mechanism.
- New updates appear at the top of relevant views while existing rows, filters, selected round context, and expanded details remain stable.
- Round status, validation, final-review, inbox, and runtime changes are delivered through the live channel or a server-managed fallback surfaced as degraded live status.
- The UI clearly distinguishes live, reconnecting, stale, fallback, and failed update states.
- Subscribing, reconnecting, and fallback recovery remain read-only and do not mutate Hub, MCP, Kubernetes, git, or OpenSpec state.
