---
id: DYNAMIC-FACTOR-RESEARCH-0805
title: Implement decision-time factor research snapshots
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T13:06:50+08:00
updated_at: 2026-08-05T13:51:07+08:00
allowed_files:
  - .claude/discussion.md
  - VALIDATION.md
  - coordination/active/DYNAMIC-FACTOR-RESEARCH-0805.md
  - jiuwenswarm/jiuwenswarm/quant/factor_research.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_research.py
acceptance:
  - A frozen single-version threshold policy computes coverage, cross-sectional rank IC evidence, direction and bounded shrinkage using only labels whose official exit is complete before the decision time; untrusted evidence and insufficient or unstable samples fail closed; deterministic hashes, negative causality tests, independent Critic, diff and scope checks pass; production_six_factor, T2, WP1-C and direct/formal remain unchanged.
---

## Goal

Implement WP1-E1 as a research-only, point-in-time factor efficacy, direction and shrinkage snapshot over the exact WP1-E0 Registry and only matured official 20-session labels.

## Non-goals

- Do not create E2 candidate strategies, similarity retrieval, Agent fusion,
  portfolio selection, historical outer evaluation or a production integration.
- Do not edit or re-export E0, production factors/configs, WP1-B/C,
  direct/formal entry points, stock-pool metadata or role prompts.
- Do not fetch data, populate a trust manifest with invented sources, scan
  thresholds or claim that current market evidence has passed.

## Invariants

- All observations predict one target only: one complete trading-day embargo,
  entry open, fixed shares for 20 sessions, twentieth-session close exit.
- Label `available_at` must be at or after exit close and no later than the new
  research decision time; equality at an exact timezone-aware 15:00 exit close
  is allowed. Recent observations without a matured label cannot enter.
- Input windows are strictly chronological and non-overlapping
  (`next.entry_date > previous.exit_date`); duplicates and daily overlapping
  pseudo-samples fail closed rather than inflate evidence.
- Canonical calendar, sector metadata and official labels require Planner-frozen
  source manifests binding authority, version, archive SHA-256 and the complete
  canonical payload. Runtime manifests remain empty until real Provider tasks
  populate them; public computation therefore fails closed by default.
- Per-date IC uses common `AVAILABLE`, finite tickers after demeaning both factor
  and target within each evidenced sector, then average-tie Spearman ranks across
  the cross-section. Every one of six sectors needs at least two common tickers;
  constant ranks are unavailable, never zero.
- The public API always uses the exact ordered E0 Registry and the single frozen
  policy below; callers cannot inject a subset, reordered Registry or thresholds.
- `production_six_factor`, T2, WP1-C and direct/formal behavior remain unchanged.

## Frozen policy v1

- `policy_id = wp1_e1_rank_ic_v1`; cadence `NON_OVERLAPPING_OFFICIAL_WINDOWS`.
- Exact universe: 49 tickers and 6 evidenced sectors; minimum common cross-section
  `30`, minimum per-date coverage `30/49`, minimum valid matured dates `8`.
- Direction magnitude gate: absolute median rank IC `>= 0.03`.
- Direction consistency gate: at least `0.625` of valid IC signs agree with the
  expected direction for `EXPECTED`, or symmetrically oppose it for `FLIPPED`;
  otherwise `NEUTRAL`.
- Any input/evidence/coverage/sample/stability gate failure yields `NEUTRAL` and
  multiplier `0`; no fallback label or imputation is permitted.
- For a qualified direction, multiplier is the product of four clipped terms:
  `abs(median_ic)/0.10`, `sign_consistency/0.75`,
  `median_coverage/0.80`, and `valid_dates/16`, each clipped to `[0,1]`.
  The final multiplier is clipped to `[0,1]`; there is no search or LLM override.

## Locate brief

- Independent Scout confidence `0.90`; validated artifact:
  `output/agent_handoffs/DYNAMIC-FACTOR-RESEARCH-0805/location.json`.
