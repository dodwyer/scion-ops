#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
# ]
# ///
"""Smoke test the scion-ops MCP server over stdio."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    params = StdioServerParameters(
        command="uv",
        args=["run", str(ROOT / "mcp_servers" / "scion_ops.py")],
        env={"SCION_OPS_ROOT": str(ROOT)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            required = {
                "scion_ops_list_agents",
                "scion_ops_round_status",
                "scion_ops_round_events",
                "scion_ops_watch_round_events",
                "scion_ops_start_round",
                "scion_ops_look",
            }
            missing = sorted(required - names)
            if missing:
                raise SystemExit(f"missing tools: {', '.join(missing)}")

            result = await session.call_tool("scion_ops_git_status", {})
            text = "\n".join(part.text for part in result.content if hasattr(part, "text"))
            agents = await session.call_tool("scion_ops_list_agents", {})
            agent_text = "\n".join(part.text for part in agents.content if hasattr(part, "text"))
            print(f"tools={len(names)}")
            print(text[:1000])
            print(agent_text[:1000])


if __name__ == "__main__":
    asyncio.run(main())
