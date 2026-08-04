---
id: WP1A-CORE-0802
title: Fix WP1-A deterministic integrity counterexamples
status: CLOSED
risk: MEDIUM
owner: Goone
created_at: 2026-08-02T18:14:51+08:00
updated_at: 2026-08-03T09:38:19+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/data_integrity.py
  - jiuwenswarm/jiuwenswarm/quant/market_width.py
  - jiuwenswarm/tests/unit_tests/quant/test_data_integrity.py
  - jiuwenswarm/tests/unit_tests/quant/test_market_width.py
acceptance:
  - Target ruff exits 0
  - Target pytest adds counterexamples and exits 0
  - scope-check exits 0
---

## Goal

Without integrating into production yet: make cross-source divergence fail closed per ticker/date so one bad ticker cannot be averaged away; scan corporate-action volume/price inversion across all tickers; compute 5d and 20d breadth returns from complete endpoint intervals; add negative tests for the 49th ticker, one-of-49 divergence, exact 5/20 intervals, short history, and date_idx boundaries.

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

- 2026-08-02T18:14:51+08:00 `DRAFT`: Task created.
- 2026-08-02T18:15:14+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-02T18:15:16+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-03T09:24:48+08:00 `IMPLEMENTED`: Builder timed out without evidence; Codex completed bounded recovery. Ruff 0; target 29 passed; related 50 passed; scope-check passed.
- 2026-08-03T09:28:07+08:00 `REVIEWED`: Qwen textual ACCEPT independently checked; Qwen did not emit artifact, so Codex wrote evidence-backed review.json.
- 2026-08-03T09:28:07+08:00 `VERIFIED`: Codex accepts the frozen local contract: ruff 0, 29 target and 50 related tests pass, scope-check pass. No path/business claim.
- 2026-08-03T09:38:19+08:00 `CLOSED`: Local core subtask closed after VERIFIED; production integration remains a separate HIGH-risk task.
