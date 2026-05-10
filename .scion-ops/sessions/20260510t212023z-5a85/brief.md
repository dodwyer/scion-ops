# Implementation Brief: use-nicegui

Session: 20260510t212023z-5a85
Base branch: main
Integration branch: round-20260510t212023z-5a85-integration

## Task Groups

### Group A: NiceGUI application and browser contracts

Owner branch: round-20260510t212023z-5a85-impl-codex

Owned paths:

- scripts/web_app_hub.py
- scripts/test-web-app-hub.py
- openspec/changes/use-nicegui/tasks.md

Scope:

- Inventory and preserve the current health, snapshot, round detail, round events, and live update JSON contracts.
- Add a NiceGUI-based operator console in the web app process with overview, rounds, round detail, inbox, runtime, and troubleshooting views.
- Keep browser-visible JSON endpoints independently testable and backward-compatible.
- Consume `/api/live` from the rendered UI for visible in-place updates, reconnect or fallback polling state, and selected round/context preservation.
- Keep the UI read-only across load, refresh, live reconnect, fallback polling, and diagnostics.
- Add focused no-spend tests for rendering, JSON compatibility, degraded source behavior, and live update consumption/state preservation.

Out of scope:

- Kind manifests, image build files, deployment docs, and smoke scripts except where a test assertion must reference an unchanged contract.
- Any round-starting, retry, abort, delete, git-writing, OpenSpec-writing, or Kubernetes-mutating behavior.

Expected task checkboxes: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, application portions of 1.10 and 1.11.

Verification commands:

- python3 -m pytest scripts/test-web-app-hub.py
- python3 scripts/web_app_hub.py --host 127.0.0.1 --port 8765, then request `/healthz`, `/api/snapshot`, and a NiceGUI page route

### Group B: NiceGUI runtime dependency, kind deployment, and smoke coverage

Owner branch: round-20260510t212023z-5a85-impl-claude

Owned paths:

- image-build/scion-ops-mcp/Dockerfile
- image-build/task-runtime/Dockerfile
- scripts/build-images.sh
- deploy/kind/control-plane/web-app-deployment.yaml
- deploy/kind/control-plane/web-app-service.yaml
- deploy/kind/control-plane/kustomization.yaml
- scripts/kind-control-plane-smoke.py
- docs/kind-control-plane.md
- README.md
- openspec/changes/use-nicegui/tasks.md

Scope:

- Ensure the kind web-app deployment starts the NiceGUI application in an image/runtime path where the NiceGUI dependency is actually installed.
- Preserve the existing Deployment, Service, labels, probes, read-only ServiceAccount/RBAC, workspace mount, auth Secret convention, host-port workflow, and environment variable meanings.
- Add or update smoke/static checks proving rendered kind manifests and smoke paths reach health or JSON snapshot endpoints without model-backed work.
- Document local and kind execution prerequisites for the NiceGUI web app.

Out of scope:

- NiceGUI page layout, UI widget implementation, application adapters, and browser live-update behavior.
- Any write controls or orchestration behavior.

Expected task checkboxes: 1.2, 1.9, deployment portions of 1.10 and 1.11.

Verification commands:

- python3 scripts/kind-control-plane-smoke.py --help
- kubectl kustomize deploy/kind/control-plane
- python3 -m pytest scripts/test-web-app-hub.py scripts/test-steward-session-validator.py

## Integration Verification

After accepted implementer handoffs are merged into round-20260510t212023z-5a85-integration, run:

- python3 -m pytest scripts/test-web-app-hub.py
- python3 -m pytest scripts/test-wait-for-review-artifact.py scripts/test-steward-session-validator.py
- kubectl kustomize deploy/kind/control-plane
- python3 scripts/validate-openspec-change.py use-nicegui

Explicit blocker checks before final review:

- The rendered kind web-app Deployment starts the NiceGUI application using a runtime image/path with the NiceGUI package installed.
- Rendered NiceGUI pages consume `/api/live` for visible in-place updates, reconnect or fallback polling feedback, and selected-context preservation.
