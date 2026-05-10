#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "PyYAML>=6,<7",
# ]
# ///
"""Read-only browser hub for scion-ops runtime state."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if not str(os.environ.get("SCION_OPS_MCP_PORT", "8765")).isdigit():
    os.environ.pop("SCION_OPS_MCP_PORT", None)

import mcp_servers.scion_ops as scion_ops


STALE_AFTER_SECONDS = 90
ROUND_RE = re.compile(r"(?:round-)?(?P<id>\d{8}t\d{6}z-[a-z0-9]+)", re.IGNORECASE)
CONTROL_PLANE_NAMES = {"scion-hub", "scion-broker", "scion-ops-mcp", "scion-ops-web-app"}
CONTROL_PLANE_DEPLOYMENTS = CONTROL_PLANE_NAMES
CONTROL_PLANE_SERVICES = CONTROL_PLANE_NAMES - {"scion-broker"}
BROWSER_JSON_CONTRACT = {
    "snapshot": {
        "readiness": "ready|degraded|unavailable",
        "sources": ["hub", "broker", "mcp", "web_app", "kubernetes", "messages", "notifications"],
        "rounds": "array of read-only round summaries",
        "inbox": "messages and notifications grouped by round_id",
    },
    "round": {
        "round_id": "MCP/Hub round id without the round- prefix",
        "status": "derived from structured Hub/MCP state before fallback text",
        "visible_status": "operator-facing status, preserving final-review blocked/change states",
        "branches": "structured artifact/branch fields, with fallback text only when needed",
        "mcp": {
            "expected_branch": "steward session expected branch",
            "pr_ready_branch": "steward session PR-ready branch",
            "remote_branch_sha": "remote branch evidence from MCP/artifacts",
            "branch_changed": "boolean or null when unknown",
            "validation_status": "passed|failed|pending|skipped or empty",
            "protocol": "steward milestone object",
            "blockers": "structured blocker strings",
            "warnings": "structured warning strings",
            "terminal": "structured terminal status when present",
        },
        "final_review": "structured final-review verdict, normalized verdict, display label, source, and blockers",
        "agents": "normalized agent records with role, template, harness_config, phase, activity, and status",
    },
    "live_updates": {
        "endpoint": "/api/live?cursor=<last_cursor>&round_id=<optional-round>",
        "transports": ["application/json long poll", "text/event-stream"],
        "cursor": "opaque stable digest of the latest emitted snapshot/detail state",
        "heartbeat_seconds": 15,
        "event_types": [
            "snapshot.initial",
            "overview.updated",
            "rounds.updated",
            "round.detail.updated",
            "timeline.appended",
            "inbox.updated",
            "runtime.updated",
            "source.error",
            "heartbeat",
        ],
        "idempotency": "every event has a stable id; timeline and inbox records preserve source ids when present and deterministic fallback ids otherwise",
        "source_errors": "source.error carries source, status, error_kind, error, and last known data remains valid for unrelated sources",
        "read_only": "subscribe, reconnect, cursor resume, and fallback polling only read existing Hub, MCP, Kubernetes, git, and OpenSpec status",
        "snapshot": "automatic read-only GET /api/snapshot update with preserved selected view and scroll context",
        "round_events": "cursor-based read-only GET /api/rounds/{round_id}/events polling for selected round timelines",
        "states": ["connected", "reconnecting", "stale", "fallback", "failed"],
    },
}
TEMPLATE_HARNESSES = {
    "spec-steward": "codex-exec",
    "spec-goal-clarifier": "codex-exec",
    "spec-goal-clarifier-claude": "claude",
    "spec-repo-explorer": "codex-exec",
    "spec-author": "codex-exec",
    "spec-ops-reviewer": "codex-exec",
    "spec-ops-reviewer-claude": "claude",
    "implementation-steward": "codex-exec",
    "impl-codex": "codex-exec",
    "impl-claude": "claude",
    "reviewer-codex": "codex-exec",
    "reviewer-claude": "claude",
    "final-reviewer-codex": "codex-exec",
    "final-reviewer-gemini": "gemini",
}
TEMPLATE_ROLES = {
    "spec-steward": "spec steward",
    "spec-goal-clarifier": "clarifier",
    "spec-goal-clarifier-claude": "clarifier",
    "spec-repo-explorer": "explorer",
    "spec-author": "author",
    "spec-ops-reviewer": "ops review",
    "spec-ops-reviewer-claude": "ops review",
    "implementation-steward": "implementation steward",
    "impl-codex": "implementer",
    "impl-claude": "implementer",
    "reviewer-codex": "peer review",
    "reviewer-claude": "peer review",
    "final-reviewer-codex": "final review",
    "final-reviewer-gemini": "final review",
}
BRANCH_FIELD_NAMES = {
    "branch",
    "targetbranch",
    "target_branch",
    "headbranch",
    "head_branch",
    "sourcebranch",
    "source_branch",
    "prreadybranch",
    "pr_ready_branch",
    "integrationbranch",
    "integration_branch",
    "finalbranch",
    "final_branch",
}
MCP_PROGRESS_KEYS = {
    "expected_branch",
    "pr_ready_branch",
    "remote_branch_sha",
    "base_branch_sha",
    "branch_changed",
    "validation_status",
    "validation",
    "protocol",
    "blockers",
    "warnings",
    "terminal",
    "pull_request",
    "pr",
    "pr_url",
    "status",
    "health",
    "summary",
    "progress_lines",
    "change",
    "project_root",
    "base_branch",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def short_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def parse_json_object(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def normalize_branch(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("refs/heads/"):
        text = text.removeprefix("refs/heads/")
    if not text or len(text) > 140 or any(char.isspace() for char in text):
        return ""
    return text


def add_unique(values: list[str], value: Any) -> None:
    normalized = normalize_branch(value)
    if normalized and normalized not in values:
        values.append(normalized)


def as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if str(value or "").strip():
        return [str(value)]
    return []


def merge_unique_strings(values: list[str], additions: Any) -> None:
    for item in as_string_list(additions):
        if item not in values:
            values.append(item)


def structured_branch_refs(item: Any) -> list[str]:
    branches: list[str] = []

    def visit(value: Any, key: str = "") -> None:
        key_normalized = key.replace("-", "_").lower()
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                visit(child, key)
            return
        if key_normalized.replace("_", "") in BRANCH_FIELD_NAMES or key_normalized in BRANCH_FIELD_NAMES:
            add_unique(branches, value)

    visit(item)
    return branches


def structured_mcp_progress(item: Any, *, source: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    payload = parse_json_object(item.get("msg") or item.get("message") or item.get("summary"))
    candidates = [item]
    if payload:
        candidates.insert(0, payload)
    best: dict[str, Any] = {}
    for data in candidates:
        if not isinstance(data, dict):
            continue
        has_progress = any(key in data for key in MCP_PROGRESS_KEYS) or data.get("source") in {
            "steward_session",
            "steward_session_validator",
            "local_git",
            "openspec_validator",
        }
        if not has_progress:
            continue
        progress = {
            "source": source,
            "time": event_time(item) if item is not data else str(data.get("created") or data.get("time") or ""),
            "expected_branch": normalize_branch(data.get("expected_branch")),
            "pr_ready_branch": normalize_branch(data.get("pr_ready_branch")),
            "remote_branch_sha": str(data.get("remote_branch_sha") or ""),
            "base_branch_sha": str(data.get("base_branch_sha") or ""),
            "branch_changed": data.get("branch_changed") if isinstance(data.get("branch_changed"), bool) else None,
            "validation_status": str(data.get("validation_status") or ""),
            "validation": data.get("validation") if isinstance(data.get("validation"), dict) else {},
            "protocol": data.get("protocol") if isinstance(data.get("protocol"), dict) else {},
            "blockers": as_string_list(data.get("blockers")),
            "warnings": as_string_list(data.get("warnings")),
            "terminal": data.get("terminal") if isinstance(data.get("terminal"), dict) else {},
            "pull_request": data.get("pull_request") if isinstance(data.get("pull_request"), dict) else {},
            "pr_url": str(data.get("pr_url") or ""),
            "status": str(data.get("status") or ""),
            "health": str(data.get("health") or ""),
            "summary": short_text(data.get("summary") or "", 260),
            "progress_lines": as_string_list(data.get("progress_lines")),
            "change": str(data.get("change") or ""),
            "project_root": str(data.get("project_root") or ""),
            "base_branch": normalize_branch(data.get("base_branch")),
        }
        artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), dict) else {}
        remote_branches = artifacts.get("remote_branches") if isinstance(artifacts.get("remote_branches"), list) else data.get("remote_branches")
        if isinstance(remote_branches, list):
            progress["remote_branches"] = [item for item in remote_branches if isinstance(item, dict)]
        if artifacts:
            progress["artifacts"] = artifacts
        pr = data.get("pr") if isinstance(data.get("pr"), dict) else {}
        if pr and not progress["pull_request"]:
            progress["pull_request"] = {"pr": pr, "pr_url": str(pr.get("url") or "")}
        if progress["pull_request"] and not progress["pr_url"]:
            pull_request = progress["pull_request"]
            pr_data = pull_request.get("pr") if isinstance(pull_request.get("pr"), dict) else {}
            progress["pr_url"] = str(pull_request.get("pr_url") or pr_data.get("url") or "")
        best = progress
        break
    return best


def merge_mcp_progress(target: dict[str, Any], progress: dict[str, Any]) -> None:
    if not progress:
        return
    defaults = {
        "sources": [],
        "expected_branch": "",
        "pr_ready_branch": "",
        "remote_branch_sha": "",
        "base_branch_sha": "",
        "branch_changed": None,
        "validation_status": "",
        "validation": {},
        "protocol": {},
        "blockers": [],
        "warnings": [],
        "terminal": {},
        "pull_request": {},
        "pr_url": "",
        "status": "",
        "health": "",
        "summary": "",
        "progress_lines": [],
        "change": "",
        "project_root": "",
        "base_branch": "",
        "remote_branches": [],
        "artifacts": {},
    }
    existing = target.get("mcp")
    if not isinstance(existing, dict):
        existing = {}
    if "sources" not in existing:
        existing = {**defaults, **existing}
        target["mcp"] = existing
    source = str(progress.get("source") or "")
    if source and source not in existing["sources"]:
        existing["sources"].append(source)
    for key in ("expected_branch", "pr_ready_branch", "remote_branch_sha", "base_branch_sha", "validation_status", "status", "health", "summary", "change", "project_root", "base_branch", "pr_url"):
        if progress.get(key):
            existing[key] = progress[key]
    if progress.get("branch_changed") is not None:
        existing["branch_changed"] = progress["branch_changed"]
    for key in ("validation", "protocol", "terminal", "artifacts", "pull_request"):
        if progress.get(key):
            existing[key] = progress[key]
    merge_unique_strings(existing["blockers"], progress.get("blockers"))
    merge_unique_strings(existing["warnings"], progress.get("warnings"))
    merge_unique_strings(existing["progress_lines"], progress.get("progress_lines"))
    remote_branches = progress.get("remote_branches")
    if isinstance(remote_branches, list):
        seen = {(item.get("branch"), item.get("sha")) for item in existing["remote_branches"] if isinstance(item, dict)}
        for item in remote_branches:
            if not isinstance(item, dict):
                continue
            identity = (item.get("branch"), item.get("sha"))
            if identity not in seen:
                existing["remote_branches"].append(item)
                seen.add(identity)


def mcp_status_is_blocking(mcp: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(mcp.get("status") or ""),
            str(mcp.get("health") or ""),
            str(mcp.get("validation_status") or ""),
        ]
    ).lower()
    if mcp.get("blockers"):
        return True
    return any(token in text for token in ("blocked", "failed", "timed_out", "degraded"))


def fallback_branch_refs(*values: Any) -> list[str]:
    branches: list[str] = []
    for value in values:
        for branch in re.findall(r"round-[A-Za-z0-9._:/@+-]+", str(value or "")):
            add_unique(branches, branch)
    return branches


def normalize_final_verdict(value: Any) -> str:
    verdict = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if verdict in {"accept", "accepted", "approved", "success", "pass", "passed"}:
        return "accept"
    if verdict in {"reject", "rejected", "request_changes", "changes_requested", "revise", "blocked", "fail", "failed"}:
        return "request_changes" if verdict != "blocked" else "blocked"
    return verdict


def final_review_label(verdict: str) -> str:
    normalized = normalize_final_verdict(verdict)
    if normalized == "accept":
        return "accepted"
    if normalized == "request_changes":
        return "changes requested"
    if normalized == "blocked":
        return "blocked"
    return normalized.replace("_", " ") if normalized else ""


def final_review_from_item(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    payload = parse_json_object(item.get("msg") or item.get("message") or item.get("summary"))
    data = payload or item
    verdict = data.get("verdict") or data.get("finalReviewVerdict") or data.get("final_review_verdict")
    if not verdict:
        summary = str(item.get("summary") or item.get("msg") or item.get("message") or "")
        match = re.search(r"\b(accept(?:ed)?|approved|request_changes|changes_requested|revise|blocked)\b", summary, re.IGNORECASE)
        if ("final" in summary.lower() or "review" in summary.lower() or "outcome" in summary.lower()) and match:
            verdict = match.group(1)
    normalized = normalize_final_verdict(verdict)
    if normalized not in {"accept", "request_changes", "blocked"}:
        return {}
    summary = short_text(
        data.get("summary")
        or data.get("notes")
        or item.get("summary")
        or item.get("msg")
        or item.get("message"),
        260,
    )
    return {
        "source": source,
        "time": event_time(item),
        "verdict": str(verdict or ""),
        "normalized_verdict": normalized,
        "status": "accepted" if normalized == "accept" else "blocked",
        "display": final_review_label(normalized),
        "summary": summary,
        "branch": next(iter(structured_branch_refs(data)), ""),
        "blocking_issues": data.get("blocking_issues") if isinstance(data.get("blocking_issues"), list) else [],
    }


def final_review_from_outcome(outcome: Any) -> dict[str, Any]:
    if not isinstance(outcome, dict):
        return {}
    final_review = outcome.get("final_review") if isinstance(outcome.get("final_review"), dict) else {}
    data = final_review or outcome
    verdict = data.get("verdict") or data.get("normalized_verdict") or data.get("status")
    normalized = normalize_final_verdict(verdict)
    if normalized not in {"accept", "request_changes", "blocked"}:
        return {}
    summary = short_text(data.get("summary") or data.get("notes") or data.get("test_results") or outcome.get("source"), 260)
    return {
        "source": data.get("source") or outcome.get("source") or "outcome",
        "time": data.get("created") or data.get("time") or "",
        "verdict": str(data.get("verdict") or verdict or ""),
        "normalized_verdict": normalized,
        "status": "accepted" if normalized == "accept" else "blocked",
        "display": final_review_label(normalized),
        "summary": summary,
        "branch": next(iter(structured_branch_refs(data)), ""),
        "blocking_issues": data.get("blocking_issues") if isinstance(data.get("blocking_issues"), list) else [],
    }


def ok_source(name: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"source": name, "ok": status == "healthy", "status": status, **extra}


def error_source(name: str, error_kind: str, error: str, **extra: Any) -> dict[str, Any]:
    return {
        "source": name,
        "ok": False,
        "status": "unavailable" if error_kind.endswith("unavailable") else "degraded",
        "error_kind": error_kind,
        "error": error,
        **extra,
    }


def classify_command_failure(args: list[str], output: str) -> str:
    text = " ".join(args).lower() + "\n" + output.lower()
    if "unauthorized" in text or "forbidden" in text or "authentication" in text:
        return "hub_auth"
    if "broker" in text or "provider" in text or "dispatch" in text:
        return "broker_dispatch"
    if "kubernetes" in text or "kubectl" in text or "pod" in text:
        return "runtime"
    return "runtime"


def run_command(args: list[str], *, timeout: int = 12) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        return {
            "ok": False,
            "timed_out": True,
            "command": args,
            "output": output,
            "error": f"command timed out after {timeout}s",
            "error_kind": "runtime",
        }
    except OSError as exc:
        return {"ok": False, "command": args, "output": "", "error": str(exc), "error_kind": "runtime"}
    payload: dict[str, Any] = {
        "ok": result.returncode == 0,
        "timed_out": False,
        "returncode": result.returncode,
        "command": args,
        "output": result.stdout,
    }
    if not payload["ok"]:
        stderr = result.stderr.strip()
        payload["stderr"] = result.stderr
        payload["error"] = stderr or result.stdout.strip() or f"command exited {result.returncode}"
        payload["error_kind"] = classify_command_failure(args, f"{result.stdout}\n{result.stderr}")
    return payload


def extract_round_id(*values: Any) -> str:
    for value in values:
        match = ROUND_RE.search(str(value or ""))
        if match:
            return match.group("id").lower()
    return ""


def event_time(item: dict[str, Any]) -> str:
    for key in ("createdAt", "created", "updatedAt", "updated", "timestamp", "time"):
        if item.get(key):
            return str(item[key])
    return ""


def agent_status(agent: dict[str, Any]) -> str:
    phase = str(agent.get("phase") or "").lower()
    activity = str(agent.get("activity") or "").lower()
    container = json.dumps(agent.get("containerStatus") or "", default=str).lower()
    text = f"{phase} {activity} {container}"
    if any(token in text for token in ("error", "failed", "crashloop", "imagepull", "backoff", "limits_exceeded")):
        return "blocked"
    if any(token in text for token in ("succeeded", "completed", "stopped", "deleted", "ended")):
        return "completed"
    if any(token in text for token in ("running", "active", "working", "started")):
        return "running"
    if any(token in text for token in ("pending", "queued", "scheduled", "starting")):
        return "waiting"
    return "unknown"


def agent_template(agent: dict[str, Any]) -> str:
    return str(agent.get("template") or agent.get("agentTemplate") or "")


def agent_harness(agent: dict[str, Any]) -> str:
    for key in ("harnessConfig", "harness_config", "harness", "default_harness_config"):
        value = str(agent.get(key) or "").strip()
        if value:
            return value
    return TEMPLATE_HARNESSES.get(agent_template(agent), "")


def agent_role(agent: dict[str, Any]) -> str:
    template = agent_template(agent)
    if template in TEMPLATE_ROLES:
        return TEMPLATE_ROLES[template]
    name = str(agent.get("name") or agent.get("slug") or agent.get("agentId") or "").lower()
    suffix_roles = (
        ("spec-steward", "spec steward"),
        ("implementation-steward", "implementation steward"),
        ("spec-clarifier", "clarifier"),
        ("spec-explorer", "explorer"),
        ("spec-author", "author"),
        ("spec-ops-review", "ops review"),
        ("impl-codex", "implementer"),
        ("impl-claude", "implementer"),
        ("final-review", "final review"),
    )
    for suffix, role in suffix_roles:
        if name.endswith(suffix) or f"-{suffix}-" in name:
            return role
    return ""


def normalize_agent(agent: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(agent)
    name = str(agent.get("name") or agent.get("slug") or agent.get("agentId") or agent.get("id") or "")
    normalized["name"] = name
    normalized["template"] = agent_template(agent)
    normalized["role"] = agent_role(agent)
    normalized["harness_config"] = agent_harness(agent)
    normalized["status"] = agent_status(agent)
    return normalized


def agent_lookup(agents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for agent in agents:
        for key in (
            agent.get("name"),
            agent.get("slug"),
            agent.get("id"),
            agent.get("agentId"),
            f"agent:{agent.get('name')}" if agent.get("name") else "",
            f"agent:{agent.get('slug')}" if agent.get("slug") else "",
        ):
            text = str(key or "").strip()
            if text:
                lookup[text] = agent
    return lookup


def source_stale(latest: str, now: datetime | None = None) -> bool:
    parsed = parse_time(latest)
    if not parsed:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - parsed).total_seconds() > STALE_AFTER_SECONDS


def stable_digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def stable_source_id(kind: str, item: dict[str, Any], *, round_id: str = "") -> str:
    source_id = item.get("id") or item.get("source_id") or item.get("messageId") or item.get("notificationId")
    if source_id:
        return f"{kind}:{source_id}"
    fallback = {
        "round_id": round_id,
        "time": event_time(item),
        "actor": item.get("agentId") or item.get("sender") or item.get("senderId") or item.get("name") or "",
        "summary": short_text(item.get("msg") or item.get("message") or item.get("summary") or item.get("taskSummary") or item.get("activity"), 360),
    }
    return f"{kind}:fallback:{stable_digest(fallback)}"


def snapshot_cursor(snapshot: dict[str, Any], detail: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "readiness": snapshot.get("readiness"),
        "overview": snapshot.get("overview"),
        "rounds": [
            {
                "round_id": row.get("round_id"),
                "status": row.get("status"),
                "visible_status": row.get("visible_status"),
                "latest_update": row.get("latest_update"),
                "branches": row.get("branches"),
                "mcp": row.get("mcp"),
                "final_review": row.get("final_review"),
            }
            for row in snapshot.get("rounds", [])
            if isinstance(row, dict)
        ],
        "inbox": snapshot.get("inbox"),
        "sources": {
            name: {
                "ok": source.get("ok"),
                "status": source.get("status"),
                "error_kind": source.get("error_kind"),
                "error": source.get("error"),
            }
            for name, source in (snapshot.get("sources") or {}).items()
            if isinstance(source, dict)
        },
    }
    if detail:
        payload["round_detail"] = {
            "round_id": detail.get("round_id"),
            "visible_status": detail.get("visible_status"),
            "cursor": detail.get("cursor"),
            "timeline": [
                {"id": item.get("id"), "type": item.get("type"), "time": item.get("time"), "summary": item.get("summary")}
                for item in detail.get("timeline", [])
                if isinstance(item, dict)
            ],
            "mcp": detail.get("mcp"),
            "final_review": detail.get("final_review"),
        }
    return f"live:{stable_digest(payload)}"


def live_event(event_type: str, data: dict[str, Any], *, cursor: str, source: str, event_id: str = "") -> dict[str, Any]:
    event_id = event_id or f"{event_type}:{source}:{stable_digest(data)}"
    return {
        "id": event_id,
        "type": event_type,
        "source": source,
        "cursor": cursor,
        "generated_at": utc_now(),
        "data": data,
    }


def source_error_events(snapshot: dict[str, Any], *, cursor: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for name, source in (snapshot.get("sources") or {}).items():
        if not isinstance(source, dict) or source.get("ok", True):
            continue
        payload = {
            "source": name,
            "status": source.get("status") or "unavailable",
            "error_kind": source.get("error_kind") or "runtime",
            "error": source.get("error") or f"{name} unavailable",
        }
        events.append(live_event("source.error", payload, cursor=cursor, source=name, event_id=f"source.error:{name}:{stable_digest(payload)}"))
    return events


def timeline_entry(event: dict[str, Any], *, round_id: str, agents_by_actor: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    item = event.get("message") or event.get("notification") or event.get("agent") or {}
    if not isinstance(item, dict):
        item = {}
    entry_type = str(event.get("type") or "event")
    source_id = stable_source_id(entry_type, item, round_id=round_id)
    actor = str(item.get("agentId") or item.get("sender") or item.get("senderId") or item.get("name") or item.get("slug") or "")
    lookup = agents_by_actor or {}
    agent = lookup.get(actor) or lookup.get(actor.removeprefix("agent:")) or {}
    if not agent and (item.get("template") or item.get("name") or item.get("slug")):
        agent = normalize_agent(item)
    return {
        "id": source_id,
        "source_id": source_id,
        "type": entry_type,
        "time": event_time(item),
        "actor": actor,
        "agent_name": agent.get("name") or actor,
        "role": agent.get("role") or "",
        "template": agent.get("template") or "",
        "harness_config": agent.get("harness_config") or "",
        "phase": item.get("phase") or agent.get("phase") or "",
        "activity": item.get("activity") or agent.get("activity") or "",
        "summary": short_text(item.get("msg") or item.get("message") or item.get("summary") or item.get("taskSummary") or item.get("activity"), 360),
        "raw": item,
    }


def build_live_update_batch(provider: RuntimeProvider | Any, *, cursor: str = "", round_id: str = "") -> dict[str, Any]:
    snapshot = build_snapshot(provider)
    detail = build_round_detail(provider, round_id) if round_id else None
    next_cursor = snapshot_cursor(snapshot, detail)
    events: list[dict[str, Any]] = []
    mode = "cursor_resume" if cursor else "initial_snapshot"
    if cursor != next_cursor:
        events.append(live_event("snapshot.initial" if not cursor else "snapshot.updated", {"snapshot": snapshot}, cursor=next_cursor, source="snapshot", event_id=f"snapshot:{next_cursor}"))
        events.append(live_event("overview.updated", snapshot.get("overview") or {}, cursor=next_cursor, source="overview"))
        events.append(live_event("rounds.updated", {"rounds": snapshot.get("rounds") or []}, cursor=next_cursor, source="rounds"))
        events.append(live_event("inbox.updated", {"inbox": snapshot.get("inbox") or []}, cursor=next_cursor, source="inbox"))
        events.append(live_event("runtime.updated", {"sources": snapshot.get("sources") or {}}, cursor=next_cursor, source="runtime"))
        events.extend(source_error_events(snapshot, cursor=next_cursor))
        if detail:
            events.append(live_event("round.detail.updated", {"round": detail}, cursor=next_cursor, source="round_detail", event_id=f"round.detail:{round_id}:{next_cursor}"))
            for entry in detail.get("timeline", []):
                if isinstance(entry, dict):
                    events.append(live_event("timeline.appended", {"round_id": round_id, "entry": entry}, cursor=next_cursor, source="round_timeline", event_id=f"timeline:{round_id}:{entry.get('id') or stable_digest(entry)}"))
    heartbeat = live_event(
        "heartbeat",
        {
            "cursor": next_cursor,
            "stale_after_seconds": snapshot.get("stale_after_seconds", STALE_AFTER_SECONDS),
            "snapshot_generated_at": snapshot.get("generated_at"),
            "round_id": round_id,
        },
        cursor=next_cursor,
        source="web_app",
        event_id=f"heartbeat:{next_cursor}",
    )
    events.append(heartbeat)
    return {
        "ok": True,
        "mode": mode,
        "cursor": next_cursor,
        "previous_cursor": cursor,
        "generated_at": utc_now(),
        "events": events,
        "snapshot": snapshot,
        "round": detail or {},
    }


def snapshot_source_failed(snapshot: dict[str, Any], source: str) -> bool:
    payload = (snapshot.get("sources") or {}).get(source)
    return isinstance(payload, dict) and payload.get("ok") is False


def merge_rows_by_key(previous: list[Any], current: list[Any], key: str) -> list[Any]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for collection in (previous, current):
        for item in collection:
            if not isinstance(item, dict):
                continue
            item_key = str(item.get(key) or "")
            if not item_key:
                continue
            if item_key not in merged:
                order.append(item_key)
            merged[item_key] = item
    return [merged[item_key] for item_key in order]


def merge_inbox_groups(previous: list[Any], current: list[Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for group in previous + current:
        if not isinstance(group, dict):
            continue
        round_id = str(group.get("round_id") or "ungrouped")
        target = groups.setdefault(round_id, {"round_id": round_id, "items": [], "latest_update": ""})
        target["latest_update"] = max(str(target.get("latest_update") or ""), str(group.get("latest_update") or ""))
        seen = {
            (str(item.get("type") or ""), str(item.get("source_id") or ""), str(item.get("time") or ""), str(item.get("summary") or ""))
            for item in target["items"]
            if isinstance(item, dict)
        }
        for item in group.get("items", []) if isinstance(group.get("items"), list) else []:
            if not isinstance(item, dict):
                continue
            item_key = (str(item.get("type") or ""), str(item.get("source_id") or ""), str(item.get("time") or ""), str(item.get("summary") or ""))
            if item_key in seen:
                continue
            seen.add(item_key)
            target["items"].append(item)
            target["latest_update"] = max(str(target.get("latest_update") or ""), str(item.get("time") or ""))
        target["items"].sort(key=lambda item: item.get("time") or "", reverse=True)
    return sorted(groups.values(), key=lambda item: item.get("latest_update") or "", reverse=True)


def merge_snapshot_preserving_source_failures(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return current
    merged = dict(current)
    item_source_failed = snapshot_source_failed(current, "messages") or snapshot_source_failed(current, "notifications")
    if item_source_failed:
        merged["rounds"] = sorted(
            merge_rows_by_key(previous.get("rounds", []), current.get("rounds", []), "round_id"),
            key=lambda item: item.get("latest_update") or "",
            reverse=True,
        )
        merged["inbox"] = merge_inbox_groups(previous.get("inbox", []), current.get("inbox", []))
        overview = dict(current.get("overview") or {})
        rounds = merged.get("rounds") or []
        overview["active_round_count"] = len([item for item in rounds if item.get("status") in {"running", "waiting", "blocked"}])
        overview["recent_round_count"] = len(rounds)
        overview["latest_update"] = max((str(item.get("latest_update") or "") for item in rounds), default=overview.get("latest_update") or current.get("generated_at"))
        merged["overview"] = overview
    return merged


def merge_round_detail_preserving_source_failures(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return current
    events = current.get("events") if isinstance(current.get("events"), dict) else {}
    if events.get("ok", True) is not False:
        return current
    merged = dict(current)
    merged["timeline"] = previous.get("timeline", [])
    return merged


def merge_live_events(state: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    seen = state.setdefault("_seen_event_ids", set())
    if not isinstance(seen, set):
        seen = set(seen)
        state["_seen_event_ids"] = seen
    for event in events:
        event_id = str(event.get("id") or stable_digest(event))
        if event_id in seen:
            continue
        seen.add(event_id)
        event_type = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        state["cursor"] = event.get("cursor") or state.get("cursor", "")
        if event_type in {"snapshot.initial", "snapshot.updated"} and isinstance(data.get("snapshot"), dict):
            state["snapshot"] = merge_snapshot_preserving_source_failures(state.get("snapshot"), data["snapshot"])
        elif event_type == "overview.updated":
            state["overview"] = data
        elif event_type == "rounds.updated":
            if state.get("snapshot") and (snapshot_source_failed(state["snapshot"], "messages") or snapshot_source_failed(state["snapshot"], "notifications")):
                state["rounds"] = state["snapshot"].get("rounds", [])
            else:
                state["rounds"] = data.get("rounds", [])
        elif event_type == "inbox.updated":
            if state.get("snapshot") and (snapshot_source_failed(state["snapshot"], "messages") or snapshot_source_failed(state["snapshot"], "notifications")):
                state["inbox"] = state["snapshot"].get("inbox", [])
            else:
                state["inbox"] = data.get("inbox", [])
        elif event_type == "runtime.updated":
            state["sources"] = data.get("sources", {})
        elif event_type == "round.detail.updated" and isinstance(data.get("round"), dict):
            details = state.setdefault("rounds_detail", {})
            round_id = data["round"].get("round_id", "")
            details[round_id] = merge_round_detail_preserving_source_failures(details.get(round_id), data["round"])
        elif event_type == "timeline.appended" and isinstance(data.get("entry"), dict):
            timelines = state.setdefault("timelines", {})
            timeline = timelines.setdefault(data.get("round_id", ""), [])
            entry_id = data["entry"].get("id")
            if entry_id and any(existing.get("id") == entry_id for existing in timeline if isinstance(existing, dict)):
                continue
            timeline.append(data["entry"])
            timeline.sort(key=lambda item: item.get("time") or "", reverse=True)
        elif event_type == "source.error":
            state.setdefault("source_errors", {})[data.get("source", event.get("source"))] = data
        elif event_type == "heartbeat":
            state["last_heartbeat"] = data
    return state


class RuntimeProvider:
    def hub_status(self) -> dict[str, Any]:
        return scion_ops.scion_ops_hub_status()

    def hub_messages(self) -> dict[str, Any]:
        try:
            client = scion_ops.HubClient("")
            messages = client.messages(limit=250)
            return {"ok": True, "source": "hub_api", "hub": client.cfg.redacted(), "items": messages}
        except scion_ops.HubAPIError as exc:
            return scion_ops._hub_error_payload(exc, "web_app_messages")

    def hub_notifications(self) -> dict[str, Any]:
        try:
            client = scion_ops.HubClient("")
            notifications = client.notifications()
            return {"ok": True, "source": "hub_api", "hub": client.cfg.redacted(), "items": notifications}
        except scion_ops.HubAPIError as exc:
            return scion_ops._hub_error_payload(exc, "web_app_notifications")

    def round_status(self, round_id: str) -> dict[str, Any]:
        return scion_ops.scion_ops_round_status(round_id=round_id, include_transcript=False, num_lines=120)

    def round_events(self, round_id: str, cursor: str = "", include_existing: bool = False) -> dict[str, Any]:
        return scion_ops.scion_ops_round_events(round_id=round_id, cursor=cursor, include_existing=include_existing)

    def round_artifacts(self, round_id: str) -> dict[str, Any]:
        return scion_ops.scion_ops_round_artifacts(round_id=round_id)

    def spec_status(self, project_root: str, change: str = "") -> dict[str, Any]:
        return scion_ops.scion_ops_spec_status(project_root=project_root, change=change)

    def validate_spec_change(self, project_root: str, change: str) -> dict[str, Any]:
        return scion_ops.scion_ops_validate_spec_change(project_root=project_root, change=change)

    def mcp_status(self) -> dict[str, Any]:
        url = os.environ.get("SCION_OPS_MCP_URL", "http://192.168.122.103:8765/mcp")
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                return ok_source("mcp", "healthy", url=url, http_status=resp.status)
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return ok_source("mcp", "healthy", url=url, http_status=exc.code)
            return error_source("mcp", "runtime", f"MCP returned HTTP {exc.code}", url=url, http_status=exc.code)
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            return error_source("mcp", "runtime", f"MCP request failed: {exc}", url=url)

    def kubernetes_status(self) -> dict[str, Any]:
        namespace = os.environ.get("SCION_K8S_NAMESPACE", "scion-agents")
        args = [
            "kubectl",
            *scion_ops._kubectl_context_args(),
            "-n",
            namespace,
            "get",
            "deploy,pod,svc,endpoints,pvc",
            "-o",
            "json",
        ]
        result = run_command(args)
        if not result["ok"]:
            return error_source(
                "kubernetes",
                result.get("error_kind", "runtime"),
                result.get("error", "kubectl failed"),
                command=args,
            )
        try:
            payload = json.loads(result["output"])
        except json.JSONDecodeError as exc:
            return error_source("kubernetes", "runtime", f"kubectl returned non-JSON output: {exc}", command=args)
        return normalize_kubernetes(payload, namespace=namespace)


def normalize_kubernetes(payload: dict[str, Any], *, namespace: str) -> dict[str, Any]:
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    deployments: list[dict[str, Any]] = []
    pods: list[dict[str, Any]] = []
    services: list[dict[str, Any]] = []
    endpoints: list[dict[str, Any]] = []
    pvcs: list[dict[str, Any]] = []
    for item in items:
        kind = item.get("kind")
        meta = item.get("metadata") or {}
        name = str(meta.get("name") or "")
        labels = meta.get("labels") or {}
        part_of = labels.get("app.kubernetes.io/part-of") == "scion-control-plane"
        relevant = part_of or name in CONTROL_PLANE_NAMES or name.startswith("round-")
        if not relevant:
            continue
        if kind == "Deployment":
            status = item.get("status") or {}
            desired = int(status.get("replicas") or item.get("spec", {}).get("replicas") or 0)
            available = int(status.get("availableReplicas") or 0)
            deployments.append({
                "name": name,
                "desired": desired,
                "available": available,
                "ready": desired > 0 and available >= desired,
            })
        elif kind == "Pod":
            status = item.get("status") or {}
            phase = str(status.get("phase") or "")
            ready = any(
                cond.get("type") == "Ready" and cond.get("status") == "True"
                for cond in status.get("conditions", [])
                if isinstance(cond, dict)
            )
            pods.append({"name": name, "phase": phase, "ready": ready})
        elif kind == "Service":
            services.append({"name": name, "type": item.get("spec", {}).get("type") or ""})
        elif kind == "Endpoints":
            subsets = item.get("subsets") if isinstance(item.get("subsets"), list) else []
            address_count = sum(len(subset.get("addresses") or []) for subset in subsets if isinstance(subset, dict))
            endpoints.append({"name": name, "address_count": address_count, "ready": address_count > 0})
        elif kind == "PersistentVolumeClaim":
            pvcs.append({"name": name, "phase": item.get("status", {}).get("phase") or ""})
    deployment_names = {item["name"] for item in deployments}
    service_names = {item["name"] for item in services}
    endpoint_names = {item["name"] for item in endpoints if item["ready"]}
    missing = sorted(CONTROL_PLANE_DEPLOYMENTS - deployment_names)
    missing_services = sorted(CONTROL_PLANE_SERVICES - service_names)
    missing_endpoints = sorted(CONTROL_PLANE_SERVICES - endpoint_names)
    bad_deployments = [item for item in deployments if not item["ready"]]
    bad_pods = [item for item in pods if not item["ready"] and item["phase"] not in {"Succeeded", "Completed"}]
    status = "healthy" if not missing and not missing_services and not missing_endpoints and not bad_deployments and not bad_pods else "degraded"
    return ok_source(
        "kubernetes",
        status,
        namespace=namespace,
        deployments=deployments,
        pods=pods,
        services=services,
        endpoints=endpoints,
        pvcs=pvcs,
        missing_deployments=missing,
        missing_services=missing_services,
        missing_endpoints=missing_endpoints,
        degraded_pods=bad_pods,
    )


def web_app_status_from_kubernetes(kubernetes: dict[str, Any]) -> dict[str, Any]:
    if not kubernetes.get("ok"):
        return error_source(
            "web_app",
            str(kubernetes.get("error_kind") or "runtime"),
            str(kubernetes.get("error") or "Kubernetes status unavailable"),
        )
    deployment = next((item for item in kubernetes.get("deployments", []) if item.get("name") == "scion-ops-web-app"), None)
    service = next((item for item in kubernetes.get("services", []) if item.get("name") == "scion-ops-web-app"), None)
    endpoint = next((item for item in kubernetes.get("endpoints", []) if item.get("name") == "scion-ops-web-app"), None)
    missing: list[str] = []
    if deployment is None:
        missing.append("deployment")
    elif not deployment.get("ready"):
        missing.append("deployment_ready")
    if service is None:
        missing.append("service")
    if endpoint is None or not endpoint.get("ready"):
        missing.append("endpoint")
    status = "healthy" if not missing else "degraded"
    return ok_source(
        "web_app",
        status,
        deployment=deployment or {},
        service=service or {},
        endpoint=endpoint or {},
        missing=missing,
    )


def normalize_hub(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("ok"):
        return error_source(
            "hub",
            str(payload.get("error_kind") or "hub_state"),
            str(payload.get("error") or "Hub status unavailable"),
            hub=payload.get("hub") or {},
        )
    brokers = payload.get("brokers") if isinstance(payload.get("brokers"), list) else []
    providers = payload.get("providers") if isinstance(payload.get("providers"), list) else []
    agents = payload.get("agents") if isinstance(payload.get("agents"), list) else []
    status = "healthy" if brokers or providers else "degraded"
    return ok_source(
        "hub",
        status,
        hub=payload.get("hub") or {},
        health=payload.get("health"),
        grove=payload.get("grove") or {},
        providers=providers,
        brokers=brokers,
        agents=agents,
        phase_counts=dict(Counter(str(agent.get("phase") or "unknown") for agent in agents if isinstance(agent, dict))),
    )


def normalize_messages(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("ok"):
        return error_source("messages", str(payload.get("error_kind") or "hub_state"), str(payload.get("error") or "Messages unavailable"))
    return ok_source("messages", "healthy", items=[item for item in payload.get("items", []) if isinstance(item, dict)])


def normalize_notifications(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("ok"):
        return error_source("notifications", str(payload.get("error_kind") or "hub_state"), str(payload.get("error") or "Notifications unavailable"))
    return ok_source("notifications", "healthy", items=[item for item in payload.get("items", []) if isinstance(item, dict)])


def build_rounds(agents: list[dict[str, Any]], messages: list[dict[str, Any]], notifications: list[dict[str, Any]], *, provider: Any = None) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    def ensure(round_id: str) -> dict[str, Any]:
        return grouped.setdefault(
            round_id,
            {
                "round_id": round_id,
                "agents": [],
                "messages": [],
                "notifications": [],
                "branches": [],
                "branch_source": "",
                "latest_update": "",
                "latest_summary": "",
                "status": "unknown",
                "visible_status": "unknown",
                "phase": "unknown",
                "outcome": "",
                "final_review": {},
                "mcp": {},
                "_structured_branches": [],
                "_fallback_branches": [],
            },
        )

    for agent in agents:
        round_id = extract_round_id(agent.get("name"), agent.get("slug"), agent.get("taskSummary"))
        if not round_id:
            continue
        agent = normalize_agent(agent)
        row = ensure(round_id)
        row["agents"].append(agent)
        for branch in structured_branch_refs(agent):
            add_unique(row["_structured_branches"], branch)
        for branch in fallback_branch_refs(agent.get("taskSummary")):
            add_unique(row["_fallback_branches"], branch)
        updated = str(agent.get("updated") or agent.get("created") or "")
        if updated > row["latest_update"]:
            row["latest_update"] = updated
            row["latest_summary"] = short_text(agent.get("taskSummary") or agent.get("activity") or agent.get("phase"))

    for collection_name, collection in (("messages", messages), ("notifications", notifications)):
        for item in collection:
            round_id = extract_round_id(
                item.get("roundId"),
                item.get("agentId"),
                item.get("sender"),
                item.get("senderId"),
                item.get("msg"),
                item.get("message"),
                item.get("summary"),
            )
            if not round_id:
                continue
            row = ensure(round_id)
            row[collection_name].append(item)
            payload = parse_json_object(item.get("msg") or item.get("message") or item.get("summary"))
            for branch in structured_branch_refs(item):
                add_unique(row["_structured_branches"], branch)
            for branch in structured_branch_refs(payload):
                add_unique(row["_structured_branches"], branch)
            merge_mcp_progress(row, structured_mcp_progress(item, source=collection_name[:-1]))
            for branch in fallback_branch_refs(item.get("msg"), item.get("message"), item.get("summary")):
                add_unique(row["_fallback_branches"], branch)
            review = final_review_from_item(item, source=collection_name[:-1])
            if review and str(review.get("time") or "") >= str(row.get("final_review", {}).get("time") or ""):
                row["final_review"] = review
            timestamp = event_time(item)
            if timestamp > row["latest_update"]:
                row["latest_update"] = timestamp
                row["latest_summary"] = short_text(item.get("msg") or item.get("message") or item.get("summary"))

    if provider is not None:
        for round_id, row in grouped.items():
            try:
                status_data = provider.round_status(round_id)
                merge_mcp_progress(row, structured_mcp_progress(status_data, source="round_status"))
                outcome = status_data.get("outcome") or {}
                merge_mcp_progress(row, structured_mcp_progress(outcome, source="round_status.outcome"))
                outcome_review = final_review_from_outcome(outcome)
                if outcome_review:
                    existing_time = str(row.get("final_review", {}).get("time") or "")
                    outcome_time = str(outcome_review.get("time") or "")
                    if not row["final_review"] or outcome_time >= existing_time:
                        row["final_review"] = outcome_review
            except Exception:
                pass
            try:
                artifacts = provider.round_artifacts(round_id)
                if isinstance(artifacts, dict):
                    merge_mcp_progress(row, {
                        "source": "round_artifacts",
                        "artifacts": artifacts,
                        "remote_branches": artifacts.get("remote_branches", []),
                    })
                    for branch in structured_branch_refs(artifacts):
                        add_unique(row["_structured_branches"], branch)
                    for branch in artifacts.get("branches", []) if isinstance(artifacts.get("branches"), list) else []:
                        add_unique(row["_structured_branches"], branch)
            except Exception:
                pass

    for row in grouped.values():
        statuses = [agent_status(agent) for agent in row["agents"]]
        if "blocked" in statuses:
            row["status"] = "blocked"
        elif any(status in {"running", "waiting"} for status in statuses):
            row["status"] = "running" if "running" in statuses else "waiting"
        elif statuses and all(status == "completed" for status in statuses):
            row["status"] = "completed"
        elif not row["agents"] and (row["messages"] or row["notifications"]):
            row["status"] = "observed"
        mcp = row.get("mcp") if isinstance(row.get("mcp"), dict) else {}
        if mcp_status_is_blocking(mcp):
            row["status"] = "blocked"
        elif row["status"] in {"unknown", "observed"} and mcp.get("status") in {"completed", "running", "waiting", "starting", "observed"}:
            row["status"] = str(mcp["status"])
        if row["final_review"]:
            if row["final_review"].get("status") == "blocked":
                row["status"] = "blocked"
            elif row["status"] in {"unknown", "observed"}:
                row["status"] = "completed"
            row["visible_status"] = str(row["final_review"].get("display") or row["status"])
        else:
            row["visible_status"] = row["status"]
        phases = [str(agent.get("phase") or "") for agent in row["agents"] if agent.get("phase")]
        row["phase"] = Counter(phases).most_common(1)[0][0] if phases else row["phase"]
        row["harnesses"] = sorted({agent.get("harness_config") for agent in row["agents"] if agent.get("harness_config")})
        row["roles"] = sorted({agent.get("role") for agent in row["agents"] if agent.get("role")})
        summaries = [str(agent.get("taskSummary") or "") for agent in row["agents"] if agent.get("taskSummary")]
        terminal = next((summary for summary in summaries if "complete:" in summary.lower() or "blocked" in summary.lower()), "")
        row["outcome"] = (
            row["final_review"].get("summary")
            or (row.get("mcp") or {}).get("summary")
            or short_text("; ".join((row.get("mcp") or {}).get("blockers", [])), 260)
            or short_text(terminal)
        )
        if row["_structured_branches"]:
            row["branches"] = row["_structured_branches"]
            row["branch_source"] = "structured"
        else:
            row["branches"] = row["_fallback_branches"]
            row["branch_source"] = "fallback" if row["branches"] else ""
        row["agent_count"] = len(row["agents"])
        row["message_count"] = len(row["messages"])
        row["notification_count"] = len(row["notifications"])
        del row["_structured_branches"]
        del row["_fallback_branches"]
    return sorted(grouped.values(), key=lambda item: item.get("latest_update") or "", reverse=True)


def build_inbox(messages: list[dict[str, Any]], notifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for kind, collection in (("message", messages), ("notification", notifications)):
        for item in collection:
            round_id = extract_round_id(
                item.get("roundId"),
                item.get("agentId"),
                item.get("sender"),
                item.get("senderId"),
                item.get("msg"),
                item.get("message"),
                item.get("summary"),
            ) or "ungrouped"
            groups[round_id].append({
                "type": kind,
                "time": event_time(item),
                "source_id": item.get("id") or item.get("agentId") or item.get("sender") or "",
                "summary": short_text(item.get("msg") or item.get("message") or item.get("summary") or item.get("status"), 260),
                "raw": item,
            })
    result = []
    for round_id, items in groups.items():
        result.append({
            "round_id": round_id,
            "items": sorted(items, key=lambda item: item.get("time") or "", reverse=True),
            "latest_update": max((str(item.get("time") or "") for item in items), default=""),
        })
    return sorted(result, key=lambda item: item.get("latest_update") or "", reverse=True)


def readiness_status(sources: dict[str, dict[str, Any]]) -> str:
    required = ["hub", "broker", "mcp", "web_app", "kubernetes"]
    states = [sources.get(name, {}).get("status", "unavailable") for name in required]
    if all(state == "healthy" for state in states):
        return "ready"
    if any(state == "healthy" for state in states):
        return "degraded"
    return "unavailable"


def transcript_display(transcript: dict[str, Any]) -> tuple[str, str]:
    if not transcript:
        return "", ""
    if transcript.get("ok"):
        return str(transcript.get("output") or ""), ""

    output = str(transcript.get("output") or "")
    error = str(transcript.get("error") or "")
    text = f"{output}\n{error}".lower()
    if (
        "failed to capture terminal output" in text
        and (
            "not_found" in text
            or "action not found" in text
            or "resource not found" in text
            or "status: 404" in text
        )
    ):
        return "", "Terminal output unavailable from Hub for this agent."
    return "", short_text(error or output, 500)


def build_health() -> dict[str, Any]:
    return {
        "ok": True,
        "status": "healthy",
        "service": "scion-ops-web-app",
        "generated_at": utc_now(),
    }


def build_snapshot(provider: RuntimeProvider | Any) -> dict[str, Any]:
    generated_at = utc_now()
    hub = normalize_hub(provider.hub_status())
    messages = normalize_messages(provider.hub_messages())
    notifications = normalize_notifications(provider.hub_notifications())
    mcp = provider.mcp_status()
    kubernetes = provider.kubernetes_status()
    web_app = web_app_status_from_kubernetes(kubernetes)
    brokers = hub.get("brokers", []) if hub.get("ok") else []
    broker = ok_source("broker", "healthy" if brokers else "degraded", brokers=brokers, count=len(brokers))
    agents = hub.get("agents", []) if hub.get("ok") else []
    message_items = messages.get("items", []) if messages.get("ok") else []
    notification_items = notifications.get("items", []) if notifications.get("ok") else []
    rounds = build_rounds(agents, message_items, notification_items, provider=provider)
    latest = max([item.get("latest_update") or "" for item in rounds], default="")
    stale = source_stale(latest, parse_time(generated_at))
    sources = {
        "hub": hub,
        "broker": broker,
        "mcp": mcp,
        "web_app": web_app,
        "kubernetes": kubernetes,
        "messages": messages,
        "notifications": notifications,
    }
    status = readiness_status(sources)
    if stale and status == "ready":
        status = "degraded"
    return {
        "ok": any(source.get("ok") for source in sources.values()),
        "generated_at": generated_at,
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "stale": stale,
        "readiness": status,
        "sources": sources,
        "overview": {
            "readiness": status,
            "active_round_count": len([item for item in rounds if item["status"] in {"running", "waiting", "blocked"}]),
            "recent_round_count": len(rounds),
            "agent_count": len(agents),
            "latest_update": latest or generated_at,
        },
        "rounds": rounds,
        "inbox": build_inbox(message_items, notification_items),
    }


def build_round_detail(provider: RuntimeProvider | Any, round_id: str) -> dict[str, Any]:
    status = provider.round_status(round_id)
    events = provider.round_events(round_id, include_existing=True)
    timeline: list[dict[str, Any]] = []
    structured_branches: list[str] = []
    fallback_branches: list[str] = []
    final_reviews: list[dict[str, Any]] = []
    mcp_holder: dict[str, Any] = {"mcp": {}}
    merge_mcp_progress(mcp_holder, structured_mcp_progress(status, source="round_status"))
    detail_agents = [
        normalize_agent(agent)
        for agent in status.get("agents", [])
        if isinstance(agent, dict)
    ] if isinstance(status.get("agents"), list) else []
    agents_by_actor = agent_lookup(detail_agents)
    status = {**status, "agents": detail_agents}
    for agent in detail_agents:
        for branch in structured_branch_refs(agent):
            add_unique(structured_branches, branch)
        for branch in fallback_branch_refs(agent.get("taskSummary")):
            add_unique(fallback_branches, branch)
    outcome = status.get("outcome") or events.get("outcome") or {}
    merge_mcp_progress(mcp_holder, structured_mcp_progress(outcome, source="round_status.outcome"))
    for branch in structured_branch_refs(outcome):
        add_unique(structured_branches, branch)
    outcome_review = final_review_from_outcome(outcome)
    if outcome_review:
        final_reviews.append(outcome_review)
    if events.get("ok"):
        merge_mcp_progress(mcp_holder, structured_mcp_progress(events, source="round_events"))
        for event in events.get("events", []):
            item = event.get("message") or event.get("notification") or event.get("agent") or {}
            payload = parse_json_object(item.get("msg") or item.get("message") or item.get("summary"))
            for branch in structured_branch_refs(item):
                add_unique(structured_branches, branch)
            for branch in structured_branch_refs(payload):
                add_unique(structured_branches, branch)
            merge_mcp_progress(mcp_holder, structured_mcp_progress(item, source=str(event.get("type") or "event")))
            for branch in fallback_branch_refs(item.get("msg"), item.get("message"), item.get("summary"), item.get("taskSummary")):
                add_unique(fallback_branches, branch)
            if event.get("message") or event.get("notification"):
                review = final_review_from_item(item, source=str(event.get("type") or "event"))
                if review:
                    final_reviews.append(review)
            timeline.append(timeline_entry(event, round_id=round_id, agents_by_actor=agents_by_actor))
    artifacts: dict[str, Any] = {}
    try:
        artifacts = provider.round_artifacts(round_id)
    except Exception:
        artifacts = {}
    if isinstance(artifacts, dict) and artifacts:
        merge_mcp_progress(mcp_holder, {
            "source": "round_artifacts",
            "artifacts": artifacts,
            "remote_branches": artifacts.get("remote_branches", []),
        })
        for branch in structured_branch_refs(artifacts):
            add_unique(structured_branches, branch)
        for branch in artifacts.get("branches", []) if isinstance(artifacts.get("branches"), list) else []:
            add_unique(structured_branches, branch)
    mcp = mcp_holder["mcp"]
    spec_status: dict[str, Any] = {}
    if mcp.get("project_root") and mcp.get("change") and hasattr(provider, "spec_status"):
        try:
            spec_status = provider.spec_status(mcp["project_root"], mcp["change"])
        except Exception:
            spec_status = {}
        if isinstance(spec_status, dict) and spec_status:
            validation = spec_status.get("validation") if isinstance(spec_status.get("validation"), dict) else {}
            if validation:
                mcp["validation"] = validation
                mcp["validation_status"] = "passed" if validation.get("ok") else "failed"
    transcript = status.get("status_transcript") if isinstance(status.get("status_transcript"), dict) else {}
    if not transcript and isinstance(status.get("consensus_transcript"), dict):
        transcript = status.get("consensus_transcript")
    runner_output, runner_output_error = transcript_display(transcript)
    final_reviews.sort(key=lambda item: item.get("time") or "")
    branches = structured_branches if structured_branches else fallback_branches
    final_review = final_reviews[-1] if final_reviews else {}
    visible_status = str(final_review.get("display") or status.get("status") or "unknown")
    if mcp_status_is_blocking(mcp):
        visible_status = "blocked"
    elif mcp.get("status") and visible_status == "unknown":
        visible_status = str(mcp["status"])
    return {
        "ok": bool(status.get("ok")) or bool(events.get("ok")),
        "round_id": round_id,
        "status": status,
        "events": events,
        "timeline": sorted(timeline, key=lambda item: item.get("time") or "", reverse=True),
        "runner_output": runner_output,
        "runner_output_error": runner_output_error,
        "outcome": outcome,
        "final_review": final_review,
        "visible_status": visible_status,
        "branches": branches,
        "branch_source": "structured" if structured_branches else ("fallback" if branches else ""),
        "mcp": mcp,
        "artifacts": artifacts if isinstance(artifacts, dict) else {},
        "spec_status": spec_status if isinstance(spec_status, dict) else {},
        "cursor": events.get("cursor") or "",
    }


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>scion-ops hub</title>
  <style>
    :root { color-scheme: light; --bg:#f7f7f5; --panel:#ffffff; --text:#202225; --muted:#676b73; --line:#d8d9dc; --good:#217a3b; --warn:#a05a00; --bad:#b42318; --info:#1f5f99; }
    * { box-sizing: border-box; }
    body { margin:0; font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif; background:var(--bg); color:var(--text); }
    header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 20px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:2; }
    h1 { font-size:18px; margin:0; }
    nav { display:flex; gap:4px; flex-wrap:wrap; }
    button { border:1px solid var(--line); background:#fff; padding:7px 10px; border-radius:6px; cursor:pointer; color:var(--text); }
    button.active { background:#202225; color:#fff; border-color:#202225; }
    main { max-width:1280px; margin:0 auto; padding:18px 20px 32px; }
    .bar { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; color:var(--muted); }
    .live-bar { align-items:flex-start; }
    .live-state { display:flex; flex-direction:column; gap:3px; }
    .secondary { font-size:12px; padding:5px 8px; color:var(--muted); }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
    .card, .table-wrap, .detail { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; }
    .status { display:inline-flex; align-items:center; gap:6px; font-weight:650; text-transform:capitalize; }
    .dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; }
    .ready .dot, .healthy .dot, .completed .dot, .accepted .dot, .connected .dot, .fallback-polling .dot { background:var(--good); }
    .degraded .dot, .waiting .dot, .stale .dot, .observed .dot, .reconnecting .dot { background:var(--warn); }
    .unavailable .dot, .blocked .dot, .error .dot, .changes-requested .dot, .failed .dot { background:var(--bad); }
    .running .dot { background:var(--info); }
    .muted { color:var(--muted); }
    .meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }
    .pill { display:inline-flex; align-items:center; gap:5px; border:1px solid var(--line); border-radius:999px; padding:2px 7px; background:#f8f9fa; font-size:12px; max-width:100%; }
    .agent-grid { display:grid; gap:8px; }
    .agent-card { display:grid; gap:6px; border:1px solid var(--line); border-radius:8px; padding:10px; background:#fff; }
    .agent-head { display:flex; justify-content:space-between; gap:8px; align-items:flex-start; }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; padding:9px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-size:12px; font-weight:650; }
    tr[data-round] { cursor:pointer; }
    tr[data-round]:hover { background:#f1f3f4; }
    .hidden { display:none; }
    .mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px; white-space:pre-wrap; overflow:auto; max-height:360px; background:#111820; color:#e9eef4; border-radius:6px; padding:10px; }
    .timeline { display:grid; gap:8px; }
    .timeline .item { border-left:3px solid var(--line); padding:5px 0 5px 10px; }
    .split { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(300px,.9fr); gap:12px; }
    .error-box { border:1px solid #efb5b0; background:#fff7f6; color:#681a14; border-radius:6px; padding:10px; }
    @media (max-width: 800px) { header { align-items:flex-start; flex-direction:column; } .split { grid-template-columns:1fr; } th:nth-child(4), td:nth-child(4) { display:none; } }
  </style>
</head>
<body>
  <header>
    <h1>scion-ops hub</h1>
    <nav>
      <button data-view="overview" class="active">Overview</button>
      <button data-view="rounds">Rounds</button>
      <button data-view="inbox">Inbox</button>
      <button data-view="runtime">Runtime</button>
    </nav>
  </header>
  <main>
    <div class="bar live-bar"><div id="refresh-state" class="live-state">Loading...</div></div>
    <section id="overview"></section>
    <section id="rounds" class="hidden"></section>
    <section id="round-detail" class="hidden"></section>
    <section id="inbox" class="hidden"></section>
    <section id="runtime" class="hidden"></section>
  </main>
  <script>
    const state = {
      view: "overview",
      snapshot: null,
      selectedRound: "",
      roundDetails: {},
      cursors: {},
      timelineKeys: {},
      live: { state: "reconnecting", mode: "fallback", lastOk: "", error: "", source: "snapshot" },
      poll: { snapshot: null, detail: null, stale: null },
      stream: null
    };
    const SNAPSHOT_POLL_MS = 15000;
    const ROUND_EVENT_POLL_MS = 5000;
    const STALE_GRACE_MS = 45000;
    const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
    const status = value => {
      const label = String(value || "unknown");
      const cls = label.toLowerCase().replace(/[\s_]+/g, "-");
      return `<span class="status ${esc(cls)}"><span class="dot"></span>${esc(label)}</span>`;
    };
    const field = (label, value) => value !== undefined && value !== null && String(value) !== "" ? `<div><strong>${esc(label)}</strong><div class="mono">${esc(value)}</div></div>` : "";
    const meta = (label, value) => value !== undefined && value !== null && String(value) !== "" ? `<span class="pill"><span class="muted">${esc(label)}</span> ${esc(value)}</span>` : "";
    const listBlock = (label, values, kind = "") => values?.length ? `<h3>${esc(label)}</h3>${values.map(value => `<div class="${kind || "muted"}">${esc(value)}</div>`).join("")}` : "";
    const mcpBlock = mcp => !mcp ? "" : `
      <h3>MCP State</h3>
      ${field("Expected branch", mcp.expected_branch)}
      ${field("PR-ready branch", mcp.pr_ready_branch)}
      ${field("Remote branch SHA", mcp.remote_branch_sha)}
      ${field("Validation", mcp.validation_status)}
      ${field("Pull request", mcp.pr_url || mcp.pull_request?.pr_url || mcp.pull_request?.pr?.url)}
      ${mcp.branch_changed !== null && mcp.branch_changed !== undefined ? field("Branch changed", mcp.branch_changed) : ""}
      ${listBlock("Blockers", mcp.blockers, "error-box")}
      ${listBlock("Warnings", mcp.warnings)}
      ${mcp.protocol && Object.keys(mcp.protocol).length ? `<pre class="mono">${esc(JSON.stringify(mcp.protocol, null, 2))}</pre>` : ""}`;
    const fmt = value => value ? new Date(value).toLocaleString() : "unknown";
    const sourceErrorBanner = names => names
      .map(name => state.snapshot?.sources?.[name])
      .filter(source => source?.ok === false)
      .map(source => `<div class="error-box">${esc(source.source || "source")}: ${esc(source.error_kind || "unavailable")} - ${esc(source.error || "source unavailable; showing last known data")}</div>`)
      .join("");
    async function getJson(url) {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return await response.json();
    }
    const captureScroll = () => ({ x: window.scrollX, y: window.scrollY });
    const restoreScroll = scroll => requestAnimationFrame(() => window.scrollTo(scroll.x, scroll.y));
    const liveLabel = () => state.live.state === "fallback" ? "fallback polling" : state.live.state;
    function updateLiveState(next) {
      state.live = { ...state.live, ...next };
      const fresh = state.live.lastOk ? `Last update ${fmt(state.live.lastOk)}` : "Waiting for first update";
      const detail = state.live.error ? `${state.live.source}: ${state.live.error}` : `${fresh} via ${state.live.mode}`;
      document.getElementById("refresh-state").innerHTML = `<div>${status(liveLabel())}</div><div class="muted">${esc(detail)}</div>`;
    }
    function markLiveOk(source) {
      updateLiveState({ state: "fallback", mode: "fallback polling", lastOk: new Date().toISOString(), error: "", source });
    }
    function markStreamOk(source) {
      updateLiveState({ state: "connected", mode: "stream", lastOk: new Date().toISOString(), error: "", source });
    }
    function markLiveError(source, err) {
      updateLiveState({ state: state.live.lastOk ? "reconnecting" : "failed", source, error: err.message || String(err) });
    }
    const snapshotSourceFailed = (snapshot, source) => snapshot?.sources?.[source]?.ok === false;
    const itemSourcesFailed = snapshot => snapshotSourceFailed(snapshot, "messages") || snapshotSourceFailed(snapshot, "notifications");
    function mergeRowsByKey(previous = [], current = [], key) {
      const rows = new Map();
      for (const item of [...previous, ...current]) {
        if (!item || !item[key]) continue;
        rows.set(String(item[key]), item);
      }
      return [...rows.values()].sort((a, b) => String(b.latest_update || "").localeCompare(String(a.latest_update || "")));
    }
    function mergeInboxGroups(previous = [], current = []) {
      const groups = new Map();
      for (const group of [...previous, ...current]) {
        const roundId = String(group?.round_id || "ungrouped");
        const target = groups.get(roundId) || { round_id: roundId, items: [], latest_update: "" };
        const seen = new Set(target.items.map(item => [item.type, item.source_id, item.time, item.summary].map(value => String(value || "")).join("|")));
        for (const item of group?.items || []) {
          const key = [item.type, item.source_id, item.time, item.summary].map(value => String(value || "")).join("|");
          if (seen.has(key)) continue;
          seen.add(key);
          target.items.push(item);
          if (String(item.time || "") > String(target.latest_update || "")) target.latest_update = item.time || "";
        }
        if (String(group?.latest_update || "") > String(target.latest_update || "")) target.latest_update = group.latest_update;
        target.items.sort((a, b) => String(b.time || "").localeCompare(String(a.time || "")));
        groups.set(roundId, target);
      }
      return [...groups.values()].sort((a, b) => String(b.latest_update || "").localeCompare(String(a.latest_update || "")));
    }
    function mergeSnapshot(nextSnapshot) {
      if (!state.snapshot || !itemSourcesFailed(nextSnapshot)) return nextSnapshot;
      const merged = { ...nextSnapshot };
      merged.rounds = mergeRowsByKey(state.snapshot.rounds || [], nextSnapshot.rounds || [], "round_id");
      merged.inbox = mergeInboxGroups(state.snapshot.inbox || [], nextSnapshot.inbox || []);
      merged.overview = { ...(nextSnapshot.overview || {}) };
      merged.overview.active_round_count = merged.rounds.filter(item => ["running", "waiting", "blocked"].includes(item.status)).length;
      merged.overview.recent_round_count = merged.rounds.length;
      merged.overview.latest_update = merged.rounds.reduce((latest, item) => String(item.latest_update || "") > latest ? String(item.latest_update || "") : latest, merged.overview.latest_update || nextSnapshot.generated_at || "");
      return merged;
    }
    function setRoundDetail(roundId, detail) {
      const previous = state.roundDetails[roundId];
      if (previous && detail?.events?.ok === false) {
        detail = { ...detail, timeline: previous.timeline || [] };
      }
      state.roundDetails[roundId] = detail;
      state.cursors[roundId] = detail.cursor || state.cursors[roundId] || "";
      delete state.timelineKeys[roundId];
      seedTimelineKeys(roundId);
    }
    function checkStaleness() {
      if (!state.live.lastOk) return;
      const age = Date.now() - new Date(state.live.lastOk).getTime();
      if (age > Math.max(STALE_GRACE_MS, (state.snapshot?.stale_after_seconds || 0) * 1000)) {
        updateLiveState({ state: "stale", error: "automatic updates are stale" });
      }
    }
    async function refresh() {
      try {
        const scroll = captureScroll();
        state.snapshot = mergeSnapshot(await getJson("/api/snapshot"));
        markLiveOk("snapshot");
        render();
        restoreScroll(scroll);
      } catch (err) {
        markLiveError("snapshot", err);
      }
    }
    const timelineKey = item => [item.type, item.time, item.summary, item.raw?.id || item.raw?.agentId || item.raw?.sender || ""].map(value => String(value || "")).join("|");
    const eventToTimeline = event => {
      const item = event.message || event.notification || event.agent || {};
      const actor = item.agentId || item.sender || item.senderId || item.name || item.slug || "";
      return {
        type: event.type || "event",
        time: item.createdAt || item.created || item.updatedAt || item.updated || item.timestamp || item.time || "",
        actor,
        agent_name: item.name || item.slug || actor,
        role: item.role || "",
        template: item.template || "",
        harness_config: item.harness_config || item.harnessConfig || item.harness || "",
        phase: item.phase || "",
        activity: item.activity || "",
        summary: item.msg || item.message || item.summary || item.taskSummary || item.activity || "",
        raw: item
      };
    };
    function seedTimelineKeys(roundId) {
      const detail = state.roundDetails[roundId];
      if (!detail || state.timelineKeys[roundId]) return;
      state.timelineKeys[roundId] = new Set((detail.timeline || []).map(timelineKey));
    }
    function mergeTimelineEvents(roundId, eventsPayload) {
      const detail = state.roundDetails[roundId];
      if (!detail || !eventsPayload?.ok) return false;
      seedTimelineKeys(roundId);
      let changed = false;
      for (const event of eventsPayload.events || []) {
        const item = eventToTimeline(event);
        const key = timelineKey(item);
        if (state.timelineKeys[roundId].has(key)) continue;
        state.timelineKeys[roundId].add(key);
        detail.timeline.push(item);
        changed = true;
      }
      detail.timeline.sort((a, b) => String(b.time || "").localeCompare(String(a.time || "")));
      if (eventsPayload.cursor) state.cursors[roundId] = eventsPayload.cursor;
      return changed;
    }
    function applyLiveEvent(payload) {
      if (!payload || typeof payload !== "object") return;
      if (payload.type === "heartbeat") {
        markStreamOk(payload.source || "stream");
        return;
      }
      const data = payload.data || {};
      if ((payload.type === "snapshot.initial" || payload.type === "snapshot.updated") && data.snapshot) {
        const scroll = captureScroll();
        state.snapshot = mergeSnapshot(data.snapshot);
        markStreamOk("snapshot");
        render();
        restoreScroll(scroll);
        return;
      }
      if (payload.type === "source.error") {
        const source = data.source || payload.source || "source";
        markLiveError(source, new Error(data.error || `${source} unavailable`));
        return;
      }
      if (payload.type === "round.detail.updated" && data.round?.round_id) {
        setRoundDetail(data.round.round_id, data.round);
        markStreamOk("round-detail");
        if (state.selectedRound === data.round.round_id) renderRoundDetail();
        return;
      }
      if (payload.type === "timeline.appended" && data.round_id && data.entry) {
        const detail = state.roundDetails[data.round_id];
        if (!detail) return;
        seedTimelineKeys(data.round_id);
        const key = timelineKey(data.entry);
        if (!state.timelineKeys[data.round_id].has(key)) {
          state.timelineKeys[data.round_id].add(key);
          detail.timeline.push(data.entry);
          detail.timeline.sort((a, b) => String(b.time || "").localeCompare(String(a.time || "")));
          if (state.selectedRound === data.round_id) renderRoundDetail();
        }
        markStreamOk("round-timeline");
        return;
      }
      if ((payload.type === "rounds.updated" || payload.type === "inbox.updated" || payload.type === "overview.updated" || payload.type === "runtime.updated") && state.snapshot) {
        if (payload.type === "rounds.updated" && !itemSourcesFailed(state.snapshot)) state.snapshot.rounds = data.rounds || [];
        if (payload.type === "inbox.updated" && !itemSourcesFailed(state.snapshot)) state.snapshot.inbox = data.inbox || [];
        if (payload.type === "overview.updated" && !itemSourcesFailed(state.snapshot)) state.snapshot.overview = data;
        if (payload.type === "runtime.updated") state.snapshot.sources = data.sources || state.snapshot.sources;
        markStreamOk(payload.source || "stream");
        render();
        return;
      }
      if (payload.type === "snapshot" && payload.snapshot) {
        const scroll = captureScroll();
        state.snapshot = mergeSnapshot(payload.snapshot);
        markStreamOk("snapshot");
        render();
        restoreScroll(scroll);
        return;
      }
      if (payload.type === "round_events" && payload.round_id) {
        const changed = mergeTimelineEvents(payload.round_id, payload);
        markStreamOk("round-events");
        if (changed && state.selectedRound === payload.round_id) renderRoundDetail();
        return;
      }
      if (payload.type === "round_detail" && payload.round_id && payload.detail) {
        setRoundDetail(payload.round_id, payload.detail);
        markStreamOk("round-detail");
        if (state.selectedRound === payload.round_id) renderRoundDetail();
      }
    }
    function startLiveUpdates() {
      if (!("EventSource" in window)) {
        updateLiveState({ state: "fallback", mode: "fallback polling", source: "snapshot", error: "" });
        return;
      }
      try {
        const stream = new EventSource("/api/live");
        state.stream = stream;
        stream.onopen = () => markStreamOk("stream");
        stream.onmessage = event => applyLiveEvent(JSON.parse(event.data));
        stream.addEventListener("snapshot.initial", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("snapshot.updated", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("overview.updated", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("rounds.updated", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("inbox.updated", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("runtime.updated", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("source.error", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("round.detail.updated", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("timeline.appended", event => applyLiveEvent(JSON.parse(event.data)));
        stream.addEventListener("heartbeat", event => applyLiveEvent(JSON.parse(event.data)));
        stream.onerror = () => {
          stream.close();
          state.stream = null;
          updateLiveState({ state: "fallback", mode: "fallback polling", source: "stream", error: "stream unavailable; using automatic polling" });
        };
      } catch (err) {
        updateLiveState({ state: "fallback", mode: "fallback polling", source: "stream", error: err.message || String(err) });
      }
    }
    function renderOverview() {
      const s = state.snapshot;
      const sources = s.sources;
      document.getElementById("overview").innerHTML = `
        <div class="grid">
          <div class="card"><div>${status(s.overview.readiness)}</div><div class="muted">Control plane readiness</div></div>
          <div class="card"><strong>${s.overview.active_round_count}</strong><div class="muted">Active or blocked rounds</div></div>
          <div class="card"><strong>${s.overview.agent_count}</strong><div class="muted">Hub agents</div></div>
          <div class="card"><strong>${fmt(s.overview.latest_update)}</strong><div class="muted">Latest update</div></div>
        </div>
        <h2>Checks</h2>
        <div class="grid">${["hub","broker","mcp","web_app","kubernetes"].map(name => `<div class="card"><div>${status(sources[name]?.status)}</div><strong>${esc(name)}</strong><div class="muted">${esc(sources[name]?.error || `${sources[name]?.count ?? ""} ${name === "broker" ? "brokers" : ""}`)}</div></div>`).join("")}</div>`;
    }
    function renderRounds() {
      const rows = state.snapshot.rounds;
      const warnings = sourceErrorBanner(["messages", "notifications"]);
      document.getElementById("rounds").innerHTML = rows.length ? `
        ${warnings}
        <div class="table-wrap"><table><thead><tr><th>Round</th><th>Status</th><th>Phase</th><th>Agents</th><th>Latest update</th><th>Outcome</th><th>Branches</th><th>MCP</th></tr></thead><tbody>
        ${rows.map(row => `<tr data-round="${esc(row.round_id)}"><td class="mono">${esc(row.round_id)}</td><td>${status(row.visible_status || row.status)}</td><td>${esc(row.phase)}</td><td>${row.agent_count}<div class="meta">${(row.harnesses || []).map(value => meta("harness", value)).join("")}${(row.roles || []).slice(0, 3).map(value => meta("role", value)).join("")}</div></td><td>${fmt(row.latest_update)}<div class="muted">${esc(row.latest_summary)}</div></td><td>${esc(row.outcome || "")}${row.mcp?.blockers?.length ? `<div class="error-box">${esc(row.mcp.blockers.join("; "))}</div>` : ""}</td><td>${(row.branches || []).map(branch => `<div class="mono">${esc(branch)}</div>`).join("")}${row.branch_source ? `<div class="muted">${esc(row.branch_source)}</div>` : ""}</td><td>${field("Expected", row.mcp?.expected_branch)}${field("PR-ready", row.mcp?.pr_ready_branch)}${field("Validation", row.mcp?.validation_status)}${field("Remote SHA", row.mcp?.remote_branch_sha)}</td></tr>`).join("")}
        </tbody></table></div>` : `${warnings}<div class="card"><strong>No rounds found</strong><div class="muted">Hub returned no round-identifiable agents, messages, or notifications.</div></div>`;
      document.querySelectorAll("[data-round]").forEach(row => row.onclick = () => openRound(row.dataset.round));
    }
    async function openRound(roundId, { force = false } = {}) {
      state.selectedRound = roundId;
      setView("round-detail");
      if (!state.roundDetails[roundId] || force) {
        document.getElementById("round-detail").innerHTML = `<div class="card">Loading ${esc(roundId)}...</div>`;
        const detail = await getJson(`/api/rounds/${encodeURIComponent(roundId)}`);
        setRoundDetail(roundId, detail);
        markLiveOk("round-detail");
      }
      renderRoundDetail();
      startRoundEventPolling();
    }
    async function pollSelectedRoundEvents() {
      const roundId = state.selectedRound;
      if (!roundId || state.view !== "round-detail") return;
      try {
        const cursor = state.cursors[roundId] || "";
        const payload = await getJson(`/api/rounds/${encodeURIComponent(roundId)}/events?cursor=${encodeURIComponent(cursor)}`);
        const changed = mergeTimelineEvents(roundId, payload);
        markLiveOk("round-events");
        if (changed) renderRoundDetail();
      } catch (err) {
        markLiveError("round-events", err);
        try {
          await openRound(roundId, { force: true });
          updateLiveState({ state: "fallback", mode: "fallback snapshot", source: "round-detail", error: "" });
        } catch (fallbackErr) {
          markLiveError("round-detail", fallbackErr);
        }
      }
    }
    function startRoundEventPolling() {
      if (state.poll.detail) clearInterval(state.poll.detail);
      state.poll.detail = setInterval(pollSelectedRoundEvents, ROUND_EVENT_POLL_MS);
    }
    function renderRoundDetail() {
      const roundId = state.selectedRound;
      const detail = state.roundDetails[roundId];
      if (!detail) return;
      const agents = detail.status.agents || [];
      const review = detail.final_review || {};
      const timelineItem = item => `<div class="item"><div>${status(item.type)}</div><div class="muted">${fmt(item.time)}</div><div>${esc(item.summary)}</div><div class="meta">${meta("agent", item.agent_name || item.actor)}${meta("role", item.role)}${meta("template", item.template)}${meta("harness", item.harness_config)}${meta("phase", item.phase)}${meta("activity", item.activity)}</div></div>`;
      const agentCard = agent => `<div class="agent-card"><div class="agent-head"><strong>${esc(agent.name || agent.slug)}</strong>${status(agent.status || agent.phase || "unknown")}</div><div class="meta">${meta("role", agent.role)}${meta("template", agent.template)}${meta("harness", agent.harness_config)}${meta("phase", agent.phase)}${meta("activity", agent.activity)}</div><div class="muted">${esc(agent.taskSummary || agent.activity || "")}</div></div>`;
      document.getElementById("round-detail").innerHTML = `
        <div class="bar"><button id="back-rounds">Back to rounds</button></div>
        <div class="split">
          <div class="detail"><h2 class="mono">${esc(roundId)}</h2><div>${status(detail.visible_status || detail.status.status || "unknown")}</div><h3>Timeline</h3><div class="timeline">${detail.timeline.length ? detail.timeline.map(timelineItem).join("") : `<div class="muted">No messages or notifications for this round.</div>`}</div></div>
          <div class="detail"><h3>Final Review</h3>${review.display ? `<div>${status(review.display)}</div><div class="muted">${esc(review.source || "")}${review.summary ? ` - ${esc(review.summary)}` : ""}</div>` : `<div class="muted">No final review available.</div>`}${mcpBlock(detail.mcp)}<h3>Branches</h3>${detail.branches?.length ? detail.branches.map(branch => `<div class="mono">${esc(branch)}</div>`).join("") + (detail.branch_source ? `<div class="muted">${esc(detail.branch_source)}</div>` : "") : `<div class="muted">No branch references available.</div>`}<h3>Agents</h3>${agents.length ? `<div class="agent-grid">${agents.map(agentCard).join("")}</div>` : `<div class="muted">No agents found.</div>`}<h3>Coordinator Output</h3>${detail.runner_output ? `<pre class="mono">${esc(detail.runner_output)}</pre>` : `<div class="muted">${esc(detail.runner_output_error || "No coordinator output available.")}</div>`}</div>
        </div>`;
      document.getElementById("back-rounds").onclick = () => setView("rounds");
    }
    function renderInbox() {
      const groups = state.snapshot.inbox;
      const warnings = sourceErrorBanner(["messages", "notifications"]);
      document.getElementById("inbox").innerHTML = groups.length ? warnings + groups.map(group => `
        <div class="detail"><h2>${esc(group.round_id)}</h2>${group.items.map(item => `<div class="timeline item"><div>${status(item.type)}</div><div class="muted">${fmt(item.time)} ${esc(item.source_id)}</div><div>${esc(item.summary)}</div></div>`).join("")}</div>`).join("") : `${warnings}<div class="card"><strong>No inbox updates</strong><div class="muted">Hub returned no messages or notifications.</div></div>`;
    }
    function renderRuntime() {
      const sources = state.snapshot.sources;
      document.getElementById("runtime").innerHTML = `<div class="grid">${Object.entries(sources).map(([name, value]) => `<div class="card"><div>${status(value.status)}</div><h2>${esc(name)}</h2>${value.error ? `<div class="error-box">${esc(value.error_kind)}: ${esc(value.error)}</div>` : ""}<pre class="mono">${esc(JSON.stringify(value, null, 2))}</pre></div>`).join("")}</div>`;
    }
    function setView(view) {
      state.view = view;
      document.querySelectorAll("main > section").forEach(el => el.classList.add("hidden"));
      document.querySelectorAll("nav button").forEach(btn => btn.classList.toggle("active", btn.dataset.view === view));
      document.getElementById(view).classList.remove("hidden");
      render();
    }
    function render() {
      if (!state.snapshot) return;
      renderOverview(); renderRounds(); renderInbox(); renderRuntime();
      if (state.view === "round-detail") {
        renderRoundDetail();
        return;
      }
      if (state.view !== "round-detail") {
        document.querySelectorAll("main > section").forEach(el => el.classList.add("hidden"));
        document.getElementById(state.view).classList.remove("hidden");
      }
    }
    document.querySelectorAll("nav button").forEach(btn => btn.onclick = () => setView(btn.dataset.view));
    startLiveUpdates();
    state.poll.snapshot = setInterval(refresh, SNAPSHOT_POLL_MS);
    state.poll.stale = setInterval(checkStaleness, 5000);
    refresh();
  </script>
</body>
</html>
"""


