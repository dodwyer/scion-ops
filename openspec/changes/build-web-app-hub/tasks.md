# Build Web App Hub Tasks

## Specification

- [x] Capture the read-first operator hub scope and explicit non-goals.
- [x] Define the initial UI workflows for control-plane overview, round list, and round drilldown.
- [x] Identify unresolved decisions that block safe implementation.
- [x] Add delta requirements for the web app hub capability.
- [x] Validate the OpenSpec change artifacts.

## Implementation Readiness Blockers

- [ ] Decide app placement/local kind hosting: existing Hub web surface, separate scion-ops web service, or MCP-hosted facade; include Kubernetes object ownership, service/port exposure, build artifact ownership, and Hub/MCP reachability.
- [ ] Decide browser authentication/session handling for local operators and read-only reviewers; include server-side read-only enforcement, secret containment, and local access assumptions.
- [ ] Decide the canonical browser API boundary and schema ownership; include Hub HTTP vs MCP-backed vs hybrid facade, endpoint ownership, versioning, read-only allowlist, error envelope, and partial-source behavior.
- [ ] Decide exact Hub/MCP field mapping to canonical UI lifecycle statuses; include raw status, terminal state, validation, agent health, blockers/warnings, timeouts, source reachability, freshness, and conflict precedence.
- [ ] Decide the live update mechanism and default refresh/staleness behavior; include transport, list/drilldown interval or heartbeat, stale threshold, event cursor/resume semantics, and backoff limits.
- [ ] Decide retention/history behavior for recent/completed rounds that are no longer observable from Hub state; include source, time/count window, and unavailable-history UI behavior.
- [ ] Decide the artifact link contract for branches, files, validation output, PR-ready references, and facade-served artifacts; include display label, copy value, click target, auth behavior, and missing-target behavior.
- [ ] Decide whether start/abort/retry/archive controls belong in a later change and what confirmation/authorization model they require; keep MVP UI and browser API read-only until approved.

## Future Implementation Tasks

- [ ] Start implementation only after all implementation readiness blockers are resolved in accepted OpenSpec artifacts.
- [ ] Implement the browser-safe read facade over canonical Hub/MCP state.
- [ ] Implement the operator hub first screen with control-plane health, filters, round summaries, and copy actions.
- [ ] Implement round drilldown with progress lines, agents, events, blockers, validation, artifacts, final verdict, and next action.
- [ ] Add tests for facade schema normalization, status mapping, stale data handling, and read-only authorization.
- [ ] Package the web app through the selected Kubernetes deployment path without manual resource patches.
