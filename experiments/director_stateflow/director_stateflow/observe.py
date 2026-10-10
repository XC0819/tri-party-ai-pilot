"""Finite read-only gh observation with a real PID record and exit priority."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from .github_data import parse_audit, parse_collab
from .model import REPO, SHA, TASK, instant
from .process import process_identity

BRANCH = "codex/TASK-20261010-005-state-visibility"


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    temporary.replace(path)


def gh_get(endpoint, deadline, pages=False):
    remaining = (instant(deadline)-datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        raise TimeoutError("deadline reached")
    args = ["gh", "api", "--method", "GET", f"repos/{REPO}/{endpoint}"]
    if pages:
        args += ["--paginate", "--slurp"]
    run = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=min(30, remaining))
    if run.returncode:
        raise RuntimeError(f"read-only gh call failed: exit {run.returncode}")
    value = json.loads(run.stdout)
    return [item for page in value for item in page] if pages else value


def guard(pr, record):
    if (pr["state"] != "open" or pr.get("merged") or pr.get("merged_at")
            or pr["head"]["sha"] != record["head_sha"] or pr["head"]["ref"] != BRANCH
            or pr["head"]["repo"]["full_name"] != REPO or pr["base"]["ref"] != "main"):
        raise ValueError("PR state/head/branch conflict")


def run(record, path):
    log_path = path.with_suffix(".jsonl")
    def log(data):
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(data, ensure_ascii=False)+"\n")
    try:
        record.update(status="running", pid=os.getpid(), process_identity=process_identity(os.getpid()),
                      started_at=now(), heartbeat_at=now(), run_id=str(uuid.uuid4()))
        if record["process_identity"] is None:
            raise RuntimeError("cannot establish OS process identity")
        save(path, record)
        log({"event": "started", "at": record["started_at"], "pid": record["pid"],
             "run_id": record["run_id"], "process_identity": record["process_identity"], "deadline": record["deadline"]})
        print(f"started pid={record['pid']} run_id={record['run_id']} deadline={record['deadline']}", flush=True)
        while datetime.now(timezone.utc) < instant(record["deadline"]):
            tick = time.monotonic()
            record["checks_this_run"] += 1
            record["checks_total"] += 1
            record["heartbeat_at"] = now()
            pr = gh_get(f"pulls/{record['pr_number']}", record["deadline"])
            guard(pr, record)
            sources = [("issues/6/comments", "task_comment"),
                       (f"issues/{record['pr_number']}/comments", "comment"),
                       (f"pulls/{record['pr_number']}/reviews", "review"),
                       (f"pulls/{record['pr_number']}/comments", "inline")]
            eligible = []
            ignored = []
            for endpoint, source in sources:
                for item in gh_get(endpoint, record["deadline"], pages=True):
                    rid = f"{source}:{item['id']}"
                    body = item.get("body")
                    if source in {"task_comment", "comment"}:
                        state = parse_collab(body)
                        if state is not None and rid not in record["state_record_ids"]:
                            record["state_record_ids"].append(rid)
                            record["github_state_events"].append(state)
                    audit = None if source == "task_comment" else parse_audit(body, record["pr_number"], record["head_sha"], record["round"])
                    if audit is None or rid in record["processed"]:
                        ignored.append(rid)
                        continue
                    stamp = item.get("submitted_at") if source == "review" else item.get("created_at")
                    if not stamp or instant(stamp) < instant(record["started_at"]) or instant(stamp) > datetime.now(timezone.utc):
                        ignored.append(rid)
                        continue
                    eligible.append(dict(record_id=rid, decision=audit, published_at=stamp,
                                         url=item.get("html_url"), author=(item.get("user") or {}).get("login")))
            if len({(x["decision"]["verdict"], x["decision"]["notes"]) for x in eligible}) > 1:
                raise ValueError("conflicting matching audit records")
            if eligible:
                receipt = sorted(eligible, key=lambda x: instant(x["published_at"]))[0]
                receipt["identified_at"] = now()
                receipt["latency_seconds"] = (instant(receipt["identified_at"])-instant(receipt["published_at"])).total_seconds()
                record["processed"].append(receipt["record_id"])
                record["receipts"].append(receipt)
                record["result"] = receipt["decision"]["verdict"]
                log({"event": "audit_received", **receipt, "checks_total": record["checks_total"]})
                print(json.dumps(receipt, ensure_ascii=False), flush=True)
                return 0
            record["heartbeat_at"] = now()
            save(path, record)
            log({"event": "poll", "at": record["heartbeat_at"], "checks_total": record["checks_total"],
                 "ignored_ids": ignored, "pr_state": pr["state"], "merged": pr["merged"]})
            print(f"poll={record['checks_total']} at={record['heartbeat_at']} no matching audit", flush=True)
            remaining = (instant(record["deadline"])-datetime.now(timezone.utc)).total_seconds()
            time.sleep(max(0, min(120-(time.monotonic()-tick), remaining)))
        record["result"] = "timeout"
        return 2
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired, TimeoutError) as exc:
        record["result"] = "timeout" if datetime.now(timezone.utc) >= instant(record["deadline"]) else "error"
        record["error"] = str(exc)
        return 2
    finally:
        record["status"] = record.get("result") if record.get("result") in {"timeout", "error"} else "stopped"
        record["stopped_at"] = now()
        record["heartbeat_at"] = record["stopped_at"]
        save(path, record)
        log({"event": "exited", "at": record["stopped_at"], "result": record.get("result"),
             "status": record["status"], "pid": record.get("pid"), "checks_total": record["checks_total"]})
        print(f"exited status={record['status']} result={record.get('result')}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--round", type=int, choices=(1, 2), default=1)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    if args.pr <= 0 or not SHA.fullmatch(args.head):
        parser.error("positive PR and full SHA required")
    if args.record.exists():
        record = json.loads(args.record.read_text(encoding="utf-8"))
        if (record["task_id"] != TASK or record["pr_number"] != args.pr or record["round"] != 1
                or args.round != 2 or record.get("result") != "request_changes" or record["head_sha"] == args.head):
            parser.error("only one matching rework/resume is permitted")
        record.update(round=2, head_sha=args.head, checks_this_run=0, result=None)
    else:
        if args.round != 1:
            parser.error("first run must be round 1")
        record = dict(task_id=TASK, pr_number=args.pr, head_sha=args.head, round=1,
                      deadline=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),
                      interval_seconds=120, checks_this_run=0, checks_total=0, processed=[], receipts=[],
                      state_record_ids=[], github_state_events=[], merge_allowed=False)
    return run(record, args.record)


if __name__ == "__main__":
    raise SystemExit(main())
