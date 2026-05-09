# Delta: Scion Consensus Rounds

## ADDED Requirements

### Requirement: Final Review Failure Classification

The system SHALL require failed post-integration final reviews to be classified as exactly one of `implementation_defect`, `integration_defect`, `verification_contract`, `environment_failure`, or `transient_agent_failure` before automated remediation is routed.

#### Scenario: Implementation defect is classified

- GIVEN a final reviewer finds a missing requirement, code bug, regression, or failed accepted test traceable to an implementation branch
- WHEN the final-review result is recorded
- THEN the failure is classified as `implementation_defect`
- AND the result includes evidence that identifies the affected implementation surface or branch when known.

#### Scenario: Integration defect is classified

- GIVEN a final reviewer finds a merge, conflict-resolution, branch selection, dependency-ordering, or integration assembly error introduced during integration
- WHEN the final-review result is recorded
- THEN the failure is classified as `integration_defect`
- AND the result includes evidence that identifies the integration branch and the observed assembly failure.

#### Scenario: Verification contract failure is classified

- GIVEN final review cannot determine pass/fail because canonical commands, arguments, fixtures, acceptance criteria, or result interpretation are missing, stale, ambiguous, or inconsistent
- WHEN the final-review result is recorded
- THEN the failure is classified as `verification_contract`
- AND the result identifies the command or process contract that must be corrected.

#### Scenario: Environment failure is classified

- GIVEN final review is blocked or fails because of unavailable infrastructure, credentials, services, dependencies, filesystem state, network access, or runtime capacity outside the submitted branches
- WHEN the final-review result is recorded
- THEN the failure is classified as `environment_failure`
- AND the result identifies the failed environment dependency when available.

#### Scenario: Transient agent failure is classified

- GIVEN final review is interrupted by an agent timeout, transport failure, malformed transient response, or non-deterministic agent execution failure that does not yet indicate a branch defect
- WHEN the final-review result is recorded
- THEN the failure is classified as `transient_agent_failure`
- AND the result preserves the transient failure evidence for retry or escalation.

### Requirement: Final Repair Budget

The system SHALL track a `max_final_repair_rounds` budget separately from implementation, peer-review, and integration repair budgets.

#### Scenario: Final repair budget is consumed

- GIVEN an integration branch has entered final review
- AND a final-review failure is classified for remediation
- WHEN the coordinator starts a final-review repair cycle
- THEN the cycle counts against `max_final_repair_rounds`
- AND it does not consume implementation, peer-review, or integration repair budgets unless those phases are explicitly re-entered by the selected route.

#### Scenario: Final repair budget is exhausted

- GIVEN the number of final-review repair cycles has reached `max_final_repair_rounds`
- WHEN another classified final-review failure requires remediation
- THEN the system stops automatic final-review repair routing
- AND escalates with the latest classification, evidence, verification handoff, branch identifiers, and route history.

### Requirement: Final Review Verification Handoff

The system SHALL require integrators to provide canonical verification commands and observed results before final review starts.

#### Scenario: Integrator provides canonical handoff

- GIVEN an integrator completes an integration branch for final review
- WHEN the integration handoff is recorded
- THEN it includes the integration branch identifier
- AND it includes the commit identifier under review when available
- AND it includes canonical verification commands
- AND it includes the integrator's observed verification results
- AND it includes known caveats, skipped checks, unavailable dependencies, or environment assumptions.

#### Scenario: Handoff is missing

- GIVEN an integration branch is ready for final review
- AND the canonical verification handoff is missing required commands or results
- WHEN final review would otherwise start
- THEN the system blocks final review routing
- AND requests integrator handoff correction without classifying the branch as an implementation or integration defect.

### Requirement: Final Review Remediation Routing

The system SHALL route classified final-review failures to the remediation path associated with their failure category.

#### Scenario: Implementation defect routes to focused repair

- GIVEN a final-review failure is classified as `implementation_defect`
- WHEN the coordinator routes remediation
- THEN the affected implementation scope is assigned for focused repair
- AND the repaired implementation must pass peer review before reintegration
- AND final review is retried only after reintegration produces a refreshed handoff.

#### Scenario: Integration defect routes to integrator repair

- GIVEN a final-review failure is classified as `integration_defect`
- WHEN the coordinator routes remediation
- THEN the integrator repairs the integration branch or creates a replacement integration branch
- AND the integrator refreshes canonical verification commands and observed results
- AND final review is retried against the repaired integration output.

#### Scenario: Verification contract routes to process correction

- GIVEN a final-review failure is classified as `verification_contract`
- WHEN the coordinator routes remediation
- THEN the verification command set, acceptance contract, fixture documentation, or result interpretation is corrected
- AND an otherwise accepted integration branch remains accepted during the correction
- AND the branch is invalidated only if the corrected verification contract exposes a separate `implementation_defect` or `integration_defect`.

#### Scenario: Environment failure routes to retry or escalation

- GIVEN a final-review failure is classified as `environment_failure`
- WHEN the coordinator routes remediation
- THEN final review is retried after the failed environment dependency is restored when recovery is possible within policy
- AND the issue is escalated when recovery is not possible within policy
- AND the submitted branches are not marked defective solely because of the environment failure.

#### Scenario: Transient agent failure routes to retry or escalation

- GIVEN a final-review failure is classified as `transient_agent_failure`
- WHEN the coordinator routes remediation
- THEN final review or the failed agent action is retried within the final-repair budget
- AND the issue is escalated when retries are exhausted
- AND repeated transient failures may be reclassified only when new evidence supports a different category.

### Requirement: Final Review Routing Validation

The system SHALL include validation coverage for the final-review remediation routing behavior when this change is implemented.

#### Scenario: Routing matrix is tested

- GIVEN representative final-review failures for each supported classification
- WHEN the routing tests execute
- THEN each classification routes to the expected next owner and phase
- AND each route preserves the classification evidence and relevant verification handoff data.

#### Scenario: Branch preservation is tested

- GIVEN a final-review failure classified as `verification_contract`, `environment_failure`, or `transient_agent_failure`
- WHEN the remediation route is selected
- THEN tests verify that otherwise accepted integration branches are not invalidated solely by that classification.

#### Scenario: Budget behavior is tested

- GIVEN final-review remediation cycles and earlier implementation or integration repair cycles exist in the same round
- WHEN budget accounting is evaluated
- THEN tests verify that `max_final_repair_rounds` is tracked independently from earlier repair budgets.
