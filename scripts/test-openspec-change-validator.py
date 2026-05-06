#!/usr/bin/env python3
"""Focused checks for the OpenSpec change validator."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-openspec-change.py"


def _run(project_root: Path, change: str) -> tuple[int, dict[str, object]]:
    result = subprocess.run(
        [
            "python3",
            str(VALIDATOR),
            "--project-root",
            str(project_root),
            "--change",
            change,
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _valid_tree(root: Path) -> None:
    change = root / "openspec" / "changes" / "add-widget"
    _write(
        change / "proposal.md",
        "# Proposal: Add Widget\n\n## Scope\n\nIn scope: add a widget.\n",
    )
    _write(
        change / "design.md",
        "# Design: Add Widget\n\nUse the existing UI path.\n",
    )
    _write(
        change / "tasks.md",
        "# Tasks\n\n- [ ] 1.1 Add widget behavior\n",
    )
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
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _valid_tree(root)

        code, payload = _run(root, "add-widget")
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert payload["spec_files"] == ["openspec/changes/add-widget/specs/widgets/spec.md"], payload

        (root / "openspec" / "changes" / "add-widget" / "design.md").unlink()
        code, payload = _run(root, "add-widget")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any("design.md" in item["path"] for item in payload["errors"]), payload

        code, payload = _run(root, "missing-widget")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any("artifact directory" in item["message"] for item in payload["errors"]), payload

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
