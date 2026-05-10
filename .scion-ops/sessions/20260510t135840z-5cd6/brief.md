# Implementation Steward Session 20260510t135840z-5cd6

Change: autorefresh-web-app
Base branch: main
Final branch: round-20260510t135840z-5cd6-integration

Goal:
Implement the approved OpenSpec change.

## Approved Artifacts Read

- openspec/changes/autorefresh-web-app/proposal.md
- openspec/changes/autorefresh-web-app/design.md
- openspec/changes/autorefresh-web-app/tasks.md
- openspec/changes/autorefresh-web-app/specs/web-app-hub/spec.md

## Task Groups

### Group A: Web App Live Update Contract and UI

Implementer branch: round-20260510t135840z-5cd6-impl-codex

Owned paths:

- scripts/web_app_hub.py
- scripts/test-web-app-hub.py
- openspec/changes/autorefresh-web-app/tasks.md

Tasks:

- 1.1 Identify current snapshot endpoints and source coverage in code comments/tests as needed.
- 1.2 Define the browser-facing live update contract in the backend JSON/SSE contract.
- 1.3 Add a read-only streaming or stream-like endpoint covering overview, rounds, selected round detail timeline, inbox, and runtime.
- 1.4 Connect the frontend to the automatic update path.
- 1.5 Preserve selected round detail state, scroll/filter context, and timeline entries while merging updates.
- 1.6 Add live, reconnecting, stale, fallback polling, and failed indicators.
- 1.7 Keep any manual refresh as secondary troubleshooting only.
- 1.8 Add fixture/unit tests for snapshot plus incremental updates, duplicate replay handling, timeline append, inbox update, runtime status changes, and final-review/status changes.
- 1.9 Add reconnect/stale-state tests for cursor resume or safe fallback snapshot behavior.

Out of scope:

- Kubernetes manifests, kind smoke workflow, image build scripts, PR/steward state files, and unrelated OpenSpec changes.
- Any write operation from the web app.

### Group B: Kind/Smoke Verification for Automatic Updates

Implementer branch: round-20260510t135840z-5cd6-impl-claude

Owned paths:

- scripts/kind-control-plane-smoke.py
- scripts/test-web-app-hub.py
- openspec/changes/autorefresh-web-app/tasks.md

Tasks:

- Add or extend no-spend smoke coverage that verifies the web app automatic update path is reachable without starting model-backed rounds.
- Add focused tests for the stream/fallback behavior if needed to keep smoke checks fixture-based and deterministic.
- Update only task checkboxes that this branch completes, most likely 1.11 if verification commands pass and any shared smoke-related subpart of 1.8/1.9.

Out of scope:

- Backend/UI implementation in scripts/web_app_hub.py unless only a narrow smoke hook is required and coordinated in the completion summary.
- Kubernetes resource mutation, Hub/MCP write paths, and unrelated docs.

## Verification Commands

Expected branch-local verification:

- python3 scripts/validate-openspec-change.py autorefresh-web-app
- python3 -m pytest scripts/test-web-app-hub.py
- python3 -m pytest scripts/test-openspec-change-validator.py scripts/test-steward-session-validator.py

Expected integration verification:

- python3 scripts/validate-openspec-change.py autorefresh-web-app
- python3 -m pytest scripts/test-web-app-hub.py
- python3 -m pytest scripts/test-openspec-change-validator.py scripts/test-steward-session-validator.py scripts/test-steward-pr-finalizer.py
- python3 scripts/kind-control-plane-smoke.py --skip-cluster --skip-broker --skip-mcp --skip-hub --skip-web-app, if supported by the current CLI, or an equivalent no-spend fixture/static smoke path.

## Integration Notes

- Product changes must land through implementer branches, not the steward branch.
- If an implementer exits without a non-empty pushed branch, record the blocker in state and start a narrower replacement only after pre-creating its remote branch from origin/main.
- Final review must branch from the pushed integration SHA.
