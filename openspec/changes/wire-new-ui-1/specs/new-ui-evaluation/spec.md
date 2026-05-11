# Delta: New UI Evaluation

## MODIFIED Requirements

### Requirement: Mocked Operator Data Contract

The system SHALL define schema-faithful operator data for the evaluation UI views so live backend wiring can replace fixtures without redesigning view data shapes, and SHALL keep mocked fixture data available only as an explicit development or test fallback once live wiring is enabled.

#### Scenario: Overview live data is available

- GIVEN the preview adapter or live data layer is running in live mode
- WHEN the overview view requests operator state
- THEN it receives live control-plane summary, source readiness, freshness, active round count, blocked round count, recent activity, and highest-priority operator attention target fields
- AND the payload identifies the source mode as live rather than mocked.

#### Scenario: Round workflow live data is available

- GIVEN the preview adapter or live data layer is running in live mode
- WHEN the rounds or round detail views request state
- THEN they receive live round identifiers, goals, states, phases, agents, branch evidence, validation state, final review state, blockers, timestamps, latest events, timeline entries, artifacts, runner output, and related messages
- AND source-specific errors or stale fields are represented without fabricating healthy fixture values.

#### Scenario: Runtime and diagnostics live data is available

- GIVEN the preview adapter or live data layer is running in live mode
- WHEN the runtime, source health, diagnostics, or raw payload views request state
- THEN they receive live Hub, MCP, Kubernetes, git, OpenSpec, adapter, and preview service health fields
- AND receive source-specific errors, degraded state, raw JSON examples, schema version, source timestamps, and freshness metadata
- AND long or raw diagnostic content remains available one level down from the default overview.

#### Scenario: Fixture fallback is explicit

- GIVEN fixture mode is explicitly enabled for local development or tests
- WHEN the preview UI loads data from fixtures
- THEN the payload and UI metadata identify the data as fixture-backed
- AND fixture fallback does not become the default production runtime path.

### Requirement: Core Mocked Operator Views

The system SHALL provide the current operator workflows in the new UI using live operational data as the primary runtime source while preserving fixture-backed examples for development and test evaluation.

#### Scenario: Operator opens the live overview

- GIVEN the new UI is running in live mode
- WHEN an operator opens the evaluation URL
- THEN the first screen shows a compact operational overview with live readiness, freshness, round counts, blocked work, recent activity, and the next useful inspection target
- AND the screen uses the new visual direction rather than a landing page or inherited current-UI layout.

#### Scenario: Operator reviews live rounds

- GIVEN live round data exists
- WHEN an operator opens the rounds view
- THEN the UI shows active and recent rounds in a dense comparison format
- AND exposes state, phase, validation, final review, branch evidence, blockers, timestamps, and latest event context
- AND allows read-only selection, filtering, or grouping of live records.

#### Scenario: Operator inspects a live round

- GIVEN a live round is selected
- WHEN the operator opens round detail
- THEN the UI shows summary, timeline, agents, decisions, validation, final review, artifacts, branch evidence, runner output, and related messages from live source data
- AND keeps raw payloads and detailed diagnostics in a drill-in, tab, expander, drawer, or diagnostics view.

#### Scenario: Operator reviews live inbox, runtime, and diagnostics

- GIVEN live inbox, runtime, and diagnostic data exists
- WHEN the operator opens those views
- THEN inbox messages are grouped by round or source with severity and timestamps
- AND runtime/source health shows Hub, MCP, Kubernetes, git, OpenSpec, adapter, and preview deployment status
- AND diagnostics expose raw payloads, schema metadata, source errors, freshness, and degraded-state evidence without crowding the default overview.

### Requirement: Read Only Preview Safety

The system SHALL keep the evaluation UI read-only while allowing live read-only access to Hub, MCP, Kubernetes, git, and OpenSpec operational state through the new UI live data path.

#### Scenario: Preview reads live sources safely

- GIVEN an operator loads, refreshes, filters, navigates, expands, or subscribes to any new UI view in live mode
- WHEN the preview needs data
- THEN it may read live Hub, MCP, Kubernetes, git, and OpenSpec operational state through defined read-only adapters, watchers, or stream bridges
- AND it does not read model-backed or provider-backed state except for read-only status fields explicitly exposed by the operational sources.

