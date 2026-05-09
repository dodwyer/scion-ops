#!/usr/bin/env python3
"""Validate representative verdict payloads against rubric/verdict.schema.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "rubric" / "verdict.schema.json"


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return True


def _validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _type_ok(value, expected_type):
        return [f"{path}: expected {expected_type}"]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not in enum")

    if expected_type == "integer":
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: value below minimum")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: value above maximum")

    if expected_type == "object":
        required = set(schema.get("required", []))
        missing = sorted(required - set(value))
        errors.extend(f"{path}.{key}: required property missing" for key in missing)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            errors.extend(f"{path}.{key}: additional property not allowed" for key in extra)
        for key, item in value.items():
            if key in properties:
                errors.extend(_validate(item, properties[key], f"{path}.{key}"))

    if expected_type == "array":
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            errors.extend(_validate(item, item_schema, f"{path}[{index}]"))

    return errors


def main() -> int:
    schema = json.loads(SCHEMA.read_text())
    samples = [
        {
            "scores": {"correctness": 4, "completeness": 5, "style": 4},
            "verdict": "accept",
            "blocking_issues": [],
            "nits": [],
            "summary": "Legacy implementation verdict remains valid.",
        },
        {
            "review_type": "implementation",
            "scores": {"correctness": 5, "completeness": 4, "style": 4},
            "verdict": "accept",
            "blocking_issues": [],
            "nits": [],
            "spec": {
                "change": "add-widget",
                "conformance": 5,
                "spec_completeness": 4,
                "task_coverage": 4,
                "operational_verification": 5,
                "checked_artifacts": [
                    "openspec/changes/add-widget/proposal.md",
                    "openspec/changes/add-widget/tasks.md",
                ],
                "unresolved_questions": [],
                "gaps": [],
            },
            "summary": "Implementation quality: tests pass. Spec conformance: matches the approved change.",
        },
        {
            "review_type": "spec",
            "scores": {"correctness": 3, "completeness": 3, "style": 4},
            "verdict": "request_changes",
            "blocking_issues": ["tasks.md does not cover rollback verification"],
            "nits": [],
            "spec": {
                "change": "add-widget",
                "conformance": 3,
                "spec_completeness": 3,
                "task_coverage": 2,
                "operational_verification": 2,
                "checked_artifacts": [
                    "openspec/changes/add-widget/proposal.md",
                    "openspec/changes/add-widget/design.md",
                    "openspec/changes/add-widget/tasks.md",
                    "openspec/changes/add-widget/specs/widgets/spec.md",
                ],
                "unresolved_questions": ["Which verification command is authoritative?"],
                "gaps": ["No operational rollback task."],
            },
            "summary": "Spec review found blocking operational gaps.",
        },
        {
            "review_type": "final",
            "scores": {"correctness": 2, "completeness": 4, "style": 4},
            "verdict": "request_changes",
            "blocking_issues": ["tests failing on integrated branch"],
            "final_failure_classification": "integration_defect",
            "final_failure_evidence": "The integration branch omitted a required file from the accepted implementation.",
            "nits": [],
            "summary": "Final review found an integration assembly defect.",
        },
    ]
    failures: list[str] = []
    for index, sample in enumerate(samples):
        failures.extend(f"sample {index}: {error}" for error in _validate(sample, schema))
    if failures:
        raise SystemExit("\n".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
