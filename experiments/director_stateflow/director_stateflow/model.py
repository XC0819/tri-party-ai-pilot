"""Immutable data and state transitions. Text fields are data, never commands."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re

TASK = "TASK-20261010-005"
REPO = "XC0819/tri-party-ai-pilot"
OWNER = {"assigned": "Codex", "developing": "Codex", "awaiting_review": "ChatGPT",
         "reviewing": "ChatGPT", "changes_requested": "Codex", "reworking": "Codex",
         "awaiting_rereview": "ChatGPT", "awaiting_user_approval": "user", "closed": "user"}
TRANSITIONS = {"assigned": {"developing"}, "developing": {"awaiting_review"},
               "awaiting_review": {"reviewing", "changes_requested", "awaiting_user_approval"},
               "reviewing": {"changes_requested", "awaiting_user_approval"},
               "changes_requested": {"reworking"}, "reworking": {"awaiting_rereview"},
               "awaiting_rereview": {"reviewing", "awaiting_user_approval", "changes_requested"},
               "awaiting_user_approval": {"closed"}, "closed": set(),
               "blocked": set(), "timed_out": set()}
POLLS = {"not_started", "running", "stopped", "timeout", "error"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
PR = re.compile(r"https://github.com/XC0819/tri-party-ai-pilot/pull/[1-9][0-9]*\Z")


def instant(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if stamp.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return stamp.astimezone(timezone.utc)


def positive_int(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class Event:
    task_id: str
    seq: int
    status: str
    owner: str
    pr_url: str
    head_sha: str
    updated_at: str
    next_action: str
    poll_status: str
    poll_interval_seconds: int
    poll_deadline: str
    evidence_url: str
    round: int = 1
    poll_run_id: str = "none"
    poll_intent: str = "not_scheduled"
    completed: tuple = ()
    trigger: str = "unknown"
    subtask: str = "unknown"
    milestones_done: int = 0
    milestones_total: int = 5
    user_approval_url: str = "none"
    notification_status: str = "not_sent"

    @classmethod
    def parse(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("event must be an object")
        required = {"task_id", "seq", "status", "owner", "pr_url", "head_sha", "updated_at",
                    "next_action", "poll_status", "poll_interval_seconds", "poll_deadline", "evidence_url"}
        if required - payload.keys():
            raise ValueError("missing required event fields: " + ",".join(sorted(required - payload.keys())))
        allowed = set(cls.__dataclass_fields__)
        if payload.keys() - allowed:
            raise ValueError("unknown event fields")
        data = dict(payload)
        if "completed" in data:
            if not isinstance(data["completed"], (list, tuple)) or any(not isinstance(x, str) for x in data["completed"]):
                raise ValueError("completed must contain text")
            data["completed"] = tuple(data["completed"])
        event = cls(**data)
        event.validate()
        return event

    def validate(self):
        for name in ("task_id", "status", "owner", "pr_url", "head_sha", "next_action", "poll_status",
                     "poll_deadline", "evidence_url", "poll_run_id", "poll_intent", "trigger", "subtask", "user_approval_url"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be nonempty text")
        positive_int(self.seq, "seq")
        positive_int(self.round, "round")
        positive_int(self.poll_interval_seconds, "poll_interval_seconds")
        positive_int(self.milestones_done, "milestones_done", 0)
        positive_int(self.milestones_total, "milestones_total")
        if self.milestones_done > self.milestones_total:
            raise ValueError("progress exceeds milestone count")
        if self.status not in TRANSITIONS or self.owner not in {"Codex", "ChatGPT", "user"}:
            raise ValueError("invalid status or business role")
        if self.status in OWNER and self.owner != OWNER[self.status]:
            raise ValueError("status responsibility mismatch")
        if self.poll_status not in POLLS or self.poll_intent not in {"scheduled", "not_scheduled"}:
            raise ValueError("invalid poll status or intent")
        if self.notification_status not in {"not_sent", "sent", "failed"}:
            raise ValueError("invalid notification status")
        instant(self.updated_at)
        if self.poll_deadline not in {"none", "unknown"}:
            instant(self.poll_deadline)
        if self.head_sha not in {"none", "unknown"} and not SHA.fullmatch(self.head_sha):
            raise ValueError("head must be full SHA or explicit none/unknown")
        if self.pr_url not in {"none", "unknown"} and not PR.fullmatch(self.pr_url):
            raise ValueError("PR must belong to the approved repository")
        if self.status not in {"assigned", "developing", "blocked", "timed_out"}:
            if not SHA.fullmatch(self.head_sha) or not PR.fullmatch(self.pr_url):
                raise ValueError("review stages need actual PR and full head SHA")
        if self.status == "closed" and not self.user_approval_url.startswith("https://github.com/"):
            raise ValueError("closed requires an explicit user approval record")


@dataclass(frozen=True)
class Reduced:
    current: Event
    ignored: tuple


def reduce_events(payloads, task_id=TASK):
    events = [Event.parse(payload) for payload in payloads]
    events = [event for event in events if event.task_id == task_id]
    if not events:
        raise ValueError("no event for this task")
    events.sort(key=lambda e: e.seq)
    current = None
    seen = {}
    ignored = []
    reworks = 0
    for event in events:
        if event.seq in seen:
            if event != seen[event.seq]:
                raise ValueError("conflicting events at same task seq")
            ignored.append((event.seq, "duplicate"))
            continue
        seen[event.seq] = event
        if current is None:
            if event.status != "assigned":
                raise ValueError("history must start with assigned")
            current = event
            continue
        if instant(event.updated_at) < instant(current.updated_at):
            ignored.append((event.seq, "older_timestamp"))
            continue
        if event.round < current.round:
            ignored.append((event.seq, "old_round"))
            continue
        changed_head = event.head_sha != current.head_sha
        first_pr = current.head_sha in {"none", "unknown"} and event.status == "awaiting_review"
        new_rework = current.status == "reworking" and event.status == "awaiting_rereview"
        if changed_head and not (first_pr or new_rework):
            ignored.append((event.seq, "old_or_unexpected_sha"))
            continue
        if current.pr_url not in {"none", "unknown"} and event.pr_url != current.pr_url:
            ignored.append((event.seq, "different_pr"))
            continue
        if new_rework:
            if not changed_head or event.round != current.round + 1 or reworks >= 1:
                raise ValueError("rework needs one new SHA/round; maximum one rework")
            reworks += 1
        elif event.round != current.round:
            ignored.append((event.seq, "unexpected_round"))
            continue
        if current.status == "closed" and event != current:
            raise ValueError("closed is terminal")
        same = current.status == event.status
        if event.status == "reworking" and not same and reworks >= 1:
            raise ValueError("one rework allowance already consumed")
        exceptional = event.status in {"blocked", "timed_out"} and current.status != "closed"
        if not same and not exceptional and event.status not in TRANSITIONS[current.status]:
            raise ValueError("illegal or backward transition")
        current = event
    return Reduced(current, tuple(ignored))
