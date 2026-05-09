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
CONTROL_PLANE_NAMES = {"scion-hub", "scion-broker", "scion-ops-mcp"}


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


def _extract_final_verdict(agents: list[dict[str, Any]], messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract final review verdict from agents and messages for a round."""
    def is_final_agent(agent: dict[str, Any]) -> bool:
        template = str(agent.get("template") or "")
        name = str(agent.get("name") or agent.get("slug") or "")
        return template.startswith("final-reviewer-") or name.endswith("-final-review")

    def normalize_verdict(value: Any) -> str:
        v = str(value or "").strip().lower()
        if v in {"accept", "accepted", "success", "pass", "passed"}:
            return "accept"
        if v in {"reject", "rejected", "request_changes", "changes_requested", "revise", "blocked", "fail", "failed"}:
            return "request_changes"
        return v

    final_agents = [a for a in agents if is_final_agent(a)]
    final_names = {str(v) for a in final_agents for v in (a.get("name"), a.get("slug"), a.get("id")) if v}

    for item in messages:
        text = str(item.get("msg") or item.get("message") or "")
        payload: dict[str, Any] = {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                payload = parsed
        except (ValueError, TypeError):
            m = re.search(r"\{[^{}]*\}", text)
            if m:
                try:
                    parsed = json.loads(m.group())
                    if isinstance(parsed, dict):
                        payload = parsed
                except (ValueError, TypeError):
                    pass
        if not payload or "verdict" not in payload:
            continue
        sender = str(item.get("sender") or item.get("senderId") or item.get("agentId") or "")
        reviewer = str(payload.get("reviewer") or "").lower()
        branch = str(payload.get("branch") or payload.get("target_branch") or "").lower()
        is_final = (
            reviewer.startswith("final-")
            or "final-review" in branch
            or any(name and name in sender for name in final_names)
        )
        if not is_final:
            continue
        nv = normalize_verdict(payload.get("verdict"))
        return {
            "verdict": str(payload.get("verdict") or ""),
            "normalized": nv,
            "status": "accepted" if nv == "accept" else "request_changes",
            "notes": str(payload.get("notes") or "")[:300],
        }

    for agent in final_agents:
        summary = str(agent.get("taskSummary") or "")
        m = re.search(r"final verdict:\s*([A-Za-z_ -]+)", summary, re.IGNORECASE)
        if m:
            nv = normalize_verdict(m.group(1))
            return {
                "verdict": m.group(1).strip(),
                "normalized": nv,
                "status": "accepted" if nv == "accept" else "request_changes",
                "notes": "",
            }

    return {}


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
            "deploy,pod,svc,pvc",
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
        elif kind == "PersistentVolumeClaim":
            pvcs.append({"name": name, "phase": item.get("status", {}).get("phase") or ""})
    missing = sorted(CONTROL_PLANE_NAMES - {item["name"] for item in deployments})
    bad_deployments = [item for item in deployments if not item["ready"]]
    bad_pods = [item for item in pods if not item["ready"] and item["phase"] not in {"Succeeded", "Completed"}]
    status = "healthy" if not missing and not bad_deployments and not bad_pods else "degraded"
    return ok_source(
        "kubernetes",
        status,
        namespace=namespace,
        deployments=deployments,
        pods=pods,
        services=services,
        pvcs=pvcs,
        missing_deployments=missing,
        degraded_pods=bad_pods,
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


def build_rounds(agents: list[dict[str, Any]], messages: list[dict[str, Any]], notifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "latest_update": "",
                "latest_summary": "",
                "status": "unknown",
                "phase": "unknown",
                "outcome": "",
            },
        )

    for agent in agents:
        round_id = extract_round_id(agent.get("name"), agent.get("slug"), agent.get("taskSummary"))
        if not round_id:
            continue
        row = ensure(round_id)
        row["agents"].append(agent)
        # Structured fields take precedence; text parsing is fallback only
        structured = [str(v).strip() for v in (agent.get("branch"), agent.get("targetBranch")) if v and str(v).strip()]
        if structured:
            for branch in structured:
                if branch not in row["branches"]:
                    row["branches"].append(branch)
        else:
            text = str(agent.get("taskSummary") or "")
            for branch in re.findall(r"round-[A-Za-z0-9._:/@+-]+", text):
                if branch not in row["branches"]:
                    row["branches"].append(branch)
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
            timestamp = event_time(item)
            if timestamp > row["latest_update"]:
                row["latest_update"] = timestamp
                row["latest_summary"] = short_text(item.get("msg") or item.get("message") or item.get("summary"))

    for row in grouped.values():
        statuses = [agent_status(agent) for agent in row["agents"]]
        verdict_info = _extract_final_verdict(row["agents"], row["messages"])
        if "blocked" in statuses:
            row["status"] = "blocked"
        elif any(status in {"running", "waiting"} for status in statuses):
            row["status"] = "running" if "running" in statuses else "waiting"
        elif statuses and all(status == "completed" for status in statuses):
            # Use final review verdict to avoid collapsing to generic "completed"
            if verdict_info.get("status") == "request_changes":
                row["status"] = "request_changes"
            elif verdict_info.get("status") == "accepted":
                row["status"] = "accepted"
            else:
                row["status"] = "completed"
        elif not row["agents"] and (row["messages"] or row["notifications"]):
            row["status"] = "observed"
        row["final_verdict"] = verdict_info.get("status") or ""
        row["final_verdict_raw"] = verdict_info.get("verdict") or ""
        row["final_verdict_notes"] = verdict_info.get("notes") or ""
        phases = [str(agent.get("phase") or "") for agent in row["agents"] if agent.get("phase")]
        row["phase"] = Counter(phases).most_common(1)[0][0] if phases else row["phase"]
        summaries = [str(agent.get("taskSummary") or "") for agent in row["agents"] if agent.get("taskSummary")]
        terminal = next((summary for summary in summaries if "complete:" in summary.lower() or "blocked" in summary.lower()), "")
        row["outcome"] = short_text(terminal)
        row["agent_count"] = len(row["agents"])
        row["message_count"] = len(row["messages"])
        row["notification_count"] = len(row["notifications"])
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
    required = ["hub", "broker", "mcp", "kubernetes"]
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
    brokers = hub.get("brokers", []) if hub.get("ok") else []
    broker = ok_source("broker", "healthy" if brokers else "degraded", brokers=brokers, count=len(brokers))
    agents = hub.get("agents", []) if hub.get("ok") else []
    message_items = messages.get("items", []) if messages.get("ok") else []
    notification_items = notifications.get("items", []) if notifications.get("ok") else []
    rounds = build_rounds(agents, message_items, notification_items)
    latest = max([item.get("latest_update") or "" for item in rounds], default="")
    stale = source_stale(latest, parse_time(generated_at))
    sources = {"hub": hub, "broker": broker, "mcp": mcp, "kubernetes": kubernetes, "messages": messages, "notifications": notifications}
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
    if events.get("ok"):
        for event in events.get("events", []):
            item = event.get("message") or event.get("notification") or event.get("agent") or {}
            timeline.append({
                "type": event.get("type") or "event",
                "time": event_time(item),
                "summary": short_text(item.get("msg") or item.get("message") or item.get("summary") or item.get("taskSummary") or item.get("activity"), 360),
                "raw": item,
            })
    transcript = status.get("consensus_transcript") if isinstance(status.get("consensus_transcript"), dict) else {}
    return {
        "ok": bool(status.get("ok")) or bool(events.get("ok")),
        "round_id": round_id,
        "status": status,
        "events": events,
        "timeline": sorted(timeline, key=lambda item: item.get("time") or ""),
        "runner_output": transcript.get("output", "") if transcript.get("ok") else "",
        "runner_output_error": "" if transcript.get("ok") or not transcript else transcript.get("error") or transcript.get("output", ""),
        "outcome": status.get("outcome") or events.get("outcome") or {},
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
    .degraded .dot, .waiting .dot, .stale .dot, .observed .dot, .request_changes .dot { background:var(--warn); }
    .unavailable .dot, .blocked .dot, .error .dot { background:var(--bad); }
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
    const status = value => `<span class="status ${esc(value)}"><span class="dot"></span>${esc(value || "unknown")}</span>`;
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
        <div class="grid">${["hub","broker","mcp","kubernetes"].map(name => `<div class="card"><div>${status(sources[name]?.status)}</div><strong>${esc(name)}</strong><div class="muted">${esc(sources[name]?.error || `${sources[name]?.count ?? ""} ${name === "broker" ? "brokers" : ""}`)}</div></div>`).join("")}</div>`;
    }
    function renderRounds() {
      const rows = state.snapshot.rounds;
      document.getElementById("rounds").innerHTML = rows.length ? `
        <div class="table-wrap"><table><thead><tr><th>Round</th><th>Status</th><th>Phase</th><th>Agents</th><th>Latest update</th><th>Outcome</th></tr></thead><tbody>
        ${rows.map(row => `<tr data-round="${esc(row.round_id)}"><td class="mono">${esc(row.round_id)}</td><td>${status(row.status)}</td><td>${esc(row.phase)}</td><td>${row.agent_count}</td><td>${fmt(row.latest_update)}<div class="muted">${esc(row.latest_summary)}</div></td><td>${esc(row.outcome || "")}${row.final_verdict ? `<div>${status(row.final_verdict)}</div>` : ""}</td></tr>`).join("")}
        </tbody></table></div>` : `<div class="card"><strong>No rounds found</strong><div class="muted">Hub returned no round-identifiable agents, messages, or notifications.</div></div>`;
      document.querySelectorAll("[data-round]").forEach(row => row.onclick = () => openRound(row.dataset.round));
    }
    async function openRound(roundId) {
      state.selectedRound = roundId;
      setView("round-detail");
      document.getElementById("round-detail").innerHTML = `<div class="card">Loading ${esc(roundId)}...</div>`;
      const detail = await getJson(`/api/rounds/${encodeURIComponent(roundId)}`);
      const agents = detail.status.agents || [];
      const outcome = detail.outcome || {};
      const finalReview = (outcome.final_review && typeof outcome.final_review === 'object') ? outcome.final_review : null;
      const verdictHtml = finalReview && finalReview.verdict
        ? `<h3>Final Review</h3><div>${status(finalReview.status || "unknown")}</div><div class="muted">${esc(finalReview.verdict)}</div>${finalReview.notes ? `<div class="muted">${esc(finalReview.notes)}</div>` : ""}`
        : (outcome.status && outcome.status !== "completed"
          ? `<h3>Final Review</h3><div>${status(outcome.status)}</div>`
          : "");
      document.getElementById("round-detail").innerHTML = `
        <div class="bar"><button id="back-rounds">Back to rounds</button><button id="refresh-round">Refresh timeline</button></div>
        <div class="split">
          <div class="detail"><h2 class="mono">${esc(roundId)}</h2><h3>Timeline</h3><div class="timeline">${detail.timeline.length ? detail.timeline.map(item => `<div class="item"><div>${status(item.type)}</div><div class="muted">${fmt(item.time)}</div><div>${esc(item.summary)}</div></div>`).join("") : `<div class="muted">No messages or notifications for this round.</div>`}</div></div>
          <div class="detail"><h3>Agents</h3>${agents.length ? agents.map(agent => `<div class="card"><strong>${esc(agent.name || agent.slug)}</strong><div>${status(agent.phase || "unknown")}</div><div class="muted">${esc(agent.taskSummary || agent.activity || "")}</div></div>`).join("") : `<div class="muted">No agents found.</div>`}${verdictHtml}<h3>Runner Output</h3>${detail.runner_output ? `<pre class="mono">${esc(detail.runner_output)}</pre>` : `<div class="muted">${esc(detail.runner_output_error || "No runner output available.")}</div>`}</div>
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
