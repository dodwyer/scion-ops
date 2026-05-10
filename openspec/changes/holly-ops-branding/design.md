# Design: Holly Ops Branding

## Overview

Holly Ops is the user-facing product name. Holly Ops Drive is the web UI name. HHD is a short form for Holly Ops Drive in compact labels after the full name has been established. Holly is the user-facing name for the action-conducting bot or coordinator.

The rename is intentionally not a runtime migration. Scion remains the underlying runtime, and actual Scion primitives keep their existing names. Compatibility identifiers also remain stable so existing deployments, MCP clients, scripts, and steward session state continue to work.

## Naming Model

Use Holly Ops for the product or operator experience as a whole. Examples include introduction text, product descriptions, release notes, and general operator-facing documentation.

Use Holly Ops Drive for the browser UI and primary web app chrome. Examples include the document title, top-level heading, main navigation identity, and startup or listening messages where they are meant for humans. Use HHD only where a compact label is necessary, such as a small nav mark or abbreviated status heading, and only when surrounding context already establishes the full name.

Use Holly for the operator-facing coordinator persona in human-readable text. Examples include coordinator status copy, prompts, handoff descriptions, and messages that describe the entity conducting actions for the operator. Holly is not a new service, binary, MCP namespace, Kubernetes controller, storage model, agent type, or Scion primitive.

Use Scion terminology when text names real runtime concepts. The UI and docs should keep names such as Scion Hub, Runtime Broker or broker, agents, MCP, templates, groves, steward sessions, OpenSpec changes, and branches when those concepts are the actual source, object, or protocol being shown.

## Compatibility Boundaries

The first branding pass must preserve existing technical identifiers. These names may still appear in user-visible diagnostics, commands, paths, and compatibility notes when the exact identifier matters:

- `scion_ops_*` MCP tool names and result contracts;
- MCP server names and tool namespaces that currently use `scion-ops` or `scion_ops`;
- `SCION_OPS_*` environment variables and existing config keys;
- Kubernetes resources, labels, services, namespaces, service accounts, PVCs, image tags, and kind contexts that currently use `scion-ops`;
- task names, scripts, CLI commands, HTTP routes, Python modules, package names, and repository paths;
- `.scion-ops/sessions/<session_id>/` durable state, state JSON fields, existing steward session ids, and round branch naming conventions.

When documentation or UI diagnostics need to mention these identifiers, they should be presented as commands, paths, resource names, compatibility details, or implementation identifiers rather than as the user-facing brand.

## Web UI Guidance

Holly Ops Drive should be the primary brand shown by the web app. Existing operational labels should remain precise: Hub, MCP State, Runtime, broker, agents, templates, steward sessions, branch refs, Kubernetes resource names, and source errors should not be softened into brand copy when they identify actual runtime data.

Coordinator-facing UI labels can use Holly where the label describes the human-facing conductor. For example, generic coordinator output may become Holly output when the content is the operator-facing coordinator narrative. If the same surface is showing a steward session id, agent role, broker decision, or MCP payload, the runtime label should remain.

The rename must not alter the web app source-of-truth behavior. The app remains a monitor over Hub, MCP, Kubernetes, OpenSpec, branch, validation, and steward session state.

## Documentation Guidance

Documentation can say that Holly Ops is powered by the Scion runtime. It should keep literal commands and identifiers unchanged so operators can still copy and run them. For example, docs may introduce Holly Ops Drive and then show existing `scion_ops_*` MCP tools, `.scion-ops/sessions/...` paths, and `SCION_OPS_*` environment variables as compatibility identifiers.

Avoid replacing every occurrence of Scion or scion-ops mechanically. Replace product-experience prose, but retain literal technical strings, code examples, manifests, config names, file paths, and runtime primitive names.

## Verification Strategy

Implementation should use no-spend checks:

- a focused text audit for visible web UI and operator-facing documentation copy;
- static or fixture tests for the web UI title, primary heading, compact HHD usage, and Holly coordinator labels;
- compatibility checks confirming MCP tool names, environment variables, Kubernetes resources, task names, script interfaces, `.scion-ops` state paths, and steward session branch conventions remain unchanged;
- existing web app tests to confirm the branding pass does not change monitoring behavior or source-of-truth semantics.
