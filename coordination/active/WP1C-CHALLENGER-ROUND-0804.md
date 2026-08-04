---
id: WP1C-CHALLENGER-ROUND-0804
title: Frozen three-mechanism WP1-C challenger round
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-04T18:22:20+08:00
updated_at: 2026-08-04T18:53:12+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/WP1C-CHALLENGER-ROUND-0804.md
  - jiuwenswarm/evaluation/challenger_round.py
  - jiuwenswarm/evaluation/unified_baseline_evaluation.py
  - jiuwenswarm/jiuwenswarm/quant/challenger_mechanisms.py
  - jiuwenswarm/jiuwenswarm/quant/challenger_registry.py
  - jiuwenswarm/tests/unit_tests/quant/test_challenger_mechanisms.py
  - jiuwenswarm/tests/unit_tests/quant/test_challenger_registry.py
  - jiuwenswarm/tests/unit_tests/quant/test_challenger_round.py
acceptance:
  - Exact three frozen mechanisms and canonical registry; bound WP1-B evidence; inner prescreens; one-shot outer evaluation; immutable research evidence; no formula scan, chaining, legacy latest overwrite or production pointer change; focused tests, independent Critic and scope review pass.
---

## Goal

Implement and evaluate exactly the three preregistered WP1-C single-mechanism challengers on the accepted WP1-B nested boundary without production mutation or outer-driven retuning.

## Non-goals

- No unrelated refactor.
- No edits to `strategy_configs.py`, factors, PositionSizer, market-width
  definitions, direct/formal entry points, Agent prompts or production registry.
- No fourth candidate, parameter/lookback/threshold scan, regime retuning,
  mechanism chaining, legacy latest consumption or historical evidence rewrite.
- No production promotion from this dirty worktree or unverified historical
  snapshot.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- Common base is exactly `phase_b_t2_score_alloc`; production remains
  `production_six_factor`; stock/sector/cash constraints remain 10%/25%/5%.
- Bind accepted WP1-B review SHA-256
  `35c72c69f1defe417cb218f84f0af55efb520b10af80883fe255e724e0b3284d`
  and evaluation hash
  `b1cd9a849bcbf53f1f32bad8363c623694782791f797e201f7aeda2296783099`.
- Every candidate starts from an identical fresh T2 score frame. Inner evidence
  may only pass/fail a frozen candidate; outer results may never construct,
  select, tune or rerun a formula.
- Trend formula: 5/10/20 percent-rank-average returns, exact three-sign
  agreement gate, bounded `0.15 * consistency` delta in `[-0.15, 0.15]`.
- Sector formula: shared six-sector 20-day relative-strength percent rank and
  positive breadth, equal 0.5/0.5 blend, bounded `0.10 * leadership` delta in
  `[-0.10, 0.10]`.
- Tail formula: downside-vol trigger/full `0.40/0.60`, negative-gap
  `-0.05/-0.10`, 60-day drawdown `0.20/0.30`; subtract `0.20 * max(severity)`
  for an exact `[-0.20, 0]` delta.
- Create-once evidence only; legacy latest and production pointer are immutable.

## Locate brief

- Inherits the accepted 0.98-confidence read-only Scout artifact
  `output/agent_handoffs/WP1C-CHALLENGER-SCOUT-0804/location.json`; the
  task-specific binding is
  `output/agent_handoffs/WP1C-CHALLENGER-ROUND-0804/location.json`.
- The injection seam is after T2 factor scores are computed/filtered and before
  positive Top-15 selection. Allocation and fixed-share backtest remain shared.
- New pure mechanism and registry modules keep production code unchanged; a
  run-scoped evaluator adapter applies one registered overlay at a time and
  delegates final outer evidence to the verified WP1-B evaluator.
- Trend inner prescreen: median 20-day rank IC >0, positive IC windows >=60%,
  paired median return delta >0. Sector: top-2 hit >=40%, sign agreement >=60%,
  paired median return delta >0. Tail: median max-DD delta <=-0.10pp, P10 return
  delta >=-0.20pp, median return delta >=-0.20pp. All are fixed AND gates.

## Implementation evidence

- Added three pure evaluation-only overlays with exact preregistered formulas,
  full decision-time 49/6 validation, immutable base-score copies, bounded
  deltas and JSON diagnostics. Tail input gaps fail closed by design.
- Canonical registry hash
  `e8add67ec0f556a5bc46bc7c8fdfcfd78cbe2836020b44e8b13ab41e99617a8d`
  binds exact candidate/formula payloads, T2 base, production pointer,
  constraints, WP1-B review SHA-256 and accepted evaluation hash. Any task,
  review, formula, candidate or production drift fails validation.
