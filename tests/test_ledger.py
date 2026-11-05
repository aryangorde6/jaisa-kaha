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


if __name__ == "__main__":
    unittest.main()
