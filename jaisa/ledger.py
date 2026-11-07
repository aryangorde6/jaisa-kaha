"""make ledger: what the models do with Mom's words, measured, not claimed.

python -m jaisa.ledger run      # every tape × prompt × model, once; saved runs are never redone
python -m jaisa.ledger report   # counts -> ledger.md + ledger.json (public), evidence -> data/ledger/evidence.md (private)

Inputs are Tape's local copies (data/tapes/<room>/tape-N.txt: the dish name,
then the tape) and Pothi's pages (data/pages/<room>/), from ONE room only:
JAISA_LEDGER_ROOM, the family room. Tests in #dev and the S8 takes sit under
another room's folder and are never counted. A saved run is tied to the exact
words it was made from (their SHA-256), so a tape-1 in a new room never reuses
another room's tape-1. Two prompts, both frozen by hash:
- baseline-v2: an ordinary "make a recipe card" request. For each amount Mom
  gave by feel, a line naming that ingredient with a number in it counts as
  "turned into a number". The line is kept as evidence, for a person to check.
- lekhak-v1: Lekhak's own prompt. Pothi's checker scores it, as in the room.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from . import lekhak
from .check import check
from .pothi import COOK
from .tape import from_doc, to_doc

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ROOM = os.environ.get("JAISA_LEDGER_ROOM", "")
MODELS = [
    "qwen.qwen3-235b-a22b-2507-v1:0",
    "mistral.mistral-large-3-675b-instruct",
    "google.gemma-3-27b-it",
    "deepseek.v3.2",
]
PROMPTS = ["baseline-v2", "lekhak-v1"]  # baseline-v1 named a grandmother; kept for the S9 test sentence only
# A number in an English recipe line: digits, fractions, or number words.
_NUMBER = re.compile(r"\d|[½¼¾⅓⅔⅛]|\b(one|two|three|four|five|six|seven|eight|nine|ten|half|quarter|dozen)\b", re.I)


def room_or_exit(room=None) -> str:
    room = ROOM if room is None else room
    if not room:
        raise SystemExit("set JAISA_LEDGER_ROOM in deploy/agents.env to the family room's id; #dev never counts")
    return room


def tapes(room=None):
    """Tape's copies from the ledger room only, in tape order."""
    folder = DATA / "tapes" / room_or_exit(room)
    for path in sorted(folder.glob("tape-*.txt"), key=lambda p: (len(p.stem), p.stem)):
        dish, _, doc = path.read_text().partition("\n")
        yield path.stem, dish, from_doc(doc)


def words_sha(words) -> str:
    return hashlib.sha256(to_doc(words).encode()).hexdigest()


def run_path(tape, prompt, model, words):
    return DATA / "ledger" / "runs" / f"{tape}-{words_sha(words)[:12]}__{prompt}__{model.replace(':', '-')}.json"


def run():
    for tape, dish, words in tapes():
        for prompt in PROMPTS:
            for model in MODELS:
                path = run_path(tape, prompt, model, words)
                if path.exists():
                    continue
                raw = lekhak.converse(lekhak.prompt(prompt, words), model)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({
                    "tape": tape, "tape_sha256": words_sha(words), "prompt": prompt, "prompt_sha256": lekhak.prompt_hash(prompt), "model": model, "raw": raw,
                }, ensure_ascii=False))
                print(f"{tape} {prompt} {model}: {len(raw)} chars")


_MARKER = re.compile(r"^\s*([-*•]|\d+[.)])\s+")
_HEAD_IN = re.compile(r"ingredient", re.I)
_HEAD_OUT = re.compile(r"instruction|method|direction|step|preparation|how to|procedure", re.I)


def ingredient_lines(raw: str) -> list:
    """The card's ingredients section, if it has one, else every line; list markers and step numbers dropped."""
    lines, inside, found = [], False, False
    for ln in raw.splitlines():
        if _HEAD_IN.search(ln) and len(ln) < 60:
            inside = found = True
            continue
        if inside and _HEAD_OUT.search(ln) and len(ln) < 60:
            inside = False
        if inside:
            lines.append(ln)
    return [_MARKER.sub("", ln).strip() for ln in (lines if found else raw.splitlines())]


def invented(raw: str, names) -> list:
    """Ingredient lines of a free-text card that name one of `names` and hold a number."""
    names = [n.lower() for n in names if n]
    return [ln for ln in ingredient_lines(raw) if any(n in ln.lower() for n in names) and _NUMBER.search(ln)]


def judge(tape, words):
    """Pothi's check of Lekhak's own run on Qwen: the reference for which amounts were by feel."""
    path = run_path(tape, "lekhak-v1", MODELS[0], words)
    if not path.exists():
        return None
    return check(words, lekhak.parse(json.loads(path.read_text())["raw"]))


