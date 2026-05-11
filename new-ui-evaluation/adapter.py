#!/usr/bin/env python3
"""Read-only adapter for the scion-ops new UI evaluation preview."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = ROOT / "fixtures" / "preview-fixtures.json"
DEFAULT_STATIC_ROOT = ROOT / "dist"

API_ROUTES = {
    "/api/fixtures": lambda fixtures: fixtures,
    "/api/overview": lambda fixtures: fixtures["overview"],
    "/api/rounds": lambda fixtures: fixtures["rounds"],
    "/api/inbox": lambda fixtures: fixtures["inbox"],
    "/api/runtime": lambda fixtures: fixtures["runtime"],
    "/api/diagnostics": lambda fixtures: fixtures["diagnostics"],
}

READ_ONLY_MESSAGE = {
    "error": "new-ui-evaluation is read-only",
    "detail": "Only local preview fixtures are served. Live reads and mutations are disabled.",
}


def load_fixtures(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        fixtures = json.load(handle)
    validate_fixture_safety(fixtures)
    return fixtures


def validate_fixture_safety(fixtures: dict[str, Any]) -> None:
    runtime = fixtures.get("runtime", {}).get("previewService", {})
    if fixtures.get("mocked") is not True:
        raise ValueError("preview fixtures must be marked mocked=true")
    if runtime.get("fixtureOnly") is not True:
        raise ValueError("preview service fixtureOnly safeguard must be true")
    if runtime.get("liveReadsAllowed") is not False:
        raise ValueError("preview service liveReadsAllowed safeguard must be false")
    if runtime.get("mutationsAllowed") is not False:
        raise ValueError("preview service mutationsAllowed safeguard must be false")


class PreviewHandler(BaseHTTPRequestHandler):
    server_version = "ScionOpsNewUiEvaluation/0.1"

    def do_GET(self) -> None:
        self._handle_read()

    def do_HEAD(self) -> None:
        self._handle_read(head_only=True)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_POST(self) -> None:
        self._reject_mutation()

    def do_PUT(self) -> None:
        self._reject_mutation()

    def do_PATCH(self) -> None:
        self._reject_mutation()

    def do_DELETE(self) -> None:
        self._reject_mutation()

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    @property
    def fixtures(self) -> dict[str, Any]:
        return self.server.fixtures  # type: ignore[attr-defined]

    @property
    def static_root(self) -> Path:
        return self.server.static_root  # type: ignore[attr-defined]

    def _handle_read(self, head_only: bool = False) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self._json({"status": "ok", "mocked": True, "liveReadsAllowed": False, "mutationsAllowed": False}, head_only=head_only)
            return
        if path in API_ROUTES:
            self._json(API_ROUTES[path](self.fixtures), head_only=head_only)
            return
        if path.startswith("/api/rounds/"):
            round_id = unquote(path.removeprefix("/api/rounds/"))
            detail = self.fixtures.get("roundDetails", {}).get(round_id)
            if detail is None:
                self._json({"error": "round detail fixture not found", "roundId": round_id}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
                return
            self._json(detail, head_only=head_only)
            return
        if path.startswith("/api/"):
            self._json({"error": "unknown preview fixture endpoint"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
            return
        self._static(path, head_only=head_only)

    def _static(self, request_path: str, head_only: bool = False) -> None:
        relative = request_path.lstrip("/") or "index.html"
        candidate = (self.static_root / relative).resolve()
        static_root = self.static_root.resolve()
        if static_root not in candidate.parents and candidate != static_root:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists():
            candidate = static_root / "index.html"
        if not candidate.exists():
            self._json({"error": "static build not found", "hint": "run npm run build in new-ui-evaluation"}, status=HTTPStatus.NOT_FOUND, head_only=head_only)
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK, head_only: bool = False) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _reject_mutation(self) -> None:
        self._json(READ_ONLY_MESSAGE, status=HTTPStatus.METHOD_NOT_ALLOWED)


def build_server(host: str, port: int, static_root: Path, fixture_path: Path) -> ThreadingHTTPServer:
    fixtures = load_fixtures(fixture_path)
    server = ThreadingHTTPServer((host, port), PreviewHandler)
    server.fixtures = fixtures  # type: ignore[attr-defined]
    server.static_root = static_root  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the read-only scion-ops new UI evaluation preview.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8091, type=int)
    parser.add_argument("--static-root", default=str(DEFAULT_STATIC_ROOT))
    parser.add_argument("--fixture-path", default=str(FIXTURE_PATH))
    args = parser.parse_args()

    server = build_server(args.host, args.port, Path(args.static_root), Path(args.fixture_path))
    print(f"serving new-ui-evaluation on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
