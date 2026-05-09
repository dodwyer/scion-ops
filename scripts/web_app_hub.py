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
WEB_APP_NAME = "scion-ops-web-app"
CONTROL_PLANE_NAMES = {"scion-hub", "scion-broker", "scion-ops-mcp", WEB_APP_NAME}
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
SPEC_ROUND_FIELDS = {
    "base_branch",
    "base_branch_sha",
    "blockers",
    "branch_changed",
    "change",
    "cursor",
    "done",
    "expected_branch",
    "health",
    "latest_event_summaries",
    "pr_ready_branch",
    "progress_lines",
    "project_root",
    "protocol",
    "remote_branch_sha",
    "status",
    "validation",
    "validation_status",
    "warnings",
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


def first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return ""


def merge_unique(existing: list[Any], incoming: Any) -> list[Any]:
    values = list(existing)
    if not isinstance(incoming, list):
        return values
    for item in incoming:
        if item not in values:
            values.append(item)
    return values


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
    final_review = data.get("final_review") if isinstance(data.get("final_review"), dict) else {}
    review_data = final_review or data
    verdict = (
        review_data.get("verdict")
        or review_data.get("normalized_verdict")
        or review_data.get("finalReviewVerdict")
        or review_data.get("final_review_verdict")
        or review_data.get("status")
    )
    if not verdict:
        summary = str(item.get("summary") or item.get("msg") or item.get("message") or "")
        match = re.search(r"\b(accept(?:ed)?|approved|request_changes|changes_requested|revise|blocked)\b", summary, re.IGNORECASE)
        if ("final" in summary.lower() or "review" in summary.lower() or "outcome" in summary.lower()) and match:
            verdict = match.group(1)
    normalized = normalize_final_verdict(verdict)
    if normalized not in {"accept", "request_changes", "blocked"}:
        return {}
    summary = short_text(
        review_data.get("summary")
        or review_data.get("notes")
        or review_data.get("source_summary")
        or item.get("summary")
        or item.get("msg")
        or item.get("message"),
        260,
    )
    blocking_issues = first_value(review_data.get("blocking_issues"), review_data.get("blockingIssues"))
    return {
        "source": source,
        "time": event_time(item),
        "verdict": str(review_data.get("verdict") or verdict or ""),
        "normalized_verdict": normalized,
        "status": "accepted" if normalized == "accept" else "blocked",
        "display": final_review_label(normalized),
        "summary": summary,
        "branch": next(iter(structured_branch_refs(review_data) or structured_branch_refs(data)), ""),
        "blocking_issues": blocking_issues if isinstance(blocking_issues, list) else [],
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
    summary = short_text(data.get("summary") or data.get("notes") or data.get("source_summary") or data.get("test_results") or outcome.get("source"), 260)
    blocking_issues = first_value(data.get("blocking_issues"), data.get("blockingIssues"))
    return {
        "source": data.get("source") or outcome.get("source") or "outcome",
        "time": data.get("created") or data.get("time") or "",
        "verdict": str(data.get("verdict") or verdict or ""),
        "normalized_verdict": normalized,
        "status": "accepted" if normalized == "accept" else "blocked",
        "display": final_review_label(normalized),
        "summary": summary,
        "branch": next(iter(structured_branch_refs(data)), ""),
        "blocking_issues": blocking_issues if isinstance(blocking_issues, list) else [],
    }


def validation_errors(validation: Any) -> list[str]:
    if not isinstance(validation, dict):
        return []
    errors: list[str] = []
    for key in ("errors", "issues", "diagnostics"):
        items = validation.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str):
                errors.append(short_text(item, 220))
            elif isinstance(item, dict):
                errors.append(short_text(item.get("message") or item.get("error") or item.get("summary") or json.dumps(item, sort_keys=True), 220))
    return errors


def normalize_artifacts(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    remote = payload.get("remote_branches") if isinstance(payload.get("remote_branches"), list) else []
    local = payload.get("branches") if isinstance(payload.get("branches"), list) else []
    return {
        "source": payload.get("source") or "",
        "project_root": payload.get("project_root") or "",
        "branches": [normalize_branch(item) for item in local if normalize_branch(item)],
        "remote_branches": [
            {"branch": normalize_branch(item.get("branch")), "sha": str(item.get("sha") or "")}
            for item in remote
            if isinstance(item, dict) and normalize_branch(item.get("branch"))
        ],
        "workspaces": payload.get("workspaces") if isinstance(payload.get("workspaces"), list) else [],
        "prompts": payload.get("prompts") if isinstance(payload.get("prompts"), list) else [],
    }


def normalize_validation(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else payload
    result = payload.get("validation_result") if isinstance(payload.get("validation_result"), dict) else {}
    status = first_value(
        payload.get("validation_status"),
        "passed" if validation.get("ok") is True else ("failed" if validation.get("ok") is False else ""),
    )
    return {
        "source": payload.get("source") or validation.get("source") or "",
        "status": str(status or ""),
        "ok": validation.get("ok"),
        "validator": validation.get("validator") or "",
        "change": payload.get("change") or validation.get("change") or "",
        "project_root": payload.get("project_root") or "",
        "errors": validation_errors(validation),
        "validation": validation,
        "validation_result": result,
        "openspec_status": payload.get("openspec_status") if isinstance(payload.get("openspec_status"), dict) else {},
    }


def normalize_spec_round_payload(payload: Any, *, source: str = "") -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if not (payload.get("source") == "spec_round_runner" or payload.get("tool") == "scion_ops_run_spec_round" or any(key in payload for key in SPEC_ROUND_FIELDS)):
        return {}
    validation = normalize_validation(payload)
    artifacts = normalize_artifacts(payload.get("artifacts"))
    protocol = payload.get("protocol") if isinstance(payload.get("protocol"), dict) else {}
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    return {
        "source": source or payload.get("source") or payload.get("tool") or "structured",
        "status": str(payload.get("status") or ""),
        "health": str(payload.get("health") or ""),
        "done": payload.get("done"),
        "change": str(payload.get("change") or ""),
        "project_root": str(payload.get("project_root") or ""),
        "base_branch": str(payload.get("base_branch") or ""),
        "expected_branch": normalize_branch(payload.get("expected_branch")),
        "pr_ready_branch": normalize_branch(payload.get("pr_ready_branch")),
        "remote_branch_sha": str(payload.get("remote_branch_sha") or ""),
        "base_branch_sha": str(payload.get("base_branch_sha") or ""),
        "branch_changed": payload.get("branch_changed"),
        "validation_status": str(first_value(payload.get("validation_status"), validation.get("status")) or ""),
        "validation": validation,
        "protocol": protocol,
        "blockers": [short_text(item, 220) for item in blockers],
        "warnings": [short_text(item, 220) for item in warnings],
        "progress_lines": payload.get("progress_lines") if isinstance(payload.get("progress_lines"), list) else [],
        "latest_event_summaries": payload.get("latest_event_summaries") if isinstance(payload.get("latest_event_summaries"), list) else [],
        "cursor": str(payload.get("cursor") or ""),
        "artifacts": artifacts,
    }


def payload_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [item]
    parsed = parse_json_object(item.get("msg") or item.get("message") or item.get("summary"))
    if parsed:
        candidates.append(parsed)
    for key in ("payload", "data", "result"):
        value = item.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    return candidates


def merge_spec_info(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if not incoming:
        return base
    merged = dict(base)
    for key in ("source", "status", "health", "change", "project_root", "base_branch", "expected_branch", "pr_ready_branch", "remote_branch_sha", "base_branch_sha", "validation_status", "cursor"):
        if incoming.get(key) not in (None, "", [], {}):
            merged[key] = incoming[key]
    for key in ("done", "branch_changed"):
        if incoming.get(key) is not None:
            merged[key] = incoming[key]
    for key in ("blockers", "warnings", "progress_lines", "latest_event_summaries"):
        merged[key] = merge_unique(merged.get(key, []), incoming.get(key))
    if incoming.get("protocol"):
        merged["protocol"] = {**merged.get("protocol", {}), **incoming["protocol"]}
    if incoming.get("validation"):
        merged["validation"] = {**merged.get("validation", {}), **incoming["validation"]}
    if incoming.get("artifacts"):
        merged["artifacts"] = {**merged.get("artifacts", {}), **incoming["artifacts"]}
    return merged


def spec_info_from_item(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    info: dict[str, Any] = {}
    for payload in payload_candidates(item):
        info = merge_spec_info(info, normalize_spec_round_payload(payload, source=source))
        if payload.get("source") in {"openspec_validator", "local_git"} and ("validation" in payload or "openspec_status" in payload):
            info = merge_spec_info(info, {"source": source, "validation": normalize_validation(payload), "validation_status": normalize_validation(payload).get("status", "")})
        if "artifacts" not in info and ("remote_branches" in payload or "branches" in payload):
            artifacts = normalize_artifacts(payload)
            if artifacts:
                info = merge_spec_info(info, {"source": source, "artifacts": artifacts})
    return info


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

    def round_artifacts(self, round_id: str, project_root: str = "") -> dict[str, Any]:
        return scion_ops.scion_ops_round_artifacts(round_id=round_id, project_root=project_root)

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
            "deploy,pod,svc,pvc,endpoints",
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
            ready_addresses = sum(len(subset.get("addresses") or []) for subset in subsets if isinstance(subset, dict))
            not_ready_addresses = sum(len(subset.get("notReadyAddresses") or []) for subset in subsets if isinstance(subset, dict))
            endpoints.append({
                "name": name,
                "ready_addresses": ready_addresses,
                "not_ready_addresses": not_ready_addresses,
                "ready": ready_addresses > 0,
            })
        elif kind == "PersistentVolumeClaim":
            pvcs.append({"name": name, "phase": item.get("status", {}).get("phase") or ""})
    missing = sorted(CONTROL_PLANE_NAMES - {item["name"] for item in deployments})
    bad_deployments = [item for item in deployments if not item["ready"]]
    bad_pods = [item for item in pods if not item["ready"] and item["phase"] not in {"Succeeded", "Completed"}]
    missing_services = sorted({WEB_APP_NAME} - {item["name"] for item in services})
    missing_endpoints = sorted({WEB_APP_NAME} - {item["name"] for item in endpoints})
    bad_endpoints = [item for item in endpoints if item["name"] == WEB_APP_NAME and not item["ready"]]
    status = "healthy" if not missing and not bad_deployments and not bad_pods and not missing_services and not missing_endpoints and not bad_endpoints else "degraded"
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
        degraded_endpoints=bad_endpoints,
    )


def web_app_health(kubernetes: dict[str, Any]) -> dict[str, Any]:
    if kubernetes.get("status") == "unavailable" or (kubernetes.get("error") and "deployments" not in kubernetes):
        return {
            "source": "web_app",
            "ok": False,
            "status": "unavailable",
            "error_kind": str(kubernetes.get("error_kind") or "runtime"),
            "error": str(kubernetes.get("error") or "Kubernetes status unavailable"),
            "kubernetes_status": kubernetes.get("status", "unavailable"),
        }
    deployments = [item for item in kubernetes.get("deployments", []) if isinstance(item, dict)]
    services = [item for item in kubernetes.get("services", []) if isinstance(item, dict)]
    pods = [item for item in kubernetes.get("pods", []) if isinstance(item, dict)]
    endpoints = [item for item in kubernetes.get("endpoints", []) if isinstance(item, dict)]
    deployment = next((item for item in deployments if item.get("name") == WEB_APP_NAME), {})
    service = next((item for item in services if item.get("name") == WEB_APP_NAME), {})
    web_pods = [item for item in pods if str(item.get("name") or "") == WEB_APP_NAME or str(item.get("name") or "").startswith(f"{WEB_APP_NAME}-")]
    endpoint = next((item for item in endpoints if item.get("name") == WEB_APP_NAME), {})
    missing: list[str] = []
    degraded: list[str] = []
    if not deployment:
        missing.append("deployment")
    elif not deployment.get("ready"):
        degraded.append("deployment")
    if not service:
        missing.append("service")
    if not web_pods:
        missing.append("pod")
    elif not any(item.get("ready") for item in web_pods):
        degraded.append("pod")
    if not endpoint:
        missing.append("endpoint")
    elif not endpoint.get("ready"):
        degraded.append("endpoint")
    status = "healthy" if not missing and not degraded else "degraded"
    return ok_source(
        "web_app",
        status,
        app_name=WEB_APP_NAME,
        deployment=deployment,
        service=service,
        pods=web_pods,
        endpoint=endpoint,
        missing=missing,
        degraded=degraded,
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
                "spec_round": {},
                "artifacts": {},
                "validation": {},
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
            row["spec_round"] = merge_spec_info(row["spec_round"], spec_info_from_item(item, source=collection_name[:-1]))
            for payload in payload_candidates(item):
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
                row["spec_round"] = merge_spec_info(row["spec_round"], normalize_spec_round_payload(status_data, source="round_status"))
                row["spec_round"] = merge_spec_info(row["spec_round"], normalize_spec_round_payload(outcome, source="round_status.outcome"))
                outcome_review = final_review_from_outcome(outcome)
                if outcome_review:
                    existing_time = str(row.get("final_review", {}).get("time") or "")
                    outcome_time = str(outcome_review.get("time") or "")
                    if not row["final_review"] or outcome_time >= existing_time:
                        row["final_review"] = outcome_review
                if hasattr(provider, "round_artifacts"):
                    artifacts = normalize_artifacts(provider.round_artifacts(round_id, project_root=row["spec_round"].get("project_root", "")))
                    if artifacts:
                        row["artifacts"] = artifacts
                        row["spec_round"] = merge_spec_info(row["spec_round"], {"artifacts": artifacts})
                        for branch in artifacts.get("branches", []):
                            add_unique(row["_structured_branches"], branch)
                        for remote in artifacts.get("remote_branches", []):
                            add_unique(row["_structured_branches"], remote.get("branch"))
                project_root = row["spec_round"].get("project_root", "")
                change = row["spec_round"].get("change", "")
                if project_root and change and hasattr(provider, "spec_status"):
                    validation = normalize_validation(provider.spec_status(project_root, change))
                    if validation:
                        row["validation"] = validation
                        row["spec_round"] = merge_spec_info(row["spec_round"], {"validation": validation, "validation_status": validation.get("status", "")})
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
        spec_status = str(row.get("spec_round", {}).get("status") or "")
        if spec_status in {"blocked", "timed_out", "failed"} or row.get("spec_round", {}).get("blockers"):
            row["status"] = "blocked"
        elif spec_status in {"running_degraded"} and row["status"] not in {"blocked"}:
            row["status"] = "running"
        elif spec_status in {"completed"} and row["status"] in {"unknown", "observed"}:
            row["status"] = "completed"
        if row["final_review"]:
            if row["final_review"].get("status") == "blocked":
                row["status"] = "blocked"
            elif row["status"] in {"unknown", "observed"}:
                row["status"] = "completed"
            row["visible_status"] = str(row["final_review"].get("display") or row["status"])
        elif row.get("spec_round", {}).get("blockers"):
            row["visible_status"] = "blocked"
        elif row.get("spec_round", {}).get("warnings") and row["status"] == "running":
            row["visible_status"] = "running degraded"
        else:
            row["visible_status"] = row["status"]
        phases = [str(agent.get("phase") or "") for agent in row["agents"] if agent.get("phase")]
        row["phase"] = Counter(phases).most_common(1)[0][0] if phases else row["phase"]
        summaries = [str(agent.get("taskSummary") or "") for agent in row["agents"] if agent.get("taskSummary")]
        terminal = next((summary for summary in summaries if "complete:" in summary.lower() or "blocked" in summary.lower()), "")
        row["outcome"] = row["final_review"].get("summary") or short_text(next(iter(row.get("spec_round", {}).get("blockers", [])), "") or next(iter(row.get("spec_round", {}).get("warnings", [])), "") or terminal)
        spec_branch = row.get("spec_round", {}).get("expected_branch") or row.get("spec_round", {}).get("pr_ready_branch")
        add_unique(row["_structured_branches"], spec_branch)
        if row["_structured_branches"]:
            row["branches"] = row["_structured_branches"]
            row["branch_source"] = "structured"
        else:
            row["branches"] = row["_fallback_branches"]
            row["branch_source"] = "fallback" if row["branches"] else ""
        if not row["artifacts"] and row.get("spec_round", {}).get("artifacts"):
            row["artifacts"] = row["spec_round"]["artifacts"]
        if not row["validation"] and row.get("spec_round", {}).get("validation"):
            row["validation"] = row["spec_round"]["validation"]
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
                "spec_round": spec_info_from_item(item, source=kind),
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
    web_app = web_app_health(kubernetes)
    brokers = hub.get("brokers", []) if hub.get("ok") else []
    broker = ok_source("broker", "healthy" if brokers else "degraded", brokers=brokers, count=len(brokers))
    agents = hub.get("agents", []) if hub.get("ok") else []
    message_items = messages.get("items", []) if messages.get("ok") else []
    notification_items = notifications.get("items", []) if notifications.get("ok") else []
    rounds = build_rounds(agents, message_items, notification_items, provider=provider)
    latest = max([item.get("latest_update") or "" for item in rounds], default="")
    stale = source_stale(latest, parse_time(generated_at))
    sources = {"hub": hub, "broker": broker, "mcp": mcp, "web_app": web_app, "kubernetes": kubernetes, "messages": messages, "notifications": notifications}
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
            "checks": {name: {"status": source.get("status", "unavailable"), "ok": source.get("ok", False), "error": source.get("error", "")} for name, source in sources.items()},
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
    spec_round = normalize_spec_round_payload(status, source="round_status")
    detail_agents = status.get("agents", []) if isinstance(status.get("agents"), list) else []
    for agent in detail_agents:
        for branch in structured_branch_refs(agent):
            add_unique(structured_branches, branch)
        for branch in fallback_branch_refs(agent.get("taskSummary")):
            add_unique(fallback_branches, branch)
    outcome = status.get("outcome") or events.get("outcome") or {}
    spec_round = merge_spec_info(spec_round, normalize_spec_round_payload(outcome, source="outcome"))
    for branch in structured_branch_refs(outcome):
        add_unique(structured_branches, branch)
    outcome_review = final_review_from_outcome(outcome)
    if outcome_review:
        final_reviews.append(outcome_review)
    if events.get("ok"):
        spec_round = merge_spec_info(spec_round, normalize_spec_round_payload(events, source="round_events"))
        for event in events.get("events", []):
            item = event.get("message") or event.get("notification") or event.get("agent") or {}
            spec_round = merge_spec_info(spec_round, spec_info_from_item(item, source=str(event.get("type") or "event")))
            for payload in payload_candidates(item):
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
                "spec_round": spec_info_from_item(item, source=str(event.get("type") or "event")),
                "raw": item,
            })
    artifacts: dict[str, Any] = {}
    validation: dict[str, Any] = {}
    if hasattr(provider, "round_artifacts"):
        try:
            artifacts = normalize_artifacts(provider.round_artifacts(round_id, project_root=spec_round.get("project_root", "")))
            spec_round = merge_spec_info(spec_round, {"artifacts": artifacts})
            for branch in artifacts.get("branches", []):
                add_unique(structured_branches, branch)
            for remote in artifacts.get("remote_branches", []):
                add_unique(structured_branches, remote.get("branch"))
        except Exception:
            artifacts = {}
    project_root = spec_round.get("project_root", "")
    change = spec_round.get("change", "")
    if project_root and change and hasattr(provider, "spec_status"):
        try:
            validation = normalize_validation(provider.spec_status(project_root, change))
            spec_round = merge_spec_info(spec_round, {"validation": validation, "validation_status": validation.get("status", "")})
        except Exception:
            validation = {}
    transcript = status.get("consensus_transcript") if isinstance(status.get("consensus_transcript"), dict) else {}
    final_reviews.sort(key=lambda item: item.get("time") or "")
    add_unique(structured_branches, spec_round.get("expected_branch"))
    add_unique(structured_branches, spec_round.get("pr_ready_branch"))
    branches = structured_branches if structured_branches else fallback_branches
    final_review = final_reviews[-1] if final_reviews else {}
    visible_status = str(final_review.get("display") or ("blocked" if spec_round.get("blockers") else "") or spec_round.get("status") or status.get("status") or "unknown")
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
        "spec_round": spec_round,
        "artifacts": artifacts or spec_round.get("artifacts", {}),
        "validation": validation or spec_round.get("validation", {}),
        "event_cursor": events.get("cursor") or spec_round.get("cursor", ""),
        "progress_lines": events.get("progress_lines") if isinstance(events.get("progress_lines"), list) else spec_round.get("progress_lines", []),
        "terminal": status.get("terminal") or events.get("terminal") or {},
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
    .chips { display:flex; gap:6px; flex-wrap:wrap; }
    .chip { border:1px solid var(--line); border-radius:999px; padding:2px 7px; font-size:12px; background:#fafafa; }
    .bad-text { color:var(--bad); }
    .warn-text { color:var(--warn); }
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
    const compactSha = value => value ? String(value).slice(0, 12) : "";
    const listItems = (items, cls = "") => items?.length ? `<ul class="${esc(cls)}">${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : "";
    const specPanel = spec => {
      if (!spec || !Object.keys(spec).length) return `<div class="muted">No spec-round fields available.</div>`;
      const protocol = spec.protocol || {};
      return `<div class="chips">
          ${spec.status ? `<span class="chip">spec ${esc(spec.status)}</span>` : ""}
          ${spec.validation_status ? `<span class="chip">validation ${esc(spec.validation_status)}</span>` : ""}
          ${spec.branch_changed !== undefined ? `<span class="chip">branch changed ${esc(spec.branch_changed)}</span>` : ""}
          ${protocol.complete !== undefined ? `<span class="chip">protocol ${esc(protocol.complete ? "complete" : "incomplete")}</span>` : ""}
        </div>
        ${spec.expected_branch ? `<div><strong>Expected</strong><div class="mono">${esc(spec.expected_branch)}</div></div>` : ""}
        ${spec.pr_ready_branch ? `<div><strong>PR-ready</strong><div class="mono">${esc(spec.pr_ready_branch)}</div></div>` : ""}
        ${spec.remote_branch_sha ? `<div><strong>Remote SHA</strong><div class="mono">${esc(compactSha(spec.remote_branch_sha))}</div></div>` : ""}
        ${listItems(spec.blockers, "bad-text")}
        ${listItems(spec.warnings, "warn-text")}`;
    };
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
        <div class="grid">${["hub","broker","mcp","web_app","kubernetes","messages","notifications"].map(name => `<div class="card"><div>${status(sources[name]?.status)}</div><strong>${esc(name)}</strong><div class="muted">${esc(sources[name]?.error || `${sources[name]?.count ?? ""} ${name === "broker" ? "brokers" : ""}`)}</div></div>`).join("")}</div>`;
    }
    function renderRounds() {
      const rows = state.snapshot.rounds;
      document.getElementById("rounds").innerHTML = rows.length ? `
        <div class="table-wrap"><table><thead><tr><th>Round</th><th>Status</th><th>Phase</th><th>Agents</th><th>Latest update</th><th>Spec / validation</th><th>Outcome</th><th>Branches</th></tr></thead><tbody>
        ${rows.map(row => `<tr data-round="${esc(row.round_id)}"><td class="mono">${esc(row.round_id)}</td><td>${status(row.visible_status || row.status)}</td><td>${esc(row.phase)}</td><td>${row.agent_count}</td><td>${fmt(row.latest_update)}<div class="muted">${esc(row.latest_summary)}</div></td><td>${specPanel(row.spec_round)}</td><td>${esc(row.outcome || "")}</td><td>${(row.branches || []).map(branch => `<div class="mono">${esc(branch)}</div>`).join("")}${row.branch_source ? `<div class="muted">${esc(row.branch_source)}</div>` : ""}</td></tr>`).join("")}
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
      const artifacts = detail.artifacts || {};
      const validation = detail.validation || {};
      document.getElementById("round-detail").innerHTML = `
        <div class="bar"><button id="back-rounds">Back to rounds</button><button id="refresh-round">Refresh timeline</button></div>
        <div class="split">
          <div class="detail"><h2 class="mono">${esc(roundId)}</h2><div>${status(detail.visible_status || detail.status.status || "unknown")}</div><div class="muted">Cursor ${esc(detail.event_cursor || "none")}</div><h3>Spec Round</h3>${specPanel(detail.spec_round)}<h3>Timeline</h3><div class="timeline">${detail.timeline.length ? detail.timeline.map(item => `<div class="item"><div>${status(item.type)}</div><div class="muted">${fmt(item.time)}</div><div>${esc(item.summary)}</div>${item.spec_round?.validation_status ? `<div class="muted">validation ${esc(item.spec_round.validation_status)}</div>` : ""}</div>`).join("") : `<div class="muted">No messages or notifications for this round.</div>`}</div></div>
          <div class="detail"><h3>Final Review</h3>${review.display ? `<div>${status(review.display)}</div><div class="muted">${esc(review.source || "")}${review.summary ? ` - ${esc(review.summary)}` : ""}</div>${listItems(review.blocking_issues, "bad-text")}` : `<div class="muted">No final review available.</div>`}<h3>Artifacts</h3>${artifacts.remote_branches?.length ? artifacts.remote_branches.map(branch => `<div class="mono">${esc(branch.branch)} ${esc(compactSha(branch.sha))}</div>`).join("") : `<div class="muted">No remote branch artifacts available.</div>`}<h3>Branches</h3>${detail.branches?.length ? detail.branches.map(branch => `<div class="mono">${esc(branch)}</div>`).join("") + (detail.branch_source ? `<div class="muted">${esc(detail.branch_source)}</div>` : "") : `<div class="muted">No branch references available.</div>`}<h3>Validation</h3>${validation.status ? `<div>${status(validation.status)}</div>${listItems(validation.errors, "bad-text")}` : `<div class="muted">No validation result available.</div>`}<h3>Agents</h3>${agents.length ? agents.map(agent => `<div class="card"><strong>${esc(agent.name || agent.slug)}</strong><div>${status(agent.phase || "unknown")}</div><div class="muted">${esc(agent.taskSummary || agent.activity || "")}</div></div>`).join("") : `<div class="muted">No agents found.</div>`}<h3>Runner Output</h3>${detail.runner_output ? `<pre class="mono">${esc(detail.runner_output)}</pre>` : `<div class="muted">${esc(detail.runner_output_error || "No runner output available.")}</div>`}</div>
        </div>`;
      document.getElementById("back-rounds").onclick = () => setView("rounds");
      document.getElementById("refresh-round").onclick = () => openRound(roundId);
    }
    function renderInbox() {
      const groups = state.snapshot.inbox;
      document.getElementById("inbox").innerHTML = groups.length ? groups.map(group => `
        <div class="detail"><h2>${esc(group.round_id)}</h2>${group.items.map(item => `<div class="timeline item"><div>${status(item.type)}</div><div class="muted">${fmt(item.time)} ${esc(item.source_id)}</div><div>${esc(item.summary)}</div>${item.spec_round?.validation_status ? `<div class="muted">validation ${esc(item.spec_round.validation_status)}</div>` : ""}${listItems(item.spec_round?.blockers, "bad-text")}${listItems(item.spec_round?.warnings, "warn-text")}</div>`).join("")}</div>`).join("") : `<div class="card"><strong>No inbox updates</strong><div class="muted">Hub returned no messages or notifications.</div></div>`;
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
