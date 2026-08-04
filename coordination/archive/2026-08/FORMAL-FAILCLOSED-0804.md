---
id: FORMAL-FAILCLOSED-0804
title: Reject any unsuccessful formal quant RPC
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-04T10:25:00+08:00
updated_at: 2026-08-04T10:27:20+08:00
allowed_files:
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/tests/unit_tests/quant/test_run_multi_agent_validator.py
  - coordination/active/FORMAL-FAILCLOSED-0804.md
acceptance:
  - Any quant RPC payload with success=false or invalid business fields makes the formal run fail immediately
  - A later successful retry cannot erase an earlier failed RPC
  - The formal prompt requires strict fetch-to-report serialization
  - Targeted tests, Ruff, py_compile, and diff-check exit 0
---

## Goal

Close the validator gap reproduced by session `multi-agent-validation-20260804-101054`, where an early failed `quant.compute_factors` call was hidden by a later successful retry and the process exited 0.

## Non-goals

- No strategy, market-data, factor, selection, allocation, backtest, or report changes.
- No redesign of openJiuwen's intrinsic team coordination tools.

## Evidence

- Reproduction: `phase_request_counts.factors=2`, first payload `success=false`, final `validation_passed=true`.
- Implementation and review evidence pending.
- 2026-08-04T10:27:20+08:00 `VERIFIED`: 2 regression tests, Ruff, py_compile, diff-check pass; formal session multi-agent-validation-20260804-102234 completed strict 8/8 with one request/execution per phase and no issues
- 2026-08-04T10:27:20+08:00 `CLOSED`: Accepted as validator fail-closed fix; full E2E remains failed on missing disclosure evidence
