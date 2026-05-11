# Proposal: Base Framework 1

## Summary

Create a new, additive UI evaluation path for scion-ops that tests a fresh operator interface without replacing or inheriting assumptions from the current UI. The evaluation UI should use TypeScript, React, and Vite for the browser application, served as static assets by a small Python HTTP/API adapter, and run in Kubernetes as a separate Deployment and Service on a distinct port from the existing UI.

The preview should use mocked, schema-faithful data to demonstrate the core operator workflows that will later be wired to real Hub, MCP, Kubernetes, git, and runtime sources.

## Motivation

The next UI direction needs to be evaluated on its own merits instead of being constrained by previous implementation choices, page structure, or visual design. Operators need a clearer way to scan current control-plane state, rounds, inbox activity, runtime health, and diagnostics. At this stage, the key decision is the frontend foundation and deployment shape, not live backend wiring.

TypeScript with React and Vite is the preferred evaluation stack because it gives the UI a typed component model, fast local iteration, a broad ecosystem for complex operator-console interactions, and a simple static build artifact. A small Python adapter keeps compatibility with the repository's existing operational language and deployment practices while avoiding a larger backend commitment during evaluation.

## Scope

In scope:

- Add a new `new-ui-evaluation` capability for a separate preview UI.
- Use TypeScript, React, and Vite for the frontend implementation direction.
- Serve the built frontend through a small Python HTTP/API adapter that also exposes mocked data endpoints.
- Deploy the preview in Kubernetes as a separate pod, Deployment, Service, and port from the existing `scion-ops-web-app`.
- Define mocked, schema-faithful data for overview, rounds, round detail and timeline, inbox and messages, runtime and source health, diagnostics, and raw payload views.
- Mock the core views needed for current operator workflows.
- Preserve the existing UI, its lifecycle, public endpoints, deployment, and operator access path.
- Prohibit live Hub, MCP, Kubernetes, git, model-backed, or state-mutating behavior in the preview UI.

Out of scope:

- Replacing, redesigning, or deprecating the current UI.
- Wiring the preview UI to live Hub, MCP, Kubernetes, git, OpenSpec, or model-backed reads.
- Adding write operations such as round start, retry, abort, delete, archive, git mutation, OpenSpec mutation, or Kubernetes mutation.
- Production authentication, authorization, user personalization, or multi-tenant behavior.
- Committing to React/Vite as the permanent production UI before the evaluation is reviewed.

## Success Criteria

- A Kubernetes pod can run the evaluation UI on a port distinct from the existing UI.
- Operators can open the preview and inspect mocked overview, rounds, round detail, inbox, runtime/source health, and diagnostics views.
- The mock data contract is explicit enough that later backend wiring can replace fixtures without redesigning view data shapes.
- The existing UI continues to run and be operated independently.
- The implementation language and framework decision is documented with tradeoffs and a clear reason for choosing TypeScript, React, Vite, and a Python adapter.
- The preview UI performs only fixture reads and local static/API serving during evaluation.
