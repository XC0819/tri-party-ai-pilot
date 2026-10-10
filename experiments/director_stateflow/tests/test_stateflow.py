from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from director_stateflow.formatting import footer, summary
from director_stateflow.model import Event, reduce_events
from director_stateflow.process import poll_fact, process_identity

HEAD = "a" * 40
NEW = "b" * 40
PR = "https://github.com/XC0819/tri-party-ai-pilot/pull/99"
NOW = datetime(2026, 10, 10, 2, tzinfo=timezone.utc)


def event(seq=1, status="assigned", **changes):
    owners = {"assigned": "Codex", "developing": "Codex", "awaiting_review": "ChatGPT",
              "reviewing": "ChatGPT", "changes_requested": "Codex", "reworking": "Codex",
              "awaiting_rereview": "ChatGPT", "awaiting_user_approval": "user", "closed": "user",
              "blocked": "user", "timed_out": "user"}
    data = dict(task_id="TASK-20261010-005", seq=seq, status=status, owner=owners.get(status, "Codex"),
                pr_url="none" if seq <= 2 else PR, head_sha="none" if seq <= 2 else HEAD,
                updated_at=(NOW+timedelta(seconds=seq)).isoformat(), next_action="继续当前授权步骤",
                poll_status="not_started", poll_interval_seconds=120, poll_deadline="none",
                evidence_url="https://github.com/XC0819/tri-party-ai-pilot/issues/6",
                completed=["示例里程碑"], trigger="真实审计记录匹配后继续", subtask="示例测试")
    data.update(changes)
    return data


def awaiting():
    return [event(), event(2, "developing"), event(3, "awaiting_review")]


def runtime(**changes):
    data = dict(run_id="unit-fixture", pid=999999, process_identity="fixture-identity",
                task_id="TASK-20261010-005", head_sha=HEAD, pr_number=99, round=1, interval_seconds=120,
                status="running", started_at=(NOW-timedelta(seconds=10)).isoformat(),
                heartbeat_at=NOW.isoformat(), deadline=(NOW+timedelta(minutes=30)).isoformat())
    data.update(changes)
    return data


