import unittest

from jaisa.check import Word
from jaisa.s8 import PHRASES, amount, score


def words(text):
    return [Word(i, w, i * 0.5) for i, w in enumerate(text.split())]


class S8(unittest.TestCase):
    def test_every_line_has_an_amount(self):
        self.assertEqual(len(PHRASES), 20)
        for p in PHRASES:
            with self.subTest(p=p):
                self.assertTrue(amount(p))

    def test_perfect_take(self):
        self.assertTrue(all(ok for _, ok, _ in score(words(" ".join(PHRASES)))))

    def test_one_wrong_line_doesnt_derail_the_rest(self):
        heard = list(PHRASES)
        heard[3] = "वेलची चिमटा भर"  # line 4 misheard; line 18 also says चिमूटभर
        r = score(words(" ".join(heard)))
        self.assertEqual([n for n, (_, ok, _) in enumerate(r, 1) if not ok], [4])

    def test_spelling_variant_still_counts(self):
        r = score(words("साखर दोन वाट्‍या"), ["साखर दोन वाट्या"])
        self.assertTrue(r[0][1])


if __name__ == "__main__":
    unittest.main()
