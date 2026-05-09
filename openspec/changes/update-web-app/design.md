# Design: Update Web App Hub With OpenSpec Change Visibility

## Overview

This change layers a small OpenSpec changes view onto the existing read-only `scripts/web_app_hub.py` hub. The view is shaped like the existing rounds and inbox views: a list with structured rows, a detail panel for a selected entry, an empty state that distinguishes "no changes" from "data source unavailable", and a refresh path that uses the same loading and stale indicators already in the hub.

The view reuses existing scion-ops data sources rather than reimplementing OpenSpec parsing or validation in the hub. The implementation should not introduce a new persistent store, a second source of truth, or any write paths.

## Information Architecture

A new top-level navigation entry called "OpenSpec" sits next to Overview, Rounds, Inbox, and Runtime. Selecting it shows:

- A list of active OpenSpec changes under `openspec/changes/` (excluding the archive directory) with: change name, artifact completeness flags (proposal, design, tasks, spec file count), and the most recent validator outcome when available.
- A detail panel for the selected change with: the artifact completeness summary, the validator outcome including the validator source identifier (`openspec_cli` or fallback) and any errors or warnings, and a list of `specs/**/spec.md` files when present.
- A small "Archived" section that lists archived change names when `openspec/changes/archive/` exists.

Round detail views gain a single OpenSpec reference field. When a round's metadata identifies a target change (already present today via task summaries, branch names, or normalized round state), the round detail shows that change name as a navigable link to the OpenSpec view. Round list rows are not expanded with this field to keep the existing dense layout.

## Data Sources

The implementation uses these existing scion-ops MCP-backed helpers and on-disk reads:

- `scion_ops_spec_status(project_root, change="")` for the active and archived change list, returning artifact completeness flags and, when a change is supplied, validator output and the validator source.
- `scion_ops_validate_spec_change(project_root, change)` for explicit validator runs when the operator selects a change.
- The same project-root resolution that the rest of the hub already uses (no new precedence rules).
- Existing round metadata for the round-to-change link. The hub already extracts structured backing fields from rounds; the OpenSpec change name is treated the same way: prefer structured fields where present, and fall back to text-derived references only when no structured field exists.

The hub must not maintain a parallel cached copy of OpenSpec change state. A short-lived in-request cache used to deduplicate validator calls during a single render is acceptable; a persistent cache is not.

## Backend Shape

A new browser-friendly endpoint returns the OpenSpec changes payload. Its response should include:

- A list of active changes with: `change`, `path`, `has_proposal`, `has_design`, `has_tasks`, `spec_file_count`.
- A list of archived changes with: `archive`, `path`.
- An optional `selected_change` block when the request specifies one, with: `change`, validator `source`, `ok`, structured `errors` and `warnings` (each carrying a path and message), and the validator command output when present.
- A `source` identifier (`local_git` for the change list, `openspec_validator` for validator output), aligned with the rest of the hub.
- The same error categories the hub already uses (`runtime`, `local_git_state`) when the OpenSpec tree cannot be read or the validator cannot be invoked.

The endpoint is read-only. It must not invoke `openspec archive` or any state-changing helper.

## Frontend Behavior

The OpenSpec view follows the existing hub conventions:

- Rows show artifact completeness with consistent indicators (present, missing) so the view is scannable.
- The detail panel shows validator output verbatim where available, distinguishes errors from warnings, and shows the validator source identifier so operators understand whether the result came from `openspec validate` or the local fallback.
- Empty state distinguishes "no changes in this project" from "OpenSpec source unavailable" and surfaces the underlying error category when the source failed.
- A stale indicator appears when the most recent successful refresh exceeds the same threshold the hub already uses.
- Refresh uses the same Refresh button and 15-second interval pattern the hub already uses; it does not introduce new polling rates or push channels.
- Round detail gains exactly one OpenSpec link when a change name is identifiable; the existing timeline, branch, and final-review rendering is unchanged.

## Operational Constraints

- The change must remain no-spend: opening or refreshing the OpenSpec view must not start agents, rounds, or any model-backed work.
- The change must not require a port-forward, an additional service, or an additional Kubernetes manifest. The view is part of the existing `scripts/web_app_hub.py` server.
- The change must not depend on the build-web-app-hub change being archived first. It layers ADDED requirements on the `web-app-hub` capability and is compatible with either an active or archived predecessor.
- The change must not regress the existing overview, rounds, round detail, inbox, or runtime views.

## Verification Strategy

Implementation should include focused verification that:

- The OpenSpec list renders with representative project states: zero changes, one in-progress change, one fully-populated change, and one archived change.
- The detail panel renders validator output for an OK case and a failing case, and clearly distinguishes errors from warnings.
- The empty state distinguishes "no changes" from "unavailable" and surfaces the error category.
- A round detail view that has an identifiable target change shows exactly one OpenSpec link and a round detail view that does not have one does not synthesize a fake link.
- Refreshing the view does not invoke any write or state-changing scion-ops operation; tests should assert only read-only helpers are used.
- The validator runs with the same `--project-root` precedence the rest of the hub uses, and project resolution failures surface the existing `local_git_state` error category.
- Existing build-web-app-hub tests continue to pass without modification.
