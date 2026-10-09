import unittest

from slugtool import slugify


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_collapses(self):
        self.assertEqual(slugify("Hello,  World!! Again"), "hello-world-again")

    def test_trim(self):
        self.assertEqual(slugify("  --Hello--  "), "hello")


if __name__ == "__main__":
    unittest.main()
