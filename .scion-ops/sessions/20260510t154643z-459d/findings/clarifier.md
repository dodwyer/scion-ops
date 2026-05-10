# Spec Clarifier Findings — web-app-2

**Session:** 20260510t154643z-459d
**Change:** web-app-2
**Date:** 2026-05-10
**Recommended change name:** `web-app-2-live-feed-ui`

---

## Goal Summary

Upgrade the scion-ops web app hub from a polling-based, vanilla-JS dashboard to a **push-driven, professionally styled operator UI** where new data surfaces at the top of feeds without page reloads. Alternative languages and frontend frameworks are explicitly permitted.

---

## Current State

The app is a single-file Python HTTP server (`scripts/web_app_hub.py`, ~2,100 lines) serving vanilla HTML/JS/CSS. It already exposes a `/api/live` SSE endpoint and a cursor-based long-poll fallback, but the frontend uses 15-second snapshot polling (`/api/snapshot`) as its primary update mechanism. The UI has four tabbed views: Overview, Rounds, Inbox, and Runtime.

---

## Interpreted Scope

### In scope
1. **Live push delivery to the frontend** — wire the existing `/api/live` SSE stream (or replace with WebSocket) so the browser receives updates without polling. Remove or demote the 15s snapshot poll.
2. **Newest-first feed ordering** — Rounds and Inbox views should prepend incoming items at the top rather than requiring a refresh or full re-render. Round events timeline may append at bottom (chronological is natural there).
3. **Professional operator UI** — Replace the current bespoke CSS/HTML with a proper frontend framework and design system. Target: dense data tables, clear status indicators, dark-friendly palette, consistent typography. Examples of acceptable stacks: React + shadcn/ui, Vue + PrimeVue, Svelte + a component library.
4. **Framework/language change permitted** — The Python backend can stay as-is (its API surface is clean), or be rewritten. The frontend stack is open; the only constraint is the existing REST+SSE API contract documented at `/api/contract`.

### Out of scope
- Adding write/action capabilities (the app is intentionally read-only).
- Changes to the MCP server, Kubernetes deployment logic, or data-source adapters.
- Altering the `/api/*` endpoint surface or data shapes (unless the implementer finds a specific blocker).
- Authentication or RBAC.

---

## Assumptions

1. **Backend API stays stable** — The implementer may change the server language/framework but must preserve the documented API contract. The frontend rewrite should target the existing endpoints.
2. **SSE is the preferred push mechanism** — WebSocket is acceptable if there is a clear reason, but SSE aligns with the existing `/api/live` design.
3. **"Professional operator UI"** means: high information density, minimal decorative chrome, dark theme preferred, keyboard-navigable tables, and clear colour-coded status badges — consistent with tooling like Grafana, ArgoCD, or Lens.
4. **Newest-first applies to Rounds and Inbox** — The Overview cards and Runtime debug view can remain static / last-updated.
5. **The rewrite is a full replacement**, not an incremental patch on top of the 2,100-line monolith. The existing file becomes the reference implementation.

---

## Unresolved Questions

| # | Question | Impact |
|---|----------|--------|
| 1 | **Dark theme required or optional?** Should the UI default to dark, follow system preference, or offer a toggle? | Low — but should be decided before design work starts |
| 2 | **Specific frontend framework preference?** React, Vue, Svelte, or something else? "Alternative frameworks allowed" leaves this fully open. | High — drives the entire build toolchain choice |
| 3 | **Backend language change?** Is there a desire to rewrite the Python server (e.g. to Go or Node for better SSE/WS performance), or is Python kept and only the frontend changes? | High — determines if this is a frontend-only or full-stack effort |
| 4 | **Round detail / drill-down view?** The current UI has a rounds table but clicking a row does not navigate to a detail page. Should the new UI add a round detail view? | Medium — out of scope if not mentioned, but likely desired for "operator focused" |
| 5 | **Deployment packaging** — should the new frontend be bundled into the same Python container, or split into a separate static-asset container? | Medium — affects the Kubernetes deployment manifest |
| 6 | **Does "push content" include real-time agent log streaming**, or only round/status-level updates? | Low — log streaming would be a significant scope increase |

---

## Recommended Next Steps

1. Get answers to questions 2 and 3 (framework + backend language) before implementation starts — they determine the scaffold.
2. Treat the existing `/api/contract` response as the canonical interface spec.
3. Implement as a parallel build (new directory, new Dockerfile target) so the old app stays runnable until the new one is validated.
