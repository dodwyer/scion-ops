# Tasks

- [ ] 1.1 Add final-review failure classification support for `implementation_defect`, `integration_defect`, `verification_contract`, `environment_failure`, and `transient_agent_failure`.
- [ ] 1.2 Add a separate `max_final_repair_rounds` policy and state counter for remediation cycles after integration reaches final review.
- [ ] 1.3 Require integrators to provide canonical verification commands, observed results, branch identifiers, and caveats before final review begins.
- [ ] 1.4 Route `implementation_defect` failures to focused implementation repair followed by peer review before reintegration.
- [ ] 1.5 Route `integration_defect` failures to integrator repair, refreshed verification handoff, and final-review retry.
- [ ] 1.6 Route `verification_contract` failures to process or command correction without invalidating otherwise accepted integration branches.
- [ ] 1.7 Route `environment_failure` and `transient_agent_failure` failures through retry and escalation behavior with preserved evidence.
- [ ] 1.8 Add tests or fixtures for the final-review routing matrix, budget exhaustion, verification handoff enforcement, and branch-preservation behavior.
- [ ] 1.9 Validate the change with the repository's OpenSpec validation workflow.
