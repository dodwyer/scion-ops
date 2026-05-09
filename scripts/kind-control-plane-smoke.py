#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
# ]
# ///
"""Smoke test the kind-hosted Scion control plane."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HUB_PORT = int(os.environ.get("SCION_OPS_KIND_HUB_PORT", "18090"))
DEFAULT_HUB_ENDPOINT = os.environ.get(
    "SCION_OPS_KIND_HUB_URL",
    f"http://192.168.122.103:{DEFAULT_HUB_PORT}",
)
DEFAULT_MCP_URL = os.environ.get("SCION_OPS_MCP_URL", "http://192.168.122.103:8765/mcp")
DEFAULT_WEB_URL = os.environ.get("SCION_OPS_WEB_URL", "http://192.168.122.103:8787")
DEFAULT_GENERIC_CONFIG = ROOT / "deploy/kind/smoke/generic-smoke-agent.yaml"
DEFAULT_GENERIC_PROMPT = "printf 'scion kind control-plane smoke\\n'; pwd; sleep 30"
DEFAULT_TEMPLATE_PROMPT = "Smoke test: report the current working directory and stop."
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
EXPORT_RE = re.compile(r"^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
IMAGE_HINT = (
    "Build and load the smoke agent image, then retry:\n"
    "  task build -- --harness claude\n"
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


def classify_output(output: str, default: str) -> str:
    text = "\n".join(
        line
        for line in output.lower().splitlines()
        if "development authentication enabled" not in line
    )
    if "unauthorized" in text or "forbidden" in text or "authentication" in text:
        return "hub_auth"
    if "not_found" in text or "not found" in text:
        return "hub_state"
    if "env-gather" in text or "required environment variable" in text:
        return "hub_state"
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
        return 'Refresh kind Hub auth:\n  eval "$(task kind:hub:auth-export)"'
    if category == "broker_dispatch":
        return "Check the dedicated broker:\n  task kind:broker:status"
    if category == "image":
        return IMAGE_HINT
    if category == "kubernetes":
        return (
            "Check the kind control plane:\n"
            "  task kind:workspace:status\n"
            "  task kind:control-plane:status"
        )
    return default


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
        raise SmokeFailure(category, f"{args[0]} is not on PATH", hint=hint, output=str(exc)) from exc
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


def parse_exports(output: str) -> dict[str, str]:
    exports: dict[str, str] = {}
    for line in output.splitlines():
        match = EXPORT_RE.match(line.strip())
        if match:
            key, value = match.groups()
            exports[key] = value.strip().strip("'\"")
    return exports


def hub_port(endpoint: str) -> int:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.port:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    return 80


def service_url(endpoint: str, path: str) -> str:
    return endpoint.rstrip("/") + "/" + path.lstrip("/")


def http_ready(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(service_url(endpoint, "/healthz"), timeout=1) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def read_url(url: str, *, timeout: int = 3, method: str = "GET") -> tuple[int, str]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def ensure_web_app(*, endpoint: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    snapshot: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        try:
            index_status, index_body = read_url(service_url(endpoint, "/"), timeout=2)
            api_status, api_body = read_url(service_url(endpoint, "/api/snapshot"), timeout=3)
            post_status, _ = read_url(service_url(endpoint, "/api/snapshot"), timeout=2, method="POST")
            if 200 <= index_status < 300 and "scion-ops hub" in index_body and 200 <= api_status < 300 and post_status == 405:
                snapshot = json.loads(api_body)
                if isinstance(snapshot, dict) and snapshot.get("sources"):
                    log(f"kind web app is reachable at {endpoint}")
                    return snapshot
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise SmokeFailure(
        "web_app",
        f"kind web app was not ready at {endpoint}: {last_error}",
        hint=(
            "Check native kind port exposure and web rollout:\n"
            "  task kind:status\n"
            "  task kind:web:status\n"
            "  task kind:web:logs"
        ),
        output=json.dumps(snapshot, indent=2) if snapshot else "",
    )


def ensure_hub_ready(*, endpoint: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        if http_ready(endpoint):
            log(f"kind Hub is reachable at {endpoint}")
            return
        time.sleep(0.25)
    raise SmokeFailure(
        "hub_unavailable",
        f"kind Hub was not reachable at {endpoint} within {timeout_seconds}s",
        hint=(
            "Check native kind port exposure and Hub rollout:\n"
            "  task kind:status\n"
            "  task kind:control-plane:status\n"
            "If this is an old cluster, recreate it with task down and task up."
        ),
    )


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


def ensure_kind_hub_auth(env: dict[str, str], *, endpoint: str) -> None:
    env["SCION_OPS_KIND_HUB_PORT"] = str(hub_port(endpoint))
    result = run(
        ["task", "kind:hub:auth-export"],
        env=env,
        category="hub_auth",
        hint="Deploy the kind control plane first:\n  task kind:control-plane:apply",
        timeout=60,
        quiet=True,
    )
    exports = parse_exports(result.output)
    token = exports.get("SCION_DEV_TOKEN", "")
    if not token.startswith("scion_dev_"):
        raise SmokeFailure(
            "hub_auth",
            "could not read SCION_DEV_TOKEN from the kind Hub pod",
            hint="Check the Hub pod:\n  task kind:control-plane:status\n  task kind:hub:logs",
            output=result.output,
        )
    env["SCION_DEV_TOKEN"] = token
    env["SCION_HUB_ENDPOINT"] = endpoint
    env["HUB_ENDPOINT"] = endpoint


def template_harness_config(template: str) -> str:
    config = ROOT / ".scion" / "templates" / template / "scion-agent.yaml"
    if not config.exists():
        return ""
    match = re.search(r"^\s*default_harness_config:\s*['\"]?([^'\"\s#]+)", config.read_text(), re.M)
    return match.group(1) if match else ""


def bootstrap_grove(
    *,
    env: dict[str, str],
    scion_bin: str,
    endpoint: str,
    template: str | None,
    broker: str,
    sync_harness: bool,
    sync_template: bool,
) -> None:
    log("link current grove to the kind Hub")
    run(
        [scion_bin, "hub", "link", "--hub", endpoint, "--non-interactive", "--yes"],
        env=env,
        category="hub_state",
        hint="Check kind Hub auth:\n  eval \"$(task kind:hub:auth-export)\"",
        timeout=90,
    )

    harness = template_harness_config(template or "")
    if sync_harness and harness:
        log(f"sync harness config {harness}")
        run(
            [
                scion_bin,
                "harness-config",
                "sync",
                harness,
                "--hub",
                endpoint,
                "--non-interactive",
                "--yes",
            ],
            env=env,
            category="hub_state",
            hint=(
                "The smoke path does not sync harness configs from the host. "
                "Run task bootstrap, or keep using the checked-in generic smoke config."
            ),
            timeout=120,
        )

    if sync_template and template:
        log(f"sync smoke template {template}")
        run(
            [
                scion_bin,
                "templates",
                "sync",
                template,
                "--hub",
                endpoint,
                "--non-interactive",
                "--yes",
            ],
            env=env,
            category="hub_state",
            hint="Check local templates under .scion/templates",
            timeout=120,
        )

    log(f"provide current grove from broker {broker}")
    run(
        [
            scion_bin,
            "broker",
            "provide",
            "--broker",
            broker,
            "--make-default",
            "--non-interactive",
            "--yes",
        ],
        env=env,
        category="broker_dispatch",
        hint="Check the dedicated broker:\n  task kind:broker:status",
        timeout=120,
    )


def verify_broker(
    *,
    env: dict[str, str],
    scion_bin: str,
    endpoint: str,
    broker: str,
) -> None:
    result = run(
        [
            scion_bin,
            "hub",
            "brokers",
            "info",
            broker,
            "--hub",
            endpoint,
            "--json",
            "--non-interactive",
        ],
        env=env,
        category="broker_dispatch",
        hint="Check the dedicated broker:\n  task kind:broker:status",
        timeout=60,
    )
    try:
        data = extract_json_object(result.output)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            "broker_dispatch",
            f"could not parse broker info for {broker}",
            output=result.output,
        ) from exc

    status = str(data.get("status") or data.get("brokerStatus") or "").lower()
    if status and status != "online":
        raise SmokeFailure(
            "broker_dispatch",
            f"broker {broker} is not online: {status}",
            hint="Check the dedicated broker:\n  task kind:broker:status",
            output=json.dumps(data, indent=2),
        )
    connection = str(data.get("connectionState") or data.get("connection_state") or "").lower()
    if connection and connection != "connected":
        raise SmokeFailure(
            "broker_dispatch",
            f"broker {broker} control channel is not connected: {connection}",
            hint="Check the dedicated broker:\n  task kind:broker:status",
            output=json.dumps(data, indent=2),
        )


async def mcp_hub_status(url: str, *, read_timeout: int = 30) -> dict[str, Any]:
    async with streamablehttp_client(url, timeout=5, sse_read_timeout=read_timeout) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("scion_ops_hub_status", {})
    text = "\n".join(part.text for part in result.content if hasattr(part, "text"))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            "mcp_transport",
            "MCP hub status returned non-JSON output",
            hint="Check the kind MCP server:\n  task kind:mcp:status",
            output=text,
        ) from exc


async def ensure_mcp(
    *,
    url: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() <= deadline:
        try:
            payload = await mcp_hub_status(url, read_timeout=20)
            log(f"kind MCP is reachable at {url}")
            return payload
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.5)
    raise SmokeFailure(
        "mcp_transport",
        f"kind MCP was not ready at {url}: {last_error}",
        hint=(
            "Check native kind port exposure and MCP rollout:\n"
            "  task kind:status\n"
            "  task kind:mcp:status\n"
            "If this is an old cluster, recreate it with task down and task up."
        ),
    )


def check_mcp_status(payload: dict[str, Any]) -> None:
    if payload.get("ok") is not False:
        return
    raise SmokeFailure(
        str(payload.get("error_kind") or "mcp_transport"),
        f"MCP Hub status failed: {payload.get('error') or payload}",
        hint="Check current grove bootstrap and MCP logs:\n  task kind:mcp:logs",
        output=json.dumps(payload, indent=2),
    )


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


def wait_for_kind_pod(
    *,
    env: dict[str, str],
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

    raise SmokeFailure(
        "kubernetes",
        f"no kind pod appeared for {agent} within {timeout_seconds}s",
        hint="Check Hub provider routing and the kind broker:\n  task kind:broker:status",
        output=json.dumps(last_data or {}, indent=2),
    )


def cleanup_command(agent: str, hub_endpoint: str) -> str:
    return f"scion delete {shlex.quote(agent)} --hub {shlex.quote(hub_endpoint)} --non-interactive --yes"


def print_cleanup(agent: str, hub_endpoint: str, context: str, namespace: str) -> None:
    print("\nCleanup commands:")
    print(f"  {cleanup_command(agent, hub_endpoint)}")
    print(f"  kubectl --context {context} get pods -n {namespace} -l scion.name={agent}")


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default=os.environ.get("SCION_KIND_CP_SMOKE_AGENT", ""))
    parser.add_argument(
        "--template",
        default=os.environ.get("SCION_KIND_CP_SMOKE_TEMPLATE", ""),
        help="use an existing Hub template instead of the checked-in generic no-auth config",
    )
    parser.add_argument("--broker", default=os.environ.get("SCION_KIND_CP_BROKER", "kind-control-plane"))
    parser.add_argument("--prompt", default=os.environ.get("SCION_KIND_CP_SMOKE_PROMPT", ""))
    parser.add_argument("--profile", default=os.environ.get("SCION_K8S_PROFILE", "kind"))
    parser.add_argument("--cluster", default=os.environ.get("KIND_CLUSTER_NAME", "scion-ops"))
    parser.add_argument("--namespace", default=os.environ.get("SCION_K8S_NAMESPACE", "scion-agents"))
    parser.add_argument("--hub", default=os.environ.get("HUB_ENDPOINT", DEFAULT_HUB_ENDPOINT))
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("SCION_KIND_CP_SMOKE_TIMEOUT", "90")))
    parser.add_argument("--startup-timeout", type=int, default=30)
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        default=os.environ.get("SCION_KIND_CP_SMOKE_SKIP_SETUP", "").lower()
        in {"1", "true", "yes", "on"},
        help="skip kind:up, workspace status, and control-plane apply",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="skip grove link, harness config sync, template sync, and broker provide",
    )
    parser.add_argument(
        "--sync-harness-config",
        action="store_true",
        default=os.environ.get("SCION_KIND_CP_SMOKE_SYNC_HARNESS_CONFIG", "").lower()
        in {"1", "true", "yes", "on"},
        help="also sync the selected template's default harness config; task bootstrap is preferred",
    )
    parser.add_argument("--skip-harness-sync", action="store_false", dest="sync_harness_config")
    parser.add_argument(
        "--sync-template",
        action="store_true",
        default=os.environ.get("SCION_KIND_CP_SMOKE_SYNC_TEMPLATE", "").lower()
        in {"1", "true", "yes", "on"},
        help="sync --template before dispatching; task bootstrap is preferred",
    )
    parser.add_argument("--skip-template-sync", action="store_false", dest="sync_template")
    parser.add_argument("--skip-mcp", action="store_true")
    parser.add_argument(
        "--keep-agent",
        action="store_true",
        default=os.environ.get("SCION_KIND_CP_SMOKE_KEEP_AGENT", "").lower()
        in {"1", "true", "yes", "on"},
        help="leave the smoke agent behind for inspection",
    )
    return parser


async def smoke(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env.update(
        {
            "HUB_ENDPOINT": args.hub,
            "SCION_HUB_ENDPOINT": args.hub,
            "SCION_OPS_ROOT": str(ROOT),
            "SCION_OPS_MCP_URL": args.mcp_url,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    scion_bin = env.get("SCION_BIN", "scion")
    context = f"kind-{args.cluster}"
    agent = args.agent or f"kind-cp-smoke-{time.strftime('%Y%m%d%H%M%S')}"
    prompt = args.prompt or (DEFAULT_TEMPLATE_PROMPT if args.template else DEFAULT_GENERIC_PROMPT)
    agent_started = False
    success = False

    generic_config = None if args.template else DEFAULT_GENERIC_CONFIG
    if generic_config and not generic_config.exists():
        raise SmokeFailure(
            "configuration",
            f"generic smoke config not found: {generic_config}",
            hint="Check deploy/kind/smoke/generic-smoke-agent.yaml",
        )

    with tempfile.TemporaryDirectory(prefix="scion-kind-cp-smoke-"):
        try:
            if not args.skip_setup:
                run(["task", "kind:up"], env=env, category="kubernetes", timeout=300)
                if args.skip_mcp:
                    run(["task", "kind:hub:apply"], env=env, category="kubernetes", timeout=180)
                else:
                    run(["task", "kind:workspace:status"], env=env, category="kubernetes", timeout=90)
                    run(["task", "kind:control-plane:apply"], env=env, category="kubernetes", timeout=180)

            status_task = "kind:hub:status" if args.skip_mcp else "kind:control-plane:status"
            run(["task", status_task], env=env, category="kubernetes", timeout=180)
            ensure_kind_hub_auth(env, endpoint=args.hub)
            ensure_hub_ready(
                endpoint=args.hub,
                timeout_seconds=args.startup_timeout,
            )

            if not args.skip_bootstrap:
                bootstrap_grove(
                    env=env,
                    scion_bin=scion_bin,
                    endpoint=args.hub,
                    template=args.template or None,
                    broker=args.broker,
                    sync_harness=args.sync_harness_config,
                    sync_template=args.sync_template,
                )

            verify_broker(env=env, scion_bin=scion_bin, endpoint=args.hub, broker=args.broker)

            if not args.skip_mcp:
                hub_status = await ensure_mcp(
                    url=args.mcp_url,
                    timeout_seconds=args.startup_timeout,
                )
                check_mcp_status(hub_status)
                web_snapshot = ensure_web_app(
                    endpoint=args.web_url,
                    timeout_seconds=args.startup_timeout,
                )
                if web_snapshot.get("sources", {}).get("web", {}).get("status") == "unavailable":
                    raise SmokeFailure(
                        "web_app",
                        "web app snapshot marks its own control-plane source unavailable",
                        hint="Check web deployment/service:\n  task kind:web:status",
                        output=json.dumps(web_snapshot, indent=2),
                    )

            log(f"dispatch {agent} through kind Hub broker {args.broker}")
            start_args = [
                scion_bin,
                "--profile",
                args.profile,
                "start",
                agent,
                "--broker",
                args.broker,
                "--no-auth",
                "--hub",
                args.hub,
                "--non-interactive",
                "--yes",
            ]
            if args.template:
                start_args += ["--type", args.template, "--no-upload"]
            elif generic_config:
                start_args += ["--config", str(generic_config)]
            start_args.append(prompt)
            run(
                start_args,
                env=env,
                category="broker_dispatch",
                hint="Check Hub provider routing and the kind broker:\n  task kind:broker:status",
                timeout=120,
            )
            agent_started = True

            pods = wait_for_kind_pod(
                env=env,
                context=context,
                namespace=args.namespace,
                agent=agent,
                timeout_seconds=args.timeout,
            )

            print("\nkind control-plane smoke passed")
            print(f"  agent:      {agent}")
            print(f"  hub:        {args.hub}")
            print(f"  mcp:        {'skipped' if args.skip_mcp else args.mcp_url}")
            print(f"  web:        {'skipped' if args.skip_mcp else args.web_url}")
            print(f"  broker:     {args.broker}")
            print(f"  config:     {args.template or generic_config}")
            print(f"  kind:       {context}/{args.namespace}")
            print(f"  pod_count:  {len(pods)}")
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


def main() -> int:
    args = parser().parse_args()
    try:
        asyncio.run(smoke(args))
    except SmokeFailure as exc:
        print(f"\nkind control-plane smoke failed [{exc.category}]: {exc}", file=sys.stderr)
        if exc.hint:
            print(f"\nNext checks:\n{exc.hint}", file=sys.stderr)
        if exc.output:
            print("\nDiagnostic output:", file=sys.stderr)
            print(exc.output.rstrip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
