---
id: WP1A-DIRECT-0803
title: Wire direct pipeline to shared MarketDataBundle
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-03T12:49:30+08:00
updated_at: 2026-08-03T13:01:28+08:00
allowed_files:
  - jiuwenswarm/scripts/run_quant_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_direct_pipeline_adapter.py
acceptance:
  - Direct entry no longer imports or calls Extension private _fetch_real_data
  - Direct entry requires exact official 49 stocks and passed shared diagnostics before factors
  - Direct result and candidate report bind the same nine-file decision-time snapshot and manifest hash
  - Direct targeted tests, Ruff, py_compile, diff-check, scope-check, and real entry run pass
---

## Goal

Make the direct run_quant_pipeline entry use the same validated shared market bundle, compact diagnostics, immutable decision-time snapshot, and fail-closed rules as the formal Extension without changing strategy semantics.

## Non-goals

- No unrelated refactor.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Qwen Scout failed before producing an artifact because the launcher exceeded its 65,536-token context. Codex reused the accepted WP1A integration map and bounded the change to the direct script plus one new focused adapter test. The only production defect boundary is the private Extension fetcher, legacy snapshot, false EvidenceRef timing, and current-day default in `run_quant_pipeline.py`.

## Implementation evidence

- Pending.

## Review evidence

- Decision: ACCEPT. All 4 acceptance criteria independently verified.
- AC1 (no Extension fetcher): zero matches in source + explicit negative test.
- AC2 (49-stock pool + diagnostics before factors): pool guard before provider call, diagnostics gate before factor computation, 2 negative tests (non-official pool + malformed bundle).
- AC3 (nine-file snapshot + manifest hash): _decision_evidence_bundle strips forward rows, write_market_data_snapshot produces 9 files with manifest_sha256, EvidenceRef binds same hash, install verification passes.
- AC4 (all gates pass): 8/8 exit codes = 0, 49 tests pass / 0 fail, rails 4/4, quality PASSED, scope-check no violations.
- Negative cases: 3 targeted tests (pool rejection, malformed bundle fail-closed, incomplete session default).
- Time causality: future-date rejection, timezone-aware as-of, forward-row exclusion on all 7 OHLCV frames.
- Residual: announcement provider returned 0 facts (TECHNICAL_PASSED); Planner attention needed for submission readiness.

## Progress

- 2026-08-03T12:49:30+08:00 `DRAFT`: Task created.
- 2026-08-03T12:52:00+08:00 `DRAFT`: Qwen Scout attempt invalid (69,643 > 65,536 tokens); no source changes.
- 2026-08-03T12:53:15+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-03T12:53:17+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-03T12:58:31+08:00 `IMPLEMENTED`: Codex implementation complete: 49 related tests pass and real direct entry exits 0 with bound 49-report candidate.
- 2026-08-03T13:01:00+08:00 `REVIEWED`: Critic ACCEPT — all 4 acceptance criteria verified; scope-check clean; 3 negative tests confirm fail-closed; review.json written with findings, checked_commands, and residual_risks.
- 2026-08-03T13:01:28+08:00 `VERIFIED`: Codex verified real direct entry, 49 related tests, dual Ruff, py_compile, exact candidate hash binding, 49 reports, 9 snapshot files, and 4/4 runtime Rails.
- 2026-08-03T13:01:28+08:00 `CLOSED`: Accepted as direct PATH_PASSED for the fixed historical run; full dual-path BUSINESS_PASSED remains pending JiuwenSwarm formal entry.
