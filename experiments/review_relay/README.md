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

Only a new AUDIT_DECISION_V1 record matching task ID, PR, current full SHA and round is eligible. Stale SHA, old publication time, malformed and already processed records are ignored. The marker and shared GitHub login do **not** authenticate the director. Notes are untrusted data, never commands; the poller only records them and exits. Codex must inspect the notes against Issue #4's allowlist before any rework. It will pause on scope expansion or required approval. No shell from notes is run, no new permission is granted, and no ChatGPT UI automation is configured.

Local state records waiting_for_audit, poll count, received/identified timestamps, latency, receipt IDs and the eventual action. JSONL records each actual check. Unit tests use synthetic records and mocked gh calls; they are **not** evidence of real director delivery or automatic rework.

The user must manually ask the ChatGPT project director to audit the PR. Technical approve remains await_user_approval with merge_allowed=false. Development handoff, real audit feedback and real rework closure are separate gates. First-round source does not guess the director's later test conditions.

## Evidence

`evidence/round1-tests.txt` contains the raw first-round test output. `evidence/round1.json` records baseline, command, exit code, scope and timing. The commit SHA, PR creation time and live receipt are reported after commit in GitHub handoff comments and local evidence, avoiding a self-referencing commit hash.
