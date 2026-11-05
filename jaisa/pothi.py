"""Pothi's book for one dish: the review, Mom's fills, and the page.

Pure logic, no network. The runner calls on_mom() only for Mom's messages and
on_tape() only for Tape's, after checking the sender itself (Switch's rule
already refuses everyone else; this is the second lock). Every string that
came from the tape, Lekhak or a chat message is escaped before it's posted,
so nothing in it can ping, link or reformat the room.
"""

import re

from .check import check
from .lexicon import fold, is_yes
from .tape import mmss

DONE_WORDS = {fold(w) for w in "पक्का पक्के पक्की pakka done".split()}
_MD = re.compile(r"([\\*_~`|<>\[\]()#])")
CHUNK = 1900  # Discord's limit is 2000


def esc(text) -> str:
    text = " ".join(str(text).split())
    return _MD.sub(r"\\\1", text).replace("@", "@​")


def _words(ws):
    return esc(" ".join(w.w for w in ws))


def chunks(lines):
    out, cur = [], ""
    for line in lines:
        if cur and len(cur) + len(line) + 1 > CHUNK:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


class Book:
    def __init__(self, dish: str, tape, draft, mom: str = "@Mom"):
        self.dish, self.tape, self.mom = dish, tape, mom
        self.result = check(tape, draft)
        self.lines = self.result.lines
        self.fills = {}  # line number -> (text, who)
        self.pending = None  # ("relay", n, text) | ("pakka",)
        self.page = None  # set once, when Mom releases it

    def name(self, n) -> str:
        ln = self.lines[n]
        return esc(ln.name_word.w if ln.name_word else ln.name_mr)

    def fillable(self):
        return [n for n, ln in enumerate(self.lines) if ln.status != "said"]

    def open_gaps(self):
        return [n for n in self.fillable() if n not in self.fills]

    # --- what Pothi posts after checking the draft ---

    def review(self) -> list:
        out = []
        for n, ln in enumerate(self.lines):
            name = self.name(n)
            if ln.status == "said":
                out += [f"> {_words(ln.quote)}", f"-# {name} · said {mmss(ln.at)}"]
            elif ln.status == "struck":
                out += [f"~~{esc(ln.claimed)}~~", f"-# {name} · {esc(ln.note)} · gap → Mom"]
            elif ln.quote:
                out += [f"> {_words(ln.quote)}", f'-# {name} · said {mmss(ln.at)} · "{esc(ln.note)}" · gap → Mom']
            else:
                out += [f"-# {name} · {esc(ln.note)} · gap → Mom"]
        for run in self.result.missed:
            out += [f"> {_words(run)}", f"-# missed by Lekhak {mmss(run[0].t)}"]
        gaps = self.open_gaps()
        if gaps:
            ask = f"{self.mom} " + " ".join(f"{self.name(n)}?" for n in gaps)
        else:
            self.pending = ("pakka",)
            ask = f"{self.mom} page pakka?"
        return chunks(out) + [ask]  # the ask on its own, so it can be sent as a mention

    # --- Mom and Tape ---

    def _match(self, text):
        """(line number, fill text) when the message starts with a fillable ingredient's name."""
        words = [w for w in text.split() if not w.startswith(("@", "<@"))]
        for n in self.fillable():
            ln = self.lines[n]
            names = {fold(ln.name_mr), ln.name_en.lower()}
            if ln.name_word:
                names.add(fold(ln.name_word.w))
            names.discard("")
            for k in (3, 2, 1):
                if len(words) > k and "".join(fold(w) for w in words[:k]) in {x.replace(" ", "") for x in names}:
                    return n, " ".join(words[k:]).strip(" ,:")
        return None, ""

    def _after_fill(self):
        if self.open_gaps():
            return []
        self.pending = ("pakka",)
        return [f"{self.mom} page pakka?"]

    def on_mom(self, text: str) -> list:
        if self.page is not None:
            return []
        if is_yes(text):
            pending, self.pending = self.pending, None
            if pending and pending[0] == "relay":
                _, n, fill = pending
                self.fills[n] = (fill, "Mom (relayed by Aryan)")
                return [f"**{esc(fill)}** — Mom"] + self._after_fill()
            if pending and pending[0] == "pakka":
                self.page = self.render()
                return []
            return []
        words = [fold(w) for w in text.split() if not w.startswith(("@", "<@"))]
        if len(words) == 1 and words[0] in DONE_WORDS:
            self.pending = ("pakka",)
            gaps = self.open_gaps()
            left = f" {len(gaps)} open: " + " · ".join(self.name(n) for n in gaps) if gaps else ""
            return [f"{self.mom} page pakka?{left}"]
        n, fill = self._match(text)
        if n is None or not fill:
            names = " · ".join(self.name(n) for n in self.fillable())
            return [f"{self.mom} कोणतं? {names}"] if names else []
        self.pending = None
        self.fills[n] = (fill, "Mom")
        return [f"**{esc(fill)}** — Mom"] + self._after_fill()

    def on_tape(self, text: str) -> list:
        """Tape's only line for Pothi besides "draft ready": "relayed by aryan: <name> <words>"."""
        if self.page is not None or not text.startswith("relayed by aryan:"):
            return []
        n, fill = self._match(text.split(":", 1)[1])
        if n is None or not fill:
            return []
        self.pending = ("relay", n, fill)
        return [f"{self.mom} बरोबर? {self.name(n)}: {esc(fill)} (relayed by Aryan)"]

    # --- the page ---

    def render(self) -> str:
        out = [f"**{esc(self.dish)}**", "-# Dadi's words from the tape, checked word by word by Pothi. Every amount is hers or Mom's. Mom approved this page.", ""]
        for n, ln in enumerate(self.lines):
            gloss = f"{esc(ln.name_en)} · " if ln.name_en else ""
            out.append(self.name(n))
            if ln.status == "said":
                out += [f"> {_words(ln.quote)}", f"-# {gloss}Dadi, {mmss(ln.at)}"]
            elif ln.quote:
                out += [f"> {_words(ln.quote)}", f'-# {gloss}Dadi, {mmss(ln.at)} · "{esc(ln.note)}"']
            else:
                out.append(f"-# {gloss}Dadi didn't say how much")
            if n in self.fills:
                fill, who = self.fills[n]
                out.append(f"**{esc(fill)}** — {who}")
            elif ln.status != "said":
                out.append("-# open: nobody measured it")
            out.append("")
        if self.result.steps:
            out.append("कृती")
            for step in self.result.steps:
                out += [f"> {_words(step)}", f"-# {mmss(step[0].t)}"]
            out.append("")
        if self.result.missed:
            out.append("-# Lekhak skipped these amounts. They're Dadi's, on the tape:")
            for run in self.result.missed:
                out += [f"> {_words(run)}", f"-# {mmss(run[0].t)}"]
            out.append("")
        out.append("-# English names are Lekhak's gloss.")
        return "\n".join(out).strip()
