# Explorer Findings: New UI Direction

Session: `20260511t125050z-3e38`
Change: `base-framework-1`
Branch: `round-20260511t125050z-3e38-spec-explorer`

## Current Framework And Runtime Evidence

- The current operator UI is implemented as a repository-local Python script, `scripts/web_app_hub.py`, with PEP 723 `uv` metadata for Python `>=3.11` and dependencies on `mcp`, `nicegui`, and `PyYAML`.
- The existing script owns a broad browser JSON contract in `BROWSER_JSON_CONTRACT`, including readiness snapshots, round detail, final review, agent matrix, runtime state, and live update cursor semantics.
- Existing Kubernetes deployment runs a `scion-ops-web-app` Deployment from the `localhost/scion-ops-mcp:latest` image and starts either `scripts/web_app_nicegui.py` when present or `scripts/web_app_hub.py` as fallback.
- Existing service is named `scion-ops-web-app`, exposes container/service port `8787`, and uses NodePort `30808`.
- Task defaults expose the current web app externally as `SCION_OPS_WEB_APP_URL` on host port `8808`, while the Kubernetes Service manifest uses NodePort `30808`; this mismatch should be treated as existing deployment context to verify before assigning the new UI port.
- Existing control-plane lifecycle tasks include only `scion-ops-web-app` in restart/status/smoke paths. A coexistence UI must add separate lifecycle names or narrowly extend smoke checks without replacing current checks.

## Prior OpenSpec Constraints

- `openspec/changes/use-nicegui/design.md` already specifies a NiceGUI rebuild and says existing browser-facing contracts are compatibility boundaries: health, snapshot, round detail, event, live update, source identifiers, timestamps, statuses, branches, blockers, warnings, final review, and runtime readiness.
- The same design requires local execution with repo tooling, the existing kind deployment model, read-only ServiceAccount/RBAC, mounted workspace, Hub dev-auth Secret convention, and smoke checks that do not start model-backed work.
- `openspec/changes/web-ui-theme/design.md` and `better-information-ui/design.md` constrain the UI toward a restrained operations console: compact status, dense comparison tables, one-level-down diagnostics, semantic state labels, no marketing/hero treatment, and responsive desktop/mobile behavior.
- `openspec/changes/autorefresh-web-app/specs/web-app-hub/spec.md` requires automatic update semantics to stay read-only and preserve source-of-truth fields.
- These prior changes are about the current `web-app-hub` capability. The new request explicitly asks for a brand new UI direction and framework/language evaluation instead of inheriting current assumptions, so the lowest-risk spec should be additive rather than another modification of `web-app-hub`.

## Recommended Framework And Language

Recommendation: TypeScript + React + Vite for the new evaluation UI, served as static assets by a small Python HTTP/API adapter.

Rationale:

- The new UI is a mocked-data evaluation surface, so it benefits from browser-native component iteration, typed mock data contracts, deterministic fixture rendering, and easy visual review.
- TypeScript gives the mock data contract first-class compile-time shape. This is useful because the requested end state is a mocked operator view that later receives real backend wiring.
- React/Vite is a conservative choice for an SPA-style operator console with tables, tabs, filters, routeable views, and fixture-driven screenshots.
- A small Python serving layer keeps compatibility with the current repo and container environment, avoids forcing Node into the runtime pod if static assets are prebuilt, and can expose `/healthz` plus `/api/mock/*` endpoints using the same Python version already present in the base image.
- This recommendation intentionally differs from current NiceGUI assumptions while still coexisting with them. The current NiceGUI/Python UI remains untouched on its existing Deployment/Service/port.

Rejected alternatives:

- Extending the existing NiceGUI app is lower tooling risk but does not satisfy the instruction to evaluate a new UI direction instead of inheriting current implementation assumptions.
- A pure static HTML/CSS/JS mock is lower dependency risk but weakens typed contracts and makes future backend wiring less disciplined.
- A full Node runtime service is viable but adds more Kubernetes/runtime surface than needed for a mocked evaluation pod.

