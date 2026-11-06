"""The three agents as processes: python -m jaisa.agents Tape|Lekhak|Pothi

Each one acts only in JAISA_ROOM (a Switch room id) and checks who's talking
before it acts, on top of Switch's addressing rules. Everyone, agent or person,
is told apart by their Switch sender id (JAISA_*_SENDER). Logs carry event
kinds, sender ids and sizes, never message text or transcripts.
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
from .pothi import Book, page_messages
from .switch import SWITCH_NAME, Agent, agent_ids

ROOM = os.environ.get("JAISA_ROOM", "")
ARYAN = os.environ.get("JAISA_ARYAN_SENDER", "")
MOM = os.environ.get("JAISA_MOM_SENDER", "")
MOM_NAME = os.environ.get("JAISA_MOM_NAME", "Mom")
# Agents are told apart by sender id too. In a live event Switch sets
# sender_kind only for the platform itself (message_events.py); an agent's
# message carries none, so its sender, @switch-agent-…:localhost, is what marks
# it. `make senders` prints these from Switch.
AGENT_SENDERS = {
    "Tape": os.environ.get("JAISA_TAPE_SENDER", ""),
    "Lekhak": os.environ.get("JAISA_LEKHAK_SENDER", ""),
    "Pothi": os.environ.get("JAISA_POTHI_SENDER", ""),
}
# Whose messages each agent acts on, so it can refuse to start without them.
NEEDS = {"Tape": ("Lekhak",), "Lekhak": ("Tape",), "Pothi": ("Tape",)}
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


def is_agent(p) -> bool:
    sender = str(p.get("sender", ""))
    return (
        p.get("sender_kind") == "agent"
        or sender.startswith("@switch-agent-")
        or (bool(sender) and sender in AGENT_SENDERS.values())
    )


def from_agent(p, name) -> bool:
    """Whether our agent `name` sent this, by its Switch sender id. Never by
    name: display names are free text. Who may address whom is Switch's rule,
    and document creators are checked by agent id on top of this."""
    sender_id = AGENT_SENDERS.get(name, "")
    return bool(sender_id) and p.get("sender") == sender_id


def from_person(p, sender_id, who) -> bool:
    if is_agent(p):
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


def frame_line(name, frame) -> str:
    """One log line per frame: what kind it is and who sent it, never the text.
    It's how we can show that a message Switch refused never reached us."""
    data = frame.get("data") if isinstance(frame, dict) else None
    p = data.get("payload") if isinstance(data, dict) else None
    if not isinstance(p, dict):
        return f"{name}: frame {frame.get('event') if isinstance(frame, dict) else '?'}"
    return f"{name}: frame {frame.get('event')} addressed={bool(p.get('addressed'))} kind={p.get('sender_kind')} from {p.get('sender')}"


async def serve(me, filter, on_open, handle):
    async for frame in me.events(filter, on_open=on_open):
        log.info(frame_line(me.name, frame))
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
        if is_agent(p):
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
            await me.op("send_targeted_message", body=f"relayed by aryan: {body[6:].strip()}", target_names=[SWITCH_NAME["Pothi"]])
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
        description=f"{dish}: Mom's words, as Tape heard them",
        instructions="One word per line: [index] seconds word. Cite word indexes; never retype the words.",
        content=tapelib.to_doc(words),
    )
    log.info("Tape: %s, %d words, %s", name, len(words), tapelib.mmss(words[-1].t if words else 0))
    # for make ledger, one folder per room: it counts the family room only, so a
    # test voice note in #dev never reaches it, and tape numbers restart per room
    keep(f"tapes/{ROOM}/{name}.txt", f"{dish}\n{tapelib.to_doc(words)}")
    await me.op("send_targeted_message", body=f"{name} {dish}", target_names=[SWITCH_NAME["Lekhak"]])


async def tape_handoff(me, ids, body):
    """Lekhak says "draft ready: draft-N". Tape passes it on only if Lekhak made that document."""
    m = re.fullmatch(r"draft ready: (draft-\d{1,4})", body)
    doc = await find_doc(me, m.group(1)) if m else None
    if not doc or doc.get("created_by_agent_id") != ids["Lekhak"]:
        await me.op("post_message", body=NOT_LEKHAKS)
        return
    await me.op("send_targeted_message", body=f"draft ready: {m.group(1)}", target_names=[SWITCH_NAME["Pothi"]])


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
        await me.op("send_targeted_message", body=f"draft ready: {name}", target_names=[SWITCH_NAME["Tape"]])

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
            try:
                await me.op("send_targeted_message", body=m[5:], target_names=[MOM_NAME])
            except Exception:
                # Mom's room name is her Discord username (JAISA_MOM_NAME). If
                # it's wrong, the question still reaches the room, unpinged.
                log.warning("Pothi: couldn't address %r (JAISA_MOM_NAME); posted without the ping", MOM_NAME)
                await me.op("post_message", body=m[5:])
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
                instructions="Every amount here is on the tape or typed by Mom. Read only.",
                content=book.page,
            )
            written = True
            keep(f"pages/{ROOM}/page-{n}.md", book.page)  # for make ledger, per room as tapes are
            save(n, book, written)  # before posting, so a failed post never writes the page twice
            # The document is the record, but no phone can open it: !list-documents
            # links to the Gateway, which listens on 127.0.0.1 only. So the family
            # reads the page here, in the room, posted once.
            for part in page_messages(f"{book.page}\n\n-# kept in Switch as room document page-{n}"):
                await me.op("post_message", body=part)
        if book:
            save(n, book, written)

    await serve(me, "addressed", on_open, handle)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not ROOM:
        raise SystemExit("set JAISA_ROOM to the Switch room id")
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    run = {"Tape": run_tape, "Lekhak": run_lekhak, "Pothi": run_pothi}.get(name)
    if not run:
        raise SystemExit("usage: python -m jaisa.agents Tape|Lekhak|Pothi")
    missing = [f"JAISA_{other.upper()}_SENDER" for other in NEEDS[name] if not AGENT_SENDERS[other]]
    if missing:
        raise SystemExit(f"{name} acts on messages from {', '.join(NEEDS[name])}: set {', '.join(missing)} (make senders prints it)")
    asyncio.run(run())


if __name__ == "__main__":
    main()
