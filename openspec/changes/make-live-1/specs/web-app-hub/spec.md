# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Operator Overview

The system SHALL provide a React/Vite operator console as the live web-app overview that summarizes scion-ops readiness from existing Hub, Runtime Broker, MCP, Kubernetes runtime state, the deployed web app control-plane component, and live update freshness.

#### Scenario: Operator opens the live React/Vite overview

- GIVEN Hub is reachable and authenticated
- AND at least one Runtime Broker provider is registered for the active grove
- AND MCP is reachable
- AND required Kubernetes deployments and services for Hub, broker, MCP, and the web app are available
- AND the live update path is fresh or connected
- WHEN an operator opens the configured live web app URL
- THEN the app shows the React/Vite operator console as the live UI
- AND shows contributing Hub, broker, MCP, web app, Kubernetes, and live update checks as healthy
- AND shows active, blocked, and recent round context without requiring the operator to open a diagnostic view.

#### Scenario: Overview avoids old UI framing

- GIVEN the live web app has been deployed
- WHEN the operator inspects the page, service metadata, docs, task output, smoke output, or runtime diagnostics
- THEN the live UI is not described as NiceGUI, an evaluation, a preview, mocked data, or a non-live console
- AND the old server-rendered UI is not advertised as the live operator path.

### Requirement: Source Of Truth Preservation

The system SHALL derive React/Vite-displayed operational state from existing scion-ops Hub, MCP, Kubernetes, git, OpenSpec, and normalized helper sources, while keeping browser-visible JSON contracts aligned with current MCP and web app tool result contracts.

#### Scenario: React/Vite renders source-backed state

- GIVEN MCP, Hub, Kubernetes, git, OpenSpec, or normalized helper output exposes structured readiness, round, event, artifact, validation, final-review, blocker, warning, or branch fields
- WHEN the live React/Vite app renders overview, rounds, round detail, inbox, runtime, or troubleshooting views
- THEN the displayed values are derived from those structured source fields
- AND message text, notification text, task summaries, agent names, or slugs are used only as fallback sources when structured fields are unavailable
- AND fallback-derived values are not allowed to override structured MCP or Hub fields.

#### Scenario: Browser JSON contract remains live and compatible

- GIVEN existing tests, smoke checks, or external scripts request browser-facing health, snapshot, round detail, event stream, or live update endpoints
- WHEN the React/Vite console is the live web app
- THEN those endpoints remain available with documented field names and semantics
- AND source identifiers, timestamps, statuses, branch fields, validation fields, blockers, warnings, final-review verdicts, cursor values, event state, and source-specific errors remain explicit JSON fields
- AND automation does not need to scrape rendered HTML to recover operational state.

### Requirement: Read Only Initial Interface

The system SHALL keep the live React/Vite web app read-only and SHALL NOT expose round-starting, aborting, retrying, deleting, archiving, git-writing, OpenSpec-writing, Kubernetes-mutating, Hub-mutating, MCP-mutating, broker-mutating, secret-mutating, PVC-mutating, or model/provider operations.

#### Scenario: Operator uses live React/Vite views

- GIVEN an operator opens overview, rounds, round detail, inbox, runtime, diagnostics, or raw payload views
- WHEN the app loads, refreshes data, expands diagnostics, follows drill-ins, reconnects streams, resumes cursors, or receives live updates
- THEN it does not start rounds
- AND it does not abort, retry, delete, archive, or mutate rounds
- AND it does not modify Kubernetes resources, Hub runtime records, MCP state, git refs or files, OpenSpec files, secrets, PVCs, runtime broker state, or model/provider state.

#### Scenario: Automatic update recovery remains read-only

- GIVEN the live React/Vite app subscribes, reconnects, resumes from a cursor, or falls back to bounded polling
- WHEN the automatic update path recovers from stale or disconnected state
- THEN recovery performs only read operations against Hub, MCP, Kubernetes, git, and OpenSpec status sources
- AND no state-changing operation is exposed as an implied or hidden side effect.

### Requirement: Kind Kustomize Installation

The system SHALL run the React/Vite operator console in the local kind control-plane install under the stable live `scion-ops-web-app` Deployment and Service identity.

#### Scenario: Control-plane kustomization renders one live web app

- GIVEN an operator runs the control-plane kustomize apply path
- WHEN kustomize renders `deploy/kind/control-plane`
- THEN the rendered resources include a web app Deployment named `scion-ops-web-app` that starts the React/Vite adapter
- AND include a web app Service named `scion-ops-web-app` with the stable operator access path
- AND do not include a separate `scion-ops-new-ui-eval` Deployment or Service as a live preview UI.

#### Scenario: Old UI is not deployed live

- GIVEN the kind control-plane web app deployment is running
- WHEN the live web app process starts
- THEN it serves the React/Vite static assets and adapter endpoints
- AND it does not start `scripts/web_app_hub.py`, the old NiceGUI app, or the previous server-rendered UI as the live browser surface.

#### Scenario: Live UI remains reachable through existing workflow

- GIVEN the kind control plane has been created with the configured host port mappings
- WHEN the `scion-ops-web-app` Service is ready
- THEN an operator can open the configured web app URL from the host without running `kubectl port-forward`
- AND no-spend smoke checks can reach health, snapshot, and event endpoints without starting model-backed rounds.
