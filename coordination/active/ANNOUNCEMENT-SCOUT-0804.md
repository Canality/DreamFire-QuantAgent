---
id: ANNOUNCEMENT-SCOUT-0804
title: Locate zero announcement and disclosure coverage
status: CLOSED
risk: HIGH
owner: Missed
created_at: 2026-08-04T10:37:48+08:00
updated_at: 2026-08-04T12:07:37+08:00
allowed_files:
acceptance:
  - location.json distinguishes not-called, upstream failure, true no-data, PIT filtering, parse failure, and missing report integration
  - lists definitions, callers, tests, reproducible commands, and a minimal proposed write whitelist without modifying source
---

## Goal

Read-only localization of the 0/49 announcement/disclosure evidence failure across provider registration, PIT filtering, fetch, parse, cache, archive, report, quality gate, and independent audit.

## Non-goals

- No unrelated refactor.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- direct/formal 均显式调用 `AnnouncementService`，并把 `event_facts` 与公告 `EvidenceRef` 传入候选包；排除未调用、未注册和报告漏接。
- `AnnouncementProvider._fetch_page()` 固定 `page_index=1`、`page_size=30`，`fetch_rich()` 随后才按历史 `as_of_time` 过滤；非空最新页被全部过滤后错误返回 `AVAILABLE_NO_EVENT`。
- 2026-08-04 只读复现：49/49 最新页请求成功，共 1,470 条，日期与标题均可解析，但截至 2025-04-18 合格条目为 0；`600000` 第 5 页有 27 条合格记录，`000001` 第 4/5 页分别有 3/30 条。
- 上游异常只映射为无原因 `UNAVAILABLE`，空响应、全未来、全解析失败都缺少独立终止原因；技术质量门仅告警，独立 E2E audit 才将 0 披露判为业务失败。
- 建议新建 HIGH 风险修复任务，冻结 Provider、服务、两条适配回归测试的最小白名单；不改变质量分级语义。

## Implementation evidence

- Pending.

## Review evidence

- Pending.

## Progress

- 2026-08-04T10:37:48+08:00 `DRAFT`: Task created.
- 2026-08-04T12:06:13+08:00 `LOCATED`: Planner accepted read-only localization: single-page PIT regression reproduced; source remains unchanged.
- 2026-08-04T12:07:37+08:00 `VERIFIED`: Planner independently reproduced 49/49 page-1 PIT filtering and sampled eligible records on later pages.
- 2026-08-04T12:07:37+08:00 `CLOSED`: Read-only localization accepted; implementation moves to ANNOUNCEMENT-PIT-0804.
