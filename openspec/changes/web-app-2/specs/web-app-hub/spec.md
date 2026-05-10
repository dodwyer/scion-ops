# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Automatic Data Delivery

The system SHALL deliver web app data updates automatically to the browser through a push-capable live stream, watch connection, cursor-based long poll, or equivalent mechanism so routine monitoring does not depend on a refresh button.

#### Scenario: Initial snapshot starts live updates

- GIVEN an operator opens the web app
- WHEN the initial data snapshot is loaded
- THEN the app establishes an automatic update path for visible operational data
- AND the app records the latest cursor, version, timestamp, or event id needed to merge subsequent updates
- AND the app shows the update path as connected when fresh data or heartbeat signals are being received.

#### Scenario: Push update arrives

- GIVEN the browser has loaded an initial snapshot
- WHEN the backend receives new feed, round, inbox, timeline, or runtime data from Hub, MCP, Kubernetes, git, OpenSpec, or normalized helper output
- THEN the backend delivers a typed update to the browser without requiring a page refresh
- AND the browser merges the update into the existing view without clearing unrelated data
- AND structured source fields remain authoritative over text-derived fallback values.

#### Scenario: Stream falls back safely

- GIVEN the preferred push, stream, or watch mechanism is unavailable
- WHEN the web app can still retrieve snapshots from the backing sources
- THEN the app uses bounded automatic polling or another safe fallback to keep data current
- AND the UI indicates that fallback mode is active
- AND the fallback path does not expose write operations or start model-backed work.

### Requirement: Inbox And Notification Updates

The system SHALL provide an inbox view for operator-relevant Hub messages and notifications, and SHALL update that inbox automatically as new updates arrive.

#### Scenario: Updates are grouped by round

- GIVEN Hub messages or notifications include round-identifying text or metadata
- WHEN an operator opens the inbox view
- THEN the app groups those updates by round where possible
- AND still shows ungrouped updates without hiding them.

#### Scenario: New update arrives at top

- GIVEN the operator has the inbox view open
- WHEN a new Hub message or notification becomes available
- THEN the inbox displays it automatically without pressing a refresh button
- AND the new item appears before older inbox items by default
- AND round grouping is updated when the new item can be associated with a round
- AND existing inbox items remain visible.

#### Scenario: No updates are available

- GIVEN Hub returns no messages or notifications for the active grove
- WHEN an operator opens the inbox view
- THEN the app shows an empty state that distinguishes no updates from a failed data source.

### Requirement: Round Detail Timeline

The system SHALL provide a round detail view that combines messages, notifications, agent status, runner output, and final outcome for a selected round, and SHALL update that view automatically as new backing data arrives.

#### Scenario: Operator inspects a round

- GIVEN a round exists in Hub-backed state
- WHEN an operator opens that round detail view
- THEN the app shows available messages and notifications
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

#### Scenario: Selected round context is preserved

- GIVEN the operator is viewing a selected round detail
- WHEN pushed updates arrive for that round or for other rounds
- THEN the selected round remains selected
- AND active filters, expanded sections, and scroll context remain stable unless the operator changes them
- AND updates for other rounds do not interrupt the selected round view.

## ADDED Requirements

### Requirement: Newest First Operational Feeds

The system SHALL display feed-style operational content in newest-first order and SHALL insert newly received content at the top without a page refresh.

#### Scenario: Feed item is pushed

- GIVEN an operator is viewing an operational feed
- WHEN a new feed item is delivered by the automatic update path
- THEN the item appears above older feed items by default
- AND the app does not reload the page
- AND existing visible items are not cleared.

#### Scenario: Operator is scrolled away from top

- GIVEN an operator is viewing a feed and has scrolled away from the newest items
- WHEN one or more new feed items arrive
- THEN the app preserves the operator's scroll position
- AND indicates that new items are available at the top
- AND shows those items when the operator returns to the top or activates the new-items affordance.

#### Scenario: Duplicate feed event is replayed

- GIVEN a feed item has already been rendered
- WHEN the same source event is delivered again during replay, reconnect, or fallback refresh
- THEN the app updates the existing item when fields changed
- AND does not create a duplicate visible item.

### Requirement: Professional Operator Interface

The system SHALL present the web app as a professional, operator-focused console optimized for repeated monitoring and diagnosis.

#### Scenario: Operator opens the app

- GIVEN an operator opens the web app
- WHEN the first screen renders
- THEN the app shows the operational console rather than a landing page
- AND the primary navigation exposes overview, feeds, rounds, inbox, and runtime views
- AND live update health and source health are visible without requiring a secondary page.

#### Scenario: Operator scans active work

- GIVEN active or recent rounds, feed items, or runtime checks exist
- WHEN an operator scans the interface
- THEN status, severity, source, round id, branch, validation, final-review, and timestamp fields are visually organized for comparison
- AND blocked, failed, stale, accepted, running, waiting, and unknown states are distinguishable
- AND unavailable sources are shown as degraded without hiding healthy source details.

#### Scenario: Narrow viewport renders

- GIVEN the app is opened on a narrow viewport
- WHEN operational rows, feed items, status labels, and controls render
- THEN critical status, source, timestamp, round id, and branch information remains readable
- AND text does not overlap adjacent controls or content
- AND controls remain usable without relying on hover-only interactions.

### Requirement: Implementation Stack Flexibility

The system MAY use alternative languages, frameworks, or UI libraries when implementing Web App 2, provided the user-facing behavior and operational contracts in this specification are preserved.

#### Scenario: Alternative stack is selected

- GIVEN an implementation chooses a different backend, frontend, transport, or UI framework from the current app
- WHEN the app is built and run in the local control-plane workflow
- THEN it still consumes Hub, MCP, Kubernetes, git, and OpenSpec data through source-of-truth contracts
- AND it preserves browser-facing structured fields for statuses, branches, validation, blockers, warnings, verdicts, timestamps, and source errors
- AND it supports automatic updates, newest-first feeds, read-only behavior, and no-spend verification.

#### Scenario: Existing stack is retained

- GIVEN an implementation keeps the current backend or frontend stack
- WHEN push updates and operator UI changes are added
- THEN the app still satisfies the same push-update, newest-first feed, reconnect, fallback, and professional UI requirements
- AND the retained stack does not require operators to refresh the page for routine monitoring.

### Requirement: Read Only Push Updates

The system SHALL keep push subscriptions, reconnects, fallback polling, and client-side update merging read-only.

#### Scenario: App receives pushed updates

- GIVEN an operator opens the app and automatic updates begin
- WHEN the app subscribes, reconnects, resumes from a cursor, merges pushed events, or falls back to polling
- THEN it does not start rounds
- AND it does not abort, retry, delete, archive, or mutate rounds
- AND it does not modify Kubernetes resources, Hub runtime records, git refs, or OpenSpec files.
