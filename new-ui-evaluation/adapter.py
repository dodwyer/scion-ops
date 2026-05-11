#!/usr/bin/env python3
"""Read-only live adapter for the scion-ops new UI evaluation preview."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
FIXTURE_PATH = ROOT / "fixtures" / "preview-fixtures.json"
DEFAULT_STATIC_ROOT = ROOT / "dist"
LIVE_SCHEMA_VERSION = "new-ui-evaluation.live.v1"
EVENT_SCHEMA_VERSION = "new-ui-evaluation.event.v1"
FIXTURE_SCHEMA_VERSION = "new-ui-evaluation.fixture.v1"
READ_ONLY_COMMAND_TIMEOUT_SECONDS = 2
SNAPSHOT_HISTORY_LIMIT = 8
ROUND_ID_RE = re.compile(r"(?:round-)?(?P<id>\d{8}t\d{6}z-[a-z0-9]+)", re.IGNORECASE)

Mode = Literal["live", "fixture"]

API_ROUTES = {
    "/api/fixtures": lambda snapshot: snapshot,
    "/api/snapshot": lambda snapshot: snapshot,
    "/api/overview": lambda snapshot: snapshot["overview"],
    "/api/rounds": lambda snapshot: snapshot["rounds"],
    "/api/inbox": lambda snapshot: snapshot["inbox"],
    "/api/runtime": lambda snapshot: snapshot["runtime"],
    "/api/diagnostics": lambda snapshot: snapshot["diagnostics"],
}

READ_ONLY_MESSAGE = {
    "error": "new-ui-evaluation is read-only",
    "detail": "Only read-only live snapshots, event streams, and explicit fixture fallback reads are served. Mutations are disabled.",
}


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_seconds(value: str | None, *, now: datetime | None = None) -> int | None:
    parsed = parse_iso(value)
    if parsed is None:
        return None
    return max(0, int(((now or utc_now()) - parsed).total_seconds()))


def stable_id(*parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"evt-{digest}"


def read_text(path: Path, *, limit: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def run_read_only_command(args: list[str], cwd: Path = PROJECT_ROOT) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=READ_ONLY_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output


def stable_digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def extract_round_id(*values: Any) -> str:
    for value in values:
        match = ROUND_ID_RE.search(str(value or ""))
        if match:
            return match.group("id")
    return ""


def load_fixtures(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        fixtures = json.load(handle)
    validate_fixture_safety(fixtures)
    return fixtures


def validate_fixture_safety(fixtures: dict[str, Any]) -> None:
    runtime = fixtures.get("runtime", {}).get("previewService", {})
    if fixtures.get("mocked") is not True:
        raise ValueError("preview fixtures must be marked mocked=true")
    if runtime.get("fixtureOnly") is not True:
        raise ValueError("preview service fixtureOnly safeguard must be true")
    if runtime.get("liveReadsAllowed") is not False:
        raise ValueError("preview service liveReadsAllowed safeguard must be false")
    if runtime.get("mutationsAllowed") is not False:
        raise ValueError("preview service mutationsAllowed safeguard must be false")


def fixture_snapshot(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    fixtures = load_fixtures(path)
    generated_at = iso_now()
    source_health = [
        source_state("Fixture", "fixture", "mocked", "Explicit local fixture fallback", generated_at, source_mode="fixture", fallback=True),
        source_state("Adapter", "preview-service", "healthy", "Serving explicit fixture fallback", generated_at, source_mode="fixture", fallback=True),
    ]
    snapshot = {
        **fixtures,
        "schemaVersion": FIXTURE_SCHEMA_VERSION,
        "sourceMode": "fixture",
        "generatedAt": generated_at,
        "cursor": stable_id("fixture", generated_at),
        "sources": source_health,
        "sourceHealth": source_health,
        "connection": {
            "status": "fallback",
            "transport": "fixture",
            "lastEventId": None,
            "lastHeartbeatAt": generated_at,
            "reconnect": {"supported": False, "maxBackoffSeconds": 0},
        },
    }
    snapshot["overview"] = {**snapshot["overview"], "sourceMode": "fixture", "mocked": True}
    snapshot["diagnostics"] = {
        **snapshot["diagnostics"],
        "schemaVersion": FIXTURE_SCHEMA_VERSION,
        "sourceMode": "fixture",
        "sourceHealth": source_health,
    }
    return snapshot


def source_state(
    name: str,
    kind: str,
    status: str,
    detail: str,
    last_seen: str | None,
    *,
    source_mode: str = "live",
    error: str | None = None,
    fallback: bool = False,
) -> dict[str, Any]:
    freshness = age_seconds(last_seen)
    stale = freshness is None or freshness > 300 or status in {"stale", "failed"}
    return {
        "name": name,
        "source": name,
        "kind": kind,
        "status": status,
        "detail": detail,
        "lastSeen": last_seen,
        "lastSuccessfulUpdate": last_seen,
        "freshnessSeconds": freshness,
        "stale": stale,
        "sourceMode": source_mode,
        "fallback": fallback,
        "error": error,
    }


class LiveSourceAggregator:
    """Builds versioned snapshots from local read-only operational sources."""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.project_root = project_root
        self.sessions_root = project_root / ".scion-ops" / "sessions"
        self.openspec_root = project_root / "openspec"
        self._scion_ops_module: Any | None = None

    def build_snapshot(self) -> dict[str, Any]:
        generated_at = iso_now()
        hub_read = self._read_hub_operational(generated_at)
        mcp_read = self._read_mcp_operational(generated_at)
        session_records = self._read_sessions(generated_at, hub_read=hub_read)
        rounds = [record["summary"] for record in session_records]
        round_details = {record["summary"]["id"]: record["detail"] for record in session_records}
        source_health = self._source_health(generated_at, session_records, hub_read=hub_read, mcp_read=mcp_read)
        inbox = self._build_inbox(session_records, source_health, generated_at)
        recent_activity = self._recent_activity(session_records, source_health, generated_at)
        source_errors = self._source_errors(source_health, generated_at)
        snapshot = {
            "schemaVersion": LIVE_SCHEMA_VERSION,
            "sourceMode": "live",
            "mocked": False,
            "generatedAt": generated_at,
            "cursor": "",
            "sources": source_health,
            "sourceHealth": source_health,
            "connection": {
                "status": "live",
                "transport": "sse",
                "lastEventId": "",
                "lastHeartbeatAt": generated_at,
                "reconnect": {"supported": True, "maxBackoffSeconds": 30, "resumeParam": "cursor"},
            },
            "overview": self._overview(rounds, source_health, recent_activity, generated_at),
            "rounds": rounds,
            "roundDetails": round_details,
            "inbox": inbox,
            "runtime": {
                "sources": source_health,
                "previewService": {
                    "name": "scion-ops-new-ui-eval",
                    "port": 8091,
                    "healthPath": "/healthz",
                    "fixtureOnly": False,
                    "liveReadsAllowed": True,
                    "mutationsAllowed": False,
                    "sourceMode": "live",
                    "streamPath": "/api/events",
                    "snapshotPath": "/api/snapshot",
                },
            },
            "diagnostics": {
                "schemaVersion": LIVE_SCHEMA_VERSION,
                "sourceMode": "live",
                "generatedAt": generated_at,
                "sourceErrors": source_errors,
                "sourceHealth": source_health,
                "rawPayloads": self._raw_payloads(session_records, source_health, hub_read=hub_read, mcp_read=mcp_read),
            },
        }
        snapshot["cursor"] = self._snapshot_cursor(snapshot)
        snapshot["connection"]["lastEventId"] = snapshot["cursor"]
        return snapshot

    def _load_scion_ops(self) -> Any | None:
        if self._scion_ops_module is not None:
            return self._scion_ops_module
        module_path = self.project_root / "mcp_servers" / "scion_ops.py"
        if not module_path.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location("new_ui_eval_scion_ops", module_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        except Exception:
            return None
        self._scion_ops_module = module
        return module

    def _read_hub_operational(self, generated_at: str) -> dict[str, Any]:
        module = self._load_scion_ops()
        if module is None or not hasattr(module, "scion_ops_hub_status"):
            return {"ok": False, "status": "degraded", "source": "hub_api", "fallback": True, "generatedAt": generated_at, "error": "MCP Hub read tools unavailable"}
        try:
            status = module.scion_ops_hub_status(project_root=str(self.project_root))
        except Exception as exc:
            return {"ok": False, "status": "degraded", "source": "hub_api", "fallback": True, "generatedAt": generated_at, "error": f"Hub status read failed: {exc}"}
        if not isinstance(status, dict):
            return {"ok": False, "status": "degraded", "source": "hub_api", "fallback": True, "generatedAt": generated_at, "error": "Hub status returned an invalid payload"}
        return {**status, "status": "healthy" if status.get("ok") else "degraded", "fallback": not bool(status.get("ok")), "generatedAt": generated_at}

    def _read_mcp_operational(self, generated_at: str) -> dict[str, Any]:
        url = os.environ.get("SCION_OPS_MCP_URL", "").strip()
        if not url:
            host = os.environ.get("SCION_OPS_MCP_HOST", "127.0.0.1")
            port = os.environ.get("SCION_OPS_MCP_PORT", "8765")
            path = os.environ.get("SCION_OPS_MCP_PATH", "/mcp")
            url = f"http://{host}:{port}{path if path.startswith('/') else '/' + path}"
        req = urllib_request.Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=2) as response:
                return {"ok": True, "status": "healthy", "source": "mcp_http", "url": url, "httpStatus": response.status, "generatedAt": generated_at}
        except urllib_error.HTTPError as exc:
            if exc.code < 500:
                return {"ok": True, "status": "healthy", "source": "mcp_http", "url": url, "httpStatus": exc.code, "generatedAt": generated_at}
            return {"ok": False, "status": "degraded", "source": "mcp_http", "url": url, "httpStatus": exc.code, "fallback": True, "generatedAt": generated_at, "error": f"MCP returned HTTP {exc.code}"}
        except (OSError, TimeoutError, urllib_error.URLError) as exc:
            return {"ok": False, "status": "degraded", "source": "mcp_http", "url": url, "fallback": True, "generatedAt": generated_at, "error": f"MCP read failed: {exc}"}

    def _read_sessions(self, generated_at: str, *, hub_read: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if hub_read and hub_read.get("ok") and isinstance(hub_read.get("agents"), list):
            records = self._records_from_hub(hub_read, generated_at)
            if records:
                return records
        if not self.sessions_root.exists():
            return []
        records: list[dict[str, Any]] = []
        for session_dir in sorted(self.sessions_root.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            findings = sorted((session_dir / "findings").glob("*.json")) if (session_dir / "findings").exists() else []
            handoffs = [payload for payload in (read_json(path) for path in findings) if payload]
            latest_handoff = self._latest_handoff(handoffs)
            updated_at = self._record_timestamp(latest_handoff, session_dir, generated_at)
            round_id = session_dir.name
            blockers = latest_handoff.get("blockers", []) if latest_handoff else []
            status = str(latest_handoff.get("status", "active")) if latest_handoff else "active"
            state = self._status_to_state(status, blockers)
            branch = latest_handoff.get("branch") if latest_handoff else None
            head_sha = latest_handoff.get("head_sha") if latest_handoff else None
            summary_text = latest_handoff.get("summary") if latest_handoff else "Session discovered from .scion-ops metadata"
            changed_files = latest_handoff.get("changed_files", []) if latest_handoff else []
            tests_run = latest_handoff.get("tests_run", []) if latest_handoff else []
            agent = latest_handoff.get("agent", "unknown") if latest_handoff else "unknown"
            summary = {
                "id": round_id,
                "goal": self._goal_from_session(round_id, latest_handoff),
                "state": state,
                "phase": self._phase_from_state(state),
                "owner": agent,
                "agents": sorted({str(payload.get("agent", "unknown")) for payload in handoffs if payload.get("agent")}),
                "branchEvidence": {
                    "branch": branch,
                    "headSha": head_sha,
                    "status": "present" if branch and head_sha else "missing",
                },
                "validation": {
                    "state": "passed" if tests_run and state in {"completed", "accepted"} else ("failed" if state == "failed" else "not-started"),
                    "summary": f"{len(tests_run)} checks recorded" if tests_run else "No validation output recorded",
                },
                "finalReview": {
                    "state": "accepted" if state in {"completed", "accepted"} else ("blocked" if blockers else "waiting"),
                    "summary": "Handoff completed" if state in {"completed", "accepted"} else ("Blocked by recorded handoff blockers" if blockers else "Awaiting review evidence"),
                },
                "blockers": blockers,
                "startedAt": self._session_started_at(round_id),
                "updatedAt": updated_at,
                "latestEvent": summary_text,
                "sourceMode": "live",
                "source": "Hub fallback",
                "fallback": True,
            }
            detail = {
                "id": round_id,
                "decisions": self._decisions_from_handoff(latest_handoff),
                "timeline": self._timeline_from_handoffs(round_id, handoffs, generated_at),
                "participants": [
                    {"agent": str(payload.get("agent", "unknown")), "role": "implementation", "status": str(payload.get("status", "reported"))}
                    for payload in handoffs
                ],
                "validationOutput": {
                    "state": summary["validation"]["state"],
                    "commands": tests_run,
                    "summary": summary["validation"]["summary"],
                },
                "artifacts": self._artifacts_from_handoff(latest_handoff),
                "runnerOutput": summary_text,
                "relatedMessages": [f"msg-{round_id}"] if blockers else [],
                "rawPayloadRef": f"raw-round-{round_id}",
                "sourceMode": "live",
                "fallback": True,
            }
            records.append({"summary": summary, "detail": detail, "raw": latest_handoff or {"session": round_id}})
        return records

    def _records_from_hub(self, hub_read: dict[str, Any], generated_at: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for agent in hub_read.get("agents", []):
            if not isinstance(agent, dict):
                continue
            round_id = extract_round_id(agent.get("name"), agent.get("slug"), agent.get("taskSummary"))
            if round_id:
                grouped.setdefault(round_id, []).append(agent)
        records: list[dict[str, Any]] = []
        for round_id, agents in sorted(grouped.items(), reverse=True):
            latest_agent = max(agents, key=lambda item: str(item.get("updated") or item.get("created") or ""))
            updated_at = str(latest_agent.get("updated") or latest_agent.get("created") or generated_at)
            blockers = [
                str(agent.get("taskSummary"))
                for agent in agents
                if "blocked" in str(agent.get("taskSummary") or agent.get("activity") or "").lower()
            ][:5]
            active = any(str(agent.get("phase") or agent.get("activity") or "").lower() in {"running", "pending", "starting", "idle"} for agent in agents)
            state = "blocked" if blockers else ("active" if active else "completed")
            summary_text = str(latest_agent.get("taskSummary") or f"Hub reported {len(agents)} agents for {round_id}")
            summary = {
                "id": round_id,
                "goal": summary_text.split(".")[0][:120],
                "state": state,
                "phase": self._phase_from_state(state),
                "owner": str(latest_agent.get("name") or latest_agent.get("slug") or "hub"),
                "agents": sorted({str(agent.get("name") or agent.get("slug")) for agent in agents if agent.get("name") or agent.get("slug")}),
                "branchEvidence": {"branch": None, "headSha": self._git_head(), "status": "hub-observed"},
                "validation": {"state": "not-started", "summary": "Validation status read from Hub agent state"},
                "finalReview": {"state": "blocked" if blockers else "waiting", "summary": "Hub operational state"},
                "blockers": blockers,
                "startedAt": self._session_started_at(round_id),
                "updatedAt": updated_at,
                "latestEvent": summary_text,
                "sourceMode": "live",
                "source": "Hub",
                "fallback": False,
            }
            timeline = [
                {
                    "id": stable_id("timeline", round_id, agent.get("name") or agent.get("slug"), agent.get("updated") or index),
                    "timestamp": str(agent.get("updated") or agent.get("created") or generated_at),
                    "actor": str(agent.get("name") or agent.get("slug") or "hub"),
                    "kind": "agent_state",
                    "summary": str(agent.get("taskSummary") or agent.get("activity") or agent.get("phase") or "Hub agent observed"),
                }
                for index, agent in enumerate(agents)
            ]
            detail = {
                "id": round_id,
                "decisions": [item["summary"] for item in timeline[:8]] or ["Hub operational state observed"],
                "timeline": timeline,
                "participants": [{"agent": name, "role": "implementation", "status": "observed"} for name in summary["agents"]],
                "validationOutput": summary["validation"],
                "artifacts": [],
                "runnerOutput": summary_text,
                "relatedMessages": [f"msg-{round_id}"] if blockers else [],
                "rawPayloadRef": f"raw-round-{round_id}",
                "sourceMode": "live",
                "fallback": False,
            }
            records.append({"summary": summary, "detail": detail, "raw": {"hub": hub_read.get("hub"), "agents": agents}})
        return records

    def _source_health(self, generated_at: str, session_records: list[dict[str, Any]], *, hub_read: dict[str, Any], mcp_read: dict[str, Any]) -> list[dict[str, Any]]:
        git_ok, git_detail = run_read_only_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.project_root)
        head_ok, head = run_read_only_command(["git", "rev-parse", "--short=12", "HEAD"], self.project_root)
        kube_ok, kube_detail = run_read_only_command(["kubectl", "get", "pods", "-A", "--request-timeout=1s"], self.project_root)
        openspec_ok = (self.openspec_root / "changes").exists()
        latest_round_update = max((record["summary"]["updatedAt"] for record in session_records), default=generated_at)
        hub_ok = bool(hub_read.get("ok"))
        mcp_ok = bool(mcp_read.get("ok"))
        return [
            source_state("Hub", "control-plane", "healthy" if hub_ok else "degraded", f"Hub API read succeeded with {hub_read.get('agent_count', len(hub_read.get('agents', [])))} agents" if hub_ok else f"Hub API unavailable; using local fallback metadata for {len(session_records)} sessions", latest_round_update if session_records else (generated_at if hub_ok else None), error=None if hub_ok else str(hub_read.get("error") or hub_read.get("error_kind") or "Hub API read failed"), fallback=not hub_ok),
            source_state("MCP", "tooling", "healthy" if mcp_ok else "degraded", f"MCP operational endpoint read succeeded ({mcp_read.get('httpStatus')})" if mcp_ok else "MCP operational endpoint unavailable", generated_at if mcp_ok else None, error=None if mcp_ok else str(mcp_read.get("error") or "MCP operational read failed"), fallback=not mcp_ok),
            source_state("Kubernetes", "orchestration", "healthy" if kube_ok else "degraded", "kubectl read succeeded" if kube_ok else kube_detail[:240] or "kubectl unavailable", generated_at if kube_ok else None, error=None if kube_ok else "kubectl get pods read failed"),
            source_state("Git", "source", "healthy" if git_ok and head_ok else "degraded", f"{git_detail}@{head}" if git_ok and head_ok else git_detail[:240], generated_at if git_ok and head_ok else None, error=None if git_ok and head_ok else "git read failed"),
            source_state("OpenSpec", "specs", "healthy" if openspec_ok else "degraded", "OpenSpec changes directory present" if openspec_ok else "OpenSpec changes directory missing", generated_at if openspec_ok else None, error=None if openspec_ok else "openspec/changes unavailable"),
            source_state("Adapter", "preview-service", "healthy", "Serving live read-only snapshot and SSE contracts", generated_at),
        ]

    def _overview(self, rounds: list[dict[str, Any]], source_health: list[dict[str, Any]], recent_activity: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
        blocked = [round_item for round_item in rounds if round_item["state"] == "blocked"]
        failed = [round_item for round_item in rounds if round_item["state"] == "failed"]
        active = [round_item for round_item in rounds if round_item["state"] in {"active", "running", "waiting", "blocked"}]
        source_statuses = {source["status"] for source in source_health}
        readiness = "degraded" if source_statuses & {"degraded", "failed", "stale"} else "healthy"
        oldest = max((source["freshnessSeconds"] or 0 for source in source_health), default=0)
        attention = blocked[0] if blocked else (failed[0] if failed else (active[0] if active else None))
        return {
            "mocked": False,
            "sourceMode": "live",
            "controlPlane": "scion-ops",
            "summary": "Live read-only operator console snapshot",
            "readiness": readiness,
            "freshness": {"status": "healthy" if oldest <= 300 else "stale", "lastUpdated": generated_at, "oldestSourceAgeSeconds": oldest},
            "counts": {
                "activeRounds": len(active),
                "blockedRounds": len(blocked),
                "failedRounds": len(failed),
                "pendingReviews": len([round_item for round_item in rounds if round_item["finalReview"]["state"] == "waiting"]),
                "unreadMessages": len(blocked) + len(failed),
            },
            "sourceReadiness": [
                {"source": source["name"], "status": source["status"], "freshnessSeconds": source["freshnessSeconds"] or 0}
                for source in source_health
            ],
            "attentionTarget": {
                "label": attention["goal"] if attention else "No active attention target",
                "roundId": attention["id"] if attention else None,
                "reason": attention["latestEvent"] if attention else "No live blockers discovered",
            },
            "recentActivity": recent_activity,
        }

    def _build_inbox(self, session_records: list[dict[str, Any]], source_health: list[dict[str, Any]], generated_at: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for record in session_records:
            summary = record["summary"]
            for blocker in summary["blockers"]:
                messages.append(
                    {
                        "id": stable_id("blocker", summary["id"], blocker),
                        "group": summary["id"],
                        "source": "Hub",
                        "severity": "critical",
                        "timestamp": summary["updatedAt"],
                        "roundId": summary["id"],
                        "title": "Round blocker",
                        "context": str(blocker),
                        "readOnly": True,
                        "sourceMode": "live",
                    }
                )
        for source in source_health:
            if source["error"]:
                messages.append(
                    {
                        "id": stable_id("source-error", source["name"], source["error"]),
                        "group": source["name"],
                        "source": source["name"],
                        "severity": "warning",
                        "timestamp": generated_at,
                        "roundId": None,
                        "title": f"{source['name']} degraded",
                        "context": source["error"],
                        "readOnly": True,
                        "sourceMode": "live",
                    }
                )
        return messages[:40]

    def _recent_activity(self, session_records: list[dict[str, Any]], source_health: list[dict[str, Any]], generated_at: str) -> list[dict[str, Any]]:
        activity = [
            {
                "id": stable_id("activity", record["summary"]["id"], record["summary"]["updatedAt"]),
                "timestamp": record["summary"]["updatedAt"],
                "severity": "critical" if record["summary"]["state"] in {"blocked", "failed"} else "info",
                "summary": record["summary"]["latestEvent"],
                "roundId": record["summary"]["id"],
            }
            for record in session_records[:8]
        ]
        for source in source_health:
            if source["error"]:
                activity.append(
                    {
                        "id": stable_id("source", source["name"], source["status"]),
                        "timestamp": generated_at,
                        "severity": "warning",
                        "summary": f"{source['name']} source is {source['status']}: {source['error']}",
                        "roundId": None,
                    }
                )
        return sorted(activity, key=lambda item: item["timestamp"], reverse=True)[:12]

    def _source_errors(self, source_health: list[dict[str, Any]], generated_at: str) -> list[dict[str, Any]]:
        return [
            {"source": source["name"], "severity": "warning", "message": source["error"], "observedAt": generated_at}
            for source in source_health
            if source["error"]
        ]

    def _raw_payloads(self, session_records: list[dict[str, Any]], source_health: list[dict[str, Any]], *, hub_read: dict[str, Any], mcp_read: dict[str, Any]) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "raw-runtime": {"sources": source_health, "liveReadsAllowed": True, "mutationsAllowed": False, "source": "live-adapter"},
            "raw-openspec": self._openspec_summary(),
            "raw-hub": {key: value for key, value in hub_read.items() if key not in {"agents"}},
            "raw-mcp": mcp_read,
        }
        for record in session_records[:20]:
            raw[f"raw-round-{record['summary']['id']}"] = record["raw"]
        return raw

    def _openspec_summary(self) -> dict[str, Any]:
        change_root = self.openspec_root / "changes" / "wire-new-ui-1"
        tasks = read_text(change_root / "tasks.md")
        return {
            "source": "OpenSpec",
            "change": "wire-new-ui-1",
            "exists": change_root.exists(),
            "completedTasks": tasks.count("- [x]"),
            "pendingTasks": tasks.count("- [ ]"),
        }

    def _latest_handoff(self, handoffs: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not handoffs:
            return None
        return sorted(handoffs, key=lambda payload: json.dumps(payload, sort_keys=True))[-1]

    def _record_timestamp(self, handoff: dict[str, Any] | None, session_dir: Path, fallback: str) -> str:
        for key in ("generatedAt", "updatedAt", "completed_at"):
            value = handoff.get(key) if handoff else None
            if isinstance(value, str) and parse_iso(value):
                return value
        try:
            return datetime.fromtimestamp(session_dir.stat().st_mtime, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except OSError:
            return fallback

    def _status_to_state(self, status: str, blockers: list[Any]) -> str:
        normalized = status.lower()
        if blockers:
            return "blocked"
        if normalized in {"completed", "accepted"}:
            return "completed"
        if normalized in {"failed", "error"}:
            return "failed"
        return "active"

    def _phase_from_state(self, state: str) -> str:
        return {"blocked": "review", "failed": "validation", "completed": "archived"}.get(state, "implementation")

    def _goal_from_session(self, round_id: str, handoff: dict[str, Any] | None) -> str:
        summary = str(handoff.get("summary", "")) if handoff else ""
        return summary.split(".")[0][:120] if summary else f"Session {round_id}"

    def _session_started_at(self, round_id: str) -> str | None:
        prefix = round_id.removeprefix("round-").split("-")[0]
        try:
            return datetime.strptime(prefix, "%Y%m%dt%H%M%Sz").replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        except ValueError:
            return None

    def _decisions_from_handoff(self, handoff: dict[str, Any] | None) -> list[str]:
        if not handoff:
            return ["Live session discovered; no handoff decisions recorded"]
        tasks = handoff.get("tasks_completed", [])
        return [str(task) for task in tasks[:8]] or ["No completed task decisions recorded"]

    def _timeline_from_handoffs(self, round_id: str, handoffs: list[dict[str, Any]], generated_at: str) -> list[dict[str, Any]]:
        if not handoffs:
            return [{"id": stable_id("timeline", round_id), "timestamp": generated_at, "actor": "adapter", "kind": "discovered", "summary": "Session discovered from live metadata"}]
        return [
            {
                "id": stable_id("timeline", round_id, payload.get("agent", "unknown"), index),
                "timestamp": str(payload.get("generatedAt") or payload.get("updatedAt") or generated_at),
                "actor": str(payload.get("agent", "unknown")),
                "kind": "handoff",
                "summary": str(payload.get("summary", "Handoff recorded")),
            }
            for index, payload in enumerate(handoffs)
        ]

    def _artifacts_from_handoff(self, handoff: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not handoff:
            return []
        artifacts = []
        if handoff.get("branch"):
            artifacts.append({"label": "implementation branch", "path": handoff["branch"], "kind": "git-branch"})
        for path in handoff.get("changed_files", [])[:20]:
            artifacts.append({"label": Path(str(path)).name, "path": str(path), "kind": "changed-file"})
        return artifacts

    def _git_head(self) -> str:
        ok, head = run_read_only_command(["git", "rev-parse", "--short=12", "HEAD"], self.project_root)
        return head if ok else "unknown"

    def _snapshot_cursor(self, snapshot: dict[str, Any]) -> str:
        payload = {
            "rounds": [
                {
                    "id": row.get("id"),
                    "state": row.get("state"),
                    "updatedAt": row.get("updatedAt"),
                    "latestEvent": row.get("latestEvent"),
                    "blockers": row.get("blockers"),
                    "branchEvidence": row.get("branchEvidence"),
                }
                for row in snapshot.get("rounds", [])
                if isinstance(row, dict)
            ],
            "inbox": snapshot.get("inbox"),
            "sources": [
                {
                    "name": source.get("name"),
                    "status": source.get("status"),
                    "detail": source.get("detail"),
                    "error": source.get("error"),
                    "fallback": source.get("fallback"),
                    "stale": source.get("stale"),
                }
                for source in snapshot.get("sourceHealth", [])
                if isinstance(source, dict)
            ],
            "openspec": snapshot.get("diagnostics", {}).get("rawPayloads", {}).get("raw-openspec"),
            "git": self._git_head(),
        }
        return f"live:{stable_digest(payload)}"


def build_event(event_type: str, source: str, payload: dict[str, Any], *, entity_id: str | None = None, cursor: str | None = None) -> dict[str, Any]:
    timestamp = iso_now()
    event_id = stable_id(EVENT_SCHEMA_VERSION, event_type, source, entity_id, cursor or stable_digest(payload), json.dumps(payload, sort_keys=True, default=str))
    return {
        "schemaVersion": EVENT_SCHEMA_VERSION,
        "type": event_type,
        "id": event_id,
        "eventId": event_id,
        "entityId": entity_id,
        "source": source,
        "timestamp": timestamp,
        "version": cursor or event_id,
        "cursor": cursor or event_id,
        "payload": payload,
        "sourceStatus": payload.get("status"),
        "stale": payload.get("stale", False),
        "error": payload.get("error"),
    }


def event_batch(snapshot: dict[str, Any], *, cursor: str = "") -> dict[str, Any]:
    heartbeat = build_event(
        "heartbeat",
        "Adapter",
        {"status": "live", "sourceMode": snapshot["sourceMode"], "generatedAt": snapshot["generatedAt"]},
        cursor=snapshot["cursor"],
    )
    events = [heartbeat]
    for source in snapshot.get("sourceHealth", []):
        if source.get("error") or source.get("stale"):
            events.append(build_event("source_status", source["name"], source, entity_id=source["name"], cursor=snapshot["cursor"]))
    if not cursor:
        events.append(
            build_event(
                "snapshot_ready",
                "Adapter",
                {"status": "live", "snapshotCursor": snapshot["cursor"], "schemaVersion": snapshot["schemaVersion"]},
                cursor=snapshot["cursor"],
            )
        )
    return {"cursor": snapshot["cursor"], "events": events}


def snapshot_replacement_event(snapshot: dict[str, Any], *, requested_cursor: str) -> dict[str, Any]:
    return build_event(
        "snapshot_ready",
        "Adapter",
        {
            "status": "snapshot_recovery",
            "reason": "requested cursor is no longer available for incremental replay",
            "requestedCursor": requested_cursor,
            "snapshotCursor": snapshot["cursor"],
            "schemaVersion": snapshot["schemaVersion"],
            "snapshot": snapshot,
        },
        cursor=snapshot["cursor"],
    )


def _items_by_id(items: list[dict[str, Any]], key: str = "id") -> dict[str, dict[str, Any]]:
    return {str(item.get(key)): item for item in items if isinstance(item, dict) and item.get(key)}


def incremental_events(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    cursor = current["cursor"]
    events: list[dict[str, Any]] = []
    previous_rounds = _items_by_id(previous.get("rounds", []))
    for round_item in current.get("rounds", []):
        if not isinstance(round_item, dict):
            continue
        round_id = str(round_item.get("id") or "")
        comparable = {
            "state": round_item.get("state"),
            "updatedAt": round_item.get("updatedAt"),
            "latestEvent": round_item.get("latestEvent"),
            "blockers": round_item.get("blockers"),
            "branchEvidence": round_item.get("branchEvidence"),
        }
        previous_item = previous_rounds.get(round_id, {})
        previous_comparable = {
            "state": previous_item.get("state"),
            "updatedAt": previous_item.get("updatedAt"),
            "latestEvent": previous_item.get("latestEvent"),
            "blockers": previous_item.get("blockers"),
            "branchEvidence": previous_item.get("branchEvidence"),
        }
        if comparable != previous_comparable:
            events.append(build_event("round_updated", str(round_item.get("source") or "Hub"), round_item, entity_id=round_id, cursor=cursor))

    previous_details = previous.get("roundDetails", {}) if isinstance(previous.get("roundDetails"), dict) else {}
    for round_id, detail in (current.get("roundDetails", {}) or {}).items():
        if not isinstance(detail, dict):
            continue
        old_entries = _items_by_id((previous_details.get(round_id) or {}).get("timeline", []) if isinstance(previous_details.get(round_id), dict) else [])
        for entry in detail.get("timeline", []):
            if isinstance(entry, dict) and entry.get("id") and old_entries.get(str(entry["id"])) != entry:
                events.append(build_event("timeline_entry", "Hub", {"roundId": round_id, "entry": entry}, entity_id=str(entry["id"]), cursor=cursor))

    previous_inbox = _items_by_id(previous.get("inbox", []))
    for item in current.get("inbox", []):
        if isinstance(item, dict) and item.get("id") and previous_inbox.get(str(item["id"])) != item:
            events.append(build_event("inbox_item", str(item.get("source") or "Hub"), item, entity_id=str(item["id"]), cursor=cursor))

    previous_sources = _items_by_id(previous.get("sourceHealth", []), key="name")
    runtime_changed = False
    for source in current.get("sourceHealth", []):
        if not isinstance(source, dict):
            continue
        name = str(source.get("name") or "")
        comparable = {key: source.get(key) for key in ("status", "detail", "error", "stale", "fallback")}
        previous_comparable = {key: previous_sources.get(name, {}).get(key) for key in ("status", "detail", "error", "stale", "fallback")}
        if comparable != previous_comparable:
            runtime_changed = True
            events.append(build_event("source_status", name, source, entity_id=name, cursor=cursor))
            if source.get("stale"):
                events.append(build_event("stale", name, source, entity_id=name, cursor=cursor))
            if source.get("fallback"):
                events.append(build_event("fallback", name, source, entity_id=name, cursor=cursor))
    if runtime_changed:
        events.append(build_event("runtime_health", "Adapter", {"sources": current.get("sourceHealth", [])}, cursor=cursor))

    previous_errors = previous.get("diagnostics", {}).get("sourceErrors", [])
    current_errors = current.get("diagnostics", {}).get("sourceErrors", [])
    if previous_errors != current_errors:
        events.append(build_event("diagnostic", "Adapter", {"sourceErrors": current_errors}, cursor=cursor))
    return events


class PreviewHandler(BaseHTTPRequestHandler):
    server_version = "ScionOpsNewUiEvaluation/0.2"

    def do_GET(self) -> None:
        self._handle_read()

    def do_HEAD(self) -> None:
        self._handle_read(head_only=True)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_POST(self) -> None:
        self._reject_mutation()

    def do_PUT(self) -> None:
        self._reject_mutation()

    def do_PATCH(self) -> None:
        self._reject_mutation()

    def do_DELETE(self) -> None:
        self._reject_mutation()

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    @property
    def mode(self) -> Mode:
        return self.server.mode  # type: ignore[attr-defined]

    @property
    def static_root(self) -> Path:
        return self.server.static_root  # type: ignore[attr-defined]

    @property
    def fixture_path(self) -> Path:
        return self.server.fixture_path  # type: ignore[attr-defined]

    @property
    def aggregator(self) -> LiveSourceAggregator:
        return self.server.aggregator  # type: ignore[attr-defined]

    def snapshot(self) -> dict[str, Any]:
        if self.mode == "fixture":
            return fixture_snapshot(self.fixture_path)
        return self.aggregator.build_snapshot()

    def _remember_snapshot(self, snapshot: dict[str, Any]) -> None:
        cursor = snapshot.get("cursor")
        if not isinstance(cursor, str) or not cursor:
            return
        with self.server.snapshot_history_lock:  # type: ignore[attr-defined]
            history = self.server.snapshot_history  # type: ignore[attr-defined]
            if cursor in history:
                history.pop(cursor)
            history[cursor] = snapshot
            while len(history) > SNAPSHOT_HISTORY_LIMIT:
                oldest_cursor = next(iter(history))
                history.pop(oldest_cursor)

    def _reconnect_events(self, requested_cursor: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        if not requested_cursor or requested_cursor == snapshot.get("cursor"):
            return []
        with self.server.snapshot_history_lock:  # type: ignore[attr-defined]
            previous_snapshot = self.server.snapshot_history.get(requested_cursor)  # type: ignore[attr-defined]
        if previous_snapshot is None:
            return [snapshot_replacement_event(snapshot, requested_cursor=requested_cursor)]
        return incremental_events(previous_snapshot, snapshot)

    def _handle_read(self, head_only: bool = False) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/healthz":
            generated_at = iso_now()
            self._json(
                {
                    "status": "ok",
                    "schemaVersion": LIVE_SCHEMA_VERSION if self.mode == "live" else FIXTURE_SCHEMA_VERSION,
                    "sourceMode": self.mode,
                    "mocked": self.mode == "fixture",
                    "liveReadsAllowed": self.mode == "live",
                    "mutationsAllowed": False,
                    "streamPath": "/api/events" if self.mode == "live" else None,
                    "generatedAt": generated_at,
                },
                head_only=head_only,
            )
            return
        if path == "/api/events":
            self._sse(parse_qs(parsed.query), head_only=head_only)
            return
        snapshot = self.snapshot()
        if path in API_ROUTES:
            self._json(API_ROUTES[path](snapshot), head_only=head_only)
            return
        if path.startswith("/api/rounds/"):
            round_id = unquote(path.removeprefix("/api/rounds/"))
            detail = snapshot.get("roundDetails", {}).get(round_id)
            if detail is None:
                self._json({"error": "round detail not found", "roundId": round_id, "sourceMode": self.mode}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
                return
            self._json(detail, head_only=head_only)
            return
        if path.startswith("/api/"):
            self._json({"error": "unknown preview endpoint", "sourceMode": self.mode}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
            return
        self._static(path, head_only=head_only)

    def _sse(self, query: dict[str, list[str]], *, head_only: bool = False) -> None:
        if self.mode != "live":
            self._json({"error": "event stream is only available in live mode", "sourceMode": self.mode}, status=HTTPStatus.CONFLICT, head_only=head_only)
            return
        requested_cursor = query.get("cursor", [""])[0]
        snapshot = self.snapshot()
        reconnect_events = self._reconnect_events(requested_cursor, snapshot)
        self._remember_snapshot(snapshot)
        batch = event_batch(snapshot, cursor=requested_cursor)
        batch["events"].extend(reconnect_events)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if head_only:
            return
        for event in batch["events"]:
            self._write_sse_event(event)
        self.wfile.flush()
        if query.get("once", ["0"])[0] == "1":
            self.close_connection = True
            return
        deadline = time.monotonic() + max(1, min(int(query.get("seconds", ["30"])[0]), 60))
        interval = max(0.1, min(float(query.get("interval", ["2"])[0]), 15.0))
        previous_snapshot = snapshot
        while time.monotonic() < deadline:
            time.sleep(interval)
            current_snapshot = self.snapshot()
            events = incremental_events(previous_snapshot, current_snapshot)
            if events:
                previous_snapshot = current_snapshot
                batch["cursor"] = current_snapshot["cursor"]
            heartbeat = build_event(
                "heartbeat",
                "Adapter",
                {"status": "live", "sourceMode": "live", "generatedAt": iso_now()},
                cursor=batch["cursor"],
            )
            try:
                for event in events:
                    self._write_sse_event(event)
                self._write_sse_event(heartbeat)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        self.close_connection = True

    def _write_sse_event(self, event: dict[str, Any]) -> None:
        data = json.dumps(event, sort_keys=True, default=str)
        frame = f"id: {event.get('cursor') or event.get('id') or ''}\nevent: {event.get('type') or 'message'}\ndata: {data}\n\n"
        self.wfile.write(frame.encode("utf-8"))

    def _static(self, request_path: str, head_only: bool = False) -> None:
        relative = request_path.lstrip("/") or "index.html"
        candidate = (self.static_root / relative).resolve()
        static_root = self.static_root.resolve()
        if static_root not in candidate.parents and candidate != static_root:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists():
            candidate = static_root / "index.html"
        if not candidate.exists():
            self._json({"error": "static build not found", "hint": "run npm run build in new-ui-evaluation"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK, head_only: bool = False) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _reject_mutation(self) -> None:
        self._json(READ_ONLY_MESSAGE, status=HTTPStatus.METHOD_NOT_ALLOWED)


def build_server(host: str, port: int, static_root: Path, fixture_path: Path, *, mode: Mode = "live", project_root: Path = PROJECT_ROOT) -> ThreadingHTTPServer:
    if mode not in {"live", "fixture"}:
        raise ValueError("mode must be live or fixture")
    if mode == "fixture":
        load_fixtures(fixture_path)
    server = ThreadingHTTPServer((host, port), PreviewHandler)
    server.mode = mode  # type: ignore[attr-defined]
    server.static_root = static_root  # type: ignore[attr-defined]
    server.fixture_path = fixture_path  # type: ignore[attr-defined]
    server.aggregator = LiveSourceAggregator(project_root)  # type: ignore[attr-defined]
    server.snapshot_history = {}  # type: ignore[attr-defined]
    server.snapshot_history_lock = threading.Lock()  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the read-only scion-ops new UI evaluation preview.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8091, type=int)
    parser.add_argument("--static-root", default=str(DEFAULT_STATIC_ROOT))
    parser.add_argument("--fixture-path", default=str(FIXTURE_PATH))
    parser.add_argument("--mode", choices=["live", "fixture"], default=os.environ.get("NEW_UI_EVALUATION_MODE", "live"))
    args = parser.parse_args()

    server = build_server(args.host, args.port, Path(args.static_root), Path(args.fixture_path), mode=args.mode)
    print(f"serving new-ui-evaluation in {args.mode} mode on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
