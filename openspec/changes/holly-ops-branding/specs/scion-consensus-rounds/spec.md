# Delta: Scion Consensus Rounds

## ADDED Requirements

### Requirement: Holly Coordinator Naming

The system SHALL use Holly as the operator-facing name for the coordinator persona while preserving Scion consensus-round runtime terminology.

#### Scenario: Coordinator action is described to an operator

- GIVEN a prompt, status message, handoff, round summary, or operator-facing documentation describes the bot or coordinator conducting actions
- WHEN the text is human-readable persona copy rather than a literal runtime identifier
- THEN the text calls the conductor Holly
- AND it does not introduce Holly as a new service, binary, Kubernetes controller, MCP namespace, tool name, agent type, template, storage model, or durable session primitive.

#### Scenario: Consensus round primitives are referenced

- GIVEN the same text references Scion Hub, Runtime Broker or broker, agents, MCP, templates, groves, OpenSpec changes, branches, steward sessions, session ids, state fields, or persisted round artifacts
- WHEN those names identify actual Scion primitives or compatibility identifiers
- THEN the existing Scion runtime terminology remains unchanged
- AND the text may phrase the relationship as Holly conducting or coordinating those existing primitives.

#### Scenario: Persisted round compatibility is required

- GIVEN existing consensus-round state, branches, and artifacts use `scion-ops`, `.scion-ops`, steward session ids, or established state field names
- WHEN Holly-facing copy is updated
- THEN the persisted identifiers remain compatible
- AND no state migration, branch rename, MCP tool rename, environment variable rename, or Kubernetes resource rename is required by this branding change.
