"""Hidden tests for py-add-feature: the new slugify function, and that word_count still works."""
import unittest

from textutil import slugify, word_count  # pylint: disable=import-error  # lives in the workspace


class SlugifyTests(unittest.TestCase):
    """slugify turns a title into a lower-case, hyphen-separated URL slug."""

    def test_basic(self):
        """Words are lower-cased and joined with a hyphen."""
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_runs(self):
        """Runs of punctuation and spaces collapse to one hyphen, with none at the ends."""
        self.assertEqual(slugify("  Rock & Roll -- Forever!  "), "rock-roll-forever")

    def test_digits_kept(self):
        """Digits are part of the slug."""
        self.assertEqual(slugify("Top 10 Tips, 2024"), "top-10-tips-2024")

    def test_empty_result(self):
        """A title with no letters or digits becomes "untitled"."""
        self.assertEqual(slugify("!!! ???"), "untitled")
        self.assertEqual(slugify(""), "untitled")

    def test_word_count_untouched(self):
        """Adding slugify must not break the existing word_count."""
        self.assertEqual(word_count("a b  c"), 3)


if __name__ == "__main__":
    unittest.main()
