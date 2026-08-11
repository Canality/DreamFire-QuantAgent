---
id: WP1-E2C
title: Deterministic strategy-pool historical replay
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-09T16:38:02+08:00
updated_at: 2026-08-11T17:35:45+08:00
allowed_files:
  - jiuwenswarm/evaluation/strategy_pool_replay.py
  - jiuwenswarm/tests/unit_tests/quant/test_strategy_pool_replay.py
acceptance:
  - Location phase first: enumerate exact evidence loaders, factor-research APIs, allocation/backtest callers, tests, and minimal write scope; no implementation before Codex freeze.
  - Replay uses exact accepted 49-stock/6-sector universe, hash-bound E0 qfq OHLCV and official 1+20 matured labels; each decision date reconstructs inputs using only information available then and all candidates share identical eligible windows.
  - Evaluate production_six_factor, t2_comparator, trend_short_5_10_20, trend_medium_20_60, and trend_long_120_250; similar_market_blend remains branch-locally BENCHMARK_UNAVAILABLE without trusted aligned benchmark evidence.
  - Pre-register metrics and thresholds before results: median return delta >=0.003, paired utility win rate >=0.60, recent-four utility wins >=3, median drawdown worsening <=0.003, worst-return worsening <=0.005; failing candidates remain DOES_NOT_QUALIFY and production never changes in this task.
  - Output immutable per-window audit evidence plus aggregate return, drawdown, volatility, Sharpe, Calmar, coverage, factor contribution, reason codes, data hashes, command/date range/exit code/artifact paths; record failed experiments as well as successful ones.
  - Focused tests, data coverage and causality checks, Ruff, py_compile, diff-check and scope-check pass; research-only changes must not import into or activate direct/formal production paths.
---

## Goal

Build and run a research-only, point-in-time deterministic replay over the accepted E0 qfq snapshot and official 20-session labels to compare production, T2, and short/medium/long trend slots before any Agent fusion.

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

- 2026-08-09T16:38:02+08:00 `DRAFT`: Task created.
- 2026-08-09T16:49:04+08:00 `LOCATED`: Scout complete: data boundaries verified (calendar/labels 2024-2026, qfq 2020-2026), trust-gate and loader gaps surfaced; location.json confidence 0.84, validate-location passed
- 2026-08-09T16:52:55+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-09T16:52:58+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-09T17:03:03+08:00 `BLOCKED`: Blocked by WP1-E2P: real admitted calendar/corporate-action evidence cannot currently satisfy PointInTimeFactorInput; bypass through private kernels rejected.
- 2026-08-11T10:06:06+08:00 `DRAFT`: WP1-E2P-R1 closed; stale 2026-08-09 baseline must not be reused. Reopened for read-only relocation against the accepted public loader and typed operate bridge.
- 2026-08-11T10:16:51+08:00 `BLOCKED`: Blocked by WP1-E2T: public per-decision FactorSnapshot and OfficialForwardLabel objects cannot currently pass provider-owned factor-research admission; replay-local trust bypass rejected.
- 2026-08-11T17:35:45+08:00 `CLOSED`: Superseded by fresh-baseline task WP1-E2C-R1, which passed independent Codex review at LOCAL_IMPLEMENTED / RESEARCH_ONLY; this stale baseline must never be reused.
