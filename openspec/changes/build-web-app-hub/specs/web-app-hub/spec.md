# Delta Spec: Web App Hub

## ADDED Requirements

### Requirement: Hub Dashboard

The system SHALL provide a browser-accessible dashboard for observing scion-ops round activity and backend connectivity.

#### Scenario: Show active and recent rounds

- GIVEN the backend has active or recent consensus, spec, or implementation rounds
- WHEN a user opens the dashboard
- THEN the dashboard shows each round identity, lifecycle state, latest update time, agent progress summary, and whether a terminal result or blocker exists

#### Scenario: Show empty round history

- GIVEN the backend is reachable and no active or recent rounds are available
- WHEN a user opens the dashboard
- THEN the dashboard shows an empty state that distinguishes no round history from a backend failure

#### Scenario: Show backend connectivity state

- GIVEN Hub or the web API facade is unavailable, misconfigured, or unauthenticated
- WHEN a user opens the dashboard
- THEN the dashboard shows the failing state category and does not present stale data as current

### Requirement: Round Detail View

The system SHALL provide a round detail view that summarizes progress, agent state, updates, terminal outcome, blockers, and artifacts for a selected round.

#### Scenario: Inspect running round

- GIVEN a round is running
- WHEN a user opens that round
- THEN the page shows progress lines, active/completed/stalled agent counts, per-agent state, and the latest messages or notifications

#### Scenario: Inspect terminal round

- GIVEN a round has terminal status
- WHEN a user opens that round
- THEN the page shows the terminal summary, result state, task summary when available, validation status when applicable, and completion signal without requiring the user to inspect raw logs

#### Scenario: Inspect blocked round

- GIVEN the backend reports one or more blockers for a round
- WHEN a user opens that round
- THEN the blockers are visible near the top of the round detail view and remain associated with the relevant terminal or in-progress state

### Requirement: Live Round Updates

The system SHALL update visible round progress from backend event snapshots or watch responses without requiring a full page reload.

#### Scenario: Follow new events

- GIVEN a user is viewing a round detail page
- WHEN new messages, notifications, or agent-state changes are reported by the backend
- THEN the page appends or updates the corresponding timeline and progress state while preserving the user's selected round

#### Scenario: Avoid duplicate events

- GIVEN the backend returns an event cursor or overlapping event snapshot
- WHEN the UI processes subsequent updates
- THEN messages, notifications, and agent-state changes that were already rendered are not duplicated

#### Scenario: Recover from watch failure

- GIVEN live watching fails after a round page has loaded
- WHEN the failure is detected
- THEN the UI keeps the last known state visible, marks the data as stale or disconnected, and offers retry behavior

### Requirement: Artifact Navigation

The system SHALL expose available artifacts and destinations associated with a round without inventing links that the backend did not provide.

#### Scenario: Show available artifacts

- GIVEN round artifacts include branches, OpenSpec paths, validation output, transcript links, log links, or pull request links
- WHEN a user opens the artifacts panel for the round
- THEN each available artifact is shown with a clear label and destination

#### Scenario: Hide unavailable artifact destinations

- GIVEN an artifact type is not present in the backend response
- WHEN the artifacts panel is rendered
- THEN the UI omits that destination or marks it unavailable without generating a guessed URL

### Requirement: Read-Only Default

The system SHALL be read-only by default for operational round state.

#### Scenario: Mutating controls are not in scope

- GIVEN the initial web app hub is deployed with default configuration
- WHEN a user views dashboard or round detail pages
- THEN start, abort, and resume controls are absent or disabled

#### Scenario: Abort remains guarded if later enabled

- GIVEN a future approved scope enables abort controls
- WHEN a user attempts to abort a round
- THEN the UI requires an explicit confirmation step before invoking the backend abort operation

### Requirement: Single Source Of Truth

The system SHALL derive displayed round state from scion-ops Hub or MCP-backed state rather than independent scraping or duplicated local records.

#### Scenario: Render from backend state

- GIVEN Hub or the MCP-backed facade returns round status, events, agents, and artifacts
- WHEN the UI renders dashboard and detail views
- THEN lifecycle, progress, terminal state, blockers, and artifacts are based on those backend responses

#### Scenario: Avoid direct Kubernetes scraping

- GIVEN Hub or MCP-backed state is available
- WHEN the UI needs round progress, messages, notifications, agent state, or artifacts
- THEN the UI does not scrape Kubernetes pods, terminal files, or local logs as the primary data source
