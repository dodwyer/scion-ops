# Build Web App Hub Tasks

## Specification

- [x] Capture the read-first operator hub scope and explicit non-goals.
- [x] Define the initial UI workflows for control-plane overview, round list, and round drilldown.
- [x] Identify unresolved decisions that block safe implementation.
- [x] Add delta requirements for the web app hub capability.
- [x] Validate the OpenSpec change artifacts.

## Implementation Readiness Blockers

- [ ] Decide app placement: existing Hub web surface, separate scion-ops web service, or MCP-hosted facade.
- [ ] Decide browser authentication/session handling for local operators and read-only reviewers.
- [ ] Decide the canonical browser API boundary and schema ownership.
- [ ] Decide the live update mechanism and default refresh/staleness behavior.
- [ ] Decide retention behavior for recent/completed rounds that are no longer observable from Hub state.
- [ ] Decide the artifact link contract for branches, files, validation output, and PR-ready references.
- [ ] Decide whether start/abort/retry/archive controls belong in a later change and what confirmation/authorization model they require.

## Future Implementation Tasks

- [ ] Implement the browser-safe read facade over canonical Hub/MCP state.
- [ ] Implement the operator hub first screen with control-plane health, filters, round summaries, and copy actions.
- [ ] Implement round drilldown with progress lines, agents, events, blockers, validation, artifacts, final verdict, and next action.
- [ ] Add tests for facade schema normalization, status mapping, stale data handling, and read-only authorization.
- [ ] Package the web app through the selected Kubernetes deployment path without manual resource patches.
