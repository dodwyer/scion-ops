# Web App Hub JSON Contract

The read-only web app exposes MCP-aligned state through `/api/snapshot`,
`/api/rounds`, `/api/rounds/<round_id>`, `/api/inbox`, and `/api/runtime`.
Structured Hub and MCP fields are authoritative. Fallback values derived from
older message text are marked with `fallback`, `fallback_derived`, or an
equivalent source field and do not override structured fields.

## Round Fields

- `round_id`: normalized round id without a leading `round-`.
- `status`: operational status such as `running`, `waiting`, `completed`, or
  `blocked`.
- `visible_status`: operator-facing status. Final-review, validation, blocker,
  and protocol states can refine this value without collapsing blocked outcomes
  to completed.
- `phase`, `agent_count`, `message_count`, `notification_count`,
  `latest_update`, `latest_summary`, `outcome`.
- `branches`: branch refs from structured Hub/MCP fields first, then fallback
  message text only when no structured branch exists.
- `branch_source`: `structured`, `fallback`, or empty.
- `spec_progress`: MCP spec-round fields including `expected_branch`,
  `pr_ready_branch`, `remote_branch_sha`, `base_branch_sha`, `branch_changed`,
  `validation_status`, `validation`, `protocol`, `blockers`, `warnings`,
  `project_root`, `change`, and `base_branch`.
- `artifacts`: normalized `scion_ops_round_artifacts` data with local branches,
  remote branches, remote SHA evidence, workspaces, and prompt paths.
- `final_review`: normalized final-review data including `verdict`,
  `normalized_verdict`, `display`, `status`, `summary`, `branch`,
  `blocking_issues`, `source`, `time`, and `fallback_derived`.

## Event Fields

Round detail preserves MCP `scion_ops_round_events` output under `events`,
including `cursor`, `changed`, `progress_lines`, `terminal`, and raw `events`.
The browser-facing `timeline` is a compact rendering of the same event list with
`type`, `time`, `summary`, and `raw`.

## Validation Fields

OpenSpec validation payloads from `scion_ops_spec_status` and
`scion_ops_validate_spec_change` normalize to `status` (`passed` or `failed`),
`ok`, `source`, `project_root`, `change`, `errors`, `validation`, and
`openspec_status` when present.

## Runtime Fields

`sources` contains separate entries for `hub`, `broker`, `mcp`, `web_app`,
`kubernetes`, `messages`, and `notifications`. Readiness requires Hub, broker,
MCP, Kubernetes, and the deployed web app to be healthy; source-specific errors
remain attached to their source instead of blanking the full snapshot.
