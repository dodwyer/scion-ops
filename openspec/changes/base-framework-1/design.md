# Design: Base Framework 1

## Overview

The new UI evaluation should be a parallel, mocked operator console that lets scion-ops assess a fresh frontend direction without disrupting the current UI. It should demonstrate the views operators need now, define the data contract those views expect, and prove the deployment can coexist safely with the existing web app.

The evaluation should not borrow the previous visual hierarchy, page layout, CSS, or implementation stack. It should use a restrained operations-console style focused on scanning, comparison, and drill-in, with mocked data that represents the shape of real scion-ops state.

## Framework And Language Decision

The evaluation UI should use TypeScript, React, and Vite.

TypeScript is the right implementation language for the browser layer because the UI will depend on structured operational records: rounds, timelines, branch evidence, source health, inbox messages, validation state, final review state, and raw diagnostics. Static types make fixture contracts explicit and reduce the risk that later live wiring drifts from the mocked shapes.

React is the preferred frontend framework because the target UI is component-heavy and stateful: tables, timelines, tabs, filters, status badges, detail panes, and diagnostics all need predictable composition. React also keeps the evaluation aligned with a widely understood ecosystem, making future hiring, review, test tooling, and UI library choices lower risk than a niche framework.

Vite is the preferred build tool because it provides fast local development, straightforward TypeScript support, and a static production build that can be served by a small adapter. It keeps the evaluation lightweight while leaving room for focused frontend tests and preview builds.

The evaluation should use a small Python HTTP/API adapter rather than a full application backend. Python matches the repository's operational tooling, can serve static assets and mocked JSON with little surface area, and keeps the preview compatible with the current Kubernetes and scripting environment.

## Alternatives Considered

NiceGUI and other Python-native UI frameworks fit existing Python code well, but they couple the browser experience to server-side UI composition. The evaluation goal is to test a modern browser-first operator console, so a typed frontend application is a better fit.

Plain server-rendered HTML would reduce tooling, but it would make interactive table, timeline, filtering, and diagnostic states harder to evolve and test. It would also provide less leverage for type-checking frontend data contracts.

Svelte, Vue, Solid, and similar frameworks could support the UI. React is preferred for this evaluation because its ecosystem, contributor familiarity, and component/testing library maturity reduce adoption risk for an operational console.

A Node-only server could serve the preview, but it would introduce a second backend runtime for a mocked adapter. The Python adapter keeps the server side intentionally small and consistent with scion-ops operational code.

## Deployment Shape

The evaluation UI should deploy separately from the existing UI.

Expected Kubernetes shape:

- A new Deployment for the evaluation UI pod.
- A new Service with a stable name distinct from the existing web app Service.
- A container port and host or service port distinct from the current UI port.
- Labels and naming that make the preview clearly identifiable as an evaluation path.
- Readiness and liveness checks for the Python adapter.
- No ServiceAccount, Secret, PVC, or environment variable that grants live mutation privileges.
- No dependency on the current UI Deployment lifecycle.

The current UI remains the production operator surface during evaluation. The preview can be started, stopped, redeployed, or removed without changing current web app behavior.

## Mock Data Contract

The Python adapter should expose mocked JSON endpoints or bundled fixture payloads that match the view needs before live source wiring exists.

The contract should include:

- Overview state: control-plane summary, active counts, blocked counts, recent activity, freshness, and top operator attention target.
- Rounds list: round id, goal, state, phase, owner or agents, branch evidence, validation state, final review state, blockers, timestamps, and latest event summary.
- Round detail: selected-round summary, timeline, participant agents, decisions, validation output summary, branch refs, artifacts, runner output, and related messages.
- Inbox and messages: grouped notifications, source, severity, timestamp, round linkage, and read-only context.
- Runtime and source health: Hub, MCP, Kubernetes, git, model/provider, adapter, fixture freshness, and preview service health.
- Diagnostics and raw payloads: source-specific errors, stale or degraded states, representative raw JSON, schema version, and fixture provenance.

Fixture data should include healthy, blocked, failed, stale, degraded, empty, and mixed-source cases so the UI can be judged against realistic operator workflows.

## Core Views

The evaluation should mock these basic views:

- **Overview:** a compact operational first screen with readiness, freshness, round counts, blocked work, and the next useful inspection target.
- **Rounds:** a dense comparison of active and recent rounds with filters or grouping for state, phase, validation, final review, branch evidence, and blockers.
- **Round Detail:** a selected-round view with summary, timeline, agents, decisions, validation, final review, artifacts, branch evidence, runner output, and messages.
- **Inbox:** operator-relevant messages grouped by round or source with severity, timestamps, and direct links to related mocked detail.
- **Runtime:** source and service health for Hub, MCP, Kubernetes, git, model/provider, adapter, and preview deployment state.
- **Diagnostics:** one-level-down raw payloads, fixture schema metadata, source errors, and degraded-state evidence.

The UI should be read-only. Controls may refresh fixture data, filter client-side lists, select rows, expand diagnostics, or navigate between mocked views, but they must not imply that real operations are available.

## Coexistence And Safety

The evaluation must not change the existing UI's routes, Service, Deployment, port, scripts, health checks, or lifecycle. Any documentation or task wiring should name the preview separately and make it clear that the current UI remains authoritative until a later OpenSpec change says otherwise.

The preview must not read live Hub, MCP, Kubernetes, git, OpenSpec, or model-backed state. This keeps evaluation deterministic, avoids accidental spend or mutation, and makes clear that displayed data is mocked. Future live wiring requires a separate change that updates the data contract, security model, and verification strategy.

## Verification Strategy

Validation should include:

- OpenSpec validation for the additive change.
- Static and type checks for the TypeScript/React/Vite application once implemented.
- Unit or fixture tests for the mocked data contract and adapter endpoints.
- Kubernetes manifest checks proving separate Deployment, Service, labels, and port.
- Smoke checks that the preview health endpoint and mocked overview load without the existing UI.
- Coexistence checks proving the existing UI still builds, deploys, and serves on its original port.
- Read-only checks proving preview routes do not contact live Hub, MCP, Kubernetes, git, OpenSpec, or model-backed systems.
