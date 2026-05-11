# Proposal: Make Live 1

## Summary

Promote the React/Vite operator UI from the temporary evaluation path to the single live scion-ops operator UI. The live UI should own the existing web app operator identity, deployment path, health and JSON contracts, and browser access path while the old NiceGUI/server-rendered UI is removed from the live kind control-plane deployment.

The change also retires preview and non-live framing from the runtime path. Names, schema identifiers, documentation, lifecycle tasks, smoke checks, and Kubernetes resources should describe the React/Vite UI as the live operator console, not an evaluation preview. Fixture-backed behavior may remain only as an explicit local development and test mode, never as a user-facing production fallback.

## Motivation

The React/Vite UI has already been wired to live read-only operational data. Keeping it as a separate preview alongside the old live UI creates two operator surfaces, two service identities, two ports, and lingering "evaluation" language that makes the intended production path ambiguous.

Operators need one canonical UI for monitoring rounds, source health, inbox updates, runtime state, diagnostics, and raw source evidence. The live path should use the newer React/Vite experience and preserve the existing read-only safety and no-spend operational contracts.

## Scope

In scope:

- Make the React/Vite UI the deployed live `scion-ops-web-app` operator surface.
- Remove the old NiceGUI/server-rendered web app from the live kind control-plane kustomize deployment.
- Remove the separate `scion-ops-new-ui-eval` preview Deployment, Service, route, lifecycle, and coexistence expectations from the desired live state.
- Keep health, snapshot, round detail, round event, live event stream, and browser-facing JSON contracts available for smoke checks and automation.
- Rename runtime-facing preview/evaluation strings, schema versions, documentation, task labels, and smoke output to live operator-console terminology.
- Keep fixture mode only as an explicit development or test mechanism that is disabled and hidden from the production live operator path.
- Preserve read-only source access, live stream behavior, reconnect behavior, stale state, source-specific failures, and no-spend verification.

Out of scope:

- Adding write operations such as starting, retrying, aborting, deleting, or archiving rounds.
- Mutating Hub records, MCP state, Kubernetes resources, git refs or files, OpenSpec files, secrets, PVCs, broker state, or model/provider state.
- Reworking authentication, authorization, alert delivery, historical replay, or multi-user collaboration.
- Deleting historical OpenSpec change records that describe earlier evaluation phases.
- Requiring a broad backend consolidation beyond what is needed for the React/Vite adapter to own the live web-app identity.

## Success Criteria

- The kind control-plane renders one live operator UI Deployment and Service using the existing web app identity.
- The rendered live operator UI serves the React/Vite application and no longer deploys the old NiceGUI/server-rendered UI or a separate new-UI evaluation service.
- Operator docs, lifecycle tasks, smoke output, schema identifiers, service labels, and default URLs no longer present the React/Vite UI as a preview or evaluation path.
- Fixture data is reachable only through explicit local development or test configuration and is visibly labeled when used.
- Existing read-only JSON, health, snapshot, round detail, event stream, source-health, reconnect, stale-state, and no-spend smoke contracts remain covered by verification.
