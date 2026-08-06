---
id: WP0A-DOC-CONTRACT-0806
title: Close generated documentation and Skill mirror contracts
status: CLOSED
risk: MEDIUM
owner: Codex
created_at: 2026-08-06T09:58:00+08:00
updated_at: 2026-08-06T10:21:00+08:00
allowed_files:
  - README.md
  - coordination/active/WP0A-DOC-CONTRACT-0806.md
  - jiuwenswarm/jiuwenswarm/extensions/quant-finance/skills/quant-investment/SKILL.md
  - jiuwenswarm/jiuwenswarm/resources/agent/workspace/skills/quant-investment/SKILL.md
  - jiuwenswarm/scripts/generate_validation_summary.py
  - jiuwenswarm/tests/unit_tests/quant/test_document_contract.py
  - jiuwenswarm/tests/unit_tests/quant/test_validation_audit_binding.py
acceptance:
  - The workspace and packaged quant-investment Skills are present and byte-identical.
  - README current status fields are machine-checked against a generated validation summary.
  - Deliberate README drift fails and generation cannot promote VALIDATION without bound real-run evidence.
  - Focused document and validation binding tests, Ruff, scope-check and git diff --check pass.
---

## Goal

Close WP0-A by restoring the packaged Skill mirror and making the README status
summary a deterministic, testable projection of current validation evidence.

## Non-goals

- Do not change any investment, Agent, Provider or submission behavior.
- Do not claim a new direct/formal run or raise an evidence grade.
- Do not rewrite append-only history.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- `VALIDATION.md` remains the current fact source; generated artifacts cannot
  create or promote validation facts.
- The workspace Skill and runtime resource mirror must not drift.

## Locate brief

- Read-only roadmap Scout evidence plus Planner reproduction found `26 collected:
  17 passed, 9 failed`; all failures are the missing runtime Skill mirror.
- Validated location confidence `0.98`, SHA-256
  `0dfc1e36902f1382892c5fa16359ce5ad2273aeb70059b933a1d68e2ee777cb1`.
- The second gap is latent: README only links the generated summary and the test
  blacklists four old numbers. Freeze a generated block renderer/checker and
  fail-closed unaudited-status tests; keep `VALIDATION.md` outside write scope.

## Implementation evidence

- Added the byte-identical runtime Skill mirror and removed two stale overlap
  statistics from the canonical/mirror pair.
- Added one machine-owned README block plus deterministic render/check/update
  functions. Missing local artifacts remain `NOT_GENERATED`; unaudited but
  otherwise successful paths remain `NOT_TESTED`, never `BUSINESS_PASSED`.
- Focused result `32 passed` (baseline `17 passed, 9 failed`); Ruff, exact Skill
  comparison, README CLI check, wheel-content check, scope-check and diff-check
  all pass. `VALIDATION.md` is unchanged at SHA-256
  `e7f1e0b6984738b4b92e5440d3c0c62ba76af7d1d594b231077846f87e1387b7`.

## Review evidence

- First independent review found one P1: artifact-derived README claims could
  bypass the generated block. The bounded closure removed those claims and
  added an external-prose regression contract.
- Final Critic verdict `ACCEPT`, P0/P1/P2/P3=`0/0/0/0`; review SHA-256
  `83bc0f2f0ae073b278590219773ead1d62f5c9ce91bd3931932a844b3b087bee`.

## Progress

- 2026-08-06T09:58:00+08:00 `DRAFT`: Task created from the independent WP0 acceptance audit (`196 passed, 1 skipped, 9 failed`).
- 2026-08-06T10:08:00+08:00 `LOCATED`: Planner validated the locate evidence and froze a seven-file docs-only boundary.
- 2026-08-06T10:08:04+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T10:13:00+08:00 `IMPLEMENTED`: WP0-A implementation passes focused, packaging and fail-closed checks; awaiting independent Critic review.
- 2026-08-06T10:17:00+08:00 `IMPLEMENTED`: Critic P1 confirmed README prose bypassed the generated block; removed all current-run counts/verdicts outside the block and added a regression guard. Closure suite is `33 passed`.
- 2026-08-06T10:21:00+08:00 `CLOSED`: Planner accepted the zero-finding closure review and verified the seven-file frozen scope and unchanged validation fact source.