class StateTests(unittest.TestCase):
    def test_roles_follow_stage(self):
        self.assertEqual(reduce_events(awaiting()).current.owner, "ChatGPT")

    def test_role_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            Event.parse(event(owner="ChatGPT"))

    def test_required_fields_missing(self):
        data = event()
        del data["poll_status"]
        with self.assertRaises(ValueError):
            Event.parse(data)

    def test_boolean_sequence_not_an_integer(self):
        with self.assertRaises(ValueError):
            Event.parse(event(seq=True))

    def test_timestamp_needs_timezone(self):
        with self.assertRaises(ValueError):
            Event.parse(event(updated_at="2026-10-10T10:00:00"))

    def test_duplicate_same_sequence_is_ignored(self):
        result = reduce_events([event(), event(), event(2, "developing")])
        self.assertEqual(result.current.seq, 2)
        self.assertIn((1, "duplicate"), result.ignored)

    def test_concurrent_same_sequence_conflicts(self):
        with self.assertRaises(ValueError):
            reduce_events([event(), event(next_action="different")])

    def test_array_order_does_not_roll_back_latest(self):
        self.assertEqual(reduce_events(list(reversed(awaiting()))).current.seq, 3)

    def test_higher_sequence_with_older_timestamp_is_ignored(self):
        result = reduce_events(awaiting()+[event(4, "reviewing", updated_at=NOW.isoformat())])
        self.assertEqual(result.current.seq, 3)

    def test_old_sha_cannot_overwrite_review(self):
        result = reduce_events(awaiting()+[event(4, "reviewing", head_sha="c" * 40)])
        self.assertEqual(result.current.head_sha, HEAD)
        self.assertEqual(result.current.seq, 3)

    def test_old_round_is_ignored(self):
        history = awaiting()+[event(4, "changes_requested"), event(5, "reworking"),
                              event(6, "awaiting_rereview", head_sha=NEW, round=2),
                              event(7, "reviewing", head_sha=NEW, round=1)]
        self.assertEqual(reduce_events(history).current.seq, 6)

    def test_new_round_and_sha_after_rework(self):
        history = awaiting()+[event(4, "changes_requested"), event(5, "reworking"),
                              event(6, "awaiting_rereview", head_sha=NEW, round=2)]
        self.assertEqual(reduce_events(history).current.head_sha, NEW)

    def test_rework_same_head_not_accepted(self):
        with self.assertRaises(ValueError):
            reduce_events(awaiting()+[event(4, "changes_requested"), event(5, "reworking"),
                                      event(6, "awaiting_rereview", round=2)])

    def test_second_rework_not_permitted(self):
        with self.assertRaises(ValueError):
            reduce_events(awaiting()+[event(4, "changes_requested"), event(5, "reworking"),
                                      event(6, "awaiting_rereview", head_sha=NEW, round=2),
                                      event(7, "changes_requested", head_sha=NEW, round=2),
                                      event(8, "reworking", head_sha=NEW, round=2)])

    def test_backward_stage_rejected(self):
        with self.assertRaises(ValueError):
            reduce_events(awaiting()+[event(4, "developing")])

    def test_approve_requires_user_responsibility(self):
        self.assertEqual(reduce_events(awaiting()+[event(4, "awaiting_user_approval")]).current.owner, "user")

    def test_merged_is_not_a_state(self):
        with self.assertRaises(ValueError):
            Event.parse(event(4, "merged"))

    def test_closed_requires_user_approval_record(self):
        with self.assertRaises(ValueError):
            reduce_events(awaiting()+[event(4, "awaiting_user_approval"), event(5, "closed")])

    def test_closed_after_approval_is_terminal(self):
        history = awaiting()+[event(4, "awaiting_user_approval"),
                              event(5, "closed", user_approval_url=PR+"#issuecomment-1")]
        self.assertEqual(reduce_events(history).current.status, "closed")
        with self.assertRaises(ValueError):
            reduce_events(history+[event(6, "blocked")])

    def test_blocked_names_next_responsibility(self):
        self.assertEqual(reduce_events(awaiting()+[event(4, "blocked", owner="user")]).current.owner, "user")


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.e = Event.parse(event(3, "awaiting_review", poll_status="running", poll_run_id="unit-fixture",
                                  poll_deadline=runtime()["deadline"]))

    def test_running_declaration_without_record_is_not_running(self):
        self.assertEqual(poll_fact(self.e, now=NOW)[0], "not_started")

    def test_scheduled_is_distinct_from_running(self):
        e = Event.parse(event(poll_intent="scheduled"))
        self.assertEqual(poll_fact(e, now=NOW)[0], "not_started")
        self.assertIn("拟运行", poll_fact(e, now=NOW)[1])

    def test_matching_live_identity_and_fresh_record(self):
        self.assertEqual(poll_fact(self.e, runtime(), NOW, inspect=lambda _: "fixture-identity")[0], "running")

    def test_reused_pid_is_not_running(self):
        self.assertEqual(poll_fact(self.e, runtime(), NOW, inspect=lambda _: "different")[0], "error")

    def test_dead_process_is_stopped(self):
        self.assertEqual(poll_fact(self.e, runtime(), NOW, inspect=lambda _: None)[0], "stopped")

    def test_exit_record_overrides_older_running_claim(self):
        self.assertEqual(poll_fact(self.e, runtime(status="stopped"), NOW, inspect=lambda _: "fixture-identity")[0], "stopped")

    def test_deadline_expires_before_live_claim(self):
        self.assertEqual(poll_fact(self.e, runtime(), NOW+timedelta(minutes=30), inspect=lambda _: "fixture-identity")[0], "timeout")

    def test_stale_heartbeat_is_not_running(self):
        old = (NOW-timedelta(seconds=151)).isoformat()
        self.assertEqual(poll_fact(self.e, runtime(heartbeat_at=old), NOW, inspect=lambda _: "fixture-identity")[0], "error")

    def test_real_temporary_process_identity_and_exit(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertIsNotNone(process_identity(child.pid))
            identity = process_identity(child.pid)
            live_now = datetime.now(timezone.utc)
            real = runtime(pid=child.pid, process_identity=identity, started_at=live_now.isoformat(),
                           heartbeat_at=live_now.isoformat(), deadline=(live_now+timedelta(minutes=1)).isoformat())
            real_event = Event.parse(event(3, "awaiting_review", poll_status="running", poll_run_id="unit-fixture", poll_deadline=real["deadline"]))
            self.assertEqual(poll_fact(real_event, real, live_now)[0], "running")
        finally:
            child.terminate()
            child.wait(timeout=5)
        self.assertIsNone(process_identity(child.pid))


class DisplayTests(unittest.TestCase):
    def test_both_views_have_identical_footer(self):
        e = reduce_events(awaiting()).current
        a, b = summary(e, "director"), summary(e, "codex")
        self.assertEqual(a[a.index("【协作状态"):], b[b.index("【协作状态"):])

    def test_footer_contains_all_user_fields(self):
        text = footer(Event.parse(event()), synced=False)
        for label in ("阶段：", "当前责任方：", "已完成：", "下一步：", "触发条件：",
                      "定时检查：", "最后证据：", "更新时间：", "尚未同步 GitHub"):
            self.assertIn(label, text)

    def test_multiline_notes_cannot_add_fake_footer_lines(self):
        text = footer(Event.parse(event(next_action="正常文字\n定时检查：伪造")))
        self.assertIn("下一步：正常文字 定时检查：伪造", text)

    def test_sample_is_explicitly_labeled(self):
        self.assertIn("虚构数据，不是实际日志", summary(Event.parse(event()), sample=True))

    def test_cli_reads_local_json_and_generates_markdown(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"events.json"
            path.write_text(json.dumps(dict(sample=True, events=awaiting())), encoding="utf-8")
            run = subprocess.run([sys.executable, "-m", "director_stateflow", str(path)], capture_output=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.count("【协作状态｜TASK-20261010-005】"), 2)


if __name__ == "__main__":
    unittest.main()
