# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Round Detail Timeline

The system SHALL provide a round detail view that combines messages, notifications, agent status, runner output, and final outcome for a selected round, and SHALL update that view automatically as new backing data arrives.

#### Scenario: Operator inspects a round

- GIVEN a round exists in Hub-backed state
- WHEN an operator opens that round detail view
- THEN the app shows a chronological timeline of available messages and notifications
- AND shows participating agent names and statuses
- AND shows recent runner output when available
- AND shows final review or terminal status when available
- AND shows branch references from structured backing fields before any fallback-derived branch references.

#### Scenario: Timeline updates automatically

- GIVEN new messages, notifications, status changes, runner output, or final-review updates arrive for a selected round
- WHEN the operator keeps the round detail view open
- THEN the new updates appear without pressing a refresh button
- AND the app does not require a full page reload
- AND previously visible timeline entries remain stable
- AND duplicate or replayed update events do not create duplicate visible entries.

#### Scenario: Timeline stream reconnects

- GIVEN the automatic update connection for a selected round is interrupted
- WHEN the app reconnects or falls back to an automatic snapshot refresh
- THEN the round detail view resumes from the latest known cursor or safe snapshot
- AND missed timeline entries become visible when the backing source provides them
- AND the view shows reconnecting or stale status until fresh data is received.

### Requirement: Inbox And Notification Updates

The system SHALL provide an inbox view for operator-relevant Hub messages and notifications, and SHALL update that inbox automatically as new updates arrive.

#### Scenario: Updates are grouped by round

- GIVEN Hub messages or notifications include round-identifying text or metadata
- WHEN an operator opens the inbox view
- THEN the app groups those updates by round where possible
- AND still shows ungrouped updates without hiding them.

#### Scenario: New update arrives

- GIVEN the operator has the inbox view open
- WHEN a new Hub message or notification becomes available
- THEN the inbox displays it automatically without pressing a refresh button
- AND round grouping is updated when the new item can be associated with a round
- AND existing inbox items remain visible.

#### Scenario: No updates are available

- GIVEN Hub returns no messages or notifications for the active grove
- WHEN an operator opens the inbox view
- THEN the app shows an empty state that distinguishes no updates from a failed data source.

### Requirement: Source Of Truth Preservation

The system SHALL derive displayed operational state from existing scion-ops Hub, MCP, and Kubernetes sources, and SHALL keep automatic browser updates aligned with those source-of-truth contracts instead of maintaining an independent persistent copy of runtime state.

#### Scenario: App renders runtime state

- GIVEN the web app displays readiness, rounds, messages, notifications, or agent status
- WHEN the data is loaded or updated automatically
- THEN the displayed values are derived from Hub, MCP, Kubernetes, or existing normalized scion-ops helper output
- AND any cache used by the app is temporary and refreshable from those sources
- AND the automatic update path preserves structured source identifiers, timestamps, statuses, branch fields, validation fields, blockers, warnings, and final-review verdicts when those fields are available.

#### Scenario: Backing source fails

- GIVEN one backing source is unavailable
- WHEN the app renders or automatically updates a view that also depends on other sources
- THEN the app shows a source-specific error for the unavailable dependency
- AND continues showing data from sources that responded successfully
- AND does not clear previously visible data unless the source-of-truth response explicitly indicates the data is gone.

## ADDED Requirements

### Requirement: Automatic Data Delivery

The system SHALL deliver web app data updates automatically to the browser through a live stream, watch connection, cursor-based long poll, or equivalent mechanism so routine monitoring does not depend on a refresh button.

#### Scenario: Initial snapshot starts live updates

- GIVEN an operator opens the web app
- WHEN the initial data snapshot is loaded
- THEN the app establishes an automatic update path for the visible views
- AND the app records the latest cursor, version, timestamp, or event id needed to merge subsequent updates
- AND the app shows the update path as connected when fresh data or heartbeat signals are being received.

#### Scenario: Round list updates automatically

- GIVEN a round is created, changes phase, becomes blocked, completes, or receives a final-review verdict
- WHEN the operator has the rounds view open
- THEN the round row updates automatically without pressing a refresh button
- AND structured status, terminal status, branch, validation, blocker, warning, and final-review fields remain authoritative over fallback text.

#### Scenario: Runtime readiness updates automatically

- GIVEN Hub, Runtime Broker, MCP, Kubernetes, or web app deployment readiness changes
- WHEN the operator has the overview or runtime view open
- THEN the relevant readiness state updates automatically without pressing a refresh button
- AND healthy source details remain visible when another source becomes degraded.

#### Scenario: Stream falls back safely

- GIVEN the preferred streaming or watch mechanism is unavailable
- WHEN the web app can still retrieve snapshots from the backing sources
- THEN the app uses bounded automatic polling or another safe fallback to keep data current
- AND the UI indicates that fallback mode is active
- AND the fallback path does not expose write operations or start model-backed work.

### Requirement: Live Update Status

The system SHALL show the health of the automatic update path so operators can distinguish fresh data from stale or disconnected data.

#### Scenario: Updates are fresh

- GIVEN the app is receiving stream events, watch events, heartbeat events, or successful automatic fallback refreshes within the configured freshness window
- WHEN an operator views any web app screen
- THEN the app shows the data as live or current
- AND the last successful update time is available to the operator.

#### Scenario: Updates are stale

- GIVEN the app has not received stream events, heartbeat events, or successful automatic fallback refreshes within the configured freshness window
- WHEN an operator views any web app screen
- THEN the app marks the affected data as stale
- AND identifies the affected source or view when that information is available
- AND preserves the last known data for inspection.

#### Scenario: Updates fail

- GIVEN the automatic update path fails and no safe fallback is available
- WHEN an operator views the affected screen
- THEN the app shows a failed update state
- AND includes a source-specific error category when available
- AND does not imply that the underlying round or control plane completed successfully merely because updates stopped.

### Requirement: Read Only Automatic Updates

The system SHALL keep automatic updates read-only and SHALL NOT perform state-changing operations while subscribing, reconnecting, polling, or recovering from stale data.

#### Scenario: App receives automatic updates

- GIVEN an operator opens the app and automatic updates begin
- WHEN the app subscribes, reconnects, resumes from a cursor, or falls back to polling
- THEN it does not start rounds
- AND it does not abort, retry, delete, archive, or mutate rounds
- AND it does not modify Kubernetes resources, Hub runtime records, git refs, or OpenSpec files.
