#!/usr/bin/env python3
"""Exercise a basic OpenSpec steward to implementation steward loop."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    return result


def _git(root: Path, *args: str) -> str:
    return _run(["git", "-C", str(root), *args]).stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _spec_branches(session_id: str) -> dict[str, str]:
    return {
        "steward": f"round-{session_id}-spec-steward",
        "clarifier": f"round-{session_id}-spec-clarifier",
        "explorer": f"round-{session_id}-spec-explorer",
        "author": f"round-{session_id}-spec-author",
        "review": f"round-{session_id}-spec-ops-review",
        "integration": f"round-{session_id}-spec-integration",
    }


def _implementation_branches(session_id: str) -> dict[str, str]:
    return {
        "steward": f"round-{session_id}-implementation-steward",
        "implementer": f"round-{session_id}-impl-codex",
        "secondary_implementer": f"round-{session_id}-impl-claude",
        "final_review": f"round-{session_id}-final-review",
        "integration": f"round-{session_id}-integration",
    }


def _setup_project(base: Path) -> tuple[Path, Path]:
    origin = base / "origin.git"
    project = base / "project"
    _run(["git", "init", "--bare", str(origin)])
    _run(["git", "init", str(project)])
    _git(project, "config", "user.email", "dev@example.invalid")
    _git(project, "config", "user.name", "Dev")
    _write(project / "README.md", "# Loop Fixture\n")
    _write(project / "src" / "loop.txt", "initial\n")
    _git(project, "add", "README.md", "src/loop.txt")
    _git(project, "commit", "-m", "initial")
    _git(project, "branch", "-M", "main")
    _git(project, "remote", "add", "origin", str(origin))
    _git(project, "push", "-u", "origin", "main")
    _git(project, "remote", "set-head", "origin", "main")
    return origin, project


def _make_fake_scion(base: Path) -> tuple[Path, Path]:
    fake_bin = base / "bin"
    fake_log = base / "scion.log"
    fake_bin.mkdir()
    fake_scion = fake_bin / "scion"
    fake_scion.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$SCION_FAKE_LOG\"\n"
        "exit 0\n"
    )
    fake_scion.chmod(0o755)
    return fake_bin, fake_log


def _env(project: Path, fake_bin: Path, fake_log: Path, session_id: str, base_branch: str) -> dict[str, str]:
    return {
        **os.environ,
        "BASE_BRANCH": base_branch,
        "GIT_AUTHOR_EMAIL": "scion-ops@example.invalid",
        "GIT_AUTHOR_NAME": "scion-ops",
        "GIT_COMMITTER_EMAIL": "scion-ops@example.invalid",
        "GIT_COMMITTER_NAME": "scion-ops",
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "SCION_FAKE_LOG": str(fake_log),
        "SCION_OPS_COLLECTION_RECIPIENT": "user:test@example.invalid",
        "SCION_OPS_PROJECT_ROOT": str(project),
        "SCION_OPS_ROUND_PREFLIGHT": "0",
        "SCION_OPS_SESSION_ID": session_id,
    }


def _write_change(project: Path, change: str, iteration: int) -> None:
    change_root = project / "openspec" / "changes" / change
    _write(
        change_root / "proposal.md",
        f"# Proposal: Loop Fixture {iteration}\n\nAdd loop fixture {iteration} behavior.\n",
    )
    _write(
        change_root / "design.md",
        f"# Design: Loop Fixture {iteration}\n\nUse the existing fixture file and no external services.\n",
    )
    _write(
        change_root / "tasks.md",
        "# Tasks\n\n"
        f"- [ ] 1.1 Add loop fixture {iteration} implementation evidence\n"
        f"- [ ] 1.2 Validate loop fixture {iteration}\n",
    )
    _write(
        change_root / "specs" / "loop-fixture" / "spec.md",
        "# Delta for Loop Fixture\n\n"
        "## ADDED Requirements\n\n"
        f"### Requirement: Loop Fixture {iteration}\n"
        f"The system SHALL record loop fixture {iteration} implementation evidence.\n\n"
        f"#### Scenario: Fixture {iteration} is implemented\n"
        "- GIVEN the approved OpenSpec change\n"
        "- WHEN the implementation branch is produced\n"
        f"- THEN loop fixture {iteration} evidence is present\n",
    )


def _load_state(project: Path, branch: str, session_id: str) -> dict[str, Any]:
    _git(project, "fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}")
    text = _git(project, "show", f"origin/{branch}:.scion-ops/sessions/{session_id}/state.json")
    state = json.loads(text)
    assert isinstance(state, dict), state
    return state


def _commit_if_needed(project: Path, message: str) -> None:
    staged = subprocess.run(
        ["git", "-C", str(project), "diff", "--cached", "--quiet"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if staged.returncode == 0:
        return
    assert staged.returncode == 1, staged.stdout
    _git(project, "commit", "-m", message)


def _commit_all(project: Path, message: str) -> None:
    _git(project, "add", ".")
    staged = subprocess.run(
        ["git", "-C", str(project), "diff", "--cached", "--quiet"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    assert staged.returncode == 1, f"expected staged changes for {message}"
    _git(project, "commit", "-m", message)


def _run_validator(
    project: Path,
    *,
    session_id: str,
    kind: str,
    change: str,
    branch: str,
    base_branch: str,
    state_branch: str,
) -> dict[str, Any]:
    args = [
        "python3",
        str(ROOT / "scripts" / "validate-steward-session.py"),
        "--project-root",
        str(project),
        "--session-id",
        session_id,
        "--kind",
        kind,
        "--change",
        change,
        "--branch",
        branch,
        "--base-branch",
        base_branch,
        "--state-branch",
        state_branch,
        "--require-ready",
        "--json",
    ]
    if kind == "spec":
        args.append("--require-multi-harness")
    result = _run(args)
    payload = json.loads(result.stdout)
    assert payload["ok"] is True, payload
    return payload


def _materialize_spec_loop(
    project: Path,
    fake_bin: Path,
    fake_log: Path,
    *,
    iteration: int,
    change: str,
    session_id: str,
) -> dict[str, Any]:
    branches = _spec_branches(session_id)
    env = _env(project, fake_bin, fake_log, session_id, "main")
    env["SCION_OPS_SPEC_CHANGE"] = change
    output = _run(
        [
            "bash",
            str(ROOT / "orchestrator" / "spec-steward.sh"),
            f"Add loop fixture {iteration}",
        ],
        cwd=ROOT,
        env=env,
    ).stdout
    assert f"Starting OpenSpec steward: {branches['steward']}" in output, output

    _git(project, "fetch", "origin", f"refs/heads/{branches['integration']}:refs/remotes/origin/{branches['integration']}")
    _git(project, "checkout", "-B", branches["integration"], f"origin/{branches['integration']}")
    _write_change(project, change, iteration)
    _commit_all(project, f"Add OpenSpec change {change}")
    _git(project, "push", "origin", f"HEAD:refs/heads/{branches['integration']}")
    _run(["python3", str(ROOT / "scripts" / "validate-openspec-change.py"), "--project-root", str(project), "--change", change])

    _git(project, "fetch", "origin", f"refs/heads/{branches['steward']}:refs/remotes/origin/{branches['steward']}")
    _git(project, "checkout", "-B", branches["steward"], f"origin/{branches['steward']}")
    _run(
        [
            "python3",
            str(ROOT / "scripts" / "steward-state.py"),
            "spec-init",
            "--project-root",
            str(project),
            "--session-id",
            session_id,
            "--change",
            change,
            "--base-branch",
            "main",
        ]
    )
    _git(project, "add", f".scion-ops/sessions/{session_id}/state.json")
    _commit_if_needed(project, f"Record spec state for {session_id}")

    _run(
        [
            "python3",
            str(ROOT / "scripts" / "steward-state.py"),
            "spec-ready",
            "--project-root",
            str(project),
            "--session-id",
            session_id,
            "--change",
            change,
            "--base-branch",
            "main",
            "--integration-branch",
            branches["integration"],
            "--validation-command",
            f"python3 scripts/validate-openspec-change.py --project-root . --change {change}",
            "--review-summary",
            f"accepted loop fixture {iteration}",
        ]
    )
    _git(project, "add", f".scion-ops/sessions/{session_id}/state.json")
    _commit_if_needed(project, f"Mark spec ready for {session_id}")
    _git(project, "push", "origin", f"HEAD:refs/heads/{branches['steward']}")

    payload = _run_validator(
        project,
        session_id=session_id,
        kind="spec",
        change=change,
        branch=branches["integration"],
        base_branch="main",
        state_branch=branches["steward"],
    )
    return {"branches": branches, "validation": payload}


def _materialize_implementation_loop(
    project: Path,
    fake_bin: Path,
    fake_log: Path,
    *,
    iteration: int,
    change: str,
    session_id: str,
    base_branch: str,
) -> dict[str, Any]:
    branches = _implementation_branches(session_id)
    output = _run(
        [
            "bash",
            str(ROOT / "orchestrator" / "implementation-steward.sh"),
            "--change",
            change,
            f"Implement loop fixture {iteration}",
        ],
        cwd=ROOT,
        env=_env(project, fake_bin, fake_log, session_id, base_branch),
    ).stdout
    assert f"Starting implementation steward: {branches['steward']}" in output, output

    initial_state = _load_state(project, branches["steward"], session_id)
    assert initial_state["kind"] == "implementation", initial_state
    assert initial_state["status"] == "running", initial_state
    assert initial_state["base_branch"] == base_branch, initial_state

    _git(project, "fetch", "origin", f"refs/heads/{branches['integration']}:refs/remotes/origin/{branches['integration']}")
    _git(project, "checkout", "-B", branches["integration"], f"origin/{branches['integration']}")
    _write(project / "implementation" / f"{change}.txt", f"implemented loop fixture {iteration}\n")
    tasks = project / "openspec" / "changes" / change / "tasks.md"
    tasks.write_text(tasks.read_text().replace("- [ ]", "- [x]"))
    _commit_all(project, f"Implement {change}")
    integration_sha = _git(project, "rev-parse", "HEAD")
    _git(project, "push", "origin", f"HEAD:refs/heads/{branches['integration']}")
    _git(project, "push", "origin", f"{integration_sha}:refs/heads/{branches['final_review']}")

    _git(project, "fetch", "origin", f"refs/heads/{branches['steward']}:refs/remotes/origin/{branches['steward']}")
    _git(project, "checkout", "-B", branches["steward"], f"origin/{branches['steward']}")
    _run(
        [
            "python3",
            str(ROOT / "scripts" / "steward-state.py"),
            "implementation-ready",
            "--project-root",
            str(project),
            "--session-id",
            session_id,
            "--change",
            change,
            "--base-branch",
            base_branch,
            "--integration-branch",
            branches["integration"],
            "--verification-command",
            f"python3 scripts/validate-openspec-change.py --project-root . --change {change}",
            "--final-review-summary",
            f"accepted implementation loop fixture {iteration}",
        ]
    )
    _git(project, "add", f".scion-ops/sessions/{session_id}/state.json")
    _commit_if_needed(project, f"Mark implementation ready for {session_id}")
    _git(project, "push", "origin", f"HEAD:refs/heads/{branches['steward']}")

    payload = _run_validator(
        project,
        session_id=session_id,
        kind="implementation",
        change=change,
        branch=branches["integration"],
        base_branch=base_branch,
        state_branch=branches["steward"],
    )
    return {"branches": branches, "validation": payload}


def _assert_fake_scion_covered(fake_log: Path, spec_session: str, implementation_session: str) -> None:
    log = fake_log.read_text()
    assert f"round-{spec_session}-spec-steward" in log, log
    assert "--type spec-steward" in log, log
    assert "mandatory_first_actions:" in log, log
    assert "start_clarifier:" in log, log
    assert "start_explorer:" in log, log
    assert "clarifier_summary_file:" in log, log
    assert "explorer_summary_file:" in log, log
    assert "ops_review_verdict_file:" in log, log
    assert "summary_file:" in log, log
    assert f'scion --profile "kind" start "round-{spec_session}-spec-clarifier"' in log, log
    assert f'scion --profile "kind" start "round-{spec_session}-spec-explorer"' in log, log
    assert "wait_review:" in log, log
    assert '--timeout-seconds "420"' in log, log
    assert f"round-{spec_session}-spec-ops-review" in log, log
    assert f"round-{implementation_session}-implementation-steward" in log, log
    assert "--type implementation-steward" in log, log


def run_loop(iterations: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _origin, project = _setup_project(base)
        fake_bin, fake_log = _make_fake_scion(base)
        for iteration in range(1, iterations + 1):
            change = f"loop-fixture-{iteration}"
            spec_session = f"loop-{iteration}-spec"
            implementation_session = f"loop-{iteration}-impl"
            spec_result = _materialize_spec_loop(
                project,
                fake_bin,
                fake_log,
                iteration=iteration,
                change=change,
                session_id=spec_session,
            )
            implementation_result = _materialize_implementation_loop(
                project,
                fake_bin,
                fake_log,
                iteration=iteration,
                change=change,
                session_id=implementation_session,
                base_branch=spec_result["branches"]["integration"],
            )
            _assert_fake_scion_covered(fake_log, spec_session, implementation_session)
            results.append(
                {
                    "iteration": iteration,
                    "change": change,
                    "spec_session": spec_session,
                    "implementation_session": implementation_session,
                    "spec_branch": spec_result["branches"]["integration"],
                    "implementation_branch": implementation_result["branches"]["integration"],
                }
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    assert args.iterations > 0, "--iterations must be positive"
    results = run_loop(args.iterations)
    print(json.dumps({"ok": True, "iterations": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
