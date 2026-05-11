# Explorer Findings: better-information-ui

## Summary

The `better-information-ui` OpenSpec change already exists and is structurally valid. The lowest-risk follow-on implementation path is to keep the change scoped to the web app hub contract and rendering surface in `scripts/web_app_hub.py`, with focused fixture coverage in `scripts/test-web-app-hub.py`.

The current app is a read-only operator console served by NiceGUI/FastAPI, but most of the visible UI is still a hand-built `INDEX_HTML` string with JavaScript rendering and CSS. The proposed change should treat the existing JSON endpoints and live-update behavior as compatibility boundaries while improving normalized display data and moving the default view toward clearer operational scanning.

## Existing OpenSpec Artifacts

- `openspec/changes/better-information-ui/proposal.md`
- `openspec/changes/better-information-ui/design.md`
- `openspec/changes/better-information-ui/tasks.md`
- `openspec/changes/better-information-ui/specs/web-app-hub/spec.md`

Local validation result:

```text
python3 scripts/validate-openspec-change.py better-information-ui --project-root .
OpenSpec change better-information-ui: ok
```

## Lowest-Risk Files

Primary implementation files:

- `scripts/web_app_hub.py`
  - `timeline_entry(...)` is the natural place to add backward-compatible normalized fields such as `entry_id`, `sequence`, `action`, `handoff`, `reason_for_handoff`, `status`, `source`, and `detail`.
  - `build_round_detail(...)` owns selected-round timeline construction and sorting.
  - `build_snapshot(...)` and `build_overview(...)` own overview summaries and readiness counts.
  - `merge_live_events(...)`, `build_live_update_batch(...)`, and the JavaScript `timelineKey` logic are the sensitive compatibility points for preserving distinct entries while suppressing exact replay duplicates.
  - `INDEX_HTML`, `nicegui_console_style()`, `nicegui_console_script()`, `nicegui_console_fragment()`, and `build_nicegui_console_components(...)` define the current rendered app surface.

- `scripts/test-web-app-hub.py`
  - Existing fixtures already cover snapshots, round detail, source failures, final review state, live update idempotency, read-only paths, and frontend contract markers.
  - Add focused tests here for normalized action/handoff/reason fields, distinct duplicate same-agent handoffs, concise default overview fields, and long-content layout contract markers.

OpenSpec files to carry into the follow-on steward round:

- `openspec/changes/better-information-ui/proposal.md`
- `openspec/changes/better-information-ui/design.md`
- `openspec/changes/better-information-ui/tasks.md`
- `openspec/changes/better-information-ui/specs/web-app-hub/spec.md`

## Constraints And Compatibility Boundaries

- Keep the interface read-only. Existing tests assert that live updates and frontend fetches do not call mutation-like provider methods and do not use non-GET fetch methods.
- Preserve browser-facing JSON compatibility. Existing endpoints include `/api/health`, `/api/overview`, `/api/snapshot`, `/api/rounds/{round_id}`, `/api/rounds/{round_id}/events`, and `/api/live`.
- Add normalized fields as backward-compatible additions rather than replacing existing `summary`, `actor`, `agent_name`, `role`, `template`, `harness_config`, `phase`, `activity`, `raw`, and id fields.
- Do not deduplicate timeline rows by agent, handoff target, action, or status. The current backend `merge_live_events(...)` deduplicates timeline appends by `entry["id"]`; the frontend currently uses `timelineKey = [type, time, summary, raw id or actor]`. Any change should use stable source identity for exact replay suppression and preserve distinct sequence positions when ids are missing.
- `build_overview(...)` is intentionally lightweight and should not fetch Kubernetes, per-round status, artifacts, or spec status; an existing test enforces this.
- `build_snapshot(...)` performs heavier source gathering and round enrichment. Overview improvements that require full control-plane source health belong in the snapshot overview, not the lightweight `/api/overview` helper unless tests are intentionally updated.
- Source-backed structured fields should take precedence over message text, notification text, task summaries, or inferred agent names.
- Raw payloads and long diagnostics are already present in data structures. The UI change should move them one interaction deeper without removing them from JSON detail payloads.

## Current UI Shape

The app currently exposes a NiceGUI page wrapper, but rendering is dominated by a static HTML/JS console:

- Overview shows four cards for readiness, active rounds, agents, and latest update, followed by source check cards.
- Rounds render a table with round id, state, operator view, and last signal.
- Round detail renders an operator summary, decision flow, raw timeline inside a `details` block, consensus, final review, MCP state, agent matrix, branches, and coordinator output.
- Runtime renders source records with raw JSON visible by default.

This means the follow-on implementation can either continue the existing static-rendering pattern with tighter structured rows, or migrate selected sections to more direct NiceGUI components. The spec asks for current NiceGUI component patterns; that is a bigger frontend refactor than simply adding fields to the existing JavaScript renderer.

## Suggested Implementation Order

1. Extend `timeline_entry(...)` with normalized fields while keeping old fields intact.
2. Add fixture tests for structured action/handoff/reason extraction and fallback behavior.
3. Adjust live update/backend and frontend deduplication keys to suppress only exact replay duplicates.
4. Add overview snapshot fields for highest-priority attention target and recent activity summaries without changing read-only source contracts.
5. Rework overview and round detail rendering so default rows show action, handoff, reason, source, timestamp/sequence, and status, with raw payloads behind a detail control.
6. Add responsive/long-content contract checks in `scripts/test-web-app-hub.py`; use browser-level checks only if the implementation steward has the local dependencies and time.

## Verification To Run

- `python3 scripts/validate-openspec-change.py better-information-ui --project-root .`
- `uv run scripts/test-web-app-hub.py` or the repo's equivalent no-spend test command for the web app fixture tests.
- If frontend layout is materially changed, run a local browser check at desktop and narrow mobile widths for no body-level horizontal overflow and no overlapping timeline controls.

## Risk Notes

- The largest implementation risk is mixing a partial NiceGUI component migration with the current HTML/JS state machine. A small, reliable implementation can first improve normalized data and current rendering, then selectively replace sections with NiceGUI components.
- Live event idempotency is easy to regress. Preserve replay suppression for identical event ids while keeping repeated same-agent exchanges visible when they have distinct source ids, timestamps, or deterministic sequence values.
- Moving raw details one interaction deeper should be visual only. Existing diagnostic data should remain available through JSON endpoints and detail payloads for tests and operator troubleshooting.
