# Operating Instructions

You are running inside a Scion-managed container. The repository is checked out
in your current working directory on a branch created for this steward. Do not
assume `/workspace` exists; use `pwd` if you need an absolute path.

## Status Signalling

- Before asking the user or coordinator a question: `sciontool status ask_user "<question>"`
- When intentionally waiting on child agents, reviews, or external input: `sciontool status blocked "<reason>"`
- When the OpenSpec session is ready or blocked with clear next actions: `sciontool status task_completed "<short summary>"`

Before signalling a ready completion, run the steward-session readiness
validator named in the system prompt. If it fails, update `state.json` as
blocked or continue repairing the session; do not claim ready.

After `task_completed`, stop. Do not ask "what next?".

## Session State

Keep durable coordinator state under `.scion-ops/sessions/<session_id>/`.
Update `state.json` after every phase transition, child completion, validation
run, blocker, and final decision. The state file is the source of truth for
automation that watches or resumes the session.

Use this high-level shape:

```json
{
  "version": 1,
  "session_id": "<session_id>",
  "kind": "spec",
  "change": "<change>",
  "base_branch": "<base_branch>",
  "status": "running",
  "phase": "authoring",
  "branches": {},
  "agents": {},
  "review": {},
  "validation": {},
  "blockers": [],
  "next_actions": []
}
```

## Git Workflow

- Work on the branch you started on for steward state only.
- Do not push to `main`, the base branch, or unrelated branches.
- Child agents own their own branches. The final spec branch is the integration
  branch named in the task prompt.
- Prefer explicit fetch, checkout, merge/cherry-pick, validation, commit, and
  push steps over hidden local state.
- If push is unavailable, record that blocker in `state.json` and in your final
  status.

## Scion CLI Use

- Use `scion --help` when you need command details.
- Use `--non-interactive` for Scion CLI commands.
- Use `--format json` when you need machine-readable output.
- Use `--notify` when starting or messaging agents so progress returns through Scion.
- Do not use `--global`; stay inside the current grove.
- Do not use `--no-hub`; scion-ops supports Hub-backed Kubernetes operation only.

## Messages

Scion messages may arrive with markers like:

```text
---BEGIN SCION MESSAGE---
---END SCION MESSAGE---
```

If a child agent or user messages you through Scion, reply with `scion message`
so the response is visible in the Hub. Collect child summaries from Hub
messages and copy the durable facts into `state.json`.
