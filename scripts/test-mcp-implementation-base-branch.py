#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "PyYAML>=6,<7",
# ]
# ///
"""Exercise MCP implementation validation against an explicit base branch."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_mcp_module():
    os.environ.setdefault("SCION_OPS_ROOT", str(ROOT))
    spec = importlib.util.spec_from_file_location("scion_ops_mcp", ROOT / "mcp_servers" / "scion_ops.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load mcp_servers/scion_ops.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["scion_ops_mcp"] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    return result.stdout.strip()


def _run_script(args: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        env={**os.environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    return result.stdout


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _sample_change(root: Path) -> None:
    change = root / "openspec" / "changes" / "add-widget"
    _write(change / "proposal.md", "# Proposal: Add Widget\n\nAdd widget behavior.\n")
    _write(change / "design.md", "# Design: Add Widget\n\nUse the existing path.\n")
    _write(change / "tasks.md", "# Tasks\n\n- [ ] 1.1 Add widget behavior\n")
    _write(
        change / "specs" / "widgets" / "spec.md",
        "# Delta for Widgets\n\n"
        "## ADDED Requirements\n\n"
        "### Requirement: Widget Creation\n"
        "The system SHALL create a widget.\n\n"
        "#### Scenario: Create widget\n"
        "- GIVEN a valid request\n"
        "- WHEN the widget is created\n"
        "- THEN the widget is visible\n",
    )


def main() -> int:
    module = _load_mcp_module()
    old_cli_flag = os.environ.get("SCION_OPS_USE_OPENSPEC_CLI")
    try:
        os.environ["SCION_OPS_USE_OPENSPEC_CLI"] = "0"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            origin = base / "origin.git"
            project = base / "project"

            subprocess.run(["git", "init", "--bare", str(origin)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "init", str(project)], check=True, stdout=subprocess.DEVNULL)
            _git(project, "config", "user.email", "dev@example.invalid")
            _git(project, "config", "user.name", "Dev")
            (project / "README.md").write_text("# Project\n")
            _git(project, "add", "README.md")
            _git(project, "commit", "-m", "initial")
            _git(project, "branch", "-M", "main")
            _git(project, "remote", "add", "origin", str(origin))
            _git(project, "push", "-u", "origin", "main")

            _git(project, "checkout", "-b", "accepted-spec")
            _sample_change(project)
            _git(project, "add", "openspec")
            _git(project, "commit", "-m", "add accepted spec")
            _git(project, "push", "-u", "origin", "accepted-spec")

            _git(project, "checkout", "main")
            _git(project, "branch", "-D", "accepted-spec")
            (project / "local-only.txt").write_text("dirty local worktree\n")
            assert not (project / "openspec" / "changes" / "add-widget").exists()

            local_result, local_validation = module._validate_spec_change_for_start(project, "add-widget")
            assert local_result["validation_ref"] == "local_worktree", local_result
            assert local_validation["ok"] is False, local_validation

            branch_result, branch_validation = module._validate_spec_change_for_start(
                project,
                "add-widget",
                "accepted-spec",
            )
            assert branch_result["source"] == "openspec_remote_validator", branch_result
            assert branch_result["validation_ref"] == "origin/accepted-spec", branch_result
            assert branch_validation["validation_ref"] == "origin/accepted-spec", branch_validation
            assert branch_validation["ok"] is True, branch_validation
            assert not (project / "openspec" / "changes" / "add-widget").exists()
            assert (project / "local-only.txt").exists()

            captured_runs: list[list[str]] = []
            original_run = module._run
            original_validate = module._validate_spec_change_for_start
            try:
                module._validate_spec_change_for_start = lambda *_args, **_kwargs: (
                    {"ok": True, "source": "stub"},
                    {"ok": True},
                )

                def fake_run(args: list[str], **_kwargs: object) -> dict[str, object]:
                    captured_runs.append(args)
                    return {
                        "ok": True,
                        "returncode": 0,
                        "timed_out": False,
                        "command": args,
                        "output": "",
                    }

                module._run = fake_run
                start_response = module.scion_ops_start_impl_round(
                    project_root=str(project),
                    change="add-widget",
                    goal="Implement widget",
                    base_branch="accepted-spec",
                )
            finally:
                module._run = original_run
                module._validate_spec_change_for_start = original_validate

            assert start_response["ok"] is True, start_response
            assert captured_runs[-1] == [
                "task",
                "spec:implement",
                "--",
                "--change",
                "add-widget",
                "Implement widget",
            ], captured_runs

            launcher_env = {
                "SCION_OPS_PROJECT_ROOT": str(project),
                "BASE_BRANCH": "accepted-spec",
                "SCION_OPS_DRY_RUN": "1",
                "SCION_OPS_ROUND_PREFLIGHT": "0",
            }
            fake_bin = base / "bin"
            fake_scion = fake_bin / "scion"
            fake_log = base / "scion.log"
            fake_bin.mkdir()
            fake_scion.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$SCION_FAKE_LOG\"\nexit 0\n")
            fake_scion.chmod(0o755)
            dry_run_output = _run_script(
                [
                    "bash",
                    str(ROOT / "orchestrator" / "implementation-steward.sh"),
                    "--change",
                    "add-widget",
                    "Implement widget",
                ],
                {
                    **launcher_env,
                    "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                    "SCION_FAKE_LOG": str(fake_log),
                    "SCION_OPS_SESSION_ID": "test-implementation",
                },
            )
            assert "Dry run command:" in dry_run_output, dry_run_output
            assert "Starting implementation steward: round-test-implementation-implementation-steward" in dry_run_output
            assert "Base branch: accepted-spec" in dry_run_output, dry_run_output
            assert '"ok": true' in dry_run_output, dry_run_output
            assert "pre-create and verify the remote child branch" in dry_run_output, dry_run_output
            assert "scripts/precreate-agent-branch.py" in dry_run_output, dry_run_output
            assert "scripts/impl-publish-handoff.sh" in dry_run_output, dry_run_output
            assert "--require-head-sha-ancestor" in dry_run_output, dry_run_output
            assert "--require-json-fields verdict summary blocking_issues" in dry_run_output, dry_run_output

            steward_output = _run_script(
                [
                    "bash",
                    str(ROOT / "orchestrator" / "implementation-steward.sh"),
                    "--change",
                    "add-widget",
                    "Implement widget",
                ],
                {
                    "SCION_OPS_PROJECT_ROOT": str(project),
                    "BASE_BRANCH": "accepted-spec",
                    "SCION_OPS_ROUND_PREFLIGHT": "0",
                    "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                    "SCION_FAKE_LOG": str(fake_log),
                    "SCION_OPS_SESSION_ID": "test-implementation",
                },
            )
            assert "Starting implementation steward: round-test-implementation-implementation-steward" in steward_output
            assert "Initialized steward state on branch: round-test-implementation-implementation-steward" in steward_output
            assert "Base branch: accepted-spec" in steward_output, steward_output
            assert "--type implementation-steward" in fake_log.read_text(), fake_log.read_text()

            steward_branch = "round-test-implementation-implementation-steward"
            final_branch = "round-test-implementation-integration"
            _git(project, "fetch", "origin", f"refs/heads/{steward_branch}:refs/remotes/origin/{steward_branch}")
            state = json.loads(
                _git(
                    project,
                    "show",
                    f"origin/{steward_branch}:.scion-ops/sessions/test-implementation/state.json",
                )
            )
            assert state["kind"] == "implementation", state
            assert state["status"] == "running", state
            assert state["branches"]["steward"] == steward_branch, state
            assert state["branches"]["integration"] == final_branch, state
            assert not _git(project, "ls-remote", "--heads", "origin", "round-test-implementation-final-review")

            validation = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts" / "validate-steward-session.py"),
                    "--project-root",
                    str(project),
                    "--session-id",
                    "test-implementation",
                    "--kind",
                    "implementation",
                    "--change",
                    "add-widget",
                    "--branch",
                    final_branch,
                    "--base-branch",
                    "accepted-spec",
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            assert validation.returncode == 0, validation.stdout
            assert not (project / "openspec" / "changes" / "add-widget").exists()
            assert (project / "local-only.txt").exists()
    finally:
        if old_cli_flag is None:
            os.environ.pop("SCION_OPS_USE_OPENSPEC_CLI", None)
        else:
            os.environ["SCION_OPS_USE_OPENSPEC_CLI"] = old_cli_flag

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
