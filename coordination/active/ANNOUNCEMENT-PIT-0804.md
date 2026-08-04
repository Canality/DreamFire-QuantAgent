---
id: ANNOUNCEMENT-PIT-0804
title: Restore historical PIT announcement coverage
status: BLOCKED
risk: HIGH
owner: Goone
created_at: 2026-08-04T12:07:57+08:00
updated_at: 2026-08-04T12:56:21+08:00
allowed_files:
  - .claude/discussion.md
  - README.md
  - VALIDATION.md
  - jiuwenswarm/jiuwenswarm/quant/reporting/announcement_service.py
  - jiuwenswarm/jiuwenswarm/quant/reporting/providers/announcement.py
  - jiuwenswarm/tests/unit_tests/quant/test_announcement_service.py
  - jiuwenswarm/tests/unit_tests/quant/test_direct_pipeline_adapter.py
  - jiuwenswarm/tests/unit_tests/quant/test_extension_cache_pipeline.py
  - jiuwenswarm/tests/unit_tests/quant/test_provider_contract.py
acceptance:
  - Historical fixtures retrieve the latest bounded eligible announcements from later pages and never admit post-as-of evidence.
  - Per-ticker diagnostics distinguish events found, true empty, no event before as-of, upstream failure, parse failure, and pagination exhaustion.
  - Direct and formal adapter tests prove announcement facts and EvidenceRefs reach their report bundles.
  - Target pytest, Ruff, py_compile, git diff --check, and scope-check pass.
  - A real 49-ticker PIT smoke and both direct/formal plus independent E2E audit determine the final evidence grade; no business-passed claim without all required artifacts.
---

## Goal

Replace single-page post-filtering with bounded point-in-time pagination and auditable terminal-cause diagnostics, then prove disclosure evidence reaches direct and formal report bundles.

## Non-goals

- No unrelated refactor.
- Do not change report-grade policy, quality-gate thresholds, Agent RPCs, portfolio logic, or the provisional submission contract.

## Invariants

- Preserve AGENTS.md and project safety contracts.
- Future evidence remains excluded using conservative Asia/Shanghai availability time.
- A pagination cap, malformed page, or exhausted retry must not be reported as true no-event.
- direct/formal continue to share the same Provider and AnnouncementService implementation.

## Locate brief

- Accepted from `ANNOUNCEMENT-SCOUT-0804`: direct/formal and report wiring exist; the reproducible defect is fixed page 1 plus post-fetch historical PIT filtering.
- The repair boundary is the Provider, shared service, four focused tests, and post-validation status documents listed in the frozen whitelist.

## Implementation evidence

- `output/agent_handoffs/ANNOUNCEMENT-PIT-0804/implementation.json` records the test-first failures, review-counterexample repairs, `69 passed, 1 skipped` target suite, static checks, and current real-run evidence.
- Server-side `end_time` narrows historical retrieval, client-side conservative PIT remains authoritative, and incomplete pagination/upstream/parse paths have distinct fail-closed diagnostics.
- After throttling cleared, one bounded 49-ticker smoke returned `1470` eligible facts with `49/49` complete/event-bearing tickers, zero parse failures, `pit_verified=true`, and an archive matching the manifest.
- The direct run `output/pipeline_results_20260804_124850.json` exited 0 and propagated `1470` announcement facts for all `49/49` tickers into the candidate report path.
- Two formal attempts stopped after the workflow retry limit. Both loaded `jiuwen_team` instead of the requested project `quant_team`; the second completed valid 8/8 RPC execution and produced 49 disclosures, but failed exact-role participation (`quant-leader=0`). Overall E2E acceptance therefore remains blocked on explicit team selection.

## Review evidence

- Four independent Critic rounds are recorded under `output/agent_handoffs/ANNOUNCEMENT-PIT-0804/`; rounds one through three supplied concrete fail-closed counterexamples that were repaired and added as regressions.
- `review_round4.json` verdict is `ACCEPT` with no findings; the focused offline suite was `69 passed, 1 skipped`.
- This accepts the provider/service implementation only. It does not override the failed formal/E2E result.

## Progress

- 2026-08-04T12:07:57+08:00 `DRAFT`: Task created.
- 2026-08-04T12:08:47+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-04T12:08:48+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-04T12:21:56+08:00 `IMPLEMENTED`: Test-first provider/service implementation complete; business verification remains open due upstream HTTP 567 throttling.
- 2026-08-04T12:46:57+08:00 `REVIEWED`: Round-four independent Critic ACCEPT; 69 passed, 1 skipped; business E2E remains unproved.
- 2026-08-04T13:00:00+08:00 `BLOCKED`: Real 49-ticker smoke and direct path reached 49/49; two formal attempts selected `jiuwen_team` instead of `quant_team`, so end-to-end acceptance moved to a separate orchestration task.
- 2026-08-04T12:56:21+08:00 `BLOCKED`: Provider/service implementation and independent review accepted; real 49-ticker smoke and direct path are 49/49, but formal E2E twice selected jiuwen_team instead of quant_team, so end-to-end acceptance is blocked on explicit formal team selection.
