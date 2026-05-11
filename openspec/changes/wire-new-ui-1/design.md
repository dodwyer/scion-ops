# Design: Wire New UI 1

## Overview

The new React/Vite evaluation UI should keep its current separation from the existing UI while changing its primary data source from fixture-backed snapshots to live operational reads. A new read-only live data layer should aggregate or bridge Hub, MCP, Kubernetes, git, and OpenSpec source state into the view payloads already used by the evaluation UI.

The browser contract is snapshot plus stream: each view can be initialized from a consistent snapshot, then maintained by typed incremental events. The transport may be Server-Sent Events, WebSocket, source-native watch bridging, or another stream-like mechanism, but the normal path must be push-based and must not depend on page refreshes or frequent whole-view reloads.

## Data Sources

Live data may be read from these source categories:

- Hub: sessions, rounds, agents, messages, notifications, branch metadata, validation and review state when available.
- MCP: tool and service status, watchable round events, runtime diagnostics, and source-specific errors.
- Kubernetes: pod, deployment, service, namespace, probe, and workload readiness for scion-ops components.
- Git: branch names, refs, commit ids, remote tracking state, and workspace evidence needed for operator inspection.
- OpenSpec: change directories, proposals, designs, tasks, delta specs, validation results, and task status.

The adapter or live data layer should preserve structured source identifiers, timestamps, versions, cursors, event ids, and source names when they exist. If a source lacks stable ids, deterministic fallback ids may be generated for display merging, but the event must still identify its source and fallback status.

## Delivery Contract

The live update contract should include:

- A schema/version identifier for snapshots and events.
- An initial snapshot for the visible view set, or a snapshot endpoint paired with a stream subscription cursor.
- Typed incremental events for round changes, timeline entries, inbox items, runtime health, diagnostics, source freshness, source errors, heartbeat, reconnect, stale, fallback, and fatal stream states.
- Stable ids for entities and events so the frontend can apply updates idempotently.
- A cursor, version, timestamp, or event id that lets the client resume after reconnect when the source supports it.
- Source-specific error and staleness metadata so one failed source does not blank unrelated healthy data.

Bounded polling is acceptable only as a degraded fallback when the push path is unavailable or a specific source has no watch-like API. It must be secondary to the stream path, rate-limited, visible to the operator as fallback mode, and must avoid repeated full page reloads.

## UI Behavior

The UI should treat live updates as the normal runtime path:

- Views should update in place without requiring refresh.
- Selected round detail, filters, grouping, scroll context, and visible expanded diagnostics should remain stable while events are merged.
- Duplicate or replayed events should update existing entities or be ignored, not create duplicate visible records.
- Existing data should remain visible if a source becomes stale or disconnected, with clear stale indicators.
- Runtime and diagnostics views should show global connection state and per-source freshness, last successful update time, degraded/fallback state, and current failure category when known.
- Fixture mode should be visibly identified as fixture-backed when explicitly enabled.

## Safety Boundaries

The live wiring narrows the earlier fixture-only rule only for read-only source reads. It does not add mutation authority. Loading snapshots, subscribing to streams, reconnecting, resuming from cursors, falling back to bounded polling, or rendering diagnostics must not start work, retry work, abort work, change Kubernetes resources, write git state, edit OpenSpec files, mutate Hub or MCP state, access secrets unnecessarily, or trigger model/provider execution.

The existing UI must remain separate from this new UI path. Implementation should not require the existing UI to share routes, services, browser state, stream endpoints, deployment lifecycle, or backend ownership with the new React/Vite evaluation UI unless a later change explicitly scopes that integration.

## Failure Handling

The client should reconnect with bounded or exponential backoff after stream interruption. When a cursor or event id is available, reconnect should resume from the latest acknowledged position. When resume is unavailable, the client may request a safe snapshot and continue applying later events.

Data that exceeds configured freshness thresholds should be marked stale. The threshold may be global by default and source-specific where needed. Stale data should remain inspectable. Source failures should degrade only the affected source, view, or fields when other sources remain healthy.

## Verification Strategy

Verification should cover:

- OpenSpec validation for this change.
- Snapshot contract tests for the live payload shapes consumed by the new UI.
- Event contract tests for typed incremental updates, stable ids, source metadata, timestamps, versions, and cursors.
- Frontend merge tests for duplicate and replayed updates, selected-view stability, stale indicators, source-specific failures, and fixture fallback labeling.
- Reconnect tests for heartbeat loss, bounded backoff, cursor resume, safe snapshot recovery, fallback mode, and failed stream state.
- Read-only safety tests proving snapshot load, subscribe, reconnect, resume, and fallback polling do not mutate Hub, MCP, Kubernetes, git, OpenSpec, runtime broker, secrets, PVCs, rounds, or model/provider state.
- Coexistence checks proving the existing UI deployment, service, port, routes, health checks, lifecycle, and operator access path are unchanged.
