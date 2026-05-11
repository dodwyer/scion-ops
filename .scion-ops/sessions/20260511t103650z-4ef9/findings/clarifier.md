# Spec Clarifier Findings — 20260511t103650z-4ef9
**Change:** better-information-ui
**Date:** 2026-05-11

---

## Understood Intent

Redesign the Operator overview and round-detail timeline UI to:

1. **Reduce noise** — strip fields that don't help an operator quickly understand what happened
2. **Surface the narrative** — each timeline entry should answer: what did the agent do, who did it hand off to, and why
3. **Allow duplicate agent entries** — back-and-forth exchanges between agents should produce visible, separate rows (no collapsing)
4. **Modernise the layout** — adopt current NiceGUI component patterns; fix desktop overflow and ensure the page is usable on mobile

---

## What Exists Today

The UI is a single file: `scripts/web_app_hub.py` (~3 050 lines).

- The skeleton is built with NiceGUI (`ui.element`, `ui.header`, `ui.timer`, etc.), but **all rendering is JavaScript-driven** — NiceGUI is used as a scaffold, not for component-level rendering.
- The timeline entry currently displays: `type`, `time`, `actor`, `agent_name`, `role`, `template`, `harness_config`, `phase`, `activity`, `summary`.
- The round-detail uses a `.split` two-column layout that likely causes overflow on narrow viewports.
- The design predates current NiceGUI element conventions; no responsive breakpoints are applied.

---

## Scope Boundaries

### In scope
- `scripts/web_app_hub.py` — timeline rendering (JavaScript template `timelineItem`), CSS, and NiceGUI page structure
- Operator overview (rounds list) and round-detail view (click-through)
- Timeline entry data model — which fields are exposed vs. hidden
- Layout: desktop no-overflow, mobile-friendly breakpoints

### Out of scope (unless confirmed)
- Backend data pipeline (`build_decision_flow`, `build_operator_summary`, `timeline_entry`) — data shape changes are NOT assumed
- Other views: inbox, runtime, checks panel
- Authentication or access control
- Non-Operator roles (dev view, raw runtime tab)

---

## Acceptance Questions for Operator

The following questions must be answered before implementation begins:

### Q1 — Timeline fields: what maps to "action / hand-off / reason"?
The current data model has these relevant fields per entry:

| Field | Current use |
|---|---|
| `activity` | agent's current activity label |
| `last_action` | last action taken by the agent |
| `summary` | message or notification text |
| `phase` | agent lifecycle phase |
| `role` | agent role (e.g. spec-steward, clarifier) |
| `type` | entry type: message / notification / agent |

**Question:** Which field(s) represent "action"? Is it `activity`, `last_action`, or the `summary` text?  
**Question:** "Hand off" — does this mean a `notification` event from one agent to another, a specific `type=message` to a named recipient, or something else?  
**Question:** "Reason for handoff" — is this the `summary` field content, or a separate structured field that needs to be added to the backend?

---

### Q2 — Which existing fields should be removed?
The current entry shows `template`, `harness_config`, `phase` alongside the narrative fields. Are all three of these to be removed, or should any be kept (e.g. `role` is likely kept)?

---

### Q3 — "New NiceGUI elements" — what is the target?
The current page uses NiceGUI as a thin scaffold with JS rendering. Two interpretation paths:

**Option A:** Keep JS rendering, just update the CSS design system (colours, spacing, typography) to match a newer aesthetic.  
**Option B:** Replace JS rendering with NiceGUI component calls (`ui.card`, `ui.timeline`, `ui.table`, etc.) for the timeline and overview cards.

Option B is a significantly larger change. Which is intended?

---

### Q4 — Mobile target
What is the minimum viewport width to support (e.g. 375 px / iPhone SE, 390 px / iPhone 14)?  
Should the two-column round-detail split stack vertically on mobile, or collapse to a single scrollable column?

---

### Q5 — Desktop overflow
Is the overflow specific to the round-detail split layout, the agent matrix table, or both? A screenshot or viewport width where it breaks would help scope the fix.

---

### Q6 — Duplicate entries: current behaviour vs. desired
The timeline already records multiple entries per agent. Is the problem that the **UI is deduplicating or collapsing** entries, or that the visual design makes it hard to distinguish repeated entries from the same agent?

---

## Non-Goals (assumptions)

- No changes to SSE/polling data pipeline
- No new backend API endpoints
- No changes to authentication or routing
- No changes to the checks panel, inbox, or runtime views
- No changes to how `build_decision_flow` or `build_operator_summary` compute data (unless Q1 reveals a missing field)

---

## Risk / Flag

The JS-rendering architecture is tightly coupled with the NiceGUI skeleton. If Q3 resolves to Option B (full NiceGUI components), the implementation scope roughly doubles and may touch the test suite (`test-web-app-hub.py`). The steward should factor this into effort estimation.
