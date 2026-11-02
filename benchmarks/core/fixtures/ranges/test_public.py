import unittest
from solution import parse_range
class Public(unittest.TestCase):
    def test_inclusive(self): self.assertEqual(parse_range("2:4"), [2,3,4])
    def test_bad(self):
        with self.assertRaises(ValueError): parse_range("4:2")
