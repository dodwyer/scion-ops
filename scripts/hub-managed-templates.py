#!/usr/bin/env python3
"""Repair and verify scion-ops managed Hub template records."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


EXPECTED_HARNESS = {
    "spec-goal-clarifier": "codex-exec",
    "spec-goal-clarifier-claude": "claude",
    "spec-repo-explorer": "codex-exec",
    "spec-author": "codex-exec",
    "spec-ops-reviewer": "codex-exec",
    "spec-ops-reviewer-claude": "claude",
    "spec-finalizer": "codex-exec",
    "spec-steward": "codex-exec",
    "implementation-steward": "codex-exec",
    "impl-codex": "codex-exec",
    "reviewer-codex": "codex-exec",
    "final-reviewer-codex": "codex-exec",
}

DEPRECATED_TEMPLATE_NAMES = {
    "consensus-runner",
    "spec-consensus-runner",
}


def die(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def endpoint() -> str:
    value = os.environ.get("SCION_HUB_ENDPOINT") or os.environ.get("HUB_ENDPOINT")
    if not value:
        die("SCION_HUB_ENDPOINT is not set")
    return value.rstrip("/")


def token() -> str:
    value = os.environ.get("SCION_DEV_TOKEN")
    if value:
        return value.strip()

    token_file = os.environ.get("SCION_DEV_TOKEN_FILE")
    paths = [Path(token_file)] if token_file else []
    paths.append(Path.home() / ".scion" / "dev-token")
    for path in paths:
        if path.is_file():
            return path.read_text().strip()

    die("Hub dev auth is unavailable")
    raise AssertionError("unreachable")


def request_json(path: str, method: str = "GET") -> dict[str, Any]:
    req = urllib.request.Request(
        endpoint() + path,
        headers={"Authorization": f"Bearer {token()}"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if method == "DELETE":
                return {}
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        die(f"Hub API {method} {path} failed: HTTP {exc.code} {detail}")
    except urllib.error.URLError as exc:
        die(f"Hub API {method} {path} failed: {exc.reason}")
    raise AssertionError("unreachable")


def list_templates() -> list[dict[str, Any]]:
    data = request_json("/api/v1/templates?limit=1000")
    templates = data.get("templates")
    if not isinstance(templates, list):
        die("Hub API did not return a templates list")
    return [item for item in templates if isinstance(item, dict)]


def is_active(template: dict[str, Any]) -> bool:
    status = str(template.get("status") or "active").lower()
    return status != "deleted" and not template.get("deletedAt") and not template.get("deleted")


def scope(template: dict[str, Any]) -> str:
    return str(template.get("scope") or "")


def name(template: dict[str, Any]) -> str:
    return str(template.get("name") or template.get("slug") or "")


def template_id(template: dict[str, Any]) -> str:
    return str(template.get("id") or "")


def harness(template: dict[str, Any]) -> str:
    return str(template.get("harness") or "")


def content_hash(template: dict[str, Any]) -> str:
    return str(template.get("contentHash") or "")


def managed_templates() -> list[dict[str, Any]]:
    return [
        template
        for template in list_templates()
        if is_active(template) and name(template) in EXPECTED_HARNESS
    ]


def deprecated_templates() -> list[dict[str, Any]]:
    return [
        template
        for template in list_templates()
        if is_active(template) and name(template) in DEPRECATED_TEMPLATE_NAMES
    ]


def delete_template(template: dict[str, Any], reason: str) -> None:
    tid = template_id(template)
    if not tid:
        die(f"cannot delete Hub template {name(template)} without an id")
    print(
        "deleting stale Hub template "
        f"{name(template)} ({scope(template) or '<unknown-scope>'}, {tid}): {reason}"
    )
    request_json(f"/api/v1/templates/{tid}", method="DELETE")


def repair_before_sync() -> None:
    for template in deprecated_templates():
        delete_template(template, "deprecated steward-only orchestration path")

    for template in managed_templates():
        want = EXPECTED_HARNESS[name(template)]
        actual = harness(template)
        if actual != want:
            delete_template(
                template,
                f"harness {actual or '<empty>'}, expected {want}",
            )


def canonical_globals(templates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    globals_by_name: dict[str, dict[str, Any]] = {}
    for template in templates:
        template_name = name(template)
        if scope(template) == "global" and harness(template) == EXPECTED_HARNESS[template_name]:
            globals_by_name[template_name] = template
    return globals_by_name


def repair_shadowing() -> None:
    for template in deprecated_templates():
        delete_template(template, "deprecated steward-only orchestration path")

    templates = managed_templates()
    globals_by_name = canonical_globals(templates)

    for template in templates:
        template_name = name(template)
        want = EXPECTED_HARNESS[template_name]
        if harness(template) != want:
            delete_template(
                template,
                f"harness {harness(template) or '<empty>'}, expected {want}",
            )
            continue

        if scope(template) == "global":
            continue

        canonical = globals_by_name.get(template_name)
        if not canonical:
            continue

        if content_hash(template) != content_hash(canonical):
            delete_template(
                template,
                "scoped override content differs from the managed global template",
            )


def verify() -> None:
    templates = managed_templates()
    globals_by_name = canonical_globals(templates)
    errors: list[str] = []

    for template in deprecated_templates():
        errors.append(
            f"{name(template)}: {scope(template) or '<unknown-scope>'} template "
            "is deprecated and must not remain active"
        )

    for template_name, want in EXPECTED_HARNESS.items():
        canonical = globals_by_name.get(template_name)
        if not canonical:
            errors.append(f"{template_name}: missing active global template with harness {want}")
            continue
        if not content_hash(canonical):
            errors.append(f"{template_name}: active global template is missing contentHash")

    for template in templates:
        template_name = name(template)
        want = EXPECTED_HARNESS[template_name]
        actual = harness(template)
        if actual != want:
            errors.append(
                f"{template_name}: {scope(template) or '<unknown-scope>'} template "
                f"uses harness {actual or '<empty>'}, expected {want}"
            )
            continue

        if scope(template) == "global":
            continue

        canonical = globals_by_name.get(template_name)
        if not canonical:
            continue

        if content_hash(template) != content_hash(canonical):
            errors.append(
                f"{template_name}: {scope(template) or '<unknown-scope>'} template "
                "shadows the managed global template with different content"
            )

    if errors:
        print("Hub managed template records are not ready:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)

    print("Hub managed template records are ready")


def main() -> None:
    if len(sys.argv) != 2:
        die("usage: hub-managed-templates.py repair-before-sync|repair-shadowing|verify")

    command = sys.argv[1]
    if command == "repair-before-sync":
        repair_before_sync()
    elif command == "repair-shadowing":
        repair_shadowing()
    elif command == "verify":
        verify()
    else:
        die(f"unknown command: {command}")


if __name__ == "__main__":
    main()
