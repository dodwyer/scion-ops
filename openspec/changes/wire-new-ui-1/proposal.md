# Proposal: Wire New UI 1

## Summary

Wire the separate React/Vite evaluation UI to live operational data while preserving its independence from the existing scion-ops UI. The new UI should move from fixture-only mocked responses to live read-only data from Hub, MCP, Kubernetes, git, and OpenSpec sources, delivered through an initial snapshot plus push-based incremental updates such as Server-Sent Events, WebSocket, source-native watches bridged through the adapter, or an equivalent streaming mechanism.

The live path must make routine monitoring work without page refreshes or polling-heavy reloads. Fixtures remain available only as an explicit development or test fallback.

## Motivation

The evaluation UI currently proves the React/Vite visual and interaction direction with schema-faithful fixtures. Operators now need to evaluate the same UI against real control-plane state: active rounds, source health, inbox messages, Kubernetes runtime status, git branch evidence, and OpenSpec change state.

Using push-based delivery keeps the UI current without turning each view into repeated snapshot reloads. It also lets the UI surface connection health, reconnecting state, and stale source data explicitly so operators can distinguish fresh source-of-truth state from cached or degraded views.

## Scope

In scope:

- Replace the primary runtime data source for the new UI with live read-only Hub, MCP, Kubernetes, git, and OpenSpec data.
- Provide an initial snapshot followed by typed incremental updates for overview, rounds, round detail, inbox, runtime, diagnostics, and raw source views.
- Deliver browser updates through SSE, WebSocket, source-native watch bridging, or an equivalent push-based stream.
- Include stable event identity, source names, timestamps, versions, cursors, or event ids so updates can be merged idempotently.
- Show connection health, reconnecting, fallback, stale, and failed states at both global and source-specific levels.
- Preserve stale data for inspection while marking it stale instead of silently clearing it.
- Use graceful reconnect and bounded backoff, resuming from a cursor or safe snapshot when available.
- Keep all live wiring read-only unless a future OpenSpec change explicitly scopes mutations.
- Preserve the existing UI and the new UI as separate code, deployment, routes, ports, services, and operator access paths.
- Retain fixture data as an explicit local development or test fallback.

Out of scope:

- Starting, retrying, aborting, deleting, archiving, or otherwise mutating rounds from the new UI.
- Mutating Hub records, MCP state, Kubernetes resources, git refs or files, OpenSpec files, secrets, PVCs, model/provider state, or runtime broker state.
- Replacing, redesigning, merging, or deprecating the existing UI.
- Cross-UI backend consolidation or shared browser data stores between the existing UI and the new UI.
- Authentication, authorization, multi-user collaboration, historical replay, alert delivery, or outbound webhooks.
- Making fixture fallback the normal production data path.

## Success Criteria

- The new UI can load a live initial snapshot for all core operator views from read-only operational sources.
- Source changes appear in the browser through incremental updates without page refreshes or polling-heavy reloads.
- Duplicate or replayed events do not duplicate visible rows, timeline entries, inbox messages, diagnostics, or source records.
- Operators can see whether data is live, reconnecting, stale, in fallback mode, or failed, including which source is affected when known.
- Stream interruption triggers graceful reconnect with bounded backoff and preserves the last known data while marking it stale as needed.
- Fixture mode remains available for development and tests but is explicitly marked and not used as the default live runtime path.
- The existing UI deployment, service, port, routes, health checks, lifecycle, and operator access path remain unchanged.
- Validation covers the OpenSpec change, live snapshot and event contracts, idempotent frontend merging, reconnect behavior, stale-data display, source-specific failures, read-only safety, and UI coexistence.
