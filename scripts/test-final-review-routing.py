#!/usr/bin/env python3
"""Fixtures and routing-matrix tests for the final-review repair loop."""

from __future__ import annotations


ROUTING: dict[str, str] = {
    "implementation_defect": "focused_impl_repair_then_peer_review",
    "integration_defect": "integrator_repair_then_retry",
    "verification_contract": "process_correction_preserve_branch",
    "environment_failure": "retry_or_escalate",
    "transient_agent_failure": "retry_or_escalate",
}

BRANCH_PRESERVING: frozenset[str] = frozenset(
    {"verification_contract", "environment_failure", "transient_agent_failure"}
)

HANDOFF_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"branch", "verification_commands", "observed_results"}
)


def route_failure(failure_class: str) -> str:
    if failure_class not in ROUTING:
        raise ValueError(f"Unknown failure class: {failure_class!r}")
    return ROUTING[failure_class]


def check_handoff(handoff: dict) -> list[str]:
    missing = sorted(HANDOFF_REQUIRED_FIELDS - set(handoff.keys()))
    if "verification_commands" not in missing:
        cmds = handoff.get("verification_commands")
        if not cmds:
            missing = sorted(set(missing) | {"verification_commands"})
    return missing


def is_budget_exhausted(final_repair_rounds_used: int, max_final_repair_rounds: int) -> bool:
    return final_repair_rounds_used >= max_final_repair_rounds


def preserves_branch(failure_class: str) -> bool:
    return failure_class in BRANCH_PRESERVING


def test_routing_matrix() -> None:
    assert route_failure("implementation_defect") == "focused_impl_repair_then_peer_review"
    assert route_failure("integration_defect") == "integrator_repair_then_retry"
    assert route_failure("verification_contract") == "process_correction_preserve_branch"
    assert route_failure("environment_failure") == "retry_or_escalate"
    assert route_failure("transient_agent_failure") == "retry_or_escalate"

    try:
        route_failure("unknown_class")
        raise AssertionError("expected ValueError for unknown class")
    except ValueError:
        pass


def test_all_classes_covered() -> None:
    expected = {
        "implementation_defect",
        "integration_defect",
        "verification_contract",
        "environment_failure",
        "transient_agent_failure",
    }
    assert set(ROUTING.keys()) == expected, f"routing keys mismatch: {set(ROUTING.keys())}"


def test_branch_preservation() -> None:
    assert preserves_branch("verification_contract") is True
    assert preserves_branch("environment_failure") is True
    assert preserves_branch("transient_agent_failure") is True
    assert preserves_branch("implementation_defect") is False
    assert preserves_branch("integration_defect") is False


def test_budget_exhaustion() -> None:
    assert is_budget_exhausted(0, 2) is False
    assert is_budget_exhausted(1, 2) is False
    assert is_budget_exhausted(2, 2) is True
    assert is_budget_exhausted(3, 2) is True
    # final repair budget is independent from earlier repair counters
    assert is_budget_exhausted(0, 2) is False  # 0 final-repair cycles != exhausted
    assert is_budget_exhausted(10, 2) is True   # 10 final-repair cycles > budget of 2


def test_handoff_enforcement() -> None:
    complete = {
        "branch": "round-abc123-integration",
        "commit": "deadbeef",
        "verification_commands": ["task verify"],
        "observed_results": "all tests passed",
        "caveats": [],
    }
    assert check_handoff(complete) == []

    missing_commands = {
        "branch": "round-abc123-integration",
        "observed_results": "passed",
    }
    assert "verification_commands" in check_handoff(missing_commands)

    empty_commands = {
        "branch": "round-abc123-integration",
        "verification_commands": [],
        "observed_results": "passed",
    }
    assert "verification_commands" in check_handoff(empty_commands)

    missing_branch = {
        "verification_commands": ["task verify"],
        "observed_results": "passed",
    }
    assert "branch" in check_handoff(missing_branch)

    empty: dict = {}
    assert set(check_handoff(empty)) == HANDOFF_REQUIRED_FIELDS


