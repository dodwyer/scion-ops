# Implementation Brief: update-web-app

Session: `20260509t231048z-native5`
Base branch: `round-20260509t185251z-1cfe-spec-integration`
Integration branch: `round-20260509t231048z-native5-integration`

## Task Groups

### A. MCP-aligned read-only web app

Owner branch: `round-20260509t231048z-native5-impl-codex`

Owned paths:

- `scripts/web_app_hub.py`
- `scripts/test-web-app-hub.py`
- web-app fixture files if added under `scripts/` or `tests/`
- `openspec/changes/update-web-app/tasks.md` checkboxes for completed group-A tasks only

Scope:

- Document the browser-facing JSON contract in code/tests for round, event, artifact, validation, blocker, warning, and final-review fields.
- Update the backend adapter to prefer current MCP/Hub structured fields from round status, round events/watch events, artifacts, spec status, validation, and spec-round progress payloads.
- Preserve fallback parsing only for missing structured fields and mark fallback-derived values so they cannot override structured MCP/Hub fields.
- Update rendered read-only views for overview, rounds, round detail, inbox, and runtime to expose status, terminal status, blockers, warnings, validation status, final review verdicts, expected branch, PR-ready branch, remote branch SHA, event cursors, and degraded MCP errors.
- Add representative no-spend fixture coverage for `scion_ops_run_spec_round`, `scion_ops_round_artifacts`, `scion_ops_spec_status`, validation payloads, and blocked/changes-requested final-review payloads.

Out of scope:

- Kubernetes/kustomize manifests, Taskfile lifecycle tasks, kind smoke scripts, operator docs, images, and deployment wiring.
- Product write operations or new MCP tool names.

Verification commands:

- `python3 -m py_compile scripts/web_app_hub.py`
- `uv run scripts/test-web-app-hub.py`
- `task spec:validate -- update-web-app`

### B. Kind/kustomize install, lifecycle, smoke, and docs

Owner branch: `round-20260509t231048z-native5-impl-claude`

Owned paths:

- `deploy/kind/control-plane/**`
- `Taskfile.yml`
- `scripts/kind-control-plane-smoke.py`
- `docs/kind-control-plane.md`
- `README.md` if needed for operator URL references
- `openspec/changes/update-web-app/tasks.md` checkboxes for completed group-B tasks only

Scope:

- Add the web app Deployment, Service, and any required read-only RBAC/config/env/secret/workspace mounts to `deploy/kind/control-plane`.
- Wire the deployed app to the in-cluster Hub endpoint, MCP URL/path, grove id conventions, mounted scion-ops checkout, dev auth secret, and optional GitHub token convention where applicable.
- Include the web app in full control-plane apply/restart/status/log workflows and add narrow web-app status/log/update/smoke tasks.
- Extend no-spend smoke coverage to verify the web app endpoint and readiness/snapshot response without starting model-backed rounds or mutating Hub runtime state.
- Update operator docs with the stable web app URL, kind install behavior, and troubleshooting commands.
- Verify rendered kustomize output includes the web app Deployment and Service.

Out of scope:

- Web app backend contract/UI behavior and web app fixture tests except for endpoint expectations needed by smoke coverage.
- MCP server API changes or new model-backed round behavior.

Verification commands:

- `python3 -m py_compile scripts/kind-control-plane-smoke.py`
- `bash -n deploy/kind/control-plane/config/broker-entrypoint.sh`
- `kubectl kustomize deploy/kind/control-plane`
- `task --list`
- `task spec:validate -- update-web-app`

## Integration Verification

Run on `round-20260509t231048z-native5-integration` after merging accepted implementer branches:

- `git diff --check`
- `task spec:validate -- update-web-app`
- `task verify`
- `kubectl kustomize deploy/kind/control-plane`
- inspect rendered output for `Deployment/scion-web-app` or the chosen stable web app deployment name and its matching `Service`
- no-spend smoke command for the deployed web app endpoint, either via `task kind:web-app:smoke` or the extended `task kind:control-plane:smoke -- --skip-round`

## Coordination Notes

- Product implementation must occur on implementer branches, not on the steward branch.
- Implementers may update only the checkboxes they complete in `openspec/changes/update-web-app/tasks.md`.
- The final review branch must be created from the pushed integration commit, not from the accepted spec base.
