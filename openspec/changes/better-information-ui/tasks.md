# Tasks

- [x] 1.1 Inventory current operator overview and selected-round timeline fields in `scripts/web_app_hub.py`, including noisy or irrelevant default details.
- [x] 1.2 Define normalized timeline entry fields for stable identity, sequence, action, handoff, reason for handoff, status, source, and detail payload.
- [x] 1.3 Update overview data selection so default content emphasizes readiness, priority attention target, recent action/handoff context, and source health.
- [x] 1.4 Update selected-round timeline normalization so action, handoff, and reason-for-handoff are explicit display fields when source data supports them.
- [x] 1.5 Preserve distinct repeated handoff entries involving the same agent or same agent pair; only suppress exact replay duplicates with the same stable source identity.
- [x] 1.6 Move raw payloads, long logs, runner output, and low-level diagnostics behind one-level-deeper NiceGUI controls.
- [x] 1.7 Rework overview and round detail rendering with current NiceGUI components for tables or row lists, tabs, expansions, chips or badges, tooltips, and responsive containers.
- [x] 1.8 Keep the legacy raw HTML/JavaScript path out of scope except for narrow endpoint or compatibility bridges required by existing contracts.
- [x] 1.9 Verify desktop rendering has no page-level horizontal overflow, overlapping controls, or clipped key timeline fields with representative long data.
- [x] 1.10 Verify mobile rendering preserves navigation, overview summary, selected round context, and timeline action/handoff/reason fields without overspill.
- [x] 1.11 Add focused no-spend tests or fixtures for normalization, duplicate preservation, concise defaults, endpoint compatibility, and responsive layout checks.
- [x] 1.12 Run OpenSpec validation for this change.
- [x] 1.13 Run relevant web app static checks and fixture tests after implementation.
