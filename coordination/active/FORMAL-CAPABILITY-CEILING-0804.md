---
id: FORMAL-CAPABILITY-CEILING-0804
title: Enforce fixed quant runtime capability ceiling
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-04T13:35:45+08:00
updated_at: 2026-08-04T15:38:33+08:00
allowed_files:
  - .claude/discussion.md
  - README.md
  - VALIDATION.md
  - jiuwenswarm/jiuwenswarm/agents/swarm/assembly.py
  - jiuwenswarm/jiuwenswarm/agents/swarm/config_specs.py
  - jiuwenswarm/jiuwenswarm/agents/swarm/providers/member_rails.py
  - jiuwenswarm/jiuwenswarm/agents/swarm/registry.py
  - jiuwenswarm/tests/agents/swarm/test_swarm_assembly.py
acceptance:
  - quant_team and its session-scoped form materialize no browser/general subagents, skills, MCPs, task planning, skill discovery, task loop, file/shell/sys-operation rail, task-board/team-management, web, cron, or unrelated tools
  - fixed leader and both analyst roles retain their existing role-owned Quant RPC boundary and send_message only as the team coordination tool
  - generic team provider and DeepAgentSpec behavior remain unchanged
  - pinned openJiuwen compatibility assumptions fail closed under unit tests and no .venv file is modified
  - target tests, Ruff, py_compile, diff-check, scope-check, fresh direct, fresh formal, and independent E2E audit are recorded
---

## Goal

Keep exactly the role-owned Quant toolkit and send_message in quant_team while removing inherited browser/subagent/skill/task-loop and generic task-board policy capabilities without changing generic teams or .venv.

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

