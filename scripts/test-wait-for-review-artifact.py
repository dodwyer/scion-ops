#!/usr/bin/env python3
"""Focused checks for review artifact wait diagnostics."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WAITER = ROOT / "scripts" / "wait-for-review-artifact.py"


def run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stdout
    return result


def git(root: Path, *args: str) -> str:
    return run(["git", "-C", str(root), *args]).stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def setup_repo(base: Path) -> tuple[Path, Path]:
    origin = base / "origin.git"
    project = base / "project"
    run(["git", "init", "--bare", str(origin)])
    run(["git", "init", "-b", "main", str(project)])
    git(project, "config", "user.email", "test@example.invalid")
    git(project, "config", "user.name", "Test User")
    write(project / "README.md", "# Review Wait\n")
    git(project, "add", ".")
    git(project, "commit", "-m", "initial")
    git(project, "remote", "add", "origin", str(origin))
    git(project, "push", "-u", "origin", "main")
    git(project, "checkout", "-b", "round-s1-spec-ops-review")
    git(project, "push", "origin", "HEAD:refs/heads/round-s1-spec-ops-review")
    return origin, project


def wait_args(project: Path, output: Path) -> list[str]:
    return [
        "python3",
        str(WAITER),
        "--project-root",
        str(project),
        "--branch",
        "round-s1-spec-ops-review",
        "--artifact",
        ".scion-ops/sessions/s1/findings/ops-review.json",
        "--agent",
        "round-s1-spec-ops-review",
        "--timeout-seconds",
        "0",
        "--poll-interval-seconds",
        "1",
        "--output",
        str(output),
    ]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _origin, project = setup_repo(base)
        output = base / "wait.json"

        missing = run(wait_args(project, output), check=False)
        assert missing.returncode == 2, missing.stdout
        missing_payload = json.loads(output.read_text())
        assert missing_payload["ok"] is False, missing_payload
        assert missing_payload["reason"] == "timeout_waiting_for_review_artifact", missing_payload
        assert missing_payload["artifact"] == ".scion-ops/sessions/s1/findings/ops-review.json", missing_payload

        verdict = {
            "review_type": "spec",
            "verdict": "accept",
            "blocking_issues": [],
            "summary": "accepted",
        }
        write(project / ".scion-ops/sessions/s1/findings/ops-review.json", json.dumps(verdict))
        git(project, "add", ".scion-ops/sessions/s1/findings/ops-review.json")
        git(project, "commit", "-m", "record review verdict")
        git(project, "push", "origin", "HEAD:refs/heads/round-s1-spec-ops-review")

        found = run(wait_args(project, output), check=False)
        assert found.returncode == 0, found.stdout
        found_payload = json.loads(output.read_text())
        assert found_payload["ok"] is True, found_payload
        assert found_payload["artifact_json"]["verdict"] == "accept", found_payload

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
