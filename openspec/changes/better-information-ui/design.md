# Design: Better Information UI

## Overview

The implementation should reshape the operator overview and selected-round detail timeline around operational questions:

- What is the current action?
- Who or what has the handoff?
- Why did the handoff happen?
- What should the operator inspect next?

The UI should remain a read-only NiceGUI operator console. It should reuse existing source adapters and preserve JSON compatibility while improving how normalized data is selected, labeled, grouped, and rendered.

## Information Model

Timeline entries should be normalized into display rows with stable identity and concise fields:

- `entry_id`: stable source id, event id, notification id, message id, or deterministic sequence fallback.
- `sequence`: chronological ordering value used when timestamps are equal or missing.
- `timestamp`: source timestamp when available.
- `agent`: actor or source agent responsible for the entry.
- `action`: short operator-readable action being performed or reported.
- `handoff`: destination agent, role, source, reviewer, coordinator, or human/operator target when a handoff exists.
- `reason_for_handoff`: concise reason from structured fields or safe fallback summary.
- `status`: semantic state such as running, waiting, blocked, completed, failed, changes requested, or unknown.
- `source`: backing source label for troubleshooting.
- `detail`: optional deeper diagnostic payload or raw source context.

The display layer must not deduplicate rows solely by agent name, handoff target, action text, or status. Duplicate-looking rows should remain visible when they represent distinct source entries. Deduplication is only appropriate for exact replay duplicates with the same stable source identity.

## Overview Layout

The overview should be compact and task-focused:

- A top readiness strip for control-plane status, live freshness, active rounds, blocked rounds, and recent completion state.
- A priority panel that names the highest-priority round or source needing attention and links to its detail or troubleshooting context.
- A concise recent activity list that favors action, handoff, reason, timestamp, and status over raw logs.
- Source health grouped by Hub, MCP, Kubernetes, broker, web app, and live update path.

Raw payloads, full logs, and verbose source diagnostics should move behind an expansion panel, drawer, dialog, tab, or detail view associated with the item they explain.

## Timeline Layout

The selected-round timeline should render entries as table-like or timeline-list rows with stable columns or labeled row sections:

- Timestamp or sequence marker.
- Agent/source.
- Action.
- Handoff.
- Reason for handoff.
- Status.
- Detail control when deeper context exists.

Desktop layouts may use a dense table or grid. Narrow layouts should stack each row into labeled sections while preserving the same information. Key fields should wrap predictably, and long identifiers or branch refs should use monospace containers with overflow handling scoped to the value rather than the whole page.

## NiceGUI Component Direction

Use current NiceGUI elements where practical instead of legacy hand-built HTML:

- `ui.table` or structured row components for dense timeline and overview activity lists.
- `ui.tabs` and `ui.tab_panels` for round detail sections.
- `ui.expansion`, drawers, or dialogs for one-level-deeper diagnostics.
- Chips, badges, icons, and tooltips for compact semantic statuses.
- Splitters or responsive columns where they improve desktop scanning without causing mobile overflow.

Custom CSS should be limited to layout constraints, responsive behavior, focus treatment, wrapping, and semantic status polish that NiceGUI components do not provide directly.

## Responsiveness

The page should render correctly at representative desktop and mobile widths. Desktop should use available width for scanning without page-level horizontal overflow. Mobile should preserve the primary workflow by stacking navigation, summary, and timeline rows; secondary diagnostics may collapse behind controls.

Checks should cover long round ids, agent names, handoff targets, reason text, branch refs, validation summaries, and source errors. The body or main app container should not exceed viewport width, and controls should not overlap adjacent content.

## Compatibility And Safety

Existing health, snapshot, round detail, round events, and live update JSON endpoints remain backward compatible. New normalized fields for `action`, `handoff`, `reason_for_handoff`, `entry_id`, or `sequence` may be added as backward-compatible fields.

All views and live-update behavior remain read-only. Opening overview, selecting a round, expanding diagnostics, reconnecting, refreshing, and polling must not mutate Hub runtime records, Kubernetes resources, git refs, OpenSpec files, or round state.

## Verification Strategy

Implementation should include no-spend checks for:

- Normalization of action, handoff, and reason-for-handoff fields from representative source data.
- Preservation of distinct duplicate same-agent and same-agent-pair exchanges.
- Overview rendering that keeps raw payloads one interaction deeper.
- Timeline rendering with long content at desktop and mobile widths.
- JSON endpoint compatibility and read-only behavior during refresh and live updates.
