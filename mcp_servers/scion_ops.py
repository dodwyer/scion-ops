#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp>=1.13,<2",
#   "PyYAML>=6,<7",
# ]
# ///
"""MCP server for operating the local scion-ops consensus harness.

The server intentionally keeps local repo inspection close to the existing
Taskfile/orchestrator workflow, while Hub-mode control and monitoring use the
Scion Hub HTTP API.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP


ROOT = Path(os.environ.get("SCION_OPS_ROOT", Path(__file__).resolve().parents[1])).resolve()
DEFAULT_TIMEOUT_SECONDS = 45
NAME_RE = re.compile(r"^[A-Za-z0-9._:/@+-]+$")
DEFAULT_HOST_WORKSPACE_ROOT = "/home/david/workspace"
DEFAULT_CONTAINER_WORKSPACE_ROOT = "/workspace"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


mcp = FastMCP(
    "scion-ops",
    instructions=(
        "Use these tools to start and monitor scion-ops consensus rounds, "
        "inspect Scion agents, and review the resulting git branches. "
        "Pass project_root for the project being changed; if omitted, the "
        "server uses its current working checkout."
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
    cwd: Path | None = None,
    check: bool = False,
) -> dict[str, Any]:
    root = cwd or _repo_root()
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


def _classify_command_failure(args: list[str], output: str) -> str:
    text = " ".join(args).lower() + "\n" + output.lower()
    if args and args[0] == "git":
        return "local_git_state"
    if "unauthorized" in text or "authentication failed" in text or "forbidden" in text:
        return "hub_auth"
    if "broker_auth_failed" in text or "runtime broker" in text or "no provider" in text:
        return "broker_dispatch"
    if "kubernetes" in text or "pod" in text or "runtime" in text or "container" in text:
        return "runtime"
    return "command"


def _command_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("ok"):
        return result
    return {
        **result,
        "source": "shell",
        "error_kind": _classify_command_failure(result.get("command", []), result.get("output", "")),
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(errors="replace"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _settings_paths(project_root: Path | None = None) -> list[Path]:
    paths: list[Path] = [Path.home() / ".scion" / "settings.yaml"]
    explicit = os.environ.get("SCION_OPS_GROVE_SETTINGS")
    if explicit:
        paths.append(Path(explicit).expanduser())

    root = project_root or _repo_root()
    local_settings = root / ".scion" / "settings.yaml"
    if local_settings.exists():
        paths.append(local_settings)

    grove_id_file = root / ".scion" / "grove-id"
    if grove_id_file.exists():
        grove_id = grove_id_file.read_text(errors="replace").strip()
        short_id = grove_id[:8]
        pattern = f"*__{short_id}/.scion/settings.yaml"
        for path in sorted((Path.home() / ".scion" / "grove-configs").glob(pattern)):
            paths.append(path)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def _effective_settings(project_root: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    settings: dict[str, Any] = {}
    sources: list[str] = []
    for path in _settings_paths(project_root):
        data = _load_yaml(path)
        if data:
            settings = _deep_merge(settings, data)
            sources.append(str(path))
    return settings, sources


def _nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _path_mappings() -> list[tuple[Path, Path]]:
    mappings: list[tuple[Path, Path]] = []
    raw = os.environ.get("SCION_OPS_PROJECT_PATH_MAP", "")
    for item in re.split(r"[;,\n]", raw):
        if not item.strip() or "=" not in item:
            continue
        host, container = item.split("=", 1)
        mappings.append((Path(host).expanduser(), Path(container).expanduser()))

    host_root = Path(os.environ.get("SCION_OPS_HOST_WORKSPACE_ROOT", DEFAULT_HOST_WORKSPACE_ROOT)).expanduser()
    container_root = Path(
        os.environ.get("SCION_OPS_CONTAINER_WORKSPACE_ROOT", DEFAULT_CONTAINER_WORKSPACE_ROOT)
    ).expanduser()
    mappings.append((host_root, container_root))
    return mappings


def _map_project_path(path: Path) -> Path:
    if path.exists():
        return path
    path_str = str(path)
    for host_root, container_root in _path_mappings():
        host = str(host_root)
        if path_str == host:
            candidate = container_root
        elif path_str.startswith(host.rstrip("/") + "/"):
            candidate = container_root / path_str[len(host.rstrip("/")) + 1 :]
        else:
            continue
        if candidate.exists():
            return candidate
    return path


def _project_root(project_root: str = "", *, require_git: bool = True) -> Path:
    raw = project_root.strip() if project_root else ""
    path = Path(raw).expanduser() if raw else _repo_root()
    path = _map_project_path(path)
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()
    else:
        path = path.resolve()
    if require_git:
        if not path.exists():
            raise ValueError(f"project_root is not visible to MCP: {path}")
        _run(["git", "config", "--global", "--add", "safe.directory", str(path)], timeout=10, cwd=_repo_root())
        result = _run(["git", "rev-parse", "--show-toplevel"], timeout=10, cwd=path)
        if not result["ok"]:
            raise ValueError(f"project_root is not a git repository visible to MCP: {path}")
        return Path(result["output"].strip()).resolve()
    if not path.exists():
        raise ValueError(f"project_root is not visible to MCP: {path}")
    return path


@dataclass(frozen=True)
class HubAuth:
    header: str
    token: str
    method: str
    source: str

    def redacted(self) -> dict[str, str]:
        return {"method": self.method, "source": self.source}


@dataclass(frozen=True)
class HubConfig:
    endpoint: str
    grove_id: str
    enabled: bool
    configured: bool
    settings_sources: list[str]
    auth: HubAuth | None

    def redacted(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "grove_id": self.grove_id,
            "enabled": self.enabled,
            "configured": self.configured,
            "settings_sources": self.settings_sources,
            "auth": self.auth.redacted() if self.auth else {"method": "none", "source": ""},
        }


class HubAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str,
        status: int | None = None,
        code: str = "",
        path: str = "",
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status = status
        self.code = code
        self.path = path
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {
            "error_kind": self.category,
            "error": str(self),
            "status": self.status,
            "code": self.code,
            "path": self.path,
            "details": self.details,
        }


def _oauth_token(endpoint: str) -> tuple[str, str]:
    credentials = Path.home() / ".scion" / "credentials.json"
    try:
        data = json.loads(credentials.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    hubs = data.get("hubs")
    if not isinstance(hubs, dict):
        return "", ""
    entry = hubs.get(endpoint) or hubs.get(endpoint.rstrip("/"))
    if not isinstance(entry, dict):
        return "", ""
    token = str(entry.get("accessToken") or "").strip()
    return token, str(credentials) if token else ""


def _hub_auth(endpoint: str) -> HubAuth | None:
    token = os.environ.get("SCION_OPS_HUB_TOKEN", "").strip()
    if token:
        return HubAuth("Authorization", token, "bearer", "SCION_OPS_HUB_TOKEN env")

    token, source = _oauth_token(endpoint)
    if token:
        return HubAuth("Authorization", token, "oauth", source)

    token = _read_text_file(Path.home() / ".scion" / "scion-token")
    if token:
        return HubAuth("X-Scion-Agent-Token", token, "agent_token", "~/.scion/scion-token")

    token = os.environ.get("SCION_AUTH_TOKEN", "").strip()
    if token:
        return HubAuth("X-Scion-Agent-Token", token, "agent_token", "SCION_AUTH_TOKEN env")

    token = os.environ.get("SCION_HUB_TOKEN", "").strip()
    if token:
        return HubAuth("Authorization", token, "bearer", "SCION_HUB_TOKEN env")

    token = os.environ.get("SCION_DEV_TOKEN", "").strip()
    if token:
        return HubAuth("Authorization", token, "devauth", "SCION_DEV_TOKEN env")

    token_file = os.environ.get("SCION_DEV_TOKEN_FILE", "").strip()
    if token_file:
        token = _read_text_file(Path(token_file).expanduser())
        if token:
            return HubAuth("Authorization", token, "devauth", f"SCION_DEV_TOKEN_FILE: {token_file}")

    token = _read_text_file(Path.home() / ".scion" / "dev-token")
    if token:
        return HubAuth("Authorization", token, "devauth", "~/.scion/dev-token")

    return None


def _hub_config(project_root: Path | None = None) -> HubConfig:
    settings, sources = _effective_settings(project_root)
    endpoint = (
        os.environ.get("SCION_OPS_HUB_ENDPOINT")
        or os.environ.get("SCION_HUB_ENDPOINT")
        or _nested(settings, "hub", "endpoint")
        or "http://127.0.0.1:8090"
    )
    endpoint = str(endpoint).rstrip("/")
    configured = bool(
        os.environ.get("SCION_OPS_HUB_ENDPOINT")
        or os.environ.get("SCION_HUB_ENDPOINT")
        or _nested(settings, "hub", "endpoint")
    )

    project_grove_id = _read_text_file(project_root / ".scion" / "grove-id") if project_root else ""
    grove_id = (
        project_grove_id
        or os.environ.get("SCION_OPS_GROVE_ID")
        or os.environ.get("SCION_HUB_GROVE_ID")
        or _nested(settings, "hub", "grove_id")
        or _nested(settings, "hub", "groveId")
        or settings.get("grove_id")
        or settings.get("groveId")
        or _read_text_file(_repo_root() / ".scion" / "grove-id")
    )
    grove_id = str(grove_id or "").strip()
    enabled = _truthy(_nested(settings, "hub", "enabled")) or bool(
        os.environ.get("SCION_OPS_HUB_ENDPOINT") or os.environ.get("SCION_HUB_ENDPOINT")
    )
    return HubConfig(
        endpoint=endpoint,
        grove_id=grove_id,
        enabled=enabled,
        configured=configured,
        settings_sources=sources,
        auth=_hub_auth(endpoint),
    )


def _hub_error_payload(error: HubAPIError, operation: str, cfg: HubConfig | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "source": "hub_api",
        "operation": operation,
        "hub": (cfg or _hub_config()).redacted(),
        **error.payload(),
    }


class HubClient:
    def __init__(self, project_root: str = "") -> None:
        self.project_root = _project_root(project_root, require_git=False) if project_root else None
        self.cfg = _hub_config(self.project_root)

    def _require_ready(self) -> None:
        if not self.cfg.enabled:
            raise HubAPIError(
                "Hub integration is disabled for this workspace",
                category="hub_state",
                details={"next": "run task up so kind creates native Hub and MCP host port mappings"},
            )
        if not self.cfg.endpoint:
            raise HubAPIError("Hub endpoint is not configured", category="hub_state")
        if not self.cfg.grove_id:
            raise HubAPIError("Hub grove id is not configured", category="hub_state")
        if not self.cfg.auth:
            raise HubAPIError(
                "No Hub auth token found",
                category="hub_auth",
                details={
                    "checked": [
                        "OAuth credentials",
                        "agent token",
                        "SCION_HUB_TOKEN",
                        "SCION_DEV_TOKEN",
                        "~/.scion/dev-token",
                    ]
                },
            )

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: Any = None,
        timeout: int = 15,
        require_grove: bool = True,
    ) -> Any:
        if require_grove:
            self._require_ready()
        elif not self.cfg.endpoint:
            raise HubAPIError("Hub endpoint is not configured", category="hub_state")

        url = self.cfg.endpoint + path
        if query:
            url += "?" + urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None}
            )

        data: bytes | None = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if self.cfg.auth:
            if self.cfg.auth.header == "Authorization":
                headers["Authorization"] = f"Bearer {self.cfg.auth.token}"
            else:
                headers[self.cfg.auth.header] = self.cfg.auth.token

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.status == 204 or not raw:
                    return None
                return json.loads(raw.decode())
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            code = ""
            message = raw or exc.reason
            details: Any = None
            try:
                parsed = json.loads(raw)
                err = parsed.get("error", {}) if isinstance(parsed, dict) else {}
                if isinstance(err, dict):
                    code = str(err.get("code") or "")
                    message = str(err.get("message") or message)
                    details = err.get("details")
            except json.JSONDecodeError:
                pass
            raise HubAPIError(
                message,
                category=_classify_hub_error(exc.code, code, message),
                status=exc.code,
                code=code,
                path=path,
                details=details,
            ) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise HubAPIError(
                f"Hub request failed: {exc}",
                category="hub_unavailable",
                path=path,
            ) from exc
        except json.JSONDecodeError as exc:
            raise HubAPIError(
                f"Hub returned non-JSON response: {exc}",
                category="hub_api",
                path=path,
            ) from exc

    def health(self) -> Any:
        return self.request("GET", "/healthz", require_grove=False)

    def grove(self) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/groves/{urllib.parse.quote(self.cfg.grove_id)}")

    def providers(self) -> list[dict[str, Any]]:
        data = self.request(
            "GET",
            f"/api/v1/groves/{urllib.parse.quote(self.cfg.grove_id)}/providers",
        )
        providers = data.get("providers", []) if isinstance(data, dict) else []
        return [item for item in providers if isinstance(item, dict)]

    def brokers(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/api/v1/runtime-brokers", query={"groveId": self.cfg.grove_id})
        brokers = data.get("brokers", []) if isinstance(data, dict) else []
        return [item for item in brokers if isinstance(item, dict)]

    def agents(self, round_filter: str = "", include_deleted: bool = False) -> list[dict[str, Any]]:
        query: dict[str, str] = {}
        if include_deleted:
            query["includeDeleted"] = "true"
        data = self.request(
            "GET",
            f"/api/v1/groves/{urllib.parse.quote(self.cfg.grove_id)}/agents",
            query=query,
        )
        agents = data.get("agents", []) if isinstance(data, dict) else []
        result = [item for item in agents if isinstance(item, dict)]
        if round_filter:
            result = [
                agent
                for agent in result
                if round_filter in str(agent.get("name", ""))
                or round_filter in str(agent.get("slug", ""))
            ]
        return result

    def messages(self, round_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
        data = self.request(
            "GET",
            "/api/v1/messages",
            query={"grove": self.cfg.grove_id, "limit": str(limit)},
        )
        messages = (data.get("items") or []) if isinstance(data, dict) else []
        result = [item for item in messages if isinstance(item, dict)]
        if round_id:
            result = [item for item in result if _round_text_match(item, round_id)]
        return result

    def notifications(self, round_id: str = "") -> list[dict[str, Any]]:
        data = self.request("GET", "/api/v1/notifications", query={"acknowledged": "true"})
        notifications = data if isinstance(data, list) else []
        result = [
            item
            for item in notifications
            if isinstance(item, dict)
            and (not item.get("groveId") or item.get("groveId") == self.cfg.grove_id)
        ]
        if round_id:
            result = [item for item in result if _round_text_match(item, round_id)]
        return result

    def stop_agent(self, agent: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(agent.get("slug") or agent.get("name") or agent.get("id"))
        self.request(
            "POST",
            f"/api/v1/groves/{urllib.parse.quote(self.cfg.grove_id)}/agents/"
            f"{urllib.parse.quote(agent_id)}/stop",
        )
        return {"agent": agent_id, "action": "stop", "ok": True}

    def delete_agent(self, agent: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(agent.get("slug") or agent.get("name") or agent.get("id"))
        self.request(
            "DELETE",
            f"/api/v1/groves/{urllib.parse.quote(self.cfg.grove_id)}/agents/{urllib.parse.quote(agent_id)}",
            query={"deleteFiles": "true", "removeBranch": "true"},
        )
        return {"agent": agent_id, "action": "delete", "ok": True}


def _classify_hub_error(status: int | None, code: str, message: str) -> str:
    text = f"{code} {message}".lower()
    if status in {401, 403} or "unauthorized" in text or "forbidden" in text:
        return "hub_auth"
    if "broker" in text or "dispatch" in text or "provider" in text:
        return "broker_dispatch"
    if "runtime" in text or "kubernetes" in text or "pod" in text or "container" in text:
        return "runtime"
    if status == 404:
        return "hub_state"
    if status and status >= 500:
        return "hub_unavailable"
    return "hub_api"


def _clean_name(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} is required")
    if not NAME_RE.match(value):
        raise ValueError(f"{label} contains unsupported characters: {value!r}")
    return value


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _agent_summary(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": agent.get("name") or agent.get("slug"),
        "slug": agent.get("slug"),
        "id": agent.get("id"),
        "template": agent.get("template"),
        "harnessConfig": agent.get("harnessConfig"),
        "harnessAuth": agent.get("harnessAuth"),
        "groveId": agent.get("groveId"),
        "phase": agent.get("phase"),
        "activity": agent.get("activity"),
        "containerStatus": agent.get("containerStatus"),
        "runtime": agent.get("runtime"),
        "runtimeBrokerId": agent.get("runtimeBrokerId"),
        "runtimeBrokerName": agent.get("runtimeBrokerName"),
        "taskSummary": agent.get("taskSummary"),
        "created": agent.get("created"),
        "updated": agent.get("updated"),
    }


def _list_agents(round_filter: str = "", project_root: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = HubClient(project_root)
    agents = client.agents(round_filter)
    return agents, {
        "ok": True,
        "source": "hub_api",
        "hub": client.cfg.redacted(),
        "count": len(agents),
    }


def _round_text_match(item: dict[str, Any], round_id: str) -> bool:
    needle = round_id.lower()
    fields = [
        item.get("id"),
        item.get("name"),
        item.get("slug"),
        item.get("agentId"),
        item.get("sender"),
        item.get("senderId"),
        item.get("msg"),
        item.get("message"),
        item.get("status"),
        item.get("taskSummary"),
    ]
    return any(needle in str(value).lower() for value in fields if value is not None)


def _list_round_messages(round_id: str, project_root: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = HubClient(project_root)
    messages = client.messages(round_id)
    return messages, {
        "ok": True,
        "source": "hub_api",
        "hub": client.cfg.redacted(),
        "count": len(messages),
    }


def _list_round_notifications(round_id: str, project_root: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = HubClient(project_root)
    notifications = client.notifications(round_id)
    return notifications, {
        "ok": True,
        "source": "hub_api",
        "hub": client.cfg.redacted(),
        "count": len(notifications),
    }


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


def _round_event_snapshot(round_id: str, project_root: str = "") -> dict[str, Any]:
    agents, agent_result = _list_agents(round_id, project_root)
    messages, message_result = _list_round_messages(round_id, project_root)
    notifications, notification_result = _list_round_notifications(round_id, project_root)
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
        "source": "hub_api",
        "hub": agent_result.get("hub") or message_result.get("hub") or notification_result.get("hub"),
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
            agent = next(
                (
                    item
                    for item in snapshot["agents"]
                    if item.get("name") == name or item.get("slug") == name
                ),
                {},
            )
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


def _default_base_branch(project_root: str = "") -> str:
    root = _project_root(project_root) if project_root else _repo_root()
    result = _run(["git", "branch", "--show-current"], timeout=10, cwd=root)
    current = result["output"].strip()
    return current or "HEAD"


@mcp.tool()
def scion_ops_hub_status(project_root: str = "") -> dict[str, Any]:
    """Show Scion Hub API health, grove, broker providers, and agents."""
    client = HubClient(project_root)
    try:
        health = client.health()
        grove = client.grove()
        providers = client.providers()
        brokers = client.brokers()
        agents = client.agents()
    except HubAPIError as exc:
        return _hub_error_payload(exc, "hub_status", client.cfg)
    summaries = [_agent_summary(agent) for agent in agents]
    return {
        "ok": True,
        "source": "hub_api",
        "hub": client.cfg.redacted(),
        "health": health,
        "grove": grove,
        "providers": providers,
        "brokers": brokers,
        "agent_count": len(summaries),
        "phase_counts": dict(Counter(str(item.get("phase")) for item in summaries)),
        "activity_counts": dict(Counter(str(item.get("activity")) for item in summaries)),
        "agents": summaries,
    }


@mcp.tool()
def scion_ops_list_agents(round_filter: str = "", project_root: str = "") -> dict[str, Any]:
    """List Scion agents from Hub API state, optionally filtered by a round id substring."""
    if round_filter:
        _clean_name(round_filter, "round_filter")
    try:
        agents, result = _list_agents(round_filter, project_root)
    except HubAPIError as exc:
        return _hub_error_payload(exc, "list_agents")
    summaries = [_agent_summary(agent) for agent in agents]
    return {
        "ok": result["ok"],
        "source": "hub_api",
        "hub": result.get("hub"),
        "round_filter": round_filter,
        "count": len(summaries),
        "phase_counts": dict(Counter(str(item.get("phase")) for item in summaries)),
        "activity_counts": dict(Counter(str(item.get("activity")) for item in summaries)),
        "agents": summaries,
    }


@mcp.tool()
def scion_ops_look(agent_name: str, num_lines: int = 160, project_root: str = "") -> dict[str, Any]:
    """Read terminal output for a Scion agent with `scion look`."""
    agent_name = _clean_name(agent_name, "agent_name")
    num_lines = _clamp(num_lines, 20, 600)
    args = ["scion"]
    root = _project_root(project_root) if project_root else None
    if root:
        args.extend(["--grove", str(root)])
    args.extend(
        [
            "look",
            agent_name,
            "--non-interactive",
            "--plain",
            "--num-lines",
            str(num_lines),
        ]
    )
    return _command_result(_run(
        args,
        timeout=35,
        cwd=root,
    ))


@mcp.tool()
def scion_ops_round_status(
    round_id: str = "",
    include_transcript: bool = True,
    num_lines: int = 120,
    project_root: str = "",
) -> dict[str, Any]:
    """Summarize a consensus round from Hub API state and optionally include the runner tail."""
    if round_id:
        _clean_name(round_id, "round_id")
    num_lines = _clamp(num_lines, 20, 400)
    try:
        agents, result = _list_agents(round_id, project_root)
    except HubAPIError as exc:
        return _hub_error_payload(exc, "round_status")
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
    transcript: dict[str, Any] = {}
    if include_transcript and consensus:
        transcript = scion_ops_look(consensus, num_lines=num_lines, project_root=project_root)
    return {
        "ok": result["ok"],
        "source": "hub_api",
        "hub": result.get("hub"),
        "round_id": round_id,
        "agents": summaries,
        "phase_counts": dict(Counter(str(item.get("phase")) for item in summaries)),
        "activity_counts": dict(Counter(str(item.get("activity")) for item in summaries)),
        "consensus_agent": consensus,
        "consensus_transcript": transcript,
    }


@mcp.tool()
def scion_ops_round_events(
    round_id: str,
    cursor: str = "",
    include_existing: bool = False,
    project_root: str = "",
) -> dict[str, Any]:
    """Read Hub messages/notifications and agent-state changes for a round."""
    round_id = _clean_name(round_id, "round_id")
    previous = _decode_cursor(cursor, round_id)
    try:
        snapshot = _round_event_snapshot(round_id, project_root)
    except HubAPIError as exc:
        return _hub_error_payload(exc, "round_events")
    events = _round_events_since(snapshot, previous, include_existing=include_existing)
    return {
        "ok": all(snapshot["commands_ok"].values()),
        "source": "hub_api",
        "hub": snapshot.get("hub"),
        "round_id": round_id,
        "changed": bool(events),
        "events": events,
        "cursor": _encode_cursor(snapshot),
        "terminal": _round_terminal_status(snapshot) or {},
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
    project_root: str = "",
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
        try:
            snapshot = _round_event_snapshot(round_id, project_root)
        except HubAPIError as exc:
            return _hub_error_payload(exc, "watch_round_events")
        previous = {
            "round_id": round_id,
            "agent_fingerprints": snapshot["agent_fingerprints"],
            "message_ids": snapshot["message_ids"],
            "notification_ids": snapshot["notification_ids"],
        }

    deadline = time.monotonic() + timeout_seconds
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        try:
            snapshot = _round_event_snapshot(round_id, project_root)
        except HubAPIError as exc:
            return _hub_error_payload(exc, "watch_round_events")
        last_snapshot = snapshot
        events = _round_events_since(snapshot, previous, include_existing=include_existing)
        terminal = _round_terminal_status(snapshot)
        if events or terminal:
            return {
                "ok": all(snapshot["commands_ok"].values()),
                "source": "hub_api",
                "hub": snapshot.get("hub"),
                "round_id": round_id,
                "changed": bool(events),
                "events": events,
                "cursor": _encode_cursor(snapshot),
                "terminal": terminal or {},
                "timed_out": False,
                "agent_count": len(snapshot["agents"]),
                "message_count": len(snapshot["messages"]),
                "notification_count": len(snapshot["notifications"]),
                "commands_ok": snapshot["commands_ok"],
            }
        time.sleep(poll_interval_seconds)

    try:
        snapshot = last_snapshot or _round_event_snapshot(round_id, project_root)
    except HubAPIError as exc:
        return _hub_error_payload(exc, "watch_round_events")
    return {
        "ok": all(snapshot["commands_ok"].values()),
        "source": "hub_api",
        "hub": snapshot.get("hub"),
        "round_id": round_id,
        "changed": False,
        "events": [],
        "cursor": _encode_cursor(snapshot),
        "terminal": _round_terminal_status(snapshot) or {},
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
    project_root: str = "",
) -> dict[str, Any]:
    """Start a detached scion-ops consensus round via `task round`."""
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt is required")
    target_root = _project_root(project_root) if project_root else _repo_root()
    env: dict[str, str] = {
        "MAX_MINUTES": str(_clamp(max_minutes, 1, 240)),
        "MAX_REVIEW_ROUNDS": str(_clamp(max_review_rounds, 1, 10)),
        "SCION_OPS_PROJECT_ROOT": str(target_root),
    }
    if round_id:
        env["ROUND_ID"] = _clean_name(round_id, "round_id")
    if base_branch:
        env["BASE_BRANCH"] = _clean_name(base_branch, "base_branch")
    else:
        env["BASE_BRANCH"] = _default_base_branch(str(target_root))
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
    event_cursor_error: dict[str, Any] = {}
    if parsed_round_id:
        try:
            event_cursor = _encode_cursor(_round_event_snapshot(parsed_round_id, str(target_root)))
        except HubAPIError as exc:
            event_cursor_error = _hub_error_payload(exc, "start_round_event_cursor")
    return {
        **_command_result(result),
        "project_root": str(target_root),
        "round_id": parsed_round_id,
        "consensus_agent": runner,
        "event_cursor": event_cursor,
        "event_cursor_error": event_cursor_error,
        "next": {
            "watch_tool": "scion_ops_watch_round_events",
            "events_tool": "scion_ops_round_events",
            "abort_tool": "scion_ops_abort_round",
        },
    }


@mcp.tool()
def scion_ops_abort_round(round_id: str, confirm: bool = False, project_root: str = "") -> dict[str, Any]:
    """Stop and delete Hub agents matching a round id. Requires confirm=true."""
    round_id = _clean_name(round_id, "round_id")
    client = HubClient(project_root)
    try:
        agents = client.agents(round_id)
    except HubAPIError as exc:
        return _hub_error_payload(exc, "abort_round", client.cfg)
    matching = [_agent_summary(agent) for agent in agents]
    if not confirm:
        return {
            "ok": False,
            "source": "hub_api",
            "hub": client.cfg.redacted(),
            "dry_run": True,
            "message": "Set confirm=true to stop and delete these agents.",
            "matching_agents": matching,
        }
    results: list[dict[str, Any]] = []
    for agent in agents:
        summary = _agent_summary(agent)
        try:
            if str(agent.get("phase") or "").lower() not in {"stopped", "deleted"}:
                results.append({**client.stop_agent(agent), "summary": summary})
            results.append({**client.delete_agent(agent), "summary": summary})
        except HubAPIError as exc:
            results.append({"ok": False, "summary": summary, **exc.payload()})
    return {
        "ok": all(item.get("ok") for item in results),
        "source": "hub_api",
        "hub": client.cfg.redacted(),
        "matching_agents_before_abort": matching,
        "results": results,
    }


@mcp.tool()
def scion_ops_round_artifacts(round_id: str, project_root: str = "") -> dict[str, Any]:
    """Find local branches and agent workspaces associated with a round id."""
    round_id = _clean_name(round_id, "round_id")
    root = _project_root(project_root) if project_root else _repo_root()
    branch_patterns = sorted({f"*{round_id}*", f"*{round_id.lower()}*"})
    branch_result = _run(["git", "branch", "--list", *branch_patterns], timeout=15, cwd=root)
    agents_dir = root / ".scion" / "agents"
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
        "source": "local_git",
        "project_root": str(root),
        "branches": [line.strip(" *+") for line in branch_result["output"].splitlines() if line.strip()],
        "workspaces": workspaces,
        "prompts": prompts,
        "branch_result": _command_result(branch_result),
    }


@mcp.tool()
def scion_ops_project_status(project_root: str) -> dict[str, Any]:
    """Resolve a target project path and show its git, grove, and Hub context."""
    root = _project_root(project_root)
    status = _run(["git", "status", "--short", "--branch"], timeout=15, cwd=root)
    branch = _run(["git", "branch", "--show-current"], timeout=10, cwd=root)
    remote = _run(["git", "remote", "get-url", "origin"], timeout=10, cwd=root)
    grove_id = _read_text_file(root / ".scion" / "grove-id")
    hub = _hub_config(root).redacted()
    return {
        "ok": status["ok"],
        "source": "local_git",
        "project_root": str(root),
        "branch": branch["output"].strip(),
        "origin": remote["output"].strip(),
        "grove_id": grove_id,
        "hub": hub,
        "status": _command_result(status),
        "next": {
            "bootstrap": "Run `task bootstrap -- <project_root>` from the scion-ops repo if grove_id is empty or preflight fails.",
            "start_round_tool": "scion_ops_start_round",
        },
    }


@mcp.tool()
def scion_ops_git_status(project_root: str = "") -> dict[str, Any]:
    """Show repo status and local round branches."""
    root = _project_root(project_root) if project_root else _repo_root()
    status = _run(["git", "status", "--short", "--branch"], timeout=15, cwd=root)
    branches = _run(["git", "branch", "--list", "round-*"], timeout=15, cwd=root)
    return {
        "source": "local_git",
        "project_root": str(root),
        "status": _command_result(status),
        "round_branches": branches["output"].splitlines(),
        "round_branch_result": _command_result(branches),
    }


@mcp.tool()
def scion_ops_git_diff(
    branch: str,
    base_branch: str = "",
    path_filter: str = "",
    stat_only: bool = False,
    max_output_chars: int = 20000,
    project_root: str = "",
) -> dict[str, Any]:
    """Show a branch diff against a base branch, optionally limited to one path."""
    branch = _clean_name(branch, "branch")
    root = _project_root(project_root) if project_root else _repo_root()
    base_branch = _clean_name(base_branch, "base_branch") if base_branch else _default_base_branch(str(root))
    max_output_chars = _clamp(max_output_chars, 1000, 60000)
    args = ["git", "diff"]
    if stat_only:
        args.append("--stat")
    args.append(f"{base_branch}..{branch}")
    if path_filter:
        args.extend(["--", path_filter])
    result = _run(args, timeout=25, cwd=root)
    output = result["output"]
    truncated = len(output) > max_output_chars
    return {
        **_command_result(result),
        "source": "local_git",
        "project_root": str(root),
        "output": output[:max_output_chars],
        "truncated": truncated,
    }


@mcp.tool()
def scion_ops_verify() -> dict[str, Any]:
    """Run the repository verification gate via `task verify`."""
    return _command_result(_run(["task", "verify"], timeout=120))


@mcp.tool()
def scion_ops_tail_round_log(num_lines: int = 160) -> dict[str, Any]:
    """Read the detached round launcher log at /tmp/scion-round.log."""
    num_lines = _clamp(num_lines, 20, 600)
    log_path = Path("/tmp/scion-round.log")
    if not log_path.exists():
        return {
            "ok": False,
            "source": "local_file",
            "error_kind": "local_state",
            "path": str(log_path),
            "output": "log file does not exist",
        }
    lines = log_path.read_text(errors="replace").splitlines()
    return {
        "ok": True,
        "source": "local_file",
        "path": str(log_path),
        "output": "\n".join(lines[-num_lines:]),
    }


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
