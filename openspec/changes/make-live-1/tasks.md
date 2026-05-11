# Tasks: Make Live 1

- [ ] Update the kind web app Deployment to serve the React/Vite adapter and built assets under the `scion-ops-web-app` live identity.
- [ ] Remove the old NiceGUI/server-rendered web app resources from the default live control-plane kustomization.
- [ ] Remove the separate `scion-ops-new-ui-eval` preview Deployment and Service from the default live control-plane kustomization.
- [ ] Rename production-facing labels, service descriptions, logs, schema version strings, source metadata, and smoke output from evaluation or preview terminology to live operator-console terminology.
- [ ] Update lifecycle tasks, image build naming, runtime scripts, smoke checks, and operator docs so they describe one live React/Vite operator UI.
- [ ] Gate fixture mode behind explicit local development or test configuration and remove user-facing production query parameters, defaults, or docs that make fixtures appear live.
- [ ] Preserve health, snapshot, round detail, event stream, runtime, diagnostics, source-health, stale, fallback, and source-failure JSON contracts for automation.
- [ ] Add or update tests for live web app endpoint compatibility, read-only safety, fixture gating, schema identity, and React/Vite production build behavior.
- [ ] Add rendered kustomize verification proving only the canonical live web app UI is deployed and the old UI plus separate preview service are absent.
- [ ] Run OpenSpec validation, frontend checks, adapter tests, and no-spend control-plane smoke checks relevant to the live operator UI.
