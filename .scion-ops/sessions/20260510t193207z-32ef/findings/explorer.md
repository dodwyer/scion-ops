# Explorer Findings: use-nicegui

Session: `20260510t193207z-32ef`
Change: `use-nicegui`
Base branch: `main`
Expected branch: `round-20260510t193207z-32ef-spec-explorer`

## Existing Framework

The web UI is currently implemented as a single Python script:

- `scripts/web_app_hub.py`
  - Inline `uv` script dependencies: `mcp>=1.13,<2`, `PyYAML>=6,<7`.
  - Imports `mcp_servers.scion_ops` directly and builds read-only snapshots from Hub, MCP, Kubernetes, git, and OpenSpec helpers.
  - Contains the source-normalization layer, browser-facing JSON contract, health endpoint, static `INDEX_HTML`, JavaScript live update behavior, and `ThreadingHTTPServer` request handler.
  - Exposes `/healthz`, `/api/snapshot`, `/api/contract`, `/api/live`, `/api/overview`, `/api/rounds`, `/api/rounds/{round_id}`, `/api/rounds/{round_id}/events`, `/api/inbox`, and `/api/runtime`.

Deployment and lifecycle are already wired:

- `deploy/kind/control-plane/web-app-deployment.yaml`
  - Reuses `localhost/scion-ops-mcp:latest`.
  - Runs `python "${SCION_OPS_ROOT}/scripts/web_app_hub.py"`.
  - Exposes container port `8787`.
  - Uses `/healthz` for readiness and liveness.
  - Mounts `/workspace`, Hub dev auth, optional GitHub token, and uses in-cluster Hub/MCP env vars.
- `deploy/kind/control-plane/web-app-service.yaml`
  - NodePort service on port `8787`, nodePort `30808`.
- `deploy/kind/control-plane/web-app-rbac.yaml`
  - Read-only access for deployments, services, pods, endpoints, and PVCs.
- `deploy/kind/control-plane/kustomization.yaml`
  - Already includes web app RBAC, Service, and Deployment.
- `Taskfile.yml`
  - `web:hub`, `update:web-app`, `kind:web-app:status`, `kind:web-app:logs`, control-plane restart/status, and smoke wiring already include the web app.

The current test surface is concentrated in:

- `scripts/test-web-app-hub.py`
  - Imports `scripts/web_app_hub.py` directly.
  - Exercises adapter behavior, health payload, snapshot construction, structured MCP precedence, final review semantics, Kubernetes web-app health, live update batches, and assertions against strings in `INDEX_HTML`.
- `scripts/kind-control-plane-smoke.py`
  - Includes no-spend web app endpoint readiness checks.
- `task verify`
  - Parses `scripts/web_app_hub.py` and runs `uv run scripts/test-web-app-hub.py`.

## Relevant OpenSpec Files

Lowest-risk OpenSpec path:

- Reuse and modify `openspec/changes/web-ui-theme/`.
  - Its `design.md` already states the design decisions must follow `https://lawsofux.com/` and use NiceGUI.
  - Its spec is already scoped to operational theme, semantic status styling, dense readable layout, and responsive operator usability.
  - Its task list is already complete, so the author should reopen or add new tasks for the NiceGUI replacement instead of creating an unrelated duplicate change.

Supporting constraints from existing accepted/in-flight web app changes:

- `openspec/changes/build-web-app-hub/specs/web-app-hub/spec.md`
  - Initial interface must stay read-only.
  - Runtime state must be derived from Hub, MCP, Kubernetes, or existing normalized helper output.
  - Source-specific failures must not blank unrelated healthy data.
  - Rounds, round detail, inbox, and overview are required views.
- `openspec/changes/update-web-app/specs/web-app-hub/spec.md`
  - Structured MCP/Hub fields are authoritative.
  - Browser-facing JSON should preserve source identifiers, timestamps, statuses, error categories, branch fields, OpenSpec validation, blockers, warnings, and final-review state.
  - Kind installation, lifecycle tasks, and no-spend smoke must continue to cover the web app.
- `openspec/changes/web-ui-theme/specs/web-app-hub/spec.md`
  - UI must stay restrained, operational, dense, semantic, responsive, and keyboard-focus visible.
  - Avoid marketing-style hero sections, ornamental gradients, decorative illustrations, oversized typography, layout motion, and decorative dashboard widgets.

## Lowest-Risk Implementation Constraints

The safest implementation is a framework swap at the presentation/server boundary, not a rewrite of the operational data model.

Keep or extract from `scripts/web_app_hub.py`:

- Data provider and normalization functions.
- `BROWSER_JSON_CONTRACT`.
- `build_health`, `build_snapshot`, `build_round_detail`, `build_live_update_batch`, and `merge_live_events`.
- Structured-field precedence rules for MCP/Hub data over fallback text parsing.
- Read-only behavior: no round start, abort, retry, delete, Kubernetes mutation, or Hub mutation.

Replace or adapt:

