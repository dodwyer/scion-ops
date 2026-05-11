# Web App UI

The `new-ui-evaluation/` directory implements the canonical live operator console for scion-ops. In the kind control-plane deployment it runs as `scion-ops-web-app` — the only browser UI Deployment and Service. Local fixtures are retained only as an explicit development or test fallback path.

## Stack

- TypeScript, React, and Vite implement the browser application.
- `new-ui-evaluation/adapter.py` is a small Python HTTP adapter that serves the built static assets, live read-only snapshots, and an SSE event stream.
- `new-ui-evaluation/fixtures/local-fixtures.json` is retained as the explicit local fixture fallback contract for overview, rounds, round detail, inbox, runtime/source health, diagnostics, and raw payloads.

This stack keeps the browser layer typed and component-oriented while keeping the server side small and aligned with the repository's Python operational tooling. The tradeoffs and alternatives are captured in `openspec/changes/base-framework-1/design.md`.

## Safety Model

The console is read-only. Browser controls may load snapshots, subscribe to the stream, reconnect, filter client-side tables, select records, navigate between views, or expand diagnostics.

The adapter only allows `GET`, `HEAD`, and `OPTIONS`. Mutation verbs return `405` with a read-only error. Live mode reads Hub state through the existing read-only MCP/Hub operational APIs when they are configured and available, probes the MCP HTTP endpoint, and reads Kubernetes, git, and OpenSpec status through read-only commands or file reads. Local `.scion-ops/sessions` metadata is retained only as explicit degraded fallback metadata when Hub reads are unavailable. It does not start, retry, abort, delete, archive, or mutate rounds; it does not write Kubernetes resources, Hub records, MCP state, git refs or files, OpenSpec files, secrets, PVCs, runtime broker state, or model/provider state.

Fixture mode is available only with `--mode fixture` or `SCION_OPS_WEB_APP_MODE=fixture`. Fixture safety checks require:

- `fixtureBacked: true`
- `runtime.liveService.fixtureOnly: true`
- `runtime.liveService.liveReadsAllowed: false`
- `runtime.liveService.mutationsAllowed: false`

No ServiceAccount, Secret, PVC, git credential, provider token, or model configuration is required. If `kubectl` cannot read cluster status, the Kubernetes source is marked degraded and other live source data remains available.

## Local Use

Install frontend dependencies:

```bash
cd new-ui-evaluation
npm install
```

Run the adapter against the built assets in live mode:

```bash
npm run build
python adapter.py --host 127.0.0.1 --port 8091
```

Open `http://127.0.0.1:8091`.

Use explicit fixture fallback for local fixture-only development or tests:

```bash
python adapter.py --host 127.0.0.1 --port 8091 --mode fixture
```

For frontend iteration with Vite proxying API calls to the adapter:

```bash
python adapter.py --host 127.0.0.1 --port 8091
npm run dev
```

Open the Vite URL, normally `http://127.0.0.1:5174`.

## Live Contract

- `GET /api/snapshot` returns a versioned `scion-ops-web-app.live.v1` snapshot containing `sourceMode`, `fixtureBacked`, `generatedAt`, a content cursor, source health, connection metadata, overview, rounds, round details, inbox, `runtime.liveService`, diagnostics, and raw payload references. Hub and MCP source health is based on read-only operational API/probe results, not local file or module existence.
- `GET /api/events` returns `text/event-stream` frames using `scion-ops-web-app.event.v1`. Events include type, stable id, entity id when applicable, source, timestamp, version/cursor, payload, source status, stale flag, and error metadata. After the initial connection frame, the stream polls read-only sources and emits typed incremental events such as `round_updated`, `timeline_entry`, `inbox_item`, `runtime_health`, `diagnostic`, `source_status`, `stale`, and `fallback` when those source slices change.
- Reconnect uses the `cursor` query parameter when available. The server keeps a bounded in-memory cursor history and replays missed typed incremental events from a known cursor; if replay is unavailable, `/api/events` emits an explicit `snapshot_ready` recovery event containing the current read-only snapshot.

## Endpoints

- `GET /healthz`
- `GET /api/snapshot`
- `GET /api/events`
- `GET /api/fixtures` (returns the active mode snapshot; fixture-backed only when explicit fixture mode is enabled)
- `GET /api/overview`
- `GET /api/rounds`
- `GET /api/rounds/{round_id}`
- `GET /api/inbox`
- `GET /api/runtime`
- `GET /api/diagnostics`

In live mode these endpoints serve read-only operational data. In fixture mode they serve local fixture data and mark `sourceMode: fixture`. A missing round detail returns `404`; this is used by the UI to demonstrate empty detail states.

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
