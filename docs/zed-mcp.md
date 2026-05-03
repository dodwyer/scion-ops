# Zed MCP Setup

This repo includes a local stdio MCP server for Zed external agents. It exposes
the existing `task`, `scion`, and git workflow through narrow tools for starting
rounds, monitoring agents, reading transcripts, checking result branches, and
aborting a round with explicit confirmation.

## Option A: Local Command

Use this when Zed can run the MCP server on the same machine as the
`scion-ops` workspace:

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
ACP. Local stdio MCP servers are the reliable path for those external agents.

## Option B: Local Command Over SSH

Use this when Zed is local but `scion-ops`, `scion`, and the agent workspaces
live on a remote host. Zed still sees a local command, but that command is
`ssh`, and the MCP stdio stream runs on the remote machine.

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

## Option C: Remote HTTP

Use this when Zed's custom server UI requires a remote URL, or when you want a
long-running MCP service on the remote host.

Start the server on the remote host:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
SCION_OPS_ROOT="$PWD" \
SCION_OPS_MCP_TRANSPORT=streamable-http \
SCION_OPS_MCP_HOST=127.0.0.1 \
SCION_OPS_MCP_PORT=8765 \
uv run mcp_servers/scion_ops.py
```

Tunnel it from your local machine:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@remote-host
```

Then configure Zed locally:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Do not expose this server directly to the public internet without an
authenticated reverse proxy. The tools can start, stop, and inspect local
Scion agents.

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

## Local Smoke Test

From the repo root:

```bash
task mcp:smoke
```

For interactive debugging:

```bash
npx -y @modelcontextprotocol/inspector uv run mcp_servers/scion_ops.py
```
