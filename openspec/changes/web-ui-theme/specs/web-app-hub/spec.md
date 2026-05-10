# Delta: Web App Hub

## ADDED Requirements

### Requirement: Operational Theme

The system SHALL present the web UI with a restrained operational theme optimized for monitoring live Scion state.

#### Scenario: Operator opens the web app

- GIVEN an operator opens the overview, rounds, round detail, inbox, or runtime view
- WHEN the view renders
- THEN the visual design uses neutral page and panel surfaces
- AND uses subdued borders, compact spacing, and readable typography
- AND avoids marketing-style hero sections, ornamental gradients, decorative illustrations, or purely decorative dashboard widgets.

#### Scenario: Theme supports repeated monitoring

- GIVEN an operator keeps the web app open while monitoring live rounds
- WHEN overview checks, round rows, timelines, metadata, validation details, branch refs, or runtime diagnostics update
- THEN the theme keeps operational data as the primary visual focus
- AND does not introduce layout motion, oversized typography, or decorative elements that compete with status changes.

### Requirement: Semantic Status Styling

The system SHALL use consistent semantic styling for operational states across all web app views.

#### Scenario: Healthy and active states are rendered

- GIVEN a source, round, live update path, final review, or validation result is healthy, ready, completed, accepted, connected, or running
- WHEN the app renders that state
- THEN the state is shown with a consistent operator-readable label
- AND the visual treatment distinguishes healthy or active state from neutral and degraded state without relying on color alone.

#### Scenario: Degraded and blocked states are rendered

- GIVEN a source, round, live update path, final review, or validation result is waiting, stale, observed, reconnecting, fallback polling, degraded, blocked, failed, unavailable, error, or changes requested
- WHEN the app renders that state
- THEN the state is shown with a consistent operator-readable label
- AND blocked, failed, unavailable, error, and changes-requested states are visually distinct from healthy, active, and waiting states
- AND source-specific error or blocker text remains visible when available.

#### Scenario: Unknown state is rendered

- GIVEN the app cannot classify a status from the backing source
- WHEN the app renders the status
- THEN the state uses a neutral unknown treatment
- AND the app does not imply that the underlying round, review, validation, or runtime source succeeded.

### Requirement: Dense Readable Operational Layout

The system SHALL keep existing web app information dense, stable, and readable for operator scanning.

#### Scenario: Round list is scanned

- GIVEN active, blocked, completed, and observed rounds are present
- WHEN an operator opens the rounds view
- THEN round id, status, decision flow, latest update, and outcome remain easy to compare in a table or table-like layout
- AND long summaries, branch names, blockers, and validation messages do not overlap adjacent cells or controls.

#### Scenario: Round detail is inspected

- GIVEN an operator opens a round detail view
- WHEN the app renders timelines, decision flow, consensus, final review, MCP state, branches, agents, and coordinator output
- THEN the layout preserves clear diagnostic grouping
- AND code-like values such as branch refs, JSON, runner output, and validation payloads use monospace treatment inside stable containers
- AND metadata such as role, template, harness, phase, activity, and branch source remains compact and readable.

#### Scenario: Runtime and inbox diagnostics are inspected

- GIVEN source errors, Hub messages, notifications, Kubernetes details, or MCP diagnostics are present
- WHEN an operator opens the inbox or runtime view
- THEN the theme preserves timestamps, source labels, status labels, and diagnostic payloads
- AND a failed source does not visually obscure healthy source details that are still available.

### Requirement: Responsive Operator Usability

The system SHALL keep the themed web app usable at typical desktop and narrow mobile widths.

#### Scenario: Narrow viewport renders primary views

- GIVEN the browser viewport is narrow
- WHEN an operator opens overview, rounds, round detail, inbox, or runtime
- THEN navigation, status labels, table content, panels, metadata pills, and action buttons do not overlap
- AND essential round identifiers and status values remain visible
- AND secondary columns or diagnostic details may wrap, collapse, or stack while preserving the primary monitoring workflow.

#### Scenario: Desktop viewport renders primary views

- GIVEN the browser viewport is desktop width
- WHEN an operator opens overview, rounds, round detail, inbox, or runtime
- THEN the app uses available width for efficient scanning
- AND avoids excessive whitespace, decorative section framing, or card nesting that reduces information density.

#### Scenario: Keyboard focus is visible

- GIVEN an operator navigates the web app with a keyboard
- WHEN focus moves through navigation buttons, refresh or back controls, and clickable round rows where applicable
- THEN the focused element has a visible focus treatment
- AND the focus treatment is consistent with the restrained operational theme.
