---
id: WINDOWS-P1-REPAIR-0804
title: Repair Windows P1 announcement health and immutable E2E binding
status: VERIFIED
risk: HIGH
owner: Codex
created_at: 2026-08-04T16:55:18+08:00
updated_at: 2026-08-04T17:28:12+08:00
allowed_files:
  - .agents/skills/verify-quant-e2e/scripts/audit_run_artifacts.py
  - .claude/discussion.md
  - VALIDATION.md
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/jiuwenswarm/extensions/quant-finance/extension.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/__init__.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/announcement_service.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/candidate_binding.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/package_builder.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/report_service.py
  - jiuwenswarm/scripts/generate_validation_summary.py
  - jiuwenswarm/scripts/run_quant_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_announcement_service.py
  - jiuwenswarm/tests/unit_tests/quant/test_direct_pipeline_adapter.py
  - jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_report_quality_gate.py
  - jiuwenswarm/tests/unit_tests/quant/test_run_multi_agent_validator.py
  - jiuwenswarm/tests/unit_tests/quant/test_validation_audit_binding.py
acceptance:
  - A required 49-ticker all-empty announcement result cannot pass without bounded retry plus an independent health/negative-control outcome; direct result persists terminal-cause diagnostics.
  - Direct and formal candidate outputs are immutable and run-scoped; direct results and formal summary bind candidate path, manifest/report hashes, announcement/disclosure counts, and snapshot identity.
  - E2E audit rejects stale results mixed with a later mutable candidate and passes only when direct/formal bindings match immutable artifacts.
  - Negative regressions, target tests, Ruff, py_compile, diff-check, scope-check, independent Critic, fresh direct/formal, and independent audit pass; historical evidence is preserved.
---

## Goal

Fail closed on implausible universe-wide announcement emptiness and bind direct/formal verification to immutable run-scoped candidate artifacts without erasing historical evidence.

## Non-goals

- No unrelated refactor.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- P1-1 root: `quant/reporting/announcement_service.py` accepts a required
  49-ticker universe when every provider result is empty. The direct and formal
  adapters call it without a required-universe contract, and the direct result
  omits per-ticker terminal causes and universe-health attempts.
- P1-1 call sites: `scripts/run_quant_pipeline.py` and
  `extensions/quant-finance/extension.py`; regression seam:
  `tests/unit_tests/quant/test_announcement_service.py` plus both adapter tests.
- P1-2 root: `package_builder.py` clears and rewrites the single mutable
  `output/submission_candidate` directory. Direct post-processing,
  `run_multi_agent.py`, and `audit_run_artifacts.py` all hard-code that path.
- P1-2 repair seam: allocate `submission_candidates/<run-id>` once, persist a
  cryptographic candidate binding (snapshot, manifests, report tree and
  disclosure counts), place that binding in direct results and the formal
  summary, and make the audit independently resolve and verify both paths.
- `generate_validation_summary.py` must require the bound independent audit for
  every `BUSINESS_PASSED` state; otherwise a stale direct result can still be
  promoted outside the E2E audit.
- Historical `output/submission_candidate` and prior handoffs remain read-only.
- No WP1-B/WP1-C file or task is in scope.

## Implementation evidence

- Required 49-ticker announcement collection now treats a universe-wide empty
  primary attempt as unhealthy, retries the whole universe with a fresh
  provider, and fails closed on a second empty attempt. The direct failure
  result retains both attempts, all per-ticker terminal causes, request/page
  counts, parse failures, and the universe terminal cause.
- Report candidates are create-once directories under
  `output/submission_candidates/<candidate-id>`. Direct and formal results bind
  their exact candidate path, candidate ID, snapshot manifest hash, report and
  evidence manifest hashes, report-tree hashes, and report/announcement/
  disclosure/evidence counts in `candidate_binding.json`.
- The independent audit resolves direct and formal candidates separately,
  recomputes every binding, rejects the legacy mutable path and shared
  candidates, and requires result/summary hashes and counts to match before the
  validation summary can emit `BUSINESS_PASSED`.
- Focused regression: 55 passed. Changed-file Ruff, py_compile, diff-check and
  frozen scope-check passed. Historical `output/submission_candidate` retained
  its `2026-08-04 15:27:34 +0800` mtime; no WP1-B/WP1-C file was touched.

## Review evidence

- Independent Critic verdict: `ACCEPT`, with no P0/P1/P2 findings. Review record:
  `output/agent_handoffs/WINDOWS-P1-REPAIR-0804/CRITIC_REVIEW.json`.
- Fresh direct result `output/pipeline_results_20260804_172026.json` passed with
  49/49 stocks, 15 holdings, 6 sectors, 5.06% cash, +0.7476% return, 1.6424%
  maximum drawdown, 1,470 announcement facts and a bound immutable candidate
  `direct-20260804_172026`.
- Fresh formal session `multi-agent-validation-20260804-172234` passed 8/8
  phases, 16 tool calls, 0 errors, exact once-only phase execution, three-role
  participation and no role-RPC violations. It binds immutable candidate
  `formal-multi-agent-validation-20260804-172234`.
- Independent audit `output/audit_result_multi-agent-validation-20260804-172234.json`
  passed with no failures. Direct binding SHA-256 is
  `f506e5f5f2123590a98728e7139fd3612041e07c90ba319aa1cf3e4588877e88`;
  formal binding SHA-256 is
  `a2db8f2b377f494adc65cc51fd95b66535e92c55001548c4f9a7c159a9650072`.

## Progress

- 2026-08-04T16:55:18+08:00 `DRAFT`: Task created.
- 2026-08-04T17:02:14+08:00 `LOCATED`: Scout accepted at confidence 0.99; both Windows P1 roots and the BUSINESS_PASSED propagation seam are localized.
- 2026-08-04T17:02:14+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-04T17:02:15+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-04T17:14:56+08:00 `IMPLEMENTED`: Both P1 repairs implemented. 55 focused tests passed; Ruff, py_compile, diff-check, and frozen scope-check passed. Awaiting independent Critic.
- 2026-08-04T17:20:12+08:00 `REVIEWED`: Independent Critic ACCEPT: no P0/P1/P2 findings; 55 focused tests passed; both Windows P1 contracts and no-WP1-B/C scope verified.
- 2026-08-04T17:28:12+08:00 `VERIFIED`: Planner accepted both P1 repairs: independent Critic ACCEPT; 55 focused tests, Ruff, py_compile, diff-check, and frozen scope-check pass; fresh direct/formal and recomputed immutable candidate-binding audit pass; historical evidence preserved and WP1-B/WP1-C untouched.
