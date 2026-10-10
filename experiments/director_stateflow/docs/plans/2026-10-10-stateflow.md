# Director Stateflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement TASK-20261010-005 in its isolated directory and measure actual director/Codex state handoff.

**Architecture:** Strict immutable events feed a guarded reducer. Chinese director/Codex summaries share the same footer. A local process record is checked against the live OS process identity before reporting running; offline examples do not prove execution. A bounded read-only gh observer receives audits, while meaningful state transitions are posted by the authorized Codex session.

**Tech Stack:** Python standard library, unittest, existing git/gh authentication and Codex in-app browser.

---

Execution is already authorized in this session. All tracked writes stay in experiments/director_stateflow/. Base is latest origin/main, not PR #5. No superpowers package, extra agents, installed service, Actions or paid API is required.

1. Implement event validation/reducer, OS process identity validation, shared Chinese formatting and local JSON CLI. Test roles, transitions, missing fields, stale/duplicate/conflicting events, old SHA/round, process expiry/exit/reused PID, approval and footer.
2. Write five clearly synthetic example scenarios and README. Execute full unittest suite and CLI examples; preserve raw outputs and diff check; assert no existing files change.
3. Commit/push only the independent branch and create a draft PR. Refresh Issue before browser sends. Post COLLAB_STATUS_V1 events with increasing seq and actual evidence URLs; record unknown values explicitly.
4. Start finite 120-second gh observation with a 30-minute deadline and runtime JSONL/PID record. Confirm process identity before publishing running. Send one complete audit notification using paste in Codex In-app Browser; do not use user Chrome. Read audit verdict only from GitHub. Perform at most one scoped rework if actually requested.
5. Stop observer on approve/error/timeout, post final status awaiting_user_approval, and provide evidence. Audit notifications are at most one per round (two if rework); final handoff has one separate message only after confirming applicable limits. Never merge or close without user approval. Verify actual dual-end footers separately from synthetic examples.
