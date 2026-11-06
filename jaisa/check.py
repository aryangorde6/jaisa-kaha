"""Pothi's check: every quantity in Lekhak's draft must be Mom's own words on the tape.

Lekhak never retypes a quantity. It cites a word range in Tape's transcript,
and Pothi reads those words itself. The tape decides, not Lekhak's label:
- the cited words hold a number or a unit      -> "said"
- the cited words hold a by-feel word           -> "gap", asked of Mom
- Lekhak said nothing about the amount          -> "gap" ("not said")
- a bad citation, or an amount typed by Lekhak  -> "struck"
Then a lexicon scan flags quantity words on the tape that no line cites.
Names and method steps are cited the same way, so the page shows Mom's own
words wherever it can, and Lekhak's text only as a labelled English gloss.
"""

from dataclasses import dataclass, field

from .lexicon import kind

MAX_SPAN = 6
MAX_STEP_SPAN = 60
# Keys a draft may carry per ingredient. Anything else that looks like an
# amount ("amount": "1 cup") is Lekhak typing a quantity, and gets struck.
_ALLOWED = {"name_mr", "name_en", "name_at", "quantity"}


@dataclass(frozen=True)
class Word:
    i: int
    w: str
    t: float  # seconds into the voice note


@dataclass
class Line:
    name_mr: str
    name_en: str
    status: str  # "said" | "gap" | "struck"
    note: str = ""
    quote: list = field(default_factory=list)  # the tape's Words
    claimed: str = ""  # what Lekhak typed, when struck
    name_word: Word = None  # the tape's word for the ingredient, when cited

    @property
    def at(self):
        return self.quote[0].t if self.quote else None


@dataclass
class Result:
    lines: list
    missed: list  # runs of Words that hold a quantity no line cites
    steps: list = field(default_factory=list)  # lists of Words, Mom's method
    bad_steps: int = 0


def _trim(words):
    """Drop leading and trailing words that aren't quantity words."""
    ks = [kind(w.w) for w in words]
    idx = [n for n, k in enumerate(ks) if k]
    return words[idx[0] : idx[-1] + 1] if idx else []


def _range(q, tape, span):
    return (
        isinstance(q, list)
        and len(q) == 2
        and all(isinstance(n, int) and not isinstance(n, bool) for n in q)
        and 0 <= q[0] <= q[1] < len(tape)
        and q[1] - q[0] < span
    )


def _line(item, tape):
    line = _quantity(item, tape)
    at = item.get("name_at")
    if isinstance(at, int) and not isinstance(at, bool) and 0 <= at < len(tape):
        line.name_word = tape[at]
    return line


def _quantity(item, tape):
    name_mr = str(item.get("name_mr", "")).strip()
    name_en = str(item.get("name_en", "")).strip()
    extra = {k: v for k, v in item.items() if k not in _ALLOWED}
    if extra:
        claimed = " ".join(str(v) for v in extra.values())
        return Line(name_mr, name_en, "struck", "not on tape", claimed=claimed)

    q = item.get("quantity")
    if q is None or q == "by_feel":
        return Line(name_mr, name_en, "gap", "not said")
    if isinstance(q, dict):
        q = q.get("words")
    if not _range(q, tape, MAX_SPAN):
        return Line(name_mr, name_en, "struck", "bad citation", claimed=str(q))

    words = _trim(tape[q[0] : q[1] + 1])
    if not words:
        return Line(name_mr, name_en, "struck", "cited words hold no quantity", claimed=str(q))
    if any(kind(w.w) == "vague" for w in words):
        return Line(name_mr, name_en, "gap", "by feel", quote=words)
    return Line(name_mr, name_en, "said", quote=words)


def _missed(tape, cited):
    """Runs of quantity words that no line cites. A bare number only counts
    when a unit follows within two words, since एक also means "a"."""
    runs, run = [], []
    for w in tape:
        k = kind(w.w)
        if k and w.i not in cited:
            run.append(w)
            continue
        if run:
            runs.append(run)
        run = []
    if run:
        runs.append(run)

    out = []
    for r in runs:
        kinds = {kind(w.w) for w in r}
        if kinds & {"unit", "vague"} or any(w.w.strip().isdigit() for w in r):
            out.append(r)
            continue
        last = r[-1].i
        nxt = [kind(w.w) for w in tape[last + 1 : last + 3]]
        if "unit" in nxt:
            out.append(r)
    return out


def check(tape, draft) -> Result:
    tape = [w if isinstance(w, Word) else Word(**w) for w in tape]
    items = draft.get("ingredients", []) if isinstance(draft, dict) else []
    lines = [_line(it, tape) for it in items if isinstance(it, dict)]
    cited = {w.i for ln in lines for w in ln.quote}
    raw_steps = draft.get("steps", []) if isinstance(draft, dict) else []
    raw_steps = raw_steps if isinstance(raw_steps, list) else []
    steps = [tape[q[0] : q[1] + 1] for q in raw_steps if _range(q, tape, MAX_STEP_SPAN)]
    return Result(lines, _missed(tape, cited), steps, len(raw_steps) - len(steps))
