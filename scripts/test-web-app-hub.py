#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "PyYAML>=6,<7",
# ]
# ///
"""Fixture tests for the read-only web app hub adapter."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("web_app_hub", ROOT / "scripts" / "web_app_hub.py")
assert SPEC and SPEC.loader
web_app_hub = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web_app_hub)


class FixtureProvider:
    def __init__(
        self,
        *,
        hub=None,
        messages=None,
        notifications=None,
        mcp=None,
        k8s=None,
        round_outcome=None,
        round_events=None,
        round_artifacts=None,
        spec_status=None,
    ) -> None:
        self._hub = hub if hub is not None else healthy_hub()
        self._messages = messages if messages is not None else healthy_messages()
        self._notifications = notifications if notifications is not None else healthy_notifications()
        self._mcp = mcp if mcp is not None else {"source": "mcp", "ok": True, "status": "healthy"}
        self._k8s = k8s if k8s is not None else healthy_k8s()
        self._round_outcome = round_outcome if round_outcome is not None else {"status": "completed"}
        self._round_events = round_events
        self._round_artifacts = round_artifacts if round_artifacts is not None else {}
        self._spec_status = spec_status if spec_status is not None else {}

    def hub_status(self):
        return self._hub

    def hub_messages(self):
        return self._messages

    def hub_notifications(self):
        return self._notifications

    def mcp_status(self):
        return self._mcp

    def kubernetes_status(self):
        return self._k8s

    def round_status(self, round_id):
        return {"ok": True, "round_id": round_id, "agents": self._hub.get("agents", []), "outcome": self._round_outcome}

    def round_events(self, round_id, cursor="", include_existing=False):
        if self._round_events is not None:
            return self._round_events
        return {
            "ok": True,
            "round_id": round_id,
            "cursor": "cursor-1",
            "events": [
                {"type": "message", "message": {"createdAt": "2026-05-09T06:35:00+00:00", "msg": f"round {round_id} update"}}
            ],
        }

    def round_artifacts(self, round_id):
        return self._round_artifacts

    def spec_status(self, project_root, change=""):
        return self._spec_status


def healthy_hub():
    return {
        "ok": True,
        "source": "hub_api",
        "hub": {"endpoint": "http://hub", "grove_id": "grove-1"},
        "health": {"ok": True},
        "grove": {"id": "grove-1"},
        "brokers": [{"id": "broker-1", "name": "kind"}],
        "providers": [{"id": "provider-1"}],
        "agents": [
            {
                "name": "round-20260509t063201z-6c02-consensus",
                "template": "consensus-runner",
                "phase": "running",
                "activity": "active",
                "taskSummary": "dispatching child agents",
                "created": "2026-05-09T06:32:01+00:00",
                "updated": "2026-05-09T06:36:01+00:00",
            },
            {
                "name": "round-20260509t063201z-6c02-codex",
                "template": "codex",
                "phase": "completed",
                "activity": "completed",
                "taskSummary": "complete: round-20260509t063201z-6c02-impl-codex",
                "created": "2026-05-09T06:33:01+00:00",
                "updated": "2026-05-09T06:37:01+00:00",
            },
        ],
    }


def healthy_messages():
    return {
        "ok": True,
        "source": "hub_api",
        "items": [
            {
                "id": "msg-1",
                "sender": "round-20260509t063201z-6c02-codex",
                "msg": "round 20260509t063201z-6c02 task_completed",
                "createdAt": "2026-05-09T06:38:01+00:00",
            }
        ],
    }


def healthy_notifications():
    return {
        "ok": True,
        "source": "hub_api",
        "items": [
            {
                "id": "note-1",
                "agentId": "round-20260509t063201z-6c02-codex",
                "summary": "final outcome accepted",
                "createdAt": "2026-05-09T06:39:01+00:00",
            }
        ],
    }


def healthy_k8s():
    return {
        "source": "kubernetes",
        "ok": True,
        "status": "healthy",
        "deployments": [
            {"name": "scion-hub", "desired": 1, "available": 1, "ready": True},
            {"name": "scion-broker", "desired": 1, "available": 1, "ready": True},
            {"name": "scion-ops-mcp", "desired": 1, "available": 1, "ready": True},
            {"name": "scion-ops-web-app", "desired": 1, "available": 1, "ready": True},
        ],
        "pods": [],
        "services": [
            {"name": "scion-hub", "type": "ClusterIP"},
            {"name": "scion-ops-mcp", "type": "ClusterIP"},
            {"name": "scion-ops-web-app", "type": "ClusterIP"},
        ],
        "endpoints": [
            {"name": "scion-hub", "address_count": 1, "ready": True},
            {"name": "scion-ops-mcp", "address_count": 1, "ready": True},
            {"name": "scion-ops-web-app", "address_count": 1, "ready": True},
        ],
    }


def healthy_round_artifacts():
    return {
        "source": "local_git",
        "branches": ["round-20260509t063201z-6c02-impl-codex"],
        "remote_branches": [
            {"branch": "round-20260509t063201z-6c02-impl-codex", "sha": "abc123"},
        ],
        "workspaces": [],
        "prompts": [],
    }


def test_health_response_is_runtime_independent():
    original = web_app_hub.utc_now
    try:
        web_app_hub.utc_now = lambda: "2026-05-09T06:39:30+00:00"
        payload = web_app_hub.build_health()
    finally:
        web_app_hub.utc_now = original
    assert payload == {
        "ok": True,
        "status": "healthy",
        "service": "scion-ops-web-app",
        "generated_at": "2026-05-09T06:39:30+00:00",
    }


def test_runtime_provider_round_status_uses_structured_state_without_transcript():
    original = web_app_hub.scion_ops.scion_ops_round_status
    calls = []
    try:
        def fake_round_status(**kwargs):
            calls.append(kwargs)
            return {"ok": True, "agents": []}

        web_app_hub.scion_ops.scion_ops_round_status = fake_round_status
        payload = web_app_hub.RuntimeProvider().round_status("20260509t063201z-6c02")
    finally:
        web_app_hub.scion_ops.scion_ops_round_status = original
    assert payload["ok"] is True
    assert calls[0]["include_transcript"] is False


def test_transcript_display_suppresses_hub_terminal_capture_404():
    raw = (
        "Using hub: http://scion-hub:8090\n"
        "Error: failed to capture terminal output for agent "
        "'round-20260510t084647z-0b23-implementation-steward': "
        "not_found: Action not found (status: 404)\n"
        "Usage: scion look <agent> [flags]"
    )
    output, error = web_app_hub.transcript_display({"ok": False, "output": raw})
    assert output == ""
    assert error == "Terminal output unavailable from Hub for this agent."
    assert "Usage: scion look" not in error


def test_healthy_snapshot_is_ready():
    original = web_app_hub.utc_now
    try:
        web_app_hub.utc_now = lambda: "2026-05-09T06:39:30+00:00"
        snapshot = web_app_hub.build_snapshot(FixtureProvider())
    finally:
        web_app_hub.utc_now = original
    assert snapshot["readiness"] == "ready"
    assert snapshot["overview"]["active_round_count"] == 1
    assert snapshot["rounds"][0]["round_id"] == "20260509t063201z-6c02"
    assert snapshot["inbox"][0]["round_id"] == "20260509t063201z-6c02"
    assert "mcp" in web_app_hub.BROWSER_JSON_CONTRACT["round"]


def test_empty_snapshot_distinguishes_no_rounds_from_source_failure():
    provider = FixtureProvider(
        hub={**healthy_hub(), "agents": []},
        messages={"ok": True, "source": "hub_api", "items": []},
        notifications={"ok": True, "source": "hub_api", "items": []},
    )
    snapshot = web_app_hub.build_snapshot(provider)
    assert snapshot["sources"]["messages"]["ok"] is True
    assert snapshot["rounds"] == []
    assert snapshot["inbox"] == []


def test_blocked_round_is_listed_as_blocked():
    hub = healthy_hub()
    hub["agents"][0] = {
        **hub["agents"][0],
        "phase": "error",
        "activity": "limits_exceeded",
        "taskSummary": "blocked waiting for operator",
    }
    snapshot = web_app_hub.build_snapshot(FixtureProvider(hub=hub))
    assert snapshot["rounds"][0]["status"] == "blocked"


def test_stale_round_degrades_readiness():
    old_hub = healthy_hub()
    for agent in old_hub["agents"]:
        agent["updated"] = "2026-05-09T06:00:00+00:00"
    original = web_app_hub.utc_now
    try:
        web_app_hub.utc_now = lambda: "2026-05-09T06:40:00+00:00"
        snapshot = web_app_hub.build_snapshot(
            FixtureProvider(
                hub=old_hub,
                messages={"ok": True, "items": []},
                notifications={"ok": True, "items": []},
            )
        )
    finally:
        web_app_hub.utc_now = original
    assert snapshot["stale"] is True
    assert snapshot["readiness"] == "degraded"


def test_unavailable_sources_preserve_partial_data():
    provider = FixtureProvider(
        mcp={"source": "mcp", "ok": False, "status": "unavailable", "error_kind": "runtime", "error": "connection refused"},
        k8s={"source": "kubernetes", "ok": False, "status": "unavailable", "error_kind": "runtime", "error": "kubectl missing"},
    )
    snapshot = web_app_hub.build_snapshot(provider)
    assert snapshot["readiness"] == "degraded"
    assert snapshot["sources"]["hub"]["ok"] is True
    assert snapshot["sources"]["mcp"]["error_kind"] == "runtime"


def test_kubernetes_normalization_reports_missing_control_plane():
    payload = {"items": [{"kind": "Deployment", "metadata": {"name": "scion-hub", "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}}, "spec": {"replicas": 1}, "status": {"availableReplicas": 1}}]}
    status = web_app_hub.normalize_kubernetes(payload, namespace="scion-agents")
    assert status["status"] == "degraded"
    assert "scion-broker" in status["missing_deployments"]
    assert "scion-ops-mcp" in status["missing_deployments"]
    assert "scion-ops-web-app" in status["missing_deployments"]
    assert "scion-ops-web-app" in status["missing_services"]
    assert "scion-ops-web-app" in status["missing_endpoints"]


def test_run_command_keeps_kubectl_warnings_out_of_json_stdout():
    result = web_app_hub.run_command(
        [
            web_app_hub.sys.executable,
            "-c",
            "import sys; sys.stderr.write('Warning: deprecated\\n'); print('{\"ok\": true}')",
        ]
    )
    assert result["ok"] is True
    assert result["output"].strip() == '{"ok": true}'
    assert json.loads(result["output"]) == {"ok": True}


def test_web_app_component_participates_in_readiness():
    k8s = healthy_k8s()
    k8s["deployments"] = [item for item in k8s["deployments"] if item["name"] != "scion-ops-web-app"]
    snapshot = web_app_hub.build_snapshot(FixtureProvider(k8s=k8s))
    assert snapshot["readiness"] == "degraded"
    assert snapshot["sources"]["web_app"]["status"] == "degraded"
    assert "deployment" in snapshot["sources"]["web_app"]["missing"]


def test_kubernetes_normalization_requires_web_app_service_and_endpoint():
    payload = {
        "items": [
            {
                "kind": "Deployment",
                "metadata": {"name": name, "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}},
                "spec": {"replicas": 1},
                "status": {"replicas": 1, "availableReplicas": 1},
            }
            for name in sorted(web_app_hub.CONTROL_PLANE_NAMES)
        ]
        + [
            {
                "kind": "Service",
                "metadata": {"name": name, "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}},
                "spec": {"type": "ClusterIP"},
            }
            for name in sorted(web_app_hub.CONTROL_PLANE_SERVICES - {"scion-ops-web-app"})
        ]
        + [
            {
                "kind": "Endpoints",
                "metadata": {"name": name, "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}},
                "subsets": [{"addresses": [{"ip": "10.0.0.1"}]}],
            }
            for name in sorted(web_app_hub.CONTROL_PLANE_SERVICES - {"scion-ops-web-app"})
        ]
    }
    status = web_app_hub.normalize_kubernetes(payload, namespace="scion-agents")
    assert status["status"] == "degraded"
    assert status["missing_deployments"] == []
    assert status["missing_services"] == ["scion-ops-web-app"]
    assert status["missing_endpoints"] == ["scion-ops-web-app"]


def test_structured_branch_fields_take_precedence_over_fallback_text_and_names():
    hub = healthy_hub()
    hub["agents"] = [
        {
            "name": "round-20260509t063201z-6c02-name-derived",
            "slug": "round-20260509t063201z-6c02-slug-derived",
            "template": "codex",
            "phase": "completed",
            "activity": "completed",
            "branch": "structured/authoritative",
            "taskSummary": "complete: round-20260509t063201z-6c02-fallback",
            "created": "2026-05-09T06:33:01+00:00",
            "updated": "2026-05-09T06:37:01+00:00",
        }
    ]
    snapshot = web_app_hub.build_snapshot(FixtureProvider(hub=hub, messages={"ok": True, "items": []}, notifications={"ok": True, "items": []}))
    row = snapshot["rounds"][0]
    assert row["branches"] == ["structured/authoritative"]
    assert row["branch_source"] == "structured"
    assert "round-20260509t063201z-6c02-fallback" not in row["branches"]
    assert "round-20260509t063201z-6c02-name-derived" not in row["branches"]
    assert "round-20260509t063201z-6c02-slug-derived" not in row["branches"]


def test_final_review_accept_is_exposed_by_backend_and_frontend_template():
    notifications = {
        "ok": True,
        "items": [
            {
                "id": "final-accept",
                "agentId": "round-20260509t063201z-6c02-final-review",
                "summary": '{"reviewer":"final-codex","verdict":"accept","branch":"round-20260509t063201z-6c02-final"}',
                "createdAt": "2026-05-09T06:41:01+00:00",
            }
        ],
    }
    snapshot = web_app_hub.build_snapshot(FixtureProvider(notifications=notifications))
    row = snapshot["rounds"][0]
    assert row["final_review"]["normalized_verdict"] == "accept"
    assert row["visible_status"] == "accepted"
    assert "Final Review" in web_app_hub.INDEX_HTML
    assert "visible_status" in web_app_hub.INDEX_HTML
    assert "review.display" in web_app_hub.INDEX_HTML


def test_final_review_changes_requested_is_not_collapsed_to_completed():
    notifications = {
        "ok": True,
        "items": [
            {
                "id": "final-request-changes",
                "agentId": "round-20260509t063201z-6c02-final-review",
                "summary": '{"reviewer":"final-gemini","verdict":"changes_requested","summary":"blocking issue found"}',
                "createdAt": "2026-05-09T06:41:01+00:00",
            }
        ],
    }
    outcome = {
        "status": "blocked",
        "source": "final_review_message",
        "final_review": {
            "source": "final_review_message",
            "created": "2026-05-09T06:41:01+00:00",
            "verdict": "changes_requested",
            "normalized_verdict": "request_changes",
            "notes": "blocking issue found",
        },
    }
    provider = FixtureProvider(notifications=notifications, round_outcome=outcome)
    snapshot = web_app_hub.build_snapshot(provider)
    row = snapshot["rounds"][0]
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    assert row["status"] == "blocked"
    assert row["visible_status"] == "changes requested"
    assert row["visible_status"] != "completed"
    assert detail["final_review"]["display"] == "changes requested"


def test_final_review_blocked_verdict_is_exposed():
    notifications = {
        "ok": True,
        "items": [
            {
                "id": "final-blocked",
                "agentId": "round-20260509t063201z-6c02-final-review",
                "summary": '{"reviewer":"final-claude","verdict":"blocked","summary":"implementation does not meet spec"}',
                "createdAt": "2026-05-09T06:41:01+00:00",
            }
        ],
    }
    snapshot = web_app_hub.build_snapshot(FixtureProvider(notifications=notifications))
    row = snapshot["rounds"][0]
    assert row["final_review"]["normalized_verdict"] == "blocked"
    assert row["status"] == "blocked"
    assert row["visible_status"] == "blocked"


def test_outcome_only_final_review_visible_in_rounds_list():
    # No final_review verdict in messages or notifications - only in outcome state
    messages = {"ok": True, "items": []}
    notifications = {
        "ok": True,
        "items": [
            {
                "id": "note-plain",
                "agentId": "round-20260509t063201z-6c02-codex",
                "summary": "round 20260509t063201z-6c02 completed",
                "createdAt": "2026-05-09T06:38:00+00:00",
            }
        ],
    }
    outcome = {
        "source": "final_review_outcome",
        "final_review": {
            "source": "outcome",
            "created": "2026-05-09T06:42:00+00:00",
            "verdict": "accept",
            "normalized_verdict": "accept",
            "summary": "all requirements met",
        },
    }
    provider = FixtureProvider(messages=messages, notifications=notifications, round_outcome=outcome)
    snapshot = web_app_hub.build_snapshot(provider)
    row = snapshot["rounds"][0]
    assert row["final_review"]["normalized_verdict"] == "accept", "outcome-only final_review must be visible in rounds list"
    assert row["visible_status"] == "accepted"


def test_spec_round_progress_fields_are_preserved_from_structured_payloads():
    progress = {
        "ok": False,
        "source": "spec_round_runner",
        "status": "blocked",
        "health": "blocked",
        "summary": "round 20260509t063201z-6c02 blocked agents=3 active=0 complete=3 unhealthy=0 validation=failed",
        "project_root": "/workspace/example",
        "change": "update-web-app",
        "base_branch": "main",
        "expected_branch": "round-20260509t063201z-6c02-spec-integration",
        "pr_ready_branch": "",
        "remote_branch_sha": "def456",
        "base_branch_sha": "abc123",
        "branch_changed": True,
        "validation_status": "failed",
        "validation": {"ok": False, "errors": [{"message": "missing scenario"}]},
        "protocol": {"integration_branch_valid": False, "ops_review_complete": True, "finalizer_complete": False, "complete": False},
        "blockers": ["OpenSpec validation failed on the remote branch"],
        "warnings": ["integration branch validates; waiting for spec finalizer"],
        "progress_lines": ["blocker OpenSpec validation failed on the remote branch"],
    }
    messages = {
        "ok": True,
        "items": [
            {
                "id": "spec-progress",
                "sender": "round-20260509t063201z-6c02-consensus",
                "msg": json.dumps(progress),
                "createdAt": "2026-05-09T06:42:01+00:00",
            }
        ],
    }
    snapshot = web_app_hub.build_snapshot(FixtureProvider(messages=messages, notifications={"ok": True, "items": []}))
    row = snapshot["rounds"][0]
    assert row["status"] == "blocked"
    assert row["mcp"]["expected_branch"] == "round-20260509t063201z-6c02-spec-integration"
    assert row["mcp"]["remote_branch_sha"] == "def456"
    assert row["mcp"]["branch_changed"] is True
    assert row["mcp"]["validation_status"] == "failed"
    assert row["mcp"]["blockers"] == ["OpenSpec validation failed on the remote branch"]
    assert "expected_branch" in web_app_hub.INDEX_HTML
    assert "MCP State" in web_app_hub.INDEX_HTML


def test_round_artifacts_remote_branches_are_exposed_in_row_and_detail():
    artifacts = {
        "source": "local_git",
        "branches": ["round-20260509t063201z-6c02-impl-codex"],
        "remote_branches": [
            {"branch": "round-20260509t063201z-6c02-impl-codex", "sha": "abc123"},
            {"branch": "round-20260509t063201z-6c02-spec-integration", "sha": "def456"},
        ],
        "workspaces": ["/tmp/workspace"],
    }
    provider = FixtureProvider(round_artifacts=artifacts)
    snapshot = web_app_hub.build_snapshot(provider)
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    row = snapshot["rounds"][0]
    assert "round-20260509t063201z-6c02-spec-integration" in row["branches"]
    assert row["mcp"]["remote_branches"][1]["sha"] == "def456"
    assert detail["artifacts"]["workspaces"] == ["/tmp/workspace"]
    assert detail["mcp"]["remote_branches"][0]["branch"] == "round-20260509t063201z-6c02-impl-codex"


def test_round_detail_loads_openspec_status_when_progress_identifies_change():
    outcome = {
        "source": "spec_round_runner",
        "status": "running",
        "project_root": "/workspace/example",
        "change": "update-web-app",
        "expected_branch": "round-20260509t063201z-6c02-spec-integration",
        "validation_status": "pending",
    }
    spec_status = {
        "ok": False,
        "source": "local_git",
        "change": "update-web-app",
        "validation": {"ok": False, "errors": [{"message": "tasks incomplete"}]},
    }
    provider = FixtureProvider(round_outcome=outcome, spec_status=spec_status)
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    assert detail["mcp"]["validation_status"] == "failed"
    assert detail["mcp"]["validation"]["errors"][0]["message"] == "tasks incomplete"
    assert detail["spec_status"]["change"] == "update-web-app"


# ---- Group B: autorefresh fixture and reconnect tests (tasks 1.8, 1.9) ----


def test_round_detail_exposes_cursor_for_incremental_updates():
    provider = FixtureProvider()
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    assert "cursor" in detail, "round detail must include a cursor field"
    assert detail["cursor"], "cursor must be non-empty when events are available"
    assert detail["timeline"], "initial detail must include timeline entries from include_existing=True"


def test_cursor_based_events_advance_and_exclude_earlier_events():
    first_events = {
        "ok": True,
        "round_id": "20260509t063201z-6c02",
        "cursor": "cursor-page-1",
        "events": [{"type": "message", "message": {"id": "msg-a", "createdAt": "2026-05-09T06:35:00+00:00", "msg": "initial event"}}],
    }
    second_events = {
        "ok": True,
        "round_id": "20260509t063201z-6c02",
        "cursor": "cursor-page-2",
        "events": [{"type": "message", "message": {"id": "msg-b", "createdAt": "2026-05-09T06:36:00+00:00", "msg": "incremental event"}}],
    }

    class StagedProvider(FixtureProvider):
        def round_events(self, round_id, cursor="", include_existing=False):
            if include_existing or not cursor:
                return first_events
            if cursor == "cursor-page-1":
                return second_events
            return {"ok": True, "round_id": round_id, "cursor": cursor, "events": []}

    provider = StagedProvider()
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    assert detail["cursor"] == "cursor-page-1"
    initial_summaries = [e["summary"] for e in detail["timeline"]]
    assert any("initial event" in s for s in initial_summaries)

    incremental = provider.round_events("20260509t063201z-6c02", cursor="cursor-page-1")
    assert incremental["cursor"] == "cursor-page-2"
    incremental_ids = [e.get("message", {}).get("id") for e in incremental["events"]]
    assert "msg-b" in incremental_ids, "incremental fetch must return new events"
    assert "msg-a" not in incremental_ids, "incremental fetch must not replay events before the cursor"


def test_timeline_entries_are_appended_in_chronological_order():
    events_response = {
        "ok": True,
        "round_id": "20260509t063201z-6c02",
        "cursor": "cursor-sorted",
        "events": [
            {"type": "message", "message": {"id": "msg-late", "createdAt": "2026-05-09T06:37:00+00:00", "msg": "later entry"}},
            {"type": "message", "message": {"id": "msg-early", "createdAt": "2026-05-09T06:35:00+00:00", "msg": "earlier entry"}},
        ],
    }
    provider = FixtureProvider(round_events=events_response)
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    summaries = [e["summary"] for e in detail["timeline"]]
    assert "earlier entry" in summaries
    assert "later entry" in summaries
    earlier_idx = next(i for i, s in enumerate(summaries) if "earlier entry" in s)
    later_idx = next(i for i, s in enumerate(summaries) if "later entry" in s)
    assert earlier_idx < later_idx, "timeline must be sorted chronologically: earlier entries first"


def test_timeline_does_not_duplicate_entries_when_rebuilt_with_same_events():
    events_response = {
        "ok": True,
        "round_id": "20260509t063201z-6c02",
        "cursor": "cursor-dedup",
        "events": [{"type": "message", "message": {"id": "msg-unique", "createdAt": "2026-05-09T06:35:00+00:00", "msg": "unique entry"}}],
    }
    provider = FixtureProvider(round_events=events_response)
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    matching = [e for e in detail["timeline"] if "unique entry" in e["summary"]]
    assert len(matching) == 1, "same event must not appear twice in a single timeline build"


def test_inbox_updates_when_new_message_arrives():
    new_message = {"id": "msg-new", "sender": "round-20260509t063201z-6c02-codex", "msg": "new autorefresh message", "createdAt": "2026-05-09T06:40:00+00:00"}
    snapshot_before = web_app_hub.build_snapshot(FixtureProvider(messages={"ok": True, "source": "hub_api", "items": []}))
    snapshot_after = web_app_hub.build_snapshot(FixtureProvider(messages={"ok": True, "source": "hub_api", "items": [new_message]}))
    before_ids = [item.get("source_id") for group in snapshot_before["inbox"] for item in group["items"]]
    after_ids = [item.get("source_id") for group in snapshot_after["inbox"] for item in group["items"]]
    assert "msg-new" not in before_ids, "new message must not be in inbox before it arrives"
    assert "msg-new" in after_ids, "new message must appear in inbox automatically"


def test_inbox_updates_when_new_notification_arrives():
    new_notification = {"id": "note-new", "agentId": "round-20260509t063201z-6c02-codex", "summary": "new notification", "createdAt": "2026-05-09T06:41:00+00:00"}
    snapshot_before = web_app_hub.build_snapshot(FixtureProvider(notifications={"ok": True, "source": "hub_api", "items": []}))
    snapshot_after = web_app_hub.build_snapshot(FixtureProvider(notifications={"ok": True, "source": "hub_api", "items": [new_notification]}))
    before_ids = [item.get("source_id") for group in snapshot_before["inbox"] for item in group["items"]]
    after_ids = [item.get("source_id") for group in snapshot_after["inbox"] for item in group["items"]]
    assert "note-new" not in before_ids
    assert "note-new" in after_ids, "new notification must appear in inbox automatically"


def test_runtime_readiness_degrades_when_mcp_becomes_unavailable():
    degraded_mcp = {"source": "mcp", "ok": False, "status": "unavailable", "error_kind": "runtime", "error": "connection refused"}
    original = web_app_hub.utc_now
    try:
        web_app_hub.utc_now = lambda: "2026-05-09T06:39:30+00:00"
        snapshot_healthy = web_app_hub.build_snapshot(FixtureProvider())
        snapshot_degraded = web_app_hub.build_snapshot(FixtureProvider(mcp=degraded_mcp))
    finally:
        web_app_hub.utc_now = original
    assert snapshot_healthy["readiness"] == "ready"
    assert snapshot_degraded["readiness"] == "degraded"
    assert snapshot_degraded["sources"]["hub"]["ok"] is True, "hub data must be preserved when MCP is down"


def test_runtime_status_change_visible_in_next_snapshot():
    hub_mixed = healthy_hub()
    hub_all_completed = healthy_hub()
    for agent in hub_all_completed["agents"]:
        agent["phase"] = "completed"
        agent["activity"] = "completed"
    original = web_app_hub.utc_now
    try:
        web_app_hub.utc_now = lambda: "2026-05-09T06:39:30+00:00"
        snapshot_running = web_app_hub.build_snapshot(FixtureProvider(hub=hub_mixed))
        snapshot_completed = web_app_hub.build_snapshot(FixtureProvider(hub=hub_all_completed))
    finally:
        web_app_hub.utc_now = original
    round_id = "20260509t063201z-6c02"
    running_row = next((r for r in snapshot_running["rounds"] if r["round_id"] == round_id), None)
    completed_row = next((r for r in snapshot_completed["rounds"] if r["round_id"] == round_id), None)
    assert running_row and running_row["status"] == "running"
    assert completed_row and completed_row["status"] == "completed"


def test_stale_snapshot_preserves_last_known_round_data():
    old_hub = healthy_hub()
    for agent in old_hub["agents"]:
        agent["updated"] = "2026-05-09T06:00:00+00:00"
    original = web_app_hub.utc_now
    try:
        web_app_hub.utc_now = lambda: "2026-05-09T06:40:00+00:00"
        snapshot = web_app_hub.build_snapshot(
            FixtureProvider(hub=old_hub, messages={"ok": True, "items": []}, notifications={"ok": True, "items": []})
        )
    finally:
        web_app_hub.utc_now = original
    assert snapshot["stale"] is True, "snapshot must be marked stale when data exceeds freshness threshold"
    assert len(snapshot["rounds"]) > 0, "last known round data must be preserved when stale"
    assert snapshot["rounds"][0]["round_id"] == "20260509t063201z-6c02"


def test_cursor_resume_after_stream_reconnect_returns_only_new_events():
    pre_event = {"type": "message", "message": {"id": "pre-reconnect", "createdAt": "2026-05-09T06:35:00+00:00", "msg": "before disconnect"}}
    post_event = {"type": "message", "message": {"id": "post-reconnect", "createdAt": "2026-05-09T06:37:00+00:00", "msg": "after reconnect"}}

    class ReconnectProvider(FixtureProvider):
        def round_events(self, round_id, cursor="", include_existing=False):
            if cursor == "cursor-at-disconnect":
                return {"ok": True, "round_id": round_id, "cursor": "cursor-resumed", "events": [post_event]}
            return {"ok": True, "round_id": round_id, "cursor": "cursor-at-disconnect", "events": [pre_event]}

    provider = ReconnectProvider()
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    assert detail["cursor"] == "cursor-at-disconnect"
    assert any("before disconnect" in e["summary"] for e in detail["timeline"])

    resumed = provider.round_events("20260509t063201z-6c02", cursor="cursor-at-disconnect")
    assert resumed["cursor"] == "cursor-resumed"
    resumed_ids = [e.get("message", {}).get("id") for e in resumed["events"]]
    assert "post-reconnect" in resumed_ids, "reconnect via cursor must deliver missed events"
    assert "pre-reconnect" not in resumed_ids, "reconnect via cursor must not replay pre-disconnect events"


def test_fallback_snapshot_preserves_partial_data_when_events_unavailable():
    provider = FixtureProvider(round_events={"ok": False, "error": "stream disconnected", "error_kind": "runtime"})
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    assert detail["round_id"] == "20260509t063201z-6c02"
    assert detail["ok"] or detail.get("status", {}).get("ok"), "partial detail must still be available when events fail"


def test_server_write_methods_are_rejected_as_read_only():
    from http import HTTPStatus
    captured = []

    class MinimalHandler(web_app_hub.HubRequestHandler):
        def respond_json(self, payload, *, status=HTTPStatus.OK):
            captured.append({"status": status, "payload": payload})

    handler = object.__new__(MinimalHandler)
    for method_name in ("do_POST", "do_PUT", "do_PATCH", "do_DELETE"):
        captured.clear()
        getattr(handler, method_name)()
        assert len(captured) == 1, f"{method_name} must call respond_json exactly once"
        assert captured[0]["status"] == HTTPStatus.METHOD_NOT_ALLOWED, f"{method_name} must return 405"
        assert captured[0]["payload"].get("ok") is False, f"{method_name} response must have ok=False"


def test_incremental_events_fetch_does_not_mutate_provider_state():
    provider = FixtureProvider()
    hub_before = provider.hub_status()
    messages_before = provider.hub_messages()
    provider.round_events("20260509t063201z-6c02", cursor="", include_existing=True)
    provider.round_events("20260509t063201z-6c02", cursor="cursor-1", include_existing=False)
    provider.round_events("20260509t063201z-6c02", cursor="cursor-2", include_existing=False)
    assert provider.hub_status() == hub_before, "hub state must not change after event fetches"
    assert provider.hub_messages() == messages_before, "message state must not change after event fetches"


def test_repeated_snapshot_refresh_does_not_start_or_modify_rounds():
    hub = healthy_hub()
    agent_count_before = len(hub["agents"])
    provider = FixtureProvider(hub=hub)
    snapshot = None
    for _ in range(3):
        snapshot = web_app_hub.build_snapshot(provider)
    assert len(provider.hub_status()["agents"]) == agent_count_before, "snapshot refresh must not create or modify agents"
    assert snapshot and snapshot["rounds"], "rounds must be present after multiple refreshes"


def test_index_html_contains_live_update_indicators():
    assert "stale" in web_app_hub.INDEX_HTML.lower(), "UI must expose stale data state to operator"
    assert "setInterval" in web_app_hub.INDEX_HTML, "UI must use setInterval for automatic polling without button press"
    assert "cursors" in web_app_hub.INDEX_HTML, "UI must track cursors for incremental update path"


def test_events_endpoint_returns_cursor_for_incremental_fetch():
    captured = []

    class TrackingProvider(FixtureProvider):
        def round_events(self, round_id, cursor="", include_existing=False):
            captured.append({"cursor": cursor, "include_existing": include_existing})
            return super().round_events(round_id, cursor=cursor, include_existing=include_existing)

    provider = TrackingProvider()
    result = provider.round_events("20260509t063201z-6c02", cursor="cursor-1", include_existing=False)
    assert result.get("ok") is True
    assert "cursor" in result, "events response must include a cursor for subsequent incremental fetches"
    assert captured[0]["cursor"] == "cursor-1"
    assert captured[0]["include_existing"] is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
