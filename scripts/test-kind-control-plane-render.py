#!/usr/bin/env python3
"""Rendered-manifest checks for the kind control plane."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def render() -> str:
    result = subprocess.run(
        ["kubectl", "kustomize", "deploy/kind/control-plane"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    return result.stdout


def test_web_resources_render() -> None:
    output = render()
    assert "kind: Deployment\n" in output
    assert "name: scion-ops-web" in output
    assert "kind: Service\n" in output
    assert "nodePort: 30878" in output
    assert "serviceAccountName: scion-ops-web" in output
    assert "SCION_OPS_MCP_URL" in output
    assert "http://scion-ops-mcp:8765/mcp" in output


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
