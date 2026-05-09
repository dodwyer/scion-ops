#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "PyYAML>=6,<7",
# ]
# ///
"""Exercise MCP base-branch defaults for legacy and steward flows."""

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


def main() -> int:
    module = _load_mcp_module()
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
        _git(project, "remote", "set-head", "origin", "main")
        _git(project, "checkout", "-b", "round-example")

        assert module._default_base_branch(str(project)) == "round-example"
        assert module._default_steward_base_branch(str(project)) == "main"

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
