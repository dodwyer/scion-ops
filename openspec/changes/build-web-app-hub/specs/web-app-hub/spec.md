# Web App Hub Specification

## ADDED Requirements

### Requirement: Control Plane Overview

The system SHALL provide a browser-accessible control-plane overview for scion-ops operators and read-only reviewers using canonical Hub/MCP-derived state.

#### Scenario: Healthy control plane is visible

Given the Hub, broker, and MCP-backed state sources are reachable
When a user opens the web app hub
Then the app shows Hub health, grove context, provider and broker state, total agent count, phase counts, activity counts, and last refreshed time.

#### Scenario: Source outage is explicit

Given one or more canonical state sources cannot be reached
When the user opens or refreshes the web app hub
Then the app shows a degraded or unavailable source state with the failing source name and does not infer success from stale data alone.

### Requirement: Round Summary List

The system SHALL show active and recent Scion/OpenSpec rounds in a scan-friendly summary view.

#### Scenario: Operator scans active rounds

Given one or more rounds are observable from canonical Hub/MCP state
When the user views the round summary list
Then each round row shows round ID, project or repo label, change ID when known, base branch when known, expected or PR-ready branch when known, status, health, validation state, agent counts, blocker count, warning count, and updated time.

#### Scenario: Reviewer filters rounds

Given multiple rounds are visible
When the user filters by project, change, round ID, status, health, or validation state
Then the list updates to only matching rounds without changing the canonical source state.

#### Scenario: User copies identifiers

Given a round summary includes copyable identifiers
When the user activates a copy action for round ID, branch, project root, change ID, or artifact reference
Then the exact identifier is copied without requiring the user to select text manually.

### Requirement: Round Drilldown

The system SHALL provide a round drilldown that explains progress, current state, blockers, artifacts, and final outcome.

#### Scenario: User opens a running round

Given a round is running
When the user opens the round drilldown
Then the app shows progress lines, active agents, unhealthy agents, completed agents, latest events or messages, validation state, warnings, blockers, and the current next action.

#### Scenario: User opens a completed round

Given a round has completed successfully
When the user opens the round drilldown
Then the app shows the final verdict, terminal state when available, validation result, artifacts, PR-ready branch, and a next action to create or inspect the PR.

#### Scenario: User opens a blocked round

Given a round is blocked, degraded, unhealthy, or timed out
When the user opens the round drilldown
Then the app shows the blocking conditions and the clearest available next action without hiding raw status details needed for debugging.

### Requirement: Canonical Read Model

The system SHALL treat Hub/MCP-derived state as canonical for the MVP and SHALL NOT require browser users to query Kubernetes logs, CLI output, or MCP tools directly.

#### Scenario: UI status is derived from canonical fields

Given the facade receives Hub/MCP state for a round
When it computes a display status
Then the display status is derived from documented canonical fields and the raw source status remains available in drilldown details.

#### Scenario: No independent round truth is introduced

Given the app displays active or recent rounds
When source data changes
Then the app refreshes from canonical source data rather than relying on an independently edited browser-side or UI-owned status store.

### Requirement: Implementation Decision Gate

The system SHALL NOT be implemented until placement, authentication, browser API ownership, status mapping, freshness, retention, artifact link, and future mutation decisions are accepted in OpenSpec artifacts.

#### Scenario: Implementation remains blocked while decisions are unresolved

Given any required implementation readiness decision is unresolved
When implementation work is proposed
Then frontend code, API code, Kubernetes manifests, runtime scripts, tests, and product documentation for the web app hub remain out of scope.

#### Scenario: Accepted decisions unblock implementation

Given accepted OpenSpec artifacts define all required implementation readiness decisions
When implementation work is proposed
Then the implementation can use those accepted decisions as constraints without inventing app placement, auth, API schema, status mapping, freshness, retention, artifact, or mutation policy.

### Requirement: Browser API Contract

The system SHALL expose browser data through an accepted read-only HTTP contract whose ownership and backing source are defined before implementation.

#### Scenario: Browser API boundary is selected

Given implementation readiness is being evaluated
When the browser API contract is reviewed
Then the contract identifies whether the API is Hub HTTP backed, MCP backed, or hybrid and names the component that owns endpoints, schemas, versioning, and error envelopes.

