# Proposal: Holly Ops Branding

## Summary

Rename the operator-facing product experience from scion-ops to Holly Ops. The browser UI should present itself as Holly Ops Drive, with HHD as the short display name, and the operator-facing bot/coordinator should be called Holly in user-visible copy.

This is a low-risk user-facing rename only. Runtime identifiers and compatibility surfaces that represent real Scion primitives or persisted infrastructure stay unchanged unless a later migration is explicitly specified.

## Motivation

Operators currently see scion-ops as both the product experience name and as part of real runtime, repository, MCP, Kubernetes, and session identifiers. The requested brand separates those concerns: Holly Ops is the user-facing product name, Holly Ops Drive is the web UI, and Holly is the operator-facing coordinator persona.

Keeping runtime identifiers stable avoids unnecessary migration risk for local kind environments, MCP clients, branch and session state, templates, and existing automation.

## Scope

In scope:

- Update user-facing web UI copy so the product experience is called Holly Ops.
- Update browser UI title, primary app chrome, empty states, status copy, and operator documentation references so the web UI is called Holly Ops Drive or HHD where short copy is needed.
- Update operator-facing coordinator copy so the acting bot/coordinator is called Holly.
- Preserve real Scion primitive terminology such as Hub, Runtime Broker, agents, MCP, templates, steward sessions, rounds, and OpenSpec.
- Preserve current runtime identifiers and compatibility paths.

Out of scope:

- Renaming MCP server identity, MCP tool names, MCP resources, or MCP protocol fields.
- Renaming Kubernetes resource names, labels used for selectors, kind cluster names, namespaces, services, deployments, or container images.
- Renaming `.scion-ops` session directories or persisted state paths.
- Renaming branch names, template names, kind names, Scion Hub primitives, broker identifiers, agent identifiers, or steward-session protocol fields.
- Migrating package/module names, environment variable names, or CLI command names unless they are strictly display-only aliases.

## Success Criteria

- Operators opening the web UI see Holly Ops Drive as the app name and can recognize HHD as its short name.
- User-facing coordinator/bot copy refers to Holly without changing underlying coordinator identifiers or stored agent records.
- Existing MCP clients, Kubernetes workflows, `.scion-ops` session state, kind control-plane resources, and Scion runtime terminology remain compatible.
- Tests or focused review cover representative UI/documentation copy and guard against accidental renames of compatibility-sensitive identifiers.
