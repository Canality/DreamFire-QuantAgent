---
id: WP1B-EVALUATION-0804
title: Competition-aligned nested evaluation and strategy promotion
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-04T17:40:19+08:00
updated_at: 2026-08-05T09:35:21+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/WP1B-EVALUATION-0804.md
  - jiuwenswarm/evaluation/phase_b_experiment.py
  - jiuwenswarm/evaluation/unified_baseline_evaluation.py
  - jiuwenswarm/jiuwenswarm/quant/evaluation_protocol.py
  - jiuwenswarm/jiuwenswarm/quant/nested_evaluation.py
  - jiuwenswarm/tests/unit_tests/quant/test_competition_window_policy.py
  - jiuwenswarm/tests/unit_tests/quant/test_nested_evaluation.py
  - jiuwenswarm/tests/unit_tests/quant/test_phase_b_experiment.py
  - jiuwenswarm/tests/unit_tests/quant/test_unified_baselines.py
acceptance:
  - Machine-readable decision/embargo/entry/20 valuation/exit dates; embargo leakage negative tests; entry-open/exit-close fixed-share accounting; outer-result isolation; paired table/bootstrap/P10/drawdown/regime evidence; deterministic rerun; dirty runs cannot promote; competition-aligned baseline and frozen scope checks pass.
---

## Goal

Implement the shared one-trading-day embargo, fixed-20-day nested evaluation, bootstrap evidence, risk non-inferiority, reproducibility and dirty-run promotion gates required by DEVELOPMENT_PLAN.md WP1-B.

## Non-goals

- No unrelated refactor.
- Do not modify production strategy weights, direct/formal entry paths, PA legacy
  challengers, or any historical `phase_b_*.json` / `unified_baselines_*.json`.
- Do not promote a strategy from this imported dirty worktree or from the
  raw/unadjusted historical Sina snapshot.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- `CompetitionWindowPolicy` remains the only source of embargo/entry/holding/
  exit semantics.
- Old next-day-entry and mutable `*_latest.json` results remain historical only.
- A statistical pass cannot override leakage, provenance, coverage, pairing,
  risk non-inferiority, determinism or clean-run failure.

## Locate brief

- Accepted Scout confidence: 0.98. WP1-B0 already computes one full embargo
  day, entry-open, 20 close valuations and fixed shares; 32 focused baseline
  tests pass.
- Missing promotion boundary: no nested outer isolation, moving-block
  bootstrap, P10/worst-drawdown non-inferiority, recent/regime evidence,
  deterministic evaluation hash or dirty-run promotion guard.
- Window records omit the exact 20 `valuation_dates`; evaluator leakage checks
  cover price history length only, not factor/evidence timestamps.
- Current Phase B always overwrites tracked `phase_b_latest.json`; legacy PA
  consumers also assert the old 21-window shape. They are excluded from this
  task and from the new promotion path.
- WP1-A is production `PATH_PASSED`, but the historical Phase-B Sina snapshot
  is raw/unadjusted and lacks the shared secondary-source/economic-policy
  binding. It may exercise the framework only as `RESEARCH_ONLY`; promotion
  remains fail-closed until a verified WP1-A snapshot binding is supplied.
- Location artifact:
  `output/agent_handoffs/WP1B-EVALUATION-0804/location.json`.

## Implementation evidence

- `CompetitionWindowPolicy` now serializes the exact decision/embargo/entry/20
  valuation/exit sequence and fails closed when price, factor or timestamped
  evidence crosses the decision cutoff.
- New `nested_evaluation.py` locks candidate selection to the first ten inner
  windows and exposes no outer rows to the selector. The selected formula is
  evaluated on ten untouched chronological outer windows with exact pairing,
  circular moving-block Bootstrap, P10/worst return, median/worst drawdown,
  recent-weighted and per-regime evidence.
- Promotion requires every frozen statistical threshold plus current protocol,
  verified WP1-A snapshot binding and clean Git state. Malicious outer access,
  mismatched windows, missing valuation dates, binding tampering, dirty state
  and risk-bound failures have negative tests.
