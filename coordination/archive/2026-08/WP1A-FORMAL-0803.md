---
id: WP1A-FORMAL-0803
title: Wire formal Extension to shared MarketDataBundle
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-03T12:25:55+08:00
updated_at: 2026-08-03T12:48:58+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/snapshot_writer.py
  - jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_snapshot_writer.py
acceptance:
  - Formal fetch no longer calls legacy _fetch_real_data and caches one validated bundle plus diagnostics
  - Partial or blocked bundle returns success=false and no raw frames enter cache or LLM output
  - compute/select/allocate/backtest/report consume server-owned cache unchanged
  - Report EvidenceRef binds the new manifest hash and installs all nine snapshot files
  - Report snapshot stops at the factor decision date and records a reproducible diagnostic policy of at least 61 rows
  - Extension target tests, Ruff, py_compile, diff-check, and scope-check exit 0
---

## Goal

Make quant.fetch_data construct and diagnose the shared MarketDataBundle, cache it server-side, return only compact diagnostics, and make report generation persist/install the new immutable snapshot; preserve all downstream server-owned phase semantics.

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

- 2026-08-03T12:25:55+08:00 `DRAFT`: Task created.
- 2026-08-03T12:26:23+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-03T12:26:25+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-03T12:38:00+08:00 `READY`: Scope expanded to snapshot writer/tests after causal review proved that the default 81-row archive policy rejected a valid 61+-row decision-time evidence slice; original baseline hashes are retained.
- 2026-08-03T12:45:19+08:00 `IMPLEMENTED`: Codex implementation complete: 51 tests pass; real Extension fetch 49/49 and live eight-stage pipeline/candidate pass. Awaiting independent critic.
- 2026-08-03T12:48:58+08:00 `REVIEWED`: Independent DeepSeek critic wrote parseable review.json with ACCEPT; Codex checked the artifact and residual risks.
- 2026-08-03T12:48:58+08:00 `VERIFIED`: Codex verified 51 tests, dual Ruff, py_compile, diff/scope checks, live 49/49 fetch, and live eight-stage Extension pipeline.
- 2026-08-03T12:48:58+08:00 `CLOSED`: Accepted as formal Extension adapter LOCAL_IMPLEMENTED with live handler evidence; full run_multi_agent remains separately unproven.
