#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
# ]
# ///
"""Smoke test the scion-ops MCP server."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://192.168.122.103:8765/mcp"
REQUIRED_TOOLS = {
    "scion_ops_list_agents",
    "scion_ops_round_status",
    "scion_ops_round_events",
    "scion_ops_watch_round_events",
    "scion_ops_start_round",
    "scion_ops_validate_spec_change",
    "scion_ops_spec_status",
    "scion_ops_archive_spec_change",
    "scion_ops_start_spec_round",
    "scion_ops_start_impl_round",
    "scion_ops_look",
}


def _text(result: object) -> str:
    content = getattr(result, "content", [])
    return "\n".join(part.text for part in content if hasattr(part, "text"))


async def _exercise_session(session: ClientSession) -> set[str]:
    await session.initialize()
    tools = await session.list_tools()
    names = {tool.name for tool in tools.tools}
    missing = sorted(REQUIRED_TOOLS - names)
    if missing:
        raise SystemExit(f"missing tools: {', '.join(missing)}")

    result = await session.call_tool("scion_ops_git_status", {})
    hub = await session.call_tool("scion_ops_hub_status", {})
    agents = await session.call_tool("scion_ops_list_agents", {})
    print(f"tools={len(names)}")
    print(_text(result)[:1000])
    print(_text(hub)[:1000])
    print(_text(agents)[:1000])
    return names


async def _smoke_stdio() -> None:
    env = os.environ.copy()
    env["SCION_OPS_ROOT"] = str(ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    params = StdioServerParameters(
        command="uv",
        args=["run", str(ROOT / "mcp_servers" / "scion_ops.py")],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await _exercise_session(session)


async def _smoke_http(url: str) -> None:
    async with streamablehttp_client(url, timeout=5, sse_read_timeout=30) as (read, write, _):
        async with ClientSession(read, write) as session:
            await _exercise_session(session)


async def _start_http_server(host: str, port: int, path: str) -> asyncio.subprocess.Process:
    env = os.environ.copy()
    env.update(
        {
            "SCION_OPS_ROOT": str(ROOT),
            "SCION_OPS_MCP_TRANSPORT": "streamable-http",
            "SCION_OPS_MCP_HOST": host,
            "SCION_OPS_MCP_PORT": str(port),
            "SCION_OPS_MCP_PATH": path,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return await asyncio.create_subprocess_exec(
        "uv",
        "run",
        str(ROOT / "mcp_servers" / "scion_ops.py"),
        cwd=ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def _wait_for_http(
    url: str,
    process: asyncio.subprocess.Process | None,
    timeout_seconds: int,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last_error = ""
    while asyncio.get_running_loop().time() <= deadline:
        if process and process.returncode is not None:
            output = ""
            if process.stdout:
                output = (await process.stdout.read()).decode(errors="replace")
            raise RuntimeError(f"HTTP MCP server exited early with {process.returncode}\n{output}")
        try:
            await _smoke_http(url)
            return
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(0.5)
    raise RuntimeError(f"HTTP MCP server was not ready at {url}: {last_error}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--url", default=os.environ.get("SCION_OPS_MCP_URL", DEFAULT_URL))
    parser.add_argument(
        "--start-server",
        action="store_true",
        help="start a temporary HTTP server if the URL is unavailable",
    )
    parser.add_argument("--host", default=os.environ.get("SCION_OPS_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SCION_OPS_MCP_PORT", "8765")))
    parser.add_argument("--path", default=os.environ.get("SCION_OPS_MCP_PATH", "/mcp"))
    parser.add_argument("--startup-timeout", type=int, default=20)
    return parser


async def main() -> None:
    args = _parser().parse_args()
    if args.transport == "stdio":
        print("transport=stdio")
        await _smoke_stdio()
        return

    print("transport=http")
    print(f"url={args.url}")
    process = None
    try:
        if args.start_server:
            try:
                await _smoke_http(args.url)
                return
            except Exception:
                pass
            process = await _start_http_server(args.host, args.port, args.path)
            await _wait_for_http(args.url, process, args.startup_timeout)
        else:
            await _smoke_http(args.url)
    finally:
        if process:
            await _stop_process(process)


if __name__ == "__main__":
    asyncio.run(main())
