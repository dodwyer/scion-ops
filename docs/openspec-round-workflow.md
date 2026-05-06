# OpenSpec Round Workflow

scion-ops uses OpenSpec as the artifact contract for goal-driven work. The
Kubernetes control plane remains the execution substrate: MCP receives the
request, Scion Hub starts the round, the kind broker creates agent pods, and
round progress is monitored through Hub events.

The design goal is simple: a user provides a goal, agents produce an approved
spec change, then agents implement that approved spec in the same target repo
context.

## Alignment

The workflow follows OpenSpec's repo-local model:

```text
openspec/
  specs/
    <domain>/spec.md
  changes/
    <change>/
      proposal.md
      design.md
      tasks.md
      specs/
        <domain>/spec.md
```

`openspec/specs/` is the accepted source of truth for current behavior.
`openspec/changes/<change>/` is the reviewable package for one proposed
change. Delta specs describe added, modified, or removed requirements rather
than restating the whole system.

scion-ops uses this layout in the target project, not in scion-ops, unless
scion-ops itself is the target project. OpenSpec coordination workspaces are
out of scope for now; the repo-local layout is the durable default for one repo
owning its planning, implementation, and archive flow.

## Artifacts

Each spec change folder contains:

| Artifact | Purpose |
|---|---|
| `proposal.md` | Intent, scope, non-goals, and user-visible outcome. |
| `specs/<domain>/spec.md` | Behavior deltas with requirements and scenarios. |
| `design.md` | Technical approach, tradeoffs, affected areas, and verification strategy. |
| `tasks.md` | Implementation checklist with small, verifiable tasks. |

Specs state observable behavior. Design captures implementation choices. Tasks
are the execution checklist. Reviewers judge conformance against these
artifacts, not only the original chat prompt.

## Personas

Spec rounds use planning-focused roles:

| Persona | Responsibility |
|---|---|
| Goal analyst | Normalize the user's goal, infer the smallest useful change, and name the change. |
| Spec author | Draft proposal, delta specs, design, and tasks. |
| Spec reviewer | Check clarity, scope control, testability, and OpenSpec layout. |
| Spec integrator | Combine accepted drafts into one spec branch. |
| Final spec reviewer | Accept or reject the integrated spec package before a spec PR. |

Implementation rounds use delivery-focused roles:

| Persona | Responsibility |
|---|---|
| Implementation planner | Read the approved change folder and select the next unchecked task set. |
| Implementer | Make code and documentation changes against the approved artifacts. |
| Implementation reviewer | Check correctness, task completion, and spec conformance. |
| Implementation integrator | Combine accepted implementation branches and update `tasks.md`. |
| Final implementation reviewer | Accept or reject the integrated branch before an implementation PR. |

The same model providers can fill these roles, but their prompts differ:
planning roles must avoid code changes unless requested; implementation roles
must treat the approved artifact set as the contract.

## State Transitions

```text
goal
  -> spec round requested
  -> openspec/changes/<change>/ drafted
  -> spec review accepted
  -> spec PR opened
  -> spec PR merged by human
  -> implementation round requested for <change>
  -> implementation branches created
  -> implementation review accepted
  -> implementation PR opened
  -> implementation PR merged by human
  -> archive/sync lifecycle applies accepted deltas to openspec/specs
```

The human merge between the spec PR and implementation PR is intentional. It
keeps ambiguous goals from becoming code before the artifacts are accepted.

Implementation rounds start from the merged spec branch and consume the change
folder by `change` name. They should not rewrite the spec intent unless
implementation discovers a real conflict; in that case the round updates the
artifacts and reports the reason.

Archive and accepted-spec sync are a later lifecycle step. Until that is
implemented, accepted change folders remain the implementation contract and
`openspec/specs/` is updated only where explicitly requested.

## MCP Entry Points

The MCP server owns orchestration entry points and leaves execution to Scion
Hub:

