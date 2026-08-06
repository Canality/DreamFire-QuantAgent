---
id: WP1B-EVIDENCE-PIN-0806
title: Pin accepted WP1-B review evidence for clean checkouts
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T14:12:00+08:00
updated_at: 2026-08-06T14:30:00+08:00
allowed_files:
  - coordination/active/WP1B-EVIDENCE-PIN-0806.md
  - coordination/evidence/WP1B-EVALUATION-0804.review.json
  - jiuwenswarm/jiuwenswarm/quant/challenger_registry.py
  - jiuwenswarm/evaluation/challenger_round.py
  - jiuwenswarm/tests/unit_tests/quant/test_challenger_registry.py
  - jiuwenswarm/tests/unit_tests/quant/test_challenger_round.py
acceptance:
  - Scout proves the external source review is the exact previously accepted byte artifact; Planner pins those unchanged bytes in tracked coordination evidence, redirects only WP1-C dependency defaults/tests, preserves task-status, byte-hash, ACCEPT/zero-blocker and evaluation-hash gates, and clean-checkout challenger tests plus tamper/semantic-repin negatives, Ruff, pycompile, scope, diff and independent review pass without changing any candidate or production pointer.
---

## Goal

Remove the clean-checkout dependency on ignored `output/` by tracking the exact
accepted WP1-B review bytes that WP1-C already cryptographically requires.

## Non-goals

- Do not synthesize, reserialize or edit historical review evidence.
- Do not restore any other ignored output, logs or research artifacts.
- Do not change WP1-B conclusions, WP1-C candidates, T2 or production.

## Invariants

- Preserve the accepted byte SHA-256
  `35c72c69f1defe417cb218f84f0af55efb520b10af80883fe255e724e0b3284d`.
- Preserve the accepted evaluation hash
  `b1cd9a849bcbf53f1f32bad8363c623694782791f797e201f7aeda2296783099`.
- Missing, byte-tampered or semantically repinned evidence fails closed.

## Locate brief

- Validated Scout confidence `0.98`, SHA-256
  `11f42c7bb8fec4764a94be76a8629d874cb8d3feac89d4e35b16005c7d8a7db0`.
- Both challenger test modules currently produce 10 failures, all at the same
  missing ignored review path. The accepted external delivery source is 5,956
  bytes, UTF-8/LF and its SHA exactly matches the code and closed WP1-B task.
- Copy those bytes unchanged to `coordination/evidence/`; do not parse or
  reserialize. Redirect only runtime/test dependency defaults, retaining all
  four existing dependency gates and frozen registry payload/hash.

## Implementation evidence

- Copied the previously accepted 5,956-byte review artifact byte-for-byte from
  the audited external delivery into tracked `coordination/evidence/`; source
  and destination both hash to
  `35c72c69f1defe417cb218f84f0af55efb520b10af80883fe255e724e0b3284d`.
- Redirected only the WP1-C default review dependency and its tests to the
  tracked path. The frozen registry payload/hash, all candidates, T2 status and
  production pointer are unchanged.
- Added clean-checkout negatives for missing review evidence and semantic
  repinning of task id, verdict, blocker count and accepted evaluation hash.
- Focused registry/round tests: 19 passed. Full quant unit suite: 610 passed,
  1 skipped. Ruff and pycompile pass; existing interpreter-shutdown dependency
  ResourceWarnings remain visible and are not suppressed.

## Review evidence

- Independent Critic verdict `ACCEPT`; P0/P1/P2/P3 are empty and the blocking
  finding count is zero. It reconstructed a clean tree from `44acb51`, overlaid
  only the six whitelisted files, passed 19/19 focused and 610/610 broad tests,
  and independently verified the immutable source bytes and all semantic gates.
- Review SHA-256:
  `50385a0a33cc6e58965dde2f2500c687e951be8f851062ddf83aaef243a04123`.
- Windows must still verify the task commit/bundle chain before adopting it;
  this migration does not recompute WP1-B or promote T2.

## Progress

- 2026-08-06T14:12:00+08:00 `DRAFT`: Task created from clean-checkout broad-suite failure audit.
- 2026-08-06T14:14:00+08:00 `LOCATED`: Scout location validated; Planner froze
  an exact six-file evidence-copy/path/test boundary.
- 2026-08-06T14:15:42+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T14:27:00+08:00 `IMPLEMENTED`: Exact accepted evidence bytes are
  tracked, WP1-C resolves them in a clean checkout, semantic and byte-tamper
  gates remain fail closed, and 610 broad quant tests pass.
- 2026-08-06T14:29:00+08:00 `REVIEWED`: Independent clean-checkout Critic
  accepted the exact six-file task with no open P0-P3 finding.
- 2026-08-06T14:30:00+08:00 `VERIFIED/CLOSED`: Planner verified the accepted
  review, full-suite result, exact-byte provenance and unchanged research and
  production state. No push and no historical evidence overwrite.
