# Design: Update Web App

## Overview

The web app should be treated as a deployed read-only control-plane component, not only a host-side convenience script. Its server-side adapter remains the browser-facing boundary, but the adapter should consume the same Scion Hub and MCP semantics that automation uses, so operators see one consistent model across CLI, MCP, and browser views.

## MCP Alignment

The implementation should update the web app adapter around current MCP result contracts instead of maintaining parallel inference rules. In particular, the app should understand:

- `scion_ops_hub_status` for Hub reachability, grove identity, broker registration, and agent summaries.
- `scion_ops_round_status`, `scion_ops_round_events`, and `scion_ops_watch_round_events` for progress, terminal status, timelines, cursors, and final-review outcomes.
- `scion_ops_round_artifacts` for local branches, remote branches, branch SHA evidence, and workspace references.
- `scion_ops_spec_status` and `scion_ops_validate_spec_change` for OpenSpec status and validation details.
- `scion_ops_run_spec_round` progress fields such as `expected_branch`, `pr_ready_branch`, `validation_status`, `branch_changed`, `protocol`, `blockers`, and `warnings` when those fields are present in stored messages, notifications, or direct MCP responses.

Structured fields from MCP and Hub remain authoritative. Text parsing is allowed only for backward compatibility with older messages that lack structured values, and fallback-derived values should be marked as fallback in the rendered model.

## Web App Runtime Shape

The web app may continue to run as a small Python HTTP server, but when deployed in kind it should use the same operational environment as the MCP pod:

- `SCION_OPS_ROOT` pointing at the mounted scion-ops checkout.
- `SCION_OPS_HUB_ENDPOINT` and `SCION_HUB_ENDPOINT` pointing at the in-cluster `scion-hub` service.
- `SCION_OPS_MCP_URL` pointing at the in-cluster MCP service and path.
- `SCION_GROVE_ID` / `SCION_OPS_GROVE_ID` derived from the mounted repo when available.
- `SCION_DEV_TOKEN_FILE` mounted from the same Hub dev-auth Secret used by MCP.
- Optional GitHub token secret mounted read-only when branch/artifact checks need authenticated remote access.

The deployed app should expose a stable HTTP port through a Kubernetes Service. For local kind, the service should be reachable via the configured host listen address without requiring `kubectl port-forward`.

## Kind And Kustomize Integration

The control-plane kustomization should include web app resources alongside Hub, broker, and MCP. The expected resource set is:

- a Deployment for the web app server;
- a Service with a stable name and port;
- any ServiceAccount/RBAC needed for read-only Kubernetes readiness inspection;
- optional ConfigMap or env wiring if the web app requires explicit server settings.

Taskfile lifecycle commands should include the web app where operators expect a complete control-plane reconciliation:

- image build/load when the web app has a dedicated image;
- `task up` and `task kind:control-plane:apply`;
- rollout restart/status for the complete control plane;
- narrow update/status/log/smoke tasks for the web app.

If the implementation reuses the MCP image, the manifest should still make the web app container command, port, probes, and labels explicit.

## UI Updates

The browser views should preserve the existing read-only operator shape while adding MCP-aligned data:

- Overview should include web app deployment health in the control-plane readiness calculation.
- Rounds should show explicit status, terminal status, blockers, warnings, validation status, final-review display, expected branch, PR-ready branch, and remote branch SHA when available.
- Round detail should show a timeline from MCP event snapshots and expose cursor refresh behavior without losing existing entries.
- Runtime should show Hub, MCP, Kubernetes, and web app deployment/service health separately.
- Inbox should continue to group messages by round, but should also surface spec-round protocol milestones and validation failures when present.

## Verification Strategy

Implementation should include no-spend checks that can run without starting model-backed rounds:

- Unit or fixture tests for current MCP result shapes, especially spec-round progress and blocked final-review outcomes.
- Tests that structured MCP fields take precedence over message text, task summaries, agent names, and slugs.
- Tests or rendered-manifest checks proving kustomize includes the web app Deployment and Service.
- Static checks for the web app server and any new Kubernetes YAML.
- A kind smoke path that verifies the web app endpoint responds and that control-plane status includes its rollout.
