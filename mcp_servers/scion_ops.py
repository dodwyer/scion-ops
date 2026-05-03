#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
# ]
# ///
"""MCP server for operating the local scion-ops consensus harness.

The server intentionally wraps the existing Taskfile/orchestrator/scion CLI
surface instead of becoming another orchestration layer.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from hashlib import sha256
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


ROOT = Path(os.environ.get("SCION_OPS_ROOT", Path(__file__).resolve().parents[1])).resolve()
DEFAULT_TIMEOUT_SECONDS = 45
NAME_RE = re.compile(r"^[A-Za-z0-9._:/@+-]+$")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


mcp = FastMCP(
    "scion-ops",
    instructions=(
        "Use these tools to start and monitor scion-ops consensus rounds, "
        "inspect Scion agents, and review the resulting git branches."
    ),
    host=os.environ.get("SCION_OPS_MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("SCION_OPS_MCP_PORT", "8765")),
    streamable_http_path=os.environ.get("SCION_OPS_MCP_PATH", "/mcp"),
    json_response=_env_bool("SCION_OPS_MCP_JSON_RESPONSE", True),
    stateless_http=_env_bool("SCION_OPS_MCP_STATELESS_HTTP", True),
)


def _repo_root() -> Path:
    taskfile = ROOT / "Taskfile.yml"
    if not taskfile.exists():
        raise RuntimeError(f"SCION_OPS_ROOT does not look like scion-ops: {ROOT}")
    return ROOT


def _login_shell_path() -> str:
    shell = os.environ.get("SHELL") or "/bin/zsh"
    try:
        result = subprocess.run(
            [shell, "-lc", 'printf "%s" "$PATH"'],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception:
        return os.environ.get("PATH", "")
    return result.stdout or os.environ.get("PATH", "")


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    path_entries = [
        str(Path.home() / ".local/bin"),
        str(Path.home() / "go/bin"),
        _login_shell_path(),
        env.get("PATH", ""),
    ]
    env["PATH"] = ":".join(entry for entry in path_entries if entry)
    env.setdefault("SCION_BIN", "scion")
    if extra:
        env.update({key: str(value) for key, value in extra.items() if value is not None})
    return env


def _run(
    args: list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> dict[str, Any]:
    root = _repo_root()
    try:
        result = subprocess.run(
            args,
            cwd=root,
            env=_env(env),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        return {
            "ok": False,
            "timed_out": True,
            "returncode": None,
            "command": args,
            "output": output,
            "error": f"command timed out after {timeout}s",
        }

    ok = result.returncode == 0
    payload = {
        "ok": ok,
        "timed_out": False,
        "returncode": result.returncode,
        "command": args,
        "output": result.stdout,
    }
    if check and not ok:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{result.stdout}")
    return payload


def _clean_name(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} is required")
    if not NAME_RE.match(value):
        raise ValueError(f"{label} contains unsupported characters: {value!r}")
    return value


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _extract_json_array(output: str) -> list[dict[str, Any]]:
    data = _extract_json_value(output)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _extract_json_value(output: str) -> Any | None:
    candidates = [match.start() for match in re.finditer(r"(?m)^\s*\[", output)]
    candidates.extend(match.start() for match in re.finditer(r"(?m)^\s*\{", output))
    candidates = sorted(set(candidates))
    for start in candidates:
        chunk = output[start:]
        stripped = chunk.lstrip()
        if not stripped:
            continue
        opener = stripped[0]
        if opener not in "[{":
            continue
        start = start + len(chunk) - len(stripped)
        closer = "]" if opener == "[" else "}"
        end = output.rfind(closer)
        if end == -1 or end < start:
            continue
        try:
            return json.loads(output[start : end + 1])
        except json.JSONDecodeError:
            continue
    return None


def _json_items(output: str) -> list[dict[str, Any]]:
    data = _extract_json_value(output)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _agent_summary(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": agent.get("name") or agent.get("slug"),
        "slug": agent.get("slug"),
        "template": agent.get("template"),
        "harnessConfig": agent.get("harnessConfig"),
        "harnessAuth": agent.get("harnessAuth"),
        "phase": agent.get("phase"),
        "activity": agent.get("activity"),
        "containerStatus": agent.get("containerStatus"),
        "taskSummary": agent.get("taskSummary"),
        "created": agent.get("created"),
        "updated": agent.get("updated"),
    }


def _list_agents(round_filter: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = _run(["scion", "list", "--format", "json"], timeout=25)
    agents = _extract_json_array(result["output"])
    if round_filter:
        agents = [
            agent
            for agent in agents
            if round_filter in str(agent.get("name", ""))
            or round_filter in str(agent.get("slug", ""))
        ]
    return agents, result


def _round_text_match(item: dict[str, Any], round_id: str) -> bool:
    needle = round_id.lower()
    fields = [
        item.get("name"),
        item.get("slug"),
        item.get("sender"),
        item.get("msg"),
        item.get("message"),
        item.get("status"),
        item.get("taskSummary"),
    ]
    return any(needle in str(value).lower() for value in fields if value is not None)


def _list_round_messages(round_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = _run(["scion", "messages", "--all", "--json", "--non-interactive"], timeout=25)
    messages = [item for item in _json_items(result["output"]) if _round_text_match(item, round_id)]
    return messages, result


def _list_round_notifications(round_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = _run(["scion", "notifications", "--all", "--json", "--non-interactive"], timeout=25)
    notifications = [item for item in _json_items(result["output"]) if _round_text_match(item, round_id)]
    return notifications, result


def _event_id(prefix: str, item: dict[str, Any]) -> str:
    value = item.get("id")
    if value:
        return f"{prefix}:{value}"
    encoded = json.dumps(item, sort_keys=True, default=str)
    return f"{prefix}:synthetic:{sha256(encoded.encode()).hexdigest()}"


def _agent_fingerprint(agent: dict[str, Any]) -> str:
    tracked = {
        "name": agent.get("name"),
        "slug": agent.get("slug"),
        "phase": agent.get("phase"),
        "activity": agent.get("activity"),
        "taskSummary": agent.get("taskSummary"),
        "template": agent.get("template"),
        "harnessConfig": agent.get("harnessConfig"),
        "harnessAuth": agent.get("harnessAuth"),
    }
    return json.dumps(tracked, sort_keys=True, default=str)


def _round_event_snapshot(round_id: str) -> dict[str, Any]:
    agents, agent_result = _list_agents(round_id)
    messages, message_result = _list_round_messages(round_id)
    notifications, notification_result = _list_round_notifications(round_id)
    summaries = [_agent_summary(agent) for agent in agents]
    return {
        "round_id": round_id,
        "agents": summaries,
        "agent_fingerprints": {
            str(item.get("name") or item.get("slug")): _agent_fingerprint(item)
            for item in summaries
            if item.get("name") or item.get("slug")
        },
        "messages": messages,
        "message_ids": [_event_id("message", item) for item in messages],
        "notifications": notifications,
        "notification_ids": [_event_id("notification", item) for item in notifications],
        "commands_ok": {
            "agents": agent_result["ok"],
            "messages": message_result["ok"],
            "notifications": notification_result["ok"],
        },
    }


def _encode_cursor(snapshot: dict[str, Any]) -> str:
    payload = {
        "version": 1,
        "round_id": snapshot["round_id"],
        "agent_fingerprints": snapshot["agent_fingerprints"],
        "message_ids": snapshot["message_ids"],
        "notification_ids": snapshot["notification_ids"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return urlsafe_b64encode(encoded).decode().rstrip("=")


def _decode_cursor(cursor: str, round_id: str) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(urlsafe_b64decode(padded.encode()).decode())
    except Exception as exc:
        raise ValueError("cursor is not a valid scion-ops event cursor") from exc
    if payload.get("round_id") != round_id:
        raise ValueError("cursor belongs to a different round_id")
    return payload


def _round_events_since(
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    include_existing: bool,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous_agents = previous.get("agent_fingerprints", {}) if previous else {}
    previous_messages = set(previous.get("message_ids", [])) if previous else set()
    previous_notifications = set(previous.get("notification_ids", [])) if previous else set()

    if previous or include_existing:
        current_agents = snapshot["agent_fingerprints"]
        for name, fingerprint in current_agents.items():
            if name not in previous_agents:
                event_type = "agent_seen" if not previous else "agent_added"
            elif previous_agents[name] != fingerprint:
                event_type = "agent_changed"
            else:
                continue
            agent = next((item for item in snapshot["agents"] if item.get("name") == name or item.get("slug") == name), {})
            events.append({"type": event_type, "agent": agent})
        for name in sorted(set(previous_agents) - set(current_agents)):
            events.append({"type": "agent_removed", "agent": {"name": name}})

        for item, item_id in zip(snapshot["messages"], snapshot["message_ids"]):
            if include_existing or item_id not in previous_messages:
                events.append({"type": "message", "id": item_id, "message": item})

        for item, item_id in zip(snapshot["notifications"], snapshot["notification_ids"]):
            if include_existing or item_id not in previous_notifications:
                events.append({"type": "notification", "id": item_id, "notification": item})

    return events


def _round_terminal_status(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    consensus = next(
        (
            item
            for item in snapshot["agents"]
            if item.get("template") == "consensus-runner"
            or (item.get("name") and str(item.get("name")).endswith("-consensus"))
        ),
        None,
    )
    if not consensus:
        return None
    summary = str(consensus.get("taskSummary") or "")
    activity = str(consensus.get("activity") or "").lower()
    if activity == "completed" or " complete:" in summary or " escalated:" in summary:
        return {
            "agent": consensus.get("name"),
            "activity": consensus.get("activity"),
            "taskSummary": consensus.get("taskSummary"),
        }
    return None


def _default_base_branch() -> str:
    result = _run(["git", "branch", "--show-current"], timeout=10)
    current = result["output"].strip()
    return current or "HEAD"


@mcp.tool()
def scion_ops_hub_status() -> dict[str, Any]:
    """Show Scion Hub status and a compact agent summary."""
    hub = _run(["scion", "hub", "status"], timeout=25)
    agents, list_result = _list_agents()
    return {
        "hub_status": hub,
        "agent_list_ok": list_result["ok"],
        "agents": [_agent_summary(agent) for agent in agents],
    }


@mcp.tool()
def scion_ops_list_agents(round_filter: str = "") -> dict[str, Any]:
    """List Scion agents, optionally filtered by a round id substring."""
    if round_filter:
        _clean_name(round_filter, "round_filter")
    agents, result = _list_agents(round_filter)
    summaries = [_agent_summary(agent) for agent in agents]
    return {
        "ok": result["ok"],
        "round_filter": round_filter,
        "count": len(summaries),
        "phase_counts": dict(Counter(str(item.get("phase")) for item in summaries)),
        "activity_counts": dict(Counter(str(item.get("activity")) for item in summaries)),
        "agents": summaries,
    }


@mcp.tool()
def scion_ops_look(agent_name: str, num_lines: int = 160) -> dict[str, Any]:
    """Read terminal output for a Scion agent with `scion look`."""
    agent_name = _clean_name(agent_name, "agent_name")
    num_lines = _clamp(num_lines, 20, 600)
    return _run(
        [
            "scion",
            "look",
            agent_name,
            "--non-interactive",
            "--plain",
            "--num-lines",
            str(num_lines),
        ],
        timeout=35,
    )


@mcp.tool()
def scion_ops_round_status(round_id: str = "", include_transcript: bool = True, num_lines: int = 120) -> dict[str, Any]:
    """Summarize a consensus round and optionally include the consensus runner tail."""
    if round_id:
        _clean_name(round_id, "round_id")
    num_lines = _clamp(num_lines, 20, 400)
    agents, result = _list_agents(round_id)
    summaries = [_agent_summary(agent) for agent in agents]
    consensus = next(
        (
            item.get("name")
            for item in summaries
            if item.get("template") == "consensus-runner"
            or (item.get("name") and str(item.get("name")).endswith("-consensus"))
        ),
        "",
    )
    transcript: dict[str, Any] | None = None
    if include_transcript and consensus:
        transcript = scion_ops_look(consensus, num_lines=num_lines)
    return {
        "ok": result["ok"],
        "round_id": round_id,
        "agents": summaries,
        "phase_counts": dict(Counter(str(item.get("phase")) for item in summaries)),
        "activity_counts": dict(Counter(str(item.get("activity")) for item in summaries)),
        "consensus_agent": consensus,
        "consensus_transcript": transcript,
    }


@mcp.tool()
def scion_ops_round_events(round_id: str, cursor: str = "", include_existing: bool = False) -> dict[str, Any]:
    """Read Hub messages/notifications and agent-state changes for a round."""
    round_id = _clean_name(round_id, "round_id")
    previous = _decode_cursor(cursor, round_id)
    snapshot = _round_event_snapshot(round_id)
    events = _round_events_since(snapshot, previous, include_existing=include_existing)
    return {
        "ok": all(snapshot["commands_ok"].values()),
        "round_id": round_id,
        "changed": bool(events),
        "events": events,
        "cursor": _encode_cursor(snapshot),
        "terminal": _round_terminal_status(snapshot),
        "agent_count": len(snapshot["agents"]),
        "message_count": len(snapshot["messages"]),
        "notification_count": len(snapshot["notifications"]),
        "commands_ok": snapshot["commands_ok"],
    }


@mcp.tool()
def scion_ops_watch_round_events(
    round_id: str,
    cursor: str = "",
    timeout_seconds: int = 90,
    poll_interval_seconds: int = 2,
    include_existing: bool = False,
) -> dict[str, Any]:
    """Wait inside the MCP server until a round has new state to report.

    MCP tools are request/response, so this is the event-friendly monitoring
    primitive: clients call once and get a response when Hub messages,
    notifications, or agent status fingerprints change. Pass the returned
    cursor back on the next call.
    """
    round_id = _clean_name(round_id, "round_id")
    timeout_seconds = _clamp(timeout_seconds, 1, 300)
    poll_interval_seconds = _clamp(poll_interval_seconds, 1, 30)

    previous = _decode_cursor(cursor, round_id)
    if previous is None and not include_existing:
        snapshot = _round_event_snapshot(round_id)
        previous = {
            "round_id": round_id,
            "agent_fingerprints": snapshot["agent_fingerprints"],
            "message_ids": snapshot["message_ids"],
            "notification_ids": snapshot["notification_ids"],
        }

    deadline = time.monotonic() + timeout_seconds
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        snapshot = _round_event_snapshot(round_id)
        last_snapshot = snapshot
        events = _round_events_since(snapshot, previous, include_existing=include_existing)
        terminal = _round_terminal_status(snapshot)
        if events or terminal:
            return {
                "ok": all(snapshot["commands_ok"].values()),
                "round_id": round_id,
                "changed": bool(events),
                "events": events,
                "cursor": _encode_cursor(snapshot),
                "terminal": terminal,
                "timed_out": False,
                "agent_count": len(snapshot["agents"]),
                "message_count": len(snapshot["messages"]),
                "notification_count": len(snapshot["notifications"]),
                "commands_ok": snapshot["commands_ok"],
            }
        time.sleep(poll_interval_seconds)

    snapshot = last_snapshot or _round_event_snapshot(round_id)
    return {
        "ok": all(snapshot["commands_ok"].values()),
        "round_id": round_id,
        "changed": False,
        "events": [],
        "cursor": _encode_cursor(snapshot),
        "terminal": _round_terminal_status(snapshot),
        "timed_out": True,
        "agent_count": len(snapshot["agents"]),
        "message_count": len(snapshot["messages"]),
        "notification_count": len(snapshot["notifications"]),
        "commands_ok": snapshot["commands_ok"],
    }


@mcp.tool()
def scion_ops_start_round(
    prompt: str,
    round_id: str = "",
    max_minutes: int = 30,
    max_review_rounds: int = 3,
    base_branch: str = "",
    final_reviewer: str = "",
) -> dict[str, Any]:
    """Start a detached scion-ops consensus round via `task round`."""
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt is required")
    env: dict[str, str] = {
        "MAX_MINUTES": str(_clamp(max_minutes, 1, 240)),
        "MAX_REVIEW_ROUNDS": str(_clamp(max_review_rounds, 1, 10)),
    }
    if round_id:
        env["ROUND_ID"] = _clean_name(round_id, "round_id")
    if base_branch:
        env["BASE_BRANCH"] = _clean_name(base_branch, "base_branch")
    if final_reviewer:
        final_reviewer = final_reviewer.strip().lower()
        if final_reviewer not in {"gemini", "codex"}:
            raise ValueError("final_reviewer must be 'gemini' or 'codex'")
        env["FINAL_REVIEWER"] = final_reviewer

    result = _run(["task", "round", "--", prompt], timeout=60, env=env)
    match = re.search(r"round_id\s*:\s*(\S+)", result["output"])
    parsed_round_id = match.group(1) if match else env.get("ROUND_ID", "")
    runner = f"round-{parsed_round_id.lower()}-consensus" if parsed_round_id else ""
    event_cursor = ""
    if parsed_round_id:
        event_cursor = _encode_cursor(_round_event_snapshot(parsed_round_id))
    return {
        **result,
        "round_id": parsed_round_id,
        "consensus_agent": runner,
        "event_cursor": event_cursor,
        "next": {
            "watch_tool": "scion_ops_watch_round_events",
            "events_tool": "scion_ops_round_events",
            "abort_tool": "scion_ops_abort_round",
        },
    }


@mcp.tool()
def scion_ops_abort_round(round_id: str, confirm: bool = False) -> dict[str, Any]:
    """Stop and delete all agents matching a round id. Requires confirm=true."""
    round_id = _clean_name(round_id, "round_id")
    agents, _ = _list_agents(round_id)
    matching = [_agent_summary(agent) for agent in agents]
    if not confirm:
        return {
            "ok": False,
            "dry_run": True,
            "message": "Set confirm=true to stop and delete these agents.",
            "matching_agents": matching,
        }
    result = _run(["bash", "orchestrator/abort.sh", round_id], timeout=90)
    return {**result, "matching_agents_before_abort": matching}


@mcp.tool()
def scion_ops_round_artifacts(round_id: str) -> dict[str, Any]:
    """Find local branches and agent workspaces associated with a round id."""
    round_id = _clean_name(round_id, "round_id")
    branch_patterns = sorted({f"*{round_id}*", f"*{round_id.lower()}*"})
    branch_result = _run(["git", "branch", "--list", *branch_patterns], timeout=15)
    agents_dir = _repo_root() / ".scion" / "agents"
    workspaces: list[str] = []
    prompts: list[str] = []
    if agents_dir.exists():
        for path in sorted(agents_dir.glob(f"*{round_id.lower()}*")):
            workspace = path / "workspace"
            prompt = path / "prompt.md"
            if workspace.exists():
                workspaces.append(str(workspace))
            if prompt.exists():
                prompts.append(str(prompt))
    return {
        "branches": [line.strip(" *+") for line in branch_result["output"].splitlines() if line.strip()],
        "workspaces": workspaces,
        "prompts": prompts,
    }


@mcp.tool()
def scion_ops_git_status() -> dict[str, Any]:
    """Show repo status and local round branches."""
    status = _run(["git", "status", "--short", "--branch"], timeout=15)
    branches = _run(["git", "branch", "--list", "round-*"], timeout=15)
    return {"status": status, "round_branches": branches["output"].splitlines()}


@mcp.tool()
def scion_ops_git_diff(
    branch: str,
    base_branch: str = "",
    path_filter: str = "",
    stat_only: bool = False,
    max_output_chars: int = 20000,
) -> dict[str, Any]:
    """Show a branch diff against a base branch, optionally limited to one path."""
    branch = _clean_name(branch, "branch")
    base_branch = _clean_name(base_branch, "base_branch") if base_branch else _default_base_branch()
    max_output_chars = _clamp(max_output_chars, 1000, 60000)
    args = ["git", "diff"]
    if stat_only:
        args.append("--stat")
    args.append(f"{base_branch}..{branch}")
    if path_filter:
        args.extend(["--", path_filter])
    result = _run(args, timeout=25)
    output = result["output"]
    truncated = len(output) > max_output_chars
    return {**result, "output": output[:max_output_chars], "truncated": truncated}


@mcp.tool()
def scion_ops_verify() -> dict[str, Any]:
    """Run the repository verification gate via `task verify`."""
    return _run(["task", "verify"], timeout=120)


@mcp.tool()
def scion_ops_tail_round_log(num_lines: int = 160) -> dict[str, Any]:
    """Read the detached round launcher log at /tmp/scion-round.log."""
    num_lines = _clamp(num_lines, 20, 600)
    log_path = Path("/tmp/scion-round.log")
    if not log_path.exists():
        return {"ok": False, "path": str(log_path), "output": "log file does not exist"}
    lines = log_path.read_text(errors="replace").splitlines()
    return {"ok": True, "path": str(log_path), "output": "\n".join(lines[-num_lines:])}


@mcp.resource("scion-ops://readme")
def read_readme() -> str:
    """Read the scion-ops README."""
    return (_repo_root() / "README.md").read_text(errors="replace")


@mcp.resource("scion-ops://taskfile")
def read_taskfile() -> str:
    """Read the scion-ops Taskfile."""
    return (_repo_root() / "Taskfile.yml").read_text(errors="replace")


@mcp.prompt()
def monitor_scion_round(round_id: str) -> str:
    """Prompt an agent to monitor a Scion consensus round."""
    round_id = _clean_name(round_id, "round_id")
    return (
        f"Use the scion-ops MCP tools to monitor round `{round_id}`. Start with "
        "scion_ops_round_events(include_existing=true), then call "
        "scion_ops_watch_round_events with the returned cursor until it reports "
        "a terminal status or blocker. Use scion_ops_look only when an event "
        "needs transcript context. Summarize phase, blockers, final branch, "
        "verification, and any cleanup issues."
    )


def main() -> None:
    transport = os.environ.get("SCION_OPS_MCP_TRANSPORT", "stdio").strip().lower()
    try:
        if transport in {"http", "streamable-http", "streamable_http"}:
            mcp.run(transport="streamable-http")
            return
        if transport != "stdio":
            raise SystemExit(f"unsupported SCION_OPS_MCP_TRANSPORT={transport!r}")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
