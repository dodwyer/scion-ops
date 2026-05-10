# Proposal: Holly Ops Branding

## Summary

Rename the user-facing product experience from scion-ops to Holly Ops. The browser/operator UI will be called Holly Ops Drive, with HHD allowed as a compact secondary label. The operator-facing bot or coordinator that conducts actions will be called Holly in human-readable copy.

This is a low-risk user-facing rename. Real Scion runtime terminology and compatibility identifiers remain unchanged unless a later migration plan explicitly changes them.

## Motivation

The current product copy exposes `scion-ops` as both a user-facing brand and an implementation identifier. That makes the operator experience feel tied to repository and runtime naming, and it creates ambiguity when copy should describe the product versus actual Scion primitives.

A clear branding contract lets the UI and docs present a cohesive Holly Ops experience while keeping Scion runtime concepts precise. It also prevents accidental breakage of existing MCP clients, Kubernetes deployments, session state, scripts, and environment variables during the first rename pass.

## Scope

In scope:

- User-facing product naming for the web UI, visible page titles, headers, navigation labels, browser metadata, empty states, status copy, and operator-facing documentation.
- Naming the web UI Holly Ops Drive and allowing HHD only as an abbreviation after the full name is established or where compact UI space requires it.
- Referring to the operator-facing action-conducting bot or coordinator as Holly in prompts, status messages, handoffs, and documentation where the text does not name a concrete Scion primitive.
- Preserving precise Scion terminology for real runtime concepts such as Hub, Runtime Broker or broker, agents, MCP, templates, groves, steward sessions, OpenSpec changes, and branches.
- Preserving compatibility identifiers such as Kubernetes resource names, MCP tool names, environment variables, task names, scripts, repository paths, module names, and `.scion-ops` state.

Out of scope:

- Renaming Kubernetes resource names, labels, namespaces, services, service accounts, PVCs, container images, kind cluster names, or deployment manifests.
- Renaming MCP server names, MCP tool names, HTTP paths, Python modules, CLI commands, Taskfile tasks, config keys, or environment variables such as `SCION_OPS_*`.
- Renaming `.scion-ops/` state directories, existing session ids, steward state fields, branch naming conventions, or persisted round artifacts.
- Renaming Scion Hub, Runtime Broker, broker, agents, MCP, templates, groves, steward sessions, or other actual Scion primitives.
- Changing behavior, permissions, authentication, orchestration flow, storage model, source-of-truth rules, or web app read/write capabilities.
- Introducing migrations for existing clusters, checkouts, Hub records, MCP clients, session state, or operator scripts.

## Success Criteria

- Primary user-facing product copy uses Holly Ops.
- The browser UI presents itself as Holly Ops Drive, and HHD is used only as a secondary short form.
- Operator-facing coordinator copy uses Holly while retaining steward session, agent, Hub, broker, MCP, and template terminology where those words name actual runtime primitives.
- UI and docs distinguish user-facing brand names from technical compatibility identifiers.
- Existing `scion_ops_*` MCP tools, `SCION_OPS_*` environment variables, Kubernetes resources, task and script interfaces, branch/session conventions, and `.scion-ops` state paths remain compatible.
- Implementation validation includes a focused user-facing text audit and a compatibility audit that confirms no runtime identifiers were renamed accidentally.
