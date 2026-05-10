#!/usr/bin/env python3
"""Focused checks for steward PR finalization."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINALIZER = ROOT / "scripts" / "finalize-steward-pr.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _valid_openspec_tree(root: Path) -> None:
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


def _init_project(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _write(root / "README.md", "# Project\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    _git(root, "checkout", "-b", "round-s1-integration")
    _valid_openspec_tree(root)
    _write(root / "app.txt", "implemented\n")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "implement widget")
    _git(root, "checkout", "main")


def _write_state(root: Path, payload: dict[str, object]) -> None:
    path = root / ".scion-ops" / "sessions" / "s1" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _implementation_state(status: str = "ready", verdict: str = "accept") -> dict[str, object]:
    return {
        "version": 1,
        "session_id": "s1",
        "kind": "implementation",
        "change": "add-widget",
        "base_branch": "main",
        "status": status,
        "phase": "complete",
        "branches": {"integration": "round-s1-integration"},
        "agents": {
            "round-s1-impl-codex": {"template": "impl-codex", "status": "completed"},
            "round-s1-final-review": {"template": "final-reviewer-codex", "status": "completed"},
        },
        "implementation": {"branch": "round-s1-integration"},
        "final_review": {"verdict": verdict},
        "verification": {"status": "passed", "commands": ["task verify"]},
        "blockers": [],
        "next_actions": ["open PR"],
    }


def _spec_state(status: str = "ready", verdict: str = "accept") -> dict[str, object]:
    return {
        "version": 1,
        "session_id": "s1",
        "kind": "spec",
        "change": "add-widget",
        "base_branch": "main",
        "status": status,
        "phase": "complete",
        "branches": {"integration": "round-s1-integration"},
        "agents": {
            "clarifier": {"template": "spec-goal-clarifier", "status": "completed"},
            "explorer": {"template": "spec-repo-explorer", "status": "completed"},
            "author": {"template": "spec-author", "status": "completed"},
            "ops_review": {"template": "spec-ops-reviewer", "status": "completed"},
        },
        "review": {"verdict": verdict},
        "validation": {"status": "passed"},
        "blockers": [],
        "next_actions": ["open PR"],
    }


def _fake_gh(bin_dir: Path) -> Path:
    script = bin_dir / "gh"
    script.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["SCION_FAKE_GH_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\\n")

if args[:2] == ["pr", "list"]:
    existing = os.environ.get("SCION_FAKE_GH_EXISTING", "")
    if existing:
        print(json.dumps([{
            "number": 12,
            "url": existing,
            "state": "OPEN",
            "title": "Existing PR",
            "baseRefName": "main",
            "headRefName": "round-s1-integration",
        }]))
    else:
        print("[]")
    raise SystemExit(0)

if args[:2] == ["pr", "create"]:
    print(os.environ.get("SCION_FAKE_GH_CREATED", "https://github.com/example/project/pull/34"))
    raise SystemExit(0)

print("unsupported gh command", file=sys.stderr)
raise SystemExit(2)
"""
    )
    script.chmod(0o755)
    return script


def _run_finalizer(
    root: Path,
    env: dict[str, str],
    *extra: str,
    kind: str = "implementation",
) -> tuple[int, dict[str, object]]:
    result = subprocess.run(
        [
            "python3",
            str(FINALIZER),
            "--project-root",
            str(root),
            "--session-id",
            "s1",
            "--kind",
            kind,
            "--change",
            "add-widget",
            "--json",
            *extra,
        ],
        env={**os.environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def _log_entries(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / "project"
        bin_dir = base / "bin"
        log = base / "gh.log"
        project.mkdir()
        bin_dir.mkdir()
        _fake_gh(bin_dir)
        _init_project(project)

        env = {
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
            "SCION_FAKE_GH_LOG": str(log),
        }

        _write_state(project, _implementation_state())
        code, payload = _run_finalizer(project, env, "--draft", "--record-state")
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert payload["created"] is True, payload
        assert payload["draft"] is True, payload
        assert payload["head"] == "round-s1-integration", payload
        assert payload["base"] == "main", payload
        assert payload["pr_url"] == "https://github.com/example/project/pull/34", payload
        assert payload["state_recording"]["state_path"].endswith("/.scion-ops/sessions/s1/state.json"), payload
        entries = _log_entries(log)
        assert entries[0][:2] == ["pr", "list"], entries
        assert entries[1][:2] == ["pr", "create"], entries
        assert "--draft" in entries[1], entries
        assert entries[1][entries[1].index("--head") + 1] == "round-s1-integration", entries
        recorded_state = json.loads((project / ".scion-ops" / "sessions" / "s1" / "state.json").read_text())
        assert recorded_state["pull_request"]["pr_url"] == "https://github.com/example/project/pull/34", recorded_state
        assert recorded_state["next_actions"] == ["Review pull request https://github.com/example/project/pull/34"]
        recorded_pr = json.loads((project / ".scion-ops" / "sessions" / "s1" / "pr.json").read_text())
        assert "validation" not in recorded_pr, recorded_pr
        assert recorded_pr["kind"] == "implementation", recorded_pr

        log.unlink()
        existing_env = {**env, "SCION_FAKE_GH_EXISTING": "https://github.com/example/project/pull/12"}
        code, payload = _run_finalizer(project, existing_env)
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert payload["created"] is False, payload
        assert payload["pr_url"] == "https://github.com/example/project/pull/12", payload
        entries = _log_entries(log)
        assert len(entries) == 1, entries
        assert entries[0][:2] == ["pr", "list"], entries

        log.unlink()
        _write_state(project, _implementation_state(status="blocked", verdict="reject"))
        code, payload = _run_finalizer(project, env)
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert payload["error"] == "steward session is not ready for a PR", payload
        assert _log_entries(log) == [], log.read_text() if log.exists() else ""

        log.unlink(missing_ok=True)
        _write_state(project, _spec_state())
        code, payload = _run_finalizer(project, env, "--record-state", kind="spec")
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert payload["kind"] == "spec", payload
        assert payload["created"] is True, payload
        assert payload["pr_url"] == "https://github.com/example/project/pull/34", payload
        recorded_state = json.loads((project / ".scion-ops" / "sessions" / "s1" / "state.json").read_text())
        assert recorded_state["pull_request"]["kind"] == "spec", recorded_state
        assert recorded_state["pull_request"]["head"] == "round-s1-integration", recorded_state

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
