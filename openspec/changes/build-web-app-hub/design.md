# Design: Build Web App Hub

## Overview

The web app hub will be an operator-facing read model over existing scion-ops state. It should favor direct, inspectable status over decorative presentation: dense enough for repeated operational use, but clear enough to spot readiness issues and round progress quickly.

The first implementation should be read-only. That keeps the source-of-truth model simple and avoids creating a second orchestration surface before the app has proven its monitoring value.

## Information Architecture

The app should provide these primary views:

- **Overview:** readiness summary for Hub, Runtime Broker, MCP, Kubernetes deployments, and agent pods; recent alerts or degraded checks; active round count.
- **Rounds:** list of active and recent rounds with round id, goal summary when available, status, phase, agent count, latest update time, and outcome.
- **Round Detail:** timeline of messages, notifications, participating agents, branch references, latest runner output, and final review/outcome when available.
- **Inbox:** operator-relevant messages and notifications, grouped by round when possible and clearly marked as unread/new only when the backing source exposes that state.
- **Runtime:** lower-level Hub, broker, MCP, and Kubernetes readiness details for diagnosing why rounds cannot progress.

## Data Sources

The implementation should reuse existing operational sources:

- Scion Hub API for agents, messages, notifications, runtime brokers, and grove-scoped state.
- Kubernetes API or existing MCP/server-side helpers for deployment, pod, service, and PVC readiness.
- Existing scion-ops MCP logic where it already normalizes round snapshots, outcomes, event cursors, and fallback log capture.

The app must not persist a competing copy of round state. Any local cache should be short-lived and clearly treated as a transport or rendering optimization.

Structured Hub, MCP, or normalized round fields are authoritative over text-derived values. In particular, branch references exposed as fields on agents, review payloads, outcome payloads, integration results, or normalized MCP round snapshots must be used before parsing message bodies, task summaries, agent names, or slugs. Text parsing is only a fallback for older payloads that do not expose structured branch fields.

## Backend Shape

A small server-side adapter may be added during implementation to present browser-friendly JSON endpoints. That adapter should:

- Resolve the active project/grove using the same configuration precedence as existing scion-ops tools.
- Normalize Hub, MCP, and Kubernetes failures into actionable categories such as `hub_auth`, `hub_state`, `broker_dispatch`, `runtime`, and `local_git_state` when those categories are available.
- Return timestamps, status strings, and identifiers without requiring the frontend to parse terminal text.
- Return final-review verdicts and branch references as explicit JSON fields so the frontend does not need to infer them from prose.
- Support polling or cursor-based incremental updates for round timelines.

## Frontend Behavior

The interface should prioritize scanning:

- Status indicators should be consistent across overview, rounds, and runtime views.
- Round rows should distinguish running, waiting, blocked, completed, and unknown states.
- Final-review verdicts such as accept, approved, request_changes, changes_requested, revise, or blocked should be visible in round rows or detail status when present, and should not be hidden behind a generic completed label.
- Round detail should identify branch references from structured backing fields before displaying any fallback-derived references.
- Time-sensitive data should show last refresh time and stale-state warnings.
- Empty states should identify whether there are no rounds, no messages, or a failed data source.
- Error states should preserve partial data where possible so one failed check does not blank the whole app.

## Operational Constraints

- The app should fit the existing local kind-based workflow and should not require port-forwarding for normal operation if the implementation can use existing host port mappings.
- Readiness must reflect actual runtime dependencies: Hub API reachability and auth, registered Runtime Broker providers, MCP reachability, Kubernetes deployment rollout, and agent pod status.
- The implementation should remain no-spend by default. It must not start model-backed rounds as part of ordinary app loading or smoke checks.
- Destructive or state-changing operations are intentionally excluded from the initial scope.

## Verification Strategy

Implementation should include focused verification that:

- Required views render with representative healthy, empty, and degraded data.
- Backend adapter responses preserve source identifiers and error categories.
- Branch-reference tests cover structured branch fields and prove they take precedence over text, task summary, agent name, and slug fallbacks.
- Final-review tests cover backend outcome mapping and frontend-visible rendering for both accepted and changes-requested verdicts.
- Round timeline updates can be refreshed without page reload.
- Kubernetes/Hub unavailable states are visible to the operator.
- The app does not invoke round-starting or state-changing commands during normal read-only use.
