# Clarifier Findings: wire-new-ui-1

**Session:** 20260511t151636z-0bbd  
**Change:** wire-new-ui-1  
**Base branch:** main  
**Date:** 2026-05-11

---

## 1. Stated Intent

Wire the existing React/Vite evaluation UI (`new-ui-evaluation/`) to live operational data using push-based delivery (SSE or WebSocket), replacing the current fixture-only mock data layer. The UI should display real Hub, MCP, Kubernetes, Git, and OpenSpec state with initial snapshots followed by incremental live updates.

---

## 2. Current State (as-built by base-framework-1)

| Component | Location | Notes |
|-----------|----------|-------|
| React/Vite UI | `new-ui-evaluation/src/` | 6 views: Overview, Rounds, Round Detail, Inbox, Runtime, Diagnostics |
| Python adapter | `new-ui-evaluation/adapter.py` | Simple `BaseHTTPRequestHandler`, port 8091, 8 GET-only routes |
| Fixture data | `new-ui-evaluation/fixtures/preview-fixtures.json` | ~1000 lines of typed JSON, schema `new-ui-evaluation.fixture.v1` |
| Data fetch | `new-ui-evaluation/src/api.ts` | `Promise.all()` of parallel GET fetches, no streaming |
| Safety flags | `adapter.py` healthz route | `fixtureOnly: true`, `liveReadsAllowed: false`, `mutationsAllowed: false` |

**No SSE, WebSocket, or live data clients exist anywhere in the stack today.**

---

## 3. Scope — In

- Replace fixture responses with live data fetched by the adapter from real sources
- Add a server-sent events (SSE) or WebSocket stream endpoint to the adapter for push delivery
- Browser-side: replace `Promise.all` polling/fetch pattern with event-stream subscription
- Initial-snapshot-plus-incremental-update pattern (subscribe → receive snapshot → receive deltas)
- Per-source staleness and connection health indicators surfaced in the Runtime and Diagnostics views
- Graceful reconnect with exponential backoff on stream disconnect
- Stale-data visual indicators when no fresh event has arrived within configurable thresholds
- Safety boundary preserved: adapter remains read-only; `mutationsAllowed: false` unchanged
- Fixture-mode retained as an explicit opt-in fallback (e.g., `FIXTURE_MODE=true` env var) for development and CI without live sources

**Data sources in scope for live wiring:**
1. **Hub** — control-plane state (rounds, agents, sessions)
2. **MCP** — tool/service status
3. **Kubernetes** — workload/pod/namespace state
4. **Git** — branch, commit, HEAD state
5. **OpenSpec** — change definitions and task state

---

## 4. Scope — Out (Non-Goals)

- Mutations via the UI or adapter (POST/PUT/PATCH/DELETE remain 405)
- Changes to the existing (non-evaluation) UI or its data paths
- Cross-UI data sharing or a shared backend between old and new UI
- Authentication/authz enforcement at the UI layer (adapter runs in-cluster; network boundary is the control)
- Real-time collaborative features (multi-user presence, conflict resolution)
- Historical replay or time-travel queries
- Alerting, notification delivery, or outbound webhooks from the adapter
- Changes to OpenSpec change definitions for any source system

---

## 5. Unresolved Questions (must be answered before implementation begins)

### 5.1 Push Mechanism
**Q:** SSE or WebSocket?  
SSE is simpler (HTTP/1.1, native browser `EventSource`, no library, unidirectional) and sufficient for read-only push. WebSocket adds bidirectional capability not needed here.  
**Recommended:** SSE unless a specific bidirectionality requirement emerges.  
**Operator must confirm or redirect.**

### 5.2 Adapter Language / Runtime
**Q:** The current adapter is Python `BaseHTTPRequestHandler` (single-threaded request/response). SSE requires long-lived connections and concurrent streaming.  
Options:  
- **A) Extend Python** with `ThreadingHTTPServer` (already used) and chunked transfer encoding — low friction, matches existing stack.  
- **B) Rewrite adapter in Node.js/TypeScript** — natural fit for the React/Vite repo, native async streaming, but adds a runtime dependency.  
- **C) Add a thin Go binary** alongside adapter.py — performant, single binary, but third runtime in the repo.  
**Operator must choose runtime.**

