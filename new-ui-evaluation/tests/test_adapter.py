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

            with patch("adapter.run_read_only_command", side_effect=fake_command):
                snapshot = LiveSourceAggregator(project_root).build_snapshot()

        self.assertEqual(snapshot["schemaVersion"], LIVE_SCHEMA_VERSION)
        self.assertEqual(snapshot["sourceMode"], "live")
        self.assertIs(snapshot["mocked"], False)
        self.assertEqual(snapshot["connection"]["transport"], "sse")
        self.assertEqual(snapshot["runtime"]["previewService"]["liveReadsAllowed"], True)
        self.assertEqual(snapshot["runtime"]["previewService"]["mutationsAllowed"], False)
        self.assertEqual(snapshot["rounds"][0]["id"], "20260511t154050z-44ce")
        self.assertEqual(snapshot["rounds"][0]["branchEvidence"]["headSha"], "abc123")
        self.assertIn("raw-runtime", snapshot["diagnostics"]["rawPayloads"])
        self.assertEqual({command[0] for command in commands}, {"git", "kubectl"})
        self.assertTrue(all(command[:2] == ["git", "rev-parse"] or command[:3] == ["kubectl", "get", "pods"] for command in commands))

    def test_live_adapter_serves_snapshot_views_events_and_rejects_mutations(self):
        server = build_server("127.0.0.1", 0, ROOT / "dist", ROOT / "fixtures" / "preview-fixtures.json", mode="live", project_root=ROOT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            status, health = request_json(f"{base_url}/healthz")
            self.assertEqual(status, 200)
            self.assertEqual(health["sourceMode"], "live")
            self.assertEqual(health["liveReadsAllowed"], True)
            self.assertEqual(health["mutationsAllowed"], False)

            status, snapshot = request_json(f"{base_url}/api/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(snapshot["schemaVersion"], LIVE_SCHEMA_VERSION)
            self.assertEqual(snapshot["sourceMode"], "live")
            self.assertEqual(snapshot["runtime"]["previewService"]["streamPath"], "/api/events")

            status, overview = request_json(f"{base_url}/api/overview")
            self.assertEqual(status, 200)
            self.assertIs(overview["mocked"], False)
            self.assertIn("sourceReadiness", overview)

            status, content_type, body = request_text(f"{base_url}/api/events?once=1")
            self.assertEqual(status, 200)
            self.assertIn("text/event-stream", content_type)
            self.assertIn(f'"schemaVersion": "{EVENT_SCHEMA_VERSION}"', body)
            self.assertIn("event: heartbeat", body)

            status, rejection = request_json(f"{base_url}/api/snapshot", method="DELETE")
            self.assertEqual(status, 405)
            self.assertEqual(rejection["error"], "new-ui-evaluation is read-only")
        finally:
            server.shutdown()
            server.server_close()

    def test_fixture_contract_includes_required_operator_shapes(self):
        fixtures = load_fixtures(ROOT / "fixtures" / "preview-fixtures.json")

        self.assertEqual(fixtures["schemaVersion"], "new-ui-evaluation.fixture.v1")
        self.assertIs(fixtures["mocked"], True)
        self.assertIs(fixtures["overview"]["mocked"], True)
        self.assertTrue(fixtures["overview"]["attentionTarget"]["reason"])
        self.assertGreaterEqual(
            {round_item["state"] for round_item in fixtures["rounds"]},
            {"blocked", "active", "failed", "completed", "empty"},
        )
        self.assertIs(fixtures["inbox"][0]["readOnly"], True)
        self.assertEqual(
            fixtures["runtime"]["previewService"],
            {
                "name": "scion-ops-new-ui-eval",
                "port": 8091,
                "healthPath": "/healthz",
                "fixtureOnly": True,
                "liveReadsAllowed": False,
                "mutationsAllowed": False,
            },
        )
        self.assertIn("raw-runtime", fixtures["diagnostics"]["rawPayloads"])

    def test_fixture_fallback_is_explicit_and_rejects_mutations(self):
        server = build_server("127.0.0.1", 0, ROOT / "dist", ROOT / "fixtures" / "preview-fixtures.json", mode="fixture")
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
                    "schemaVersion": "new-ui-evaluation.fixture.v1",
                    "sourceMode": "fixture",
                    "mocked": True,
                    "liveReadsAllowed": False,
                    "mutationsAllowed": False,
                    "streamPath": None,
                    "generatedAt": health["generatedAt"],
                },
            )

            status, overview = request_json(f"{base_url}/api/overview")
            self.assertEqual(status, 200)
            self.assertIs(overview["mocked"], True)
            self.assertEqual(overview["counts"]["blockedRounds"], 2)

            status, rounds = request_json(f"{base_url}/api/rounds")
            self.assertEqual(status, 200)
            self.assertTrue(any(round_item["id"] == "round-empty-fixture" for round_item in rounds))

            status, detail = request_json(f"{base_url}/api/rounds/round-20260511t091500z-117a")
            self.assertEqual(status, 200)
            self.assertEqual(detail["rawPayloadRef"], "raw-round-blocked")

            status, rejection = request_json(f"{base_url}/api/rounds", method="POST")
            self.assertEqual(status, 405)
            self.assertEqual(rejection["error"], "new-ui-evaluation is read-only")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
