#!/usr/bin/env python3
"""Focused checks for steward session validation."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-steward-session.py"


def _run(project_root: Path, kind: str, *extra: str) -> tuple[int, dict[str, object]]:
    result = subprocess.run(
        [
            "python3",
            str(VALIDATOR),
            "--project-root",
            str(project_root),
            "--session-id",
            "s1",
            "--kind",
            kind,
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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _valid_openspec_tree(root: Path) -> None:
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


def _write_state(root: Path, payload: dict[str, object]) -> None:
    state = root / ".scion-ops" / "sessions" / "s1" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _init_repo(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _write(root / "README.md", "# Test\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    _git(root, "checkout", "-b", "round-s1-spec-integration")
    _valid_openspec_tree(root)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add openspec")


def _spec_state() -> dict[str, object]:
    return {
        "version": 1,
        "session_id": "s1",
        "kind": "spec",
        "change": "add-widget",
        "base_branch": "main",
        "status": "ready",
        "phase": "complete",
        "branches": {"integration": "round-s1-spec-integration"},
        "agents": {},
        "validation": {"status": "passed", "command": "python3 scripts/validate-openspec-change.py"},
        "blockers": [],
        "next_actions": ["start implementation"],
    }


def _implementation_state() -> dict[str, object]:
    return {
        "version": 1,
        "session_id": "s1",
        "kind": "implementation",
        "change": "add-widget",
        "base_branch": "main",
        "status": "ready",
        "phase": "complete",
        "branches": {"integration": "round-s1-spec-integration"},
        "agents": {},
        "implementation": {"branch": "round-s1-spec-integration"},
        "reviews": [],
        "final_review": {"verdict": "accept"},
        "verification": {"status": "passed", "command": "task verify"},
        "blockers": [],
        "next_actions": ["open PR"],
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _init_repo(root)

        _write_state(root, _spec_state())
        code, payload = _run(root, "spec", "--require-ready")
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert payload["branch"]["resolved_ref"] == "round-s1-spec-integration", payload

        _git(root, "checkout", "-b", "round-s1-spec-steward")
        _write_state(root, _spec_state())
        _git(root, "add", ".scion-ops/sessions/s1/state.json")
        _git(root, "commit", "-m", "record spec steward state")
        _git(root, "checkout", "main")
        code, payload = _run(root, "spec", "--require-ready")
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert payload["state_source"].startswith("round-s1-spec-steward:"), payload
        assert payload["openspec_validation_source"] == "round-s1-spec-integration", payload

        _write_state(root, _implementation_state())
        code, payload = _run(root, "implementation", "--require-ready")
        assert code == 0, payload
        assert payload["ok"] is True, payload

        blocked = _implementation_state()
        blocked["final_review"] = {"verdict": "reject"}
        _write_state(root, blocked)
        code, payload = _run(root, "implementation", "--require-ready")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any("final_review" in item["path"] for item in payload["errors"]), payload

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
