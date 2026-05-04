# Zed MCP Setup

This repo includes an MCP server for Zed external agents. It exposes the
existing `task`, `scion`, Hub, and git workflow through narrow tools for
starting rounds, monitoring agents, reading transcripts, checking result
branches, and aborting a round with explicit confirmation.

For Hub mode, prefer streamable HTTP. It keeps one long-lived MCP service
attached to the `scion-ops` workspace and lets Zed, Claude, Codex, or a tunnel
connect by URL.

The examples below assume the current default deployment: Hub, broker, and MCP
run on the host or remote host that owns the workspace. If MCP later runs inside
kind, use the same Zed URL shape but expose it through the service/port-forward
described in `docs/kind-control-plane.md`.

## Choose A Mode

| Mode | Zed config | Who starts the MCP server | Best fit |
|---|---|---|---|
| HTTP URL | `url` | You, systemd, tmux, or another supervisor | Hub-mode default |
| HTTP URL over SSH tunnel | `url` | Remote shell starts MCP; local SSH forwards the port | Zed local, Scion remote |
| Remote HTTP URL | `url` | Remote supervisor starts MCP behind network controls | Shared or always-on remote setup |
| Local stdio | `command` and `args` | Zed launches `uv run .../scion_ops.py` | Everything runs on one machine |
| SSH stdio | `command` and `args` running `ssh` | Zed launches local `ssh`; SSH launches remote MCP | No long-lived HTTP service |
| kind-hosted HTTP URL | `url` | Kubernetes runs MCP; user starts port-forward or ingress | Proposed all-in-kind path |

In all modes, the external agent does not independently discover or start this
MCP server. Zed reads `context_servers`, connects to the configured MCP server,
and forwards the tool surface to Claude Agent or Codex through ACP.

## Workspace Binding

The MCP server operates on the workspace where it is started. For this project
that is:

```text
/home/david/workspace/github/livewyer-ops/scion-ops
```

For stdio configs, set `SCION_OPS_ROOT` to that path. For HTTP configs, start
the server from that repo root or set `SCION_OPS_ROOT` in the process
environment. Zed does not pass the current buffer's directory to an already
running HTTP MCP server.

For multiple work directories, run one MCP server per workspace and give each
server a distinct port or path.

## Hub API Operation

In Hub mode, the MCP tools read Scion state through the Hub HTTP API instead of
using `scion list`, `scion messages`, or `scion notifications` as the primary
control path. The local shell is still used for repo/git inspection, `task
round`, `task verify`, and terminal transcript compatibility via `scion look`.

The MCP server resolves Hub configuration from the workspace and Scion
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

## Hub Preflight

Run these on the machine that owns the `scion-ops` workspace:

```bash
task hub:up
eval "$(task hub:auth-export)"
task hub:link
task hub:status
```

`task hub:status` should show a running local Hub, linked grove, broker state,
and current agents. If the kind runtime is part of the test, also check:

```bash
task broker:kind-status
```

## Preferred: HTTP URL

Start the MCP server from the repo root:

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

Configure Zed with the URL in `.zed/settings.json` or user settings:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

In this mode Zed opens HTTP requests to an already-running MCP server. Zed does
not run `task mcp:http`, and the external agent does not run the MCP command.

Smoke test the HTTP transport:

```bash
task mcp:http:smoke
```

The smoke task connects to the configured URL first. If no MCP server responds,
it starts a temporary local server, lists tools, calls Hub status and agent
listing, then shuts it down.

For the experimental kind-hosted MCP deployment, keep Zed configured with a URL
but point it at the forwarded service endpoint, for example
`http://127.0.0.1:8765/mcp`.

For the experimental kind-hosted MCP slice, start the port-forward with:

```bash
task kind:mcp:port-forward
```

In another terminal, smoke test the forwarded service without starting a host
fallback:

```bash
task kind:mcp:smoke
```

## Remote HTTP By SSH Tunnel

Use this when `scion-ops`, `scion`, Hub, and agent workspaces live on a remote
host, but Zed runs locally.

On the remote host:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
task hub:status
task mcp:http
```

On the local machine:

```bash
ssh -N -L 8765:127.0.0.1:8765 david@192.168.122.103
```

Then configure Zed locally with the tunneled URL:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Zed connects to `127.0.0.1:8765` on the local machine. SSH carries that traffic
to the remote MCP server. The remote MCP server still operates from the remote
`SCION_OPS_ROOT`.

## Remote HTTP Deployment

For an always-on remote MCP service, keep the MCP server bound to the remote
host's loopback interface and place an authenticated reverse proxy, VPN, or
firewall-controlled private network in front of it:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
SCION_OPS_MCP_HOST=127.0.0.1 SCION_OPS_MCP_PORT=8765 task mcp:http
```

Configure Zed with the protected external URL:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "https://scion-ops.example.com/mcp"
    }
  }
}
```

Only bind `SCION_OPS_MCP_HOST=0.0.0.0` on a trusted private network or behind
controls that enforce authentication. The MCP HTTP transport itself should be
treated as a privileged project-control interface.

## Stdio: Local Command

Use stdio when Zed can run the MCP server on the same machine as the
`scion-ops` workspace and you want Zed to manage the process lifetime.

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

In this mode Zed starts the local command and owns the MCP process lifetime.
This is different from HTTP URL mode, where the server must already be running.

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

Keep the remote shell quiet: any login banner printed to stdout can break stdio
MCP.

## Security Notes

The MCP tools can start rounds, inspect transcripts and branches, stop/delete
agents, and read Hub state for this grove. Treat access to the MCP endpoint as
access to operate this project.

Keep the default `127.0.0.1` bind for local and SSH-tunnel setups. For remote
HTTP, use an SSH tunnel, VPN, firewall, or authenticated reverse proxy with TLS.
Do not expose the MCP server directly on the public internet.

Hub credentials stay on the machine running the MCP server. Zed URL
configuration does not need the Scion dev token or subscription credential
files.

## Operational Checks

From the machine running the MCP server:

```bash
task hub:status
task mcp:smoke
task mcp:http:smoke
```

From an external agent in Zed, check the live tool path:

```text
Use the scion-ops MCP server to run scion_ops_hub_status and scion_ops_list_agents.
```

Healthy Hub-mode tool responses include `source: "hub_api"` and redacted `hub`
metadata with the expected endpoint and grove id.

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
