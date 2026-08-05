---
id: LEGACY-ROLE-CLEANUP-0805
title: Remove active legacy role compatibility and refresh project truth
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-05T09:40:00+08:00
updated_at: 2026-08-05T10:12:09+08:00
allowed_files:
  - .claude/discussion.md
  - .claude/skills/explain-change.md
  - AGENTS.md
  - CLAUDE.md
  - DEVELOPMENT_PLAN.md
  - README.md
  - VALIDATION.md
  - coordination/active/LEGACY-ROLE-CLEANUP-0805.md
  - coordination/active/WINDOWS-P1-REPAIR-0804.md
  - coordination/active/WP1B-EVALUATION-0804.md
  - jiuwenswarm/evaluation/policy_validator_prototype.py
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/jiuwenswarm/agents/swarm/providers/tools.py
  - jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py
  - jiuwenswarm/jiuwenswarm/quant/agent_structured_output.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/__init__.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/agent_view_parser.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/company_report.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/models.py
  - jiuwenswarm/jiuwenswarm/quant/roles/alpha_analyst.md
  - jiuwenswarm/jiuwenswarm/quant/roles/coordinator.md
  - jiuwenswarm/jiuwenswarm/quant/roles/risk_evidence_analyst.md
  - jiuwenswarm/jiuwenswarm/quant/team_config.py
  - jiuwenswarm/tests/agents/swarm/test_swarm_assembly.py
  - jiuwenswarm/tests/unit_tests/quant/test_agent_structured_output.py
  - jiuwenswarm/tests/unit_tests/quant/test_agent_view_parser.py
  - jiuwenswarm/tests/unit_tests/quant/test_document_contract.py
  - jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_report_models.py
  - jiuwenswarm/tests/unit_tests/quant/test_report_quality_gate.py
acceptance:
  - Active team, RPC, parser, report and prompt paths expose only Coordinator, Alpha Analyst and Risk & Evidence Analyst; legacy roles fail closed; market-regime labels and historical evidence remain; focused tests, direct/formal/E2E, independent Critic and frozen scope pass.
---

## Goal

Delete the remaining active compatibility layer for the retired analyst roles,
align current architecture documentation, and publish an isolated local code
version for Windows re-verification.

## Non-goals

- Do not change factor formulas, selection, allocation, backtest or promotion logic.
- Do not rewrite market-regime `bull` / `bear` / `range` labels.
- Do not delete or overwrite historical experiments, evidence, archives or prior
  Windows delivery packages.
- Do not bump the upstream JiuwenSwarm package version, tag or push.

## Invariants

- Formal team remains exactly Coordinator + Alpha Analyst + Risk & Evidence Analyst.
- Formal Extension remains exactly eight deterministic quant RPC handlers.
- Alpha and Risk & Evidence proposals are advisory; Coordinator-owned cached
  select / allocate / backtest / report stages remain authoritative and fail closed.
- `VALIDATION.md` is updated only after current-commit verification; README and
  discussion summarize it afterward.

## Locate brief

- Independent read-only Scout confidence: 0.98.
- Current RPC registry and runtime members already use Alpha/Risk, but active
  persona loading, parser/export adapter, report-model compatibility, report
  renderer, Coordinator prompt and POC/current documentation retain old identities.
- Preserve all market-regime and historical-evidence occurrences. Delete only
  source symbols and branches with no current caller, then add rejection tests.
- Location artifact: `output/agent_handoffs/LEGACY-ROLE-CLEANUP-0805/location.json`.

## Implementation evidence

- Deleted the retired-role persona loads, short aliases, pair parser/export,
  `AgentView` compatibility branches, report-renderer branches and two dead
  structured-output schemas. Unsupported view roles now fail closed.
- Rewrote the current Coordinator role contract and aligned current code/docs;
  retained market-regime `bull` / `bear` / `range` and immutable history.
- Independent Critic identified and root fixed one P1: report generation now
  requires both current analyst cache entries to parse cleanly before any
  artifact write; four missing/corrupt-cache negative cases fail closed.
- Focused regression: 61 passed; position constraints: 6 passed; changed-file
  Ruff passed. Quant suite: 422 passed, 1 skipped, 9 known baseline failures
  caused by the absent out-of-scope resource skill mirror.
- Post-P1 direct exited 0 (`pipeline_results_20260805_100118.json`); formal
  exited 0 (`multi-agent-validation-20260805-100147`, exact 8/8, 12 tool calls,
  no role violation); independent E2E audit exited 0 and passed both bindings.

## Review evidence

- Independent Critic verdict `ACCEPT`; open P0/P1/P2/P3 findings all zero.
- The one early P1 was resolved by required dual-current-view parsing before
  artifact writes and verified with four negative cases plus fresh dual paths.
- Review artifact:
  `output/agent_handoffs/LEGACY-ROLE-CLEANUP-0805/review.json`;
  SHA-256 `e04e34ddebf462d10d219fb1bd3162cabe48f53dd84f7a468c8b1c2f103eabfd`.

## Progress

- 2026-08-05T09:40:00+08:00 `DRAFT`: Task created from accepted read-only Scout localization.
- 2026-08-05T09:36:06+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T09:36:43+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-05T09:36:43+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-05T10:05:00+08:00 `IMPLEMENTED`: Bounded deletion, current-doc refresh and fresh direct/formal/E2E verification complete; independent Critic pending.
- 2026-08-05T10:10:00+08:00 `REVIEWED`: Independent Critic ACCEPT; one early P1 resolved and reverified; no open finding.
- 2026-08-05T10:11:44+08:00 `VERIFIED`: Planner accepted 61 focused tests, Ruff, py_compile, diff/scope checks, fresh direct/formal and the independent E2E audit.
- 2026-08-05T10:12:09+08:00 `CLOSED`: v2.14 task scope accepted for isolated local commit and Windows handoff; no tag or push authorized.
