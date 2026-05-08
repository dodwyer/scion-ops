# OpenSpec Operations

scion-ops uses OpenSpec as the contract between planning rounds and
implementation rounds.

## Artifact Contract

A spec round writes only:

```text
openspec/changes/<change>/proposal.md
openspec/changes/<change>/design.md
openspec/changes/<change>/tasks.md
openspec/changes/<change>/specs/**/spec.md
```

It must not implement code, tests, manifests, product docs, or runtime scripts.

`tasks.md` must use checkbox tasks. At least one delta spec must include one of:

- `## ADDED Requirements`
- `## MODIFIED Requirements`
- `## REMOVED Requirements`

Delta specs use:

- `### Requirement: <name>`
- `#### Scenario: <name>`

## Shell Workflow

Start a spec round:

```bash
task bootstrap -- /path/to/project

SCION_OPS_PROJECT_ROOT=/path/to/project \
SCION_OPS_SPEC_CHANGE=add-widget \
task spec:round -- "Specify the widget behavior."
```

Render the prompt without starting agents:

```bash
SCION_OPS_PROJECT_ROOT=/path/to/project \
SCION_OPS_SPEC_CHANGE=add-widget \
task spec:round:dry-run -- "Specify the widget behavior."
```

Validate artifacts:

```bash
task spec:validate -- --project-root /path/to/project --change add-widget
```

Start implementation after the spec PR is merged:

```bash
task bootstrap -- /path/to/project

SCION_OPS_PROJECT_ROOT=/path/to/project \
task spec:implement -- --change add-widget "Implement the approved change."
```

Render the implementation prompt without starting agents:

```bash
SCION_OPS_PROJECT_ROOT=/path/to/project \
task spec:implement:dry-run -- --change add-widget "Implement the approved change."
```

Archive after the implementation PR is merged:

```bash
task spec:archive -- --project-root /path/to/project --change add-widget
task spec:archive -- --project-root /path/to/project --change add-widget --yes
```

The archive command syncs accepted delta specs into `openspec/specs/` and moves
the change folder under `openspec/changes/archive/`.

## MCP Workflow

For Zed and other MCP clients, keep the request small:

```text
Use scion-ops on project_root=/path/to/project.

Run a spec round for change=add-widget:
"Specify the widget behavior."
```

The external agent should call `scion_ops_run_spec_round`. That tool starts or
resumes the round, watches for progress, validates the artifact branch, and
returns the PR-ready branch when done. Re-call it with `next.args` until
`done=true`.

Implementation request:

```text
Use scion-ops on project_root=/path/to/project.

Validate change=add-widget, then start an implementation round from that
approved spec:
"Implement the approved change."
```

Archive request:

```text
Use scion-ops on project_root=/path/to/project.

Archive accepted OpenSpec change=add-widget and show the plan only.
```

Apply archive only when the plan is correct:

```text
Apply the OpenSpec archive for change=add-widget with confirm=true.
```

## Review Requirements

Spec PR review checks:

- only `openspec/changes/<change>/` artifacts changed
- `proposal.md`, `design.md`, `tasks.md`, and at least one delta spec exist
- requirements and scenarios are concrete enough to implement
- unresolved questions are explicit
- operational verification expectations are represented in `tasks.md`

Implementation PR review checks:

- implementation follows the approved artifacts
- `tasks.md` is updated for completed work
- scope drift is treated as blocking
- target repo verification passed

## Runtime Dependency Policy

Validation remains repo-local and script-based. Do not add the OpenSpec CLI to
runtime images unless the current validator leaves a concrete validation gap.
