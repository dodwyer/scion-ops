# Proposal: Autorefresh Web App

## Summary

Update the web app hub specification so operational data arrives automatically instead of requiring an operator to press a refresh button. The browser should keep overview, rounds, round detail, runtime, and inbox data current through a live stream or equivalent incremental update mechanism while preserving the existing read-only, source-of-truth behavior.

## Motivation

The web app is intended to monitor active Scion rounds and control-plane status. Manual refresh makes that experience lag behind the underlying Hub, MCP, and Kubernetes state, and it requires operators to repeatedly poll the UI while waiting for progress. The app should behave more like a live operations console: new messages, status changes, validation results, final-review outcomes, and runtime degradations should appear without user action.

## Scope

In scope:

- Automatic browser updates for overview, rounds, round detail timelines, inbox, and runtime status.
- A backend delivery path based on server-sent events, WebSocket, MCP watch streams, cursor-based long polling, or another implementation-compatible streaming approach.
- Incremental update semantics that preserve existing visible rows and timeline entries while adding or updating changed data.
- Visible connected, reconnecting, stale, and failed update states.
- A fallback refresh path when streaming is unavailable, without making a refresh button the primary data path.
- No-spend verification using fixtures or local control-plane state only.

Out of scope:

- Starting, aborting, retrying, archiving, or otherwise mutating rounds from the web app.
- Replacing Hub, MCP, or Kubernetes as the source of truth.
- Adding hosted production deployment, authentication, or multi-user collaboration features.
- Requiring model-backed rounds for ordinary smoke tests.

## Assumptions

- Current Hub, MCP, or normalized round event sources expose enough timestamps, cursors, or event identifiers to support incremental updates without clearing the UI.
- If true push streaming is not available for every backing source, the backend may bridge polling or watch APIs into a browser stream as long as the browser receives automatic updates without operator action.

## Success Criteria

- Operators no longer need a refresh button to see new round messages, status transitions, validation failures, final-review outcomes, or runtime readiness changes.
- Round detail timelines append new entries without a full page reload and without duplicating existing entries.
- The UI clearly shows when live updates are connected, reconnecting, stale, or failed.
- Automatic updates do not start model-backed work or mutate Hub, MCP, Kubernetes, git, or OpenSpec state.