- Unified evaluator accepts an optional evaluation-only overlay at the located
  seam, asserts the overlay changes only composite values, keeps selection /
  allocation / constraints / fixed-share backtest unchanged, and records
  per-window diagnostics plus finite forward-target coverage.
- Runner uses only inner windows 0–9 for the three frozen prescreens. A
  construction/prescreen failure is written once and cannot reach outer data;
  each passing candidate would call the accepted WP1-B boundary exactly once.
  Evidence trees are create-once and contain preregistration, inner, outer,
  failures, details, decision, the canonical reproduction payload and a hash
  manifest; no latest pointer exists. The verifier recomputes the round hash
  and binds every details/inner/failure/outer payload, so rehashing a tampered
  manifest cannot create an accepted result.
- Focused mechanism/registry/runner plus WP1-B, timing, sizing, market-width
  and fixed-share regressions: 95 passed. Ruff, py_compile, diff-check and
  frozen scope-check pass with zero violations.
- Two exploratory failures were retained: first exposed one untradable forward
  target and led to explicit finite-target coverage; second confirmed the tail
  candidate's preregistered missing-open fail-close and led only to per-candidate
  failure retention, not formula or threshold changes.
- Final run directories `wp1c_20260804_184701` and `wp1c_20260804_184710`
  have identical registry, details, inner/failure and decision hashes; both
  have round hash
  `3b5c335066e0ec5a81f4d27b6c00db9cdc176c68ccc04831c023cd686aec7202`.
  All three candidates failed before outer evaluation: trend missed positive
  paired median return (`-0.0346pp`), sector sign agreement was `46.6667% <
  60%`, and tail failed construction on missing decision-time opens. Status is
  `DOES_NOT_QUALIFY`; no outer result was opened and production was unchanged.
- Each final tree passes an independent file-set/SHA-256/registry/decision /
  reproduction verifier over 12 evidence files. Manifest SHA-256 values are
  `cde4b69dbed571b57ed81d0f14209c85d63bde2eabbc886e40068c2e6e220f15`
  and `f9cb59f757f22c9b4206eff588ff7494025b794e680b00dd4448c0b9479b9df3`;
  both share canonical evidence file-map digest
  `216f2be6b9b7ab4bc333cc92bfab3159df33b78bded4f94041ba46b3d527a994`.
  The registry hash itself is a source-level frozen constant, so runtime
  mutation cannot mint a different accepted round.

## Review evidence

- Independent read-only Critic verdict `ACCEPT`, blocking findings `0`.
- Review artifact:
  `output/agent_handoffs/WP1C-CHALLENGER-ROUND-0804/review.json`; SHA-256
  `cdf5915578010959da3aaec9a622217b9fe9b2168219cc6bc635bacdefc31fb5`.
- Critic independently reran 95/95, Ruff, py_compile and diff-check; reverified
  final 12-file runs 184701/184710 and confirmed frozen production/latest
  hashes unchanged. It explicitly rejected the earlier stale 11-file trees.
- Residual limits are accepted and disclosed: dirty Git, raw/unadjusted
  non-WP1-A-verified snapshot, no live candidate reaching outer, two windows
  with 48 finite forward targets, and tail construction failure. None permits
  promotion; all reinforce the final `DOES_NOT_QUALIFY` decision.

## Progress

- 2026-08-04T18:22:20+08:00 `DRAFT`: Task created.
- 2026-08-04T18:23:59+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-04T18:24:00+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-04T18:38:20+08:00 `IMPLEMENTED`: Exactly three frozen mechanisms, canonical WP1-B-bound registry, inner-only prescreens and immutable runner implemented. 95 focused/regression tests pass. Two deterministic runs stop before outer with all candidates rejected; production unchanged.
- 2026-08-04T18:48:17+08:00 `IMPLEMENTED`: Added canonical reproduction binding and a manifest-rehash tamper counterexample. 95/95 regressions, Ruff and py_compile pass; fresh 12-file runs 184701/184710 independently verify to the same round hash. Earlier 11-file runs remain retained but are superseded as final evidence.
- 2026-08-04T18:51:41+08:00 `REVIEWED`: Independent Critic ACCEPT; 95/95 and both 12-file runs reverified; no blocking findings.
- 2026-08-04T18:53:12+08:00 `VERIFIED`: Planner verified Critic ACCEPT, deterministic evidence, frozen scope and honest DOES_NOT_QUALIFY decision.
- 2026-08-04T18:53:12+08:00 `CLOSED`: Acceptance complete; stop WP1-C Alpha search and retain frozen T2 baseline; no production/latest mutation.
