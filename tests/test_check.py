import unittest

from jaisa.check import Word, check
from jaisa.lexicon import fold, is_yes, kind

# "besan, a quarter kilo; ghee by feel; sugar two vaatis; and cardamom, a pinch"
SAID = "बेसन पाव किलो घ्यायचं तूप अंदाजाने घालायचं साखर दोन वाट्या आणि वेलची चिमूटभर"
TAPE = [Word(i, w, 10.0 + i) for i, w in enumerate(SAID.split())]


def draft(*items):
    return {"ingredients": list(items)}


def item(name, q, **extra):
    return {"name_mr": name, "name_en": "", "quantity": q, **extra}


class Check(unittest.TestCase):
    def test_full_draft(self):
        r = check(TAPE, draft(
            item("बेसन", [1, 2]),
            item("तूप", [5, 5]),
            item("साखर", [8, 9]),
            item("वेलची", [12, 12]),
        ))
        self.assertEqual([ln.status for ln in r.lines], ["said", "gap", "said", "said"])
        self.assertEqual([w.w for w in r.lines[0].quote], ["पाव", "किलो"])
        self.assertEqual(r.lines[1].note, "by feel")
        self.assertEqual(r.lines[1].at, 15.0)
        self.assertEqual(r.missed, [])

    def test_typed_amount_is_struck(self):
        r = check(TAPE, draft(item("तूप", None, amount="1 cup")))
        self.assertEqual(r.lines[0].status, "struck")
        self.assertEqual(r.lines[0].note, "not on tape")
        self.assertIn("1 cup", r.lines[0].claimed)

    def test_tape_beats_the_label(self):
        # Lekhak calls the by-feel words an amount; the tape still says by feel
        r = check(TAPE, draft(item("तूप", {"words": [5, 5], "kind": "amount"})))
        self.assertEqual((r.lines[0].status, r.lines[0].note), ("gap", "by feel"))

    def test_citation_without_quantity_is_struck(self):
        r = check(TAPE, draft(item("तूप", [4, 4])))
        self.assertEqual(r.lines[0].note, "cited words hold no quantity")

    def test_bad_citations_are_struck(self):
        for q in ([20, 21], [3, 1], [-1, 0], [0, 9], ["1", "2"], [True, 2], [1], "1 cup"):
            with self.subTest(q=q):
                self.assertEqual(check(TAPE, draft(item("x", q))).lines[0].status, "struck")

    def test_wide_citation_is_trimmed(self):
        r = check(TAPE, draft(item("बेसन", [0, 3])))
        self.assertEqual([w.w for w in r.lines[0].quote], ["पाव", "किलो"])

    def test_not_said_is_a_gap(self):
        r = check(TAPE, draft(item("मीठ", None)))
        self.assertEqual((r.lines[0].status, r.lines[0].note), ("gap", "not said"))

    def test_lexicon_scan_flags_what_lekhak_skipped(self):
        r = check(TAPE, draft(item("बेसन", [1, 2]), item("साखर", [8, 9])))
        self.assertEqual([[w.w for w in run] for run in r.missed], [["अंदाजाने"], ["चिमूटभर"]])
        self.assertEqual(r.missed[0][0].t, 15.0)

    def test_bare_ek_is_not_a_quantity(self):
        tape = [Word(i, w, i) for i, w in enumerate("एक काम कर मग दोन वाट्या".split())]
        r = check(tape, draft())
        self.assertEqual([[w.w for w in run] for run in r.missed], [["दोन", "वाट्या"]])

    def test_garbage_draft(self):
        self.assertEqual(check(TAPE, "not json").lines, [])
        self.assertEqual(check(TAPE, {"ingredients": ["x", 3]}).lines, [])


class Lexicon(unittest.TestCase):
    def test_spelling_variants_fold_together(self):
        self.assertEqual(fold("वाट्‍या"), fold("वाट्या"))
        self.assertEqual(fold("थोडंसं"), fold("थोडसं"))
        self.assertEqual(fold("वाटी,"), fold("वाटी"))

    def test_kinds(self):
        self.assertEqual(kind("२"), "number")
        self.assertEqual(kind("1/2"), "number")
        self.assertEqual(kind("अर्धी"), "number")
        self.assertEqual(kind("वाटी।"), "unit")
        self.assertEqual(kind("चवीनुसार"), "vague")
        self.assertIsNone(kind("तूप"))

    def test_hundreds_are_numbers(self):
        for w in ("तीनशे", "अडीचशे", "शंभर", "हजार", "सहाशे"):
            with self.subTest(w=w):
                self.assertEqual(kind(w), "number")

    def test_only_a_plain_yes_is_yes(self):
        for t in ("हो", "@Pothi हो", "Ho", "हो.", "haan", "yes", "होय"):
            with self.subTest(t=t):
                self.assertTrue(is_yes(t))
        for t in ("नाही", "हो पण थांब", "", "@Pothi", "ho ho"):
            with self.subTest(t=t):
                self.assertFalse(is_yes(t))


if __name__ == "__main__":
    unittest.main()