- Unified/Phase-B evaluators no longer emit an actionable `QUALIFIES` from the
  legacy all-window comparison and never update tracked `*_latest.json` files;
  new artifacts are create-once under `output/wp1b_evaluations/`.
- Focused validation: 57 passed; Ruff, py_compile and task-file diff-check
  passed. The generic scope checker reports only the separately owned
  `WP1C-CHALLENGER-SCOUT-0804.md`, which was created in parallel and closed by
  the Planner; all nine WP1-B source/test changes are inside the frozen
  whitelist.
- Two runs on the same immutable historical snapshot produced identical
  evaluation hash
  `b1cd9a849bcbf53f1f32bad8363c623694782791f797e201f7aeda2296783099`.
  The inner selector locked `phase_b_t2_score_alloc`; outer evidence passed
  all six statistical gates: median return delta `+0.8356pp`, Bootstrap
  positive probability `1.0`, utility win rate `0.8`, and P10/median/worst
  drawdown non-inferiority. Git is dirty and the raw Sina snapshot is not
  WP1-A verified, so both runs are correctly `RESEARCH_ONLY` and never
  promotion eligible. Immutable artifacts:
  `wp1b_20260804_181757.json` and `wp1b_20260804_181808.json`.

## Review evidence

- Independent Critic `ACCEPT`, zero blocking findings. Final review artifact:
  `output/agent_handoffs/WP1B-EVALUATION-0804/review.json`, SHA-256
  `35c72c69f1defe417cb218f84f0af55efb520b10af80883fe255e724e0b3284d`.
- Critic independently reran 57 tests, Ruff and diff-check; recomputed run6/run7
  artifact hashes; compared exact date identities and deterministic
  details/evaluation hashes; and confirmed all 8 frozen historical JSON hashes
  are unchanged.
- Planner accepts the task-owned scope check. The only repository-wide change
  excluded is the separately owned and already `CLOSED` WP1-C read-only Scout
  contract, whose path, owner and SHA-256 are explicit in `scope_check.json`.
- Residual risk is bounded and disclosed: no live promotion-eligible WP1-A
  snapshot exists, only ten outer windows are available, and the observed run
  must remain `RESEARCH_ONLY`.

## Progress

- 2026-08-04T17:40:19+08:00 `DRAFT`: Task created.
- 2026-08-04T17:47:22+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-04T17:47:22+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-04T17:55:59+08:00 `IMPLEMENTED`: Fail-closed nested promotion framework implemented test-first. 48 focused tests, Ruff, py_compile, diff-check and frozen scope-check pass. Two same-snapshot runs have identical evaluation hash; historical latest files unchanged; observed T2 outer evidence fails worst-drawdown gate and remains non-promotable.
- 2026-08-04T18:10:30+08:00 `IMPLEMENTED`: Critic counterexamples closed with independently recomputed Git/config/snapshot/WP1-A report bindings, exact default-plan promotion gating and same-day 15:00 cutoff checks. 50 focused tests pass. Two reruns have identical nested hash and statistical qualification, but remain `RESEARCH_ONLY` because the worktree is dirty and snapshot is not WP1-A verified.
- 2026-08-04T18:18:20+08:00 `IMPLEMENTED`: Final Critic counterexample closed: each hash-bound WP1-A report must also parse as JSON with semantic `VERIFIED` status. 57 focused/backtest tests pass; two post-fix reruns preserve the deterministic nested hash and `RESEARCH_ONLY` gate.
- 2026-08-04T18:20:16+08:00 `REVIEWED`: Independent Critic ACCEPT: 57 focused/backtest tests, Ruff, diff-check, owned scope, deterministic run6/run7 and historical evidence hashes verified; no blocking finding.
- 2026-08-05T09:35:21+08:00 `VERIFIED`: Planner verified the accepted Critic evidence and WP1-C's downstream binding; result remains RESEARCH_ONLY with no promotion.
- 2026-08-05T09:35:21+08:00 `CLOSED`: Acceptance complete; the nested evaluation boundary is frozen and subsequent work must not reinterpret the research-only result.
