# Tasks: Make Live 1

- [ ] Update the live web-app deployment so `scion-ops-web-app` runs the React/Vite adapter and serves the built React/Vite assets.
- [ ] Remove the old server-rendered UI from the live deployment path.
- [ ] Remove the separate `scion-ops-new-ui-eval` Deployment, Service, kustomization entry, task lifecycle, and smoke target from the desired live state.
- [ ] Update runtime setup and smoke defaults so operators use one live UI endpoint.
- [x] Rename production-facing schema, runtime, service, health, and diagnostic metadata to remove preview/evaluation naming.
- [x] Keep fixture data and fixture mode available only as explicit local development and test fallback paths.
- [ ] Rewrite operator docs so the React/Vite console is documented as the canonical live UI.
- [ ] Add or update tests for health, snapshot, SSE, static assets, read-only mutation rejection, and removal of preview coexistence assumptions.
- [ ] Run OpenSpec validation, frontend checks, adapter tests, rendered kustomize inspection, and no-spend kind smoke checks.
