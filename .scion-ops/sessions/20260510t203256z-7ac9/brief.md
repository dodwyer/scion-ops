# Implementation Brief: use-nicegui

## Goal

Implement the approved `use-nicegui` OpenSpec change by replacing the read-only
browser UI with a NiceGUI operator console while preserving existing JSON,
health, round detail, live update, kind deployment, and smoke-test contracts.

## Task Groups

### Group A: NiceGUI application and contract tests

- Branch: `round-20260510t203256z-7ac9-impl-codex`
- Owned paths:
  - `scripts/web_app_hub.py`
  - `scripts/test-web-app-hub.py`
  - any new Python helper module under `scripts/` that is imported by
    `scripts/web_app_hub.py`
  - `openspec/changes/use-nicegui/tasks.md` task checkboxes for completed Group A work only
- Scope:
  - Add NiceGUI runtime dependency metadata and an app entry path that can run
    locally and in the existing web app process.
  - Keep browser-facing adapter functions independently testable.
  - Build NiceGUI overview, rounds, round detail, inbox, runtime, and
    troubleshooting views using existing structured snapshot/detail/update
    sources.
  - Preserve read-only behavior and existing `/healthz`, snapshot, round detail,
    round event, and live update JSON contracts.
  - Add focused no-spend tests for NiceGUI route rendering, contract
    compatibility, degraded source handling, responsive/layout markers, and
    Laws of UX constraints where practical in Python tests.
- Out of scope:
  - `deploy/**`
  - `docs/**`
  - image build files
  - kind lifecycle scripts

### Group B: kind deployment, docs, and smoke coverage

- Branch: `round-20260510t203256z-7ac9-impl-claude`
- Owned paths:
  - `deploy/kind/control-plane/web-app-deployment.yaml`
  - `deploy/kind/control-plane/web-app-service.yaml`
  - `deploy/kind/control-plane/kustomization.yaml`
  - `docs/kind-control-plane.md`
  - `scripts/kind-control-plane-smoke.py`
  - deployment/smoke-focused tests if needed
  - `openspec/changes/use-nicegui/tasks.md` task checkboxes for completed Group B work only
- Scope:
  - Ensure the kind web app deployment starts the NiceGUI application with the
    existing service identity, ports, probes, workspace mount, auth Secret,
    Hub/MCP environment, grove id conventions, and read-only ServiceAccount/RBAC.
  - Ensure smoke checks continue to use health or JSON snapshot endpoints without
    starting model-backed work.
  - Update documentation for the NiceGUI web app local/kind workflow.
- Out of scope:
  - `scripts/web_app_hub.py`
  - UI component implementation
  - adapter contract rewrites

## Verification Commands

- Group A:
  - `python3 scripts/validate-openspec-change.py --change use-nicegui --project-root .`
  - `uv run scripts/test-web-app-hub.py`
  - targeted startup check, for example `timeout 15s uv run scripts/web_app_hub.py` with probe requests if the branch adds a local smoke helper
- Group B:
  - `python3 scripts/validate-openspec-change.py --change use-nicegui --project-root .`
  - `python3 scripts/kind-control-plane-smoke.py --help`
  - `kubectl kustomize deploy/kind/control-plane`
- Integration:
  - `python3 scripts/validate-openspec-change.py --change use-nicegui --project-root .`
  - `uv run scripts/test-web-app-hub.py`
  - `python3 scripts/kind-control-plane-smoke.py --help`
  - `kubectl kustomize deploy/kind/control-plane`

## Steward Notes

- Product implementation edits must be made only on implementer branches.
- The steward branch owns durable session state, branch-guard outputs, wait
  diagnostics, integration records, final-review records, and PR finalization
  records.
- Integration must accept only implementer branches with valid handoff JSON and
  non-empty branch movement from `main`.
