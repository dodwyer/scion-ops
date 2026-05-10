# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Round Detail Timeline

The system SHALL provide a round detail view that combines messages, notifications, agent status, runner output, validation state, final-review state, and final outcome for a selected round, and SHALL update that view through the browser live update channel as new backing data arrives.

#### Scenario: Operator inspects a round

- GIVEN a round exists in Hub-backed or MCP-backed state
- WHEN an operator opens that round detail view
- THEN the app shows available messages, notifications, status changes, validation state, final-review state, runner output, and terminal outcome
- AND shows participating agent names and statuses
- AND shows branch references from structured backing fields before any fallback-derived branch references
- AND indicates whether the displayed data is live, reconnecting, stale, fallback, or failed.

#### Scenario: New round detail update is pushed

- GIVEN new messages, notifications, agent status changes, runner output, validation changes, or final-review updates arrive for a selected round
- WHEN the operator keeps the round detail view open
- THEN the app receives the update through the live update channel without pressing a refresh button
- AND the newest operational update appears at the top of the detail update surface
- AND previously visible entries remain available and stable
- AND duplicate or replayed update events do not create duplicate visible entries.

#### Scenario: Timeline stream reconnects

- GIVEN the live update connection for a selected round is interrupted
- WHEN the app reconnects or resumes from the latest known cursor, event id, or safe snapshot version
- THEN missed round detail updates become visible when the backing source provides them
- AND replayed events are merged idempotently
- AND the view shows reconnecting or stale status until fresh data or heartbeat information is received.

### Requirement: Inbox And Notification Updates

The system SHALL provide an inbox view for operator-relevant Hub messages and notifications, and SHALL update that inbox through the browser live update channel as new updates arrive.

#### Scenario: Updates are grouped by round

- GIVEN Hub messages or notifications include round-identifying text or metadata
- WHEN an operator opens the inbox view
- THEN the app groups those updates by round where possible
- AND still shows ungrouped updates without hiding them.

#### Scenario: New inbox update is pushed

- GIVEN the operator has the inbox view open
- WHEN a new Hub message or notification becomes available
- THEN the inbox displays it through the live update channel without pressing a refresh button
- AND the newest inbox item or affected round group appears at the top of the inbox surface
- AND round grouping is updated when the new item can be associated with a round
- AND existing inbox items remain visible.

#### Scenario: No updates are available

- GIVEN Hub returns no messages or notifications for the active grove
- WHEN an operator opens the inbox view
- THEN the app shows an empty state that distinguishes no updates from a failed data source
- AND the live update status still indicates whether the inbox source is connected, stale, fallback, or failed.

## ADDED Requirements

### Requirement: Push First Live Delivery

The system SHALL deliver web app operational data to the browser through a push-first live update channel, such as WebSocket, server-sent events, MCP watch streams bridged to the browser, or an equivalent dynamic mechanism, so routine monitoring does not depend on refresh buttons or browser-side auto-refresh timers.

#### Scenario: Initial snapshot enters live mode

- GIVEN an operator opens the web app
- WHEN the initial data snapshot is loaded or delivered as the first live event
- THEN the app establishes a live update channel for visible operational views
- AND records the latest cursor, version, timestamp, or event id needed to merge subsequent updates
- AND shows the update path as connected when fresh data or heartbeat signals are being received.

#### Scenario: Round list update is pushed

- GIVEN a round is created, changes phase, becomes blocked, completes, receives validation results, or receives a final-review verdict
- WHEN the operator has the rounds view open
- THEN the round row updates through the live update channel without pressing a refresh button
- AND new or changed round status appears at the top of the current-operations surface
- AND structured status, terminal status, branch, validation, blocker, warning, and final-review fields remain authoritative over fallback text.

#### Scenario: Runtime readiness update is pushed

- GIVEN Hub, Runtime Broker, MCP, Kubernetes, or web app deployment readiness changes
- WHEN the operator has the overview or runtime view open
- THEN the relevant readiness state updates through the live update channel without pressing a refresh button
- AND the newest readiness change appears at the top of the current status surface
- AND healthy source details remain visible when another source becomes degraded.

