# Zed MCP Setup

scion-ops supports Zed through the Kubernetes-hosted streamable HTTP MCP
service.

## Start The Service

Deploy the local kind control plane:

```bash
task up
```

The local URL is:

```text
http://192.168.122.103:8765/mcp
```

Verify it in another terminal:

```bash
task kind:mcp:smoke
```

## Register In Zed

If Zed can reach the remote host address directly, add this to
`.zed/settings.json` or your Zed user settings:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://192.168.122.103:8765/mcp"
    }
  }
}
```

If Zed is running locally and should reach MCP through the Zed SSH connection,
forward the remote MCP port and point the context server at the local forwarded
port:

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

Zed connects to the URL. It does not run the MCP command, and the external
agent does not start MCP. Kubernetes owns the MCP server process.

## Remote Workspace

If Zed runs locally and scion-ops runs on the remote host, run the kind
deployment on the remote host:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
task up
```

Then use the same remote-host URL in Zed, or the SSH-forwarded local URL when
using the forwarded configuration above:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://192.168.122.103:8765/mcp"
    }
  }
}
```

The MCP server operates from the workspace mounted in the Kubernetes
Deployment. The default kind mount is the host workspace tree at:

```text
/workspace
```

The MCP server auto-discovers the scion-ops checkout inside that tree and maps
host project paths under `/home/david/workspace` to their in-pod `/workspace`
paths. If a target repo is outside the mounted tree, recreate kind with
`SCION_OPS_WORKSPACE_HOST_PATH` set to a parent directory that contains both
scion-ops and the target repo.

Repo URLs prepared through `scion_ops_prepare_github_repo` are cloned into the
MCP checkout PVC at `/home/scion/checkouts/github` by default. Use the returned
`project_root`; it is the path visible to the MCP server and round launcher.

## Tool State

The MCP pod reads Hub state through the in-cluster `scion-hub` Service and
uses the Hub dev token mounted read-only from the Hub PVC. Treat this MCP
service as a privileged project-control interface. Do not expose it outside a
trusted local tunnel, VPN, or authenticated ingress.

## Rounds

Use one shape for every project:

```text
Use scion-ops to start a round on project_root=/home/david/workspace/github/example/project:
"improve README.md"
```

The external agent should call `scion_ops_project_status` first, then
`scion_ops_start_round` with the same `project_root`. The target repo should be
on a clean branch with any important local work committed or pushed; Kubernetes
agents work from git branches, not uncommitted editor state.

For a release smoke through MCP, keep it explicit because it uses subscription
credentials:

```text
Use scion-ops on project_root=/home/david/workspace/github/example/project.
Start a short release smoke round with max_minutes=8, max_review_rounds=1, and final_reviewer=gemini:
"Make the smallest safe README wording improvement, verify it, push the branch, and report the PR-ready branch name."
Monitor it with event watching.
```

The external agent should call `scion_ops_start_round` with those bounded
arguments, then `scion_ops_watch_round_events`.

When the target repo is not checked out yet, pass a GitHub URL:

```text
Use scion-ops to prepare repo_url=https://github.com/example/project.git,
then start a round:
"improve README.md"
```

The external agent should call `scion_ops_prepare_github_repo` first and use
the returned `project_root` for `scion_ops_project_status`,
`scion_ops_start_round`, and follow-up monitoring. Existing checkouts are reused
only when their `origin` matches the requested repository. A mismatched checkout,
non-git directory, auth failure, or workspace mount problem is reported as a
blocked state for the operator to resolve.

## Spec-Driven Rounds

Ask for a spec round with the target project and goal:

```text
Use scion-ops on project_root=/home/david/workspace/github/example/project.
Start a spec round for change=add-widget:
"Specify the smallest useful widget improvement. Produce OpenSpec artifacts only."
Monitor it with event watching and report the PR-ready spec branch.
```

The external agent should call:

```text
scion_ops_project_status(project_root)
scion_ops_start_spec_round(project_root, goal, change)
scion_ops_watch_round_events(round_id, cursor)
scion_ops_round_artifacts(project_root, round_id)
```

After the spec PR is merged, ask for implementation from the approved spec:

```text
Use scion-ops on project_root=/home/david/workspace/github/example/project.
Validate change=add-widget, then start an implementation round from that approved spec.
Monitor it with event watching and report the PR-ready implementation branch.
```

The external agent should call:

```text
scion_ops_spec_status(project_root, change)
scion_ops_start_impl_round(project_root, change, goal)
scion_ops_watch_round_events(round_id, cursor)
scion_ops_round_artifacts(project_root, round_id)
```

`scion_ops_start_impl_round` validates the artifact set before launching
agents. Missing or invalid specs fail before model work starts.

After the implementation PR is merged, ask for archive cleanup:

```text
Use scion-ops on project_root=/home/david/workspace/github/example/project.
Archive accepted OpenSpec change=add-widget, sync accepted specs, and report the archive path.
```

The external agent should first call
`scion_ops_archive_spec_change(project_root, change, confirm=false)` and show
the plan. After confirmation, it calls the same tool with `confirm=true`, then
uses `scion_ops_spec_status(project_root, change)` to show the archived state.
