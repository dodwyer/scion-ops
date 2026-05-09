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
    def __init__(self, *, hub=None, messages=None, notifications=None, mcp=None, k8s=None, round_outcome=None, round_events=None, artifacts=None, spec_status=None, validation=None) -> None:
        self._hub = hub if hub is not None else healthy_hub()
        self._messages = messages if messages is not None else healthy_messages()
        self._notifications = notifications if notifications is not None else healthy_notifications()
        self._mcp = mcp if mcp is not None else {"source": "mcp", "ok": True, "status": "healthy"}
        self._k8s = k8s if k8s is not None else healthy_k8s()
        self._round_outcome = round_outcome if round_outcome is not None else {"status": "completed"}
        self._round_events = round_events
        self._artifacts = artifacts if artifacts is not None else {}
        self._spec_status = spec_status if spec_status is not None else {}
        self._validation = validation if validation is not None else {}

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

    def round_artifacts(self, round_id, project_root=""):
        return self._artifacts

    def spec_status(self, project_root, change=""):
        return self._spec_status

    def validate_spec_change(self, project_root, change):
        return self._validation


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
        "pods": [{"name": "scion-ops-web-app-abc123", "phase": "Running", "ready": True}],
        "services": [{"name": "scion-ops-web-app", "type": "ClusterIP"}],
        "endpoints": [{"name": "scion-ops-web-app", "ready_addresses": 1, "not_ready_addresses": 0, "ready": True}],
    }


def test_healthy_snapshot_is_ready():
    original = web_app_hub.utc_now
    try:
        web_app_hub.utc_now = lambda: "2026-05-09T06:39:30+00:00"
        snapshot = web_app_hub.build_snapshot(FixtureProvider())
    finally:
        web_app_hub.utc_now = original
    assert snapshot["readiness"] == "ready"
    assert snapshot["sources"]["web_app"]["status"] == "healthy"
    assert snapshot["overview"]["checks"]["web_app"]["status"] == "healthy"
    assert snapshot["overview"]["active_round_count"] == 1
    assert snapshot["rounds"][0]["round_id"] == "20260509t063201z-6c02"
    assert snapshot["inbox"][0]["round_id"] == "20260509t063201z-6c02"
    runtime = {"sources": snapshot["sources"]}
    assert runtime["sources"]["web_app"]["deployment"]["name"] == "scion-ops-web-app"
    assert '"web_app"' in web_app_hub.INDEX_HTML


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


def test_missing_web_app_service_degrades_readiness():
    k8s = healthy_k8s()
    k8s["services"] = []
    snapshot = web_app_hub.build_snapshot(FixtureProvider(k8s=k8s))
    assert snapshot["readiness"] == "degraded"
    assert snapshot["sources"]["web_app"]["status"] == "degraded"
    assert "service" in snapshot["sources"]["web_app"]["missing"]


def test_missing_web_app_endpoint_degrades_readiness():
    k8s = healthy_k8s()
    k8s["endpoints"] = []
    snapshot = web_app_hub.build_snapshot(FixtureProvider(k8s=k8s))
    assert snapshot["readiness"] == "degraded"
    assert snapshot["sources"]["web_app"]["status"] == "degraded"
    assert "endpoint" in snapshot["sources"]["web_app"]["missing"]


