# Delta: New UI Evaluation

## ADDED Requirements

### Requirement: Evaluation UI Framework

The system SHALL implement the new UI evaluation direction as a separate browser application using TypeScript, React, and Vite, served by a small Python HTTP/API adapter.

#### Scenario: Framework decision is applied

- GIVEN the evaluation UI is scaffolded
- WHEN maintainers inspect the frontend implementation
- THEN the browser application is written in TypeScript
- AND uses React for component composition and interactive view state
- AND uses Vite for local development and production static asset builds
- AND does not reuse the current UI framework, page structure, CSS assumptions, or server-rendered layout as the basis for the new direction.

#### Scenario: Python adapter serves the preview

- GIVEN the evaluation UI has been built
- WHEN the preview process starts
- THEN a small Python adapter serves the built static assets
- AND exposes mocked JSON endpoints or equivalent fixture-backed responses required by the preview views
- AND exposes a health endpoint suitable for Kubernetes probes
- AND does not require a full production backend service for the evaluation.

#### Scenario: Framework rationale is preserved

- GIVEN maintainers review the evaluation artifacts
- WHEN they compare the chosen stack with reasonable alternatives
- THEN the documented rationale explains why TypeScript, React, Vite, and a Python adapter were chosen
- AND identifies tradeoffs against Python-native UI frameworks, plain server-rendered HTML, alternative JavaScript frameworks, and Node-only serving.

### Requirement: Separate Preview Deployment

The system SHALL run the evaluation UI as a separate Kubernetes workload from the existing scion-ops UI.

#### Scenario: Preview deploys independently

- GIVEN the evaluation UI Kubernetes manifests are applied
- WHEN Kubernetes creates the preview resources
- THEN the preview runs in its own Deployment and pod
- AND is exposed through a Service distinct from the existing UI Service
- AND uses labels and resource names that identify it as the new UI evaluation path.

#### Scenario: Preview uses a distinct port

- GIVEN the existing UI is deployed on its current port
- WHEN the evaluation UI Service is created
- THEN the evaluation UI serves traffic on a different container and service port from the existing UI
- AND operators can reach the preview without replacing, port-forwarding over, or shadowing the current UI endpoint.

#### Scenario: Existing UI remains unchanged

- GIVEN the evaluation UI is deployed, restarted, stopped, or removed
- WHEN operators use the existing scion-ops UI
- THEN the existing UI Deployment, Service, port, health checks, routes, lifecycle scripts, and operator access path continue to behave as before
- AND the preview deployment does not become a prerequisite for the existing UI.

### Requirement: Mocked Operator Data Contract

The system SHALL define schema-faithful mocked data for the evaluation UI views so later live backend wiring can replace fixtures without redesigning view data shapes.

#### Scenario: Overview mock data is available

- GIVEN the preview adapter is running
- WHEN the overview view requests mocked state
- THEN it receives control-plane summary, source readiness, freshness, active round count, blocked round count, recent activity, and highest-priority operator attention target fields
- AND the payload identifies that the data is mocked.

#### Scenario: Round workflow mock data is available

- GIVEN the preview adapter is running
- WHEN the rounds or round detail views request mocked state
- THEN they receive round identifiers, goals, states, phases, agents, branch evidence, validation state, final review state, blockers, timestamps, latest events, timeline entries, artifacts, runner output, and related messages
- AND the fixtures include healthy, blocked, failed, stale, degraded, empty, and mixed-source examples.

#### Scenario: Runtime and diagnostics mock data is available

- GIVEN the preview adapter is running
- WHEN the runtime, source health, diagnostics, or raw payload views request mocked state
- THEN they receive representative Hub, MCP, Kubernetes, git, model/provider, adapter, and preview service health fields
- AND receive source-specific errors, degraded state, raw JSON examples, schema version, and fixture provenance fields
- AND long or raw diagnostic content remains available one level down from the default overview.

### Requirement: Core Mocked Operator Views

