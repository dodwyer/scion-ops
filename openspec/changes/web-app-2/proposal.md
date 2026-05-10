# Proposal: Web App 2

## Summary

Evolve the web app into a live, operator-focused console where new operational content is pushed into the browser and inserted at the top of feeds without requiring a page refresh. The implementation may use the current stack or an alternative language/framework when that better supports reliable push delivery, clear state management, and maintainable operator workflows.

## Motivation

Operators need to watch active rounds, inbox messages, runtime status, validation results, and final-review outcomes as they change. A refresh-oriented interface causes missed context, stale decisions, and unnecessary reloads. The next version should behave like a professional operations surface: live by default, visually restrained, dense enough for scanning, and explicit about source health.

## Scope

In scope:

- Push or push-like browser updates for operational feeds, round lists, round detail timelines, inbox updates, and runtime status.
- New content inserted at the top of feed-style views while preserving selection, filters, and scroll context.
- A professional operator UI with compact navigation, clear status hierarchy, source health, timestamps, and degraded-state treatment.
- Backend and frontend implementation freedom, including alternative languages or frameworks, as long as source-of-truth and read-only contracts are preserved.
- Idempotent update merging, replay handling, reconnect behavior, and safe fallback when push transport is unavailable.
- No-spend verification using fixtures, local state, or mocked transports only.

Out of scope:

- Starting, aborting, retrying, archiving, or otherwise mutating rounds from the web app.
- Replacing Hub, MCP, Kubernetes, git, or OpenSpec as the source of truth.
- Hosted production deployment, authentication expansion, or multi-user collaboration.
- Model-backed round execution as part of ordinary UI verification.

## Success Criteria

- Operators see new feed items, round updates, inbox entries, timeline events, and runtime changes without refreshing the page.
- Feed-style views place newly received content at the top and avoid duplicate entries during replay or reconnect.
- The interface reads as a professional operations console rather than a marketing page or decorative dashboard.
- Live, reconnecting, stale, fallback, and failed update states are visible without hiding the last known data.
- App loading, push subscriptions, reconnects, and fallback polling remain read-only and no-spend.
