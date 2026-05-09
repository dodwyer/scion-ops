# Proposal: Update Web App Hub With OpenSpec Change Visibility

## Summary

Extend the existing read-only scion-ops web app hub with an OpenSpec changes view so operators can see active and archived OpenSpec changes, their artifact completeness, and validator status without leaving the hub for a CLI session. The update reuses the same Hub, MCP, and Kubernetes data sources the hub already depends on, and preserves the read-only invariant established by the build-web-app-hub change.

## Motivation

scion-ops rounds are organized around OpenSpec changes (proposal, design, tasks, delta specs), but the current web app hub only surfaces agent rounds, control-plane readiness, messages, notifications, and runtime state. To learn whether a change has the required artifacts, whether the validator accepts it, or whether it has been archived, operators still have to run `openspec list`, `openspec validate`, or the project-status MCP tool. That gap is small per-task but recurring, and it is the most-asked status question in spec rounds.

Adding a focused OpenSpec changes view closes that gap with no new orchestration surface and no new write paths.

## Scope

In scope:

- A new OpenSpec changes view in the existing web app hub.
- A backend endpoint that returns active OpenSpec changes, their artifact completeness (proposal, design, tasks, spec count), and validator outcome for the selected change, sourced from the existing scion-ops `spec_status` and `validate_spec_change` MCP helpers.
- Listing of archived OpenSpec changes when the project carries an archive directory.
- Linking visible rounds to their target OpenSpec change when round metadata identifies one, so operators can navigate from a round timeline to the change it produces.
- Empty, stale, degraded, and error states for the OpenSpec data source consistent with the existing overview, rounds, inbox, and runtime views.

Out of scope for this change:

- Editing, creating, archiving, or validating OpenSpec changes from the web app.
- Lifting the existing read-only invariant or adding round-mutating actions.
- Replacing the existing CLI `openspec` workflow or the scion-ops MCP tools.
- Multi-project navigation, authentication, or hosted production deployment.
- Changing how rounds, inbox, runtime, or overview views are rendered today, beyond adding the OpenSpec change reference where round metadata already identifies one.

## Success Criteria

- Operators can open the web app hub and see the list of active OpenSpec changes for the active project, with each change clearly indicating whether `proposal.md`, `design.md`, `tasks.md`, and at least one `specs/**/spec.md` are present.
- Operators can see the validator outcome for a selected OpenSpec change, including the validator source identifier and any reported errors or warnings.
- Operators can see archived OpenSpec changes when the project's archive directory exists, distinguished from active changes.
- Operators can navigate from a round detail view to the OpenSpec change it targets when the round is associated with one.
- The OpenSpec changes view reflects the on-disk OpenSpec tree on each refresh and does not maintain an independent persistent copy of change state.
- The web app hub continues to be read-only after this change is implemented; no new write paths or state-changing operations are added.

## Assumptions

This proposal makes the following assumptions because the spec round did not receive a direction-setting answer to the clarifier's open questions on scope. Implementation rounds should adjust scope only by an explicit follow-up change.

1. The spec round retains the read-only invariant from build-web-app-hub. The clarifier's question about lifting read-only is resolved as "preserve read-only".
2. The capability slug `web-app-hub` continues to host all hub deltas. This change adds requirements to the same capability rather than introducing a new one.
3. The view applies to the active project resolved by the existing scion-ops project-root precedence. Multi-project navigation is not in scope.
4. Validator output is sourced from the existing `scion_ops_validate_spec_change` MCP helper rather than reimplementing OpenSpec validation in the web app.
5. The OpenSpec change visibility update does not add Kubernetes, Helm, or hosted-deployment artifacts. Hosting the web app inside the kind cluster is tracked separately and is not part of this change.

## Unresolved Questions

The clarifier asked four direction questions and received no explicit answer before this spec round began. The author resolved each question by assumption above so an implementation round can proceed.

- Question A (which bucket to update) is resolved as "add a focused OpenSpec changes view".
- Question B (archive build-web-app-hub first vs. layer alongside) is resolved as "layer additional ADDED requirements onto the same `web-app-hub` capability without depending on prior archival".
- Question C (preserve read-only vs. lift) is resolved as "preserve read-only".
- Question D (concrete trigger) is resolved as "the recurring operator need to inspect change artifact and validator state during spec rounds".

If a stakeholder needs a different scope, the recommended next step is to author a separate change rather than expanding this one.
