# Design: Holly Ops Branding

## Overview

The implementation should treat Holly Ops as a display-layer brand, not a runtime migration. The web app remains the read-only browser surface over Scion Hub, Runtime Broker, MCP, Kubernetes, OpenSpec, and steward-session state, but the operator-facing experience should no longer present `scion-ops hub` as the product name.

## Naming Model

Display names:

- Product experience: `Holly Ops`
- Web UI: `Holly Ops Drive`
- Web UI short name: `HHD`
- Operator-facing bot/coordinator persona: `Holly`

Preserved runtime names:

- Scion primitives: Hub, Runtime Broker, agents, MCP, templates, steward sessions, rounds, OpenSpec
- MCP server identity, tool names, resource URIs, result field names, and protocol semantics
- Kubernetes resource names and kind cluster/resource conventions
- `.scion-ops` paths and persisted session state
- Branch names, template names, kind names, environment variables, package/module names, and CLI command names unless a specific item is clearly display-only

## Web UI Copy

The web UI should update visible product chrome and browser metadata to use Holly Ops Drive. This includes the document title, main heading, navigation labels where they name the app, read-only error messages, startup log messages intended for operators, and empty/degraded copy that currently describes the browser surface as the scion-ops hub.

HHD may be used where constrained UI space benefits from a short label, but the first prominent app identity should use Holly Ops Drive. Views that describe backing systems should continue to use Scion names when referring to actual runtime sources, for example Scion Hub readiness, MCP status, broker registration, agent state, and steward-session evidence.

## Coordinator Copy

Operator-facing copy that describes the action-taking coordinator or bot should call it Holly. This should be limited to display text such as headings, labels, summaries, and operator help text.

Structured data, source identifiers, agent records, log-derived fields, MCP fields, and status payloads that use `coordinator` as a runtime role should remain unchanged. The UI may render a display label of Holly for those records while preserving the source role for diagnostics.

## Compatibility Boundaries

The implementation should avoid broad search-and-replace changes. Strings must be evaluated by role:

- Display copy naming the product or web UI should change to Holly Ops, Holly Ops Drive, or HHD.
- Display copy naming the operator-facing coordinator persona should change to Holly.
- Runtime identifiers and compatibility contracts should stay as-is.
- Documentation should distinguish display names from preserved implementation names where both appear.

No migration is required for existing state. Any future change that renames MCP tools, Kubernetes resources, `.scion-ops` paths, branch conventions, or Scion primitive names should be proposed separately with an explicit migration plan.

## Verification Strategy

Verification should include focused checks that the user-visible web app name changed and that compatibility-sensitive identifiers did not change. Suitable checks include:

- Web app fixture or snapshot tests for title, heading, and coordinator display labels.
- Static review or tests for startup/operator-facing copy where the app name is emitted.
- Existing MCP, web app, and kind manifest tests to confirm tool names, resource names, and `.scion-ops` paths remain stable.
- OpenSpec validation for this change artifact.