The system SHALL provide mocked views for the current operator workflows needed to evaluate the new UI direction.

#### Scenario: Operator opens the mocked overview

- GIVEN the preview UI is running
- WHEN an operator opens the evaluation URL
- THEN the first screen shows a compact operational overview with readiness, freshness, round counts, blocked work, recent activity, and the next useful inspection target
- AND the screen uses the new visual direction rather than a landing page or inherited current-UI layout.

#### Scenario: Operator reviews mocked rounds

- GIVEN mocked round data exists
- WHEN an operator opens the rounds view
- THEN the UI shows active and recent rounds in a dense comparison format
- AND exposes state, phase, validation, final review, branch evidence, blockers, timestamps, and latest event context
- AND allows read-only selection, filtering, or grouping of mocked records.

#### Scenario: Operator inspects a mocked round

- GIVEN a mocked round is selected
- WHEN the operator opens round detail
- THEN the UI shows summary, timeline, agents, decisions, validation, final review, artifacts, branch evidence, runner output, and related messages
- AND keeps raw payloads and detailed diagnostics in a drill-in, tab, expander, drawer, or diagnostics view.

#### Scenario: Operator reviews inbox, runtime, and diagnostics

- GIVEN mocked inbox, runtime, and diagnostic data exists
- WHEN the operator opens those views
- THEN inbox messages are grouped by round or source with severity and timestamps
- AND runtime/source health shows Hub, MCP, Kubernetes, git, model/provider, adapter, and preview deployment status
- AND diagnostics expose raw payloads, schema metadata, source errors, and degraded-state evidence without crowding the default overview.

### Requirement: Read Only Preview Safety

The system SHALL keep the evaluation UI read-only and fixture-backed during the base framework evaluation.

#### Scenario: Preview avoids live source reads

- GIVEN an operator loads, refreshes, filters, navigates, or expands any preview view
- WHEN the preview needs data
- THEN it reads only local mocked fixtures or adapter-provided mocked responses
- AND does not read live Hub, MCP, Kubernetes, git, OpenSpec, model-backed, or provider-backed state.

#### Scenario: Preview avoids mutations

- GIVEN an operator interacts with overview, rounds, round detail, inbox, runtime, diagnostics, or raw payload views
- WHEN controls are used
- THEN the preview does not start, retry, abort, delete, archive, or mutate rounds
- AND does not modify Kubernetes resources, Hub runtime records, git refs, OpenSpec files, secrets, PVCs, or model/provider state.

#### Scenario: Preview communicates mocked status

- GIVEN the evaluation UI displays operational records
- WHEN an operator views any mocked state
- THEN the UI or adjacent metadata makes clear that the records are preview fixtures
- AND does not imply that mocked readiness, round progress, validation, final review, or runtime health represents live source-of-truth state.

### Requirement: Evaluation Verification

The system SHALL include no-spend verification for the new UI evaluation stack, mocked contract, deployment shape, and coexistence with the current UI.

#### Scenario: Static and contract checks run

- GIVEN implementation work for the evaluation UI is complete
- WHEN maintainers run the relevant validation checks
- THEN TypeScript type checks and frontend build checks pass
- AND adapter tests verify the mocked data endpoints and fixture contract shape
- AND the checks do not start model-backed work or contact live providers.

#### Scenario: Deployment checks prove separation

- GIVEN the preview Kubernetes manifests are rendered or applied
- WHEN maintainers inspect or smoke test them
- THEN the preview has a separate Deployment, Service, labels, probes, and distinct port
- AND the preview health endpoint and mocked overview can load independently of the existing UI.

#### Scenario: Coexistence checks protect current UI

- GIVEN the evaluation UI is present in the repository
- WHEN maintainers run coexistence checks
- THEN the existing UI deployment, service, port, health behavior, routes, and lifecycle remain unchanged
- AND failures in the preview do not fail the existing UI's smoke path except where an explicit preview-only check is being run.
