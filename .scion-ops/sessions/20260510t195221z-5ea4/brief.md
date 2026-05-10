# Implementation Brief: use-nicegui

## Approved Artifacts

- `openspec/changes/use-nicegui/proposal.md`
- `openspec/changes/use-nicegui/design.md`
- `openspec/changes/use-nicegui/tasks.md`
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md`

## Task Groups

### Group A: NiceGUI application and browser contracts

- Branch: `round-20260510t195221z-5ea4-impl-codex`
- Owned paths:
  - `scripts/web_app_hub.py`
  - `scripts/test-web-app-hub.py`
  - `openspec/changes/use-nicegui/tasks.md`
- Tasks:
  - Inventory and preserve public HTTP, JSON, health, round detail, round events, and live update contracts.
  - Add NiceGUI runtime dependency metadata and a Python-native app entry point in the existing web app process.
  - Keep browser-facing data adapters independently testable from NiceGUI widget rendering.
  - Build read-only NiceGUI overview, rounds, round detail, inbox, runtime, and troubleshooting views.
  - Preserve read-only behavior and backward-compatible JSON endpoint semantics.
  - Add focused no-spend tests for rendering, contract compatibility, degraded sources, progressive troubleshooting, and Laws of UX constraints.
- Out of scope:
  - `deploy/kind/**`
  - `docs/**`
  - `Taskfile.yml`
  - Kubernetes smoke script changes except for facts needed in existing adapter tests.

### Group B: kind deployment, lifecycle, docs, and smoke wiring

- Branch: `round-20260510t195221z-5ea4-impl-claude`
- Owned paths:
  - `deploy/kind/control-plane/**`
  - `deploy/kind/smoke/**`
  - `scripts/kind-control-plane-smoke.py`
  - `scripts/kind-scion-runtime.sh`
  - `Taskfile.yml`
  - `docs/kind-control-plane.md`
  - `openspec/changes/use-nicegui/tasks.md`
- Tasks:
  - Update web app Deployment startup, probes, service expectations, and runtime environment for the NiceGUI app while preserving the existing service identity and port compatibility.
  - Preserve workspace, Hub dev-auth Secret, GitHub token, in-cluster Hub/MCP URL, grove id, ServiceAccount, and read-only RBAC conventions.
  - Update lifecycle task and kind smoke coverage for NiceGUI health/snapshot readiness without starting model-backed work.
  - Update documentation for local/kind NiceGUI operation and troubleshooting.
- Out of scope:
  - NiceGUI UI component implementation details in `scripts/web_app_hub.py` beyond command/path assumptions required for deployment.
  - Browser JSON contract changes and adapter normalization logic.

## Integration Plan

1. Start both implementer agents from `main` after pre-creating and verifying their remote child branches.
2. Accept non-empty implementation branches that commit and push their assigned slices.
3. Merge both branches into `round-20260510t195221z-5ea4-integration`, resolving conflicts without reverting implementer work.
4. Run verification locally on the integration branch.
5. Start final review from the pushed integration commit.
6. If final review accepts, record ready state and create or return the GitHub PR for the integration branch.

## Verification Commands

- `python3 scripts/validate-openspec-change.py openspec/changes/use-nicegui`
- `uv run pytest scripts/test-web-app-hub.py`
- `uv run scripts/web_app_hub.py --host 127.0.0.1 --port 8787` with no-spend HTTP checks:
  - `GET /healthz`
  - `GET /api/snapshot`
  - representative rendered NiceGUI route
- `kubectl kustomize deploy/kind/control-plane`
- `python3 scripts/kind-control-plane-smoke.py --skip-setup --skip-agent --web-app-url "$SCION_OPS_WEB_APP_URL"` when a kind control plane is available.
