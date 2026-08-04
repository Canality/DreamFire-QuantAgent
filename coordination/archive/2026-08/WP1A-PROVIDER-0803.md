---
id: WP1A-PROVIDER-0803
title: Build shared five-source market data provider
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-03T11:50:16+08:00
updated_at: 2026-08-03T12:13:02+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/market_data_provider.py
  - jiuwenswarm/tests/unit_tests/quant/test_market_data_provider.py
acceptance:
  - Real provider adapters preserve progressive per-ticker fallback instead of whole-batch fallback
  - Canonical OHLCV and volume units are explicit and tested
  - Independent secondary close evidence exists for every ticker or the build fails closed
  - Benchmark and point-in-time boundaries are explicit
  - Provider target tests, Ruff, py_compile, and scope-check exit 0
---

## Goal

Locate, then implement a shared provider layer that builds a complete MarketDataBundle with OHLCV, per-ticker provenance, independent secondary overlap, benchmark evidence, explicit units, and fail-closed coverage; do not wire direct/formal entries in this task.

## Non-goals

- No unrelated refactor.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Pending.

## Implementation evidence

- Pending.

## Review evidence

- Decision: ACCEPT. All 5 acceptance criteria verified against source and test evidence. No actionable defects found.
- Review artifact: `output/agent_handoffs/WP1A-PROVIDER-0803/review.json`

## Progress

- 2026-08-03T11:50:16+08:00 `DRAFT`: Task created.
- 2026-08-03T11:53:50+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-03T11:53:52+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-03T12:03:36+08:00 `IMPLEMENTED`: Codex bounded implementation complete: 12 provider tests and 53 related tests pass; dual Ruff, py_compile, diff-check, and scope-check pass. No entry-path claim.
- 2026-08-03T12:15:00+08:00 `REVIEWED`: Critic (Qwen) reviewed in fresh session. Decision ACCEPT — all 5 acceptance criteria verified. No actionable defects. Scope-check passed. Residual risks documented.
- 2026-08-03T12:13:02+08:00 `VERIFIED`: DeepSeek independent review ACCEPT; final 53 related tests, Ruff, diff-check, and scope-check pass. Real isolated 49/49 primary + 49/49 independent secondary + CSI300 diagnostics passed; no entry-path claim.
- 2026-08-03T12:13:02+08:00 `CLOSED`: Closed as verified shared-provider foundation. Direct/formal adapter migration, richer snapshot persistence, and corporate-action policy remain separate tasks.