def test_normalized_kubernetes_missing_web_app_service_and_endpoint_degrades():
    payload = {
        "items": [
            {"kind": "Deployment", "metadata": {"name": "scion-hub", "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}}, "spec": {"replicas": 1}, "status": {"availableReplicas": 1}},
            {"kind": "Deployment", "metadata": {"name": "scion-broker", "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}}, "spec": {"replicas": 1}, "status": {"availableReplicas": 1}},
            {"kind": "Deployment", "metadata": {"name": "scion-ops-mcp", "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}}, "spec": {"replicas": 1}, "status": {"availableReplicas": 1}},
            {"kind": "Deployment", "metadata": {"name": "scion-ops-web-app", "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}}, "spec": {"replicas": 1}, "status": {"availableReplicas": 1}},
            {"kind": "Pod", "metadata": {"name": "scion-ops-web-app-abc123", "labels": {"app.kubernetes.io/part-of": "scion-control-plane"}}, "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]}},
        ]
    }
    status = web_app_hub.normalize_kubernetes(payload, namespace="scion-agents")
    snapshot = web_app_hub.build_snapshot(FixtureProvider(k8s=status))
    assert status["status"] == "degraded"
    assert status["missing_services"] == ["scion-ops-web-app"]
    assert status["missing_endpoints"] == ["scion-ops-web-app"]
    assert snapshot["readiness"] == "degraded"
    assert snapshot["sources"]["web_app"]["missing"] == ["service", "endpoint"]


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


def spec_round_payload(**overrides):
    payload = {
        "ok": False,
        "done": True,
        "status": "blocked",
        "health": "blocked",
        "summary": "round 20260509t063201z-6c02 blocked validation=failed",
        "source": "spec_round_runner",
        "project_root": "/workspace",
        "round_id": "20260509t063201z-6c02",
        "change": "update-web-app",
        "base_branch": "main",
        "expected_branch": "round-20260509t063201z-6c02-spec-integration",
        "pr_ready_branch": "",
        "remote_branch_sha": "1111222233334444555566667777888899990000",
        "base_branch_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "branch_changed": False,
        "validation_status": "failed",
        "validation": {
            "ok": False,
            "validator": "openspec_cli",
            "errors": [{"message": "Requirement missing scenario"}],
        },
        "protocol": {
            "integration_branch_valid": False,
            "ops_review_agent_count": 1,
            "ops_review_complete": True,
            "finalizer_agent_count": 0,
            "finalizer_complete": False,
            "complete": False,
        },
        "blockers": ["expected branch did not move from base SHA"],
        "warnings": ["OpenSpec validation is currently failing on the remote branch"],
        "progress_lines": ["round 20260509t063201z-6c02 blocked validation=failed"],
        "cursor": "cursor-spec-1",
    }
    payload.update(overrides)
    return payload


def artifact_payload():
    return {
        "source": "local_git",
        "project_root": "/workspace",
        "branches": ["round-20260509t063201z-6c02-spec-integration"],
        "remote_branches": [
            {
                "branch": "round-20260509t063201z-6c02-spec-integration",
                "sha": "1111222233334444555566667777888899990000",
            }
        ],
        "workspaces": ["/workspace/.scion/agents/round/workspace"],
        "prompts": [],
    }


def spec_status_payload():
    return {
        "ok": False,
        "source": "local_git",
        "project_root": "/workspace",
        "change": "update-web-app",
        "validation": {
            "ok": False,
            "validator": "openspec_cli",
            "errors": ["OpenSpec validation failed"],
        },
        "validation_result": {"ok": False, "error_kind": "openspec_validation"},
        "openspec_status": {"ok": False},
    }


def test_current_run_spec_round_fields_are_preserved_in_rounds_detail_and_inbox():
    payload = spec_round_payload()
    messages = {
        "ok": True,
        "items": [
            {
                "id": "spec-progress",
                "sender": "round-20260509t063201z-6c02-consensus",
                "msg": json.dumps(payload),
                "createdAt": "2026-05-09T06:42:01+00:00",
            }
        ],
    }
    provider = FixtureProvider(
        messages=messages,
        notifications={"ok": True, "items": []},
        round_events={
            "ok": True,
            "round_id": "20260509t063201z-6c02",
            "cursor": "cursor-events-2",
            "progress_lines": payload["progress_lines"],
            "events": [{"type": "message", "message": messages["items"][0]}],
            "outcome": {},
        },
    )
    snapshot = web_app_hub.build_snapshot(provider)
    row = snapshot["rounds"][0]
    assert row["status"] == "blocked"
    assert row["spec_round"]["expected_branch"] == "round-20260509t063201z-6c02-spec-integration"
    assert row["spec_round"]["validation_status"] == "failed"
    assert row["spec_round"]["branch_changed"] is False
    assert row["spec_round"]["blockers"] == ["expected branch did not move from base SHA"]
    assert snapshot["inbox"][0]["items"][0]["spec_round"]["warnings"]
    detail = web_app_hub.build_round_detail(provider, "20260509t063201z-6c02")
    assert detail["event_cursor"] == "cursor-events-2"
    assert detail["spec_round"]["protocol"]["complete"] is False


def test_round_artifacts_and_spec_status_shapes_are_exposed():
    payload = spec_round_payload(status="completed", ok=True, done=True, validation_status="passed", blockers=[], warnings=[], branch_changed=True, pr_ready_branch="round-20260509t063201z-6c02-spec-integration")
    messages = {
        "ok": True,
        "items": [
            {
                "id": "spec-complete",
                "sender": "round-20260509t063201z-6c02-consensus",
                "msg": json.dumps(payload),
                "createdAt": "2026-05-09T06:42:01+00:00",
            }
        ],
    }
    provider = FixtureProvider(
        messages=messages,
        notifications={"ok": True, "items": []},
        artifacts=artifact_payload(),
        spec_status=spec_status_payload(),
    )
    snapshot = web_app_hub.build_snapshot(provider)
    row = snapshot["rounds"][0]
    assert row["artifacts"]["remote_branches"][0]["sha"] == "1111222233334444555566667777888899990000"
    assert row["validation"]["status"] == "failed"
    assert row["spec_round"]["validation"]["errors"] == ["OpenSpec validation failed"]
    assert "round-20260509t063201z-6c02-spec-integration" in row["branches"]


def test_blocked_final_review_structured_payload_preserves_issues():
    notifications = {
        "ok": True,
        "items": [
            {
                "id": "final-structured-blocked",
                "agentId": "round-20260509t063201z-6c02-final-review",
                "summary": json.dumps({
                    "final_review": {
                        "source": "final_review_message",
                        "verdict": "blocked",
                        "normalized_verdict": "blocked",
                        "source_summary": "blocked by missing fixture coverage",
                        "blocking_issues": ["fixture coverage missing"],
                    }
                }),
                "createdAt": "2026-05-09T06:43:01+00:00",
            }
        ],
    }
    snapshot = web_app_hub.build_snapshot(FixtureProvider(notifications=notifications))
    row = snapshot["rounds"][0]
    assert row["status"] == "blocked"
    assert row["final_review"]["summary"] == "blocked by missing fixture coverage"
    assert row["final_review"]["blocking_issues"] == ["fixture coverage missing"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
