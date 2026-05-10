#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "nicegui>=2.0,<3",
#   "PyYAML>=6,<7",
# ]
# ///
"""Read-only browser hub for scion-ops runtime state."""

from __future__ import annotations

import argparse
import hashlib
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
        "decision_flow": "role-ordered outline of starts, reports, decisions, and terminal explanations with agent/template/harness provenance",
        "consensus": "multi-harness role participation and review/steward summary",
        "terminal_summary": "operator-facing current/terminal explanation, including blockers or stall context when available",
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
ROLE_FLOW_ORDER = {
    "spec steward": 0,
    "clarifier": 10,
    "explorer": 20,
    "author": 30,
    "ops review": 40,
    "spec finalizer": 45,
    "implementation steward": 50,
    "implementer": 60,
    "peer review": 70,
    "final review": 80,
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


def role_rank(role: Any) -> int:
    return ROLE_FLOW_ORDER.get(str(role or "").strip().lower(), 999)


def flow_label(summary: Any, *, status: Any = "", event_type: Any = "") -> str:
    text = " ".join([str(summary or ""), str(status or ""), str(event_type or "")]).lower()
    if any(token in text for token in ("blocked", "failed", "failure", "error", "changes requested", "request_changes")):
        return "Blocked"
    if re.search(r"\baccept(?:ed)?\b|\bapproved\b|\bverdict[^a-z0-9]+accept\b", text):
        return "Accepted"
    if any(token in text for token in ("ready", "pr recorded", "pull request", "validated", "validation passed")):
        return "Ready"
    if any(token in text for token in ("complete", "completed", "task_completed", "succeeded")):
        return "Completed"
    if any(token in text for token in ("started", "starting", "created")):
        return "Started"
    if any(token in text for token in ("stalled", "idle", "waiting")):
        return "Waiting"
    if event_type:
        return "Notified" if str(event_type) == "notification" else "Reported"
    return "Reported"


def flow_event(label: str, summary: Any, *, time_value: Any = "", source: str = "", event_type: str = "") -> dict[str, Any]:
    return {
        "label": label,
        "summary": short_text(summary, 360),
        "time": str(time_value or ""),
        "source": source,
        "type": event_type,
    }


def add_flow_event(stage: dict[str, Any], event: dict[str, Any]) -> None:
    if not event.get("summary"):
        return
    identity = (event.get("label"), event.get("summary"), event.get("time"), event.get("source"))
    existing = {
        (item.get("label"), item.get("summary"), item.get("time"), item.get("source"))
        for item in stage.get("events", [])
        if isinstance(item, dict)
    }
    if identity not in existing:
        stage.setdefault("events", []).append(event)


def build_decision_flow(agents: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    by_agent: dict[str, dict[str, Any]] = {}
    by_role: dict[str, dict[str, Any]] = {}

    def stage_for(role: str, agent_name: str = "", agent: dict[str, Any] | None = None) -> dict[str, Any]:
        role = role or "observed"
        key = agent_name or f"role:{role}"
        stage = by_agent.get(key) or by_role.get(role)
        if stage is None:
            stage = {
                "id": f"{role}:{agent_name or stable_digest({'role': role, 'agent': agent_name})}",
                "role": role,
                "agent_name": agent_name,
                "template": "",
                "harness_config": "",
                "status": "observed",
                "phase": "",
                "activity": "",
                "started_at": "",
                "updated_at": "",
                "events": [],
            }
            stages.append(stage)
        if agent:
            stage["agent_name"] = stage.get("agent_name") or str(agent.get("name") or "")
            stage["template"] = stage.get("template") or str(agent.get("template") or "")
            stage["harness_config"] = stage.get("harness_config") or str(agent.get("harness_config") or "")
            stage["status"] = str(agent.get("status") or stage.get("status") or "observed")
            stage["phase"] = str(agent.get("phase") or stage.get("phase") or "")
            stage["activity"] = str(agent.get("activity") or stage.get("activity") or "")
            stage["started_at"] = str(agent.get("created") or stage.get("started_at") or "")
            stage["updated_at"] = str(agent.get("updated") or stage.get("updated_at") or "")
        if agent_name:
            by_agent[agent_name] = stage
        by_role[role] = stage
        return stage

    normalized_agents = [normalize_agent(agent) for agent in agents if isinstance(agent, dict)]
    for agent in sorted(normalized_agents, key=lambda item: (role_rank(item.get("role")), str(item.get("created") or ""), str(item.get("name") or ""))):
        role = str(agent.get("role") or "observed")
        name = str(agent.get("name") or agent.get("slug") or "")
        stage = stage_for(role, name, agent)
        if agent.get("created"):
            add_flow_event(stage, flow_event("Started", f"{role} started", time_value=agent.get("created"), source=name, event_type="agent"))
        summary = agent.get("taskSummary") or agent.get("activity") or agent.get("phase")
        if summary:
            add_flow_event(
                stage,
                flow_event(
                    flow_label(summary, status=agent.get("status")),
                    summary,
                    time_value=agent.get("updated") or agent.get("created"),
                    source=name,
                    event_type="agent",
                ),
            )

    for item in sorted([entry for entry in timeline if isinstance(entry, dict)], key=lambda entry: str(entry.get("time") or "")):
        role = str(item.get("role") or "")
        agent_name = str(item.get("agent_name") or item.get("actor") or "")
        agent = by_agent.get(agent_name) or by_agent.get(agent_name.removeprefix("agent:")) or {}
        if not role and agent:
            role = str(agent.get("role") or "")
        stage = stage_for(role or "observed", str(agent.get("agent_name") or agent.get("name") or agent_name))
        if item.get("template") and not stage.get("template"):
            stage["template"] = str(item.get("template") or "")
        if item.get("harness_config") and not stage.get("harness_config"):
            stage["harness_config"] = str(item.get("harness_config") or "")
        if item.get("phase") and not stage.get("phase"):
            stage["phase"] = str(item.get("phase") or "")
        if item.get("activity"):
            stage["activity"] = str(item.get("activity") or stage.get("activity") or "")
        summary = item.get("summary") or item.get("activity")
        add_flow_event(
            stage,
            flow_event(
                flow_label(summary, status=stage.get("status"), event_type=item.get("type")),
                summary,
                time_value=item.get("time"),
                source=str(item.get("source_id") or item.get("actor") or ""),
                event_type=str(item.get("type") or "event"),
            ),
        )

    for stage in stages:
        stage["events"] = sorted(stage.get("events", []), key=lambda item: str(item.get("time") or ""))
        latest = stage["events"][-1] if stage["events"] else {}
        stage["latest_event"] = latest
        stage["summary"] = latest.get("summary") or ""

    return sorted(stages, key=lambda item: (role_rank(item.get("role")), str(item.get("started_at") or item.get("updated_at") or ""), str(item.get("agent_name") or "")))


def build_terminal_summary(
    *,
    visible_status: str,
    mcp: dict[str, Any],
    final_review: dict[str, Any],
    agents: list[dict[str, Any]],
    decision_flow: list[dict[str, Any]],
    outcome: Any,
) -> str:
    blockers = as_string_list(mcp.get("blockers"))
    if blockers:
        return f"Blocked: {short_text('; '.join(blockers), 420)}"

    review_text = short_text(final_review.get("summary") or "", 420) if final_review else ""
    status_text = str(visible_status or "").lower()
    if status_text in {"blocked", "failed", "changes requested", "request_changes"}:
        return f"{visible_status.capitalize()}: {review_text or short_text(mcp.get('summary') or outcome, 420) or 'see the latest role events for details'}"

    terminal = mcp.get("terminal") if isinstance(mcp.get("terminal"), dict) else {}
    terminal_summary = short_text(terminal.get("summary") or terminal.get("message") or "", 420)
    if terminal_summary:
        return terminal_summary

    latest_events = [
        stage.get("latest_event")
        for stage in decision_flow
        if isinstance(stage.get("latest_event"), dict) and stage.get("latest_event", {}).get("summary")
    ]
    latest_events.sort(key=lambda item: str(item.get("time") or ""))
    latest = latest_events[-1] if latest_events else {}

    stalled = [
        str(agent.get("role") or agent.get("name") or "")
        for agent in agents
        if "stall" in str(agent.get("activity") or "").lower() and agent_status(agent) != "completed"
    ]
    if stalled:
        detail = latest.get("summary") or mcp.get("summary") or "no later explanation is available"
        return f"Stalled: {', '.join(stalled)}. Last update: {short_text(detail, 360)}"

    if status_text in {"completed", "accepted"}:
        return f"Completed: {review_text or short_text(mcp.get('summary') or latest.get('summary') or outcome, 420)}"
    if status_text in {"running", "waiting", "observed", "unknown"}:
        if latest:
            return f"Current: {short_text(latest.get('summary'), 420)}"
        return "No role decision messages have been observed yet."
    return short_text(review_text or mcp.get("summary") or latest.get("summary") or "", 420)


def build_consensus_summary(agents: list[dict[str, Any]], decision_flow: list[dict[str, Any]], final_review: dict[str, Any], mcp: dict[str, Any]) -> dict[str, Any]:
    harness_roles: dict[str, list[str]] = defaultdict(list)
    for agent in agents:
        role = str(agent.get("role") or "")
        harness = str(agent.get("harness_config") or "")
        if role and harness and role not in harness_roles[harness]:
            harness_roles[harness].append(role)
    harnesses = sorted(harness_roles)
    review_display = str(final_review.get("display") or "")
    review_summary = short_text(final_review.get("summary") or "", 260)
    terminal_status = str((mcp.get("terminal") or {}).get("status") or mcp.get("status") or "")
    parts = []
    if len(harnesses) > 1:
        parts.append(f"Multi-LLM flow across {', '.join(harnesses)}")
    elif harnesses:
        parts.append(f"Single-harness flow on {harnesses[0]}")
    if review_display:
        parts.append(f"review {review_display}")
    if terminal_status:
        parts.append(f"terminal {terminal_status}")
    if not parts and decision_flow:
        parts.append(f"{len(decision_flow)} role stages observed")
    return {
        "mode": "multi_harness" if len(harnesses) > 1 else ("single_harness" if harnesses else "unknown"),
        "harnesses": [{"harness": harness, "roles": harness_roles[harness]} for harness in harnesses],
        "stage_count": len(decision_flow),
        "review": review_display,
        "summary": "; ".join(parts),
        "review_summary": review_summary,
    }


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
                "flow_summary": row.get("flow_summary"),
                "terminal_summary": row.get("terminal_summary"),
                "decision_flow": row.get("decision_flow"),
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
            "decision_flow": detail.get("decision_flow"),
            "terminal_summary": detail.get("terminal_summary"),
            "consensus": detail.get("consensus"),
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
        agents_by_actor = agent_lookup(row["agents"])
        row_timeline: list[dict[str, Any]] = []
        for message in row["messages"]:
            row_timeline.append(timeline_entry({"type": "message", "message": message}, round_id=row["round_id"], agents_by_actor=agents_by_actor))
        for notification in row["notifications"]:
            row_timeline.append(timeline_entry({"type": "notification", "notification": notification}, round_id=row["round_id"], agents_by_actor=agents_by_actor))
        row["decision_flow"] = build_decision_flow(row["agents"], row_timeline)
        row["consensus"] = build_consensus_summary(row["agents"], row["decision_flow"], row["final_review"], row.get("mcp") or {})
        row["terminal_summary"] = build_terminal_summary(
            visible_status=row["visible_status"],
            mcp=row.get("mcp") or {},
            final_review=row["final_review"],
            agents=row["agents"],
            decision_flow=row["decision_flow"],
            outcome=row["outcome"],
        )
        row["flow_summary"] = row["terminal_summary"] or row["outcome"] or row["latest_summary"]
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
    sorted_timeline = sorted(timeline, key=lambda item: item.get("time") or "", reverse=True)
    decision_flow = build_decision_flow(detail_agents, sorted_timeline)
    consensus = build_consensus_summary(detail_agents, decision_flow, final_review, mcp)
    terminal_summary = build_terminal_summary(
        visible_status=visible_status,
        mcp=mcp,
        final_review=final_review,
        agents=detail_agents,
        decision_flow=decision_flow,
        outcome=outcome,
    )
    return {
        "ok": bool(status.get("ok")) or bool(events.get("ok")),
        "round_id": round_id,
        "status": status,
        "events": events,
        "timeline": sorted_timeline,
        "decision_flow": decision_flow,
        "consensus": consensus,
        "terminal_summary": terminal_summary,
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


NICEGUI_FRONTEND_MARKERS = {
    "framework": "nicegui",
    "entrypoint": "scripts/web_app_hub.py",
    "routes": ["/", "/rounds", "/rounds/{round_id}", "/inbox", "/runtime", "/troubleshooting"],
    "json_contracts": [
        "/healthz",
        "/api/healthz",
        "/api/snapshot",
        "/api/rounds",
        "/api/rounds/{round_id}",
        "/api/rounds/{round_id}/events",
        "/api/live",
        "/api/inbox",
        "/api/runtime",
    ],
    "live_markers": ["EventSource", "fallback polling", "cursor resume", "stale feedback"],
    "layout_markers": ["operator-console", "responsive-grid", "dense-rounds", "one-level-down-troubleshooting"],
    "read_only_forbidden": [
        "start round",
        "abort round",
        "retry round",
        "delete round",
        "archive round",
        "write git",
        "write openspec",
        "mutate kubernetes",
    ],
}


def source_operator_summary(name: str, source: dict[str, Any]) -> dict[str, Any]:
    status = str(source.get("status") or ("healthy" if source.get("ok") else "unavailable"))
    detail = ""
    if source.get("error"):
        detail = f"{source.get('error_kind') or 'source'}: {source.get('error')}"
    elif name == "broker":
        detail = f"{source.get('count', 0)} broker(s)"
    elif name == "kubernetes":
        missing = as_string_list(source.get("missing_deployments")) + as_string_list(source.get("missing_services")) + as_string_list(source.get("missing_endpoints"))
        detail = f"{len(missing)} missing runtime item(s)" if missing else "control-plane resources present"
    elif name == "web_app":
        detail = "deployment, service, and endpoint ready" if status == "healthy" else ", ".join(as_string_list(source.get("missing"))) or "web app readiness degraded"
    else:
        detail = "source available"
    return {
        "name": name,
        "status": status,
        "ok": bool(source.get("ok")),
        "detail": short_text(detail, 180),
        "diagnostic_target": f"/troubleshooting?source={urllib.parse.quote(name)}",
    }


def next_inspection_target(snapshot: dict[str, Any]) -> dict[str, str]:
    sources = snapshot.get("sources") if isinstance(snapshot.get("sources"), dict) else {}
    for name in ("hub", "broker", "mcp", "web_app", "kubernetes", "messages", "notifications"):
        source = sources.get(name) if isinstance(sources.get(name), dict) else {}
        if source and (source.get("ok") is False or source.get("status") not in {"healthy", "ready"}):
            return {
                "kind": "source",
                "label": name,
                "status": str(source.get("status") or "unavailable"),
                "summary": short_text(source.get("error") or f"{name} is {source.get('status') or 'degraded'}", 220),
                "href": f"/troubleshooting?source={urllib.parse.quote(name)}",
            }
    for row in snapshot.get("rounds", []) if isinstance(snapshot.get("rounds"), list) else []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or row.get("visible_status") or "")
        review = str((row.get("final_review") or {}).get("display") or "")
        if status in {"blocked", "failed", "waiting"} or review in {"blocked", "changes requested"}:
            target = "final review" if review else ("validation" if (row.get("mcp") or {}).get("validation_status") else "timeline")
            return {
                "kind": "round",
                "label": str(row.get("round_id") or ""),
                "status": str(row.get("visible_status") or status),
                "summary": short_text(row.get("terminal_summary") or row.get("flow_summary") or row.get("outcome"), 220),
                "href": f"/rounds/{urllib.parse.quote(str(row.get('round_id') or ''))}?focus={urllib.parse.quote(target)}",
            }
    if snapshot.get("stale"):
        return {
            "kind": "live",
            "label": "live freshness",
            "status": "stale",
            "summary": "latest round update is older than the configured freshness threshold",
            "href": "/troubleshooting?source=live",
        }
    return {
        "kind": "overview",
        "label": "control plane",
        "status": str(snapshot.get("readiness") or "unknown"),
        "summary": "no blocked source or round is currently highest priority",
        "href": "/runtime",
    }


def build_operator_view_model(snapshot: dict[str, Any]) -> dict[str, Any]:
    overview = snapshot.get("overview") if isinstance(snapshot.get("overview"), dict) else {}
    sources = snapshot.get("sources") if isinstance(snapshot.get("sources"), dict) else {}
    source_order = ["hub", "broker", "mcp", "web_app", "kubernetes", "messages", "notifications"]
    source_summaries = [
        source_operator_summary(name, sources[name])
        for name in source_order
        if isinstance(sources.get(name), dict)
    ]
    return {
        "readiness": overview.get("readiness") or snapshot.get("readiness") or "unknown",
        "generated_at": snapshot.get("generated_at") or "",
        "latest_update": overview.get("latest_update") or snapshot.get("generated_at") or "",
        "stale": bool(snapshot.get("stale")),
        "counts": {
            "active_or_blocked": overview.get("active_round_count", 0),
            "recent_rounds": overview.get("recent_round_count", 0),
            "agents": overview.get("agent_count", 0),
        },
        "next_inspection": next_inspection_target(snapshot),
        "sources": source_summaries,
        "rounds": snapshot.get("rounds") if isinstance(snapshot.get("rounds"), list) else [],
        "inbox": snapshot.get("inbox") if isinstance(snapshot.get("inbox"), list) else [],
        "markers": NICEGUI_FRONTEND_MARKERS["layout_markers"],
    }


PROVIDER: RuntimeProvider = RuntimeProvider()


NICEGUI_APP_REGISTERED = False


def nicegui_provider() -> RuntimeProvider:
    return PROVIDER


def json_response(payload: dict[str, Any], status_code: int = 200) -> Any:
    from fastapi.responses import JSONResponse

    return JSONResponse(content=json.loads(json.dumps(payload, sort_keys=True, default=str)), status_code=status_code, headers={"Cache-Control": "no-store"})


def status_badge(value: Any) -> Any:
    from nicegui import ui

    label = str(value or "unknown")
    normalized = label.lower().replace("_", " ").replace("-", " ")
    icon = "check_circle" if normalized in {"ready", "healthy", "completed", "accepted", "connected"} else ("error" if normalized in {"blocked", "failed", "unavailable", "changes requested"} else "pending")
    colors = {
        "ready": "bg-green-50 text-green-800 border-green-200",
        "healthy": "bg-green-50 text-green-800 border-green-200",
        "completed": "bg-green-50 text-green-800 border-green-200",
        "accepted": "bg-green-50 text-green-800 border-green-200",
        "connected": "bg-green-50 text-green-800 border-green-200",
        "running": "bg-blue-50 text-blue-800 border-blue-200",
        "waiting": "bg-amber-50 text-amber-900 border-amber-200",
        "degraded": "bg-amber-50 text-amber-900 border-amber-200",
        "stale": "bg-amber-50 text-amber-900 border-amber-200",
        "blocked": "bg-red-50 text-red-800 border-red-200",
        "failed": "bg-red-50 text-red-800 border-red-200",
        "unavailable": "bg-red-50 text-red-800 border-red-200",
        "changes requested": "bg-red-50 text-red-800 border-red-200",
    }
    with ui.element("span").classes(f"inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold {colors.get(normalized, 'bg-gray-50 text-gray-700 border-gray-200')}").props(f'aria-label="status {label}"'):
        ui.icon(icon).classes("text-sm")
        ui.label(label)


def add_shell(active: str) -> None:
    from nicegui import ui

    ui.add_head_html(
        """
        <style>
          body { background:#f6f7f8; color:#202225; }
          .operator-console a:focus, .operator-console button:focus { outline:2px solid #1f5f99; outline-offset:2px; }
          .console-wrap { max-width:1280px; margin:0 auto; padding:16px 18px 32px; }
          .responsive-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }
          .dense-rounds .q-table th, .dense-rounds .q-table td { white-space:normal; vertical-align:top; }
          @media (max-width: 720px) { .console-wrap { padding:10px; } .hide-narrow { display:none; } }
        </style>
        """
    )
    with ui.header().classes("bg-white text-gray-900 border-b border-gray-200 px-4 py-2"):
        with ui.row().classes("w-full items-center justify-between gap-3"):
            ui.label("scion-ops hub").classes("text-lg font-semibold")
            with ui.tabs(value=active).classes("text-gray-800") as tabs:
                for name, href in (("overview", "/"), ("rounds", "/rounds"), ("inbox", "/inbox"), ("runtime", "/runtime"), ("troubleshooting", "/troubleshooting")):
                    ui.tab(name, label=name.title()).on("click", lambda _=None, target=href: ui.navigate.to(target))
    ui.query(".nicegui-content").classes("operator-console")


def summary_panel(label: str, value: Any, caption: str = "") -> None:
    from nicegui import ui

    with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3"):
        ui.label(str(value)).classes("text-xl font-semibold")
        ui.label(label).classes("text-sm text-gray-600")
        if caption:
            ui.label(caption).classes("text-xs text-gray-500")


def render_overview(snapshot: dict[str, Any]) -> None:
    from nicegui import ui

    model = build_operator_view_model(snapshot)
    add_shell("overview")
    with ui.element("main").classes("console-wrap"):
        with ui.row().classes("items-center justify-between w-full gap-2"):
            with ui.column().classes("gap-1"):
                ui.label("Overview").classes("text-xl font-semibold")
                ui.label(f"Generated {model['generated_at']}").classes("text-xs text-gray-500")
            status_badge(model["readiness"])
        with ui.element("section").classes("responsive-grid mt-3"):
            summary_panel("Active or blocked", model["counts"]["active_or_blocked"])
            summary_panel("Recent rounds", model["counts"]["recent_rounds"])
            summary_panel("Hub agents", model["counts"]["agents"])
            summary_panel("Latest update", model["latest_update"], "live freshness" if not model["stale"] else "stale")
        target = model["next_inspection"]
        with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3 mt-3"):
            with ui.row().classes("items-center justify-between gap-2"):
                with ui.column().classes("gap-1"):
                    ui.label("Next inspection").classes("font-semibold")
                    ui.label(f"{target['label']} - {target['summary']}").classes("text-sm text-gray-700")
                status_badge(target["status"])
                ui.link("Open", target["href"]).classes("px-3 py-2 rounded-md border border-gray-300 text-sm")
        ui.label("Runtime checks").classes("font-semibold mt-4")
        with ui.element("section").classes("responsive-grid mt-2"):
            for source in model["sources"]:
                with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(source["name"]).classes("font-semibold")
                        status_badge(source["status"])
                    ui.label(source["detail"]).classes("text-sm text-gray-600")
                    ui.link("Troubleshoot", source["diagnostic_target"]).classes("text-sm")


def render_rounds(snapshot: dict[str, Any]) -> None:
    from nicegui import ui

    add_shell("rounds")
    rows = snapshot.get("rounds") if isinstance(snapshot.get("rounds"), list) else []
    with ui.element("main").classes("console-wrap dense-rounds"):
        ui.label("Rounds").classes("text-xl font-semibold")
        if not rows:
            with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3 mt-3").props("data-empty-rounds"):
                ui.label("No rounds found").classes("font-semibold text-gray-700")
                ui.label("Hub returned no round-identifiable agents, messages, or notifications.").classes("text-sm text-gray-600")
            return
        for row in rows:
            with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3 mt-3"):
                with ui.row().classes("items-start justify-between w-full gap-3"):
                    with ui.column().classes("gap-1 min-w-0"):
                        ui.link(str(row.get("round_id") or ""), f"/rounds/{row.get('round_id') or ''}").classes("font-mono font-semibold break-all")
                        ui.label(short_text(row.get("terminal_summary") or row.get("flow_summary") or row.get("outcome"), 240)).classes("text-sm text-gray-700")
                    status_badge(row.get("visible_status") or row.get("status"))
                with ui.row().classes("gap-2 mt-2 flex-wrap text-xs text-gray-600"):
                    ui.label(f"phase {row.get('phase') or 'unknown'}")
                    ui.label(f"latest {row.get('latest_update') or 'unknown'}")
                    ui.label(f"validation {(row.get('mcp') or {}).get('validation_status') or 'unknown'}")
                    ui.label(f"final review {(row.get('final_review') or {}).get('display') or 'none'}")
                blockers = (row.get("mcp") or {}).get("blockers") or []
                if blockers:
                    ui.label("; ".join(blockers)).classes("text-sm text-red-800 bg-red-50 border border-red-200 rounded-md p-2 mt-2")
                branches = row.get("branches") or []
                if branches:
                    ui.label("Branches").classes("text-xs font-semibold text-gray-600 mt-2")
                    for branch in branches[:4]:
                        ui.label(branch).classes("font-mono text-xs break-all")


def render_round_detail(round_id: str, detail: dict[str, Any]) -> None:
    from nicegui import ui

    add_shell("rounds")
    with ui.element("main").classes("console-wrap"):
        with ui.row().classes("items-center justify-between w-full gap-2"):
            ui.link("Back to rounds", "/rounds").classes("px-3 py-2 rounded-md border border-gray-300 text-sm")
            status_badge(detail.get("visible_status") or (detail.get("status") or {}).get("status"))
        ui.label(round_id).classes("font-mono text-xl font-semibold break-all mt-3")
        ui.label(detail.get("terminal_summary") or "").classes("text-sm text-gray-700")
        with ui.tabs(value="flow").classes("mt-4") as tabs:
            for name in ("flow", "timeline", "agents", "validation", "branches", "diagnostics"):
                ui.tab(name, label=name.title())
        with ui.tab_panels(tabs, value="flow").classes("w-full bg-transparent"):
            with ui.tab_panel("flow"):
                for stage in detail.get("decision_flow", []):
                    with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3 mb-2"):
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(stage.get("role") or "observed").classes("font-semibold")
                            status_badge(stage.get("status") or "observed")
                        ui.label(stage.get("summary") or "").classes("text-sm text-gray-700")
                        ui.label(f"{stage.get('agent_name') or ''} {stage.get('harness_config') or ''}").classes("text-xs text-gray-500")
            with ui.tab_panel("timeline"):
                for item in detail.get("timeline", []):
                    with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3 mb-2"):
                        status_badge(item.get("type"))
                        ui.label(item.get("time") or "").classes("text-xs text-gray-500")
                        ui.label(item.get("summary") or "").classes("text-sm")
            with ui.tab_panel("agents"):
                for agent in (detail.get("status") or {}).get("agents", []):
                    with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3 mb-2"):
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(agent.get("name") or agent.get("slug") or "").classes("font-mono text-sm break-all")
                            status_badge(agent.get("status") or agent.get("phase"))
                        ui.label(f"{agent.get('role') or ''} {agent.get('template') or ''} {agent.get('harness_config') or ''}").classes("text-xs text-gray-500")
                        ui.label(agent.get("taskSummary") or agent.get("activity") or "").classes("text-sm")
            with ui.tab_panel("validation"):
                mcp = detail.get("mcp") or {}
                status_badge(mcp.get("validation_status") or "unknown")
                ui.json_editor({"content": {"json": mcp.get("validation") or {}}}).classes("w-full")
            with ui.tab_panel("branches"):
                for branch in detail.get("branches", []):
                    ui.label(branch).classes("font-mono text-xs break-all")
                ui.json_editor({"content": {"json": detail.get("artifacts") or {}}}).classes("w-full mt-2")
            with ui.tab_panel("diagnostics"):
                ui.label("Troubleshooting").classes("font-semibold")
                ui.json_editor({"content": {"json": detail}}).classes("w-full troubleshooting-panel")


def render_inbox(snapshot: dict[str, Any]) -> None:
    from nicegui import ui

    add_shell("inbox")
    with ui.element("main").classes("console-wrap"):
        ui.label("Inbox").classes("text-xl font-semibold")
        groups = snapshot.get("inbox") if isinstance(snapshot.get("inbox"), list) else []
        if not groups:
            ui.label("No inbox updates").classes("text-gray-600 mt-3")
        for group in groups:
            with ui.card().classes("rounded-md shadow-none border border-gray-200 p-3 mt-3"):
                ui.label(group.get("round_id") or "ungrouped").classes("font-mono font-semibold break-all")
                for item in group.get("items", []):
                    with ui.row().classes("items-start gap-2 w-full border-t border-gray-100 pt-2 mt-2"):
                        status_badge(item.get("type"))
                        with ui.column().classes("gap-1 min-w-0"):
                            ui.label(item.get("time") or "").classes("text-xs text-gray-500")
                            ui.label(item.get("summary") or "").classes("text-sm")


def render_runtime(snapshot: dict[str, Any], *, troubleshooting: bool = False, selected_source: str = "") -> None:
    from nicegui import ui

    add_shell("troubleshooting" if troubleshooting else "runtime")
    sources = snapshot.get("sources") if isinstance(snapshot.get("sources"), dict) else {}
    with ui.element("main").classes("console-wrap"):
        ui.label("Troubleshooting" if troubleshooting else "Runtime").classes("text-xl font-semibold")
        ui.label("Raw diagnostics are grouped one level below the overview. The interface is read-only.").classes("text-sm text-gray-600")
        for name, source in sources.items():
            if selected_source and selected_source != name and not troubleshooting:
                continue
            with ui.expansion(name, icon="manage_search", value=(name == selected_source or not troubleshooting)).classes("w-full mt-3 border border-gray-200 rounded-md bg-white"):
                with ui.row().classes("items-center gap-2"):
                    status_badge(source.get("status"))
                    if source.get("error"):
                        ui.label(f"{source.get('error_kind')}: {source.get('error')}").classes("text-sm text-red-800")
                if troubleshooting:
                    ui.json_editor({"content": {"json": source}}).classes("w-full troubleshooting-panel")


def register_nicegui_app() -> None:
    global NICEGUI_APP_REGISTERED
    if NICEGUI_APP_REGISTERED:
        return
    NICEGUI_APP_REGISTERED = True
    from fastapi import Request
    from fastapi.responses import StreamingResponse
    from nicegui import app, ui

    @app.get("/healthz")
    def healthz() -> Any:
        return json_response(build_health())

    @app.get("/api/healthz")
    def api_healthz() -> Any:
        return json_response(build_health())

    @app.get("/api/snapshot")
    def api_snapshot() -> Any:
        return json_response(build_snapshot(nicegui_provider()))

    @app.get("/api/contract")
    def api_contract() -> Any:
        return json_response({"ok": True, "contract": BROWSER_JSON_CONTRACT})

    @app.get("/api/overview")
    def api_overview() -> Any:
        return json_response(build_snapshot(nicegui_provider())["overview"])

    @app.get("/api/rounds")
    def api_rounds() -> Any:
        return json_response({"rounds": build_snapshot(nicegui_provider())["rounds"]})

    @app.get("/api/rounds/{round_id}/events")
    def api_round_events(round_id: str, cursor: str = "") -> Any:
        return json_response(nicegui_provider().round_events(round_id, cursor=cursor, include_existing=False))

    @app.get("/api/rounds/{round_id}")
    def api_round(round_id: str) -> Any:
        return json_response(build_round_detail(nicegui_provider(), round_id))

    @app.get("/api/inbox")
    def api_inbox() -> Any:
        return json_response({"inbox": build_snapshot(nicegui_provider())["inbox"]})

    @app.get("/api/runtime")
    def api_runtime() -> Any:
        return json_response({"sources": build_snapshot(nicegui_provider())["sources"]})

    @app.get("/api/live")
    @app.get("/api/stream")
    def api_live(request: Request, cursor: str = "", round_id: str = "", seconds: int = 30, format: str = "") -> Any:
        accepts_sse = "text/event-stream" in request.headers.get("accept", "") or format == "sse"
        if not accepts_sse:
            return json_response(build_live_update_batch(nicegui_provider(), cursor=cursor or request.headers.get("last-event-id", ""), round_id=round_id))

        def frames() -> Any:
            deadline = time.monotonic() + max(1, min(seconds, 60))
            current_cursor = cursor or request.headers.get("last-event-id", "")
            while time.monotonic() <= deadline:
                batch = build_live_update_batch(nicegui_provider(), cursor=current_cursor, round_id=round_id)
                current_cursor = batch["cursor"]
                for event in batch["events"]:
                    data = json.dumps(event, sort_keys=True, default=str)
                    yield f"id: {event.get('cursor') or event.get('id') or ''}\nevent: {event.get('type') or 'message'}\ndata: {data}\n\n"
                if batch["events"] and any(event.get("type") != "heartbeat" for event in batch["events"]):
                    continue
                time.sleep(15)

        return StreamingResponse(frames(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "Connection": "keep-alive"})

    @ui.page("/")
    def page_overview() -> None:
        render_overview(build_snapshot(nicegui_provider()))

    @ui.page("/rounds")
    def page_rounds() -> None:
        render_rounds(build_snapshot(nicegui_provider()))

    @ui.page("/rounds/{round_id}")
    def page_round_detail(round_id: str) -> None:
        render_round_detail(round_id, build_round_detail(nicegui_provider(), round_id))

    @ui.page("/inbox")
    def page_inbox() -> None:
        render_inbox(build_snapshot(nicegui_provider()))

    @ui.page("/runtime")
    def page_runtime() -> None:
        render_runtime(build_snapshot(nicegui_provider()))

    @ui.page("/troubleshooting")
    def page_troubleshooting(source: str = "") -> None:
        render_runtime(build_snapshot(nicegui_provider()), troubleshooting=True, selected_source=source)


def serve(host: str, port: int) -> None:
    register_nicegui_app()
    from nicegui import ui

    print(f"scion-ops NiceGUI web app hub listening on http://{host}:{port}")
    ui.run(host=host, port=port, title="scion-ops hub", reload=False, show=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only scion-ops web app hub.")
    parser.add_argument("--host", default=os.environ.get("SCION_OPS_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SCION_OPS_WEB_PORT", "8787")))
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
