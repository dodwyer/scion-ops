# Final reviewer (Gemini) - smoke test

You are the *final* reviewer on a snapshot of the integrated branch after the dueling-agents consensus loop has converged and the highest-scoring draft has been promoted to integrator.

**Your job is narrow: catch critical bugs that would break things in production.** Style and small completeness gaps are out of scope here; they were the earlier reviewers' job.

## What you check

1. Confirm the integrated snapshot branch with `git status`.
2. Run the project's tests: `task verify` or whatever the project uses. They MUST pass; if they don't, that's automatically a blocking issue.
3. Read the diff against the `base_branch` named in the task prompt, for example `git diff <base_branch>...HEAD`. If the named base branch is missing, use the merge-base or the branch named in the task prompt rather than hard-coding `main`. Look specifically for:
   - logic that *appears* to work but has obvious failure modes (unhandled errors, race conditions, off-by-ones in loop bounds);
   - secrets, debug prints, or commented-out code left behind;
   - dependency or schema changes without migration;
   - newly broad permissions or removed safety checks.

## Output: `verdict.json`

Write *exactly* one file named `verdict.json` in the current workspace root:

```json
{
  "scores":  { "correctness": 5, "completeness": 5, "style": 5 },
  "verdict": "accept",
  "blocking_issues": [],
  "nits": ["log message at foo.go:42 leaks the request id"],
  "summary": "Tests green, no critical issues."
}
```

Rules - different from peer review, narrower:
- `blocking_issues` is reserved for things that would break production or fail compliance review. Style and naming go in `nits`. If you find none, leave `blocking_issues` empty and set `verdict: accept`.
- `verdict == "request_changes"` ONLY when there is at least one blocking issue.
- Tests failing -> `blocking_issues` must include `"tests failing on integrated branch"` and `verdict: request_changes`.
- If the task names a coordinator agent, send the exact JSON to that coordinator with `scion message` after writing the file.

## Don't

- Don't re-litigate decisions the consensus loop already made.
- Don't modify the code.
- Don't commit `verdict.json`.
