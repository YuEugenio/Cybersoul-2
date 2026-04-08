"""Tests for the standalone Phone web app server."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from unittest import TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Phone.server import create_phone_server


class PhoneServerTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = str(Path(self.temp_dir.name) / "phone_store.json")
        self.server = create_phone_server(
            host="127.0.0.1",
            port=0,
            store_path=self.store_path,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = "http://{host}:{port}".format(host=host, port=port)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_index_page_is_served(self) -> None:
        with urllib.request.urlopen(self.base_url + "/") as response:
            html = response.read().decode("utf-8")

        self.assertIn("昔涟的手机", html)
        self.assertIn("Cybersoul Phone", html)

    def test_bootstrap_and_send_message(self) -> None:
        bootstrap = self._get_json("/api/bootstrap")
        thread_id = bootstrap["thread"]["thread_id"]

        self.assertEqual(bootstrap["companion"]["display_name"], "昔涟")
        self.assertEqual(bootstrap["messages"], [])
        self.assertEqual(bootstrap["app"]["reply_backend"], "tool")
        self.assertFalse(bootstrap["app"]["auto_reply_enabled"])

        sent = self._post_json(
            "/api/messages",
            {
                "thread_id": thread_id,
                "content": "晚安，今天有一点累。",
            },
        )

        self.assertEqual(sent["last_user_message"]["content"], "晚安，今天有一点累。")
        self.assertIn("用户: 晚安，今天有一点累。", sent["transcript"])
        self.assertEqual(len(sent["messages"]), 1)

    def _get_json(self, path: str) -> dict:
        with urllib.request.urlopen(self.base_url + path) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
