import unittest

from slugtool import truncate_slug


class TestTruncateSlug(unittest.TestCase):
    def test_last_boundary_within_limit(self):
        self.assertEqual(truncate_slug("the-quick-brown-fox", 10), "the-quick")

    def test_first_boundary_at_limit(self):
        self.assertEqual(truncate_slug("the-quick-brown-fox", 3), "the")

    def test_boundary_at_limit(self):
        self.assertEqual(truncate_slug("hello-world", 5), "hello")

    def test_boundary_before_limit(self):
        self.assertEqual(truncate_slug("hello-world", 6), "hello")

    def test_hard_cut_without_boundary(self):
        self.assertEqual(truncate_slug("helloworld", 5), "hello")

    def test_short_slug_unchanged(self):
        self.assertEqual(truncate_slug("hello", 10), "hello")

    def test_zero_limit(self):
        self.assertEqual(truncate_slug("hello-world", 0), "")

    def test_negative_limit(self):
        self.assertEqual(truncate_slug("hello-world", -1), "")

    def test_exact_length_unchanged(self):
        self.assertEqual(truncate_slug("hello-", 6), "hello-")

    def test_repeated_hyphens_do_not_leave_trailing_hyphen(self):
        self.assertEqual(truncate_slug("hello--world", 7), "hello")

    def test_empty_slug(self):
        self.assertEqual(truncate_slug("", 5), "")


if __name__ == "__main__":
    unittest.main()
