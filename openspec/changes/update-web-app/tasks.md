# Tasks

- [ ] 1.1 Confirm the existing web app hub entry points and adapter boundaries for adding read-only lifecycle diagnostics.
- [ ] 1.2 Extend backend normalization to expose lifecycle phase, owner, blocker, branch, commit, verification handoff, final-review repair, source freshness, and source error fields.
- [ ] 1.3 Update the round list with phase/status/verdict/owner/source filters, severity-aware sorting, and URL-preserved selection state.
- [ ] 1.4 Update round detail with lifecycle, provenance, verification handoff, final-review repair, and source diagnostics panels.
- [ ] 1.5 Update runtime diagnostics to correlate degraded Hub, Runtime Broker, MCP, Kubernetes, git, and verification sources with affected round behavior.
- [ ] 1.6 Preserve read-only behavior by ensuring app load, refresh, filtering, sorting, and detail navigation do not invoke round mutation, Hub write, Kubernetes write, or git mutation paths.
- [ ] 1.7 Add focused fixtures or tests for healthy lifecycle data, blocked rounds, final-review repair state, structured provenance precedence, stale data, unavailable sources, filters, sorts, and URL state.
- [ ] 1.8 Verify the change with the repository's OpenSpec validator and the standard web app hub checks selected during implementation.