#### Scenario: Non-push source is bridged

- GIVEN a backing source cannot provide direct push or watch events
- WHEN the backend can still retrieve safe read-only snapshots or cursor-based changes
- THEN the backend may bridge that source into the browser live update channel
- AND the UI indicates fallback or degraded live mode for the affected source
- AND the browser does not rely on a client-side auto-refresh timer for ordinary monitoring.

### Requirement: Refresh Controls Removed

The system SHALL remove operator-facing refresh buttons from normal monitoring screens because current operational data is delivered by the live update mechanism.

#### Scenario: Operator monitors overview and runtime

- GIVEN the live update channel is available or attempting recovery
- WHEN an operator views the overview or runtime screen
- THEN no ordinary refresh button is shown for keeping those screens current
- AND the operator can determine freshness from the live update status indicator.

#### Scenario: Operator monitors rounds, details, and inbox

- GIVEN the live update channel is available or attempting recovery
- WHEN an operator views rounds, round detail, or inbox screens
- THEN no ordinary refresh button is shown for keeping those screens current
- AND incoming updates are applied automatically through the live update channel.

#### Scenario: Diagnostic resync is retained

- GIVEN implementation retains a diagnostic resync action for troubleshooting
- WHEN that action is exposed to an operator
- THEN it is visually and semantically secondary to the live status indicator
- AND it is not labeled or positioned as the normal way to refresh operational data
- AND ordinary monitoring remains functional without using it.

### Requirement: Newest First Operational Updates

The system SHALL place newly arrived operational information at the top of relevant visible surfaces so operators can watch current status arrive without scanning to the bottom of the page.

#### Scenario: Live feed receives an update

- GIVEN an operator is viewing a feed, inbox group, round list, or round detail update surface
- WHEN a new live event is merged into the displayed data
- THEN the new operational item appears above older operational items in that surface
- AND existing filters, selected round context, expanded rows, and scroll context remain stable.

#### Scenario: Existing item changes

- GIVEN a pushed event updates an item that is already visible
- WHEN the event has the same stable source id or deterministic fallback id
- THEN the existing item is updated in place
- AND it is not duplicated
- AND its ordering reflects the latest meaningful operational update time when the view is sorted by recency.

### Requirement: Live Update Status

The system SHALL show the health of the live update path so operators can distinguish fresh pushed data from stale, fallback, reconnecting, or failed data.

#### Scenario: Updates are fresh

- GIVEN the app is receiving live events, watch events, heartbeat events, or server-bridged fallback updates within the configured freshness window
- WHEN an operator views any web app screen
- THEN the app shows the data as live or current
- AND the last successful update time is available to the operator.

#### Scenario: Updates are stale

- GIVEN the app has not received live events, heartbeat events, or successful fallback updates within the configured freshness window
- WHEN an operator views any web app screen
- THEN the app marks the affected data as stale
- AND identifies the affected source or view when that information is available
- AND preserves the last known data for inspection.

#### Scenario: Updates fail

- GIVEN the live update path fails and no safe fallback is available
- WHEN an operator views the affected screen
- THEN the app shows a failed update state
- AND includes a source-specific error category when available
- AND does not imply that the underlying round or control plane completed successfully merely because updates stopped.

### Requirement: Read Only Live Updates

The system SHALL keep live updates read-only and SHALL NOT perform state-changing operations while subscribing, reconnecting, replaying events, polling server-side fallback sources, or recovering from stale data.

#### Scenario: App receives live updates

- GIVEN an operator opens the app and live updates begin
- WHEN the app subscribes, reconnects, resumes from a cursor or event id, replays missed events, or receives server-bridged fallback updates
- THEN it does not start rounds
- AND it does not abort, retry, delete, archive, or mutate rounds
- AND it does not modify Kubernetes resources, Hub runtime records, git refs, or OpenSpec files.
