# Delta: Web App Hub

## ADDED Requirements

### Requirement: Holly Ops Drive Branding

The system SHALL present the browser/operator UI as Holly Ops Drive in primary user-facing branding surfaces.

#### Scenario: Operator opens the web UI

- GIVEN an operator opens the web app
- WHEN the document title, primary heading, navigation identity, or equivalent top-level brand surface renders
- THEN the UI identifies itself as Holly Ops Drive
- AND the UI does not present scion-ops or Scion Ops as the product brand on those primary surfaces.

#### Scenario: Compact UI space uses abbreviation

- GIVEN a UI surface has constrained space
- AND the surrounding view has already established Holly Ops Drive as the web UI name
- WHEN an abbreviated brand label is rendered
- THEN the label may use HHD
- AND HHD is treated as a short form for Holly Ops Drive rather than a replacement for the full name across primary branding surfaces.

### Requirement: Holly Ops Product Copy

The system SHALL use Holly Ops for user-facing copy that describes the product or operator experience as a whole.

#### Scenario: Product-experience copy is rendered

- GIVEN the web UI renders overview text, empty states, page descriptions, startup messages, or operator-facing help text
- WHEN the text describes the product experience rather than a concrete runtime identifier
- THEN the copy uses Holly Ops as the product name
- AND avoids using scion-ops or Scion Ops as the user-facing product name.

#### Scenario: Runtime-powered positioning is rendered

- GIVEN the UI explains the relationship between the product and its backing runtime
- WHEN the copy mentions Scion
- THEN it may describe Holly Ops as powered by or built on the Scion runtime
- AND it preserves Scion naming for actual runtime concepts.

### Requirement: Runtime Terminology Preservation

The system SHALL preserve precise Scion runtime terminology in web UI labels and diagnostics when those terms name actual backing systems, primitives, or source data.

#### Scenario: Runtime source data is shown

- GIVEN the web UI renders data from Hub, Runtime Broker, MCP, Kubernetes, OpenSpec, branch, validation, template, agent, grove, or steward session sources
- WHEN labels, table headings, metadata, diagnostics, or source errors identify those actual concepts
- THEN the UI keeps the corresponding runtime terminology
- AND does not rename those concepts to Holly Ops, Holly Ops Drive, HHD, or Holly.

#### Scenario: Steward session details are shown

- GIVEN the web UI renders a steward session id, phase, branch convention, state field, or persisted round artifact
- WHEN the surface identifies the durable Scion session primitive
- THEN it uses steward session terminology
- AND it may mention Holly only in surrounding human-readable copy that describes the coordinator persona conducting actions.

### Requirement: Compatibility Identifier Preservation

The system SHALL preserve existing compatibility identifiers in web UI diagnostics, examples, commands, and source-specific details.

#### Scenario: Technical identifiers are displayed

- GIVEN the web UI displays or documents MCP tool names, MCP server names, environment variables, Kubernetes resources, task names, scripts, CLI commands, HTTP paths, repository paths, module names, config keys, image names, or state paths
- WHEN those identifiers currently use `scion_ops`, `scion-ops`, `SCION_OPS`, or `.scion-ops`
- THEN the exact identifier remains unchanged
- AND the UI presents it as a technical identifier, command, path, resource name, or compatibility detail rather than as the product brand.

#### Scenario: Existing sessions remain visible

- GIVEN existing steward session state is stored under `.scion-ops/sessions/<session_id>/`
- WHEN the web UI discovers or displays that state
- THEN the UI continues to read and display the existing state without requiring a directory rename, state migration, branch rename, or session id rewrite.

### Requirement: Holly Coordinator Persona

The system SHALL use Holly as the operator-facing name for the bot or coordinator that conducts actions in human-readable web UI copy.

#### Scenario: Coordinator narrative is rendered

- GIVEN the web UI renders human-readable coordinator prompts, status summaries, handoff text, or action-conducting output
- WHEN the text describes the operator-facing conductor rather than a concrete Scion primitive
- THEN the copy calls that conductor Holly
- AND it does not imply that Holly is a new MCP tool namespace, Kubernetes resource, service, binary, agent type, steward session type, or storage model.

#### Scenario: Coordinator output contains runtime details

- GIVEN Holly-facing output includes steward session ids, agents, templates, broker decisions, MCP payloads, branch refs, Kubernetes resource names, or `.scion-ops` paths
- WHEN those details are rendered inside the output
- THEN the runtime and compatibility identifiers remain unchanged
- AND only the surrounding persona label or narrative uses Holly.

### Requirement: Branding Change Verification

The system SHALL include focused verification for the Holly Ops branding pass when this change is implemented.

#### Scenario: User-facing text audit is performed

- GIVEN implementation updates web UI and operator-facing text
- WHEN verification runs
- THEN checks confirm primary branding uses Holly Ops Drive
- AND product-experience copy uses Holly Ops
- AND coordinator persona copy uses Holly where appropriate.

#### Scenario: Compatibility audit is performed

- GIVEN implementation updates branding copy
- WHEN verification runs
- THEN checks confirm MCP tool names, MCP server identifiers, Kubernetes resources, task/script interfaces, HTTP paths, environment variables, config keys, repository paths, modules, `.scion-ops` state paths, steward session state fields, and branch naming conventions were not renamed accidentally.
