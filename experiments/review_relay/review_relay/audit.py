"""Parse untrusted GitHub text into data, never executable instructions."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re


TASK_ID = "TASK-20261010-004"
BRANCH = "codex/TASK-20261010-004-review-relay"
REPO = "XC0819/tri-party-ai-pilot"
SHA = re.compile(r"[0-9a-f]{40}\Z")


def utc(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return stamp.astimezone(timezone.utc)


@dataclass(frozen=True)
class Audit:
    task_id: str
    pr_number: int
    head_sha: str
    round: int
    verdict: str
    notes: str


def parse_audit(body):
    if not isinstance(body, str):
        return None
    lines = body.strip().splitlines()
    markers = [i for i, line in enumerate(lines) if line.strip() == "AUDIT_DECISION_V1"]
    if len(markers) != 1:
        return None
    fields = {}
    notes = []
    in_notes = False
    required = {"task_id", "pr_number", "head_sha", "round", "verdict", "notes"}
    for line in lines[markers[0] + 1:]:
        if line.strip() == "```":
            break
        key, sep, value = line.partition(":")
        key = key.strip()
        if key in required and sep:
            if key in fields or in_notes:
                return None
            fields[key] = value.strip()
            if key == "notes":
                in_notes = True
                notes.append(value.strip())
        elif in_notes:
            notes.append(line)
        elif line.strip():
            return None
    if set(fields) != required:
        return None
    if not SHA.fullmatch(fields["head_sha"]):
        return None
    if not re.fullmatch(r"[1-9][0-9]*", fields["pr_number"]):
        return None
    if fields["round"] not in ("1", "2"):
        return None
    if fields["verdict"] not in ("request_changes", "approve", "blocked"):
        return None
    return Audit(fields["task_id"], int(fields["pr_number"]), fields["head_sha"],
                 int(fields["round"]), fields["verdict"], "\n".join(notes))


def select_audit(records, *, pr_number, head_sha, round_number, since, processed):
    """Return a single matching receipt; conflicting matching decisions stop work."""
    eligible = []
    ignored = []
    for record in records:
        rid = record["record_id"]
        if rid in processed:
            ignored.append({"record_id": rid, "reason": "duplicate"})
            continue
        decision = parse_audit(record.get("body"))
        if decision is None:
            ignored.append({"record_id": rid, "reason": "unstructured_or_invalid"})
            continue
        if (decision.task_id, decision.pr_number, decision.head_sha, decision.round) != (
                TASK_ID, pr_number, head_sha, round_number):
            ignored.append({"record_id": rid, "reason": "context_mismatch"})
            continue
        try:
            fresh = utc(record["published_at"]) >= utc(since)
        except (KeyError, TypeError, ValueError):
            fresh = False
        if not fresh:
            ignored.append({"record_id": rid, "reason": "not_new"})
            continue
        eligible.append((record, decision))
    if len({(a.verdict, a.notes) for _, a in eligible}) > 1:
        raise ValueError("conflicting audit records for current head/round")
    if not eligible:
        return None, ignored
    eligible.sort(key=lambda pair: utc(pair[0]["published_at"]))
    return eligible[0], ignored
