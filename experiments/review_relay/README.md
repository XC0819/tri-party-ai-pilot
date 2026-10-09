# TASK-20261010-004: review relay experiment

Pure Python standard-library experiment. All repository changes are confined to this directory. Existing slugtool and root tests are untouched.

Run from `experiments/review_relay`:

```text
python -m unittest discover -s tests -v
```

`decide_action(verdict, rework_count, max_reworks=2)` implements the Issue contract: pending → wait, approve → await_user_approval, request_changes → rework below the limit, otherwise escalate. Invalid verdicts or negative counts raise ValueError. The live pilot uses a stricter maximum of **one** automatic rework. It never merges.

## GitHub polling

Run using existing local gh authentication; never put tokens in code or evidence:

```text
python -m review_relay.poll --pr <number> --head <40-char SHA> --created-at <GitHub created_at> --state <local evidence directory>/poll-state.json
```

Fixed read-only gh GET requests inspect the PR state, issue comments, submitted reviews and inline comments. Checks begin immediately and then every 120 seconds, stopping at 30 minutes after PR creation. Requests have bounded timeouts. Errors, changed heads, closed/merged PRs or conflicting audits stop the experiment. A second round uses the same state and original deadline:

```text
python -m review_relay.poll --pr <number> --head <new SHA> --round 2 --state <same local state file>
```

Only a new AUDIT_DECISION_V1 record matching task ID, PR, current full SHA and round is eligible. Stale SHA, old publication time, malformed and already processed records are ignored. The marker and shared GitHub login do **not** authenticate the director. Notes are untrusted data, never commands; the poller only records them and exits. Codex must inspect the notes against Issue #4's allowlist before any rework. It will pause on scope expansion or required approval. No shell from notes is run and no new permission is granted. GitHub API records with a missing or null user preserve author=null.

Local state records waiting_for_audit, poll count, received/identified timestamps, latency, receipt IDs and the eventual action. JSONL records each actual check. Unit tests use synthetic records and mocked gh calls; they are **not** evidence of real director delivery or automatic rework.

The revised Issue #4 (2026-10-09T17:00:22Z), explicitly adopted by the user, permits at most two local Chrome notifications to this director conversation, one per round. These are sent by the current Codex session using unified-computer-use browser controls; there is no daemon that reads ChatGPT output or sends unlimited messages. Audit decisions are obtained only from GitHub. Technical approve remains await_user_approval with merge_allowed=false. Development handoff, real audit feedback, rework closure and notification protocol correctness are separate gates. First-round source did not guess the director's later test conditions.

## Evidence

`evidence/round1-tests.txt` contains the raw first-round test output. `evidence/round1.json` records baseline, command, exit code, scope and timing. The commit SHA, PR creation time and live receipt are reported after commit in GitHub handoff comments and local evidence, avoiding a self-referencing commit hash.

Round 1 received a real GitHub review requesting a regression for user=null. The added tests reproduced AttributeError for comment, review and inline sources before the fix; `evidence/round2-tests.txt` records the passing full suite after the fix. `evidence/round2.json` records the audit, one rework and receipt timing. Local raw evidence retains the failing tests and actual polling events.

Notification caveat: the round-1 native typeText call submitted only the marker because its first newline acted as Enter. That incomplete message triggered a real GitHub audit; it does not meet the full structured notification protocol. The unsent remainder is replaced for round 2 and pasted as one multiline message. Exactly two submitted messages are allowed; no extra round-1 correction is sent. Native Windows sky was not used: the actual control path is cua_repl with the Chrome extension, accessibility controls and paste. Precise first-send time was not instrumented; the evidence reports this limitation rather than inventing a timestamp.
