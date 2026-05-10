#!/usr/bin/env python3
"""Final-review remediation routing policy for implementation steward sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FINAL_REVIEW_FAILURE_CLASSES = {
    "implementation_defect",
    "integration_defect",
    "verification_contract",
    "environment_failure",
    "transient_agent_failure",
}


@dataclass(frozen=True)
class FinalReviewRepairPolicy:
    max_final_repair_rounds: int = 2


_ROUTES: dict[str, dict[str, Any]] = {
    "implementation_defect": {
        "owner": "implementer",
        "next_phase": "focused_implementation_repair",
        "requires_peer_review": True,
        "requires_reintegration": True,
        "requires_refreshed_handoff": True,
        "preserve_integration_branch": False,
    },
    "integration_defect": {
        "owner": "integrator",
        "next_phase": "integration_repair",
        "requires_peer_review": False,
        "requires_reintegration": False,
        "requires_refreshed_handoff": True,
        "preserve_integration_branch": False,
    },
    "verification_contract": {
        "owner": "verification_owner",
        "next_phase": "verification_contract_correction",
        "requires_peer_review": False,
        "requires_reintegration": False,
        "requires_refreshed_handoff": True,
        "preserve_integration_branch": True,
    },
    "environment_failure": {
        "owner": "environment_owner",
        "next_phase": "retry_after_environment_recovery",
        "requires_peer_review": False,
        "requires_reintegration": False,
        "requires_refreshed_handoff": False,
        "preserve_integration_branch": True,
    },
    "transient_agent_failure": {
        "owner": "coordinator",
        "next_phase": "retry_final_review_agent",
        "requires_peer_review": False,
        "requires_reintegration": False,
        "requires_refreshed_handoff": False,
        "preserve_integration_branch": True,
    },
}


def validate_final_review_handoff(handoff: dict[str, Any] | None) -> list[str]:
    """Return missing handoff fields that block final review startup."""
    missing: list[str] = []
    handoff = handoff or {}
    if not str(handoff.get("integration_branch") or "").strip():
        missing.append("integration_branch")
    if not _non_empty_list(handoff.get("canonical_commands")):
        missing.append("canonical_commands")
    if not _non_empty_list(handoff.get("observed_results")):
        missing.append("observed_results")
    if "caveats" not in handoff:
        missing.append("caveats")
    return missing


def can_start_final_review(handoff: dict[str, Any] | None) -> tuple[bool, list[str]]:
    missing = validate_final_review_handoff(handoff)
    return not missing, missing


def route_final_review_failure(
    failure_classification: str,
    *,
    evidence: str,
    handoff: dict[str, Any],
    final_repair_rounds_used: int,
    policy: FinalReviewRepairPolicy | None = None,
    route_history: list[Any] | None = None,
) -> dict[str, Any]:
    """Return the remediation route for a classified final-review failure."""
    policy = policy or FinalReviewRepairPolicy()
    if failure_classification not in FINAL_REVIEW_FAILURE_CLASSES:
        return {
            "status": "classification_required",
            "reason": "unsupported final-review failure classification",
            "budget_consumed": False,
        }
    if not str(evidence or "").strip():
        return {
            "status": "classification_clarification_required",
            "classification": failure_classification,
            "reason": "classification evidence is required before routing",
            "budget_consumed": False,
        }
    allowed, missing = can_start_final_review(handoff)
    if not allowed:
        return {
            "status": "handoff_correction_required",
            "classification": failure_classification,
            "missing_handoff_fields": missing,
            "budget_consumed": False,
            "preserve_integration_branch": True,
        }
    if final_repair_rounds_used >= policy.max_final_repair_rounds:
        return {
            "status": "escalate",
            "classification": failure_classification,
            "reason": "max_final_repair_rounds exhausted",
            "max_final_repair_rounds": policy.max_final_repair_rounds,
            "final_repair_rounds_used": final_repair_rounds_used,
            "budget_consumed": False,
            "handoff": handoff,
            "evidence": evidence,
            "route_history": route_history if route_history is not None else [],
        }

    route = dict(_ROUTES[failure_classification])
    route.update(
        {
            "status": "route",
            "classification": failure_classification,
            "evidence": evidence,
            "budget_consumed": True,
            "max_final_repair_rounds": policy.max_final_repair_rounds,
            "final_repair_rounds_used": final_repair_rounds_used + 1,
            "handoff": handoff,
        }
    )
    return route


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)
