"""Marathi quantity words, and the folding that makes Transcribe's spellings compare equal.

Transcribe's mr-IN model writes numbers as words, and spells the same word in
more than one way (with or without nukta, anusvara, ZWJ). Everything Pothi
compares goes through fold() first.
"""

import re
import unicodedata

# nukta, chandrabindu, anusvara, ZWNJ, ZWJ
_DROP = dict.fromkeys(map(ord, "़ँं‌‍"), None)
_PUNCT = re.compile(r"[\s।॥,.;:!?\"'()\[\]{}\-–—]+")
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NUMERAL = re.compile(r"^\d+([./]\d+)?$|^[½¼¾]$")


def fold(word: str) -> str:
    w = unicodedata.normalize("NFC", word).translate(_DROP)
    return _PUNCT.sub("", w).translate(_DEV_DIGITS).lower()


def _folded(words):
    return frozenset(fold(w) for w in words.split())


NUMBERS = {
    fold(k): v
    for k, v in {
        "एक": 1, "दोन": 2, "तीन": 3, "चार": 4, "पाच": 5,
        "सहा": 6, "सात": 7, "आठ": 8, "नऊ": 9, "दहा": 10,
        "अर्धा": 0.5, "अर्धी": 0.5, "अर्धे": 0.5, "अर्ध": 0.5,
        "पाव": 0.25, "दीड": 1.5, "अडीच": 2.5,
        # modifiers on the next number: sava = +1/4, sade = +1/2, paavne = -1/4
        "सव्वा": 1.25, "साडे": 0.5, "पावणे": 0.75,
    }.items()
}

UNITS = _folded(
    "वाटी वाट्या वाटीभर कप कपभर चमचा चमचे चमचाभर टीस्पून टेबलस्पून "
    "मूठ मुठ मूठभर मुठभर चिमूट चिमूटभर चिमटी चिमटीभर किलो ग्रॅम ग्राम "
    "लिटर मिली पेला पेलाभर ग्लास डाव पळी पळीभर नग"
)

# Words that mean "by feel": Pothi turns these into a gap for Mom, never a number.
VAGUE = _folded(
    "अंदाजाने अंदाजे अंदाज थोडं थोडंसं थोडसं थोडा थोडी थोडे जरासं जरा "
    "चवीनुसार आवडीनुसार गरजेनुसार हवं हवे तेवढं लागेल तसं"
)

# Mom's yes. Anything else is not a yes.
YES = _folded("हो हों होय ho hoy haan han yes")


def kind(word: str):
    """'number', 'unit', 'vague' or None."""
    w = fold(word)
    if w in VAGUE:
        return "vague"
    if w in UNITS:
        return "unit"
    if w in NUMBERS or _NUMERAL.match(w):
        return "number"
    return None


def is_yes(text: str) -> bool:
    words = [fold(w) for w in text.split() if not w.startswith(("@", "<@"))]
    words = [w for w in words if w]
    return len(words) == 1 and words[0] in YES
