#!/usr/bin/env python3
"""Focused tests for implementation steward orchestration helpers."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, check: bool = True):
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
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


def load_hub_templates_module():
    spec = importlib.util.spec_from_file_location(
        "hub_managed_templates",
        ROOT / "scripts" / "hub-managed-templates.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["hub_managed_templates"] = module
    spec.loader.exec_module(module)
    return module


def test_template_harness_maps_are_in_sync() -> None:
    module = load_hub_templates_module()
    expected = module.EXPECTED_HARNESS
    for name, harness in {
        "impl-claude": "claude",
        "reviewer-claude": "claude",
        "final-reviewer-gemini": "gemini",
    }.items():
        assert expected.get(name) == harness, expected

    preflight = (ROOT / "scripts" / "kind-round-preflight.sh").read_text()
    for name, harness in {
        "impl-claude": "claude",
        "reviewer-claude": "claude",
        "final-reviewer-gemini": "gemini",
    }.items():
        assert re.search(rf"\[{re.escape(name)}\]={re.escape(harness)}\b", preflight), preflight


def setup_origin_with_diverged_main(base: Path) -> tuple[Path, Path]:
    origin = base / "origin.git"
    work = base / "work"
    run(["git", "init", "--bare", str(origin)])
    run(["git", "init", "-b", "main", str(work)])
    git(work, "config", "user.email", "test@example.invalid")
    git(work, "config", "user.name", "Test User")
    write(work / "README.md", "initial\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "initial")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-u", "origin", "main")
    git(work, "checkout", "-b", "steward")
    git(work, "push", "origin", "HEAD:refs/heads/steward")
    git(work, "checkout", "main")
    write(work / "README.md", "main moved\n")
    git(work, "commit", "-am", "move main")
    git(work, "push", "origin", "main")
    return origin, work


def test_precreate_agent_branch_fetches_base_for_shallow_checkout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        origin, work = setup_origin_with_diverged_main(base)
        project = base / "project"
        run(["git", "clone", "--single-branch", "--branch", "steward", f"file://{origin}", str(project)])

        result = run(
            [
                "python3",
                str(ROOT / "scripts" / "precreate-agent-branch.py"),
                "--project-root",
                str(project),
                "--branch",
                "child",
                "--base-branch",
                "main",
            ]
        )
        payload = json.loads(result.stdout)
        assert payload["ok"] is True, payload
        assert payload["created"] is True, payload
        assert payload["base_sha"] == payload["child_sha"], payload
        assert git(work, "ls-remote", "--heads", "origin", "child").split()[0] == git(
            work, "rev-parse", "origin/main"
        )


def setup_publish_repo(base: Path) -> tuple[Path, str]:
    origin = base / "origin.git"
    project = base / "project"
    run(["git", "init", "--bare", str(origin)])
    run(["git", "init", "-b", "main", str(project)])
    git(project, "config", "user.email", "test@example.invalid")
    git(project, "config", "user.name", "Test User")
    write(project / "README.md", "publish\n")
    git(project, "add", ".")
    git(project, "commit", "-m", "initial")
    git(project, "remote", "add", "origin", str(origin))
    git(project, "push", "-u", "origin", "main")
    git(project, "checkout", "-b", "round-s1-impl-codex")
    return project, "round-s1-impl-codex"


def test_impl_publish_handoff_commits_pushes_and_verifies_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project, branch = setup_publish_repo(base)
        handoff = ".scion-ops/sessions/s1/findings/round-s1-impl-codex.json"
        write(project / "src" / "feature.txt", "implemented\n")
        write(
            project / handoff,
            json.dumps(
                {
                    "status": "completed",
                    "changed_files": ["src/feature.txt"],
                    "tasks_completed": ["1.1"],
                    "tests_run": ["unit fixture"],
                    "blockers": [],
                    "summary": "implemented fixture",
                }
            ),
        )

        result = run(
            [
                "bash",
                str(ROOT / "scripts" / "impl-publish-handoff.sh"),
                "--project-root",
                str(project),
                "--session-id",
                "s1",
                "--agent",
                branch,
                "--branch",
                branch,
                "--handoff",
                handoff,
            ]
        )
        assert '"agent": "round-s1-impl-codex"' in result.stdout, result.stdout
        artifact = json.loads(git(project, "show", f"origin/{branch}:{handoff}"))
        assert artifact["agent"] == branch, artifact
        assert artifact["branch"] == branch, artifact
        assert artifact["head_sha"], artifact
        assert git(project, "show", f"origin/{branch}:src/feature.txt") == "implemented"

        wait = run(
            [
                "python3",
                str(ROOT / "scripts" / "wait-for-review-artifact.py"),
                "--project-root",
                str(project),
                "--branch",
                branch,
                "--artifact",
                handoff,
                "--agent",
                branch,
                "--timeout-seconds",
                "0",
                "--poll-interval-seconds",
                "1",
                "--require-head-sha-ancestor",
                "--require-json-fields",
                "agent",
                "status",
                "branch",
                "head_sha",
                "changed_files",
                "tasks_completed",
                "tests_run",
                "blockers",
                "summary",
            ]
        )
        assert json.loads(wait.stdout)["ok"] is True, wait.stdout


def write_sample_change(project: Path, change: str) -> None:
    root = project / "openspec" / "changes" / change
    write(root / "proposal.md", "# Proposal: Add Widget\n\nAdd widget behavior.\n")
    write(root / "design.md", "# Design: Add Widget\n\nUse the existing path.\n")
    write(root / "tasks.md", "# Tasks\n\n- [ ] 1.1 Add widget behavior\n")
    write(
        root / "specs" / "widgets" / "spec.md",
        "# Delta for Widgets\n\n"
        "## ADDED Requirements\n\n"
        "### Requirement: Widget Creation\n"
        "The system SHALL create a widget.\n\n"
        "#### Scenario: Create widget\n"
        "- GIVEN a valid request\n"
        "- WHEN the widget is created\n"
        "- THEN the widget is visible\n",
    )


def test_implementation_steward_prompt_uses_helpers_and_handoff_wait() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        origin = base / "origin.git"
        project = base / "project"
        run(["git", "init", "--bare", str(origin)])
        run(["git", "init", "-b", "main", str(project)])
        git(project, "config", "user.email", "test@example.invalid")
        git(project, "config", "user.name", "Test User")
        write(project / "README.md", "# Project\n")
        write_sample_change(project, "add-widget")
        git(project, "add", ".")
        git(project, "commit", "-m", "add accepted spec")
        git(project, "remote", "add", "origin", str(origin))
        git(project, "push", "-u", "origin", "main")

        fake_bin = base / "bin"
        fake_bin.mkdir()
        fake_scion = fake_bin / "scion"
        fake_scion.write_text("#!/usr/bin/env bash\nexit 0\n")
        fake_scion.chmod(0o755)
        output = run(
            [
                "bash",
                str(ROOT / "orchestrator" / "implementation-steward.sh"),
                "--change",
                "add-widget",
                "Implement widget",
            ],
            env={
                **os.environ,
                "SCION_OPS_PROJECT_ROOT": str(project),
                "SCION_OPS_DRY_RUN": "1",
                "SCION_OPS_ROUND_PREFLIGHT": "0",
                "SCION_OPS_SESSION_ID": "s1",
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            },
        ).stdout
        assert "scripts/precreate-agent-branch.py" in output, output
        assert "scripts/impl-publish-handoff.sh" in output, output
        assert "handoff_file:" in output, output
        assert "--require-head-sha-ancestor" in output, output
        assert "--require-json-fields agent status branch head_sha" in output, output


def main() -> int:
    test_template_harness_maps_are_in_sync()
    test_precreate_agent_branch_fetches_base_for_shallow_checkout()
    test_impl_publish_handoff_commits_pushes_and_verifies_artifact()
    test_implementation_steward_prompt_uses_helpers_and_handoff_wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
