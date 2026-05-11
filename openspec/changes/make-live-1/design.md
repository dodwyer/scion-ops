# Design: Make Live 1

## Overview

The React/Vite UI becomes the canonical live operator console by taking over the existing web app deployment identity and operator access path. The previous NiceGUI/server-rendered implementation is retired from live deployment rather than kept as a parallel browser surface.

The desired runtime shape is one live UI service: `scion-ops-web-app`. It serves the React/Vite static application through the Python adapter, exposes the existing health and JSON contracts used by automation, and connects to the live read-only snapshot and event-stream data path. The separate `scion-ops-new-ui-eval` preview identity is removed from kustomize and from normal lifecycle commands.

## Runtime Identity

The live operator UI should use permanent web app naming in Kubernetes resources, labels, docs, logs, scripts, and smoke output. Names that imply preview, evaluation, fixture-first behavior, or non-live operation should not appear in production-facing runtime paths.

Schema version strings and source metadata should use live console terminology such as a scion-ops console or web-app contract. Earlier evaluation schema names may remain in historical OpenSpec records or migration notes, but live endpoints must not advertise `new-ui-evaluation` as the current product identity.

## Deployment Shape

The kind control-plane kustomization should render only the live web app resources for the operator UI. The web app Deployment should start the React/Vite adapter and serve the built browser assets. The web app Service should keep the stable operator access path expected by local workflows and smoke checks.

The old UI manifests and the separate evaluation manifests should not both be rendered. If implementation keeps transitional files in the repository for a short period, they must not be part of the default live deployment and must not be documented as operator access paths.

## Data And Endpoint Compatibility

The live React/Vite UI continues to consume live read-only state from Hub, MCP, Kubernetes, git, and OpenSpec sources through the snapshot and event contracts established by prior changes. Browser-facing endpoints remain suitable for tests and automation:

- health and readiness probes;
- current snapshot or overview payloads;
- round detail payloads;
- round event or timeline payloads;
- live event stream or equivalent update path;
- runtime, source-health, stale, fallback, and failure metadata.

Automation should not need to scrape rendered HTML to recover operational state. Endpoint field additions are allowed when needed for the live UI identity, but existing compatible semantics should be preserved where current smoke checks and scripts depend on them.

## Fixture And Development Mode

Fixture-backed data remains useful for frontend unit tests, local visual iteration, and deterministic contract tests. It must be explicit, isolated from the production Deployment, and visibly labeled whenever it is active.

The live operator path must not expose query parameters, default CLI flags, environment defaults, smoke commands, or documentation that invite operators to use fixture or preview mode as the normal runtime. If a development mode remains, it should be gated by local/test configuration and excluded from production manifests.

## Safety Boundaries

This promotion does not add mutation authority. Page load, filtering, navigation, snapshot fetches, SSE or WebSocket subscriptions, reconnect, cursor resume, bounded fallback polling, health checks, and diagnostics remain read-only.

The live UI must not start, retry, abort, delete, archive, or mutate rounds, and must not modify Kubernetes resources, Hub runtime records, MCP state, git refs or files, OpenSpec files, secrets, PVCs, runtime broker state, or model/provider state.

## Verification Strategy

Verification should cover:

- OpenSpec validation for this change.
- Frontend typecheck, tests, and production build for the React/Vite UI.
- Adapter tests for health, snapshot, round detail, event stream, source-health, stale, fallback, and failure payloads.
- Tests proving fixture mode is explicit, labeled, and absent from production deployment defaults.
- Rendered kustomize checks proving the live deployment has one operator UI service using the web app identity and no separate evaluation preview service.
- No-spend smoke checks proving the live web app serves React/Vite live data through the canonical operator URL without starting model-backed work or mutating control-plane state.
