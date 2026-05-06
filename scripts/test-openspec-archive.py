#!/usr/bin/env python3
"""Exercise the OpenSpec archive lifecycle on a sample project."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVER = ROOT / "scripts" / "archive-openspec-change.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _sample(root: Path) -> None:
    change = root / "openspec" / "changes" / "add-widget"
    _write(change / "proposal.md", "# Proposal: Add Widget\n\n## Scope\n\nAdd widget behavior.\n")
    _write(change / "design.md", "# Design: Add Widget\n\nUse the existing widget path.\n")
    _write(change / "tasks.md", "# Tasks\n\n- [x] 1.1 Add widget behavior\n")
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


def _run(root: Path, *extra: str) -> tuple[int, dict[str, object]]:
    result = subprocess.run(
        [
            "python3",
            str(ARCHIVER),
            "--project-root",
            str(root),
            "--change",
            "add-widget",
            "--json",
            *extra,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _sample(root)

        code, payload = _run(root)
        assert code == 0, payload
        assert payload["dry_run"] is True, payload
        assert payload["synced_specs"][0]["action"] == "would_sync", payload
        assert (root / "openspec" / "changes" / "add-widget").exists()

        code, payload = _run(root, "--yes")
        assert code == 0, payload
        assert payload["dry_run"] is False, payload
        assert not (root / "openspec" / "changes" / "add-widget").exists()
        assert payload["archive_path"].startswith("openspec/changes/archive/"), payload
        archived = root / payload["archive_path"]
        assert (archived / "proposal.md").exists()
        accepted = root / "openspec" / "specs" / "widgets" / "spec.md"
        text = accepted.read_text()
        assert "scion-ops:accepted-change add-widget" in text
        assert "Requirement: Widget Creation" in text

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
