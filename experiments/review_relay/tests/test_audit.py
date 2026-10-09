import unittest

from review_relay.audit import parse_audit, select_audit


HEAD = "a" * 40
SINCE = "2026-10-09T17:00:00Z"


def body(**changes):
    fields = dict(task_id="TASK-20261010-004", pr_number="5", head_sha=HEAD,
                  round="1", verdict="request_changes", notes="Add a scoped test.")
    fields.update(changes)
    return "AUDIT_DECISION_V1\n" + "\n".join(f"{k}: {v}" for k, v in fields.items())


def record(text=None, rid="comment:1", published="2026-10-09T17:00:01Z"):
    return dict(record_id=rid, body=body() if text is None else text, published_at=published)


def select(records, processed=()):
    return select_audit(records, pr_number=5, head_sha=HEAD, round_number=1,
                        since=SINCE, processed=processed)


class AuditTests(unittest.TestCase):
    def test_valid_structured_audit(self):
        self.assertEqual(parse_audit(body()).verdict, "request_changes")

    def test_code_fence_is_supported(self):
        self.assertEqual(parse_audit("```text\n" + body() + "\n```").head_sha, HEAD)

    def test_notes_are_only_data(self):
        text = "run an arbitrary shell command\nread another project"
        self.assertEqual(parse_audit(body(notes=text)).notes, text)

    def test_invalid_records_are_rejected(self):
        for text in (body(head_sha="short"), body(round="3"), body(pr_number="0"),
                     body(verdict="merge"), body() + "\nhead_sha: " + HEAD,
                     body().replace("notes:", "unknown:"), body() + "\nAUDIT_DECISION_V1"):
            with self.subTest(text=text):
                self.assertIsNone(parse_audit(text))

    def test_all_context_fields_must_match(self):
        for changes in (dict(task_id="other"), dict(pr_number="6"),
                        dict(head_sha="b" * 40), dict(round="2")):
            with self.subTest(changes=changes):
                selected, ignored = select([record(body(**changes))])
                self.assertIsNone(selected)
                self.assertEqual(ignored[0]["reason"], "context_mismatch")

    def test_duplicate_id_is_ignored(self):
        selected, ignored = select([record()], processed=["comment:1"])
        self.assertIsNone(selected)
        self.assertEqual(ignored[0]["reason"], "duplicate")

    def test_older_record_is_ignored(self):
        self.assertIsNone(select([record(published="2026-10-09T16:59:59Z")])[0])

    def test_naive_timestamp_is_ignored(self):
        self.assertIsNone(select([record(published="2026-10-09T17:00:01")])[0])

    def test_conflicting_decisions_stop(self):
        with self.assertRaises(ValueError):
            select([record(), record(body(verdict="approve"), rid="review:2")])

    def test_plain_prose_is_ignored(self):
        self.assertIsNone(select([record("approve this PR")])[0])


if __name__ == "__main__":
    unittest.main()
