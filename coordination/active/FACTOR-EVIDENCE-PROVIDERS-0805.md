---
id: FACTOR-EVIDENCE-PROVIDERS-0805
title: Build auditable research evidence providers
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T14:05:18+08:00
updated_at: 2026-08-05T14:42:38+08:00
allowed_files:
  - .claude/discussion.md
  - DEVELOPMENT_PLAN.md
  - VALIDATION.md
  - coordination/active/FACTOR-EVIDENCE-PROVIDERS-0805.md
  - jiuwenswarm/jiuwenswarm/quant/candidate_factors.py
  - jiuwenswarm/jiuwenswarm/quant/factor_evidence_provider.py
  - jiuwenswarm/jiuwenswarm/quant/factor_research.py
  - jiuwenswarm/tests/unit_tests/quant/test_candidate_factors.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_evidence_provider.py
  - jiuwenswarm/tests/unit_tests/quant/test_factor_research.py
acceptance:
  - Scout identifies exact authoritative source/archive boundaries and missing evidence; Planner freezes explicit schemas, source versions and file scope; negative tests prove future, mutable, incomplete, caller-injected and non-canonical evidence fails closed; any claim of real readiness is backed by repository-held bytes and recomputable hashes; E0/E1 research tests, independent Critic, diff and scope checks pass; production_six_factor, T2, WP1-C and direct/formal remain unchanged.
---

## Goal

Locate and implement the smallest research-only Provider boundary that can turn repository-held, point-in-time source archives into canonical calendar, official 1+20 forward-label, PIT sector and trusted E0 snapshot evidence without caller self-attestation or production integration.

## Non-goals

- Do not download or invent exchange calendars, corporate-action histories,
  adjusted prices, historical sector classifications or per-ticker ledgers.
- Do not promote the tracked Sina snapshot, static `SECTOR_MAP` or caller-supplied
  path/hash to a trusted E0/E1 source.
- Do not construct E2 candidates, alter production/T2/WP1-C, or integrate with
  direct/formal/Agent entry points.

## Invariants

- Public readiness inspection accepts no path, hash, authority, source version
  or allowlist argument. Repository-relative sources and expected digests are
  owned by one research-only Provider module.
- Every pinned file is resolved below the repository root, must be a regular
  non-symlink file, and is rehashed from bytes. Snapshot directory membership,
  JSON manifest digest, manifest-declared child hashes and frozen metadata must
  agree before source bytes can be described as verified.
- Verified source bytes are not automatically admissible research evidence.
  Calendar, sector, forward-label, corporate-action and E0-snapshot capabilities
  each have an explicit `AVAILABLE/UNAVAILABLE` disposition and reason codes.
- Central E0/E1 trust-key and E0-snapshot sets remain immutable and empty in
  this task. E0/E1 call the shared Provider boundary; tests may replace it only
  through explicit test-only monkeypatching.
- Preserve AGENTS.md, official 1+20 causality, exact 49/6 scope and all existing
  project safety contracts.

## Locate brief

- Independent Scout artifact
  `output/agent_handoffs/FACTOR-EVIDENCE-PROVIDERS-0805/location.json` validates
  with confidence `0.89`; recommended risk remains `HIGH`.
- The only tracked OHLC archive is
  `jiuwenswarm/evaluation/data_snapshots/sina_20260721_135352`: manifest SHA-256
  `59bc1092018cc21894f3e331ee708d6644ed7669297f2f011cff6ab267518961`,
  open SHA-256 `b3f33a2e4af92db2f4906f0337424ab9a41dcda804db5d9f10766aee45b87a74`
  and close SHA-256
  `1aaeec24f2811a707268736b2b2b88b9c0ccbf07a6ca6885b742a864208fff18`.
  It is explicitly `raw/unadjusted`, has a global Sina source and no per-ticker
  provenance ledger or official exchange calendar.
- The canonical contest Excel is tracked at `赛题文档/上市公司列表.xlsx`, SHA-256
  `c021d69b5c3bf3ea0c4626811df5ed9a02cd4c67e1068ad2f0ce35d759210617`.
  Planner inspection confirms 49 names in six columns, but the file contains no
  historical effective/observed timestamps or classification version chain.
- No tracked PIT corporate-action archive, point-in-time adjusted-price archive,
  official SSE/SZSE session archive, historical sector archive or real research
  trust manifest exists. This task therefore implements a deterministic
  readiness/audit boundary and must finish `DATA_BLOCKED`, not fabricate a real
  manifest or enter E2.

