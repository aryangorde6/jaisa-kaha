import unittest

from jaisa.ledger import invented, page_numbers_unquoted

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


if __name__ == "__main__":
    unittest.main()
