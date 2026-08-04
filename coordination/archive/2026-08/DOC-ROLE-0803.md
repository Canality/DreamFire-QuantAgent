---
id: DOC-ROLE-0803
title: Make fresh-session identity prompts current-only
status: CLOSED
risk: LOW
owner: Codex
created_at: 2026-08-03T09:28:48+08:00
updated_at: 2026-08-03T09:38:19+08:00
allowed_files:
  - AGENT_WORKFLOW.md
  - CLAUDE.md
acceptance:
  - No current identity prompt says '不再只是策略建议者'
  - Workflow explicitly forbids transition-history wording in fresh-session identity/fact context
  - scope-check exits 0
---

## Goal

Replace the historical-negation identity wording and codify that injected role/fact prompts contain only current responsibilities, permissions, objectives, and stop rules; keep transition history in versioned records.

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

- 2026-08-03T09:28:48+08:00 `DRAFT`: Task created.
- 2026-08-03T09:29:06+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-03T09:29:07+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-03T09:30:XX+08:00 `IMPLEMENTED`: Removed '不再只是"策略建议者"' from CLAUDE.md; scope-check passed.
- 2026-08-03T09:34:19+08:00 `IMPLEMENTED`: Qwen timed out after partial edit; Codex completed both current-only identity/fact documentation requirements. Assertions and scope-check pass.
- 2026-08-03T09:36:01+08:00 `REVIEWED`: Critic reviewed and ACCEPTed. All acceptance criteria satisfied.
- 2026-08-03T09:37:09+08:00 `VERIFIED`: Codex accepts the current-only identity/fact contract; Qwen critic ACCEPT verified against files and scope.
- 2026-08-03T09:38:19+08:00 `CLOSED`: Current-only identity/fact prompt rule verified and closed.
