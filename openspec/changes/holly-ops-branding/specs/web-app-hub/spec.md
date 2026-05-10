# Delta: Web App Hub

## ADDED Requirements

### Requirement: Holly Ops Drive Branding

The system SHALL present the web UI as Holly Ops Drive, with HHD as an accepted short form, wherever the UI identifies the product experience to a human operator.

#### Scenario: Operator opens the web app

- GIVEN an operator opens the web UI in a browser
- WHEN the page title, app header, primary product label, or read-only app description renders
- THEN the UI identifies itself as Holly Ops Drive
- AND compact labels MAY use HHD after the full name has been established
- AND browser-visible product identity does not use scion-ops hub as the product name.

#### Scenario: Web UI describes backing sources

- GIVEN the web UI renders overview, rounds, inbox, runtime, or round detail data
- WHEN labels refer to actual backing systems or diagnostics
- THEN the UI preserves accurate Scion runtime terms such as Hub, broker, agents, MCP, templates, steward sessions, branches, rounds, OpenSpec, final review, and Kubernetes
- AND the UI does not rename those runtime primitives to Holly Ops Drive or HHD.

### Requirement: Holly Operator Persona

The system SHALL use Holly for operator-facing references to the bot or coordinator that conducts actions, without renaming Scion protocol roles or durable state fields.

#### Scenario: Coordinator output is shown as persona copy

- GIVEN the UI, README, documentation, or human-readable MCP instructions describe the action-conducting assistant to an operator
- WHEN that text is product or persona copy rather than a protocol field
- THEN the assistant is named Holly
- AND the text may clarify that Holly coordinates Scion-backed rounds.

#### Scenario: Runtime role terminology is shown

- GIVEN templates, steward sessions, agent records, final-review routing, branch metadata, JSON fields, or protocol text rely on coordinator, steward, agent, template, or specialist terminology
- WHEN those terms identify Scion mechanics or compatibility contracts
- THEN the existing Scion role terminology remains unchanged
- AND no compatibility field is renamed solely for branding.

### Requirement: Branding Compatibility Boundary

The system SHALL preserve existing compatibility identifiers during this low-risk branding pass.

#### Scenario: Deployment identifiers are referenced

- GIVEN documentation, scripts, tests, or web diagnostics reference Kubernetes resources, kind contexts, image names, services, labels, selectors, or RBAC subjects
- WHEN those references are executable identifiers or deployed resource names
- THEN names such as `scion-ops-web-app`, `scion-ops-mcp`, `scion-ops`, `kind-scion-ops`, and `localhost/scion-ops-mcp:latest` remain unchanged
- AND surrounding prose may describe the product as Holly Ops or the UI as Holly Ops Drive.

#### Scenario: Client and state identifiers are referenced

- GIVEN documentation, MCP server code, tests, or session tooling reference MCP tool names, Python modules, env vars, CLI flags, JSON fields, or session paths
- WHEN those references are compatibility identifiers
- THEN names such as `scion_ops_*`, `SCION_OPS_*`, `mcp_servers/scion_ops.py`, and `.scion-ops` remain unchanged
- AND the implementation does not require a migration for existing clients or steward session state.

### Requirement: Holly Ops Documentation Branding

The system SHALL update operator-facing documentation prose to introduce Holly Ops and Holly Ops Drive while preserving executable compatibility examples.

#### Scenario: Operator reads README or docs prose

- GIVEN README or operator documentation describes the product experience in prose
- WHEN the prose is not an executable command, path, env var, resource name, or protocol identifier
- THEN it uses Holly Ops for the product experience
- AND it uses Holly Ops Drive for the web UI when the web experience is specifically referenced.

#### Scenario: Operator follows documented commands

- GIVEN README or operator documentation includes commands, config snippets, MCP tool names, paths, Kubernetes resource names, env vars, or branch/session state examples
- WHEN those examples are required for existing deployments or clients
- THEN the examples preserve their current compatibility identifiers
- AND any nearby renamed prose clearly distinguishes branding from unchanged operational names.
