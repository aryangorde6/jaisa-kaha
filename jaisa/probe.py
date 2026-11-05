"""Live checks against the real room. Each runs as one of our agents, so stop
that agent's own process first: Switch keeps one connection per agent.

  python -m jaisa.probe smoke
      As Tape: posts tape-999, a TEST transcript from tests/test_pothi.py (not
      Dadi), addresses the real Lekhak and waits for its draft. Checks Lekhak's
      answer by sender id, the draft's creator in Switch's records, and runs
      Pothi's checker on it. Deletes tape-999 after. draft-999 stays, because
      only Lekhak may delete it.

  python -m jaisa.probe ask <Agent> <target> <words...>
      Sends one targeted message as <Agent> and prints what Switch says about
      the target: live, offline, or not_permitted. For the video's "the model
      too" beat: python -m jaisa.probe ask Lekhak pothi ghee 1 cup

Prints ids, flags and counts, never transcripts.
"""

import asyncio
import json
import sys

from . import agents, tape as tapelib
from .check import check
from .switch import Agent, agent_ids

SMOKE = "999"


async def smoke() -> bool:
    from tests.test_pothi import TAPE  # the project's own test transcript, not Dadi

    me, ids = Agent("Tape"), agent_ids()
    ok = False

    async def on_open():
        await me.op("connect_to_room", room_id=agents.ROOM, include_general_instructions=False)
        old = await agents.find_doc(me, f"tape-{SMOKE}")
        if old:
            await me.op("delete_room_document", document_id=old["id"])
        await me.op(
            "create_room_document",
            name=f"tape-{SMOKE}",
            description="TEST, not Dadi: make smoke",
            instructions="A test transcript from the project's own tests. Deleted after the check.",
            content=tapelib.to_doc(TAPE),
        )
        await me.op("send_targeted_message", body=f"tape-{SMOKE} smoke test", target_names=["lekhak"])
        print("sent @lekhak tape-999 (a test transcript); waiting for Lekhak, up to 3 minutes")

    async def run():
        nonlocal ok
        async for frame in me.events("all", on_open=on_open):
            p = agents.message(frame)
            if not p or not p.get("addressed"):
                continue
            print(agents.frame_line("smoke", frame))
            if not agents.from_agent(p, "Lekhak"):
                print("  not Lekhak's sender id: ignored")
                continue
            d = await agents.find_doc(me, f"draft-{SMOKE}")
            by_lekhak = bool(d) and d.get("created_by_agent_id") == ids["Lekhak"]
            print(f"  Lekhak answered {agents.said(p)!r}; draft-{SMOKE} made by Lekhak: {by_lekhak}")
            if by_lekhak:
                r = check(TAPE, json.loads(await agents.load_doc(me, d)))
                statuses = [line.status for line in r.lines]
                print("  Pothi's checker:", {s: statuses.count(s) for s in sorted(set(statuses))}, "| missed:", len(r.missed))
                ok = True
            return

    try:
        await asyncio.wait_for(run(), 180)
    finally:
        t = await agents.find_doc(me, f"tape-{SMOKE}")
        if t:
            await me.op("delete_room_document", document_id=t["id"])
            print(f"deleted tape-{SMOKE}")
    print("make smoke:", "ok" if ok else "FAILED")
    return ok


async def ask(who: str, target: str, text: str) -> dict:
    me = Agent(who)
    result = {}

    async def on_open():
        nonlocal result
        await me.op("connect_to_room", room_id=agents.ROOM, include_general_instructions=False)
        result = await me.op("send_targeted_message", body=text, target_names=[target]) or {}

    async def run():
        async for _ in me.events("addressed", on_open=on_open):
            if result:
                return

    await asyncio.wait_for(run(), 30)
    statuses = result.get("target_statuses", {})
    print(f"{who} -> @{target}: {statuses.get(target, 'no status')}")
    return result


def main():
    if not agents.ROOM:
        raise SystemExit("load deploy/agents.env first (the make targets do)")
    args = sys.argv[1:]
    if args == ["smoke"]:
        sys.exit(0 if asyncio.run(smoke()) else 1)
    if len(args) >= 4 and args[0] == "ask" and args[1] in agents.AGENT_SENDERS:
        asyncio.run(ask(args[1], args[2], " ".join(args[3:])))
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
