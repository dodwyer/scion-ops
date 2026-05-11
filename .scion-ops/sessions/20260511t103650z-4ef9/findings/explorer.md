# Explorer Findings: better-information-ui

## Scope Read

Goal: improve the Operator overview and selected-round timeline so the visible information is relevant and formatted around action, handoff, and reason-for-handoff; allow repeated entries per agent for back-and-forth handoffs; refresh the implementation to use current NiceGUI elements; verify desktop and mobile rendering without overspill.

## Lowest-Risk OpenSpec Targets

Use a new OpenSpec change for this work instead of editing archived/implemented deltas directly. The existing active/current spec surface to modify is the `web-app-hub` capability.

Recommended files:

- `openspec/changes/<change-id>/proposal.md`
- `openspec/changes/<change-id>/design.md`
- `openspec/changes/<change-id>/tasks.md`
- `openspec/changes/<change-id>/specs/web-app-hub/spec.md`

Lowest-risk requirement deltas to add/modify:

- Add or modify `Requirement: Operator Overview` to require concise, relevant operator state instead of broad diagnostic dumping.
- Modify `Requirement: Round Detail Timeline` to require an operator-facing exchange timeline whose primary fields are `action`, `handoff`, and `reason_for_handoff`.
- Add a focused requirement such as `Requirement: Handoff Exchange Timeline` if the author wants to keep the timeline behavior distinct from generic messages/notifications.
- Modify or extend `Requirement: NiceGUI Frontend` / `Requirement: NiceGUI Responsive Operator Layout` to require use of first-class NiceGUI components for layout, tabs/rows/tables/expansion/detail panes where practical, with desktop and narrow mobile viewport checks.

Existing relevant specs already present:

- `openspec/changes/use-nicegui/specs/web-app-hub/spec.md` already requires a NiceGUI overview, progressive troubleshooting, source-of-truth preservation, read-only behavior, and responsive desktop/mobile layout.
- `openspec/changes/web-ui-theme/specs/web-app-hub/spec.md` already requires restrained operational theme, semantic status styling, dense readable layout, and responsive usability.
- `openspec/changes/autorefresh-web-app/specs/web-app-hub/spec.md` already requires live round detail timeline updates and duplicate/replayed update suppression.
- `openspec/changes/update-web-app/specs/web-app-hub/spec.md` already requires MCP-aligned structured fields and final-review semantics.
- `openspec/changes/build-web-app-hub/specs/web-app-hub/spec.md` is the baseline for overview, round progress, round detail timeline, inbox, source-of-truth, and read-only interface.

## Implementation Choke Points

The current implementation is mostly in `scripts/web_app_hub.py`.

- `timeline_entry()` at `scripts/web_app_hub.py:1213` normalizes message/notification/agent events into a generic `summary` plus metadata. This is the lowest-risk backend point to add explicit `action`, `handoff`, and `reason_for_handoff` fields while preserving existing `summary`, `raw`, id, time, source, and agent metadata.
- `build_decision_flow()` at `scripts/web_app_hub.py:688` groups timeline entries by agent/role and de-duplicates events through `add_flow_event()`. The new behavior should be careful not to collapse legitimate repeated handoff exchanges. If duplicate suppression remains, identity should include the source event id and handoff fields so back-and-forth entries survive.
- `build_round_detail()` at `scripts/web_app_hub.py:1959` is where round status, events, artifacts, final review, timeline, decision flow, operator summary, agent matrix, and runner output are assembled. This is the right integration point for a new `handoff_timeline` or enriched `timeline` contract.
- The current visible selected-round timeline rendering is old HTML string assembly inside `renderRoundDetail()` at `scripts/web_app_hub.py:2700`, with raw timeline hidden in a `<details>` block. This is likely why the page still feels like the old design even though the entrypoint is NiceGUI.
- `build_nicegui_console_components()` at `scripts/web_app_hub.py:2781` currently creates only a NiceGUI shell/header/sections; most content is still injected by JavaScript into section HTML. A spec should push implementation toward real NiceGUI components for the main layout and controls while preserving current JSON/live contracts.

## Contract Constraints To Preserve

- Keep JSON and health route compatibility: `/api/snapshot`, `/api/rounds`, `/api/rounds/{round_id}`, `/api/rounds/{round_id}/events`, `/api/live`, `/api/stream`, `/api/runtime`, `/api/inbox`, `/healthz`, `/api/healthz`.
- Preserve read-only behavior. The UI and live update paths must not start, abort, retry, archive, mutate Kubernetes resources, write git refs, or change OpenSpec files.
- Continue deriving state from structured Hub, MCP, Kubernetes, artifact, validation, final-review, blocker, warning, and branch fields before falling back to message prose.
- Preserve live update semantics: automatic updates, cursor resume, stale/fallback/failed status, source-specific error handling, and no full page reload for selected round updates.
- Preserve existing duplicate/replay protection for actual repeated live events, but do not dedupe distinct handoff exchanges merely because they involve the same agent pair or similar text.
- Keep final-review statuses such as blocked, failed, revise, request changes, and accepted visible as structured operator status, not generic completion.
- Keep desktop layout dense and readable, with no horizontal overspill; narrow/mobile layout should wrap or stack metadata/action controls and keep round id, status, action, handoff, reason, timestamp, and agent visible.

## Suggested Spec Acceptance Criteria

- Overview default view shows only relevant operator state: current action, next inspection target, blocked/degraded source or round, and latest meaningful update. Raw payloads/logs stay one interaction level down.
- Selected round detail exposes a handoff/exchange timeline sorted chronologically or reverse-chronologically with stable rows containing at least: time, actor/agent, role, action, handoff target or handoff description, reason for handoff, status/outcome, and source.
- Multiple handoff entries for the same agent are visible when the backing events represent a back-and-forth exchange.
- Generic lifecycle noise such as started/idle/offline/running does not dominate the primary timeline unless no meaningful action/handoff entries exist.
- The frontend uses NiceGUI components for the primary app shell and selected-round/operator surfaces, with older injected HTML limited to compatibility only if unavoidable.
- Desktop and mobile viewport verification is required, including a check for horizontal overflow/overspill on overview and round detail.

## Test Targets

Existing tests are in `scripts/test-web-app-hub.py`.

Add focused tests for:

- `timeline_entry()` or a new normalization helper extracting/preserving `action`, `handoff`, and `reason_for_handoff` from structured event payloads.
- Round detail JSON containing a handoff/exchange timeline and preserving duplicate same-agent back-and-forth entries with distinct source ids.
- Frontend markers proving the primary selected-round timeline renders action/handoff/reason labels instead of only generic summary text.
- NiceGUI entrypoint/component tests proving the implementation no longer relies solely on the old JavaScript-injected detail layout for the primary operator surfaces.
- Responsive/static rendering checks, ideally via existing no-spend web app tests or a lightweight browser/screenshot check, to catch horizontal overflow on desktop and narrow mobile widths.

## Risk Notes

- The biggest behavioral risk is changing dedupe logic too broadly. Keep replay/idempotency protection keyed to stable source ids while allowing distinct source ids from the same agent to render separately.
- The biggest UI risk is mixing first-class NiceGUI components with the current JavaScript live-update machinery. Preserve backend contracts first, then migrate visible surfaces incrementally.
- The safest implementation path is backend contract enrichment first, tests second, then UI rendering changes. Avoid changing MCP/Hub source contracts unless a structured field is already available.
