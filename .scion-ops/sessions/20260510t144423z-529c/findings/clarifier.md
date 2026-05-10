# Clarifier Findings: Dynamic Web App Operational Updates

## Goal Clarification

The requested change is to make the web app behave as a live operator console. Operational information should be delivered to the browser by a push-oriented or streaming mechanism, such as WebSocket, server-sent events, MCP watch streams bridged to the browser, or another modern live data delivery path. The operator should not need to press refresh or wait for a page-level auto refresh to understand current round, runtime, inbox, or control-plane status.

New operational events should be inserted at the top of the visible feed or page region so the newest status is immediately visible while the operator watches the screen. Existing refresh buttons should be removed from the normal UI because they imply manual polling and are no longer part of the intended workflow.

This clarification is stricter than a generic automatic refresh requirement. Browser-side timer polling may be acceptable only as a degraded fallback when a stream cannot be established, and the UI should make that fallback state visible. The primary implementation should use a live subscription, stream, watch, or equivalent push-style delivery path.

## Recommended Scope

In scope:

- Replace manual refresh controls with a live update connection for operator-facing views.
- Prefer WebSocket, SSE, MCP watch stream bridging, Kubernetes watch bridging, or another push-style mechanism over browser timer polling.
- Load an initial snapshot, then merge incremental updates into existing visible state.
- Insert newly received operational items at the top of timeline, inbox, and event/feed-style views.
- Preserve structured source-of-truth fields from Hub, MCP, Kubernetes, and normalized scion-ops helpers.
- Show live, reconnecting, stale, fallback, and failed update states so operators know whether the screen is current.
- Keep the interface read-only while subscribing, reconnecting, recovering, or using a fallback path.
- Verify with no-spend fixtures or local control-plane state only.

Out of scope:

- Starting, aborting, retrying, archiving, or otherwise mutating Scion rounds from the web app.
- Replacing Hub, MCP, Kubernetes, git, or OpenSpec as the source of truth.
- Adding authentication, hosted production deployment, or multi-user collaboration.
- Starting model-backed rounds during ordinary verification.
- A full rewrite solely for framework preference unless the existing stack cannot support the live update contract cleanly.

## Assumptions

- The current web app already has or will have JSON endpoints for overview, rounds, round detail, inbox, and runtime state.
- Existing MCP tools or helper paths can expose enough cursor, event id, timestamp, or version information to support incremental merging without duplicating events.
- If one backing source cannot stream directly, the backend may bridge that source into the browser stream using a controlled server-side watch or polling loop.
- The operator primarily needs current status and newest events first, but historical items should remain available below the newest entries.
- Removing visible refresh buttons does not remove safe internal recovery paths; reconnect and fallback behavior can still refresh data automatically.

## Unresolved Questions

- Should the preferred browser transport be WebSocket or server-sent events, or should the implementation choose based on the current Python/web stack?
- Which views must be newest-first: all event-like views, only the inbox and round detail timeline, or also the round list?
- Should a hidden or diagnostics-only manual refresh action remain available for troubleshooting, or should refresh controls be removed entirely from the UI?
- What freshness window should mark data as stale for each source?
- Should the first implementation extend the existing web app stack, or is a framework migration desired only if it materially improves the live update implementation?

## Recommended Change Name

`stream-operator-web-updates`