- `INDEX_HTML` and the hand-written JavaScript rendering.
- `HubRequestHandler` / `ThreadingHTTPServer` routing.
- HTML string assertions in tests.

NiceGUI-specific constraints:

- Add `nicegui` to the inline `uv` dependencies in `scripts/web_app_hub.py` or move the UI into a new script with the same deployment command updated.
- Preserve `--host`, `--port`, `SCION_OPS_WEB_HOST`, and `SCION_OPS_WEB_PORT` behavior so `Taskfile.yml` and Kubernetes env vars keep working.
- Preserve `/healthz` because Kubernetes probes and smoke checks depend on it.
- Preserve existing `/api/*` JSON routes unless tests and smoke are intentionally updated together; this is the lowest-risk way to keep external and fixture contracts stable while NiceGUI renders the UI.
- NiceGUI normally runs on FastAPI/Starlette/Uvicorn, so implementation should use NiceGUI page routes for the UI and FastAPI routes for the existing JSON endpoints.
- Ensure the container image has the new dependency available through `uv` inline metadata or image build updates. Because the deployment currently invokes `python scripts/web_app_hub.py`, plain `python` will not install inline `uv` dependencies. The existing script works only because required packages are already in the reused MCP image. NiceGUI must therefore be added to the image dependencies or the deployment command must run through `uv run`.

Deployment constraints:

- Keep the process listening on `0.0.0.0:8787` in-cluster.
- Keep readiness/liveness path `/healthz`.
- Keep the `scion-ops-web-app` Deployment, Service, RBAC, labels, and NodePort behavior.
- If the deployment command changes to `uv run`, verify the MCP image contains `uv` and that startup remains acceptable for readiness probe timing.

Testing constraints:

- Update `scripts/test-web-app-hub.py` to stop depending on `INDEX_HTML` internals where possible.
- Preserve adapter-level tests for structured MCP precedence, blocked final review semantics, web app Kubernetes health, and live update merge behavior.
- Add focused NiceGUI route tests or rendered HTML checks for overview, rounds, round detail, inbox, and runtime using fixture data.
- Add responsive/theme checks only at the cheapest reliable level available in this repo. A simple rendered page smoke plus CSS/class assertions is lower risk than requiring browser tooling if Playwright is not already installed.
- Run:
  - `python3 scripts/validate-openspec-change.py web-ui-theme`
  - `uv run scripts/test-web-app-hub.py`
  - `task verify` when time/environment allows.
  - `kubectl kustomize deploy/kind/control-plane` or equivalent manifest render if deployment files change.

## Laws of UX Guidance for This UI

For the operator audience, apply Laws of UX as operational constraints rather than visual decoration:

- Jakob's Law: preserve familiar operations-console patterns: persistent nav, status summaries, tables for comparison, detail drill-downs, and explicit diagnostics.
- Hick's Law: default to concise action/context signals; put deep troubleshooting one level down in expandable or secondary detail areas.
- Miller's Law: group status by source and round; avoid dumping all raw MCP/Kubernetes detail into the first screen.
- Fitts's Law: make primary navigation, refresh, back, and row-selection targets easy to hit without oversized marketing UI.
- Proximity and Common Region: group status, branch, validation, final-review, and blocker details by source/round so operators can scan causality.
- Doherty Threshold: keep refresh feedback visible and quick; preserve current content while source-specific data refreshes or fails.
- Aesthetic-Usability Effect: restrained polish should improve confidence, but must not hide severity, provenance, timestamps, or source-specific errors.

## Recommended Author Plan

1. Update `openspec/changes/web-ui-theme/tasks.md` to add explicit NiceGUI migration tasks and verification tasks.
2. Refactor `scripts/web_app_hub.py` internally so adapter/model functions remain importable and rendering/server code is isolated.
3. Add NiceGUI dependency support in the runtime path that actually runs in Kubernetes.
4. Rebuild UI routes in NiceGUI:
   - Overview: concise readiness and source status.
   - Rounds: dense table-like comparison.
   - Round detail: default summary plus one-level-down diagnostics for MCP, branches, validation, logs, and timeline.
   - Inbox: grouped by round with timestamps and source labels.
   - Runtime: source-specific health, Kubernetes web app status, and troubleshooting payloads.
5. Preserve the existing JSON endpoints and health endpoint while replacing the static `INDEX_HTML` implementation.
6. Update tests around route/render behavior and keep adapter tests intact.
7. Validate OpenSpec, tests, and rendered kind manifests.

## Primary Risk

The largest implementation risk is dependency/runtime mismatch: the deployed web app currently runs with `python`, not `uv run`, and reuses the MCP image. NiceGUI must be available in that image or startup will fail in kind even if local `uv run scripts/web_app_hub.py` works.

The second-largest risk is accidentally rewriting the source-of-truth logic while changing frameworks. Keep the MCP/Hub/Kubernetes normalization path stable and make NiceGUI consume the same snapshot/detail structures.
