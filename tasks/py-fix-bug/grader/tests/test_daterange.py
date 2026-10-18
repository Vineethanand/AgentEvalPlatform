import unittest

from daterange import days_between


class T(unittest.TestCase):
    def test_same_month(self):
        self.assertEqual(days_between("2024-03-01", "2024-03-15"), 14)

    def test_month_boundary(self):
        self.assertEqual(days_between("2024-01-30", "2024-02-02"), 3)

    def test_leap_year(self):
        self.assertEqual(days_between("2024-02-28", "2024-03-01"), 2)

    def test_year(self):
        self.assertEqual(days_between("2023-01-01", "2024-01-01"), 365)

    def test_negative(self):
        self.assertEqual(days_between("2024-03-10", "2024-03-01"), -9)
