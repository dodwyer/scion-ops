# Design: Update Web App

## Overview

The update should extend the web app hub as a read-only operational console. It should surface normalized lifecycle and diagnostic fields that already exist in Hub, MCP, Kubernetes, git, verification, and round-state outputs, while avoiding any UI affordance that implies the browser can change round state.

## Data Model

The backend adapter should expose browser-friendly fields for:

- Round lifecycle phase, status, terminal outcome, current owner, and next expected action when available.
- Branch and commit provenance for spec author, implementation agents, reviewers, integrators, final reviewers, and archived changes.
- Canonical verification commands, observed results, skipped checks, caveats, and timestamps from integration or final-review handoff state.
- Final-review failure classification, repair route, final repair budget usage, route history, and escalation reason when present.
- Source freshness and error metadata for Hub, Runtime Broker, MCP, Kubernetes, local git state, and verification helpers.

Structured fields from Hub, MCP, normalized round snapshots, handoff payloads, and review outcomes are authoritative. Text-derived values may be displayed only as fallback-derived data and should be labeled or ordered so they do not override structured provenance.

## User Experience

The round list should support fast operational scanning:

- Filter by lifecycle phase, status, final-review verdict, owner, and degraded source when the backing data supports those dimensions.
- Sort by last update, creation time, phase, outcome, or severity.
- Preserve selected filters and selected round ids in the URL so shared links reproduce the same read-only view.
- Keep empty, loading, stale, and unavailable-source states distinct.

Round detail should add focused panels for:

- Lifecycle summary with phase, owner, next action, blockers, and latest update.
- Provenance with branch and commit identifiers grouped by role.
- Verification handoff with canonical commands and observed results.
- Final-review repair with classification, route, budget, history, and current disposition.
- Source diagnostics showing which backing systems contributed data and which failed.

The runtime view should continue to show readiness checks, but should add clearer correlation between degraded dependencies and affected round behavior.

## Read-Only Constraints

The web app must not expose controls or endpoints that mutate scion-ops state. Refreshing, filtering, sorting, opening details, copying identifiers, and following local links are allowed. Starting rounds, aborting rounds, retrying agents, applying repair routes, writing Hub records, modifying Kubernetes resources, or changing git branches from the app remain prohibited.

## Error Handling

Source failures should be represented independently. A Kubernetes failure must not hide Hub messages; a Hub auth failure must not hide local git diagnostics; a verification-command failure must not be collapsed into a generic round failure when structured error categories are available.

When data is stale, the app should show the last successful source timestamp and the failed refresh timestamp if available. Unknown fields should remain visibly unknown rather than being guessed from unrelated text.

## Verification Strategy

Implementation should include fixture or unit coverage proving:

- Lifecycle phase, owner, branch, commit, verification, and final-review repair fields render from structured data.
- Text-derived fallbacks do not override structured branch, commit, verdict, or classification fields.
- Filters, sorts, and URL state select the expected rounds without mutating backing data.
- Partial-source failures preserve available data and expose source-specific error categories.
- Normal app loading and refresh do not call round-starting, repair, retry, abort, archive, Kubernetes write, Hub write, or git mutation paths.
