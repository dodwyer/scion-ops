# Delta: New UI Evaluation

## MODIFIED Requirements

### Requirement: Evaluation UI Framework

The system SHALL preserve the React, TypeScript, Vite, and Python adapter implementation as the basis of the live operator console, while retiring evaluation-only framing from production-facing runtime paths.

#### Scenario: Framework decision becomes live console foundation

- GIVEN maintainers inspect the live operator UI implementation
- WHEN they review the browser application and adapter
- THEN the browser application is written in TypeScript
- AND uses React for component composition and interactive view state
- AND uses Vite for local development and production static asset builds
- AND uses a Python adapter to serve built static assets plus health, snapshot, detail, diagnostic, and live event endpoints
- AND production-facing naming describes this stack as the live operator console rather than an evaluation preview.

### Requirement: Mocked Operator Data Contract

The system SHALL keep schema-faithful fixture data available only for explicit local development and tests now that the React/Vite UI is the live operator console.

#### Scenario: Live data is the default

- GIVEN the React/Vite operator console is running as the live web app
- WHEN overview, rounds, round detail, inbox, runtime, diagnostics, or raw source views request state
- THEN they receive live read-only operational data from Hub, MCP, Kubernetes, git, and OpenSpec sources
- AND the payload identifies the source mode as live.

#### Scenario: Fixtures remain test-only

- GIVEN a frontend unit test, adapter contract test, or explicitly configured local development session needs deterministic data
- WHEN fixture data is enabled
- THEN the payload and visible UI metadata identify the data as fixture-backed
- AND fixture data does not become the default runtime source for the live operator console.

### Requirement: Read Only Preview Safety

The system SHALL carry forward the read-only safety boundary for the React/Vite console while replacing preview-only fixture restrictions with live read-only source access.

#### Scenario: Live console reads sources safely

- GIVEN an operator loads, refreshes, filters, navigates, expands, subscribes, reconnects, resumes, or uses fallback polling in any live console view
- WHEN the console needs operational data
- THEN it may read live Hub, MCP, Kubernetes, git, and OpenSpec state through defined read-only adapters, watchers, or stream bridges
- AND it does not read model-backed or provider-backed state except for read-only status fields explicitly exposed by operational sources.

#### Scenario: Live console avoids mutations

- GIVEN an operator interacts with overview, rounds, round detail, inbox, runtime, diagnostics, or raw payload views
- WHEN controls are used, streams connect, streams reconnect, snapshots load, cursors resume, or fallback polling runs
- THEN the console does not start, retry, abort, delete, archive, or mutate rounds
- AND does not modify Kubernetes resources, Hub runtime records, MCP state, git refs or files, OpenSpec files, secrets, PVCs, runtime broker state, or model/provider state.

## REMOVED Requirements

### Requirement: Separate Preview Deployment

The system SHALL NOT require the React/Vite UI to run as a separate preview Deployment, Service, port, route, or operator access path once it is promoted to the live web app.

#### Scenario: Separate preview identity is retired

- GIVEN the live control-plane kustomization is rendered or applied
- WHEN Kubernetes resources for browser UIs are inspected
- THEN the React/Vite UI is represented by the canonical web app Deployment and Service
- AND no separate new-UI evaluation preview Deployment or Service is required for normal operator use
- AND no coexistence guarantee is required between the old UI and a separate React/Vite preview because the React/Vite UI is the live UI.

### Requirement: Core Mocked Operator Views

The system SHALL NOT define mocked operator views as the normal React/Vite operator experience after live promotion.

#### Scenario: Operator opens live views instead of mocked views

- GIVEN an operator opens the canonical live web app URL
- WHEN the overview, rounds, round detail, inbox, runtime, diagnostics, or raw source views render
- THEN they are live operational views by default
- AND they do not present representative fixture scenarios as if they were current control-plane state.

### Requirement: Evaluation Verification

The system SHALL NOT require verification that proves a separate mocked preview coexists with the old UI as the desired production state.

#### Scenario: Verification targets live promotion

- GIVEN maintainers run verification for the promoted React/Vite console
- WHEN deployment and smoke checks execute
- THEN they prove the React/Vite UI owns the live web app identity
- AND they prove old UI resources plus separate preview resources are absent from the default live deployment
- AND they do not require failures in a separate preview to be isolated from an old production UI because that coexistence model has been retired.
