"""Decode only data markers from GitHub; no instructions are executed."""

from dataclasses import asdict
import json

from .model import Event, SHA, TASK


def marker_payload(body, marker):
    if not isinstance(body, str):
        return None
    lines = body.strip().splitlines()
    locations = [i for i, line in enumerate(lines) if line.strip() == marker]
    if len(locations) != 1:
        return None
    tail = "\n".join(lines[locations[0]+1:]).strip()
    if tail.startswith("{"):
        try:
            value, end = json.JSONDecoder().raw_decode(tail)
        except ValueError:
            return None
        remainder = tail[end:].strip()
        if remainder and not remainder.startswith("【协作状态｜"):
            return None
        return value if isinstance(value, dict) else None
    values = {}
    for line in tail.splitlines():
        if line.strip() == "```" or line.startswith("【协作状态｜"):
            break
        key, sep, value = line.partition(":")
        if not sep or key.strip() in values:
            return None
        values[key.strip()] = value.strip()
    return values


def parse_collab(body):
    data = marker_payload(body, "COLLAB_STATUS_V1")
    if data is None:
        return None
    for key in ("seq", "round", "poll_interval_seconds", "milestones_done", "milestones_total"):
        if key in data and isinstance(data[key], str):
            try:
                data[key] = int(data[key])
            except ValueError:
                return None
    try:
        return asdict(Event.parse(data))
    except (ValueError, TypeError):
        return None


def parse_audit(body, pr, head, round_number):
    # Notes may be multiple lines. They stay data; the fixed metadata precedes notes.
    if not isinstance(body, str) or body.splitlines().count("AUDIT_DECISION_V1") != 1:
        return None
    tail = body.split("AUDIT_DECISION_V1", 1)[1].strip()
    if tail.startswith("{"):
        values = marker_payload(body, "AUDIT_DECISION_V1")
    else:
        headers, sep, notes = tail.partition("\nnotes:")
        if not sep:
            return None
        values = {}
        for line in headers.splitlines():
            key, delimiter, value = line.partition(":")
            if not delimiter or key.strip() in values:
                return None
            values[key.strip()] = value.strip()
        values["notes"] = notes.strip().removesuffix("```").strip()
    if not isinstance(values, dict) or set(values) != {"task_id", "pr_number", "head_sha", "round", "verdict", "notes"}:
        return None
    if str(values["pr_number"]) != str(pr) or str(values["round"]) != str(round_number):
        return None
    if values["task_id"] != TASK or values["head_sha"] != head or not SHA.fullmatch(head):
        return None
    if not isinstance(values["verdict"], str) or values["verdict"] not in {"request_changes", "approve", "blocked"}:
        return None
    if not isinstance(values["notes"], str) or not values["notes"].strip():
        return None
    return values
