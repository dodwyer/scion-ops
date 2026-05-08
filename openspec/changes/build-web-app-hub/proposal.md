# Proposal: Build Web App Hub

## Summary

Create a web application hub for observing scion-ops progress and updates without requiring operators or reviewers to use the CLI or MCP client directly. The hub presents active and recent consensus, spec, and implementation rounds; shows per-agent state; streams round updates; surfaces terminal results and blockers; and links to artifacts such as branches, logs, and OpenSpec output.

## Motivation

scion-ops already exposes round state through Hub and MCP affordances, including hub status, agent lists, round status, round events, watch cursors, artifacts, project/spec status, and start/abort round operations. Maintainers and reviewers need a productized web surface that turns those backend records into an operational view: what is running, what changed, what is blocked, and where the resulting artifacts are.

## Goals

- Provide a browser-based interface for repo maintainers, operators, and reviewers to inspect scion-ops round progress.
- Center the experience on consensus/spec/implementation rounds and their current state.
- Use Hub or MCP-derived APIs as the source of truth rather than scraping Kubernetes pods or terminal logs directly.
- Support live progress following through polling, long-poll, or equivalent event watching.
- Make terminal state, blockers, validation status, and artifact links obvious from the round detail view.
- Keep destructive or workflow-changing controls out of the default scope unless explicitly enabled by a later implementation decision.

## Non-Goals

- Implementing the web app in this change.
- Adding Kubernetes manifests, runtime scripts, tests, or frontend package scaffolding in this change.
- Defining a new source of truth for round state separate from Hub/MCP.
- Exposing start, abort, or resume controls by default.
- Providing a multi-tenant authorization system in this specification.

## Scope

In scope:

- A read-focused web hub with dashboard, round detail, agent state, event feed, artifact links, and backend connectivity states.
- API contract expectations for consuming the existing scion-ops state primitives.
- Explicit UX behavior for live updates, empty/error states, terminal outcomes, and blockers.
- Implementation tasks that can be executed after spec approval.

Out of scope for the initial implementation:

- Mutating controls for starting, aborting, or resuming rounds.
- Direct pod log scraping.
- Retention policy changes to Hub storage.
- Public internet deployment and authentication policy beyond preserving existing Hub/MCP authentication expectations.

## Open Questions

- Should the initial implementation consume Hub HTTP APIs directly, call the MCP server from a thin backend, or expose a dedicated web API that normalizes MCP-derived summaries?
- Is the first release scoped to one configured project/grove, or should the UI include a project selector?
- What retention window should be shown for completed rounds if Hub exposes more history than the UI can comfortably render?
- Which artifact URL forms are stable enough to deep-link in the first release: GitHub branches, OpenSpec change paths, Hub records, terminal transcript endpoints, or local-only paths?
