---
id: DYNAMIC-FACTOR-REGISTRY-0805
title: Implement the research-only Factor Registry and trend candidate snapshot
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T12:11:30+08:00
updated_at: 2026-08-05T13:01:28+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/DYNAMIC-FACTOR-REGISTRY-0805.md
  - jiuwenswarm/jiuwenswarm/quant/candidate_factors.py
  - jiuwenswarm/jiuwenswarm/quant/factor_registry.py
  - jiuwenswarm/tests/unit_tests/quant/test_candidate_factors.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_registry.py
acceptance:
  - Exactly twelve versioned trend definitions expose the complete WP1-E0 metadata and verified implementation hashes; pure point-in-time computations enforce decision time, canonical contiguous sessions, corporate-action policy, exact minimum lookbacks and unavailable-not-zero behavior; focused tests, Ruff, pycompile, independent Critic, production-boundary assertions, diff and frozen scope pass; evidence remains LOCAL_IMPLEMENTED and production_six_factor/T2/WP1-C/direct/formal behavior is unchanged.
---

## Goal

Implement the first research-only WP1-E0 foundation: an immutable, auditable
Factor Registry plus deterministic point-in-time raw snapshots for the twelve
preregistered trend factors.

## Non-goals

- Do not implement factor efficacy, direction flipping, dynamic weights,
  similarity retrieval, strategy construction, Agent fusion or historical replay.
- Do not modify or import from current production `factors.py`,
  `strategy_configs.py`, Extension, direct/formal entry points or role prompts.
- Do not fetch data, run a parameter scan, change a strategy status or claim
  business/path completion.

## Invariants

- Every definition supports only the official forecast horizon `(20,)`; lookback
  periods are inputs, not alternate targets.
- Only timezone-aware decision times and data at or before that time are valid.
- Required canonical sessions must be consecutive, unique, finite and positive;
  gaps and unverified corporate-action policy fail closed.
- Insufficient history and zero volatility are explicit unavailable results,
  never fabricated zeros.
- `production_six_factor`, T2 and the closed WP1-C registry remain byte-for-byte
  outside this task.

## Locate brief

- Independent Scout confidence `0.91`; machine-readable artifact:
  `output/agent_handoffs/DYNAMIC-FACTOR-REGISTRY-0805/location.json`.
- Located a one-way research dependency and confirmed current `raw_unadjusted`
  provider metadata, generic calendar checks and date-only indexes cannot prove
  the E0 corporate-action/session/close-availability contracts.

## Test-first evidence

- Before implementation, both new test modules failed collection with
  `ModuleNotFoundError` for `candidate_factors`; 0 tests were collected.
- After implementation: focused E0 tests `28 passed`; existing direct adapter
  and market-data service regressions `20 passed`.
- The broader quant directory collected 460 tests: `440 passed, 1 skipped,
  19 failed`. All 19 failures require ignored `output/` review artifacts or the
  missing out-of-scope resource Skill mirror; they do not import the E0 modules
  through production paths and were not misreported as green.

## Implementation evidence

- Added an immutable ordered 12-definition Registry with exact metadata,
  minimum lookbacks and canonical registry hash
  `81f4c64170e3b6ee9c55377b5d88d3c64903b28a2f52131bfcbf5fbced9e12ab`.
- Added pure raw snapshots with source-bound implementation hashes, input and
  snapshot hashes, explicit unavailable status, exact canonical-session match,
  timezone-aware decision close and corporate-action evidence gates.
- Calendar evidence binds authority/source/version/full sessions; corporate-action
  evidence binds policy/tickers/window/results. Kernel hashes discover transitive
  helpers; snapshot serialization revalidates its canonical payload hash.
- The runtime authority manifest is intentionally empty until a separate Provider
  task freezes real archived sources. Public computation therefore fails closed
  by default; formula/snapshot tests install an explicit test-only manifest that
  binds the full structured evidence hash, never an arbitrary caller hash.
- The public snapshot API always uses the exact ordered twelve-definition
  Registry and exposes no registry injection. Boolean, complex and other
  non-real prices are rejected before float conversion.
- Production isolation is AST-tested; the current production pointer and weights
  remain unchanged. Ruff, pycompile and `git diff --check` passed.

## Review evidence

- First independent Critic verdict `CHANGES_REQUIRED`: P1=2, P2=3. Findings
  covered self-certified evidence strings, incomplete execution/dependency hash
  binding, mutable snapshot payloads, noncanonical DataFrame hashing and shallow
  production isolation tests.
- All five first-review findings were fixed inside the frozen scope. The next
  review found one residual provenance P1 and two P2 issues (Registry injection
  and complex-price coercion); all three were fixed. Final independent verdict
  is `ACCEPT`, P0/P1/P2/P3 all zero. `review.json` SHA-256:
  `9c786efee86a0908b78c733204d28adc3fe74cee688659d740dd4376806b6bba`.

## Progress

- 2026-08-05T12:11:30+08:00 `DRAFT`: Task created from clean plan commit `43559a4`.
- 2026-08-05T12:16:47+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T12:16:47+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T12:24:51+08:00 `IMPLEMENTED`: E0 Registry, pure snapshots and focused regressions pass; independent Critic pending.
- 2026-08-05T12:39:00+08:00 `IMPLEMENTED`: Closed two P1 and three P2 findings; E0 24/24 and static checks pass; re-review pending.
- 2026-08-05T12:56:54+08:00 `IMPLEMENTED`: Runtime trust manifest now defaults empty/fail-closed; removed Registry injection and rejected lossy non-real prices; E0 28/28; final re-review pending.
- 2026-08-05T13:01:28+08:00 `REVIEWED`: Independent Critic ACCEPT; P0/P1/P2/P3 all zero; review SHA-256 9c786efee86a0908b78c733204d28adc3fe74cee688659d740dd4376806b6bba.
- 2026-08-05T13:01:28+08:00 `VERIFIED`: Planner verified 28 focused tests, 20 production-boundary regressions, Ruff, pycompile, registry hash, diff-check and frozen scope.
- 2026-08-05T13:01:28+08:00 `CLOSED`: Accepted as LOCAL_IMPLEMENTED research-only WP1-E0; authority manifest remains empty and production remains unchanged.
