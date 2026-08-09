---
id: GITHUB-PUBLISH-0809
title: 公开 GitHub 发布整理与安全修复
status: CLOSED
risk: MEDIUM
owner: Claude
created_at: 2026-08-09T13:14:57+08:00
updated_at: 2026-08-09T13:46:05+08:00
allowed_files:
  - .gitignore
  - DEVELOPMENT_PLAN.md
  - README.md
  - VALIDATION.md
  - jiuwenswarm/jiuwenswarm/resources/config.yaml
  - 策略实验/进展报告/2026-08-09_GitHub发布前进展摘要.md
acceptance:
  - HEAD 高置信 secret 扫描无实值凭据
  - README 与 VALIDATION 的 v2.15 Windows 状态一致
  - 本机 .codex 与 codex-opencode-go 启动脚本保持未跟踪且被忽略
  - 不将 SubmissionContract 提升为 CONFIRMED，不生成正式比赛提交包
  - CRLF-aware git diff --check、目标测试、direct/formal/E2E 按发布门执行
---

## Goal

移除公开默认配置中的实值 API key，纠正 README 当前事实，排除本机 Codex 启动文件，生成 2026-08-09 进展摘要，并保留正式比赛提交阻塞边界。

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

- 2026-08-09T13:14:57+08:00 `DRAFT`: Task created.
- 2026-08-09T13:19:08+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-09T13:35:29+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-09T13:36:31+08:00 `IMPLEMENTED`: Codex re-froze baseline after accepted scope utility fix; redacted original release diff is preserved and scope-check passes.
- 2026-08-09T13:40:19+08:00 `REVIEWED`: Codex review decision MODIFY: record fresh direct evidence and formal/E2E Not tested boundary.
- 2026-08-09T13:40:20+08:00 `READY`: MODIFY authorized within existing VALIDATION/progress-report whitelist; baseline remains frozen.
- 2026-08-09T13:42:10+08:00 `IMPLEMENTED`: Recorded fresh direct as PATH_PASSED; formal/E2E remain Not tested without safe credentials; document contract and scope-check pass.
- 2026-08-09T13:43:18+08:00 `READY`: Second MODIFY: correct direct command and artifact path bases only.
- 2026-08-09T13:44:44+08:00 `IMPLEMENTED`: Corrected fresh direct command to jiuwenswarm-working-directory form and output artifacts to repository-root-relative form; document and scope checks pass.
- 2026-08-09T13:46:04+08:00 `REVIEWED`: Codex final independent review ACCEPT after two resolved documentation findings.
- 2026-08-09T13:46:05+08:00 `VERIFIED`: Independent tests, secret/ignore/diff gates and fresh direct PATH_PASSED reproduced; formal/E2E Not tested boundary recorded.
- 2026-08-09T13:46:05+08:00 `CLOSED`: Public GitHub release preparation accepted; ready to commit and push.
