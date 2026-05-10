#!/usr/bin/env python3
"""Create or return the GitHub PR for a ready Scion steward session."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-steward-session.py"
PR_URL_RE = re.compile(r"https://github\.com/\S+/pull/\d+")


def _run(args: list[str], *, cwd: Path) -> dict[str, Any]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": args,
        "output": result.stdout,
    }


def _json_payload(result: dict[str, Any]) -> Any:
    try:
        return json.loads(str(result.get("output") or ""))
    except json.JSONDecodeError:
        return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _branch_name(ref: str) -> str:
    ref = ref.strip()
    if ref.startswith("refs/remotes/origin/"):
        return ref.removeprefix("refs/remotes/origin/")
    if ref.startswith("origin/"):
        return ref.removeprefix("origin/")
    if ref.startswith("refs/heads/"):
        return ref.removeprefix("refs/heads/")
    if ref.startswith("refs/") or "^" in ref or ":" in ref or ref.startswith("-"):
        return ""
    return ref


def _failure(
    *,
    args: argparse.Namespace,
    message: str,
    validation_result: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    gh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "source": "steward_pr_finalizer",
        "project_root": str(Path(args.project_root).expanduser().resolve()),
        "session_id": args.session_id,
        "kind": args.kind,
        "change": args.change,
        "error": message,
        "validation_result": validation_result or {},
        "validation": validation or {},
        "gh": gh or {},
    }


def _validator_args(args: argparse.Namespace, project_root: Path) -> list[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "--project-root",
        str(project_root),
        "--session-id",
        args.session_id,
        "--kind",
        args.kind,
        "--json",
        "--require-ready",
    ]
    if args.change:
        command.extend(["--change", args.change])
    if args.branch:
        command.extend(["--branch", args.branch])
    if args.base_branch:
        command.extend(["--base-branch", args.base_branch])
    if args.state_branch:
        command.extend(["--state-branch", args.state_branch])
    return command


def _default_title(validation: dict[str, Any], args: argparse.Namespace) -> str:
    change = _text(validation.get("change")) or args.change or args.session_id
    if args.kind == "spec":
        return f"OpenSpec: {change}"
    return f"Implement OpenSpec: {change}"


def _list_text(values: list[Any]) -> str:
    lines: list[str] = []
    for value in values:
        text = _text(value)
        if text:
            lines.append(f"- `{text}`")
    return "\n".join(lines) if lines else "- Not recorded"


def _default_body(
    *,
    args: argparse.Namespace,
    validation: dict[str, Any],
    head: str,
    base: str,
    head_commit: str,
    base_commit: str,
) -> str:
    state = validation.get("state") if isinstance(validation.get("state"), dict) else {}
    change = _text(validation.get("change")) or args.change
    lines = [
        f"Created by scion-ops after successful {args.kind} steward validation.",
        "",
        f"- Session: `{args.session_id}`",
        f"- Change: `{change}`",
        f"- Head: `{head}`{f' (`{head_commit[:12]}`)' if head_commit else ''}",
        f"- Base: `{base}`{f' (`{base_commit[:12]}`)' if base_commit else ''}",
        "- Steward validation: passed",
    ]

    if args.kind == "implementation":
        final_review = state.get("final_review") if isinstance(state.get("final_review"), dict) else {}
        verification = state.get("verification") if isinstance(state.get("verification"), dict) else {}
        lines.extend(
            [
                f"- Final review: `{_text(final_review.get('verdict')) or 'accept'}`",
                f"- Verification: `{_text(verification.get('status')) or 'passed'}`",
            ]
        )
        commands = verification.get("commands")
        if isinstance(commands, list) and commands:
            lines.extend(["", "Verification commands:", _list_text(commands)])
    else:
        review = state.get("review") if isinstance(state.get("review"), dict) else {}
        lines.append(f"- OpenSpec review: `{_text(review.get('verdict')) or 'accept'}`")

    return "\n".join(lines)


def _existing_pr_payload(item: dict[str, Any], *, head: str, base: str) -> dict[str, Any]:
    return {
        "number": item.get("number"),
        "url": item.get("url"),
        "state": item.get("state"),
        "title": item.get("title"),
        "head": item.get("headRefName") or head,
        "base": item.get("baseRefName") or base,
    }


def _compact_pr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    pr = payload.get("pr") if isinstance(payload.get("pr"), dict) else {}
    return {
        "source": payload.get("source"),
        "session_id": payload.get("session_id"),
        "kind": payload.get("kind"),
        "change": payload.get("change"),
        "head": payload.get("head"),
        "base": payload.get("base"),
        "head_commit": payload.get("head_commit"),
        "base_commit": payload.get("base_commit"),
        "created": payload.get("created"),
        "draft": payload.get("draft"),
        "pr": pr,
        "pr_url": payload.get("pr_url") or pr.get("url"),
    }


def _record_state(args: argparse.Namespace, project_root: Path, payload: dict[str, Any]) -> dict[str, str]:
    session_dir = project_root / ".scion-ops" / "sessions" / args.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    state_path = session_dir / "state.json"
    pr_path = session_dir / "pr.json"
    compact = _compact_pr_payload(payload)
    pr_path.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n")

    state: dict[str, Any] = {}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text())
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            state = loaded
    state["pull_request"] = compact
    pr_url = _text(compact.get("pr_url"))
    if pr_url:
        state["next_actions"] = [f"Review pull request {pr_url}"]
    else:
        state["next_actions"] = [f"Review pull request for {compact.get('head')} into {compact.get('base')}"]
    state_path.write_text(json.dumps(state, indent=2, sort_keys=False) + "\n")
    return {"state_path": str(state_path), "pr_path": str(pr_path)}


def _with_state_recording(
    args: argparse.Namespace,
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if args.record_state and payload.get("ok"):
        payload["state_recording"] = _record_state(args, project_root, payload)
    return payload


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).expanduser().resolve()
    validation_result = _run(_validator_args(args, project_root), cwd=ROOT)
    validation = _json_payload(validation_result)
    if not isinstance(validation, dict):
        return _failure(
            args=args,
            message="steward validator did not return JSON",
            validation_result=validation_result,
        )
    if not validation_result["ok"] or not validation.get("ok"):
        return _failure(
            args=args,
            message="steward session is not ready for a PR",
            validation_result=validation_result,
            validation=validation,
        )

    branch_info = validation.get("branch") if isinstance(validation.get("branch"), dict) else {}
    head = _branch_name(_text(branch_info.get("branch")))
    base = _branch_name(_text(branch_info.get("base_branch")))
    if not head:
        return _failure(args=args, message="validated state does not name a PR head branch", validation=validation)
    if not base:
        return _failure(args=args, message="validated state does not name a PR base branch", validation=validation)

    gh_path = shutil.which("gh")
    if not gh_path:
        return _failure(args=args, message="GitHub CLI `gh` is not available on PATH", validation=validation)

    list_args = [
        gh_path,
        "pr",
        "list",
        "--head",
        head,
        "--base",
        base,
        "--state",
        "all",
        "--json",
        "number,url,state,title,baseRefName,headRefName",
        "--limit",
        "1",
    ]
    list_result = _run(list_args, cwd=project_root)
    existing = _json_payload(list_result)
    if not list_result["ok"] or not isinstance(existing, list):
        return _failure(
            args=args,
            message="failed to query existing pull requests",
            validation_result=validation_result,
            validation=validation,
            gh={"list": list_result},
        )
    if existing:
        pr = _existing_pr_payload(existing[0], head=head, base=base)
        return _with_state_recording(args, project_root, {
            "ok": True,
            "source": "steward_pr_finalizer",
            "project_root": str(project_root),
            "session_id": args.session_id,
            "kind": args.kind,
            "change": _text(validation.get("change")) or args.change,
            "head": head,
            "base": base,
            "head_commit": _text(branch_info.get("commit")),
            "base_commit": _text(branch_info.get("base_commit")),
            "created": False,
            "draft": False,
            "pr": pr,
            "pr_url": _text(pr.get("url")),
            "validation": validation,
            "gh": {"list": list_result},
        })

    draft = bool(args.draft or _env_bool("SCION_OPS_PR_DRAFT"))
    title = args.title.strip() if args.title else _default_title(validation, args)
    body = args.body.strip() if args.body else _default_body(
        args=args,
        validation=validation,
        head=head,
        base=base,
        head_commit=_text(branch_info.get("commit")),
        base_commit=_text(branch_info.get("base_commit")),
    )
    create_args = [
        gh_path,
        "pr",
        "create",
        "--base",
        base,
        "--head",
        head,
        "--title",
        title,
        "--body",
        body,
    ]
    if draft:
        create_args.append("--draft")
    create_result = _run(create_args, cwd=project_root)
    if not create_result["ok"]:
        return _failure(
            args=args,
            message="failed to create pull request",
            validation_result=validation_result,
            validation=validation,
            gh={"list": list_result, "create": create_result},
        )

    url_match = PR_URL_RE.search(str(create_result.get("output") or ""))
    pr_url = url_match.group(0) if url_match else ""
    if not pr_url:
        return _failure(
            args=args,
            message="failed to parse pull request URL",
            validation_result=validation_result,
            validation=validation,
            gh={"list": list_result, "create": create_result},
        )
    return _with_state_recording(args, project_root, {
        "ok": True,
        "source": "steward_pr_finalizer",
        "project_root": str(project_root),
        "session_id": args.session_id,
        "kind": args.kind,
        "change": _text(validation.get("change")) or args.change,
        "head": head,
        "base": base,
        "head_commit": _text(branch_info.get("commit")),
        "base_commit": _text(branch_info.get("base_commit")),
        "created": True,
        "draft": draft,
        "pr": {"url": pr_url, "head": head, "base": base, "title": title},
        "pr_url": pr_url,
        "validation": validation,
        "gh": {"list": list_result, "create": create_result},
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--kind", required=True, choices=("spec", "implementation"))
    parser.add_argument("--change", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--base-branch", default="")
    parser.add_argument("--state-branch", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--record-state", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = finalize(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif payload.get("ok"):
        action = "created" if payload.get("created") else "exists"
        print(f"pull request {action}: {payload.get('pr_url')}")
    else:
        print(f"pull request failed: {payload.get('error')}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