def test_representative_final_review_states() -> None:
    base_handoff = {
        "branch": "round-20260509t120000z-test-integration",
        "commit": "abc123",
        "verification_commands": ["task verify"],
        "observed_results": "all 42 tests passed",
        "caveats": [],
    }
    base_final_review: dict = {
        "final_repair_rounds_used": 0,
        "max_final_repair_rounds": 2,
        "repair_history": [],
    }

    # Fixture: implementation defect routed to focused repair
    state_impl = {
        "round_id": "20260509t120000z-test",
        "status": "running",
        "integration": {"branch": base_handoff["branch"], "verification_handoff": base_handoff},
        "final_review": {
            **base_final_review,
            "final_repair_rounds_used": 1,
            "repair_history": [
                {
                    "cycle": 1,
                    "failure_class": "implementation_defect",
                    "evidence": "test_widget_creation fails: expected 200 got 404",
                    "route": route_failure("implementation_defect"),
                }
            ],
        },
    }
    assert state_impl["final_review"]["repair_history"][0]["route"] == "focused_impl_repair_then_peer_review"
    assert not preserves_branch("implementation_defect")

    # Fixture: verification contract — branch must stay accepted
    state_vc = {
        "round_id": "20260509t120000z-test",
        "status": "running",
        "integration": {"branch": base_handoff["branch"], "verification_handoff": base_handoff},
        "final_review": {
            **base_final_review,
            "final_repair_rounds_used": 1,
            "repair_history": [
                {
                    "cycle": 1,
                    "failure_class": "verification_contract",
                    "evidence": "task verify command not found in container",
                    "route": route_failure("verification_contract"),
                }
            ],
        },
    }
    assert state_vc["final_review"]["repair_history"][0]["route"] == "process_correction_preserve_branch"
    assert preserves_branch("verification_contract")

    # Fixture: budget exhausted after two transient failures
    state_exhausted = {
        "round_id": "20260509t120000z-test",
        "status": "escalate",
        "integration": {"branch": base_handoff["branch"], "verification_handoff": base_handoff},
        "final_review": {
            "final_repair_rounds_used": 2,
            "max_final_repair_rounds": 2,
            "repair_history": [
                {
                    "cycle": 1,
                    "failure_class": "transient_agent_failure",
                    "evidence": "agent timed out after 90m",
                    "route": route_failure("transient_agent_failure"),
                },
                {
                    "cycle": 2,
                    "failure_class": "transient_agent_failure",
                    "evidence": "agent timed out again",
                    "route": route_failure("transient_agent_failure"),
                },
            ],
        },
    }
    assert is_budget_exhausted(
        state_exhausted["final_review"]["final_repair_rounds_used"],
        state_exhausted["final_review"]["max_final_repair_rounds"],
    )
    assert state_exhausted["status"] == "escalate"
    # environment_failure and transient don't mark branches defective
    for entry in state_exhausted["final_review"]["repair_history"]:
        assert preserves_branch(entry["failure_class"])

    # Fixture: integration defect with refreshed handoff after repair
    refreshed_handoff = {**base_handoff, "verification_commands": ["task verify", "kubectl get pods"]}
    state_int_defect = {
        "round_id": "20260509t120000z-test",
        "status": "running",
        "integration": {
            "branch": "round-20260509t120000z-test-integration-r1",
            "verification_handoff": refreshed_handoff,
        },
        "final_review": {
            **base_final_review,
            "final_repair_rounds_used": 1,
            "repair_history": [
                {
                    "cycle": 1,
                    "failure_class": "integration_defect",
                    "evidence": "merge conflict left marker in config.yaml",
                    "route": route_failure("integration_defect"),
                }
            ],
        },
    }
    assert state_int_defect["final_review"]["repair_history"][0]["route"] == "integrator_repair_then_retry"
    assert check_handoff(state_int_defect["integration"]["verification_handoff"]) == []


def main() -> int:
    tests = [
        test_routing_matrix,
        test_all_classes_covered,
        test_branch_preservation,
        test_budget_exhaustion,
        test_handoff_enforcement,
        test_representative_final_review_states,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures.append(f"{test.__name__}: {exc}")
        except Exception as exc:
            failures.append(f"{test.__name__}: unexpected error: {exc}")
    if failures:
        raise SystemExit("\n".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
