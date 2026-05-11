# Design: Make Live 1

## Overview

The live operator UI should have one stable operational identity: `scion-ops-web-app`. The React/Vite frontend and its Python adapter become the implementation behind that identity. The old server-rendered UI stops being deployed as the live browser surface, and the separate `scion-ops-new-ui-eval` preview identity is retired from manifests, smoke checks, tasks, and operator documentation.

The change is intentionally a promotion and cleanup, not a broad backend redesign. The React/Vite adapter continues to expose read-only snapshots, Server-Sent Events, health, diagnostics, and static assets. Operators keep a single live URL and single service lifecycle.

## Deployment Model

The kind control-plane kustomization should render a single browser UI Deployment and Service named `scion-ops-web-app`. That deployment runs the React/Vite adapter image, serves the built static assets, and exposes the adapter health and data endpoints on the service port used by the live web app.

The separate `scion-ops-new-ui-eval` Deployment and Service should be removed from the desired live install. The old web-app deployment implementation should not start `scripts/web_app_hub.py` or the NiceGUI/server-rendered UI in the live path.

## Runtime Contract

The live UI remains read-only. Page load, filtering, navigation, diagnostics, snapshot fetches, SSE connection, SSE reconnect, cursor resume, and fallback polling may read Hub, MCP, Kubernetes, git, and OpenSpec operational state. They must not mutate rounds, Hub records, MCP state, Kubernetes resources, git refs or files, OpenSpec files, secrets, PVCs, runtime broker state, or model/provider state.

Production-facing payloads should use stable live UI naming. Schema versions, runtime service names, source identifiers, errors, health responses, and diagnostics should not describe the live service as an evaluation preview. Fixture-specific metadata may remain in fixture files and tests only when it is clearly marked as local development or test data.

## Documentation And Tooling

Operator documentation should present the React/Vite console as the canonical live UI. Task descriptions, smoke messages, default URLs, runtime setup output, and troubleshooting hints should refer to the live web app path instead of a separate new UI evaluation preview.

Smoke checks should validate one live UI endpoint. They should prove health, snapshot, event stream, live source mode, and read-only safeguards for `scion-ops-web-app`; they should not require coexistence between the old UI and the new UI.

## Verification Strategy

Verification should include:

- `python3 scripts/validate-openspec-change.py --project-root . --change make-live-1`.
- Rendered kustomize inspection proving the live UI Service and Deployment use `scion-ops-web-app` and no separate `scion-ops-new-ui-eval` UI resource remains.
- Adapter tests for `/healthz`, `/api/snapshot`, `/api/events`, static asset serving, and mutation rejection.
- Frontend typecheck, test, and build for the React/Vite UI.
- No-spend kind smoke proving the live web-app endpoint serves live read-only React/Vite data and the old preview coexistence check is gone.
