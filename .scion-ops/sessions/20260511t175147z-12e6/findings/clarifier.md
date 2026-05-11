# Spec Clarifier Findings: make-live-1

**Session:** 20260511t175147z-12e6  
**Change:** make-live-1  
**Date:** 2026-05-11

---

## Goal (as stated)

> Remove the old UI and put the new UI live. Ensure the new UI removes old preview and non-live references.

---

## Current State

Two UIs coexist as separate Kubernetes Deployments:

| | Old UI | New UI |
|---|---|---|
| **Name** | `scion-ops-web-app` | `scion-ops-new-ui-eval` |
| **Framework** | NiceGUI (Python, server-rendered) | React + TypeScript + Vite + Python adapter |
| **Port** | 8787 / NodePort 30808 | 8080 / NodePort 30880 |
| **Entry** | `scripts/web_app_hub.py` | `new-ui-evaluation/` directory |
| **Mode env** | N/A | `NEW_UI_EVALUATION_MODE=live` |

Both are included in `deploy/kind/control-plane/kustomization.yaml`. The new UI is already running in live mode (not fixture mode) per its deployment env var.

### "Preview/non-live" references to remove

The new UI carries evaluation/preview framing throughout:
- **Directory name**: `new-ui-evaluation/`
- **Service/Deployment name**: `scion-ops-new-ui-eval`
- **Schema version strings**: `new-ui-evaluation.live.v1`, `new-ui-evaluation.fixture.v1`
- **Fixture mode**: `?fixture=1`, `?mode=fixture` URL params; `--mode fixture` CLI flag; `preview-fixtures.json`; `fixtureOnly`, `liveReadsAllowed`, `mocked` safety flags
- **Docs**: `docs/new-ui-evaluation.md` — framed as an evaluation guide
- **Test fixtures**: `src/__tests__/fixtures.test.tsx` tests fixture contract
- **OpenSpec specs**: `openspec/changes/wire-new-ui-1/` and `openspec/changes/base-framework-1/` reference "evaluation" framing

---

## Interpreted Scope

### In scope (minimum to make the new UI "live")

1. **Remove old UI from deployment** — remove `web-app-deployment.yaml` and `web-app-service.yaml` from `kustomization.yaml`. Old port 30808 goes away.
2. **Clean up new UI naming** — rename service/deployment from `scion-ops-new-ui-eval` to a permanent name (e.g. `scion-ops-web`).
3. **Remove or gate fixture mode** — strip `?fixture=1` / `--mode fixture` / fixture safety metadata from the production path. Fixture mode was scaffolding for pre-live evaluation; it should not be user-accessible in the live product.
4. **Update schema version strings** — `new-ui-evaluation.live.v1` → a non-evaluation versioned string.
5. **Update docs** — `docs/new-ui-evaluation.md` should be rewritten as the canonical UI operations guide.

### Likely out of scope (not stated, should not assume)

- Deleting `scripts/web_app_hub.py` from the codebase (vs. just removing from deployment)
- Renaming the `new-ui-evaluation/` source directory
- Changing NodePort from 30880 (unless port standardisation is part of the change)
- Removing OpenSpec history/change records

---

## Unresolved Questions for Operator

1. **Permanent service name**: What should the new UI's Kubernetes Service/Deployment be named? Options: `scion-ops-web`, `scion-ops-ui`, `scion-ops-console`, or keep a variant of current.

2. **Old UI source code**: Should `scripts/web_app_hub.py` be deleted from the repo entirely, or only removed from the deployment kustomization? (Deletion is irreversible without git history.)

3. **NodePort**: Should the new UI take over port 30808 (old UI's port), keep 30880, or is port unimportant?

4. **Fixture mode disposition**: 
   - Remove entirely from adapter and frontend (clean break)?
   - Or keep as a dev-only flag not exposed in production deployment?

5. **Schema version string**: What should replace `new-ui-evaluation.live.v1`? (e.g. `scion-ops-console.live.v1`)

6. **Directory rename**: Should `new-ui-evaluation/` be renamed to match the new permanent identity?

7. **Scope of "non-live references"**: Does this include removing the OpenSpec evaluation framing in `openspec/changes/wire-new-ui-1/` and `base-framework-1/`, or only runtime/deployment artefacts?

---

## Acceptance Criteria (draft)

- [ ] Old UI (`scion-ops-web-app`) is no longer deployed; port 30808 is no longer exposed.
- [ ] New UI is reachable and named consistently (no "eval" or "evaluation" in service/deployment names).
- [ ] No user-accessible fixture/preview mode in the live deployment (URL params and CLI flags either removed or non-functional in production).
- [ ] Schema version strings do not contain "evaluation".
- [ ] Docs reflect the new UI as the canonical, live operator console.
- [ ] `kustomization.yaml` references only the new UI resources.
- [ ] All existing tests pass against the updated naming and schema versions.
