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
    finally:
        if old_cli_flag is None:
            os.environ.pop("SCION_OPS_USE_OPENSPEC_CLI", None)
        else:
            os.environ["SCION_OPS_USE_OPENSPEC_CLI"] = old_cli_flag

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
