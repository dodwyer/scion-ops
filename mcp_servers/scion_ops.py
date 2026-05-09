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
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP


ROOT = Path(os.environ.get("SCION_OPS_ROOT", Path(__file__).resolve().parents[1])).resolve()
DEFAULT_TIMEOUT_SECONDS = 45
NAME_RE = re.compile(r"^[A-Za-z0-9._:/@+-]+$")
ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[()][A-Za-z0-9])")
DEFAULT_HOST_WORKSPACE_ROOT = "/home/david/workspace"
DEFAULT_CONTAINER_WORKSPACE_ROOT = "/workspace"
DEFAULT_REPO_CHECKOUT_SUBDIR = "github"
PLACEHOLDER_SUMMARY_TOKENS = (
    "<round_id>",
    "<branch>",
    "<agent",
    "<summary>",
    "<json verdict>",
    "round ...",
    "round-...",
    "...-integration",
    "...-spec-",
    "concrete reason",
    "concrete question",
    "concrete verdict json",
    "round_id",
    "agent_name",
    "concrete_summary",
    "collection_recipient",
)
SPEC_CHILD_TEMPLATES = {
    "spec-goal-clarifier",
    "spec-repo-explorer",
    "spec-author",
    "spec-ops-reviewer",
    "spec-finalizer",
}
OPENSPEC_REQUIRED_FILES = ("proposal.md", "design.md", "tasks.md")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_port(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    raw = value.strip()
    try:
        return int(raw)
    except ValueError:
        parsed = urllib.parse.urlparse(raw)
        if parsed.port is not None:
            return parsed.port
    raise ValueError(f"{name} must be an integer port or URL with a port, got {value!r}")


mcp = FastMCP(
    "scion-ops",
    instructions=(
        "Use these tools to start and monitor scion-ops consensus rounds, "
        "inspect Scion agents, and review the resulting git branches. "
        "Pass project_root for the project being changed; if omitted, the "
        "server uses its current working checkout."
    ),
    host=os.environ.get("SCION_OPS_MCP_HOST", "127.0.0.1"),
    port=_env_port("SCION_OPS_MCP_PORT", 8765),
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
    except OSError as exc:
        return {
            "ok": False,
            "timed_out": False,
            "returncode": None,
            "command": args,
            "output": "",
            "error": str(exc),
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


def _kubernetes_namespace() -> str:
    namespace = os.environ.get("SCION_K8S_NAMESPACE", "").strip()
    if namespace:
        return namespace
    ns_file = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if ns_file.exists():
        text = ns_file.read_text(errors="replace").strip()
        if text:
            return text
    return "scion-agents"


def _kubectl_context_args() -> list[str]:
    context = os.environ.get("SCION_OPS_KUBE_CONTEXT", "").strip() or os.environ.get("KIND_CONTEXT", "").strip()
    return ["--context", context] if context else []


def _kubectl_agent_logs(agent_name: str, num_lines: int) -> dict[str, Any]:
    args = [
        "kubectl",
        *_kubectl_context_args(),
        "-n",
        _kubernetes_namespace(),
        "logs",
        agent_name,
        "--tail",
        str(num_lines),
    ]
    result = _run(args, timeout=35)
    if isinstance(result.get("output"), str):
        result["output"] = ANSI_RE.sub("", result["output"])
    return result


def _looks_like_missing_terminal_output(result: dict[str, Any]) -> bool:
    output = str(result.get("output") or "").lower()
    error = str(result.get("error") or "").lower()
    return (
        not result.get("ok")
        and (
            (
                "failed to capture terminal output" in output
                and ("not_found" in output or "resource not found" in output)
            )
            or "no such file or directory" in error
        )
    )


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


def _map_project_path(path: Path, *, require_exists: bool = True) -> Path:
    if require_exists and path.exists():
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
        if not require_exists or candidate.exists():
            return candidate
    return path


def _host_path_for_project_path(path: Path) -> Path:
    path_str = str(path)
    for host_root, container_root in _path_mappings():
        container = str(container_root)
        if path_str == container:
            return host_root
        if path_str.startswith(container.rstrip("/") + "/"):
            return host_root / path_str[len(container.rstrip("/")) + 1 :]
    return path


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_under_workspace_root(path: Path) -> bool:
    for host_root, container_root in _path_mappings():
        if _path_within(path, host_root) or _path_within(path, container_root):
            return True
    return False


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
class GitHubRepoRef:
    owner: str
    repo: str
    input_kind: str
    clone_url: str
    https_url: str
    ssh_url: str


def _strip_dot_git(name: str) -> str:
    return name[:-4] if name.endswith(".git") else name


def _github_repo_ref(repo_url: str) -> GitHubRepoRef:
    raw = repo_url.strip()
    if not raw:
        raise ValueError("repo_url is required")

    input_kind = "https"
    path = ""
    if raw.startswith("git@github.com:"):
        input_kind = "ssh"
        path = raw.removeprefix("git@github.com:")
    else:
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme == "https" and parsed.hostname == "github.com":
            path = parsed.path.lstrip("/")
        elif parsed.scheme == "ssh" and parsed.hostname == "github.com":
            input_kind = "ssh"
            path = parsed.path.lstrip("/")
        else:
            raise ValueError("repo_url must be a GitHub HTTPS or SSH URL")

    parts = [part for part in path.rstrip("/").split("/") if part]
    if len(parts) != 2:
        raise ValueError("repo_url must identify exactly one GitHub repository")
    owner = parts[0]
    repo = _strip_dot_git(parts[1])
    name_re = re.compile(r"^[A-Za-z0-9_.-]+$")
    if not name_re.fullmatch(owner) or not name_re.fullmatch(repo):
        raise ValueError("repo_url contains unsupported owner or repository characters")
    https_url = f"https://github.com/{owner}/{repo}.git"
    ssh_url = f"git@github.com:{owner}/{repo}.git"
    clone_url = ssh_url if input_kind == "ssh" else https_url
    return GitHubRepoRef(
        owner=owner,
        repo=repo,
        input_kind=input_kind,
        clone_url=clone_url,
        https_url=https_url,
        ssh_url=ssh_url,
    )


def _github_remote_key(remote_url: str) -> str:
    try:
        ref = _github_repo_ref(remote_url.strip())
    except ValueError:
        return ""
    return f"{ref.owner.lower()}/{ref.repo.lower()}"


def _configured_checkout_root(checkout_root: str = "") -> Path:
    host_root = Path(os.environ.get("SCION_OPS_HOST_WORKSPACE_ROOT", DEFAULT_HOST_WORKSPACE_ROOT)).expanduser()
    configured_env = os.environ.get("SCION_OPS_REPO_CHECKOUT_ROOT", "").strip()
    configured = checkout_root.strip() or configured_env
    if configured:
        requested = Path(configured).expanduser()
        if not requested.is_absolute():
            requested = host_root / requested
    else:
        requested = host_root / DEFAULT_REPO_CHECKOUT_SUBDIR
    if not requested.is_absolute():
        requested = (_repo_root() / requested).resolve()
    actual = _map_project_path(requested, require_exists=False).resolve()
    if not _path_under_workspace_root(actual) and not (configured_env and not checkout_root.strip()):
        raise ValueError(f"checkout_root is outside the configured workspace tree: {requested}")
    return actual


def _git_summary(root: Path) -> dict[str, Any]:
    _run(["git", "config", "--global", "--add", "safe.directory", str(root)], timeout=10, cwd=_repo_root())
    status = _run(["git", "status", "--short", "--branch"], timeout=15, cwd=root)
    branch = _run(["git", "branch", "--show-current"], timeout=10, cwd=root)
    remote = _run(["git", "remote", "get-url", "origin"], timeout=10, cwd=root)
    status_lines = status["output"].splitlines()
    dirty_lines = [
        line
        for line in status_lines
        if line.strip() and not line.startswith("##") and not line.startswith("warning:")
    ]
    return {
        "branch": branch["output"].strip(),
        "origin": remote["output"].strip(),
        "dirty": bool(dirty_lines),
        "status": _command_result(status),
        "branch_result": _command_result(branch),
        "origin_result": _command_result(remote),
    }


def _clone_failure_kind(result: dict[str, Any]) -> str:
    if result.get("timed_out"):
        return "clone_timeout"
    output = result.get("output", "").lower()
    if (
        "authentication failed" in output
        or "permission denied" in output
        or "could not read from remote repository" in output
        or "repository not found" in output
    ):
        return "git_auth"
    return "clone"


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
        "containerStatus": agent.get("containerStatus"),
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


def _message_text(item: dict[str, Any]) -> str:
    return str(item.get("msg") or item.get("message") or item.get("summary") or "")


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _final_review_agents(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        agent
        for agent in agents
        if str(agent.get("template") or "").startswith("final-reviewer-")
        or str(agent.get("name") or agent.get("slug") or "").endswith("-final-review")
    ]


def _normalize_final_verdict(value: Any) -> str:
    verdict = str(value or "").strip().lower()
    if verdict in {"accept", "accepted", "approved", "success", "pass", "passed"}:
        return "accept"
    if verdict == "blocked":
        return "blocked"
    if verdict in {"reject", "rejected", "request_changes", "changes_requested", "revise", "fail", "failed"}:
        return "request_changes"
    return verdict


def _final_review_outcome(snapshot: dict[str, Any]) -> dict[str, Any]:
    agents = snapshot.get("agents", [])
    final_agents = _final_review_agents(agents)
    final_names = {
        str(value)
        for agent in final_agents
        for value in (agent.get("name"), agent.get("slug"), agent.get("id"))
        if value
    }
    candidates: list[dict[str, Any]] = []
    for item in snapshot.get("messages", []):
        payload = _parse_json_object(_message_text(item))
        if not payload:
            continue
        reviewer = str(payload.get("reviewer") or "").lower()
        branch = str(payload.get("branch") or payload.get("target_branch") or "").lower()
        sender = str(item.get("sender") or item.get("senderId") or item.get("agentId") or "")
        is_final = (
            reviewer.startswith("final-")
            or "final-review" in branch
            or any(name and name in sender for name in final_names)
        )
        if not is_final or "verdict" not in payload:
            continue
        created = _parse_timestamp(item.get("createdAt") or item.get("created") or item.get("updated"))
        candidates.append({
            "source": "final_review_message",
            "agent": sender.removeprefix("agent:") or payload.get("reviewer") or "",
            "created": created.isoformat() if created else "",
            "verdict": str(payload.get("verdict") or ""),
            "normalized_verdict": _normalize_final_verdict(payload.get("verdict")),
            "test_results": str(payload.get("test_results") or ""),
            "branch": str(payload.get("branch") or payload.get("target_branch") or ""),
            "blocking_issues": payload.get("blocking_issues") if isinstance(payload.get("blocking_issues"), list) else [],
            "final_failure_classification": str(payload.get("final_failure_classification") or ""),
            "final_failure_evidence": str(payload.get("final_failure_evidence") or ""),
            "notes": _short_text(payload.get("notes"), limit=500),
        })

    if candidates:
        candidates.sort(key=lambda item: item.get("created") or "")
        latest = candidates[-1]
        latest["status"] = "accepted" if latest["normalized_verdict"] == "accept" else "blocked"
        return latest

    for agent in final_agents:
        summary = str(agent.get("taskSummary") or "")
        match = re.search(r"final verdict:\s*([A-Za-z_ -]+)", summary, flags=re.IGNORECASE)
        if not match:
            continue
        normalized = _normalize_final_verdict(match.group(1))
        return {
            "source": "final_review_summary",
            "agent": agent.get("name") or agent.get("slug") or "",
            "created": agent.get("updated") or "",
            "verdict": match.group(1).strip(),
            "normalized_verdict": normalized,
            "test_results": "",
            "branch": "",
            "blocking_issues": [],
            "notes": "",
            "status": "accepted" if normalized == "accept" else "blocked",
        }
    return {}


def _round_outcome(snapshot: dict[str, Any]) -> dict[str, Any]:
    final_review = _final_review_outcome(snapshot)
    if final_review:
        return {
            "status": final_review["status"],
            "source": final_review["source"],
            "final_review": final_review,
        }

    terminal = _round_terminal_status_from_consensus(snapshot)
    if terminal:
        summary = str(terminal.get("taskSummary") or "")
        status = "completed"
        summary_lower = summary.lower()
        if (
            "escalated:" in summary_lower
            or summary_lower.startswith("escalate:")
            or "blocked" in summary_lower
            or "request_changes" in summary_lower
        ):
            status = "blocked"
        elif not summary.strip():
            status = "unknown"
        return {
            "status": status,
            "source": "consensus",
            "consensus": terminal,
        }
    return {}


def _round_terminal_status_from_consensus(snapshot: dict[str, Any]) -> dict[str, Any] | None:
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
    phase = str(consensus.get("phase") or "").lower()
    activity = str(consensus.get("activity") or "").lower()
    container_status = str(consensus.get("containerStatus") or "").lower()
    terminal_state = (
        phase in {"stopped", "deleted", "ended", "completed", "error", "failed"}
        or activity in {"completed", "limits_exceeded"}
        or any(token in container_status for token in ("succeeded", "completed", "failed", "error"))
    )
    if not terminal_state:
        return None
    has_placeholder = _has_placeholder_summary(consensus)
    has_terminal_summary = (
        (" complete:" in summary or " escalated:" in summary or summary.startswith("spec ready:"))
        and not has_placeholder
    )
    if has_placeholder:
        return None
    if activity == "completed" or has_terminal_summary or terminal_state:
        return {
            "agent": consensus.get("name"),
            "phase": consensus.get("phase"),
            "activity": consensus.get("activity"),
            "containerStatus": consensus.get("containerStatus"),
            "taskSummary": consensus.get("taskSummary"),
        }
    return None


def _round_terminal_status(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    outcome = _round_outcome(snapshot)
    if outcome:
        return outcome
    return _round_terminal_status_from_consensus(snapshot)


def _snapshot_outcome(snapshot: dict[str, Any]) -> dict[str, Any]:
    return _round_outcome(snapshot)


def _default_base_branch(project_root: str = "") -> str:
    root = _project_root(project_root) if project_root else _repo_root()
    result = _run(["git", "branch", "--show-current"], timeout=10, cwd=root)
    current = result["output"].strip()
    return current or "HEAD"


def _default_steward_base_branch(project_root: str = "") -> str:
    root = _project_root(project_root) if project_root else _repo_root()
    origin_head = _run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        timeout=10,
        cwd=root,
    )
    if origin_head.get("ok"):
        value = origin_head["output"].strip()
        if value.startswith("origin/"):
            return value.removeprefix("origin/")
    for candidate in ("main", "master"):
        remote = _run(
            ["git", "rev-parse", "--verify", "--quiet", f"origin/{candidate}^{{commit}}"],
            timeout=10,
            cwd=root,
        )
        local = _run(
            ["git", "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"],
            timeout=10,
            cwd=root,
        )
        if remote.get("ok") or local.get("ok"):
            return candidate
    current = _default_base_branch(str(root))
    if current.startswith("round-"):
        return "main"
    return current or "main"


def _target_round_env(target_root: Path) -> dict[str, str]:
    env = {"SCION_OPS_PROJECT_ROOT": str(target_root)}
    grove_id = _read_text_file(target_root / ".scion" / "grove-id")
    if grove_id:
        env["SCION_GROVE_ID"] = grove_id
        env["SCION_OPS_GROVE_ID"] = grove_id
    return env


def _github_https_remote(remote_url: str) -> str:
    remote_url = remote_url.strip()
    if not remote_url:
        return ""
    if remote_url.startswith("https://github.com/"):
        return remote_url
    ssh_match = re.fullmatch(r"git@github\.com:(?P<repo>\S+)", remote_url)
    if ssh_match:
        return f"https://github.com/{ssh_match.group('repo')}"
    parsed = urllib.parse.urlparse(remote_url)
    if parsed.scheme == "ssh" and parsed.hostname == "github.com":
        path = parsed.path.lstrip("/")
        if parsed.username == "git" and path:
            return f"https://github.com/{path}"
    return ""


def _github_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip() or _read_text_file(
        Path("/run/secrets/scion-github-token/GITHUB_TOKEN")
    )


def _preferred_remote_for_reads(remote_url: str) -> str:
    https_remote = _github_https_remote(remote_url)
    if https_remote and _github_token():
        return https_remote
    return "origin"


def _run_git_authenticated(
    args: list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    cwd: Path | None = None,
) -> dict[str, Any]:
    token = _github_token()
    if not token:
        return _run(["git", *args], timeout=timeout, cwd=cwd)

    with tempfile.TemporaryDirectory(prefix="scion-git-auth-") as tmp:
        askpass = Path(tmp) / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *Username*) printf '%s\\n' x-access-token ;;\n"
            "  *) printf '%s\\n' \"$GITHUB_TOKEN\" ;;\n"
            "esac\n"
        )
        askpass.chmod(0o700)
        return _run(
            ["git", *args],
            timeout=timeout,
            cwd=cwd,
            env={
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "GITHUB_TOKEN": token,
            },
        )


def _remote_branch_sha(root: Path, branch: str) -> tuple[str, dict[str, Any]]:
    remote_url_result = _run(["git", "remote", "get-url", "origin"], timeout=10, cwd=root)
    remote = _preferred_remote_for_reads(remote_url_result["output"]) if remote_url_result["ok"] else "origin"
    result = _run_git_authenticated(["ls-remote", "--heads", remote, branch], timeout=25, cwd=root)
    primary = result
    if not result["ok"]:
        https_remote = _github_https_remote(remote_url_result["output"]) if remote_url_result["ok"] else ""
        if https_remote and remote != https_remote:
            result = _run_git_authenticated(["ls-remote", "--heads", https_remote, branch], timeout=25, cwd=root)
    sha = ""
    if result["ok"]:
        for line in result["output"].splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == f"refs/heads/{branch}":
                sha = parts[0]
                break
    return sha, {
        "result": _command_result(result),
        "primary_result": _command_result(primary),
    }


def _validate_remote_spec_change_result(root: Path, change: str, branch: str) -> dict[str, Any]:
    remote_url_result = _run(["git", "remote", "get-url", "origin"], timeout=10, cwd=root)
    if not remote_url_result["ok"]:
        return {
            "ok": False,
            "source": "openspec_remote_validator",
            "change": change,
            "branch": branch,
            "clone_result": {},
            "validation_result": {},
            "validation": {},
            "error": "origin remote is unavailable",
            "remote_url_result": _command_result(remote_url_result),
        }
    clone_url = _github_https_remote(remote_url_result["output"]) or remote_url_result["output"].strip()
    with tempfile.TemporaryDirectory(prefix="scion-openspec-validate-") as tmp:
        checkout = Path(tmp) / "checkout"
        clone_result = _run_git_authenticated(
            ["clone", "--depth", "1", "--branch", branch, clone_url, str(checkout)],
            timeout=90,
            cwd=_repo_root(),
        )
        if not clone_result["ok"]:
            return {
                "ok": False,
                "source": "openspec_remote_validator",
                "change": change,
                "branch": branch,
                "clone_result": _command_result(clone_result),
                "validation_result": {},
                "validation": {},
                "remote_url_result": _command_result(remote_url_result),
            }
        validation_result, validation = _validate_spec_change_result(checkout, change)
        return {
            "ok": bool(validation.get("ok")),
            "source": "openspec_remote_validator",
            "change": change,
            "branch": branch,
            "clone_result": _command_result(clone_result),
            "validation_result": validation_result,
            "validation": validation,
            "remote_url_result": _command_result(remote_url_result),
        }


def _parse_json_result(result: dict[str, Any]) -> dict[str, Any]:
    if not result.get("output"):
        return {}
    try:
        payload = json.loads(result["output"])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _openspec_cli_env() -> dict[str, str]:
    return {
        "OPENSPEC_TELEMETRY": "0",
        "DO_NOT_TRACK": "1",
        "NO_COLOR": "1",
    }


def _openspec_command_summary(result: dict[str, Any]) -> dict[str, Any]:
    output = result.get("output", "")
    if len(output) > 2000:
        output = output[:2000] + "\n[truncated]"
    return {
        "ok": result.get("ok", False),
        "timed_out": result.get("timed_out", False),
        "returncode": result.get("returncode"),
        "command": result.get("command", []),
        "output": output,
        "error": result.get("error", ""),
    }


def _openspec_change_file_metadata(root: Path, change: str) -> dict[str, Any]:
    change_path = root / "openspec" / "changes" / change
    specs_dir = change_path / "specs"
    spec_files = sorted(path for path in specs_dir.glob("**/spec.md") if path.is_file()) if specs_dir.exists() else []
    return {
        "change_path": _relative_to_root(change_path, root),
        "required_files": {
            filename: _relative_to_root(change_path / filename, root) for filename in OPENSPEC_REQUIRED_FILES
        },
        "spec_files": [_relative_to_root(path, root) for path in spec_files],
    }


def _openspec_issue_to_finding(issue: Any, root: Path) -> dict[str, str]:
    if isinstance(issue, dict):
        path = issue.get("path") or issue.get("file") or issue.get("location") or ""
        message = issue.get("message") or issue.get("error") or issue.get("detail") or json.dumps(issue, sort_keys=True)
    else:
        path = ""
        message = str(issue)
    if isinstance(path, list):
        path = ".".join(str(item) for item in path)
    path = str(path or root)
    return {"path": path, "message": str(message)}


def _openspec_validate_payload(root: Path, change: str, cli_payload: dict[str, Any]) -> dict[str, Any]:
    items = cli_payload.get("items", [])
    selected_item: dict[str, Any] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("id") == change:
                selected_item = item
                break
        if not selected_item and len(items) == 1 and isinstance(items[0], dict):
            selected_item = items[0]

    issues = selected_item.get("issues", []) if selected_item else []
    if not isinstance(issues, list):
        issues = [issues]
    totals = cli_payload.get("summary", {}).get("totals", {}) if isinstance(cli_payload.get("summary"), dict) else {}
    failed_count = totals.get("failed") if isinstance(totals, dict) else None
    if isinstance(selected_item.get("valid"), bool):
        ok = selected_item["valid"]
    elif isinstance(failed_count, int):
        ok = failed_count == 0
    else:
        ok = not issues

    return {
        "ok": ok,
        "validator": "openspec_cli",
        "project_root": str(root),
        "change": change,
        **_openspec_change_file_metadata(root, change),
        "errors": [] if ok else [_openspec_issue_to_finding(issue, root) for issue in issues],
        "warnings": [],
        "openspec_cli": cli_payload,
    }


def _run_openspec_validation(root: Path, change: str) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _run(
        ["openspec", "validate", change, "--json", "--no-interactive"],
        timeout=30,
        cwd=root,
        env=_openspec_cli_env(),
    )
    payload = _parse_json_result(result)
    if not payload:
        return result, {}

    validation = _openspec_validate_payload(root, change, payload)
    command_result = _command_result(result)
    command_result["source"] = "openspec_cli"
    if not validation.get("ok"):
        command_result["error_kind"] = "openspec_validation"
    return command_result, validation


def _run_python_openspec_validation(
    root: Path,
    change: str,
    cli_attempt: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _run(
        [
            "python3",
            str(_repo_root() / "scripts" / "validate-openspec-change.py"),
            "--project-root",
            str(root),
            "--change",
            change,
            "--json",
        ],
        timeout=20,
        cwd=_repo_root(),
    )
    payload = _parse_json_result(result)
    if payload:
        payload["validator"] = "scion_ops_python"
        if cli_attempt:
            payload["openspec_cli_attempt"] = _openspec_command_summary(cli_attempt)
    command_result = _command_result(result)
    command_result["source"] = "scion_ops_python"
    if payload and not payload.get("ok"):
        command_result["error_kind"] = "openspec_validation"
    return command_result, payload


def _openspec_status_result(root: Path, change: str) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _run(
        ["openspec", "status", "--change", change, "--json"],
        timeout=20,
        cwd=root,
        env=_openspec_cli_env(),
    )
    payload = _parse_json_result(result)
    command_result = _command_result(result)
    command_result["source"] = "openspec_cli_status"
    if not payload and not result.get("ok"):
        command_result["error_kind"] = "openspec_status"
    return command_result, payload


def _parse_started_round_id(output: str, fallback: str = "") -> str:
    for pattern in (r"round_id\s*:\s*(\S+)", r"Round id:\s*(\S+)"):
        match = re.search(pattern, output, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return fallback


def _start_round_response(
    result: dict[str, Any],
    *,
    target_root: Path,
    parsed_round_id: str,
    runner: str,
    next_hints: dict[str, str],
) -> dict[str, Any]:
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
        "next": next_hints,
    }


def _start_steward_response(
    result: dict[str, Any],
    *,
    target_root: Path,
    parsed_session_id: str,
    steward: str,
    next_hints: dict[str, str],
) -> dict[str, Any]:
    event_cursor = ""
    event_cursor_error: dict[str, Any] = {}
    if parsed_session_id:
        try:
            event_cursor = _encode_cursor(_round_event_snapshot(parsed_session_id, str(target_root)))
        except HubAPIError as exc:
            event_cursor_error = _hub_error_payload(exc, "start_steward_event_cursor")
    return {
        **_command_result(result),
        "project_root": str(target_root),
        "session_id": parsed_session_id,
        "round_id": parsed_session_id,
        "steward_agent": steward,
        "event_cursor": event_cursor,
        "event_cursor_error": event_cursor_error,
        "next": next_hints,
    }


def _validate_spec_change_result(root: Path, change: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if _env_bool("SCION_OPS_USE_OPENSPEC_CLI", True):
        cli_result, cli_payload = _run_openspec_validation(root, change)
        if cli_payload:
            return cli_result, cli_payload
        return _run_python_openspec_validation(root, change, cli_result)
    return _run_python_openspec_validation(root, change)


def _validate_spec_change_for_start(
    root: Path,
    change: str,
    base_branch: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if base_branch:
        branch = _clean_name(base_branch, "base_branch")
        result = _validate_remote_spec_change_result(root, change, branch)
        validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
        validation_ref = f"origin/{branch}"
        if validation:
            validation = {**validation, "validation_ref": validation_ref}
        return {**result, "project_root": str(root), "validation_ref": validation_ref}, validation

    result, validation = _validate_spec_change_result(root, change)
    validation_ref = "local_worktree"
    if validation:
        validation = {**validation, "validation_ref": validation_ref}
    return {**result, "validation_ref": validation_ref}, validation


def _archive_spec_change_result(root: Path, change: str, confirm: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    args = [
        "python3",
        str(_repo_root() / "scripts" / "archive-openspec-change.py"),
        "--project-root",
        str(root),
        "--change",
        change,
        "--json",
    ]
    if confirm:
        args.append("--yes")
    result = _run(args, timeout=30, cwd=_repo_root())
    payload = _parse_json_result(result)
    command_result = _command_result(result)
    if payload and not payload.get("ok"):
        command_result["error_kind"] = "openspec_archive"
    return command_result, payload


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
    """Read terminal output for a Scion agent, falling back to Kubernetes pod logs."""
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
    look_result = _command_result(_run(
        args,
        timeout=35,
        cwd=root,
    ))
    if look_result.get("ok") or not _looks_like_missing_terminal_output(look_result):
        return look_result

    log_result = _command_result(_kubectl_agent_logs(agent_name, num_lines))
    if log_result.get("ok"):
        return {
            **log_result,
            "source": "kubernetes_logs",
            "fallback_from": "scion_look",
            "look_result": look_result,
        }
    return {
        **look_result,
        "kubernetes_log_result": log_result,
    }


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
        messages, message_result = _list_round_messages(round_id, project_root)
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
    status_agent = consensus or next(
        (
            item.get("name")
            for item in summaries
            if str(item.get("template") or "").endswith("steward")
            and _agent_health(item) != "completed"
        ),
        "",
    )
    transcript: dict[str, Any] = {}
    if include_transcript and status_agent:
        transcript = scion_ops_look(status_agent, num_lines=num_lines, project_root=project_root)
    snapshot = {
        "agents": summaries,
        "messages": messages,
        "notifications": [],
    }
    outcome = _snapshot_outcome(snapshot)
    return {
        "ok": result["ok"] and message_result["ok"],
        "source": "hub_api",
        "hub": result.get("hub"),
        "round_id": round_id,
        "agents": summaries,
        "phase_counts": dict(Counter(str(item.get("phase")) for item in summaries)),
        "activity_counts": dict(Counter(str(item.get("activity")) for item in summaries)),
        "progress": _round_agent_progress(summaries),
        "outcome": outcome,
        "terminal": _round_terminal_status(snapshot) or {},
        "consensus_agent": consensus,
        "status_agent": status_agent,
        "consensus_transcript": transcript,
        "status_transcript": transcript,
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
    progress_lines = _snapshot_progress_lines(snapshot, round_id)
    return {
        "ok": all(snapshot["commands_ok"].values()),
        "source": "hub_api",
        "hub": snapshot.get("hub"),
        "round_id": round_id,
        "summary": progress_lines[0] if progress_lines else f"round {round_id} observed",
        "progress_lines": progress_lines,
        "changed": bool(events),
        "events": events,
        "cursor": _encode_cursor(snapshot),
        "outcome": _snapshot_outcome(snapshot),
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
            progress_lines = _snapshot_progress_lines(snapshot, round_id)
            return {
                "ok": all(snapshot["commands_ok"].values()),
                "source": "hub_api",
                "hub": snapshot.get("hub"),
                "round_id": round_id,
                "summary": progress_lines[0] if progress_lines else f"round {round_id} observed",
                "progress_lines": progress_lines,
                "changed": bool(events),
                "events": events,
                "cursor": _encode_cursor(snapshot),
                "outcome": _snapshot_outcome(snapshot),
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
    progress_lines = _snapshot_progress_lines(snapshot, round_id)
    return {
        "ok": all(snapshot["commands_ok"].values()),
        "source": "hub_api",
        "hub": snapshot.get("hub"),
        "round_id": round_id,
        "summary": progress_lines[0] if progress_lines else f"round {round_id} observed",
        "progress_lines": progress_lines,
        "changed": False,
        "events": [],
        "cursor": _encode_cursor(snapshot),
        "outcome": _snapshot_outcome(snapshot),
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
        **_target_round_env(target_root),
        "MAX_MINUTES": str(_clamp(max_minutes, 1, 240)),
        "MAX_REVIEW_ROUNDS": str(_clamp(max_review_rounds, 1, 10)),
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
    parsed_round_id = _parse_started_round_id(result["output"], env.get("ROUND_ID", ""))
    runner = f"round-{parsed_round_id.lower()}-consensus" if parsed_round_id else ""
    return _start_round_response(
        result,
        target_root=target_root,
        parsed_round_id=parsed_round_id,
        runner=runner,
        next_hints={
            "watch_tool": "scion_ops_watch_round_events",
            "events_tool": "scion_ops_round_events",
            "abort_tool": "scion_ops_abort_round",
        },
    )


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
    """Find local/remote branches and agent workspaces associated with a round id."""
    round_id = _clean_name(round_id, "round_id")
    root = _project_root(project_root) if project_root else _repo_root()
    branch_patterns = sorted({f"*{round_id}*", f"*{round_id.lower()}*"})
    branch_result = _run(["git", "branch", "--list", *branch_patterns], timeout=15, cwd=root)
    remote_url_result = _run(["git", "remote", "get-url", "origin"], timeout=10, cwd=root)
    remote = _preferred_remote_for_reads(remote_url_result["output"]) if remote_url_result["ok"] else "origin"
    remote_result = _run_git_authenticated(
        ["ls-remote", "--heads", remote, *branch_patterns],
        timeout=25,
        cwd=root,
    )
    remote_primary_result = remote_result
    remote_fallback_result: dict[str, Any] = {}
    if not remote_result["ok"] and remote_url_result["ok"]:
        https_remote = _github_https_remote(remote_url_result["output"])
        if https_remote and remote != https_remote:
            remote_fallback_result = _run_git_authenticated(
                ["ls-remote", "--heads", https_remote, *branch_patterns],
                timeout=25,
                cwd=root,
            )
            if remote_fallback_result["ok"]:
                remote_result = remote_fallback_result
    remote_branches: list[dict[str, str]] = []
    if remote_result["ok"]:
        for line in remote_result["output"].splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                remote_branches.append({
                    "sha": parts[0],
                    "branch": parts[1].removeprefix("refs/heads/"),
                })
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
        "remote_branches": remote_branches,
        "workspaces": workspaces,
        "prompts": prompts,
        "branch_result": _command_result(branch_result),
        "remote_url_result": _command_result(remote_url_result),
        "remote_primary_result": _command_result(remote_primary_result),
        "remote_fallback_result": _command_result(remote_fallback_result) if remote_fallback_result else {},
        "remote_branch_result": _command_result(remote_result),
    }


@mcp.tool()
def scion_ops_prepare_github_repo(repo_url: str, checkout_root: str = "") -> dict[str, Any]:
    """Prepare a visible local checkout for a GitHub repository URL."""
    try:
        ref = _github_repo_ref(repo_url)
    except ValueError as exc:
        return {
            "ok": False,
            "source": "github_repo_prepare",
            "error_kind": "unsupported_url",
            "error": str(exc),
            "repo_url": repo_url,
        }

    try:
        root = _configured_checkout_root(checkout_root)
    except ValueError as exc:
        return {
            "ok": False,
            "source": "github_repo_prepare",
            "error_kind": "workspace_mount",
            "error": str(exc),
            "repo_url": repo_url,
            "owner": ref.owner,
            "repo": ref.repo,
        }

    project_root = (root / ref.owner / ref.repo).resolve()
    host_project_root = _host_path_for_project_path(project_root)
    base_payload: dict[str, Any] = {
        "source": "github_repo_prepare",
        "repo_url": repo_url,
        "owner": ref.owner,
        "repo": ref.repo,
        "input_kind": ref.input_kind,
        "clone_url": ref.clone_url,
        "https_url": ref.https_url,
        "ssh_url": ref.ssh_url,
        "checkout_root": str(root),
        "host_checkout_root": str(_host_path_for_project_path(root)),
        "project_root": str(project_root),
        "host_project_root": str(host_project_root),
        "mcp_visible": project_root.exists(),
        "next": {
            "project_status_tool": "scion_ops_project_status",
            "start_round_tool": "scion_ops_start_round",
            "start_spec_round_tool": "scion_ops_start_spec_round",
        },
    }

    expected_remote = f"{ref.owner.lower()}/{ref.repo.lower()}"
    if project_root.exists():
        if not project_root.is_dir():
            return {
                **base_payload,
                "ok": False,
                "action": "blocked",
                "error_kind": "git_state",
                "error": f"checkout path exists but is not a directory: {project_root}",
                "mcp_visible": True,
            }
        revparse = _run(["git", "rev-parse", "--show-toplevel"], timeout=10, cwd=project_root)
        if not revparse["ok"]:
            return {
                **base_payload,
                "ok": False,
                "action": "blocked",
                "error_kind": "git_state",
                "error": f"checkout path exists but is not a git repository: {project_root}",
                "mcp_visible": True,
                "revparse_result": _command_result(revparse),
            }
        git_root = Path(revparse["output"].strip()).resolve()
        summary = _git_summary(git_root)
        actual_remote = _github_remote_key(summary["origin"])
        if actual_remote != expected_remote:
            return {
                **base_payload,
                **summary,
                "ok": False,
                "action": "blocked",
                "error_kind": "git_state",
                "error": "existing checkout origin does not match repo_url",
                "project_root": str(git_root),
                "host_project_root": str(_host_path_for_project_path(git_root)),
                "mcp_visible": True,
            }
        return {
            **base_payload,
            **summary,
            "ok": True,
            "action": "reused",
            "project_root": str(git_root),
            "host_project_root": str(_host_path_for_project_path(git_root)),
            "mcp_visible": True,
        }

    try:
        project_root.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            **base_payload,
            "ok": False,
            "action": "blocked",
            "error_kind": "workspace_mount",
            "error": f"failed to create checkout parent {project_root.parent}: {exc}",
        }

    clone = _run(["git", "clone", ref.clone_url, str(project_root)], timeout=180, cwd=project_root.parent)
    if not clone["ok"]:
        return {
            **base_payload,
            "ok": False,
            "action": "clone_failed",
            "error_kind": _clone_failure_kind(clone),
            "error": clone.get("error") or "git clone failed",
            "clone_result": {**clone, "source": "local_git", "error_kind": _clone_failure_kind(clone)},
            "mcp_visible": project_root.exists(),
        }

    summary = _git_summary(project_root)
    return {
        **base_payload,
        **summary,
        "ok": True,
        "action": "cloned",
        "clone_result": _command_result(clone),
        "mcp_visible": project_root.exists(),
    }


@mcp.tool()
def scion_ops_project_status(project_root: str) -> dict[str, Any]:
    """Resolve a target project path and show its git, grove, and Hub context."""
    root = _project_root(project_root)
    summary = _git_summary(root)
    grove_id = _read_text_file(root / ".scion" / "grove-id")
    hub = _hub_config(root).redacted()
    return {
        "ok": summary["status"]["ok"],
        "source": "local_git",
        "project_root": str(root),
        "host_project_root": str(_host_path_for_project_path(root)),
        "mcp_visible": root.exists(),
        "branch": summary["branch"],
        "origin": summary["origin"],
        "dirty": summary["dirty"],
        "grove_id": grove_id,
        "hub": hub,
        "status": summary["status"],
        "branch_result": summary["branch_result"],
        "origin_result": summary["origin_result"],
        "next": {
            "prepare_github_repo_tool": "scion_ops_prepare_github_repo",
            "bootstrap": "Run `task bootstrap -- <project_root>` from the scion-ops repo if grove_id is empty or preflight fails.",
            "start_round_tool": "scion_ops_start_round",
            "spec_status_tool": "scion_ops_spec_status",
            "start_spec_round_tool": "scion_ops_start_spec_round",
        },
    }


@mcp.tool()
def scion_ops_validate_spec_change(project_root: str, change: str) -> dict[str, Any]:
    """Validate an OpenSpec change artifact set in a target project."""
    root = _project_root(project_root)
    change = _clean_name(change, "change")
    command_result, payload = _validate_spec_change_result(root, change)
    return {
        **command_result,
        "source": "openspec_validator",
        "project_root": str(root),
        "change": change,
        "validation": payload,
    }


@mcp.tool()
def scion_ops_spec_status(project_root: str, change: str = "") -> dict[str, Any]:
    """List OpenSpec changes in a target project and optionally validate one change."""
    root = _project_root(project_root)
    changes_dir = root / "openspec" / "changes"
    archive_dir = changes_dir / "archive"
    changes: list[dict[str, Any]] = []
    if changes_dir.exists():
        for path in sorted(item for item in changes_dir.iterdir() if item.is_dir() and item.name != "archive"):
            changes.append({
                "change": path.name,
                "path": str(path.relative_to(root)),
                "has_proposal": (path / "proposal.md").exists(),
                "has_design": (path / "design.md").exists(),
                "has_tasks": (path / "tasks.md").exists(),
                "spec_file_count": len(list((path / "specs").glob("**/spec.md"))) if (path / "specs").exists() else 0,
            })
    archived_changes: list[dict[str, str]] = []
    if archive_dir.exists():
        for path in sorted(item for item in archive_dir.iterdir() if item.is_dir()):
            archived_changes.append({"archive": path.name, "path": str(path.relative_to(root))})
    validation: dict[str, Any] = {}
    validation_result: dict[str, Any] = {}
    openspec_status: dict[str, Any] = {}
    openspec_status_result: dict[str, Any] = {}
    ok = True
    if change:
        change = _clean_name(change, "change")
        validation_result, validation = _validate_spec_change_result(root, change)
        if validation.get("validator") == "openspec_cli":
            openspec_status_result, openspec_status = _openspec_status_result(root, change)
        ok = bool(validation.get("ok"))
    return {
        "ok": ok,
        "source": "local_git",
        "project_root": str(root),
        "changes_path": str(changes_dir.relative_to(root)),
        "changes": changes,
        "archive_path": str(archive_dir.relative_to(root)),
        "archived_changes": archived_changes,
        "change": change,
        "validation": validation,
        "validation_result": validation_result,
        "openspec_status": openspec_status,
        "openspec_status_result": openspec_status_result,
        "next": {
            "draft_spec_tool": "scion_ops_start_spec_round",
            "draft_spec_steward_tool": "scion_ops_start_spec_steward",
            "validate_tool": "scion_ops_validate_spec_change",
            "start_implementation_tool": "scion_ops_start_impl_round",
            "start_implementation_steward_tool": "scion_ops_start_implementation_steward",
            "archive_tool": "scion_ops_archive_spec_change",
            "watch_tool": "scion_ops_watch_round_events",
        },
    }


@mcp.tool()
def scion_ops_archive_spec_change(project_root: str, change: str, confirm: bool = False) -> dict[str, Any]:
    """Archive an accepted OpenSpec change and sync accepted specs. Requires confirm=true to apply."""
    root = _project_root(project_root)
    change = _clean_name(change, "change")
    command_result, payload = _archive_spec_change_result(root, change, confirm)
    return {
        **command_result,
        "source": "openspec_archive",
        "project_root": str(root),
        "change": change,
        "archive": payload,
        "next": {
            "apply": "Call again with confirm=true to apply the archive." if not confirm else "",
            "status_tool": "scion_ops_spec_status",
        },
    }


@mcp.tool()
def scion_ops_start_spec_round(
    goal: str,
    project_root: str,
    change: str = "",
    round_id: str = "",
    base_branch: str = "",
) -> dict[str, Any]:
    """Start an OpenSpec-only spec-building Scion round for a target project."""
    goal = goal.strip()
    if not goal:
        raise ValueError("goal is required")
    target_root = _project_root(project_root)
    env: dict[str, str] = _target_round_env(target_root)
    if change:
        env["SCION_OPS_SPEC_CHANGE"] = _clean_name(change, "change")
    if round_id:
        env["ROUND_ID"] = _clean_name(round_id, "round_id")
    if base_branch:
        env["BASE_BRANCH"] = _clean_name(base_branch, "base_branch")
    else:
        env["BASE_BRANCH"] = _default_base_branch(str(target_root))
    result = _run(["task", "spec:round", "--", goal], timeout=60, env=env)
    parsed_round_id = _parse_started_round_id(result["output"], env.get("ROUND_ID", ""))
    runner = f"round-{parsed_round_id.lower()}-spec-consensus" if parsed_round_id else ""
    return _start_round_response(
        result,
        target_root=target_root,
        parsed_round_id=parsed_round_id,
        runner=runner,
        next_hints={
            "status_tool": "scion_ops_round_status",
            "watch_tool": "scion_ops_watch_round_events",
            "events_tool": "scion_ops_round_events",
            "artifacts_tool": "scion_ops_round_artifacts",
            "abort_tool": "scion_ops_abort_round",
        },
    )


@mcp.tool()
def scion_ops_start_spec_steward(
    goal: str,
    project_root: str,
    change: str = "",
    session_id: str = "",
    base_branch: str = "",
) -> dict[str, Any]:
    """Start a Scion-native OpenSpec steward session for a target project."""
    goal = goal.strip()
    if not goal:
        raise ValueError("goal is required")
    target_root = _project_root(project_root)
    env: dict[str, str] = _target_round_env(target_root)
    if change:
        env["SCION_OPS_SPEC_CHANGE"] = _clean_name(change, "change")
    if session_id:
        env["SCION_OPS_SESSION_ID"] = _clean_name(session_id, "session_id")
    if base_branch:
        env["BASE_BRANCH"] = _clean_name(base_branch, "base_branch")
    else:
        env["BASE_BRANCH"] = _default_steward_base_branch(str(target_root))
    result = _run(["task", "spec:steward", "--", goal], timeout=60, env=env)
    parsed_session_id = _parse_started_round_id(result["output"], env.get("SCION_OPS_SESSION_ID", ""))
    steward = f"round-{parsed_session_id.lower()}-spec-steward" if parsed_session_id else ""
    return _start_steward_response(
        result,
        target_root=target_root,
        parsed_session_id=parsed_session_id,
        steward=steward,
        next_hints={
            "watch_tool": "scion_ops_watch_round_events",
            "events_tool": "scion_ops_round_events",
            "artifacts_tool": "scion_ops_round_artifacts",
            "validate_tool": "scion_ops_validate_steward_session",
            "abort_tool": "scion_ops_abort_round",
        },
    )


def _compact_round_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for event in events:
        item = event.get("agent") or event.get("message") or event.get("notification") or {}
        compact.append({
            "type": event.get("type"),
            "name": (
                item.get("name")
                or item.get("slug")
                or item.get("agentName")
                or item.get("agent")
                or item.get("sender")
                or ""
            ),
            "phase": item.get("phase") or "",
            "activity": item.get("activity") or "",
            "summary": item.get("taskSummary") or item.get("summary") or item.get("message") or item.get("msg") or "",
        })
    return compact


def _short_text(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _round_agent_inactive(agent: dict[str, Any]) -> bool:
    phase = str(agent.get("phase") or "").lower()
    activity = str(agent.get("activity") or "").lower()
    container_status = str(agent.get("containerStatus") or "").lower()
    return (
        phase in {"stopped", "deleted", "ended", "completed", "error", "failed"}
        or activity in {"completed", "limits_exceeded"}
        or "succeeded" in container_status
        or "completed" in container_status
        or "failed" in container_status
        or "error" in container_status
        or container_status == "stopped"
    )


def _round_agents_inactive(agents: list[dict[str, Any]]) -> bool:
    if not agents:
        return False
    return all(_round_agent_inactive(agent) for agent in agents)


def _has_placeholder_summary(agent: dict[str, Any]) -> bool:
    summary = str(agent.get("taskSummary") or agent.get("summary") or "")
    return any(token in summary.lower() for token in PLACEHOLDER_SUMMARY_TOKENS)


def _is_spec_consensus_agent(agent: dict[str, Any]) -> bool:
    name = str(agent.get("name") or agent.get("slug") or "")
    return agent.get("template") == "spec-consensus-runner" or name.endswith("-spec-consensus")


def _is_spec_child_agent(agent: dict[str, Any]) -> bool:
    name = str(agent.get("name") or agent.get("slug") or "")
    return (
        str(agent.get("template") or "") in SPEC_CHILD_TEMPLATES
        or any(name.endswith(f"-{suffix}") for suffix in (
            "spec-clarifier",
            "spec-explorer",
            "spec-author",
            "spec-ops-review",
            "spec-finalizer",
        ))
    )


def _spec_agents_for_phase(agents: list[dict[str, Any]], *, template: str, name_suffix: str) -> list[dict[str, Any]]:
    return [
        agent
        for agent in agents
        if str(agent.get("template") or "") == template
        or str(agent.get("name") or agent.get("slug") or "").endswith(name_suffix)
    ]


def _spec_phase_complete(agents: list[dict[str, Any]], *, template: str, name_suffix: str) -> bool:
    return any(
        _round_agent_inactive(agent)
        for agent in _spec_agents_for_phase(
            agents,
            template=template,
            name_suffix=name_suffix,
        )
    )


def _agent_health(agent: dict[str, Any]) -> str:
    phase = str(agent.get("phase") or "").lower()
    activity = str(agent.get("activity") or "").lower()
    status = json.dumps(agent.get("containerStatus") or "", default=str).lower()
    status_text = f"{phase} {activity} {status}"
    container_completed = "succeeded" in status or "completed" in status
    has_summary = bool(str(agent.get("taskSummary") or "").strip()) and not _has_placeholder_summary(agent)
    if container_completed:
        return "completed"
    if has_summary:
        if activity == "completed" or _round_agent_inactive(agent):
            return "completed"
    if any(token in status_text for token in ("limits_exceeded", "error", "failed", "crashloop", "imagepull", "backoff")):
        return "error"
    if _round_agent_inactive(agent):
        if phase in {"error", "failed"} and not has_summary:
            return "error"
        return "completed"
    if activity == "stalled" or "stalled" in status_text:
        if "running" in status:
            return "running"
        return "stalled"
    if phase in {"running", "started"} or activity in {"active", "running", "working"}:
        return "running"
    if phase in {"pending", "created", "queued", "scheduled", "starting"}:
        return "pending"
    return "unknown"


def _agent_progress_item(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": agent.get("name") or agent.get("slug") or "",
        "template": agent.get("template") or "",
        "phase": agent.get("phase") or "",
        "activity": agent.get("activity") or "",
        "health": _agent_health(agent),
        "summary": _short_text(agent.get("taskSummary")),
        "updated": agent.get("updated") or "",
    }


def _round_agent_progress(agents: list[dict[str, Any]]) -> dict[str, Any]:
    items = sorted(
        (_agent_progress_item(agent) for agent in agents),
        key=lambda item: (str(item.get("name") or ""), str(item.get("template") or "")),
    )
    active = [item for item in items if item["health"] in {"running", "pending", "unknown"}]
    completed = [item for item in items if item["health"] == "completed"]
    unhealthy = [item for item in items if item["health"] in {"error", "stalled"}]
    return {
        "agent_count": len(items),
        "health_counts": dict(Counter(str(item.get("health")) for item in items)),
        "active_agents": active,
        "completed_agents": completed,
        "unhealthy_agents": unhealthy,
    }


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _round_elapsed_seconds(agents: list[dict[str, Any]]) -> int | None:
    created = [_parse_timestamp(agent.get("created")) for agent in agents]
    timestamps = [item for item in created if item]
    if not timestamps:
        return None
    return max(0, int((datetime.now(timezone.utc) - min(timestamps)).total_seconds()))


def _latest_event_summaries(events: list[dict[str, Any]]) -> list[str]:
    summaries: list[str] = []
    for event in events:
        event_type = str(event.get("type") or "event")
        name = str(event.get("name") or "")
        phase = str(event.get("phase") or "")
        activity = str(event.get("activity") or "")
        summary = _short_text(event.get("summary"), limit=180)
        parts = [part for part in (phase, activity) if part]
        label = name or event_type
        suffix = f" ({', '.join(parts)})" if parts else ""
        detail = f": {summary}" if summary else ""
        summaries.append(_short_text(f"{event_type}: {label}{suffix}{detail}", limit=260))
    return summaries


def _agent_progress_line(agent: dict[str, Any]) -> str:
    name = str(agent.get("name") or agent.get("template") or "agent")
    health = str(agent.get("health") or "unknown")
    summary = _short_text(agent.get("summary"), limit=180)
    if health == "completed":
        status = "complete"
    elif health == "pending":
        status = "started"
    else:
        status = health
    detail = f" {summary}" if summary else ""
    return _short_text(f"agent {name} {status}{detail}", limit=260)


def _round_progress_lines(
    *,
    round_id: str,
    status: str,
    progress: dict[str, Any],
    validation_status: str = "",
    pr_ready_branch: str = "",
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    active = progress.get("active_agents", [])
    completed = progress.get("completed_agents", [])
    unhealthy = progress.get("unhealthy_agents", [])
    parts = [
        f"round {round_id} {status}",
        f"agents={progress.get('agent_count', 0)}",
        f"active={len(active)}",
        f"complete={len(completed)}",
        f"unhealthy={len(unhealthy)}",
    ]
    if validation_status:
        parts.append(f"validation={validation_status}")
    lines = [" ".join(parts)]
    lines.extend(_agent_progress_line(agent) for agent in unhealthy)
    lines.extend(_agent_progress_line(agent) for agent in active)
    lines.extend(_agent_progress_line(agent) for agent in completed)
    if pr_ready_branch:
        lines.append(f"round {round_id} complete branch {pr_ready_branch}")
    for warning in warnings or []:
        lines.append(_short_text(f"warning {warning}", limit=260))
    for blocker in blockers or []:
        lines.append(_short_text(f"blocker {blocker}", limit=260))
    return lines


def _snapshot_progress_lines(snapshot: dict[str, Any], round_id: str) -> list[str]:
    progress = _round_agent_progress(snapshot.get("agents", []))
    terminal = _round_terminal_status(snapshot)
    status = "completed" if terminal else "running" if progress["active_agents"] else "observed"
    return _round_progress_lines(round_id=round_id, status=status, progress=progress)


def _spec_round_artifact_state(
    *,
    target_root: Path,
    project_root: str,
    round_id: str,
    expected_branch: str,
    base_branch: str,
    change: str,
    validate: bool,
) -> dict[str, Any]:
    base_sha, _ = _remote_branch_sha(target_root, base_branch)
    artifacts = scion_ops_round_artifacts(round_id, project_root=project_root)
    final_branch = next(
        (
            item
            for item in artifacts.get("remote_branches", [])
            if item.get("branch") == expected_branch
        ),
        {},
    )
    branch_sha = str(final_branch.get("sha") or "")
    branch_changed = bool(branch_sha and branch_sha != base_sha)
    validation: dict[str, Any] = {}
    validation_status = "skipped" if not validate or not change else "pending"
    if validate and change and branch_changed:
        validation = _validate_remote_spec_change_result(target_root, _clean_name(change, "change"), expected_branch)
        validation_status = "passed" if validation.get("ok") else "failed"
    return {
        "artifacts": artifacts,
        "base_branch_sha": base_sha,
        "remote_branch_sha": branch_sha,
        "branch_changed": branch_changed,
        "validation": validation,
        "validation_status": validation_status,
    }


def _spec_round_next_args(
    *,
    project_root: str,
    goal: str,
    change: str,
    round_id: str,
    base_branch: str,
    cursor: str,
    watch_seconds: int,
    poll_interval_seconds: int,
    validate: bool,
) -> dict[str, Any]:
    return {
        "project_root": project_root,
        "goal": goal,
        "change": change,
        "round_id": round_id,
        "base_branch": base_branch,
        "cursor": cursor,
        "watch_seconds": watch_seconds,
        "poll_interval_seconds": poll_interval_seconds,
        "validate": validate,
        "wait_until_complete": False,
    }


def _spec_round_progress_response(
    *,
    target_root: Path,
    project_root: str,
    goal: str,
    change: str,
    round_id: str,
    monitor_round_id: str,
    base_branch: str,
    expected_branch: str,
    cursor: str,
    watch_seconds: int,
    poll_interval_seconds: int,
    validate: bool,
    started: dict[str, Any],
    last_watch: dict[str, Any],
    events_seen: list[dict[str, Any]],
    round_timed_out: bool = False,
) -> dict[str, Any]:
    try:
        agents, result = _list_agents(monitor_round_id, project_root)
    except HubAPIError as exc:
        return {
            "ok": False,
            "done": True,
            "status": "blocked",
            "source": "spec_round_runner",
            "stage": "monitor",
            "round_id": round_id,
            **_hub_error_payload(exc, "run_spec_round"),
        }
    summaries = [_agent_summary(agent) for agent in agents]
    progress = _round_agent_progress(summaries)
    consensus_agent = next((agent for agent in summaries if _is_spec_consensus_agent(agent)), {})
    child_agents = [agent for agent in summaries if _is_spec_child_agent(agent)]
    ops_review_agents = _spec_agents_for_phase(
        child_agents,
        template="spec-ops-reviewer",
        name_suffix="-spec-ops-review",
    )
    finalizer_agents = _spec_agents_for_phase(
        child_agents,
        template="spec-finalizer",
        name_suffix="-spec-finalizer",
    )
    ops_review_complete = _spec_phase_complete(
        child_agents,
        template="spec-ops-reviewer",
        name_suffix="-spec-ops-review",
    )
    finalizer_complete = _spec_phase_complete(
        child_agents,
        template="spec-finalizer",
        name_suffix="-spec-finalizer",
    )
    placeholder_agents = [agent for agent in summaries if _has_placeholder_summary(agent)]
    placeholder_summary = bool(placeholder_agents)
    terminal = last_watch.get("terminal") or _round_terminal_status({
        "agents": summaries,
        "messages": [],
        "notifications": [],
    }) or {}
    artifact_state = _spec_round_artifact_state(
        target_root=target_root,
        project_root=project_root,
        round_id=round_id,
        expected_branch=expected_branch,
        base_branch=base_branch,
        change=change,
        validate=validate,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    done = False
    status = "running" if summaries else "starting"
    round_finished = bool(terminal) or _round_agents_inactive(summaries)
    integration_branch_valid = (
        artifact_state["branch_changed"]
        and artifact_state["validation_status"] in {"passed", "skipped"}
    )
    protocol_complete = integration_branch_valid and ops_review_complete and finalizer_complete
    if protocol_complete:
        done = True
        status = "completed"
    elif round_finished and placeholder_summary and not child_agents:
        done = True
        status = "blocked"
        blockers.append("spec consensus runner exited with placeholder summary before spawning spec personas")
    elif progress["unhealthy_agents"]:
        done = True
        status = "blocked"
        blockers.append("one or more round agents are stalled or unhealthy")
    elif artifact_state["validation_status"] == "failed":
        if round_finished or round_timed_out:
            done = True
            status = "blocked"
            blockers.append("OpenSpec validation failed on the remote branch")
        else:
            status = "running_degraded"
            warnings.append("OpenSpec validation is currently failing on the remote branch")
    elif round_timed_out:
        done = True
        status = "timed_out"
        blockers.append("round did not finish before timeout")
    elif round_finished:
        done = True
        status = "blocked"
        if not artifact_state["remote_branch_sha"]:
            blockers.append(f"expected branch was not found on origin: {expected_branch}")
        elif not artifact_state["branch_changed"]:
            blockers.append(f"expected branch did not move from base SHA: {expected_branch}")
        elif integration_branch_valid:
            if not ops_review_agents:
                blockers.append("spec operations reviewer was not spawned")
            elif not ops_review_complete:
                blockers.append("spec operations reviewer did not complete")
            if not finalizer_agents:
                blockers.append("spec finalizer was not spawned")
            elif not finalizer_complete:
                blockers.append("spec finalizer did not complete")
        if terminal and not blockers:
            blockers.append("round reported terminal status before a valid spec branch was available")

    if integration_branch_valid and not protocol_complete and status in {"starting", "running"}:
        missing = []
        if not ops_review_complete:
            missing.append("spec operations review")
        if not finalizer_complete:
            missing.append("spec finalizer")
        if missing:
            warnings.append(f"integration branch validates; waiting for {', '.join(missing)}")

    if progress["unhealthy_agents"] and status in {"starting", "running"}:
        status = "running_degraded"

    overall_health = "ok"
    if status == "completed":
        overall_health = "complete"
    elif status in {"blocked", "timed_out"}:
        overall_health = "blocked"
    elif progress["unhealthy_agents"] or warnings:
        overall_health = "degraded"
    elif not summaries:
        overall_health = "starting"

    progress_lines = _round_progress_lines(
        round_id=round_id,
        status=status,
        progress=progress,
        validation_status=artifact_state["validation_status"],
        pr_ready_branch=expected_branch if status == "completed" else "",
        blockers=blockers,
        warnings=warnings,
    )
    artifacts = artifact_state["artifacts"] if done else {
        "source": artifact_state["artifacts"].get("source"),
        "project_root": artifact_state["artifacts"].get("project_root"),
        "remote_branches": artifact_state["artifacts"].get("remote_branches", []),
    }
    if done:
        next_payload = {
            "open_pr": f"Create a PR from {expected_branch} into the base branch." if status == "completed" else "",
            "abort_tool": "scion_ops_abort_round",
            "events_tool": "scion_ops_round_events",
        }
    else:
        next_payload = {
            "tool": "scion_ops_run_spec_round",
            "args": _spec_round_next_args(
                project_root=project_root,
                goal=goal,
                change=change,
                round_id=round_id,
                base_branch=base_branch,
                cursor=cursor,
                watch_seconds=watch_seconds,
                poll_interval_seconds=poll_interval_seconds,
                validate=validate,
            ),
            "message": "Call this tool again with next.args to continue monitoring.",
            "abort_tool": "scion_ops_abort_round",
        }

    return {
        "ok": status not in {"blocked", "timed_out"},
        "done": done,
        "status": status,
        "health": overall_health,
        "summary": progress_lines[0] if progress_lines else f"round {round_id} {status}",
        "progress_lines": progress_lines,
        "source": "spec_round_runner",
        "project_root": project_root,
        "round_id": round_id,
        "monitor_round_id": monitor_round_id,
        "change": change,
        "base_branch": base_branch,
        "elapsed_seconds": _round_elapsed_seconds(summaries),
        "expected_branch": expected_branch,
        "pr_ready_branch": expected_branch if status == "completed" else "",
        "remote_branch_sha": artifact_state["remote_branch_sha"],
        "base_branch_sha": artifact_state["base_branch_sha"],
        "branch_changed": artifact_state["branch_changed"],
        "validation_status": artifact_state["validation_status"],
        "validation": artifact_state["validation"],
        "protocol": {
            "integration_branch_valid": integration_branch_valid,
            "ops_review_agent_count": len(ops_review_agents),
            "ops_review_complete": ops_review_complete,
            "finalizer_agent_count": len(finalizer_agents),
            "finalizer_complete": finalizer_complete,
            "complete": protocol_complete,
        },
        "blockers": blockers,
        "warnings": warnings,
        "terminal": terminal,
        "placeholder_summary": placeholder_summary,
        "placeholder_agents": [_agent_progress_item(agent) for agent in placeholder_agents],
        "spawned_spec_agent_count": len(child_agents),
        "spawned_spec_agents": [_agent_progress_item(agent) for agent in child_agents],
        "consensus_agent": _agent_progress_item(consensus_agent) if consensus_agent else {},
        "progress": progress,
        "latest_events": events_seen[-20:],
        "latest_event_summaries": _latest_event_summaries(events_seen[-10:]),
        "cursor": cursor,
        "watch": {
            "changed": bool(last_watch.get("changed")),
            "timed_out": bool(last_watch.get("timed_out")),
            "agent_count": last_watch.get("agent_count", len(summaries)),
            "message_count": last_watch.get("message_count"),
            "notification_count": last_watch.get("notification_count"),
            "commands_ok": last_watch.get("commands_ok", result.get("commands_ok", {})),
        },
        "start": started,
        "artifacts": artifacts,
        "next": next_payload,
    }


@mcp.tool()
def scion_ops_run_spec_round(
    goal: str,
    project_root: str,
    change: str = "",
    round_id: str = "",
    base_branch: str = "",
    timeout_minutes: int = 45,
    watch_seconds: int = 30,
    poll_interval_seconds: int = 3,
    cursor: str = "",
    validate: bool = True,
    wait_until_complete: bool = False,
) -> dict[str, Any]:
    """Start or resume an OpenSpec-only spec round and return a progress snapshot.

    This is the compact default workflow for external agents: call it with
    project_root, goal, and optional change. By default it watches briefly and
    returns progress plus next.args for the next call. Set wait_until_complete
    for automation that should block until the PR-ready branch or a blocker.
    """
    goal = goal.strip()
    if change:
        change = _clean_name(change, "change")
    target_root = _project_root(project_root)
    project_root = str(target_root)
    base_branch = _clean_name(base_branch, "base_branch") if base_branch else _default_base_branch(project_root)
    watch_seconds = _clamp(watch_seconds, 1, 120)
    timeout_minutes = _clamp(timeout_minutes, 1, 240)
    poll_interval_seconds = _clamp(poll_interval_seconds, 1, 30)

    started: dict[str, Any] = {}
    if round_id:
        parsed_round_id = _clean_name(round_id, "round_id")
    else:
        if not goal:
            raise ValueError("goal is required when starting a spec round")
        started = scion_ops_start_spec_round(
            goal=goal,
            project_root=project_root,
            change=change,
            round_id=round_id,
            base_branch=base_branch,
        )
        parsed_round_id = str(started.get("round_id") or "")
        cursor = str(started.get("event_cursor") or cursor)
        if not started.get("ok") or not parsed_round_id:
            return {
                "ok": False,
                "done": True,
                "status": "blocked",
                "source": "spec_round_runner",
                "stage": "start",
                "start": started,
                "error": "failed to start spec round",
            }

    expected_branch = f"round-{parsed_round_id}-spec-integration"
    monitor_round_id = parsed_round_id.lower()
    if monitor_round_id != parsed_round_id and cursor:
        cursor = ""
    deadline = time.monotonic() + (timeout_minutes * 60)
    events_seen: list[dict[str, Any]] = []
    last_watch: dict[str, Any] = {}

    while True:
        remaining = max(1, int(deadline - time.monotonic())) if wait_until_complete else watch_seconds
        watch_window = min(watch_seconds, remaining)
        last_watch = scion_ops_watch_round_events(
            round_id=monitor_round_id,
            cursor=cursor,
            timeout_seconds=watch_window,
            poll_interval_seconds=poll_interval_seconds,
            include_existing=False,
            project_root=project_root,
        )
        cursor = str(last_watch.get("cursor") or cursor)
        events_seen.extend(_compact_round_events(last_watch.get("events", []))[-25:])
        if not last_watch.get("ok", True):
            return {
                "ok": False,
                "done": True,
                "status": "blocked",
                "source": "spec_round_runner",
                "stage": "monitor",
                "round_id": parsed_round_id,
                "monitor_round_id": monitor_round_id,
                "watch": last_watch,
                "blockers": [str(last_watch.get("error") or "failed to watch round events")],
            }
        response = _spec_round_progress_response(
            target_root=target_root,
            project_root=project_root,
            goal=goal,
            change=change,
            round_id=parsed_round_id,
            monitor_round_id=monitor_round_id,
            base_branch=base_branch,
            expected_branch=expected_branch,
            cursor=cursor,
            watch_seconds=watch_seconds,
            poll_interval_seconds=poll_interval_seconds,
            validate=validate,
            started=started,
            last_watch=last_watch,
            events_seen=events_seen,
            round_timed_out=wait_until_complete and time.monotonic() >= deadline,
        )
        if not wait_until_complete or response.get("done"):
            return response


def _start_impl_round(
    *,
    goal: str,
    project_root: str,
    change: str,
    round_id: str,
    max_minutes: int,
    max_review_rounds: int,
    base_branch: str,
    final_reviewer: str,
) -> dict[str, Any]:
    target_root = _project_root(project_root)
    change = _clean_name(change, "change")
    effective_base_branch = _clean_name(base_branch, "base_branch") if base_branch else _default_base_branch(str(target_root))
    validation_ref_branch = effective_base_branch if base_branch else ""
    validation_result, validation = _validate_spec_change_for_start(target_root, change, validation_ref_branch)
    if not validation.get("ok"):
        return {
            **validation_result,
            "project_root": str(target_root),
            "change": change,
            "base_branch": effective_base_branch,
            "validation": validation,
            "next": {
                "draft_spec_tool": "scion_ops_start_spec_round",
                "spec_status_tool": "scion_ops_spec_status",
            },
        }
    env: dict[str, str] = {
        **_target_round_env(target_root),
        "MAX_MINUTES": str(_clamp(max_minutes, 1, 240)),
        "MAX_REVIEW_ROUNDS": str(_clamp(max_review_rounds, 1, 10)),
    }
    if round_id:
        env["ROUND_ID"] = _clean_name(round_id, "round_id")
    env["BASE_BRANCH"] = effective_base_branch
    if final_reviewer:
        final_reviewer = final_reviewer.strip().lower()
        if final_reviewer not in {"gemini", "codex"}:
            raise ValueError("final_reviewer must be 'gemini' or 'codex'")
        env["FINAL_REVIEWER"] = final_reviewer
    args = ["task", "spec:implement", "--", "--change", change]
    if goal.strip():
        args.append(goal.strip())
    result = _run(args, timeout=60, env=env)
    parsed_round_id = _parse_started_round_id(result["output"], env.get("ROUND_ID", ""))
    runner = f"round-{parsed_round_id.lower()}-consensus" if parsed_round_id else ""
    response = _start_round_response(
        result,
        target_root=target_root,
        parsed_round_id=parsed_round_id,
        runner=runner,
        next_hints={
            "status_tool": "scion_ops_round_status",
            "watch_tool": "scion_ops_watch_round_events",
            "events_tool": "scion_ops_round_events",
            "artifacts_tool": "scion_ops_round_artifacts",
            "abort_tool": "scion_ops_abort_round",
        },
    )
    return {**response, "change": change, "base_branch": effective_base_branch, "validation": validation}


@mcp.tool()
def scion_ops_start_impl_round(
    project_root: str,
    change: str,
    goal: str = "",
    round_id: str = "",
    max_minutes: int = 90,
    max_review_rounds: int = 3,
    base_branch: str = "",
    final_reviewer: str = "",
) -> dict[str, Any]:
    """Start an implementation round from an approved OpenSpec change."""
    return _start_impl_round(
        goal=goal,
        project_root=project_root,
        change=change,
        round_id=round_id,
        max_minutes=max_minutes,
        max_review_rounds=max_review_rounds,
        base_branch=base_branch,
        final_reviewer=final_reviewer,
    )


@mcp.tool()
def scion_ops_start_implementation_round(
    project_root: str,
    change: str,
    goal: str = "",
    round_id: str = "",
    max_minutes: int = 90,
    max_review_rounds: int = 3,
    base_branch: str = "",
    final_reviewer: str = "",
) -> dict[str, Any]:
    """Alias for scion_ops_start_impl_round."""
    return _start_impl_round(
        goal=goal,
        project_root=project_root,
        change=change,
        round_id=round_id,
        max_minutes=max_minutes,
        max_review_rounds=max_review_rounds,
        base_branch=base_branch,
        final_reviewer=final_reviewer,
    )


@mcp.tool()
def scion_ops_start_implementation_steward(
    project_root: str,
    change: str,
    goal: str = "",
    session_id: str = "",
    base_branch: str = "",
) -> dict[str, Any]:
    """Start a Scion-native implementation steward session from an approved OpenSpec change."""
    target_root = _project_root(project_root)
    change = _clean_name(change, "change")
    effective_base_branch = _clean_name(base_branch, "base_branch") if base_branch else _default_steward_base_branch(str(target_root))
    validation_ref_branch = effective_base_branch if base_branch else ""
    validation_result, validation = _validate_spec_change_for_start(target_root, change, validation_ref_branch)
    if not validation.get("ok"):
        return {
            **validation_result,
            "project_root": str(target_root),
            "change": change,
            "base_branch": effective_base_branch,
            "validation": validation,
            "next": {
                "draft_spec_steward_tool": "scion_ops_start_spec_steward",
                "spec_status_tool": "scion_ops_spec_status",
            },
        }

    env: dict[str, str] = _target_round_env(target_root)
    if session_id:
        env["SCION_OPS_SESSION_ID"] = _clean_name(session_id, "session_id")
    env["BASE_BRANCH"] = effective_base_branch

    args = ["task", "spec:implement:steward", "--", "--change", change]
    if goal.strip():
        args.append(goal.strip())
    result = _run(args, timeout=60, env=env)
    parsed_session_id = _parse_started_round_id(result["output"], env.get("SCION_OPS_SESSION_ID", ""))
    steward = f"round-{parsed_session_id.lower()}-implementation-steward" if parsed_session_id else ""
    response = _start_steward_response(
        result,
        target_root=target_root,
        parsed_session_id=parsed_session_id,
        steward=steward,
        next_hints={
            "watch_tool": "scion_ops_watch_round_events",
            "events_tool": "scion_ops_round_events",
            "artifacts_tool": "scion_ops_round_artifacts",
            "validate_tool": "scion_ops_validate_steward_session",
            "abort_tool": "scion_ops_abort_round",
        },
    )
    return {**response, "change": change, "base_branch": effective_base_branch, "validation": validation}


@mcp.tool()
def scion_ops_validate_steward_session(
    project_root: str,
    session_id: str,
    kind: str,
    change: str = "",
    branch: str = "",
    state_branch: str = "",
    base_branch: str = "",
    require_ready: bool = True,
) -> dict[str, Any]:
    """Validate durable state for a Scion OpenSpec steward session."""
    target_root = _project_root(project_root)
    session_id = _clean_name(session_id, "session_id")
    kind = kind.strip().lower()
    if kind not in {"spec", "implementation"}:
        raise ValueError("kind must be 'spec' or 'implementation'")

    args = [
        "python3",
        str(_repo_root() / "scripts" / "validate-steward-session.py"),
        "--project-root",
        str(target_root),
        "--session-id",
        session_id,
        "--kind",
        kind,
        "--json",
    ]
    if change:
        args.extend(["--change", _clean_name(change, "change")])
    if branch:
        args.extend(["--branch", _clean_name(branch, "branch")])
    if state_branch:
        args.extend(["--state-branch", _clean_name(state_branch, "state_branch")])
    if base_branch:
        args.extend(["--base-branch", _clean_name(base_branch, "base_branch")])
    if require_ready:
        args.append("--require-ready")

    result = _run(args, timeout=30, cwd=_repo_root())
    payload = _parse_json_result(result)
    if payload:
        return {**_command_result(result), "source": "steward_session_validator", "validation": payload}
    return {
        **_command_result(result),
        "source": "steward_session_validator",
        "project_root": str(target_root),
        "session_id": session_id,
        "kind": kind,
        "error": "validator did not return JSON",
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
        f"Use the scion-ops MCP tools to monitor round `{round_id}`. For new "
        "spec rounds, prefer scion_ops_run_spec_round so start, progress "
        "snapshots, artifact collection, and validation use one repeatable "
        "tool. Re-call it with returned next.args until done=true. For existing "
        "rounds, start with "
        "scion_ops_round_events(include_existing=true), then call "
        "scion_ops_watch_round_events with the returned cursor until it reports "
        "a terminal status or blocker. Use scion_ops_look only when an event "
        "needs transcript context. Summarize phase, blockers, final branch, "
        "verification, and any cleanup issues."
    )


def main() -> None:
    transport = os.environ.get("SCION_OPS_MCP_TRANSPORT", "streamable-http").strip().lower()
    try:
        if transport in {"http", "streamable-http", "streamable_http"}:
            mcp.run(transport="streamable-http")
            return
        raise SystemExit(f"unsupported SCION_OPS_MCP_TRANSPORT={transport!r}")
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
