from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from adapter import EVENT_SCHEMA_VERSION, LIVE_SCHEMA_VERSION, LiveSourceAggregator, build_server, load_fixtures


ROOT = Path(__file__).resolve().parents[1]


def request_json(url: str, method: str = "GET"):
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def request_text(url: str):
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.headers.get("Content-Type"), response.read().decode("utf-8")


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class AdapterTests(unittest.TestCase):
    def test_live_snapshot_contract_includes_sources_and_view_payloads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            write_json(
                project_root / ".scion-ops" / "sessions" / "20260511t154050z-44ce" / "findings" / "handoff.json",
                {
                    "agent": "round-20260511t154050z-44ce-impl-codex",
                    "status": "completed",
                    "branch": "round-20260511t154050z-44ce-impl-codex",
                    "head_sha": "abc123",
                    "changed_files": ["new-ui-evaluation/adapter.py"],
                    "tasks_completed": ["Define live snapshot schema"],
                    "tests_run": ["python3 -m unittest discover -s tests"],
                    "blockers": [],
                    "summary": "Implemented live adapter contract.",
                },
            )
            (project_root / "openspec" / "changes" / "wire-new-ui-1").mkdir(parents=True)
            (project_root / "openspec" / "changes" / "wire-new-ui-1" / "tasks.md").write_text("- [x] Define live snapshot schema\n- [ ] UI work\n", encoding="utf-8")
            (project_root / "mcp_servers").mkdir()
            (project_root / "mcp_servers" / "scion_ops.py").write_text("# test mcp server\n", encoding="utf-8")

            commands: list[list[str]] = []

            def fake_command(args, cwd):
                commands.append(args)
                if args[:2] == ["git", "rev-parse"] and "--abbrev-ref" in args:
                    return True, "round-20260511t154050z-44ce-impl-codex"
                if args[:2] == ["git", "rev-parse"]:
                    return True, "abc123"
                if args[:3] == ["kubectl", "get", "pods"]:
                    return False, "cluster unavailable in test"
                return False, "unexpected command"

            with (
                patch("adapter.run_read_only_command", side_effect=fake_command),
                patch.object(LiveSourceAggregator, "_read_hub_operational", return_value={"ok": False, "status": "degraded", "fallback": True, "error": "Hub unavailable"}),
                patch.object(LiveSourceAggregator, "_read_mcp_operational", return_value={"ok": False, "status": "degraded", "fallback": True, "error": "MCP unavailable"}),
            ):
                snapshot = LiveSourceAggregator(project_root).build_snapshot()

        self.assertEqual(snapshot["schemaVersion"], LIVE_SCHEMA_VERSION)
        self.assertEqual(snapshot["sourceMode"], "live")
        self.assertIs(snapshot["fixtureBacked"], False)
        self.assertEqual(snapshot["connection"]["transport"], "sse")
        self.assertEqual(snapshot["runtime"]["liveService"]["liveReadsAllowed"], True)
        self.assertEqual(snapshot["runtime"]["liveService"]["mutationsAllowed"], False)
        self.assertEqual(snapshot["rounds"][0]["id"], "20260511t154050z-44ce")
        self.assertEqual(snapshot["rounds"][0]["branchEvidence"]["headSha"], "abc123")
        self.assertIn("raw-runtime", snapshot["diagnostics"]["rawPayloads"])
        self.assertIn("raw-hub", snapshot["diagnostics"]["rawPayloads"])
        self.assertTrue(next(source for source in snapshot["sourceHealth"] if source["name"] == "Hub")["fallback"])
        self.assertEqual({command[0] for command in commands}, {"git", "kubectl"})
        self.assertTrue(all(command[:2] == ["git", "rev-parse"] or command[:3] == ["kubectl", "get", "pods"] for command in commands))

    def test_live_snapshot_uses_hub_and_mcp_operational_reads_when_available(self):
        hub_read = {
            "ok": True,
            "agent_count": 1,
            "hub": {"endpoint": "http://hub.example", "grove_id": "grove-1"},
            "agents": [
                {
                    "name": "round-20260511t154050z-44ce-implementation-steward",
                    "phase": "running",
                    "activity": "idle",
                    "taskSummary": "Implement live adapter repair",
                    "updated": "2026-05-11T15:50:00Z",
                }
            ],
        }
        mcp_read = {"ok": True, "status": "healthy", "httpStatus": 405, "url": "http://mcp.example/mcp"}

        def fake_command(args, cwd):
            if args[:2] == ["git", "rev-parse"] and "--abbrev-ref" in args:
                return True, "round-20260511t154050z-44ce-repair-live-codex"
            if args[:2] == ["git", "rev-parse"]:
                return True, "def456"
            if args[:3] == ["kubectl", "get", "pods"]:
                return True, "pods"
            return False, "unexpected command"

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            (project_root / "openspec" / "changes" / "wire-new-ui-1").mkdir(parents=True)
            with (
                patch("adapter.run_read_only_command", side_effect=fake_command),
                patch.object(LiveSourceAggregator, "_read_hub_operational", return_value=hub_read),
                patch.object(LiveSourceAggregator, "_read_mcp_operational", return_value=mcp_read),
            ):
                snapshot = LiveSourceAggregator(project_root).build_snapshot()

        self.assertEqual(snapshot["rounds"][0]["id"], "20260511t154050z-44ce")
        hub_source = next(source for source in snapshot["sourceHealth"] if source["name"] == "Hub")
        mcp_source = next(source for source in snapshot["sourceHealth"] if source["name"] == "MCP")
        self.assertEqual(hub_source["status"], "healthy")
        self.assertIs(hub_source["fallback"], False)
        self.assertIn("Hub API read succeeded", hub_source["detail"])
        self.assertEqual(mcp_source["status"], "healthy")
        self.assertIn("operational endpoint read succeeded", mcp_source["detail"])

    def test_live_adapter_serves_snapshot_views_events_and_rejects_mutations(self):
        server = build_server("127.0.0.1", 0, ROOT / "dist", ROOT / "fixtures" / "local-fixtures.json", mode="live", project_root=ROOT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            status, health = request_json(f"{base_url}/healthz")
            self.assertEqual(status, 200)
            self.assertEqual(health["service"], "scion-ops-web-app")
            self.assertEqual(health["sourceMode"], "live")
            self.assertEqual(health["liveReadsAllowed"], True)
            self.assertEqual(health["mutationsAllowed"], False)

            status, snapshot = request_json(f"{base_url}/api/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(snapshot["schemaVersion"], LIVE_SCHEMA_VERSION)
            self.assertEqual(snapshot["sourceMode"], "live")
            self.assertEqual(snapshot["runtime"]["liveService"]["streamPath"], "/api/events")

            status, overview = request_json(f"{base_url}/api/overview")
            self.assertEqual(status, 200)
            self.assertIs(overview["fixtureBacked"], False)
            self.assertIn("sourceReadiness", overview)

            status, content_type, body = request_text(f"{base_url}/api/events?once=1")
            self.assertEqual(status, 200)
            self.assertIn("text/event-stream", content_type)
            self.assertIn(f'"schemaVersion": "{EVENT_SCHEMA_VERSION}"', body)
            self.assertIn("event: heartbeat", body)

            status, rejection = request_json(f"{base_url}/api/snapshot", method="DELETE")
            self.assertEqual(status, 405)
            self.assertEqual(rejection["error"], "scion-ops-web-app is read-only")
        finally:
            server.shutdown()
            server.server_close()

    def test_sse_stream_emits_typed_incremental_events_for_source_changes(self):
        first = {
            "schemaVersion": LIVE_SCHEMA_VERSION,
            "sourceMode": "live",
            "generatedAt": "2026-05-11T15:40:00Z",
            "cursor": "live:first",
            "sourceHealth": [
                {"name": "Hub", "status": "healthy", "detail": "ok", "error": None, "stale": False, "fallback": False},
                {"name": "MCP", "status": "healthy", "detail": "ok", "error": None, "stale": False, "fallback": False},
            ],
            "sources": [],
            "overview": {},
            "rounds": [
                {"id": "20260511t154050z-44ce", "state": "active", "updatedAt": "2026-05-11T15:40:00Z", "latestEvent": "started", "blockers": [], "branchEvidence": {"headSha": "a"}, "source": "Hub"}
            ],
            "roundDetails": {
                "20260511t154050z-44ce": {
                    "timeline": [{"id": "entry-1", "timestamp": "2026-05-11T15:40:00Z", "summary": "started"}]
                }
            },
            "inbox": [],
            "runtime": {},
            "diagnostics": {"sourceErrors": []},
        }
        second = {
            **first,
            "generatedAt": "2026-05-11T15:40:01Z",
            "cursor": "live:second",
            "sourceHealth": [
                {"name": "Hub", "status": "degraded", "detail": "Hub API unavailable; using fallback", "error": "Hub down", "stale": True, "fallback": True},
                {"name": "MCP", "status": "healthy", "detail": "ok", "error": None, "stale": False, "fallback": False},
            ],
            "rounds": [
                {"id": "20260511t154050z-44ce", "state": "blocked", "updatedAt": "2026-05-11T15:40:01Z", "latestEvent": "blocked", "blockers": ["review"], "branchEvidence": {"headSha": "b"}, "source": "Hub"}
            ],
            "roundDetails": {
                "20260511t154050z-44ce": {
                    "timeline": [
                        {"id": "entry-1", "timestamp": "2026-05-11T15:40:00Z", "summary": "started"},
                        {"id": "entry-2", "timestamp": "2026-05-11T15:40:01Z", "summary": "blocked"},
                    ]
                }
            },
            "inbox": [
                {"id": "inbox-1", "source": "Hub", "timestamp": "2026-05-11T15:40:01Z", "context": "review", "readOnly": True}
            ],
            "diagnostics": {"sourceErrors": [{"source": "Hub", "message": "Hub down"}]},
        }

        class ChangingAggregator:
            def __init__(self):
                self.calls = 0

            def build_snapshot(self):
                self.calls += 1
                return first if self.calls == 1 else second

        server = build_server("127.0.0.1", 0, ROOT / "dist", ROOT / "fixtures" / "local-fixtures.json", mode="live", project_root=ROOT)
        server.aggregator = ChangingAggregator()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            status, content_type, body = request_text(f"{base_url}/api/events?seconds=1&interval=0.1")
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", content_type)
        for event_type in ("round_updated", "timeline_entry", "inbox_item", "source_status", "stale", "fallback", "runtime_health", "diagnostic"):
            self.assertIn(f"event: {event_type}", body)
        self.assertNotIn("snapshot.updated", body)

    def test_sse_reconnect_replays_missed_events_from_known_cursor_or_replaces_snapshot(self):
        first = {
            "schemaVersion": LIVE_SCHEMA_VERSION,
            "sourceMode": "live",
            "generatedAt": "2026-05-11T15:40:00Z",
            "cursor": "live:first",
            "sourceHealth": [
                {"name": "Hub", "status": "healthy", "detail": "ok", "error": None, "stale": False, "fallback": False},
            ],
            "sources": [],
            "overview": {},
            "rounds": [
                {"id": "20260511t154050z-44ce", "state": "active", "updatedAt": "2026-05-11T15:40:00Z", "latestEvent": "started", "blockers": [], "branchEvidence": {"headSha": "a"}, "source": "Hub"}
            ],
            "roundDetails": {
                "20260511t154050z-44ce": {
                    "timeline": [{"id": "entry-1", "timestamp": "2026-05-11T15:40:00Z", "summary": "started"}]
                }
            },
            "inbox": [],
            "runtime": {},
            "diagnostics": {"sourceErrors": []},
        }
        second = {
            **first,
            "generatedAt": "2026-05-11T15:40:01Z",
            "cursor": "live:second",
            "sourceHealth": [
                {"name": "Hub", "status": "degraded", "detail": "Hub API unavailable; using fallback", "error": "Hub down", "stale": True, "fallback": True},
            ],
            "rounds": [
                {"id": "20260511t154050z-44ce", "state": "blocked", "updatedAt": "2026-05-11T15:40:01Z", "latestEvent": "blocked", "blockers": ["review"], "branchEvidence": {"headSha": "b"}, "source": "Hub"}
            ],
            "roundDetails": {
                "20260511t154050z-44ce": {
                    "timeline": [
                        {"id": "entry-1", "timestamp": "2026-05-11T15:40:00Z", "summary": "started"},
                        {"id": "entry-2", "timestamp": "2026-05-11T15:40:01Z", "summary": "blocked"},
                    ]
                }
            },
            "inbox": [
                {"id": "inbox-1", "source": "Hub", "timestamp": "2026-05-11T15:40:01Z", "context": "review", "readOnly": True}
            ],
            "diagnostics": {"sourceErrors": [{"source": "Hub", "message": "Hub down"}]},
        }

        class ReconnectAggregator:
            def __init__(self):
                self.calls = 0

            def build_snapshot(self):
                self.calls += 1
                return first if self.calls == 1 else second

        server = build_server("127.0.0.1", 0, ROOT / "dist", ROOT / "fixtures" / "local-fixtures.json", mode="live", project_root=ROOT)
        server.aggregator = ReconnectAggregator()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            status, _, initial_body = request_text(f"{base_url}/api/events?once=1")
            self.assertEqual(status, 200)
            self.assertIn("event: snapshot_ready", initial_body)
            self.assertIn('"snapshotCursor": "live:first"', initial_body)

            status, _, replay_body = request_text(f"{base_url}/api/events?once=1&cursor=live:first")
            self.assertEqual(status, 200)

            status, _, replacement_body = request_text(f"{base_url}/api/events?once=1&cursor=live:missing")
            self.assertEqual(status, 200)
        finally:
            server.shutdown()
            server.server_close()

        for event_type in ("round_updated", "timeline_entry", "inbox_item", "source_status", "stale", "fallback", "runtime_health", "diagnostic"):
            self.assertIn(f"event: {event_type}", replay_body)
        self.assertNotIn('"status": "snapshot_recovery"', replay_body)
        self.assertIn("event: snapshot_ready", replacement_body)
        self.assertIn('"status": "snapshot_recovery"', replacement_body)
        self.assertIn('"requestedCursor": "live:missing"', replacement_body)
        self.assertIn('"snapshotCursor": "live:second"', replacement_body)
        self.assertIn('"rounds"', replacement_body)

    def test_fixture_contract_includes_required_operator_shapes(self):
        fixtures = load_fixtures(ROOT / "fixtures" / "local-fixtures.json")

        self.assertEqual(fixtures["schemaVersion"], "scion-ops-web-app.fixture.v1")
        self.assertIs(fixtures["fixtureBacked"], True)
        self.assertIs(fixtures["overview"]["fixtureBacked"], True)
        self.assertTrue(fixtures["overview"]["attentionTarget"]["reason"])
        self.assertGreaterEqual(
            {round_item["state"] for round_item in fixtures["rounds"]},
            {"blocked", "active", "failed", "completed", "empty"},
        )
        self.assertIs(fixtures["inbox"][0]["readOnly"], True)
        self.assertEqual(
            fixtures["runtime"]["liveService"],
            {
                "name": "scion-ops-web-app",
                "port": 8091,
                "healthPath": "/healthz",
                "fixtureOnly": True,
                "liveReadsAllowed": False,
                "mutationsAllowed": False,
            },
        )
        self.assertIn("raw-runtime", fixtures["diagnostics"]["rawPayloads"])

    def test_fixture_fallback_is_explicit_and_rejects_mutations(self):
        server = build_server("127.0.0.1", 0, ROOT / "dist", ROOT / "fixtures" / "local-fixtures.json", mode="fixture")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            status, health = request_json(f"{base_url}/healthz")
            self.assertEqual(status, 200)
            self.assertEqual(
                health,
                {
                    "status": "ok",
                    "service": "scion-ops-web-app",
                    "schemaVersion": "scion-ops-web-app.fixture.v1",
                    "sourceMode": "fixture",
                    "fixtureBacked": True,
                    "liveReadsAllowed": False,
                    "mutationsAllowed": False,
                    "streamPath": None,
                    "generatedAt": health["generatedAt"],
                },
            )

            status, overview = request_json(f"{base_url}/api/overview")
            self.assertEqual(status, 200)
            self.assertIs(overview["fixtureBacked"], True)
            self.assertEqual(overview["counts"]["blockedRounds"], 2)

            status, rounds = request_json(f"{base_url}/api/rounds")
            self.assertEqual(status, 200)
            self.assertTrue(any(round_item["id"] == "round-empty-fixture" for round_item in rounds))

            status, detail = request_json(f"{base_url}/api/rounds/round-20260511t091500z-117a")
            self.assertEqual(status, 200)
            self.assertEqual(detail["rawPayloadRef"], "raw-round-blocked")

            status, rejection = request_json(f"{base_url}/api/rounds", method="POST")
            self.assertEqual(status, 405)
            self.assertEqual(rejection["error"], "scion-ops-web-app is read-only")
        finally:
            server.shutdown()
            server.server_close()

    def test_static_assets_are_served_with_spa_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            static_root = Path(temp_dir) / "dist"
            static_root.mkdir()
            (static_root / "index.html").write_text("<main>live operator console</main>", encoding="utf-8")
            (static_root / "asset.txt").write_text("asset-body", encoding="utf-8")
            server = build_server("127.0.0.1", 0, static_root, ROOT / "fixtures" / "local-fixtures.json", mode="live", project_root=ROOT)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                status, content_type, body = request_text(f"{base_url}/asset.txt")
                self.assertEqual(status, 200)
                self.assertIn("text/plain", content_type)
                self.assertEqual(body, "asset-body")

                status, content_type, body = request_text(f"{base_url}/rounds/anything")
                self.assertEqual(status, 200)
                self.assertIn("text/html", content_type)
                self.assertIn("live operator console", body)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
