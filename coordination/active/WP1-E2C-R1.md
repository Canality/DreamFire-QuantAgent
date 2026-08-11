---
id: WP1-E2C-R1
title: Re-locate deterministic strategy-pool historical replay on accepted typed evidence
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-11T13:56:51+08:00
updated_at: 2026-08-11T15:26:39+08:00
allowed_files:
  - coordination/active/WP1-E2C-R1.md
  - jiuwenswarm/evaluation/strategy_pool_replay.py
  - jiuwenswarm/tests/unit_tests/quant/test_strategy_pool_replay.py
acceptance:
  - Read-only location.json enumerates every public evidence loader, strategy candidate, allocation/backtest caller, output contract and focused test needed for E2C.
  - Location proves the exact 49-stock/6-sector, E0 qfq, 604-label and per-decision FactorSnapshot trust path with no private kernel, monkeypatch trust or replay-local rank-IC copy.
  - Location preserves preregistered five-candidate metrics and thresholds, BENCHMARK_UNAVAILABLE fail-closed behavior, production isolation and failed-experiment recording.
  - No source, test, archive, documentation, direct/formal/RPC/E2E, network, commit or push action occurs before Codex accepts location and freezes a fresh baseline.
---

## Goal

Read-only re-location of E2C against the accepted v2 forward-label, operate, calendar, sector and FactorSnapshot public bridges; propose the smallest exact implementation whitelist without editing product code.

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

- 2026-08-11T13:56:51+08:00 `DRAFT`: Task created.
- 2026-08-11T13:59:38+08:00 `LOCATED`: Read-only re-location complete (local-code-scout): five candidates + BENCHMARK_UNAVAILABLE; decision set = calendar ∩ matured v2 labels ∩ >=251 prior ∩ operate coverage; minimal whitelist = 2 NEW replay files; no source/test/archive/docs change.
- 2026-08-11T14:16:54+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-11T14:16:54+08:00 `LOCATED`: Codex accepted read-only location; exact two-new-file implementation scope approved
- 2026-08-11T14:17:38+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T14:32:07+08:00 `IMPLEMENTED`: E2C replay implemented in 2 NEW files: 25 focused tests pass; ruff/py_compile/diff-check pass; scope-check passed=true violations=[]; deterministic replay exit 0 (~74s, 12 windows 2025-01-14..2025-12-11): production OK, t2 QUALIFIED, 3 trend slots DOES_NOT_QUALIFY (insufficient matured windows), similar_market_blend BENCHMARK_UNAVAILABLE. Artifact output/replay/strategy_pool_replay.json.
- 2026-08-11T14:42:37+08:00 `REVIEWED`: Codex independent review MODIFY: candidate minimum incorrectly 4 not 8; immutable audit/hash and aggregate output contract incomplete.
- 2026-08-11T14:42:39+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-11T14:48:53+08:00 `IMPLEMENTED`: MODIFY fixes applied: <8 comparable windows fails closed (7-fail/8-evaluable boundary tests); immutable audit/hash + aggregate (return/drawdown/vol/SR/Calmar/coverage/factor contribution) with verify_artifact tamper detection; 31 focused tests pass; ruff/py_compile/diff-check pass; scope-check passed=true violations=[]; replay exit 0 (~72s) artifact_sha256 b45fbaeb... (verify_artifact=True).
- 2026-08-11T15:26:39+08:00 `REVIEWED`: Codex review round 2 ACCEPT; scope, 31 focused tests, static checks, hash recomputation and independent replay passed.
- 2026-08-11T15:26:39+08:00 `VERIFIED`: Independent Windows local replay reproduced artifact SHA-256 and all candidate verdicts.
- 2026-08-11T15:26:39+08:00 `CLOSED`: Accepted at LOCAL_IMPLEMENTED only; production unchanged; no PATH/BUSINESS claim.
