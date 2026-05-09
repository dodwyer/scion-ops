# Implementation Brief: update-web-app

Session: 20260509t213633z-native3
Base branch: round-20260509t185251z-1cfe-spec-integration
Final integration branch: round-20260509t213633z-native3-integration

## Task Groups

### A. Web App MCP Contract And UI

Owner branch: round-20260509t213633z-native3-impl-codex

Owned paths:
- scripts/web_app_hub.py
- scripts/test-web-app-hub.py
- openspec/changes/update-web-app/tasks.md

Scope:
- Document and enforce the browser-facing JSON contract in code/tests for current MCP structured round, event, artifact, OpenSpec validation, blocker, warning, and final-review fields.
- Update the backend adapter to prefer structured MCP/Hub fields and mark fallback-derived data without allowing text fallbacks to override structured values.
- Update the embedded read-only UI for overview, rounds, round detail, inbox, and runtime rendering of spec-round progress, expected/pr-ready branches, remote branch evidence, validation, blockers, warnings, and final-review semantics.
- Add/refresh fixture tests for current `scion_ops_run_spec_round`, `scion_ops_round_artifacts`, `scion_ops_spec_status`, `scion_ops_validate_spec_change`, event cursor, and blocked final-review payloads.

Out of scope:
- Kubernetes manifests, Taskfile kind lifecycle tasks, smoke script changes, and docs.
- MCP server API changes or new write operations.

Expected task checkboxes:
- 1.1, 1.2, 1.3, 1.4, and relevant verification checkbox 3.2 after local tests.

Verification commands:
- `python3 -m py_compile scripts/web_app_hub.py scripts/test-web-app-hub.py`
- `uv run scripts/test-web-app-hub.py`

### B. Kind Install, Lifecycle Tasks, Smoke, And Docs

Owner branch: round-20260509t213633z-native3-impl-claude

Owned paths:
- deploy/kind/control-plane/**
- Taskfile.yml
- scripts/kind-control-plane-smoke.py
- docs/kind-control-plane.md
- README.md
- openspec/changes/update-web-app/tasks.md

Scope:
- Add web app Deployment, Service, and any required read-only ServiceAccount/RBAC/config under `deploy/kind/control-plane`.
- Wire in-cluster Hub/MCP endpoints, grove id discovery, workspace mount, dev auth Secret, optional GitHub token, explicit command, ports, probes, labels, and service exposure.
- Include the web app in control-plane apply/restart/status/log workflows and add narrow web app update/status/log/smoke tasks.
- Extend no-spend control-plane smoke coverage to verify the web app HTTP endpoint/readiness without starting model-backed rounds.
- Document the kind web app URL, install behavior, and troubleshooting commands.

Out of scope:
- Python web app adapter/UI behavior and web app fixture tests, except smoke script endpoint checks.
- MCP server API changes or new write operations.

Expected task checkboxes:
- 2.1, 2.2, 2.3, 2.4, and relevant verification checkboxes 3.2/3.3 after local checks.

Verification commands:
- `python3 -m py_compile scripts/kind-control-plane-smoke.py`
- `kubectl kustomize deploy/kind/control-plane`
- `task --list`
- `bash -n scripts/kind-bootstrap.sh scripts/kind-scion-runtime.sh scripts/build-images.sh`

### C. Steward Integration And Final Verification

Owner branch: round-20260509t213633z-native3-integration

Owned paths:
- integration commits only from accepted implementer branches
- .scion-ops/sessions/20260509t213633z-native3/**
- openspec/changes/update-web-app/tasks.md final verification checkboxes only

Scope:
- Merge or cherry-pick accepted implementer branch changes into the final integration branch.
- Resolve task checkbox conflicts without dropping completed work.
- Run OpenSpec validation and repo-level verification.
- Render kind kustomization and confirm web app Deployment and Service are included.
- Start final-review agent and require an accepting verdict JSON before marking ready.

Verification commands:
- `python3 scripts/validate-openspec-change.py update-web-app`
- `task verify`
- `kubectl kustomize deploy/kind/control-plane`
- focused smoke command as provided by implementer branch B

## Coordination Rules

- Product implementation happens only on implementer branches.
- Each child branch must be pre-created from `round-20260509t185251z-1cfe-spec-integration` and verified at the base SHA before `scion start`.
- If an implementer fails to start or exits without branch movement, record the blocker in `state.json`; replacement prompts must be narrower.
- Keep the web app read-only. Do not add start, abort, retry, archive, or other mutating browser operations.
