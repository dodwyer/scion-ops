# Proposal: Make Live 1

## Summary

Make the React/Vite operator console the live scion-ops web UI under the existing live web-app operator path. The old server-rendered UI must no longer be the deployed browser surface, and the React/Vite UI must stop being described or deployed as a separate evaluation preview.

## Motivation

The React/Vite UI has already moved beyond fixture-only evaluation and now reads live operational state. Keeping it behind preview naming and a separate service creates operator confusion: there appear to be two UIs, two ports, and two deployment lifecycles even though the requested outcome is one live UI.

This change establishes the new UI as the single live operator console while keeping the important production contracts from the current web app: stable service identity, read-only behavior, health checks, snapshot and event APIs, no-spend smoke checks, and structured operational data.

## Scope

In scope:

- Promote the React/Vite UI and its Python adapter to the live web-app deployment and operator access path.
- Preserve the stable `scion-ops-web-app` Kubernetes Service and Deployment identity for the live UI.
- Remove the old UI from the live deployment path.
- Remove separate preview/evaluation deployment, service, port, docs, task, smoke, and runtime references from the desired live state.
- Keep fixture data only as a local development and test fallback, not as a production preview mode.
- Rename production-facing schema, runtime, and status metadata so it does not carry `new-ui-evaluation`, `preview`, `eval`, `mocked`, or non-live wording.
- Preserve read-only source access, health checks, snapshots, SSE events, fallback polling, source diagnostics, and no-spend validation.

Out of scope:

- Adding write operations, authentication, authorization, alerts, historical replay, or model/provider execution.
- Changing the source-of-truth contracts for Hub, MCP, Kubernetes, git, or OpenSpec data beyond what is required for the live UI promotion.
- Deleting historical OpenSpec changes.
- Renaming the source directory unless a later implementation change chooses to do so as a mechanical cleanup.

## Success Criteria

- The rendered kind control-plane install contains one live browser UI service and deployment: `scion-ops-web-app`.
- The live web-app service serves the React/Vite operator console and adapter endpoints.
- The old server-rendered UI is not started by the live deployment.
- Operator docs and task names describe the React/Vite console as the live UI, not an evaluation preview.
- Production API payloads and runtime metadata avoid preview/evaluation naming while preserving structured read-only contracts.
- Fixture mode remains available only for explicit local development and tests.
- OpenSpec validation passes for this change.