#### Scenario: Preview avoids mutations

- GIVEN an operator interacts with overview, rounds, round detail, inbox, runtime, diagnostics, or raw payload views
- WHEN controls are used, streams connect, streams reconnect, snapshots load, cursors resume, or fallback polling runs
- THEN the preview does not start, retry, abort, delete, archive, or mutate rounds
- AND does not modify Kubernetes resources, Hub runtime records, MCP state, git refs or files, OpenSpec files, secrets, PVCs, runtime broker state, or model/provider state.

#### Scenario: Preview communicates data source mode

- GIVEN the evaluation UI displays operational records
- WHEN an operator views live, stale, fallback, failed, or fixture-backed state
- THEN the UI or adjacent metadata makes the current source mode and freshness clear
- AND does not imply that stale, fixture-backed, or disconnected data is fresh source-of-truth state.

### Requirement: Evaluation Verification

The system SHALL include no-spend verification for the new UI live data contract, push-based update behavior, read-only safety, stale-data handling, and coexistence with the current UI.

#### Scenario: Static and contract checks run

- GIVEN implementation work for the live evaluation UI is complete
- WHEN maintainers run the relevant validation checks
- THEN TypeScript type checks and frontend build checks pass
- AND adapter or live data layer tests verify initial snapshot payloads and incremental event payloads
- AND the checks do not start model-backed work or contact live providers for mutations.

#### Scenario: Live update checks prove push behavior

- GIVEN live source data changes after the initial snapshot
- WHEN maintainers run live update verification
- THEN the UI receives typed incremental events through SSE, WebSocket, source-native watch bridging, or an equivalent stream-like mechanism
- AND updates appear without page reloads or polling-heavy whole-view refreshes
- AND duplicate or replayed events do not create duplicate visible rows, timeline entries, inbox messages, diagnostics, or source records.

#### Scenario: Reconnect and stale checks run

- GIVEN the live update connection is interrupted, delayed, or partially failed
- WHEN maintainers run reconnect and stale-data verification
- THEN the client reconnects with bounded backoff
- AND resumes from a cursor or event id when available
- AND falls back to a safe snapshot or bounded fallback polling only when the push path is unavailable
- AND preserves last known data with clear stale, reconnecting, fallback, or failed indicators.

#### Scenario: Safety and coexistence checks protect current systems

- GIVEN the evaluation UI is wired to live read-only data
- WHEN maintainers run safety and coexistence checks
- THEN snapshot loading, subscribing, reconnecting, cursor resume, and fallback polling do not mutate Hub, MCP, Kubernetes, git, OpenSpec, runtime broker, secrets, PVCs, rounds, or model/provider state
- AND the existing UI deployment, service, port, health behavior, routes, lifecycle, and operator access path remain unchanged
- AND failures in the new UI live path do not fail the existing UI's smoke path except where an explicit new-UI-only check is being run.

## ADDED Requirements

### Requirement: Live Operational Data Contract

The system SHALL expose live read-only operational data from Hub, MCP, Kubernetes, git, and OpenSpec to the new React/Vite evaluation UI through a versioned snapshot and event contract.

#### Scenario: Initial snapshot contains live source metadata

- GIVEN an operator opens the new UI in live mode
- WHEN the UI loads its initial snapshot
- THEN the snapshot includes schema version, source mode, generated timestamp, source names, source freshness, source health, and the current view payloads
- AND includes enough entity identity for the frontend to merge later incremental updates.

#### Scenario: Incremental events are typed and idempotent

- GIVEN a live source changes after the initial snapshot
- WHEN the live data layer emits an incremental update
- THEN the event includes event type, stable event id or deterministic fallback id, affected entity id, source name, timestamp, version or cursor when available, and payload
- AND replaying the same event does not duplicate visible UI records.

#### Scenario: Source-specific failure is represented

- GIVEN one live source is unavailable or degraded
- WHEN the snapshot or event stream reports state for affected views
- THEN the payload identifies the failing source and failure category
- AND preserves healthy source data from other sources
- AND does not silently clear previously visible data unless the source-of-truth response explicitly indicates removal.

### Requirement: Push Based Update Delivery

