# Testing Plan

The supported verification path is Kubernetes-only.

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
- kind-hosted Hub dev auth
- co-located Runtime Broker status
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

## Known Test Gap

The Kubernetes smoke still uses the checked-in generic no-auth smoke config, so
it proves broker dispatch and MCP readiness without spending subscription model
usage. The next full validation is a short `scion_ops_start_round` call against
a clean target branch after `task bootstrap` passes. That round should use
Scion's explicit `auth-file` harness authentication path for Claude, Codex,
and optional Gemini final review, including Claude's companion `CLAUDE_CONFIG`
state file with Scion's `/workspace` checkout marked trusted and
bypass-permissions startup accepted for the Kubernetes agent sandbox. The
bootstrapped Claude config should not carry host-local MCP server registrations
into agent pods, and the Claude round templates should use native Scion
`command_args` to pass `--print` so the prompt is submitted immediately. Codex
is the default final reviewer; Gemini is an explicit option with Codex fallback
when capacity or auth prevents a verdict.
