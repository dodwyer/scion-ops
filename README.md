# scion-ops

Kubernetes-only operating layer for running dueling Scion agents against a
Scion Hub, co-located Runtime Broker, HTTP MCP server, and agent pods.

The supported deployment target is Kubernetes. For local development this repo
uses `kind`; host workstation Hub, host broker, local-only Scion, and stdio MCP
workflows are no longer supported project modes.

## Quickstart

Prerequisites are `task`, `podman`, `kind`, `kubectl`, `uv`, `scion`, and an
upstream Scion checkout at `~/workspace/github/GoogleCloudPlatform/scion` unless
you pass `task build -- --src <path>`.

```bash
task build      # build all Scion and scion-ops images
task up         # create/update kind and apply the Kubernetes control plane
task test       # smoke test Hub, broker, MCP, and Kubernetes agent dispatch
task down       # destroy the local kind deployment
```

`task up` is also the deploy and update operation: it reconciles the kind
cluster, base runtime resources, image loading, and control-plane Kustomize
target. Hidden aliases `task deploy`, `task update`, and `task destroy` map to
the same lifecycle operations for agents that use those words.

The current smoke test dispatches an inline no-auth generic Scion agent through
the kind-hosted Hub and co-located broker. Subscription-backed Claude, Codex,
and Gemini consensus rounds remain the next bootstrap step in issue #29:
credentials, harness configs, and templates must be restored into the
Kubernetes-hosted Hub without relying on host-local upload paths.

## Kubernetes Shape

```text
kind cluster:
  scion-hub Deployment
    Hub/API/Web
    co-located Kubernetes Runtime Broker
    PVC-backed Scion state
  scion-ops-mcp Deployment
    streamable HTTP MCP server
    mounted scion-ops workspace
  Scion agent pods

host:
  repo checkout
  container image build source
  kubectl port-forwards for local inspection and Zed
```

The Kubernetes resources are native Kustomize manifests under `deploy/kind`.
They are intentionally deployable with `kubectl apply -k`; Helm packaging can
come later only if the values and lifecycle model justify it.

## MCP And Zed

The supported MCP transport is the Kubernetes-hosted HTTP service. Start the
deployment, then expose MCP locally:

```bash
task up
task kind:mcp:port-forward
```

Configure Zed with:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Smoke test the forwarded service with `task kind:mcp:smoke`. See
`docs/zed-mcp.md`.

## Layout

- `.scion/templates/` — agent role definitions for the consensus protocol
- `CLAUDE.md` — project engineering standards
- `KNOWNISSUES.md` — intentional exceptions and exit criteria
- `deploy/kind/` — Kubernetes resources for kind, Hub, broker, and MCP
- `docs/kind-control-plane.md` — Kubernetes deployment model
- `docs/kind-scion-runtime.md` — kind runtime substrate details
- `docs/testing-plan.md` — verification plan
- `docs/zed-mcp.md` — Kubernetes-hosted MCP registration
- `mcp_servers/scion_ops.py` — streamable HTTP MCP server
- `orchestrator/` — consensus round launcher and agent utilities
- `rubric/` — reviewer prompt and verdict schema
- `scripts/build-images.sh` — image build helper
- `scripts/kind-scion-runtime.sh` — kind substrate helper
- `scripts/kind-control-plane-smoke.py` — Kubernetes control-plane smoke

## Rounds

`task round -- "prompt"` remains the intended one-line product operation for a
full consensus round. Do not treat it as complete for subscription-backed
Kubernetes operation until issue #29 restores Claude, Codex, Gemini credentials,
templates, and harness configs into the Kubernetes-hosted Hub.
