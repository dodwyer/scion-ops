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
    def __init__(self, *, hub=None, messages=None, notifications=None, mcp=None, k8s=None) -> None:
        self._hub = hub if hub is not None else healthy_hub()
        self._messages = messages if messages is not None else healthy_messages()
        self._notifications = notifications if notifications is not None else healthy_notifications()
        self._mcp = mcp if mcp is not None else {"source": "mcp", "ok": True, "status": "healthy"}
        self._k8s = k8s if k8s is not None else healthy_k8s()

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
        return {"ok": True, "round_id": round_id, "agents": self._hub.get("agents", []), "outcome": {"status": "completed"}}

    def round_events(self, round_id, cursor="", include_existing=False):
        return {
            "ok": True,
            "round_id": round_id,
            "cursor": "cursor-1",
            "events": [
                {"type": "message", "message": {"createdAt": "2026-05-09T06:35:00+00:00", "msg": f"round {round_id} update"}}
            ],
        }


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
        ],
        "pods": [],
    }


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


def test_structured_branch_field_takes_precedence_over_text_fallback():
    """Structured agent.branch/targetBranch is used directly; text parsing is fallback only."""
    agents = [
        {
            "name": "round-20260509t063201z-aaaa-impl",
            "phase": "completed",
            "activity": "completed",
            "branch": "main",  # structured field present
            "taskSummary": "complete: round-20260509t063201z-aaaa-impl-from-text",  # would match if fallback used
        },
        {
            "name": "round-20260509t063201z-bbbb-impl",
            "phase": "completed",
            "activity": "completed",
            # no structured branch field — text parsing is the fallback
            "taskSummary": "complete: round-20260509t063201z-bbbb-impl-from-text",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, [], [])
    by_id = {r["round_id"]: r for r in rounds}

    # Agent with structured 'branch': use it directly, do not text-parse taskSummary
    aaaa_round = by_id.get("20260509t063201z-aaaa")
    assert aaaa_round is not None
    assert "main" in aaaa_round["branches"]
    assert "round-20260509t063201z-aaaa-impl-from-text" not in aaaa_round["branches"]

    # Agent without structured field: text parsing is used as fallback
    bbbb_round = by_id.get("20260509t063201z-bbbb")
    assert bbbb_round is not None
    assert "round-20260509t063201z-bbbb-impl-from-text" in bbbb_round["branches"]


def test_targeted_branch_field_takes_precedence_over_text_fallback():
    """Structured agent.targetBranch is used directly when present."""
    agents = [
        {
            "name": "round-20260509t063201z-cccc-impl",
            "phase": "completed",
            "activity": "completed",
            "targetBranch": "round-20260509t063201z-cccc-impl-structured",
            "taskSummary": "complete: round-20260509t063201z-cccc-impl-from-text",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, [], [])
    assert len(rounds) == 1
    row = rounds[0]
    assert "round-20260509t063201z-cccc-impl-structured" in row["branches"]
    assert "round-20260509t063201z-cccc-impl-from-text" not in row["branches"]


def test_structured_branch_from_message_payload_takes_precedence_over_text_in_message_body():
    """Structured branch in message JSON payload suppresses text-parsed branches from message body."""
    agents = [
        {
            "name": "round-20260509t063201z-jjjj-consensus",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "dispatching",
            "updated": "2026-05-09T06:38:00+00:00",
        },
    ]
    messages = [
        {
            "id": "msg-review-1",
            "sender": "round-20260509t063201z-jjjj-final-review",
            # JSON payload has structured branch; text also mentions a different branch in notes
            "msg": json.dumps({
                "branch": "main",
                "notes": "see round-20260509t063201z-jjjj-impl-text-only for context",
            }),
            "createdAt": "2026-05-09T06:39:00+00:00",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, messages, [])
    assert len(rounds) == 1
    row = rounds[0]
    # Structured branch from JSON payload is used
    assert "main" in row["branches"]
    # Text-parsed branch from message body is suppressed because structured branch is present
    assert "round-20260509t063201z-jjjj-impl-text-only" not in row["branches"]


def test_structured_branch_from_outcome_payload_takes_precedence_over_agent_text_fallback():
    """Structured branch in outcome/integration payload suppresses text-parsed branches from agent taskSummary."""
    agents = [
        {
            "name": "round-20260509t063201z-kkkk-impl-codex",
            "phase": "completed",
            "activity": "completed",
            # taskSummary text would yield a branch via text parsing if no structured branch exists
            "taskSummary": "complete: round-20260509t063201z-kkkk-impl-codex",
            "updated": "2026-05-09T06:38:00+00:00",
        },
    ]
    messages = [
        {
            "id": "msg-outcome-1",
            "roundId": "20260509t063201z-kkkk",
            # Outcome payload with structured branch pointing to the actual revision branch
            "msg": json.dumps({
                "outcome": {
                    "branch": "round-20260509t063201z-kkkk-impl-codex-r2",
                    "status": "completed",
                }
            }),
            "createdAt": "2026-05-09T06:39:00+00:00",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, messages, [])
    assert len(rounds) == 1
    row = rounds[0]
    # Structured branch from outcome payload is used
    assert "round-20260509t063201z-kkkk-impl-codex-r2" in row["branches"]
    # Text-parsed branch from agent taskSummary is suppressed because structured branch exists
    assert "round-20260509t063201z-kkkk-impl-codex" not in row["branches"]


def test_final_review_verdict_accepted_exposed_by_backend():
    """Backend exposes 'accepted' verdict for final-review agents and sets status to 'accepted'."""
    agents = [
        {
            "name": "round-20260509t063201z-dddd-consensus",
            "template": "consensus-runner",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "complete: round-20260509t063201z-dddd",
            "updated": "2026-05-09T06:38:00+00:00",
        },
        {
            "name": "round-20260509t063201z-dddd-final-review",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "final verdict: accept — all checks passed",
            "updated": "2026-05-09T06:39:00+00:00",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, [], [])
    assert len(rounds) == 1
    row = rounds[0]
    assert row["round_id"] == "20260509t063201z-dddd"
    assert row["final_verdict"] == "accepted"
    assert row["status"] == "accepted"


def test_final_review_verdict_changes_requested_not_collapsed_to_completed():
    """Backend exposes 'request_changes' and does NOT collapse it to generic 'completed'."""
    agents = [
        {
            "name": "round-20260509t063201z-eeee-consensus",
            "template": "consensus-runner",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "complete: round-20260509t063201z-eeee",
            "updated": "2026-05-09T06:38:00+00:00",
        },
        {
            "name": "round-20260509t063201z-eeee-final-review",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "final verdict: request_changes — tests failing",
            "updated": "2026-05-09T06:39:00+00:00",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, [], [])
    assert len(rounds) == 1
    row = rounds[0]
    assert row["round_id"] == "20260509t063201z-eeee"
    assert row["final_verdict"] == "request_changes"
    assert row["status"] == "request_changes"
    assert row["status"] != "completed"


def test_final_review_verdict_approved_normalizes_to_accepted():
    """Backend normalizes 'approved' verdict to 'accepted' status (not 'request_changes')."""
    agents = [
        {
            "name": "round-20260509t063201z-ffff-consensus",
            "template": "consensus-runner",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "complete: round-20260509t063201z-ffff",
            "updated": "2026-05-09T06:38:00+00:00",
        },
        {
            "name": "round-20260509t063201z-ffff-final-review",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "final verdict: approved — implementation accepted",
            "updated": "2026-05-09T06:39:00+00:00",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, [], [])
    assert len(rounds) == 1
    row = rounds[0]
    assert row["final_verdict"] == "accepted"
    assert row["status"] == "accepted"


def test_final_review_verdict_blocked_renders_as_blocked_not_request_changes():
    """Backend exposes 'blocked' verdict as 'blocked' status, not 'request_changes'."""
    agents = [
        {
            "name": "round-20260509t063201z-gggg-consensus",
            "template": "consensus-runner",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "complete: round-20260509t063201z-gggg",
            "updated": "2026-05-09T06:38:00+00:00",
        },
        {
            "name": "round-20260509t063201z-gggg-final-review",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "final verdict: blocked — critical issues found",
            "updated": "2026-05-09T06:39:00+00:00",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, [], [])
    assert len(rounds) == 1
    row = rounds[0]
    assert row["final_verdict"] == "blocked"
    assert row["status"] == "blocked"
    assert row["status"] != "request_changes"


def test_frontend_html_renders_verdict_fields():
    """Frontend HTML CSS and JS render verdict values produced by representative backend data."""
    # Build representative rounds for each relevant verdict outcome
    def make_agents(tag: str, verdict_text: str) -> list[dict]:
        return [
            {
                "name": f"round-20260509t063201z-{tag}-consensus",
                "template": "consensus-runner",
                "phase": "completed",
                "activity": "completed",
                "taskSummary": f"complete: round-20260509t063201z-{tag}",
                "updated": "2026-05-09T06:38:00+00:00",
            },
            {
                "name": f"round-20260509t063201z-{tag}-final-review",
                "phase": "completed",
                "activity": "completed",
                "taskSummary": f"final verdict: {verdict_text}",
                "updated": "2026-05-09T06:39:00+00:00",
            },
        ]

    rounds_accepted = web_app_hub.build_rounds(make_agents("vvvv", "accepted — all checks passed"), [], [])
    rounds_changes = web_app_hub.build_rounds(make_agents("wwww", "request_changes — tests failing"), [], [])
    rounds_blocked = web_app_hub.build_rounds(make_agents("xxxx", "blocked — spec violations"), [], [])

    # Backend produces correct verdict values
    assert rounds_accepted[0]["final_verdict"] == "accepted"
    assert rounds_changes[0]["final_verdict"] == "request_changes"
    assert rounds_blocked[0]["final_verdict"] == "blocked"

    # Frontend HTML has CSS classes to render each verdict value
    html = web_app_hub.INDEX_HTML
    for verdict in (rounds_accepted[0]["final_verdict"], rounds_changes[0]["final_verdict"], rounds_blocked[0]["final_verdict"]):
        assert f".{verdict} .dot" in html, f"CSS class for verdict '{verdict}' missing from INDEX_HTML"
    # JS must reference final_verdict field from round data
    assert "final_verdict" in html
    # JS must reference final_review from round detail outcome
    assert "final_review" in html


def test_alternate_structured_agent_branch_fields_take_precedence_over_text_fallback():
    """target_branch and branchName agent fields are treated as structured and suppress text fallback."""
    agents = [
        {
            "name": "round-20260509t063201z-nnnn-impl",
            "phase": "completed",
            "activity": "completed",
            "target_branch": "round-20260509t063201z-nnnn-impl-structured",
            "taskSummary": "complete: round-20260509t063201z-nnnn-impl-from-text",
        },
        {
            "name": "round-20260509t063201z-mmmm-impl",
            "phase": "completed",
            "activity": "completed",
            "branchName": "round-20260509t063201z-mmmm-impl-structured",
            "taskSummary": "complete: round-20260509t063201z-mmmm-impl-from-text",
        },
    ]
    rounds = web_app_hub.build_rounds(agents, [], [])
    by_id = {r["round_id"]: r for r in rounds}

    # target_branch field: use structured, suppress text fallback
    nnnn = by_id.get("20260509t063201z-nnnn")
    assert nnnn is not None
    assert "round-20260509t063201z-nnnn-impl-structured" in nnnn["branches"]
    assert "round-20260509t063201z-nnnn-impl-from-text" not in nnnn["branches"]

    # branchName field: use structured, suppress text fallback
    mmmm = by_id.get("20260509t063201z-mmmm")
    assert mmmm is not None
    assert "round-20260509t063201z-mmmm-impl-structured" in mmmm["branches"]
    assert "round-20260509t063201z-mmmm-impl-from-text" not in mmmm["branches"]


def test_notification_sourced_final_verdict_not_collapsed_to_completed():
    """A final-review verdict present only in a notification is surfaced in round rows."""
    agents = [
        {
            "name": "round-20260509t063201z-pppp-consensus",
            "template": "consensus-runner",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "complete: round-20260509t063201z-pppp",
            "updated": "2026-05-09T06:38:00+00:00",
        },
        {
            "name": "round-20260509t063201z-pppp-final-review",
            "phase": "completed",
            "activity": "completed",
            "taskSummary": "review complete",
            "updated": "2026-05-09T06:39:00+00:00",
        },
    ]
    # Verdict is only in a notification, not in any message
    notifications = [
        {
            "id": "note-verdict-1",
            "agentId": "round-20260509t063201z-pppp-final-review",
            "sender": "round-20260509t063201z-pppp-final-review",
            "msg": json.dumps({"verdict": "request_changes", "reviewer": "final-reviewer", "notes": "tests failing"}),
            "createdAt": "2026-05-09T06:40:00+00:00",
        }
    ]
    rounds = web_app_hub.build_rounds(agents, [], notifications)
    assert len(rounds) == 1
    row = rounds[0]
    assert row["round_id"] == "20260509t063201z-pppp"
    assert row["status"] == "request_changes"
    assert row["status"] != "completed"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
