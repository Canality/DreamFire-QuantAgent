---
id: SCOPE-IGNORE-0809
title: 修复 scope-check 忽略文件误报
status: CLOSED
risk: LOW
owner: Claude
created_at: 2026-08-09T13:25:13+08:00
updated_at: 2026-08-09T13:33:56+08:00
allowed_files:
  - jiuwenswarm/tests/unit_tests/quant/test_agent_task_cli.py
  - scripts/agent_task.py
acceptance:
  - baseline 未跟踪文件仅变为 ignored 且内容不变时不报 changed
  - baseline 文件内容改变或删除时仍报 changed/violation
  - scope-check 自身目标回归通过
---

## Goal

当 .gitignore 在任务内新增规则时，scope-check 对 baseline 已知且仍存在的文件继续重哈希，避免把仅变为 ignored 的未跟踪文件误判为越界，同时继续检测真实修改和删除。

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

- 2026-08-09T13:25:13+08:00 `DRAFT`: Task created.
- 2026-08-09T13:27:24+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-09T13:32:24+08:00 `IMPLEMENTED`: Baseline-known ignored files are safely rehashed; focused regressions, static checks and scope-check pass.
- 2026-08-09T13:33:22+08:00 `REVIEWED`: Codex independent diff review ACCEPT; no findings.
- 2026-08-09T13:33:56+08:00 `VERIFIED`: Codex independently reproduced 4 focused regressions, Ruff, py_compile, diff-check, and scope-check.
- 2026-08-09T13:33:56+08:00 `CLOSED`: Accepted and closed; tool fix ready for release commit.
