---
id: WP1-E2A
title: 六槽位研究策略池注册表
status: CLOSED
risk: MEDIUM
owner: Claude
created_at: 2026-08-09T14:15:10+08:00
updated_at: 2026-08-09T15:32:38+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/quant/strategy_pool.py
  - jiuwenswarm/tests/unit_tests/quant/test_strategy_pool.py
acceptance:
  - 精确六槽位顺序与名称固定
  - production_six_factor 是唯一 production-qualified hard fallback
  - 短中长期槽位 factor union 精确等于现有 12 个 Factor Registry ID，目标统一 20 sessions
  - t2_comparator 绑定 phase_b_t2_score_alloc，研究模块不被 direct/formal 或 quant/__init__ 导入
  - 聚焦测试、Ruff、py_compile、diff-check、scope-check 通过
---

## Goal

新增独立不可变六槽位研究注册表，绑定现有 12 个因子和唯一 20 日目标，并以负向测试证明不改变生产指针或 production callers。

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

- 2026-08-09T14:15:10+08:00 `DRAFT`: Task created.
- 2026-08-09T14:15:28+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-09T14:19:20+08:00 `BLOCKED`: Claude/OpenCode Go/DS one-shot patch exceeded configured budget (reported $0.805 vs $0.10 cap) and returned no patch; stopped to protect cost.
- 2026-08-09T14:25:34+08:00 `READY`: User authorized unrestricted OpenCode Go plan usage; resume full Claude/DS execution under frozen scope.
- 2026-08-09T15:32:08+08:00 `IMPLEMENTED`: Local Claude/DS patch applied; Codex corrected factor_id extraction and test root mechanically; focused validation passed.
- 2026-08-09T15:32:38+08:00 `REVIEWED`: Codex independent diff review: ACCEPT, no findings.
- 2026-08-09T15:32:38+08:00 `VERIFIED`: Focused tests, Ruff, compile, isolation scan, diff-check, and scope-check passed.
- 2026-08-09T15:32:38+08:00 `CLOSED`: Accepted immutable six-slot research registry; production pointer and callers unchanged.
