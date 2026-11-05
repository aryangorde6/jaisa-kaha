"""A small client for Switch's custom-agent protocol.

An agent registers once (POST /agents with a registration key) and gets an
id and an API key. It then holds one websocket for events and calls
operations over HTTP with the same connection id. Keys live in keys/<name>.json
(mode 600) and are never logged; keys/ids.json maps names to ids, which aren't
secret, so each agent can check who it's talking to without holding the
others' keys.

Frames arrive as {"event", "data", "id"}. A room message is event "message"
with data.payload = {addressed, sender, sender_name, sender_kind, message_id,
body, attachments: [{filename, mimetype, size, mxc}], ...}
(switch_core/bridges/agent/protocol/message_events.py).
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

API = os.environ.get("SWITCH_API", "http://127.0.0.1:8100")
KEYS = Path(__file__).resolve().parent.parent / "keys"
log = logging.getLogger("switch")


# httpx and websockets are imported where they're used, so the tests run on
# the standard library alone.


def register(name: str, description: str, registration_key: str) -> dict:
    import httpx

    resp = httpx.post(
        f"{API}/agents",
        headers={"Authorization": f"Bearer {registration_key}"},
        json={
            "name": name,
            "description": description,
            "connector_type": "custom",
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
            },
            "overwrite": True,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise SystemExit(f"register {name}: HTTP {resp.status_code} {resp.text[:300]}")
    agent = resp.json()
    KEYS.mkdir(mode=0o700, exist_ok=True)
    path = KEYS / f"{name}.json"
    path.write_text(json.dumps({"id": agent["id"], "api_key": agent["api_key"]}))
    os.chmod(path, 0o600)
    ids = KEYS / "ids.json"
    known = json.loads(ids.read_text()) if ids.exists() else {}
    ids.write_text(json.dumps({**known, name: agent["id"]}, indent=1))
    return {"id": agent["id"]}


def agent_ids() -> dict:
    return json.loads((KEYS / "ids.json").read_text())


class Agent:
    def __init__(self, name: str):
        import httpx

        creds = json.loads((KEYS / f"{name}.json").read_text())
        self.name = name
        self.id = creds["id"]
        self._auth = {"Authorization": f"Bearer {creds['api_key']}"}
        self.conn_id = str(uuid.uuid4())
        self.cursor = 0
        self.http = httpx.AsyncClient(
            base_url=API,
            headers={**self._auth, "X-Switch-Connection-Id": self.conn_id},
            timeout=30,
        )

    async def op(self, name: str, **body) -> dict:
        resp = await self.http.post(f"/agents/{self.id}/ops/{name}", json=body)
        if resp.status_code >= 400:
            log.warning("%s %s: HTTP %s", self.name, name, resp.status_code)
            resp.raise_for_status()
        return resp.json().get("result") if resp.content else None

    async def media(self, room_id: str, mxc: str) -> bytes:
        resp = await self.http.get(f"/agents/{self.id}/rooms/{room_id}/media", params={"mxc": mxc})
        resp.raise_for_status()
        return resp.content

    async def events(self, filter: str = "addressed", on_open=None):
        """Yield event frames forever, reconnecting with a short backoff.
        on_open runs after each (re)connect, e.g. to connect_to_room, since
        ops need an open socket with this connection id."""
        import websockets

        ws_base = API.replace("http", "ws", 1)
        url = f"{ws_base}/agents/{self.id}/connection/ws?connection_id={self.conn_id}&filter={filter}"
        delay = 1
        while True:
            try:
                async with websockets.connect(url, additional_headers=self._auth) as ws:
                    delay = 1
                    opened = False
                    async for raw in ws:
                        frame = json.loads(raw)
                        event = frame.get("event")
                        if event == "ping":
                            await ws.send(json.dumps({"type": "pong", "cursor": self.cursor}))
                            continue
                        if event in ("refused", "evicted"):
                            log.warning("%s: %s %s", self.name, event, frame.get("data"))
                            if (frame.get("data") or {}).get("code") == "taken_over":
                                raise SystemExit(f"{self.name}: another process took this agent over")
                            break
                        if event == "connection_state" and on_open and not opened:
                            opened = True
                            await on_open()
                        if isinstance(frame.get("id"), int):
                            self.cursor = frame["id"]
                        yield frame
            except (OSError, websockets.ConnectionClosed) as e:
                log.warning("%s: connection lost (%s), retrying in %ss", self.name, type(e).__name__, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
