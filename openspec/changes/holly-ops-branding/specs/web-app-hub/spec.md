# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Operator Overview

The system SHALL provide a web overview that summarizes Scion runtime readiness from existing Hub, Runtime Broker, MCP, Kubernetes runtime state, and the deployed Holly Ops Drive control-plane component.

#### Scenario: Operator opens Holly Ops Drive

- GIVEN an operator opens the web UI
- WHEN the overview renders
- THEN the browser-visible app identity is Holly Ops Drive
- AND constrained app identity may use HHD as the short name
- AND the overview still identifies real backing sources with their Scion runtime names, including Hub, broker, MCP, Kubernetes, agents, and steward-session state.

#### Scenario: Runtime source is displayed

- GIVEN the app renders Hub, Runtime Broker, MCP, Kubernetes, OpenSpec, template, agent, round, or steward-session details
- WHEN those details name real Scion primitives or compatibility surfaces
- THEN the app preserves the Scion runtime terminology
- AND it does not relabel those primitives as Holly Ops entities.

### Requirement: Round Detail Timeline

The system SHALL provide a round detail view that combines messages, notifications, agent status, runner output, coordinator output, and final outcome for a selected round while using Holly as the operator-facing coordinator display name.

#### Scenario: Coordinator output is displayed

- GIVEN a selected round includes coordinator output, coordinator status, or coordinator-derived terminal state
- WHEN the round detail view renders user-facing headings, labels, or summaries for that actor
- THEN the actor is displayed as Holly
- AND the underlying source role, structured field names, diagnostics, and runtime identifiers remain available without migration.

#### Scenario: Agent and steward terminology is displayed

- GIVEN a selected round includes Scion agents, steward sessions, templates, MCP events, branch evidence, or OpenSpec validation state
- WHEN the round detail view renders those diagnostics
- THEN it preserves those real runtime terms
- AND it does not rename agents, steward sessions, templates, MCP events, branch identifiers, or OpenSpec fields to Holly-specific runtime identifiers.

### Requirement: Source Of Truth Preservation

The system SHALL derive displayed operational state from existing Scion Hub, MCP, and Kubernetes sources, and SHALL keep browser-visible branding separate from source-of-truth identifiers and compatibility contracts.

#### Scenario: Branding is applied to display copy only

- GIVEN source data contains MCP tool names, MCP resource URIs, Kubernetes resource names, `.scion-ops` paths, kind names, template names, branch names, environment variable names, or structured Scion fields
- WHEN the web app normalizes and renders the data
- THEN it may apply Holly Ops Drive, HHD, or Holly labels only in display copy
- AND it preserves source identifiers and structured values in JSON, diagnostics, logs, and compatibility-sensitive surfaces.

#### Scenario: Existing clients continue to work

- GIVEN existing MCP clients, kind workflows, Kubernetes manifests, OpenSpec tooling, branch workflows, or `.scion-ops` session readers depend on current identifiers
- WHEN the Holly Ops branding change is implemented
- THEN those identifiers remain unchanged
- AND no migration is required for existing session state or local control-plane resources.

## ADDED Requirements

### Requirement: Holly Ops Display Identity

The system SHALL present the user-facing product experience as Holly Ops and the browser UI as Holly Ops Drive.

#### Scenario: Primary app identity renders

- GIVEN an operator opens any primary web app view
- WHEN the page chrome and browser metadata render
- THEN the visible app name is Holly Ops Drive
- AND the broader product name is Holly Ops where product-level copy is needed
- AND the app does not present the primary browser surface as `scion-ops hub`.

#### Scenario: Short name is needed

- GIVEN a compact navigation item, status label, browser context, or documentation table needs a short web UI name
- WHEN a short name is used
- THEN the short name is HHD
- AND the first prominent identity in operator-facing documentation or app chrome still makes clear that HHD means Holly Ops Drive.

### Requirement: Holly Coordinator Display

The system SHALL display the operator-facing bot/coordinator persona as Holly without changing runtime coordinator identifiers.

#### Scenario: Operator-facing bot copy renders

- GIVEN the UI or documentation describes the bot or coordinator that conducts actions for an operator
- WHEN that copy is display-only
- THEN it calls the persona Holly
- AND it does not require renaming stored coordinator role values, agent identifiers, MCP fields, or log-derived source names.

#### Scenario: Diagnostic source identity is needed

- GIVEN an operator inspects raw diagnostics, structured JSON, MCP payloads, logs, or source field names
- WHEN those diagnostics contain `coordinator` or other existing runtime identifiers
- THEN the app preserves those identifiers for traceability
- AND any Holly display label does not obscure the underlying source identity.
