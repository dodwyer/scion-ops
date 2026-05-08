# Zed MCP Operations

scion-ops exposes a Kubernetes-hosted streamable HTTP MCP server. Zed connects
to that URL. Zed and external agents do not start the MCP process.

## Start MCP

On the host running the kind control plane:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
task up
task bootstrap -- /home/david/workspace/github/livewyer-ops/scion-ops
task kind:mcp:smoke
```

Default URL:

```text
http://192.168.122.103:8765/mcp
```

## Register In Zed

Direct remote URL:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://192.168.122.103:8765/mcp"
    }
  }
}
```

If Zed cannot reach `192.168.122.103:8765`, expose that route with your normal
SSH or VPN setup and point the context server `url` at the reachable HTTP MCP
endpoint. scion-ops does not manage that network tunnel.

## Project Roots

`project_root` must be a path visible to the MCP server.

For local kind, host paths under `/home/david/workspace` are mapped into the MCP
pod under `/workspace`.

If a repo is not checked out locally, ask the MCP server to prepare it:

```text
Use the scion-ops MCP server.
Prepare GitHub repo https://github.com/OWNER/REPO and return the project_root.
```

Use the returned `project_root` for status, spec, implementation, and archive
calls.

## Health Checks

Ask Zed:

```text
Use the scion-ops MCP server. Call scion_ops_project_status for project_root=/path/to/project and summarize it.
```

```text
Use the scion-ops MCP server. Call scion_ops_hub_status and summarize Hub, broker, and agent health.
```

## Start A Round

```text
Use scion-ops on project_root=/path/to/project.

Start a round:
"Make the requested change, verify it, push the resulting branch, and report the PR-ready branch name."
```

The external agent should call `scion_ops_start_round`, then monitor with
`scion_ops_watch_round_events` until terminal.

## Start A Spec Round

```text
Use scion-ops on project_root=/path/to/project.

Run a spec round for change=add-widget:
"Specify the widget behavior."
```

`spec round` already means OpenSpec artifacts only. The external agent should
call `scion_ops_run_spec_round` and re-call it with `next.args` until
`done=true`.

## Start Implementation From Spec

```text
Use scion-ops on project_root=/path/to/project.

Validate change=add-widget, then start an implementation round from that approved spec:
"Implement the approved change, update tasks.md, verify it, push the branch, and report the PR-ready branch name."
```

The external agent should call `scion_ops_start_impl_round`, then monitor with
`scion_ops_watch_round_events`.

## Archive Accepted Spec

Plan first:

```text
Use scion-ops on project_root=/path/to/project.

Archive accepted OpenSpec change=add-widget and show the plan only.
```

Apply only after review:

```text
Use scion-ops on project_root=/path/to/project.

Apply the OpenSpec archive for change=add-widget with confirm=true.
```

## Abort Or Inspect

```text
Use scion-ops on project_root=/path/to/project.

Show round status for round_id=<round-id>. If it is still running, abort it with confirm=true.
```

Useful tools:

- `scion_ops_round_status`
- `scion_ops_round_events`
- `scion_ops_watch_round_events`
- `scion_ops_round_artifacts`
- `scion_ops_abort_round`
