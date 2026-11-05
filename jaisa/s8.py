"""S8: how well Transcribe mr-IN hears Marathi amounts.

python -m jaisa.s8 audio/s8-quiet.m4a [vocabulary-name] > s8-quiet.md

The take is the 20 lines below, read in order with a pause between them. A
line counts as right when its amount words come out exactly (after fold),
next to each other, within a few words of where the last line ended. Every
line is printed beside what Transcribe heard, for the hand-check S8 asks for.
"""

import json
import sys
from pathlib import Path

from .lexicon import fold, kind
from .tape import transcribe

PHRASES = [
    "बेसन पाव किलो", "साखर दोन वाट्या", "तूप अंदाजाने", "वेलची चिमूटभर", "मीठ चवीनुसार",
    "पाणी एक ग्लास", "हळद अर्धा चमचा", "तिखट एक चमचा", "रवा दीड वाटी", "गूळ अडीच वाट्या",
    "खोबरं मूठभर", "दूध अर्धा लिटर", "जिरं थोडंसं", "शेंगदाणे सव्वा वाटी", "मैदा साडे तीन वाट्या",
    "तेल पावणे दोन वाट्या", "पोहे तीन वाट्या", "ओवा चिमूटभर", "तीळ दोन चमचे", "हिंग जरासं",
]
WINDOW = 10  # how far past the last match a line may start


def amount(phrase):
    return [fold(w) for w in phrase.split() if kind(w)]


def score(words, phrases=PHRASES):
    """[(phrase, right, heard words)] for each line, in order."""
    heard = [fold(w.w) for w in words]
    out, pos = [], 0
    for phrase in phrases:
        want, n = amount(phrase), len(amount(phrase))
        hit = next((j for j in range(pos, min(pos + WINDOW, len(heard) - n + 1)) if heard[j : j + n] == want), None)
        if hit is None:
            out.append((phrase, False, [w.w for w in words[pos : pos + len(phrase.split())]]))
        else:
            start = max(hit - 1, pos)
            out.append((phrase, True, [w.w for w in words[start : hit + n]]))
            pos = hit + n
    return out


def report(name, results):
    right = sum(ok for _, ok, _ in results)
    lines = [f"### {name}: {right}/{len(results)} amounts right", "", "| # | Said | Heard | Amount right |", "|---|---|---|---|"]
    lines += [f"| {i} | {p} | {' '.join(h)} | {'yes' if ok else '**no**'} |" for i, (p, ok, h) in enumerate(results, 1)]
    return right, "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m jaisa.s8 <audio file> [vocabulary name]")
    path = Path(sys.argv[1])
    audio = path.read_bytes()
    runs = [("no vocabulary", "")]
    if len(sys.argv) > 2:
        runs.append((f"vocabulary {sys.argv[2]}", sys.argv[2]))
    print(f"## S8 · {path.name}\n")
    for name, vocab in runs:
        words = transcribe(audio, path.name, poll=3, vocabulary=vocab)
        right, table = report(name, score(words))
        print(table, "\n")
        print(f"<details><summary>Full transcript ({len(words)} words)</summary>\n\n{' '.join(w.w for w in words)}\n\n</details>\n")
        print(json.dumps({"take": path.name, "run": name, "right": right, "of": len(PHRASES)}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
