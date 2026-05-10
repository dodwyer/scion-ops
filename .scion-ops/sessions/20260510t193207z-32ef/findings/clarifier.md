# Clarifier Findings — Session 20260510t193207z-32ef

**Change:** `use-nicegui`
**Date:** 2026-05-10

---

## Understood Intent

Replace the existing hand-written HTTP server UI (`scripts/web_app_hub.py`, ~2,500 lines of embedded HTML/CSS/JS) with a **NiceGUI**-based frontend. The new UI targets **operators** who need:

- **Primary view**: concise, action- and context-relevant information at a glance (round status, control plane health, blockers, decisions needing attention)
- **Secondary view**: in-depth troubleshooting detail one navigation level down (agent logs, decision timelines, MCP trace, terminal summaries)

The current structure is explicitly discarded — this is a greenfield implementation informed by the existing data model, not a port.

Laws of UX (https://lawsofux.com/) are to be applied as design constraints, particularly:
- **Hick's Law** — limit choices on the primary view; surface only what demands operator attention
- **Miller's Law** — chunk information (≤7 items per group) rather than flat lists
- **Doherty Threshold** — target <400 ms feedback on user interactions
- **Progressive Disclosure** — details are one level down, never on the overview
- **Aesthetic-Usability Effect** — clean, consistent visual language increases perceived reliability

---

## Confirmed Scope

| In Scope | Evidence / Assumption |
|---|---|
| New NiceGUI app replacing `web_app_hub.py` | "fresh starting point" |
| Read-only operator monitoring dashboard | existing UI is read-only; no write requirement stated |
| Round list with status (running, blocked, completed, failed) | core existing feature |
| Control plane health (Hub, Broker, MCP, Web App, k8s) | core existing feature |
| Round detail: agent timeline, decisions, consensus | core existing feature |
| Inbox / notifications | core existing feature |
| Real-time updates (NiceGUI's async push model replaces SSE polling) | NiceGUI native capability |
| Kubernetes deployment (same pod, port 8787) | existing deployment target |
| Docker image update to include NiceGUI dependency | required by new framework |

---

## Likely Non-Goals (to confirm)

1. **Write / control operations** — triggering rounds, approving decisions, sending messages to agents from the UI. Not mentioned; current UI is read-only.
2. **Mobile / responsive layout** — operator context is assumed to be a desktop browser.
3. **Multi-user sessions or auth changes** — dev-auth model is unchanged; NiceGUI will inherit the same access model.
4. **Feature parity line-for-line** — "fresh start" implies the information architecture may differ from the existing UI, not just a 1:1 port.
5. **Dark mode / theming** — not mentioned; NiceGUI's default theme is acceptable unless specified.

---

## Unresolved Questions (operator input required)

### Q1 — Primary view information hierarchy
What belongs on the **overview/landing page** vs. the **drill-down detail page**?

*Proposed default:*
- **Overview**: control plane health badges, active rounds with status pill + one-line summary, unread inbox count, any blocked/stalled rounds highlighted
- **Detail**: agent timeline, decision tree, consensus breakdown, terminal logs, MCP branch state

Is this the right split, or should rounds be further subdivided (e.g., separate views for "needing attention" vs. "running fine")?

---

### Q2 — Interactivity scope
Should the operator be able to perform **any write actions** through the new UI?

Examples that exist in the current system but are not in the current UI:
- Approving a blocked agent decision
- Sending a message to an agent
- Triggering a new round

If write operations are out of scope for v1, confirm so the data layer can be designed read-only.

---

### Q3 — Real-time update model
NiceGUI supports native async push (server → client) without polling. Should the new implementation:

a) Use NiceGUI's built-in async/await push (preferred — cleaner, no client-side JS polling)
b) Preserve the existing SSE endpoint for compatibility with other consumers (e.g., MCP server or CLI tools that may consume it)

Are there non-browser consumers of the current SSE stream that must remain?

---

### Q4 — Data layer reuse vs. rewrite
"Ignore the current structure" — does this apply to the **data-fetching layer** (HTTP calls to Hub/Broker/MCP/k8s APIs) as well as the presentation layer?

The existing `web_app_hub.py` contains significant logic for querying Scion Hub endpoints, parsing round/agent state, and normalising Kubernetes pod status. Should this logic be:

a) Extracted into a shared module and reused by the NiceGUI app (less duplication)
b) Rewritten from scratch in the new app (full fresh start, may diverge in design)

---

### Q5 — Deployment change: image and startup
NiceGUI runs via `uvicorn` (bundled). The current app uses only stdlib. The Docker image will need NiceGUI added as a dependency. Confirm:

- Should NiceGUI be pinned to a specific version, or start with latest stable?
- Is the existing port (8787) correct for the new app?
- Should the new entrypoint use `uv run` inline dependencies (consistent with other scripts) or a `requirements.txt` / `pyproject.toml` in the image?

---

### Q6 — Acceptance criteria
What defines "done" for this change?

Proposed minimum:
1. NiceGUI app deploys successfully in the kind cluster (`task x` passes)
2. Overview page loads within Doherty Threshold (<400 ms) with live control plane data
3. Round detail page is reachable from the overview in one click
4. Inbox is reachable from the overview in one click
5. Real-time updates reflect state changes without a page reload

Are there additional acceptance criteria (e.g., specific Laws of UX checked, accessibility baseline, smoke test coverage)?

---

## Risk Flags

| Risk | Severity | Notes |
|---|---|---|
| NiceGUI WebSocket requirement | Medium | NiceGUI uses WebSockets for push; confirm kind ingress/service allows WS traffic on port 8787 |
| Image size increase | Low | Adding NiceGUI + uvicorn increases image footprint; measure before finalising |
| Loss of SSE endpoint | Low-Medium | If any non-browser tools consume the current SSE stream, they will break unless the endpoint is preserved alongside the NiceGUI app |
| Fresh-start scope creep | Medium | "Ignore the current structure" risks over-engineering; implementation should be constrained to operator monitoring only |

---

## Recommended Implementation Approach (for implementer)

1. **Single new file** (e.g., `scripts/web_app.py`) replacing `web_app_hub.py`, using NiceGUI and `uv` inline dependencies
2. **Separate data module** (`scripts/hub_client.py` or similar) extracted from existing logic, shared cleanly
3. **Three primary views**: Overview, Round Detail, Inbox — navigated via NiceGUI's `ui.navigate` / page router
4. **NiceGUI async timers** for real-time refresh (replace SSE polling)
5. **Docker image** updated with NiceGUI dependency via inline `uv` script header
6. **Kubernetes manifest** updated only if entrypoint or port changes