#### Scenario: Browser API handles partial canonical source failures

Given one canonical source is unavailable while others remain reachable
When the browser requests summary or drilldown data
Then the API returns partial data with explicit source failure metadata rather than hiding the source outage or fabricating missing state.

### Requirement: Lifecycle Status Mapping

The system SHALL define exact mappings from canonical Hub/MCP fields to UI lifecycle statuses before implementation.

#### Scenario: Status mapping uses documented source fields

Given a round has raw status, terminal state, validation state, agent health, blocker count, warning count, timeout state, source reachability, updated time, and freshness metadata
When the UI displays a lifecycle status
Then the status is selected using a documented mapping and conflict precedence.

#### Scenario: Raw status remains inspectable

Given the UI lifecycle status differs from the raw Hub/MCP status
When the user opens round drilldown diagnostics
Then the raw source status and fields used for mapping remain visible.

### Requirement: Read First Safety Boundary

The MVP SHALL expose read-only browser behavior and SHALL NOT expose start, abort, retry, archive, or other mutating controls until explicitly approved.

#### Scenario: Reviewer cannot mutate rounds

Given a read-only reviewer opens the web app hub
When they inspect control-plane or round state
Then no mutating round control is available from the UI or browser API.

#### Scenario: Mutating action is deferred

Given an operator wants to start, abort, retry, or archive a round from the web app
When the MVP is in scope
Then the app presents no such control and the decision is tracked as a future change requiring explicit authorization and confirmation design.

#### Scenario: Server enforces read-only reviewer access

Given a read-only reviewer has access to the web app hub
When they send a browser API request
Then the server-side facade authorizes only read operations regardless of whether a mutating UI control is visible.

### Requirement: Data Freshness

The system SHALL make refresh and stale-state behavior visible to users.

#### Scenario: Data refreshes automatically

Given the user is viewing the round list or a round drilldown
When the app refreshes data through polling, long polling, server-sent events, or WebSocket updates
Then the user can see the last refreshed time and whether the latest refresh succeeded.

#### Scenario: Data becomes stale

Given the app cannot refresh from the canonical source within the configured freshness window
When the user views existing data
Then the app marks the data as stale and preserves the last known state without presenting it as current.

#### Scenario: Freshness contract is configured

Given implementation readiness is being evaluated
When the freshness behavior is reviewed
Then the selected transport, list and drilldown interval or heartbeat, stale threshold, event cursor or resume behavior, and backoff limits are documented.

### Requirement: Recent Round Retention Contract

The system SHALL define the canonical source and limits for recent and completed round history before implementation.

#### Scenario: Recent history source is selected

Given the UI promises active and recent rounds
When implementation readiness is evaluated
Then the accepted artifacts identify whether recent rounds come from currently observable Hub state, Hub/MCP event history, Git or worktree artifacts, or a separately approved persistent read model.

#### Scenario: Older history is unavailable

Given a completed round is outside the accepted retention source or window
When the user searches or filters for that round
Then the UI explains that the round is unavailable from the configured history source instead of implying it never existed.

### Requirement: Artifact Link Contract

The system SHALL define structured artifact reference behavior before rendering artifacts as clickable browser links.

#### Scenario: Artifact reference is displayed

Given the facade returns an artifact reference
When the UI renders the artifact
Then the display label, copy value, click target, authorization behavior, and missing-target behavior follow the accepted artifact contract.

#### Scenario: Artifact link semantics are unknown

Given an artifact reference type does not have accepted link semantics
When the UI renders the artifact
Then the UI may show a copyable plain-text reference but does not create a clickable link.

### Requirement: Browser Credential Containment

The system SHALL prevent Hub, MCP, and dev-auth credentials from being exposed to client-side JavaScript.

#### Scenario: Browser requests summary data

Given the browser requests control-plane or round data
When the request is served
Then any Hub/MCP credentials are used only by the server-side facade or selected trusted server component and are not returned in the browser payload.

#### Scenario: Redacted source metadata is displayed

Given the app displays source or authentication metadata
When metadata includes credential-bearing fields
Then the app shows only redacted source labels or non-secret identifiers.
