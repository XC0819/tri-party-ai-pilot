import unittest

from review_relay.workflow import decide_action


class WorkflowTests(unittest.TestCase):
    def test_pending_waits(self):
        self.assertEqual(decide_action("pending", 0), "wait")

    def test_approve_awaits_user(self):
        self.assertEqual(decide_action("approve", 0), "await_user_approval")

    def test_first_request_reworks(self):
        self.assertEqual(decide_action("request_changes", 0), "rework")

    def test_below_default_limit_reworks(self):
        self.assertEqual(decide_action("request_changes", 1), "rework")

    def test_at_default_limit_escalates(self):
        self.assertEqual(decide_action("request_changes", 2), "escalate")

    def test_above_limit_escalates(self):
        self.assertEqual(decide_action("request_changes", 3), "escalate")

    def test_zero_limit_escalates(self):
        self.assertEqual(decide_action("request_changes", 0, 0), "escalate")

    def test_custom_limit_reworks(self):
        self.assertEqual(decide_action("request_changes", 2, 3), "rework")

    def test_custom_boundary_escalates(self):
        self.assertEqual(decide_action("request_changes", 1, 1), "escalate")

    def test_unknown_verdict_is_invalid(self):
        with self.assertRaises(ValueError):
            decide_action("merge", 0)

    def test_negative_count_is_invalid(self):
        with self.assertRaises(ValueError):
            decide_action("pending", -1)

    def test_negative_limit_is_invalid(self):
        with self.assertRaises(ValueError):
            decide_action("approve", 0, -1)


if __name__ == "__main__":
    unittest.main()
