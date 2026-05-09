#!/usr/bin/env python3
"""Focused tests for final-review remediation routing."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "scripts" / "final_review_repair.py"


def _load_policy():
    spec = importlib.util.spec_from_file_location("final_review_repair", POLICY)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load final_review_repair.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["final_review_repair"] = module
    spec.loader.exec_module(module)
    return module


def _handoff() -> dict[str, object]:
    return {
        "integration_branch": "round-test-integration",
        "commit": "abc1234",
        "canonical_commands": ["task verify"],
        "observed_results": ["task verify passed"],
        "caveats": [],
        "source_branches": ["round-test-impl-codex", "round-test-impl-claude"],
    }


def main() -> int:
    policy = _load_policy()
    handoff = _handoff()

    expected = {
        "implementation_defect": ("implementer", "focused_implementation_repair", False),
        "integration_defect": ("integrator", "integration_repair", False),
        "verification_contract": ("verification_owner", "verification_contract_correction", True),
        "environment_failure": ("environment_owner", "retry_after_environment_recovery", True),
        "transient_agent_failure": ("coordinator", "retry_final_review_agent", True),
    }
    for classification, (owner, next_phase, preserved) in expected.items():
        route = policy.route_final_review_failure(
            classification,
            evidence=f"{classification} evidence",
            handoff=handoff,
            final_repair_rounds_used=0,
            policy=policy.FinalReviewRepairPolicy(max_final_repair_rounds=2),
        )
        assert route["status"] == "route", route
        assert route["owner"] == owner, route
        assert route["next_phase"] == next_phase, route
        assert route["preserve_integration_branch"] is preserved, route
        assert route["budget_consumed"] is True, route
        assert route["final_repair_rounds_used"] == 1, route
        assert route["handoff"] == handoff, route

    route = policy.route_final_review_failure(
        "transient_agent_failure",
        evidence="agent transport failure",
        handoff=handoff,
        route_history=[
            {
                "classification": "transient_agent_failure",
                "route": "retry_final_review_agent",
            }
        ],
        final_repair_rounds_used=2,
        policy=policy.FinalReviewRepairPolicy(max_final_repair_rounds=2),
    )
    assert route["status"] == "escalate", route
    assert route["budget_consumed"] is False, route
    assert route["max_final_repair_rounds"] == 2, route
    assert route["route_history"] == [
        {
            "classification": "transient_agent_failure",
            "route": "retry_final_review_agent",
        }
    ], route

    earlier_budgets = {
        "implementation_repair_rounds_used": 3,
        "peer_review_rounds_used": 3,
        "integration_repair_rounds_used": 1,
    }
    route = policy.route_final_review_failure(
        "environment_failure",
        evidence="registry unavailable",
        handoff=handoff,
        final_repair_rounds_used=0,
        policy=policy.FinalReviewRepairPolicy(max_final_repair_rounds=1),
    )
    assert route["status"] == "route", route
    assert route["final_repair_rounds_used"] == 1, route
    assert earlier_budgets == {
        "implementation_repair_rounds_used": 3,
        "peer_review_rounds_used": 3,
        "integration_repair_rounds_used": 1,
    }, earlier_budgets

    allowed, missing = policy.can_start_final_review(
        {
            "integration_branch": "round-test-integration",
            "canonical_commands": [],
            "observed_results": ["task verify passed"],
        }
    )
    assert allowed is False, missing
    assert missing == ["canonical_commands", "caveats"], missing

    route = policy.route_final_review_failure(
        "verification_contract",
        evidence="missing fixture argument",
        handoff=handoff,
        final_repair_rounds_used=0,
    )
    assert route["preserve_integration_branch"] is True, route
    assert route["requires_reintegration"] is False, route

    route = policy.route_final_review_failure(
        "implementation_defect",
        evidence="",
        handoff=handoff,
        final_repair_rounds_used=0,
    )
    assert route["status"] == "classification_clarification_required", route
    assert route["budget_consumed"] is False, route

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
