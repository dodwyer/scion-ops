#!/usr/bin/env python3
"""Validate durable state for Scion OpenSpec steward sessions."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


READY_STATUSES = {"ready", "completed", "success"}
PASSING_STATUSES = {"passed", "success", "ok"}
ACCEPT_VERDICTS = {"accept", "accepted", "pass", "passed"}
COMPLETED_AGENT_STATUS_TOKENS = ("completed", "complete", "succeeded", "success", "passed", "ready")
FAILED_AGENT_STATUS_TOKENS = (
    "failed",
    "failure",
    "error",
    "errored",
    "limits_exceeded",
    "limit_exceeded",
    "blocked",
    "rejected",
)
SPEC_REQUIRED_AGENT_MARKERS = {
    "clarifier": ("spec-clarifier", "spec-goal-clarifier"),
    "explorer": ("spec-explorer", "spec-repo-explorer"),
    "author": ("spec-author",),
    "ops_review": ("spec-ops-review", "spec-ops-reviewer"),
}
IMPLEMENTATION_REQUIRED_AGENT_MARKERS = {
    "implementer": ("impl-codex", "impl-claude"),
    "final_review": ("final-review", "final-reviewer"),
}


@dataclass(frozen=True)
class Finding:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


def _load_openspec_validator():
    validator_path = Path(__file__).resolve().with_name("validate-openspec-change.py")
    spec = importlib.util.spec_from_file_location("openspec_change_validator", validator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validator from {validator_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.validate_openspec_change


def _read_json_text(text: str, source: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(value, dict):
        return None, f"{source} must contain a JSON object"
    return value, None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return _read_json_text(path.read_text(), str(path))
    except OSError as exc:
        return None, str(exc)


def _get_path(value: dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_status(value: Any) -> str:
    return _text(value).strip().lower()


def _git(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _git_bytes(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _fetch_remote_branch(project_root: Path, branch: str) -> None:
    if not branch or branch.startswith("-") or "/" in branch and branch.startswith("refs/"):
        return
    _git(
        project_root,
        ["fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}"],
    )


def _ensure_remote_tracking_ref(project_root: Path, ref: str) -> None:
    if ref.startswith("origin/"):
        _fetch_remote_branch(project_root, ref.removeprefix("origin/"))


def _resolve_commit(project_root: Path, ref: str) -> tuple[str | None, str | None]:
    if not ref:
        return None, None

    for candidate in (ref, f"origin/{ref}"):
        result = _git(project_root, ["rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"])
        sha = result.stdout.strip()
        if result.returncode == 0 and sha:
            return sha, candidate

    result = _git(project_root, ["ls-remote", "--heads", "origin", ref])
    if result.returncode == 0:
        first = result.stdout.strip().splitlines()
        if first:
            sha = first[0].split()[0]
            _fetch_remote_branch(project_root, ref)
            fetched = _git(project_root, ["rev-parse", "--verify", "--quiet", f"origin/{ref}^{{commit}}"])
            fetched_sha = fetched.stdout.strip()
            if fetched.returncode == 0 and fetched_sha:
                return fetched_sha, f"origin/{ref}"
            return sha, f"origin/{ref}"

    return None, None


def _state_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".scion-ops" / "sessions" / session_id / "state.json"


def _state_relpath(session_id: str) -> str:
    return f".scion-ops/sessions/{session_id}/state.json"


def _steward_branch(session_id: str, kind: str) -> str:
    suffix = "spec-steward" if kind == "spec" else "implementation-steward"
    return f"round-{session_id}-{suffix}"


def _load_state(project_root: Path, session_id: str, kind: str, state_branch: str) -> tuple[dict[str, Any], str, str | None]:
    state_file = _state_path(project_root, session_id)
    if state_file.exists():
        loaded, load_error = _read_json(state_file)
        return loaded or {}, str(state_file), load_error

    relpath = _state_relpath(session_id)
    branches = [state_branch] if state_branch else []
    default_branch = _steward_branch(session_id, kind)
    branches.extend([default_branch, f"origin/{default_branch}"])
    seen: set[str] = set()
    for branch in branches:
        if not branch or branch in seen:
            continue
        seen.add(branch)
        _ensure_remote_tracking_ref(project_root, branch)
        result = _git(project_root, ["show", f"{branch}:{relpath}"])
        if result.returncode != 0:
            continue
        loaded, load_error = _read_json_text(result.stdout, f"{branch}:{relpath}")
        return loaded or {}, f"{branch}:{relpath}", load_error

    return {}, str(state_file), "steward state file is missing"


def _state_branch(state: dict[str, Any], kind: str) -> str:
    branches = state.get("branches")
    if isinstance(branches, dict):
        integration = _text(branches.get("integration"))
        if integration:
            return integration
    if kind == "implementation":
        implementation_branch = _text(_get_path(state, "implementation.branch"))
        if implementation_branch:
            return implementation_branch
    return ""


def _agent_text(state: dict[str, Any]) -> str:
    agents = state.get("agents")
    if not isinstance(agents, dict):
        return ""
    return json.dumps(agents, sort_keys=True).lower() + "\n" + "\n".join(str(key).lower() for key in agents)


def _agent_entries(state: dict[str, Any]) -> list[tuple[str, Any]]:
    agents = state.get("agents")
    if not isinstance(agents, dict):
        return []
    return list(agents.items())


def _agent_matches(name: str, payload: Any, markers: tuple[str, ...]) -> bool:
    text = name.lower()
    if isinstance(payload, dict):
        text += "\n" + json.dumps(payload, sort_keys=True).lower()
    else:
        text += "\n" + _text(payload).lower()
    return any(marker in text for marker in markers)


def _agent_status_values(payload: Any) -> list[str]:
    if isinstance(payload, str):
        return [_normalize_status(payload)]
    if not isinstance(payload, dict):
        return []

    values: list[str] = []
    for key in (
        "status",
        "phase",
        "activity",
        "health",
        "containerStatus",
        "container_status",
        "task_status",
        "verdict",
    ):
        value = payload.get(key)
        if value is not None:
            values.append(_normalize_status(value))
    return values


def _has_status_token(statuses: list[str], tokens: tuple[str, ...]) -> bool:
    return any(token in status for status in statuses for token in tokens)


def _agent_role_completion(state: dict[str, Any], markers: tuple[str, ...]) -> tuple[bool, str]:
    matches = [(name, payload) for name, payload in _agent_entries(state) if _agent_matches(name, payload, markers)]
    if not matches:
        return False, "missing"

    saw_incomplete = False
    for _name, payload in matches:
        statuses = _agent_status_values(payload)
        if _has_status_token(statuses, FAILED_AGENT_STATUS_TOKENS):
            return False, "failed"
        if _has_status_token(statuses, COMPLETED_AGENT_STATUS_TOKENS):
            return True, ""
        saw_incomplete = True

    if saw_incomplete:
        return False, "incomplete"
    return False, "missing_status"


def _openspec_validation_from_worktree_or_branch(
    project_root: Path,
    change: str,
    branch: str,
) -> tuple[dict[str, Any], str]:
    validate_openspec_change = _load_openspec_validator()
    local_validation = validate_openspec_change(project_root, change)
    if local_validation.get("ok") or not branch:
        return local_validation, "worktree"

    branch_sha, branch_ref = _resolve_commit(project_root, branch)
    if not branch_sha or not branch_ref:
        return local_validation, "worktree"

    archive = _git_bytes(project_root, ["archive", "--format=tar", branch_ref, f"openspec/changes/{change}"])
    if archive.returncode != 0:
        return local_validation, "worktree"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
            tar.extractall(tmp_root)
        branch_validation = validate_openspec_change(tmp_root, change)
        branch_validation["source_ref"] = branch_ref
        if branch_validation.get("ok"):
            return branch_validation, branch_ref

    return local_validation, "worktree"


def validate(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).expanduser().resolve()
    errors: list[Finding] = []
    warnings: list[Finding] = []
    state_file = _state_path(project_root, args.session_id)
    state_source = str(state_file)
    state: dict[str, Any] = {}

    if not project_root.exists():
        errors.append(Finding(str(project_root), "project root does not exist"))
    elif not project_root.is_dir():
        errors.append(Finding(str(project_root), "project root is not a directory"))

    if project_root.exists() and project_root.is_dir():
        loaded, state_source, load_error = _load_state(project_root, args.session_id, args.kind, args.state_branch)
        if load_error:
            errors.append(Finding(state_source, load_error))
        elif loaded is not None:
            state = loaded

    expected_change = args.change or _text(state.get("change"))
    expected_branch = args.branch or _state_branch(state, args.kind)
    base_branch = args.base_branch or _text(state.get("base_branch"))

    if state:
        required_fields = {
            "version": "state must include schema version",
            "session_id": "state must include session_id",
            "kind": "state must include kind",
            "change": "state must include change",
            "base_branch": "state must include base_branch",
            "status": "state must include status",
            "phase": "state must include phase",
        }
        for field, message in required_fields.items():
            if field not in state:
                errors.append(Finding(f"state.{field}", message))

        if _text(state.get("session_id")) != args.session_id:
            errors.append(Finding("state.session_id", "state session_id does not match requested session"))
        if _text(state.get("kind")) != args.kind:
            errors.append(Finding("state.kind", "state kind does not match requested kind"))
        if expected_change and _text(state.get("change")) != expected_change:
            errors.append(Finding("state.change", "state change does not match requested change"))

        if not isinstance(state.get("branches"), dict):
            warnings.append(Finding("state.branches", "state should include a branches object"))
        if not isinstance(state.get("agents"), dict):
            warnings.append(Finding("state.agents", "state should include an agents object"))
        if not isinstance(state.get("blockers"), list):
            warnings.append(Finding("state.blockers", "state should include a blockers list"))
        if not isinstance(state.get("next_actions"), list):
            warnings.append(Finding("state.next_actions", "state should include a next_actions list"))

        state_integration_branch = _text(_get_path(state, "branches.integration"))
        if expected_branch and state_integration_branch and state_integration_branch != expected_branch:
            errors.append(Finding("state.branches.integration", "state integration branch does not match requested branch"))

    openspec_validation: dict[str, Any] | None = None
    openspec_validation_source = ""
    if expected_change and project_root.exists() and project_root.is_dir():
        openspec_validation, openspec_validation_source = _openspec_validation_from_worktree_or_branch(
            project_root,
            expected_change,
            expected_branch,
        )
        if not openspec_validation.get("ok"):
            for item in openspec_validation.get("errors", []):
                path = _text(item.get("path") if isinstance(item, dict) else "openspec")
                message = _text(item.get("message") if isinstance(item, dict) else item)
                errors.append(Finding(path, message))
    elif args.require_ready:
        errors.append(Finding("change", "change is required for ready validation"))

    branch_info: dict[str, str | None] = {
        "branch": expected_branch or None,
        "commit": None,
        "resolved_ref": None,
        "base_branch": base_branch or None,
        "base_commit": None,
        "base_resolved_ref": None,
    }
    if expected_branch and project_root.exists() and project_root.is_dir():
        branch_sha, branch_ref = _resolve_commit(project_root, expected_branch)
        branch_info["commit"] = branch_sha
        branch_info["resolved_ref"] = branch_ref
        if branch_sha is None:
            errors.append(Finding("branch", f"branch does not exist locally or on origin: {expected_branch}"))

        if base_branch:
            base_sha, base_ref = _resolve_commit(project_root, base_branch)
            branch_info["base_commit"] = base_sha
            branch_info["base_resolved_ref"] = base_ref
            if base_sha is None:
                warnings.append(Finding("base_branch", f"base branch could not be resolved: {base_branch}"))
            elif branch_sha == base_sha:
                warnings.append(Finding("branch", "branch resolves to the same commit as base"))
    elif args.require_ready:
        errors.append(Finding("branch", "ready steward sessions must name a final branch"))

    if state and args.require_ready:
        status = _normalize_status(state.get("status"))
        if status not in READY_STATUSES:
            errors.append(Finding("state.status", "ready validation requires status ready, completed, or success"))

        validation_status = _normalize_status(_get_path(state, "validation.status"))
        if args.kind == "spec" and validation_status not in PASSING_STATUSES:
            errors.append(Finding("state.validation.status", "spec sessions must record passing validation"))

        if args.kind == "spec":
            for role, markers in SPEC_REQUIRED_AGENT_MARKERS.items():
                completed, reason = _agent_role_completion(state, markers)
                if not completed:
                    errors.append(
                        Finding(
                            f"state.agents.{role}",
                            f"ready spec sessions must record this specialist agent with a successful completion status ({reason})",
                        )
                    )
            review_verdict = _normalize_status(_get_path(state, "review.verdict"))
            if review_verdict not in ACCEPT_VERDICTS:
                errors.append(Finding("state.review.verdict", "spec sessions require an accepting ops-review verdict"))

        if args.kind == "implementation":
            for role, markers in IMPLEMENTATION_REQUIRED_AGENT_MARKERS.items():
                completed, reason = _agent_role_completion(state, markers)
                if not completed:
                    errors.append(
                        Finding(
                            f"state.agents.{role}",
                            f"ready implementation sessions must record this agent with a successful completion status ({reason})",
                        )
                    )
            final_verdict = _normalize_status(_get_path(state, "final_review.verdict"))
            if final_verdict not in ACCEPT_VERDICTS:
                errors.append(Finding("state.final_review.verdict", "implementation sessions require an accepting final review"))

            verification_status = _normalize_status(_get_path(state, "verification.status"))
            if verification_status not in PASSING_STATUSES:
                errors.append(Finding("state.verification.status", "implementation sessions must record passing verification"))

    payload: dict[str, Any] = {
        "ok": not errors,
        "project_root": str(project_root),
        "session_id": args.session_id,
        "kind": args.kind,
        "change": expected_change,
        "state_path": str(state_file),
        "state_source": state_source,
        "state": state,
        "openspec_validation": openspec_validation,
        "openspec_validation_source": openspec_validation_source,
        "branch": branch_info,
        "errors": [finding.as_dict() for finding in errors],
        "warnings": [finding.as_dict() for finding in warnings],
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--kind", required=True, choices=("spec", "implementation"))
    parser.add_argument("--change", default="")
    parser.add_argument("--base-branch", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--state-branch", default="")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = validate(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "ok" if payload["ok"] else "failed"
        print(f"steward session validation {status}: {payload['session_id']}")
        for item in payload["errors"]:
            print(f"error: {item['path']}: {item['message']}")
        for item in payload["warnings"]:
            print(f"warning: {item['path']}: {item['message']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
