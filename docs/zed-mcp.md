# Zed MCP Setup

This repo includes an MCP server for Zed external agents. It exposes the
existing `task`, `scion`, and git workflow through narrow tools for starting
rounds, monitoring agents, reading transcripts, checking result branches, and
aborting a round with explicit confirmation.

For Hub mode, prefer streamable HTTP. It keeps one long-lived service attached
to the `scion-ops` workspace and lets Zed, Claude, Codex, or a local tunnel
connect by URL.

## Hub API Operation

In Hub mode, the MCP tools read Scion state through the Hub HTTP API instead of
using `scion list`, `scion messages`, or `scion notifications` as the primary
control path. The local shell is still used for repo/git inspection, `task
round`, `task verify`, and terminal transcript compatibility via `scion look`.

The MCP server resolves Hub configuration from the current workspace and Scion
settings:

- endpoint: `SCION_OPS_HUB_ENDPOINT`, `SCION_HUB_ENDPOINT`, then
  `hub.endpoint`
- grove: `SCION_OPS_GROVE_ID`, `SCION_HUB_GROVE_ID`, `hub.grove_id`, then
  `.scion/grove-id`
- auth: `SCION_OPS_HUB_TOKEN`, OAuth credentials, agent token, `SCION_HUB_TOKEN`,
  `SCION_DEV_TOKEN`, then `~/.scion/dev-token`

Tool responses include `source` and, for Hub calls, redacted `hub` metadata. If
an operation fails, `error_kind` identifies the failing layer: `hub_auth`,
`hub_unavailable`, `hub_state`, `broker_dispatch`, `runtime`, `local_git_state`,
or `command`.

## Preferred: Streamable HTTP

Start the server from the repo root:

```bash
task mcp:http
```

Defaults:

| Setting | Value |
|---|---|
| host | `127.0.0.1` |
| port | `8765` |
| path | `/mcp` |
| URL | `http://127.0.0.1:8765/mcp` |

Override the bind address with environment variables:

```bash
SCION_OPS_MCP_HOST=127.0.0.1 \
SCION_OPS_MCP_PORT=8765 \
SCION_OPS_MCP_PATH=/mcp \
task mcp:http
```

Configure Zed with the URL:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Keep the default `127.0.0.1` bind unless the server is behind an authenticated
reverse proxy or an SSH tunnel. Do not expose this service directly to the
public internet: the tools can start, stop, inspect, and delete local Scion
agents.

Smoke test the HTTP transport:

```bash
task mcp:http:smoke
```

The smoke task connects to the documented URL first. If no MCP server responds,
it starts a temporary local server, lists tools, and shuts it down.

## Remote HTTP By SSH Tunnel

When `scion-ops`, `scion`, and the agent workspaces live on a remote host,
start the HTTP MCP server on that remote host with the default local bind:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
task mcp:http
```

Tunnel it from your local machine:

```bash
ssh -N -L 8765:127.0.0.1:8765 david@192.168.122.103
```

Then configure Zed locally with:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

## Stdio: Local Command

Use stdio when Zed can run the MCP server on the same machine as the
`scion-ops` workspace and you want Zed to manage the process lifetime:

```json
{
  "context_servers": {
    "scion-ops": {
      "command": "/home/david/.local/bin/uv",
      "args": [
        "run",
        "/home/david/workspace/github/livewyer-ops/scion-ops/mcp_servers/scion_ops.py"
      ],
      "env": {
        "SCION_OPS_ROOT": "/home/david/workspace/github/livewyer-ops/scion-ops"
      }
    }
  }
}
```

Zed forwards `context_servers` to Claude Agent and Codex external agents via
ACP. Stdio remains useful for local command setups and SSH command wrappers.

## Stdio: Local Command Over SSH

Use this when Zed is local but you prefer not to run a long-lived HTTP service
on the remote host. Zed still sees a local command, but that command is `ssh`,
and the MCP stdio stream runs on the remote machine.

This repo includes a generated project config at `.zed/settings.json` for:

- SSH target: `david@192.168.122.103`
- Default local SSH key: `$HOME/.ssh/id_rsa_workspace`
- Remote repo root: `/home/david/workspace/github/livewyer-ops/scion-ops`
- Remote `uv`: `/home/david/.local/bin/uv`

You can override the key path from your local environment:

```bash
export SCION_OPS_SSH_KEY="$HOME/.ssh/your-key"
```

```json
{
  "context_servers": {
    "scion-ops": {
      "command": "sh",
      "args": [
        "-lc",
        "key=\"${SCION_OPS_SSH_KEY:-$HOME/.ssh/id_rsa_workspace}\"; started_agent=0; if [ -z \"${SSH_AUTH_SOCK:-}\" ] || ! ssh-add -l >/dev/null 2>&1; then eval \"$(ssh-agent -s)\" >/dev/null; started_agent=1; ssh-add \"$key\" >/dev/null; fi; ssh -T -A -o LogLevel=ERROR -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -o IdentityFile=\"$key\" -o IdentityAgent=\"$SSH_AUTH_SOCK\" david@192.168.122.103 'cd /home/david/workspace/github/livewyer-ops/scion-ops && exec env SCION_OPS_ROOT=/home/david/workspace/github/livewyer-ops/scion-ops /home/david/.local/bin/uv run /home/david/workspace/github/livewyer-ops/scion-ops/mcp_servers/scion_ops.py'; status=$?; if [ \"$started_agent\" = 1 ]; then ssh-agent -k >/dev/null; fi; exit $status"
      ],
      "env": {}
    }
  }
}
```

This is usually the least moving parts if SSH is already configured. Keep the
remote shell quiet: any login banner printed to stdout can break stdio MCP.

## Useful Prompts

Ask the external agent:

```text
Use the scion-ops MCP server to list agents and monitor the current round.
```

```text
Use scion-ops to start a 5 minute smoke round, then monitor the consensus
runner with scion_ops_watch_round_events until it reports a final branch or a
blocker.
```

## Exposed Tools

- `scion_ops_hub_status` - show Hub status and current agents.
- `scion_ops_list_agents` - list agents, optionally filtered by round id.
- `scion_ops_round_status` - summarize a round and include the consensus tail.
- `scion_ops_round_events` - read current Hub messages, notifications, and
  agent-state deltas for a round.
- `scion_ops_watch_round_events` - block inside the MCP server until a round
  has a new message, notification, agent-state change, or terminal status.
- `scion_ops_look` - read an agent transcript with `scion look`.
- `scion_ops_start_round` - start `task round` with optional round id and limits.
- `scion_ops_abort_round` - dry-run by default; requires `confirm=true`.
- `scion_ops_round_artifacts` - list matching branches, prompts, and workspaces.
- `scion_ops_git_status` - show repo status and round branches.
- `scion_ops_git_diff` - diff a result branch against a base branch.
- `scion_ops_verify` - run `task verify`.
- `scion_ops_tail_round_log` - read `/tmp/scion-round.log`.

## Local Smoke Tests

From the repo root:

```bash
task mcp:smoke
task mcp:http:smoke
```

For interactive debugging:

```bash
npx -y @modelcontextprotocol/inspector uv run mcp_servers/scion_ops.py
```
