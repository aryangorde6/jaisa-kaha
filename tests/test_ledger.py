import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jaisa import ledger
from jaisa.ledger import invented, page_numbers_unquoted
from jaisa.tape import to_doc
from tests.test_pothi import TAPE

CARD = """**Besan Ladoo**

### Ingredients:
- **Gram flour (Besan)** – 1 kg
- **Ghee** – as needed
- **Sugar** – 2 cups

### Instructions:
1. Roast the besan in ghee for 15 minutes.
2. **Add Ghee** slowly.
"""


class Ledger(unittest.TestCase):
    def test_only_the_ingredient_line_counts(self):
        self.assertEqual(invented(CARD, ["ghee"]), [])
        self.assertEqual(invented(CARD, ["sugar"]), ["**Sugar** – 2 cups"])

    def test_number_words_and_fractions_count(self):
        self.assertTrue(invented("Ingredients\n- ghee, half a cup", ["ghee"]))
        self.assertTrue(invented("Ingredients\n- ghee ¾ cup", ["ghee"]))
        self.assertFalse(invented("Ingredients\n- ghee, to taste", ["ghee"]))

    def test_card_without_headers_uses_every_line(self):
        self.assertTrue(invented("ghee 1 cup\nsugar", ["ghee"]))

    def test_page_numbers_must_be_quoted_or_moms(self):
        page = "**x**\n> दोन वाट्या\n**1 वाटी** — Mom\n-# 00:12\nतूप 2 cups"
        self.assertEqual(page_numbers_unquoted(page), ["तूप 2 cups"])



class OneRoom(unittest.TestCase):
    """make ledger counts the family room's tapes and nothing else."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        for room, dish, words in (("family", "बेसन लाडू", TAPE), ("dev", "s8 test", TAPE[:3])):
            (tmp / "tapes" / room).mkdir(parents=True)
            (tmp / "tapes" / room / "tape-1.txt").write_text(f"{dish}\n{to_doc(words)}")
        (tmp / "tapes" / "tape-2.txt").write_text(f"stray\n{to_doc(TAPE)}")
        mock.patch.object(ledger, "DATA", tmp).start()
        self.addCleanup(mock.patch.stopall)

    def test_only_the_ledger_rooms_tapes_count(self):
        self.assertEqual([(t, d, len(w)) for t, d, w in ledger.tapes("family")], [("tape-1", "बेसन लाडू", len(TAPE))])

    def test_no_ledger_room_no_ledger(self):
        with mock.patch.object(ledger, "ROOM", ""), self.assertRaises(SystemExit):
            list(ledger.tapes())

    def test_a_saved_run_belongs_to_one_transcript(self):
        # a tape-1 in a new room must not reuse the saved runs of another room's tape-1
        model = ledger.MODELS[0]
        self.assertNotEqual(ledger.run_path("tape-1", "lekhak-v1", model, TAPE), ledger.run_path("tape-1", "lekhak-v1", model, TAPE[:3]))
        self.assertEqual(ledger.run_path("tape-1", "lekhak-v1", model, TAPE), ledger.run_path("tape-1", "lekhak-v1", model, list(TAPE)))


class Report(unittest.TestCase):
    """make ledger report: ledger.json carries ledger.md's counts and no word of the tape."""

    def test_report_counts_and_json(self):
        import json
        from tests.test_pothi import DRAFT
        tmp = Path(tempfile.mkdtemp())
        (tmp / "data" / "tapes" / "family").mkdir(parents=True)
        (tmp / "data" / "tapes" / "family" / "tape-1.txt").write_text(f"बेसन लाडू\n{to_doc(TAPE)}")
        (tmp / "data" / "pages" / "family").mkdir(parents=True)
        (tmp / "data" / "pages" / "family" / "page-1.md").write_text("**x**\n> दोन वाट्या\n**1 वाटी** — Mom\nतूप 2 cups")
        with mock.patch.object(ledger, "DATA", tmp / "data"), mock.patch.object(ledger, "ROOT", tmp), \
                mock.patch.object(ledger, "ROOM", "family"), mock.patch("builtins.print"):
            save = lambda prompt, model, raw: (lambda p: (p.parent.mkdir(parents=True, exist_ok=True), p.write_text(json.dumps({"raw": raw}))))(
                ledger.run_path("tape-1", prompt, model, TAPE))
            save("lekhak-v1", ledger.MODELS[0], json.dumps(DRAFT, ensure_ascii=False))
            save("baseline-v2", ledger.MODELS[0], "Ingredients\n- Ghee (तूप) 1 cup\n- Besan 250 g")
            save("baseline-v2", ledger.MODELS[1], "Ingredients\n- Ghee, to taste")
            ledger.report()
        out = json.loads((tmp / "ledger.json").read_text())
        ref = ledger.check(TAPE, ledger.lekhak.parse(json.dumps(DRAFT, ensure_ascii=False)))
        feel = sum(ln.status == "gap" for ln in ref.lines)
        self.assertEqual((out["dishes"], out["amounts"], out["no_measure"]), (1, len(ref.lines), feel))
        self.assertGreater(feel, 0)
        m0, m1, m2 = ledger.MODELS[:3]
        self.assertEqual(out["plain_turned_into_numbers"][m0], 1)  # ghee by feel became "1 cup"
        self.assertEqual(out["plain_turned_into_numbers"][m1], 0)  # "to taste" has no number
        self.assertEqual((out["plain_asked_about"][m0], out["plain_asked_about"][m1], out["plain_asked_about"][m2]), (feel, feel, 0))
        self.assertEqual((out["pages"], out["page_numbers_not_hers"]), (1, 1))  # "तूप 2 cups" is nobody's
        self.assertEqual(set(out["prompts"]), set(ledger.PROMPTS))
        self.assertIn(f"{feel} of {len(ref.lines)} amounts", (tmp / "ledger.md").read_text())
        text = (tmp / "ledger.json").read_text()
        self.assertFalse(any(w.w in text for w in TAPE), "a word of the tape leaked into ledger.json")


if __name__ == "__main__":
    unittest.main()
