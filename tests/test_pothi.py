import re
import unittest

from jaisa.check import Word
from jaisa.pothi import CHUNK, TAG, YES_HOW, Book, esc, gap_how, page_messages
from jaisa.tape import from_doc, media_format, mmss, to_doc, words

SAID = "बेसन पाव किलो घ्यायचं तूप अंदाजाने घालायचं साखर दोन वाट्या आणि वेलची चिमूटभर"
TAPE = [Word(i, w, 70.0 + i) for i, w in enumerate(SAID.split())]
# Qwen's real answer to prompt lekhak-v1 on this sentence (Thu 5 Nov)
DRAFT = {
    "ingredients": [
        {"name_mr": "बेसन", "name_at": 0, "name_en": "besan", "quantity": [1, 2]},
        {"name_mr": "तूप", "name_at": 4, "name_en": "ghee", "quantity": [5, 5]},
        {"name_mr": "साखर", "name_at": 7, "name_en": "sugar", "quantity": [8, 9]},
        {"name_mr": "वेलची", "name_at": 11, "name_en": "cardamom", "quantity": [12, 12]},
    ],
    "steps": [[0, 2], [4, 5], [7, 9], [11, 12]],
}


class Flow(unittest.TestCase):
    def test_review_asks_mom_for_the_gap_only(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        msg = "\n".join(b.review())
        self.assertIn("-# तूप · said 01:15 · \"by feel\" · gap → Mom", msg)
        self.assertTrue(msg.endswith("@Mom तूप?\n" + gap_how("तूप")))
        self.assertIsNone(b.pending)

    def test_moms_fill_then_yes_releases_the_page(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        b.review()
        self.assertEqual(b.on_mom("@Pothi तूप अर्धी वाटी, स्टीलची"), ["**अर्धी वाटी, स्टीलची** — Mom", "@Mom page pakka?\n" + YES_HOW])
        self.assertIsNone(b.page)
        self.assertEqual(b.on_mom("हो"), [])
        self.assertIn("> अंदाजाने", b.page)
        self.assertIn("**अर्धी वाटी, स्टीलची** — Mom", b.page)
        self.assertEqual(b.on_mom("@Pothi तूप एक वाटी"), [])  # written once

    def test_relay_needs_moms_yes(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        b.review()
        self.assertEqual(b.on_tape("relayed by aryan: तूप अर्धी वाटी"), ["@Mom बरोबर? तूप: अर्धी वाटी (relayed by Aryan)\n" + YES_HOW])
        self.assertEqual(b.fills, {})
        self.assertEqual(b.on_mom("हो")[0], "**अर्धी वाटी** — Mom")
        self.assertEqual(b.fills[1], ("अर्धी वाटी", "Mom (relayed by Aryan)"))

    def test_relay_dropped_when_mom_says_something_else(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        b.on_tape("relayed by aryan: तूप एक कप")
        b.on_mom("@Pothi तूप अर्धी वाटी")
        self.assertEqual(b.fills[1], ("अर्धी वाटी", "Mom"))

    def test_a_typed_fill_cannot_overwrite_the_tape(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        self.assertEqual(b.on_mom("@Pothi साखर तीन वाट्या"), ["@Mom कोणतं? तूप\n" + gap_how("तूप")])
        self.assertEqual(b.fills, {})

    def test_pakka_with_gaps_open_lists_them(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        self.assertEqual(b.on_mom("पक्का"), ["@Mom page pakka? 1 open: तूप\n" + YES_HOW])
        b.on_mom("ho")
        self.assertIn("-# open: nobody measured it", b.page)

    def test_stray_yes_does_nothing(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        b.review()
        self.assertEqual(b.on_mom("हो"), [])
        self.assertIsNone(b.page)

    def test_struck_amount_shown_in_review_not_on_page(self):
        b = Book("x", TAPE, {"ingredients": [{"name_mr": "तूप", "name_at": 4, "name_en": "ghee", "quantity": None, "amount": "1 cup"}]})
        self.assertIn("~~1 cup~~", "\n".join(b.review()))
        b.on_mom("pakka")
        b.on_mom("हो")
        self.assertNotIn("1 cup", b.page)

    def test_model_text_cannot_ping_or_format(self):
        self.assertEqual(esc("@everyone **x**"), "@​everyone \\*\\*x\\*\\*")
        b = Book("x", TAPE, {"ingredients": [{"name_mr": "तूप", "name_en": "<@123> [a](http://x)", "quantity": [5, 5]}]})
        b.on_mom("pakka")
        b.on_mom("हो")
        self.assertNotIn("<@123>", b.page)
        self.assertNotIn("](http", b.page)

    def test_name_comes_from_the_tape(self):
        draft = {"ingredients": [{"name_mr": "लोणी", "name_at": 4, "name_en": "butter", "quantity": [5, 5]}]}
        self.assertTrue(Book("x", TAPE, draft).review()[0].count("-# तूप ·"))


# Switch's own mention pattern (clients/mentions.py, 0.31.0): an @ followed
# straight away by name characters.
SWITCH_MENTION = re.compile(r"@([A-Za-z0-9._-]+)")


class MomKnowsHowToAnswer(unittest.TestCase):
    """Only a message that tags Pothi reaches it: this server runs without
    "follow the conversation", and a Discord Reply carries no mention. So every
    question says how to answer, and Pothi never writes a real mention of an
    agent, which Switch would route to it or refuse in the room."""

    def every_message(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        msgs = b.review()
        msgs += b.on_mom("@Pothi अर्धी तूप वाटी")  # the name at neither end: कोणतं?
        msgs += b.on_tape("relayed by aryan: तूप अर्धी वाटी")
        msgs += b.on_mom("@Pothi अर्धी वाटी तूप")
        msgs += b.on_mom("पक्का")
        b.on_mom("हो")
        return msgs + [b.page]

    def test_every_question_says_how_to_answer(self):
        asks = [m for m in self.every_message() if m.startswith("@Mom ")]
        self.assertEqual(len(asks), 5)
        for m in asks:
            self.assertIn(f"\n-# उत्तर: {TAG} ", m)

    def test_pothi_never_tags_an_agent(self):
        for m in self.every_message():
            self.assertFalse({t.lower() for t in SWITCH_MENTION.findall(m)} & {"pothi", "tape", "lekhak"}, m)
        self.assertIsNone(SWITCH_MENTION.match(TAG))

    def test_the_name_may_come_last(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        self.assertEqual(b.on_mom("@Pothi अर्धी वाटी तूप"), ["**अर्धी वाटी** — Mom", "@Mom page pakka?\n" + YES_HOW])
        self.assertEqual(b.fills[1], ("अर्धी वाटी", "Mom"))

    def test_a_name_in_the_middle_is_asked_about(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        self.assertEqual(b.on_mom("@Pothi अर्धी तूप वाटी"), ["@Mom कोणतं? तूप\n" + gap_how("तूप")])
        self.assertEqual(b.fills, {})


class PageInTheRoom(unittest.TestCase):
    """The page is posted in the room as well, since no phone can open the document."""

    def test_a_short_page_is_one_message(self):
        b = Book("बेसन लाडू", TAPE, DRAFT)
        b.review()
        b.on_mom("@Pothi तूप अर्धी वाटी, स्टीलची")
        b.on_mom("हो")
        self.assertEqual(page_messages(b.page), [b.page])

    def test_a_long_page_is_cut_between_ingredients(self):
        blocks = [f"साखर {i}\n> {'साखर दोन वाट्या ' * 6}\n-# sugar · Mom, 01:{i:02d}" for i in range(60)]
        page = "\n\n".join(blocks)
        msgs = page_messages(page)
        self.assertGreater(len(msgs), 1)
        self.assertTrue(all(len(m) <= CHUNK for m in msgs))
        self.assertEqual("\n\n".join(msgs), page)
        starts = {blk.split("\n")[0] for blk in blocks}
        self.assertTrue(all(m.split("\n")[0] in starts for m in msgs))

    def test_a_line_longer_than_a_message_is_cut_at_spaces(self):
        line = " ".join(f"शब्द{i}" for i in range(900))
        msgs = page_messages(line)
        self.assertGreater(len(msgs), 1)
        self.assertTrue(all(len(m) <= CHUNK for m in msgs))
        self.assertEqual(" ".join(msgs), line)


class Tape(unittest.TestCase):
    TRANSCRIBE = {
        "results": {
            "transcripts": [{"transcript": "तूप अंदाजाने."}],
            "items": [
                {"type": "pronunciation", "start_time": "1.25", "end_time": "1.6", "alternatives": [{"content": "तूप"}]},
                {"type": "pronunciation", "start_time": "1.6", "end_time": "2.4", "alternatives": [{"content": "अंदाजाने"}]},
                {"type": "punctuation", "alternatives": [{"content": "."}]},
            ],
        }
    }

    def test_words_drop_punctuation(self):
        self.assertEqual(words(self.TRANSCRIBE), [Word(0, "तूप", 1.25), Word(1, "अंदाजाने", 1.6)])

    def test_vocabulary_phrases_split_into_words(self):
        # Transcribe returns a custom-vocabulary phrase as one hyphenated token.
        from jaisa.lexicon import kind
        item = {"type": "pronunciation", "start_time": "2.5", "alternatives": [{"content": "पाव-किलो"}]}
        got = words({"results": {"items": [item]}})
        self.assertEqual(got, [Word(0, "पाव", 2.5), Word(1, "किलो", 2.5)])
        self.assertEqual([kind(w.w) for w in got], ["number", "unit"])

    def test_doc_round_trip(self):
        self.assertEqual(from_doc(to_doc(TAPE)), TAPE)

    def test_doc_rejects_gaps_and_junk(self):
        for doc in ("[1] 0.00 तूप", "[0] 0.00 तूप\n[2] 1.00 x", "[0] 0.00 two words", "hello"):
            with self.subTest(doc=doc):
                with self.assertRaises(ValueError):
                    from_doc(doc)

    def test_formats(self):
        self.assertEqual(media_format("voice-message.ogg"), "ogg")
        self.assertEqual(media_format("a.M4A"), "mp4")
        with self.assertRaises(ValueError):
            media_format("evil.html")

    def test_mmss(self):
        self.assertEqual(mmss(75.9), "01:15")


if __name__ == "__main__":
    unittest.main()
