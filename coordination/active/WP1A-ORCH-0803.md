---
id: WP1A-ORCH-0803
title: Remove generic planning noise from fixed quant team
status: BLOCKED
risk: HIGH
owner: Codex
created_at: 2026-08-03T13:24:00+08:00
updated_at: 2026-08-04T10:27:20+08:00
allowed_files:
  - jiuwenswarm/jiuwenswarm/agents/swarm/assembly.py
  - jiuwenswarm/jiuwenswarm/agents/swarm/config_specs.py
  - jiuwenswarm/tests/agents/swarm/test_swarm_assembly.py
acceptance:
  - A quant_team runtime receives only the minimal fixed-pipeline rails and the role-scoped Quant toolkit
  - Generic teams retain their existing rails and tools unchanged
  - TaskPlanning, skill evolution/retrieval, web, cron, filesystem, and unrelated tools cannot enter a quant_team member spec
  - Existing Alpha/Risk role tool boundaries remain enforced
  - Targeted assembly/guard tests, dual Ruff, py_compile, diff-check, scope-check, direct entry, and one formal entry are executed
---

## Goal

Prevent a fixed eight-stage quant run from being diverted by generic planning tools, while reducing the LLM tool schema and prompt surface.

## Non-goals

- No change to factor, selection, allocation, backtest, provider, or evidence semantics.
- No weakening of the repeated-call/no-progress guards.

## Invariants

- Generic JiuwenSwarm teams keep their current capability profile.
- Alpha and Risk & Evidence members retain only their role-owned Quant RPC at runtime.

## Locate brief

- `assembly.enrich_team_spec_for_swarm` knows the concrete team name and is the correct place to mark a quant team profile.
- `config_specs._build_team_capability_specs` owns declarative rails/tools and can select a minimal fixed profile before any runtime object exists.
- `test_swarm_assembly.py` already owns capability and named-template regression coverage.

## Implementation evidence

- Pending.

## Review evidence

- Pending.

## Progress

- 2026-08-03T13:24:00+08:00 `LOCATED`: Root cause reproduced: after fetch/factors, Leader called `update_task(cancelled)` six times and failed at 2/8. Scope localized to declarative team capability assembly.
- 2026-08-03T13:24:38+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-04T10:27:20+08:00 `BLOCKED`: Formal reached 8/8, but runtime chunks still contain build_team/create_task/view_task/claim_task/list_files and browser_agent/sys_operation injection; current 3-file implementation does not satisfy capability-removal acceptance
