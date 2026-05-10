# Explorer Findings: holly-ops-branding

## Scope Read

The repository currently keeps OpenSpec material under active change folders in `openspec/changes/`. There is no top-level `openspec/specs/` baseline in this checkout yet; `scripts/archive-openspec-change.py` creates or appends accepted baseline specs when a change is archived. The local OpenSpec validator requires each new change to include:

- `proposal.md`
- `design.md`
- `tasks.md` with checkbox tasks
- at least one `specs/**/spec.md` file with `## ADDED Requirements`, `## MODIFIED Requirements`, or `## REMOVED Requirements`, plus at least one requirement and scenario

Lowest-risk OpenSpec target:

- Add a new focused change at `openspec/changes/holly-ops-branding/`.
- Put the primary delta in `openspec/changes/holly-ops-branding/specs/web-app-hub/spec.md`.
- Use `MODIFIED Requirements` for existing web app requirements that mention the product surface, and `ADDED Requirements` for an explicit naming/terminology requirement if needed.

## Existing Product Surface

The web app spec history is concentrated in these existing changes:

- `openspec/changes/build-web-app-hub/specs/web-app-hub/spec.md`
- `openspec/changes/update-web-app/specs/web-app-hub/spec.md`
- `openspec/changes/autorefresh-web-app/specs/web-app-hub/spec.md`
- `openspec/changes/web-ui-theme/specs/web-app-hub/spec.md`

Relevant existing constraints from those specs:

- The web app is a read-only operator interface.
- It derives displayed state from existing Hub, MCP, Kubernetes, and normalized helper output.
- Structured MCP/Hub fields are authoritative over fallback text.
- The browser UI must keep blocked, degraded, stale, changes-requested, and unknown states visible.
- The theme should stay restrained and operational, not marketing-oriented.
- Automatic updates and smoke checks must remain no-spend and must not start, abort, retry, archive, or mutate rounds, Kubernetes resources, Hub runtime records, git refs, or OpenSpec files.

## Branding Rename Boundaries

User-facing rename intent:

- Product experience: `Holly Ops`
- Web UI: `Holly Ops Drive`
- Short web UI name: `HHD`
- Operator-facing bot/coordinator that conducts actions: `Holly`

Compatibility boundaries to preserve:

- Keep real Scion runtime terminology where it identifies actual primitives: `Hub`, `Runtime Broker`/`broker`, `agents`, `MCP`, `templates`, `harnesses`, `steward sessions`, and Kubernetes.
- Keep Kubernetes resource names compatible unless a migration plan is specified. Existing names include `scion-ops-mcp`, `scion-ops-web-app`, `scion-hub`, `scion-broker`, cluster `scion-ops`, context `kind-scion-ops`, namespace `scion-agents`, PVCs, RBAC, service accounts, image names, and in-cluster service URLs.
- Keep MCP tool names compatible unless a migration plan is specified. Existing operator tools use `scion_ops_*` names.
- Keep durable session paths compatible. `.scion-ops/sessions/<session_id>/` is used by steward state, validation, and session handoff.
- Keep Scion template names and agent role identifiers compatible unless a migration plan is specified. Current code/specs rely on names such as `spec-steward`, `implementation-steward`, `spec-repo-explorer`, `spec-author`, `impl-codex`, and `final-reviewer-codex`.

## Lowest-Risk Spec Shape

Recommended new `web-app-hub` delta:

```markdown
## ADDED Requirements

### Requirement: Holly Ops Branding

The system SHALL present the operator-facing product experience as Holly Ops and the browser UI as Holly Ops Drive, abbreviated HHD, while preserving existing Scion runtime, MCP, Kubernetes, template, and steward-session identifiers where those identifiers are compatibility contracts.

#### Scenario: Operator opens the web UI
- GIVEN an operator opens the web UI
- WHEN the app renders navigation, document title, page header, empty states, and read-only service messages
- THEN the interface identifies itself as Holly Ops Drive
- AND compact labels may use HHD when space is constrained
- AND it does not present the browser UI as scion-ops hub or Web App Hub.

#### Scenario: Runtime identifiers remain precise
- GIVEN the app displays Hub, broker, MCP, agent, template, harness, Kubernetes, branch, or steward-session data from backing sources
- WHEN that data is rendered
- THEN actual Scion primitive names and compatibility identifiers remain unchanged
- AND the UI may add Holly/Holly Ops framing only as display copy, not by rewriting source identifiers.

#### Scenario: Coordinator display copy uses Holly
- GIVEN operator-facing copy refers to the bot or coordinator conducting actions
- WHEN that copy is rendered in the UI or documentation
- THEN it uses Holly as the display name
- AND existing steward, agent, and coordinator identifiers from backing runtime state remain visible when they are the source-of-truth value.
```

Potential `MODIFIED Requirements` candidates:

- `Operator Overview`: change "summarizes scion-ops readiness" to "summarizes Holly Ops readiness" while still listing Hub, broker, MCP, web app, and Kubernetes checks.
- `Operational Theme`: change "web UI" wording to "Holly Ops Drive" where it is clearly product copy.
- `Source Of Truth Preservation`: keep `scion-ops` references only where they identify existing helper output, state paths, or MCP contracts.
- `MCP Contract Compatibility`: do not rename `scion_ops_*` tools in the requirement unless the change includes explicit compatibility aliases and migration work.

## Implementation Risk Notes

Likely low-risk implementation files after the spec is approved:

- `scripts/web_app_hub.py`: document title, `<h1>`, read-only error message, server log/argparse description, possibly the module docstring if treated as user-facing.
- `scripts/test-web-app-hub.py`: assertions for document title/header/read-only message if tests are added or updated.
- `README.md` and web app docs: user-facing headings and descriptions can say Holly Ops/Holly Ops Drive, while default cluster/context/MCP examples should keep existing identifiers unless a migration is specified.

Higher-risk or out-of-scope without migration:

- `mcp_servers/scion_ops.py` function names and MCP tool names.
- `.scion-ops` session paths and steward validators.
- `deploy/kind/**` resource names, service names, PVCs, service accounts, environment variable names, and image names.
- `Taskfile.yml` command names and deployment workflow identifiers.
- Scion template names, branch naming conventions, and agent role detection.

## Constraints To Carry Forward

- This is a display/terminology spec first, not a resource migration.
- Do not replace "Scion" when referring to upstream Scion or real Scion primitives.
- Do not rewrite source-of-truth runtime values in the browser to look branded; display them exactly when they are identifiers, branch names, tool names, Kubernetes names, template names, agent names, or session paths.
- If a later phase wants Kubernetes resources, MCP tools, environment variables, image names, cluster names, or `.scion-ops` paths renamed, it should be a separate migration spec with compatibility aliases, rollout/rollback behavior, and state migration rules.
