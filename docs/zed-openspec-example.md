# Zed MCP OpenSpec Example

This is a complete operator walkthrough for using Zed, the scion-ops MCP
server, and OpenSpec rounds against a real target repo.

The example target is this repo:

```text
/home/david/workspace/github/livewyer-ops/scion-ops
```

The example change is:

```text
workspace-prune-preview
```

Goal: specify and then implement a dry-run workspace prune operation that lists
MCP-prepared GitHub checkouts, identifies clean inactive checkouts that would be
safe to delete, and refuses dirty or active workspaces. The spec round is
OpenSpec-only by definition. The implementation round must make the code change
from the approved spec.

## 1. Start scion-ops

Run these commands on the host where the kind control plane runs:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
git switch main
git pull --ff-only
task up
task bootstrap -- /home/david/workspace/github/livewyer-ops/scion-ops
task kind:mcp:smoke
task test -- --skip-setup
```

Expected result:

- Hub is reachable at `http://192.168.122.103:18090`
- MCP is reachable at `http://192.168.122.103:8765/mcp`
- Hub, broker, and MCP deployments are rolled out
- the no-spend smoke agent dispatch passes

## 2. Register MCP In Zed

Use this Zed setting when Zed can reach the remote host directly:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://192.168.122.103:8765/mcp"
    }
  }
}
```

Use this setting when Zed reaches the remote host through an SSH port forward:

```json
{
  "ssh_connections": [
    {
      "host": "192.168.122.103",
      "username": "david",
      "port_forwards": [
        {
          "local_port": 8765,
          "remote_host": "192.168.122.103",
          "remote_port": 8765
        }
      ]
    }
  ],
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Zed connects to the HTTP URL. It does not run an MCP command locally.
Kubernetes owns the MCP server process.

## 3. Create The Tracking Issue

Run this from the target repo:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
gh issue create \
  --title "Add workspace prune preview workflow" \
  --body "## Goal
Add a dry-run workspace prune operation for MCP-prepared GitHub checkouts.

## Scope
- Specify the behavior with OpenSpec first.
- List checkout candidates.
- Mark clean inactive checkouts as safe-to-delete candidates.
- Refuse dirty checkouts and active round workspaces.
- Do not delete anything in the preview operation.

## Verification
- task verify
- focused tests for prune candidate classification
"
```

Save the returned issue URL. The branch names will come from the Scion rounds.

## 4. Start The Spec Round From Zed

Open Zed's agent panel and paste this exact request:

```text
Use scion-ops on project_root=/home/david/workspace/github/livewyer-ops/scion-ops.

Run a spec round for change=workspace-prune-preview:
"Specify a dry-run workspace prune operation for MCP-prepared GitHub checkouts. It should list checkout candidates, identify clean inactive checkouts that are safe to delete, refuse dirty checkouts and active round workspaces, and not delete anything in this change."
```

The external agent should use this MCP tool:

```text
scion_ops_run_spec_round(project_root, goal, change)
```

Expected result:

- a Scion spec round starts in Hub
- spec personas create `openspec/changes/workspace-prune-preview/`
- the tool monitors Hub events, validates the remote spec branch, and reports a
  PR-ready spec branch

## 5. Review The Spec Branch

When Zed reports the branch, set it in your terminal:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
SPEC_BRANCH=<branch-reported-by-zed>
git fetch origin "$SPEC_BRANCH"
git switch "$SPEC_BRANCH"
task spec:validate -- --project-root "$PWD" --change workspace-prune-preview
git diff main...HEAD -- openspec/changes/workspace-prune-preview
```

The spec branch should normally contain only:

```text
openspec/changes/workspace-prune-preview/proposal.md
openspec/changes/workspace-prune-preview/design.md
openspec/changes/workspace-prune-preview/tasks.md
openspec/changes/workspace-prune-preview/specs/**/spec.md
```

Create the spec PR:

```bash
gh pr create \
  --base main \
  --head "$SPEC_BRANCH" \
  --title "Spec workspace prune preview" \
  --body "Closes <issue-url-or-number>

## Summary
- add OpenSpec artifacts for workspace-prune-preview
- define preview-only prune behavior for MCP-prepared GitHub checkouts

## Verification
- task spec:validate -- --project-root \$PWD --change workspace-prune-preview
"
```

Review the PR in GitHub. If it is correct, merge it there. Then update local
`main`:

```bash
git switch main
git pull --ff-only
```

## 6. Start The Implementation Round From Zed

After the spec PR is merged, paste this into Zed:

```text
Use scion-ops on project_root=/home/david/workspace/github/livewyer-ops/scion-ops.

Validate change=workspace-prune-preview, then start an implementation round from that approved spec with max_minutes=30, max_review_rounds=2, and final_reviewer=codex:
"Implement the approved workspace-prune-preview OpenSpec change. Keep scope to the approved tasks, update tasks.md, run task verify, push the result branch, and report the PR-ready implementation branch name."

Monitor it with event watching.
```

The external agent should use these MCP tools:

```text
scion_ops_spec_status(project_root, change)
scion_ops_start_impl_round(project_root, change, goal, max_minutes=30, max_review_rounds=2, final_reviewer="codex")
scion_ops_watch_round_events(round_id, cursor)
scion_ops_round_artifacts(project_root, round_id)
```

Expected result:

- validation runs before model work starts
- implementation personas read the approved OpenSpec artifacts
- code, tests, docs, and `tasks.md` updates land on a PR-ready branch

## 7. Review The Implementation Branch

When Zed reports the implementation branch:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
IMPL_BRANCH=<branch-reported-by-zed>
git fetch origin "$IMPL_BRANCH"
git switch "$IMPL_BRANCH"
task verify
task spec:validate -- --project-root "$PWD" --change workspace-prune-preview
git diff main...HEAD
```

Create the implementation PR:

```bash
gh pr create \
  --base main \
  --head "$IMPL_BRANCH" \
  --title "Implement workspace prune preview" \
  --body "Implements workspace-prune-preview.

## Summary
- implement the approved OpenSpec change
- update tasks.md with completed work

## Verification
- task verify
- task spec:validate -- --project-root \$PWD --change workspace-prune-preview
"
```

Review and merge the PR in GitHub. Then update local `main`:

```bash
git switch main
git pull --ff-only
```

## 8. Archive The Accepted Change

After the implementation PR is merged, first ask Zed for the archive plan:

```text
Use scion-ops on project_root=/home/david/workspace/github/livewyer-ops/scion-ops.
Archive accepted OpenSpec change=workspace-prune-preview, sync accepted specs, and show the plan only.
```

The external agent should call:

```text
scion_ops_archive_spec_change(project_root, change, confirm=false)
```

If the plan is correct, ask Zed to apply it:

```text
Use scion-ops on project_root=/home/david/workspace/github/livewyer-ops/scion-ops.
Apply the OpenSpec archive for change=workspace-prune-preview with confirm=true, then show spec status for that change.
```

The external agent should call:

```text
scion_ops_archive_spec_change(project_root, change, confirm=true)
scion_ops_spec_status(project_root, change)
```

If you prefer to archive from the terminal instead:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
git switch main
git pull --ff-only
task spec:archive -- --project-root "$PWD" --change workspace-prune-preview
git switch -c archive-workspace-prune-preview
task spec:archive -- --project-root "$PWD" --change workspace-prune-preview --yes
task verify
git status --short
git add openspec
git commit -m "Archive workspace prune preview spec"
git push -u origin archive-workspace-prune-preview
gh pr create \
  --base main \
  --head archive-workspace-prune-preview \
  --title "Archive workspace prune preview spec" \
  --body "Archive accepted OpenSpec change workspace-prune-preview.

## Verification
- task spec:archive -- --project-root \$PWD --change workspace-prune-preview
- task spec:archive -- --project-root \$PWD --change workspace-prune-preview --yes
- task verify
"
```

## 9. If The Repo Is Not Checked Out Yet

Use a GitHub URL instead of a local path. Paste this into Zed:

```text
Use scion-ops to prepare repo_url=https://github.com/<owner>/<repo>.git.
Then use the returned project_root for a spec round with change=workspace-prune-preview:
"Specify a dry-run workspace prune operation."
```

The external agent should call `scion_ops_prepare_github_repo` first and then
use the returned `project_root` for every later MCP call.

## 10. Abort Or Inspect A Round

If a round stalls, ask Zed:

```text
Use scion-ops on project_root=/home/david/workspace/github/livewyer-ops/scion-ops.
Show round status for round_id=<round-id>, then abort it if it is still running.
```

The external agent should call:

```text
scion_ops_round_status(round_id, project_root)
scion_ops_abort_round(round_id, confirm=true, project_root)
```
