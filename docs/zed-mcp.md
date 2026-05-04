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

Add this to `.zed/settings.json` or your Zed user settings:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://192.168.122.103:8765/mcp"
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

Then use the same remote-host URL in Zed:

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
