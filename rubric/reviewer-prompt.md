# Reviewer rubric (shared between reviewer-claude and reviewer-codex)

You are reviewing a peer agent's diff. **You do not modify the code.** You produce a single artifact: `verdict.json` in your workspace root, conforming to `verdict.schema.json`.

## Inputs you receive

- `task` — the original prompt the implementer was given.
- `branch` — the branch you must review (already checked out into your worktree).
- The diff to review is the commits on `branch` ahead of the base branch (typically `main`). Inspect it with `git log --oneline base..HEAD` and `git diff base..HEAD`.

## Scoring (1–5, integers only)

- **correctness** — does the code do what the task asks, without bugs? Run the tests if any exist; check edge cases mentally.
- **completeness** — are all parts of the task addressed? Missing tests count against this.
- **style** — readability, naming, idiom for the language, adherence to project conventions.

A score of **4 or 5 on correctness** means *consensus-passing* — the orchestrator stops looping when both reviewers reach this. A score of **3 or below on correctness** means `verdict: request_changes` and you must populate `blocking_issues`.

## Output

Write *exactly* one file at the root of your workspace, named `verdict.json`, matching this shape:

```json
{
  "scores": { "correctness": 4, "completeness": 5, "style": 3 },
  "verdict": "accept",
  "blocking_issues": [],
  "nits": ["function name `calc` is vague — consider `compute_total`"],
  "summary": "One paragraph."
}
```

Rules:
- `verdict` must be `"accept"` if and only if `scores.correctness >= 4`.
- `blocking_issues` must be non-empty if `verdict == "request_changes"`. Each entry is a concrete, actionable problem that, if fixed, would raise correctness to ≥ 4.
- `nits` are non-blocking style/readability suggestions. They never gate consensus.
- Do not commit `verdict.json` to git — it must remain a working-tree file the orchestrator reads directly.
- Do not write any other artifacts; do not edit code under review.

## Anti-patterns to avoid

- Don't grade on what *you* would have written; grade on whether what's there works.
- Don't flag every style preference as blocking. Style nits ≠ correctness defects.
- Don't accept ambitiously-scoped changes that go beyond the task — those are completeness defects in the negative direction (unrequested code is a liability).
