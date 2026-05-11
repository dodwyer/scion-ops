# Clarifier Findings: better-information-ui

**Session:** 20260511t114424z-3da2  
**Change:** better-information-ui  
**Date:** 2026-05-11

---

## What Problem Is Being Solved

The operator-facing web app hub presents too much information without prioritization. Operators cannot easily determine what is happening, who owns the next step, or why a handoff occurred. Raw payloads, logs, and low-level diagnostics dominate the default view. Additionally, when the same agent or agent pair exchanges messages multiple times, the UI may suppress those repeated entries — hiding meaningful operational evidence.

---

## Proposed Change

**Name:** `better-information-ui`  
**Target file:** `scripts/web_app_hub.py`  
**Target rendering path:** NiceGUI (used in Kubernetes deployment)

Reshape the operator overview and selected-round timeline around four operator questions:

1. What is the current action?
2. Who has the handoff?
3. Why did the handoff happen?
4. What should I inspect next?

Key deliverables:
- Normalized timeline entries with stable `entry_id`, `sequence`, `action`, `handoff`, `reason_for_handoff`, `status`, `source`, and `detail` fields.
- Overview restructured as: readiness strip → priority panel → recent activity list → source health.
- Raw payloads, logs, and diagnostics moved behind NiceGUI expansion panels, drawers, tabs, or dialogs.
- First-class NiceGUI components: `ui.table`, `ui.tabs`, `ui.tab_panels`, `ui.expansion`, chips, badges, tooltips, splitters.
- Responsive desktop and mobile layouts with no page-level horizontal overflow.

---

## Scope

**In scope:**
- `scripts/web_app_hub.py` — NiceGUI rendering path only.
- Operator overview content and selected-round timeline.
- Timeline entry normalization for action, handoff, and reason-for-handoff.
- Preservation of distinct repeated same-agent or same-agent-pair exchanges.
- Moving diagnostics one interaction deeper via NiceGUI controls.
- Desktop and mobile responsive layout correctness.
- No-spend normalization tests and responsive layout fixture checks.

**Out of scope:**
- The raw HTML/CSS/JS rendering path (`INDEX_HTML` variable) — left as-is.
- Authentication or authorization changes.
- Write/mutation controls — UI remains strictly read-only.
- Changes to Hub, MCP, Kubernetes, or OpenSpec data contracts beyond backward-compatible display field additions.
- Live-update transport behavior (SSE fallback, polling, cursor resumption).
- Non-overview/non-timeline views (runtime diagnostics page, inbox, source error banners).

---

## Assumptions

The following questions were considered non-blocking and converted to implementation assumptions:

1. **NiceGUI path is the primary target.** The app supports two rendering paths: raw HTML (local dev) and NiceGUI (Kubernetes). This change targets the NiceGUI path. The raw HTML path is not updated and may be addressed separately.

2. **Normalization is server-side (Python), not client-side.** New `action`, `handoff`, `reason_for_handoff`, `entry_id`, and `sequence` fields are added to existing JSON responses as backward-compatible extensions. No new endpoints are required.

3. **Structured source fields are partially available.** Existing timeline/round data from Hub, MCP, notifications, and messages contains partial structured data that maps to the new fields. Text-based fallbacks (task summaries, agent names, notification text) are acceptable when structured fields are absent.

4. **Currently-pinned NiceGUI version supports required components.** The implementation uses the NiceGUI version already present in the project without upgrades. If a specific component (`ui.table`, `ui.expansion`, etc.) is unavailable in the pinned version, the implementer should use the closest available alternative and note the deviation.

5. **"No-spend tests" means Python pytest fixtures.** Tests exercise normalization logic and layout checks without making model API calls. Snapshot-style checks for JSON contract compatibility are acceptable.

6. **Deduplication is identity-only.** Only entries with the same stable source identity (matching `entry_id`) may be suppressed. All other repeated entries — including same-agent or same-agent-pair exchanges — remain visible as distinct rows.

---

## Open Questions

None are blocking. All questions were resolved as assumptions above.

---

## Acceptance Signals for Steward

The implementation steward should treat this change as ready to proceed when:

- [ ] `scripts/web_app_hub.py` NiceGUI views use `ui.table`, `ui.tabs`, `ui.expansion`, chips, and tooltips for overview and round-detail timeline.
- [ ] Timeline entries expose `action`, `handoff`, `reason_for_handoff` as labeled fields (not buried in raw payloads).
- [ ] Raw payloads, runner output, and low-level diagnostics are behind at least one expansion or tab interaction.
- [ ] Multiple distinct handoffs involving the same agent pair are each visible as separate rows.
- [ ] Desktop viewport: no body-level horizontal overflow, no overlapping controls, long IDs/branch refs constrained to their containers.
- [ ] Mobile viewport: navigation, readiness, and timeline action/handoff/reason stack without overspill.
- [ ] Existing `/api/snapshot`, `/api/rounds/{round_id}`, and `/api/live` contracts remain backward-compatible.
- [ ] No-spend normalization tests cover structured-field preference, text-fallback path, and identity-only deduplication.
- [ ] OpenSpec validation passes for `openspec/changes/better-information-ui/`.
