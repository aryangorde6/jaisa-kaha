"""Registration: Switch's lowercase name, the display name people see, and a key
file nobody else can read. httpx is faked, so this runs on the standard library."""

import asyncio
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from jaisa import switch


class FakeResponse:
    status_code = 200

    def json(self):
        return {"id": "agent-1", "api_key": "secret-agent-key"}


class Register(unittest.TestCase):
    def setUp(self):
        self.sent = {}
        fake_httpx = types.SimpleNamespace(post=lambda url, **kw: self.sent.update(kw) or FakeResponse())
        self.keys = Path(tempfile.mkdtemp()) / "keys"
        self.patches = [
            mock.patch.dict(sys.modules, {"httpx": fake_httpx}),
            mock.patch.object(switch, "KEYS", self.keys),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_switch_name_is_lowercase_and_display_name_kept(self):
        switch.register("Pothi", "Mom's.", "reg-key")
        self.assertEqual(self.sent["json"]["name"], "pothi")
        self.assertEqual(self.sent["json"]["display_name"], "Pothi")
        self.assertEqual(self.sent["headers"]["Authorization"], "Bearer reg-key")

    def test_every_switch_name_passes_switchs_rule(self):
        # agent_core.py: lowercase letters, digits, dots, hyphens, underscores.
        for name in switch.SWITCH_NAME.values():
            self.assertRegex(name, r"^[a-z0-9._-]+$")

    def test_key_file_is_mode_600_and_ids_have_no_key(self):
        old = os.umask(0o022)
        try:
            switch.register("Tape", "Aryan's.", "reg-key")
        finally:
            os.umask(old)
        key_file = self.keys / "Tape.json"
        self.assertEqual(stat.S_IMODE(key_file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.keys.stat().st_mode), 0o700)
        self.assertEqual(json.loads(key_file.read_text())["api_key"], "secret-agent-key")
        ids = (self.keys / "ids.json").read_text()
        self.assertEqual(json.loads(ids), {"Tape": "agent-1"})
        self.assertNotIn("secret-agent-key", ids)


class Op(unittest.TestCase):
    """The real Agent.op, over a fake httpx: the agents' tests use a fake Agent,
    so this is what checks the call itself."""

    def test_an_operation_can_take_a_name_argument(self):
        sent = []

        class Response:
            status_code, content = 200, b"{}"

            def json(self):
                return {"result": {"document_id": "doc-1"}}

        class AsyncClient:
            def __init__(self, **kw):
                self.headers = kw["headers"]

            async def post(self, url, json):
                sent.append((url, json))
                return Response()

        keys = Path(tempfile.mkdtemp())
        (keys / "Tape.json").write_text(json.dumps({"id": "agent-1", "api_key": "k"}))
        with mock.patch.dict(sys.modules, {"httpx": types.SimpleNamespace(AsyncClient=AsyncClient)}), \
                mock.patch.object(switch, "KEYS", keys):
            agent = switch.Agent("Tape")
            result = asyncio.run(agent.op("create_room_document", name="tape-1", description="d", instructions="i", content="c"))
        self.assertEqual(result, {"document_id": "doc-1"})
        self.assertEqual(sent, [("/agents/agent-1/ops/create_room_document",
                                 {"name": "tape-1", "description": "d", "instructions": "i", "content": "c"})])


if __name__ == "__main__":
    unittest.main()
