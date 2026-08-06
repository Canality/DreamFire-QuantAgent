---
id: DYNAMIC-RESEARCH-PLAN-0805
title: Preregister dynamic factor research and bounded strategy selection roadmap
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T11:46:21+08:00
updated_at: 2026-08-05T12:10:08+08:00
allowed_files:
  - .claude/discussion.md
  - DEVELOPMENT_PLAN.md
  - VALIDATION.md
  - coordination/active/DYNAMIC-RESEARCH-PLAN-0805.md
acceptance:
  - Plan version and change record reflect the new architecture; all candidate research shares the official embargo/open/20-day/close target; old WP1-C remains frozen; production_six_factor and T2 evidence grades remain unchanged; Factor Registry, dynamic research, multi-cycle construction, similarity retrieval, bounded Agent debate/fusion, nested evaluation, resource and failure gates are split into ordered non-overlapping work packages; independent Critic, links, diff and frozen scope pass.
---

## Goal

Translate the user-authorized dynamic factor/strategy research direction into a
versioned, auditable execution contract before any new candidate formula enters
code or evaluation.

## Non-goals

- Do not change production code, factor formulas, strategy pointers or evidence grades.
- Do not reinterpret or overwrite the closed WP1-B/WP1-C results.
- Do not claim that recent unlabeled market data validates a strategy.
- Do not start a parameter scan, production integration or Agent prompt change.

## Invariants

- Every candidate predicts the same official target: decision close, one full
  trading-day embargo, entry open, twenty fixed-share trading days, final close.
- Historical replay reconstructs the entire selector from information available
  at each decision time; future outer results cannot build, tune or select it.
- `production_six_factor` remains production and T2 remains `RESEARCH_ONLY`.
- Market matrices stay server-side; Agents receive bounded, versioned research
  summaries and can act only through a deterministic selector/fusion contract.

## Locate brief

- Independent Scout confidence `0.93`; machine-readable artifact:
  `output/agent_handoffs/DYNAMIC-RESEARCH-PLAN-0805/location.json`.
- Located the static `StrategySpec`/`FactorCalculator` boundary, incomplete
  selector replay, missing PIT similarity schema and placeholder future-evidence
  checks in the disabled Agent overlay.
- Confirmed current direct/formal forward-return split is not a price-level proof
  of the official embargo/open/fixed-share/close evaluator.

## Implementation evidence

- `DEVELOPMENT_PLAN.md` advanced from 1.9.0 to 2.0.0 and applies to `4a3d812`
  descendants.
- Added WP1-E0 through E4 with exact first-round budgets: 12 trend factors,
  6 strategy slots, one prior-only similarity policy and A0/A1/A2 fusion.
- Frozen the official target, mature-label rule, production fallback, LLM action
  bounds, full-selector replay and separate promotion requirements.
- `VALIDATION.md` records only `DESIGN_ONLY`; `.claude/discussion.md` carries the
  current Windows handoff. No code, evidence grade or production pointer changed.

## Review evidence

- First independent Critic verdict `CHANGES_REQUIRED`: P1=4, P2=1. Findings
  covered fallback ambiguity, outer online-update semantics, exact minimum
  lookbacks, Agent call/proposal replay budgets and similarity tie-breaking.
- All five contracts were revised without expanding the frozen file scope;
  re-review closed every P1 and found one remaining P2 in the daily similarity
  key. `decision_date` is now the sole key inside the frozen policy/registry
  scope; snapshot/schema hashes are immutable bound attributes and conflicts
  fail closed.
- Final independent Critic verdict `ACCEPT`; open P0/P1/P2/P3 all zero. Review
  SHA-256: `3f89bad80820a83d60a4ac3b5dd572382e335f236f7182a9e63f9ccfc8ac4f1a`.
- Targeted current/history document contracts: `8 passed`. Full document file:
  `8 passed, 9 failed`; all nine are the recorded baseline `FileNotFoundError`
  for the absent out-of-scope resource Skill mirror. Modified Markdown links,
  `git diff --check` and frozen scope-check passed.

## Progress

- 2026-08-05T11:46:21+08:00 `DRAFT`: Task created from latest clean baseline `4a3d812`.
- 2026-08-05T11:52:38+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T11:52:39+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T11:57:49+08:00 `IMPLEMENTED`: Plan 2.0.0, current validation truth and handoff updated inside the frozen documentation scope.
- 2026-08-05T12:06:58+08:00 `IMPLEMENTED`: Closed four P1 and one P2 contract findings; refreshed task diff and scope-check (`violations=[]`).
- 2026-08-05T12:09:04+08:00 `IMPLEMENTED`: Closed re-review P2 by enforcing one similarity state per decision date with immutable snapshot/schema bindings.
- 2026-08-05T12:10:08+08:00 `REVIEWED`: Independent Critic final `ACCEPT`; no open finding.
- 2026-08-05T12:10:08+08:00 `VERIFIED`: Planner accepted targeted 8/8, known 9 baseline failures, links, diff and frozen scope.
- 2026-08-05T12:10:08+08:00 `CLOSED`: Plan task accepted for an isolated local commit; no production integration, package, tag or push.
