# scion-ops

Dueling-agents consensus loop on top of [GoogleCloudPlatform/scion](https://github.com/GoogleCloudPlatform/scion).
Two implementer agents (Claude + Codex) draft the same prompt in isolated worktrees; cross-review with a 1–5 rubric; the highest-scoring draft is promoted to integrator; tests are the binding gate.

## Quickstart

```bash
task install      # bootstrap host: scion CLI, runtime checks, PATH
task init         # scion init --machine + scion init for this grove
task hub:up       # start local Scion Hub on :8080
task round -- "your prompt here"
```

Audit trail lands in `state/<round-id>.json`; agents are visible at <http://localhost:8080>.

## Layout

- `.scion/templates/` — agent role definitions (impl/reviewer × {claude,codex} + final-reviewer-codex)
- `orchestrator/round.sh` — consensus state machine
- `rubric/` — reviewer prompt + verdict JSON schema
- `scripts/bootstrap-host.sh` — one-shot host preflight

See `/home/david/.claude/plans/https-claude-ai-share-a56e403d-3326-4857-staged-rocket.md` for the full design.
