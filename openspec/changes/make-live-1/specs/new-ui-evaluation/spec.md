# Delta: New UI Evaluation

## MODIFIED Requirements

### Requirement: Mocked Operator Data Contract

The system SHALL preserve schema-faithful fixture data only as an explicit local development or test fallback for the React/Vite operator console; fixture data SHALL NOT define a production preview identity or the normal live runtime path.

#### Scenario: Fixture fallback is local only

- GIVEN a developer or test explicitly enables fixture mode outside the production deployment
- WHEN the React/Vite UI loads fixture data
- THEN the payload and UI metadata identify the data as fixture-backed
- AND fixture fallback does not become the default live runtime path
- AND fixture mode is not exposed as a production preview service.

#### Scenario: Production data is live

- GIVEN the live web app deployment is running
- WHEN the React/Vite UI requests operator state
- THEN it receives live read-only operational data by default
- AND production payloads do not identify the service as mocked, fixture-only, an evaluation preview, or a non-live UI.

### Requirement: Core Mocked Operator Views

The system SHALL provide the current React/Vite operator workflows as the canonical live UI using live operational data as the primary runtime source while preserving fixture-backed examples for development and test verification only.

#### Scenario: Operator opens the live console

- GIVEN the React/Vite UI is deployed under `scion-ops-web-app`
- WHEN an operator opens the configured live web app URL
- THEN the first screen shows a compact operational overview with live readiness, freshness, round counts, blocked work, recent activity, and the next useful inspection target
- AND the screen is presented as the live operator console rather than an evaluation URL or preview.

#### Scenario: Operator reviews live operational views

- GIVEN live round, inbox, runtime, source health, diagnostic, and raw payload data exists
- WHEN an operator opens the React/Vite views
- THEN the UI shows source-backed state with severity, timestamps, validation, final review, branch evidence, blockers, events, artifacts, and runtime diagnostics
- AND allows only read-only selection, filtering, grouping, navigation, and drill-in interactions.

### Requirement: Read Only Preview Safety

The system SHALL keep the React/Vite UI read-only while replacing preview-specific safety language with live UI safety language for production documentation, runtime metadata, and smoke checks.

#### Scenario: Live UI reads sources safely

- GIVEN an operator loads, refreshes, filters, navigates, expands diagnostics, or subscribes to any React/Vite view in live mode
- WHEN the UI needs data
- THEN it may read live Hub, MCP, Kubernetes, git, and OpenSpec operational state through defined read-only adapters, watchers, or stream bridges
- AND it does not read model-backed or provider-backed state except for read-only status fields explicitly exposed by the operational sources.

#### Scenario: Live UI avoids mutations

- GIVEN an operator interacts with overview, rounds, round detail, inbox, runtime, diagnostics, or raw payload views
- WHEN controls are used, streams connect, streams reconnect, snapshots load, cursors resume, or fallback polling runs
- THEN the live UI does not start, retry, abort, delete, archive, or mutate rounds
- AND does not modify Kubernetes resources, Hub runtime records, MCP state, git refs or files, OpenSpec files, secrets, PVCs, runtime broker state, or model/provider state.

### Requirement: Evaluation Verification

The system SHALL verify the React/Vite UI as the live web app, including read-only safety, live data contracts, health checks, event delivery, fixture isolation, and removal of preview coexistence assumptions.

#### Scenario: Static and contract checks run for the live UI

- GIVEN implementation work for the live React/Vite UI promotion is complete
- WHEN maintainers run relevant validation checks
- THEN TypeScript type checks and frontend build checks pass
- AND adapter tests verify live health, snapshot payloads, event payloads, static asset serving, and mutation rejection
- AND fixture checks verify fixtures are explicit development or test fallback only.

#### Scenario: Smoke checks target one live UI

- GIVEN the kind control-plane install is running
- WHEN maintainers run no-spend smoke checks
- THEN the checks validate the `scion-ops-web-app` live UI health, snapshot, and event endpoints
- AND the checks do not require a separate new UI evaluation endpoint
- AND the checks do not require coexistence between old and new UI services.

## REMOVED Requirements

### Requirement: Separate Evaluation Preview Deployment

The system SHALL NOT require a separate deployed `scion-ops-new-ui-eval` preview service or deployment once the React/Vite UI is promoted to the live web app.

#### Scenario: Preview deployment is absent from desired live state

- GIVEN the control-plane kustomization is rendered for the live install
- WHEN operators inspect browser UI resources
- THEN there is no required `scion-ops-new-ui-eval` Deployment or Service
- AND preview-only NodePort, URL, task, smoke, and documentation references are absent from the desired live state.
