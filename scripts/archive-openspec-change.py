#!/usr/bin/env python3
"""Archive an accepted OpenSpec change and sync its delta specs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate-openspec-change.py"


def _run_validator(project_root: Path, change: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "python3",
            str(VALIDATOR),
            "--project-root",
            str(project_root),
            "--change",
            change,
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "errors": [{"path": str(project_root), "message": result.stdout.strip()}],
        }
    payload["validator_returncode"] = result.returncode
    return payload


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _archive_path(root: Path, change: str) -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_root = root / "openspec" / "changes" / "archive"
    candidate = archive_root / f"{date}-{change}"
    if not candidate.exists():
        return candidate
    suffix = datetime.now(timezone.utc).strftime("%H%M%S")
    return archive_root / f"{date}-{change}-{suffix}"


def _spec_title(path: Path) -> str:
    domain = path.parent.name.replace("-", " ").replace("_", " ").strip()
    return f"{domain.title()} Specification" if domain else "Specification"


def _sync_spec(source: Path, target: Path, root: Path, change: str) -> dict[str, str]:
    source_rel = _relative(source, root)
    target_rel = _relative(target, root)
    marker_start = f"<!-- scion-ops:accepted-change {change} source={source_rel} -->"
    marker_end = f"<!-- /scion-ops:accepted-change {change} -->"
    source_text = source.read_text(errors="replace").strip()
    block = f"\n\n{marker_start}\n{source_text}\n{marker_end}\n"

    if target.exists():
        existing = target.read_text(errors="replace")
        if marker_start in existing:
            return {"source": source_rel, "target": target_rel, "action": "already_synced"}
        target.write_text(existing.rstrip() + block)
        return {"source": source_rel, "target": target_rel, "action": "appended"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"# {_spec_title(target)}\n\n## Accepted Changes{block}")
    return {"source": source_rel, "target": target_rel, "action": "created"}


def archive_change(project_root: Path, change: str, apply: bool) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    validation = _run_validator(root, change)
    change_path = root / "openspec" / "changes" / change
    archive_path = _archive_path(root, change)
    spec_sources = [root / path for path in validation.get("spec_files", [])]

    plan = {
        "ok": bool(validation.get("ok")),
        "dry_run": not apply,
        "project_root": str(root),
        "change": change,
        "change_path": _relative(change_path, root),
        "archive_path": _relative(archive_path, root),
        "validation": validation,
        "synced_specs": [],
    }
    if not validation.get("ok"):
        plan["ok"] = False
        return plan

    if not apply:
        plan["synced_specs"] = [
            {
                "source": _relative(source, root),
                "target": _relative(root / "openspec" / "specs" / source.relative_to(change_path / "specs"), root),
                "action": "would_sync",
            }
            for source in spec_sources
        ]
        return plan

    synced_specs = []
    try:
        for source in spec_sources:
            target = root / "openspec" / "specs" / source.relative_to(change_path / "specs")
            synced_specs.append(_sync_spec(source, target, root, change))

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(change_path), str(archive_path))
    except OSError as exc:
        plan["ok"] = False
        plan["errors"] = [{"path": _relative(root, root), "message": f"{type(exc).__name__}: {exc}"}]
        plan["synced_specs"] = synced_specs
        return plan
    plan["synced_specs"] = synced_specs
    plan["dry_run"] = False
    plan["ok"] = True
    return plan


def _print_human(payload: dict[str, Any]) -> None:
    action = "planned" if payload["dry_run"] else "archived"
    print(f"OpenSpec change {payload['change']}: {action}")
    print(f"project_root: {payload['project_root']}")
    print(f"archive_path: {payload['archive_path']}")
    if not payload["ok"]:
        print("errors:")
        for item in payload.get("errors", []):
            print(f"  - {item.get('path')}: {item.get('message')}")
        for item in payload.get("validation", {}).get("errors", []):
            print(f"  - {item.get('path')}: {item.get('message')}")
    if payload["synced_specs"]:
        print("synced_specs:")
        for item in payload["synced_specs"]:
            print(f"  - {item['source']} -> {item['target']} ({item['action']})")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="target project root")
    parser.add_argument("--change", required=True, help="OpenSpec change name")
    parser.add_argument("--yes", action="store_true", help="apply the archive and spec sync")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = archive_change(Path(args.project_root), args.change, apply=args.yes)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)
        if not args.yes and payload["ok"]:
            print("Re-run with --yes to apply.")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
