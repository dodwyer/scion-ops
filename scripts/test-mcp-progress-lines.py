#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "PyYAML>=6,<7",
# ]
# ///
"""Exercise compact MCP progress line helpers."""

from __future__ import annotations

import importlib.util
import os
import sys
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


def main() -> int:
    module = _load_mcp_module()
    progress = {
        "agent_count": 3,
        "active_agents": [
            {
                "name": "round-test-spec-consensus",
                "health": "running",
                "summary": "",
            }
        ],
        "completed_agents": [
            {
                "name": "round-test-spec-author",
                "health": "completed",
                "summary": "wrote OpenSpec artifacts",
            }
        ],
        "unhealthy_agents": [
            {
                "name": "round-test-spec-review",
                "health": "stalled",
                "summary": "waiting for branch",
            }
        ],
    }

    lines = module._round_progress_lines(
        round_id="test",
        status="running_degraded",
        progress=progress,
        validation_status="pending",
        warnings=["integration branch validates; waiting for finalizer"],
    )
    assert lines[0] == "round test running_degraded agents=3 active=1 complete=1 unhealthy=1 validation=pending"
    assert "agent round-test-spec-consensus running" in lines
    assert "agent round-test-spec-author complete wrote OpenSpec artifacts" in lines
    assert "agent round-test-spec-review stalled waiting for branch" in lines
    assert lines[-1] == "warning integration branch validates; waiting for finalizer"

    complete_lines = module._round_progress_lines(
        round_id="test",
        status="completed",
        progress={**progress, "active_agents": [], "unhealthy_agents": []},
        validation_status="passed",
        pr_ready_branch="round-test-spec-integration",
    )
    assert complete_lines[0] == "round test completed agents=3 active=0 complete=1 unhealthy=0 validation=passed"
    assert complete_lines[-1] == "round test complete branch round-test-spec-integration"

    missing_terminal = {
        "ok": False,
        "output": "failed to capture terminal output: not_found: Action not found (status: 404)",
    }
    assert module._looks_like_missing_terminal_output(missing_terminal)

    auth_failure = {"ok": False, "output": "failed to capture terminal output: unauthorized"}
    assert not module._looks_like_missing_terminal_output(auth_failure)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
