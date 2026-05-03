#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
# ]
# ///
"""End-to-end smoke test for local Hub + kind + HTTP MCP operation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HUB_ENDPOINT = "http://127.0.0.1:8090"
DEFAULT_MCP_URL = "http://127.0.0.1:8765/mcp"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
IMAGE_HINT = (
    "Build and load the agent image, then retry:\n"
    "  task images:build -- --harness claude\n"
    "  task kind:load-images -- localhost/scion-base:latest localhost/scion-claude:latest"
)


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    output: str


class SmokeFailure(RuntimeError):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        hint: str = "",
        output: str = "",
    ) -> None:
        super().__init__(message)
        self.category = category
        self.hint = hint
        self.output = output


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def command_line(args: list[str]) -> str:
    return shlex.join(args)


def run(
    args: list[str],
    *,
    env: dict[str, str],
    category: str,
    hint: str = "",
    timeout: int = 180,
    check: bool = True,
    quiet: bool = False,
) -> CommandResult:
    if not quiet:
        print(f"+ {command_line(args)}", flush=True)
    try:
        proc = subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SmokeFailure(
            category,
            f"{args[0]} is not on PATH",
            hint=hint,
            output=str(exc),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        raise SmokeFailure(
            category,
            f"command timed out after {timeout}s: {command_line(args)}",
            hint=hint,
            output=output,
        ) from exc

    output = proc.stdout or ""
    if output and not quiet:
        print(output.rstrip(), flush=True)
    if check and proc.returncode != 0:
        raise SmokeFailure(
            classify_output(output, category),
            f"command failed with exit {proc.returncode}: {command_line(args)}",
            hint=hint_for_output(output, hint),
            output=output,
        )
    return CommandResult(args=args, returncode=proc.returncode, output=output)


def classify_output(output: str, default: str) -> str:
    text = output.lower()
    if "unauthorized" in text or "forbidden" in text or "authentication" in text:
        return "hub_auth"
    if "broker" in text or "provider" in text or "dispatch" in text:
        return "broker_dispatch"
    if "imagepullbackoff" in text or "errimagepull" in text or "pull image" in text:
        return "image"
    if "kubernetes" in text or "kubectl" in text or "pod" in text or "namespace" in text:
        return "kubernetes"
    return default


def hint_for_output(output: str, default: str) -> str:
    category = classify_output(output, "")
    if category == "hub_auth":
        return 'Refresh Hub auth and link the grove:\n  eval "$(task hub:auth-export)"\n  task hub:link'
    if category == "broker_dispatch":
        return "Refresh broker registration and provider routing:\n  task broker:kind-provide"
    if category == "image":
        return IMAGE_HINT
    if category == "kubernetes":
        return "Check the kind runtime:\n  task kind:up\n  task kind:status\n  task kind:doctor"
    return default


def parse_token_export(output: str) -> str:
    match = re.search(r"SCION_DEV_TOKEN=(scion_dev_[A-Za-z0-9]+)", output)
    return match.group(1) if match else ""


def extract_json_object(output: str) -> dict[str, Any]:
    cleaned = ANSI_RE.sub("", output)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"{", cleaned):
        try:
            data, _ = decoder.raw_decode(cleaned[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise json.JSONDecodeError("no JSON object found", cleaned, 0)


def ensure_hub_auth(env: dict[str, str], *, force_dev_token: bool = False) -> None:
    if env.get("SCION_AUTH_TOKEN") or env.get("SCION_HUB_TOKEN"):
        return
    if env.get("SCION_DEV_TOKEN") and not force_dev_token:
        return
    result = run(
        ["task", "hub:auth-export"],
        env=env,
        category="hub_auth",
        hint="Start Hub first:\n  task hub:up",
        timeout=30,
    )
    token = parse_token_export(result.output)
    if not token:
        raise SmokeFailure(
            "hub_auth",
            "could not parse SCION_DEV_TOKEN from task hub:auth-export",
            hint="Restart Hub and inspect the server log:\n  task hub:up\n  task hub:logs",
            output=result.output,
        )
    env["SCION_DEV_TOKEN"] = token


def broker_name(env: dict[str, str], scion_bin: str) -> str:
    result = run(
        [scion_bin, "broker", "status", "--json"],
        env=env,
        category="broker_dispatch",
        hint="Register the broker:\n  task broker:kind-provide",
        timeout=30,
    )
    try:
        data = extract_json_object(result.output)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            "broker_dispatch",
            "scion broker status did not return JSON",
            hint="Check broker state:\n  task broker:kind-status",
            output=result.output,
        ) from exc
    name = str(data.get("brokerName") or data.get("brokerId") or "").strip()
    if not name:
        raise SmokeFailure(
            "broker_dispatch",
            "broker is not registered",
            hint="Register and provide the broker:\n  task broker:kind-provide",
            output=result.output,
        )
    return name


def pod_data(env: dict[str, str], context: str, namespace: str, agent: str) -> dict[str, Any]:
    result = run(
        [
            "kubectl",
            "--context",
            context,
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            f"scion.name={agent}",
            "-o",
            "json",
        ],
        env=env,
        category="kubernetes",
        check=False,
        quiet=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise SmokeFailure(
            "kubernetes",
            "kubectl could not read smoke pod state",
            hint="Check the kind runtime:\n  task kind:status",
            output=result.output,
        )
    return json.loads(result.output)


def pod_waiting_reason(pod: dict[str, Any]) -> tuple[str, str]:
    statuses = pod.get("status", {}).get("containerStatuses") or []
    statuses += pod.get("status", {}).get("initContainerStatuses") or []
    for status in statuses:
        waiting = status.get("state", {}).get("waiting")
        if waiting:
            return str(waiting.get("reason") or ""), str(waiting.get("message") or "")
    return "", ""


def wait_for_kind_pod(
    env: dict[str, str],
    *,
    context: str,
    namespace: str,
    agent: str,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    log(f"wait for kind pod scion.name={agent}")
    deadline = time.monotonic() + timeout_seconds
    last_data: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        data = pod_data(env, context, namespace, agent)
        last_data = data
        pods = [item for item in data.get("items", []) if isinstance(item, dict)]
        if pods:
            for pod in pods:
                reason, message = pod_waiting_reason(pod)
                if reason.lower() in {"errimagepull", "imagepullbackoff", "invalidimagename"}:
                    describe = describe_pods(env, context, namespace, agent)
                    raise SmokeFailure(
                        "image",
                        f"kind pod cannot pull its image: {reason}",
                        hint=IMAGE_HINT,
                        output=f"{message}\n\n{describe}",
                    )
            run(
                [
                    "kubectl",
                    "--context",
                    context,
                    "get",
                    "pods",
                    "-n",
                    namespace,
                    "-l",
                    f"scion.name={agent}",
                    "-o",
                    "wide",
                ],
                env=env,
                category="kubernetes",
                timeout=20,
            )
            return pods
        time.sleep(1)

    output = json.dumps(last_data or {}, indent=2)
    raise SmokeFailure(
        "kubernetes",
        f"no kind pod appeared for {agent} within {timeout_seconds}s",
        hint="Check broker routing and Kubernetes runtime:\n  task broker:kind-status\n  task kind:status",
        output=output,
    )


def describe_pods(env: dict[str, str], context: str, namespace: str, agent: str) -> str:
    result = run(
        [
            "kubectl",
            "--context",
            context,
            "describe",
            "pods",
            "-n",
            namespace,
            "-l",
            f"scion.name={agent}",
        ],
        env=env,
        category="kubernetes",
        check=False,
        quiet=True,
        timeout=30,
    )
    return result.output


def result_text(result: object) -> str:
    content = getattr(result, "content", [])
    return "\n".join(part.text for part in content if hasattr(part, "text"))


async def call_mcp_tool(
    url: str,
    name: str,
    args: dict[str, Any],
    *,
    read_timeout: int = 30,
) -> dict[str, Any]:
    async with streamablehttp_client(url, timeout=5, sse_read_timeout=read_timeout) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            text = result_text(result)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            "mcp_transport",
            f"MCP tool {name} returned non-JSON output",
            hint="Check the MCP server:\n  task mcp:http:smoke",
            output=text,
        ) from exc


async def start_mcp_server(
    env: dict[str, str],
    *,
    host: str,
    port: int,
    path: str,
) -> asyncio.subprocess.Process:
    process_env = env.copy()
    process_env.update(
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
        env=process_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


async def stop_process(process: asyncio.subprocess.Process | None) -> None:
    if not process or process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def ensure_mcp(
    env: dict[str, str],
    *,
    url: str,
    host: str,
    port: int,
    path: str,
    startup_timeout: int,
) -> tuple[asyncio.subprocess.Process | None, dict[str, Any]]:
    try:
        status = await call_mcp_tool(url, "scion_ops_hub_status", {}, read_timeout=20)
        log(f"reuse HTTP MCP server at {url}")
        return None, status
    except Exception as first_error:
        log(f"start temporary HTTP MCP server at {url}")
        process = await start_mcp_server(env, host=host, port=port, path=path)
        deadline = time.monotonic() + startup_timeout
        last_error: Exception = first_error
        while time.monotonic() <= deadline:
            if process.returncode is not None:
                output = ""
                if process.stdout:
                    output = (await process.stdout.read()).decode(errors="replace")
                raise SmokeFailure(
                    "mcp_transport",
                    f"HTTP MCP server exited early with {process.returncode}",
                    hint="Check the MCP server:\n  task mcp:http:smoke",
                    output=output,
                )
            try:
                status = await call_mcp_tool(url, "scion_ops_hub_status", {}, read_timeout=20)
                return process, status
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(0.5)
        await stop_process(process)
        raise SmokeFailure(
            "mcp_transport",
            f"HTTP MCP server was not ready at {url}: {last_error}",
            hint="Check the MCP server:\n  task mcp:http:smoke",
        ) from last_error


def check_mcp_ok(payload: dict[str, Any], operation: str) -> None:
    if payload.get("ok") is not False:
        return
    category = str(payload.get("error_kind") or "mcp_tool")
    raise SmokeFailure(
        category,
        f"MCP {operation} failed: {payload.get('error') or payload}",
        hint=hint_for_mcp_category(category),
        output=json.dumps(payload, indent=2),
    )


def hint_for_mcp_category(category: str) -> str:
    if category == "hub_auth":
        return 'Refresh Hub auth:\n  eval "$(task hub:auth-export)"\n  task hub:status'
    if category in {"hub_unavailable", "hub_state"}:
        return "Check Hub state:\n  task hub:up\n  task hub:status"
    if category == "broker_dispatch":
        return "Check broker/provider routing:\n  task broker:kind-provide\n  task broker:kind-status"
    if category == "runtime":
        return "Check the kind runtime:\n  task kind:status\n  task kind:doctor"
    return "Check the HTTP MCP transport:\n  task mcp:http:smoke"


def cleanup_command(agent: str, hub_endpoint: str) -> str:
    return f"scion delete {shlex.quote(agent)} --hub {shlex.quote(hub_endpoint)} --non-interactive --yes"


def print_cleanup(agent: str, hub_endpoint: str, context: str, namespace: str) -> None:
    print("\nCleanup commands:")
    print(f"  {cleanup_command(agent, hub_endpoint)}")
    print(f"  kubectl --context {context} get pods -n {namespace} -l scion.name={agent}")
    print("  task kind:down  # optional: delete the local kind cluster")


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default=os.environ.get("SCION_E2E_AGENT", ""))
    parser.add_argument("--template", default=os.environ.get("SCION_E2E_TEMPLATE", "reviewer-claude"))
    parser.add_argument(
        "--prompt",
        default=os.environ.get(
            "SCION_E2E_PROMPT",
            "Smoke test: report the current working directory and stop.",
        ),
    )
    parser.add_argument("--profile", default=os.environ.get("SCION_K8S_PROFILE", "kind"))
    parser.add_argument("--cluster", default=os.environ.get("KIND_CLUSTER_NAME", "scion-ops"))
    parser.add_argument("--namespace", default=os.environ.get("SCION_K8S_NAMESPACE", "scion-agents"))
    parser.add_argument("--hub", default=os.environ.get("HUB_ENDPOINT", DEFAULT_HUB_ENDPOINT))
    parser.add_argument("--mcp-url", default=os.environ.get("SCION_OPS_MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--mcp-host", default=os.environ.get("SCION_OPS_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--mcp-port", type=int, default=int(os.environ.get("SCION_OPS_MCP_PORT", "8765")))
    parser.add_argument("--mcp-path", default=os.environ.get("SCION_OPS_MCP_PATH", "/mcp"))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("SCION_E2E_TIMEOUT_SECONDS", "90")))
    parser.add_argument(
        "--mcp-watch-timeout",
        type=int,
        default=int(os.environ.get("SCION_E2E_MCP_WATCH_SECONDS", "90")),
    )
    parser.add_argument("--mcp-startup-timeout", type=int, default=20)
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        default=os.environ.get("SCION_E2E_SKIP_SETUP", "").lower() in {"1", "true", "yes", "on"},
        help="skip kind:up, hub:up, and broker:kind-provide; only verify and run the smoke",
    )
    parser.add_argument(
        "--keep-agent",
        action="store_true",
        default=os.environ.get("SCION_E2E_KEEP_AGENT", "").lower() in {"1", "true", "yes", "on"},
        help="leave the smoke agent behind for inspection",
    )
    return parser


async def smoke(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env.update(
        {
            "HUB_ENDPOINT": args.hub,
            "SCION_OPS_MCP_URL": args.mcp_url,
            "SCION_OPS_ROOT": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    scion_bin = env.get("SCION_BIN", "scion")
    agent = args.agent or f"e2e-kind-mcp-{time.strftime('%Y%m%d%H%M%S')}"
    context = f"kind-{args.cluster}"
    mcp_process: asyncio.subprocess.Process | None = None
    agent_started = False
    success = False

    try:
        if not args.skip_setup:
            run(["task", "kind:up"], env=env, category="kubernetes", timeout=300)
            run(["task", "hub:up"], env=env, category="hub_unavailable", timeout=120)
            ensure_hub_auth(env, force_dev_token=True)
            run(["task", "hub:status"], env=env, category="hub_state", timeout=120)
            run(["task", "broker:kind-provide"], env=env, category="broker_dispatch", timeout=240)
            ensure_hub_auth(env, force_dev_token=True)

        run(["task", "kind:status"], env=env, category="kubernetes", timeout=60)
        run(["task", "broker:kind-status"], env=env, category="broker_dispatch", timeout=90)

        mcp_process, hub_status = await ensure_mcp(
            env,
            url=args.mcp_url,
            host=args.mcp_host,
            port=args.mcp_port,
            path=args.mcp_path,
            startup_timeout=args.mcp_startup_timeout,
        )
        check_mcp_ok(hub_status, "scion_ops_hub_status")

        baseline = await call_mcp_tool(
            args.mcp_url,
            "scion_ops_round_events",
            {"round_id": agent, "include_existing": False},
            read_timeout=30,
        )
        check_mcp_ok(baseline, "scion_ops_round_events")

        name = broker_name(env, scion_bin)
        log(f"dispatch {agent} through Hub broker {name} on profile {args.profile}")
        run(
            [
                scion_bin,
                "--profile",
                args.profile,
                "start",
                agent,
                "--broker",
                name,
                "--type",
                args.template,
                "--no-auth",
                "--hub",
                args.hub,
                "--non-interactive",
                "--yes",
                args.prompt,
            ],
            env=env,
            category="broker_dispatch",
            hint="Check broker/provider routing:\n  task broker:kind-status",
            timeout=90,
        )
        agent_started = True

        pods = wait_for_kind_pod(
            env,
            context=context,
            namespace=args.namespace,
            agent=agent,
            timeout_seconds=args.timeout,
        )

        log("wait for Hub state change through HTTP MCP")
        events = await call_mcp_tool(
            args.mcp_url,
            "scion_ops_watch_round_events",
            {
                "round_id": agent,
                "cursor": baseline.get("cursor", ""),
                "timeout_seconds": args.mcp_watch_timeout,
                "poll_interval_seconds": 1,
            },
            read_timeout=args.mcp_watch_timeout + 30,
        )
        check_mcp_ok(events, "scion_ops_watch_round_events")
        if not events.get("changed"):
            raise SmokeFailure(
                "mcp_transport",
                "HTTP MCP did not observe a Hub state change for the smoke agent",
                hint="Check MCP and Hub state:\n  task mcp:http:smoke\n  task hub:status",
                output=json.dumps(events, indent=2),
            )

        status = await call_mcp_tool(
            args.mcp_url,
            "scion_ops_round_status",
            {"round_id": agent, "include_transcript": False},
            read_timeout=30,
        )
        check_mcp_ok(status, "scion_ops_round_status")

        print("\nE2E smoke passed")
        print(f"  agent:      {agent}")
        print(f"  hub:        {args.hub}")
        print(f"  mcp:        {args.mcp_url}")
        print(f"  kind:       {context}/{args.namespace}")
        print(f"  pod_count:  {len(pods)}")
        print(f"  events:     {len(events.get('events') or [])}")
        print(f"  source:     {events.get('source')}")
        success = True
    finally:
        if agent_started and success and not args.keep_agent:
            log(f"delete smoke agent {agent}")
            run(
                [scion_bin, "delete", agent, "--hub", args.hub, "--non-interactive", "--yes"],
                env=env,
                category="cleanup",
                check=False,
                timeout=60,
            )
        elif agent_started:
            print_cleanup(agent, args.hub, context, args.namespace)
        await stop_process(mcp_process)


def main() -> int:
    args = parser().parse_args()
    try:
        asyncio.run(smoke(args))
    except SmokeFailure as exc:
        print(f"\nE2E smoke failed [{exc.category}]: {exc}", file=sys.stderr)
        if exc.hint:
            print(f"\nNext checks:\n{exc.hint}", file=sys.stderr)
        if exc.output:
            print("\nDiagnostic output:", file=sys.stderr)
            print(exc.output.rstrip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
