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
CONTROL_PLANE_SERVICES = CONTROL_PLANE_NAMES
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
            stderr=subprocess.STDOUT,
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
        payload["error"] = result.stdout.strip() or f"command exited {result.returncode}"
        payload["error_kind"] = classify_command_failure(args, result.stdout)
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


def source_stale(latest: str, now: datetime | None = None) -> bool:
    parsed = parse_time(latest)
    if not parsed:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - parsed).total_seconds() > STALE_AFTER_SECONDS


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
        return scion_ops.scion_ops_round_status(round_id=round_id, include_transcript=True, num_lines=120)

    def round_events(self, round_id: str, cursor: str = "", include_existing: bool = False) -> dict[str, Any]:
        return scion_ops.scion_ops_round_events(round_id=round_id, cursor=cursor, include_existing=include_existing)

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
                "_structured_branches": [],
                "_fallback_branches": [],
            },
        )

    for agent in agents:
        round_id = extract_round_id(agent.get("name"), agent.get("slug"), agent.get("taskSummary"))
        if not round_id:
            continue
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
                outcome = status_data.get("outcome") or {}
                outcome_review = final_review_from_outcome(outcome)
                if outcome_review:
                    existing_time = str(row.get("final_review", {}).get("time") or "")
                    outcome_time = str(outcome_review.get("time") or "")
                    if not row["final_review"] or outcome_time >= existing_time:
                        row["final_review"] = outcome_review
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
        summaries = [str(agent.get("taskSummary") or "") for agent in row["agents"] if agent.get("taskSummary")]
        terminal = next((summary for summary in summaries if "complete:" in summary.lower() or "blocked" in summary.lower()), "")
        row["outcome"] = row["final_review"].get("summary") or short_text(terminal)
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
    detail_agents = status.get("agents", []) if isinstance(status.get("agents"), list) else []
    for agent in detail_agents:
        for branch in structured_branch_refs(agent):
            add_unique(structured_branches, branch)
        for branch in fallback_branch_refs(agent.get("taskSummary")):
            add_unique(fallback_branches, branch)
    outcome = status.get("outcome") or events.get("outcome") or {}
    for branch in structured_branch_refs(outcome):
        add_unique(structured_branches, branch)
    outcome_review = final_review_from_outcome(outcome)
    if outcome_review:
        final_reviews.append(outcome_review)
    if events.get("ok"):
        for event in events.get("events", []):
            item = event.get("message") or event.get("notification") or event.get("agent") or {}
            payload = parse_json_object(item.get("msg") or item.get("message") or item.get("summary"))
            for branch in structured_branch_refs(item):
                add_unique(structured_branches, branch)
            for branch in structured_branch_refs(payload):
                add_unique(structured_branches, branch)
            for branch in fallback_branch_refs(item.get("msg"), item.get("message"), item.get("summary"), item.get("taskSummary")):
                add_unique(fallback_branches, branch)
            if event.get("message") or event.get("notification"):
                review = final_review_from_item(item, source=str(event.get("type") or "event"))
                if review:
                    final_reviews.append(review)
            timeline.append({
                "type": event.get("type") or "event",
                "time": event_time(item),
                "summary": short_text(item.get("msg") or item.get("message") or item.get("summary") or item.get("taskSummary") or item.get("activity"), 360),
                "raw": item,
            })
    transcript = status.get("consensus_transcript") if isinstance(status.get("consensus_transcript"), dict) else {}
    final_reviews.sort(key=lambda item: item.get("time") or "")
    branches = structured_branches if structured_branches else fallback_branches
    final_review = final_reviews[-1] if final_reviews else {}
    visible_status = str(final_review.get("display") or status.get("status") or "unknown")
    return {
        "ok": bool(status.get("ok")) or bool(events.get("ok")),
        "round_id": round_id,
        "status": status,
        "events": events,
        "timeline": sorted(timeline, key=lambda item: item.get("time") or ""),
        "runner_output": transcript.get("output", "") if transcript.get("ok") else "",
        "runner_output_error": "" if transcript.get("ok") or not transcript else transcript.get("error") or transcript.get("output", ""),
        "outcome": outcome,
        "final_review": final_review,
        "visible_status": visible_status,
        "branches": branches,
        "branch_source": "structured" if structured_branches else ("fallback" if branches else ""),
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
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
    .card, .table-wrap, .detail { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; }
    .status { display:inline-flex; align-items:center; gap:6px; font-weight:650; text-transform:capitalize; }
    .dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; }
    .ready .dot, .healthy .dot, .completed .dot, .accepted .dot { background:var(--good); }
    .degraded .dot, .waiting .dot, .stale .dot, .observed .dot { background:var(--warn); }
    .unavailable .dot, .blocked .dot, .error .dot, .changes-requested .dot { background:var(--bad); }
    .running .dot { background:var(--info); }
    .muted { color:var(--muted); }
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
    <div class="bar"><div id="refresh-state">Loading...</div><button id="refresh">Refresh</button></div>
    <section id="overview"></section>
    <section id="rounds" class="hidden"></section>
    <section id="round-detail" class="hidden"></section>
    <section id="inbox" class="hidden"></section>
    <section id="runtime" class="hidden"></section>
  </main>
  <script>
    const state = { view: "overview", snapshot: null, selectedRound: "", cursors: {} };
    const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
    const status = value => {
      const label = String(value || "unknown");
      const cls = label.toLowerCase().replace(/[\s_]+/g, "-");
      return `<span class="status ${esc(cls)}"><span class="dot"></span>${esc(label)}</span>`;
    };
    const fmt = value => value ? new Date(value).toLocaleString() : "unknown";
    async function getJson(url) {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return await response.json();
    }
    async function refresh() {
      document.getElementById("refresh-state").textContent = "Loading...";
      try {
        state.snapshot = await getJson("/api/snapshot");
        render();
        document.getElementById("refresh-state").textContent = `Last refresh ${fmt(state.snapshot.generated_at)}${state.snapshot.stale ? " - stale data" : ""}`;
      } catch (err) {
        document.getElementById("refresh-state").innerHTML = `<span class="error-box">Snapshot unavailable: ${esc(err.message)}</span>`;
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
      document.getElementById("rounds").innerHTML = rows.length ? `
        <div class="table-wrap"><table><thead><tr><th>Round</th><th>Status</th><th>Phase</th><th>Agents</th><th>Latest update</th><th>Outcome</th><th>Branches</th></tr></thead><tbody>
        ${rows.map(row => `<tr data-round="${esc(row.round_id)}"><td class="mono">${esc(row.round_id)}</td><td>${status(row.visible_status || row.status)}</td><td>${esc(row.phase)}</td><td>${row.agent_count}</td><td>${fmt(row.latest_update)}<div class="muted">${esc(row.latest_summary)}</div></td><td>${esc(row.outcome || "")}</td><td>${(row.branches || []).map(branch => `<div class="mono">${esc(branch)}</div>`).join("")}${row.branch_source ? `<div class="muted">${esc(row.branch_source)}</div>` : ""}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="card"><strong>No rounds found</strong><div class="muted">Hub returned no round-identifiable agents, messages, or notifications.</div></div>`;
      document.querySelectorAll("[data-round]").forEach(row => row.onclick = () => openRound(row.dataset.round));
    }
    async function openRound(roundId) {
      state.selectedRound = roundId;
      setView("round-detail");
      document.getElementById("round-detail").innerHTML = `<div class="card">Loading ${esc(roundId)}...</div>`;
      const detail = await getJson(`/api/rounds/${encodeURIComponent(roundId)}`);
      const agents = detail.status.agents || [];
      const review = detail.final_review || {};
      document.getElementById("round-detail").innerHTML = `
        <div class="bar"><button id="back-rounds">Back to rounds</button><button id="refresh-round">Refresh timeline</button></div>
        <div class="split">
          <div class="detail"><h2 class="mono">${esc(roundId)}</h2><div>${status(detail.visible_status || detail.status.status || "unknown")}</div><h3>Timeline</h3><div class="timeline">${detail.timeline.length ? detail.timeline.map(item => `<div class="item"><div>${status(item.type)}</div><div class="muted">${fmt(item.time)}</div><div>${esc(item.summary)}</div></div>`).join("") : `<div class="muted">No messages or notifications for this round.</div>`}</div></div>
          <div class="detail"><h3>Final Review</h3>${review.display ? `<div>${status(review.display)}</div><div class="muted">${esc(review.source || "")}${review.summary ? ` - ${esc(review.summary)}` : ""}</div>` : `<div class="muted">No final review available.</div>`}<h3>Branches</h3>${detail.branches?.length ? detail.branches.map(branch => `<div class="mono">${esc(branch)}</div>`).join("") + (detail.branch_source ? `<div class="muted">${esc(detail.branch_source)}</div>` : "") : `<div class="muted">No branch references available.</div>`}<h3>Agents</h3>${agents.length ? agents.map(agent => `<div class="card"><strong>${esc(agent.name || agent.slug)}</strong><div>${status(agent.phase || "unknown")}</div><div class="muted">${esc(agent.taskSummary || agent.activity || "")}</div></div>`).join("") : `<div class="muted">No agents found.</div>`}<h3>Runner Output</h3>${detail.runner_output ? `<pre class="mono">${esc(detail.runner_output)}</pre>` : `<div class="muted">${esc(detail.runner_output_error || "No runner output available.")}</div>`}</div>
        </div>`;
      document.getElementById("back-rounds").onclick = () => setView("rounds");
      document.getElementById("refresh-round").onclick = () => openRound(roundId);
    }
    function renderInbox() {
      const groups = state.snapshot.inbox;
      document.getElementById("inbox").innerHTML = groups.length ? groups.map(group => `
        <div class="detail"><h2>${esc(group.round_id)}</h2>${group.items.map(item => `<div class="timeline item"><div>${status(item.type)}</div><div class="muted">${fmt(item.time)} ${esc(item.source_id)}</div><div>${esc(item.summary)}</div></div>`).join("")}</div>`).join("") : `<div class="card"><strong>No inbox updates</strong><div class="muted">Hub returned no messages or notifications.</div></div>`;
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
      if (state.view !== "round-detail") {
        document.querySelectorAll("main > section").forEach(el => el.classList.add("hidden"));
        document.getElementById(state.view).classList.remove("hidden");
      }
    }
    document.querySelectorAll("nav button").forEach(btn => btn.onclick = () => setView(btn.dataset.view));
    document.getElementById("refresh").onclick = refresh;
    refresh();
    setInterval(refresh, 15000);
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
            elif path == "/api/snapshot":
                self.respond_json(build_snapshot(self.provider))
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
