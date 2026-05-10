# Explorer Findings: holly-ops-branding

## Scope Read

- Goal: low-risk user-facing rename from scion-ops to Holly Ops; web UI name should be Holly Ops Drive, abbreviated HHD; operator-facing bot/coordinator should be Holly.
- Compatibility constraint: preserve real Scion primitive terminology such as Hub, broker, agents, MCP, templates, and steward sessions.
- Compatibility constraint: keep Kubernetes resource names, MCP tool names, and `.scion-ops` session state compatible unless a migration plan is explicitly specified.
- Repository state: branch `round-20260510t180845z-3fc5-spec-explorer` is based on `main` and was clean before this findings artifact.

## Existing Web App

- Main implementation is `scripts/web_app_hub.py`, a single Python HTTP server with embedded HTML/CSS/JS in `INDEX_HTML`.
- The current page title and header are `scion-ops hub`. Primary nav labels are `Overview`, `Rounds`, `Inbox`, and `Runtime`.
- Existing UI copy and browser-facing labels preserve runtime/source terminology heavily: `Hub agents`, `MCP State`, `Coordinator Output`, `Control plane readiness`, `Final Review`, `Decision Flow`, `Consensus`, `Branches`, `Agents`, and source names like `hub`, `broker`, `mcp`, `web_app`, and `kubernetes`.
- The app is read-only and exposes JSON endpoints such as `/api/snapshot`, `/api/rounds/{round_id}`, `/api/rounds/{round_id}/events`, `/api/live`, and `/healthz`.
- The browser JSON contract is embedded as `BROWSER_JSON_CONTRACT`; it explicitly names Hub/MCP/Kubernetes/message/notification sources and describes the current web app as read-only.
- `CONTROL_PLANE_NAMES`, `CONTROL_PLANE_DEPLOYMENTS`, and `CONTROL_PLANE_SERVICES` currently include Kubernetes names `scion-hub`, `scion-broker`, `scion-ops-mcp`, and `scion-ops-web-app`. Per the explicit goal, these are compatibility-sensitive and should not be renamed in a first-pass branding change.
- The web app launch messages and argparse description use `scion-ops web app hub` language. These are operator-visible but less central than the page title/header.

## Existing Kubernetes And Kind State

- Kind defaults are centralized in `Taskfile.yml` and `scripts/kind-scion-runtime.sh`.
- Default cluster/context names are `scion-ops` and `kind-scion-ops`.
- The deployed web app resource names are `scion-ops-web-app` across Deployment, Service, ServiceAccount, Role, RoleBinding, labels, rollout tasks, health checks, and smoke tests.
- The MCP resource and image names are `scion-ops-mcp`; MCP deployment env names include `SCION_OPS_ROOT`, `SCION_OPS_MCP_*`, `SCION_OPS_HUB_ENDPOINT`, and related compatibility variables.
- The web app deployment reuses the `localhost/scion-ops-mcp:latest` image and executes `scripts/web_app_hub.py`.
- In-cluster repo discovery assumes paths ending in `/scion-ops`; preserving this is important unless a migration is designed.
- Docs under `docs/kind-control-plane.md` expose operator commands using `kubectl ... deploy/scion-ops-web-app`, `deploy/scion-ops-mcp`, `kind-scion-ops`, and the default web URL. Those command/resource names should remain unchanged for now, but surrounding product prose can be rebranded.

## MCP And Runtime Naming

- MCP server implementation is `mcp_servers/scion_ops.py`.
- MCP server name is `scion-ops`, instructions say "Use these tools to start and monitor scion-ops rounds and steward sessions", and tool names use the `scion_ops_` prefix.
- Existing docs and tests call tools such as `scion_ops_hub_status`, `scion_ops_round_status`, `scion_ops_round_events`, `scion_ops_watch_round_events`, `scion_ops_round_artifacts`, `scion_ops_spec_status`, `scion_ops_validate_spec_change`, and `scion_ops_prepare_github_repo`.
- The explicit goal says MCP tool names should remain compatible, so OpenSpec should avoid requiring `holly_ops_*` or `hhd_*` tool renames in this change.
- Runtime state and env vars use `SCION_OPS_*`; preserve these for compatibility in the low-risk rename.

## Session And Steward State

- Durable steward/session state is intentionally stored under `.scion-ops/sessions/<session_id>/`.
- `scripts/steward-state.py`, `scripts/validate-steward-session.py`, finalizer tests, and Scion templates all refer to `.scion-ops/sessions`.
- Templates under `.scion/templates/*` repeatedly describe "Scion-managed" agents, Hub messaging, coordinator/steward roles, and `.scion-ops` state paths.
- "Coordinator" is both user-facing copy and an internal role in templates, repair classifications, and final review routing. The product goal says the operator-facing bot/coordinator should be called Holly, but care is needed to avoid breaking existing agent-role protocol text that expects "coordinator" or "steward".
- Recommended low-risk framing: require UI/operator prose to say Holly where it refers to the action-conducting assistant, while preserving `coordinator`, `steward`, agent role names, and message protocol fields where they are Scion/session mechanics.

