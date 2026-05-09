# Delta: Web App Hub

## ADDED Requirements

### Requirement: Operator Overview

The system SHALL provide a web overview that summarizes scion-ops readiness from existing Hub, Runtime Broker, MCP, and Kubernetes runtime state.

#### Scenario: Control plane is ready

- GIVEN Hub is reachable and authenticated
- AND at least one Runtime Broker provider is registered for the active grove
- AND MCP is reachable
- AND required Kubernetes deployments are available
- WHEN an operator opens the overview
- THEN the app shows the control plane as ready
- AND the app shows the contributing Hub, broker, MCP, and Kubernetes checks as healthy.

#### Scenario: Runtime dependency is degraded

- GIVEN one or more Hub, Runtime Broker, MCP, or Kubernetes checks fail
- WHEN an operator opens the overview
- THEN the app shows the control plane as degraded or unavailable
- AND the app identifies which dependency failed
- AND the app preserves any healthy dependency details that are still available.

### Requirement: Round Progress Visibility

The system SHALL provide a web view of active and recent Scion agent rounds using Hub-backed agent, message, notification, and outcome state.

#### Scenario: Active round is listed

- GIVEN a Scion round has active agents in the Hub state
- WHEN an operator opens the rounds view
- THEN the app lists the round by round id
- AND shows the current status or phase
- AND shows the participating agents
- AND shows the latest available update time or message summary.

#### Scenario: Completed or blocked round is listed

- GIVEN a Scion round has terminal outcome state
- WHEN an operator opens the rounds view
- THEN the app distinguishes completed rounds from blocked rounds
- AND shows the final outcome or review status when available
- AND retains branch references when they are present in the backing state.

#### Scenario: Branch references use structured backing state

- GIVEN Hub, MCP, or normalized round state exposes branch references as structured fields for agents, reviews, outcomes, or integration results
- WHEN the app renders a rounds or round detail view
- THEN those structured branch fields are treated as the authoritative branch source
- AND message text, notification text, task summaries, agent names, or slugs are used only as fallback sources when no structured branch field is present
- AND the app does not label an agent name or slug as a branch when a structured branch value is available.

#### Scenario: Final review verdict is visible

- GIVEN Hub messages, notifications, or normalized outcome state include a final review verdict such as accept, approved, request_changes, changes_requested, revise, or blocked
- WHEN the app renders a rounds or round detail view
- THEN the visible status includes that final review verdict or an equivalent operator-readable outcome
- AND a changes-requested or blocked final review is not displayed as a generic completed state
- AND the round detail view shows the final-review source summary when available.

### Requirement: Round Detail Timeline

The system SHALL provide a round detail view that combines messages, notifications, agent status, runner output, and final outcome for a selected round.

#### Scenario: Operator inspects a round

- GIVEN a round exists in Hub-backed state
- WHEN an operator opens that round detail view
- THEN the app shows a chronological timeline of available messages and notifications
- AND shows participating agent names and statuses
- AND shows recent runner output when available
- AND shows final review or terminal status when available
- AND shows branch references from structured backing fields before any fallback-derived branch references.

#### Scenario: Timeline refreshes

- GIVEN new messages or notifications arrive for a selected round
- WHEN the app refreshes the round detail data
- THEN the new updates appear without requiring a full page reload
- AND previously visible timeline entries remain stable.

### Requirement: Inbox And Notification Updates

The system SHALL provide an inbox view for operator-relevant Hub messages and notifications.

#### Scenario: Updates are grouped by round

- GIVEN Hub messages or notifications include round-identifying text or metadata
- WHEN an operator opens the inbox view
- THEN the app groups those updates by round where possible
- AND still shows ungrouped updates without hiding them.

#### Scenario: No updates are available

- GIVEN Hub returns no messages or notifications for the active grove
- WHEN an operator opens the inbox view
- THEN the app shows an empty state that distinguishes no updates from a failed data source.

### Requirement: Source Of Truth Preservation

The system SHALL derive displayed operational state from existing scion-ops Hub, MCP, and Kubernetes sources instead of maintaining an independent persistent copy of runtime state.

#### Scenario: App renders runtime state

- GIVEN the web app displays readiness, rounds, messages, notifications, or agent status
- WHEN the data is loaded
- THEN the displayed values are derived from Hub, MCP, Kubernetes, or existing normalized scion-ops helper output
- AND any cache used by the app is temporary and refreshable from those sources.

#### Scenario: Backing source fails

- GIVEN one backing source is unavailable
- WHEN the app renders a view that also depends on other sources
- THEN the app shows a source-specific error for the unavailable dependency
- AND continues showing data from sources that responded successfully.

### Requirement: Read Only Initial Interface

The system SHALL keep the initial web app hub read-only and SHALL NOT expose round-starting, aborting, retrying, or other state-changing operations.

#### Scenario: Operator uses the initial app

- GIVEN an operator opens any web app hub view
- WHEN the app loads or refreshes data
- THEN it does not start rounds
- AND it does not abort, retry, delete, or mutate rounds
- AND it does not modify Kubernetes resources or Hub runtime records.
