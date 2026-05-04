# kind Broker Runtime

This wires the host-managed workstation Runtime Broker to the kind-backed
Kubernetes profile. The shape follows the upstream Scion model:

- Hub is the control plane for groves, agents, templates, and broker routing.
- Runtime Broker is the compute provider for a grove.
- Kubernetes is selected by a Scion profile at agent dispatch time.

This is the current default. A future all-in-kind path would run the broker
inside kind as well; that design, persistence model, and constraints live in
`docs/kind-control-plane.md`.

References:

- Runtime Broker guide: <https://googlecloudplatform.github.io/scion/hub-user/runtime-broker/>
- Kubernetes runtime guide: <https://googlecloudplatform.github.io/scion/hub-admin/kubernetes/>

## Prerequisites

Start from the local kind and host Hub workflows:

```bash
task kind:up
task hub:up
eval "$(task hub:auth-export)"
task hub:link
```

Build and load the agent images before running real agents on kind. The smoke
task uses `reviewer-claude`, so `localhost/scion-claude:latest` is the minimum
image needed for this check:

```bash
task images:build
task kind:load-images -- \
  localhost/scion-base:latest \
  localhost/scion-claude:latest \
  localhost/scion-codex:latest \
  localhost/scion-gemini:latest
```

## Configure The Profile

Configure Scion's global `kind` profile to target the kind kube context and
namespace:

```bash
task broker:kind-configure
```

This writes the broker-facing profile in `~/.scion/settings.yaml`:

```yaml
image_registry: localhost
runtimes:
  kubernetes:
    type: kubernetes
    context: kind-scion-ops
    namespace: scion-agents
profiles:
  kind:
    runtime: kubernetes
```

The profile is named `kind`, while the runtime name remains `kubernetes`. That
keeps the broker metadata and Hub dashboard aligned with Scion's Kubernetes
runtime type.

## Provide This Grove

Refresh the broker registration so Hub sees the updated profile list, then add
the broker as a provider for this grove and make it the default:

```bash
task broker:kind-provide
```

This runs:

- `scion broker register --force`
- `scion server stop` followed by `task hub:up`-equivalent startup, so the
  embedded broker reloads refreshed HMAC credentials
- `scion broker provide --make-default`

Check the result:

```bash
task broker:kind-status
```

The broker profile list should include `kind` with the kind context and
namespace.

## Smoke Dispatch

Dispatch a minimal Hub agent using the kind profile and verify that a
Kubernetes pod appears:

```bash
task broker:kind-smoke
```

By default, the task deletes the smoke agent after observing the pod. Keep it
for inspection with:

```bash
SCION_KIND_SMOKE_KEEP=1 task broker:kind-smoke
```

The smoke task is intentionally a dispatch check, not a full consensus round.
It proves Hub routed to the local broker and the broker selected the kind
Kubernetes runtime for `--profile kind`. It passes `--no-auth` so the check
does not depend on copying local subscription credentials into the smoke pod.
Override `SCION_KIND_SMOKE_TEMPLATE` when you want to verify another harness.
