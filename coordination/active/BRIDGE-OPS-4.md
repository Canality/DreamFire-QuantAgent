---
id: BRIDGE-OPS-4
title: Make Stop-hook handoff delivery idempotent
status: CLOSED
risk: MEDIUM
owner: Codex
created_at: 2026-08-13T00:00:00+08:00
updated_at: 2026-08-13T00:00:00+08:00
allowed_files:
  - .codex/hooks/discussion_bridge_stop.py
  - scripts/tests/test_discussion_bridge_hooks.py
  - coordination/active/BRIDGE-OPS-4.md
acceptance:
  - One unchanged handoff wakes Codex at most once across repeated Stop-hook processes.
  - A changed discussion or outbox content remains deliverable.
  - Existing freshness, lock and standby tests remain passing.
---

## Goal

Persist a content-addressed delivery receipt so an already reviewed Claude outbox cannot
re-enter the Codex Stop hook indefinitely.

## Non-goals

- No product, quant, report or submission changes.
- No deletion or rewriting of existing handoff evidence.

## Progress

- 2026-08-13 `READY`: User authorized diagnosis and repair; bridge-only scope frozen.
- 2026-08-13 `CLOSED`: Added a persistent content-addressed Codex delivery receipt.
  Focused bridge tests passed (`26 passed, 1 skipped`); Python compilation and
  `git diff --check` passed.