### 5.3 Adapter as Aggregator vs. Browser-Direct
**Q:** Should the adapter aggregate all source data server-side and push a unified event stream to the browser? Or should the browser connect directly to some sources (e.g., a Hub WebSocket)?  
**Recommended:** Adapter as aggregator — keeps CORS/auth complexity out of the browser and maintains the existing clean separation.  
**Operator must confirm.**

### 5.4 Update Triggers and Frequency
**Q:** What triggers a push event to connected browsers?  
Options:  
- **Poll-on-server**: adapter polls each source on a configurable interval (e.g., every 5s) and pushes diffs  
- **Source-native push**: subscribe to Hub/MCP native event streams and relay  
- **Hybrid**: poll slow sources, relay fast ones  
**Operator must specify per-source trigger model and acceptable latency.**

### 5.5 Staleness Thresholds
**Q:** What age (seconds) makes data "stale" for each source? The fixtures currently show MCP at 310s (degraded) and Git at 1820s (stale), but these are not defined as thresholds.  
**Operator must define per-source stale thresholds** (or confirm a single global default is acceptable).

### 5.6 Fixture Fallback Behaviour
**Q:** When a live source is unavailable, should the adapter:  
- **A)** Return stale cached data with a staleness indicator  
- **B)** Return an error event so the UI shows "source offline"  
- **C)** Fall back to fixture data for that source  
**Recommended:** A (stale cache) for transient outages, B (error event) after a configurable timeout.  
**Operator must confirm failure semantics.**

### 5.7 Hub API Access
**Q:** How does the adapter authenticate to the Hub API from within the cluster? Is there a service account, token mount, or in-cluster DNS endpoint?  
**Operator must provide Hub API access method** (endpoint, auth mechanism).

### 5.8 Kubernetes Client Access
**Q:** Does the adapter run inside the cluster (in-cluster kubeconfig) or outside (local kubeconfig mount)?  
**Operator must confirm deployment context** for K8s client initialisation.

### 5.9 Scope of UI Changes
**Q:** Does this change touch only data plumbing (`api.ts`, `adapter.py`), or does it also require new UI components (e.g., a connection status banner, staleness badge)?  
The task description mentions "connection health/staleness indicators" — these likely require new React components.  
**Operator must confirm whether UI component changes are in scope.**

### 5.10 Deployment: Dev vs. Production Path
**Q:** Is the live-data adapter intended to run:  
- Only in local dev (via `npm run dev` proxy to `:8091`)  
- Only in-cluster (Kubernetes deployment)  
- Both  
This affects whether the Vite dev proxy config and Kubernetes manifests both need updating.  
**Operator must confirm target deployment contexts.**

---

## 6. Acceptance Criteria (draft — requires operator confirmation)

1. Navigating to any view in the new UI shows live operational data, not fixture values, within a configurable initial load timeout.
2. Data updates pushed by the adapter appear in the UI without a page reload.
3. If the stream disconnects, the UI reconnects automatically with backoff and displays a "reconnecting" indicator.
4. Each data source in the Runtime view shows a freshness timestamp and a staleness indicator when data exceeds its threshold.
5. With `FIXTURE_MODE=true`, the adapter reverts to fixture data (existing behaviour preserved).
6. All adapter endpoints remain GET-only; POST/PUT/PATCH/DELETE still return 405.
7. The existing UI (non-evaluation) is unmodified.
8. `npm run typecheck` and `npm test` pass after changes.

---

## 7. Recommended Clarification Recipients

The following questions from §5 are blockers for implementation and should be answered by the operator before an implementation spec is written:

| # | Question | Blocker? |
|---|----------|---------|
| 5.1 | SSE vs WebSocket | Yes |
| 5.2 | Adapter runtime | Yes |
| 5.3 | Adapter-as-aggregator | Yes |
| 5.4 | Update triggers + frequency | Yes |
| 5.5 | Staleness thresholds | Yes |
| 5.6 | Fixture fallback behaviour | Yes |
| 5.7 | Hub API auth | Yes |
| 5.8 | Kubernetes client context | Yes |
| 5.9 | UI component scope | Yes |
| 5.10 | Dev vs production deployment | Yes |
