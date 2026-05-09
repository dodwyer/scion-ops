# Web App JSON Contract

This document defines the browser-facing JSON contract for the read-only
scion-ops web app. It is an operator/developer contract for the current MCP and
Hub structured fields consumed by the browser; it does not define mutating web
app operations.

Structured MCP, Hub, and Kubernetes fields are authoritative. Values recovered
from message text, notification text, task summaries, agent names, or slugs are
fallback values only and must be marked as fallback in the browser model.

## Endpoints

- `GET /api/snapshot` returns the full dashboard snapshot.
- `GET /api/overview` returns `snapshot.overview`.
- `GET /api/rounds` returns `{ "rounds": snapshot.rounds }`.
- `GET /api/rounds/{round_id}` returns one round detail snapshot.
- `GET /api/rounds/{round_id}/events?cursor=...` returns the MCP event delta.
- `GET /api/inbox` returns `{ "inbox": snapshot.inbox }`.
- `GET /api/runtime` returns `{ "sources": snapshot.sources }`.

All timestamps are ISO-8601 strings when the source provides parseable time.
Unknown values are represented as empty strings, empty arrays, empty objects, or
`unknown` status strings rather than omitted fields where the frontend needs a
stable shape.

## Snapshot

`/api/snapshot` returns:

```json
{
  "ok": true,
  "generated_at": "2026-05-09T21:36:33+00:00",
  "stale_after_seconds": 90,
  "stale": false,
  "readiness": "ready",
  "sources": {},
  "overview": {},
  "rounds": [],
  "inbox": []
}
```

- `ok`: true when any source returned usable data.
- `readiness`: `ready`, `degraded`, or `unavailable`.
- `stale`: true when the newest round update is older than
  `stale_after_seconds`.
- `sources`: source health records for `hub`, `broker`, `mcp`, `kubernetes`,
  `messages`, and `notifications`.

## Source Health

Every source health record uses the same envelope:

```json
{
  "source": "hub_api",
  "ok": true,
  "status": "healthy"
}
```

Error records add:

```json
{
  "ok": false,
  "status": "degraded",
  "error_kind": "hub_auth",
  "error": "..."
}
```

`status` is `healthy`, `degraded`, or `unavailable`. `error_kind` must preserve
the source-specific category from the adapter or MCP result, such as `hub_auth`,
`hub_status`, `round_events`, `runtime`, `mcp_unavailable`, or
`openspec_validator`. If MCP is unreachable, MCP-specific fields are degraded
with the MCP error category while Hub and Kubernetes data continue to render.

## Rounds

Each `snapshot.rounds[]` row summarizes a round from Hub agents, messages,
notifications, and MCP `scion_ops_round_status` outcome data:

```json
{
  "round_id": "20260509t213633z-native3",
  "agents": [],
  "messages": [],
  "notifications": [],
  "branches": ["round-20260509t213633z-native3-impl-contract-doc"],
  "branch_source": "structured",
  "latest_update": "2026-05-09T21:40:00Z",
  "latest_summary": "complete: ...",
  "status": "blocked",
  "visible_status": "changes requested",
  "phase": "running",
  "outcome": "...",
  "final_review": {},
  "agent_count": 4,
  "message_count": 12,
  "notification_count": 3
}
```

- `status`: normalized round state such as `running`, `waiting`, `completed`,
  `blocked`, `observed`, or `unknown`.
- `visible_status`: display status. A structured final-review verdict may make
  this `accepted`, `changes requested`, or `blocked`.
- `branches`: branch refs from structured fields first. Structured branch field
  names include `branch`, `target_branch`, `head_branch`, `source_branch`,
  `pr_ready_branch`, `integration_branch`, and `final_branch`.
- `branch_source`: `structured` when branches came from structured MCP/Hub
  fields, `fallback` when parsed from prose/name fields, or empty when no branch
  evidence is available.
- `final_review`: latest normalized final-review record when present.

Fallback branch values must never override structured branch evidence.

## Round Detail

`/api/rounds/{round_id}` returns:

```json
{
  "ok": true,
  "round_id": "20260509t213633z-native3",
  "status": {},
  "events": {},
  "timeline": [],
  "runner_output": "",
  "runner_output_error": "",
  "outcome": {},
  "final_review": {},
  "visible_status": "blocked",
  "branches": [],
  "branch_source": "structured"
}
```

- `status`: raw `scion_ops_round_status` result, including `progress`,
  `terminal`, `outcome`, `agents`, and optional `consensus_transcript`.
- `events`: raw `scion_ops_round_events` result with cursor and counts.
- `timeline`: browser-ready event list sorted by time.
- `outcome`: structured MCP outcome from round status or events.
- `branches` and `branch_source`: same precedence rules as round rows.

`timeline[]` entries have:

```json
{
  "type": "message",
  "time": "2026-05-09T21:41:00Z",
  "summary": "operator-readable summary",
  "raw": {}
}
```

