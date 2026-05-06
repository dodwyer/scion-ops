# Testing Plan

The supported verification path is Kubernetes-only.

## Smoke Tiers

| Tier | Command | Model spend | Purpose |
|---|---|---:|---|
| Static | `task verify` | no | Check task surface, syntax, and repo-local validators. |
| Cheap control plane | `task test` | no | Prove kind, Hub, broker, MCP, and Kubernetes no-auth agent dispatch. |
| Release round | `task release:smoke` | yes | Prove subscription-backed Claude, Codex, and final reviewer credentials in Kubernetes. |

Keep `task test` as the frequent local health check. It must stay no-auth and
no-spend so it is safe to run during normal iteration. Run
`task release:smoke` only before a release, after credential changes, or when
debugging model-backed round dispatch.

`task release:smoke` defaults to:

- `SCION_OPS_RELEASE_SMOKE_MAX_MINUTES=8`
- `SCION_OPS_RELEASE_SMOKE_MAX_REVIEW_ROUNDS=1`
- `SCION_OPS_RELEASE_SMOKE_FINAL_REVIEWER=gemini`

The command bootstraps the selected target repo unless
`SCION_OPS_RELEASE_SMOKE_BOOTSTRAP=0` is set. Use
`SCION_OPS_RELEASE_SMOKE_FINAL_REVIEWER=codex` when the release check should
avoid Gemini capacity or auth.

## Lifecycle Check

Use this sequence for a full local validation:

```bash
task x
```

`task x` expands to `task build`, `task up`, `task bootstrap`, and `task test`.
The build step ensures the configured Scion checkout has the repo-owned runtime
patches before building images. The bootstrap step restores shared Hub
credentials, harness configs, and templates before a round is started.

`task test` runs `scripts/kind-control-plane-smoke.py`. It verifies:

- kind cluster and workspace mount
- Kubernetes control-plane rollout
- kind-hosted Hub dev auth and restored Hub auth/session Secrets
- dedicated Runtime Broker registration and control-channel status
- HTTP MCP service readiness
- Hub-backed MCP status call
- no-auth generic agent dispatch through the broker
- agent pod creation in `scion-agents`
- smoke agent cleanup after success

Destroy local cluster state with:

```bash
task down
```

## Narrow Checks

When changing one layer, run the closest check first:

```bash
task kind:workspace:status
task scion:patch:status
task kind:control-plane:status
task kind:mcp:smoke
task kind:broker:status
```

Use the kind-native host mappings for direct inspection:

```bash
eval "$(task kind:hub:auth-export)"
task kind:mcp:smoke
```

## Static Verification

For docs or Python-only edits:

```bash
task verify
```

This checks whitespace, task listing, and Python syntax without trying to
recreate the Kubernetes cluster.

## Failure Classes

Use the nearest failing tier to classify problems:

| Class | Signals | First check |
|---|---|---|
| Setup | missing tools, broken task surface, invalid manifests or scripts | `task verify` |
| Hub | unhealthy Hub, missing dev auth/session Secret, missing grove link, missing Hub secrets | `task kind:hub:status` and `task bootstrap` |
| Broker | no broker provider, broker auth failure, dispatch rejected before pod creation | `task kind:broker:status` |
| Kubernetes runtime | no agent pod, pod stuck, image pull, RBAC, or namespace errors | `kubectl --context kind-scion-ops -n scion-agents get pods` |
| MCP | HTTP service unavailable or missing tool surface | `task kind:mcp:smoke` |
| Model credentials | Claude, Codex, or Gemini agent starts but cannot authenticate or produce output | `task release:smoke` plus `scion_ops_watch_round_events` |

The release tier uses Scion's explicit `auth-file` harness authentication path
for Claude, Codex, and optional Gemini final review. It validates that
`CLAUDE_AUTH`, `CLAUDE_CONFIG`, `CODEX_AUTH`, and `GEMINI_OAUTH_CREDS` have
been restored as Hub secrets by `task bootstrap`.
