# Tasks

- [x] 1.1 Inventory current UI deployment, service, port, health, and lifecycle paths that must remain untouched by the preview.
- [ ] 1.2 Scaffold the evaluation frontend with TypeScript, React, and Vite in a location that is clearly separate from the existing UI implementation.
- [ ] 1.3 Add a small Python HTTP/API adapter that serves the Vite build and mocked JSON data for the preview.
- [ ] 1.4 Define typed mock data models and fixtures for overview, rounds, round detail, timeline, inbox, runtime/source health, diagnostics, and raw payloads.
- [ ] 1.5 Build the mocked overview, rounds, round detail, inbox, runtime, and diagnostics views using the new visual direction.
- [ ] 1.6 Add explicit UI and adapter safeguards so the preview performs no live Hub, MCP, Kubernetes, git, OpenSpec, model-backed, or state-mutating operations.
- [ ] 1.7 Add Kubernetes manifests for a separate evaluation UI Deployment, Service, labels, probes, and distinct port.
- [ ] 1.8 Document how operators start, reach, and evaluate the preview alongside the current UI.
- [ ] 1.9 Add focused checks for TypeScript types, frontend build, adapter mocked endpoints, fixture contract shape, and preview health.
- [ ] 1.10 Add coexistence checks proving the existing UI deployment, service, port, and health behavior remain unchanged.
- [ ] 1.11 Run OpenSpec validation and the relevant no-spend static, unit, and manifest checks.
