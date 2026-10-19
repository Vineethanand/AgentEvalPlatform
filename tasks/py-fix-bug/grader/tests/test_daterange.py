"""Hidden tests for py-fix-bug: days_between must count whole days correctly in the edge cases it got wrong."""
import unittest

from daterange import days_between  # pylint: disable=import-error  # lives in the workspace


class T(unittest.TestCase):
    """days_between(start, end) returns end minus start in days."""

    def test_same_month(self):
        """Two dates in one month."""
        self.assertEqual(days_between("2024-03-01", "2024-03-15"), 14)

    def test_month_boundary(self):
        """The range crosses from January into February."""
        self.assertEqual(days_between("2024-01-30", "2024-02-02"), 3)

    def test_leap_year(self):
        """2024 has a 29 February, so 28 Feb to 1 Mar is two days."""
        self.assertEqual(days_between("2024-02-28", "2024-03-01"), 2)

    def test_year(self):
        """A non-leap year has 365 days."""
        self.assertEqual(days_between("2023-01-01", "2024-01-01"), 365)

    def test_negative(self):
        """An end date before the start gives a negative number."""
        self.assertEqual(days_between("2024-03-10", "2024-03-01"), -9)
