#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "PyYAML>=6,<7",
# ]
# ///
"""Exercise MCP OpenSpec CLI selection and fallback behavior."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_mcp_module():
    os.environ.setdefault("SCION_OPS_ROOT", str(ROOT))
    spec = importlib.util.spec_from_file_location("scion_ops_mcp", ROOT / "mcp_servers" / "scion_ops.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load mcp_servers/scion_ops.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["scion_ops_mcp"] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _sample_change(root: Path) -> None:
    change = root / "openspec" / "changes" / "add-widget"
    _write(change / "proposal.md", "# Proposal: Add Widget\n\nAdd widget behavior.\n")
    _write(change / "design.md", "# Design: Add Widget\n\nUse the existing path.\n")
    _write(change / "tasks.md", "# Tasks\n\n- [ ] 1.1 Add widget behavior\n")
    _write(
        change / "specs" / "widgets" / "spec.md",
        "# Delta for Widgets\n\n"
        "## ADDED Requirements\n\n"
        "### Requirement: Widget Creation\n"
        "The system SHALL create a widget.\n\n"
        "#### Scenario: Create widget\n"
        "- GIVEN a valid request\n"
        "- WHEN the widget is created\n"
        "- THEN the widget is visible\n",
    )


def _fake_openspec(bin_dir: Path) -> None:
    script = bin_dir / "openspec"
    script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import sys

            args = sys.argv[1:]
            if args and args[0] == "validate":
                change = args[1]
                print(json.dumps({
                    "items": [{"id": change, "type": "change", "valid": True, "issues": []}],
                    "summary": {"totals": {"items": 1, "passed": 1, "failed": 0}},
                    "version": "1.0",
                }))
                raise SystemExit(0)
            if args and args[0] == "status":
                change = args[args.index("--change") + 1]
                print(json.dumps({
                    "changeName": change,
                    "isComplete": True,
                    "artifacts": [{"id": "tasks", "outputPath": "tasks.md", "status": "done"}],
                }))
                raise SystemExit(0)
            raise SystemExit(2)
            """
        )
    )
    script.chmod(0o755)


def main() -> int:
    module = _load_mcp_module()
    old_path = os.environ.get("PATH", "")
    old_cli_flag = os.environ.get("SCION_OPS_USE_OPENSPEC_CLI")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            _sample_change(root)
            _fake_openspec(bin_dir)

            os.environ["PATH"] = f"{bin_dir}:{old_path}"
            os.environ["SCION_OPS_USE_OPENSPEC_CLI"] = "1"

            result, payload = module._validate_spec_change_result(root, "add-widget")
            assert result["source"] == "openspec_cli", result
            assert payload["validator"] == "openspec_cli", payload
            assert payload["ok"] is True, payload
            assert payload["spec_files"] == ["openspec/changes/add-widget/specs/widgets/spec.md"], payload

            status_result, status = module._openspec_status_result(root, "add-widget")
            assert status_result["source"] == "openspec_cli_status", status_result
            assert status["changeName"] == "add-widget", status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            _sample_change(root)
            os.environ["SCION_OPS_USE_OPENSPEC_CLI"] = "0"
            result, payload = module._validate_spec_change_result(root, "add-widget")
            assert result["source"] == "scion_ops_python", result
            assert payload["validator"] == "scion_ops_python", payload
            assert payload["ok"] is True, payload
            assert "openspec_cli_attempt" not in payload, payload
    finally:
        os.environ["PATH"] = old_path
        if old_cli_flag is None:
            os.environ.pop("SCION_OPS_USE_OPENSPEC_CLI", None)
        else:
            os.environ["SCION_OPS_USE_OPENSPEC_CLI"] = old_cli_flag

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
