from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from adapter import build_server, load_fixtures


ROOT = Path(__file__).resolve().parents[1]


def request_json(url: str, method: str = "GET"):
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


class AdapterTests(unittest.TestCase):
    def test_fixture_contract_includes_required_operator_shapes(self):
        fixtures = load_fixtures(ROOT / "fixtures" / "preview-fixtures.json")

        self.assertEqual(fixtures["schemaVersion"], "new-ui-evaluation.fixture.v1")
        self.assertIs(fixtures["mocked"], True)
        self.assertTrue(fixtures["overview"]["attentionTarget"]["reason"])
        self.assertGreaterEqual(
            {round_item["state"] for round_item in fixtures["rounds"]},
            {"blocked", "active", "failed", "completed", "empty"},
        )
        self.assertIs(fixtures["inbox"][0]["readOnly"], True)
        self.assertEqual(
            fixtures["runtime"]["previewService"],
            {
                "name": "new-ui-evaluation",
                "port": 8091,
                "healthPath": "/healthz",
                "fixtureOnly": True,
                "liveReadsAllowed": False,
                "mutationsAllowed": False,
            },
        )
        self.assertIn("raw-runtime", fixtures["diagnostics"]["rawPayloads"])

    def test_adapter_serves_mocked_endpoints_and_rejects_mutations(self):
        server = build_server("127.0.0.1", 0, ROOT / "dist", ROOT / "fixtures" / "preview-fixtures.json")
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
                    "mocked": True,
                    "liveReadsAllowed": False,
                    "mutationsAllowed": False,
                },
            )

            status, overview = request_json(f"{base_url}/api/overview")
            self.assertEqual(status, 200)
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
