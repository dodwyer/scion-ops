# Implementation Brief: update-web-app

Session: 20260509t223549z-native4
Base branch: round-20260509t185251z-1cfe-spec-integration
Integration branch: round-20260509t223549z-native4-integration

## Task Groups

### Group A: Web app MCP contract, read-only adapter, UI, and fixtures

Owner branch: round-20260509t223549z-native4-impl-codex

Owned paths:
- scripts/web_app_hub.py
- scripts/test-web-app-hub.py
- openspec/changes/update-web-app/tasks.md
- Any narrowly scoped fixture files added under scripts/ or tests/ for web app contract coverage

Tasks:
- 1.1 Review current MCP tool outputs used by the web app and document the browser-facing JSON contract in code/tests or adjacent fixture comments.
- 1.2 Update the backend adapter to prefer current structured MCP/Hub fields for round status, event cursors, branch artifacts, OpenSpec validation, blockers, warnings, and final-review verdicts.
- 1.3 Update overview, rounds, round detail, inbox, and runtime rendering so blocked, changes-requested, validation-failed, expected-branch, PR-ready-branch, remote branch SHA, and web app readiness fields remain visible.
- 1.4 Add/update fixtures for `scion_ops_run_spec_round`, `scion_ops_round_artifacts`, `scion_ops_spec_status`, and blocked final-review payloads.
- Mark only completed 1.x task checkboxes.

Out of scope:
- Kubernetes manifests, Taskfile lifecycle commands, smoke scripts, and operator docs except as needed to avoid test breakage.
- Write operations or any new browser action that mutates Hub/MCP state.

Verification commands:
- `python scripts/test-web-app-hub.py`
- Any narrower test command added for web app MCP fixture coverage.

### Group B: Kind/kustomize install, lifecycle tasks, smoke, and docs

Owner branch: round-20260509t223549z-native4-impl-claude

Owned paths:
- deploy/kind/control-plane/**
- deploy/kind/kustomization.yaml
- Taskfile.yml
- scripts/kind-control-plane-smoke.py
- scripts/smoke-mcp-server.py if the no-spend smoke path must share endpoint checks
- docs/kind-control-plane.md
- README.md if it already documents local control-plane URLs
- openspec/changes/update-web-app/tasks.md

Tasks:
- 2.1 Add web app Deployment, Service, read-only service account/RBAC as needed, probes, environment, dev auth secret mount, optional GitHub token mount, workspace mount, labels, and service exposure to the control-plane kustomization.
- 2.2 Include the web app in kind lifecycle tasks for build/load as needed, apply, restart/status/logs, and narrow update workflows.
- 2.3 Extend no-spend smoke coverage so the deployed web app endpoint/readiness responds without starting model-backed rounds or mutating Hub runtime state.
- 2.4 Update operator docs for URL, install behavior, and troubleshooting.
- Mark only completed 2.x task checkboxes and any verification task this branch directly completes.

Out of scope:
- Web app MCP parsing/rendering behavior except for the minimum Kubernetes health shape needed by the app endpoint checks.
- Changes to accepted OpenSpec archives outside `openspec/changes/update-web-app`.

Verification commands:
- `kubectl kustomize deploy/kind/control-plane`
- `task --list` or equivalent Taskfile syntax/listing check
- Focused no-spend smoke command for the web app endpoint if available without a live kind cluster; otherwise document the exact live-cluster command run or blocked.

## Integration Verification

The steward will integrate both non-empty implementer branches into `round-20260509t223549z-native4-integration`, then run:
- `openspec validate update-web-app --strict`
- `python scripts/test-web-app-hub.py`
- `kubectl kustomize deploy/kind/control-plane`
- `python scripts/kind-control-plane-smoke.py --help` or the implemented no-spend dry/static mode
- Any repository static checks surfaced by the implementers

The final-review branch must be created from the pushed integration SHA. The final reviewer must write `.scion-ops/sessions/20260509t223549z-native4/reviews/final-review.json` and return an accepting verdict before the session is marked ready.
