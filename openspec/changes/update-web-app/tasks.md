# Tasks

- [ ] 1.1 Review the current scion-ops MCP tool outputs used by the web app and document the browser-facing JSON contract for round, event, artifact, validation, and final-review fields.
- [x] 1.2 Update the web app backend adapter to consume current MCP/Hub structured fields for round status, event cursors, branch artifacts, OpenSpec validation, blockers, warnings, and final-review verdicts.
- [x] 1.3 Update rounds, round detail, overview, inbox, and runtime views so MCP-aligned fields are visible without collapsing blocked or changes-requested outcomes into generic completed state.
- [x] 1.4 Add or update fixtures for current MCP result shapes, including `scion_ops_run_spec_round`, `scion_ops_round_artifacts`, `scion_ops_spec_status`, and blocked final-review payloads.
- [ ] 2.1 Add web app Kubernetes resources under the kind control-plane kustomization with stable labels, probes, environment, secrets, workspace mounts, and service exposure.
- [ ] 2.2 Include the web app in kind lifecycle tasks for image build/load as needed, control-plane apply, restart/status/logs, and narrow update workflows.
- [ ] 2.3 Extend no-spend control-plane smoke or add a focused smoke check that verifies the deployed web app endpoint and readiness without starting model-backed rounds.
- [ ] 2.4 Update operator documentation for the web app URL, kind install behavior, and troubleshooting commands.
- [x] 3.1 Run OpenSpec validation for this change.
- [x] 3.2 Run repo static checks and web app fixture tests after implementation.
- [ ] 3.3 Render or apply the kind kustomization to verify the web app Deployment and Service are included.
