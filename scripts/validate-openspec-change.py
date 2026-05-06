#!/usr/bin/env python3
"""Validate a repo-local OpenSpec change artifact set."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CHANGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REQUIRED_FILES = ("proposal.md", "design.md", "tasks.md")


@dataclass(frozen=True)
class Finding:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _has_heading(text: str) -> bool:
    return any(line.startswith("# ") for line in text.splitlines())


def _validate_required_file(path: Path, root: Path, findings: list[Finding]) -> None:
    rel = _relative(path, root)
    if not path.exists():
        findings.append(Finding(rel, "required file is missing"))
        return
    if not path.is_file():
        findings.append(Finding(rel, "required path is not a file"))
        return
    text = _read(path).strip()
    if not text:
        findings.append(Finding(rel, "required file is empty"))
        return
    if not _has_heading(text):
        findings.append(Finding(rel, "required file must include a top-level heading"))


def _validate_tasks(path: Path, root: Path, findings: list[Finding]) -> None:
    if not path.exists() or not path.is_file():
        return
    text = _read(path)
    if not re.search(r"(?m)^-\s+\[[ xX]\]\s+", text):
        findings.append(Finding(_relative(path, root), "tasks.md must include checkbox tasks"))


def _validate_spec_file(path: Path, root: Path, findings: list[Finding]) -> None:
    text = _read(path)
    rel = _relative(path, root)
    if not text.strip():
        findings.append(Finding(rel, "spec file is empty"))
        return
    if "### Requirement:" not in text:
        findings.append(Finding(rel, "spec file must include at least one requirement"))
    if "#### Scenario:" not in text:
        findings.append(Finding(rel, "spec file must include at least one scenario"))
    if not re.search(r"(?m)^## (ADDED|MODIFIED|REMOVED) Requirements\b", text):
        findings.append(
            Finding(rel, "delta spec should include ADDED, MODIFIED, or REMOVED Requirements section")
        )


def validate_openspec_change(project_root: Path, change: str) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    errors: list[Finding] = []
    warnings: list[Finding] = []

    if not root.exists():
        errors.append(Finding(str(root), "project root does not exist"))
        return _payload(root, change, errors, warnings, [], root / "openspec" / "changes" / change)
    if not root.is_dir():
        errors.append(Finding(str(root), "project root is not a directory"))
        return _payload(root, change, errors, warnings, [], root / "openspec" / "changes" / change)
    if not CHANGE_RE.match(change):
        errors.append(Finding(change, "change name must use letters, numbers, dots, dashes, or underscores"))
        return _payload(root, change, errors, warnings, [], root / "openspec" / "changes" / change)

    change_path = root / "openspec" / "changes" / change
    if not change_path.exists():
        errors.append(Finding(_relative(change_path, root), "change artifact directory is missing"))
        return _payload(root, change, errors, warnings, [], change_path)
    if not change_path.is_dir():
        errors.append(Finding(_relative(change_path, root), "change artifact path is not a directory"))
        return _payload(root, change, errors, warnings, [], change_path)

    for filename in REQUIRED_FILES:
        _validate_required_file(change_path / filename, root, errors)
    _validate_tasks(change_path / "tasks.md", root, errors)

    specs_dir = change_path / "specs"
    spec_files: list[Path] = []
    if not specs_dir.exists():
        errors.append(Finding(_relative(specs_dir, root), "specs directory is missing"))
    elif not specs_dir.is_dir():
        errors.append(Finding(_relative(specs_dir, root), "specs path is not a directory"))
    else:
        spec_files = sorted(path for path in specs_dir.glob("**/spec.md") if path.is_file())
        if not spec_files:
            errors.append(Finding(_relative(specs_dir, root), "no delta spec files found under specs/**/spec.md"))
        for path in spec_files:
            _validate_spec_file(path, root, errors)

    return _payload(root, change, errors, warnings, spec_files, change_path)


def _payload(
    root: Path,
    change: str,
    errors: list[Finding],
    warnings: list[Finding],
    spec_files: list[Path],
    change_path: Path,
) -> dict[str, Any]:
    required = {
        filename: str((change_path / filename).relative_to(root))
        if str(change_path).startswith(str(root))
        else str(change_path / filename)
        for filename in REQUIRED_FILES
    }
    return {
        "ok": not errors,
        "project_root": str(root),
        "change": change,
        "change_path": _relative(change_path, root),
        "required_files": required,
        "spec_files": [_relative(path, root) for path in spec_files],
        "errors": [finding.as_dict() for finding in errors],
        "warnings": [finding.as_dict() for finding in warnings],
    }


def _print_human(payload: dict[str, Any]) -> None:
    status = "ok" if payload["ok"] else "invalid"
    print(f"OpenSpec change {payload['change']}: {status}")
    print(f"project_root: {payload['project_root']}")
    print(f"change_path: {payload['change_path']}")
    if payload["spec_files"]:
        print("spec_files:")
        for path in payload["spec_files"]:
            print(f"  - {path}")
    if payload["errors"]:
        print("errors:")
        for item in payload["errors"]:
            print(f"  - {item['path']}: {item['message']}")
    if payload["warnings"]:
        print("warnings:")
        for item in payload["warnings"]:
            print(f"  - {item['path']}: {item['message']}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("positional_change", nargs="?", help="OpenSpec change name")
    parser.add_argument("--project-root", default=".", help="target project root")
    parser.add_argument("--change", default="", help="OpenSpec change name")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main() -> int:
    args = _parser().parse_args()
    change = (args.change or args.positional_change or "").strip()
    if not change:
        print("change is required", file=sys.stderr)
        return 2
    payload = validate_openspec_change(Path(args.project_root), change)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
