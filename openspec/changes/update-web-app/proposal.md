# Proposal: Update Web App

## Summary

Enhance the read-only scion-ops web app hub with deeper operator diagnostics for round execution, configuration provenance, final-review remediation, and degraded runtime dependencies. The update keeps the web app read-only while making it easier to understand why a round is waiting, blocked, or ready for operator attention.

## Motivation

The initial web app hub gives operators a consolidated view of readiness, rounds, messages, notifications, and runtime state. As rounds move through spec authoring, implementation, integration, and final review, operators also need clearer visibility into phase-specific blockers, branch and commit provenance, canonical verification evidence, and final-review repair routing. Without those details, operators still have to fall back to CLI output or raw messages to understand the next action.

This change specifies an incremental update that improves the app as an operational read model without introducing web-based mutations or a competing state store.

## Scope

In scope:

- A round lifecycle view that distinguishes spec authoring, implementation, peer review, integration, final review, repair, archived, and blocked phases when backing state exposes them.
- Configuration and provenance panels showing active grove/project settings, branch names, commit identifiers, source timestamps, and data-source freshness.
- Final-review and repair-loop visibility, including failure classification, handoff evidence, repair budget state, route history, and current owner when available.
- Stronger degraded-state diagnostics for Hub, Runtime Broker, MCP, Kubernetes, git checkout state, and verification-command failures.
- Filtering, sorting, and persistent URL state for operational round lists without persisting independent round data.
- Tests and fixtures covering the updated read-only rendering and normalization behavior.

Out of scope:

- Starting, aborting, retrying, repairing, approving, archiving, or otherwise mutating rounds from the web app.
- Changing orchestration behavior, Kubernetes manifests, Hub APIs, MCP tools, or runtime scripts except for read-only adapter support required by implementation.
- Adding authentication, multi-user permissions, hosted deployment, or production hardening beyond the existing local control-plane model.
- Replacing CLI or MCP workflows.

## Success Criteria

- Operators can identify the current lifecycle phase and next responsible owner for active and recent rounds when that data is available.
- Operators can inspect branch, commit, verification, and final-review repair details without parsing raw message bodies.
- Degraded runtime or verification states preserve partial data and show source-specific causes.
- Updated views remain read-only and do not start, stop, retry, repair, or mutate rounds during normal loading or refresh.
- Implementation can be validated with fixture coverage for healthy, blocked, final-review repair, stale, and unavailable-source states.

## Unresolved Questions

- The implementation may choose whether filters are encoded only in the URL or also mirrored in browser-local preferences; either choice must not persist round state.
- The exact visual grouping of lifecycle phases can follow the existing app layout as long as the required phase, owner, and blocker details remain visible.
