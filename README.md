# scion-ops

Dueling-agents consensus loop on top of [GoogleCloudPlatform/scion](https://github.com/GoogleCloudPlatform/scion).
Two implementer agents (Claude + Codex) draft the same prompt in isolated worktrees; cross-review with a 1-5 rubric; the highest-scoring draft is promoted to integrator; Gemini performs the default final independent smoke review; tests are the binding gate.

## Quickstart

```bash
task install      # bootstrap host: scion CLI, runtime checks, PATH
task init         # scion init --machine + scion init for this grove
task kind:up      # create/reuse local kind cluster for Scion K8s runtime tests
task hub:up       # start local Scion Hub on :8090
eval "$(task hub:auth-export)"
task hub:link     # link grove, register auth files/configs, sync templates
task round -- "your prompt here"
```

`task round` starts a `consensus-runner` agent. That runner coordinates the
implementers, reviewers, integrator, and final reviewer through Scion messages
and agent status rather than host-side worktree polling. Agents are visible at
<http://127.0.0.1:8090>.

Claude agents use the Claude subscription credential file from
`~/.claude/.credentials.json`; Codex agents use `~/.codex/auth.json`; Gemini
agents use the personal OAuth credential file from `~/.gemini/oauth_creds.json`.
`task hub:link` uploads all three as grove-scoped Hub file secrets and syncs
the Claude, Codex, and Gemini harness configs.

Set `FINAL_REVIEWER=codex` when starting a round if you want to skip Gemini for
that run.

For local Kubernetes runtime testing, use `task kind:up`, then
`task kind:configure-scion` and `task kind:doctor`. See
`docs/kind-scion-runtime.md`.

For local Hub mode, use `task hub:up`, authenticate with
`eval "$(task hub:auth-export)"`, then run `task hub:link`. See
`docs/local-hub-mode.md`.

To advertise the kind Kubernetes runtime through the local broker, run
`task broker:kind-configure`, then `task broker:kind-provide`. See
`docs/kind-broker-runtime.md`.

The current default deployment keeps Hub, broker, and MCP on the host while
kind runs agent pods. The proposed all-in-kind control-plane path is documented
in `docs/kind-control-plane.md` and should remain Kustomize-first until the
resource model is proven. The experimental kind control-plane runs Hub/Web with
a co-located Runtime Broker plus the HTTP MCP service. Apply it separately with
`task kind:control-plane:apply` and verify it with
`task kind:control-plane:status`. Expose the kind-hosted Hub and MCP services
locally with `task kind:hub:port-forward` and `task kind:mcp:port-forward`.
Use `eval "$(task kind:hub:auth-export)"` for host CLI auth against the
port-forwarded kind Hub. New kind clusters mount this repo into the kind node
for the MCP Deployment; verify that substrate with
`task kind:workspace:status`.

## Layout

- `.scion/templates/` — agent role definitions, including `consensus-runner`
- `CLAUDE.md` — agent guidance and project engineering standards
- `KNOWNISSUES.md` — intentional exceptions and risks to revisit
- `deploy/kind/` — native Kubernetes resources for the local kind runtime and experimental Hub/broker/MCP control plane
- `docs/kind-control-plane.md` — proposed Kustomize path for running Hub, broker, and MCP in kind
- `docs/kind-broker-runtime.md` — broker registration and kind profile workflow
- `docs/local-hub-mode.md` — local Hub/Web/Broker workstation workflow
- `docs/testing-plan.md` — layer checks and end-to-end smoke workflow
- `orchestrator/round.sh` — thin launcher for the consensus runner
- `mcp_servers/scion_ops.py` — streamable HTTP and stdio MCP server for Zed external agents
- `rubric/` — reviewer prompt + verdict JSON schema
- `scripts/kind-scion-runtime.sh` — local kind orchestration helper
- `scripts/hub-mode.sh` — local Scion Hub workstation helper
- `scripts/kind-broker-runtime.sh` — local broker/kind profile helper
- `scripts/bootstrap-host.sh` — one-shot host preflight

## Zed MCP

Use `task mcp:http` to run the MCP server at `http://127.0.0.1:8765/mcp` for
Hub-mode external agents. Verify it with `task mcp:http:smoke`. Stdio remains
available with `task mcp:stdio` and `task mcp:smoke`. The MCP agent/status
tools read Hub state through the Hub HTTP API. See `docs/zed-mcp.md`.

## Testing

Use `task smoke:e2e` to validate the local Hub + kind + HTTP MCP stack in one
run. The project testing plan is in `docs/testing-plan.md`.

See `/home/david/.claude/plans/https-claude-ai-share-a56e403d-3326-4857-staged-rocket.md` for the full design.