- Reuse E0 `FactorSnapshot`/Registry hash and `CompetitionWindowPolicy` semantics,
  but not the obsolete close-to-close `ic_walk_forward` label or mutable
  challenger dictionaries.
- Located no hash-bound official per-ticker label or PIT sector evidence. The
  implementation must add research-only evidence schemas and keep both real
  trust manifests empty instead of treating `SECTOR_MAP` or caller hashes as proof.

## Test-first evidence

- Before implementation, the new test module failed collection with
  `ModuleNotFoundError: jiuwenswarm.quant.factor_research`; 0 tests collected.
- After implementation: WP1-E1 focused tests `11 passed`; E0+E1 research
  regressions `39 passed`; official window/nested/direct/market regressions
  `65 passed`; Ruff, pycompile and production-import isolation pass.
- The wider quant directory collected 475 tests: `455 passed, 1 skipped,
  19 failed`. The 19 failures are the already known missing ignored WP1-B
  review artifacts under `output/` and the missing out-of-scope resource Skill
  mirror; none touches an allowed E1 file. This is recorded as an environment
  limitation, not misreported as a green full-suite result.

## Implementation evidence

- Added research-only immutable `FactorResearchPolicy`, sector metadata and
  official forward-label evidence, trusted canonical calendar/E0 observation
  binding, per-date sector-residualized Rank IC, deterministic direction gates
  and bounded shrinkage metrics for the exact twelve-factor Registry.
- Policy hash:
  `7de2b5b29e34baa4d4e1c2a04f4a9cd1ee4178014efd526713c5e788adcf06d0`.
- The public API exposes no Registry or policy injection. It rejects overlapping
  windows, weekend/delayed/skipped canonical sessions, future/unmatured labels,
  mismatched decision dates/calendars, malformed 1+20 windows, incomplete 49/6
  sectors, untrusted calendar/labels/sectors/E0 snapshots, weak samples,
  insufficient coverage and constant ranks.
- Runtime trust roots remain immutable and empty; tests use explicit test-only
  roots. No real factor direction or multiplier has been claimed.

## Review evidence

- First independent verdict `CHANGES_REQUIRED`, P1=1: a trusted label could use
  a Saturday embargo and skipped valuation sessions because only monotonic dates
  were checked. Labels and E0 snapshots now bind one trusted full canonical
  calendar and validate exact positions `i/i+1/i+2..i+21`; weekend, delayed
  entry, skipped sessions and exit-close 14:59/15:00 boundaries are tested.
- Final independent re-review `ACCEPT`; `findings=[]`, P0/P1/P2/P3 all zero.
  The Critic re-executed the calendar counterexamples, hash tampering, threshold
  boundary, tie handling, scope and production-isolation checks. Final
  `review.json` SHA-256:
  `80e89fd85381a891d456bf0ab60511e5f05bc6d35e810e448027537c23296a17`.

## Progress

- 2026-08-05T13:06:50+08:00 `DRAFT`: Task created.
- 2026-08-05T13:17:27+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T13:17:27+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T13:27:57+08:00 `IMPLEMENTED`: WP1-E1 policy, trusted evidence schemas, matured official labels, sector-residual Rank IC, direction and bounded shrinkage implemented; E1 10/10, research 38/38 and related regression 65/65 pass; independent Critic pending.
- 2026-08-05T13:41:26+08:00 `IMPLEMENTED`: Closed the canonical-calendar P1; E1 11/11, E0+E1 39/39 and related 65/65 pass; re-review requested.
- 2026-08-05T13:51:07+08:00 `REVIEWED`: Independent Critic ACCEPT; P0-P3 all zero; review SHA-256 80e89fd85381a891d456bf0ab60511e5f05bc6d35e810e448027537c23296a17.
- 2026-08-05T13:51:07+08:00 `VERIFIED`: Planner verified E1 11/11, E0+E1 39/39, Ruff, pycompile, diff and frozen scope; real trust roots remain empty and production unchanged.
- 2026-08-05T13:51:07+08:00 `CLOSED`: WP1-E1 closed as LOCAL_IMPLEMENTED; next task must build real Provider trust manifests before E2.