class HubRequestHandler(BaseHTTPRequestHandler):
    provider: RuntimeProvider = RuntimeProvider()

    def do_HEAD(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/":
                self.respond_html(INDEX_HTML)
            elif path in {"/healthz", "/api/healthz"}:
                self.respond_json(build_health())
            elif path == "/api/snapshot":
                self.respond_json(build_snapshot(self.provider))
            elif path == "/api/contract":
                self.respond_json({"ok": True, "contract": BROWSER_JSON_CONTRACT})
            elif path in {"/api/live", "/api/stream"}:
                cursor = query.get("cursor", [self.headers.get("Last-Event-ID", "")])[0]
                round_id = query.get("round_id", [""])[0]
                accepts_sse = "text/event-stream" in self.headers.get("Accept", "") or query.get("format", [""])[0] == "sse"
                if accepts_sse:
                    self.respond_sse(cursor=cursor, round_id=round_id, seconds=int(query.get("seconds", ["30"])[0] or 30))
                else:
                    self.respond_json(build_live_update_batch(self.provider, cursor=cursor, round_id=round_id))
            elif path == "/api/overview":
                self.respond_json(build_snapshot(self.provider)["overview"])
            elif path == "/api/rounds":
                self.respond_json({"rounds": build_snapshot(self.provider)["rounds"]})
            elif path.startswith("/api/rounds/") and path.endswith("/events"):
                round_id = urllib.parse.unquote(path.removeprefix("/api/rounds/").removesuffix("/events").strip("/"))
                self.respond_json(self.provider.round_events(round_id, cursor=query.get("cursor", [""])[0], include_existing=False))
            elif path.startswith("/api/rounds/"):
                round_id = urllib.parse.unquote(path.removeprefix("/api/rounds/").strip("/"))
                self.respond_json(build_round_detail(self.provider, round_id))
            elif path == "/api/inbox":
                self.respond_json({"inbox": build_snapshot(self.provider)["inbox"]})
            elif path == "/api/runtime":
                self.respond_json({"sources": build_snapshot(self.provider)["sources"]})
            else:
                self.respond_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.respond_json({"ok": False, "error_kind": "web_app", "error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        self.respond_json({"ok": False, "error": "web app hub is read-only"}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    def do_PUT(self) -> None:
        self.do_POST()

    def do_PATCH(self) -> None:
        self.do_POST()

    def do_DELETE(self) -> None:
        self.do_POST()

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def respond_html(self, body: str) -> None:
        data = body.encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, sort_keys=True, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_sse(self, *, cursor: str = "", round_id: str = "", seconds: int = 30) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        deadline = time.monotonic() + max(1, min(seconds, 60))
        current_cursor = cursor
        while time.monotonic() <= deadline:
            batch = build_live_update_batch(self.provider, cursor=current_cursor, round_id=round_id)
            current_cursor = batch["cursor"]
            try:
                for event in batch["events"]:
                    self.write_sse_event(event)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            if batch["events"] and any(event.get("type") != "heartbeat" for event in batch["events"]):
                continue
            time.sleep(15)

    def write_sse_event(self, event: dict[str, Any]) -> None:
        data = json.dumps(event, sort_keys=True, default=str)
        frame = f"id: {event.get('cursor') or event.get('id') or ''}\nevent: {event.get('type') or 'message'}\ndata: {data}\n\n"
        self.wfile.write(frame.encode())


def serve(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), HubRequestHandler)
    print(f"scion-ops web app hub listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only scion-ops web app hub.")
    parser.add_argument("--host", default=os.environ.get("SCION_OPS_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SCION_OPS_WEB_PORT", "8787")))
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
