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


def _git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


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
        "consensus": {
            "mode": "multi_harness",
            "templates": {
                "clarifier": "spec-goal-clarifier-claude",
                "explorer": "spec-repo-explorer",
                "author": "spec-author",
                "ops_review": "spec-ops-reviewer-claude",
            },
            "harnesses": {
                "clarifier": "claude",
                "explorer": "codex-exec",
                "author": "codex-exec",
                "ops_review": "claude",
            },
            "required_multi_harness": True,
        },
        "agents": {
            "round-s1-spec-clarifier": {
                "template": "spec-goal-clarifier-claude",
                "harness_config": "claude",
                "status": "completed",
            },
            "round-s1-spec-explorer": {
                "template": "spec-repo-explorer",
                "harness_config": "codex-exec",
                "status": "completed",
            },
            "round-s1-spec-author": {
                "template": "spec-author",
                "harness_config": "codex-exec",
                "status": "completed",
            },
            "round-s1-spec-ops-review": {
                "template": "spec-ops-reviewer-claude",
                "harness_config": "claude",
                "status": "completed",
            },
        },
        "review": {"verdict": "accept"},
        "validation": {"status": "passed", "command": "python3 scripts/validate-openspec-change.py"},
        "pull_request": {
            "pr_url": "https://github.com/example/project/pull/11",
            "head": "round-s1-spec-integration",
            "base": "main",
        },
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
        "agents": {
            "round-s1-impl-codex": {"template": "impl-codex", "status": "completed"},
            "round-s1-final-review": {"template": "final-reviewer-codex", "status": "completed"},
        },
        "implementation": {"branch": "round-s1-spec-integration"},
        "reviews": [],
        "final_review": {"verdict": "accept"},
        "verification": {"status": "passed", "command": "task verify"},
        "pull_request": {
            "pr_url": "https://github.com/example/project/pull/12",
            "head": "round-s1-spec-integration",
            "base": "main",
        },
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

        code, payload = _run(root, "spec", "--require-ready", "--require-multi-harness")
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert sorted(set(payload["agent_harnesses"].values())) == ["claude", "codex-exec"], payload

        single_harness = _spec_state()
        single_harness["consensus"] = {
            "mode": "single_harness",
            "harnesses": {
                "clarifier": "codex-exec",
                "explorer": "codex-exec",
                "author": "codex-exec",
                "ops_review": "codex-exec",
            },
        }
        for agent in single_harness["agents"].values():
            agent["harness_config"] = "codex-exec"
        _write_state(root, single_harness)
        code, payload = _run(root, "spec", "--require-ready", "--require-multi-harness")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any(item["path"] == "state.agents.harness_config" for item in payload["errors"]), payload

        _write_state(root, _spec_state())

        missing_pr = _spec_state()
        missing_pr.pop("pull_request")
        _write_state(root, missing_pr)
        code, payload = _run(root, "spec", "--require-ready", "--require-pr")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any(item["path"] == "state.pull_request.pr_url" for item in payload["errors"]), payload

        wrong_pr_branch = _spec_state()
        wrong_pr_branch["pull_request"]["head"] = "round-s1-other"
        _write_state(root, wrong_pr_branch)
        code, payload = _run(root, "spec", "--require-ready", "--require-pr")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any(item["path"] == "state.pull_request.head" for item in payload["errors"]), payload

        failed_child = _spec_state()
        failed_child["agents"]["round-s1-spec-clarifier"] = {
            "template": "spec-goal-clarifier",
            "status": "completed",
            "activity": "limits_exceeded",
        }
        _write_state(root, failed_child)
        code, payload = _run(root, "spec", "--require-ready")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any("state.agents.clarifier" in item["path"] for item in payload["errors"]), payload

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

        code, payload = _run(root, "implementation", "--require-ready", "--require-pr")
        assert code == 0, payload
        assert payload["ok"] is True, payload

        unchanged_branch = _implementation_state()
        unchanged_branch["base_branch"] = "round-s1-spec-integration"
        _write_state(root, unchanged_branch)
        code, payload = _run(root, "implementation", "--require-ready")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any(item["path"] == "branch" and "same commit" in item["message"] for item in payload["errors"]), payload

        blocked = _implementation_state()
        blocked["final_review"] = {"verdict": "reject"}
        _write_state(root, blocked)
        code, payload = _run(root, "implementation", "--require-ready")
        assert code == 1, payload
        assert payload["ok"] is False, payload
        assert any("final_review" in item["path"] for item in payload["errors"]), payload

        repaired_review = _implementation_state()
        repaired_review["agents"]["round-s1-final-review"] = {
            "template": "final-reviewer-codex",
            "status": "rejected",
            "verdict": "reject",
        }
        repaired_review["agents"]["round-s1-final-review-r2"] = {
            "template": "final-reviewer-codex",
            "status": "accepted",
            "verdict": "accept",
        }
        repaired_review["final_review"] = {
            "verdict": "reject",
            "status": "rejected",
            "replacement_verdict": "accept",
            "replacement_status": "accepted",
            "accepted_review_branch": "round-s1-final-review-r2",
        }
        _write_state(root, repaired_review)
        code, payload = _run(root, "implementation", "--require-ready")
        assert code == 0, payload
        assert payload["ok"] is True, payload

        origin = root.parent / f"{root.name}-origin.git"
        origin.mkdir()
        _git(origin, "init", "--bare")
        _git(root, "remote", "add", "origin", str(origin))
        _git(root, "push", "origin", "main", "round-s1-spec-integration")
        _git(root, "fetch", "origin", "round-s1-spec-integration")
        stale_remote_tracking = _git_output(root, "rev-parse", "origin/round-s1-spec-integration")

        other = root.parent / f"{root.name}-other"
        subprocess.run(["git", "clone", str(origin), str(other)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _git(other, "config", "user.email", "test@example.com")
        _git(other, "config", "user.name", "Test User")
        _git(other, "checkout", "round-s1-spec-integration")
        _write(other / "README.md", "# Test\n\nRemote update\n")
        _git(other, "add", "README.md")
        _git(other, "commit", "-m", "remote update")
        _git(other, "push", "origin", "round-s1-spec-integration")
        remote_head = _git_output(root, "ls-remote", "--heads", "origin", "round-s1-spec-integration").split()[0]
        assert stale_remote_tracking != remote_head

        _write_state(root, _implementation_state())
        code, payload = _run(root, "implementation", "--require-ready")
        assert code == 0, payload
        assert payload["ok"] is True, payload
        assert payload["branch"]["resolved_ref"] == "origin/round-s1-spec-integration", payload
        assert payload["branch"]["commit"] == remote_head, payload

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
