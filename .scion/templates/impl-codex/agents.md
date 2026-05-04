# Operating Instructions

You are running inside a Scion-managed container. The repository is checked out
in your current working directory on a branch created for this agent. Do not
assume `/workspace` exists; use `pwd` if you need an absolute path.

## Status Signalling

- Before asking the user or coordinator a question: `sciontool status ask_user "<question>"`
- When intentionally waiting: `sciontool status blocked "<reason>"`
- When the implementation is done: `sciontool status task_completed "<short summary>"`

After `task_completed`, stop. Do not ask "what next?".

## Git Workflow

- Work on the branch you started on. Do not push to `main`, the base branch, or any branch other than your own.
- Run the project test command before completing. `task verify` is preferred when available.
- Commit your work with a clear message. Avoid destructive history changes and force pushes.
- In Hub-backed git groves, push your current branch when `origin` is configured: `git push -u origin HEAD`.
- If push is unavailable, leave the commit locally and mention that in your completion status.

## Scion CLI Use

- Use `scion --help` when you need command details.
- Use `--non-interactive` for Scion CLI commands.
- Use `--format json` when you need machine-readable output.
- Use `--notify` when starting or messaging agents so progress returns through Scion.
- Do not use `--global`; stay inside the current grove.
- Do not use `--no-hub`; scion-ops supports Hub-backed Kubernetes operation only.
- Do not inspect or modify `.scion` internals unless your task is specifically about Scion configuration.

## Messages

Scion messages may arrive with markers like:

```text
---BEGIN SCION MESSAGE---
---END SCION MESSAGE---
```

If a coordinator or user messages you through Scion, reply with `scion message`
so the response is visible in the Hub.
