# New UI Evaluation Preview

The new UI evaluation is an additive, fixture-backed operator console under `new-ui-evaluation/`. It does not replace the existing `scion-ops-web-app`, does not share its routes or server implementation, and does not read live Hub, MCP, Kubernetes, git, OpenSpec, model, or provider state.

## Stack

- TypeScript, React, and Vite implement the browser application.
- `new-ui-evaluation/adapter.py` is a small Python HTTP adapter that serves the built static assets and local JSON fixtures.
- `new-ui-evaluation/fixtures/preview-fixtures.json` is the evaluation data contract for overview, rounds, round detail, inbox, runtime/source health, diagnostics, and raw payloads.

This stack keeps the browser layer typed and component-oriented while keeping the server side small and aligned with the repository's Python operational tooling. The tradeoffs and alternatives are captured in `openspec/changes/base-framework-1/design.md`.

## Safety Model

The preview is read-only. Browser controls only refresh local fixture reads, filter client-side tables, select mocked records, navigate between views, or expand diagnostics.

The adapter only allows `GET`, `HEAD`, and `OPTIONS`. Mutation verbs return `405` with a read-only error. Fixture safety checks require:

- `mocked: true`
- `runtime.previewService.fixtureOnly: true`
- `runtime.previewService.liveReadsAllowed: false`
- `runtime.previewService.mutationsAllowed: false`

No ServiceAccount, Secret, PVC, kubeconfig, git credential, provider token, or model configuration is required for this Group A preview slice.

## Local Use

Install frontend dependencies:

```bash
cd new-ui-evaluation
npm install
```

Run the adapter against the built assets:

```bash
npm run build
python adapter.py --host 127.0.0.1 --port 8091
```

Open `http://127.0.0.1:8091`.

For frontend iteration with Vite proxying API calls to the adapter:

```bash
python adapter.py --host 127.0.0.1 --port 8091
npm run dev
```

Open the Vite URL, normally `http://127.0.0.1:5174`.

## Fixture Endpoints

- `GET /healthz`
- `GET /api/fixtures`
- `GET /api/overview`
- `GET /api/rounds`
- `GET /api/rounds/{round_id}`
- `GET /api/inbox`
- `GET /api/runtime`
- `GET /api/diagnostics`

These endpoints serve local fixture data only. A missing round detail returns `404`; this is used by the UI to demonstrate empty detail states.

## Verification

Run the no-spend checks:

```bash
cd new-ui-evaluation
npm run typecheck
npm test
npm run build
python3 -m unittest discover -s tests
```

These checks validate TypeScript types, render the fixture-backed React overview, verify the fixture contract, exercise adapter endpoints, and confirm mutation requests are rejected.
