---
id: FORMAL-TEAM-SELECT-0804
title: Select the exact project quant_team in formal validation
status: CLOSED
risk: HIGH
owner: Goone
created_at: 2026-08-04T12:57:37+08:00
updated_at: 2026-08-04T13:17:30+08:00
allowed_files:
  - .claude/discussion.md
  - README.md
  - VALIDATION.md
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/jiuwenswarm/agents/harness/team/config_loader.py
  - jiuwenswarm/jiuwenswarm/agents/harness/team/team_manager.py
  - jiuwenswarm/tests/unit_tests/agentserver/test_team_config_loader.py
  - jiuwenswarm/tests/unit_tests/agentserver/test_team_manager_registry.py
  - jiuwenswarm/tests/unit_tests/quant/test_run_multi_agent_validator.py
acceptance:
  - A negative regression proves multiple configured teams no longer select the first unrelated team.
  - The formal validator requests quant_team through a public explicit-selection path and validates quant-leader, alpha_analyst, and risk_evidence_analyst before Runner execution.
  - Focused config-loader, TeamManager/formal-validator tests, Ruff, py_compile, git diff --check, and scope-check pass.
  - A fresh direct log, formal run, and independent artifact audit determine final E2E status; no pass claim on partial evidence.
---

## Goal

Make the formal validator request quant_team explicitly, preserve unrelated user teams, and fail closed before Runner execution when the resolved leader/member identities differ from the frozen quant roles.

## Non-goals

- No unrelated refactor.
- Do not delete or reorder unrelated user teams.
- Do not change quant RPCs, portfolio logic, provider behavior, or report-grade policy.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- Callers that do not request a team retain the existing first-team default.
- An explicit missing or mismatched team fails before `Runner.run_agent_team_streaming`.

## Locate brief

- `output/agent_handoffs/FORMAL-TEAM-SELECT-0804/location.json` validated at confidence `0.99`.
- The formal validator refreshed `quant_team` in the user config but `load_team_spec_dict` always chose the first `modes.team` entry. Both failed formal logs showed the resulting generic `team-leader`/zero-member spec.
- The minimal repair boundary is an optional exact selector in the loader and TeamManager, plus a formal-only exact identity guard.

## Implementation evidence

- `output/agent_handoffs/FORMAL-TEAM-SELECT-0804/implementation.json` records five test-first failures, the repairs, focused passing regressions, and the pre-existing unrelated config-template test failure.
- A real no-LLM spec probe resolved `quant_team_formal-team-selection-probe`, leader `quant-leader`, and exactly `alpha_analyst` plus `risk_evidence_analyst`.
- Ruff with the file's pre-existing bootstrap `E402` exception, py_compile, diff-check, and scope-check pass.

## Review evidence

- `review.json` verdict `MODIFY`：指出重复角色被 set 吞掉、空白 selector 回退、session 规范化分叉和 Runner 前测试证明不足。
- 四项均补负向回归并修复；`review_round2.json` verdict `ACCEPT`，无新 findings。目标集合为 `71 passed, 2 skipped`，另有 1 个已披露的基线前配置模板失败被排除。

## Verification evidence

- 最新 direct `output/pipeline_results_20260804_131305.json` 与持久化日志退出 0，公告/披露 49/49。
- formal session `multi-agent-validation-20260804-131332` 真实加载精确 team/leader/two members，证明本任务目标通过生产入口；随后因白名单外的通用 task-board 能力噪声在 0/8 失败关闭。
- 独立 audit `output/audit_result_multi-agent-validation-20260804-131332.json` 退出 1，完整 E2E 保持 `BUSINESS_FAILED`；后继阻断归属 `WP1A-ORCH-0803`。

## Progress

- 2026-08-04T12:57:37+08:00 `DRAFT`: Task created.
- 2026-08-04T12:58:30+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-04T12:58:30+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-04T13:03:23+08:00 `IMPLEMENTED`: Test-first exact team selection and pre-Runner identity guard implemented; focused regressions, real spec probe, static checks, and scope-check pass; pending independent Critic and fresh E2E.
- 2026-08-04T13:12:46+08:00 `REVIEWED`: Round-two independent Critic ACCEPT after all four round-one findings were repaired; 71 passed, 2 skipped with one disclosed pre-baseline config-template test deselected; proceed to fresh direct/formal/audit acceptance.
- 2026-08-04T13:17:30+08:00 `VERIFIED`: Exact formal quant_team selection verified in real session multi-agent-validation-20260804-131332; direct passed, formal/audit failed only on successor capability-ceiling scope; VALIDATION updated before README and discussion.
- 2026-08-04T13:17:30+08:00 `CLOSED`: Task goal complete and independently accepted; end-to-end business status remains failed and is handed to WP1A-ORCH-0803.
