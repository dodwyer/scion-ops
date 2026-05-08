# Build Web App Hub

## Summary

Build an operator-facing web app hub for scion-ops progress and updates. The hub gives local operators and read-only reviewers a browser interface for Scion/OpenSpec rounds without requiring them to poll the CLI, MCP tools, Kubernetes logs, or Hub internals directly.

## Motivation

scion-ops already exposes useful operational state through the kind-hosted Scion Hub and MCP tools, including Hub health, agent lists, round status, event streams, OpenSpec validation state, progress lines, blockers, artifacts, and PR-ready branches. That state is currently optimized for automation and terminal workflows. Operators need a consolidated UI that answers:

- Is the control plane healthy enough to run or monitor rounds?
- Which rounds are active, completed, blocked, or degraded?
- What changed most recently in a round?
- Which agent, validation, or artifact condition requires attention?
- What branch, round ID, or next action should be copied into the next workflow?

## Scope

In scope:

- A read-first web app experience for local kind scion-ops operators and read-only reviewers.
- Control-plane overview for Hub, broker, MCP/API reachability, providers, grove context, and agent health.
- Active and recent round lists with status, health, project, change, base branch, PR-ready branch, validation state, agent counts, blockers, and updated time.
- Round drilldown for progress lines, agent states, latest messages/notifications/events, blockers, artifacts, terminal outcome, and final verdict.
- Filters by project, change, round ID, status, and health.
- Copy actions for round IDs, branch names, project roots, change IDs, and artifact references.
- Clear next-action presentation when a round is blocked, completed, timed out, or still running.
- A data-source contract that treats existing Hub/MCP state as canonical and avoids duplicating operational truth in the browser.

Out of scope for this change:

- Implementing the frontend, API, Kubernetes manifests, scripts, tests, or product documentation.
- Start, abort, retry, archive, or other mutating controls until explicitly approved.
- Replacing the Hub, broker, MCP server, OpenSpec validator, or Kubernetes runtime.
- Long-term analytics, cross-cluster federation, or multi-tenant SaaS operation.

## Decisions And Constraints

- The MVP is read-first. Mutating controls are a blocker until separately approved because they affect active agent processes and state-driven operations.
- The app must derive status from canonical scion-ops sources rather than scraping Kubernetes logs or maintaining an independent round database.
- The app should prefer an HTTP-accessible facade/API backed by Hub/MCP data over browser-direct MCP calls if that keeps browser concerns, authentication, and schema normalization contained.
- Kubernetes convergence remains the operating model for deployment when implementation begins; no manual resource patches or ad hoc runtime scripts should be required.
- Implementation readiness depends on resolving app placement, auth/session handling, live update transport, retention source, artifact link contract, and canonical round statuses.

## Success Criteria

- An operator can open one web page and understand control-plane health and the current round queue.
- A reviewer can inspect a round drilldown and see progress, blockers, validation status, artifacts, final verdict, and the PR-ready branch without CLI access.
- Displayed status is traceable to existing Hub/MCP fields and does not create a second source of truth.
- The design clearly separates read-only MVP behavior from future mutating actions.
