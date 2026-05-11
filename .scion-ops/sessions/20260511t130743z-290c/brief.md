# Implementation Brief: 20260511t130743z-290c

Change: `base-framework-1`
Base branch: `main`
Integration branch: `round-20260511t130743z-290c-integration`

## Accepted Scope

Build an additive, read-only `new-ui-evaluation` preview path for scion-ops. The preview uses a TypeScript + React + Vite browser app served by a small Python adapter with mocked JSON fixtures. It must deploy independently from the existing `scion-ops-web-app`, use separate preview resource names and a distinct port, and must not perform live Hub, MCP, Kubernetes, git, OpenSpec, model/provider reads, or any mutations.

Concrete preview names and ports to use unless an implementer finds a direct conflict:

- App/package directory: `new-ui-evaluation/`
- Python adapter module: `new_ui_evaluation`
- Kubernetes Deployment: `scion-ops-new-ui-evaluation`
- Kubernetes Service: `scion-ops-new-ui-evaluation`
- App label: `app.kubernetes.io/name: scion-ops-new-ui-evaluation`
- Container/API port: `8088`
- Service port: `8088`
- Existing UI resources and port remain unchanged.

## Task Groups

### Group A: Preview application, adapter, fixtures, docs

Owner branch: `round-20260511t130743z-290c-impl-codex`

Owned paths:

- `new-ui-evaluation/**`
- `docs/new-ui-evaluation.md`
- `openspec/changes/base-framework-1/tasks.md` only for completed Group A checkboxes
- `.scion-ops/sessions/20260511t130743z-290c/findings/round-20260511t130743z-290c-impl-codex.json`

Responsibilities:

- Inventory current UI behavior enough to document protected resource names, ports, and lifecycle paths.
- Scaffold TypeScript, React, and Vite under `new-ui-evaluation/frontend`.
- Add a small Python adapter under `new-ui-evaluation/adapter` that serves the built frontend, `/healthz`, and fixture-backed mocked JSON endpoints.
- Define typed frontend data models and schema-faithful fixtures for overview, rounds, round detail/timeline, inbox, runtime/source health, diagnostics, and raw payloads.
- Build read-only mocked operator views for overview, rounds, round detail, inbox, runtime, and diagnostics using a new operations-console visual direction.
- Add explicit safety guards and tests showing the adapter serves only local fixtures and exposes no mutation or live-source behavior.
- Document the framework rationale, preview resource names/ports, operator access expectations, mocked-data status, and read-only limitations.

Out of scope:

- Editing `deploy/**`, `scripts/kind-*.py`, `scripts/kind-*.sh`, or `scripts/build-images.sh`.
- Changing existing `scripts/web_app_hub.py`, current UI routes, current UI deployment/service, or current UI smoke behavior.
- Adding live Hub, MCP, Kubernetes, git, OpenSpec, provider, model, credential, Secret, PVC, or mutation behavior.

Suggested verification:

- `python3 -m pytest new-ui-evaluation/tests`
- `npm --prefix new-ui-evaluation/frontend run typecheck`
- `npm --prefix new-ui-evaluation/frontend run build`
- `python3 scripts/validate-openspec-change.py --change base-framework-1`

### Group B: Kubernetes manifests, image/build integration, smoke and coexistence checks

Owner branch: `round-20260511t130743z-290c-impl-claude`

Owned paths:

- `deploy/kind/control-plane/new-ui-evaluation-*.yaml`
- `deploy/kind/control-plane/kustomization.yaml`
- `deploy/kind/smoke/**`
- `scripts/build-images.sh`
- `scripts/kind-control-plane-smoke.py`
- `scripts/kind-bootstrap.sh` only if preview-specific wiring is required
- `image-build/**` only for a preview-specific Dockerfile/build context if needed
- `openspec/changes/base-framework-1/tasks.md` only for completed Group B checkboxes
- `.scion-ops/sessions/20260511t130743z-290c/findings/round-20260511t130743z-290c-impl-claude.json`

Responsibilities:

- Add Kubernetes manifests for the separate preview Deployment, Service, labels, probes, and distinct `8088` port.
- Wire preview manifests into kind/kustomize without changing existing `scion-ops-web-app` Deployment, Service, port, health probes, routes, lifecycle, or operator access path.
- Add no-spend manifest/smoke coverage proving the preview resources are separate and the preview health plus mocked overview can load independently.
- Add coexistence checks proving existing UI deployment/service/port/health expectations remain unchanged.
- Keep preview resources free of ServiceAccounts, Secrets, PVCs, mutation privileges, and live-source environment variables.

Out of scope:

- Editing preview React components, frontend fixtures, or adapter endpoint implementations except for minimal path/port alignment needed for manifests.
- Replacing, redesigning, or changing the existing web app behavior.
- Introducing live-source wiring or write operations.

Suggested verification:

- `python3 scripts/kind-control-plane-smoke.py --help`
- `python3 scripts/validate-openspec-change.py --change base-framework-1`
- Manifest render/check command chosen by implementer from existing repo patterns, documented in handoff.
- Preview-specific smoke command chosen by implementer from existing repo patterns, documented in handoff.

## Steward Verification After Integration

- `python3 scripts/validate-openspec-change.py --change base-framework-1`
- `python3 -m pytest new-ui-evaluation/tests`
- `npm --prefix new-ui-evaluation/frontend run typecheck`
- `npm --prefix new-ui-evaluation/frontend run build`
- Preview manifest/smoke/coexistence checks added by Group B.

## Integration Notes

- Do not implement product changes in the steward checkout.
- Accept only branches with durable JSON handoffs, branch movement, changed files, completed assigned tasks, and documented tests.
- If an implementer is blocked or times out, record the structured blocker in `.scion-ops/sessions/20260511t130743z-290c/state.json` and route a narrower replacement branch if policy allows.
