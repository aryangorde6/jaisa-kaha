"""Live checks against the real room. Each runs as one of our agents, so stop
that agent's own process first: Switch keeps one connection per agent.

  python -m jaisa.probe smoke
      As Tape: posts tape-999, a TEST transcript from tests/test_pothi.py (not
      Mom's), addresses the real Lekhak and waits for its draft. Checks Lekhak's
      answer by sender id, the draft's creator in Switch's records, and runs
      Pothi's checker on it. Deletes tape-999 after. draft-999 stays, because
      only Lekhak may delete it.

  python -m jaisa.probe rehearse
      The same, then hands draft-999 to the real Pothi, as Tape does. Pothi's
      review of the TEST transcript appears in the room, and Mom answers it on
      her phone: a dress rehearsal in #dev before her own recipe. tape-999
      stays, since Pothi reads it; the next smoke or rehearse replaces it.

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


async def smoke(to_pothi=False) -> bool:
    from tests.test_pothi import TAPE  # the project's own test transcript, not Mom's

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
            description="TEST, not Mom's: make smoke",
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
                if to_pothi:
                    await me.op("send_targeted_message", body=f"draft ready: draft-{SMOKE}", target_names=["pothi"])
                    print(f"sent @pothi draft ready: draft-{SMOKE}. Pothi's review is in the room: Mom answers it on her phone")
            return

    try:
        await asyncio.wait_for(run(), 180)
    finally:
        t = None if to_pothi and ok else await agents.find_doc(me, f"tape-{SMOKE}")
        if t:
            await me.op("delete_room_document", document_id=t["id"])
            print(f"deleted tape-{SMOKE}")
    print("make rehearse:" if to_pothi else "make smoke:", "ok" if ok else "FAILED")
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
    if args in (["smoke"], ["rehearse"]):
        sys.exit(0 if asyncio.run(smoke(to_pothi=args == ["rehearse"])) else 1)
    if len(args) >= 4 and args[0] == "ask" and args[1] in agents.AGENT_SENDERS:
        asyncio.run(ask(args[1], args[2], " ".join(args[3:])))
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
