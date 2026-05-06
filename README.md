# scion-ops

Kubernetes-only operating layer for running dueling Scion agents against a
Scion Hub, co-located Runtime Broker, HTTP MCP server, and agent pods.

The supported deployment target is Kubernetes. Local development uses `kind`
with Podman as the default provider.

## Quickstart

Prerequisites are `task`, `podman`, `kind`, `kubectl`, `uv`, `scion`, and an
upstream Scion checkout at `~/workspace/github/GoogleCloudPlatform/scion` unless
you pass `task build -- --src <path>`.

```bash
task x          # build, create/update, bootstrap, deploy, and smoke test
task build      # build all Scion and scion-ops images
task up         # create/update kind and apply the Kubernetes control plane
task bootstrap  # restore Hub credentials, harness configs, and templates
task test       # smoke test Hub, broker, MCP, and Kubernetes agent dispatch
task down       # destroy the local kind deployment
```

`task up` is also the deploy and update operation: it reconciles the kind
cluster, base runtime resources, image loading, and control-plane Kustomize
target. Hidden aliases `task deploy`, `task update`, and `task destroy` map to
the same lifecycle operations for agents that use those words.

For local iteration, use the smallest task that matches the changed asset:

```bash
task dev:scion:deploy      # rebuild Scion binaries and restart Hub only
task dev:mcp:restart       # restart MCP after mounted Python source changes
task build:mcp             # rebuild only the MCP image
task update:mcp            # load the MCP image and restart MCP only
task build:harness -- codex
task load:image -- localhost/scion-codex:latest
task dev:test              # smoke test without reapplying setup
task storage:status        # inspect Podman storage before image work
```

`task bootstrap` is the default credential and template restore path. It links
the target repo as a Hub grove, provides the kind broker, stores shared
subscription credentials as Hub secrets, and syncs the scion-ops templates from
inside the Hub pod so host-local upload paths are not used.
The default LLM auth path uses provider subscription credential files:
`CLAUDE_AUTH`, `CLAUDE_CONFIG`, `CODEX_AUTH`, and `GEMINI_OAUTH_CREDS`,
selected through Scion's `auth-file` harness auth. Vertex ADC is not restored
by default; enable it deliberately with `SCION_OPS_BOOTSTRAP_VERTEX_ADC=1` and
provide `GOOGLE_CLOUD_PROJECT` plus a Google Cloud region variable.

## Kubernetes Shape

```text
kind cluster:
  scion-hub Deployment
    Hub/API/Web
    co-located Kubernetes Runtime Broker
    PVC-backed Scion state
  scion-ops-mcp Deployment
    streamable HTTP MCP server
    mounted host workspace tree
  Scion agent pods

host:
  repo checkout and target project checkouts
  container image build source
  kind native host ports for Hub and MCP
```

The Kubernetes resources are native Kustomize manifests under `deploy/kind`.
They are intentionally deployable with `kubectl apply -k`; Helm packaging can
come later only if the values and lifecycle model justify it.

## MCP And Zed

The supported MCP transport is the Kubernetes-hosted HTTP service. `task up`
creates kind native port mappings, so MCP is available on the host address
without a `kubectl port-forward` process:

```bash
task up
```

Configure Zed with:

```json
{
  "context_servers": {
    "scion-ops": {
      "url": "http://192.168.122.103:8765/mcp"
    }
  }
}
```

Smoke test the HTTP service with `task kind:mcp:smoke`. See `docs/zed-mcp.md`.

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
- `scripts/kind-bootstrap.sh` — Hub credential, harness, and template restore
- `scripts/kind-scion-runtime.sh` — kind substrate helper
- `scripts/kind-dev-scion.sh` — fast Hub/Broker Scion binary update helper
- `scripts/storage-status.sh` — Podman storage diagnostic helper
- `scripts/kind-control-plane-smoke.py` — Kubernetes control-plane smoke

## Rounds

`task round -- "prompt"` starts a consensus round against the selected target
project. Bootstrap the target once, then pass its project root when starting a
round from the scion-ops checkout:

```bash
task bootstrap -- /home/david/workspace/github/example/project
SCION_OPS_PROJECT_ROOT=/home/david/workspace/github/example/project task round -- "prompt"
```

The MCP tool `scion_ops_start_round` accepts the same target as `project_root`.
Agents work from the target repo's Hub grove and branch context; uncommitted
local work is not included unless it is committed or pushed before the round.
