---
id: WP1-E2
title: 多 lookback 候选与 prior-only 相似市场策略池
status: CLOSED
risk: HIGH
owner: Claude
created_at: 2026-08-09T13:47:58+08:00
updated_at: 2026-08-11T17:35:45+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/strategy_pool.py
  - jiuwenswarm/tests/unit_tests/quant/test_strategy_pool.py
acceptance:
  - 精确注册 production_six_factor、t2_comparator、trend_short_5_10_20、trend_medium_20_60、trend_long_120_250、similar_market_blend 六槽位
  - production_six_factor 唯一生产资格与硬回退不变，其他槽位不得静默改 production
  - 短中长期槽位复用已注册 12 个趋势候选并统一预测官方 embargo/open/20-session/close 目标
  - 相似市场仅使用 expanding prior、median/MAD、至少 60 个历史状态、5 个成熟且不重叠邻居，并按 distance/decision_date/market_snapshot_hash 稳定排序
  - benchmark 缺失、MAD 为零或邻居不足只关闭相似分支并给出 reason code；基础研究契约失败才硬回退 production
  - direct/formal 两路径调用边界与负向时序测试被枚举；本任务只产生 RESEARCH_ONLY 证据
---

## Goal

在不改变 production_six_factor 生产指针的前提下，实现六槽位 RESEARCH_ONLY 策略池及失败关闭的 prior-only 相似市场分支，为 WP1-E3/E4 提供确定性可回放候选。

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

- 2026-08-09T13:47:58+08:00 `DRAFT`: Task created.
- 2026-08-09T13:58:19+08:00 `LOCATED`: Write scope approved by Codex.
- 2026-08-09T13:58:21+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-09T14:09:21+08:00 `BLOCKED`: Two tool-driven Claude attempts stopped with zero source changes; implementation-method challenge recorded.
- 2026-08-09T14:09:22+08:00 `READY`: Codex MODIFY: authorize one tool-free task-scoped DeepSeek patch attempt under same frozen baseline.
- 2026-08-09T14:14:37+08:00 `BLOCKED`: Umbrella split after bounded Claude/OpenCode Go/DS execution attempts produced no source changes; proceed via WP1-E2A then WP1-E2B.
- 2026-08-11T17:35:45+08:00 `CLOSED`: Successor tasks E2A/E2B/E2P-R1/E2T-R1/E2C-R1 closed the strategy-pool, typed-evidence and deterministic-replay scope at LOCAL_IMPLEMENTED / RESEARCH_ONLY; production remains unchanged.