| Tool | Responsibility |
|---|---|
| `scion_ops_project_status` | Confirm target project root, branch, origin, Hub link, and git status. |
| `scion_ops_validate_spec_change` | Validate an OpenSpec change folder before implementation starts. |
| `scion_ops_start_spec_round` | Start a planning round from `project_root`, `goal`, and optional `change`. |
| `scion_ops_start_implementation_round` | Start a delivery round from `project_root` and approved `change`. |
| `scion_ops_round_status` | Read current Hub state for a round. |
| `scion_ops_watch_round_events` | Stream state changes and task summaries without polling sleeps. |
| `scion_ops_round_artifacts` | Discover pushed branches and PR-ready outputs for a round. |

`scion_ops_start_round` remains useful for direct implementation prompts, but
the spec-driven path should prefer the explicit spec and implementation round
tools so the artifact contract is visible in the request.

## Validation

Use the validator before an implementation round starts:

```bash
task spec:validate -- --project-root /path/to/project --change <change>
```

The validator checks that `openspec/changes/<change>/` exists, that
`proposal.md`, `design.md`, and `tasks.md` are present and non-empty, that
`tasks.md` includes checkbox tasks, and that at least one
`specs/**/spec.md` delta spec contains requirements and scenarios.

MCP clients use the same validation path through
`scion_ops_validate_spec_change(project_root, change)`.

## Spec Round Launch

Use `task spec:round` to launch the spec-building personas against the selected
target project:

```bash
task bootstrap -- /path/to/project
SCION_OPS_PROJECT_ROOT=/path/to/project task spec:round -- "draft the spec goal"
```

Optionally provide a stable change name:

```bash
SCION_OPS_PROJECT_ROOT=/path/to/project \
SCION_OPS_SPEC_CHANGE=add-widget \
task spec:round -- "draft the spec goal"
```

For a no-model prompt rendering check:

```bash
task spec:round:dry-run -- "draft the spec goal"
```

The spec round uses these templates:

| Template | Role |
|---|---|
| `spec-consensus-runner` | Coordinates the spec protocol and final branch. |
| `spec-goal-clarifier` | Narrows scope, assumptions, and blocking questions. |
| `spec-repo-explorer` | Inspects the target repo so the spec follows local patterns. |
| `spec-author` | Writes only `openspec/changes/<change>/` artifacts. |
| `spec-ops-reviewer` | Checks OpenSpec structure and operational fit. |
| `spec-finalizer` | Produces the PR-ready spec integration branch. |

## Implementation From Spec

After the spec PR is merged, start implementation from the approved change
folder:

```bash
task bootstrap -- /path/to/project
SCION_OPS_PROJECT_ROOT=/path/to/project \
task spec:implement -- --change <change> "implement the approved change"
```

`task spec:implement` validates `openspec/changes/<change>/` before it starts
the round. Missing or invalid artifacts fail before any agent is launched. The
implementation prompt names the approved artifact paths and requires agents to
read them before editing, update `tasks.md` checkboxes, and treat spec drift as
a blocking review issue.

For a no-model prompt rendering check against a valid artifact tree:

```bash
SCION_OPS_PROJECT_ROOT=/path/to/project \
task spec:implement:dry-run -- --change <change> "implement the approved change"
```

## PR Flow

Spec PR:

- Branch name: `round-<round>-spec-integration` or equivalent Scion round branch.
- Changes: only `openspec/changes/<change>/` artifacts unless the target repo
  already requires supporting docs.
- Verification: artifact validation and nearest cheap repo verification.
- Merge gate: human review.

Implementation PR:

- Branch name: `round-<round>-implementation-integration` or equivalent Scion
  round branch.
- Changes: code, docs, tests, and checked tasks in `openspec/changes/<change>/tasks.md`.
- Verification: the approved change's task checks plus the target repo's
  standard test command.
- Merge gate: human review.

## First Implementation Slice

Issue #45 is the first implementation slice after this design lands. It should
add the OpenSpec-style artifact layout and validation support with the smallest
useful scope:

- document the target layout expected by scion-ops rounds
- add a lightweight validator for required artifacts and basic headings
- keep validation local to repo files and cheap enough for `task verify`
- avoid adding OpenSpec CLI installation or MCP round tools in this slice

Issues #46 through #50 then layer on personas, implementation templates, MCP
entry points, spec-conformance verdicts, and archive/sync lifecycle.

## Known Issues

No new exception is introduced by this design. The first slice deliberately
keeps OpenSpec CLI installation out of the runtime images until the validation
and prompt contract prove that a dependency is needed.
