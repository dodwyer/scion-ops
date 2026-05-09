# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Round Progress Visibility

The system SHALL provide a web view of active and recent Scion agent rounds using Hub-backed agent, message, notification, lifecycle, provenance, verification, and outcome state.

#### Scenario: Active round shows lifecycle phase

- GIVEN a Scion round has active Hub or normalized round state
- AND the backing state exposes a lifecycle phase such as spec authoring, implementation, peer review, integration, final review, repair, archived, or blocked
- WHEN an operator opens the rounds view
- THEN the app lists the round by round id
- AND shows the current lifecycle phase
- AND shows the current owner or next responsible role when available
- AND shows the latest available update time or message summary.

#### Scenario: Blocked round shows actionable blocker

- GIVEN a round is waiting, blocked, degraded, or unable to proceed
- AND the backing state exposes a blocker, degraded dependency, final-review classification, verification failure, or escalation reason
- WHEN an operator opens the rounds view
- THEN the app distinguishes the blocked or degraded state from ordinary running and completed states
- AND shows the source-specific reason when available
- AND preserves available branch, commit, verification, and outcome details.

#### Scenario: Round list can be filtered and sorted

- GIVEN active and recent rounds have lifecycle, status, verdict, owner, update time, or degraded-source metadata
- WHEN an operator filters or sorts the rounds view
- THEN the app updates the visible list without mutating backing state
- AND the selected filters, sort order, and selected round id are represented in the URL
- AND reloading or sharing that URL restores the same read-only selection when the same backing data is available.

### Requirement: Round Detail Timeline

The system SHALL provide a round detail view that combines messages, notifications, agent status, runner output, lifecycle state, provenance, verification handoff, final-review repair state, source diagnostics, and final outcome for a selected round.

#### Scenario: Operator inspects lifecycle and provenance

- GIVEN a round exists in Hub-backed or normalized state
- WHEN an operator opens that round detail view
- THEN the app shows the lifecycle phase, status, current owner, blockers, and latest update when available
- AND shows branch and commit identifiers grouped by role when available
- AND uses structured backing fields before any fallback-derived text values
- AND labels unknown values as unknown instead of inferring them from unrelated text.

#### Scenario: Operator inspects verification handoff

- GIVEN integration or final-review handoff state exposes canonical verification commands, observed results, skipped checks, caveats, timestamps, or environment assumptions
- WHEN an operator opens the round detail view
- THEN the app shows that verification handoff data in a dedicated detail area
- AND distinguishes failed commands, skipped checks, missing handoff data, and unavailable verification dependencies when those categories are available.

#### Scenario: Operator inspects final-review repair state

- GIVEN final-review or repair-loop state exposes a failure classification, repair route, final repair budget usage, route history, current disposition, or escalation reason
- WHEN an operator opens the round detail view
- THEN the app shows the final-review repair state in operator-readable form
- AND a changes-requested, blocked, verification-contract, environment, or transient-agent result is not displayed as a generic completed state
- AND the app preserves classification evidence and relevant branch or handoff identifiers when available.

### Requirement: Source Of Truth Preservation

The system SHALL derive displayed operational state from existing scion-ops Hub, MCP, Kubernetes, git, verification, and normalized helper sources instead of maintaining an independent persistent copy of runtime state.

#### Scenario: Structured source data takes precedence

- GIVEN structured fields expose lifecycle phase, owner, blocker, branch, commit, verification, final-review verdict, repair classification, or source error data
- WHEN the app renders a list, detail, inbox, or runtime view
- THEN those structured fields are authoritative
- AND message text, notification text, task summaries, agent names, slugs, or runner output are used only as fallback sources when no structured field exists
- AND fallback-derived data does not replace structured values.

#### Scenario: Partial source failure is visible

- GIVEN one or more backing sources fail while other sources respond successfully
- WHEN the app renders overview, rounds, round detail, inbox, or runtime views
- THEN the app shows source-specific errors for each unavailable dependency
- AND continues showing data from sources that responded successfully
- AND shows last successful source timestamps or stale-state markers when available.

### Requirement: Read Only Initial Interface

The system SHALL keep the web app hub read-only and SHALL NOT expose round-starting, aborting, retrying, repairing, approving, archiving, or other state-changing operations.

#### Scenario: Operator changes web app view state

- GIVEN an operator opens the web app hub
- WHEN the operator refreshes data, changes filters, changes sorting, opens a round detail view, copies identifiers, or follows a read-only local link
- THEN the app does not start, abort, retry, repair, approve, archive, delete, or mutate rounds
- AND it does not write Hub records
- AND it does not modify Kubernetes resources
- AND it does not change git branches, commits, remotes, or working tree state.

#### Scenario: Mutation affordances are absent

- GIVEN the app displays blocked, failed, changes-requested, or repairable round states
- WHEN an operator views list, detail, inbox, overview, or runtime pages
- THEN the app does not present controls that imply the browser can perform repair, retry, approval, archive, abort, or state-changing actions
- AND any next-action text identifies the responsible owner or workflow outside the web app.
