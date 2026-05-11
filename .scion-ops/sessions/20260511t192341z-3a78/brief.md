# Implementation Brief: make-live-1

Session: 20260511t192341z-3a78
Base branch: main
Integration branch: round-20260511t192341z-3a78-integration

## Goal

Promote the React/Vite operator console and Python adapter to the live `scion-ops-web-app` UI, remove the old server-rendered/NiceGUI UI from the live deployment path, and remove preview/evaluation wording and lifecycle from live runtime, manifests, smoke, tasks, and operator docs.

## Task Groups

### Group A: Live React/Vite Adapter And Frontend Contract

Branch: round-20260511t192341z-3a78-impl-codex

Owned paths:
- `new-ui-evaluation/**`

Scope:
- Rename production-facing adapter schema, health, runtime, source, error, diagnostic, and static-serving metadata away from `new-ui-evaluation`, preview, eval, mocked, and non-live wording.
- Preserve fixture mode as an explicit local development/test fallback only.
- Keep health, `/api/snapshot`, `/api/events`, static assets, and read-only mutation rejection working under the live UI contract.
- Update frontend copy and tests in `new-ui-evaluation/**` so the browser surface presents the React/Vite console as the live operator console.
- Update only the task checkboxes this branch fully completes.

Out of scope:
- Kubernetes manifests, Dockerfiles, Taskfile, runtime scripts, smoke scripts, and docs outside `new-ui-evaluation/**`.
- Deleting the historical `new-ui-evaluation` source directory.

Verification commands:
- `cd new-ui-evaluation && npm test`
- `cd new-ui-evaluation && npm run typecheck`
- `cd new-ui-evaluation && npm run build`
- `python3 -m pytest new-ui-evaluation/tests/test_adapter.py`

### Group B: Live Deployment, Smoke, Task, Runtime, And Docs Promotion

Branch: round-20260511t192341z-3a78-impl-claude

Owned paths:
- `deploy/kind/control-plane/**`
- `deploy/kind/cluster.yaml.tpl`
- `image-build/**`
- `scripts/build-images.sh`
- `scripts/kind-control-plane-smoke.py`
- `scripts/kind-scion-runtime.sh`
- `Taskfile.yml`
- `docs/**`
- `openspec/changes/make-live-1/tasks.md`

Scope:
- Make the rendered kind control-plane install run the React/Vite adapter image behind the stable `scion-ops-web-app` Deployment and Service.
- Remove `scion-ops-new-ui-eval` Deployment, Service, kustomization entry, task lifecycle, image build target naming, runtime setup output, smoke target, and preview coexistence checks from desired live state.
- Ensure the old `scripts/web_app_hub.py`/NiceGUI UI is not started by the live deployment path.
- Update operator docs and task descriptions to describe the React/Vite console as the canonical live UI.
- Update only the task checkboxes this branch fully completes.

Out of scope:
- React/Vite application source and adapter internals under `new-ui-evaluation/**`.
- Historical OpenSpec changes outside `openspec/changes/make-live-1/tasks.md`.

Verification commands:
- `python3 scripts/validate-openspec-change.py --project-root . --change make-live-1`
- `kubectl kustomize deploy/kind/control-plane | rg 'scion-ops-web-app|scion-ops-new-ui-eval|web_app_hub|adapter.py'`
- `python3 scripts/kind-control-plane-smoke.py --help`
- `python3 -m py_compile scripts/kind-control-plane-smoke.py`

## Integration Verification

Run on the integration branch after accepted implementation branches are merged:
- `python3 scripts/validate-openspec-change.py --project-root . --change make-live-1`
- `cd new-ui-evaluation && npm test`
- `cd new-ui-evaluation && npm run typecheck`
- `cd new-ui-evaluation && npm run build`
- `python3 -m pytest new-ui-evaluation/tests/test_adapter.py`
- `python3 -m py_compile scripts/kind-control-plane-smoke.py`
- `kubectl kustomize deploy/kind/control-plane > /tmp/make-live-1-rendered.yaml`
- `rg 'scion-ops-new-ui-eval|new-ui-eval|web_app_hub|NiceGUI|previewService' /tmp/make-live-1-rendered.yaml` should return no live UI matches.
- No-spend kind smoke when a kind control plane is available: `python3 scripts/kind-control-plane-smoke.py`.
