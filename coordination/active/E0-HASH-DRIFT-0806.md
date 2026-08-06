---
id: E0-HASH-DRIFT-0806
title: Restore deterministic Factor Registry implementation binding
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T09:40:00+08:00
updated_at: 2026-08-06T09:55:00+08:00
allowed_files:
  - coordination/active/E0-HASH-DRIFT-0806.md
  - jiuwenswarm/jiuwenswarm/quant/candidate_factors.py
  - jiuwenswarm/jiuwenswarm/quant/factor_registry.py
  - jiuwenswarm/tests/unit_tests/quant/test_candidate_factors.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_registry.py
acceptance:
  - Identify whether the registry or implementation changed and preserve the intended factor formula.
  - The focused Factor Registry and candidate-factor test suites pass.
  - A stale or mismatched implementation hash still fails closed.
  - scope-check, Ruff and git diff --check pass.
---

## Goal

Diagnose and repair the current `trend_consistency_5_10_20` implementation-hash
drift without changing the frozen factor formula, production strategy, E1P gate or
research evidence level.

## Non-goals

- Do not implement WP1-E2/E3/E4.
- Do not admit a new Provider or construct a real factor snapshot.
- Do not change production factor weights or strategy selection.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- The registry remains fail-closed when executable source differs from its bound hash.
- `production_six_factor` and `T2=RESEARCH_ONLY` remain unchanged.

## Locate brief

- Scout confidence `0.99`; validated `location.json` SHA-256
  `700eac84ef0a33f1680ea23f287c71b100a272303cb8785a53a010ee71894981`.
- Root cause: `_function_dependency_closure()` only reads the outer
  `code.co_names`. Python 3.9/3.11 place `_momentum` in the list-comprehension
  code object, while Python 3.12 exposes it in the outer code object. Identical
  source therefore hashes differently.
- Frozen repair: recursively traverse nested code objects, preserve the formula,
  and coordinately repin only the trend-consistency factor to the complete
  transitive-closure hash.

## Implementation evidence

- Builder changed only the frozen source/test files. `_code_global_names()` now
  recursively visits nested `CodeType` constants, so Python 3.11 and 3.12 bind
  the same transitive helper set. The sole coordinated pin is now
  `532fd547407203b4ebb51d4ec054adcb1d71752b46d8f573f854c6c229010406`.
- Focused tests: `29 passed`; Ruff, Python 3.11 parity probe, diff-check and
  scope-check all exited `0`. Full commands are in `implementation.json`.

## Review evidence

- Independent Critic verdict `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`; review SHA-256
  `c3178d74f380a992f63aeab1dfce38416eb95e89120c1af0bcc493e40fe4c05a`.
- Critic independently passed the focused suite on Python 3.11.15 and 3.12.13
  (`29 passed` on each), confirmed all 12 implementation hashes match across
  interpreters, and retained stale/helper/parameter tamper rejection.

## Progress

- 2026-08-06T09:40:00+08:00 `DRAFT`: Task created from full-roadmap audit after a fresh focused run exposed one root hash mismatch and nine cascading E0 failures.
- 2026-08-06T09:44:00+08:00 `LOCATED`: Planner validated the read-only Scout artifact, approved the five-file write scope and rejected a pin-only repair.
- 2026-08-06T09:50:00+08:00 `IMPLEMENTED`: Interpreter-independent dependency binding and coordinated repin pass focused and negative tests; awaiting independent Critic review.
- 2026-08-06T09:55:00+08:00 `CLOSED`: Planner accepted the independent zero-finding review and verified scope, static checks, Python-version parity and 95 adjacent E0/E1/Provider/contract regressions.
- 2026-08-06T09:45:10+08:00 `READY`: Baseline frozen; implementation may start.
