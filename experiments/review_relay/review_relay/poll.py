"""Bounded read-only polling. Receiving notes never executes a command."""

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import time

from .audit import BRANCH, REPO, SHA, TASK_ID, select_audit, utc
from .workflow import decide_action


INTERVAL = 120
WINDOW = 1800


def now():
    return datetime.now(timezone.utc).isoformat()


def guard_pr(pr, state):
    if pr["state"] != "open" or pr.get("merged") or pr.get("merged_at"):
        raise ValueError("PR no longer open and unmerged")
    if pr["number"] != state["pr_number"]:
        raise ValueError("PR number conflict")
    if pr["head"]["sha"] != state["head_sha"] or pr["head"]["ref"] != BRANCH:
        raise ValueError("PR head/branch conflict")
    if pr["base"]["ref"] != "main":
        raise ValueError("PR base branch conflict")
    if pr["head"]["repo"]["full_name"] != REPO:
        raise ValueError("PR head repository conflict")


def normalize(items, source):
    result = []
    for item in items:
        stamp = item.get("submitted_at") if source == "review" else item.get("created_at")
        if not stamp:  # Draft reviews are not published decisions.
            continue
        result.append({"record_id": f"{source}:{item['id']}", "body": item.get("body"),
                       "published_at": stamp, "url": item.get("html_url"),
                       "author": item.get("user", {}).get("login")})
    return result


def gh_get(endpoint, deadline, *, paginated=False):
    remaining = (utc(deadline) - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise TimeoutError("poll deadline reached")
    command = ["gh", "api", "--method", "GET", f"repos/{REPO}/{endpoint}"]
    if paginated:
        command.extend(["--paginate", "--slurp"])
    run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                         timeout=min(30, remaining), check=False)
    if run.returncode:
        # Do not copy raw diagnostics that could contain sensitive credential data.
        raise RuntimeError(f"read-only gh API failed, exit_code={run.returncode}")
    payload = json.loads(run.stdout)
    if paginated:
        return [item for page in payload for item in page]
    return payload


def save(path, state):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def log(path, event):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def receive(state, records, identified_at):
    selected, ignored = select_audit(records, pr_number=state["pr_number"],
                                    head_sha=state["head_sha"], round_number=state["round"],
                                    since=state["round_started_at"], processed=state["processed"])
    if selected is None:
        return None, ignored
    record, decision = selected
    action = "blocked" if decision.verdict == "blocked" else decide_action(
        decision.verdict, state["rework_count"], max_reworks=1)
    # The notes remain untrusted data for a scope check by the authorized Codex session.
    receipt = {**record, "decision": asdict(decision), "identified_at": identified_at,
               "latency_seconds": (utc(identified_at) - utc(record["published_at"])).total_seconds(),
               "action": action, "requires_scope_check": action == "rework"}
    state["processed"].append(record["record_id"])
    state["receipts"].append(receipt)
    state["status"] = "audit_received" if action == "rework" else action
    return receipt, ignored


def run_poll(state, path):
    events = path.with_suffix(".jsonl")
    state["status"] = "waiting_for_audit"
    save(path, state)
    while True:
        if datetime.now(timezone.utc) >= utc(state["deadline"]):
            state["status"] = "timeout"
            state["stopped_at"] = now()
            save(path, state)
            log(events, {"event": "timeout", "at": state["stopped_at"]})
            print("timeout: stopped at original 30-minute deadline", flush=True)
            return 2
        check_started = time.monotonic()
        state["poll_count"] += 1
        at = now()
        try:
            pr = gh_get(f"pulls/{state['pr_number']}", state["deadline"])
            guard_pr(pr, state)
            records = []
            for endpoint, source in ((f"issues/{state['pr_number']}/comments", "comment"),
                                     (f"pulls/{state['pr_number']}/reviews", "review"),
                                     (f"pulls/{state['pr_number']}/comments", "inline")):
                records.extend(normalize(gh_get(endpoint, state["deadline"], paginated=True), source))
            receipt, ignored = receive(state, records, now())
            log(events, {"event": "poll", "at": at, "poll_count": state["poll_count"],
                         "round": state["round"], "head_sha": state["head_sha"],
                         "pr_state": pr["state"], "merged": pr["merged"],
                         "ignored": ignored, "receipt": receipt})
            save(path, state)
            print(f"poll={state['poll_count']} round={state['round']} at={at} status={state['status']}", flush=True)
            if receipt:
                print(json.dumps(receipt, ensure_ascii=False), flush=True)
                return 0
        except (ValueError, KeyError, RuntimeError, OSError, subprocess.TimeoutExpired, TimeoutError) as exc:
            state["status"] = "timeout" if utc(state["deadline"]) <= datetime.now(timezone.utc) else "blocked"
            state["error"] = str(exc)
            state["stopped_at"] = now()
            save(path, state)
            log(events, {"event": state["status"], "at": state["stopped_at"], "reason": str(exc)})
            print(f"stopped: {state['status']}: {exc}", flush=True)
            return 2
        remaining = (utc(state["deadline"]) - datetime.now(timezone.utc)).total_seconds()
        time.sleep(max(0, min(INTERVAL - (time.monotonic() - check_started), remaining)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--state", type=Path, required=True, help="local untracked evidence path")
    parser.add_argument("--created-at", help="GitHub PR creation timestamp, required on first run")
    parser.add_argument("--round", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    if args.pr <= 0 or not SHA.fullmatch(args.head):
        parser.error("positive PR number and lowercase 40-character head SHA required")
    if args.state.exists():
        state = json.loads(args.state.read_text(encoding="utf-8"))
        if state["task_id"] != TASK_ID or state["pr_number"] != args.pr or state["merge_allowed"] is not False:
            parser.error("state context conflict")
        if args.round == 2:
            if state["status"] != "audit_received" or state["round"] != 1 or state["rework_count"] != 0:
                parser.error("only one rework transition is authorized")
            if args.head == state["head_sha"]:
                parser.error("round 2 requires a new rework SHA")
            state.update(round=2, head_sha=args.head, rework_count=1, round_started_at=now())
        elif state["status"] != "waiting_for_audit" or args.head != state["head_sha"] or state["round"] != 1:
            parser.error("cannot replay a terminal or mismatched state")
    else:
        if args.round != 1 or not args.created_at:
            parser.error("first run requires round 1 and --created-at")
        created = utc(args.created_at)
        state = {"task_id": TASK_ID, "pr_number": args.pr, "head_sha": args.head,
                 "round": 1, "rework_count": 0, "merge_allowed": False,
                 "created_at": created.isoformat(), "round_started_at": created.isoformat(),
                 "deadline": (created + timedelta(seconds=WINDOW)).isoformat(),
                 "interval_seconds": INTERVAL, "poll_count": 0, "processed": [], "receipts": [],
                 "codex_execution_sessions": 1, "automatic_model_wakeups": 0}
    return run_poll(state, args.state)


if __name__ == "__main__":
    raise SystemExit(main())
