# Design: Add Final Review Repair Loop

## Overview

The final-review repair loop begins only after an integration branch has been produced and handed to final reviewers. It does not replace implementation repair, peer review, or integrator repair. Instead, it adds a late-stage classification and routing layer that decides whether a final-review failure requires focused implementation repair, integrator repair, verification-contract correction, retry, or escalation.

The loop should preserve the accepted work whenever possible. A final-review issue should invalidate an integration branch only when the classified defect shows that the branch content or integration itself is wrong.

## Failure Taxonomy

Final reviewers should classify failed final reviews into one of these categories:

- `implementation_defect`: a bug, missing requirement, incomplete test expectation, or regression traceable to an implementation branch that was integrated.
- `integration_defect`: a merge, conflict-resolution, branch selection, dependency ordering, or integration assembly issue introduced by the integrator.
- `verification_contract`: a mismatch between expected verification and the command contract, such as missing commands, wrong command arguments, stale acceptance criteria, unavailable test fixture documentation, or ambiguous pass/fail interpretation.
- `environment_failure`: an infrastructure, service, credential, filesystem, network, dependency availability, or runtime-capacity failure outside the submitted branches.
- `transient_agent_failure`: an agent timeout, interrupted run, transport failure, malformed transient response, or other non-deterministic agent execution failure that does not yet indicate a branch defect.

The implementation should require reviewers to include evidence for the selected category. If the evidence is insufficient, the round should be treated as needing classification clarification rather than routed to an arbitrary repair path.

## Verification Handoff

Before final review starts, the integrator must provide canonical verification evidence. The handoff should include:

- The integration branch and commit identifiers under review.
- The canonical verification commands the final reviewer should run or inspect.
- The results the integrator observed, including pass/fail status, relevant output summaries, and timestamps when available.
- Known caveats, skipped checks, unavailable dependencies, or environment assumptions.
- References to any implementation and peer-review repair branches that materially affected the final integration.

Final reviewers should use this handoff as the baseline for deciding whether the failure is in the code, the integration, the verification contract, or the execution environment.

## Routing Model

The routing behavior should be explicit:

- `implementation_defect` routes to a focused repair assignment for the responsible implementation surface. The repaired work must receive peer review before it returns to integration.
- `integration_defect` routes to the integrator for branch assembly repair. After integrator repair, the integrator must refresh the handoff and request final review again.
- `verification_contract` routes to correction of the verification process, command set, or acceptance contract. Otherwise accepted integration branches remain accepted unless the corrected contract exposes a separate implementation or integration defect.
- `environment_failure` routes to retry only after the environment is restored or to escalation when the environment cannot be restored within the round policy.
- `transient_agent_failure` routes to retry within the final-repair budget and escalates when retry attempts are exhausted or repeated failure suggests a different category.

## Repair Budget

`max_final_repair_rounds` should be tracked separately from implementation, peer-review, and integration repair budgets. It counts remediation cycles that occur after final review reports a classified failure. The budget should not be consumed by pure environment waits unless the implementation policy intentionally counts repeated retry attempts after recovery.

When the final-repair budget is exhausted, the coordinator should stop automatic remediation and surface the last classification, evidence, branch identifiers, verification handoff, and attempted route history for escalation.

## Validation Strategy

The eventual implementation should include focused tests or fixtures that cover:

- Each failure category routes to the expected owner and next phase.
- `max_final_repair_rounds` is independent from earlier repair budgets.
- Integrator handoff data is required before final review can start.
- Verification-contract corrections do not invalidate an otherwise accepted integration branch by themselves.
- Environment and transient failures retry or escalate without misclassifying branch content as defective.
- Repair history preserves classification evidence and canonical verification command/results.
