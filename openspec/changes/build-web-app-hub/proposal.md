# Proposal: Build Web App Hub

## Summary

Add a browser-based operator interface for scion-ops progress and updates. The hub will give operators a single place to inspect Scion Hub-backed runtime state, Kubernetes readiness, active and historical agent rounds, inbox and notification updates, and high-level status signals without switching between CLI commands.

## Motivation

scion-ops currently exposes operational state through CLI tools, MCP tools, Hub APIs, Kubernetes inspection, and round messages. That is powerful but fragmented for day-to-day monitoring. Operators need a focused web surface that reflects the same source-of-truth runtime state and makes round progress, readiness, and actionable updates visible at a glance.

## Scope

In scope:

- A web interface for the local scion-ops control plane.
- Read-only dashboards for Hub health, Runtime Broker availability, Kubernetes deployment and pod readiness, and MCP reachability.
- Round views showing Scion agent rounds, current phase/status, involved agents, branch names when available, recent progress, and terminal outcome.
- Inbox and notification views backed by Hub message and notification state.
- Refresh behavior that keeps the interface current without requiring manual CLI polling.
- Empty, loading, stale, degraded, and error states that make operational status clear.
- Implementation planning that preserves Hub, Kubernetes, and existing scion-ops workflows as the source of truth.

Out of scope for this change:

- Starting, aborting, retrying, or mutating rounds from the web interface.
- Changing Kubernetes manifests, runtime scripts, task commands, or product documentation during this spec round.
- Replacing the existing CLI, MCP, or Hub APIs.
- Adding authentication, multi-user roles, or hosted production deployment beyond the existing local control-plane assumptions.

## Success Criteria

- Operators can open the web app and see whether scion-ops is ready to run rounds.
- Operators can identify active rounds, completed rounds, blocked rounds, and the latest meaningful update for each round.
- Operators can inspect round messages, inbox items, and notifications without using `scion messages` or MCP calls directly.
- Runtime state shown in the app is derived from existing Hub, Kubernetes, and MCP surfaces rather than duplicated static state.
- The implementation can be delivered incrementally without introducing write operations or speculative orchestration paths.

## Unresolved Questions

No material implementation blockers are known for this spec. Implementation may still choose the concrete frontend framework and backend adapter shape based on the existing repository standards at that time.
