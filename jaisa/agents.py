"""The three agents as processes: python -m jaisa.agents Tape|Lekhak|Pothi

Each one acts only in JAISA_ROOM (a Switch room id) and checks who's talking
before it acts, on top of Switch's addressing rules. Agents are told apart by
sender_kind "agent" plus their name; people by their Switch sender id. Logs
carry event kinds, sender ids and sizes, never message text or transcripts.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from . import budget, lekhak, tape as tapelib
from .pothi import Book
from .switch import Agent, agent_ids

ROOM = os.environ.get("JAISA_ROOM", "")
ARYAN = os.environ.get("JAISA_ARYAN_SENDER", "")
MOM = os.environ.get("JAISA_MOM_SENDER", "")
MOM_NAME = os.environ.get("JAISA_MOM_NAME", "Mom")
DATA = Path(__file__).resolve().parent.parent / "data"
log = logging.getLogger("jaisa")

# Tape's fixed lines. It never says anything else, and never repeats what it was sent.
NOT_AUDIO = "-# not a voice note Tape can read: audio only, up to 20 MB and 10 minutes"
NO_LINKS = "-# Tape doesn't open links; post the voice note itself"
NO_AUDIO = "-# no voice note to transcribe"
NOT_LEKHAKS = "-# not a draft from Lekhak; not passed on"
TOO_MANY = "-# too many hand-offs in 10 minutes; dropped"
CAPPED = "-# today's limit is reached; try tomorrow"


def message(frame):
    """The payload of a room message in our room, or None."""
    if frame.get("event") != "message":
        return None
    data = frame.get("data") or {}
    if data.get("room_id") != ROOM:
        return None
    return data.get("payload") or None


def said(p) -> str:
    """The body without @mentions, on one line."""
    return " ".join(w for w in str(p.get("body", "")).split() if not w.startswith(("@", "<@")))


def from_agent(p, name) -> bool:
    return p.get("sender_kind") == "agent" and p.get("sender_name") == name


def from_person(p, sender_id, who) -> bool:
    if p.get("sender_kind") == "agent":
        return False
    if sender_id and p.get("sender") == sender_id:
        return True
    log.warning("%s? sender %s is not configured (JAISA_%s_SENDER)", who, p.get("sender"), who.upper())
    return False


async def find_doc(me, name):
    refs = await me.op("list_references") or {}
    return next((d for d in refs.get("documents", []) if d.get("name") == name), None)


async def load_doc(me, doc) -> str:
    [entry] = await me.op("load_internal_documents", ids=[doc["id"]])
    return entry["content"]


async def next_number(me) -> int:
    refs = await me.op("list_references") or {}
    nums = [int(m.group(1)) for d in refs.get("documents", []) if (m := re.fullmatch(r"tape-(\d{1,4})", d.get("name", "")))]
    return max(nums, default=0) + 1


def keep(rel, text):
    """A local copy under data/ (gitignored, never published) for make ledger."""
    path = DATA / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def connector(me):
    async def on_open():
        await me.op("connect_to_room", room_id=ROOM, include_general_instructions=False)
        log.info("%s: in room %s", me.name, ROOM)
    return on_open


async def serve(me, filter, on_open, handle):
    async for frame in me.events(filter, on_open=on_open):
        try:
            await handle(frame)
        except Exception:
            log.exception("%s: a frame failed", me.name)


def looks_audio(att) -> bool:
    """A first look from the event; the bytes are checked by ffprobe later."""
    try:
        tapelib.media_format(att.get("filename", ""))
    except ValueError:
        return False
    return 0 < att.get("size", 0) <= tapelib.MAX_BYTES


# --- Tape ------------------------------------------------------------------

async def run_tape():
    me, ids = Agent("Tape"), agent_ids()
    last_audio = None  # Aryan's newest attachment, for "@Tape <dish>" sent after it
    handoffs = budget.Handoffs()

    async def handle(frame):
        nonlocal last_audio
        p = message(frame)
        if not p:
            return
        if p.get("sender_kind") == "agent":
            if p.get("addressed") and from_agent(p, "Lekhak"):
                if handoffs.allow():
                    await tape_handoff(me, ids, said(p))
                else:
                    await me.op("post_message", body=TOO_MANY)
            return
        attachments = p.get("attachments") or []
        if not (attachments or p.get("addressed")) or not from_person(p, ARYAN, "Aryan"):
            return
        if attachments:
            last_audio = attachments[-1]
        if not p.get("addressed"):
            return
        body = said(p)
        if "://" in body or "www." in body:
            await me.op("post_message", body=NO_LINKS)
        elif body.startswith("relay "):
            await me.op("send_targeted_message", body=f"relayed by aryan: {body[6:].strip()}", target_names=["Pothi"])
        elif last_audio:
            att, last_audio = last_audio, None
            await tape_transcribe(me, att, dish=body[:60] or "recipe")
        else:
            await me.op("post_message", body=NO_AUDIO)

    await serve(me, "all", connector(me), handle)


async def tape_transcribe(me, att, dish):
    if not looks_audio(att):
        await me.op("post_message", body=NOT_AUDIO)
        return
    audio = await me.media(ROOM, att["mxc"])
    try:
        seconds = await asyncio.to_thread(tapelib.probe, audio)
    except ValueError as e:
        log.info("Tape: refused an attachment (%s)", e)
        await me.op("post_message", body=NOT_AUDIO)
        return
    if not budget.spend(DATA / "budget.json", "transcribe"):
        await me.op("post_message", body=CAPPED)
        return
    log.info("Tape: %d bytes, %.0f s of %s", len(audio), seconds, tapelib.media_format(att["filename"]))
    words = await asyncio.to_thread(tapelib.transcribe, audio, att["filename"])
    name = f"tape-{await next_number(me)}"
    await me.op(
        "create_room_document",
        name=name,
        description=f"{dish}: Dadi's words, as Tape heard them",
        instructions="One word per line: [index] seconds word. Cite word indexes; never retype the words.",
        content=tapelib.to_doc(words),
    )
    log.info("Tape: %s, %d words, %s", name, len(words), tapelib.mmss(words[-1].t if words else 0))
    keep(f"tapes/{name}.txt", f"{dish}\n{tapelib.to_doc(words)}")  # for make ledger
    await me.op("send_targeted_message", body=f"{name} {dish}", target_names=["Lekhak"])


async def tape_handoff(me, ids, body):
    """Lekhak says "draft ready: draft-N". Tape passes it on only if Lekhak made that document."""
    m = re.fullmatch(r"draft ready: (draft-\d{1,4})", body)
    doc = await find_doc(me, m.group(1)) if m else None
    if not doc or doc.get("created_by_agent_id") != ids["Lekhak"]:
        await me.op("post_message", body=NOT_LEKHAKS)
        return
    await me.op("send_targeted_message", body=f"draft ready: {m.group(1)}", target_names=["Pothi"])


# --- Lekhak ----------------------------------------------------------------

async def run_lekhak():
    me, ids = Agent("Lekhak"), agent_ids()
    handoffs = budget.Handoffs()

    async def handle(frame):
        p = message(frame)
        if not p or not p.get("addressed") or not from_agent(p, "Tape"):
            return
        m = re.match(r"tape-(\d{1,4})\b", said(p))
        doc = await find_doc(me, m.group(0)) if m else None
        if not doc or doc.get("created_by_agent_id") != ids["Tape"]:
            return
        if not handoffs.allow():
            await me.op("post_message", body=TOO_MANY)
            return
        if not budget.spend(DATA / "budget.json", "model"):
            await me.op("post_message", body=CAPPED)
            return
        words = tapelib.from_doc(await load_doc(me, doc))
        draft, raw = await asyncio.to_thread(lekhak.write_draft, words)
        (DATA / "drafts").mkdir(parents=True, exist_ok=True)
        (DATA / "drafts" / f"{m.group(0)}-{int(time.time())}.json").write_text(json.dumps(
            {"model": lekhak.MODEL, "prompt": "lekhak-v1", "prompt_sha256": lekhak.prompt_hash("lekhak-v1"), "raw": raw},
            ensure_ascii=False,
        ))
        if draft is None:
            await me.op("post_message", body="-# draft failed: the model's answer wasn't JSON")
            return
        name, content = f"draft-{m.group(1)}", json.dumps(draft, ensure_ascii=False)
        existing = await find_doc(me, name)
        if existing:
            await me.op("update_room_document", document_id=existing["id"], content=content)
        else:
            await me.op(
                "create_room_document",
                name=name,
                description=f"Lekhak's draft of {m.group(0)}",
                instructions="JSON. Every quantity is a word-index citation into the tape; Pothi checks each one.",
                content=content,
            )
        await me.op("send_targeted_message", body=f"draft ready: {name}", target_names=["Tape"])

    await serve(me, "addressed", connector(me), handle)


# --- Pothi -----------------------------------------------------------------

STATE = DATA / "pothi.json"


async def open_book(me, ids, n):
    draft_doc, tape_doc = await find_doc(me, f"draft-{n}"), await find_doc(me, f"tape-{n}")
    if not draft_doc or draft_doc.get("created_by_agent_id") != ids["Lekhak"]:
        return None
    if not tape_doc or tape_doc.get("created_by_agent_id") != ids["Tape"]:
        return None
    try:
        draft = json.loads(await load_doc(me, draft_doc))
        words = tapelib.from_doc(await load_doc(me, tape_doc))
    except ValueError:
        return None
    dish = str(tape_doc.get("description", "")).split(":")[0]
    return Book(dish, words, draft)


def save(n, book, written):
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"n": n, "fills": book.fills, "pending": book.pending, "written": written}, ensure_ascii=False))


async def send(me, msgs):
    for m in msgs:
        if m.startswith("@Mom "):
            await me.op("send_targeted_message", body=m[5:], target_names=[MOM_NAME])
        else:
            await me.op("post_message", body=m)


async def run_pothi():
    me, ids = Agent("Pothi"), agent_ids()
    book, n, written = None, None, False

    async def on_open():
        nonlocal book, n, written
        await connector(me)()
        if book is None and STATE.exists():
            st = json.loads(STATE.read_text())
            book = await open_book(me, ids, st["n"])
            if book:
                n, written = st["n"], st["written"]
                book.fills = {int(k): tuple(v) for k, v in st["fills"].items()}
                book.pending = tuple(st["pending"]) if st["pending"] else None
                if written:
                    book.page = book.render()

    async def handle(frame):
        nonlocal book, n, written
        p = message(frame)
        if not p or not p.get("addressed"):
            return
        log.info("Pothi: addressed by %s (%s)", p.get("sender"), p.get("sender_kind"))
        replies = []
        if from_agent(p, "Tape"):
            m = re.fullmatch(r"draft ready: draft-(\d{1,4})", said(p))
            if m:
                new = await open_book(me, ids, m.group(1))
                if new is None:
                    replies = ["-# that draft isn't Lekhak's, or its tape isn't Tape's; not read"]
                else:
                    book, n, written = new, m.group(1), False
                    replies = book.review()
            elif book:
                replies = book.on_tape(said(p))
        elif book and from_person(p, MOM, "Mom"):
            replies = book.on_mom(said(p))
        await send(me, replies)
        if book and book.page and not written:
            await me.op(
                "create_room_document",
                name=f"page-{n}",
                description=f"{book.dish}: approved by Mom",
                instructions="Every amount here is Dadi's, on the tape, or Mom's. Read only.",
                content=book.page,
            )
            written = True
            keep(f"pages/page-{n}.md", book.page)  # for make ledger
        if book:
            save(n, book, written)

    await serve(me, "addressed", on_open, handle)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not ROOM:
        raise SystemExit("set JAISA_ROOM to the Switch room id")
    run = {"Tape": run_tape, "Lekhak": run_lekhak, "Pothi": run_pothi}.get(sys.argv[1] if len(sys.argv) > 1 else "")
    if not run:
        raise SystemExit("usage: python -m jaisa.agents Tape|Lekhak|Pothi")
    asyncio.run(run())


if __name__ == "__main__":
    main()
