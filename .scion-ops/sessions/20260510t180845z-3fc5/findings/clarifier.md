# Spec Clarification: holly-ops-branding

**Change:** `holly-ops-branding`  
**Session:** `20260510t180845z-3fc5`  
**Date:** 2026-05-10

---

## Goal Summary

Rename the product experience from *scion-ops* to *Holly Ops*. The web UI is to be called **Holly Ops Drive** (abbreviated **HHD** per the spec). The operator-facing bot/coordinator is to be called **Holly**. Scion runtime primitives (Hub, broker, agents, MCP, templates, steward sessions) retain their current names.

---

## Branding Inventory

### In-scope for user-facing rename (low-risk first pass)

| Location | Current Value | Proposed |
|---|---|---|
| README.md title | `# scion-ops` | `# Holly Ops Drive` |
| docs/ product name | "scion-ops" throughout | "Holly Ops" / "Holly Ops Drive" |
| Web UI HTML title/headings (`scripts/web_app_hub.py`) | "scion-ops" | "Holly Ops Drive" |
| MCP server display name (`mcp_servers/scion_ops.py` line ~88) | `FastMCP("scion-ops", ...)` | `FastMCP("holly-ops", ...)` |
| Zeditor context server key (`.zed/settings.json`) | `"scion-ops"` | `"holly-ops"` |
| MCP server `instructions` string | "scion-ops rounds…" | "Holly Ops rounds…" |
| Git author default name (`implementation-steward.sh`) | `scion-ops` | `Holly` or `holly-ops` |
| Git author default email | `scion-ops@example.invalid` | TBD (see questions) |

### Explicitly out of scope (per goal statement)

| Item | Reason |
|---|---|
| Kubernetes resource names (`scion-ops-mcp`, `scion-ops-web-app`, RBAC, PVCs) | Migration plan required |
| MCP tool function names (`scion_ops_*`, 23 functions) | Breaking change; callers rely on these names |
| `.scion-ops/` session state directory | Compatibility; existing sessions would break |
| Environment variables (`SCION_OPS_*`, 30+ vars) | Not user-facing; breaking change for deployments |
| Docker image tags (`localhost/scion-ops-mcp:latest`) | Deployment-facing; requires migration plan |
| Scion runtime terms: Hub, broker, agents, MCP, templates, steward sessions | Preserved by design |

---

## Assumptions

1. **"User-facing" means visible to the human operator** — web UI, documentation, the MCP server's advertised name, and the coordinator persona name. It does not include environment variables, Kubernetes labels, or internal Python identifiers.

2. **"Holly" as operator bot** refers to the persona presented through the MCP server (the entity an operator chats with / invokes). The most natural mapping is the MCP server display name and its `instructions` text. It does not require renaming underlying agent template files or Scion Hub primitives.

3. **HHD is intentional** — the spec abbreviates "Holly Ops Drive" as "HHD." The natural initialism would be "HOD." This is flagged as a question below; proceeding on the assumption HHD is a deliberate brand choice.

4. **No migration for .scion-ops/**: The `.scion-ops/sessions/` directory is referenced by active tooling; renaming it is a separate, breaking migration not covered here.

5. **Zeditor `.zed/settings.json` is in scope** as a user-facing IDE configuration that names the MCP context server. Renaming the key there is low-risk and consistent with renaming the MCP server display name.

6. **`mcp_servers/scion_ops.py` filename** is left unchanged in this pass; only internal strings and the FastMCP registration name change. The Python module name (`scion_ops`) is an internal identifier.

---

## Unresolved Questions

1. **"HHD" abbreviation** — "Holly Ops Drive" abbreviates naturally to "HOD," not "HHD." Is "HHD" a deliberate brand decision (e.g., "Holly Holistic Drive"?), a typo, or should it be "HOD"? The web UI and documentation need a consistent short form.

2. **Scope of "Holly" persona** — Is "Holly" only the MCP server display name, or should it also appear as: (a) a named persona in web UI headers/footers, (b) the default git commit author name, (c) agent template role descriptions? Clarifying this determines whether `implementation-steward.sh` and agent templates are touched.

3. **MCP server name change impact** — Renaming `FastMCP("scion-ops")` to `FastMCP("holly-ops")` changes the advertised server name. Any existing Zeditor/client configurations that reference `"scion-ops"` by string will need to be updated alongside. Is that update included in this change, or tracked separately?

4. **Git author email** — The default `scion-ops@example.invalid` is a placeholder. Should it become `holly@example.invalid`, remain a `scion-ops` address, or be left to the operator to configure?

5. **"Holly Ops" vs "Holly Ops Drive"** — The goal names two things: the overall product is "Holly Ops" and the web UI specifically is "Holly Ops Drive." Should documentation and README use "Holly Ops" (product) while only the web UI uses "Holly Ops Drive"? Or does everything adopt the "Holly Ops Drive" / HHD brand?

6. **Favicon / logo assets** — Does the web app have any graphical assets (`/workspace/scripts/web_app_hub.py` serves an HTML SPA) that reference the old brand? If so, are new assets being provided or will placeholder text suffice?

---

## Recommended Change Name

**`holly-ops-branding`** (as already assigned) — accurately describes user-facing rename without implying infrastructure migration.

---

## Recommended First-Pass Scope (Low-Risk)

Given the goal's preference for low-risk first, the recommended minimal viable rename covers:

1. `README.md` — title and product description text
2. `docs/` — all occurrences of "scion-ops" as a product name
3. `scripts/web_app_hub.py` — HTML `<title>`, visible headings, module docstring
4. `mcp_servers/scion_ops.py` — `FastMCP(...)` name argument and `instructions` string
5. `.zed/settings.json` — context server key rename from `"scion-ops"` to `"holly-ops"`

Everything else deferred to a follow-on migration change with explicit scope.
