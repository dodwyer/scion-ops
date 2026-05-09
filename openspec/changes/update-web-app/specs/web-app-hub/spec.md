# Delta: Web App Hub OpenSpec Change Visibility

## ADDED Requirements

### Requirement: OpenSpec Changes View

The system SHALL provide a web view that lists active OpenSpec changes for the active project and SHALL distinguish active changes from archived changes.

#### Scenario: Active changes are listed

- GIVEN the active project's `openspec/changes/` directory contains one or more change directories
- AND none of those changes are under the `archive/` subdirectory
- WHEN an operator opens the OpenSpec view
- THEN the app lists each active change by its directory name
- AND the app indicates whether `proposal.md`, `design.md`, and `tasks.md` are present for that change
- AND the app indicates how many `specs/**/spec.md` files are present for that change.

#### Scenario: Archived changes are listed separately

- GIVEN the active project's `openspec/changes/archive/` directory contains one or more archived change directories
- WHEN an operator opens the OpenSpec view
- THEN the app shows those archived changes in a section that is visually distinct from the active list
- AND the active list does not include any archived change.

#### Scenario: No changes are present

- GIVEN the active project has no `openspec/changes/` directory or has an empty one
- WHEN an operator opens the OpenSpec view
- THEN the app shows an empty state that identifies the project has no OpenSpec changes
- AND the empty state is distinct from a data-source failure state.

#### Scenario: OpenSpec source is unavailable

- GIVEN the OpenSpec data source cannot be read because of a runtime or local-git-state failure
- WHEN an operator opens the OpenSpec view
- THEN the app shows a source-specific error that names the failed source
- AND the app does not show a misleading empty state in place of the error.

### Requirement: OpenSpec Change Detail And Validator Outcome

The system SHALL provide a detail panel for a selected OpenSpec change that shows the validator outcome, the validator source identifier, and any reported errors or warnings.

#### Scenario: Validator reports success

- GIVEN an operator selects an OpenSpec change in the OpenSpec view
- AND the validator returns a successful result
- WHEN the detail panel renders
- THEN the panel shows the validator source identifier
- AND the panel indicates the change passed validation
- AND the panel does not show fabricated errors when none were reported.

#### Scenario: Validator reports errors

- GIVEN an operator selects an OpenSpec change in the OpenSpec view
- AND the validator returns one or more errors or warnings
- WHEN the detail panel renders
- THEN the panel lists each error and warning with its file path and message as reported by the validator
- AND the panel distinguishes errors from warnings
- AND the panel shows the validator source identifier so the operator can tell whether the result came from the OpenSpec CLI validator or the local fallback.

#### Scenario: Detail panel preserves read-only behavior

- GIVEN an operator opens or refreshes an OpenSpec change detail panel
- WHEN the panel loads its data
- THEN the request only invokes read-only OpenSpec helpers
- AND the request does not archive, mutate, or otherwise change any OpenSpec artifact.

### Requirement: Round Detail OpenSpec Reference

The system SHALL surface the OpenSpec change a round targets in the round detail view when a target change is identifiable from existing round backing state.

#### Scenario: Round metadata identifies a target change via a structured field

- GIVEN a round's Hub, MCP, or normalized backing state exposes a structured field that identifies its target OpenSpec change
- WHEN an operator opens that round detail view
- THEN the round detail view shows the OpenSpec change name
- AND the round detail view links the operator to the OpenSpec view for that change
- AND the round detail view does not derive a different change name from message text or task summaries when the structured field is present.

#### Scenario: Round metadata identifies a target change only via text

- GIVEN a round has no structured target-change field
- AND a round message, notification, or task summary mentions a recognizable change name that exists under `openspec/changes/`
- WHEN the round detail view renders
- THEN the round detail view may show the recognized change name as a fallback link
- AND the round detail view labels the link as derived from text rather than as authoritative metadata.

#### Scenario: Round has no identifiable change

- GIVEN a round has no structured target-change field
- AND no round message, notification, or task summary identifies a known OpenSpec change
- WHEN the round detail view renders
- THEN the round detail view does not show an OpenSpec change reference for that round
- AND the round detail view does not synthesize a fabricated change name.

### Requirement: OpenSpec View Source Of Truth

The system SHALL derive the OpenSpec view from the on-disk OpenSpec tree and the existing scion-ops validator helpers without maintaining a competing persistent copy of OpenSpec change state.

#### Scenario: View reflects the on-disk tree on each refresh

- GIVEN the operator triggers a refresh of the OpenSpec view
- WHEN the view loads
- THEN the displayed list is derived from the current contents of `openspec/changes/` for the active project
- AND any cache used during the request is short-lived and does not survive across refreshes as a competing source of truth.

#### Scenario: Validator output uses the existing helper

- GIVEN the OpenSpec view shows validator output for a selected change
- WHEN the validator output is loaded
- THEN it is produced by the existing scion-ops validator helper
- AND the OpenSpec view does not reimplement OpenSpec validation logic.

### Requirement: Read Only OpenSpec View

The system SHALL keep the OpenSpec view read-only and SHALL NOT expose change-creating, change-editing, change-archiving, or other state-changing OpenSpec operations.

#### Scenario: Operator uses the OpenSpec view

- GIVEN an operator opens or refreshes the OpenSpec view or a change detail panel
- WHEN the view loads or refreshes data
- THEN the app does not create, edit, archive, or delete any OpenSpec change
- AND the app does not modify Kubernetes resources or Hub runtime records
- AND the app does not invoke any scion-ops helper that performs state-changing operations.
