# Proposal: Build Web App Hub

## Summary

Create a web application hub for observing scion-ops progress and updates without requiring operators or reviewers to use the CLI or MCP client directly. The hub presents active and recent consensus, spec, and implementation rounds; shows per-agent state; streams round updates; surfaces terminal results and blockers; and links to artifacts such as branches, logs, and OpenSpec output.

## Motivation

scion-ops already exposes round state through Hub and MCP affordances, including hub status, agent lists, round status, round events, watch cursors, artifacts, project/spec status, and start/abort round operations. Maintainers and reviewers need a productized web surface that turns those backend records into an operational view: what is running, what changed, what is blocked, and where the resulting artifacts are.

## Goals

- Provide a browser-based interface for repo maintainers, operators, and reviewers to inspect scion-ops round progress.
- Center the experience on consensus/spec/implementation rounds and their current state.
- Use a dedicated read-only web API facade backed by Hub/MCP-derived APIs as the source of truth rather than scraping Kubernetes pods or terminal logs directly.
- Support live progress following through polling, long-poll, or equivalent event watching.
- Make terminal state, blockers, validation status, and artifact links obvious from the round detail view.
- Scope the first release to one configured project/grove and a bounded recent-round window.
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
- API contract expectations for a dedicated web facade that consumes existing scion-ops state primitives.
- Explicit UX behavior for live updates, empty/error states, terminal outcomes, and blockers.
- Kubernetes-compatible packaging and operation requirements for the web app.
- Implementation tasks that can be executed after spec approval.

Out of scope for the initial implementation:

- Mutating controls for starting, aborting, or resuming rounds.
- Direct pod log scraping.
- Retention policy changes to Hub storage.
- Public internet deployment and authentication policy beyond preserving existing Hub/MCP authentication expectations.
- Multi-project browsing in the initial release.

## Decisions

- The initial implementation SHALL expose a dedicated read-only web API facade for the browser. The facade may call Hub HTTP or MCP internally, but browser code must consume the facade contract.
- The first release SHALL observe a single configured project/grove identity. A project selector is out of scope until a later change defines multi-project discovery and authorization.
- The dashboard SHALL show active rounds plus a bounded completed-round window. The default display window is the most recent 50 completed rounds or 14 days, whichever is smaller, unless implementation configuration narrows it.
- Artifact destinations SHALL be rendered only when supplied by the facade or backend as stable link targets. The UI must not invent URLs for branches, OpenSpec paths, Hub records, transcripts, logs, or local-only paths.
- The web app SHALL be packaged for the repo's Kubernetes-based operating model, with configuration supplied through the deployment environment and service discovery rather than ad hoc local runtime scripts.
