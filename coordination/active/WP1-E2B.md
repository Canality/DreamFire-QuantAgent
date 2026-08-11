---
id: WP1-E2B
title: Prior-only similar-market selector
status: CLOSED
risk: MEDIUM
owner: Claude
created_at: 2026-08-09T15:34:16+08:00
updated_at: 2026-08-09T16:32:56+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/market_similarity.py
  - jiuwenswarm/tests/unit_tests/quant/test_market_similarity.py
acceptance:
  - Uses six frozen dimensions and expanding-prior median/MAD only; minimum 60 mature historical states; selects exactly 5 non-overlapping neighbors sorted by distance, decision_date, market_snapshot_hash.
  - Benchmark unavailable, missing/non-finite features, zero MAD, insufficient history, or insufficient non-overlapping neighbors closes only the similar-market branch with deterministic reason codes.
  - Current/future/unmatured states never enter scale or neighbor selection; inputs/results are immutable; no direct/formal/quant package import or production activation.
  - Focused pytest, adjacent research tests, Ruff, py_compile, diff-check, and scope-check pass.
---

## Goal

Implement the six-dimensional prior-only similar-market neighbor selector as research-only logic with deterministic fail-closed reason codes; do not activate production.

## Non-goals

- No unrelated refactor.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Pending.

## Implementation evidence

- Pending.

## Review evidence

- Pending.

## Progress

- 2026-08-09T15:34:16+08:00 `DRAFT`: Task created.
- 2026-08-09T15:36:46+08:00 `LOCATED`: Reused accepted WP1-E2 Claude location evidence for the bounded E2B split.
- 2026-08-09T15:36:48+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-09T16:09:23+08:00 `IMPLEMENTED`: market_similarity.py + 25 tests implemented; scope-check exit 2 flags pre-existing Codex-owned .claude/discussion.md change; see implementation.json
- 2026-08-09T16:14:51+08:00 `READY`: Codex review MODIFY: noneligible malformed history affects result; wrong-type history raises; bool accepted. See discussion/review.json.
- 2026-08-09T16:21:28+08:00 `IMPLEMENTED`: MODIFY fix applied: eligibility pre-filter, bool rejection, no-exception fail-close; 37/37 tests; see implementation.json
- 2026-08-09T16:32:56+08:00 `REVIEWED`: Codex re-review ACCEPT; prior poison/bool/wrong-object blockers fixed.
- 2026-08-09T16:32:56+08:00 `VERIFIED`: 37 focused tests, Ruff, compile, diff-check, production isolation, and scope-check passed.
- 2026-08-09T16:32:56+08:00 `CLOSED`: Accepted prior-only similar-market selector; real benchmark integration remains separate and fail-closed.
