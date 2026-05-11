# Explorer Findings: make-live-1

## Scope Read

Goal: remove the old UI, make the React/Vite new UI the live operator UI, and remove old preview and non-live references.

The repo currently has two browser surfaces:

- Existing live UI: `scripts/web_app_hub.py` or optional `scripts/web_app_nicegui.py`, deployed as `scion-ops-web-app` by `deploy/kind/control-plane/web-app-deployment.yaml`, exposed through `deploy/kind/control-plane/web-app-service.yaml` on container port `8787`, NodePort `30808`, and default host URL `http://192.168.122.103:8808`.
- New UI: `new-ui-evaluation/` React/Vite app plus `new-ui-evaluation/adapter.py`, deployed separately as `scion-ops-new-ui-eval` by `deploy/kind/control-plane/new-ui-evaluation-deployment.yaml`, exposed through `deploy/kind/control-plane/new-ui-evaluation-service.yaml` on container port `8080`, NodePort `30880`, and default host URL `http://192.168.122.103:8880`.

Recent OpenSpec history intentionally kept those surfaces separate. `base-framework-1` introduced a fixture-backed preview, `wire-new-ui-1` made that preview live-read capable while still separate, and `use-nicegui`/`update-web-app`/`autorefresh-web-app` define the current production web app as a read-only web-app hub.

## Lowest-Risk OpenSpec Shape

Use a new change directory:

```text
openspec/changes/make-live-1/
  proposal.md
  design.md
  tasks.md
  specs/web-app-hub/spec.md
  specs/new-ui-evaluation/spec.md
```

Recommended split:

- `specs/web-app-hub/spec.md`: primary delta for the live operator UI identity. Modify requirements so the system's deployed web app uses the React/Vite operator console and keeps the existing live URL/service identity. Add scenarios for the new UI serving as the default live web app, preserving read-only source-of-truth behavior, retaining health/snapshot/SSE endpoints, and removing the old NiceGUI/server-rendered UI path from the live deployment.
- `specs/new-ui-evaluation/spec.md`: cleanup delta for retiring the preview identity. Modify or remove requirements that require separate preview naming, separate preview ports, fixture-first/evaluation language, and coexistence with the old UI. Add scenarios that explicit fixture mode remains a development/test fallback only and is not described as a production preview.

This is lower risk than inventing a third capability name because the existing spec set already distinguishes `web-app-hub` as the production operator surface and `new-ui-evaluation` as the temporary React/Vite path.

## Constraints To Preserve

- Keep the UI read-only. Page load, filtering, navigation, snapshot fetches, SSE connection/reconnect, fallback polling, diagnostics, and health checks must not mutate Hub records, MCP state, Kubernetes resources, git refs/files, OpenSpec files, secrets, PVCs, broker state, rounds, or model/provider state.
- Keep the browser-facing operational data contract aligned with existing Hub, MCP, Kubernetes, git, and OpenSpec structured fields. The spec should not ask the frontend to parse prose where structured MCP or Hub fields exist.
- Preserve Kubernetes probe behavior and no-spend smoke behavior. The live web app still needs `/healthz` and JSON/SSE endpoints suitable for smoke checks.
- Make `scion-ops-web-app` the single live browser service name and operator access path. Remove `scion-ops-new-ui-eval` as a separate deployed preview service from the desired state.
- Remove preview/non-live language from operator docs and task names where it would survive as the normal path: `docs/new-ui-evaluation.md`, `docs/kind-control-plane.md`, `Taskfile.yml`, `scripts/kind-scion-runtime.sh`, `scripts/kind-control-plane-smoke.py`, `deploy/kind/control-plane/kustomization.yaml`, and the `new-ui-evaluation-*` manifests.
- Keep fixture mode explicit for local development and tests only. Do not make fixtures the production fallback for the live operator path.
- Avoid expanding scope into authentication, write operations, model/provider execution, historical replay, alerts, or backend consolidation beyond what is necessary to make the React/Vite adapter own the live web-app identity.

## Implementation Surface The Spec Should Anticipate

Likely code and manifest changes after the spec is accepted:

- Change `deploy/kind/control-plane/web-app-deployment.yaml` to run the React/Vite adapter/image under the `scion-ops-web-app` Deployment identity.
- Change or remove `deploy/kind/control-plane/new-ui-evaluation-deployment.yaml` and `deploy/kind/control-plane/new-ui-evaluation-service.yaml`.
- Update `deploy/kind/control-plane/kustomization.yaml` so only the live web-app resources are rendered.
- Update `Taskfile.yml` to remove `new-ui-eval` preview lifecycle tasks or convert the useful pieces into `web-app` live tasks.
- Update `scripts/build-images.sh` and `image-build/new-ui-eval/Dockerfile` naming if the React/Vite image becomes the web-app image.
- Update `scripts/kind-control-plane-smoke.py` and `scripts/kind-scion-runtime.sh` defaults/checks so smoke validates one live UI endpoint rather than coexistence between two UI endpoints.
- Update docs to describe the React/Vite app as the live operator console, not an evaluation preview.

## Validation Hooks

The resulting OpenSpec change should be valid under `scripts/validate-openspec-change.py`: include `proposal.md`, `design.md`, checkbox tasks, and at least one delta spec with `## ADDED Requirements`, `## MODIFIED Requirements`, or `## REMOVED Requirements`, plus `### Requirement` and `#### Scenario` entries.

Post-implementation verification should include:

- OpenSpec validation for `make-live-1`.
- Frontend typecheck, tests, and build under `new-ui-evaluation/`.
- Adapter endpoint tests for `/healthz`, `/api/snapshot`, `/api/events`, and mutation rejection.
- Rendered kustomize check proving only the live `scion-ops-web-app` UI service/deployment remains.
- No-spend kind smoke proving the live UI endpoint serves React/Vite live data and no preview endpoint/coexistence requirement remains.