- 2026-08-04T13:35:45+08:00 `DRAFT`: Task created.
- 2026-08-04T13:36:43+08:00 `LOCATED`: Scout accepted at confidence 0.98; fixed-context provider/spec adapter localized to four project modules plus one test file; docs reserved for post-verification updates.
- 2026-08-04T13:36:43+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-04T13:36:43+08:00 `READY`: Exact eight-file whitelist and per-file baselines frozen; implementation authorized, dependency files remain read-only evidence only.
- 2026-08-04T13:46:14+08:00 `IMPLEMENTED`: Project-layer fixed-context ceiling implemented. 153 target tests passed; Ruff, py_compile, diff-check, and scope-check passed; .venv untouched. Awaiting independent Critic review before formal verification.
- 2026-08-04T14:21:51+08:00 `IMPLEMENTED`: Critic round 1 MODIFY addressed: exact canonical quant identity prevents prefix capture; serialized/recovered contexts retain and validate the fixed discriminator. 156 target tests passed; Ruff, py_compile, diff-check, scope-check passed. Awaiting re-review.
- 2026-08-04T14:26:58+08:00 `REVIEWED`: Independent Critic round 2 ACCEPT: 16 focused tests; serialization/recovery ceiling, exact team identity, discriminator fail-closed behavior, role-owned Quant boundary, send_message-only coordination, generic pass-through, and pinned compatibility verified.
- 2026-08-04T14:34:14+08:00 `IMPLEMENTED`: Fresh formal attempt exposed TeamAgentConfigurator injecting core.sys_operation/core.team.workspace after enrichment; fail-closed stopped 0/8 before LLM. Runtime adapter now allowlists only fixed prompt/safety rails, bounded team tool/policy, and observability. Added formal-shape regression. 157 target tests, Ruff, py_compile, diff-check, scope-check pass; awaiting re-review before rerun.
- 2026-08-04T14:42:58+08:00 `REVIEWED`: Independent Critic round 3 ACCEPT: 15 focused tests plus role probes. Fixed formal-shape resolution has no SysOperationRail/TeamWorkspaceRail/SkillUseRail/SubagentRail/TaskPlanningRail; fs/code/shell deny; TeamTool only send_message with no workspace manager; fixed policy and role-owned Quant RPCs preserved; generic unchanged.
- 2026-08-04T14:50:55+08:00 `IMPLEMENTED`: Formal attempt 2 exposed framework-internal workspace bootstrap requiring fs(). Added an unregistered workspace-root-sandboxed internal FS, kept code/shell denied, and added no-tool-card/no-SysOperationRail boundary regression. 158 target tests, Ruff, py_compile, diff-check, and scope-check pass; prior review invalidated, awaiting fresh Critic.
- 2026-08-04T15:02:31+08:00 `IMPLEMENTED`: Critic round 4 MODIFY addressed: fixed context no longer falls back to process CWD; missing, empty, or whitespace-only member workspace now fails closed, while explicit roots are normalized and remain the sole sandbox root. Added three negative regressions and exact sandbox assertions. 161 target tests and all static/scope checks pass; awaiting round 5 re-review.
- 2026-08-04T15:04:13+08:00 `REVIEWED`: Independent Critic round 5 ACCEPT: round4 workspace/CWD HIGH closed; None/empty/whitespace workspace fails closed, explicit resolved root is the sole restricted sandbox. Focused 9 passed; no new findings. Formal-shaped rail stripping, code/shell denial, no FS/shell cards, send_message-only, generic pass-through, and pinned fail-closed remain intact.
- 2026-08-04T15:10:22+08:00 `IMPLEMENTED`: Invalidated formal attempt crossed workspace initialization and reached Quant/send_message, then exposed pinned openJiuwen only registers predefined members through build_team. Added fixed-leader server-side exact three-member roster bootstrap before first model call; build_team remains absent from agent tools. Wrong/missing roster fails closed. 163 target tests and all static/scope checks pass; prior review invalidated, awaiting round 6.
- 2026-08-04T15:15:16+08:00 `REVIEWED`: Independent Critic round 6 ACCEPT: fixed leader bootstraps the exact roster before first model call, recovery skips duplicate build but revalidates, teammate never bootstraps, wrong/missing roster fails closed, agent TeamTool remains send_message-only, and generic behavior delegates unchanged. Focused 6 passed.
- 2026-08-04T15:20:54+08:00 `IMPLEMENTED`: Valid-date formal attempt registered the exact roster and delivered both messages, but predefined analysts remained UNSTARTED because the fixed TeamToolRail dropped openJiuwen's on_teammate_created runtime handle. Preserved exactly that callback without restoring allocator/workspace/spawn/task tools; regression asserts callback identity and send_message-only surface. Target 163 passed; Ruff, py_compile, diff-check, and scope-check passed. Round 6 invalidated; awaiting independent round 7 review.
- 2026-08-04T15:26:11+08:00 `REVIEWED`: Independent Critic round 7 ACCEPT with no findings. Focused 6 passed; behavior probe proved send_message awaits backend startup with the identical on_teammate_created callback before delivery. Callback only starts registered UNSTARTED roster members; no allocator/workspace/swarmflow/spawn/build/clean/async/task tools were restored, and generic provider remains direct upstream delegation.
- 2026-08-04T15:32:02+08:00 `VERIFIED`: Post-fix direct passed 49/49 with 1470 announcement facts and Quality PASSED. Formal session multi-agent-validation-20260804-152646 passed 8/8 with exact-once execution, 0 errors/cache hits, three-role participation, role RPC 1/1 and no violations. Independent audit audit_result_multi-agent-validation-20260804-152646.json passed. VALIDATION.md updated first, then README and current discussion; full report remains FINANCIAL_PARTIAL and submission contract remains blocked.
- 2026-08-04T15:38:33+08:00 `CLOSED`: All frozen acceptance criteria passed: independent Critic round 7 ACCEPT; target/static/scope checks passed; post-fix direct and formal passed; independent E2E audit passed; VALIDATION.md, README, and current discussion updated. Local task-only baseline/head refs and Windows handoff package prepared; no push.