## Lowest-Risk OpenSpec Shape

Create a new change directory:

- `openspec/changes/base-framework-1/proposal.md`
- `openspec/changes/base-framework-1/design.md`
- `openspec/changes/base-framework-1/tasks.md`
- `openspec/changes/base-framework-1/specs/new-ui-evaluation/spec.md`

Use a new spec capability name such as `new-ui-evaluation`, `operator-ui-evaluation`, or `scion-ops-ui-preview`. Avoid modifying `specs/web-app-hub/spec.md` in this change unless the author needs to explicitly document coexistence with the old UI.

Expected requirements for the delta spec:

- Framework and language decision is documented, including evaluated alternatives and final rationale.
- New UI is deployed as a separate Kubernetes pod/Deployment from `scion-ops-web-app`.
- New UI uses a different Service and host-reachable port from the existing UI.
- New UI serves mocked data only and does not call Hub, MCP, Kubernetes, git, OpenSpec, or model-backed work for live state.
- Mock data contract covers current operator workflows: overview, rounds list, round detail/timeline, inbox/messages, runtime/source health, and diagnostics/raw payloads.
- Mocked views represent ready, running, blocked, changes-requested, failed, stale, and empty states.
- Coexistence is explicit: no replacement of current `scion-ops-web-app`, no mutation of its Deployment/Service/probes, and no shared selector labels that route traffic ambiguously.
- Verification includes static contract checks, render checks for core views, Kubernetes manifest checks proving a distinct Deployment/Service/port, and no-spend smoke against `/healthz` and mocked data endpoints.

## Implementation Constraints To Hand Off

- Use distinct Kubernetes names, for example `scion-ops-ui-preview`, with labels that do not collide with `app.kubernetes.io/name: scion-ops-web-app`.
- Choose ports after checking existing allocations. Current UI uses container/service port `8787` and Service NodePort `30808`; Taskfile defaults mention host port `8808`.
- Keep the preview read-only by construction: mocked fixtures should be bundled or served from local JSON files, and UI controls should be filters/navigation/diagnostic expansion only.
- Keep deployment additive in `deploy/kind/control-plane/kustomization.yaml`; do not remove current `web-app-*` resources.
- Add a dedicated image only if necessary. Lowest risk is probably a small preview image or an explicit command in the existing image that serves prebuilt static assets, but the spec should require the author to justify this choice.
- Preserve current `task up`, `task test`, and existing web app smoke behavior. Add preview-specific task/smoke coverage rather than repurposing `kind:web-app:*`.

## Suggested Mock Data Contract

Top-level fixture shape:

- `generated_at`
- `readiness`
- `sources[]` with `id`, `label`, `status`, `latency_ms`, `last_seen`, and optional `error`
- `rounds[]` with `round_id`, `title`, `phase`, `visible_status`, `updated_at`, `agents[]`, `branches`, `validation`, `final_review`, `blockers[]`, and `warnings[]`
- `timeline[]` per round with `entry_id`, `timestamp`, `actor`, `role`, `action`, `handoff`, `reason_for_handoff`, `status`, `source`, and optional `detail`
- `inbox[]` with `id`, `round_id`, `source`, `severity`, `summary`, `created_at`, and optional `payload`
- `runtime` with deployments/services/pods/readiness for the mocked control plane and preview UI
- `diagnostics` with raw fixture payloads and source errors

## Open Questions For Author/Steward

- Which exact host port should the preview use, given the current service manifest uses NodePort `30808` while Taskfile defaults expose `8808`?
- Should the TypeScript build output be checked in for the Kubernetes pod to serve directly, or should image build include `npm ci && npm run build`?
- Should the preview smoke test be part of the default `task test` path immediately, or separate until the evaluation UI is accepted?

## Risk Summary

The main risk is accidentally replacing or coupling to the current `web-app-hub` path. Keep the OpenSpec change additive, give the preview its own capability name and Kubernetes identity, and make the mock data contract explicit enough that the later backend wiring can be specified as a separate change.
