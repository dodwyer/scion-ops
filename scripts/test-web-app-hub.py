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
        "pull_request": {"pr_url": "https://github.com/example/project/pull/44", "head": "round-20260509t063201z-6c02-spec-integration"},
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
    assert row["mcp"]["pr_url"] == "https://github.com/example/project/pull/44"
    assert "expected_branch" in web_app_hub.INDEX_HTML
    assert "MCP State" in web_app_hub.INDEX_HTML
    assert "Pull request" in web_app_hub.INDEX_HTML


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


def test_live_contract_describes_typed_events_and_source_coverage():
    contract = web_app_hub.BROWSER_JSON_CONTRACT["live_updates"]
    assert contract["endpoint"].startswith("/api/live")
    assert "snapshot.initial" in contract["event_types"]
    assert "timeline.appended" in contract["event_types"]
    assert "source.error" in contract["event_types"]
    assert "Hub" in contract["read_only"]
    assert "kubernetes" in contract["source_errors"] or "source.error" in contract["source_errors"]


def test_live_initial_snapshot_emits_typed_cursor_and_heartbeat_events():
    batch = web_app_hub.build_live_update_batch(FixtureProvider(), round_id="20260509t063201z-6c02")
    event_types = [event["type"] for event in batch["events"]]
    assert batch["ok"] is True
    assert batch["cursor"].startswith("live:")
    assert event_types[:5] == ["snapshot.initial", "overview.updated", "rounds.updated", "inbox.updated", "runtime.updated"]
    assert "round.detail.updated" in event_types
    assert "timeline.appended" in event_types
    assert event_types[-1] == "heartbeat"
    assert all(event.get("id") and event.get("cursor") == batch["cursor"] for event in batch["events"])


def test_live_incremental_updates_capture_inbox_runtime_status_and_final_review_changes():
    first = web_app_hub.build_live_update_batch(FixtureProvider())
    changed_notifications = {
        "ok": True,
        "items": [
            *healthy_notifications()["items"],
            {
                "id": "final-changes",
                "agentId": "round-20260509t063201z-6c02-final-review",
                "summary": '{"verdict":"changes_requested","summary":"needs repair"}',
                "createdAt": "2026-05-09T06:44:01+00:00",
            },
        ],
    }
    changed_k8s = healthy_k8s()
    changed_k8s["status"] = "degraded"
    changed_k8s["ok"] = True
    changed_k8s["deployments"][0] = {**changed_k8s["deployments"][0], "available": 0, "ready": False}
    second = web_app_hub.build_live_update_batch(
        FixtureProvider(notifications=changed_notifications, k8s=changed_k8s),
        cursor=first["cursor"],
    )
    assert second["cursor"] != first["cursor"]
    state = web_app_hub.merge_live_events({}, second["events"])
    row = state["rounds"][0]
    assert row["visible_status"] == "changes requested"
    assert state["inbox"][0]["items"][0]["source_id"] == "final-changes"
    assert state["sources"]["kubernetes"]["status"] == "degraded"


def test_live_duplicate_replayed_events_are_idempotent_for_snapshot_and_timeline_appends():
    round_events = {
        "ok": True,
        "round_id": "20260509t063201z-6c02",
        "cursor": "cursor-2",
        "events": [
            {"type": "message", "message": {"id": "msg-2", "createdAt": "2026-05-09T06:45:00+00:00", "msg": "round 20260509t063201z-6c02 step one"}},
            {"type": "message", "message": {"id": "msg-2", "createdAt": "2026-05-09T06:45:00+00:00", "msg": "round 20260509t063201z-6c02 step one"}},
        ],
    }
    batch = web_app_hub.build_live_update_batch(FixtureProvider(round_events=round_events), round_id="20260509t063201z-6c02")
    replayed = batch["events"] + batch["events"]
    state = web_app_hub.merge_live_events({}, replayed)
    timeline = state["timelines"]["20260509t063201z-6c02"]
    assert [entry["id"] for entry in timeline] == ["message:msg-2"]
    assert len(state["_seen_event_ids"]) == len({event["id"] for event in batch["events"]})


