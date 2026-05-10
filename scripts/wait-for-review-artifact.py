#!/usr/bin/env python3
"""Wait for a review agent to publish a durable verdict artifact."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
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


def tail_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def fetch_branch(project_root: Path, branch: str) -> dict[str, Any]:
    return run_command(
        ["git", "fetch", "--quiet", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"],
        cwd=project_root,
        timeout=60,
    )


def branch_head(project_root: Path, branch: str) -> str:
    result = run_command(
        ["git", "rev-parse", "--verify", f"origin/{branch}^{{commit}}"],
        cwd=project_root,
        timeout=15,
    )
    if result["ok"]:
        return str(result["output"]).strip()
    return ""


def read_artifact(project_root: Path, branch: str, artifact: str) -> tuple[bool, str, dict[str, Any] | None]:
    result = run_command(["git", "show", f"origin/{branch}:{artifact}"], cwd=project_root, timeout=15)
    if not result["ok"]:
        return False, str(result["output"]), None
    text = str(result["output"])
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    return True, text, parsed


def is_ancestor(project_root: Path, ancestor: str, descendant: str) -> bool:
    if not ancestor or not descendant:
        return False
    result = run_command(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=project_root, timeout=15)
    return bool(result["ok"])


def agent_status(profile: str, agent: str) -> dict[str, Any]:
    if not profile or not shutil.which("scion"):
        return {}
    result = run_command(["scion", "--profile", profile, "list", "--format", "json"], timeout=30)
    if not result["ok"]:
        return {"source": "scion list", "ok": False, "output": tail_text(str(result["output"]), 4000)}
    try:
        payload = json.loads(str(result["output"]) or "[]")
    except json.JSONDecodeError:
        return {"source": "scion list", "ok": False, "output": tail_text(str(result["output"]), 4000)}
    if not isinstance(payload, list):
        return {"source": "scion list", "ok": False, "output": tail_text(str(result["output"]), 4000)}
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("slug") == agent or item.get("name") == agent or item.get("id") == agent:
            return {"source": "scion list", "ok": True, "agent": item}
    return {"source": "scion list", "ok": True, "agent": None}


def scion_look(profile: str, agent: str) -> str:
    if not profile or not shutil.which("scion"):
        return ""
    result = run_command(["scion", "--profile", profile, "look", agent], timeout=30)
    return tail_text(str(result["output"]), 12000)


def kubectl_diagnostics(agent: str, context: str, namespace: str) -> dict[str, str]:
    if not shutil.which("kubectl"):
        return {}
    diagnostics: dict[str, str] = {}
    logs = run_command(
        [
            "kubectl",
            "--context",
            context,
            "-n",
            namespace,
            "logs",
            agent,
            "--all-containers=true",
            "--tail=200",
        ],
        timeout=30,
    )
    diagnostics["logs"] = tail_text(str(logs["output"]), 12000)
    pod = run_command(
        ["kubectl", "--context", context, "-n", namespace, "get", "pod", agent, "-o", "json"],
        timeout=30,
    )
    diagnostics["pod"] = tail_text(str(pod["output"]), 12000)
    return diagnostics


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def wait_for_artifact(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    output_path = args.output.resolve() if args.output else None
    deadline = time.monotonic() + max(args.timeout_seconds, 0)
    attempts: list[dict[str, Any]] = []
    last_fetch: dict[str, Any] = {}
    last_head = ""
    last_error = ""
    required_fields = list(args.require_json_fields or [])

    while True:
        checked_at = utc_now()
        last_fetch = fetch_branch(project_root, args.branch)
        last_head = branch_head(project_root, args.branch)
        found, artifact_text, parsed = read_artifact(project_root, args.branch, args.artifact)
        artifact_valid = found
        validation_errors: list[str] = []
        if found and required_fields:
            if not isinstance(parsed, dict):
                artifact_valid = False
                validation_errors.append("artifact is not a JSON object")
            else:
                missing = [field for field in required_fields if field not in parsed]
                if missing:
                    artifact_valid = False
                    validation_errors.append("artifact is missing required fields: " + ", ".join(missing))
        if found and args.require_head_sha_match:
            if not isinstance(parsed, dict):
                artifact_valid = False
                validation_errors.append("artifact is not a JSON object")
            elif str(parsed.get("head_sha") or "") != last_head:
                artifact_valid = False
                validation_errors.append(
                    f"artifact head_sha {parsed.get('head_sha') or '<empty>'} does not match branch head {last_head}"
                )
        if found and args.require_head_sha_ancestor:
            if not isinstance(parsed, dict):
                artifact_valid = False
                validation_errors.append("artifact is not a JSON object")
            elif not is_ancestor(project_root, str(parsed.get("head_sha") or ""), last_head):
                artifact_valid = False
                validation_errors.append(
                    f"artifact head_sha {parsed.get('head_sha') or '<empty>'} is not an ancestor of branch head {last_head}"
                )
        attempts.append(
            {
                "checked_at": checked_at,
                "branch_head": last_head,
                "artifact_found": found,
                "artifact_valid": artifact_valid,
                "validation_errors": validation_errors,
                "fetch_ok": bool(last_fetch.get("ok")),
            }
        )
        if found and artifact_valid:
            payload = {
                "ok": True,
                "source": "review_artifact_wait",
                "branch": args.branch,
                "branch_head": last_head,
                "artifact": args.artifact,
                "artifact_json": parsed,
                "artifact_text": artifact_text if parsed is None else "",
                "attempts": attempts,
                "completed_at": utc_now(),
            }
            if output_path:
                write_json(output_path, payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        last_error = "; ".join(validation_errors) if validation_errors else artifact_text
        if time.monotonic() >= deadline:
            break
        time.sleep(min(args.poll_interval_seconds, max(deadline - time.monotonic(), 0)))

    diagnostics = {
        "ok": False,
        "source": "review_artifact_wait",
        "reason": "timeout_waiting_for_review_artifact",
        "branch": args.branch,
        "branch_head": last_head,
        "artifact": args.artifact,
        "agent": args.agent,
        "timeout_seconds": args.timeout_seconds,
        "poll_interval_seconds": args.poll_interval_seconds,
        "attempts": attempts,
        "last_fetch": last_fetch,
        "last_artifact_error": tail_text(last_error, 4000),
        "agent_status": agent_status(args.scion_profile, args.agent),
        "scion_look_tail": scion_look(args.scion_profile, args.agent),
        "kubectl": kubectl_diagnostics(args.agent, args.kube_context, args.kube_namespace),
        "completed_at": utc_now(),
    }
    if output_path:
        write_json(output_path, diagnostics)
    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--scion-profile", default="kind")
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--poll-interval-seconds", type=int, default=15)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--kube-context", default="kind-scion-ops")
    parser.add_argument("--kube-namespace", default="scion-agents")
    parser.add_argument("--require-json-fields", nargs="*", default=[])
    parser.add_argument("--require-head-sha-match", action="store_true")
    parser.add_argument("--require-head-sha-ancestor", action="store_true")
    args = parser.parse_args()
    if args.poll_interval_seconds <= 0:
        parser.error("--poll-interval-seconds must be positive")
    return wait_for_artifact(args)


if __name__ == "__main__":
    raise SystemExit(main())
