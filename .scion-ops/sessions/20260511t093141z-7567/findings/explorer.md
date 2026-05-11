# Explorer Findings: Better Information UI

Session: `20260511t093141z-7567`
Change: `better-information-ui`
Base branch: `main`
Expected branch: `round-20260511t093141z-7567-spec-explorer`

## Recommendation

Create a narrow OpenSpec change at `openspec/changes/better-information-ui/` with the standard files:

- `proposal.md`
- `design.md`
- `tasks.md`
- `specs/web-app-hub/spec.md`

The lowest-risk spec surface is the existing `web-app-hub` capability. Do not introduce a new spec area. The current NiceGUI, theme, MCP/source preservation, live update, read-only, and responsive requirements already live under `openspec/changes/use-nicegui/specs/web-app-hub/spec.md`, so this change should modify or add requirements there conceptually rather than broadening into deployment or runtime behavior.

## Relevant Existing OpenSpec Constraints

- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:113` already requires a NiceGUI frontend and a fresh operator-console structure.
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:125` says the visible interface is organized around overview, rounds, round detail, inbox, runtime, and troubleshooting, and does not need to preserve prior HTML structure or CSS.
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:133` requires NiceGUI components to preserve selected round/filter/expanded state and avoid duplicate timeline or inbox entries for replayed update events.
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:141` through `:165` already covers concise defaults and one-level-down diagnostics.
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:167` through `:192` covers Laws of UX constraints for grouping, proximity, and explicit feedback.
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:194` through `:219` covers desktop/mobile rendering and basic accessibility.
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:36` through `:62` is the important source-of-truth boundary: keep structured JSON fields authoritative and preserve partial data when one source fails.
- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md:64` through `:81` keeps the UI read-only. The information UI work should not add mutating controls.

These are broad enough that the new spec should focus on the missing information architecture: action, handoff, and reason for handoff.

## Current Implementation Shape

The current web app is technically NiceGUI-hosted but much of the visible UI is still an embedded HTML/CSS/JavaScript renderer:

- `scripts/web_app_hub.py:1798` starts a large `INDEX_HTML` string containing the old document, style, and script.
- `scripts/web_app_hub.py:2291` through `:2408` renders overview, rounds, round detail, inbox, and runtime by assigning `innerHTML`.
- `scripts/web_app_hub.py:2465` through `:2481` builds only a shallow NiceGUI shell with header, nav buttons, and placeholder sections.
- `scripts/web_app_hub.py:2383` through `:2398` puts round detail into two dense columns with timeline, decision flow, final review, MCP state, branches, agents, and coordinator output all visible in one pass.
- `scripts/web_app_hub.py:2406` through `:2408` renders runtime as raw JSON by default, which conflicts with the concise-default/one-level-down diagnostic direction.

The spec should explicitly require the implementation to use modern NiceGUI elements for the visible information architecture: tabs, splitters, tables, rows, expansion panels, dialogs/drawers, badges, and route/page state where appropriate. Keeping JavaScript only for the existing live update transport is lower risk than allowing the primary UI to remain an HTML-string app inside NiceGUI.

## Data/Behavior Hotspots To Preserve

- `scripts/web_app_hub.py:686` defines backend `build_decision_flow(...)`. It groups by role/agent and adds stage events from agents plus timeline entries.
- `scripts/web_app_hub.py:982` defines `timeline_entry(...)`, preserving source ids and agent metadata.
- `scripts/web_app_hub.py:1390` defines `build_rounds(...)`, which is the safest backend place for any row-level action/handoff/reason summaries.
- `scripts/web_app_hub.py:1677` defines `build_round_detail(...)`, which is the safest backend place for detailed action/handoff/reason entries.
- `scripts/web_app_hub.py:1931` through `:1937` deduplicates decision-flow events in the frontend by label, summary, time, and source. The new requirement should prohibit collapsing legitimate repeated action/handoff entries for the same agent when they represent separate back-and-forth.
- `scripts/web_app_hub.py:2193` through `:2204` deduplicates live timeline append events by stable key/id. The spec should preserve replay idempotency while retaining distinct source events.

