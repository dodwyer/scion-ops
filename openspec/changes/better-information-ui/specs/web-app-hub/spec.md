# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Operator Overview

The system SHALL provide a NiceGUI operator overview that summarizes scion-ops readiness and recent round activity with concise, relevant information focused on operator action, handoff, reason for handoff, source health, and the next useful inspection target.

#### Scenario: Operator opens concise overview

- GIVEN Hub, MCP, Kubernetes, broker, web app, live update, and round sources provide current state
- WHEN an operator opens the overview
- THEN the overview shows control-plane readiness and live freshness first
- AND shows active, blocked, and recent round context in compact summaries
- AND highlights the highest-priority source or round needing attention when one exists
- AND avoids showing raw payloads, long logs, exhaustive validation output, or low-level diagnostic details by default.

#### Scenario: Overview activity favors actionable context

- GIVEN recent round activity includes messages, notifications, agent status, handoffs, or outcome updates
- WHEN the overview renders recent activity
- THEN each activity item favors the current action, handoff target when present, reason for handoff when present, timestamp, status, and source
- AND omits irrelevant backing fields from the default row
- AND provides a one-level-deeper control for detailed diagnostics when those details are available.

#### Scenario: Overview remains source backed and read only

- GIVEN the overview displays readiness, activity, blockers, warnings, or source errors
- WHEN the data is loaded, refreshed, or updated live
- THEN displayed values are derived from existing structured Hub, MCP, Kubernetes, live update, or normalized helper output
- AND fallback-derived action, handoff, or reason text is used only when structured fields are unavailable
- AND loading, refreshing, drilling into details, or receiving live updates does not mutate round state, Hub records, Kubernetes resources, git refs, or OpenSpec files.

### Requirement: Round Detail Timeline

The system SHALL provide a selected-round timeline that presents each meaningful source entry as a stable row with action, handoff, reason for handoff, status, timestamp or sequence, agent or source, and optional one-level-deeper diagnostics.

#### Scenario: Operator inspects selected round timeline

- GIVEN a selected round has messages, notifications, agent transitions, runner updates, final-review updates, or outcome state
- WHEN the operator opens the round detail timeline
- THEN the timeline shows entries in chronological or deterministic sequence order
- AND each entry shows the responsible agent or source
- AND each entry shows an operator-readable action
- AND each entry shows the handoff target when a handoff exists
- AND each entry shows the reason for handoff when available
- AND detailed payloads, long logs, runner output, and raw source records are available one interaction deeper instead of dominating the row.

#### Scenario: Duplicate same-agent exchanges are preserved

- GIVEN a round contains multiple handoffs or back-and-forth exchanges involving the same agent or the same pair of agents
- AND those exchanges have distinct source ids, event ids, message ids, notification ids, timestamps, or sequence positions
- WHEN the timeline renders
- THEN each distinct exchange remains visible as its own timeline entry
- AND the app does not collapse entries solely because agent, handoff target, action text, or status match
- AND exact replay duplicates with the same stable source identity may be suppressed without hiding distinct exchanges.

#### Scenario: Timeline fields are normalized compatibly

- GIVEN source data exposes structured action, handoff, reason, role, destination, reviewer, coordinator, outcome, blocker, or summary fields
- WHEN timeline entries are normalized for display or JSON detail endpoints
- THEN structured fields are preferred for `action`, `handoff`, and `reason_for_handoff`
- AND message text, notification text, task summaries, or agent names are used only as fallback sources
- AND newly added normalized fields are backward-compatible additions to existing browser-facing JSON contracts.

## ADDED Requirements

### Requirement: Modern NiceGUI Information Layout

The system SHALL render the operator overview and selected-round detail using current NiceGUI component patterns with responsive layouts that avoid desktop and mobile overspill.

#### Scenario: Desktop layout supports dense scanning without overflow

- GIVEN a desktop browser viewport and representative long round ids, agent names, handoff targets, branch refs, validation summaries, source errors, and reason text
- WHEN the operator opens overview or selected-round detail
- THEN NiceGUI components use available width for dense scanning
- AND timeline or activity rows do not overlap adjacent controls
- AND the page does not produce body-level horizontal overflow
- AND long code-like values are constrained inside their own stable containers.

#### Scenario: Mobile layout preserves primary information

- GIVEN a narrow mobile browser viewport and representative long content
- WHEN the operator opens overview or selected-round detail
- THEN navigation, readiness, selected round context, activity rows, and timeline rows stack or wrap predictably
- AND action, handoff, reason for handoff, timestamp or sequence, and status remain visible
- AND secondary diagnostics may collapse into tabs, expansions, drawers, or dialogs
- AND controls remain selectable without overlapping text or each other.

#### Scenario: Current NiceGUI elements replace legacy information blocks

- GIVEN the overview, round detail, timeline, or diagnostic content is rendered
- WHEN implementation chooses UI primitives
- THEN it uses first-class NiceGUI components such as tables, structured row lists, tabs, tab panels, expansions, chips or badges, tooltips, drawers, dialogs, or splitters where practical
- AND custom HTML or CSS is limited to behavior that NiceGUI components do not cover, such as responsive constraints, text wrapping, focus treatment, and semantic status polish
- AND the UI does not reintroduce decorative dashboard framing, card nesting, or legacy unstructured information dumps.
