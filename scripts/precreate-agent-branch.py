#!/usr/bin/env python3
"""Pre-create and verify a remote agent branch from a base branch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(args: list[str], *, cwd: Path | None = None, timeout: int = 60) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "returncode": None, "output": str(exc), "missing": args[0]}
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        return {"ok": False, "returncode": None, "output": output, "timeout": timeout}
    return {"ok": result.returncode == 0, "returncode": result.returncode, "output": result.stdout}


def git(project_root: Path, *args: str, timeout: int = 60) -> dict[str, Any]:
    return run(["git", *args], cwd=project_root, timeout=timeout)


def authenticated_remote(remote: str) -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return remote
    if remote.startswith("https://github.com/"):
        return "https://x-access-token:" + token + "@github.com/" + remote.removeprefix("https://github.com/")
    if remote.startswith("git@github.com:"):
        return "https://x-access-token:" + token + "@github.com/" + remote.removeprefix("git@github.com:")
    if remote.startswith("ssh://git@github.com/"):
        return "https://x-access-token:" + token + "@github.com/" + remote.removeprefix("ssh://git@github.com/")
    return remote


def ls_remote_head(project_root: Path, remote: str, branch: str) -> str:
    result = git(project_root, "ls-remote", "--heads", remote, branch, timeout=60)
    if not result["ok"]:
        return ""
    line = str(result["output"]).strip().splitlines()
    if not line:
        return ""
    return line[0].split()[0]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def precreate(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    remote_result = git(project_root, "remote", "get-url", "origin", timeout=15)
    if not remote_result["ok"] or not str(remote_result["output"]).strip():
        payload = {
            "ok": False,
            "reason": "origin_remote_missing",
            "project_root": str(project_root),
            "branch": args.branch,
            "base_branch": args.base_branch,
            "completed_at": utc_now(),
        }
        if args.output:
            write_json(args.output.resolve(), payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2

    remote = authenticated_remote(str(remote_result["output"]).strip())
    base_sha = ls_remote_head(project_root, remote, args.base_branch)
    if not base_sha:
        payload = {
            "ok": False,
            "reason": "base_branch_missing",
            "project_root": str(project_root),
            "branch": args.branch,
            "base_branch": args.base_branch,
            "completed_at": utc_now(),
        }
        if args.output:
            write_json(args.output.resolve(), payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 3

    child_sha = ls_remote_head(project_root, remote, args.branch)
    created = False
    fetch_result: dict[str, Any] | None = None
    push_result: dict[str, Any] | None = None

    if not child_sha:
        fetch_result = git(
            project_root,
            "fetch",
            "--quiet",
            "--depth=1",
            remote,
            f"+refs/heads/{args.base_branch}:refs/remotes/origin/{args.base_branch}",
            timeout=120,
        )
        if not fetch_result["ok"]:
            payload = {
                "ok": False,
                "reason": "base_branch_fetch_failed",
                "project_root": str(project_root),
                "branch": args.branch,
                "base_branch": args.base_branch,
                "base_sha": base_sha,
                "fetch": fetch_result,
                "completed_at": utc_now(),
            }
            if args.output:
                write_json(args.output.resolve(), payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 4

        push_result = git(
            project_root,
            "push",
            remote,
            f"refs/remotes/origin/{args.base_branch}:refs/heads/{args.branch}",
            timeout=120,
        )
        if not push_result["ok"]:
            payload = {
                "ok": False,
                "reason": "branch_push_failed",
                "project_root": str(project_root),
                "branch": args.branch,
                "base_branch": args.base_branch,
                "base_sha": base_sha,
                "push": push_result,
                "completed_at": utc_now(),
            }
            if args.output:
                write_json(args.output.resolve(), payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 5
        created = True
        child_sha = ls_remote_head(project_root, remote, args.branch)

    ok = child_sha == base_sha
    payload = {
        "ok": ok,
        "reason": "" if ok else "child_branch_not_at_base",
        "project_root": str(project_root),
        "branch": args.branch,
        "base_branch": args.base_branch,
        "base_sha": base_sha,
        "child_sha": child_sha,
        "created": created,
        "fetch": fetch_result,
        "push": push_result,
        "completed_at": utc_now(),
    }
    if args.output:
        write_json(args.output.resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ok else 6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--branch", required=True)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    return precreate(args)


if __name__ == "__main__":
    raise SystemExit(main())