The system SHALL deliver routine new UI updates through a push-based browser path such as SSE, WebSocket, source-native watch bridging, or an equivalent stream-like mechanism.

#### Scenario: Snapshot starts stream processing

- GIVEN an operator opens the new UI
- WHEN the initial snapshot is loaded or delivered
- THEN the browser establishes a push-based update subscription for the visible live data
- AND records the latest cursor, event id, version, or timestamp needed to merge subsequent events
- AND shows the update path as live when fresh data or heartbeat signals are received.

#### Scenario: Browser updates without reload

- GIVEN Hub, MCP, Kubernetes, git, or OpenSpec state changes
- WHEN the change is relevant to the current new UI views
- THEN the browser updates the affected overview, rounds, round detail, inbox, runtime, diagnostics, or raw payload state without a page refresh
- AND does not depend on polling-heavy full snapshot reloads for normal monitoring.

#### Scenario: Fallback polling is bounded

- GIVEN the preferred push path or a source-native watch is unavailable
- WHEN the UI can still retrieve safe read-only snapshots
- THEN the system may use bounded fallback polling or safe snapshot refresh
- AND the UI indicates fallback mode
- AND fallback polling remains secondary to the push path and avoids page-level reload behavior.

### Requirement: Connection Health And Staleness

The system SHALL show global and per-source live connection health so operators can distinguish fresh, reconnecting, stale, fallback, and failed data.

#### Scenario: Updates are live

- GIVEN the UI receives stream events, watch events, heartbeat events, or successful bounded fallback refreshes within the freshness window
- WHEN an operator views any new UI screen
- THEN the UI marks the affected data as live or current
- AND makes the last successful update time available.

#### Scenario: Updates are stale

- GIVEN the UI has not received stream events, heartbeat events, or successful fallback refreshes for a source within the configured freshness window
- WHEN an operator views affected data
- THEN the UI marks that source or view as stale
- AND preserves the last known data for inspection
- AND identifies the affected source when known.

#### Scenario: Updates fail

- GIVEN the live update path fails and no safe fallback is available
- WHEN an operator views the affected screen
- THEN the UI shows a failed update state
- AND includes a source-specific failure category when available
- AND does not imply that underlying rounds, validation, review, runtime, git, or OpenSpec state completed successfully merely because updates stopped.

### Requirement: Graceful Reconnect And Resume

The system SHALL recover from live update interruptions with bounded backoff and resume from the latest safe position when possible.

#### Scenario: Stream reconnects with cursor

- GIVEN the browser has received a cursor, version, timestamp, or event id
- WHEN the live update connection is interrupted
- THEN the browser reconnects using bounded or exponential backoff
- AND requests resume from the latest known safe position when supported by the live data layer.

#### Scenario: Stream recovers from safe snapshot

- GIVEN resume from a cursor is unavailable or rejected
- WHEN the browser reconnects
- THEN it requests a safe read-only snapshot
- AND applies later incremental events from the new snapshot position
- AND preserves operator-visible context where possible.

#### Scenario: Reconnect remains read-only

- GIVEN reconnect, resume, safe snapshot recovery, or fallback polling is running
- WHEN the live data path communicates with Hub, MCP, Kubernetes, git, or OpenSpec
- THEN it performs only read-only operations
- AND does not start, retry, abort, delete, archive, mutate, or trigger model/provider work.

### Requirement: Existing UI Separation

The system SHALL preserve the separation between the existing scion-ops UI and the new React/Vite evaluation UI while adding live data wiring to the new UI.

#### Scenario: Existing UI remains unchanged

- GIVEN the new UI live data path is deployed, restarted, disconnected, failed, or removed
- WHEN operators use the existing scion-ops UI
- THEN the existing UI Deployment, Service, port, health checks, routes, lifecycle scripts, data paths, and operator access path continue to behave as before
- AND the existing UI does not depend on the new UI stream endpoint, adapter, browser state, or fixture fallback.

#### Scenario: New UI remains separately addressable

- GIVEN both UIs are deployed
- WHEN an operator accesses the new React/Vite evaluation UI
- THEN it remains available through its own code path, deployment, service, port, routes, lifecycle, and operator access path
- AND live wiring for the new UI does not merge the two UI backends unless a future OpenSpec change explicitly scopes that integration.
