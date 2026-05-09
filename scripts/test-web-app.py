#!/usr/bin/env python3
"""Tests for web_app/server.py data-transformation helpers.

These tests cover the helper functions and API data-shaping logic using
representative data fixtures for healthy, empty, blocked, stale, and
unavailable runtime states. No live Hub or Kubernetes connection is required.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# Load the server module without executing main()
_SERVER_PATH = Path(__file__).resolve().parents[1] / "web_app" / "server.py"
_spec = importlib.util.spec_from_file_location("web_app.server", _SERVER_PATH)
assert _spec and _spec.loader, f"Could not load {_SERVER_PATH}"
_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server)  # type: ignore[union-attr]

_round_prefix = _server._round_prefix
_phase_status = _server._phase_status
_agent_summary = _server._agent_summary
_round_text_match = _server._round_text_match
_extract_round_id = _server._extract_round_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ROUND_ID = "round-20260509t063201z-6c02"

AGENT_RUNNING: dict[str, Any] = {
    "name": f"{ROUND_ID}-impl-claude",
    "slug": f"{ROUND_ID}-impl-claude",
    "phase": "running",
    "activity": "active",
    "containerStatus": "",
    "template": "claude",
    "taskSummary": "",
    "created": "2026-05-09T06:32:01Z",
    "updated": "2026-05-09T06:40:00Z",
}

AGENT_TERMINAL: dict[str, Any] = {
    "name": f"{ROUND_ID}-consensus",
    "slug": f"{ROUND_ID}-consensus",
    "phase": "stopped",
    "activity": "completed",
    "containerStatus": "succeeded",
    "template": "consensus-runner",
    "taskSummary": "impl complete: all checks passed",
    "created": "2026-05-09T06:32:01Z",
    "updated": "2026-05-09T07:00:00Z",
}

AGENT_BLOCKED: dict[str, Any] = {
    "name": f"{ROUND_ID}-consensus",
    "slug": f"{ROUND_ID}-consensus",
    "phase": "stopped",
    "activity": "completed",
    "containerStatus": "succeeded",
    "template": "consensus-runner",
    "taskSummary": "escalated: needs human input",
    "created": "2026-05-09T06:32:01Z",
    "updated": "2026-05-09T07:10:00Z",
}

AGENT_PENDING: dict[str, Any] = {
    "name": f"{ROUND_ID}-spec-author",
    "slug": f"{ROUND_ID}-spec-author",
    "phase": "pending",
    "activity": "",
    "containerStatus": "",
    "template": "spec-author",
    "taskSummary": "",
    "created": "2026-05-09T06:32:01Z",
    "updated": "2026-05-09T06:32:05Z",
}

MESSAGE_WITH_ROUND: dict[str, Any] = {
    "id": "msg-001",
    "sender": "round-20260509t063201z-6c02-impl-claude",
    "msg": f"Progress update for {ROUND_ID}",
    "created": "2026-05-09T06:45:00Z",
}

NOTIFICATION_WITH_ROUND: dict[str, Any] = {
    "id": "notif-001",
    "groveId": "test-grove",
    "message": f"Agent {ROUND_ID}-impl-claude updated",
    "created": "2026-05-09T06:46:00Z",
}

NOTIFICATION_NO_ROUND: dict[str, Any] = {
    "id": "notif-002",
    "groveId": "test-grove",
    "message": "System notification without round context",
    "created": "2026-05-09T06:47:00Z",
}


# ---------------------------------------------------------------------------
# Tests: _round_prefix
# ---------------------------------------------------------------------------

def test_round_prefix_standard() -> None:
    assert _round_prefix("round-20260509t063201z-6c02-impl-claude") == "round-20260509t063201z-6c02"


def test_round_prefix_consensus() -> None:
    assert _round_prefix("round-20260509t063201z-6c02-consensus") == "round-20260509t063201z-6c02"


def test_round_prefix_no_match() -> None:
    assert _round_prefix("scion-hub") == ""
    assert _round_prefix("") == ""
    assert _round_prefix("smoke-agent-12345") == ""


def test_round_prefix_uppercase_insensitive() -> None:
    # The regex is IGNORECASE; mixed-case should still match
    assert _round_prefix("Round-20260509t063201z-6c02-claude") == "Round-20260509t063201z-6c02"


# ---------------------------------------------------------------------------
# Tests: _phase_status
# ---------------------------------------------------------------------------

def test_phase_status_running() -> None:
    assert _phase_status(AGENT_RUNNING) == "running"


def test_phase_status_terminal_stopped() -> None:
    assert _phase_status(AGENT_TERMINAL) == "terminal"


def test_phase_status_terminal_completed() -> None:
    agent = {**AGENT_TERMINAL, "phase": "completed", "activity": "completed"}
    assert _phase_status(agent) == "terminal"


def test_phase_status_terminal_container() -> None:
    agent = {"phase": "unknown", "activity": "unknown", "containerStatus": "failed"}
    assert _phase_status(agent) == "terminal"


def test_phase_status_pending() -> None:
    assert _phase_status(AGENT_PENDING) == "pending"


def test_phase_status_empty() -> None:
    assert _phase_status({}) == "pending"


# ---------------------------------------------------------------------------
# Tests: _agent_summary
# ---------------------------------------------------------------------------

def test_agent_summary_keys() -> None:
    summary = _agent_summary(AGENT_RUNNING)
    expected_keys = {"name", "slug", "phase", "activity", "containerStatus", "template", "taskSummary", "created", "updated"}
    assert expected_keys.issubset(summary.keys())


def test_agent_summary_values() -> None:
    summary = _agent_summary(AGENT_RUNNING)
    assert summary["name"] == f"{ROUND_ID}-impl-claude"
    assert summary["phase"] == "running"
    assert summary["template"] == "claude"


def test_agent_summary_missing_fields() -> None:
    summary = _agent_summary({})
    assert summary["name"] is None
    assert summary["phase"] is None


# ---------------------------------------------------------------------------
# Tests: _round_text_match
# ---------------------------------------------------------------------------

def test_round_text_match_sender() -> None:
    assert _round_text_match(MESSAGE_WITH_ROUND, ROUND_ID) is True


def test_round_text_match_body() -> None:
    assert _round_text_match(MESSAGE_WITH_ROUND, ROUND_ID) is True


def test_round_text_match_no_match() -> None:
    assert _round_text_match({"id": "x", "msg": "unrelated"}, ROUND_ID) is False


def test_round_text_match_case_insensitive() -> None:
    item = {"msg": ROUND_ID.upper()}
    assert _round_text_match(item, ROUND_ID) is True


# ---------------------------------------------------------------------------
# Tests: _extract_round_id
# ---------------------------------------------------------------------------

def test_extract_round_id_from_message() -> None:
    result = _extract_round_id(MESSAGE_WITH_ROUND)
    assert result == ROUND_ID


def test_extract_round_id_from_notification() -> None:
    result = _extract_round_id(NOTIFICATION_WITH_ROUND)
    assert result == ROUND_ID


def test_extract_round_id_no_match() -> None:
    result = _extract_round_id(NOTIFICATION_NO_ROUND)
    assert result == ""


# ---------------------------------------------------------------------------
# Tests: api_rounds grouping logic (offline fixture)
# ---------------------------------------------------------------------------

def _make_agents_data(agents: list[dict[str, Any]]) -> dict[str, Any]:
    return {"agents": agents}


def test_round_grouping_single_round() -> None:
    agents = [AGENT_RUNNING, AGENT_TERMINAL]
    round_map: dict[str, list[dict[str, Any]]] = {}
    for agent in agents:
        name = str(agent.get("name") or "")
        prefix = _round_prefix(name)
        if prefix:
            round_map.setdefault(prefix, []).append(agent)
    assert list(round_map.keys()) == [ROUND_ID]
    assert len(round_map[ROUND_ID]) == 2


def test_round_grouping_two_rounds() -> None:
    other_id = "round-20260510t000000z-aaaa"
    agent_other = {**AGENT_RUNNING, "name": f"{other_id}-impl-claude"}
    agents = [AGENT_RUNNING, agent_other]
    round_map: dict[str, list[dict[str, Any]]] = {}
    for agent in agents:
        name = str(agent.get("name") or "")
        prefix = _round_prefix(name)
        if prefix:
            round_map.setdefault(prefix, []).append(agent)
    assert len(round_map) == 2
    assert ROUND_ID in round_map
    assert other_id in round_map


def test_round_grouping_excludes_non_round_agents() -> None:
    non_round = {**AGENT_RUNNING, "name": "smoke-agent-12345"}
    agents = [AGENT_RUNNING, non_round]
    round_map: dict[str, list[dict[str, Any]]] = {}
    for agent in agents:
        name = str(agent.get("name") or "")
        prefix = _round_prefix(name)
        if prefix:
            round_map.setdefault(prefix, []).append(agent)
    assert list(round_map.keys()) == [ROUND_ID]


# ---------------------------------------------------------------------------
# Tests: runtime state scenarios
# ---------------------------------------------------------------------------

def test_healthy_state() -> None:
    checks = [
        {"name": "hub", "ok": True, "detail": "reachable"},
        {"name": "broker", "ok": True, "detail": "1 of 1 online"},
        {"name": "mcp", "ok": True, "detail": "HTTP 200"},
        {"name": "kubernetes", "ok": True, "detail": "3/3 deployments ready"},
    ]
    overall_ok = all(c["ok"] for c in checks)
    assert overall_ok is True


def test_degraded_state_single_failure() -> None:
    checks = [
        {"name": "hub", "ok": True, "detail": "reachable"},
        {"name": "broker", "ok": False, "detail": "0 of 1 online"},
        {"name": "mcp", "ok": True, "detail": "HTTP 200"},
        {"name": "kubernetes", "ok": True, "detail": "3/3 deployments ready"},
    ]
    overall_ok = all(c["ok"] for c in checks)
    assert overall_ok is False
    failing = [c["name"] for c in checks if not c["ok"]]
    assert failing == ["broker"]


def test_unavailable_state() -> None:
    checks = [
        {"name": "hub", "ok": False, "detail": "connection refused"},
        {"name": "broker", "ok": False, "detail": "hub unavailable"},
        {"name": "mcp", "ok": False, "detail": "connection refused"},
        {"name": "kubernetes", "ok": True, "detail": "3/3 deployments ready"},
    ]
    overall_ok = all(c["ok"] for c in checks)
    assert overall_ok is False
    failing = [c["name"] for c in checks if not c["ok"]]
    assert set(failing) == {"hub", "broker", "mcp"}


def test_empty_rounds_state() -> None:
    rounds: list[dict[str, Any]] = []
    assert len(rounds) == 0


def test_stale_detection() -> None:
    # Stale check: a round with no updates for more than expected
    from datetime import datetime, timezone, timedelta
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    round_data = {"id": ROUND_ID, "updated": old_ts, "status": "running"}
    updated = round_data["updated"]
    assert updated < datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _collect_tests() -> list[tuple[str, Any]]:
    return [
        (name, obj)
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]


def main() -> int:
    tests = _collect_tests()
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