## Frozen inventory and dispositions

- Inventory id `wp1_factor_evidence_inventory_v1`; exact artifacts are the
  contest Excel plus all seven files in the single tracked Sina snapshot.
- `SOURCE_BYTES`: verifiable only when all fixed paths, file-set membership,
  SHA-256 values and frozen manifest metadata match.
- `CANONICAL_CALENDAR`: `UNAVAILABLE_NO_OFFICIAL_CALENDAR_ARCHIVE`.
- `PIT_SECTOR`: `UNAVAILABLE_NO_HISTORICAL_SECTOR_VERSION`.
- `OFFICIAL_FORWARD_LABEL`: `UNAVAILABLE_RAW_NO_LEDGER_OR_CALENDAR`.
- `PIT_CORPORATE_ACTION`: `UNAVAILABLE_NO_CORPORATE_ACTION_ARCHIVE`.
- `E0_FACTOR_SNAPSHOT`: `UNAVAILABLE_UNADJUSTED_INPUT_AND_EMPTY_TRUST_ROOT`.
- E1 readiness is false unless every prerequisite is available; no partial
  capability may populate an E0/E1 trust key.

## Implementation evidence

- Test-first collection failed with `ImportError` while
  `factor_evidence_provider` did not exist; 0 tests collected.
- Added one research-only fixed inventory for the canonical contest Excel and
  seven tracked Sina snapshot files. It rejects caller path/hash injection,
  missing/tampered/symlinked files, unexpected directory members, manifest
  metadata/child-hash mismatches and forged membership without an available
  capability.
- E0 and E1 now consult the single Provider-owned trust boundary instead of
  separate module-local sets. Runtime evidence keys and E0 snapshot hashes are
  immutable empty frozensets; existing unit fixtures use explicit test-only
  function monkeypatches rather than changing production roots.
- Current fixed bytes verify: inventory SHA-256
  `80ed930703975460726ee73d1fc48844c00754227b53c7def5f07a1489cef0a7`,
  audit SHA-256
  `9c5829f78756e8efd8d050a1b3a5f4ca89b6a2493620f217741e3ea973db7a8f`.
  All five research capabilities remain unavailable, `ready_for_e0=false` and
  `ready_for_e1=false`.
- Provider negatives `6 passed`; Provider+E0+E1 research `45 passed`; provider,
  Registry, E0/E1, market-data, submission-contract and snapshot-writer adjacent
  regression `114 passed`; changed-file Ruff and pycompile pass.
- The full quant directory collected 481 tests: `461 passed, 1 skipped,
  19 failed`. The same 19 known failures require ignored WP1-B review artifacts
  and the out-of-scope resource Skill mirror; none is in this task's frozen
  files. The focused/adjacent suites are green, but the full suite is not
  reported as passing.

## Review evidence

- Independent Critic final verdict `ACCEPT`; P0/P1/P2/P3 are `0/0/0/0`.
- Critic independently reran Provider `6/6`, research `45/45`, adjacent
  `114/114`, Ruff, pycompile, diff check and exact `10/10` scope.
- Final patch binding is recorded in
  `output/agent_handoffs/FACTOR-EVIDENCE-PROVIDERS-0805/review.json`; its digest
  is reported outside the tracked diff to avoid a self-referential review hash.

## Progress

- 2026-08-05T14:05:18+08:00 `DRAFT`: Task created.
- 2026-08-05T14:13:40+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T14:13:48+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T14:26:50+08:00 `IMPLEMENTED`: Fixed 8-file source inventory, central fail-closed E0/E1 trust boundary and DATA_BLOCKED capability audit implemented; Provider 6/6, research 45/45, adjacent 114/114, Ruff and pycompile pass; Critic pending.
- 2026-08-05T14:42:38+08:00 `REVIEWED`: Independent Critic ACCEPT; P0/P1/P2/P3=0/0/0/0; final binding is recorded in the task review artifact.
- 2026-08-05T14:42:38+08:00 `VERIFIED`: Provider 6/6, research 45/45, adjacent 114/114, Ruff, pycompile, diff and exact scope passed; result remains DATA_BLOCKED.
- 2026-08-05T14:42:38+08:00 `CLOSED`: Closed LOCAL_IMPLEMENTED / DATA_BLOCKED; no production or E2 integration.
