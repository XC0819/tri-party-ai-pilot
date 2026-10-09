from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_relay.audit import BRANCH, REPO
from review_relay.poll import guard_pr, normalize, receive, run_poll
from test_audit import HEAD, SINCE, body, record


def state():
    return dict(task_id="TASK-20261010-004", pr_number=5, head_sha=HEAD, round=1,
                rework_count=0, round_started_at=SINCE, processed=[], receipts=[],
                poll_count=0, deadline=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())


def pr():
    return dict(number=5, state="open", merged=False, merged_at=None,
                head=dict(sha=HEAD, ref=BRANCH, repo=dict(full_name=REPO)), base=dict(ref="main"))


class PollTests(unittest.TestCase):
    def test_guard_accepts_open_unmerged_expected_head(self):
        guard_pr(pr(), state())

    def test_guard_stops_on_merged_closed_or_changed_head(self):
        for change in (dict(merged=True), dict(state="closed"),
                       dict(head=dict(sha="b" * 40, ref=BRANCH, repo=dict(full_name=REPO))),
                       dict(base=dict(ref="different")), dict(number=6)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                guard_pr({**pr(), **change}, state())

    def test_review_publication_time_and_draft_filter(self):
        items = [dict(id=1, submitted_at=SINCE, body=body()), dict(id=2, body=body())]
        result = normalize(items, "review")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["record_id"], "review:1")

    def test_first_rework_receipt_does_not_execute_notes(self):
        current = state()
        receipt, _ = receive(current, [record()], "2026-10-09T17:00:05Z")
        self.assertEqual(receipt["action"], "rework")
        self.assertTrue(receipt["requires_scope_check"])
        self.assertEqual(receipt["latency_seconds"], 4)
        self.assertEqual(current["rework_count"], 0)
        self.assertEqual(current["status"], "audit_received")
        self.assertEqual(current["processed"], ["comment:1"])

    def test_second_request_escalates_without_second_rework(self):
        current = state()
        current.update(round=2, rework_count=1)
        receipt, _ = receive(current, [record(body(round="2"))], "2026-10-09T17:00:05Z")
        self.assertEqual(receipt["action"], "escalate")

    def test_approval_keeps_human_gate(self):
        current = state()
        receipt, _ = receive(current, [record(body(verdict="approve"))], "2026-10-09T17:00:05Z")
        self.assertEqual(receipt["action"], "await_user_approval")

    def test_blocked_stops(self):
        current = state()
        receipt, _ = receive(current, [record(body(verdict="blocked"))], "2026-10-09T17:00:05Z")
        self.assertEqual(receipt["action"], "blocked")

    def test_expired_deadline_makes_no_api_call(self):
        current = state()
        current["deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with tempfile.TemporaryDirectory() as folder, patch("review_relay.poll.gh_get") as get:
            self.assertEqual(run_poll(current, Path(folder) / "state.json"), 2)
            get.assert_not_called()
            self.assertEqual(current["status"], "timeout")

    def test_api_permission_failure_stops_without_retry_or_permission_change(self):
        current = state()
        with tempfile.TemporaryDirectory() as folder, patch("review_relay.poll.gh_get", side_effect=RuntimeError("permission failure")):
            self.assertEqual(run_poll(current, Path(folder) / "state.json"), 2)
            self.assertEqual(current["poll_count"], 1)
            self.assertEqual(current["status"], "blocked")

    def test_live_loop_path_persists_receipt(self):
        current = state()
        api_results = [pr(), [dict(id=1, created_at="2026-10-09T17:00:01Z", body=body())], [], []]
        with tempfile.TemporaryDirectory() as folder, patch("review_relay.poll.gh_get", side_effect=api_results), patch("review_relay.poll.now", return_value="2026-10-09T17:00:05Z"):
            target = Path(folder) / "state.json"
            self.assertEqual(run_poll(current, target), 0)
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "audit_received")
            self.assertEqual(len(saved["receipts"]), 1)


if __name__ == "__main__":
    unittest.main()
