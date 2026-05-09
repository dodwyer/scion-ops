# Proposal: Update Web App

## Summary

Update the read-only web app hub so it stays aligned with the current scion-ops MCP service contract and becomes part of the local kind/kustomize control-plane install. The web app should present the same Scion Hub, round, artifact, final-review, and validation state that the MCP service now exposes, while being deployable through the same `task up` and `deploy/kind/control-plane` workflow as Hub, broker, and MCP.

## Motivation

The MCP service has been updated to better align with Scion conventions, including structured round snapshots, OpenSpec validation/status helpers, explicit artifact and branch fields, normalized final-review outcomes, and kind-hosted streamable HTTP operation. The web app currently exists as a local script and must not drift from those operator-facing MCP semantics.

Operators also need the web app included in the repeatable local control-plane install. If Hub, broker, and MCP are reconciled by kustomize but the web app is started manually, the browser surface can lag behind the deployed runtime and miss the same in-cluster configuration, secrets, and health checks.

## Scope

In scope:

- Align web app data loading and rendering with the current scion-ops MCP tool result shapes.
- Prefer structured MCP/Hub fields for round ids, branch refs, artifacts, validation status, final-review verdicts, and blocker summaries.
- Show OpenSpec spec-round status, validation result, expected branch, PR-ready branch, and remote branch evidence when present.
- Add the web app to the local kind control plane through kustomize resources, service exposure, rollout status, and update tasks.
- Ensure the web app uses the same in-cluster Scion Hub, MCP URL, grove id, workspace mount, dev auth, and GitHub token conventions as the MCP deployment where applicable.
- Add verification for MCP contract fixtures and rendered deployment resources.

Out of scope:

- Adding web app write operations such as starting, aborting, retrying, or archiving rounds.
- Replacing MCP APIs or changing MCP tool names as part of the web app update.
- Adding production authentication, multi-user authorization, or non-kind deployment targets.
- Changing accepted OpenSpec archives outside this change artifact.

## Success Criteria

- The web app displays the same round status, artifact branch, final review, validation, and blocker semantics exposed by the current MCP service.
- The app can be installed with the kind control plane using kustomize and reached through a stable service/host port without manual port-forwarding.
- `task up`, narrow web-app update tasks, control-plane status, and no-spend smoke checks account for the web app rollout.
- Backend and frontend tests cover representative current MCP payloads, including spec-round progress and blocked final-review outcomes.
