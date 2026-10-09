# Review Relay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Execute TASK-20261010-004 inside the experiment and measure actual GitHub audit delivery.

**Architecture:** A pure decision function is separate from a strict audit parser and a read-only bounded gh poller. Codex handles at most one scoped rework after inspecting the audit; the poller never executes audit notes or merges. Runtime evidence is stored outside tracked source.

**Tech Stack:** Python standard library, unittest, existing authenticated gh and git.

---

The user authorized execution in this session. Existing skills are used for planning and execution; unavailable superpowers helpers are not dependencies. All repository writes stay under experiments/review_relay/.

### Task 1: Workflow
- Create tests/test_workflow.py with at least eight independent cases for the explicit Issue contract. Run `python -m unittest discover -s tests -v` to capture the initial failure.
- Create review_relay/workflow.py and __init__.py. Implement the four actions and required ValueError checks. Repeat the same command.
- Do not invent the second-round audit requirements.

### Task 2: Audit receipt and polling
- Create review_relay/audit.py, review_relay/poll.py, tests/test_audit.py and tests/test_poll.py.
- Accept only AUDIT_DECISION_V1 matching task, PR, full head SHA and round, new after the round start; reject duplicate fields, malformed records and conflict. Persist processed IDs.
- Read gh issue comments, review bodies and inline review comments. Confirm the PR stays open, unmerged, on the specified branch and head. Bound requests and polling by a shared 30-minute deadline and a 120-second interval.
- The fixed gh API calls are read-only. Notes are data, never shell commands. Test filtering, deduplication, conflict, timeout and state guards.

### Task 3: Handoff
- Write README.md, raw test output and public-safe first-round evidence under the experiment.
- Check staged scope and `git diff --check`; commit and push only codex/TASK-20261010-004-review-relay.
- Open an unmerged draft PR, post task/base/head/command/exit/file evidence to Issue and PR, attach PR to this chat.

### Task 4: Live experiment
- Start bounded read-only polling immediately after PR creation, save waiting_for_audit and actual timestamps locally.
- Ask the user to manually trigger the project director with the PR number. Do not operate ChatGPT.
- On a matching request_changes, inspect notes for scope and permission; perform at most one local rework, rerun tests, commit/push the same branch and refresh evidence. Resume round 2 without extending the original deadline.
- On approval record await_user_approval; on blocked/conflict/timeout/error stop. Never merge. Report each gate from actual evidence, including limits on Codex invocation counts.
