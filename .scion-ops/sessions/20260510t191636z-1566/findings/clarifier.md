# Clarifier Findings: holly-ops-branding

**Session:** 20260510t191636z-1566  
**Change:** holly-ops-branding  
**Date:** 2026-05-10

---

## Understood Intent

Rename the user-facing product experience from **scion-ops** to **Holly Ops**, with:
- The web UI (browser hub) renamed to **Holly Ops Drive** (abbreviated **HHD**)
- The operator-facing coordinator/bot persona renamed to **Holly**
- Underlying Scion runtime primitives (Hub, broker, agents, MCP, templates, steward sessions) left unchanged
- A low-risk, user-facing-first approach: Kubernetes resource names, MCP tool names, and `.scion-ops/` session state paths **preserved** unless a migration plan is explicitly specified

---

## What Exists Today

The codebase uses `scion-ops` consistently as a lowercase product name across:

| Layer | Current Name | Rename Target |
|---|---|---|
| README.md title | `# scion-ops` | `# Holly Ops` |
| Web UI display text (web_app_hub.py) | "scion-ops" labels | "Holly Ops Drive" |
| Python MCP server init name | `"scion-ops"` (FastMCP) | "holly-ops" or "holly"? |
| Zed context server label | `"scion-ops"` | "holly-ops"? |
| Kind cluster name | `scion-ops` | preserve (infra) |
| Kind context name | `kind-scion-ops` | preserve (infra) |
| K8s resource names | `scion-ops-mcp`, `scion-ops-web-app` | preserve (per spec) |
| K8s label `part-of` | `scion-control-plane` | preserve |
| MCP tool names | `scion_ops_*` | preserve (per spec) |
| Docker image dir | `image-build/scion-ops-mcp/` | preserve or rename? |
| `.scion-ops/` session paths | `.scion-ops/sessions/…` | preserve (per spec) |
| Docs referencing "scion-ops web UI" | multiple | update to "Holly Ops Drive" |

There is no existing "Holly" or "Holly Ops" branding anywhere in the codebase.

---

## Scope Boundaries (Proposed)

### In scope (user-facing, low-risk)
- `README.md` — title and product description prose
- `scripts/web_app_hub.py` — all display text, page titles, section headings visible in the browser UI
- `docs/` — any mention of "scion-ops" used as a product/UI label (not runtime path references)
- `openspec/changes/*/proposal.md` — product-name references in specs

### Out of scope (preserved, per spec)
- All Kubernetes resource names and labels (`scion-ops-mcp`, `scion-ops-web-app`, `scion-hub`, `scion-broker`)
- All MCP tool function names (`scion_ops_*`)
- `.scion-ops/` directory structure and session state paths
- Kind cluster/context names (`scion-ops`, `kind-scion-ops`)
- Scion runtime primitives (Hub, broker, agents, templates, steward)

### Unclear / needs decision (see questions below)
- Docker image directory `image-build/scion-ops-mcp/` and Dockerfile labels
- Zed context server name in `.zed/settings.json`
- FastMCP server `name=` parameter in `mcp_servers/scion_ops.py`
- Python file and module name `mcp_servers/scion_ops.py`

---

## Operator-Facing Acceptance Questions

**Q1 — Abbreviation discrepancy:** The spec names the web UI "Holly Ops Drive" but abbreviates it **HHD**. "Holly Ops Drive" would naturally abbreviate to **HOD**. Is HHD intentional (e.g. does it stand for something else, like "Holly Hub Drive"), or should the abbreviation be HOD?

**Q2 — "Holly" persona scope:** The spec says Holly is "the operator-facing bot/coordinator that conducts actions." In the current codebase the coordinator role is played by the MCP server (`scion_ops.py`) and steward agents. Should "Holly" be:
  - (a) A display-name-only rebrand of the existing MCP/steward layer (no code restructuring), or
  - (b) A new named persona/agent in the UI that wraps or presents the steward session?

**Q3 — MCP server identity:** The FastMCP server is initialized with `name="scion-ops"`. This name may appear in MCP client discovery and Claude's tool descriptions. Should this be renamed to `"holly"` or `"holly-ops"`, or is it preserved as a runtime primitive name (like the tool names)?

**Q4 — Docker image directory:** `image-build/scion-ops-mcp/` contains the Dockerfile for the MCP server image. This is a code-path name, not directly user-visible. Should it be renamed (accepting a small migration cost) or preserved alongside the K8s resource names?

**Q5 — Zed editor context server:** `.zed/settings.json` labels the context server `"scion-ops"`. This is developer-tooling UX. Is it in scope for the Holly rebrand, or is it considered an internal/dev-facing label?

**Q6 — Migration plan trigger:** The spec defers Kubernetes resource renaming and MCP tool renaming to a future explicit migration plan. Should that plan be defined as a follow-on OpenSpec change (separate `change` entry), or will it be scoped into this same session once the user-facing pass is reviewed?

---

## Non-Goals (Confirmed)

- No changes to Scion runtime internals (Hub protocol, broker, agent SDK, template format)
- No Kubernetes resource renaming in this pass
- No MCP tool renaming in this pass
- No changes to `.scion-ops/` session directory structure
- No changes to the kind cluster or context names

---

## Risk Notes

- The web UI (`web_app_hub.py`) references `CONTROL_PLANE_NAMES` as a set of Kubernetes service names (`scion-ops-web-app`, `scion-ops-mcp`, etc.). These names are **functional** — they drive service discovery. Any rename here must keep those values as Kubernetes names, only changing what is displayed to the operator.
- If Q3 is answered "rename MCP server name," MCP clients (Claude Desktop, Zed) will need their config updated; this is a small but non-zero coordination cost.
