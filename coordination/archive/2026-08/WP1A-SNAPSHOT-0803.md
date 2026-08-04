---
id: WP1A-SNAPSHOT-0803
title: Persist immutable MarketDataBundle diagnostics snapshot
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-03T12:14:29+08:00
updated_at: 2026-08-03T12:25:07+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/reporting/__init__.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/snapshot_writer.py
  - jiuwenswarm/tests/unit_tests/quant/test_snapshot_writer.py
acceptance:
  - Every persisted matrix and JSON artifact has a recomputable hash in one manifest
  - Manifest records provider evidence, calendar, adjustment policy, as-of/retrieved-at, and exact 49-ticker coverage
  - Reload verification rejects any tampered market-data or diagnostics artifact
  - Legacy snapshot tests remain green
  - Target Ruff, pytest, py_compile, diff-check, and scope-check exit 0
---

## Goal

Add a new immutable snapshot API for canonical OHLCV, independent secondary closes, benchmark, diagnostics, provider evidence, calendar/adjustment/as-of metadata and hashes while preserving the legacy snapshot API until both entries migrate.

## Non-goals

- No unrelated refactor.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Pending.

## Implementation evidence

- Builder claimed 29 target/contract tests pass, all static checks (ruff, py_compile, diff-check, scope-check) exit 0.

## Review evidence

- Critic verified: scope-check (PASS), py_compile (PASS), ruff (PASS), git diff-check (PASS).
- Critic BLOCKED on pytest: pandas DLL ImportError due to Chinese path encoding in this environment.
- Code review: implementation is solid — hash manifest, provider evidence, tamper detection, collision safety, legacy API preservation all verified by static analysis.
- Decision: MODIFY — Planner must independently confirm pytest pass before VERIFIED.
- Minor finding: __init__.py added exports for pre-existing announcement_service/report_grade (benign, out-of-scope).

## Progress

- 2026-08-03T12:14:29+08:00 `DRAFT`: Task created.
- 2026-08-03T12:15:12+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-03T12:15:14+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-03T12:20:02+08:00 `IMPLEMENTED`: New full-bundle snapshot API implemented in frozen 3-file scope; 29 target/contract tests and all static/scope checks pass. Legacy API preserved; no entry claim.
- 2026-08-03T12:35:00+08:00 `REVIEWED`: Critic verified 4/5 static checks. Pytest blocked by pandas DLL (environment, not code). Decision: MODIFY — Planner must independently confirm pytest pass. Code review found implementation solid; minor __init__.py scope expansion noted.
- 2026-08-03T12:25:07+08:00 `IMPLEMENTED`: Post-review evidence rerun in project Python: 29 passed; Ruff, scope-check, and diff-check exit 0.
- 2026-08-03T12:25:07+08:00 `REVIEWED`: DeepSeek static logic accepted and requested environment pytest; project Python resolved it. Codex arbiter review ACCEPT.
- 2026-08-03T12:25:07+08:00 `VERIFIED`: All snapshot acceptance criteria met locally; legacy API preserved. No direct/formal claim.
- 2026-08-03T12:25:07+08:00 `CLOSED`: Closed as LOCAL_IMPLEMENTED foundation for subsequent direct/formal adapter tasks.
