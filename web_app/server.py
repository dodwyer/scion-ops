#!/usr/bin/env python3
"""Read-only web app hub for scion-ops operator monitoring.

Serves a browser frontend and JSON API endpoints that proxy Hub, Kubernetes,
and MCP state. No write operations are exposed.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any

PORT = int(os.environ.get("SCION_OPS_WEB_PORT", "8880"))
HOST = os.environ.get("SCION_OPS_WEB_HOST", "0.0.0.0")

HUB_ENDPOINT = (
    os.environ.get("SCION_OPS_HUB_ENDPOINT")
    or os.environ.get("SCION_HUB_ENDPOINT")
    or "http://scion-hub:8090"
).rstrip("/")

GROVE_ID_FILE = Path(
    os.environ.get("SCION_OPS_ROOT", "/workspace/scion-ops")
) / ".scion" / "grove-id"

DEV_TOKEN_FILE = os.environ.get("SCION_DEV_TOKEN_FILE", "")

MCP_HOST = os.environ.get("SCION_OPS_MCP_HOST_INTERNAL", "scion-ops-mcp")
MCP_PORT = int(os.environ.get("SCION_OPS_MCP_PORT_INTERNAL", "8765"))

NAMESPACE = os.environ.get("SCION_K8S_NAMESPACE", "scion-agents")
K8S_API = "https://kubernetes.default.svc"
K8S_SA_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"
K8S_SA_CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

STATIC_DIR = Path(__file__).parent / "static"

ROUND_RE = re.compile(r"(round-[a-z0-9]+-[a-z0-9]+)", re.IGNORECASE)
BRANCH_RE = re.compile(r"(round-[a-z0-9]+-[a-z0-9]+-[a-z][a-z0-9-]*)", re.IGNORECASE)

_FINAL_REVIEW_RE = re.compile(r"final.?review|verdict", re.IGNORECASE)
_REQUEST_CHANGES_RE = re.compile(r"request.?changes|changes.?requested", re.IGNORECASE)
_APPROVED_RE = re.compile(r"\bapproved\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Auth / config helpers
# ---------------------------------------------------------------------------

def _read_grove_id() -> str:
    grove_id = (
        os.environ.get("SCION_OPS_GROVE_ID")
        or os.environ.get("SCION_GROVE_ID")
        or ""
    )
    if grove_id:
        return grove_id.strip()
    try:
        return GROVE_ID_FILE.read_text().strip()
    except OSError:
        return ""


def _read_hub_token() -> str:
    token = os.environ.get("SCION_DEV_TOKEN", "").strip()
    if token:
        return token
    if DEV_TOKEN_FILE:
        try:
            return Path(DEV_TOKEN_FILE).read_text().strip()
        except OSError:
            pass
    return (
        os.environ.get("SCION_HUB_TOKEN", "").strip()
        or os.environ.get("SCION_AUTH_TOKEN", "").strip()
    )


def _hub_headers() -> dict[str, str]:
    token = _read_hub_token()
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Hub HTTP helpers
# ---------------------------------------------------------------------------

def _hub_get(
    path: str,
    query: dict[str, str] | None = None,
    timeout: int = 10,
) -> tuple[Any, str | None]:
    url = HUB_ENDPOINT + path
    if query:
        url += "?" + urllib.parse.urlencode(
            {k: v for k, v in query.items() if v is not None}
        )
    req = urllib.request.Request(url, headers=_hub_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None, None
            return json.loads(raw.decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return None, str(exc)
    except json.JSONDecodeError as exc:
        return None, f"JSON error: {exc}"


# ---------------------------------------------------------------------------
# Kubernetes API helpers
# ---------------------------------------------------------------------------

def _k8s_token() -> str:
    try:
        return Path(K8S_SA_TOKEN).read_text().strip()
    except OSError:
        return ""


def _k8s_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        ctx.load_verify_locations(K8S_SA_CA)
    except (OSError, ssl.SSLError):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _k8s_get(path: str, timeout: int = 10) -> tuple[Any, str | None]:
    token = _k8s_token()
    if not token:
        return None, "no in-cluster service account token"
    url = K8S_API + path
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=_k8s_ssl_context(), timeout=timeout) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return None, str(exc)
    except json.JSONDecodeError as exc:
        return None, f"JSON error: {exc}"


# ---------------------------------------------------------------------------
# MCP reachability
# ---------------------------------------------------------------------------

def _check_mcp() -> tuple[bool, str]:
    try:
        conn_url = f"http://{MCP_HOST}:{MCP_PORT}/"
        req = urllib.request.Request(conn_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        # Any HTTP response means the server is running
        return exc.code < 500, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Round / agent helpers
# ---------------------------------------------------------------------------

def _round_prefix(name: str) -> str:
    m = ROUND_RE.match(name or "")
    return m.group(1) if m else ""


def _phase_status(agent: dict[str, Any]) -> str:
    phase = str(agent.get("phase") or "").lower()
    activity = str(agent.get("activity") or "").lower()
    container = str(agent.get("containerStatus") or "").lower()
    if phase in {"stopped", "deleted", "ended", "completed", "error", "failed"}:
        return "terminal"
    if activity in {"completed", "limits_exceeded"}:
        return "terminal"
    if any(t in container for t in ("succeeded", "completed", "failed", "error")):
        return "terminal"
    if phase in {"running", "started"} or activity in {"active", "running"}:
        return "running"
    return "pending"


def _agent_summary(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": agent.get("name") or agent.get("slug"),
        "slug": agent.get("slug"),
        "phase": agent.get("phase"),
        "activity": agent.get("activity"),
        "containerStatus": agent.get("containerStatus"),
        "template": agent.get("template"),
        "taskSummary": agent.get("taskSummary"),
        "created": agent.get("created"),
        "updated": agent.get("updated"),
    }


def _round_text_match(item: dict[str, Any], round_id: str) -> bool:
    needle = round_id.lower()
    fields = [
        item.get("id"),
        item.get("name"),
        item.get("slug"),
        item.get("agentId"),
        item.get("sender"),
        item.get("senderId"),
        item.get("msg"),
        item.get("message"),
        item.get("status"),
        item.get("taskSummary"),
    ]
    return any(needle in str(v).lower() for v in fields if v is not None)


def _extract_round_id(item: dict[str, Any]) -> str:
    text = json.dumps(item, default=str)
    m = ROUND_RE.search(text)
    return m.group(1) if m else ""


def _extract_branches_from_text(text: str, round_id: str) -> set[str]:
    """Return branch-like references in text that start with round_id."""
    return {
        m.group(1)
        for m in BRANCH_RE.finditer(text)
        if m.group(1).lower().startswith(round_id.lower())
    }


def _find_verdict(
    messages: list[dict[str, Any]], notifications: list[dict[str, Any]]
) -> dict[str, str] | None:
    """Return a final-review verdict dict if one is found in messages/notifications."""
    for item in messages + notifications:
        text = json.dumps(item, default=str)
        if not _FINAL_REVIEW_RE.search(text):
            continue
        summary = str(item.get("msg") or item.get("message") or "")
        if _REQUEST_CHANGES_RE.search(text):
            return {"decision": "request_changes", "summary": summary}
        if _APPROVED_RE.search(text):
            return {"decision": "approved", "summary": summary}
    return None


# ---------------------------------------------------------------------------
# API handlers
# ---------------------------------------------------------------------------

def api_overview() -> dict[str, Any]:
    grove_id = _read_grove_id()
    checks: list[dict[str, Any]] = []

    # Hub health
    _, hub_err = _hub_get("/healthz", timeout=5)
    hub_ok = hub_err is None
    checks.append({"name": "hub", "ok": hub_ok, "detail": hub_err or "reachable"})

    # Broker
    broker_ok = False
    broker_detail = "hub unavailable" if not hub_ok else "not checked"
    if hub_ok and grove_id:
        data, err = _hub_get(
            "/api/v1/runtime-brokers", query={"groveId": grove_id}, timeout=8
        )
        if err:
            broker_detail = err
        else:
            brokers = (data.get("brokers") or []) if isinstance(data, dict) else []
            online = [
                b for b in brokers
                if isinstance(b, dict) and str(b.get("status") or "").lower() == "online"
            ]
            broker_ok = len(online) > 0
            broker_detail = f"{len(online)} of {len(brokers)} online"
    checks.append({"name": "broker", "ok": broker_ok, "detail": broker_detail})

    # MCP
    mcp_ok, mcp_detail = _check_mcp()
    checks.append({"name": "mcp", "ok": mcp_ok, "detail": mcp_detail or "reachable"})

    # Kubernetes deployments
    k8s_data, k8s_err = _k8s_get(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments")
    if k8s_err:
        checks.append({"name": "kubernetes", "ok": False, "detail": k8s_err})
    else:
        items = (k8s_data.get("items") or []) if isinstance(k8s_data, dict) else []
        ready_count = sum(
            1 for item in items
            if isinstance(item, dict)
            and any(
                c.get("type") == "Available" and c.get("status") == "True"
                for c in ((item.get("status") or {}).get("conditions") or [])
            )
        )
        k8s_ok = ready_count == len(items) and len(items) > 0
        checks.append({
            "name": "kubernetes",
            "ok": k8s_ok,
            "detail": f"{ready_count}/{len(items)} deployments ready",
        })

    overall_ok = all(c["ok"] for c in checks)
    return {
        "ok": overall_ok,
        "status": "ready" if overall_ok else "degraded",
        "checks": checks,
        "grove_id": grove_id,
        "hub_endpoint": HUB_ENDPOINT,
    }


def api_rounds() -> dict[str, Any]:
    grove_id = _read_grove_id()
    if not grove_id:
        return {
            "ok": False,
            "error": "grove_id not configured",
            "error_kind": "hub_state",
            "rounds": [],
        }

    data, err = _hub_get(
        f"/api/v1/groves/{urllib.parse.quote(grove_id)}/agents",
        query={"includeDeleted": "true"},
    )
    if err:
        return {"ok": False, "error": err, "error_kind": "hub_unavailable", "rounds": []}

    all_agents = (data.get("agents") or []) if isinstance(data, dict) else []

    round_map: dict[str, list[dict[str, Any]]] = {}
    for agent in all_agents:
        if not isinstance(agent, dict):
            continue
        name = str(agent.get("name") or agent.get("slug") or "")
        prefix = _round_prefix(name)
        if prefix:
            round_map.setdefault(prefix, []).append(agent)

    rounds = []
    for prefix, group in round_map.items():
        updated = max(
            (str(a.get("updated") or a.get("created") or "") for a in group),
            default="",
        )
        statuses = [_phase_status(a) for a in group]
        if all(s == "terminal" for s in statuses):
            block_keywords = ("blocked", "escalat", "ask_user")
            all_texts = " ".join(
                str(a.get("taskSummary") or "") + " " + str(a.get("activity") or "")
                for a in group
            ).lower()
            status = "blocked" if any(kw in all_texts for kw in block_keywords) else "completed"
        elif any(s == "running" for s in statuses):
            status = "running"
        else:
            status = "pending"

        consensus = next(
            (
                a for a in group
                if str(a.get("template") or "").endswith("consensus")
                or str(a.get("name") or "").endswith("-consensus")
            ),
            None,
        )
        summary = str(consensus.get("taskSummary") or "") if consensus else ""

        rounds.append({
            "id": prefix,
            "agents": [_agent_summary(a) for a in group],
            "agent_count": len(group),
            "status": status,
            "updated": updated,
            "summary": summary,
        })

    rounds.sort(key=lambda r: r["updated"], reverse=True)
    return {"ok": True, "rounds": rounds, "agent_count": len(all_agents)}


def api_round_detail(round_id: str) -> dict[str, Any]:
    grove_id = _read_grove_id()
    if not grove_id:
        return {"ok": False, "error": "grove_id not configured", "error_kind": "hub_state"}

    agents_data, agents_err = _hub_get(
        f"/api/v1/groves/{urllib.parse.quote(grove_id)}/agents",
        query={"includeDeleted": "true"},
    )
    raw_agents: list[dict[str, Any]] = []
    if not agents_err and isinstance(agents_data, dict):
        raw_agents = [
            a for a in (agents_data.get("agents") or [])
            if isinstance(a, dict) and round_id.lower() in str(a.get("name") or "").lower()
        ]
    agents = [_agent_summary(a) for a in raw_agents]

    # Fetch messages and notifications before computing outcome and branches so
    # final-review verdicts and explicit branch references can be incorporated.
    msgs_data, msgs_err = _hub_get(
        "/api/v1/messages",
        query={"grove": grove_id, "limit": "200"},
    )
    messages: list[dict[str, Any]] = []
    if not msgs_err and isinstance(msgs_data, dict):
        messages = [
            m for m in (msgs_data.get("items") or [])
            if isinstance(m, dict) and _round_text_match(m, round_id)
        ]

    notifs_data, notifs_err = _hub_get(
        "/api/v1/notifications", query={"acknowledged": "true"}
    )
    notifications: list[dict[str, Any]] = []
    if not notifs_err and isinstance(notifs_data, list):
        notifications = [
            n for n in notifs_data
            if isinstance(n, dict) and _round_text_match(n, round_id)
        ]

    # Derive round status from agent phase/activity.
    statuses = [_phase_status(a) for a in raw_agents]
    if not raw_agents:
        round_status = "pending"
    elif all(s == "terminal" for s in statuses):
        block_keywords = ("blocked", "escalat", "ask_user")
        all_texts = " ".join(
            str(a.get("taskSummary") or "") + " " + str(a.get("activity") or "")
            for a in raw_agents
        ).lower()
        round_status = "blocked" if any(kw in all_texts for kw in block_keywords) else "completed"
    elif any(s == "running" for s in statuses):
        round_status = "running"
    else:
        round_status = "pending"

    consensus = next(
        (
            a for a in raw_agents
            if str(a.get("template") or "").endswith("consensus")
            or str(a.get("name") or "").endswith("-consensus")
        ),
        None,
    )
    outcome: dict[str, Any] = {
        "status": round_status,
        "summary": str(consensus.get("taskSummary") or "") if consensus else "",
    }

    # Enrich outcome with final-review verdict from Hub messages/notifications.
    verdict = _find_verdict(messages, notifications)
    if verdict:
        outcome["final_review"] = verdict
        if verdict["decision"] == "request_changes" and round_status == "completed":
            outcome["status"] = "changes_requested"

    # Extract branch references from message/notification content and agent
    # taskSummary fields; fall back to agent name-based inference when none are found.
    branch_set: set[str] = set()
    for item in messages + notifications:
        branch_set |= _extract_branches_from_text(json.dumps(item, default=str), round_id)
    for agent in raw_agents:
        branch_set |= _extract_branches_from_text(
            str(agent.get("taskSummary") or ""), round_id
        )
    if not branch_set:
        branch_set = {
            str(a.get("name") or a.get("slug") or "")
            for a in raw_agents
            if str(a.get("name") or a.get("slug") or "")
        }
    branches = sorted(branch_set)

    non_consensus = [
        a for a in raw_agents
        if not (
            str(a.get("template") or "").endswith("consensus")
            or str(a.get("name") or "").endswith("-consensus")
        )
        and a.get("taskSummary")
    ]
    runner_output = str(non_consensus[-1].get("taskSummary") or "") if non_consensus else ""

    errors: dict[str, str] = {}
    if agents_err:
        errors["agents"] = agents_err
    if msgs_err:
        errors["messages"] = msgs_err
    if notifs_err:
        errors["notifications"] = notifs_err

    return {
        "ok": not errors or bool(agents or messages or notifications),
        "round_id": round_id,
        "agents": agents,
        "outcome": outcome,
        "branches": branches,
        "runner_output": runner_output,
        "messages": messages,
        "notifications": notifications,
        "errors": errors,
    }


def api_inbox() -> dict[str, Any]:
    grove_id = _read_grove_id()
    if not grove_id:
        return {
            "ok": False,
            "error": "grove_id not configured",
            "error_kind": "hub_state",
            "groups": [],
        }

    msgs_data, msgs_err = _hub_get(
        "/api/v1/messages",
        query={"grove": grove_id, "limit": "200"},
    )
    notifs_data, notifs_err = _hub_get(
        "/api/v1/notifications", query={"acknowledged": "true"}
    )

    messages: list[dict[str, Any]] = []
    if not msgs_err and isinstance(msgs_data, dict):
        messages = [m for m in (msgs_data.get("items") or []) if isinstance(m, dict)]

    notifications: list[dict[str, Any]] = []
    if not notifs_err and isinstance(notifs_data, list):
        notifications = [
            n for n in notifs_data
            if isinstance(n, dict)
            and (not n.get("groveId") or n.get("groveId") == grove_id)
        ]

    groups: dict[str, dict[str, Any]] = {}
    for msg in messages:
        key = _extract_round_id(msg) or "_ungrouped"
        if key not in groups:
            groups[key] = {
                "round_id": key if key != "_ungrouped" else None,
                "messages": [],
                "notifications": [],
            }
        groups[key]["messages"].append(msg)

    for notif in notifications:
        key = _extract_round_id(notif) or "_ungrouped"
        if key not in groups:
            groups[key] = {
                "round_id": key if key != "_ungrouped" else None,
                "messages": [],
                "notifications": [],
            }
        groups[key]["notifications"].append(notif)

    group_list = sorted(
        groups.values(),
        key=lambda g: g.get("round_id") or "",
        reverse=True,
    )

    errors: dict[str, str] = {}
    if msgs_err:
        errors["messages"] = msgs_err
    if notifs_err:
        errors["notifications"] = notifs_err

    return {
        "ok": not errors or bool(messages or notifications),
        "groups": group_list,
        "message_count": len(messages),
        "notification_count": len(notifications),
        "errors": errors,
    }


def api_runtime() -> dict[str, Any]:
    grove_id = _read_grove_id()
    checks: dict[str, Any] = {}

    # Hub health
    health_data, hub_err = _hub_get("/healthz", timeout=5)
    checks["hub"] = {
        "ok": hub_err is None,
        "detail": hub_err or str(health_data or "ok"),
        "endpoint": HUB_ENDPOINT,
    }

    # Brokers
    if grove_id and hub_err is None:
        data, err = _hub_get(
            "/api/v1/runtime-brokers", query={"groveId": grove_id}, timeout=8
        )
        if err:
            checks["brokers"] = {"ok": False, "detail": err}
        else:
            brokers = (data.get("brokers") or []) if isinstance(data, dict) else []
            checks["brokers"] = {
                "ok": any(
                    str(b.get("status") or "").lower() == "online" for b in brokers
                ),
                "brokers": brokers,
                "detail": f"{len(brokers)} registered",
            }

    # MCP
    mcp_ok, mcp_detail = _check_mcp()
    checks["mcp"] = {"ok": mcp_ok, "detail": mcp_detail, "host": MCP_HOST, "port": MCP_PORT}

    # K8s deployments
    k8s_data, k8s_err = _k8s_get(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments")
    if k8s_err:
        checks["kubernetes"] = {"ok": False, "detail": k8s_err}
    else:
        items = (k8s_data.get("items") or []) if isinstance(k8s_data, dict) else []
        deploys = []
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") or {}
            spec = item.get("spec") or {}
            status = item.get("status") or {}
            conds = status.get("conditions") or []
            available = any(
                c.get("type") == "Available" and c.get("status") == "True"
                for c in conds
            )
            deploys.append({
                "name": meta.get("name", ""),
                "ready": status.get("readyReplicas", 0),
                "desired": spec.get("replicas", 0),
                "available": available,
            })
        checks["kubernetes"] = {
            "ok": bool(deploys) and all(d["available"] for d in deploys),
            "deployments": deploys,
            "namespace": NAMESPACE,
        }

    # K8s pods
    pods_data, pods_err = _k8s_get(f"/api/v1/namespaces/{NAMESPACE}/pods")
    if pods_err:
        checks["pods"] = {"ok": False, "detail": pods_err}
    else:
        items = (pods_data.get("items") or []) if isinstance(pods_data, dict) else []
        pods = []
        for pod in items:
            if not isinstance(pod, dict):
                continue
            meta = pod.get("metadata") or {}
            pods.append({
                "name": meta.get("name", ""),
                "phase": (pod.get("status") or {}).get("phase", "Unknown"),
                "labels": meta.get("labels") or {},
            })
        running_pods = [p for p in pods if p["phase"] not in ("Succeeded", "Unknown")]
        checks["pods"] = {
            "ok": all(p["phase"] == "Running" for p in running_pods),
            "pods": pods,
        }

    return {
        "ok": all(c.get("ok", False) for c in checks.values()),
        "grove_id": grove_id,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path

        if path in ("/", "/index.html"):
            self.send_static(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/api/overview":
            self.send_json(api_overview())
        elif path == "/api/rounds":
            self.send_json(api_rounds())
        elif path.startswith("/api/rounds/"):
            round_id = urllib.parse.unquote(path[len("/api/rounds/"):])
            self.send_json(api_round_detail(round_id))
        elif path == "/api/inbox":
            self.send_json(api_inbox())
        elif path == "/api/runtime":
            self.send_json(api_runtime())
        elif path == "/healthz":
            self.send_json({"ok": True})
        else:
            self.send_error(404)

    def do_HEAD(self) -> None:
        self.do_GET()


def main() -> None:
    server = _ThreadingHTTPServer((HOST, PORT), _Handler)
    print(f"scion-ops web hub on {HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
