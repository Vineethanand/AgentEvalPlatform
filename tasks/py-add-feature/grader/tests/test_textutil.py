import unittest

from textutil import slugify, word_count


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_runs(self):
        self.assertEqual(slugify("  Rock & Roll -- Forever!  "), "rock-roll-forever")

    def test_digits_kept(self):
        self.assertEqual(slugify("Top 10 Tips, 2024"), "top-10-tips-2024")

    def test_empty_result(self):
        self.assertEqual(slugify("!!! ???"), "untitled")
        self.assertEqual(slugify(""), "untitled")

    def test_word_count_untouched(self):
        self.assertEqual(word_count("a b  c"), 3)


if __name__ == "__main__":
    unittest.main()
