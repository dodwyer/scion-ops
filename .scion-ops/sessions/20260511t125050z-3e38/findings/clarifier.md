# Clarifier Findings: base-framework-1

**Session:** 20260511t125050z-3e38  
**Change:** base-framework-1  
**Date:** 2026-05-11  
**Role:** Spec Clarifier

---

## Restated Intent

Build an evaluation-ready replacement UI for scion-ops that:
- Selects and justifies a frontend framework and implementation language from first principles (not inheriting NiceGUI/Python)
- Mocks the core operator views with realistic but static data
- Runs in a separate Kubernetes pod on a different port, coexisting safely with the current UI
- Serves as the design and architecture baseline for eventual real backend wiring

---

## Current State (as observed)

| Dimension | Current |
|-----------|---------|
| Framework | NiceGUI 2.x (Python) |
| Language | Python 3.11+ |
| Port | 8787 (NodePort 30808) |
| Deployment | kustomize, namespace `scion-agents` |
| Views | Overview, Rounds list, Round detail, Inbox, Runtime |
| Data source | Hub API (live), MCP snapshots |
| Hosting | `localhost/scion-ops-mcp:latest` container |

---

## Scope Boundaries

### In scope
- Framework/language selection with written justification
- New Dockerfile for the new UI container
- Kubernetes deployment manifests (separate pod, new port)
- Mocked data contract mirroring Hub API response shapes for: rounds, agents, decisions, inbox
- Mock implementations of: Overview dashboard, Rounds list, Round detail, Inbox
- Kustomize or Helm overlay enabling both UIs to run simultaneously

### Out of scope
- Live backend wiring (Hub API, MCP, WebSocket/SSE)
- Authentication or access control
- Replacing or modifying the current NiceGUI UI
- CI/CD pipeline changes
- State-mutating operations in the UI (this is a read-only operator console)
- Migration of existing data or sessions

---

## Non-Goals

- Feature parity with the current UI before evaluation is complete
- Production-grade error handling or observability in the new UI at this stage
- Matching the visual style of the current NiceGUI UI
- Supporting multiple simultaneous users or session management

---

## Unresolved Questions (Must Resolve Before Design)

### 1. Language boundary: JS/TS frontend vs Python alternative?
The current stack is all-Python. The ask to "evaluate from first principles" implies a JS/TS SPA (React, Vue, Svelte) is fair game, but it also means introducing a new language and build toolchain into the repo.

**Question:** Is the evaluation explicitly open to a JS/TS frontend, or is there a preference to stay within Python (e.g., Streamlit, Gradio, or raw FastAPI+HTML)?

### 2. Port assignment for the new UI
The current UI is on port 8787 / NodePort 30808.

**Question:** What port (container) and NodePort should the new UI bind to? A concrete suggestion: container port 3000 / NodePort 30300. Confirm or provide an alternative.

### 3. Mock data fidelity
Two options for mock data:
- **Schema-faithful mocks** — JSON that exactly mirrors Hub API response structures, even if the field values are fabricated. This makes backend wiring a drop-in swap.
- **Illustrative mocks** — Simplified JSON shaped for the UI's needs, not necessarily Hub API-compatible. Faster to build, but requires a mapping layer later.

**Question:** Which fidelity is required? Preference is schema-faithful, but confirm.

### 4. Which views are required for the evaluation?
The current UI has five views. For an evaluation mock, not all may be necessary.

**Question:** Is the minimum viable view set: Overview + Rounds list + Round detail? Or must Inbox and Runtime also be mocked?

### 5. Coexistence mechanism
Two options:
- **Separate Kubernetes Deployment** — new pod, new Service, new NodePort. Completely independent lifecycle from the existing UI.
- **Sidecar or second container in existing pod** — shares lifecycle with current UI pod.

**Question:** Confirm the preference is a fully separate Deployment (recommended for clean evaluation isolation).

### 6. Acceptance criteria for framework selection
The deliverable includes a justification for the chosen framework. Acceptance is ambiguous without criteria.

**Question:** Who reviews the justification and on what basis is "accepted" determined? Is a written comparison matrix sufficient, or does a human operator need to sign off before implementation proceeds?

### 7. Evaluation lifespan and promotion path
Is this new UI intended to:
- a) Replace the current NiceGUI UI once validated (old UI decommissioned), or
- b) Run permanently in parallel as an optional interface?

This affects naming, port permanence, and how deep to invest in the deployment shape.

---

## Operator-Facing Acceptance Questions

These are the questions an operator reviewing this change would ask:

1. Can both UIs run simultaneously without port conflicts or resource contention?
2. Is the new UI clearly labeled as "evaluation / mocked data" to avoid confusion with live data?
3. Does the new Dockerfile follow the same build conventions as existing images (base image policy, registry, tags)?
4. Is the mock data contract documented well enough that a backend engineer can wire real data later without touching the UI?
5. Does the new deployment use the existing Kustomize/Helm patterns, or does it introduce a new deployment mechanism that operators must learn?

---

## Recommended Clarifications to Seek

Before the design phase begins, the steward should resolve questions 1, 3, and 5 above as the highest-impact blockers. Questions 2 and 4 can default to reasonable values (port 3000/30300; schema-faithful mocks) if no response is received.
