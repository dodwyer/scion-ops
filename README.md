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
task dev:mcp:restart       # restart MCP after mounted Python source changes
task build:base            # rebuild only the Scion base image
task update:hub            # load the base image and restart Hub only
task build:mcp             # rebuild only the MCP image
task update:mcp            # load the MCP image and restart MCP only
task build:harness -- codex
task load:image -- localhost/scion-codex:latest
task dev:test              # smoke test without reapplying setup
task storage:status        # inspect Podman storage before image work
```

The default image-based Hub update path is `task build:base` followed by
`task update:hub`: rebuild the base image from the Scion source, then load it
into kind and restart the Hub pod without a full cluster reconciliation.

`task build` and `task build:base` first ensure the configured Scion source has
the repo-owned runtime patch set from `patches/scion/`. Inspect or apply it
directly with:

```bash
task scion:patch:status
task scion:patch:apply
task scion:patch:check
```

The default source remains `~/workspace/github/GoogleCloudPlatform/scion`; set
`SCION_SRC` or pass `task build -- --src <path>` when using another checkout.

For normal full rebuilds, rootless Podman should report the `overlay` storage
driver. `vfs` is suitable only for very small experiments because it copies
layers instead of sharing them and can consume disk quickly.

`task bootstrap` is the default credential and template restore path. It links
the target repo as a Hub grove, provides the kind broker, stores shared
subscription credentials as Hub secrets, and syncs the scion-ops templates from
inside the Hub pod so host-local upload paths are not used.
The default LLM auth path uses provider subscription credential files:
`CLAUDE_AUTH`, `CLAUDE_CONFIG`, `CODEX_AUTH`, and `GEMINI_OAUTH_CREDS`,
selected through Scion's `auth-file` harness auth. Vertex ADC is not restored
by default; enable it deliberately with `SCION_OPS_BOOTSTRAP_VERTEX_ADC=1` and
provide `GOOGLE_CLOUD_PROJECT` plus a Google Cloud region variable.
When restoring `CLAUDE_CONFIG`, bootstrap preserves the subscription state and
marks Scion's `/workspace` agent checkout as trusted so Claude starts
non-interactively in Kubernetes. Bootstrap also prepares the synced Claude
harness settings to skip the bypass-permissions warning inside Scion's
sandboxed agent pods. Host-local Claude MCP server registrations are stripped
from the agent config; Scion rounds should use the repo's explicit harness and
template configuration. Claude round templates pass `--print` through native
Scion `command_args` so multiline prompts are submitted as a single
non-interactive model turn.
Rounds default to a Codex final reviewer for the reliable path; Gemini remains
available as an explicit final reviewer and falls back to Codex if capacity or
auth prevents a verdict.

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
The kind Hub uses a stable `SCION_SERVER_HUB_HUBID` so Hub-scoped bootstrap
secrets remain visible after Hub pod rollouts. The Hub deployment runs the
Scion binary from `localhost/scion-base:latest`; persistent Hub state must not
override the image binary.

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
- `patches/scion/` — Scion runtime patches required by this deployment
- `rubric/` — reviewer prompt and verdict schema
- `scripts/build-images.sh` — image build helper
- `scripts/kind-bootstrap.sh` — Hub credential, harness, and template restore
- `scripts/kind-scion-runtime.sh` — kind substrate helper
- `scripts/scion-runtime-patches.sh` — Scion runtime patch apply/check helper
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

If a round reaches its watchdog limit, scion-ops stops the round agents and
keeps their Hub records for inspection. Use `task abort -- <round_id>` when the
diagnostics are no longer needed. Set `SCION_OPS_WATCHDOG_DELETE=1` only when
automatic timeout cleanup is preferred over post-run inspection.
