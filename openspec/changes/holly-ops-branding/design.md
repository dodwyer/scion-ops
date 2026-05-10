# Design: Holly Ops Branding

## Overview

This change defines a branding layer for the existing Scion operations experience. The product name is Holly Ops. The web UI name is Holly Ops Drive, and HHD is the short form to use where space is constrained. The operator-facing assistant that conducts actions is Holly.

The rename is intentionally limited to text that humans read as product or persona copy. Runtime identifiers and protocol names remain unchanged unless a future migration explicitly changes them.

## Naming Rules

Use Holly Ops for the overall product experience:

- README title and introductory prose;
- documentation prose that describes the operator experience;
- non-protocol descriptions of the system as a product.

Use Holly Ops Drive for the web UI:

- browser title and visible app header;
- page-level descriptions of the read-only operations console;
- tests or fixtures that assert the UI identity.

Use HHD as the approved abbreviation:

- compact UI copy where the full name would be too long;
- documentation after first spelling out Holly Ops Drive.

Use Holly for the operator-facing bot/coordinator:

- user-facing prose that refers to the assistant conducting actions;
- visible labels that describe coordinator output when the label is clearly persona-oriented.

Do not replace Scion terms that refer to actual runtime primitives. Hub, broker, agents, MCP, templates, steward sessions, rounds, branches, OpenSpec, final review, and Kubernetes diagnostics should remain named as such.

## Compatibility Boundary

The following identifiers stay unchanged in this first pass:

- Kubernetes resources such as `scion-ops-web-app`, `scion-ops-mcp`, RBAC subjects, services, deployments, labels, selectors, and PVC references;
- default kind names such as `scion-ops` and `kind-scion-ops`;
- image names such as `localhost/scion-ops-mcp:latest`;
- env vars such as `SCION_OPS_ROOT`, `SCION_OPS_MCP_*`, and `SCION_OPS_HUB_ENDPOINT`;
- MCP tool names such as `scion_ops_round_status`;
- Python module names, filenames, package paths, and CLI flags that existing scripts or clients reference;
- `.scion-ops` session state directories and recorded artifacts.

Documentation may mention these unchanged identifiers in command examples and compatibility notes. Those occurrences should not be treated as stale branding.

## Implementation Guidance

The web app should change visible product strings without changing its read-only JSON contract or backing source names. Source labels such as Hub, MCP, Kubernetes, broker, and web_app remain diagnostic terms.

Documentation updates should avoid global search-and-replace. The implementation should distinguish product prose from compatibility identifiers. Command blocks, paths, tool names, env vars, branch names, Kubernetes manifests, and state directories should be preserved unless they are clearly explanatory prose rather than executable identifiers.

MCP server human-readable instructions may refer to Holly Ops or Holly, but MCP tool names and the `scion_ops` module remain stable. If a client-facing server display name is changed, matching client configuration examples should be updated in the same implementation round and called out as a compatibility-sensitive visible-name change.

Agent template and steward prompt text should be changed only where the text is plainly operator-facing branding. Prompt protocol words such as coordinator, steward, agent, template, specialist, and review should remain if they define Scion behavior.

## Verification Strategy

Implementation should include no-spend validation:

- OpenSpec validation for this change;
- focused web app tests or fixture checks that assert Holly Ops Drive/HHD appears in visible UI identity;
- targeted searches confirming `scion-ops hub` no longer appears as browser-visible product copy;
- targeted searches confirming compatibility identifiers such as `scion-ops-web-app`, `scion_ops_*`, `SCION_OPS_*`, and `.scion-ops` remain available;
- documentation review for command blocks and paths that must retain old compatibility identifiers.