## Existing OpenSpec State

- Existing web app capability specs live under:
  - `openspec/changes/build-web-app-hub/specs/web-app-hub/spec.md`
  - `openspec/changes/update-web-app/specs/web-app-hub/spec.md`
  - `openspec/changes/autorefresh-web-app/specs/web-app-hub/spec.md`
  - `openspec/changes/web-ui-theme/specs/web-app-hub/spec.md`
- These specs call the capability "Web App Hub" and repeatedly use "web app hub", "operator", "scion-ops readiness", and source-of-truth language around Hub/MCP/Kubernetes.
- `web-ui-theme` defines the current desired visual style: restrained operational console, dense layout, semantic status styling, no marketing hero, and no decorative dashboard widgets.
- For the new change, likely files to author are:
  - `openspec/changes/holly-ops-branding/proposal.md`
  - `openspec/changes/holly-ops-branding/design.md`
  - `openspec/changes/holly-ops-branding/tasks.md`
  - `openspec/changes/holly-ops-branding/specs/web-app-hub/spec.md`
- The spec can modify existing web-app requirements rather than create a new runtime capability. The underlying spec directory may reasonably stay `web-app-hub` to avoid scope churn, even while visible product copy becomes Holly Ops Drive.

## Likely Spec Requirements

- Web UI Branding: browser title, header, primary product labels, and read-only web app descriptions identify the UI as Holly Ops Drive, with HHD allowed as an abbreviation.
- Holly Operator Persona: operator-facing references to the action-conducting bot/coordinator use Holly where shown to humans, without renaming Scion roles, templates, agent records, or protocol fields.
- Runtime Terminology Preservation: Hub, broker, agents, MCP, templates, steward sessions, round ids, branches, OpenSpec validation, final review, and Kubernetes source diagnostics remain named as-is when they refer to actual runtime primitives.
- Compatibility Preservation: Kubernetes resources, ServiceAccounts, labels/selectors, image names, env vars, MCP server/tool names, default kind cluster/context names, and `.scion-ops` session paths remain unchanged in this first pass.
- Documentation Branding: README and operator docs should introduce Holly Ops/Holly Ops Drive while keeping command examples and compatibility identifiers unchanged.

## Expected Implementation Surfaces

- `scripts/web_app_hub.py`: page title/header; possibly docstring, server log line, argparse description, `BROWSER_JSON_CONTRACT` human descriptions, and `Coordinator Output` label if judged operator-facing.
- `scripts/test-web-app-hub.py`: assertions over UI strings and health service name. Resource-name assertions should stay `scion-ops-web-app`.
- `README.md`, `docs/kind-control-plane.md`, `docs/openspec-round-workflow.md`, and `docs/zed-mcp.md`: product prose and user prompts can be rebranded; command snippets, MCP tool names, env vars, cluster/context names, and paths should be preserved.
- `.scion/templates/spec-steward/*` and `.scion/templates/implementation-steward/*`: possible narrow copy changes for operator-facing coordinator identity, but high risk because these prompts define protocol and durable state behavior. Spec should be precise before touching them.
- `mcp_servers/scion_ops.py`: likely only human-readable instructions/docstring are in scope. Tool names and module filename should stay unchanged.
- `deploy/kind/*`, `image-build/scion-ops-mcp/*`, and lifecycle scripts: mostly out of scope for a low-risk rename except comments/help text. Resource names and file paths should not be changed.

## Risks And Guardrails

- High risk: renaming Kubernetes resources such as `scion-ops-web-app` or `scion-ops-mcp` would require selectors, RBAC subjects, PVCs, services, smoke tests, docs, and existing clusters to migrate together.
- High risk: renaming MCP tool names from `scion_ops_*` would break existing clients and docs, especially Zed examples and smoke tests.
- High risk: renaming `.scion-ops` session paths would break steward validation/finalization, branch artifact collection, and existing durable sessions.
- Medium risk: replacing "Scion" globally would obscure real Scion primitives and make Hub/broker/agent diagnostics less accurate.
- Medium risk: replacing "coordinator" globally could break agent prompt contracts and final review routing language.
- Low risk: changing visible web UI product labels, README intro copy, and doc prose around "the web app" to "Holly Ops Drive".
- Suggested validation after implementation: `python3 scripts/test-web-app-hub.py`, targeted `rg` checks for unwanted UI strings, and existing static/OpenSpec validation used by this repo.
