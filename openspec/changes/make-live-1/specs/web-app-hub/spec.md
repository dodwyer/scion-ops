# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Operator Overview

The system SHALL provide a React/Vite live operator overview that summarizes scion-ops readiness and recent round activity through the canonical web app service, using concise source-backed information focused on operator action, handoff, source health, live freshness, and the next useful inspection target.

#### Scenario: Operator opens the live React overview

- GIVEN Hub, MCP, Kubernetes, broker, web app, live update, and round sources provide current state
- WHEN an operator opens the canonical web app URL
- THEN the React/Vite operator console is served as the live UI
- AND the overview shows control-plane readiness, live freshness, active round count, blocked round count, recent round context, and the highest-priority source or round needing attention
- AND the page does not present itself as a preview, evaluation build, mocked demo, or non-live UI.

#### Scenario: Overview remains source backed and read only

- GIVEN the overview displays readiness, activity, blockers, warnings, source errors, or stale state
- WHEN data is loaded, refreshed, streamed, reconnected, or recovered from fallback polling
- THEN displayed values are derived from structured Hub, MCP, Kubernetes, git, OpenSpec, live update, or normalized helper output
- AND fallback-derived text is used only when structured fields are unavailable
- AND loading, refreshing, drilling into details, or receiving live updates does not mutate round state, Hub records, MCP state, Kubernetes resources, git refs, OpenSpec files, secrets, PVCs, broker state, or model/provider state.

### Requirement: Kind Kustomize Installation

The system SHALL run the React/Vite operator console as the canonical local kind web app while preserving the stable web app Deployment, Service, probe, workspace, auth, and read-only runtime conventions.

#### Scenario: Control-plane kustomization renders one live UI

- GIVEN an operator renders or applies `deploy/kind/control-plane`
- WHEN kustomize produces the control-plane resources
- THEN the rendered resources include one live operator UI Deployment using the web app identity
- AND include one live operator UI Service using the web app identity and stable operator access path
- AND do not include a separate new-UI evaluation or preview Deployment or Service
- AND do not include the old NiceGUI/server-rendered UI as the live web app workload.

#### Scenario: Live web app uses in-cluster Scion configuration

- GIVEN the React/Vite operator console runs inside the kind control plane
- WHEN it loads runtime configuration
- THEN it uses the in-cluster Hub endpoint
- AND it uses the in-cluster MCP service URL and path
- AND it uses the active grove id from the mounted scion-ops checkout when available
- AND it reads Hub dev auth from the same mounted Secret convention used by MCP and the previous web app.

### Requirement: Source Of Truth Preservation

The system SHALL derive React/Vite-displayed operational state from existing scion-ops Hub, MCP, Kubernetes, git, and OpenSpec sources, while keeping browser-visible JSON contracts aligned with current MCP and web app tool result contracts.

#### Scenario: Live console renders source-backed state

- GIVEN MCP, Hub, Kubernetes, git, OpenSpec, or normalized helper output exposes structured readiness, round, event, artifact, validation, final-review, blocker, warning, branch, source-health, stale, fallback, or failure fields
- WHEN the React/Vite console renders overview, rounds, round detail, inbox, runtime, diagnostics, or raw source views
- THEN displayed values are derived from those structured source fields
- AND message text, notification text, task summaries, agent names, or slugs are used only as fallback sources when structured fields are unavailable
- AND fallback-derived values are not allowed to override structured MCP, Hub, Kubernetes, git, or OpenSpec fields.

#### Scenario: Browser JSON contract remains compatible

- GIVEN existing tests, smoke checks, or external scripts request browser-facing JSON snapshot, round detail, round event, live update, runtime, source-health, or health endpoints
- WHEN the React/Vite console owns the live web app identity
- THEN those endpoints remain available with backward-compatible field names and semantics where currently consumed
- AND source identifiers, timestamps, statuses, branch fields, validation fields, blockers, warnings, final-review verdicts, cursor values, live update state, stale state, fallback state, schema version, and source-specific errors remain explicit JSON fields
- AND automation does not need to scrape rendered HTML to recover operational state.

## ADDED Requirements

### Requirement: React Vite Live Operator Console

The system SHALL make the React/Vite UI the single live operator console for scion-ops.

#### Scenario: React/Vite console owns the web app identity

- GIVEN the live operator UI is deployed locally or in kind
- WHEN an operator or smoke check reaches the canonical web app URL
- THEN the served browser application is the React/Vite console
- AND the live UI is identified as the scion-ops web app or operator console
- AND production-facing routes, labels, titles, schema versions, logs, docs, tasks, and smoke output do not identify the normal path as evaluation, preview, mocked, fixture-backed, or non-live.

#### Scenario: Old UI is retired from the live path

- GIVEN the live control-plane deployment is rendered, applied, restarted, or smoke tested
- WHEN operators use the canonical web app URL
- THEN the old NiceGUI/server-rendered UI is not served as the live operator interface
- AND the old UI is not required for health checks, JSON snapshots, event streams, source-health reporting, docs, lifecycle tasks, or no-spend smoke checks.

#### Scenario: One operator UI access path is documented

- GIVEN operators read local kind or runtime documentation
- WHEN they look for the scion-ops operator UI
- THEN the documented access path points to the canonical live React/Vite web app
- AND documentation does not instruct operators to choose between old and new UIs or to open a separate preview URL for normal monitoring.

### Requirement: Live Fixture Boundary

The system SHALL keep fixture-backed UI data only as an explicit local development or test facility and SHALL NOT expose fixture mode as a production operator path.

#### Scenario: Production path is live

- GIVEN the live web app Deployment starts in the kind control plane
- WHEN the React/Vite console loads its initial snapshot or subscribes to updates
- THEN the source mode is live by default
- AND fixture query parameters, fixture CLI defaults, fixture schema versions, or mocked safety flags are not available as normal operator controls in the production path.

#### Scenario: Fixture mode is explicit and labeled

- GIVEN maintainers intentionally enable fixture mode for local development or tests
- WHEN the UI displays fixture-backed data
- THEN the payload and visible UI metadata identify the data as fixture-backed
- AND the fixture mode cannot be mistaken for current source-of-truth Hub, MCP, Kubernetes, git, or OpenSpec state.

### Requirement: Live UI Verification

The system SHALL include no-spend verification that the React/Vite UI is the live web app and that old preview or non-live references are absent from production-facing paths.

#### Scenario: Deployment verification proves single live UI

- GIVEN maintainers run rendered kustomize or control-plane smoke checks
- WHEN the live operator UI resources are inspected
- THEN exactly one canonical web app UI Deployment and Service are expected
- AND old NiceGUI live resources and separate new-UI evaluation resources are not expected in the default live manifest set.

#### Scenario: Runtime verification proves live terminology

- GIVEN maintainers run endpoint, smoke, documentation, or static checks for the live operator UI
- WHEN production-facing output is inspected
- THEN default URLs, titles, schema identifiers, source mode, logs, task names, and smoke messages use live operator-console terminology
- AND preview, evaluation, mocked, or fixture terminology appears only in historical OpenSpec artifacts, tests, or explicitly labeled local development fixtures.

#### Scenario: Safety verification remains no-spend

- GIVEN maintainers run live UI verification
- WHEN page load, snapshot fetch, event subscription, reconnect, cursor resume, fallback polling, health checks, or diagnostics are exercised
- THEN the checks do not start model-backed work
- AND do not mutate Hub records, MCP state, Kubernetes resources, git refs or files, OpenSpec files, secrets, PVCs, broker state, rounds, or model/provider state.
