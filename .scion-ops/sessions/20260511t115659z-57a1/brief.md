# Implementation Brief: better-information-ui

Session: `20260511t115659z-57a1`
Base branch: `round-20260511t114424z-3da2-spec-integration`
Integration branch: `round-20260511t115659z-57a1-integration`

## Approved Scope

Implement the accepted OpenSpec change under `openspec/changes/better-information-ui`. The work is limited to the NiceGUI web app hub path and focused tests:

- Improve the operator overview so it prioritizes readiness, live freshness, active/blocked/recent round context, priority attention target, recent actionable activity, and grouped source health.
- Normalize timeline display rows with stable `entry_id`, `sequence`, `timestamp`, `agent`, `action`, `handoff`, `reason_for_handoff`, `status`, `source`, and optional `detail`.
- Preserve distinct repeated same-agent or same-agent-pair exchanges while suppressing only exact replay duplicates with the same stable source identity.
- Move raw payloads, logs, runner output, and low-level diagnostics behind one interaction.
- Keep JSON endpoints and read-only behavior backward compatible.
- Add focused no-spend tests for normalization, duplicate preservation, concise defaults, endpoint compatibility, and responsive layout markers.

## Task Groups

### Group A: Data Model, Normalization, and JSON Compatibility

Implementer branch: `round-20260511t115659z-57a1-impl-codex`

Owned paths:

- `scripts/web_app_hub.py`
- `scripts/test-web-app-hub.py`
- `openspec/changes/better-information-ui/tasks.md`
- `.scion-ops/sessions/20260511t115659z-57a1/findings/round-20260511t115659z-57a1-impl-codex.json`

Tasks:

- Inventory the existing overview and timeline data fields.
- Add normalized timeline fields for stable identity, sequence, action, handoff, reason for handoff, status, source, and detail payload.
- Update overview data selection to expose concise readiness, priority target, recent action/handoff context, and source health fields.
- Preserve distinct repeated handoff entries; suppress only exact replay duplicates with the same stable source identity.
- Add or update no-spend fixture tests for normalization, duplicate preservation, concise overview data, JSON endpoint compatibility, and read-only refresh/live helpers.
- Update only completed task checkboxes in `openspec/changes/better-information-ui/tasks.md`.

Out of scope:

- Broad visual redesign beyond data fields needed by the UI.
- Kubernetes manifests, kind install scripts, MCP server contracts, authentication, or mutation behavior.
- Replacing the legacy raw HTML/JavaScript frontend path except narrow compatibility bridges.

### Group B: NiceGUI Rendering, Diagnostics Drill-In, and Responsive Layout

Implementer branch: `round-20260511t115659z-57a1-impl-claude`

Owned paths:

- `scripts/web_app_hub.py`
- `scripts/test-web-app-hub.py`
- `openspec/changes/better-information-ui/tasks.md`
- `.scion-ops/sessions/20260511t115659z-57a1/findings/round-20260511t115659z-57a1-impl-claude.json`

Tasks:

- Rework the NiceGUI operator overview and selected-round detail rendering to use current component patterns or structured NiceGUI-backed DOM: compact readiness strip, priority panel, recent activity rows, source health grouping, tabs/expansions/detail controls, chips/badges/tooltips where practical.
- Keep raw payloads, logs, runner output, validation detail, and diagnostic records one interaction deeper.
- Add responsive constraints so long round ids, branch refs, agent names, handoff targets, reasons, and source errors wrap inside their containers without page-level horizontal overflow.
- Add or update no-spend tests that assert the NiceGUI fragment/style/script exposes responsive layout markers and detail controls without reintroducing default raw dumps.
- Update only completed task checkboxes in `openspec/changes/better-information-ui/tasks.md`.

Out of scope:

- Changing source-of-truth adapters, Hub/MCP/Kubernetes contracts, git refs, OpenSpec source contracts, authentication, or mutation behavior.
- Reworking non-NiceGUI legacy UI except compatibility bridges required by existing endpoints or live update behavior.

## Verification Commands

Run on implementer branches as relevant:

- `python3 -m pytest scripts/test-web-app-hub.py`
- `python3 scripts/web_app_hub.py --help`
- `openspec validate better-information-ui --strict`

Run on the integration branch before final review:

- `python3 -m pytest scripts/test-web-app-hub.py`
- `openspec validate better-information-ui --strict`
- Any focused static/import check already used by the implementers, such as `python3 scripts/web_app_hub.py --help`.

No-spend expectation: tests must use fixtures and local helper functions only. Do not call external LLM APIs or mutate Hub, Kubernetes, git refs, or OpenSpec state outside the allowed task checkbox updates.