def test_live_reconnect_with_current_cursor_returns_heartbeat_only_and_bogus_cursor_falls_back_to_snapshot():
    provider = FixtureProvider()
    first = web_app_hub.build_live_update_batch(provider)
    resumed = web_app_hub.build_live_update_batch(provider, cursor=first["cursor"])
    fallback = web_app_hub.build_live_update_batch(provider, cursor="live:missing")
    assert [event["type"] for event in resumed["events"]] == ["heartbeat"]
    assert fallback["mode"] == "cursor_resume"
    assert fallback["events"][0]["type"] == "snapshot.updated"
    assert fallback["events"][0]["data"]["snapshot"]["rounds"]


def test_live_source_specific_errors_do_not_clear_healthy_sources():
    provider = FixtureProvider(
        mcp={"source": "mcp", "ok": False, "status": "unavailable", "error_kind": "runtime", "error": "connection refused"},
        k8s={"source": "kubernetes", "ok": False, "status": "unavailable", "error_kind": "runtime", "error": "kubectl missing"},
    )
    batch = web_app_hub.build_live_update_batch(provider)
    errors = [event for event in batch["events"] if event["type"] == "source.error"]
    assert {event["source"] for event in errors} >= {"mcp", "kubernetes", "web_app"}
    runtime = next(event for event in batch["events"] if event["type"] == "runtime.updated")
    assert runtime["data"]["sources"]["hub"]["ok"] is True
    assert runtime["data"]["sources"]["mcp"]["error_kind"] == "runtime"


def test_live_update_path_is_read_only_and_does_not_validate_or_mutate():
    class TrackingProvider(FixtureProvider):
        def __init__(self):
            super().__init__()
            self.calls = []

        def validate_spec_change(self, project_root, change):
            self.calls.append(("validate_spec_change", project_root, change))
            raise AssertionError("live updates must not validate or mutate")

        def start_round(self):
            self.calls.append(("start_round",))
            raise AssertionError("live updates must not start rounds")

    provider = TrackingProvider()
    batch = web_app_hub.build_live_update_batch(provider, round_id="20260509t063201z-6c02")
    assert batch["ok"] is True
    assert provider.calls == []


def test_frontend_live_update_contract_markers_are_present():
    contract = web_app_hub.BROWSER_JSON_CONTRACT["live_updates"]
    html = web_app_hub.INDEX_HTML
    assert contract["round_events"].startswith("cursor-based read-only GET")
    assert contract["states"] == ["connected", "reconnecting", "stale", "fallback", "failed"]
    assert "SNAPSHOT_POLL_MS" in html
    assert "ROUND_EVENT_POLL_MS" in html
    assert "/api/snapshot" in html
    assert "/api/rounds/${encodeURIComponent(roundId)}/events?cursor=${encodeURIComponent(cursor)}" in html
    assert "state.cursors[roundId]" in html
    assert "timelineKeys" in html
    assert "mergeTimelineEvents" in html
    assert "EventSource" in html
    assert "/api/updates" in html
    assert "markStreamOk" in html
    assert "checkStaleness" in html
    assert "fallback polling" in html
    assert "Refresh snapshot" in html
    assert "Troubleshooting snapshot refresh" in html


def test_frontend_automatic_update_fetches_are_read_only_no_spend_paths():
    html = web_app_hub.INDEX_HTML
    assert "fetch(url, { cache: \"no-store\" })" in html
    assert "method:" not in html
    assert "/api/snapshot" in html
    assert "/api/rounds/${encodeURIComponent(roundId)}/events" in html
    assert "/api/rounds/${encodeURIComponent(roundId)}" in html
    for forbidden in (
        "scion_ops_start",
        "scion_ops_abort",
        "scion_ops_retry",
        "scion_ops_archive",
        "validate_spec_change(",
        "do_POST(",
    ):
        assert forbidden not in html


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
