#!/usr/bin/env python3
"""Create normalized durable state for Scion steward sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def session_root(project_root: Path, session_id: str) -> Path:
    return project_root / ".scion-ops" / "sessions" / session_id


def state_path(project_root: Path, session_id: str) -> Path:
    return session_root(project_root, session_id) / "state.json"


def branch_names(session_id: str) -> dict[str, str]:
    return {
        "steward": f"round-{session_id}-spec-steward",
        "clarifier": f"round-{session_id}-spec-clarifier",
        "explorer": f"round-{session_id}-spec-explorer",
        "author": f"round-{session_id}-spec-author",
        "review": f"round-{session_id}-spec-ops-review",
        "integration": f"round-{session_id}-spec-integration",
    }


def implementation_branch_names(session_id: str) -> dict[str, str]:
    return {
        "steward": f"round-{session_id}-implementation-steward",
        "implementer": f"round-{session_id}-impl-codex",
        "secondary_implementer": f"round-{session_id}-impl-claude",
        "final_review": f"round-{session_id}-final-review",
        "integration": f"round-{session_id}-integration",
    }


def spec_agent_records(session_id: str) -> dict[str, dict[str, str]]:
    branches = branch_names(session_id)
    return {
        "clarifier": {
            "name": branches["clarifier"],
            "branch": branches["clarifier"],
            "template": "spec-goal-clarifier",
            "status": "completed",
        },
        "explorer": {
            "name": branches["explorer"],
            "branch": branches["explorer"],
            "template": "spec-repo-explorer",
            "status": "completed",
        },
        "author": {
            "name": branches["author"],
            "branch": branches["author"],
            "template": "spec-author",
            "status": "completed",
        },
        "ops_review": {
            "name": branches["review"],
            "branch": branches["review"],
            "template": "spec-ops-reviewer",
            "status": "completed",
        },
    }


def implementation_base_state(args: argparse.Namespace, status: str, phase: str) -> dict[str, Any]:
    path = state_path(Path(args.project_root).resolve(), args.session_id)
    existing = load_existing(path)
    branches = implementation_branch_names(args.session_id)
    branches.update(existing.get("branches") if isinstance(existing.get("branches"), dict) else {})
    if getattr(args, "integration_branch", ""):
        branches["integration"] = args.integration_branch

    implementation = existing.get("implementation") if isinstance(existing.get("implementation"), dict) else {}
    implementation.setdefault("branch", "")
    implementation.setdefault("base_branch", args.base_branch)
    implementation.setdefault("integration_branch", branches["integration"])

    verification = existing.get("verification") if isinstance(existing.get("verification"), dict) else {}
    verification.setdefault("status", "pending")
    final_review = existing.get("final_review") if isinstance(existing.get("final_review"), dict) else {}
    blockers = existing.get("blockers") if isinstance(existing.get("blockers"), list) else []
    next_actions = existing.get("next_actions") if isinstance(existing.get("next_actions"), list) else []

    return {
        "version": 1,
        "session_id": args.session_id,
        "round_id": args.session_id,
        "kind": "implementation",
        "change": args.change,
        "base_branch": args.base_branch,
        "status": status,
        "phase": phase,
        "branches": branches,
        "agents": existing.get("agents") if isinstance(existing.get("agents"), dict) else {},
        "implementation": implementation,
        "reviews": existing.get("reviews") if isinstance(existing.get("reviews"), list) else [],
        "final_review": final_review,
        "verification": verification,
        "blockers": blockers,
        "next_actions": next_actions,
    }


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=False) + "\n")
    print(path)


def base_state(args: argparse.Namespace, status: str, phase: str) -> dict[str, Any]:
    path = state_path(Path(args.project_root).resolve(), args.session_id)
    existing = load_existing(path)
    branches = branch_names(args.session_id)
    branches.update(existing.get("branches") if isinstance(existing.get("branches"), dict) else {})
    if getattr(args, "integration_branch", ""):
        branches["integration"] = args.integration_branch

    blockers = existing.get("blockers") if isinstance(existing.get("blockers"), list) else []
    next_actions = existing.get("next_actions") if isinstance(existing.get("next_actions"), list) else []

    return {
        "version": 1,
        "session_id": args.session_id,
        "round_id": args.session_id,
        "kind": "spec",
        "change": args.change,
        "base_branch": args.base_branch,
        "status": status,
        "phase": phase,
        "branches": branches,
        "agents": existing.get("agents") if isinstance(existing.get("agents"), dict) else {},
        "review": existing.get("review") if isinstance(existing.get("review"), dict) else {},
        "validation": existing.get("validation") if isinstance(existing.get("validation"), dict) else {},
        "blockers": blockers,
        "next_actions": next_actions,
    }


def spec_init(args: argparse.Namespace) -> None:
    root = Path(args.project_root).resolve()
    state = base_state(args, "running", args.phase)
    state["validation"] = {"status": "pending"}
    if not state["next_actions"]:
        state["next_actions"] = [
            "Start spec-goal-clarifier and spec-repo-explorer agents",
            "Create OpenSpec artifacts on the author branch",
            "Validate and review the integration branch",
        ]
    write_state(state_path(root, args.session_id), state)


def spec_ready(args: argparse.Namespace) -> None:
    root = Path(args.project_root).resolve()
    state = base_state(args, "ready", "complete")
    state["agents"] = spec_agent_records(args.session_id)
    state["review"] = {
        "verdict": args.review_verdict,
        "agent": branch_names(args.session_id)["review"],
        "summary": args.review_summary,
    }
    state["validation"] = {
        "status": "passed",
        "command": args.validation_command,
        "integration_branch": args.integration_branch,
        "review_agent": branch_names(args.session_id)["review"],
    }
    state["blockers"] = []
    state["next_actions"] = [
        f"Use {args.integration_branch} for OpenSpec review or implementation planning",
    ]
    write_state(state_path(root, args.session_id), state)


def spec_blocked(args: argparse.Namespace) -> None:
    root = Path(args.project_root).resolve()
    state = base_state(args, "blocked", args.phase)
    state["blockers"] = [args.blocker]
    state["next_actions"] = [args.next_action]
    write_state(state_path(root, args.session_id), state)


def implementation_init(args: argparse.Namespace) -> None:
    root = Path(args.project_root).resolve()
    state = implementation_base_state(args, "running", args.phase)
    if not state["next_actions"]:
        state["next_actions"] = [
            "Write implementation brief and bounded task groups",
            "Start bounded implementer agents",
            "Integrate the accepted implementation branch",
            "Run verification and final review",
        ]
    write_state(state_path(root, args.session_id), state)


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--change", required=True)
    parser.add_argument("--base-branch", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("spec-init")
    add_common(init_parser)
    init_parser.add_argument("--phase", default="clarifying")
    init_parser.set_defaults(func=spec_init)

    ready_parser = subparsers.add_parser("spec-ready")
    add_common(ready_parser)
    ready_parser.add_argument("--integration-branch", required=True)
    ready_parser.add_argument("--validation-command", required=True)
    ready_parser.add_argument("--review-verdict", default="accept")
    ready_parser.add_argument("--review-summary", default="")
    ready_parser.set_defaults(func=spec_ready)

    blocked_parser = subparsers.add_parser("spec-blocked")
    add_common(blocked_parser)
    blocked_parser.add_argument("--phase", default="blocked")
    blocked_parser.add_argument("--blocker", required=True)
    blocked_parser.add_argument("--next-action", required=True)
    blocked_parser.set_defaults(func=spec_blocked)

    implementation_init_parser = subparsers.add_parser("implementation-init")
    add_common(implementation_init_parser)
    implementation_init_parser.add_argument("--integration-branch", required=True)
    implementation_init_parser.add_argument("--phase", default="starting")
    implementation_init_parser.set_defaults(func=implementation_init)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
