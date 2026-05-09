# Implementation Steward Session 20260509t212708z-native2

Change: update-web-app
Base branch: round-20260509t185251z-1cfe-spec-integration
Final branch: round-20260509t212708z-native2-integration

Goal:
Implement the accepted OpenSpec change update-web-app from fresh spec steward session 20260509t185251z-1cfe. Align the web app with current scion-ops MCP structured fields, keep it read-only, include it in the kind/kustomize control-plane install, add required tests and no-spend smoke coverage, verify rendered kustomize output, and produce the PR-ready integration output.

## Approved Artifacts

- `openspec/changes/update-web-app/proposal.md`
- `openspec/changes/update-web-app/design.md`
- `openspec/changes/update-web-app/tasks.md`
- `openspec/changes/update-web-app/specs/web-app-hub/spec.md`

## Task Groups And Branch Ownership

### Group A: MCP-Aligned Web App Contract And UI

Branch: `round-20260509t212708z-native2-impl-codex`

Owned paths:
- `scripts/web_app_hub.py`
- `scripts/test-web-app-hub.py`
- optional web-app fixture files under `scripts/` if needed
- `openspec/changes/update-web-app/tasks.md` only for completed tasks in group A

Scope:
- Document or encode the browser-facing JSON contract for MCP-aligned round, event, artifact, validation, blocker, warning, and final-review fields.
- Update the read-only backend adapter to prefer current MCP/Hub structured fields and use prose parsing only as fallback.
- Update overview, rounds, round detail, runtime, and inbox rendering so blocked, changes-requested, validation failure, branch, and protocol milestone state remains visible.
- Add or update fixture tests for representative current MCP payloads including `scion_ops_run_spec_round`, `scion_ops_round_artifacts`, `scion_ops_spec_status`, and blocked final-review payloads.

Out of scope:
- Kubernetes manifests, Taskfile lifecycle changes, docs, and kind smoke scripts.
- Product write operations or new MCP tool names.
- Accepted OpenSpec archives outside `openspec/changes/update-web-app`.

Expected completed task checkboxes:
- `1.1`
- `1.2`
- `1.3`
- `1.4`

### Group B: Kind/Kustomize Install, Lifecycle, Docs, Smoke

Branch: `round-20260509t212708z-native2-impl-claude`

Owned paths:
- `deploy/kind/control-plane/**`
- `Taskfile.yml`
- `scripts/kind-control-plane-smoke.py`
- `docs/kind-control-plane.md`
- `README.md` only if it already documents kind control-plane URLs or lifecycle
- `openspec/changes/update-web-app/tasks.md` only for completed tasks in group B

Scope:
- Add web app Deployment, Service, and any required read-only ServiceAccount/RBAC/config wiring to `deploy/kind/control-plane`.
- Wire in-cluster Hub/MCP/grove/dev-auth/workspace settings consistently with the MCP deployment.
- Include the web app in kind lifecycle tasks for apply, rollout status, logs, and narrow web-app update/status workflows.
- Extend no-spend smoke coverage to verify the deployed web app endpoint/readiness without starting model-backed rounds.
- Update operator docs for the web app URL, kind install behavior, and troubleshooting commands.
- Verify rendered `deploy/kind/control-plane` kustomize output includes the web app Deployment and Service.

Out of scope:
- Web app Python adapter/UI/test fixture changes except where absolutely necessary to support a documented smoke endpoint.
- Product write operations or MCP contract changes.
- Accepted OpenSpec archives outside `openspec/changes/update-web-app`.

Expected completed task checkboxes:
- `2.1`
- `2.2`
- `2.3`
- `2.4`
- `3.3` if render verification is run on this branch

## Steward Integration Tasks

Branch: `round-20260509t212708z-native2-integration`

Owned paths:
- Integration merge commits across accepted implementer branches.
- `.scion-ops/sessions/20260509t212708z-native2/**` durable state and reviews.
- `openspec/changes/update-web-app/tasks.md` verification checkboxes after integration verification.

Scope:
- Confirm implementer branches moved, review summaries, and integrate accepted changes.
- Resolve conflicts without reverting unrelated user or implementer work.
- Run final verification and update tasks `3.1`, `3.2`, and any remaining `3.3` only after commands pass.
- Start final-review agent and require an accepting verdict before marking ready.

## Verification Commands

Run on implementer branches as applicable, then repeat on integration:

- `openspec validate update-web-app --strict` or repo-equivalent OpenSpec validation command if this repo uses a wrapper.
- `python3 scripts/test-web-app-hub.py`
- `python3 -m py_compile scripts/web_app_hub.py scripts/test-web-app-hub.py scripts/kind-control-plane-smoke.py`
- `kubectl kustomize deploy/kind/control-plane` or `kustomize build deploy/kind/control-plane`
- `task kind:control-plane:status` if a kind cluster is available.
- `python3 scripts/kind-control-plane-smoke.py --no-spend` or the repo-equivalent no-spend smoke invocation, after confirming the script's actual CLI.

## Notes

- The web app must remain read-only.
- Structured MCP/Hub fields are authoritative; fallback values must not override them.
- Final-review rejected, changes-requested, revise, failed, or blocked states must not render as generic completion.
- The kind install must expose the web app without requiring manual `kubectl port-forward`.
