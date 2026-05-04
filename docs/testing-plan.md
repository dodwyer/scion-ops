# Testing Plan

The supported verification path is Kubernetes-only.

## Lifecycle Check

Use this sequence for a full local validation:

```bash
task build
task up
task test
```

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
task kind:control-plane:status
task kind:mcp:smoke
task kind:broker:status
```

Use port-forwards for direct local inspection:

```bash
task kind:hub:port-forward
task kind:mcp:port-forward
```

## Static Verification

For docs or Python-only edits:

```bash
task verify
```

This checks whitespace, task listing, and Python syntax without trying to
recreate the Kubernetes cluster.

## Known Test Gap

The Kubernetes smoke intentionally uses an inline generic no-auth agent. It
does not prove Claude, Codex, or Gemini subscription-backed consensus rounds.
That is blocked on issue #29, which must restore credentials, templates, and
harness configs into the Kubernetes-hosted Hub without host-local upload paths.
