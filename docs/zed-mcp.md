# Zed MCP Setup

scion-ops supports Zed through the Kubernetes-hosted streamable HTTP MCP
service. Stdio MCP and host-launched MCP servers are not supported project
modes.

## Start The Service

Deploy the local kind control plane:

```bash
task up
```

Expose MCP locally:

```bash
task kind:mcp:port-forward
```

The forwarded URL is:

```text
http://127.0.0.1:8765/mcp
```

Verify it in another terminal:

```bash
task kind:mcp:smoke
```

## Register In Zed

Add this to `.zed/settings.json` or your Zed user settings:

```json
{
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

If Zed runs locally and scion-ops runs on a remote host, start the port-forward
on the remote host:

```bash
cd /home/david/workspace/github/livewyer-ops/scion-ops
task up
task kind:mcp:port-forward
```

Then tunnel the local port to the remote host:

```bash
ssh -N -L 8765:127.0.0.1:8765 david@192.168.122.103
```

Keep the same Zed URL:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

The MCP server operates from the workspace mounted in the Kubernetes
Deployment, which defaults to:

```text
/workspace/scion-ops
```

## Tool State

The MCP pod reads Hub state through the in-cluster `scion-hub` Service and
uses the Hub dev token mounted read-only from the Hub PVC. Treat this MCP
service as a privileged project-control interface. Do not expose it outside a
trusted local tunnel, VPN, or authenticated ingress.

## Rounds

The MCP tool `scion_ops_start_round` calls `task round`. Full
subscription-backed Kubernetes rounds require issue #29 so credentials,
templates, and harness configs are restored into the Kubernetes-hosted Hub.
