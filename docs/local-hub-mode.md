# Local Hub Mode

This project uses Scion workstation mode as the local control plane. In that
mode a single local Scion server runs:

- Hub API: control plane for groves, templates, secrets, messages, and agent
  state.
- Runtime Broker: execution plane for creating and managing agents.
- Web Frontend: browser dashboard for the same Hub state.

This is the current default for local development. It keeps Hub, broker, and
MCP host-managed while kind runs agent pods through the Kubernetes runtime
profile. The proposed all-in-kind alternative is documented in
`docs/kind-control-plane.md` and is not the default path yet.

## Defaults

| Setting | Value |
|---|---|
| bind host | `127.0.0.1` |
| web and Hub endpoint | `http://127.0.0.1:8090` |
| server log | `~/.scion/server.log` |
| authentication | development token from local server log |

Override the bind host, port, or client endpoint when needed:

```bash
HUB_BIND_HOST=0.0.0.0 HUB_ENDPOINT=http://192.168.122.103:8090 task hub:up
```

Keep `HUB_ENDPOINT` or Scion's `SCION_HUB_ENDPOINT` set to the address clients
should use. Binding to `0.0.0.0` only controls where the server listens.

## Start And Link

Start or reuse the local workstation server:

```bash
task hub:up
```

The task waits until Hub, Broker, and Web are all reported as running by
`scion server status`. It prints the dashboard URL and the next commands.

Authenticate the shell with the development token printed by the server:

```bash
eval "$(task hub:auth-export)"
```

Link this grove and sync the runtime assets:

```bash
task hub:link
```

That task:

- sets `hub.endpoint`
- enables Hub integration
- links the current grove
- uploads Claude, Codex, and Gemini subscription credential files as Hub file
  secrets
- prepares and syncs harness configs
- syncs local templates to Hub

## Operate

Check the local server, Hub connection, grove link, broker, and current agents:

```bash
task hub:status
```

Open the dashboard at:

```text
http://127.0.0.1:8090
```

Tail the server log:

```bash
task hub:logs
```

Stop the local Scion server:

```bash
task hub:down
```

Stopping the workstation server also stops the co-located Runtime Broker. Agents
managed by that broker are no longer reachable until the server is restarted.

If the all-in-kind control plane is enabled later, lifecycle and persistence
checks should move to `kubectl` and the Kustomize resources described in
`docs/kind-control-plane.md`.

## Local-Only Escape Hatch

Use Scion's global `--no-hub` flag for one-off local-only commands:

```bash
scion start scratch "echo local" --detach --no-hub
scion list --no-hub
scion delete scratch --no-hub
```

There is also a smoke task for the same path:

```bash
task smoke:local
```

To disable Hub integration for this grove until re-enabled:

```bash
task hub:disable
```
