# Proposal: Holly Ops Branding

## Summary

Rename the user-facing product experience from scion-ops to Holly Ops. The web UI should present itself as Holly Ops Drive, with HHD as the approved short form, and operator-facing references to the action-conducting bot or coordinator should use Holly.

This is a low-risk branding change. It preserves Scion runtime terminology and compatibility identifiers where those names refer to real primitives, APIs, resource names, session paths, or deployment contracts.

## Motivation

Operators currently see the repository/runtime name, scion-ops, in places that describe the product experience. That makes the human-facing interface feel like an internal implementation name rather than a branded operations experience.

The rename should make the product identity clear without obscuring the underlying Scion model. Hub, broker, agents, MCP, templates, steward sessions, branches, rounds, OpenSpec validation, and Kubernetes diagnostics remain accurate operational terms.

## Scope

In scope:

- Present the web UI as Holly Ops Drive and allow HHD as its short label.
- Present the overall product experience as Holly Ops in README and operator documentation prose.
- Use Holly for operator-facing references to the bot or coordinator that conducts actions.
- Update browser-visible titles, headers, and human-readable descriptions that currently expose scion-ops as the product name.
- Update documentation prose while preserving command examples and compatibility identifiers.
- Update focused tests or checks that assert visible product labels.

Out of scope:

- Renaming Kubernetes resources, namespaces, services, deployments, labels, selectors, ServiceAccounts, images, or default kind cluster/context names.
- Renaming MCP tools, Python modules, package paths, env vars, CLI flags, or JSON fields that existing clients use.
- Renaming `.scion-ops` session state paths or existing durable session artifacts.
- Replacing Scion runtime terms such as Hub, broker, agents, MCP, templates, steward sessions, branches, rounds, or OpenSpec.
- Adding a migration for existing clusters, client configurations, or session state.
- Implementing product code as part of this OpenSpec-only change.

## Success Criteria

- Operators see Holly Ops Drive or HHD as the web UI identity instead of scion-ops hub.
- Operator-facing product prose introduces Holly Ops while retaining accurate Scion runtime terminology.
- Human-facing references to the action-conducting bot/coordinator use Holly where doing so does not rename protocol roles or durable state fields.
- Existing Kubernetes resource names, MCP tool names, env vars, image names, `.scion-ops` paths, and Scion primitive names remain compatible.
- OpenSpec validation passes for this change.