`raw` preserves the original Hub message, notification, or agent record for
operator inspection.

## Event Cursor And Timeline

`/api/rounds/{round_id}/events` directly exposes the MCP
`scion_ops_round_events` or `scion_ops_watch_round_events` shape:

```json
{
  "ok": true,
  "source": "hub_api",
  "round_id": "20260509t213633z-native3",
  "summary": "round ... running",
  "progress_lines": [],
  "changed": true,
  "events": [],
  "cursor": "...",
  "outcome": {},
  "terminal": {},
  "agent_count": 4,
  "message_count": 12,
  "notification_count": 3,
  "commands_ok": {}
}
```

Clients pass the returned `cursor` on the next poll. `changed` describes whether
new events were returned for that cursor. `terminal` is a structured terminal
status when MCP detects one; the UI must not collapse blocked terminal outcomes
into generic completion.

## Artifact Branch Evidence

When the backend includes `scion_ops_round_artifacts` or
`scion_ops_run_spec_round.artifacts`, preserve these fields:

```json
{
  "source": "local_git",
  "project_root": "/workspace",
  "branches": ["round-..."],
  "remote_branches": [
    { "branch": "round-...", "sha": "abc123..." }
  ],
  "workspaces": [],
  "prompts": [],
  "branch_result": {},
  "remote_url_result": {},
  "remote_primary_result": {},
  "remote_fallback_result": {},
  "remote_branch_result": {}
}
```

`remote_branches[].sha` is the remote branch evidence. If
`remote_fallback_result` is populated, it is fallback transport evidence for a
remote read attempt and should be surfaced as degraded/fallback source context,
not as a replacement for structured `remote_branches`.

## OpenSpec Status And Validation

`scion_ops_spec_status` fields relevant to the browser are:

```json
{
  "ok": true,
  "source": "local_git",
  "project_root": "/workspace",
  "changes_path": "openspec/changes",
  "changes": [],
  "archive_path": "openspec/changes/archive",
  "archived_changes": [],
  "change": "update-web-app",
  "validation": {},
  "validation_result": {},
  "openspec_status": {},
  "openspec_status_result": {}
}
```

`scion_ops_validate_spec_change` returns the same validation payload under
`validation`, with command status fields from the validator result. The browser
must preserve `ok`, `source`, `change`, validation errors, and command output
metadata so operators can distinguish failed validation from unavailable
validation.

For `scion_ops_run_spec_round`, preserve these spec-round progress fields when
present in direct responses, stored messages, or notifications:

```json
{
  "status": "blocked",
  "health": "blocked",
  "expected_branch": "round-...-spec-integration",
  "pr_ready_branch": "",
  "remote_branch_sha": "",
  "base_branch_sha": "abc123...",
  "branch_changed": false,
  "validation_status": "failed",
  "validation": {},
  "protocol": {
    "integration_branch_valid": false,
    "ops_review_agent_count": 1,
    "ops_review_complete": true,
    "finalizer_agent_count": 0,
    "finalizer_complete": false,
    "complete": false
  },
  "blockers": ["OpenSpec validation failed on the remote branch"],
  "warnings": [],
  "cursor": "...",
  "watch": {}
}
```

`validation_status` values include `pending`, `passed`, `failed`, and
`skipped`. Missing expected branches, unchanged remote branches, failed
validation, incomplete protocol milestones, or timeout blockers should render as
degraded or blocked state.

## Final Review

Final-review records appear at `round.final_review`,
`round_detail.final_review`, or inside `outcome.final_review`:

```json
{
  "source": "final_review_message",
  "time": "2026-05-09T21:42:00Z",
  "verdict": "changes_requested",
  "normalized_verdict": "request_changes",
  "status": "blocked",
  "display": "changes requested",
  "summary": "review summary",
  "branch": "round-...",
  "blocking_issues": []
}
```

Supported normalized verdicts are:

- `accept`: display `accepted`, status `accepted`.
- `request_changes`: display `changes requested`, status `blocked`.
- `blocked`: display `blocked`, status `blocked`.

Only structured final-review verdicts, normalized verdicts, source summaries,
and blocking issue lists may drive accepted or blocked final-review display.
Fallback text can identify older final-review messages but must not override a
structured verdict.

## Inbox

`snapshot.inbox[]` groups messages and notifications by round:

```json
{
  "round_id": "20260509t213633z-native3",
  "latest_update": "2026-05-09T21:43:00Z",
  "items": [
    {
      "type": "message",
      "time": "2026-05-09T21:43:00Z",
      "source_id": "agent-or-message-id",
      "summary": "...",
      "raw": {}
    }
  ]
}
```

Spec-round progress messages should expose structured fields from their `raw`
payload when available, including blockers, warnings, validation status,
expected branch, PR-ready branch, protocol state, and remote branch evidence.