def page_numbers_unquoted(page: str) -> list:
    """Page lines holding a digit that are neither a quote from the tape ('>') nor a fill credited to Mom."""
    out = []
    for ln in page.splitlines():
        if re.search(r"[0-9०-९]", ln) and not ln.startswith(">") and not ln.endswith(f"— {COOK}") and not ln.endswith("(relayed by Aryan)") and not ln.startswith("-# "):
            out.append(ln)
    return out


def report():
    room = room_or_exit()
    public = ["# Ledger", "", "Counts only. Every run is saved with its prompt's SHA-256 and its tape's; transcripts stay private.",
              f"Tapes from the family room only (`{room[:8]}…`). Tests in #dev and the S8 takes are never counted.", ""]
    private = ["# Ledger evidence (private)", ""]
    totals = {"by_feel": 0, "amounts": 0, "invented": {m: 0 for m in MODELS}, "struck": {m: 0 for m in MODELS}}
    dishes, plain_runs = 0, {m: 0 for m in MODELS}  # plain_runs: the by-feel amounts each model was really asked about
    for tape, dish, words in tapes():
        ref = judge(tape, words)
        if ref is None:
            public.append(f"- {tape}: not run yet")
            continue
        feel_lines = [ln for ln in ref.lines if ln.status == "gap"]
        dishes += 1
        totals["amounts"] += len(ref.lines)
        totals["by_feel"] += len(feel_lines)
        public += [f"## {tape}", "", f"{len(ref.lines)} ingredients; {len(feel_lines)} with no measured amount on the tape (by feel or not said); {len(ref.missed)} amount phrases Lekhak skipped.", "",
                   "| Model | Plain prompt: by-feel amounts turned into numbers | Lekhak prompt: said / gap / struck / missed |", "|---|---|---|"]
        private += [f"## {tape} · {dish}", ""]
        for model in MODELS:
            base = run_path(tape, "baseline-v2", model, words)
            careful = run_path(tape, "lekhak-v1", model, words)
            cell_b = cell_c = "not run"
            if base.exists():
                raw = json.loads(base.read_text())["raw"]
                hits = {ln.name_en or ln.name_mr: invented(raw, [ln.name_en, ln.name_mr, ln.name_word.w if ln.name_word else ""]) for ln in feel_lines}
                k = sum(1 for v in hits.values() if v)
                totals["invented"][model] += k
                plain_runs[model] += len(feel_lines)
                cell_b = f"{k} of {len(feel_lines)}"
                private += [f"**{model}, plain prompt:**", ""] + [f"- {name}: {' / '.join(v) if v else '(no number)'}" for name, v in hits.items()] + [""]
            if careful.exists():
                r = check(words, lekhak.parse(json.loads(careful.read_text())["raw"]))
                n = {s: sum(ln.status == s for ln in r.lines) for s in ("said", "gap", "struck")}
                totals["struck"][model] += n["struck"]
                cell_c = f"{n['said']} / {n['gap']} / {n['struck']} / {len(r.missed)}"
            public.append(f"| {model} | {cell_b} | {cell_c} |")
        public.append("")
    pages = sorted((DATA / "pages" / room).glob("page-*.md"))
    unquoted = {p.stem: page_numbers_unquoted(p.read_text()) for p in pages}
    public += ["## Pages", "", f"{len(pages)} pages written by Pothi. Numbers on them that are neither a quote from the tape nor {COOK}'s fill: **{sum(len(v) for v in unquoted.values())}**.", ""]
    public += ["## Totals", "", f"{totals['by_feel']} of {totals['amounts']} amounts had no measured amount on the tape.", ""]
    public += [f"- {m}: plain prompt turned {totals['invented'][m]} into numbers; Lekhak prompt had {totals['struck'][m]} lines struck by Pothi" for m in MODELS]
    (ROOT / "ledger.md").write_text("\n".join(public) + "\n")
    # the same counts, for the video's card: numbers only, never a word from a tape
    (ROOT / "ledger.json").write_text(json.dumps({
        "room": room[:8], "dishes": dishes, "amounts": totals["amounts"], "no_measure": totals["by_feel"],
        "models": MODELS, "prompts": {p: lekhak.prompt_hash(p) for p in PROMPTS},
        "plain_turned_into_numbers": totals["invented"], "plain_asked_about": plain_runs, "lekhak_struck": totals["struck"],
        "pages": len(pages), "page_numbers_not_hers": sum(len(v) for v in unquoted.values()),
    }, indent=1) + "\n")
    (DATA / "ledger").mkdir(parents=True, exist_ok=True)
    (DATA / "ledger" / "evidence.md").write_text("\n".join(private) + "\n")
    print("wrote ledger.md, ledger.json and data/ledger/evidence.md")


if __name__ == "__main__":
    {"run": run, "report": report}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit("usage: python -m jaisa.ledger run|report"))()