Recommended source contract addition: an additive field such as `handoff_flow` or `operator_flow` on round rows and round detail, where each entry has at least:

- `id`
- `time`
- `agent_name`
- `role`
- `action`
- `handoff_to` or `handoff_from`
- `reason`
- `status`
- `source_id`

This should be additive to existing `decision_flow`, `timeline`, `agents`, `final_review`, and `mcp` fields to avoid breaking tests or external JSON consumers.

## Proposed New/Modified Requirements

Recommended delta spec topics for `openspec/changes/better-information-ui/specs/web-app-hub/spec.md`:

1. Modify `NiceGUI Frontend` or add `NiceGUI Native Information UI`
   - Require primary overview, rounds, round detail, inbox, runtime, and troubleshooting views to be composed with NiceGUI elements rather than HTML-string page rendering.
   - Allow small JavaScript helpers only for live update transport or NiceGUI interop, not primary layout generation.

2. Add `Operator Information Architecture`
   - Default overview shows the highest-priority action needed, owner/source, handoff target when known, and reason.
   - Rounds view compares current action, latest handoff, reason for handoff, final review/validation state, latest update, and blocker summary.
   - Round detail starts with a concise operator summary before deeper tabs/panels.

3. Add `Action And Handoff Flow`
   - Round detail shows chronological entries for action, handoff, and reason for handoff.
   - Distinct back-and-forth entries for the same agent pair remain visible.
   - Replay duplicate events remain idempotent only when the source id or deterministic event identity is the same.

4. Modify `Progressive Troubleshooting`
   - Runtime raw JSON and coordinator output move behind one-level-down panels.
   - Overview/detail defaults avoid raw payloads and long logs.

5. Modify `NiceGUI Responsive Operator Layout`
   - Desktop must avoid horizontal overspill for long round ids, branch refs, and reasons.
   - Mobile must keep round id, current action, handoff target, reason, state, and latest update readable by wrapping/collapsing secondary fields.

## Suggested Tasks

Use focused tasks that avoid deployment churn:

- Add/update OpenSpec requirements for action/handoff/reason IA and native NiceGUI rendering.
- Add additive backend flow summaries without removing current JSON fields.
- Replace primary `innerHTML` view rendering with NiceGUI-built components while preserving existing API routes.
- Move raw runtime/source JSON, protocol payloads, coordinator output, and long validation details behind NiceGUI expanders/tabs/drawers.
- Add no-spend fixture tests for duplicate handoff preservation, JSON compatibility, desktop no-overspill markers, mobile stacking, and raw diagnostics one level down.
- Run `scripts/validate-openspec-change.py better-information-ui` and `scripts/test-web-app-hub.py`.

## Existing Tests And Validation To Respect

- `scripts/validate-openspec-change.py` requires `proposal.md`, `design.md`, `tasks.md`, and at least one `specs/**/spec.md` with `### Requirement:` and `#### Scenario:`.
- `scripts/test-web-app-hub.py:417` through `:438` protects structured branch precedence.
- `scripts/test-web-app-hub.py:441` through `:542` protects final-review visibility and changes-requested/blocked semantics.
- `scripts/test-web-app-hub.py:545` through `:594` protects structured steward progress fields and MCP state display.
- Existing live update tests protect replay idempotency and partial-source preservation, so duplicate handoff preservation should be specified as preserving distinct source events, not disabling dedupe entirely.

## Risk Notes

- Highest risk: rewriting the UI to native NiceGUI while preserving the current live update behavior and JSON endpoints.
- Medium risk: defining handoff/action extraction from unstructured messages. The spec should require structured source fields first and allow message-derived entries only as fallback.
- Low risk: additive JSON fields and layout requirements, because current contracts already support backward-compatible growth.
- Avoid touching kind manifests, MCP tool contracts, and read/write runtime behavior in this change unless the author finds a direct UI dependency.
