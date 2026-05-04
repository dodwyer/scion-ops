# Testing Plan

Use the narrow checks while changing one layer, and `task smoke:e2e` before
trusting the full local Hub-mode stack.

This plan covers the current default: host-managed Hub, broker, and MCP with
kind used as the Kubernetes agent runtime. The experimental all-in-kind control
plane is documented in `docs/kind-control-plane.md`; it should get its own
smoke task once the broker resources are implemented.

## Layer Checks

Host and Scion CLI:

```bash
task install
task init
```

kind Kubernetes substrate:

```bash
task kind:up
task kind:status
task kind:doctor
```

Local Hub, Web, and workstation broker:

```bash
task hub:up
eval "$(task hub:auth-export)"
task hub:link
task hub:status
```

Broker registration for the kind profile:

```bash
task broker:kind-provide
task broker:kind-status
```

HTTP MCP transport and Hub-backed tool surface:

```bash
task mcp:http:smoke
```

For the experimental kind-hosted Hub/MCP path, mirror the HTTP MCP check with:

```bash
task kind:workspace:status
task kind:control-plane:apply
task kind:control-plane:status
task kind:mcp:port-forward
task kind:mcp:smoke
```

Run `task kind:mcp:smoke` in a second terminal while the port-forward is active.
The kind-hosted broker dispatch remains a follow-up.

## End-To-End Smoke

Run the whole local path with:

```bash
task smoke:e2e
```

The default run calls `task broker:kind-provide`, which can restart the local
Scion workstation server so the embedded broker reloads refreshed credentials.
Use `--skip-setup` for a non-restarting verification of an already-running
stack.

The task:

- creates or reuses the kind cluster and applies `deploy/kind`
- starts or reuses the local Hub/Web/Broker workstation server
- refreshes Hub auth and checks grove status
- configures and provides the local broker for the `kind` Scion profile
- starts or reuses the HTTP MCP server
- dispatches a no-auth smoke agent through Hub to the kind broker
- verifies that a kind pod appears for the agent
- monitors the smoke agent through `scion_ops_watch_round_events` over HTTP MCP
- deletes the smoke agent after a successful run unless told to keep it

Keep the smoke agent for inspection:

```bash
SCION_E2E_KEEP_AGENT=1 task smoke:e2e
```

Skip setup when you only want to verify an already-running stack:

```bash
task smoke:e2e -- --skip-setup
```

Useful overrides:

| Variable | Default |
|---|---|
| `SCION_E2E_AGENT` | generated `e2e-kind-mcp-*` name |
| `SCION_E2E_TEMPLATE` | `reviewer-claude` |
| `SCION_E2E_PROMPT` | short cwd smoke prompt |
| `SCION_E2E_TIMEOUT_SECONDS` | `90` |
| `SCION_E2E_MCP_WATCH_SECONDS` | `90` |
| `SCION_OPS_MCP_URL` | `http://127.0.0.1:8765/mcp` |

## Images

The default smoke template uses the Claude harness image. Build and load it
before running the end-to-end smoke if the kind node does not already have it:

```bash
task images:build -- --harness claude
task kind:load-images -- localhost/scion-base:latest localhost/scion-claude:latest
```

If the kind provider cannot see Podman images directly, use an archive:

```bash
podman save localhost/scion-claude:latest -o /tmp/scion-claude.tar
task kind:load-archive -- /tmp/scion-claude.tar
```

## Failure Categories

`task smoke:e2e` exits non-zero with a category and the next checks to run:

- `hub_auth`: refresh dev auth with `eval "$(task hub:auth-export)"` and rerun
  `task hub:status`
- `hub_state` or `hub_unavailable`: check `task hub:up` and `task hub:status`
- `broker_dispatch`: refresh provider routing with `task broker:kind-provide`
- `kubernetes`: check `task kind:status` and `task kind:doctor`
- `image`: build and load the required harness image into kind
- `mcp_transport`: check `task mcp:http:smoke`

## Cleanup

The end-to-end smoke uses a unique agent name and deletes it after a successful
run by default. If a failure leaves the agent behind, the script prints the
exact cleanup command:

```bash
scion delete <agent> --hub http://127.0.0.1:8090 --non-interactive --yes
```

Delete the local kind cluster only when you want to remove the whole runtime
substrate:

```bash
task kind:down
```
