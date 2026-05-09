# Proposal: Add Final Review Repair Loop

## Summary

Add a post-integration final-review remediation loop for scion-ops consensus rounds. The loop will classify final-review failures, apply a dedicated repair budget, preserve canonical verification evidence across integrator and final-review handoff, and route each failure class to the least disruptive remediation path.

## Motivation

Consensus rounds can produce integration branches that pass peer review and integration but still fail final review. Today that late failure path is underspecified: implementation issues, integrator mistakes, verification-command drift, environment outages, and transient agent failures can all look like a generic final-review failure. That ambiguity makes it too easy to invalidate otherwise acceptable work, rerun the wrong agents, or lose the verification evidence needed to repair the round quickly.

A dedicated final-review remediation loop gives coordinators and agents a consistent contract for deciding what failed, who repairs it, how many final repair attempts are allowed, and when to retry or escalate.

## Scope

In scope:

- A final-review failure taxonomy with `implementation_defect`, `integration_defect`, `verification_contract`, `environment_failure`, and `transient_agent_failure`.
- A separate `max_final_repair_rounds` budget that applies only after integration reaches final review.
- A required integrator handoff containing canonical verification commands, results, relevant branch identifiers, and known verification caveats.
- Routing rules for implementation defects through focused repair and peer review before reintegration.
- Routing rules for integration defects through integrator repair before final review is retried.
- Routing rules for verification-contract failures through process or command correction without invalidating otherwise accepted integration branches.
- Retry and escalation handling for environment and transient agent failures.
- Validation expectations and test coverage for the new routing behavior.

Out of scope for this change:

- Implementing the orchestration code, tests, Kubernetes manifests, runtime scripts, or product documentation.
- Changing the existing integration acceptance criteria except where final-review routing needs the canonical verification handoff.
- Defining UI behavior for monitoring the loop.

## Success Criteria

- Final reviewers can classify every final-review failure into one of the required categories.
- Coordinators can determine whether to route repair to implementers, integrators, process/verification owners, retry logic, or escalation.
- Accepted integration branches are not invalidated solely because the verification contract needs correction.
- Final-review remediation uses a budget independent from earlier implementation or integration repair budgets.
- Later implementation can verify the routing matrix with focused automated tests and representative round-state fixtures.

## Unresolved Questions

- The exact default value for `max_final_repair_rounds` should be selected during implementation or configuration design.
- The durable storage location for handoff evidence should follow the existing round-state persistence model selected by the implementation.
